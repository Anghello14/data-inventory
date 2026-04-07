"""
test_oracle_reader.py – Pruebas unitarias para OracleReader.

Usa mocks para evitar conexiones reales a Oracle.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pandas as pd
import pytest

from extract.oracle_reader import OracleReader


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def reader() -> OracleReader:
    return OracleReader(url="oracle+oracledb://user:pass@host:1521/SVC", batch_size=3)


def _make_chunk(n: int, start: int = 0) -> pd.DataFrame:
    """Genera un DataFrame de prueba con n filas."""
    return pd.DataFrame({"id": range(start, start + n), "val": ["x"] * n})


# ---------------------------------------------------------------------------
# Tests de estado de conexión
# ---------------------------------------------------------------------------

class TestConnectionState:
    def test_engine_raises_when_not_connected(self, reader: OracleReader) -> None:
        with pytest.raises(RuntimeError, match="no está conectado"):
            _ = reader.engine

    @patch("extract.oracle_reader.create_engine")
    def test_connect_creates_engine(self, mock_create: MagicMock, reader: OracleReader) -> None:
        mock_create.return_value = MagicMock()
        reader.connect()
        mock_create.assert_called_once()
        assert reader._engine is not None

    @patch("extract.oracle_reader.create_engine")
    def test_disconnect_clears_engine(self, mock_create: MagicMock, reader: OracleReader) -> None:
        mock_engine = MagicMock()
        mock_create.return_value = mock_engine
        reader.connect()
        reader.disconnect()
        mock_engine.dispose.assert_called_once()
        assert reader._engine is None

    @patch("extract.oracle_reader.create_engine")
    def test_context_manager(self, mock_create: MagicMock, reader: OracleReader) -> None:
        mock_create.return_value = MagicMock()
        with reader as r:
            assert r._engine is not None
        assert reader._engine is None


# ---------------------------------------------------------------------------
# Tests de read_table
# ---------------------------------------------------------------------------

class TestReadTable:
    @patch("extract.oracle_reader.create_engine")
    @patch("extract.oracle_reader.pd.read_sql")
    def test_reads_all_pages(self, mock_read_sql: MagicMock, mock_create: MagicMock) -> None:
        """Debe leer hasta agotar los datos (retorna vacío)."""
        mock_create.return_value = MagicMock()
        # Primera página: 3 filas; segunda: vacío → fin
        mock_read_sql.side_effect = [_make_chunk(3), pd.DataFrame()]

        with OracleReader(url="oracle+oracledb://u:p@h:1/S", batch_size=3) as r:
            results = list(r.read_table("MI_TABLA", schema="SCH"))

        assert len(results) == 1
        assert len(results[0]) == 3

    @patch("extract.oracle_reader.create_engine")
    @patch("extract.oracle_reader.pd.read_sql")
    def test_stops_when_chunk_smaller_than_batch(
        self, mock_read_sql: MagicMock, mock_create: MagicMock
    ) -> None:
        """Si la página tiene menos filas que batch_size, es la última."""
        mock_create.return_value = MagicMock()
        mock_read_sql.side_effect = [_make_chunk(2)]   # 2 < batch_size=3

        with OracleReader(url="oracle+oracledb://u:p@h:1/S", batch_size=3) as r:
            results = list(r.read_table("T"))

        assert len(results) == 1
        assert len(results[0]) == 2

    @patch("extract.oracle_reader.create_engine")
    @patch("extract.oracle_reader.pd.read_sql")
    def test_multiple_pages(
        self, mock_read_sql: MagicMock, mock_create: MagicMock
    ) -> None:
        """Múltiples páginas completas seguidas de un DataFrame vacío."""
        mock_create.return_value = MagicMock()
        mock_read_sql.side_effect = [
            _make_chunk(3, start=0),
            _make_chunk(3, start=3),
            pd.DataFrame(),
        ]
        with OracleReader(url="oracle+oracledb://u:p@h:1/S", batch_size=3) as r:
            results = list(r.read_table("T"))

        assert len(results) == 2
        total = sum(len(r) for r in results)
        assert total == 6


# ---------------------------------------------------------------------------
# Tests de count_rows
# ---------------------------------------------------------------------------

class TestCountRows:
    @patch("extract.oracle_reader.create_engine")
    def test_count_returns_integer(self, mock_create: MagicMock) -> None:
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.scalar.return_value = 42
        mock_engine.connect.return_value = mock_conn
        mock_create.return_value = mock_engine

        with OracleReader(url="oracle+oracledb://u:p@h:1/S", batch_size=100) as r:
            count = r.count_rows("MI_TABLA", schema="SCH")

        assert count == 42
        assert isinstance(count, int)


# ---------------------------------------------------------------------------
# Tests de _full_table_name
# ---------------------------------------------------------------------------

class TestFullTableName:
    def test_with_schema(self, reader: OracleReader) -> None:
        assert reader._full_table_name("TABLA", "SCH") == "SCH.TABLA"

    def test_without_schema_uses_default(self, reader: OracleReader) -> None:
        result = reader._full_table_name("TABLA", None)
        # Debe incluir el schema por defecto
        assert "TABLA" in result


# ---------------------------------------------------------------------------
# Tests de validación de identificadores
# ---------------------------------------------------------------------------

class TestIdentifierValidation:
    def test_valid_identifier(self, reader: OracleReader) -> None:
        assert reader._full_table_name("MI_TABLA", "MI_ESQUEMA") == "MI_ESQUEMA.MI_TABLA"

    def test_invalid_table_name_raises(self, reader: OracleReader) -> None:
        with pytest.raises(ValueError, match="inválido"):
            reader._full_table_name("MI TABLA", "SCH")

    def test_invalid_schema_raises(self, reader: OracleReader) -> None:
        with pytest.raises(ValueError, match="inválido"):
            reader._full_table_name("TABLA", "SCH;DROP TABLE--")

    def test_sql_injection_in_table_raises(self, reader: OracleReader) -> None:
        with pytest.raises(ValueError):
            reader._full_table_name("TABLA; DROP TABLE X--", "SCH")

    def test_numbers_in_identifier_allowed(self, reader: OracleReader) -> None:
        result = reader._full_table_name("TABLA2", "SCH1")
        assert result == "SCH1.TABLA2"
