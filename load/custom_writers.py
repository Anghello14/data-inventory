"""
Ejemplos de CsvWriter personalizado para que cada dev adapte a su tabla.
Copia estos ejemplos y customiza según tus necesidades.
"""

import pandas as pd
import logging
from load.excel_csv import CsvWriter, ExcelWriter


class MiCsvWriterPersonalizado(CsvWriter):
    """
    Ejemplo 1: Ordenar columnas específicamente en el CSV CLEAN
    Útil cuando necesitas cierto orden de campos para downstream processing
    """

    def _seleccionar_columnas_clean(self, df):
        # Elegir columnas y orden específico
        columnas_deseadas = ['ID', 'NOMBRE', 'CORREO', 'TELEFONO']
        # Solo incluir columnas que existan en el DataFrame
        columnas_existentes = [c for c in columnas_deseadas if c in df.columns]
        return df[columnas_existentes]

    def _seleccionar_columnas_dirty(self, df):
        # Para DIRTY, incluir REJECTION_REASON al final para saber por qué se rechazó
        cols = [c for c in df.columns if c != 'REJECTION_REASON']
        if 'REJECTION_REASON' in df.columns:
            return df[cols + ['REJECTION_REASON']]
        return df[cols]


class MiCsvWriterConTransformacion(CsvWriter):
    """
    Ejemplo 2: Transformar datos antes de escribir
    Convertir tipos, renombrar columnas, etc.
    """

    def _preprocesar_clean(self, df):
        # Renombrar columnas para compatibilidad con downstream
        df = df.rename(columns={
            'CORREO': 'EMAIL',
            'TELEFONO': 'PHONE',
            'FECHA_CREACION': 'CREATED_AT'
        })

        # Convertir tipos si es necesario
        if 'ID' in df.columns:
            df['ID'] = df['ID'].astype(str)

        # Agregar columnas de timestamp
        df['EXPORTED_AT'] = pd.Timestamp.now()

        return df

    def _preprocesar_dirty(self, df):
        # Para registros sucios, también renombrar columns
        df = df.rename(columns={
            'CORREO': 'EMAIL',
            'TELEFONO': 'PHONE'
        })
        return df


class MiExcelWriterPersonalizado(ExcelWriter):
    """
    Ejemplo 3: Personalizar Excel (ordenar columnas, transformaciones)
    """

    def _seleccionar_columnas_clean(self, df):
        # Ordenar columnas en el Excel: ID primero, luego las demás
        columnas_ordenadas = ['ID']
        columnas_ordenadas.extend([c for c in df.columns if c != 'ID'])
        return df[columnas_ordenadas]

    def _preprocesar_clean(self, df):
        # Formatear valores (ej: mayúsculas en NOMBRE)
        if 'NOMBRE' in df.columns:
            df['NOMBRE'] = df['NOMBRE'].str.upper()
        return df


class DualWriterConLogicaCompleja(CsvWriter):
    """
    Ejemplo 4: CSV con lógica de filtrado adicional
    Útil cuando quieres excluir ciertos registros o columnas del CSV
    """

    def _seleccionar_columnas_clean(self, df):
        # Excluir columnas que comienzan con "TEMP_" o "_INTERNAL"
        columnas_finales = [c for c in df.columns
                          if not c.startswith('TEMP_') and not c.startswith('_')]
        return df[columnas_finales]

    def _preprocesar_clean(self, df):
        # Filtrar filas según cierto criterio
        # Ej: excluir registros con STATUS="INACTIVO"
        if 'STATUS' in df.columns:
            df = df[df['STATUS'] != 'INACTIVO']
            logging.info(f"Se filtraron registros INACTIVOS. Total final: {len(df)}")

        # Formatear valores
        for col in df.select_dtypes(include=['object']).columns:
            if col != 'CORREO':  # No formatear emails
                df[col] = df[col].str.strip()  # Remover espacios

        return df


class MiCsvWriterFormatoEspecial(CsvWriter):
    """
    Ejemplo 5: CSV con separador y encoding personalizados
    Útil para sistemas legacy que requieren ciertos formatos
    """

    def __init__(self, nombre_tabla, directorio_salida=None):
        super().__init__(nombre_tabla, directorio_salida)
        self.separador = ';'  # En lugar de coma
        self.encoding = 'latin-1'  # En lugar de utf-8

    def escribir(self, df_clean, df_dirty, df_summary=None, df_nulls=None, incluir_clean=True, incluir_dirty=True):
        """Override escribir para usar separador personalizado"""
        try:
            if df_clean is not None and not df_clean.empty:
                df_clean = self._seleccionar_columnas_clean(df_clean)
                df_clean = self._preprocesar_clean(df_clean)

            if df_dirty is not None and not df_dirty.empty:
                df_dirty = self._seleccionar_columnas_dirty(df_dirty)
                df_dirty = self._preprocesar_dirty(df_dirty)

            # Escribir con separador personalizado
            if incluir_clean:
                if df_clean is not None and not df_clean.empty:
                    df_clean.to_csv(self.ruta_clean, index=False,
                                  encoding=self.encoding, sep=self.separador)
                    logging.info(f"CSV CLEAN generado (sep='{self.separador}'): {self.ruta_clean}")

            if incluir_dirty:
                if df_dirty is not None and not df_dirty.empty:
                    df_dirty.to_csv(self.ruta_dirty, index=False,
                                  encoding=self.encoding, sep=self.separador)
                    logging.info(f"CSV DIRTY generado (sep='{self.separador}'): {self.ruta_dirty}")

            return True
        except Exception as e:
            logging.error(f"Error al escribir CSV: {str(e)}")
            return False


# ============================================================================
# CÓMO USAR ESTOS EJEMPLOS
# ============================================================================
# 1. En etl/pipeline.py, imports necesarios:
#    from load.custom_writers import MiCsvWriterPersonalizado
#
# 2. Crear pipeline con writer personalizado:
#    pipeline = ETLPipeline(
#        nombre_tabla="MI_TABLA",
#        config_tabla=config,
#        writer_class=MiCsvWriterPersonalizado
#    )
#
# 3. O, para usar desde main.py, crear una función helper:
#    def obtener_writer_para_tabla(nombre_tabla):
#        if nombre_tabla == "CLIENTES":
#            return MiCsvWriterPersonalizado
#        elif nombre_tabla == "PEDIDOS":
#            return MiCsvWriterConTransformacion
#        return CsvWriter  # default
