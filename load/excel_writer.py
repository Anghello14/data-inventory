"""
Modulo de escritura de resultados.
Optimizado para generar reportes tecnicos en formato Excel (.xlsx).
"""
import pandas as pd
import logging
from config.settings import DATA_OUTPUT_DIR

def generar_excel_inventario(nombre_tabla, df_clean, df_dirty, df_summary, df_nulls):
    """
    Crea un archivo Excel con cuatro pestañas fundamentales para la auditoria:
    1. ANALISIS_TECNICO: Resumen ejecutivo de calidad y peso.
    2. DETALLE_COLUMNAS: Inventario de tipos de datos y nulos.
    3. CLEAN: Registros que cumplen con todas las reglas de integridad.
    4. DIRTY: Registros con errores (Duplicados, ?, Emails invalidos, etc).
    """
    ruta_archivo = DATA_OUTPUT_DIR / f"INVENTARIO_{nombre_tabla}.xlsx"
    
    try:
        with pd.ExcelWriter(ruta_archivo, engine='openpyxl') as writer:
            # Pestaña 1: Resumen Ejecutivo
            df_summary.to_excel(writer, sheet_name='ANALISIS_TECNICO', index=False)
            
            # Pestaña 2: Inventario de Columnas y Mapeo
            df_nulls.to_excel(writer, sheet_name='DETALLE_COLUMNAS', index=False)
            
            # Pestaña 3: Datos Limpios
            if df_clean is not None and not df_clean.empty:
                df_clean.to_excel(writer, sheet_name='CLEAN', index=False)
            else:
                # Crear pestaña vacía con encabezado informativo si no hay datos limpios
                pd.DataFrame({"INFO": ["Sin registros que cumplan las reglas de integridad"]}).to_excel(writer, sheet_name='CLEAN', index=False)
                
            # Pestaña 4: Datos con Error (Dirty)
            if df_dirty is not None and not df_dirty.empty:
                df_dirty.to_excel(writer, sheet_name='DIRTY', index=False)
            else:
                # Crear pestaña vacía si la calidad es del 100%
                pd.DataFrame({"INFO": ["No se detectaron errores de integridad ni caracteres corruptos"]}).to_excel(writer, sheet_name='DIRTY', index=False)

        # Log de confirmación profesional
        logging.info(f"[{nombre_tabla}] Inventario Excel generado exitosamente.")
        return True

    except Exception as e:
        logging.error(f"[{nombre_tabla}] Error al escribir el archivo Excel: {str(e)}")
        return False