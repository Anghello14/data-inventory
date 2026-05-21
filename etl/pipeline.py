import logging
import time
from extract.oracle_reader import OracleReader
from transform.profiler import DataProfiler
from load.excel_csv import ExcelWriter, CsvWriter, DualWriter


class ETLPipeline:
    """
    Orquestador genérico del ETL: Extract → Transform → Load

    Uso básico:
        pipeline = ETLPipeline(nombre_tabla="MI_TABLA", config_tabla={...})
        df_clean, df_dirty = pipeline.ejecutar()

    Soporta múltiples formatos: excel, csv, dual (ambos)
    """

    def __init__(self, nombre_tabla, config_tabla, esquema="SPE", reader=None, writer_class=None):
        self.nombre_tabla = nombre_tabla
        self.config_tabla = config_tabla
        self.esquema = esquema
        self.reader = reader or OracleReader()
        self.df_raw = None
        self.df_clean = None
        self.df_dirty = None
        self.df_summary = None
        self.df_nulls = None

        # Elegir writer según config o parámetro
        self.writer_class = writer_class or self._obtener_writer_class()

    def _obtener_writer_class(self):
        """Selecciona el writer según la configuración"""
        salida_config = self.config_tabla.get('salida', {})
        formato = salida_config.get('formato', 'excel').lower()

        if formato == 'csv':
            return CsvWriter
        elif formato == 'dual' or formato == 'ambos':
            return DualWriter
        else:  # default a excel
            return ExcelWriter

    def ejecutar(self):
        """
        Ejecuta el pipeline completo: extract → transform → load
        Retorna: (df_clean, df_dirty)
        """
        inicio = time.time()

        try:
            # 1. EXTRACT
            logging.info(f"[{self.nombre_tabla}] === EXTRACT ===")
            self.df_raw = self._extract()
            if self.df_raw is None or self.df_raw.empty:
                logging.warning(f"[{self.nombre_tabla}] Extracción vacía. Abortando.")
                return None, None

            # 2. TRANSFORM
            logging.info(f"[{self.nombre_tabla}] === TRANSFORM ===")
            self._transform()

            # 3. LOAD
            logging.info(f"[{self.nombre_tabla}] === LOAD ===")
            self._load()

            duracion = round((time.time() - inicio) / 60, 2)
            logging.info(f"[{self.nombre_tabla}] Pipeline completado en {duracion} min")
            return self.df_clean, self.df_dirty

        except Exception as e:
            logging.error(f"[{self.nombre_tabla}] ERROR en pipeline: {str(e)}")
            return None, None

    def _extract(self):
        """Extrae datos de Oracle"""
        try:
            limite = self.config_tabla.get('extraccion', {}).get('limite')
            df = self.reader.extract_tabla(self.nombre_tabla, self.esquema, limite)

            if df is not None and not df.empty:
                logging.info(f"[{self.nombre_tabla}] Extracción OK: {len(df)} registros")

            return df

        except Exception as e:
            logging.error(f"[{self.nombre_tabla}] Error en extract: {str(e)}")
            return None

    def _transform(self):
        """Transforma y perfila los datos"""
        try:
            # Excluir columnas pesadas si están especificadas
            df_input = self.df_raw.copy()
            exclude_cols = self.config_tabla.get('exclude_from_profiling', [])
            if exclude_cols:
                cols_a_excluir = [c for c in exclude_cols if c in df_input.columns]
                if cols_a_excluir:
                    logging.info(f"Excluyendo {len(cols_a_excluir)} columnas del perfilado: {cols_a_excluir}")
                    df_input = df_input.drop(columns=cols_a_excluir)

            # Profiler
            profiler = DataProfiler(df_input, self.nombre_tabla, self.config_tabla)
            self.df_clean, self.df_dirty, self.df_summary, self.df_nulls = profiler.analizar()

            logging.info(f"[{self.nombre_tabla}] Transform OK: {len(self.df_clean) if self.df_clean is not None else 0} limpios")

        except Exception as e:
            logging.error(f"[{self.nombre_tabla}] Error en transform: {str(e)}")

    def _load(self):
        """Escribe los datos según el formato especificado"""
        try:
            writer = self.writer_class(self.nombre_tabla)

            # Obtener configuración de salida
            salida_config = self.config_tabla.get('salida', {})
            incluir_clean = salida_config.get('incluir_clean', True)
            incluir_dirty = salida_config.get('incluir_dirty', True)

            writer.escribir(
                self.df_clean,
                self.df_dirty,
                self.df_summary,
                self.df_nulls,
                incluir_clean=incluir_clean,
                incluir_dirty=incluir_dirty
            )
            logging.info(f"[{self.nombre_tabla}] Load OK")

        except Exception as e:
            logging.error(f"[{self.nombre_tabla}] Error en load: {str(e)}")

    def get_estadisticas(self):
        """Retorna estadísticas del pipeline"""
        if self.df_summary is None:
            return {}
        return self.df_summary.to_dict(orient='records')[0] if not self.df_summary.empty else {}
