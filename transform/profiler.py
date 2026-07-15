import pandas as pd
import logging

class DataProfiler:
    def __init__(self, df, nombre_tabla, config_tabla):
        # df           : DataFrame con los datos extraídos de Oracle (ya saneados)
        # nombre_tabla : nombre lógico usado en logs y en el archivo Excel de salida
        # config_tabla : dict del YAML con pk, not_null, sensible, etc.
        self.df = df
        self.nombre_tabla = nombre_tabla
        self.config = config_tabla
        self.total_registros = len(df)
        
    def _inferir_tipos_destino(self, serie):
        # Mapea el dtype de pandas al equivalente en MongoDB y PostgreSQL
        # para que el inventario incluya sugerencias de migración de tipos
        dtype = str(serie.dtype).lower()
        if "int" in dtype: return "INT8 / NumberLong", "BIGINT"
        elif "float" in dtype: return "DOUBLE / Decimal128", "NUMERIC"
        elif "datetime" in dtype or "timestamp" in dtype: return "DATE / ISODate", "TIMESTAMP"
        elif "object" in dtype: return "STRING / Object", "TEXT / VARCHAR"
        else: return "MIXED / String", "VARCHAR"

    def analizar(self):
        # Punto central del módulo: ejecuta las 4 etapas de auditoría técnica
        # (dimensionamiento, segregación clean/dirty, detalle de columnas, resumen ejecutivo)
        # y retorna cuatro DataFrames listos para ser escritos en el Excel de inventario.
        if self.df.empty:
            logging.warning(f"[{self.nombre_tabla}] DataFrame vacio. Saltando perfilado.")
            return None, None, None, None

        logging.info(f"[{self.nombre_tabla}] Iniciando auditoria tecnica...")

        # Normaliza espacios en columnas de texto para evitar falsos positivos
        # por caracteres invisibles al inicio o al final del valor.
        cols_texto = self.df.select_dtypes(include=['object', 'string']).columns
        for col in cols_texto:
            self.df[col] = self.df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)

        # 1. DIMENSIONAMIENTO
        # Calcula el peso en memoria del DataFrame para estimar el tamaño en disco
        uso_memoria_bytes = self.df.memory_usage(deep=True).sum()
        tamano_mb = round(uso_memoria_bytes / (1024 * 1024), 2)

        # 2. SEGREGACIÓN DE DATOS (CLEAN / DIRTY)
        # Se marca cada fila con la razón de rechazo; al final se separan en dos DataFrames
        self.df['REJECTION_REASON'] = ""
        
        # A. Validación de PK (Solo si existe)
        pk_col = self.config.get('pk')
        if pk_col and pk_col in self.df.columns:
            mask_dups = self.df.duplicated(subset=[pk_col], keep=False)
            self.df.loc[mask_dups, 'REJECTION_REASON'] += f"DUPLICADO_EN_PK_{pk_col} | "

        # B. Validación de campos vacíos con nulabilidad + detección de columnas muertas.
        # Si la columna permite NULL, no se marca como DIRTY por venir vacía.
        # Aun así, registramos columnas totalmente vacías para trazabilidad técnica.
        columnas_obligatorias = {
            str(col).upper() for col in self.config.get('not_null', []) if col
        }
        if pk_col:
            columnas_obligatorias.add(str(pk_col).upper())

        columnas_muertas_chunk = []

        for col in self.df.columns:
            if col == 'REJECTION_REASON':
                continue

            mask_nulos = self.df[col].isnull()
            if pd.api.types.is_string_dtype(self.df[col]) or self.df[col].dtype == 'object':
                mask_blancos = self.df[col].notnull() & (self.df[col].astype(str).str.strip() == "")
            else:
                mask_blancos = pd.Series(False, index=self.df.index)

            mask_vacios = mask_nulos | mask_blancos

            if mask_vacios.all():
                columnas_muertas_chunk.append(col)
                continue

            if col.upper() not in columnas_obligatorias:
                continue

            self.df.loc[mask_vacios, 'REJECTION_REASON'] += f"{col} vacio | "

        if columnas_muertas_chunk:
            logging.info(
                f"[{self.nombre_tabla}] Columnas totalmente vacías en chunk: {columnas_muertas_chunk}"
            )

        # C. DETECCIÓN DE CARACTERES CORRUPTOS (Tildes mal insertadas '?')
        # Buscamos en todas las columnas de texto (object)
        cols_texto = self.df.select_dtypes(include=['object']).columns
        for col in cols_texto:
            if col == 'REJECTION_REASON': continue
            # Detecta el signo '?' que indica error de encoding en Oracle
            mask_corrupto = self.df[col].astype(str).str.contains(r'\?', na=False)
            self.df.loc[mask_corrupto, 'REJECTION_REASON'] += f"CARACTER_CORRUPTO_EN_{col} | "

        # D. VALIDACIÓN DE FORMATO EMAIL
        # Identificamos columnas que probablemente contienen correos por su nombre
        cols_email = [c for c in self.df.columns if 'EMAIL' in c.upper() or 'CORREO' in c.upper()]
        regex_email = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        for col in cols_email:
            # Solo validamos si tiene contenido para no chocar con la regla de nulos
            mask_invalid_email = (~self.df[col].astype(str).str.match(regex_email, na=True)) & (self.df[col].notnull())
            self.df.loc[mask_invalid_email, 'REJECTION_REASON'] += f"FORMATO_EMAIL_INVALIDO_EN_{col} | "

        # SEPARACIÓN FINAL
        df_dirty = self.df[self.df['REJECTION_REASON'] != ""].copy()
        df_clean = self.df[self.df['REJECTION_REASON'] == ""].copy()
        
        if not df_clean.empty:
            df_clean = df_clean.drop(columns=['REJECTION_REASON'])

        indice_num = (len(df_clean) / self.total_registros) * 100
        df_nulls = None
        df_summary = None

        logging.info(f"[{self.nombre_tabla}] Perfilado finalizado. Peso: {tamano_mb} MB. Calidad: {indice_num:.2f}%")
        
        return df_clean, df_dirty, df_summary, df_nulls