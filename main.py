"""
Orquestador Principal - Proyecto SPE
Maneja separadores visuales tanto en consola (print) como en archivo (logging).
"""
import yaml
import logging
import time
import os
from datetime import datetime
from pathlib import Path

from extract.oracle_reader import OracleReader
from transform.profiler import DataProfiler
from load.excel_writer import generar_excel_inventario
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
    inicio_proceso = time.time()
    
    # Separador de inicio de sesión
    logging.info("="*60)
    logging.info(f" INICIO DE EJECUCIÓN - ID: {timestamp_run}")
    logging.info("="*60)
    
    reader = OracleReader()
    
    try:
        with open('config/tablas.yaml', 'r', encoding='utf-8') as f:
            config_maestra = yaml.safe_load(f)
        
        esquema = config_maestra.get('esquema_origen', 'SPE')
        tablas_dict = config_maestra.get('tablas', {})
        total = len(tablas_dict)

        for i, (nombre_tabla, config_tabla) in enumerate(tablas_dict.items(), 1):
            
            # SEPARADOR VISUAL: Ahora usamos logging para que quede en el archivo .log
            # Esto ayuda a identificar bloques de datos al abrir el TXT
            logging.info(f"{'-'*70}")
            logging.info(f" TABLA {i}/{total}: {nombre_tabla}")
            logging.info(f"{'-'*70}")

            check_excel = DATA_OUTPUT_DIR / f"INVENTARIO_{nombre_tabla}.xlsx"
            check_masivo = DATA_OUTPUT_DIR / f"INVENTARIO_{nombre_tabla}_DATOS_MASIVOS.xlsx"

            if check_excel.exists() or check_masivo.exists():
                logging.info(f"STATUS: SKIP (Ya procesada)")
                continue
            
            try:
                # 1. Extracción
                df_raw = reader.extract_table_paginated(esquema, nombre_tabla)
                
                if df_raw.empty:
                    logging.info(f"STATUS: VACÍA")
                    continue

                # 2. Perfilado
                profiler = DataProfiler(df_raw, nombre_tabla, config_tabla)
                df_clean, df_dirty, df_summary, df_nulls = profiler.analizar()

                # 3. Escritura
                generar_excel_inventario(nombre_tabla, df_clean, df_dirty, df_summary, df_nulls)
                
            except Exception as e:
                logging.error(f"ERROR en tabla {nombre_tabla}: {str(e)}")

        logging.info("="*60)
        logging.info(f"RESUMEN: Pipeline finalizado en {round((time.time()-inicio_proceso)/60, 2)} min")
        logging.info("="*60)

    except Exception as e:
        logging.error(f"FALLO CRÍTICO: {e}")
    finally:
        reader.close()

if __name__ == "__main__":
    ejecutar_inventario_completo()