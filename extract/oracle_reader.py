"""
Modulo de extraccion de datos desde Oracle Database.
Optimizado con Batch Dinamico y Arraysize de alto rendimiento.
"""
import oracledb
import pandas as pd
import logging
import os
from config.settings import ORACLE_USER, ORACLE_PASS, DSN, ORACLE_CLIENT_PATH

class OracleReader:
    def __init__(self):
        try:
            if ORACLE_CLIENT_PATH and os.path.exists(ORACLE_CLIENT_PATH):
                try:
                    oracledb.init_oracle_client(lib_dir=ORACLE_CLIENT_PATH)
                    logging.info("Modo Thick inicializado correctamente.")
                except oracledb.ProgrammingError:
                    pass
            else:
                logging.error(f"Ruta de Oracle Client no configurada: {ORACLE_CLIENT_PATH}")
                raise FileNotFoundError("Oracle Client Path invalido.")

            self.conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASS, dsn=DSN)
            self.tablas_vacias = [] 
            logging.info("Conexion establecida exitosamente con Oracle.")
        except Exception as e:
            logging.error(f"Fallo critico al conectar con Oracle: {str(e)}")
            raise

    def get_count(self, esquema, tabla):
        tabla_full = f"{esquema}.{tabla}"
        query = f"SELECT COUNT(*) FROM {tabla_full}"
        try:
            with self.conn.cursor() as cur:
                cur.execute(query)
                count = cur.fetchone()[0]
                if count == 0:
                    self.tablas_vacias.append(tabla_full)
                    logging.info(f"Registro: La tabla {tabla_full} esta vacia.")
                return count
        except Exception as e:
            logging.error(f"Error al obtener conteo de {tabla_full}: {str(e)}")
            return None

    def determinar_batch_size(self, total_rows):
        if total_rows <= 100000:
            return total_rows 
        elif total_rows <= 1000000:
            return 250000      
        else:
            return 500000      

    def extract_table_paginated(self, esquema, tabla):
        tabla_full = f"{esquema}.{tabla}"
        total_rows = self.get_count(esquema, tabla)

        if total_rows is None or total_rows == 0:
            return pd.DataFrame()

        batch_size = self.determinar_batch_size(total_rows)
        logging.info(f"[{tabla_full}] Registros: {total_rows}. Estrategia: Batch de {batch_size}")

        offset = 0
        chunks = []
        
        while offset < total_rows:
            limite_superior = offset + batch_size
            query = f"""
                SELECT * FROM (
                    SELECT a.*, ROWNUM rnum FROM (
                        SELECT * FROM {tabla_full}
                    ) a WHERE ROWNUM <= {limite_superior}
                ) WHERE rnum > {offset}
            """
            
            try:
                with self.conn.cursor() as cur:
                    cur.arraysize = 25000 # OPTIMIZACION DE RED
                    cur.execute(query)
                    cols = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                    
                    chunk = pd.DataFrame(rows, columns=cols)
                    if 'RNUM' in chunk.columns:
                        chunk = chunk.drop(columns=['RNUM'])
                    chunks.append(chunk)
                
                offset += batch_size
                logging.info(f"Progreso [{tabla_full}]: Extraidos {min(offset, total_rows)} de {total_rows}.")
            except Exception as e:
                logging.error(f"Error en extraccion paginada de {tabla_full}: {str(e)}")
                break

        return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()

    def get_reporte_vacias(self):
        return self.tablas_vacias

    def close(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()
            logging.info("Conexion con Oracle cerrada.")