from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, csrf, login_manager
from models import Funcionario, Rol, Acciones, TipoAccion
from werkzeug.exceptions import abort # Importar abort para require_admin
from datetime import datetime

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@login_manager.user_loader
def load_user(uid):
    """Carga el usuario por ID. Solo carga si está activo."""
    return Funcionario.query.filter_by(ID_funcionario=int(uid), activo=True).first()

def require_admin():
    """Restringe el acceso solo a Administradores."""
    if not current_user.is_authenticated or current_user.rol.nombre_rol != "ADMIN":
        abort(403) # Acceso Denegado

# --- 1.1 Iniciar Sesión ---
@auth_bp.get("/login")
def login():
    # Asegúrate de usar la plantilla base sin sidebar
    return render_template("login.html") 


@auth_bp.post("/login")
def login_post():
    """Procesa el inicio de sesión con credenciales."""
    usuario = request.form.get("usuario","").strip()
    password = request.form.get("password","").strip()
    
    # Busca el usuario, filtrando también por 'activo=True'
    user = Funcionario.query.filter_by(usuario=usuario, activo=True).first()
    
    if not user or not user.check_password(password):
        flash("Usuario o contraseña inválidos o usuario inactivo.","danger")
        return redirect(url_for("auth.login"))
        
    login_user(user, remember=True)

    try:
        # Asumiendo que TipoAccion ya tiene ID=4 para 'LOGIN'
        log = Acciones(
            ID_funcionario=user.ID_funcionario,
            tabla_afectada='Sistema',
            ID_tipo_accion=4, # Usamos 4 para LOGIN (basado en el seeding que definimos)
            descripcion=f"Inicio de sesión exitoso. Hora: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        # Esto previene que una falla en el log detenga el login exitoso
        print(f"ERROR AL REGISTRAR LOGIN EN AUDITORIA: {e}")
        db.session.rollback()

    flash(f"Bienvenido, {user.nombre} {user.apellido}","success")
    return redirect(url_for("dashboard"))

# --- 1.2 Cerrar Sesión ---
@auth_bp.post("/logout")
@login_required
def logout():
    """Cierra la sesión del usuario actual."""
    logout_user()
    # ... redirige al login
    return redirect(url_for("auth.login"))

# --- 1.3 Gestión de Usuarios (CRUD - Solo ADMIN) ---

@auth_bp.get("/users")
@login_required
def users_list():
    """Lista todos los usuarios (Funcionarios). Solo ADMIN."""
    require_admin()
    # Muestra todos los usuarios (activos e inactivos) para que el Admin pueda gestionarlos
    users = Funcionario.query.order_by(Funcionario.fecha_creacion.desc()).all()
    roles = Rol.query.all()
    return render_template("users_list.html", users=users, roles=roles)

@auth_bp.get("/users/new")
@login_required
def users_new():
    """Muestra el formulario para crear un nuevo usuario. Solo ADMIN."""
    require_admin()
    roles = Rol.query.all()
    return render_template("users_form.html", user=None, roles=roles)

@auth_bp.get("/users/edit/<int:uid>")
@login_required
def users_edit(uid):
    """Muestra el formulario para editar un usuario existente. Solo ADMIN."""
    require_admin()
    user = Funcionario.query.get_or_404(uid)
    roles = Rol.query.all()
    return render_template("users_form.html", user=user, roles=roles)

@auth_bp.post("/users/save")
@login_required
def users_save():
    """Guarda (Crea o Edita) un usuario. Solo ADMIN."""
    require_admin()
    uid = request.form.get("id")
    # Capturar el estado 'activo' del formulario (solo si está presente en el form de edición)
    activo_form = request.form.get("activo") 

    data = {
        "usuario": request.form.get("usuario").strip(),
        "nombre": request.form.get("nombre").strip(),
        "apellido": request.form.get("apellido").strip(),
        "cedula": request.form.get("cedula").strip(),
        "telefono": request.form.get("telefono"),
        "email": request.form.get("email"),
        "domicilio": request.form.get("domicilio"),
        "ID_rol": int(request.form.get("ID_rol")),
    }
    password = request.form.get("password","").strip()

    if uid:
        # --- Edición ---
        u = Funcionario.query.get_or_404(int(uid))
        
        # Actualizar campos
        for k,v in data.items(): setattr(u,k,v)
        
        # Actualizar estado activo/inactivo si viene del formulario
        if activo_form is not None:
             u.activo = True if activo_form == "on" else False
        
        # Actualizar contraseña si se proporciona
        if password: u.set_password(password)
            
        db.session.commit()
        flash("Funcionario actualizado","success")
    else:
        # --- Creación ---
        if Funcionario.query.filter_by(usuario=data["usuario"]).first():
            flash("El usuario ya existe","danger")
            return redirect(url_for("auth.users_new"))
            
        # Al crear, se establece 'activo=True' por defecto
        data["activo"] = True 
        u = Funcionario(**data)
        
        if not password:
            flash("Debes indicar contraseña","danger")
            return redirect(url_for("auth.users_new"))
            
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        flash("Funcionario creado","success")
        
    return redirect(url_for("auth.users_list"))

# --- 1.3 Desactivar/Activar Usuario (Acción directa) ---
@auth_bp.post("/users/toggle-active/<int:uid>")
@login_required
def users_toggle_active(uid):
    """Alterna el estado 'activo' del usuario. Solo ADMIN."""
    require_admin()
    user = Funcionario.query.get_or_404(uid)
    # Alterna el estado actual
    user.activo = not user.activo 
    db.session.commit()
    
    accion = "activado" if user.activo else "desactivado"
    flash(f"Funcionario {user.nombre} {user.apellido} {accion} correctamente.","success")
    return redirect(url_for("auth.users_list"))


# --- 1.4 Cambiar Contraseña ---
@auth_bp.post("/change-password")
@login_required
def change_password():
    """Permite al usuario autenticado cambiar su propia contraseña."""
    current = request.form.get("current_password","")
    new = request.form.get("new_password","")
    
    if not current_user.check_password(current):
        flash("Contraseña actual incorrecta","danger")
        return redirect(url_for("dashboard")) # Redirige al dashboard o a donde sea el formulario
        
    if not new or len(new) < 8: # Añadir una validación simple de longitud
        flash("La nueva contraseña debe tener al menos 8 caracteres.","danger")
        return redirect(url_for("dashboard"))
        
    current_user.set_password(new)
    db.session.commit()
    flash("Contraseña actualizada","success")
    return redirect(url_for("dashboard"))