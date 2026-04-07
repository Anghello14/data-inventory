"""
test_csv_writer.py – Pruebas unitarias para CsvWriter.

No requiere conexión a Oracle ni a ningún servicio externo.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from load.csv_writer import CsvWriter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "id": [1, 2, 3],
        "nombre": ["Ana", "Luis", "Pedro"],
        "monto": [100.5, 200.0, 300.75],
    })


@pytest.fixture
def writer(tmp_path: Path) -> CsvWriter:
    return CsvWriter(
        output_dir=tmp_path / "output",
        manifest_filename="manifest.json",
    )


# ---------------------------------------------------------------------------
# Tests de write()
# ---------------------------------------------------------------------------

class TestWrite:
    def test_creates_csv_file(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        path = writer.write(sample_df, "test.csv")
        assert path.exists()

    def test_auto_adds_csv_extension(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        path = writer.write(sample_df, "sin_extension")
        assert path.suffix == ".csv"

    def test_row_count(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        path = writer.write(sample_df, "datos.csv")
        lines = path.read_text(encoding="utf-8").splitlines()
        # encabezado + 3 filas
        assert len(lines) == 4

    def test_header_columns(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        path = writer.write(sample_df, "datos.csv")
        header = path.read_text(encoding="utf-8").splitlines()[0]
        assert "id" in header
        assert "nombre" in header
        assert "monto" in header

    def test_no_index_by_default(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        path = writer.write(sample_df, "datos.csv")
        df_read = pd.read_csv(path)
        assert "Unnamed: 0" not in df_read.columns

    def test_manifest_registered_after_write(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        writer.write(sample_df, "datos.csv")
        assert len(writer.manifest) == 1

    def test_manifest_entry_has_sha256(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        writer.write(sample_df, "datos.csv")
        assert "sha256" in writer.manifest[0]
        assert len(writer.manifest[0]["sha256"]) == 64


# ---------------------------------------------------------------------------
# Tests de write_chunks()
# ---------------------------------------------------------------------------

class TestWriteChunks:
    def test_creates_multiple_files(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        chunks = (sample_df.iloc[[i]] for i in range(len(sample_df)))
        paths = writer.write_chunks(chunks, "datos")
        assert len(paths) == 3

    def test_files_are_numbered(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        chunks = [sample_df.iloc[[0]], sample_df.iloc[[1]]]
        paths = writer.write_chunks(iter(chunks), "tabla_x")
        names = [p.name for p in paths]
        assert "tabla_x_part0001.csv" in names
        assert "tabla_x_part0002.csv" in names

    def test_manifest_has_all_entries(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        chunks = [sample_df, sample_df]
        writer.write_chunks(iter(chunks), "tabla_y")
        assert len(writer.manifest) == 2


# ---------------------------------------------------------------------------
# Tests de save_manifest()
# ---------------------------------------------------------------------------

class TestSaveManifest:
    def test_creates_manifest_file(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        writer.write(sample_df, "datos.csv")
        manifest_path = writer.save_manifest()
        assert manifest_path.exists()

    def test_manifest_is_valid_json(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        writer.write(sample_df, "datos.csv")
        manifest_path = writer.save_manifest()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_manifest_total_archivos(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        writer.write(sample_df, "a.csv")
        writer.write(sample_df, "b.csv")
        manifest_path = writer.save_manifest()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["total_archivos"] == 2

    def test_manifest_includes_extra_metadata(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        writer.write(sample_df, "datos.csv")
        manifest_path = writer.save_manifest(extra_metadata={"version": "1.0", "proyecto": "SPE"})
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["version"] == "1.0"
        assert data["proyecto"] == "SPE"

    def test_manifest_archivos_list(self, writer: CsvWriter, sample_df: pd.DataFrame) -> None:
        writer.write(sample_df, "datos.csv")
        manifest_path = writer.save_manifest()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert isinstance(data["archivos"], list)
        assert len(data["archivos"]) == 1
        assert data["archivos"][0]["filas"] == 3
        assert data["archivos"][0]["columnas"] == 3


# ---------------------------------------------------------------------------
# Tests del separador personalizado
# ---------------------------------------------------------------------------

class TestDelimiter:
    def test_pipe_delimiter(self, tmp_path: Path, sample_df: pd.DataFrame) -> None:
        writer = CsvWriter(output_dir=tmp_path, delimiter="|")
        path = writer.write(sample_df, "datos_pipe.csv")
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert "|" in first_line

    def test_semicolon_delimiter(self, tmp_path: Path, sample_df: pd.DataFrame) -> None:
        writer = CsvWriter(output_dir=tmp_path, delimiter=";")
        path = writer.write(sample_df, "datos_sc.csv")
        df_read = pd.read_csv(path, sep=";")
        assert list(df_read.columns) == ["id", "nombre", "monto"]


# ---------------------------------------------------------------------------
# Edge case: DataFrame vacío
# ---------------------------------------------------------------------------

class TestEmptyDataFrame:
    def test_write_empty_df(self, writer: CsvWriter) -> None:
        df = pd.DataFrame(columns=["a", "b"])
        path = writer.write(df, "empty.csv")
        assert path.exists()
        assert len(writer.manifest) == 1
        assert writer.manifest[0]["filas"] == 0
