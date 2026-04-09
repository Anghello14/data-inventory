"""
Módulo de extracción de datos desde Oracle Database.

Utiliza la librería oracledb en modo Thin (sin instalación de Oracle Client).
Implementa extracción paginada para manejar tablas de gran volumen sin saturar RAM.
"""
import oracledb
import pandas as pd
import logging
# Credenciales y DSN de conexión definidos en config/settings.py
from config.settings import ORACLE_USER, ORACLE_PASS, DSN


class OracleReader:
    """
    Clase responsable de la conexión y extracción de datos desde Oracle.

    Establece una conexión persistente en modo Thin al instanciarse.
    Debe cerrarse explícitamente con el método close() al finalizar.
    """

    def __init__(self):
        """
        Inicializa la conexión a Oracle en modo Thin.
        Modo Thin: no requiere Oracle Instant Client instalado en el sistema.
        """
        self.conn = oracledb.connect(user=ORACLE_USER, password=ORACLE_PASS, dsn=DSN)

    def get_count(self, table):
        """
        Obtiene el conteo exacto de filas en Oracle para reconciliación.

        Se usa antes de la extracción para verificar que se descargaron
        exactamente las mismas filas que existen en la base de datos.

        Parámetros:
          table -- Nombre de la tabla a contar.

        Retorna:
          Entero con el número total de filas en Oracle.
        """
        query = f"SELECT COUNT(*) FROM {table}"
        with self.conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchone()[0]  # Retorna el primer (y único) valor de la fila

    def extract_table_paginated(self, table, batch_size=50000):
        """
        Extrae todos los datos de una tabla usando paginación OFFSET/FETCH.

        La paginación evita cargar millones de filas en memoria de una sola vez.
        El ORDER BY es obligatorio en Oracle para que OFFSET/FETCH funcione
        de forma determinista.

        Parámetros:
          table      -- Nombre de la tabla a extraer.
          batch_size -- Número de filas por página (por defecto 50.000).

        Retorna:
          DataFrame de pandas con la extracción completa concatenada.
        """
        # Obtener total de filas para saber cuántas páginas iterar
        total_rows = self.get_count(table)
        offset = 0       # Posición inicial de la ventana de paginación
        chunks = []      # Lista para acumular cada bloque extraído

        while offset < total_rows:
            # ORDER BY 1 es obligatorio en Oracle para usar OFFSET/FETCH
            query = f"""
                SELECT * FROM {table}
                ORDER BY 1
                OFFSET {offset} ROWS FETCH NEXT {batch_size} ROWS ONLY
            """
            # Usar cursor directamente para evitar el UserWarning de pd.read_sql
            # con conexiones que no son SQLAlchemy
            with self.conn.cursor() as cur:
                cur.execute(query)
                cols = [desc[0] for desc in cur.description]  # Nombres de columnas del resultado
                rows = cur.fetchall()
            chunk = pd.DataFrame(rows, columns=cols)
            chunks.append(chunk)
            offset += batch_size  # Avanzar la ventana al siguiente bloque
            logging.info(
                f"[{table}] Extraidos {min(offset, total_rows)} "
                f"de {total_rows} registros..."
            )

        # Si la tabla está vacía, retornar DataFrame vacío
        if not chunks:
            return pd.DataFrame()

        # Concatenar todos los bloques en un único DataFrame final
        return pd.concat(chunks, ignore_index=True)

    def close(self):
        """
        Cierra la conexión a Oracle de forma segura.
        Debe llamarse siempre al finalizar, incluso si hubo errores.
        """
        if self.conn:
            self.conn.close()