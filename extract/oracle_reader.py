"""
oracle_reader.py – Lectura paginada de tablas Oracle mediante SQLAlchemy.

Clase principal: OracleReader
  - Conecta a Oracle a través de SQLAlchemy (driver oracledb, thin mode).
  - Expone métodos para leer una tabla completa o por rangos de fecha/lote,
    devolviendo los datos en fragmentos (chunks) de tamaño configurable para
    no saturar la memoria.
"""

from __future__ import annotations

import logging
import re
from typing import Generator, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Validación de identificadores Oracle
# ---------------------------------------------------------------------------

_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_$#]*$')


def _validate_identifier(value: str, label: str = "identificador") -> str:
    """
    Valida que *value* sea un identificador Oracle seguro.

    Sólo permite letras, dígitos, guiones bajos, $ y #.  Lanza
    ``ValueError`` si el valor no cumple el patrón.

    Args:
        value: Identificador a validar (nombre de tabla, columna, esquema…).
        label: Nombre descriptivo para el mensaje de error.

    Returns:
        El mismo *value* si es válido.

    Raises:
        ValueError: Si el identificador contiene caracteres no permitidos.
    """
    if not _IDENTIFIER_RE.match(value):
        raise ValueError(
            f"{label} inválido: '{value}'. "
            "Solo se permiten letras, dígitos, '_', '$' y '#'."
        )
    return value


def _validate_identifiers(values: list[str], label: str = "columna") -> list[str]:
    """Valida una lista de identificadores y devuelve la misma lista."""
    return [_validate_identifier(v, label) for v in values]


class OracleReader:
    """Lee datos de Oracle en páginas y los devuelve como DataFrames."""

    def __init__(
        self,
        url: str = settings.SQLALCHEMY_URL,
        batch_size: int = settings.DEFAULT_BATCH_SIZE,
    ) -> None:
        """
        Inicializa el lector con una URL de SQLAlchemy.

        Args:
            url: URL de conexión SQLAlchemy.
                 Ej.: ``oracle+oracledb://user:pass@host:1521/SERVICE``
            batch_size: Número de filas por fragmento.
        """
        self.url = url
        self.batch_size = batch_size
        self._engine: Optional[Engine] = None

    # ------------------------------------------------------------------
    # Gestión de la conexión
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Crea el engine de SQLAlchemy (modo thin, sin Oracle Client)."""
        logger.info("Creando engine SQLAlchemy para Oracle…")
        self._engine = create_engine(
            self.url,
            thick_mode=False,   # oracledb thin mode – no requiere Oracle Client
            pool_pre_ping=True,
        )
        logger.info("Engine creado correctamente.")

    def disconnect(self) -> None:
        """Cierra el engine y libera el pool de conexiones."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
            logger.info("Engine cerrado.")

    def __enter__(self) -> "OracleReader":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Utilidades internas
    # ------------------------------------------------------------------

    @property
    def engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError(
                "El reader no está conectado. Llama a connect() primero "
                "o usa el context manager (with OracleReader() as reader)."
            )
        return self._engine

    def _full_table_name(self, table: str, schema: Optional[str] = None) -> str:
        schema = schema or settings.DEFAULT_SCHEMA
        _validate_identifier(table, "tabla")
        if schema:
            _validate_identifier(schema, "esquema")
        return f"{schema}.{table}" if schema else table

    # ------------------------------------------------------------------
    # Lectura completa con paginación
    # ------------------------------------------------------------------

    def read_table(
        self,
        table: str,
        schema: Optional[str] = None,
        columns: Optional[list[str]] = None,
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Lee una tabla completa en páginas usando OFFSET/FETCH.

        Args:
            table:   Nombre de la tabla.
            schema:  Esquema propietario (usa DEFAULT_SCHEMA si se omite).
            columns: Lista de columnas a seleccionar; ``None`` = todas.

        Yields:
            DataFrame con ``batch_size`` filas como máximo.
        """
        full_name = self._full_table_name(table, schema)
        if columns:
            _validate_identifiers(columns, "columna")
        col_expr = ", ".join(columns) if columns else "*"
        offset = 0

        logger.info("Iniciando lectura de %s (batch_size=%d).", full_name, self.batch_size)

        while True:
            query = text(
                f"SELECT {col_expr} FROM {full_name} "
                f"OFFSET :offset ROWS FETCH NEXT :batch ROWS ONLY"
            )
            with self.engine.connect() as conn:
                chunk = pd.read_sql(query, conn, params={"offset": offset, "batch": self.batch_size})

            if chunk.empty:
                logger.info("Lectura de %s finalizada. Total filas ≈ %d.", full_name, offset)
                break

            logger.debug("Leídas filas %d – %d de %s.", offset + 1, offset + len(chunk), full_name)
            yield chunk
            offset += len(chunk)

            if len(chunk) < self.batch_size:
                logger.info("Último fragmento recibido. Total filas = %d.", offset)
                break

    # ------------------------------------------------------------------
    # Lectura filtrada por rango de fechas
    # ------------------------------------------------------------------

    def read_by_date(
        self,
        table: str,
        col_fecha: str,
        fecha_inicio: str,
        fecha_fin: str,
        schema: Optional[str] = None,
        columns: Optional[list[str]] = None,
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Lee filas de una tabla dentro de un rango de fechas.

        Args:
            table:        Nombre de la tabla.
            col_fecha:    Columna de tipo DATE/TIMESTAMP para el filtro.
            fecha_inicio: Fecha de inicio en formato ``'YYYY-MM-DD'``.
            fecha_fin:    Fecha de fin en formato ``'YYYY-MM-DD'``.
            schema:       Esquema propietario.
            columns:      Columnas a seleccionar.

        Yields:
            DataFrame con hasta ``batch_size`` filas.
        """
        full_name = self._full_table_name(table, schema)
        _validate_identifier(col_fecha, "col_fecha")
        if columns:
            _validate_identifiers(columns, "columna")
        col_expr = ", ".join(columns) if columns else "*"
        offset = 0

        logger.info(
            "Leyendo %s filtrado por %s entre %s y %s.",
            full_name, col_fecha, fecha_inicio, fecha_fin,
        )

        while True:
            query = text(
                f"SELECT {col_expr} FROM {full_name} "
                f"WHERE {col_fecha} BETWEEN TO_DATE(:fi, 'YYYY-MM-DD') "
                f"AND TO_DATE(:ff, 'YYYY-MM-DD') "
                f"ORDER BY {col_fecha} "
                f"OFFSET :offset ROWS FETCH NEXT :batch ROWS ONLY"
            )
            params = {
                "fi": fecha_inicio,
                "ff": fecha_fin,
                "offset": offset,
                "batch": self.batch_size,
            }
            with self.engine.connect() as conn:
                chunk = pd.read_sql(query, conn, params=params)

            if chunk.empty:
                break

            yield chunk
            offset += len(chunk)

            if len(chunk) < self.batch_size:
                break

    # ------------------------------------------------------------------
    # Lectura filtrada por lote
    # ------------------------------------------------------------------

    def read_by_lote(
        self,
        table: str,
        col_lote: str,
        lote: str | int,
        schema: Optional[str] = None,
        columns: Optional[list[str]] = None,
    ) -> Generator[pd.DataFrame, None, None]:
        """
        Lee las filas de un lote específico.

        Args:
            table:    Nombre de la tabla.
            col_lote: Columna que identifica el lote.
            lote:     Valor del lote a filtrar.
            schema:   Esquema propietario.
            columns:  Columnas a seleccionar.

        Yields:
            DataFrame con hasta ``batch_size`` filas.
        """
        full_name = self._full_table_name(table, schema)
        _validate_identifier(col_lote, "col_lote")
        if columns:
            _validate_identifiers(columns, "columna")
        col_expr = ", ".join(columns) if columns else "*"
        offset = 0

        logger.info("Leyendo %s para lote=%s.", full_name, lote)

        while True:
            query = text(
                f"SELECT {col_expr} FROM {full_name} "
                f"WHERE {col_lote} = :lote "
                f"OFFSET :offset ROWS FETCH NEXT :batch ROWS ONLY"
            )
            params = {"lote": lote, "offset": offset, "batch": self.batch_size}
            with self.engine.connect() as conn:
                chunk = pd.read_sql(query, conn, params=params)

            if chunk.empty:
                break

            yield chunk
            offset += len(chunk)

            if len(chunk) < self.batch_size:
                break

    # ------------------------------------------------------------------
    # Conteo de filas
    # ------------------------------------------------------------------

    def count_rows(
        self,
        table: str,
        schema: Optional[str] = None,
    ) -> int:
        """
        Devuelve el número de filas de una tabla.

        Args:
            table:  Nombre de la tabla.
            schema: Esquema propietario.

        Returns:
            Número entero de filas.
        """
        full_name = self._full_table_name(table, schema)
        query = text(f"SELECT COUNT(*) AS cnt FROM {full_name}")
        with self.engine.connect() as conn:
            result = conn.execute(query).scalar()
        return int(result)
