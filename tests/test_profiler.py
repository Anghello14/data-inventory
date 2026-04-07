"""
test_profiler.py – Pruebas unitarias para DataProfiler.

No requiere conexión a Oracle. Trabaja con DataFrames sintéticos.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from transform.profiler import DataProfiler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df() -> pd.DataFrame:
    """DataFrame sintético con distintos tipos de datos y nulos."""
    return pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "nombre": ["Ana", "Luis", None, "Pedro", "Ana"],
        "edad": [25, 30, None, 22, 28],
        "saldo": [100.5, 200.0, 300.75, None, 150.0],
    })


@pytest.fixture
def profiler(sample_df: pd.DataFrame) -> DataProfiler:
    return DataProfiler(sample_df, table_name="TEST")


# ---------------------------------------------------------------------------
# Tests básicos de construcción del perfil
# ---------------------------------------------------------------------------

class TestProfilerBuild:
    def test_build_returns_self(self, profiler: DataProfiler) -> None:
        result = profiler.build()
        assert result is profiler

    def test_profile_has_one_row_per_column(self, profiler: DataProfiler, sample_df: pd.DataFrame) -> None:
        profile = profiler.profile
        assert len(profile) == len(sample_df.columns)

    def test_profile_columns_present(self, profiler: DataProfiler) -> None:
        expected = {"tabla", "columna", "tipo_dato", "total_filas", "nulos",
                    "pct_nulos", "no_nulos", "pct_no_nulos", "cardinalidad", "pct_unicidad"}
        assert expected.issubset(set(profiler.profile.columns))

    def test_table_name_in_profile(self, profiler: DataProfiler) -> None:
        assert (profiler.profile["tabla"] == "TEST").all()


# ---------------------------------------------------------------------------
# Tests de métricas de nulos
# ---------------------------------------------------------------------------

class TestNullMetrics:
    def test_null_count_nombre(self, profiler: DataProfiler) -> None:
        row = profiler.profile.set_index("columna").loc["nombre"]
        assert row["nulos"] == 1

    def test_null_count_id(self, profiler: DataProfiler) -> None:
        row = profiler.profile.set_index("columna").loc["id"]
        assert row["nulos"] == 0

    def test_pct_nulos_nombre(self, profiler: DataProfiler) -> None:
        row = profiler.profile.set_index("columna").loc["nombre"]
        assert row["pct_nulos"] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Tests de cardinalidad
# ---------------------------------------------------------------------------

class TestCardinalidad:
    def test_id_full_cardinalidad(self, profiler: DataProfiler) -> None:
        row = profiler.profile.set_index("columna").loc["id"]
        assert row["cardinalidad"] == 5

    def test_nombre_cardinalidad(self, profiler: DataProfiler) -> None:
        # Ana aparece 2 veces → 3 valores únicos (Ana, Luis, Pedro)
        row = profiler.profile.set_index("columna").loc["nombre"]
        assert row["cardinalidad"] == 3


# ---------------------------------------------------------------------------
# Tests de estadísticas numéricas
# ---------------------------------------------------------------------------

class TestNumericStats:
    def test_numeric_cols_have_min_max(self, profiler: DataProfiler) -> None:
        for col in ("id", "edad", "saldo"):
            row = profiler.profile.set_index("columna").loc[col]
            assert row["min"] is not None
            assert row["max"] is not None

    def test_edad_min_max(self, profiler: DataProfiler) -> None:
        row = profiler.profile.set_index("columna").loc["edad"]
        assert row["min"] == 22
        assert row["max"] == 30


# ---------------------------------------------------------------------------
# Tests de exportación
# ---------------------------------------------------------------------------

class TestExportJson:
    def test_to_dict_returns_list(self, profiler: DataProfiler) -> None:
        result = profiler.to_dict()
        assert isinstance(result, list)
        assert len(result) == 4

    def test_to_json_valid(self, profiler: DataProfiler) -> None:
        json_str = profiler.to_json()
        data = json.loads(json_str)
        assert isinstance(data, list)

    def test_to_json_saves_file(self, profiler: DataProfiler, tmp_path: Path) -> None:
        out = tmp_path / "perfil.json"
        profiler.to_json(out)
        assert out.exists()
        assert out.stat().st_size > 0


class TestExportCsv:
    def test_to_csv_creates_file(self, profiler: DataProfiler, tmp_path: Path) -> None:
        out = tmp_path / "perfil.csv"
        profiler.to_csv(out)
        assert out.exists()

    def test_to_csv_has_header(self, profiler: DataProfiler, tmp_path: Path) -> None:
        out = tmp_path / "perfil.csv"
        profiler.to_csv(out)
        lines = out.read_text(encoding="utf-8").splitlines()
        assert "columna" in lines[0]


class TestExportExcel:
    def test_to_excel_creates_file(self, profiler: DataProfiler, tmp_path: Path) -> None:
        out = tmp_path / "perfil.xlsx"
        profiler.to_excel(out)
        assert out.exists()

    def test_to_excel_readable(self, profiler: DataProfiler, tmp_path: Path) -> None:
        out = tmp_path / "perfil.xlsx"
        profiler.to_excel(out)
        df_read = pd.read_excel(out, sheet_name="Perfil")
        assert len(df_read) == 4


# ---------------------------------------------------------------------------
# Tests de resumen
# ---------------------------------------------------------------------------

class TestSummary:
    def test_summary_keys(self, profiler: DataProfiler) -> None:
        s = profiler.summary()
        assert "tabla" in s
        assert "total_filas" in s
        assert "total_columnas" in s
        assert "columnas_con_nulos" in s

    def test_summary_total_filas(self, profiler: DataProfiler) -> None:
        assert profiler.summary()["total_filas"] == 5

    def test_summary_total_columnas(self, profiler: DataProfiler) -> None:
        assert profiler.summary()["total_columnas"] == 4

    def test_summary_cols_con_nulos(self, profiler: DataProfiler) -> None:
        # nombre, edad, saldo tienen nulos → 3 columnas
        assert profiler.summary()["columnas_con_nulos"] == 3


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame({"a": pd.Series([], dtype=float)})
        profiler = DataProfiler(df, "EMPTY")
        profile = profiler.profile
        assert len(profile) == 1
        assert profile.iloc[0]["total_filas"] == 0
        assert profile.iloc[0]["pct_nulos"] == 0.0

    def test_all_nulls_column(self) -> None:
        df = pd.DataFrame({"x": [None, None, None]})
        profiler = DataProfiler(df, "ALL_NULLS")
        row = profiler.profile.iloc[0]
        assert row["nulos"] == 3
        assert row["pct_nulos"] == pytest.approx(100.0)
        assert row["cardinalidad"] == 0
