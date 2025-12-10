from flask import Blueprint, render_template, request, send_file, flash, redirect, url_for
from flask_login import login_required
from extensions import db
from models import Cliente, DetallePago, Asistencia, Rutina, Suscripcion, Funcionario, Acciones, TipoAccion 
from sqlalchemy import func
import pandas as pd
from utils_excel import df_to_excel_download
from io import BytesIO
from datetime import date, timedelta, datetime

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")

@reports_bp.get("/central")
@login_required
def central():
    """Vista central de reportes, KPIs y clientes morosos."""
    
    # ... (Lógica de central) ...

    # 2. CLIENTES MOROSOS (Requisito 1.4 de Pagos: Clientes sin suscripción activa vigente a hoy)
    today = date.today()
    morosos = []
    
    for c in Cliente.query.filter_by(activo=True).all(): 
        s = (Suscripcion.query
             .filter_by(ID_cliente=c.ID_cliente)
             .order_by(Suscripcion.fecha_vencimiento.desc())
             .first())
             
        if not s or s.fecha_vencimiento < today or s.estado != 'Activa':
            morosos.append(c)

    return render_template("reports_central.html",
                           total_clientes = Cliente.query.filter_by(activo=True).count(),
                           total_rutinas=Rutina.query.count(),
                           total_asistencias=Asistencia.query.count(),
                           total_pagos=db.session.query(func.coalesce(func.sum(DetallePago.monto), 0)).scalar() or 0,
                           morosos=morosos)

# --- REQUISITOS 1.2 Y 1.4 DE ASISTENCIA (Reportes de Frecuencia) ---
@reports_bp.get("/asistencia_frecuencia", endpoint="attendance_frequency_report")
@login_required
def attendance_frequency_report():
    """Genera reportes de frecuencia de asistencia por día y por cliente."""
    
    fecha_hoy = date.today()
    fecha_30_dias_atras = fecha_hoy - timedelta(days=30)

    f_desde_str = request.args.get("desde") or fecha_30_dias_atras.strftime('%Y-%m-%d')
    f_hasta_str = request.args.get("hasta") or fecha_hoy.strftime('%Y-%m-%d')
    
    try:
        f_desde_obj = datetime.strptime(f_desde_str, '%Y-%m-%d').date()
        f_hasta_obj = datetime.strptime(f_hasta_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Formato de fecha inválido. Usando rango por defecto.", "danger")
        f_desde_obj = fecha_30_dias_atras
        f_hasta_obj = fecha_hoy
        f_desde_str = f_desde_obj.strftime('%Y-%m-%d')
        f_hasta_str = f_hasta_obj.strftime('%Y-%m-%d')

    # 1. Frecuencia Diaria Global (Requisito 1.2)
    frecuencia_diaria = (db.session.query(
        func.date(Asistencia.hora_entrada).label('dia'),
        func.count(Asistencia.ID_asistencia).label('total_visitas')
    ).filter(
        func.date(Asistencia.hora_entrada) >= f_desde_obj, 
        func.date(Asistencia.hora_entrada) <= f_hasta_obj
    ).group_by('dia')
    .order_by('dia')
    .all())

    # 2. Frecuencia por Cliente (Requisito 1.4)
    frecuencia_cliente = (db.session.query(
        Cliente.nombre, Cliente.apellido, Cliente.cedula,
        func.count(Asistencia.ID_asistencia).label('total_visitas')
    ).join(Asistencia)
    .filter(
        func.date(Asistencia.hora_entrada) >= f_desde_obj,
        func.date(Asistencia.hora_entrada) <= f_hasta_obj
    ).group_by(Cliente.ID_cliente, Cliente.nombre, Cliente.apellido, Cliente.cedula)
    .order_by(func.count(Asistencia.ID_asistencia).desc())
    .all())
    
    return render_template("reports_attendance_frequency.html", 
                           frecuencia_diaria=frecuencia_diaria,
                           frecuencia_cliente=frecuencia_cliente,
                           desde=f_desde_str, 
                           hasta=f_hasta_str)



@reports_bp.get("/auditoria")
@login_required
def auditoria_log():
    """Muestra el historial completo de acciones del sistema."""
    # Nota: Solo los administradores deberían ver esto en un sistema real.
    # require_admin() # Descomentar si tienes la función para restringir acceso
    
    # Capturar filtros
    f_usuario = request.args.get("usuario", "").strip()
    f_tabla = request.args.get("tabla", "").strip()
    f_desde = request.args.get("desde")
    
    q = Acciones.query.join(Funcionario).join(TipoAccion)
    
    # Aplicar filtros de búsqueda
    if f_usuario:
        like = f"%{f_usuario}%"
        q = q.filter((Funcionario.nombre.ilike(like)) | (Funcionario.apellido.ilike(like)) | (Funcionario.usuario.ilike(like)))
    
    if f_tabla:
        q = q.filter(Acciones.tabla_afectada == f_tabla)
        
    if f_desde:
        try:
            f_desde_dt = datetime.strptime(f_desde, '%Y-%m-%d').date()
            q = q.filter(Acciones.fecha_accion >= f_desde_dt)
        except ValueError:
            pass
            
    # Obtener los últimos 100 registros, ordenados por fecha descendente
    logs = q.order_by(Acciones.ID_accion.desc()).limit(100).all()
    
    # Obtener todas las tablas únicas para el selector de filtro (si lo necesitas)
    tablas_unicas = db.session.query(Acciones.tabla_afectada).distinct().all()
    
    return render_template("reports_auditoria.html",
                           logs=logs,
                           f_usuario=f_usuario,
                           f_tabla=f_tabla,
                           f_desde=f_desde,
                           tablas_unicas=[t[0] for t in tablas_unicas])


@reports_bp.get("/export", endpoint="export_data")
@login_required
def export_data():
    """Maneja la exportación de diferentes tablas a Excel (Req. 1.6)."""
    tipo = request.args.get("tipo") 
    
    # Capturar los filtros (que son strings del URL o None)
    fecha_hoy_str = date.today().strftime('%Y-%m-%d')
    fecha_30_dias_atras_str = (date.today() - timedelta(days=30)).strftime('%Y-%m-%d')
    f_desde = request.args.get("desde") or fecha_30_dias_atras_str
    f_hasta = request.args.get("hasta") or fecha_hoy_str
    
    try:
        # Usamos los objetos date para filtrar en SQL
        f_desde_obj = datetime.strptime(f_desde, '%Y-%m-%d').date()
        f_hasta_obj = datetime.strptime(f_hasta, '%Y-%m-%d').date()
    except ValueError:
        # En caso de fechas inválidas, usamos el rango de 30 días
        f_desde_obj = datetime.strptime(fecha_30_dias_atras_str, '%Y-%m-%d').date()
        f_hasta_obj = datetime.strptime(fecha_hoy_str, '%Y-%m-%d').date()
        
    df = pd.DataFrame()
    filename = f"{tipo}_export.xlsx"

    if tipo == "attendance":
        # Filtramos la consulta base con los objetos date
        q = (Asistencia.query
             .filter(func.date(Asistencia.hora_entrada) >= f_desde_obj)
             .filter(func.date(Asistencia.hora_entrada) <= f_hasta_obj)
             .order_by(Asistencia.ID_asistencia.desc()))
        
        qs = q.all()
        rows = []
        for a in qs:
            # --- CORRECCIÓN CRÍTICA: TRATAMIENTO SEGURO DEL OBJETO ---
            
            # Hora de Entrada: Debe ser formateado solo si tiene el atributo strftime (es decir, si es datetime)
            entrada_str = ""
            if isinstance(a.hora_entrada, datetime):
                 entrada_str = a.hora_entrada.strftime("%Y-%m-%d %H:%M")
            elif hasattr(a.hora_entrada, 'strftime'):
                 # Para el caso que sea solo db.Time, aunque debería ser db.DateTime
                 entrada_str = a.hora_entrada.strftime("%H:%M")

            salida_str = ""
            if isinstance(a.hora_salida, datetime):
                 salida_str = a.hora_salida.strftime("%Y-%m-%d %H:%M")
            elif hasattr(a.hora_salida, 'strftime'):
                 salida_str = a.hora_salida.strftime("%H:%M")
                 
            # --------------------------------------------------------

            rows.append({
                "ID": a.ID_asistencia, 
                "Cliente": f"{a.cliente.nombre} {a.cliente.apellido}",
                "Entrada": entrada_str,
                "Salida": salida_str,
                "Obs": a.observaciones or ""
            })
        df = pd.DataFrame(rows)

    elif tipo == "clients":
        qs = Cliente.query.order_by(Cliente.ID_cliente.asc()).all()
        rows = [{
            "ID": c.ID_cliente, 
            "Nombre": c.nombre, 
            "Apellido": c.apellido,
            "Cédula": c.cedula, 
            "Email": c.email or "",
            "Estado": "Activo" if c.activo else "Inactivo",
        } for c in qs]
        df = pd.DataFrame(rows)
            
    elif tipo == "payments":
        qs = DetallePago.query.order_by(DetallePago.ID_detalle_pago.desc()).all()
        rows = [{
            "ID Pago": p.ID_detalle_pago, 
            "Cliente": f"{p.suscripcion.cliente.nombre} {p.suscripcion.cliente.apellido}",
            "Cédula": p.suscripcion.cliente.cedula, 
            "Monto": float(p.monto),
            "Método": p.metodo_pago, 
            "Fecha Pago": p.fecha_pago.strftime("%Y-%m-%d %H:%M"), 
            "Suscripcion Tipo": p.suscripcion.tipo.nombre
        } for p in qs]
        df = pd.DataFrame(rows)
        
    elif tipo == "routines":
        # CONSULTA: Obtener todas las rutinas con sus detalles
        qs = Rutina.query.order_by(Rutina.ID_rutina.desc()).all()
        rows = []
        
        for r in qs:
            # 1. Obtener los detalles de los ejercicios de la rutina (r.detalles)
            if r.detalles:
                for d in r.detalles:
                    # 2. Crear una fila por CADA EJERCICIO
                    rows.append({
                        "ID Rutina": r.ID_rutina,
                        "Nombre Rutina": r.nombre_rutina,
                        "Objetivo Principal": r.objetivo.descripcion if r.objetivo else "",
                        "Grupo Muscular": d.grupo_muscular.nombre,
                        "Tipo Ejercicio": d.tipo_ejercicio.nombre,
                        "Nombre Ejercicio": d.nombre_ejercicio,
                        "Orden": d.orden,
                        "Series": d.series,
                        "Repeticiones": d.repeticiones,
                        "Descanso (seg)": d.descanso_seg,
                        "Creador": f"{r.creador.nombre} {r.creador.apellido}"
                    })
            else:
                # Caso para Rutinas que no tienen ejercicios detallados
                rows.append({
                    "ID Rutina": r.ID_rutina,
                    "Nombre Rutina": r.nombre_rutina,
                    "Objetivo Principal": r.objetivo.descripcion if r.objetivo else "",
                    "Grupo Muscular": "SIN DETALLES",
                    "Tipo Ejercicio": "SIN DETALLES",
                    "Nombre Ejercicio": "SIN DETALLES",
                    "Series": 0,
                    "Repeticiones": "",
                    "Descanso (seg)": 0,
                    "Creador": f"{r.creador.nombre} {r.creador.apellido}"
                })
                
        df = pd.DataFrame(rows)
        
    elif tipo == "suscripciones":
        qs = Suscripcion.query.order_by(Suscripcion.ID_suscripcion.desc()).all()
        rows = [{
            "ID": s.ID_suscripcion, 
            "Cliente": f"{s.cliente.nombre} {s.cliente.apellido}",
            "Tipo": s.tipo.nombre, 
            "Desde": s.fecha_inicio.strftime("%Y-%m-%d"),
            "Vence": s.fecha_vencimiento.strftime("%Y-%m-%d"), 
            "Estado": s.estado
        } for s in qs]
        df = pd.DataFrame(rows)

    if df.empty:
        flash(f"No hay datos para exportar del tipo '{tipo}'.", "warning")
        return redirect(url_for("reports.central"))

    content, filename = df_to_excel_download(df, filename)
    return send_file(BytesIO(content), as_attachment=True,
                     download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@reports_bp.get("/export/auditoria", endpoint="export_auditoria")
@login_required
def export_auditoria():
    """Exporta el Log de Auditoría a Excel, aplicando los filtros de fecha y usuario."""
    # Capturar filtros (usando la misma lógica que auditoria_log)
    f_usuario = request.args.get("usuario", "").strip()
    f_tabla = request.args.get("tabla", "").strip()
    f_desde = request.args.get("desde")
    
    # Construir la consulta base
    q = Acciones.query.join(Funcionario).join(TipoAccion)
    
    # Aplicar filtros de búsqueda
    if f_usuario:
        like = f"%{f_usuario}%"
        q = q.filter((Funcionario.nombre.ilike(like)) | (Funcionario.apellido.ilike(like)) | (Funcionario.usuario.ilike(like)))
    
    if f_tabla:
        q = q.filter(Acciones.tabla_afectada == f_tabla)
        
    if f_desde:
        try:
            f_desde_dt = datetime.strptime(f_desde, '%Y-%m-%d').date()
            q = q.filter(Acciones.fecha_accion >= f_desde_dt)
        except ValueError:
            pass
            
    # Obtener todos los registros filtrados, ordenados por fecha
    logs = q.order_by(Acciones.ID_accion.desc()).all()
    
    if not logs:
        flash("No hay registros para exportar con los filtros seleccionados.", "warning")
        return redirect(url_for("reports.auditoria_log"))

    rows = []
    for log in logs:
        rows.append({
            "ID": log.ID_accion,
            "Fecha": log.fecha_accion.strftime('%Y-%m-%d %H:%M:%S'),
            "Funcionario": f"{log.funcionario.nombre} ({log.funcionario.usuario})",
            "Tipo Accion": log.tipo_accion.nombre_accion,
            "Tabla Afectada": log.tabla_afectada,
            "Descripcion": log.descripcion
        })
        
    df = pd.DataFrame(rows)
    filename = f"auditoria_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    content, filename = df_to_excel_download(df, filename)
    return send_file(BytesIO(content), as_attachment=True,
                     download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")