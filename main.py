"""
Punto de entrada principal del pipeline ETL de auditoría.

Flujo de ejecución:
  1. Configurar logging con timestamp único por corrida.
  2. Leer el archivo YAML con la configuración de tablas.
  3. Por cada tabla: extraer datos crudos → segregar → guardar Excel.
"""
import logging
import yaml
from datetime import datetime
from pathlib import Path

# Importaciones de módulos propios del pipeline
from extract.oracle_reader import OracleReader       # Lector de Oracle
from load.excel_writer import save_triad_excel       # Escritor de archivos Excel
from transform.profiler import segregate_data        # Motor de clasificación CLEAN/DIRTY


def setup_logging():
    """
    Configura el sistema de logging del pipeline.

    Crea un archivo de log único por cada ejecución con el formato:
      logs/Log_YYYYMMDD_HHMMSS.log

    Salida dual: archivo en disco + consola (stdout).
    """
    # Directorio de logs — se crea si no existe
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Nombre dinámico basado en la fecha/hora de inicio del pipeline
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"Log_{timestamp}.log"

    # Configuración del logger raíz
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Handler para escritura en archivo
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setFormatter(formatter)

    # Handler para salida por consola
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    # Limpiar handlers previos (evita duplicados si se llama más de una vez)
    logger.handlers = []
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logging.info(f"Log de auditoria iniciado: {log_path.name}")


def run_pipeline():
    """
    Orquesta el pipeline completo de extracción y clasificación de datos.

    Pasos:
      1. Inicializa el logging con timestamp único.
      2. Lee la configuración de tablas desde el YAML.
      3. Extrae cada tabla en bruto desde Oracle (sin modificar).
      4. Clasifica registros en CLEAN y DIRTY según criterios de calidad.
      5. Exporta tres archivos Excel por tabla: CLEAN, DIRTY y SUMMARY.
    """
    # PASO 1 — Iniciar logging antes de cualquier operación
    setup_logging()
    logging.info("INICIANDO PIPELINE DE AUDITORIA")

    # PASO 2 — Leer configuración de tablas desde el archivo YAML
    try:
        with open("config/tablas.yaml", "r") as f:
            # Obtiene el diccionario de tablas; devuelve {} si la clave no existe
            tables_config = yaml.safe_load(f).get('tablas', {})
    except Exception as e:
        logging.error(f"Error al leer configuracion YAML: {e}")
        return  # Aborta el pipeline si no puede leer la configuración

    # Instancia del lector de Oracle — establece conexión en modo Thin
    reader = OracleReader()

    try:
        # PASO 3 — Iterar sobre cada tabla definida en el YAML
        for table_name in tables_config.keys():
            logging.info(f"--- PROCESANDO TABLA: {table_name} ---")

            # 3a. Extracción total cruda — paginada por bloques para no saturar RAM
            df_raw = reader.extract_table_paginated(table_name)

            # 3b. Leer metadatos de la tabla (clave primaria, columna de fecha, tipo de período)
            meta = tables_config[table_name]

            # PASO 4 — Segregación estricta: no se limpia nada, solo se clasifica
            df_clean, df_dirty, df_summary, df_null_cols = segregate_data(
                df_raw,
                table_name,
                pk=meta.get('pk'),                   # Columna clave primaria para detectar duplicados
                col_fecha=meta.get('col_fecha'),      # Columna de fecha para validación de rango temporal
                period_type=meta.get('periodo_tipo'), # Tipo de período: 'mensual', 'anual' o 'completa'
            )

            # PASO 5 — Guardar los tres archivos Excel de resultados
            save_triad_excel(df_clean, df_dirty, df_summary, df_null_cols, table_name)

            logging.info(
                f"Tabla {table_name} finalizada. "
                f"Limpios: {len(df_clean)} | Sucios: {len(df_dirty)}"
            )

    except Exception as e:
        # Captura cualquier error no controlado durante el procesamiento de tablas
        logging.error(f"Error en la ejecucion del pipeline: {e}")
    finally:
        # Siempre cerrar la conexión a Oracle, aunque haya errores
        reader.close()
        logging.info("PIPELINE FINALIZADO.")


# Punto de entrada cuando se ejecuta el script directamente
if __name__ == "__main__":
    run_pipeline()