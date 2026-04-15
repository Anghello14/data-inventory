"""
Script de recuperación de emergencia.
Reconstruye el REPORTE_MAESTRO tal como existía el 14/04/2026 antes de ser
sobreescrito por main_masivas.py el 15/04/2026 a las 13:10:51.

Estrategia:
  1. Parsea el log pipeline_20260414_084752.log para extraer las listas
     tablas_vacias, tablas_masivas y tablas_pocos_registros.
  2. Lee TODOS los archivos INVENTARIO_*.xlsx de data_output/ que fueron
     creados/modificados el 14/04/2026 (excluye los del 15/04).
  3. Llama a consolidar_inventario() con esos datos y guarda el reporte
     reconstruido como REPORTE_MAESTRO_MIGRACION_SPE_RECUPERADO.xlsx.
"""

import re
import os
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from config.settings import DATA_OUTPUT_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

LOG_ABRIL14 = Path("logs/pipeline_20260414_084752.log")
ARCHIVO_RECUPERADO = DATA_OUTPUT_DIR / "REPORTE_MAESTRO_MIGRACION_SPE_RECUPERADO.xlsx"

# ── 1. Parsear el log del 14/04 ──────────────────────────────────────────────

def parsear_log_abril14(ruta_log: Path):
    """Extrae las clasificaciones de tablas del log del 14/04."""
    tablas_vacias = []
    tablas_masivas = []
    tablas_pocos_registros = []
    detalle_constraints = []

    tabla_actual = None
    re_procesando = re.compile(r'PROCESANDO \d+/\d+: (.+)$')
    re_masiva     = re.compile(r'TABLA MASIVA: (\S+) \((\d+) reg\)')
    re_pocos      = re.compile(r'TABLA CON POCOS REGISTROS: (\S+) \((\d+)\)')
    re_vacia      = re.compile(r'STATUS: TABLA VAC')

    with open(ruta_log, encoding='utf-8', errors='replace') as f:
        for linea in f:
            m_proc = re_procesando.search(linea)
            if m_proc:
                tabla_actual = m_proc.group(1).strip()
                continue

            m_masiva = re_masiva.search(linea)
            if m_masiva:
                tablas_masivas.append({
                    'nombre': m_masiva.group(1),
                    'registros': int(m_masiva.group(2))
                })
                continue

            m_pocos = re_pocos.search(linea)
            if m_pocos:
                tablas_pocos_registros.append({
                    'nombre': m_pocos.group(1),
                    'registros': int(m_pocos.group(2))
                })
                continue

            if re_vacia.search(linea) and tabla_actual:
                tablas_vacias.append({'nombre': tabla_actual, 'registros': 0})
                continue

    logging.info(f"Tablas vacías encontradas en log:          {len(tablas_vacias)}")
    logging.info(f"Tablas masivas encontradas en log:         {len(tablas_masivas)}")
    logging.info(f"Tablas con pocos registros encontradas:    {len(tablas_pocos_registros)}")
    return tablas_vacias, tablas_masivas, tablas_pocos_registros, detalle_constraints


# ── 2. Identificar inventarios del 14/04 ─────────────────────────────────────

def inventarios_abril14():
    """Lista los INVENTARIO_*.xlsx creados/modificados el 14/04/2026."""
    fecha_limite = datetime(2026, 4, 15, 0, 0, 0)
    archivos = []
    for f in DATA_OUTPUT_DIR.iterdir():
        if f.name.startswith("INVENTARIO_") and f.name.endswith(".xlsx") \
                and not f.name.startswith("~$"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime)
            if mtime < fecha_limite:
                archivos.append(f.name)
            else:
                logging.warning(f"Excluido (modificado el 15/04): {f.name}  ({mtime})")
    logging.info(f"Inventarios del 14/04 que se usarán: {len(archivos)}")
    return archivos


# ── 3. Consolidar (versión local sin tocar el reporte maestro original) ──────

def consolidar_recuperacion(tablas_vacias, tablas_masivas,
                             tablas_pocos_registros, detalle_constraints,
                             archivos_inventario):
    lista_analisis = []
    lista_columnas = []

    logging.info(f"Consolidando {len(archivos_inventario)} archivos de inventario...")

    for nombre_archivo in archivos_inventario:
        ruta_full = DATA_OUTPUT_DIR / nombre_archivo
        try:
            with pd.ExcelFile(ruta_full) as xls:
                if 'ANALISIS_TECNICO' in xls.sheet_names:
                    df_res = pd.read_excel(xls, sheet_name='ANALISIS_TECNICO')
                    lista_analisis.append(df_res)
                if 'DETALLE_COLUMNAS' in xls.sheet_names:
                    df_cols = pd.read_excel(xls, sheet_name='DETALLE_COLUMNAS')
                    df_mapeo = df_cols[['TIPO_ORACLE_PANDAS',
                                        'SUGERENCIA_POSTGRES',
                                        'SUGERENCIA_MONGODB']].copy()
                    lista_columnas.append(df_mapeo)
        except Exception as e:
            logging.error(f"Error procesando {nombre_archivo}: {e}")

    df_vacias  = pd.DataFrame(tablas_vacias)  if tablas_vacias  else pd.DataFrame(columns=['nombre', 'registros'])
    df_masivas = pd.DataFrame(tablas_masivas) if tablas_masivas else pd.DataFrame(columns=['nombre', 'registros'])
    df_pocos   = pd.DataFrame(tablas_pocos_registros) if tablas_pocos_registros else pd.DataFrame(columns=['nombre', 'registros'])
    df_constraints = pd.DataFrame(detalle_constraints) if detalle_constraints else pd.DataFrame()

    resumen_constraints = []
    if not df_constraints.empty:
        for tipo, col, desc in [
            ('PRIMARY KEY (PK)', 'PK',     'Identificadores únicos de tabla'),
            ('FOREIGN KEY (FK)', 'FK',     'Relaciones de integridad referencial'),
            ('UNIQUE',           'UNIQUE', 'Restricciones de unicidad'),
            ('CHECK',            'CHECK',  'Validaciones de dominio de datos'),
        ]:
            resumen_constraints.append({
                'TIPO_RESTRICCION':    tipo,
                'TOTAL_ENCONTRADAS':  len(df_constraints[df_constraints[col] != 'N/A']),
                'DESCRIPCION':         desc
            })
    df_resumen_const = pd.DataFrame(resumen_constraints)

    if lista_columnas:
        df_maestro_tipos = pd.concat(lista_columnas, ignore_index=True)
        df_maestro_tipos = df_maestro_tipos.drop_duplicates().sort_values(by='TIPO_ORACLE_PANDAS')
    else:
        df_maestro_tipos = pd.DataFrame(columns=['TIPO_ORACLE_PANDAS',
                                                   'SUGERENCIA_POSTGRES',
                                                   'SUGERENCIA_MONGODB'])

    try:
        with pd.ExcelWriter(ARCHIVO_RECUPERADO, engine='openpyxl') as writer:
            if lista_analisis:
                pd.concat(lista_analisis, ignore_index=True).to_excel(
                    writer, sheet_name='INVENTARIO_GENERAL', index=False)
            df_maestro_tipos.to_excel(
                writer, sheet_name='CATALOGO_TIPOS_DATOS', index=False)
            if not df_constraints.empty:
                df_constraints.to_excel(
                    writer, sheet_name='DETALLE_CONSTRAINTS', index=False)
                df_resumen_const.to_excel(
                    writer, sheet_name='RESUMEN_INTEGRIDAD', index=False)
            df_vacias.to_excel(writer,  sheet_name='TABLAS_VACIAS', index=False)
            df_masivas.to_excel(writer, sheet_name='TABLAS_MASIVAS', index=False)
            df_pocos.to_excel(writer,   sheet_name='TABLAS_POCOS_REGISTROS', index=False)

        logging.info(f"✅  REPORTE RECUPERADO GUARDADO EN: {ARCHIVO_RECUPERADO}")
    except Exception as e:
        logging.error(f"Error al guardar el reporte recuperado: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.info("="*60)
    logging.info(" INICIO DE RECUPERACIÓN DE REPORTE MAESTRO ANTERIOR")
    logging.info("="*60)

    if not LOG_ABRIL14.exists():
        raise FileNotFoundError(f"No se encontró el log: {LOG_ABRIL14}")

    vacias, masivas, pocos, constraints = parsear_log_abril14(LOG_ABRIL14)
    archivos = inventarios_abril14()

    if not archivos:
        logging.error("No se encontraron archivos INVENTARIO del 14/04. Abortando.")
    else:
        consolidar_recuperacion(vacias, masivas, pocos, constraints, archivos)
