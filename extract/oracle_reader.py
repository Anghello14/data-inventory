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

    def obtener_columnas_not_null(self, esquema, tabla):
        # Obtiene columnas con restricción NOT NULL directamente del diccionario de Oracle.
        query = f"""
        SELECT COLUMN_NAME
        FROM ALL_TAB_COLUMNS
        WHERE OWNER = '{esquema}'
          AND TABLE_NAME = '{tabla}'
          AND NULLABLE = 'N'
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(query)
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            logging.warning(f"No se pudieron obtener columnas NOT NULL de {esquema}.{tabla}: {e}")
            return []

    def obtener_estadisticas_vacios(self, esquema, tabla):
        # Detecta columnas completamente vacías y calcula porcentaje de vacío por columna.
        # En columnas de texto, "vacía" incluye NULL y también espacios en blanco.
        tabla_full = f"{esquema}.{tabla}"
        _BINARY_TYPES = (
            oracledb.DB_TYPE_BLOB,
            oracledb.DB_TYPE_RAW,
            oracledb.DB_TYPE_LONG_RAW,
        )
        _TEXT_TYPES = (
            oracledb.DB_TYPE_CHAR,
            oracledb.DB_TYPE_NCHAR,
            oracledb.DB_TYPE_VARCHAR,
            oracledb.DB_TYPE_NVARCHAR,
            oracledb.DB_TYPE_LONG,
        )

        try:
            with self.conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {tabla_full} WHERE 1=0")
                col_meta = [(desc[0], desc[1]) for desc in cur.description]

            columnas_analizables = [
                (name, col_type) for name, col_type in col_meta if col_type not in _BINARY_TYPES
            ]
            if not columnas_analizables:
                return [], {}

            exprs = []
            for col, col_type in columnas_analizables:
                if col_type in _TEXT_TYPES:
                    exprs.append(
                        f'SUM(CASE WHEN NULLIF(TRIM("{col}"), \'\') IS NULL THEN 1 ELSE 0 END) AS "{col}"'
                    )
                else:
                    exprs.append(
                        f'SUM(CASE WHEN "{col}" IS NULL THEN 1 ELSE 0 END) AS "{col}"'
                    )

            query = f"SELECT COUNT(*) AS TOTAL_FILAS, {', '.join(exprs)} FROM {tabla_full}"

            with self.conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()

            if not row:
                return [], {}

            total_filas = int(row[0] or 0)
            vacios_por_columna = row[1:]

            columnas_muertas = [
                col for (col, _), valor in zip(columnas_analizables, vacios_por_columna)
                if total_filas > 0 and int(valor or 0) == total_filas
            ]

            porcentaje_vacio_por_columna = {}
            for (col, _), vacios_col in zip(columnas_analizables, vacios_por_columna):
                vacios_col = int(vacios_col or 0)
                porcentaje = 0.0 if total_filas == 0 else (vacios_col / total_filas) * 100
                porcentaje_vacio_por_columna[col] = round(porcentaje, 2)

            return columnas_muertas, porcentaje_vacio_por_columna
        except Exception as e:
            logging.warning(f"No se pudieron detectar columnas muertas en {tabla_full}: {e}")
            return [], {}

    def extract_table_paginated(self, esquema, tabla, chunk_size=50000, start_chunk=0, excluded_columns=None):
        # Extrae registros de la tabla en chunks para evitar sobrecarga de memoria.
        # Antes de transferir datos, inspecciona los tipos de columna para excluir
        # BLOBs/RAW del SELECT y evitar bloqueos de red por datos binarios pesados.
        tabla_full = f"{esquema}.{tabla}"
        excluded_columns = set(excluded_columns or [])
        logging.info(
            f"Iniciando extraccion protegida de {tabla_full} en chunks de {chunk_size} "
            f"(reanudar desde chunk {start_chunk + 1})..."
        )

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

            # 2. Construir SELECT sustituyendo columnas binarias por NULL y
            # excluyendo columnas muertas detectadas a nivel tabla.
            select_parts = []
            cols = []
            for name, col_type in col_meta:
                if name in excluded_columns:
                    continue
                if col_type in _BINARY_TYPES:
                    select_parts.append(f'NULL AS "{name}"')
                else:
                    select_parts.append(f'"{name}"')
                cols.append(name)

            if not cols:
                logging.warning(f"[{tabla}] No hay columnas para extraer tras exclusiones. Se omite tabla.")
                return

            binary_cols = [name for name, t in col_meta if t in _BINARY_TYPES]
            if binary_cols:
                logging.info(f"[{tabla}] Columnas BLOB/RAW omitidas (sin transferencia): {binary_cols}")
            if excluded_columns:
                logging.info(f"[{tabla}] Columnas excluidas por muertas: {sorted(excluded_columns)}")

            offset_rows = max(int(start_chunk), 0) * int(chunk_size)
            columnas_select = ', '.join(select_parts)
            query = (
                "SELECT * FROM ("
                f"SELECT {columnas_select}, ROW_NUMBER() OVER (ORDER BY ROWID) AS RN "
                f"FROM {tabla_full}"
                ") "
                "WHERE RN > :offset_rows "
                "ORDER BY RN"
            )

            # 3. Extraccion real sin datos binarios por lotes
            with self.conn.cursor() as cur:
                cur.arraysize = 25000
                cur.execute(query, offset_rows=offset_rows)

                _ILLEGAL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffd]')
                total_cargado = offset_rows
                chunk_actual = int(start_chunk)

                while True:
                    rows = cur.fetchmany(chunk_size)
                    if not rows:
                        break

                    chunk_actual += 1

                    rows = [
                        tuple(
                            None if isinstance(v, bytes)
                            else (_ILLEGAL.sub('', v) if isinstance(v, str) else v)
                            for v in row
                        )
                        for row in rows
                    ]

                    total_cargado += len(rows)
                    logging.info(
                        f"Progreso [{tabla}]: {total_cargado} registros cargados "
                        f"(chunk {chunk_actual})."
                    )
                    df_chunk = pd.DataFrame(rows, columns=cols + ['RN'])
                    yield df_chunk.drop(columns=['RN'])
        except Exception as e:
            logging.error(f"Error en extraccion de {tabla_full}: {e}")
            raise

    def close(self):
        # Libera el recurso de conexión al finalizar el pipeline
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
            logging.info("Conexion con Oracle cerrada.")