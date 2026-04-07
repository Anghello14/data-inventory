"""
settings.py – Configuración central del proyecto ETL.

Carga los parámetros de conexión, rutas de salida y demás valores por
defecto.  Los valores sensibles (usuario/contraseña) deben estar en
variables de entorno o en un archivo .env (nunca en el repositorio).
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Directorios base
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR = BASE_DIR / "logs"

# Crea los directorios si no existen
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Conexión Oracle
# ---------------------------------------------------------------------------
DB_USER = os.environ.get("ORACLE_USER", "usuario")
DB_PASSWORD = os.environ.get("ORACLE_PASSWORD", "contraseña")
DB_HOST = os.environ.get("ORACLE_HOST", "localhost")
DB_PORT = int(os.environ.get("ORACLE_PORT", "1521"))
DB_SERVICE = os.environ.get("ORACLE_SERVICE", "ORCL")

# DSN estilo Easy Connect (oracledb / cx_Oracle)
DSN = f"{DB_HOST}:{DB_PORT}/{DB_SERVICE}"

# URL de SQLAlchemy usando el driver oracledb (thin mode)
SQLALCHEMY_URL = (
    f"oracle+oracledb://{DB_USER}:{DB_PASSWORD}@{DSN}"
)

# ---------------------------------------------------------------------------
# Parámetros de extracción
# ---------------------------------------------------------------------------
DEFAULT_BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "10000"))   # filas por página
DEFAULT_SCHEMA = os.environ.get("ORACLE_SCHEMA", DB_USER.upper())

# ---------------------------------------------------------------------------
# Parámetros de salida
# ---------------------------------------------------------------------------
CSV_DELIMITER = ","
CSV_ENCODING = "utf-8"
MANIFEST_FILENAME = "manifest.json"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE = LOGS_DIR / "etl.log"
