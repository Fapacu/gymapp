from flask import current_app
from datetime import datetime, date, timedelta, time
from passlib.hash import pbkdf2_sha256 as hasher
from flask_login import UserMixin
from sqlalchemy import CheckConstraint
from extensions import db

# =========================
# Tablas de Seguridad
# =========================
class Rol(db.Model):
    __tablename__ = "rol"
    ID_rol = db.Column(db.Integer, primary_key=True)
    nombre_rol = db.Column(db.String(45), nullable=False)  # 'ADMIN' | 'PERSONAL'
    descripcion = db.Column(db.String(100))

class Funcionario(db.Model, UserMixin):
    __tablename__ = "funcionario"
    ID_funcionario = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(45), nullable=False)
    apellido = db.Column(db.String(45), nullable=False)
    cedula = db.Column(db.String(20), unique=True, nullable=False)
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    domicilio = db.Column(db.String(100))
    usuario = db.Column(db.String(45), unique=True, nullable=False)
    contrasena = db.Column(db.String(255), nullable=False)
    ID_rol = db.Column(db.Integer, db.ForeignKey("rol.ID_rol"), nullable=False)
    activo = db.Column(db.Boolean, default=True) # Campo añadido para la desactivación/activación
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)

    rol = db.relationship("Rol")

    # Propiedad añadida para evitar el error "no tiene la propiedad id" (InvalidRequestError)
    @property
    def id(self):
        return self.ID_funcionario

    def get_id(self):
        return str(self.ID_funcionario)

    def set_password(self, raw):
        self.contrasena = hasher.hash(raw)

    def check_password(self, raw):
        return hasher.verify(raw, self.contrasena)

# =========================
# Clientes
# =========================
class Cliente(db.Model):
    __tablename__ = "cliente"
    ID_cliente = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(70), nullable=False)
    apellido = db.Column(db.String(70), nullable=False)
    cedula = db.Column(db.String(20), unique=True, nullable=False)
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(100))
    direccion = db.Column(db.String(100))
    fecha_nacimiento = db.Column(db.Date)
    genero = db.Column(db.Enum('M', 'F', 'Otro'))
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    activo = db.Column(db.Boolean, default=True)

# =========================
# Asistencias
# =========================
# En models.py, modifica la clase Asistencia

class Asistencia(db.Model):
    __tablename__ = "asistencia"
    ID_asistencia = db.Column(db.Integer, primary_key=True)
    ID_cliente = db.Column(db.Integer, db.ForeignKey("cliente.ID_cliente"), nullable=False)
    ID_funcionario = db.Column(db.Integer, db.ForeignKey('funcionario.ID_funcionario'), nullable=True) 
    funcionario = db.relationship('Funcionario', backref='asistencias_registradas')
    
    # --- CAMBIO IMPORTANTE: Cambiado a DateTime para permitir el filtrado por fecha y reportes ---
    hora_entrada = db.Column(db.DateTime) 
    hora_salida = db.Column(db.DateTime) # También debe ser DateTime si se registra en el mismo campo
    # ------------------------------------------------------------------------------------------
    
    observaciones = db.Column(db.Text)

    cliente = db.relationship("Cliente")


# -----------------------------------------------------
# Tablas de Auditoría
# -----------------------------------------------------

class TipoAccion(db.Model):
    __tablename__ = "tipo_accion"
    ID_tipo_accion = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre_accion = db.Column(db.String(45))
    # No necesita más relaciones aquí

class Acciones(db.Model):
    __tablename__ = "acciones"
    ID_accion = db.Column(db.Integer, primary_key=True) # El SQL lo tiene sin autoincrement, pero debería ser auto
    ID_funcionario = db.Column(db.Integer, db.ForeignKey("funcionario.ID_funcionario"), nullable=False)
    tabla_afectada = db.Column(db.String(50), nullable=False)
    ID_tipo_accion = db.Column(db.Integer, db.ForeignKey("tipo_accion.ID_tipo_accion"), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    fecha_accion = db.Column(db.DateTime, default=datetime.utcnow)

    # Relaciones para conveniencia en la consulta
    funcionario = db.relationship("Funcionario")
    tipo_accion = db.relationship("TipoAccion")

# =========================
# Suscripciones / Pagos
# =========================
class TipoSuscripcion(db.Model):
    __tablename__ = "tipo_suscripcion"
    ID_tipo_suscripcion = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    periodo_dias = db.Column(db.Integer, nullable=False)
    precio = db.Column(db.Numeric(14,2), nullable=False)
    beneficios = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)

class Suscripcion(db.Model):
    __tablename__ = "suscripcion"
    ID_suscripcion = db.Column(db.Integer, primary_key=True)
    ID_cliente = db.Column(db.Integer, db.ForeignKey("cliente.ID_cliente"), nullable=False)
    ID_tipo_suscripcion = db.Column(db.Integer, db.ForeignKey("tipo_suscripcion.ID_tipo_suscripcion"), nullable=False)
    fecha_inicio = db.Column(db.Date, nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=False)
    fecha_registro = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.Enum('Activa','Vencida','Cancelada','Pendiente'), default='Activa')
    observaciones = db.Column(db.Text)

    cliente = db.relationship("Cliente")
    tipo = db.relationship("TipoSuscripcion")

class DetallePago(db.Model):
    __tablename__ = "detalle_pago"
    ID_detalle_pago = db.Column(db.Integer, primary_key=True)
    monto = db.Column(db.Numeric(14,2), nullable=False)
    fecha_pago = db.Column(db.DateTime, default=datetime.utcnow)
    metodo_pago = db.Column(db.Enum('Efectivo','Tarjeta','Transferencia','Otro'), nullable=False)
    estado_pago = db.Column(db.Enum('Pendiente','Pagado','Cancelado'), default='Pendiente')
    descripcion = db.Column(db.String(100))
    ID_funcionario = db.Column(db.Integer, db.ForeignKey("funcionario.ID_funcionario"), nullable=False)
    suscripcion_ID_suscripcion = db.Column(db.Integer, db.ForeignKey("suscripcion.ID_suscripcion"), nullable=False)

    funcionario = db.relationship("Funcionario")
    suscripcion = db.relationship("Suscripcion")

class Comprobante(db.Model):
    __tablename__ = "comprobante"
    # la tabla de tu schema NO tiene AUTO_INCREMENT
    idcomprobante = db.Column(db.Integer, primary_key=True)
    detalle_pago_ID_detalle_pago = db.Column(db.Integer, db.ForeignKey("detalle_pago.ID_detalle_pago"), nullable=False)
    numero = db.Column(db.String(20), unique=True, nullable=False)
    fecha_emision = db.Column(db.DateTime, nullable=False)
    monto_total = db.Column(db.Numeric(14,2))
    emitido_por = db.Column(db.Integer, db.ForeignKey("funcionario.ID_funcionario"), nullable=False)

    detalle = db.relationship("DetallePago")
    emisor = db.relationship("Funcionario")

# =========================
# Rutinas (modelo simple + asignación)
# =========================
rutina_musculo = db.Table('rutina_musculo',
    db.Column('rutina_id', db.Integer, db.ForeignKey('rutina.ID_rutina'), primary_key=True),
    db.Column('musculo_id', db.Integer, db.ForeignKey('grupo_muscular.idgrupo_muscular'), primary_key=True)
)

class GrupoMuscular(db.Model):
    __tablename__ = "grupo_muscular"
    idgrupo_muscular = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(45), nullable=False)


class Objetivo(db.Model):
    __tablename__ = "objetivo"
    idobjetivo = db.Column(db.Integer, primary_key=True, autoincrement=True) 
    descripcion = db.Column(db.String(45), nullable=False)

class TipoEjercicio(db.Model):
    __tablename__ = "tipo_ejercicio"
    ID_tipo_ejercicio = db.Column(db.Integer, primary_key=True, autoincrement=True) 
    nombre = db.Column(db.String(40), nullable=False)

class Rutina(db.Model):
    __tablename__ = "rutina"
    ID_rutina = db.Column(db.Integer, primary_key=True)
    nombre_rutina = db.Column(db.String(100), nullable=False)
    observaciones = db.Column(db.Text)
    idobjetivo = db.Column(db.Integer, db.ForeignKey("objetivo.idobjetivo"), nullable=False)
    creado_por = db.Column(db.Integer, db.ForeignKey("funcionario.ID_funcionario"), nullable=False)
    descripcion = db.Column(db.String(45))  # usaremos esto como "resumen/plan corto"

    objetivo = db.relationship("Objetivo")
    creador = db.relationship("Funcionario")
    grupos_musculares = db.relationship('GrupoMuscular', secondary=rutina_musculo, lazy='subquery',
                                        backref=db.backref('rutinas', lazy=True))

class RutinaAsignacion(db.Model):
    __tablename__ = "rutina_asignacion"
    # la tabla de tu schema NO tiene AUTO_INCREMENT
    idrutina_asignacion = db.Column(db.Integer, primary_key=True)
    ID_cliente = db.Column(db.Integer, db.ForeignKey("cliente.ID_cliente"), nullable=False)
    ID_rutina = db.Column(db.Integer, db.ForeignKey("rutina.ID_rutina"), nullable=False)
    asignado_por = db.Column(db.Integer, db.ForeignKey("funcionario.ID_funcionario"), nullable=False)
    desde = db.Column(db.Date, nullable=False)
    hasta = db.Column(db.Date, nullable=False)
    vigente = db.Column(db.Boolean)

    cliente = db.relationship("Cliente")
    rutina = db.relationship("Rutina")
    asignador = db.relationship("Funcionario")

class RutinaDetalle(db.Model):
    __tablename__ = "rutina_detalle"
    ID_rutina_detalle = db.Column(db.Integer, primary_key=True)
    ID_rutina = db.Column(db.Integer, db.ForeignKey("rutina.ID_rutina"), nullable=False)
    
    # Nuevo: Relaciones a las categorías
    ID_grupo_muscular = db.Column(db.Integer, db.ForeignKey("grupo_muscular.idgrupo_muscular"), nullable=False)
    ID_tipo_ejercicio = db.Column(db.Integer, db.ForeignKey("tipo_ejercicio.ID_tipo_ejercicio"), nullable=False)
    
    nombre_ejercicio = db.Column(db.String(100), nullable=False)
    series = db.Column(db.Integer)
    repeticiones = db.Column(db.String(20)) # Puede ser '10-12' o 'Fallo'
    descanso_seg = db.Column(db.Integer)
    orden = db.Column(db.Integer) # Para saber el orden de ejecución

    rutina = db.relationship("Rutina", backref=db.backref('detalles', cascade="all, delete-orphan", lazy=True))
    grupo_muscular = db.relationship("GrupoMuscular")
    tipo_ejercicio = db.relationship("TipoEjercicio")

# =========================
# Utilidades de negocio
# =========================
def estado_cliente_general(cliente_id: int) -> str:
    """
    'al día' si tiene suscripción Activa y fecha_vencimiento >= hoy.
    'por vencer' si Activa pero vence en <= ALERT_DAYS_BEFORE días.
    'en mora' si no hay activa o está vencida.
    """
    today = date.today()
    days_before = int(current_app.config.get("ALERT_DAYS_BEFORE", 5))

    # Usamos directamente la clase Suscripcion ya definida arriba en este mismo archivo
    sus = (Suscripcion.query
           .filter_by(ID_cliente=cliente_id)
           .order_by(Suscripcion.fecha_vencimiento.desc())
           .first())
    if not sus:
        return "en mora"
    if sus.estado == 'Activa' and sus.fecha_vencimiento >= today:
        if (sus.fecha_vencimiento - today).days <= days_before:
            return "por vencer"
        return "al día"
    return "en mora"

def next_int_id_from_timestamp() -> int:
    """Genera un ID entero usando YYYYMMDDHHMMSSmmm (corto a 12+ dígitos si deseas)."""
    return int(datetime.utcnow().strftime("%Y%m%d%H%M%S%f")[:15])