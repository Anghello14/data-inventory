"""
Modulo de escritura de resultados.
Soporta archivos unificados .xlsx y exportacion a .csv para tablas masivas (>1M filas).
"""
import pandas as pd
import logging
from config.settings import DATA_OUTPUT_DIR

def generar_excel_inventario(nombre_tabla, df_clean, df_dirty, df_summary, df_nulls):
    """
    Crea un inventario tecnico. Si el volumen supera 1,000,000 de filas,
    utiliza CSV para los datos y Excel solo para el reporte de auditoria.
    """
    try:
        # Límite técnico de seguridad para Excel (Max: 1,048,576)
        LIMITE_EXCEL = 1000000
        total_filas = len(df_clean) if df_clean is not None else 0

        # CASO A: TABLAS MASIVAS (> 1 Millon de filas)
        if total_filas > LIMITE_EXCEL:
            logging.warning(f"[{nombre_tabla}] Volumen masivo detectado ({total_filas} filas). Usando modo CSV.")
            
            # 1. Guardar el ANALISIS en Excel (siempre util para el jefe)
            ruta_analisis = DATA_OUTPUT_DIR / f"INVENTARIO_{nombre_tabla}_DATOS_MASIVOS.xlsx"
            with pd.ExcelWriter(ruta_analisis, engine='openpyxl') as writer:
                df_summary.to_excel(writer, sheet_name='ANALISIS_TECNICO', index=False)
                df_nulls.to_excel(writer, sheet_name='DETALLE_COLUMNAS', index=False)
            
            # 2. Guardar los DATOS en CSV (sin limite de filas)
            if df_clean is not None:
                df_clean.to_csv(DATA_OUTPUT_DIR / f"DATOS_{nombre_tabla}_CLEAN.csv", index=False)
            if df_dirty is not None and not df_dirty.empty:
                df_dirty.to_csv(DATA_OUTPUT_DIR / f"DATOS_{nombre_tabla}_DIRTY.csv", index=False)
            
            logging.info(f"[{nombre_tabla}] Inventario masivo generado (Excel + CSV).")
            return True

        # CASO B: TABLAS ESTÁNDAR (Estructura de pestañas original)
        ruta_archivo = DATA_OUTPUT_DIR / f"INVENTARIO_{nombre_tabla}.xlsx"
        with pd.ExcelWriter(ruta_archivo, engine='openpyxl') as writer:
            df_summary.to_excel(writer, sheet_name='ANALISIS_TECNICO', index=False)
            df_nulls.to_excel(writer, sheet_name='DETALLE_COLUMNAS', index=False)
            
            if df_clean is not None and not df_clean.empty:
                df_clean.to_excel(writer, sheet_name='CLEAN', index=False)
            else:
                pd.DataFrame({"INFO": ["Sin registros limpios"]}).to_excel(writer, sheet_name='CLEAN', index=False)
                
            if df_dirty is not None and not df_dirty.empty:
                df_dirty.to_excel(writer, sheet_name='DIRTY', index=False)
            else:
                pd.DataFrame({"INFO": ["Sin errores detectados"]}).to_excel(writer, sheet_name='DIRTY', index=False)

        logging.info(f"[{nombre_tabla}] Inventario consolidado generado en Excel.")
        return True
    
    except Exception as e:
        logging.error(f"Error critico al escribir resultados para {nombre_tabla}: {str(e)}")
        return False