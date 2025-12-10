import re
from sqlalchemy.exc import IntegrityError
from sqlalchemy import event
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required,current_user
from extensions import db
from models import Cliente, Suscripcion, estado_cliente_general, Asistencia, RutinaAsignacion, Acciones, TipoAccion, Funcionario,DetallePago
from utils_excel import df_to_excel_download
from io import BytesIO
import pandas as pd
from utils import format_currency_robust

clients_bp = Blueprint("clients", __name__, url_prefix="/clients")


def _norm(s):
    return (s or "").strip()

def _norm_cedula(s: str) -> str:
    # Simula la limpieza de la cédula para unicidad
    return s.replace(".", "").replace("-", "").strip()


@clients_bp.get("/")
@login_required
def list_clients():
    q = request.args.get("q","").strip()
    estado = request.args.get("estado","")
    query = Cliente.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Cliente.nombre.ilike(like)) |
            (Cliente.apellido.ilike(like)) |
            (Cliente.cedula.ilike(like))
        )
    clients = query.order_by(Cliente.fecha_registro.desc()).all()
    estados = {c.ID_cliente: estado_cliente_general(c.ID_cliente) for c in clients}
    if estado:
        clients = [c for c in clients if estados[c.ID_cliente] == estado]
    return render_template("clients_list.html", clients=clients, estados=estados, q=q, estado=estado)

@clients_bp.get("/new")
@login_required
def new_client():
    return render_template("clients_form.html", client=None)

@clients_bp.get("/<int:cid>/edit")
@login_required
def edit_client(cid):
    client = Cliente.query.get_or_404(cid)
    return render_template("clients_form.html", client=client)

@clients_bp.post("/save")
@login_required
def save_client():
    # 1. CAPTURA Y NORMALIZACIÓN DE DATOS
    cid = request.form.get("id")
    nombre = _norm(request.form.get("nombre"))
    apellido = _norm(request.form.get("apellido"))
    cedula = _norm_cedula(request.form.get("cedula")) # Cédula normalizada para búsqueda
    telefono = _norm(request.form.get("telefono"))
    email = _norm(request.form.get("email"))
    direccion = _norm(request.form.get("direccion"))
    genero = request.form.get("genero") or None
    fecha_nacimiento = request.form.get("fecha_nacimiento") or None
    activo_flag = True if request.form.get("activo") == "on" else False

    # Validación básica
    if not nombre or not apellido or not cedula:
        flash("Nombre, apellido y cédula son obligatorios.", "danger")
        return redirect(url_for("clients.list_clients"))

    # Determinar si es una acción de CREAR o MODIFICAR
    is_new = not cid
    
    # 2. LÓGICA DE AUDITORÍA Y COMMIT

    if is_new:
        # --- CREACIÓN ---
        existente = Cliente.query.filter_by(cedula=cedula).first()
        
        if existente:
            # Si ya existe con esa cédula (aunque estuviera inactivo), se reactiva
            existente.nombre = nombre
            existente.apellido = apellido
            existente.telefono = telefono or None
            existente.email = email or None
            existente.direccion = direccion or None
            existente.genero = genero
            existente.fecha_nacimiento = fecha_nacimiento or None
            existente.activo = True # Reactivar
            c = existente
            log_tipo_id = 2 # MODIFICAR (Reactivación)
            log_desc = f"Cliente ID {existente.ID_cliente} reactivado y actualizado. Cédula: {cedula}."
        else:
            # Creación de nuevo registro
            c = Cliente(
                nombre=nombre, apellido=apellido, cedula=cedula,
                telefono=telefono or None, email=email or None,
                direccion=direccion or None, genero=genero,
                fecha_nacimiento=fecha_nacimiento or None, activo=activo_flag
            )
            db.session.add(c)
            db.session.flush() # Obtiene el ID antes del commit final
            log_tipo_id = 1 # CREAR
            log_desc = f"Nuevo Cliente ID {c.ID_cliente} creado. Cédula: {cedula}."
    else:
        # --- EDICIÓN / ACTUALIZACIÓN ---
        c = Cliente.query.get_or_404(int(cid))
        
        # Validación de unicidad de cédula (no pisar la cédula de otro)
        existe_otro = Cliente.query.filter(Cliente.cedula == cedula, Cliente.ID_cliente != c.ID_cliente).first()
        if existe_otro:
            flash("Esa cédula pertenece a otro cliente.", "danger")
            return redirect(url_for("clients.edit_client", cid=cid))

        # Actualizar campos del objeto existente
        c.nombre = nombre
        c.apellido = apellido
        c.cedula = cedula
        c.telefono = telefono or None
        c.email = email or None
        c.direccion = direccion or None
        c.genero = genero
        c.fecha_nacimiento = fecha_nacimiento or None
        c.activo = activo_flag
        
        log_tipo_id = 2 # MODIFICAR
        log_desc = f"Cliente ID {c.ID_cliente} actualizado. Cédula: {cedula}."

    try:
        # Commit de la acción principal (creación/actualización del cliente)
        db.session.commit()
        
        # --- REGISTRO DE AUDITORÍA (Se ejecuta en una nueva transacción implícita) ---
        log = Acciones(
            ID_funcionario=current_user.ID_funcionario,
            tabla_afectada='Cliente',
            ID_tipo_accion=log_tipo_id,
            descripcion=log_desc
        )
        db.session.add(log)
        db.session.commit() # Commit del log de auditoría
        
        flash(f"Cliente {'creado' if is_new else 'actualizado'}","success")

    except IntegrityError:
        # Captura de error si algo falló en la BD (ej. duplicidad de cédula no capturada)
        db.session.rollback()
        flash("Error de integridad: Ya existe un cliente con esa cédula.", "danger")

    return redirect(url_for("clients.list_clients"))


@clients_bp.post("/<int:cid>/toggle")
@login_required
def toggle_client(cid):
    c = Cliente.query.get_or_404(cid)
    c.activo = not c.activo
    db.session.commit()
    flash("Cliente actualizado","info")
    return redirect(url_for("clients.list_clients"))

@clients_bp.get("/<int:cid>/profile")
@login_required
def client_profile(cid):
    # 'cid' es el ID del cliente pasado por la URL
    c = Cliente.query.get_or_404(cid)
    sus = (Suscripcion.query.filter_by(ID_cliente=cid)
           .order_by(Suscripcion.fecha_vencimiento.desc()).all())
           
    # 1. Consulta para obtener todos los pagos de este cliente
    historial_pagos_db = ( # Renombro la variable para evitar confusión
        DetallePago.query
        # Unir DetallePago a Suscripcion para poder filtrar por ID_cliente
        .join(Suscripcion, DetallePago.suscripcion_ID_suscripcion == Suscripcion.ID_suscripcion)
        # ERROR CORREGIDO AQUÍ: Usamos 'cid', no 'client_id'
        .filter(Suscripcion.ID_cliente == cid) 
        .order_by(DetallePago.fecha_pago.desc()) # Mostrar el más reciente primero
        .all()
    )

    # 2. Formatear y preparar los datos para la plantilla
    pagos_formateados = []
    for pago in historial_pagos_db:
        # Intenta obtener el nombre del tipo de suscripción
        tipo_nombre = pago.suscripcion.tipo.nombre if pago.suscripcion.tipo else "N/A"
        
        # Lógica para manejar el nombre personalizado (para el PDF y ahora para el historial)
        descripcion_pago = pago.descripcion
        if descripcion_pago and descripcion_pago.startswith("Pago de suscripción"):
            nombre_extraido = descripcion_pago.replace("Pago de suscripción", "").strip()
            if nombre_extraido:
                tipo_nombre = nombre_extraido
        
        pagos_formateados.append({
            'fecha': pago.fecha_pago.strftime('%Y-%m-%d %H:%M'),
            'monto_formateado': format_currency_robust(pago.monto), # Usa tu función de formato
            'metodo': pago.metodo_pago,
            'suscripcion_tipo': tipo_nombre,
            'periodo_inicio': pago.suscripcion.fecha_inicio.strftime('%Y-%m-%d'),
            'periodo_fin': pago.suscripcion.fecha_vencimiento.strftime('%Y-%m-%d'),
            'detalle_id': pago.ID_detalle_pago
        })
        
    asistencias = Asistencia.query.filter_by(ID_cliente=cid).order_by(Asistencia.ID_asistencia.desc()).all()
    rutinas = RutinaAsignacion.query.filter_by(ID_cliente=cid).order_by(RutinaAsignacion.desde.desc()).all()
    estado = estado_cliente_general(cid)
    
    return render_template("client_profile.html", 
                           client=c, 
                           suscripciones=sus, 
                           estado=estado, 
                           historial_pagos=pagos_formateados, # ERROR CORREGIDO AQUÍ: Se pasa la variable.
                           asistencias=asistencias, 
                           rutinas=rutinas)

@clients_bp.get("/export")
@login_required
def export_clients():
    qs = Cliente.query.order_by(Cliente.ID_cliente.asc()).all()
    rows = []
    for c in qs:
        rows.append({
            "ID": c.ID_cliente,
            "Nombre": c.nombre,
            "Apellido": c.apellido,
            "Cédula": c.cedula,
            "Teléfono": c.telefono or "",
            "Email": c.email or "",
            "Estado": "Activo" if c.activo else "Inactivo",
            "Estado General": estado_cliente_general(c.ID_cliente),
            "Registrado": c.fecha_registro.strftime("%Y-%m-%d"),
        })
    df = pd.DataFrame(rows)
    content, filename = df_to_excel_download(df, "clientes.xlsx")
    return send_file(BytesIO(content), as_attachment=True,
                     download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
