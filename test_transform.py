import yaml
import logging
import pandas as pd
from extract.oracle_reader import OracleReader
from transform.profiler import DataProfiler
from config.settings import DATA_OUTPUT_DIR

# Configuración de logs para ver el rendimiento en consola
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def ejecutar_prueba_integrada():
    logging.info("Iniciando prueba de integración (Oracle -> Profiler -> Excel 3 Pestañas)")
    reader = OracleReader()
    
    try:
        # 1. Cargar configuración
        with open('config/tablas.yaml', 'r', encoding='utf-8') as f:
            config_maestra = yaml.safe_load(f)
        
        esquema = config_maestra.get('esquema_origen', 'SPE')
        tablas_dict = config_maestra.get('tablas', {})
        
        # Probamos con las primeras 5 tablas para validar la estructura de pestañas
        seleccion_test = list(tablas_dict.keys())[:5]
        
        for nombre_tabla in seleccion_test:
            logging.info(f"==> PROCESANDO: {nombre_tabla}")
            
            # 2. Extracción desde Oracle
            df_raw = reader.extract_table_paginated(esquema, nombre_tabla)
            
            if df_raw.empty:
                logging.info(f"Tabla {nombre_tabla} sin registros. Continuando...")
                continue

            # 3. Perfilado de Datos
            config_tabla = tablas_dict.get(nombre_tabla, {})
            profiler = DataProfiler(df_raw, nombre_tabla, config_tabla)
            df_clean, df_dirty, df_summary, df_nulls = profiler.analizar()

            # 4. ESCRITURA SIMULADA (Un solo archivo, tres pestañas)
            # Definimos la ruta del archivo único para esta tabla
            ruta_excel = DATA_OUTPUT_DIR / f"INVENTARIO_{nombre_tabla}.xlsx"
            
            with pd.ExcelWriter(ruta_excel, engine='openpyxl') as writer:
                # Pestaña 1: Resumen y Análisis Técnico (Combinamos summary y nulls)
                df_summary.to_excel(writer, sheet_name='ANALISIS_TECNICO', index=False)
                # Escribimos el detalle de columnas un poco más abajo en la misma pestaña o en otra
                df_nulls.to_excel(writer, sheet_name='DETALLE_COLUMNAS', index=False)
                
                # Pestaña 2: Datos Limpios
                if not df_clean.empty:
                    df_clean.to_excel(writer, sheet_name='CLEAN', index=False)
                
                # Pestaña 3: Datos con Error
                if not df_dirty.empty:
                    df_dirty.to_excel(writer, sheet_name='DIRTY', index=False)

            logging.info(f"Archivo generado exitosamente: {ruta_excel.name}")

    except Exception as e:
        logging.error(f"Error en la prueba: {e}")
    finally:
        reader.close()
        logging.info("Prueba finalizada.")

if __name__ == "__main__":
    ejecutar_prueba_integrada()