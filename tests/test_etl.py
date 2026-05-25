import pytest
import pandas as pd
from transform.profiler import DataProfiler
from load.write_csv import CsvWriter
from pathlib import Path
import tempfile


class TestDataProfiler:
    """Tests para validaciones del DataProfiler"""

    def test_deteccion_duplicados_pk(self):
        """Verifica que detecta duplicados en PK"""
        df = pd.DataFrame({
            'ID': [1, 1, 2, 3],
            'NOMBRE': ['A', 'B', 'C', 'D']
        })
        config = {'pk': 'ID', 'campos_obligatorios': []}
        profiler = DataProfiler(df, 'TEST', config)
        clean, dirty = profiler.analizar()

        assert len(clean) == 2
        assert len(dirty) >= 2

    def test_deteccion_nulos_obligatorios(self):
        """Verifica que detecta nulos en campos obligatorios"""
        df = pd.DataFrame({
            'ID': [1, 2, 3],
            'NOMBRE': ['A', None, 'C']
        })
        config = {'pk': 'ID', 'campos_obligatorios': ['NOMBRE']}
        profiler = DataProfiler(df, 'TEST', config)
        clean, dirty = profiler.analizar()

        assert len(clean) == 2
        assert len(dirty) == 1

    def test_validacion_email(self):
        """Verifica que valida formato email"""
        df = pd.DataFrame({
            'ID': [1, 2, 3],
            'CORREO': ['valido@test.com', 'invalido@', 'otro@domain.com']
        })
        config = {
            'pk': 'ID',
            'campos_obligatorios': [],
            'reglas_validacion': {
                'reglas': [{'id': 'R001', 'campo': 'CORREO'}]
            }
        }
        profiler = DataProfiler(df, 'TEST', config)
        clean, dirty = profiler.analizar()

        assert len(clean) == 2
        assert len(dirty) == 1

    def test_dataframe_vacio(self):
        """Verifica comportamiento con DataFrame vacío"""
        df = pd.DataFrame()
        config = {'pk': 'ID', 'campos_obligatorios': []}
        profiler = DataProfiler(df, 'TEST', config)
        result = profiler.analizar()

        assert result == (None, None)


class TestCsvWriter:
    """Tests para el CsvWriter"""

    def test_crear_csv_clean_y_dirty(self):
        """Verifica que se crean dos archivos CSV (CLEAN y DIRTY)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CsvWriter('TEST', tmpdir)

            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['A', 'B']})
            df_dirty = pd.DataFrame({'ID': [3], 'NOMBRE': ['C'], 'REJECTION_REASON': ['ERROR']})

            resultado = writer.escribir(df_clean, df_dirty)
            assert resultado is True
            assert writer.ruta_clean.exists()
            assert writer.ruta_dirty.exists()

    def test_csv_sin_errores(self):
        """Verifica que genera CSV CLEAN cuando todo es válido"""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CsvWriter('TEST', tmpdir)

            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['A', 'B']})
            df_dirty = pd.DataFrame()

            resultado = writer.escribir(df_clean, df_dirty)
            assert resultado is True
            assert writer.ruta_clean.exists()

    def test_seleccionar_columnas_clean(self):
        """Verifica que se pueden seleccionar columnas específicas para CLEAN"""
        class CustomCsvWriter(CsvWriter):
            def _seleccionar_columnas_clean(self, df):
                return df[['ID']]

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CustomCsvWriter('TEST', tmpdir)
            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['A', 'B']})
            df_dirty = pd.DataFrame()

            writer.escribir(df_clean, df_dirty)

            df_read = pd.read_csv(writer.ruta_clean)
            assert list(df_read.columns) == ['ID']

    def test_preprocesar_csv_clean(self):
        """Verifica que se pueden transformar datos antes de escribir CSV"""
        class CustomCsvWriter(CsvWriter):
            def _preprocesar_clean(self, df):
                df['NOMBRE'] = df['NOMBRE'].str.upper()
                return df

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CustomCsvWriter('TEST', tmpdir)
            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['alice', 'bob']})
            df_dirty = pd.DataFrame()

            writer.escribir(df_clean, df_dirty)

            df_read = pd.read_csv(writer.ruta_clean)
            assert df_read['NOMBRE'].iloc[0] == 'ALICE'
            assert df_read['NOMBRE'].iloc[1] == 'BOB'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
