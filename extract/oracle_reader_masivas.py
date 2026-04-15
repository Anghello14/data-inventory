"""
Modulo de extraccion de datos desde Oracle Database.
Optimizado con metadatos de integridad y manejo de objetos pesados (CLOB).
"""
import oracledb
import pandas as pd
import logging
import os
from config.settings import ORACLE_USER, ORACLE_PASS, DSN, ORACLE_CLIENT_PATH

class OracleReader:
    def __init__(self):
        # MANEJADOR UNIVERSAL: Convierte CLOB, NCLOB, BLOB y XMLType a tipos nativos de Python
        def output_type_handler(cursor, name, default_type, size, precision, scale):
            # Para textos gigantes (CLOB, NCLOB y XML)
            if default_type in (oracledb.DB_TYPE_CLOB, oracledb.DB_TYPE_NCLOB, oracledb.DB_TYPE_XMLTYPE):
                return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
            # Para binarios (BLOB)
            if default_type == oracledb.DB_TYPE_BLOB:
                return cursor.var(oracledb.DB_TYPE_LONG_RAW, arraysize=cursor.arraysize)

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
        """Obtiene el total de registros para decidir la estrategia de carga."""
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
        """Consulta las tablas de sistema para identificar PK, FK, UNIQUE y CHECK."""
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
                for rtype, rcol in rows:
                    if rtype == 'P': res['PK'] = rcol
                    elif rtype == 'R': res['FK'] = rcol
                    elif rtype == 'U': res['UNIQUE'] = rcol
                    elif rtype == 'C': res['CHECK'] = rcol
            return res
        except Exception as e:
            logging.warning(f"No se pudieron obtener restricciones de {tabla}: {e}")
            return res

    def extract_table_paginated(self, esquema, tabla):
        """Extrae datos de forma lineal, protegida contra tipos pesados."""
        tabla_full = f"{esquema}.{tabla}"
        logging.info(f"Iniciando extraccion protegida de {tabla_full}...")
        
        try:
            with self.conn.cursor() as cur:
                # Buffer optimizado para no saturar la red con datos pesados
                cur.arraysize = 5000 
                cur.execute(f"SELECT * FROM {tabla_full}")
                
                cols = [desc[0] for desc in cur.description]
                rows = cur.fetchall() 
                
                df = pd.DataFrame(rows, columns=cols)
                logging.info(f"Progreso [{tabla}]: {len(df)} registros cargados.")
                return df
        except Exception as e:
            logging.error(f"Error en extraccion de {tabla_full}: {e}")
            return pd.DataFrame()

    def get_metadata_completo(self, esquema, tabla, total_filas):
        """
        Obtiene todo lo necesario para ANALISIS_TECNICO y DETALLE_COLUMNAS
        directamente del diccionario de Oracle y una sola consulta de conteos.
        No transfiere ninguna fila de datos.
        """
        # 1. Nombres y tipos de columnas desde el diccionario
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT COLUMN_NAME, DATA_TYPE, NULLABLE
                    FROM ALL_TAB_COLUMNS
                    WHERE OWNER = :1 AND TABLE_NAME = :2
                    ORDER BY COLUMN_ID
                """, [esquema, tabla])
                cols_info = cur.fetchall()
        except Exception as e:
            logging.error(f"Error obteniendo columnas de {tabla}: {e}")
            return None

        if not cols_info:
            return None

        # 2. Estimación de peso desde estadísticas de Oracle
        tamano_mb = 0.0
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT NVL(AVG_ROW_LEN, 0) * :1 / 1024 / 1024
                    FROM ALL_TABLES
                    WHERE OWNER = :2 AND TABLE_NAME = :3
                """, [total_filas, esquema, tabla])
                row = cur.fetchone()
                if row and row[0]:
                    tamano_mb = round(float(row[0]), 2)
        except Exception:
            pass

        # 3. Conteo de nulos en una sola pasada por la tabla (por lotes de 50 columnas)
        col_names = [r[0] for r in cols_info]
        null_counts = {c: 0 for c in col_names}
        tabla_full = f'"{esquema}"."{tabla}"'
        batch_size = 50

        for i in range(0, len(col_names), batch_size):
            batch = col_names[i:i + batch_size]
            # Alias posicional para evitar conflictos con nombres especiales
            selects = ", ".join(
                f'COUNT(*)-COUNT("{c}") AS C{i + j}' for j, c in enumerate(batch)
            )
            try:
                with self.conn.cursor() as cur:
                    cur.execute(f"SELECT {selects} FROM {tabla_full}")
                    row = cur.fetchone()
                    if row:
                        for j, c in enumerate(batch):
                            null_counts[c] = int(row[j]) if row[j] is not None else 0
            except Exception as e:
                logging.warning(f"[{tabla}] No se pudieron obtener nulos en batch {i}: {e}")

        return {
            'cols_info': cols_info,   # list of (COLUMN_NAME, DATA_TYPE, NULLABLE)
            'null_counts': null_counts,
            'tamano_mb': tamano_mb,
        }

    def close(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
            logging.info("Conexion con Oracle cerrada.")
