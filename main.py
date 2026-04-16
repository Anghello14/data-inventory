import yaml
import logging
import time
import os
from datetime import datetime
from pathlib import Path

from extract.oracle_reader import OracleReader
from transform.profiler import DataProfiler
from load.excel_writer import generar_excel_inventario
from generar_reporte_maestro import consolidar_inventario
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
    
    # Separador visual de inicio
    logging.info("="*60)
    logging.info(f" INICIO DE EJECUCIÓN - ID: {timestamp_run}")
    logging.info("="*60)
    
    reader = OracleReader()
    
    # OBJETOS DE RECOLECCIÓN PARA REPORTE MAESTRO
    tablas_vacias = []
    tablas_masivas = []
    tablas_pocos_registros = []
    detalle_constraints = []
    
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

            check_excel = DATA_OUTPUT_DIR / f"INVENTARIO_{nombre_tabla}.xlsx"

            # IDEMPOTENCIA
            if check_excel.exists():
                logging.info(f"STATUS: SKIP (Archivo Excel ya existe)")
                continue
            
            try:
                # 1. OBTENCIÓN DE CONTEO Y METADATOS (Constraints)
                count = reader.get_count(esquema, nombre_tabla)
                constraints = reader.obtener_restricciones(esquema, nombre_tabla)
                constraints['TABLA'] = nombre_tabla
                detalle_constraints.append(constraints)

                # VALIDACIÓN: TABLAS VACÍAS
                if count == 0:
                    logging.info(f"STATUS: TABLA VACÍA. Registrando...")
                    tablas_vacias.append({'nombre': nombre_tabla, 'registros': 0})
                    continue

                # VALIDACIÓN: TABLAS MASIVAS (> 1,000,000)
                if count > 1000000:
                    logging.warning(f"TABLA MASIVA: {nombre_tabla} ({count} reg). Alimentando objeto y saltando...")
                    tablas_masivas.append({'nombre': nombre_tabla, 'registros': count})
                    continue

                # VALIDACIÓN: POCOS REGISTROS (< 100) - Se procesan pero se marcan
                if count < 100:
                    logging.info(f"TABLA CON POCOS REGISTROS: {nombre_tabla} ({count})")
                    tablas_pocos_registros.append({'nombre': nombre_tabla, 'registros': count})

                # 2. EXTRACCIÓN
                df_raw = reader.extract_table_paginated(esquema, nombre_tabla)
                
                if df_raw.empty:
                    logging.info(f"STATUS: SIN DATOS TRAS EXTRACCIÓN")
                    continue

                # --- FILTRO ANTIBLOQUEO ---
                # Identificamos columnas pesadas por nombre para no procesarlas en el profiler
                # Agregamos 'XML' y 'BLOB' a la búsqueda por si acaso
                cols_pesadas = [c for c in df_raw.columns if any(k in c.upper() for k in ['DESCRIPCION', 'COMENTARIO', 'OBSERVACION', 'XML', 'DATA', 'IMG', 'FILE'])]
                
                if cols_pesadas:
                    logging.info(f"Omitiendo {len(cols_pesadas)} columnas pesadas para el perfilado.")
                    df_input = df_raw.drop(columns=cols_pesadas)
                else:
                    df_input = df_raw
                # --------------------------

                # 3. PERFILADO (Usamos el df_input filtrado)
                if constraints.get('PK') == 'N/A':
                    config_tabla['pk'] = None
                else:
                    config_tabla['pk'] = constraints['PK']

                profiler = DataProfiler(df_input, nombre_tabla, config_tabla)
                df_clean, df_dirty, df_summary, df_nulls = profiler.analizar()

                # 4. ESCRITURA (Usamos los resultados del perfilado optimizado)
                generar_excel_inventario(nombre_tabla, df_clean, df_dirty, df_summary, df_nulls)
                logging.info(f"STATUS: EXITOSO. Inventario generado.")
                
            except Exception as e:
                logging.error(f"ERROR en tabla {nombre_tabla}: {str(e)}")

        # 5. CONSOLIDACIÓN DEL REPORTE MAESTRO
        print(f"\n{'*'*70}")
        logging.info("INICIANDO CONSOLIDACIÓN DEL REPORTE MAESTRO...")
        print(f"{'*'*70}")
        
        consolidar_inventario(tablas_vacias, tablas_masivas, tablas_pocos_registros, detalle_constraints)
        
        logging.info(f"RESUMEN FINAL: Pipeline completado en {round((time.time()-inicio_proceso)/60, 2)} min.")
        logging.info("="*60)

    except Exception as e:
        logging.error(f"FALLO CRÍTICO EN EL FLUJO: {str(e)}")
    finally:
        reader.close()

if __name__ == "__main__":
    ejecutar_inventario_completo()