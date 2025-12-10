DB_HOST = "localhost"
DB_USER = "root"
DB_PASSWORD = ""         
DB_NAME = "gimnasio_db"

# ——— App settings ———
SECRET_KEY = "fabcontrol444333222_suer777"
SESSION_IDLE_MINUTES = 10          # inactividad (sesión permanente)
ALERT_DAYS_BEFORE = 5              # días previos para “por vencer”

import os

class Config:
    # Exponemos los mismos valores en app.config
    DB_HOST = os.environ.get("DB_HOST", DB_HOST)
    DB_USER = os.environ.get("DB_USER", DB_USER)
    DB_PASSWORD = os.environ.get("DB_PASSWORD", DB_PASSWORD)
    DB_NAME = os.environ.get("DB_NAME", DB_NAME)

    SECRET_KEY = os.environ.get("SECRET_KEY", SECRET_KEY)
    SESSION_IDLE_MINUTES = int(os.environ.get("SESSION_IDLE_MINUTES", SESSION_IDLE_MINUTES))
    ALERT_DAYS_BEFORE = int(os.environ.get("ALERT_DAYS_BEFORE", ALERT_DAYS_BEFORE))

    # Cadena de conexión construida con las variables simples
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}?charset=utf8mb4"
        # Nota: si DB_PASSWORD está vacío, PyMySQL lo maneja bien: root:@host…
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True