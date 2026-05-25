import pandas as pd
import logging
import os
from config.settings import DATA_OUTPUT_DIR

def acumular_csv_inventario(nombre_tabla, df_clean, df_dirty, timestamp):
    """
    Acumula df_clean y df_dirty a CSVs con timestamp en el nombre y columnas de trazabilidad.

    - Genera: CLEAN_YYYYMMDD_HHMMSS.csv y DIRTY_YYYYMMDD_HHMMSS.csv
    - Cada fila incluye TABLA_ORIGEN (nombre de tabla) y TIMESTAMP_CARGA (momento de carga)
    - Modo append: si el CSV existe, agrega filas; si no existe, crea con header

    Args:
        nombre_tabla (str): Nombre lógico de la tabla para TABLA_ORIGEN
        df_clean (pd.DataFrame): Registros que pasaron validación
        df_dirty (pd.DataFrame): Registros con errores (incluye REJECTION_REASON)
        timestamp (str): Formato YYYYMMDD_HHMMSS para trazabilidad
    """

    ruta_clean = DATA_OUTPUT_DIR / f"CLEAN_{timestamp}.csv"
    ruta_dirty = DATA_OUTPUT_DIR / f"DIRTY_{timestamp}.csv"

    try:
        # --- PROCESAMIENTO DE CLEAN ---
        if df_clean is not None and not df_clean.empty:
            df_clean_copia = df_clean.copy()
            df_clean_copia['TABLA_ORIGEN'] = nombre_tabla
            df_clean_copia['TIMESTAMP_CARGA'] = timestamp

            # Determinar si escribir con header (primera vez vs append)
            modo_append = os.path.exists(ruta_clean)
            df_clean_copia.to_csv(
                ruta_clean,
                mode='a',
                header=not modo_append,
                index=False,
                encoding='utf-8'
            )

            filas_clean = len(df_clean_copia)
            logging.info(f"[{nombre_tabla}] {filas_clean} registros CLEAN acumulados a {ruta_clean.name}")

        # --- PROCESAMIENTO DE DIRTY ---
        if df_dirty is not None and not df_dirty.empty:
            df_dirty_copia = df_dirty.copy()
            df_dirty_copia['TABLA_ORIGEN'] = nombre_tabla
            df_dirty_copia['TIMESTAMP_CARGA'] = timestamp

            # Determinar si escribir con header (primera vez vs append)
            modo_append = os.path.exists(ruta_dirty)
            df_dirty_copia.to_csv(
                ruta_dirty,
                mode='a',
                header=not modo_append,
                index=False,
                encoding='utf-8'
            )

            filas_dirty = len(df_dirty_copia)
            logging.info(f"[{nombre_tabla}] {filas_dirty} registros DIRTY acumulados a {ruta_dirty.name}")

        return True

    except Exception as e:
        logging.error(f"[{nombre_tabla}] Error al escribir CSVs acumulativos: {str(e)}")
        return False
