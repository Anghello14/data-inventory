import yaml
import logging
import time
import os
from datetime import datetime

from extract.oracle_reader import OracleReader
from transform.profiler import DataProfiler
from load.excel_writer import generar_excel_inventario
from config.settings import DATA_OUTPUT_DIR

# --- CONFIGURACIÓN DE LOGS DINÁMICOS ---
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
    logging.info(f"=== INICIANDO PIPELINE (ID: {timestamp_run}) ===")
    
    reader = OracleReader()
    
    try:
        with open('config/tablas.yaml', 'r', encoding='utf-8') as f:
            config_maestra = yaml.safe_load(f)
        
        esquema = config_maestra.get('esquema_origen', 'SPE')
        tablas_dict = config_maestra.get('tablas', {})
        total = len(tablas_dict)

        for i, (nombre_tabla, config_tabla) in enumerate(tablas_dict.items(), 1):
            ruta_excel = DATA_OUTPUT_DIR / f"INVENTARIO_{nombre_tabla}.xlsx"

            # --- LÓGICA DE IDEMPOTENCIA ---
            if ruta_excel.exists():
                logging.info(f"[{i}/{total}] SKIP: {nombre_tabla} ya existe (Idempotencia activa).")
                continue
            
            logging.info(f"[{i}/{total}] PROCESANDO: {nombre_tabla}")
            
            try:
                # 1. Extracción
                df_raw = reader.extract_table_paginated(esquema, nombre_tabla)
                
                if df_raw.empty:
                    # Creamos un archivo pequeño o registro para evitar re-procesar tablas vacías
                    logging.info(f"Tabla {nombre_tabla} vacía.")
                    continue

                # 2. Perfilado
                profiler = DataProfiler(df_raw, nombre_tabla, config_tabla)
                df_clean, df_dirty, df_summary, df_nulls = profiler.analizar()

                # 3. Escritura
                generar_excel_inventario(nombre_tabla, df_clean, df_dirty, df_summary, df_nulls)
                
            except Exception as e:
                logging.error(f"Fallo en tabla {nombre_tabla}: {str(e)}")
                # Opcional: eliminar archivo corrupto si quedó a medias para que la próxima vez se reintente

        logging.info(f"=== PIPELINE FINALIZADO EN {round((time.time()-inicio_proceso)/60, 2)} MIN ===")

    except Exception as e:
        logging.error(f"Error crítico: {e}")
    finally:
        reader.close()

if __name__ == "__main__":
    ejecutar_inventario_completo()