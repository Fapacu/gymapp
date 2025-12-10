from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import (Cliente, TipoSuscripcion, Suscripcion, DetallePago, Comprobante,Acciones , next_int_id_from_timestamp)
from utils_pdf import build_receipt_pdf
from io import BytesIO
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, date
from decimal import Decimal
from werkzeug.exceptions import NotFound 


# --- FUNCIÓN DE FORMATO ROBUSTA (NO USA LOCALE) ---
def format_currency_robust(value):
    """Formatea a cadena de moneda (1.000.000,00) sin depender de locale."""
    if value is None:
        return '0,00'
    
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
        
    formatted_value = "{:,.2f}".format(value)
    
    # Convierte de formato Inglés/Python (1,000,000.00) a Español (1.000.000,00)
    return formatted_value.replace(",", "#").replace(".", ",").replace("#", ".")
# ---------------------------------------------------

payments_bp = Blueprint("payments", __name__, url_prefix="/payments")

@payments_bp.get("/pending")
@login_required
def list_pending():
    return redirect(url_for('clients.list_clients', estado='en mora'))

@payments_bp.get("/")
@login_required
def list_payments():
    f_cliente = request.args.get("cliente","").strip()
    f_desde = request.args.get("desde","")
    f_hasta = request.args.get("hasta","")
    
    # NOTA: Asegúrate de que la relación JOIN use el nombre correcto de columna si ID_detalle_pago es diferente
    q = (DetallePago.query
         .join(Suscripcion, DetallePago.suscripcion_ID_suscripcion==Suscripcion.ID_suscripcion)
         .join(Cliente, Suscripcion.ID_cliente==Cliente.ID_cliente))

    if f_cliente:
        like = f"%{f_cliente}%"
        q = q.filter((Cliente.nombre.ilike(like)) | (Cliente.apellido.ilike(like)) | (Cliente.cedula.ilike(like)))

    if f_desde:
        q = q.filter(DetallePago.fecha_pago >= f_desde+" 00:00:00")
    if f_hasta:
        q = q.filter(DetallePago.fecha_pago <= f_hasta+" 23:59:59")

    pagos = q.order_by(DetallePago.fecha_pago.desc()).all()
    return render_template("payments_list.html", pagos=pagos)

@payments_bp.get("/new")
@login_required
def new_payment():
    clients = Cliente.query.filter_by(activo=True).order_by(Cliente.apellido.asc()).all()
    
    # 🚨 CRÍTICO: Asegúrate de que esta consulta devuelve datos.
    tipos = TipoSuscripcion.query.filter_by(activo=True).order_by(TipoSuscripcion.precio.asc()).all()
    
    # Prepara los datos si necesitas formatear el precio, como lo has hecho antes.
    tipos_formateados = []
    for t in tipos:
        t_dict = t.__dict__.copy() 
        t_dict['precio_formateado'] = format_currency_robust(t.precio)
        tipos_formateados.append(t_dict)
        
    today = date.today().strftime('%Y-%m-%d')
    
    # Pasa la lista de tipos formateados (o la lista 'tipos' si no los formateas)
    return render_template("payments_form.html", clients=clients, tipos=tipos_formateados, today=today)


@payments_bp.get("/api/search_clients")
@login_required
def search_clients_ajax():
    """Ruta para búsqueda de clientes por AJAX (usada por Select2)."""
    query = request.args.get('q', '').strip()
    
    clients = []
    if query and len(query) >= 2:
        search_term = f"%{query}%"
        # Usamos 'Cliente' (asegúrate de que esté importado correctamente)
        clients = Cliente.query.filter(
            (Cliente.nombre.ilike(search_term)) | 
            (Cliente.apellido.ilike(search_term)) |
            (Cliente.cedula.ilike(search_term))
        ).limit(20).all()
    else:
        # Si el query es muy corto, devolvemos un array vacío para rendimiento
        return jsonify(results=[])

    results = []
    for client in clients:
        results.append({
            'id': client.ID_cliente, 
            'text': f"{client.apellido}, {client.nombre} (C.I: {client.cedula or 'N/A'})"
        })
        
    return jsonify(results=results)


@payments_bp.post("/save")
@login_required
def save_payment():
    # 1. OBTENER Y ASEGURAR EL ID DEL FUNCIONARIO ACTUAL
    funcionario_id = current_user.ID_funcionario 
    if not funcionario_id:
        flash("Error de sesión: No se pudo identificar al funcionario.", "danger")
        return redirect(url_for("payments.new_payment"))
    
    try:
        # 2. CAPTURAR Y VALIDAR DATOS DEL FORMULARIO
        client_id_str = request.form.get("client_id", "").strip() 
        tipo_data = request.form.get("tipo_id", "").strip() 
        metodo_pago = request.form.get("metodo_pago")
        fecha_inicio_str = request.form.get("fecha_inicio")
        
        # Campos para suscripción personalizada
        precio_custom_str = request.form.get("precio_custom")
        dias_custom_str = request.form.get("dias_custom") 
        
        # VALIDACIÓN BÁSICA DE CAMPOS NULOS
        if not all([client_id_str, tipo_data, metodo_pago, fecha_inicio_str]):
             raise ValueError("Faltan datos críticos en el formulario.")
        
        # --- VALIDACIÓN CRÍTICA DEL CLIENTE ---
        if not client_id_str.isdigit(): 
             raise ValueError("Debe seleccionar un cliente válido.")
        client_id = int(client_id_str)
        Cliente.query.get_or_404(client_id)
        # ----------------------------------------------
        
        # 3. DETERMINAR TIPO DE SUSCRIPCIÓN (PREDEFINIDA o PERSONALIZADA)
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        
        if tipo_data == 'CUSTOM':
            # 3.1 SUSCRIPCIÓN PERSONALIZADA (Lógica funcional)
            if not precio_custom_str or not dias_custom_str:
                raise ValueError("Faltan el precio o los días para la suscripción personalizada.")
            
            precio_limpio = precio_custom_str.replace('.', '').replace(',', '.')
            dias_limpio = dias_custom_str.strip()

            try:
                if not dias_limpio.isdigit():
                    raise ValueError("Los días deben ser un número entero.")
                    
                monto_final = Decimal(precio_limpio)
                dias_periodo = int(dias_limpio)
                
            except Exception:
                raise ValueError("El precio o los días personalizados tienen un formato incorrecto.")

            if monto_final <= 0 or dias_periodo <= 0:
                raise ValueError("El precio o los días deben ser valores positivos.")
            
            tipo_id = 1 
            nombre_suscripcion = f"Personalizada ({dias_periodo} días)"
            
        else:
            # 3.2 SUSCRIPCIÓN PREDEFINIDA (Lógica corregida)
            if '|' not in tipo_data:
                # Este caso ocurre si se selecciona "-- Seleccionar --" (value="")
                # o si el dato es corrupto (ej. sin ID).
                 raise ValueError("Debe seleccionar un tipo de suscripción válido.")

            # Extraemos el ID del formato "ID|DIAS"
            tipo_id_str = tipo_data.split("|")[0].strip()
            
            # VALIDACIÓN CRÍTICA FINAL PARA PREDEFINIDAS
            if not tipo_id_str.isdigit():
                 raise ValueError("El tipo de suscripción seleccionado no tiene un ID válido. Revise sus datos de configuración.")
            
            tipo_id = int(tipo_id_str) # CONVERSIÓN CORRECTA
            
            # Verificar existencia y obtener datos
            tipo_suscripcion = TipoSuscripcion.query.get_or_404(tipo_id)
            
            monto_final = tipo_suscripcion.precio
            dias_periodo = tipo_suscripcion.periodo_dias
            nombre_suscripcion = tipo_suscripcion.nombre
        # -----------------------------------------------

        # 4. CÁLCULO DE FECHA DE VENCIMIENTO
        fecha_vencimiento = fecha_inicio + timedelta(days=dias_periodo)

        # 5. CREAR SUSCRIPCIÓN
        # ... (Resto de la lógica de guardado: Suscripcion, DetallePago, Comprobante, Acciones)
        sus = Suscripcion(
            ID_cliente=client_id,
            ID_tipo_suscripcion=tipo_id, 
            fecha_inicio=fecha_inicio,
            fecha_vencimiento=fecha_vencimiento,
            estado='Activa',
            observaciones=f"Creada por pago - {nombre_suscripcion}"
        )
        db.session.add(sus)
        db.session.flush()

        # 6. CREAR DETALLE PAGO
        pago = DetallePago(
            monto=monto_final, 
            fecha_pago=datetime.utcnow(),
            metodo_pago=metodo_pago,
            estado_pago='Pagado',
            descripcion=f"Pago de suscripción {nombre_suscripcion}",
            ID_funcionario=funcionario_id,
            suscripcion_ID_suscripcion=sus.ID_suscripcion
        )
        db.session.add(pago)
        db.session.flush()

        # 7. CREAR COMPROBANTE
        comp_id = next_int_id_from_timestamp()
        numero = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{client_id}"
        comp = Comprobante(
            idcomprobante=comp_id,
            detalle_pago_ID_detalle_pago=pago.ID_detalle_pago,
            numero=numero,
            fecha_emision=datetime.utcnow(),
            monto_total=monto_final, 
            emitido_por=funcionario_id
        )
        db.session.add(comp)
        
        db.session.commit() 

        # 8. REGISTRAR ACCIÓN
        log = Acciones(
            ID_funcionario=funcionario_id,
            tabla_afectada='DetallePago/Suscripcion',
            ID_tipo_accion=1, # CREAR
            descripcion=f"Pago de {nombre_suscripcion} ($ {monto_final}) registrado para Cliente ID {client_id}."
        )
        db.session.add(log)
        
        db.session.commit()

        flash("Pago registrado, suscripción creada y comprobante emitido.", "success")
        return redirect(url_for("payments.list_payments"))
    
    except NotFound: 
        flash("Error de datos: El Cliente o el Tipo de Suscripción seleccionado no existe.", "danger")
        return redirect(url_for("payments.new_payment"))
    
    except ValueError as e:
        flash(f"Error en el formato de los datos: {str(e)}. Revise los campos.", "danger")
        return redirect(url_for("payments.new_payment"))

    except IntegrityError:
        db.session.rollback()
        flash("Error de integridad: Falla de clave foránea o dato nulo en la DB.", "danger")
        return redirect(url_for("payments.new_payment"))
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error crítico al procesar: {str(e)}", "danger")
        return redirect(url_for("payments.new_payment"))
        
@payments_bp.get("/receipt/<int:detalle_id>")
@login_required
def receipt(detalle_id):
    pago = DetallePago.query.get_or_404(detalle_id)
    sus = pago.suscripcion
    cliente = sus.cliente
    tipo = sus.tipo

    tipo_suscripcion_nombre = sus.tipo.nombre
    descripcion_pago = pago.descripcion
    
    if descripcion_pago.startswith("Pago de suscripción"):
        nombre_extraido = descripcion_pago.replace("Pago de suscripción", "").strip()
        if nombre_extraido:
            tipo_suscripcion_nombre = nombre_extraido
            
    periodo = f"{sus.fecha_inicio.strftime('%Y-%m-%d')} a {sus.fecha_vencimiento.strftime('%Y-%m-%d')}"

    data = {
        "numero": (pago.ID_detalle_pago),
        "fecha": pago.fecha_pago.strftime("%Y-%m-%d %H:%M"),
        "cliente": f"{cliente.nombre} {cliente.apellido}",
        "cedula": cliente.cedula,
        "importe": format_currency_robust(pago.monto),
        "metodo": pago.metodo_pago,
        "tipo": tipo_suscripcion_nombre, 
        "periodo": periodo,
        "vence": sus.fecha_vencimiento.strftime("%Y-%m-%d")
    }
    pdf = build_receipt_pdf(data)
    return send_file(BytesIO(pdf), as_attachment=True,
                     download_name=f"recibo_{pago.ID_detalle_pago}.pdf",
                     mimetype="application/pdf")