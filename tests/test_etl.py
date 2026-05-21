import pytest
import pandas as pd
from transform.profiler import DataProfiler
from load.excel_csv import ExcelWriter, CsvWriter, DualWriter
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
        config = {'pk': 'ID', 'not_null': [], 'sensible': False}
        profiler = DataProfiler(df, 'TEST', config)
        clean, dirty, summary, nulls = profiler.analizar()

        assert len(clean) == 2  # Solo dos registros únicos sin duplicados
        assert len(dirty) >= 2  # Dos registros con duplicados
        assert 'DUPLICADO_EN_PK_ID' in dirty['REJECTION_REASON'].values[0]

    def test_deteccion_nulos_obligatorios(self):
        """Verifica que detecta nulos en campos NOT NULL"""
        df = pd.DataFrame({
            'ID': [1, 2, 3],
            'NOMBRE': ['A', None, 'C']
        })
        config = {'pk': 'ID', 'not_null': ['NOMBRE'], 'sensible': False}
        profiler = DataProfiler(df, 'TEST', config)
        clean, dirty, summary, nulls = profiler.analizar()

        assert len(clean) == 2
        assert len(dirty) == 1
        assert 'NULO_EN_CAMPO_OBLIGATORIO_NOMBRE' in dirty['REJECTION_REASON'].values[0]

    def test_validacion_email(self):
        """Verifica que valida formato email"""
        df = pd.DataFrame({
            'ID': [1, 2, 3],
            'CORREO': ['valido@test.com', 'invalido@', 'otro@domain.com']
        })
        config = {
            'pk': 'ID',
            'not_null': [],
            'sensible': False,
            'validaciones_campos': {'CORREO': 'email'}
        }
        profiler = DataProfiler(df, 'TEST', config)
        clean, dirty, summary, nulls = profiler.analizar()

        assert len(clean) == 2
        assert len(dirty) == 1
        assert 'FORMATO_EMAIL_INVALIDO_EN_CORREO' in dirty['REJECTION_REASON'].values[0]

    def test_dataframe_vacio(self):
        """Verifica comportamiento con DataFrame vacío"""
        df = pd.DataFrame()
        config = {'pk': 'ID', 'not_null': [], 'sensible': False}
        profiler = DataProfiler(df, 'TEST', config)
        result = profiler.analizar()

        assert result == (None, None, None, None)

    def test_resumen_ejecutivo(self):
        """Verifica que el resumen contiene las métricas correctas"""
        df = pd.DataFrame({
            'ID': [1, 2, 3],
            'NOMBRE': ['A', 'B', 'C']
        })
        config = {'pk': 'ID', 'not_null': ['NOMBRE'], 'sensible': False}
        profiler = DataProfiler(df, 'TEST', config)
        clean, dirty, summary, nulls = profiler.analizar()

        assert summary is not None
        assert summary['TABLA'].values[0] == 'TEST'
        assert summary['TOTAL_FILAS_ORACLE'].values[0] == 3
        assert summary['FILAS_LIMPIAS'].values[0] == 3
        assert '100.00' in summary['INDICE_CALIDAD'].values[0]


class TestExcelWriter:
    """Tests para el ExcelWriter"""

    def test_crear_excel_basico(self):
        """Verifica que se crea un archivo Excel válido"""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ExcelWriter('TEST', tmpdir)

            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['A', 'B']})
            df_dirty = pd.DataFrame({'ID': [3], 'NOMBRE': ['C'], 'REJECTION_REASON': ['ERROR']})
            df_summary = pd.DataFrame({
                'TABLA': ['TEST'],
                'TOTAL_FILAS_ORACLE': [3],
                'FILAS_LIMPIAS': [2],
                'INDICE_CALIDAD': ['66.67%']
            })
            df_nulls = pd.DataFrame({'COLUMNA': ['ID', 'NOMBRE'], 'TIPO_ORACLE_PANDAS': ['int64', 'object']})

            resultado = writer.escribir(df_clean, df_dirty, df_summary, df_nulls)
            assert resultado is True
            assert writer.ruta_archivo.exists()

    def test_preprocesamiento_personalizado(self):
        """Verifica que se pueden customizar los datos antes de escribir"""
        class CustomWriter(ExcelWriter):
            def _preprocesar_clean(self, df):
                df['PROCESADO'] = True
                return df

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CustomWriter('TEST', tmpdir)

            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['A', 'B']})
            df_dirty = pd.DataFrame()
            df_summary = pd.DataFrame({'TABLA': ['TEST'], 'TOTAL_FILAS_ORACLE': [2]})
            df_nulls = pd.DataFrame({'COLUMNA': ['ID']})

            resultado = writer.escribir(df_clean, df_dirty, df_summary, df_nulls)
            assert resultado is True

    def test_excel_sin_errores(self):
        """Verifica que genera Excel cuando todo es limpio"""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = ExcelWriter('TEST', tmpdir)

            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['A', 'B']})
            df_dirty = None
            df_summary = pd.DataFrame({'TABLA': ['TEST'], 'TOTAL_FILAS_ORACLE': [2]})
            df_nulls = pd.DataFrame({'COLUMNA': ['ID']})

            resultado = writer.escribir(df_clean, df_dirty, df_summary, df_nulls)
            assert resultado is True


class TestCsvWriter:
    """Tests para el CsvWriter"""

    def test_crear_csv_clean_y_dirty(self):
        """Verifica que se crean dos archivos CSV (CLEAN y DIRTY)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CsvWriter('TEST', tmpdir)

            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['A', 'B']})
            df_dirty = pd.DataFrame({'ID': [3], 'NOMBRE': ['C'], 'REJECTION_REASON': ['ERROR']})
            df_summary = None
            df_nulls = None

            resultado = writer.escribir(df_clean, df_dirty, df_summary, df_nulls)
            assert resultado is True
            assert writer.ruta_clean.exists()
            assert writer.ruta_dirty.exists()

    def test_csv_sin_errores(self):
        """Verifica que genera CSV CLEAN vacío cuando todo es válido"""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CsvWriter('TEST', tmpdir)

            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['A', 'B']})
            df_dirty = None

            resultado = writer.escribir(df_clean, df_dirty, None, None)
            assert resultado is True
            assert writer.ruta_clean.exists()
            assert writer.ruta_dirty.exists()

    def test_seleccionar_columnas_clean(self):
        """Verifica que se pueden seleccionar columnas específicas para CLEAN"""
        class CustomCsvWriter(CsvWriter):
            def _seleccionar_columnas_clean(self, df):
                return df[['ID']]  # Solo la columna ID

        with tempfile.TemporaryDirectory() as tmpdir:
            writer = CustomCsvWriter('TEST', tmpdir)
            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['A', 'B']})
            df_dirty = pd.DataFrame()

            writer.escribir(df_clean, df_dirty, None, None)

            # Verificar que el CSV CLEAN solo tiene columna ID
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

            writer.escribir(df_clean, df_dirty, None, None)

            # Verificar que los nombres están en mayúsculas
            df_read = pd.read_csv(writer.ruta_clean)
            assert df_read['NOMBRE'].iloc[0] == 'ALICE'
            assert df_read['NOMBRE'].iloc[1] == 'BOB'


class TestDualWriter:
    """Tests para el DualWriter (Excel + CSV)"""

    def test_crear_ambos_formatos(self):
        """Verifica que DualWriter crea ambos formatos"""
        with tempfile.TemporaryDirectory() as tmpdir:
            writer = DualWriter('TEST', tmpdir)

            df_clean = pd.DataFrame({'ID': [1, 2], 'NOMBRE': ['A', 'B']})
            df_dirty = pd.DataFrame({'ID': [3], 'NOMBRE': ['C'], 'REJECTION_REASON': ['ERROR']})
            df_summary = pd.DataFrame({'TABLA': ['TEST']})
            df_nulls = pd.DataFrame({'COLUMNA': ['ID']})

            resultado = writer.escribir(df_clean, df_dirty, df_summary, df_nulls)
            assert resultado is True

            # Verificar que existen ambos formatos
            assert (tmpdir / 'INVENTARIO_TEST.xlsx') in Path(tmpdir).glob('*.xlsx')
            assert (tmpdir / 'TEST_CLEAN.csv') in Path(tmpdir).glob('*.csv')
            assert (tmpdir / 'TEST_DIRTY.csv') in Path(tmpdir).glob('*.csv')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
