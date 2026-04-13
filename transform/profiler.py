import pandas as pd
import logging
import re

class DataProfiler:
    def __init__(self, df, nombre_tabla, config_tabla):
        self.df = df
        self.nombre_tabla = nombre_tabla
        self.config = config_tabla
        self.total_registros = len(df)
        
    def _inferir_tipos_destino(self, serie):
        dtype = str(serie.dtype).lower()
        if "int" in dtype: return "INT8 / NumberLong", "BIGINT"
        elif "float" in dtype: return "DOUBLE / Decimal128", "NUMERIC"
        elif "datetime" in dtype or "timestamp" in dtype: return "DATE / ISODate", "TIMESTAMP"
        elif "object" in dtype: return "STRING / Object", "TEXT / VARCHAR"
        else: return "MIXED / String", "VARCHAR"

    def analizar(self):
        if self.df.empty:
            logging.warning(f"[{self.nombre_tabla}] DataFrame vacio. Saltando perfilado.")
            return None, None, None, None

        logging.info(f"[{self.nombre_tabla}] Iniciando auditoria tecnica...")

        # 1. DIMENSIONAMIENTO
        uso_memoria_bytes = self.df.memory_usage(deep=True).sum()
        tamano_mb = round(uso_memoria_bytes / (1024 * 1024), 2)

        # 2. SEGREGACIÓN DE DATOS (CLEAN / DIRTY)
        self.df['REJECTION_REASON'] = ""
        
        # A. Validación de PK (Solo si existe)
        pk_col = self.config.get('pk')
        if pk_col and pk_col in self.df.columns:
            mask_dups = self.df.duplicated(subset=[pk_col], keep=False)
            self.df.loc[mask_dups, 'REJECTION_REASON'] += f"DUPLICADO_EN_PK_{pk_col} | "

        # B. Validación de Campos Obligatorios (NOT NULL)
        not_null_cols = self.config.get('not_null', [])
        for col in not_null_cols:
            if col in self.df.columns:
                mask_nulos = self.df[col].isnull()
                self.df.loc[mask_nulos, 'REJECTION_REASON'] += f"NULO_EN_CAMPO_OBLIGATORIO_{col} | "

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

        # 3. DETALLE DE COLUMNAS (Mapeo de tipos Oracle)
        conteo_nulos = self.df.isnull().sum()
        reporte_columnas = []
        columnas_muertas = [col for col in self.df.columns if (nulos_col := conteo_nulos[col]) == self.total_registros]

        for col in self.df.columns:
            if col == 'REJECTION_REASON': continue
            mongo_type, pg_type = self._inferir_tipos_destino(self.df[col])
            nulos_col = int(conteo_nulos[col])
            
            reporte_columnas.append({
                'COLUMNA': col,
                'TIPO_ORACLE_PANDAS': str(self.df[col].dtype),
                'SUGERENCIA_POSTGRES': pg_type,
                'SUGERENCIA_MONGODB': mongo_type,
                'CANTIDAD_NULOS': nulos_col,
                'PORCENTAJE_NULOS': f"{(nulos_col / self.total_registros * 100):.2f}%",
                'ESTADO_COLUMNA': "MUERTA (BORRAR)" if nulos_col == self.total_registros else "ACTIVA"
            })
        df_nulls = pd.DataFrame(reporte_columnas)

        # 4. RESUMEN EJECUTIVO (Cálculo de calidad real)
        indice_num = (len(df_clean) / self.total_registros) * 100
        df_summary = pd.DataFrame([{
            'TABLA': self.nombre_tabla,
            'TOTAL_FILAS_ORACLE': self.total_registros,
            'PESO_ESTIMADO_MB': tamano_mb,
            'FILAS_LIMPIAS': len(df_clean),
            'FILAS_CON_ERROR': len(df_dirty),
            'COLUMNAS_TOTALES': len(self.df.columns) - 1,
            'COLUMNAS_MUERTAS': len(columnas_muertas),
            'SENSIBLE': "SI" if self.config.get('sensible') else "NO",
            'INDICE_CALIDAD': f"{indice_num:.2f}%"
        }])

        logging.info(f"[{self.nombre_tabla}] Perfilado finalizado. Peso: {tamano_mb} MB. Calidad: {indice_num:.2f}%")
        
        return df_clean, df_dirty, df_summary, df_nulls