import argparse
import logging
import os
from datetime import datetime

from load.postgres_writer import PostgresCsvLoader


def _build_parser():
    parser = argparse.ArgumentParser(
        description="Inserta un CSV en una tabla de Postgres elegida por parametro."
    )
    parser.add_argument("--csv", required=True, help="Ruta al archivo CSV origen")
    parser.add_argument("--tabla", required=True, help="Tabla destino en Postgres")
    parser.add_argument("--schema", default="public", help="Schema destino (default: public)")
    parser.add_argument("--delimiter", default=",", help="Separador del CSV (default: ,)")
    parser.add_argument("--encoding", default="utf-8", help="Encoding del CSV (default: utf-8)")
    parser.add_argument("--chunk-size", type=int, default=5000, help="Tamano de lote por insert")
    parser.add_argument(
        "--truncate",
        action="store_true",
        help="Trunca la tabla antes de insertar",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Valida CSV y tabla pero no inserta datos",
    )
    return parser


def _configure_logging():
    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = f"logs/carga_postgres_{timestamp}.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler(),
        ],
    )


def main():
    parser = _build_parser()
    args = parser.parse_args()

    _configure_logging()

    try:
        loader = PostgresCsvLoader()
        total = loader.insert_csv(
            csv_path=args.csv,
            table_name=args.tabla,
            schema_name=args.schema,
            delimiter=args.delimiter,
            encoding=args.encoding,
            chunk_size=args.chunk_size,
            truncate_before_insert=args.truncate,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            logging.info(
                "DRY RUN completado. Filas validadas para %s.%s: %s",
                args.schema,
                args.tabla,
                total,
            )
        else:
            logging.info(
                "Proceso finalizado. Filas insertadas en %s.%s: %s",
                args.schema,
                args.tabla,
                total,
            )

    except Exception as exc:
        logging.error("Fallo en la carga CSV->Postgres: %s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
