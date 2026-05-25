import pandas as pd
import logging
from pathlib import Path
from config.settings import DATA_OUTPUT_DIR


class BaseWriter:
    """
    Define interfaz común y hooks de personalización.
    Los desarrolladores subclasean para personalizar columnas y transformaciones.
    """

    def __init__(self, nombre_tabla, directorio_salida=None):
        self.nombre_tabla = nombre_tabla
        self.directorio = Path(directorio_salida) if directorio_salida else DATA_OUTPUT_DIR
        self.directorio.mkdir(exist_ok=True)

    def _seleccionar_columnas_clean(self, df):
        # Hook: cada dev elige qué columnas y en qué orden para CLEAN
        # Default: todas las columnas en el orden que están
        return df

    def _seleccionar_columnas_dirty(self, df):
        # Hook: cada dev elige qué columnas y en qué orden para DIRTY
        # Default: todas las columnas en el orden que están
        return df

    def _preprocesar_clean(self, df):
        # Hook: transformaciones (renombrar, convertir tipos, formatear)
        return df

    def _preprocesar_dirty(self, df):
        # Hook: transformaciones
        return df

    def escribir(self, df_clean, df_dirty, incluir_clean=True, incluir_dirty=True):
        raise NotImplementedError("Subclases deben implementar escribir()")


class CsvWriter(BaseWriter):
    """
    Writer para CSV: genera TABLA_CLEAN.csv y TABLA_DIRTY.csv.

    Cada dev puede personalizar:
    - Qué columnas incluir en cada CSV (_seleccionar_columnas_*)
    - Transformaciones de datos (_preprocesar_*)
    - Separador y encoding
    """

    def __init__(self, nombre_tabla, directorio_salida=None):
        super().__init__(nombre_tabla, directorio_salida)
        self.ruta_clean = self.directorio / f"{nombre_tabla}_CLEAN.csv"
        self.ruta_dirty = self.directorio / f"{nombre_tabla}_DIRTY.csv"
        self.separador = ','
        self.encoding = 'utf-8-sig'

    def escribir(self, df_clean, df_dirty, incluir_clean=True, incluir_dirty=True):
        """
        Escribe datos CLEAN y DIRTY a dos archivos CSV separados.

        Args:
            df_clean: DataFrame con registros válidos
            df_dirty: DataFrame con registros rechazados
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
                    df_clean.to_csv(
                        self.ruta_clean,
                        index=False,
                        encoding=self.encoding,
                        sep=self.separador
                    )
                    logging.info(f"[{self.nombre_tabla}] CSV CLEAN: {len(df_clean)} registros → {self.ruta_clean}")
                else:
                    cols = df_dirty.columns if df_dirty is not None and not df_dirty.empty else []
                    pd.DataFrame(columns=cols).to_csv(self.ruta_clean, index=False, encoding=self.encoding, sep=self.separador)
                    logging.info(f"[{self.nombre_tabla}] CSV CLEAN vacío")

            # Escribir CSV DIRTY
            if incluir_dirty:
                if df_dirty is not None and not df_dirty.empty:
                    df_dirty.to_csv(
                        self.ruta_dirty,
                        index=False,
                        encoding=self.encoding,
                        sep=self.separador
                    )
                    logging.info(f"[{self.nombre_tabla}] CSV DIRTY: {len(df_dirty)} registros → {self.ruta_dirty}")
                else:
                    cols = df_clean.columns if df_clean is not None and not df_clean.empty else []
                    pd.DataFrame(columns=cols).to_csv(self.ruta_dirty, index=False, encoding=self.encoding, sep=self.separador)
                    logging.info(f"[{self.nombre_tabla}] CSV DIRTY vacío")

            return True

        except Exception as e:
            logging.error(f"[{self.nombre_tabla}] Error al escribir CSV: {str(e)}")
            return False


