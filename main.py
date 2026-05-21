import yaml
import logging
import time
import os
from datetime import datetime
from pathlib import Path

from extract.oracle_reader import OracleReader
from etl.pipeline import ETLPipeline

timestamp_run = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f"logs/pipeline_{timestamp_run}.log"
os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)


def ejecutar_inventario_completo():
    inicio_proceso = time.time()

    logging.info("=" * 60)
    logging.info(f" INICIO DE EJECUCIÓN - ID: {timestamp_run}")
    logging.info("=" * 60)

    reader = OracleReader()
    estadisticas_globales = []

    try:
        with open('config/etl_config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        esquema = config.get('esquema_origen', 'SPE')
        tablas = config.get('tablas', {})
        pipeline_config = config.get('pipeline', {})
        total = len(tablas)

        for i, (nombre_tabla, config_tabla) in enumerate(tablas.items(), 1):
            print(f"\n{'=' * 70}")
            logging.info(f" PROCESANDO {i}/{total}: {nombre_tabla}")
            print(f"{'=' * 70}")

            try:
                # Crear y ejecutar pipeline para esta tabla
                pipeline = ETLPipeline(nombre_tabla, config_tabla, esquema, reader)
                df_clean, df_dirty = pipeline.ejecutar()

                # Guardar estadísticas
                stats = pipeline.get_estadisticas()
                if stats:
                    estadisticas_globales.append(stats)

            except Exception as e:
                logging.error(f"ERROR en tabla {nombre_tabla}: {str(e)}")

        # RESUMEN FINAL
        print(f"\n{'*' * 70}")
        logging.info("RESUMEN FINAL DEL PIPELINE")
        print(f"{'*' * 70}")

        if estadisticas_globales:
            logging.info(f"Tablas procesadas: {len(estadisticas_globales)}")

        duracion_total = round((time.time() - inicio_proceso) / 60, 2)
        logging.info(f"Pipeline completado en {duracion_total} min.")
        logging.info("=" * 60)

    except Exception as e:
        logging.error(f"FALLO CRÍTICO EN EL FLUJO: {str(e)}")
    finally:
        reader.close()


if __name__ == "__main__":
    ejecutar_inventario_completo()
