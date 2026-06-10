import pandas as pd
import logging
import os
from pathlib import Path
from config.settings import DATA_OUTPUT_DIR


CSV_ROW_LIMIT = 1_048_576
CSV_SAFETY_MARGIN = 100
MAX_ROWS_PER_FILE = CSV_ROW_LIMIT - CSV_SAFETY_MARGIN


def _normalizar_texto_a_minuscula(df):
    # Convierte a minúsculas todas las columnas de texto conservando nulos.
    columnas_texto = df.select_dtypes(include=['object', 'string']).columns
    for col in columnas_texto:
        df[col] = df[col].where(df[col].isna(), df[col].astype(str).str.lower())
    return df


def _escribir_csv_particionado(df, ruta_base, max_rows_per_file):
    """
    Escribe un DataFrame en uno o varios CSVs con límite de filas por archivo.

    El archivo base se convierte en:
    - *_001.csv, *_002.csv, ...
    """
    if df is None or df.empty:
        return

    carpeta = ruta_base.parent
    nombre_base = ruta_base.stem
    extension = ruta_base.suffix

    archivos_existentes = sorted(carpeta.glob(f"{nombre_base}_*.csv"))

    if archivos_existentes:
        ultimo_archivo = archivos_existentes[-1]
        try:
            indice_archivo = int(ultimo_archivo.stem.rsplit('_', 1)[-1])
        except ValueError:
            indice_archivo = 1
            ultimo_archivo = carpeta / f"{nombre_base}_{indice_archivo:03d}{extension}"
    else:
        indice_archivo = 1
        ultimo_archivo = carpeta / f"{nombre_base}_{indice_archivo:03d}{extension}"

    def _contar_filas_datos(ruta_csv: Path):
        if not ruta_csv.exists():
            return 0
        with ruta_csv.open('r', encoding='utf-8', newline='') as f:
            total_lineas = sum(1 for _ in f)
        return max(total_lineas - 1, 0)

    filas_en_actual = _contar_filas_datos(ultimo_archivo)
    inicio = 0

    while inicio < len(df):
        if filas_en_actual >= max_rows_per_file:
            indice_archivo += 1
            ultimo_archivo = carpeta / f"{nombre_base}_{indice_archivo:03d}{extension}"
            filas_en_actual = _contar_filas_datos(ultimo_archivo)

        espacio_disponible = max_rows_per_file - filas_en_actual
        filas_a_escribir = min(espacio_disponible, len(df) - inicio)
        fin = inicio + filas_a_escribir
        df_chunk = df.iloc[inicio:fin]

        modo_append = os.path.exists(ultimo_archivo)
        df_chunk.to_csv(
            ultimo_archivo,
            mode='a',
            header=not modo_append,
            index=False,
            encoding='utf-8'
        )

        filas_en_actual += filas_a_escribir
        inicio = fin

def acumular_csv_inventario(nombre_tabla, df_clean, df_dirty, timestamp, total_registros_tabla=None):
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
        total_registros_tabla (int|None): Conteo total de filas de la tabla para decidir
            modo particionado cuando el procesamiento es por chunks.
    """
    nombre_tabla_archivo = nombre_tabla.lower()

    # Escala automáticamente: si alguna salida supera el umbral,
    # se guarda en carpeta propia y en archivos particionados.
    filas_clean = len(df_clean) if df_clean is not None else 0
    filas_dirty = len(df_dirty) if df_dirty is not None else 0
    total_estimado = total_registros_tabla if total_registros_tabla is not None else (filas_clean + filas_dirty)
    requiere_particionado = (
        total_estimado > MAX_ROWS_PER_FILE
    )

    if requiere_particionado:
        output_dir = DATA_OUTPUT_DIR / nombre_tabla
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = DATA_OUTPUT_DIR

    ruta_clean = output_dir / f"{nombre_tabla_archivo}_clean_{timestamp}.csv"
    ruta_dirty = output_dir / f"{nombre_tabla_archivo}_dirty_{timestamp}.csv"

    try:
        # --- PROCESAMIENTO DE CLEAN ---
        if df_clean is not None and not df_clean.empty:
            df_clean_copia = df_clean.copy()
            df_clean_copia['TABLA_ORIGEN'] = nombre_tabla
            df_clean_copia['TIMESTAMP_CARGA'] = timestamp
            df_clean_copia = _normalizar_texto_a_minuscula(df_clean_copia)

            if requiere_particionado:
                _escribir_csv_particionado(df_clean_copia, ruta_clean, MAX_ROWS_PER_FILE)
            else:
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

            if requiere_particionado:
                _escribir_csv_particionado(df_dirty_copia, ruta_dirty, MAX_ROWS_PER_FILE)
            else:
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
