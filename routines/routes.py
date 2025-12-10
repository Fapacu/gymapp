from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file,jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Cliente, Rutina, Objetivo, RutinaAsignacion, next_int_id_from_timestamp
from utils_pdf import build_routine_pdf
from sqlalchemy.exc import IntegrityError
from io import BytesIO
from datetime import datetime, date
from models import RutinaDetalle, GrupoMuscular, TipoEjercicio, Acciones, TipoAccion, Funcionario
from auth.routes import require_admin

routines_bp = Blueprint("routines", __name__, url_prefix="/routines")

@routines_bp.get("/config")
@login_required
def config_rutinas():
    """Muestra los listados de catálogos para edición."""
    require_admin()
    objetivos = Objetivo.query.order_by(Objetivo.idobjetivo.asc()).all()
    musculos = GrupoMuscular.query.order_by(GrupoMuscular.nombre.asc()).all()
    tipos_ejercicio = TipoEjercicio.query.order_by(TipoEjercicio.nombre.asc()).all()
    
    return render_template("config_rutinas.html", 
                           objetivos=objetivos, 
                           musculos=musculos, 
                           tipos_ejercicio=tipos_ejercicio)

@routines_bp.post("/config/save_item")
@login_required
def save_item():
    """Guarda un nuevo ítem de catálogo (Músculo, Objetivo, o Tipo Ejercicio)."""
    require_admin()
    tipo = request.form.get("tipo") # Debe ser 'objetivo', 'musculo', o 'ejercicio'
    nombre = request.form.get("nombre").strip()
    
    if not nombre:
        flash(f"El nombre del item es obligatorio.", "danger")
        return redirect(url_for("routines.config_rutinas"))

    try:
        if tipo == 'objetivo':
            db.session.add(Objetivo(descripcion=nombre))
        elif tipo == 'musculo':
            db.session.add(GrupoMuscular(nombre=nombre))
        elif tipo == 'ejercicio':
            db.session.add(TipoEjercicio(nombre=nombre))
        else:
            flash("Tipo de catálogo inválido.", "danger")
            return redirect(url_for("routines.config_rutinas"))
        
        db.session.flush()
        log = Acciones(
            ID_funcionario=current_user.ID_funcionario,
            tabla_afectada=f"Catalogo_{tipo}",
            ID_tipo_accion=1, # Asume que ID 1 = CREAR
            descripcion=f"Creación del nuevo ítem '{nombre}' en el catálogo de {tipo}."
        )
        db.session.add(log)
            
        db.session.commit()
        flash(f"'{nombre}' agregado exitosamente al catálogo '{tipo}'.", "success")
        
    except IntegrityError:
        db.session.rollback()
        flash(f"Error: Ya existe un ítem con ese nombre en el catálogo de {tipo}.", "danger")
        
    return redirect(url_for("routines.config_rutinas"))

@routines_bp.get("/")
@login_required
def list_routines():
    # 1. Obtener todas las rutinas base
    items = Rutina.query.order_by(Rutina.ID_rutina.desc()).all()
    
    # 2. Obtener TODAS las asignaciones VIGENTES (activa=True Y fecha_hasta >= hoy)
    today = date.today()
    asignaciones_vigentes = RutinaAsignacion.query.filter(
        RutinaAsignacion.vigente == True,
        RutinaAsignacion.hasta >= today
    ).all()
    
    # 3. Mapear las asignaciones por ID de Rutina
    # Esto crea un diccionario donde la clave es el ID de la Rutina y el valor es el objeto RutinaAsignacion.
    asignaciones_map = {}
    for ra in asignaciones_vigentes:
        # Solo mapeamos la primera asignación vigente encontrada por rutina ID
        if ra.ID_rutina not in asignaciones_map:
            asignaciones_map[ra.ID_rutina] = ra 

    # 4. Pasar ambas listas/diccionarios al template
    return render_template("routines_list.html", 
                           items=items, 
                           asignaciones_map=asignaciones_map)

@routines_bp.get("/new")
@login_required
def new_routine():
    objetivos = Objetivo.query.order_by(Objetivo.descripcion.asc()).all()
    tipos_ejercicios = TipoEjercicio.query.order_by(TipoEjercicio.nombre.asc()).all()
    musculos = GrupoMuscular.query.order_by(GrupoMuscular.nombre.asc()).all() 
    return render_template("routines_form.html", item=None, objetivos=objetivos, 
                           musculos=musculos, tipos_ejercicios=tipos_ejercicios)

@routines_bp.get("/api/search_clients")
@login_required
def search_clients_ajax():
    """Ruta para búsqueda de clientes por AJAX (usada por Select2)."""
    query = request.args.get('q', '').strip()
    
    clients = []
    if query and len(query) >= 2:
        search_term = f"%{query}%"
        clients = Cliente.query.filter(
            (Cliente.nombre.ilike(search_term)) | 
            (Cliente.apellido.ilike(search_term)) |
            (Cliente.cedula.ilike(search_term))
        ).limit(20).all()
    else:
        return jsonify(results=[])

    results = []
    for client in clients:
        results.append({
            'id': client.ID_cliente, 
            'text': f"{client.apellido}, {client.nombre} (C.I: {client.cedula or 'N/A'})"
        })
        
    return jsonify(results=results)

@routines_bp.get("/<int:rid>/edit")
@login_required
def edit_routine(rid):
    item = Rutina.query.get_or_404(rid)
    objetivos = Objetivo.query.order_by(Objetivo.descripcion.asc()).all()
    musculos = GrupoMuscular.query.order_by(GrupoMuscular.nombre.asc()).all()
    tipos_ejercicios = TipoEjercicio.query.order_by(TipoEjercicio.nombre.asc()).all()
    
    # Obtener los IDs de los músculos ya seleccionados en esta rutina
    musculos_seleccionados_ids = [m.idgrupo_muscular for m in item.grupos_musculares] 
    
    return render_template("routines_form.html", item=item, objetivos=objetivos, 
                           musculos=musculos, musculos_seleccionados_ids=musculos_seleccionados_ids,
                           tipos_ejercicios=tipos_ejercicios)

@routines_bp.post("/save")
@login_required
def save_routine():
    rid = request.form.get("id")
    nombre_rutina = request.form.get("nombre_rutina").strip()
    descripcion_corta = request.form.get("descripcion_corta").strip() 
    observaciones = request.form.get("observaciones").strip() or None
    objetivo_id = int(request.form.get("idobjetivo"))
    
    # Capturar datos de detalle
    nombres_ejercicios = request.form.getlist("ejercicio_nombre")
    grupos_musculares_ids = request.form.getlist("grupo_muscular_id")
    tipos_ejercicios_ids = request.form.getlist("tipo_ejercicio_id")
    series_list = request.form.getlist("series")
    repeticiones_list = request.form.getlist("repeticiones")
    descansos_list = request.form.getlist("descanso_seg")

    if not nombre_rutina or not descripcion_corta:
        flash("El nombre y la descripción detallada son obligatorios", "danger")
        return redirect(url_for("routines.list_routines"))
    
    is_new = not rid
    
    try:
        if rid:
            # --- EDICIÓN ---
            item = Rutina.query.get_or_404(int(rid))
            item.nombre_rutina = nombre_rutina
            item.descripcion = descripcion_corta
            item.observaciones = observaciones
            item.idobjetivo = objetivo_id
            
            # Limpiar detalles antiguos (usando la relación de cascada)
            item.detalles = [] 

            log_tipo_id = 2 # MODIFICAR
            log_desc = f"Rutina '{nombre_rutina}' (ID {rid}) actualizada. Total de ejercicios: {len(nombres_ejercicios)}."
        else:
            # --- CREACIÓN ---
            item = Rutina(nombre_rutina=nombre_rutina, 
                          descripcion=descripcion_corta, 
                          observaciones=observaciones, 
                          idobjetivo=objetivo_id, 
                          creado_por=current_user.ID_funcionario)
            db.session.add(item)
            
            log_tipo_id = 1 # CREAR
            log_desc = f"Nueva Rutina '{nombre_rutina}' creada por {current_user.usuario}."

        # El flush es necesario para obtener el ID_rutina antes de crear los detalles
        db.session.flush() 

        # --- GESTIÓN DE RELACIÓN MUCHOS-A-MUCHOS (Grupos Musculares Focales) ---
        item.grupos_musculares.clear() 
        musculos_ids = request.form.getlist("musculos") # Asume que el formulario pasa los IDs de músculo
        if musculos_ids:
            musculos_obj = GrupoMuscular.query.filter(GrupoMuscular.idgrupo_muscular.in_(musculos_ids)).all()
            for m in musculos_obj:
                item.grupos_musculares.append(m)

        # --- GESTIÓN DE DETALLE DE EJERCICIOS (RutinaDetalle) ---
        if nombres_ejercicios:
            for i, nombre in enumerate(nombres_ejercicios):
                if nombre.strip(): 
                    detalle = RutinaDetalle(
                        ID_rutina=item.ID_rutina,
                        ID_grupo_muscular=int(grupos_musculares_ids[i]),
                        ID_tipo_ejercicio=int(tipos_ejercicios_ids[i]),
                        nombre_ejercicio=nombre.strip(),
                        series=int(series_list[i]) if series_list[i].isdigit() else 0,
                        repeticiones=repeticiones_list[i].strip(),
                        descanso_seg=int(descansos_list[i]) if descansos_list[i].isdigit() else 0,
                        orden=i + 1
                    )
                    db.session.add(detalle)
        
        # --- REGISTRO DE AUDITORÍA ---
        # El log se añade aquí para garantizar que 'item.ID_rutina' existe
        log = Acciones(
            ID_funcionario=current_user.ID_funcionario,
            tabla_afectada='Rutina',
            ID_tipo_accion=log_tipo_id,
            descripcion=log_desc
        )
        db.session.add(log)
        
        db.session.commit() # Commit final que incluye la Rutina, Detalles y Log

        flash(f"Rutina y detalles guardados con éxito.", "success")
        
    except IntegrityError:
        db.session.rollback()
        flash("Error de integridad: Ya existe un registro con ese nombre de rutina o datos duplicados.", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Error crítico al guardar la rutina: {str(e)}", "danger")
        
    return redirect(url_for("routines.list_routines"))

@routines_bp.get("/assign")
@login_required
def assign_routine_form():
    clientes = Cliente.query.order_by(Cliente.nombre.asc()).all()
    rutinas = Rutina.query.order_by(Rutina.nombre_rutina.asc()).all()
    return render_template("routines_assign.html", clientes=clientes, rutinas=rutinas)

@routines_bp.post("/assign")
@login_required
def assign_routine():
    cliente_id = int(request.form.get("cliente_id"))
    rutina_id = int(request.form.get("rutina_id"))
    desde = request.form.get("desde")
    hasta = request.form.get("hasta")
    asign_id = next_int_id_from_timestamp()
    ra = RutinaAsignacion(
        idrutina_asignacion=asign_id,
        ID_cliente=cliente_id,
        ID_rutina=rutina_id,
        asignado_por=current_user.ID_funcionario,
        desde=desde, hasta=hasta, vigente=True
    )
    db.session.add(ra)
    log = Acciones(
            ID_funcionario=current_user.ID_funcionario,
            tabla_afectada='RutinaAsignacion',
            ID_tipo_accion=1, # CREAR
            descripcion=f"Rutina ID {rutina_id} asignada a Cliente ID {cliente_id}."
        )
    db.session.add(log)
    db.session.commit()
    flash("Rutina asignada al cliente","success")
    return redirect(url_for("routines.list_routines"))

@routines_bp.get("/pdf/<int:asign_id>")
@login_required
def routine_pdf(asign_id):
    ra = RutinaAsignacion.query.get_or_404(asign_id)
    r = ra.rutina
    c = ra.cliente
    cab = {
        "cliente": f"{c.nombre} {c.apellido} ({c.cedula})",
        "rutina": r.nombre_rutina,
        "objetivo": r.objetivo.descripcion if r.objetivo else "",
        "observaciones": r.observaciones or "",
        "asignada_desde": ra.desde.strftime("%Y-%m-%d"),
        "asignada_hasta": ra.hasta.strftime("%Y-%m-%d")
    }
    contenido = r.descripcion or "(Sin detalle)"
    pdf = build_routine_pdf(cab, contenido)
    return send_file(BytesIO(pdf), as_attachment=True,
                     download_name=f"rutina_{c.cedula}_{asign_id}.pdf",
                     mimetype="application/pdf")
