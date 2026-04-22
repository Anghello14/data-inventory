import yaml
import logging
import time
import os
from datetime import datetime
from pathlib import Path

from extract.oracle_reader_masivas import OracleReader
from transform.profiler_masivas import DataProfiler
from load.excel_writer_masivas import generar_excel_inventario
from generar_reporte_maestro_masivo import consolidar_inventario
from config.settings import DATA_OUTPUT_DIR_MASIVAS

# --- CONFIGURACIÓN DE LOGS ---
timestamp_run = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f"logs/pipeline_masivas_{timestamp_run}.log"
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
    # Variante del pipeline para tablas masivas (> 1M filas).
    # NO transfiere datos; trabaja exclusivamente con metadatos del diccionario Oracle
    # para generar el inventario sin saturar la red ni la memoria.
    inicio_proceso = time.time()
    
    # Separador visual de inicio
    logging.info("="*60)
    logging.info(f" INICIO DE EJECUCIÓN (MASIVAS) - ID: {timestamp_run}")
    logging.info("="*60)
    
    # Instancia única de conexión a Oracle; se reutiliza para todas las tablas del ciclo
    reader = OracleReader()

    # OBJETOS DE RECOLECCIÓN PARA REPORTE MAESTRO
    tablas_vacias = []
    tablas_masivas = []
    tablas_pocos_registros = []
    detalle_constraints = []
    
    try:
        with open('config/tablas_masivas.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        esquema = config.get('esquema_origen', 'SPE')
        tablas = config.get('tablas', {})
        total = len(tablas)

        for i, (nombre_tabla, config_tabla) in enumerate(tablas.items(), 1):
            # Separador visual por tabla (Consola y Log)
            print(f"\n{'='*70}")
            logging.info(f" PROCESANDO {i}/{total}: {nombre_tabla}")
            print(f"{'='*70}")

            # Ruta esperada del inventario individual; se usa para control de idempotencia
            check_excel = DATA_OUTPUT_DIR_MASIVAS / f"INVENTARIO_{nombre_tabla}.xlsx"

            # IDEMPOTENCIA
            if check_excel.exists():
                logging.info(f"STATUS: SKIP (Archivo Excel ya existe)")
                continue
            
            try:
                # 1. CONTEO
                count = reader.get_count(esquema, nombre_tabla)
                constraints = reader.obtener_restricciones(esquema, nombre_tabla)
                constraints['TABLA'] = nombre_tabla
                detalle_constraints.append(constraints)

                if count == 0:
                    logging.info(f"STATUS: TABLA VACÍA. Registrando...")
                    tablas_vacias.append({'nombre': nombre_tabla, 'registros': 0})
                    continue

                if count < 100:
                    logging.info(f"TABLA CON POCOS REGISTROS: {nombre_tabla} ({count})")
                    tablas_pocos_registros.append({'nombre': nombre_tabla, 'registros': count})

                # 2. METADATOS (sin transferir filas)
                # Enriquecer config_tabla con el conteo real y la PK detectada en Oracle
                config_tabla['total_filas'] = count
                if constraints.get('PK') != 'N/A':
                    config_tabla['pk'] = constraints['PK']
                else:
                    config_tabla['pk'] = None

                metadata = reader.get_metadata_completo(esquema, nombre_tabla, count)
                if not metadata:
                    logging.warning(f"STATUS: SIN METADATOS. Saltando.")
                    continue

                # 3. PERFILADO
                profiler = DataProfiler(metadata, nombre_tabla, config_tabla)
                df_summary, df_nulls = profiler.analizar()

                # 4. ESCRITURA
                generar_excel_inventario(nombre_tabla, df_summary, df_nulls)
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
        # Error no controlado que rompe el flujo global (ej. fallo de configuración)
        logging.error(f"FALLO CRÍTICO EN EL FLUJO: {str(e)}")
    finally:
        # Garantiza el cierre de la conexión Oracle sin importar si hubo error
        reader.close()

if __name__ == "__main__":
    ejecutar_inventario_completo()
