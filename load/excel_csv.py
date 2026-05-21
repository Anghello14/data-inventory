import pandas as pd
import logging
from pathlib import Path
from config.settings import DATA_OUTPUT_DIR


class BaseWriter:
    """
    Clase base para todos los writers. Define la interfaz común y hooks de personalización.
    Cada dev puede subclasear y override _preprocesar_clean y _preprocesar_dirty.
    """

    def __init__(self, nombre_tabla, directorio_salida=None):
        self.nombre_tabla = nombre_tabla
        self.directorio = Path(directorio_salida) if directorio_salida else DATA_OUTPUT_DIR
        self.directorio.mkdir(exist_ok=True)

    def _seleccionar_columnas_clean(self, df):
        # Hook: cada dev puede elegir qué columnas y en qué orden escribir para CLEAN
        # Por defecto, todas las columnas en el orden que están
        return df

    def _seleccionar_columnas_dirty(self, df):
        # Hook: cada dev puede elegir qué columnas y en qué orden escribir para DIRTY
        # Por defecto, todas las columnas en el orden que están
        return df

    def _preprocesar_clean(self, df):
        # Hook: transformaciones (renombrar, convertir tipos, formatear)
        return df

    def _preprocesar_dirty(self, df):
        # Hook: transformaciones (renombrar, convertir tipos, formatear)
        return df

    def escribir(self, df_clean, df_dirty, df_summary, df_nulls, incluir_clean=True, incluir_dirty=True):
        raise NotImplementedError("Subclases deben implementar escribir()")


class ExcelWriter(BaseWriter):
    """
    Writer para Excel con 4 pestañas: ANALISIS_TECNICO, DETALLE_COLUMNAS, CLEAN, DIRTY
    """

    def __init__(self, nombre_tabla, directorio_salida=None):
        super().__init__(nombre_tabla, directorio_salida)
        self.ruta_archivo = self.directorio / f"INVENTARIO_{nombre_tabla}.xlsx"

    def escribir(self, df_clean, df_dirty, df_summary, df_nulls, incluir_clean=True, incluir_dirty=True):
        """
        Escribe los DataFrames a Excel con pestañas configurables.
        """
        try:
            # Preprocesar y seleccionar columnas
            if df_clean is not None and not df_clean.empty:
                df_clean = self._seleccionar_columnas_clean(df_clean)
                df_clean = self._preprocesar_clean(df_clean)

            if df_dirty is not None and not df_dirty.empty:
                df_dirty = self._seleccionar_columnas_dirty(df_dirty)
                df_dirty = self._preprocesar_dirty(df_dirty)

            with pd.ExcelWriter(self.ruta_archivo, engine='openpyxl') as writer:
                # Pestaña 1: Resumen Ejecutivo
                df_summary.to_excel(writer, sheet_name='ANALISIS_TECNICO', index=False)

                # Pestaña 2: Inventario de Columnas
                df_nulls.to_excel(writer, sheet_name='DETALLE_COLUMNAS', index=False)

                # Pestaña 3: Datos Limpios
                if incluir_clean:
                    if df_clean is not None and not df_clean.empty:
                        df_clean.to_excel(writer, sheet_name='CLEAN', index=False)
                    else:
                        pd.DataFrame({"INFO": ["Sin registros que cumplan las reglas de integridad"]}).to_excel(writer, sheet_name='CLEAN', index=False)

                # Pestaña 4: Datos con Error
                if incluir_dirty:
                    if df_dirty is not None and not df_dirty.empty:
                        df_dirty.to_excel(writer, sheet_name='DIRTY', index=False)
                    else:
                        pd.DataFrame({"INFO": ["No se detectaron errores"]}).to_excel(writer, sheet_name='DIRTY', index=False)

            logging.info(f"[{self.nombre_tabla}] Excel generado: {self.ruta_archivo}")
            return True

        except Exception as e:
            logging.error(f"[{self.nombre_tabla}] Error al escribir Excel: {str(e)}")
            return False


class CsvWriter(BaseWriter):
    """
    Writer para CSV: genera dos archivos (CLEAN.csv y DIRTY.csv) con datos separados.
    Cada dev puede customizar el orden de columnas y transformaciones.
    """

    def __init__(self, nombre_tabla, directorio_salida=None):
        super().__init__(nombre_tabla, directorio_salida)
        self.ruta_clean = self.directorio / f"{nombre_tabla}_CLEAN.csv"
        self.ruta_dirty = self.directorio / f"{nombre_tabla}_DIRTY.csv"

    def escribir(self, df_clean, df_dirty, df_summary=None, df_nulls=None, incluir_clean=True, incluir_dirty=True):
        """
        Escribe datos CLEAN y DIRTY a dos archivos CSV separados.

        Args:
            df_clean: DataFrame con registros válidos
            df_dirty: DataFrame con registros rechazados
            df_summary: Resumen ejecutivo (opcional para CSV)
            df_nulls: Detalle de columnas (opcional para CSV)
            incluir_clean: si True, escribe CLEAN.csv
            incluir_dirty: si True, escribe DIRTY.csv
        """
        try:
            # Preprocesar y seleccionar columnas
            if df_clean is not None and not df_clean.empty:
                df_clean = self._seleccionar_columnas_clean(df_clean)
                df_clean = self._preprocesar_clean(df_clean)

            if df_dirty is not None and not df_dirty.empty:
                df_dirty = self._seleccionar_columnas_dirty(df_dirty)
                df_dirty = self._preprocesar_dirty(df_dirty)

            # Escribir CSV CLEAN
            if incluir_clean:
                if df_clean is not None and not df_clean.empty:
                    df_clean.to_csv(self.ruta_clean, index=False, encoding='utf-8-sig')
                    logging.info(f"[{self.nombre_tabla}] CSV CLEAN generado: {self.ruta_clean}")
                else:
                    # Si no hay registros limpios, crear CSV vacío pero con header
                    pd.DataFrame(columns=df_dirty.columns if df_dirty is not None else []).to_csv(
                        self.ruta_clean, index=False, encoding='utf-8-sig'
                    )
                    logging.info(f"[{self.nombre_tabla}] CSV CLEAN vacío (sin registros válidos)")

            # Escribir CSV DIRTY
            if incluir_dirty:
                if df_dirty is not None and not df_dirty.empty:
                    df_dirty.to_csv(self.ruta_dirty, index=False, encoding='utf-8-sig')
                    logging.info(f"[{self.nombre_tabla}] CSV DIRTY generado: {self.ruta_dirty}")
                else:
                    # Si no hay registros con error, crear CSV vacío
                    pd.DataFrame(columns=df_clean.columns if df_clean is not None else []).to_csv(
                        self.ruta_dirty, index=False, encoding='utf-8-sig'
                    )
                    logging.info(f"[{self.nombre_tabla}] CSV DIRTY vacío (sin errores detectados)")

            return True

        except Exception as e:
            logging.error(f"[{self.nombre_tabla}] Error al escribir CSV: {str(e)}")
            return False


class DualWriter(BaseWriter):
    """
    Writer que genera AMBOS formatos: Excel + CSV.
    Útil cuando necesitas reportes ejecutivos (Excel) + datos para procesamiento (CSV).
    """

    def __init__(self, nombre_tabla, directorio_salida=None):
        super().__init__(nombre_tabla, directorio_salida)
        self.excel_writer = ExcelWriter(nombre_tabla, directorio_salida)
        self.csv_writer = CsvWriter(nombre_tabla, directorio_salida)

    def escribir(self, df_clean, df_dirty, df_summary, df_nulls, incluir_clean=True, incluir_dirty=True):
        """Escribe a ambos formatos"""
        excel_ok = self.excel_writer.escribir(df_clean, df_dirty, df_summary, df_nulls, incluir_clean, incluir_dirty)
        csv_ok = self.csv_writer.escribir(df_clean, df_dirty, df_summary, df_nulls, incluir_clean, incluir_dirty)
        return excel_ok and csv_ok

    def _seleccionar_columnas_clean(self, df):
        # Delegar a los writers individuales
        df = self.excel_writer._seleccionar_columnas_clean(df)
        df = self.csv_writer._seleccionar_columnas_clean(df)
        return df

    def _seleccionar_columnas_dirty(self, df):
        # Delegar a los writers individuales
        df = self.excel_writer._seleccionar_columnas_dirty(df)
        df = self.csv_writer._seleccionar_columnas_dirty(df)
        return df

    def _preprocesar_clean(self, df):
        # Delegar a los writers individuales
        df = self.excel_writer._preprocesar_clean(df)
        df = self.csv_writer._preprocesar_clean(df)
        return df

    def _preprocesar_dirty(self, df):
        # Delegar a los writers individuales
        df = self.excel_writer._preprocesar_dirty(df)
        df = self.csv_writer._preprocesar_dirty(df)
        return df


def generar_excel_inventario(nombre_tabla, df_clean, df_dirty, df_summary, df_nulls):
    # Función legacy para compatibilidad
    writer = ExcelWriter(nombre_tabla)
    return writer.escribir(df_clean, df_dirty, df_summary, df_nulls)