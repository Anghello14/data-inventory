"""
main.py – Orquestación del pipeline ETL completo.

Flujo:
  1. Carga la configuración de tablas desde config/tablas.yaml.
  2. Por cada tabla activa:
     a. Extract  → Lee la tabla de Oracle en páginas (OracleReader).
     b. Transform → Perfila los datos (DataProfiler).
     c. Load     → Escribe CSVs y genera el manifiesto (CsvWriter).
  3. Guarda el manifiesto global con metadatos de ejecución.

Uso:
    python main.py [--fecha-inicio YYYY-MM-DD] [--fecha-fin YYYY-MM-DD]
                   [--lote LOTE] [--tabla NOMBRE_TABLA]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import yaml

from config import settings
from extract.oracle_reader import OracleReader
from load.csv_writer import CsvWriter
from transform.profiler import DataProfiler


# ---------------------------------------------------------------------------
# Configuración de logging
# ---------------------------------------------------------------------------

def _setup_logging() -> None:
    """Configura el sistema de logging con salida a consola y archivo."""
    log_format = "%(asctime)s [%(levelname)s] %(name)s – %(message)s"
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(settings.LOG_FILE, encoding="utf-8"),
    ]
    logging.basicConfig(level=log_level, format=log_format, handlers=handlers)


# ---------------------------------------------------------------------------
# Carga de configuración de tablas
# ---------------------------------------------------------------------------

def _load_tablas(path: Path) -> list[dict]:
    """Lee el archivo YAML de definición de tablas."""
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("tablas", [])


# ---------------------------------------------------------------------------
# Pipeline por tabla
# ---------------------------------------------------------------------------

def process_table(
    reader: OracleReader,
    writer: CsvWriter,
    tabla_cfg: dict,
    fecha_inicio: str | None = None,
    fecha_fin: str | None = None,
    lote: str | None = None,
) -> None:
    """
    Ejecuta el ciclo extract → transform → load para una sola tabla.

    Args:
        reader:       Instancia conectada de OracleReader.
        writer:       Instancia de CsvWriter.
        tabla_cfg:    Diccionario con la configuración de la tabla.
        fecha_inicio: Fecha inicio para filtrar (opcional).
        fecha_fin:    Fecha fin para filtrar (opcional).
        lote:         Valor de lote para filtrar (opcional).
    """
    logger = logging.getLogger(__name__)
    nombre = tabla_cfg["nombre"]
    schema = tabla_cfg.get("schema")
    col_fecha = tabla_cfg.get("col_fecha")
    col_lote = tabla_cfg.get("col_lote")

    logger.info("─" * 60)
    logger.info("Procesando tabla: %s.%s", schema or settings.DEFAULT_SCHEMA, nombre)

    # -- EXTRACT -----------------------------------------------------------
    if lote and col_lote:
        logger.info("Modo filtro: lote=%s, col_lote=%s", lote, col_lote)
        chunks = reader.read_by_lote(nombre, col_lote, lote, schema=schema)
    elif fecha_inicio and fecha_fin and col_fecha:
        logger.info("Modo filtro: fecha %s → %s, col_fecha=%s", fecha_inicio, fecha_fin, col_fecha)
        chunks = reader.read_by_date(nombre, col_fecha, fecha_inicio, fecha_fin, schema=schema)
    else:
        logger.info("Modo lectura completa.")
        chunks = reader.read_table(nombre, schema=schema)

    # Materializa los chunks para poder perfilar y luego escribir
    all_chunks = list(chunks)

    if not all_chunks:
        logger.warning("No se obtuvieron datos para %s. Se omite.", nombre)
        return

    total_rows = sum(len(c) for c in all_chunks)
    logger.info("Filas extraídas: %d.", total_rows)

    # -- TRANSFORM (perfil sobre el primer chunk como muestra) -----------
    sample = all_chunks[0]
    profiler = DataProfiler(sample, table_name=nombre)
    profiler.build()

    profile_csv = settings.OUTPUT_DIR / f"perfil_{nombre}.csv"
    profiler.to_csv(profile_csv)
    logger.info("Perfil de calidad guardado en %s.", profile_csv)

    summary = profiler.summary()
    logger.info(
        "Resumen calidad – total_cols=%d, cols_con_nulos=%d, pct_nulos_global=%.2f%%",
        summary["total_columnas"],
        summary["columnas_con_nulos"],
        summary["pct_nulos_global"],
    )

    # -- LOAD --------------------------------------------------------------
    base_name = f"data_{nombre.lower()}"
    if len(all_chunks) == 1:
        writer.write(all_chunks[0], f"{base_name}.csv")
    else:
        writer.write_chunks(iter(all_chunks), base_filename=base_name)

    logger.info("Tabla %s procesada con éxito.", nombre)


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline ETL: Oracle → CSV con perfilamiento de calidad."
    )
    parser.add_argument("--fecha-inicio", help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--fecha-fin", help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--lote", help="Valor de lote a procesar")
    parser.add_argument("--tabla", help="Procesar sólo esta tabla (nombre exacto)")
    return parser.parse_args()


def main() -> None:
    _setup_logging()
    logger = logging.getLogger(__name__)
    args = parse_args()

    tablas_path = settings.CONFIG_DIR / "tablas.yaml"
    todas_tablas = _load_tablas(tablas_path)

    # Filtrar por tabla específica si se indicó
    tablas_activas = [
        t for t in todas_tablas
        if t.get("activa", True)
        and (args.tabla is None or t["nombre"].upper() == args.tabla.upper())
    ]

    if not tablas_activas:
        logger.error("No hay tablas activas que procesar.")
        sys.exit(1)

    logger.info("Tablas a procesar: %s", [t["nombre"] for t in tablas_activas])

    writer = CsvWriter(output_dir=settings.OUTPUT_DIR)

    t_inicio = time.monotonic()

    with OracleReader(batch_size=settings.DEFAULT_BATCH_SIZE) as reader:
        for tabla_cfg in tablas_activas:
            try:
                process_table(
                    reader,
                    writer,
                    tabla_cfg,
                    fecha_inicio=args.fecha_inicio,
                    fecha_fin=args.fecha_fin,
                    lote=args.lote,
                )
            except Exception:
                logger.exception("Error procesando tabla '%s'. Se continúa.", tabla_cfg["nombre"])

    writer.save_manifest(
        extra_metadata={
            "parametros": {
                "fecha_inicio": args.fecha_inicio,
                "fecha_fin": args.fecha_fin,
                "lote": args.lote,
                "tabla": args.tabla,
            }
        }
    )

    elapsed = time.monotonic() - t_inicio
    logger.info("Pipeline finalizado en %.2f segundos.", elapsed)


if __name__ == "__main__":
    main()
