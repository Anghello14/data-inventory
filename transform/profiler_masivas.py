import pandas as pd
import logging

# Mapeo de tipos Oracle a sugerencias de destino
_ORACLE_TO_PG = {
    'NUMBER': 'NUMERIC', 'INTEGER': 'BIGINT', 'FLOAT': 'NUMERIC',
    'BINARY_FLOAT': 'NUMERIC', 'BINARY_DOUBLE': 'NUMERIC',
    'VARCHAR2': 'VARCHAR', 'NVARCHAR2': 'VARCHAR', 'CHAR': 'CHAR',
    'NCHAR': 'CHAR', 'CLOB': 'TEXT', 'NCLOB': 'TEXT',
    'DATE': 'TIMESTAMP', 'TIMESTAMP': 'TIMESTAMP',
    'BLOB': 'BYTEA', 'RAW': 'BYTEA', 'LONG': 'TEXT',
}
_ORACLE_TO_MONGO = {
    'NUMBER': 'NumberLong / Decimal128', 'INTEGER': 'NumberLong',
    'FLOAT': 'Decimal128', 'BINARY_FLOAT': 'Decimal128', 'BINARY_DOUBLE': 'Decimal128',
    'VARCHAR2': 'String', 'NVARCHAR2': 'String', 'CHAR': 'String',
    'NCHAR': 'String', 'CLOB': 'String', 'NCLOB': 'String',
    'DATE': 'ISODate', 'TIMESTAMP': 'ISODate',
    'BLOB': 'BinData', 'RAW': 'BinData', 'LONG': 'String',
}

def _mapear_tipo(oracle_type):
    base = oracle_type.split('(')[0].upper()
    pg   = _ORACLE_TO_PG.get(base, 'VARCHAR')
    mongo = _ORACLE_TO_MONGO.get(base, 'String')
    return oracle_type, pg, mongo


class DataProfiler:
    def __init__(self, metadata, nombre_tabla, config_tabla):
        """
        metadata: dict devuelto por OracleReader.get_metadata_completo()
          - cols_info: list of (COLUMN_NAME, DATA_TYPE, NULLABLE)
          - null_counts: dict {col_name: int}
          - tamano_mb: float
        """
        self.metadata = metadata
        self.nombre_tabla = nombre_tabla
        self.config = config_tabla

    def analizar(self):
        if not self.metadata:
            logging.warning(f"[{self.nombre_tabla}] Sin metadatos. Saltando perfilado.")
            return None, None

        logging.info(f"[{self.nombre_tabla}] Iniciando auditoria tecnica...")

        cols_info   = self.metadata['cols_info']       # (name, type, nullable)
        null_counts = self.metadata['null_counts']
        tamano_mb   = self.metadata['tamano_mb']
        total_filas = self.config.get('total_filas', 0)

        # --- DETALLE DE COLUMNAS ---
        reporte_columnas = []
        columnas_muertas = 0

        for col_name, col_type, nullable in cols_info:
            tipo_oracle, pg_type, mongo_type = _mapear_tipo(col_type)
            nulos = null_counts.get(col_name, 0)
            es_muerta = (total_filas > 0) and (nulos == total_filas)
            if es_muerta:
                columnas_muertas += 1
            pct = f"{(nulos / total_filas * 100):.2f}%" if total_filas > 0 else "N/A"
            reporte_columnas.append({
                'COLUMNA':            col_name,
                'TIPO_ORACLE':        tipo_oracle,
                'SUGERENCIA_POSTGRES': pg_type,
                'SUGERENCIA_MONGODB': mongo_type,
                'NULLABLE_ORACLE':    nullable,
                'CANTIDAD_NULOS':     nulos,
                'PORCENTAJE_NULOS':   pct,
                'ESTADO_COLUMNA':     "MUERTA (BORRAR)" if es_muerta else "ACTIVA"
            })
        df_nulls = pd.DataFrame(reporte_columnas)

        # --- RESUMEN EJECUTIVO ---
        total_cols = len(cols_info)
        cols_activas = total_cols - columnas_muertas
        indice_num = (cols_activas / total_cols * 100) if total_cols else 0

        df_summary = pd.DataFrame([{
            'TABLA':             self.nombre_tabla,
            'TOTAL_FILAS_ORACLE': total_filas,
            'PESO_ESTIMADO_MB':  tamano_mb,
            'COLUMNAS_TOTALES':  total_cols,
            'COLUMNAS_MUERTAS':  columnas_muertas,
            'SENSIBLE':          "SI" if self.config.get('sensible') else "NO",
            'INDICE_CALIDAD':    f"{indice_num:.2f}%"
        }])

        logging.info(
            f"[{self.nombre_tabla}] Perfilado finalizado. "
            f"Peso: {tamano_mb} MB. Calidad: {indice_num:.2f}%"
        )
        return df_summary, df_nulls
