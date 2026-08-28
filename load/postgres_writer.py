import logging
import re
import uuid
from pathlib import Path

import pandas as pd
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values

from config.settings import (
    DATA_OUTPUT_DIR,
    POSTGRES_DB,
    POSTGRES_HOST,
    POSTGRES_PASS,
    POSTGRES_PORT,
    POSTGRES_USER,
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class PostgresCsvLoader:
    _INT_RANGES = {
        "smallint": (-32768, 32767),
        "integer": (-2147483648, 2147483647),
        "bigint": (-9223372036854775808, 9223372036854775807),
    }

    def __init__(self):
        self._validate_env()

    def _validate_env(self):
        missing = []
        if not POSTGRES_HOST:
            missing.append("POSTGRES_HOST")
        if not POSTGRES_DB:
            missing.append("POSTGRES_DB")
        if not POSTGRES_USER:
            missing.append("POSTGRES_USER")
        if not POSTGRES_PASS:
            missing.append("POSTGRES_PASS")

        if missing:
            missing_vars = ", ".join(missing)
            raise ValueError(f"Faltan variables de entorno para Postgres: {missing_vars}")

    @staticmethod
    def _validate_identifier(identifier: str, label: str):
        if not identifier or not _IDENTIFIER_RE.match(identifier):
            raise ValueError(f"{label} invalido: {identifier!r}")

    @staticmethod
    def _normalize_empty(value):
        if value is None:
            return None
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    def _connect(self):
        return psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            dbname=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASS,
        )

    def _get_table_columns(self, conn, schema: str, table: str):
        query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
        """

        with conn.cursor() as cur:
            cur.execute(query, (schema, table))
            return [row[0] for row in cur.fetchall()]

    def _get_table_uuid_columns(self, conn, schema: str, table: str):
        query = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
              AND data_type = 'uuid'
        """

        with conn.cursor() as cur:
            cur.execute(query, (schema, table))
            return {row[0] for row in cur.fetchall()}

    def _get_table_column_types(self, conn, schema: str, table: str):
        query = """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
        """

        with conn.cursor() as cur:
            cur.execute(query, (schema, table))
            return {row[0]: row[1] for row in cur.fetchall()}

    @staticmethod
    def _is_valid_uuid(value) -> bool:
        if value is None:
            return True
        if not isinstance(value, str):
            return False
        try:
            uuid.UUID(value)
            return True
        except (ValueError, AttributeError, TypeError):
            return False

    @staticmethod
    def _is_int_like(value) -> bool:
        if value is None:
            return True
        if isinstance(value, int):
            return True
        if not isinstance(value, str):
            return False
        text = value.strip()
        if text == "":
            return True
        if text[0] in {"+", "-"}:
            text = text[1:]
        return text.isdigit()

    @classmethod
    def _is_int_in_range(cls, value, data_type: str) -> bool:
        if value is None:
            return True
        min_value, max_value = cls._INT_RANGES[data_type]
        try:
            num = int(str(value).strip())
        except (TypeError, ValueError):
            return False
        return min_value <= num <= max_value

    @staticmethod
    def _resolve_csv_path(csv_path: str) -> Path:
        source = Path(csv_path)
        if source.exists() and source.is_file():
            return source

        # Si el usuario pasa solo el nombre del archivo, intentamos en data_output/
        if len(source.parts) == 1:
            candidate = DATA_OUTPUT_DIR / source.name
            if candidate.exists() and candidate.is_file():
                return candidate

        raise FileNotFoundError(
            f"CSV no encontrado: {source}. Probado tambien en: {DATA_OUTPUT_DIR / source.name}"
        )

    def insert_csv(
        self,
        csv_path: str,
        table_name: str,
        schema_name: str = "public",
        delimiter: str = ",",
        encoding: str = "utf-8",
        chunk_size: int = 5000,
        truncate_before_insert: bool = False,
        dry_run: bool = False,
    ):
        self._validate_identifier(schema_name, "Schema")
        self._validate_identifier(table_name, "Tabla")

        source = self._resolve_csv_path(csv_path)

        conn = self._connect()
        total_inserted = 0

        try:
            table_columns = self._get_table_columns(conn, schema_name, table_name)
            table_uuid_columns = self._get_table_uuid_columns(conn, schema_name, table_name)
            table_column_types = self._get_table_column_types(conn, schema_name, table_name)
            if not table_columns:
                raise ValueError(f"No existe la tabla destino {schema_name}.{table_name}")

            normalized_table_cols = {c.lower(): c for c in table_columns}

            reader = pd.read_csv(
                source,
                sep=delimiter,
                encoding=encoding,
                dtype=object,
                chunksize=chunk_size,
            )

            first_chunk = True
            mapped_columns = []

            with conn.cursor() as cur:
                for chunk in reader:
                    if first_chunk:
                        csv_columns = list(chunk.columns)
                        unknown = [c for c in csv_columns if c.lower() not in normalized_table_cols]
                        if unknown:
                            unknown_text = ", ".join(unknown)
                            raise ValueError(
                                f"Columnas del CSV no existen en {schema_name}.{table_name}: {unknown_text}"
                            )

                        mapped_columns = [normalized_table_cols[c.lower()] for c in csv_columns]

                        if truncate_before_insert and not dry_run:
                            truncate_query = sql.SQL("TRUNCATE TABLE {}.{} CASCADE").format(
                                sql.Identifier(schema_name),
                                sql.Identifier(table_name),
                            )
                            cur.execute(truncate_query)
                            logging.info(
                                "Tabla %s.%s truncada antes de insertar.",
                                schema_name,
                                table_name,
                            )

                        first_chunk = False

                    if chunk.empty:
                        continue

                    chunk = chunk.where(pd.notnull(chunk), None)
                    rows = [
                        tuple(self._normalize_empty(value) for value in row)
                        for row in chunk.itertuples(index=False, name=None)
                    ]

                    if not rows:
                        continue

                    for row_idx, row in zip(chunk.index.tolist(), rows):
                        for col_idx, col_name in enumerate(mapped_columns, start=1):
                            value = row[col_idx - 1]
                            csv_line = int(row_idx) + 2  # +1 por base 1 y +1 por cabecera

                            if col_name in table_uuid_columns and not self._is_valid_uuid(value):
                                raise ValueError(
                                    "Discrepancia de tipo UUID en cabecera "
                                    f"'{col_name}' (columna {col_idx}, linea CSV {csv_line}): "
                                    f"valor invalido '{value}'"
                                )

                            col_type = table_column_types.get(col_name)
                            if col_type in self._INT_RANGES:
                                if not self._is_int_like(value):
                                    raise ValueError(
                                        "Discrepancia de tipo numerico en cabecera "
                                        f"'{col_name}' (columna {col_idx}, linea CSV {csv_line}): "
                                        f"se esperaba {col_type}, valor invalido '{value}'"
                                    )
                                if not self._is_int_in_range(value, col_type):
                                    min_value, max_value = self._INT_RANGES[col_type]
                                    raise ValueError(
                                        "Discrepancia de rango numerico en cabecera "
                                        f"'{col_name}' (columna {col_idx}, linea CSV {csv_line}): "
                                        f"{value} fuera de rango para {col_type} "
                                        f"[{min_value}, {max_value}]"
                                    )

                    if dry_run:
                        total_inserted += len(rows)
                        continue

                    insert_sql = sql.SQL("INSERT INTO {}.{} ({}) VALUES %s").format(
                        sql.Identifier(schema_name),
                        sql.Identifier(table_name),
                        sql.SQL(", ").join(sql.Identifier(col) for col in mapped_columns),
                    )

                    execute_values(cur, insert_sql.as_string(cur), rows, page_size=chunk_size)
                    total_inserted += len(rows)

                if first_chunk:
                    raise ValueError("El CSV no contiene filas o esta vacio.")

            if dry_run:
                conn.rollback()
                logging.info(
                    "DRY RUN: Se validaron %s filas para %s.%s sin insertar datos.",
                    total_inserted,
                    schema_name,
                    table_name,
                )
            else:
                conn.commit()
                logging.info(
                    "Carga completada: %s filas insertadas en %s.%s.",
                    total_inserted,
                    schema_name,
                    table_name,
                )

            return total_inserted

        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
