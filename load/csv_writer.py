import pandas as pd
import logging
import os
from config.settings import DATA_OUTPUT_DIR


def _normalizar_texto_a_minuscula(df):
    # Convierte a minúsculas todas las columnas de texto conservando nulos.
    columnas_texto = df.select_dtypes(include=['object', 'string']).columns
    for col in columnas_texto:
        df[col] = df[col].where(df[col].isna(), df[col].astype(str).str.lower())
    return df

def acumular_csv_inventario(nombre_tabla, df_clean, df_dirty, timestamp):
    """
    Escribe df_clean y df_dirty a CSVs por tabla con timestamp y columnas de trazabilidad.

    - Genera: nombretabla_clean_YYYYMMDD_HHMMSS.csv y nombretabla_dirty_YYYYMMDD_HHMMSS.csv
    - Cada fila incluye TABLA_ORIGEN (nombre de tabla) y TIMESTAMP_CARGA (momento de carga)
    - Modo append: si el CSV existe, agrega filas; si no existe, crea con header

    Args:
        nombre_tabla (str): Nombre lógico de la tabla para TABLA_ORIGEN
        df_clean (pd.DataFrame): Registros que pasaron validación
        df_dirty (pd.DataFrame): Registros con errores (incluye REJECTION_REASON)
        timestamp (str): Formato YYYYMMDD_HHMMSS para trazabilidad
    """

    nombre_tabla_archivo = nombre_tabla.lower()
    ruta_clean = DATA_OUTPUT_DIR / f"{nombre_tabla_archivo}_clean_{timestamp}.csv"
    ruta_dirty = DATA_OUTPUT_DIR / f"{nombre_tabla_archivo}_dirty_{timestamp}.csv"

    try:
        # --- PROCESAMIENTO DE CLEAN ---
        if df_clean is not None and not df_clean.empty:
            df_clean_copia = df_clean.copy()
            df_clean_copia['TABLA_ORIGEN'] = nombre_tabla
            df_clean_copia['TIMESTAMP_CARGA'] = timestamp
            df_clean_copia = _normalizar_texto_a_minuscula(df_clean_copia)

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
            df_dirty_copia = _normalizar_texto_a_minuscula(df_dirty_copia)

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
