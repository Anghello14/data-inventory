import pandas as pd
import logging

from transform.profiler import DataProfiler


def test_vacios_en_nullable_no_mandan_a_dirty():
    df = pd.DataFrame(
        {
            "OBLIGATORIO": [None, "", "valor"],
            "OPCIONAL": [None, "", None],
        }
    )
    config = {"pk": None, "not_null": ["OBLIGATORIO"]}

    profiler = DataProfiler(df.copy(), "TABLA_TEST", config)
    df_clean, df_dirty, _, _ = profiler.analizar()

    assert len(df_dirty) == 2
    assert len(df_clean) == 1
    assert df_dirty["REJECTION_REASON"].str.contains("OBLIGATORIO vacio", na=False).all()
    assert not df_dirty["REJECTION_REASON"].str.contains("OPCIONAL vacio", na=False).any()


def test_not_null_totalmente_vacio_no_manda_todo_a_dirty():
    df = pd.DataFrame(
        {
            "OBLIGATORIO": [None, "", "   "],
            "OTRA": [1, 2, 3],
        }
    )
    config = {"pk": None, "not_null": ["OBLIGATORIO"]}

    profiler = DataProfiler(df.copy(), "TABLA_TEST", config)
    df_clean, df_dirty, _, _ = profiler.analizar()

    assert len(df_clean) == 3
    assert len(df_dirty) == 0


def test_loguea_columna_muerta_aunque_sea_nullable(caplog):
    df = pd.DataFrame(
        {
            "OPCIONAL": [None, "", "   "],
            "OTRA": [1, 2, 3],
        }
    )
    config = {"pk": None, "not_null": []}

    profiler = DataProfiler(df.copy(), "TABLA_TEST", config)

    with caplog.at_level(logging.INFO):
        df_clean, df_dirty, _, _ = profiler.analizar()

    assert len(df_dirty) == 0
    assert len(df_clean) == 3
    assert "Columnas totalmente vacías en chunk" in caplog.text
    assert "OPCIONAL" in caplog.text
