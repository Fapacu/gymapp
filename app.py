from datetime import timedelta
from flask import Flask, render_template, redirect, url_for, flash, session
from flask_login import login_required, current_user
# Importa la configuración y las extensiones
from config import Config
from extensions import db, csrf, login_manager
# Importa todos los Blueprints (Módulos)
from models import Funcionario, Rol, TipoEjercicio, GrupoMuscular, Objetivo, TipoSuscripcion, TipoAccion# Importa modelos para el seeding
from auth.routes import auth_bp
from clients.routes import clients_bp
from payments.routes import payments_bp
from attendance.routes import attendance_bp
from routines.routes import routines_bp
from reports.routes import reports_bp
from decimal import Decimal
from models import Cliente, Rutina, Asistencia, DetallePago



def format_currency_robust(value):
    # ... (código de formato) ...
    if value is None:
        return '0,00'
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    formatted_value = "{:,.2f}".format(value)
    return formatted_value.replace(",", "#").replace(".", ",").replace("#", ".")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    app.permanent_session_lifetime = timedelta(minutes=app.config.get("SESSION_IDLE_MINUTES", 10))
    
    # Inicialización de Extensiones
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    @app.before_request
    def _make_session_permanent():
        session.permanent = True

    with app.app_context():
        db.create_all()
        
        # --- Lógica de Inicialización (Seeding) ---
        
        # 1. Seed Roles
        if Rol.query.count() == 0:
            db.session.add(Rol(ID_rol=1, nombre_rol="ADMIN", descripcion="Administrador"))
            db.session.add(Rol(ID_rol=2, nombre_rol="PERSONAL", descripcion="Personal de sala"))
            db.session.commit()
        
        # 2. Seed Admin
        if not Funcionario.query.filter_by(usuario="admin").first():
            admin = Funcionario(
                ID_funcionario=1, # Asignación de ID Manual
                nombre="Admin", apellido="Principal", cedula="0001",
                usuario="admin", ID_rol=1 # ID del rol ADMIN
            )
            admin.set_password("admin123")
            db.session.add(admin)
            db.session.commit()

        # 3. Seed Tipos de Suscripción
        # Asegúrate de que TipoSuscripcion esté importado en el inicio de app.py
        if TipoSuscripcion.query.count() == 0:
            suscripciones_base = [
                # ID 1: 7 días (Semanal)
                {"id": 1, "nombre": "Semanal Pruebas", "dias": 7, "precio": 35000.00}, 
                
                # ID 2: 1 mes (Mensual)
                {"id": 2, "nombre": "Mensual Básico", "dias": 30, "precio": 100000.00}, 
                
                # ID 3: 3 meses (Trimestral)
                {"id": 3, "nombre": "Trimestral", "dias": 90, "precio": 270000.00}, # <-- CORREGIDO a 270.000
                
                # ID 4: 1 año (Anual)
                {"id": 4, "nombre": "Anual Premium", "dias": 365, "precio": 1000000.00} # <-- CORREGIDO a 1.000.000
            ]
            for data in suscripciones_base:
                db.session.add(TipoSuscripcion(
                    ID_tipo_suscripcion=data["id"], 
                    nombre=data["nombre"], descripcion=f"Plan {data['nombre']}.",
                    periodo_dias=data["dias"], precio=data["precio"], activo=True
                ))
            db.session.commit()
            
        # 4. Seed Tipos de Ejercicios
        if TipoEjercicio.query.count() == 0: # <-- Esto debe ser TRUE para que se ejecute
            tipos = [
                {"id": 1, "nombre": "Fuerza (Barra/Mancuernas)"}, 
                {"id": 2, "nombre": "Máquina"}, 
                {"id": 3, "nombre": "Cardio"}, 
                {"id": 4, "nombre": "Peso Corporal"}, 
                {"id": 5, "nombre": "Estiramiento"}
            ]
            for data in tipos:
                db.session.add(TipoEjercicio(ID_tipo_ejercicio=data["id"], nombre=data["nombre"])) 
            db.session.commit()
            
        # 5. Seed Grupos Musculares
        if GrupoMuscular.query.count() == 0:
            musculos = [
                {"id": 1, "nombre": "Pecho"}, {"id": 2, "nombre": "Espalda"}, {"id": 3, "nombre": "Hombro"}, 
                {"id": 4, "nombre": "Bíceps"}, {"id": 5, "nombre": "Tríceps"}, {"id": 6, "nombre": "Pierna (Cuádriceps)"}, 
                {"id": 7, "nombre": "Pierna (Femorales)"}, {"id": 8, "nombre": "Abdomen"}
            ]
            for data in musculos:
                db.session.add(GrupoMuscular(idgrupo_muscular=data["id"], nombre=data["nombre"])) # ID MANUAL
            db.session.commit()

        # 6. Seed Objetivos
        if Objetivo.query.count() == 0:
            objetivos_frecuentes = [
                {"id": 1, "descripcion": "Hipertrofia (Aumento muscular)"}, 
                {"id": 2, "descripcion": "Pérdida de Peso (Definición)"}, 
                {"id": 3, "descripcion": "Fuerza Máxima"}, 
                {"id": 4, "descripcion": "Resistencia Muscular"},
                {"id": 5, "descripcion": "Mantenimiento General"}
            ]
            for data in objetivos_frecuentes:
                db.session.add(Objetivo(idobjetivo=data["id"], descripcion=data["descripcion"])) # ID MANUAL
            db.session.commit()

        if TipoAccion.query.count() == 0:
            acciones_base = [
                {"id": 1, "nombre": "CREAR"},
                {"id": 2, "nombre": "MODIFICAR"},
                {"id": 3, "nombre": "ELIMINAR"},
                {"id": 4, "nombre": "LOGIN"}
            ]
            for data in acciones_base:
                db.session.add(TipoAccion(ID_tipo_accion=data["id"], nombre_accion=data["nombre"]))
            db.session.commit()

        # Registrar el filtro de Jinja con la función robusta
        app.jinja_env.filters['currency'] = format_currency_robust

        # ---------------------------------------------

    # Registro de Blueprints (Módulos)
    app.register_blueprint(auth_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(routines_bp)
    app.register_blueprint(reports_bp)

    @app.get("/")
    @login_required # Asegura que solo usuarios logueados accedan
    def dashboard():
        # 1. Obtener el total de Clientes
        total_clientes = Cliente.query.count()
        
        # 2. Obtener el total de Rutinas
        total_rutinas = Rutina.query.count()
        
        # 3. Obtener el total de Asistencias (por ejemplo, del día o un periodo)
        # Ejemplo simple: total histórico de registros de asistencia
        total_asistencias = Asistencia.query.count()
        
        # 4. Obtener el Total de Ingresos Acumulados
        # Necesitarías una columna 'monto' en tu modelo Ingreso
        # Si 'Ingreso' tiene una columna 'monto', puedes usar una función de agregación:
        from sqlalchemy import func
        total_ingresos = DetallePago.query.with_entities(func.sum(DetallePago.monto)).scalar() or 0.00
        
        # Formatear el ingreso para mostrarlo como moneda (opcional)
        ingresos_formateados = f"${total_ingresos:,.2f}"

        # Renderizar la plantilla y pasarle los datos
        return render_template(
            'dashboard.html', 
            total_clientes=total_clientes, 
            total_rutinas=total_rutinas, 
            total_asistencias=total_asistencias, 
            total_ingresos=ingresos_formateados # Pasa la variable formateada
        )

    # Manejo de error 403 (Acceso Denegado)
    @app.errorhandler(403)
    def forbidden(e):
        flash("No tienes permisos para esta acción","warning")
        return redirect(url_for("dashboard"))

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=8010)