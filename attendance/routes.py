from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Cliente, Asistencia,Acciones,TipoAccion
from sqlalchemy import func
from datetime import datetime, timedelta, date
from collections import defaultdict

attendance_bp = Blueprint("attendance", __name__, url_prefix="/attendance")

# En attendance/routes.py

@attendance_bp.get("/")
@login_required
def list_attendance():
    f_cliente = request.args.get("cliente","").strip()
    f_desde = request.args.get("desde")
    f_hasta = request.args.get("hasta")
    
    q = Asistencia.query.join(Cliente)
    
    # 1. Aplicar filtro de búsqueda por cliente
    if f_cliente:
        like = f"%{f_cliente}%"
        q = q.filter(
            (Cliente.nombre.ilike(like)) | 
            (Cliente.apellido.ilike(like)) | 
            (Cliente.cedula.ilike(like))
        )

    # 2. Aplicar filtros de rango de fechas
    # Se añade la comprobación de fecha y la conversión a date
    if f_desde:
        try:
            f_desde_dt = datetime.strptime(f_desde, '%Y-%m-%d').date()
            q = q.filter(Asistencia.hora_entrada >= f_desde_dt)
        except ValueError:
            pass # Ignora si la fecha es inválida

    if f_hasta:
        try:
            f_hasta_dt = datetime.strptime(f_hasta, '%Y-%m-%d').date()
            q = q.filter(Asistencia.hora_entrada < f_hasta_dt + timedelta(days=1))
        except ValueError:
            pass # Ignora si la fecha es inválida
        
    # 3. Obtener y ordenar los registros (más reciente primero)
    items = q.order_by(Asistencia.hora_entrada.desc()).all()
    
    # 4. AGREGAR LÓGICA CRÍTICA: Agrupar los items por fecha
    asistencias_agrupadas = defaultdict(list)
    for item in items:
        # Extraer solo la fecha y formatearla como string (ej: "2025-11-20")
        fecha_str = item.hora_entrada.strftime('%Y-%m-%d') if item.hora_entrada else 'Fecha Desconocida'
        asistencias_agrupadas[fecha_str].append(item)

    # 5. Pasar el diccionario agrupado al template (SOLUCIÓN AL ERROR)
    return render_template("attendance_list.html", 
                           asistencias_agrupadas=asistencias_agrupadas, 
                           cliente=f_cliente, 
                           desde=f_desde, 
                           hasta=f_hasta)


@attendance_bp.get("/api/search_clients") # Se usa attendance_bp por conveniencia
@login_required
def search_clients_ajax():
    # 1. Obtener el término de búsqueda (query)
    query = request.args.get('q', '').strip()
    
    # 2. Construir la consulta de búsqueda
    clients = []
    if query and len(query) >= 2: # Solo buscar si hay al menos 2 caracteres
        search_term = f"%{query}%"
        clients = Cliente.query.filter(
            (Cliente.nombre.ilike(search_term)) | 
            (Cliente.apellido.ilike(search_term)) |
            (Cliente.cedula.ilike(search_term))
        ).limit(20).all() # Limitar a 20 resultados
    else:
        # Opcional: Si la query es muy corta, no devuelve resultados para ahorrar recursos
        return jsonify(results=[])

    # 3. Formatear los resultados para Select2
    results = []
    for client in clients:
        results.append({
            # 'id' es el valor que se enviará en el formulario (ID_cliente)
            'id': client.ID_cliente, 
            # 'text' es lo que verá el usuario en el buscador
            'text': f"{client.apellido}, {client.nombre} (C.I: {client.cedula or 'N/A'})"
        })
        
    return jsonify(results=results)

@attendance_bp.get("/new")
@login_required
def new_attendance():
    clients = Cliente.query.order_by(Cliente.nombre.asc()).all()
    return render_template("attendance_form.html", clients=clients)

@attendance_bp.post("/save")
@login_required
def save_attendance():
    # 1. CAPTURAR DATOS COMUNES Y DETERMINAR ACCIÓN
    action_type = request.form.get("action_type") # entry, exit, manual_complete
    funcionario_id = current_user.ID_funcionario
    
    try:
        client_id = int(request.form.get("client_id"))
    except (TypeError, ValueError):
        flash("Debe seleccionar un cliente válido.", "danger")
        return redirect(url_for("attendance.list_attendance"))

    now = datetime.now()
    
    accion_exitosa = False
    log_tipo_id = None 
    log_desc = None
    
    # DATOS ESPECÍFICOS DEL FORMULARIO MANUAL
    fecha_asistencia_str = request.form.get("fecha_asistencia") # Fecha del día olvidado
    hora_salida_str = request.form.get("hora_salida")
    
    # ---------------------------------------------------------------
    # 🎯 1. REGISTRO MANUAL SOLO SALIDA (Asistencia olvidada)
    # ---------------------------------------------------------------
    if action_type == 'manual_complete':
        
        # Validación de datos mínimos para la corrección de salida
        if not fecha_asistencia_str or not hora_salida_str:
            flash("Para la corrección manual, debe proporcionar la Fecha y la Hora de Salida.", "danger")
            return redirect(url_for("attendance.list_attendance"))

        try:
            fecha_asistencia = datetime.strptime(fecha_asistencia_str, '%Y-%m-%d').date()
            # Combinamos fecha y hora para obtener un datetime completo de la salida
            hora_salida_manual = datetime.strptime(f"{fecha_asistencia_str} {hora_salida_str}", '%Y-%m-%d %H:%M')
            
        except ValueError:
            flash("Formato de fecha u hora incorrecto. Use YYYY-MM-DD y HH:MM.", "danger")
            return redirect(url_for("attendance.list_attendance"))

        # 1. Buscar un registro de entrada abierto para esa fecha específica
        registro_abierto = Asistencia.query.filter(
        Asistencia.ID_cliente == client_id,
        func.date(Asistencia.hora_entrada) == fecha_asistencia,
        Asistencia.hora_salida.is_(None) # SOLO BUSCAMOS REGISTROS SIN SALIDA
    ).first()

        if registro_abierto:
            
            # Validación de que la salida manual sea posterior a la entrada registrada
            if hora_salida_manual <= registro_abierto.hora_entrada:
                flash("La hora de salida manual es anterior o igual a la hora de entrada ya registrada.", "danger")
                return redirect(url_for("attendance.list_attendance"))
            
            # ACTUACIÓN: Actualizar la hora de salida del registro existente
            registro_abierto.hora_salida = hora_salida_manual
            registro_abierto.observaciones = f"Salida manual corregida por Funcionario ID {funcionario_id}"
            
            flash(f"Salida manual ({hora_salida_str}) aplicada al registro de entrada del {fecha_asistencia_str}.", "success")
            accion_exitosa = True
            log_tipo_id = 2 # MODIFICAR
            log_desc = f"Salida manual corregida para Cliente ID {client_id} en fecha {fecha_asistencia_str}."
        
        else:
                # MENSAJE CLARO SI NO ENCUENTRA REGISTRO ABIERTO
                # (Esto incluye si el registro ya estaba cerrado)
                registro_existente = Asistencia.query.filter(
                    Asistencia.ID_cliente == client_id,
                    func.date(Asistencia.hora_entrada) == fecha_asistencia,
                ).first()

                if registro_existente and registro_existente.hora_salida is not None:
                    flash("Este registro de asistencia ya estaba cerrado (tiene hora de salida).", "danger")
                else:
                    flash(f"No se encontró un registro de entrada abierto para el cliente ID {client_id} en la fecha {fecha_asistencia_str}.", "danger")
                return redirect(url_for("attendance.list_attendance"))
                    
            # 3. Actualizar la hora de salida del registro existente
        registro_abierto.hora_salida = hora_salida_manual
            
    # ---------------------------------------------------------------
    # 🎯 2. REGISTRO AUTOMÁTICO/POR BOTÓN (Entrada/Salida con hora actual)
    # ---------------------------------------------------------------
    else:
        # Aquí se mantiene tu lógica actual para los botones 'entry' y 'exit'
        today = now.date() 
        registro_abierto = Asistencia.query.filter(
            Asistencia.ID_cliente == client_id,
            func.date(Asistencia.hora_entrada) == today,
            Asistencia.hora_salida.is_(None)
        ).first()
        
        if action_type == 'entry':
            # --- CASO ENTRADA ---
            if registro_abierto:
                flash("Ya existe un registro de ENTRADA abierto para este cliente hoy.", "warning")
            else:
                item = Asistencia(
                    ID_cliente=client_id, 
                    hora_entrada=now, 
                    hora_salida=None, 
                    observaciones="Registro por botón de ENTRADA",
                    ID_funcionario=funcionario_id
                )
                db.session.add(item)
                flash("¡Entrada registrada con éxito!", "success")
                accion_exitosa = True
                log_tipo_id = 1 # CREAR
                log_desc = f"Entrada registrada por botón para Cliente ID {client_id}."
                
        elif action_type == 'exit':
            # --- CASO SALIDA ---
            if registro_abierto:
                if now.time() <= registro_abierto.hora_entrada.time():
                    flash("La hora de salida debe ser posterior a la de llegada.", "danger")
                else:
                    registro_abierto.hora_salida = now
                    flash("¡Salida registrada con éxito!", "success")
                    accion_exitosa = True
                    log_tipo_id = 2 # MODIFICAR
                    log_desc = f"Salida registrada por botón para Cliente ID {client_id}."
            else:
                flash("No se puede registrar la SALIDA. No hay una entrada abierta hoy.", "danger")
        
        else:
             flash("Acción de asistencia no reconocida.", "danger")

    # ---------------------------------------------------------------
    # 🎯 AUDITORÍA Y COMMIT FINAL
    if accion_exitosa and log_tipo_id:
        log = Acciones(
            ID_funcionario=funcionario_id,
            tabla_afectada='Asistencia',
            ID_tipo_accion=log_tipo_id, 
            descripcion=log_desc
        )
        db.session.add(log)
        
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Error al guardar la asistencia y el log en la base de datos.", "danger")
            
    return redirect(url_for("attendance.list_attendance"))