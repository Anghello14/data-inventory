import pandas as pd
import logging
from config.settings import DATA_OUTPUT_DIR

def generar_excel_inventario(nombre_tabla, df_clean, df_dirty, df_summary, df_nulls):
    
    """
    Crea un unico archivo .xlsx por tabla con pestañas:
    1. ANALISIS_TECNICO (Resumen y Dimensionamiento)
    2. DETALLE_COLUMNAS (Mapeo de tipos y Nulos)
    3. CLEAN (Datos listos para migrar)
    4. DIRTY (Datos con errores detectados)
    """
    try:
        # Definimos la ruta del archivo unico
        ruta_archivo = DATA_OUTPUT_DIR / f"INVENTARIO_{nombre_tabla}.xlsx"
        
        # Usamos el motor openpyxl para gestionar multiples pestañas
        with pd.ExcelWriter(ruta_archivo, engine='openpyxl') as writer:
            
            # Pestaña 1: Resumen de Calidad y Peso
            df_summary.to_excel(writer, sheet_name='ANALISIS_TECNICO', index=False)
            
            # Pestaña 2: Auditoria de Columnas (Crucial para el mapeo a Postgres/Mongo)
            df_nulls.to_excel(writer, sheet_name='DETALLE_COLUMNAS', index=False)
            
            # Pestaña 3: Datos Limpios
            if df_clean is not None and not df_clean.empty:
                df_clean.to_excel(writer, sheet_name='CLEAN', index=False)
            else:
                # Si no hay datos limpios, dejamos una hoja informativa
                pd.DataFrame({"INFO": ["No se encontraron registros limpios"]}).to_excel(writer, sheet_name='CLEAN', index=False)
                
            # Pestaña 4: Datos Sucios / Rechazados
            if df_dirty is not None and not df_dirty.empty:
                df_dirty.to_excel(writer, sheet_name='DIRTY', index=False)
            else:
                pd.DataFrame({"INFO": ["No se detectaron errores en esta tabla"]}).to_excel(writer, sheet_name='DIRTY', index=False)

        logging.info(f"[{nombre_tabla}] Inventario consolidado generado en Excel.")
        return True
    
    except Exception as e:
        logging.error(f"Error critico al escribir el Excel para {nombre_tabla}: {str(e)}")
        return False