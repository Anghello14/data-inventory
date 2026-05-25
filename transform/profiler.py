import pandas as pd
import logging
from datetime import datetime
import re

class DataProfiler:
    def __init__(self, df, nombre_tabla, config_tabla):
        # df           : DataFrame con los datos extraídos de Oracle (ya saneados)
        # nombre_tabla : nombre lógico usado en logs y en el archivo Excel de salida
        # config_tabla : dict del YAML con pk, not_null, sensible, reglas_validacion, etc.
        self.df = df
        self.nombre_tabla = nombre_tabla
        self.config = config_tabla
        self.total_registros = len(df)

        # Cargar reglas de validación desde config
        self.reglas_validacion = self.config.get('reglas_validacion', {}).get('reglas', [])
        
    def _validar_email(self, valor):
        """R001: Valida formato de correo válido"""
        if pd.isna(valor):
            return True
        regex_email = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(regex_email, str(valor)))

    def _validar_fecha_no_futura(self, valor, campo):
        """R002: Valida fecha YYYY-MM-DD y no futura"""
        if pd.isna(valor):
            return True
        try:
            fecha = pd.to_datetime(valor, format='%Y-%m-%d')
            hoy = pd.Timestamp(datetime.now().date())
            return fecha <= hoy
        except:
            return False

    def _detectar_caracteres_corruptos(self, valor, campos_sensibles=['nombre', 'apellido', 'dirección']):
        """R003: Detecta caracteres corruptos o no imprimibles (?, tildes mal codificadas, etc.)"""
        if pd.isna(valor):
            return False
        valor_str = str(valor)
        # Detecta ?, caracteres de control, encoding inválido
        if '?' in valor_str or any(ord(c) < 32 for c in valor_str if c not in '\n\r\t'):
            return True
        return False

    def _validar_documento_unico(self, df, campo_documento):
        """R004: Valida que no haya duplicados de documento en el lote"""
        if campo_documento not in df.columns:
            return pd.Series([False] * len(df), index=df.index)
        duplicados = df[campo_documento].duplicated(keep=False)
        return duplicados

    def _validar_campos_obligatorios(self, df, campos_obligatorios):
        """R005: Valida que campos obligatorios no estén nulos"""
        mask_invalido = pd.Series([False] * len(df), index=df.index)
        for campo in campos_obligatorios:
            if campo in df.columns:
                mask_invalido = mask_invalido | df[campo].isnull()
        return mask_invalido

    def _validar_telefono_digitos(self, valor):
        """R006: Valida que teléfono contenga al menos dígitos"""
        if pd.isna(valor):
            return True
        valor_limpio = re.sub(r'\D', '', str(valor))
        return len(valor_limpio) > 0

    def _registro_completo(self, fila):
        """Valida que el registro NO tenga NINGÚN campo null (completamente completo)"""
        return fila.isnull().sum() == 0

    def analizar(self):
        if self.df.empty:
            logging.warning(f"[{self.nombre_tabla}] DataFrame vacio.")
            return None, None

        logging.info(f"[{self.nombre_tabla}] Iniciando validación de datos...")
        self.df['REJECTION_REASON'] = ""

        # R004: Validación de documentos duplicados
        pk_col = self.config.get('pk')
        if pk_col and pk_col in self.df.columns:
            mask_dups = self._validar_documento_unico(self.df, pk_col)
            self.df.loc[mask_dups, 'REJECTION_REASON'] += f"R004_DOCUMENTO_DUPLICADO | "

        # R005: Validación de campos obligatorios
        campos_obligatorios = self.config.get('campos_obligatorios', [])
        if campos_obligatorios:
            mask_obligatorios = self._validar_campos_obligatorios(self.df, campos_obligatorios)
            self.df.loc[mask_obligatorios, 'REJECTION_REASON'] += "R005_CAMPOS_OBLIGATORIOS_VACIOS | "

        # R003: Detección de caracteres corruptos
        cols_texto = self.df.select_dtypes(include=['object']).columns
        for col in cols_texto:
            if col == 'REJECTION_REASON':
                continue
            mask_corrupto = self.df[col].apply(lambda x: self._detectar_caracteres_corruptos(x))
            self.df.loc[mask_corrupto, 'REJECTION_REASON'] += f"R003_CARACTERES_CORRUPTOS | "

        # R001, R002, R006: Validaciones según reglas configuradas
        for regla in self.reglas_validacion:
            id_regla = regla.get('id')
            campo = regla.get('campo')

            if campo not in self.df.columns:
                continue

            if id_regla == 'R001':
                mask_invalid = self.df[campo].apply(lambda x: not self._validar_email(x))
                self.df.loc[mask_invalid, 'REJECTION_REASON'] += "R001_FORMATO_EMAIL_INVALIDO | "

            elif id_regla == 'R002':
                mask_invalid = self.df[campo].apply(lambda x: not self._validar_fecha_no_futura(x, campo))
                self.df.loc[mask_invalid, 'REJECTION_REASON'] += "R002_FECHA_INVALIDA_O_FUTURA | "

            elif id_regla == 'R006':
                mask_invalid = self.df[campo].apply(lambda x: not self._validar_telefono_digitos(x))
                self.df.loc[mask_invalid, 'REJECTION_REASON'] += "R006_TELEFONO_INVALIDO | "

        # Validación especial: Solo CLEAN si el registro es COMPLETO (sin ningún null)
        mask_incompleto = self.df.apply(lambda fila: not self._registro_completo(fila), axis=1)
        self.df.loc[mask_incompleto, 'REJECTION_REASON'] += "REGISTRO_INCOMPLETO | "

        # Separación final
        df_dirty = self.df[self.df['REJECTION_REASON'] != ""].copy()
        df_clean = self.df[self.df['REJECTION_REASON'] == ""].copy()

        if not df_clean.empty:
            df_clean = df_clean.drop(columns=['REJECTION_REASON'])

        logging.info(f"[{self.nombre_tabla}] Validación completada. CLEAN: {len(df_clean)}, DIRTY: {len(df_dirty)}")

        return df_clean, df_dirty