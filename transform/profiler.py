"""
Módulo de perfilado y segregación de datos.

Responsabilidad principal:
  Clasificar registros crudos de Oracle en dos grupos:
    - CLEAN  → registros que superan todos los criterios de calidad.
    - DIRTY  → registros que fallan al menos un criterio, con motivo detallado.

IMPORTANTE: Ningún dato es modificado. Solo se clasifica.
"""
import pandas as pd
import logging
from datetime import datetime


def _col(df, name):
    """
    Parámetros:
      df   -- DataFrame de pandas con los datos extraídos.
      name -- Nombre de la columna a buscar (cualquier capitalización).

    Retorna:
      El nombre real de la columna tal como aparece en df.columns, o None.
    """
    name_lower = name.lower()
    for c in df.columns:
        if c.lower() == name_lower:
            return c
    return None


def segregate_data(df, table, pk=None, col_fecha=None, period_type=None):
    """
    Parámetros:
      df          -- DataFrame con los datos crudos extraídos de Oracle.
      table       -- Nombre de la tabla (usado en logs y en el archivo de salida).
      pk          -- Nombre de la columna clave primaria (para detectar duplicados).
      col_fecha   -- Nombre de la columna de fecha principal (para validar rango temporal).
      period_type -- Tipo de período esperado: 'mensual', 'anual' o 'completa'.

    Retorna:
      df_clean    -- DataFrame con registros válidos (sin columnas 100% nulas).
      df_dirty    -- DataFrame con registros rechazados + columna REJECTION_REASON.
      df_summary  -- DataFrame con resumen estadístico de calidad (1 fila).
      df_null_cols-- DataFrame con conteo de nulos por columna.
    """
    # Copia defensiva — nunca se modifica el DataFrame original
    df_raw = df.copy()

    # Log de diagnóstico: muestra qué columnas recibió este DataFrame
    logging.info(f"[{table}] Columnas recibidas: {list(df_raw.columns)}")

    fully_null_cols = df_raw.columns[df_raw.isnull().all()].tolist()
    if fully_null_cols:
        logging.warning(
            f"[{table}] Columnas 100% nulas (excluidas de CLEAN y de validaciones): "
            f"{fully_null_cols}"
        )

    def active_col(name):
        """
        Igual que _col() pero devuelve None si la columna es 100% nula.
        Impide que las reglas de rechazo penalicen columnas vacías.
        """
        real = _col(df_raw, name)
        if real and real in fully_null_cols:
            return None  # Columna existente pero vacía - ignorar en validaciones
        return real

    # Máscara booleana acumulativa — True = registro sucio
    is_dirty = pd.Series(False, index=df_raw.index)
    # Serie de texto acumulativa — almacena los motivos de rechazo por fila
    reasons = pd.Series([""] * len(df_raw), index=df_raw.index, dtype=str)

    def flag(mask, reason):
        """
        Marca registros como sucios y acumula el motivo de rechazo.

        Parámetros:
          mask   -- Serie booleana con True en los registros a rechazar.
          reason -- Código de motivo de rechazo (ej. 'NULL_IN_EMAIL').
        """
        nonlocal is_dirty
        # Reindexar para garantizar alineación correcta de índices
        mask = mask.reindex(df_raw.index, fill_value=False)
        is_dirty = is_dirty | mask
        # Concatenar motivo al existente si el registro ya tenía otros rechazos
        reasons[mask] = reasons[mask].apply(
            lambda x: f"{x} | {reason}" if x else reason
        )
        if mask.any():
            logging.info(
                f"[{table}] Regla '{reason}': "
                f"{int(mask.sum())} registro(s) marcados como DIRTY."
            )

    # Cualquier registro con un campo clave vacío es inválido.
    # Las columnas 100% nulas se omiten
    required_fields = [
        'apellido', 'paciente_id', 'medico_id', 'nombre',
        'municipio_id', 'email', 'fecha_cita', 'cita_id',
        'especialidad_id', 'internacion_id', 'examen_id',
        'resultado_id', 'receta_id', 'factura_id',
    ]
    for field_name in required_fields:
        # active_col devuelve None si la columna es 100% nula - se salta
        real = active_col(field_name)
        if real:
            mask_null = df_raw[real].isnull()  # True donde el valor es NULL
            flag(mask_null, f"NULL_IN_{real.upper()}")

    # Se usa df.duplicated() con keep=False para marcar TODOS los duplicados
    pk_col = active_col(pk) if pk else None
    if pk_col:
        # keep=False - marca tanto el primero como el segundo duplicado
        mask_duplicates = df_raw.duplicated(subset=[pk_col], keep=False)
        flag(mask_duplicates, f"PK_DUPLICADA_{pk_col.upper()}")


    # Sexo: únicamente M / F / X son valores válidos
    gender_col = active_col('sexo')
    if gender_col:
        flag(~df_raw[gender_col].isin(['M', 'F', 'X']), "GENERO INVALIDO")

    # Email: debe contener @ y cumplir el formato básico de correo
    email_col = active_col('email')
    if email_col:
        # Expresión regular para validar formato de email
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        flag(
            ~df_raw[email_col].astype(str).str.match(email_regex, na=False),
            "EMAIL INVALIDO"
        )

    # Hora de cita: formato obligatorio HH:MM (ej. 08:30, 14:00)
    time_col = active_col('hora_cita')
    if time_col:
        flag(
            # Regex: exactamente 2 dígitos, dos puntos, 2 dígitos
            ~df_raw[time_col].astype(str).str.match(r'^\d{2}:\d{2}$', na=False),
            "HORA INVALIDA"
        )

    # Montos negativos — ningún monto financiero puede ser negativo
    for amount_field in ['total_factura', 'monto', 'valor', 'monto_total']:
        amount_col = active_col(amount_field)
        if amount_col:
            flag(
                # Convertir a numérico primero; errores de parsing → NaN (no se marcan aquí)
                pd.to_numeric(df_raw[amount_col], errors='coerce') < 0,
                "MONTO NEGATIVO"
            )

    # Detecta columnas que debería tener un tipo numérico o de fecha pero llegaron como texto plano (dtype=object) desde Oracle.

    # Columnas de fecha con texto no convertible a datetime
    for c in df_raw.columns:
        if 'fecha' in c.lower() and c not in fully_null_cols and df_raw[c].dtype == object:
            # Intentar conversión; los que fallen quedan como NaT
            parsed_date = pd.to_datetime(df_raw[c], errors='coerce')
            # Marcar solo los que tenían valor pero no se pudieron convertir
            mask_bad_type = df_raw[c].notna() & parsed_date.isna()
            flag(mask_bad_type, f"TIPO ERRONEO{c.upper()}")

    # Columnas numéricas que llegaron como texto (dtype=object)
    numeric_fields = [
        'total_factura', 'monto', 'valor', 'monto_total',
        'dosis', 'cantidad', 'dias_internacion'
    ]
    for num_field in numeric_fields:
        num_col = active_col(num_field)
        if num_col and df_raw[num_col].dtype == object:
            parsed_num = pd.to_numeric(df_raw[num_col], errors='coerce')
            # Registro con valor pero que no se pudo convertir a número
            mask_bad_num = df_raw[num_col].notna() & parsed_num.isna()
            flag(mask_bad_num, f"TIPO ERRONEO{num_col.upper()}")

    # Valida que las fechas estén dentro de la ventana esperada según el tipo de período configurado en el YAML.
    # Valor por defecto si la tabla no tiene columna de fecha configurada
    date_range_info = {"FECHA_MIN": "N/A", "FECHA_MAX": "N/A", "FUERA_RANGO": 0}
    date_col = active_col(col_fecha) if col_fecha else None
    if date_col:
        # Parsear fechas; las que no se puedan convertir quedan como NaT
        parsed_dates = pd.to_datetime(df_raw[date_col], errors='coerce')
        current_year = datetime.now().year

        # Definir ventana de fechas permitida según tipo de período del YAML
        if period_type == "mensual":
            # Solo se acepta el año en curso
            min_date = pd.Timestamp(f"{current_year}-01-01")
            max_date = pd.Timestamp(f"{current_year}-12-31")
        elif period_type == "anual":
            # Se aceptan los últimos 5 años
            min_date = pd.Timestamp(f"{current_year - 5}-01-01")
            max_date = pd.Timestamp(f"{current_year}-12-31")
        else:
            # Tablas 'completa': solo rechazar fechas históricamente imposibles
            min_date = pd.Timestamp("1900-01-01")
            max_date = pd.Timestamp(f"{current_year + 1}-12-31")

        # Marcar fechas fuera de la ventana permitida
        mask_out_of_range = parsed_dates.notna() & (
            (parsed_dates < min_date) | (parsed_dates > max_date)
        )
        flag(mask_out_of_range, f"FUERA DE RANGO{date_col.upper()}")

        # Registrar estadísticas del rango temporal real de los datos
        if parsed_dates.notna().any():
            date_range_info = {
                "FECHA_MIN": str(parsed_dates.min().date()),
                "FECHA_MAX": str(parsed_dates.max().date()),
                "FUERA_RANGO": int(mask_out_of_range.sum()),
            }
            logging.info(
                f"[{table}] Rango temporal '{date_col}': "
                f"{date_range_info['FECHA_MIN']} → {date_range_info['FECHA_MAX']} "
                f"| Fuera de rango: {date_range_info['FUERA_RANGO']}"
            )

    # DIRTY: todos los registros que fallaron al menos un criterio
    df_dirty = df_raw[is_dirty].copy()
    # Insertar columna de motivo al inicio para facilitar la revisión
    df_dirty.insert(0, "MOTIVO RECHAZO", reasons[is_dirty].values)

    # CLEAN: registros que pasaron todos los criterios
    df_clean = df_raw[~is_dirty].copy()
    # Eliminar del CLEAN las columnas que estuvieron 100% vacías
    if fully_null_cols:
        df_clean = df_clean.drop(columns=fully_null_cols, errors='ignore')

    logging.info(
        f"[{table}] Resultado → CLEAN: {len(df_clean)} | "
        f"DIRTY: {len(df_dirty)} | TOTAL: {len(df_raw)}"
    )

    # RESUMEN — métricas consolidadas de calidad por tabla
    total = len(df_raw)
    df_summary = pd.DataFrame([{
        "TABLA":                table,
        "TOTAL_FILAS":        total,
        "REGISTROS_LIMPIOS":        len(df_clean),
        "REGISTROS_RECHAZADOS":        len(df_dirty),
        "TOTAL_NULLS":          int(df_raw.isnull().sum().sum()),   # Suma de nulos en toda la tabla
        "PK_DUPLICADA":         int(df_raw.duplicated(subset=[pk_col], keep=False).sum()) if pk_col else 0,
        "COLUMNAS_VACIAS":   ", ".join(fully_null_cols) if fully_null_cols else "NONE",
        "FECHA_MIN":             date_range_info["FECHA_MIN"],
        "FECHA_MAX":             date_range_info["FECHA_MAX"],
        "FUERA_RANGO": date_range_info["FUERA_RANGO"],
        "PORCENTAJE_CALIDAD":          f"{(len(df_clean) / total * 100) if total > 0 else 0:.2f}%",
    }])

    # NULOS POR COLUMNA — detalle de nulos para cada campo
    null_rows = []
    for col in df_raw.columns:
        null_count = int(df_raw[col].isnull().sum())  # Conteo de nulos en esta columna
        null_rows.append({
            "TABLA":        table,
            "COLUMNA":       col,
            "TIPO_ORIGINAL":  str(df_raw[col].dtype),           # Tipo de dato original de Oracle
            "NULOS":        null_count,
            "NO_NULOS":    total - null_count,
            "PORCENTAJE_NULOS":     f"{(null_count / total * 100) if total > 0 else 0:.2f}%",
            "COLUMNAS_NULAS":   "YES" if null_count == total else "NO",  # Columna completamente vacía
        })
    df_null_cols = pd.DataFrame(null_rows)

    # Retornar los cuatro DataFrames resultantes del proceso
    return df_clean, df_dirty, df_summary, df_null_cols