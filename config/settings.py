import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar las variables del archivo .env
load_dotenv()

# ----------------------------------------------------------------
# RUTAS DEL PROYECTO
# ----------------------------------------------------------------
# Si este archivo está en config/settings.py, subimos dos niveles para llegar a la raíz
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_OUTPUT_DIR = BASE_DIR / "data_output"
LOGS_DIR = BASE_DIR / "logs"

# Crear directorios si no existen
for folder in [DATA_OUTPUT_DIR, LOGS_DIR]:
    folder.mkdir(exist_ok=True)

# ----------------------------------------------------------------
# CONFIGURACIÓN DE ORACLE (Desde .env)
# ----------------------------------------------------------------
ORACLE_USER = os.getenv("ORACLE_USER")
ORACLE_PASS = os.getenv("ORACLE_PASS")
ORACLE_HOST = os.getenv("ORACLE_HOST")
ORACLE_PORT = os.getenv("ORACLE_PORT")
ORACLE_SERVICE = os.getenv("ORACLE_SERVICE")

# DSN construido dinámicamente
DSN = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"

# Ruta del cliente (Modo Thick)
ORACLE_CLIENT_PATH = os.getenv("ORACLE_CLIENT_PATH")

# ----------------------------------------------------------------
# CONFIGURACIÓN DE POSTGRESQL (Desde .env)
# ----------------------------------------------------------------
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5435")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASS = os.getenv("POSTGRES_PASS")