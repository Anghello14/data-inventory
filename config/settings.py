"""
Configuración centralizada del proyecto write_csv.

Define rutas de directorios y credenciales de conexión a Oracle.
Todas las variables aquí definidas son importadas por los demás módulos.
"""
import os
from pathlib import Path

# ----------------------------------------------------------------
# RUTAS DEL PROYECTO
# BASE_DIR apunta a la raíz del proyecto (directorio write_csv/)
# ----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # Sube dos niveles desde config/
DATA_OUTPUT_DIR = BASE_DIR / "data_output"          # Carpeta donde se guardan los Excel de salida
LOGS_DIR = BASE_DIR / "logs"                        # Carpeta de archivos de log por ejecución
SQLITE_DB_PATH = BASE_DIR / "extraccion" / "control_extraccion.db"  # BD de control (no usado actualmente)

# Crear directorios si no existen al importar este módulo
for folder in [DATA_OUTPUT_DIR, LOGS_DIR]:
    folder.mkdir(exist_ok=True)

# ----------------------------------------------------------------
# CREDENCIALES Y CONFIGURACIÓN DE ORACLE
# Asegúrate de que coincidan con los valores de tu contenedor Docker.
# ----------------------------------------------------------------
ORACLE_USER = "hospital_admin"   # Usuario de la base de datos Oracle
ORACLE_PASS = "Hospital123"      # Contraseña del usuario Oracle
ORACLE_HOST = "localhost"        # Host donde corre Oracle (Docker en local)
ORACLE_PORT = "1522"             # Puerto expuesto por el contenedor Docker
ORACLE_SERVICE = "XEPDB1"        # Nombre del servicio/PDB de Oracle

# DSN (Data Source Name) — cadena de conexión en formato host:puerto/servicio
# Usada por oracledb en modo Thin (sin instalación de Oracle Client)
DSN = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"