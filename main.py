import yaml
import logging
import time
import os
from datetime import datetime
from pathlib import Path

from extract.oracle_reader import OracleReader
from transform.profiler import DataProfiler
from load.csv_writer import acumular_csv_inventario
from config.settings import DATA_OUTPUT_DIR

# --- CONFIGURACIÓN DE LOGS ---
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
    # Orquesta el pipeline completo: lee config YAML, itera tabla por tabla,
    # extrae datos desde Oracle, los perfila, y acumula registros a CSVs (CLEAN, DIRTY).
    inicio_proceso = time.time()
    
    # Separador visual de inicio
    logging.info("="*60)
    logging.info(f" INICIO DE EJECUCIÓN - ID: {timestamp_run}")
    logging.info("="*60)
    
    # Instancia única de conexión a Oracle; se reutiliza para todas las tablas del ciclo
    reader = OracleReader()

    try:
        with open('config/tablas.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        esquema = config.get('esquema_origen', 'SPE')
        tablas = config.get('tablas', {})
        total = len(tablas)

        for i, (nombre_tabla, config_tabla) in enumerate(tablas.items(), 1):
            # Separador visual por tabla (Consola y Log)
            print(f"\n{'='*70}")
            logging.info(f" PROCESANDO {i}/{total}: {nombre_tabla}")
            print(f"{'='*70}")

            try:
                # 1. OBTENCIÓN DE CONTEO Y METADATOS (Constraints)
                count = reader.get_count(esquema, nombre_tabla)
                constraints = reader.obtener_restricciones(esquema, nombre_tabla)

                # VALIDACIÓN: TABLAS VACÍAS
                if count == 0:
                    logging.info(f"STATUS: TABLA VACÍA. Registrando...")
                    continue

                # VALIDACIÓN: POCOS REGISTROS (< 100) - Se procesan pero se marcan
                if count < 100:
                    logging.info(f"TABLA CON POCOS REGISTROS: {nombre_tabla} ({count})")

                # 2. EXTRACCIÓN Y PROCESAMIENTO EN CHUNKS
                # Conservamos todas las columnas de la fuente para que el CSV final
                # represente la estructura real de la tabla. El filtrado de LOBs/
                # binarios ya ocurre en OracleReader, así que no hace falta excluir
                # columnas de texto como DESCRIPCION en esta etapa.

                # 3. PERFILADO (Usamos el df_input por chunk)
                # Inyectar la PK real al config de la tabla para que el profiler la valide
                if constraints.get('PK') == 'N/A':
                    config_tabla['pk'] = None
                else:
                    config_tabla['pk'] = constraints['PK']

                procesado_al_menos_un_chunk = False
                for df_raw in reader.extract_table_paginated(esquema, nombre_tabla, chunk_size=50000):
                    procesado_al_menos_un_chunk = True
                    df_input = df_raw

                    profiler = DataProfiler(df_input, nombre_tabla, config_tabla)
                    df_clean, df_dirty, df_summary, df_nulls = profiler.analizar()

                    # 4. ESCRITURA (Usamos los resultados del perfilado optimizado)
                    acumular_csv_inventario(
                        nombre_tabla,
                        df_clean,
                        df_dirty,
                        timestamp_run,
                        total_registros_tabla=count,
                    )

                if not procesado_al_menos_un_chunk:
                    logging.info(f"STATUS: SIN DATOS TRAS EXTRACCIÓN")
                    continue

                logging.info(f"STATUS: EXITOSO. Datos acumulados a CSVs.")
                
            except Exception as e:
                logging.error(f"ERROR en tabla {nombre_tabla}: {str(e)}")

        logging.info(f"RESUMEN FINAL: Pipeline completado en {round((time.time()-inicio_proceso)/60, 2)} min.")
        logging.info("="*60)

    except Exception as e:
        # Error no controlado que rompe el flujo global (ej. fallo de configuración)
        logging.error(f"FALLO CRÍTICO EN EL FLUJO: {str(e)}")
    finally:
        # Garantiza el cierre de la conexión Oracle sin importar si hubo error
        reader.close()

if __name__ == "__main__":
    ejecutar_inventario_completo()