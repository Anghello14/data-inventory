from pathlib import Path

# ----------------------------------------------------------------
# RUTAS DEL PROYECTO
# BASE_DIR apunta a la raíz del proyecto (directorio data-inventory/)
BASE_DIR = Path(__file__).resolve().parent          # Sube un nivel desde config/
DATA_OUTPUT_DIR = BASE_DIR / "data_output"          # Carpeta donde se guardan los Excel de salida
LOGS_DIR = BASE_DIR / "logs"                        # Carpeta de archivos de log por ejecución

# Crear directorios si no existen al importar este módulo
for folder in [DATA_OUTPUT_DIR, LOGS_DIR]:
    folder.mkdir(exist_ok=True)

# ----------------------------------------------------------------
# CREDENCIALES Y CONFIGURACIÓN DE ORACLE
ORACLE_USER = "MODER_APE"                                                              # Usuario de la base de datos Oracle
ORACLE_PASS = "ApeSena2025*"                                                           # Contraseña del usuario Oracle
ORACLE_HOST = "172.24.247.16"                                                          # Host donde corre Oracle
ORACLE_PORT = "1521"                                                                   # Puerto expuesto por Oracle
ORACLE_SERVICE = "LETOSDEV_96f_bog.bogrodclientpri.bognoprodexa1.oraclevcn.com"        # Nombre del servicio/PDB de Oracle

# DSN (Data Source Name) — cadena de conexión en formato host:puerto/servicio
# Usada por oracledb en modo Thin (sin instalación de Oracle Client)
DSN = f"{ORACLE_HOST}:{ORACLE_PORT}/{ORACLE_SERVICE}"