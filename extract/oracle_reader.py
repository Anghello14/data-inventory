import oracledb
import pandas as pd
import logging
import os
import re
from config.settings import ORACLE_USER, ORACLE_PASS, DSN, ORACLE_CLIENT_PATH

class OracleReader:
    def __init__(self):
        # Manejador de tipos especiales: convierte LOBs y fechas a tipos seguros
        # antes de que el driver intente materializarlos como objetos Python nativos
        def output_type_handler(cursor, name, default_type, size, precision, scale):
            # Para textos gigantes (CLOB, NCLOB y XML)
            if default_type in (oracledb.DB_TYPE_CLOB, oracledb.DB_TYPE_NCLOB, oracledb.DB_TYPE_XMLTYPE):
                return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
            # Para binarios (BLOB)
            if default_type == oracledb.DB_TYPE_BLOB:
                return cursor.var(oracledb.DB_TYPE_LONG_RAW, arraysize=cursor.arraysize)
            # Para fechas: devolver como string para evitar errores con años fuera del rango de Python
            if default_type in (oracledb.DB_TYPE_DATE, oracledb.DB_TYPE_TIMESTAMP,
                                oracledb.DB_TYPE_TIMESTAMP_TZ, oracledb.DB_TYPE_TIMESTAMP_LTZ):
                return cursor.var(oracledb.DB_TYPE_VARCHAR, size=50, arraysize=cursor.arraysize)

        try:
            if ORACLE_CLIENT_PATH and os.path.exists(ORACLE_CLIENT_PATH):
                try:
                    oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
                    logging.info("Conexion: Modo Thick inicializado.")
                except oracledb.ProgrammingError:
                    pass
            else:
                logging.error(f"Oracle Client Path invalido: {ORACLE_CLIENT_PATH}")
                raise FileNotFoundError("Oracle Client no encontrado.")

            self.conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASS, dsn=DSN)
            
            # ASIGNAR EL MANEJADOR A LA CONEXIÓN
            self.conn.outputtypehandler = output_type_handler
            
            logging.info("Conexion establecida exitosamente con Oracle (Protección LOB activa).")
        except Exception as e:
            logging.error(f"Fallo critico al conectar con Oracle: {str(e)}")
            raise

    def get_count(self, esquema, tabla):
        # Consulta rápida de conteo: determina la estrategia de carga
        # (tabla vacía / pocos registros / masiva) antes de extraer cualquier fila
        tabla_full = f"{esquema}.{tabla}"
        query = f"SELECT COUNT(*) FROM {tabla_full}"
        try:
            with self.conn.cursor() as cur:
                cur.execute(query)
                return cur.fetchone()[0]
        except Exception as e:
            logging.error(f"Error al obtener conteo de {tabla_full}: {e}")
            return 0

    def obtener_restricciones(self, esquema, tabla):
        # Consulta ALL_CONSTRAINTS y ALL_CONS_COLUMNS para catalogar PK, FK, UNIQUE y CHECK
        # Estos datos se incluyen en el Reporte Maestro y se usan para validar duplicados en la PK
        query = f"""
        SELECT 
            CONSTRAINT_TYPE, 
            COLUMN_NAME 
        FROM ALL_CONSTRAINTS cons
        JOIN ALL_CONS_COLUMNS cols ON cons.CONSTRAINT_NAME = cols.CONSTRAINT_NAME
        WHERE cons.OWNER = '{esquema}' 
          AND cons.TABLE_NAME = '{tabla}'
        """
        res = {'PK': 'N/A', 'FK': 'N/A', 'UNIQUE': 'N/A', 'CHECK': 'N/A'}
        try:
            with self.conn.cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                # Mapear cada tipo de restricción a su columna correspondiente
                for rtype, rcol in rows:
                    if rtype == 'P': res['PK'] = rcol
                    elif rtype == 'R': res['FK'] = rcol
                    elif rtype == 'U': res['UNIQUE'] = rcol
                    elif rtype == 'C': res['CHECK'] = rcol
            return res
        except Exception as e:
            logging.warning(f"No se pudieron obtener restricciones de {tabla}: {e}")
            return res

    def extract_table(self, esquema, tabla, limite=None):
        # Extrae todos los registros de la tabla en una sola pasada (carga en memoria).
        # Antes de transferir datos, inspecciona los tipos de columna para excluir
        # BLOBs/RAW del SELECT y evitar bloqueos de red por datos binarios pesados.
        tabla_full = f"{esquema}.{tabla}"
        logging.info(f"Iniciando extraccion protegida de {tabla_full}...")

        # Tipos binarios que no se deben transferir (BLOB, RAW, LONG_RAW)
        _BINARY_TYPES = (
            oracledb.DB_TYPE_BLOB,
            oracledb.DB_TYPE_RAW,
            oracledb.DB_TYPE_LONG_RAW,
        )

        try:
            # 1. Consulta de inspección: obtener metadatos de columnas sin traer datos
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {tabla_full} WHERE 1=0")
                col_meta = [(desc[0], desc[1]) for desc in cur.description]

            # 2. Construir SELECT sustituyendo columnas binarias por NULL
            select_parts = [
                f'NULL AS "{name}"' if col_type in _BINARY_TYPES else f'"{name}"'
                for name, col_type in col_meta
            ]
            cols = [name for name, _ in col_meta]
            binary_cols = [name for name, t in col_meta if t in _BINARY_TYPES]
            if binary_cols:
                logging.info(f"[{tabla}] Columnas BLOB/RAW omitidas (sin transferencia): {binary_cols}")

            query = f"SELECT {', '.join(select_parts)} FROM {tabla_full}"

            # 3. Extraccion real sin datos binarios
            with self.conn.cursor() as cur:
                cur.arraysize = 30000
                cur.execute(query)
                rows = cur.fetchall()

            # Limpiar caracteres ilegales para Excel en campos de texto
            _ILLEGAL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]')
            rows = [
                tuple(
                    None if isinstance(v, bytes)
                    else (_ILLEGAL.sub('', v) if isinstance(v, str) else v)
                    for v in row
                )
                for row in rows
            ]

            df = pd.DataFrame(rows, columns=cols)
            logging.info(f"Progreso [{tabla}]: {len(df)} registros cargados.")
            return df
        except Exception as e:
            logging.error(f"Error en extraccion de {tabla_full}: {e}")
            return pd.DataFrame()

    def extract_tabla(self, nombre_tabla, esquema="SPE", limite=None):
        # Interfaz simplificada: recibe nombre tabla y esquema (con default)
        # Útil para llamadas simples donde el esquema es siempre el mismo
        return self.extract_table(esquema, nombre_tabla, limite)

    def close(self):
        # Libera el recurso de conexión al finalizar el pipeline
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
            logging.info("Conexion con Oracle cerrada.")