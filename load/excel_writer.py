"""
Módulo de escritura de archivos Excel de salida.

Genera tres archivos por tabla procesada:
  - {TABLA}_CLEAN.xlsx    → Registros que pasaron todos los criterios de calidad.
  - {TABLA}_DIRTY.xlsx    → Registros rechazados con su motivo de rechazo.
  - {TABLA}_SUMMARY.xlsx  → Comparativo estadístico (2 hojas: SUMMARY y NULLS_BY_COLUMN).
"""
import pandas as pd
import logging
from config.settings import DATA_OUTPUT_DIR  # Ruta de salida definida en settings.py


def save_triad_excel(df_clean, df_dirty, df_summary, df_null_cols, table):
    """
    Guarda los tres archivos Excel de resultados para una tabla.

    Parámetros:
      df_clean    -- DataFrame con registros válidos (sin columnas 100% nulas).
      df_dirty    -- DataFrame con registros rechazados + columna REJECTION_REASON.
      df_summary  -- DataFrame de una fila con métricas de calidad de la tabla.
      df_null_cols-- DataFrame con conteo y porcentaje de nulos por columna.
      table       -- Nombre de la tabla (se usa como prefijo en los nombres de archivo).

    Retorna:
      Tupla con las rutas (Path) de los tres archivos generados.
    """
    # Crear directorio de salida si no existe (parents=True crea subdirectorios)
    DATA_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ----------------------------------------------------------------
    # ARCHIVO 1 — CLEAN
    # Contiene únicamente los registros que superaron todos los criterios.
    # Las columnas 100% nulas fueron removidas por el profiler.
    # ----------------------------------------------------------------
    path_clean = DATA_OUTPUT_DIR / f"{table}_CLEAN.xlsx"
    df_clean.to_excel(path_clean, index=False, engine='openpyxl')
    logging.info(f"[{table}] CLEAN guardado: {path_clean.name}  ({len(df_clean)} registros)")

    # ----------------------------------------------------------------
    # ARCHIVO 2 — DIRTY
    # Contiene los registros rechazados con la columna REJECTION_REASON
    # indicando el/los criterios que fallaron (separados por ' | ').
    # ----------------------------------------------------------------
    path_dirty = DATA_OUTPUT_DIR / f"{table}_DIRTY.xlsx"
    df_dirty.to_excel(path_dirty, index=False, engine='openpyxl')
    logging.info(f"[{table}] DIRTY guardado: {path_dirty.name}  ({len(df_dirty)} registros)")

    # ----------------------------------------------------------------
    # ARCHIVO 3 — SUMMARY (comparativo de calidad)
    # Dos hojas:
    #   · SUMMARY         → métricas globales de la tabla (1 fila)
    #   · NULLS_BY_COLUMN → detalle de nulos y tipo por cada columna
    # ----------------------------------------------------------------
    path_summary = DATA_OUTPUT_DIR / f"{table}_SUMMARY.xlsx"
    with pd.ExcelWriter(path_summary, engine='openpyxl') as writer:
        # Hoja 1: métricas consolidadas
        df_summary.to_excel(writer, sheet_name='SUMMARY', index=False)
        # Hoja 2: detalle de nulos columna por columna
        df_null_cols.to_excel(writer, sheet_name='NULLS_BY_COLUMN', index=False)
    logging.info(f"[{table}] SUMMARY guardado: {path_summary.name}")

    # Retornar las rutas de los tres archivos para trazabilidad
    return path_clean, path_dirty, path_summary