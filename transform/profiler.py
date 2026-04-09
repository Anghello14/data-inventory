"""
Modulo de perfilado y segregacion de datos (Versión Profesional).
Responsabilidad: Auditoria tecnica, calculo de peso en disco, 
deteccion de nulos/duplicados e inferencia de tipos para destino.
"""
import pandas as pd
import numpy as np
import logging

class DataProfiler:
    def __init__(self, df, nombre_tabla, config_tabla):
        """
        Inicializa el profiler con los datos crudos y la configuracion del YAML.
        """
        self.df = df
        self.nombre_tabla = nombre_tabla
        self.config = config_tabla
        self.total_registros = len(df)
        
    def _inferir_tipos_destino(self, serie):
        """
        Analiza el tipo de dato de Pandas y sugiere el equivalente en motores destino.
        """
        dtype = str(serie.dtype).lower()
        
        if "int" in dtype:
            return "INT8 / NumberLong", "BIGINT"
        elif "float" in dtype:
            return "DOUBLE / Decimal128", "NUMERIC"
        elif "datetime" in dtype or "timestamp" in dtype:
            return "DATE / ISODate", "TIMESTAMP"
        elif "object" in dtype:
            # Si es string, podria ser un JSON o un texto largo
            return "STRING / Object", "TEXT / VARCHAR"
        else:
            return "MIXED / String", "VARCHAR"

    def analizar(self):
        """
        Ejecuta el perfilado completo: Segregacion, Calidad y Dimensionamiento.
        """
        if self.df.empty:
            logging.warning(f"[{self.nombre_tabla}] DataFrame vacio. Saltando perfilado.")
            return None, None, None, None

        logging.info(f"[{self.nombre_tabla}] Iniciando auditoria tecnica...")

        # 1. CALCULO DE PESO EN DISCO (MEMORIA REAL)
        # Usamos deep=True para incluir el peso real de las cadenas de texto (VARCHARs)
        uso_memoria_bytes = self.df.memory_usage(deep=True).sum()
        tamano_mb = round(uso_memoria_bytes / (1024 * 1024), 2)

        # 2. ANALISIS DE COLUMNAS MUERTAS (100% Nulas)
        conteo_nulos = self.df.isnull().sum()
        columnas_muertas = conteo_nulos[conteo_nulos == self.total_registros].index.tolist()

        # 3. SEGREGACION PROFESIONAL (CLEAN vs DIRTY)
        # Criterio 1: Filas completamente vacias
        mask_vacia = self.df.isnull().all(axis=1)
        
        # Criterio 2: Duplicados en la primera columna (asumida como PK técnica si no hay otra)
        pk_candidata = self.df.columns[0]
        mask_duplicados = self.df.duplicated(subset=[pk_candidata], keep='first')

        # Creamos la columna de trazabilidad de errores
        self.df['REJECTION_REASON'] = ""
        self.df.loc[mask_vacia, 'REJECTION_REASON'] += "FILA_TOTALMENTE_VACIA | "
        self.df.loc[mask_duplicados, 'REJECTION_REASON'] += f"DUPLICADO_EN_PK_{pk_candidata} | "

        # Separacion de datasets
        df_dirty = self.df[self.df['REJECTION_REASON'] != ""].copy()
        df_clean = self.df[self.df['REJECTION_REASON'] == ""].copy()
        
        # En el set limpio, eliminamos la columna tecnica de error
        if not df_clean.empty:
            df_clean = df_clean.drop(columns=['REJECTION_REASON'])

        # 4. REPORTE DETALLADO DE COLUMNAS (Para el Excel de Analisis)
        reporte_columnas = []
        for col in self.df.columns:
            if col == 'REJECTION_REASON': continue
            
            nulos_col = int(conteo_nulos[col])
            mongo_type, pg_type = self._inferir_tipos_destino(self.df[col])
            
            reporte_columnas.append({
                'COLUMNA': col,
                'TIPO_ORACLE_PANDAS': str(self.df[col].dtype),
                'SUGERENCIA_POSTGRES': pg_type,
                'SUGERENCIA_MONGODB': mongo_type,
                'CANTIDAD_NULOS': nulos_col,
                'PORCENTAJE_NULOS': f"{(nulos_col / self.total_registros * 100):.2f}%",
                'ESTADO_COLUMNA': "MUERTA (BORRAR)" if col in columnas_muertas else "ACTIVA"
            })
        df_nulls = pd.DataFrame(reporte_columnas)

        # 5. RESUMEN EJECUTIVO (SUMMARY)
        resumen_data = {
            'TABLA': self.nombre_tabla,
            'TOTAL_FILAS_ORACLE': self.total_registros,
            'PESO_ESTIMADO_MB': tamano_mb,
            'FILAS_LIMPIAS': len(df_clean),
            'FILAS_CON_ERROR': len(df_dirty),
            'COLUMNAS_TOTALES': len(self.df.columns) - 1,
            'COLUMNAS_MUERTAS': len(columnas_muertas),
            'SENSIBLE': "SI" if self.config.get('sensible') else "NO",
            'DESTINO_SUGERIDO': self.config.get('destino_sugerido', 'N/A'),
            'INDICE_CALIDAD': f"{(len(df_clean) / self.total_registros * 100):.2f}%"
        }
        df_summary = pd.DataFrame([resumen_data])

        logging.info(f"[{self.nombre_tabla}] Perfilado finalizado. Peso: {tamano_mb} MB. Calidad: {resumen_data['INDICE_CALIDAD']}")

        return df_clean, df_dirty, df_summary, df_nulls