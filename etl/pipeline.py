import logging
import time
from extract.oracle_reader import OracleReader
from transform.profiler import DataProfiler
from load.write_csv import CsvWriter


class ETLPipeline:
    """
    Orquestador genérico del ETL: Extract → Transform → Load

    Genera dos CSVs por tabla:
    - TABLA_CLEAN.csv: registros válidos
    - TABLA_DIRTY.csv: registros rechazados

    Uso:
        pipeline = ETLPipeline(nombre_tabla="MI_TABLA", config_tabla={...})
        df_clean, df_dirty = pipeline.ejecutar()

    Personalización:
        class MiPipeline(ETLPipeline):
            def _cargar_writer(self):
                return MiCsvWriter(self.nombre_tabla)
    """

    def __init__(self, nombre_tabla, config_tabla, esquema="SPE", reader=None):
        self.nombre_tabla = nombre_tabla
        self.config_tabla = config_tabla
        self.esquema = esquema
        self.reader = reader or OracleReader()
        self.df_raw = None
        self.df_clean = None
        self.df_dirty = None

    def _cargar_writer(self):
        """Carga el writer (CsvWriter por defecto). Override para usar custom writer."""
        return CsvWriter(self.nombre_tabla)

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
                logging.info(f"[{self.nombre_tabla}] {len(df)} registros extraídos")

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
                    logging.info(f"Excluyendo {len(cols_a_excluir)} columnas: {cols_a_excluir}")
                    df_input = df_input.drop(columns=cols_a_excluir)

            # Profiler
            profiler = DataProfiler(df_input, self.nombre_tabla, self.config_tabla)
            self.df_clean, self.df_dirty = profiler.analizar()

            clean_count = len(self.df_clean) if self.df_clean is not None else 0
            dirty_count = len(self.df_dirty) if self.df_dirty is not None else 0
            logging.info(f"[{self.nombre_tabla}] {clean_count} limpios, {dirty_count} dirty")

        except Exception as e:
            logging.error(f"[{self.nombre_tabla}] Error en transform: {str(e)}")

    def _load(self):
        """Escribe los CSVs (CLEAN y DIRTY)"""
        try:
            writer = self._cargar_writer()

            # Obtener configuración de salida
            salida_config = self.config_tabla.get('salida', {})
            incluir_clean = salida_config.get('incluir_clean', True)
            incluir_dirty = salida_config.get('incluir_dirty', True)

            writer.escribir(
                self.df_clean,
                self.df_dirty,
                incluir_clean=incluir_clean,
                incluir_dirty=incluir_dirty
            )
            logging.info(f"[{self.nombre_tabla}] CSVs generados")

        except Exception as e:
            logging.error(f"[{self.nombre_tabla}] Error en load: {str(e)}")

    def get_estadisticas(self):
        """Retorna estadísticas básicas del pipeline"""
        return {
            'tabla': self.nombre_tabla,
            'registros_clean': len(self.df_clean) if self.df_clean is not None else 0,
            'registros_dirty': len(self.df_dirty) if self.df_dirty is not None else 0
        }
