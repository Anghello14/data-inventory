import pandas as pd
import logging
from pathlib import Path
from config.settings import DATA_OUTPUT_DIR

class ExcelWriter:
    """
    Writer flexible para Excel que permite transformar datos antes de escribir.
    Los desarrolladores pueden subclasear y override `_preprocesar_clean` y `_preprocesar_dirty`
    """

    def __init__(self, nombre_tabla, directorio_salida=None):
        self.nombre_tabla = nombre_tabla
        self.directorio = Path(directorio_salida) if directorio_salida else DATA_OUTPUT_DIR
        self.ruta_archivo = self.directorio / f"INVENTARIO_{nombre_tabla}.xlsx"

    def _preprocesar_clean(self, df):
        # Hook para que cada dev customize los datos limpios antes de escribir
        # Ej: convertir fechas, renombrar columnas, formatear valores
        return df

    def _preprocesar_dirty(self, df):
        # Hook para que cada dev customize los datos dirty antes de escribir
        return df

    def escribir(self, df_clean, df_dirty, df_summary, df_nulls, incluir_clean=True, incluir_dirty=True):
        """
        Escribe los DataFrames a Excel con pestañas configurables.

        Args:
            df_clean: DataFrame con registros válidos
            df_dirty: DataFrame con registros rechazados
            df_summary: Resumen ejecutivo
            df_nulls: Detalle de columnas
            incluir_clean: si False, no escribe pestaña CLEAN
            incluir_dirty: si False, no escribe pestaña DIRTY
        """
        try:
            # Preprocesar
            if df_clean is not None and not df_clean.empty:
                df_clean = self._preprocesar_clean(df_clean)

            if df_dirty is not None and not df_dirty.empty:
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


def generar_excel_inventario(nombre_tabla, df_clean, df_dirty, df_summary, df_nulls):
    # Función legacy para compatibilidad
    writer = ExcelWriter(nombre_tabla)
    return writer.escribir(df_clean, df_dirty, df_summary, df_nulls)