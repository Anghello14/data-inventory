"""
Modulo de escritura de resultados para tablas masivas.
Genera reportes tecnicos en formato Excel (.xlsx) con solo las pestanas
ANALISIS_TECNICO y DETALLE_COLUMNAS (omite CLEAN y DIRTY).
"""
import pandas as pd
import logging
from config.settings import DATA_OUTPUT_DIR_MASIVAS

def generar_excel_inventario(nombre_tabla, df_summary, df_nulls):
    """
    Crea un archivo Excel con dos pestañas fundamentales para la auditoria de tablas masivas:
    1. ANALISIS_TECNICO: Resumen ejecutivo de calidad y peso.
    2. DETALLE_COLUMNAS: Inventario de tipos de datos y nulos.
    """
    ruta_archivo = DATA_OUTPUT_DIR_MASIVAS / f"INVENTARIO_{nombre_tabla}.xlsx"
    
    try:
        with pd.ExcelWriter(ruta_archivo, engine='openpyxl') as writer:
            # Pestaña 1: Resumen Ejecutivo
            df_summary.to_excel(writer, sheet_name='ANALISIS_TECNICO', index=False)
            
            # Pestaña 2: Inventario de Columnas y Mapeo
            df_nulls.to_excel(writer, sheet_name='DETALLE_COLUMNAS', index=False)

        logging.info(f"[{nombre_tabla}] Inventario Excel (masivas) generado exitosamente.")
        return True

    except Exception as e:
        logging.error(f"[{nombre_tabla}] Error al escribir el archivo Excel: {str(e)}")
        return False
