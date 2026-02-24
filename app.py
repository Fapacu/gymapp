from datetime import timedelta
from flask import Flask, render_template, redirect, url_for, flash, session
from flask_login import login_required
from config import Config
from extensions import db, csrf, login_manager

# Modelos necesarios para el dashboard
from models import (
    Funcionario, Rol, TipoEjercicio, GrupoMuscular,
    Objetivo, TipoSuscripcion, TipoAccion,
    Cliente, Rutina, Asistencia, DetallePago
)

# Blueprints
from auth.routes import auth_bp
from clients.routes import clients_bp
from payments.routes import payments_bp
from attendance.routes import attendance_bp
from routines.routes import routines_bp
from reports.routes import reports_bp

from decimal import Decimal
from sqlalchemy import func


def format_currency_robust(value):
    if value is None:
        return '0,00'
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    formatted_value = "{:,.2f}".format(value)
    return formatted_value.replace(",", "#").replace(".", ",").replace("#", ".")


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.permanent_session_lifetime = timedelta(
        minutes=app.config.get("SESSION_IDLE_MINUTES", 10)
    )

    # Inicializar extensiones
    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    @app.before_request
    def _make_session_permanent():
        session.permanent = True

    # Registrar filtro Jinja
    app.jinja_env.filters['currency'] = format_currency_robust

    # Registrar Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(routines_bp)
    app.register_blueprint(reports_bp)

    @app.get("/")
    @login_required
    def dashboard():
        total_clientes = Cliente.query.count()
        total_rutinas = Rutina.query.count()
        total_asistencias = Asistencia.query.count()
        total_ingresos = (
            DetallePago.query.with_entities(func.sum(DetallePago.monto)).scalar()
            or 0.00
        )

        ingresos_formateados = f"${total_ingresos:,.2f}"

        return render_template(
            'dashboard.html',
            total_clientes=total_clientes,
            total_rutinas=total_rutinas,
            total_asistencias=total_asistencias,
            total_ingresos=ingresos_formateados
        )

    @app.errorhandler(403)
    def forbidden(e):
        flash("No tienes permisos para esta acción", "warning")
        return redirect(url_for("dashboard"))

    return app


app = create_app()