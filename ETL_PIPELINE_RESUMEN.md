# Pipeline ETL: Oracle SPE → CSVs → PostgreSQL

## 1. Arquitectura General

```
┌─────────────────────────────────────────────────────────────────────┐
│                        main.py (ORQUESTADOR)                        │
│                                                                     │
│  ┌─────────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │  extract/        │    │  transform/       │    │  load/        │  │
│  │  oracle_reader   │───▶│  profiler         │───▶│  csv_writer   │  │
│  │  .py             │    │  .py              │    │  .py          │  │
│  └─────────────────┘    └──────────────────┘    └───────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  _etl_checkpoint.json (IDEMPOTENCIA / REANUDACIÓN)           │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │  CSVs CLEAN/DIRTY│
                  │  (data_output/)  │
                  └──────────────────┘
                           │
                           ▼
                  ┌──────────────────────────┐
                  │  cargar_csv_postgres.py   │
                  │  + postgres_writer.py     │
                  └──────────────────────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │    PostgreSQL     │
                  │  (catalogs_db)    │
                  └──────────────────┘
```

El pipeline se divide en 3 etapas ejecutadas por `main.py`, más una carga opcional a PostgreSQL:

| Etapa | Módulo | Responsabilidad |
|-------|--------|-----------------|
| **Extract** | `extract/oracle_reader.py` | Conexión Oracle, detección de columnas muertas, extracción paginada por chunks |
| **Transform** | `transform/profiler.py` | Validación de calidad: PK duplicadas, nulos, caracteres corruptos, emails inválidos. Separa CLEAN / DIRTY |
| **Load (CSV)** | `load/csv_writer.py` | Acumulación incremental a CSVs planos con trazabilidad |
| **Load (Postgres)** | `cargar_csv_postgres.py` + `load/postgres_writer.py` | Inserción masiva desde CSV a PostgreSQL con validación de esquema y dry-run |

---

## 2. Extracción — `extract/oracle_reader.py`

### 2.1. Conexión con protección de tipos (LOBs, fechas)

```python
def output_type_handler(cursor, name, default_type, size, precision, scale):
    if default_type in (oracledb.DB_TYPE_CLOB, oracledb.DB_TYPE_NCLOB, oracledb.DB_TYPE_XMLTYPE):
        return cursor.var(oracledb.DB_TYPE_LONG, arraysize=cursor.arraysize)
    if default_type == oracledb.DB_TYPE_BLOB:
        return cursor.var(oracledb.DB_TYPE_LONG_RAW, arraysize=cursor.arraysize)
    if default_type in (oracledb.DB_TYPE_DATE, oracledb.DB_TYPE_TIMESTAMP,
                        oracledb.DB_TYPE_TIMESTAMP_TZ, oracledb.DB_TYPE_TIMESTAMP_LTZ):
        return cursor.var(oracledb.DB_TYPE_VARCHAR, size=50, arraysize=cursor.arraysize)

self.conn.outputtypehandler = output_type_handler
```

**¿Por qué es importante?** Oracle maneja tipos que Python no soporta nativamente (CLOB, BLOB, fechas con años fuera de rango). Este handler los convierte automáticamente al vuelo: LOBs → `LONG`/`LONG_RAW`, fechas → `VARCHAR` con formato string, evitando errores de materialización.

### 2.2. Detección de columnas muertas

```python
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
```

Una sola consulta calcula el % de vacío por columna. Las columnas con 100% NULL o whitespace se marcan como **muertas** y se excluyen de la extracción, ahorrando ancho de banda y evitando falsos positivos en el perfilado.

### 2.3. Extracción paginada con reanudación

```python
def extract_table_paginated(self, esquema, tabla, chunk_size=50000, start_chunk=0, excluded_columns=None):
    ...
    cols = []
    for name, col_type in col_meta:
        if name in excluded_columns:
            continue
        if col_type in _BINARY_TYPES:
            select_parts.append(f'NULL AS "{name}"')
        else:
            select_parts.append(f'"{name}"')
        cols.append(name)

    query = f"SELECT {', '.join(select_parts)} FROM {tabla_full} ORDER BY ROWID"

    with self.conn.cursor() as cur:
        cur.arraysize = 25000
        cur.execute(query)
        while True:
            rows = cur.fetchmany(chunk_size)
            if not rows:
                break
            chunk_actual += 1
            if chunk_actual <= start_chunk:
                continue  # Salta chunks ya procesados
            ...
            yield pd.DataFrame(rows, columns=cols)
```

- **Chunks de 50.000** filas para control de memoria
- **Columnas binarias** se sustituyen por `NULL` en el SELECT (no se transfieren por red)
- **Saneamiento de caracteres**: elimina bytes nulos `\x00` y `\ufffd` (replacement character) que rompen CSV
- **`yield`** → generador que permite al orquestador procesar chunk por chunk sin cargar toda la tabla en RAM

---

## 3. Transformación / Perfilado — `transform/profiler.py`

### 3.1. Validaciones aplicadas a cada chunk

```python
# A. DUPLICADOS EN PK
mask_dups = self.df.duplicated(subset=[pk_col], keep=False)
self.df.loc[mask_dups, 'REJECTION_REASON'] += f"DUPLICADO_EN_PK_{pk_col} | "

# B. CAMPOS VACÍOS (NULL o whitespace)
for col in self.df.columns:
    if col == 'REJECTION_REASON':
        continue
    mask_nulos = self.df[col].isnull()
    if pd.api.types.is_string_dtype(self.df[col]):
        mask_blancos = self.df[col].notnull() & (self.df[col].astype(str).str.strip() == "")
    mask_vacios = mask_nulos | mask_blancos
    if mask_vacios.all():
        continue  # Columna muerta → no la validamos
    self.df.loc[mask_vacios, 'REJECTION_REASON'] += f"{col} vacio | "

# C. CARACTERES CORRUPTOS (tildes mal insertadas como '?')
mask_corrupto = self.df[col].astype(str).str.contains(r'\?', na=False)
self.df.loc[mask_corrupto, 'REJECTION_REASON'] += f"CARACTER_CORRUPTO_EN_{col} | "

# D. FORMATO EMAIL
regex_email = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
mask_invalid_email = (~self.df[col].astype(str).str.match(regex_email, na=True)) & (self.df[col].notnull())
self.df.loc[mask_invalid_email, 'REJECTION_REASON'] += f"FORMATO_EMAIL_INVALIDO_EN_{col} | "
```

### 3.2. Segregación CLEAN / DIRTY

```python
df_dirty = self.df[self.df['REJECTION_REASON'] != ""].copy()
df_clean = self.df[self.df['REJECTION_REASON'] == ""].copy()
if not df_clean.empty:
    df_clean = df_clean.drop(columns=['REJECTION_REASON'])
```

- **CLEAN**: filas que pasaron TODAS las validaciones
- **DIRTY**: filas con al menos un error, incluyendo columna `REJECTION_REASON` concatenada con el detalle de cada regla que falló

### 3.3. Reporte de calidad

```python
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
```

---

## 4. Orquestación e Idempotencia — `main.py`

### 4.1. Estructura del checkpoint (JSON)

```json
{
  "output_timestamp": "20260609_140236",
  "tables": {
    "SPE_REGIONAL": {
      "status": "completed",
      "last_completed_chunk": 1,
      "dead_columns": ["COLUMNA_MUERTA"],
      "dead_columns_checked": true
    },
    "SPE_CENTRO_SPE": {
      "status": "in_progress",
      "last_completed_chunk": 3,
      "dead_columns": [],
      "dead_columns_checked": true
    }
  }
}
```

### 4.2. Idempotencia profunda: cómo funciona

El checkpoint se guarda en `data_output/_etl_checkpoint.json` y permite:

| Escenario | Comportamiento |
|-----------|---------------|
| **Pipeline completo exitoso** | Todas las tablas quedan en `"status": "completed"`. Al re-ejecutar, se salta TODO. |
| **Fallo a mitad de tabla grande** | La tabla queda en `"status": "in_progress"` con `last_completed_chunk: N`. La siguiente ejecución reanuda desde `chunk N+1`. |
| **Fallo en una tabla, otras completadas** | Las tablas con `completed` se saltan; se reprocesa solo la fallida. |
| **Cambio de estructura en Oracle** | `dead_columns_checked: false` fuerza recalcular columnas muertas (aunque hoy se recalcula siempre). |
| **Timestamp constante por corrida** | `output_timestamp` se fija al inicio de la ejecución. Todos los CSVs generados usan el mismo timestamp, agrupando la corrida completa. |

**Código clave:**

```python
CHECKPOINT_FILE = DATA_OUTPUT_DIR / "_etl_checkpoint.json"

def _cargar_checkpoint():
    estado_base = {"output_timestamp": None, "tables": {}}
    if not CHECKPOINT_FILE.exists():
        return estado_base
    with CHECKPOINT_FILE.open('r', encoding='utf-8') as f:
        estado = json.load(f)
    estado.setdefault("output_timestamp", None)
    estado.setdefault("tables", {})
    return estado
```

### 4.3. Escritura atómica del checkpoint

```python
def _guardar_checkpoint(estado):
    tmp_file = CHECKPOINT_FILE.with_suffix('.tmp')
    with tmp_file.open('w', encoding='utf-8') as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    tmp_file.replace(CHECKPOINT_FILE)  # Atómico en Linux
```

Se escribe primero a un archivo temporal (`.tmp`) y luego se mueve atómicamente con `replace()`. Esto evita corrupción si el proceso se interrumpe durante la escritura.

### 4.4. Flujo completo del orquestador

```python
def ejecutar_inventario_completo():
    reader = OracleReader()
    checkpoint = _cargar_checkpoint()

    for nombre_tabla, config_tabla in tablas.items():
        estado_tabla = _obtener_estado_tabla(checkpoint, nombre_tabla)

        # Saltar si ya completada → IDEMPOTENCIA
        if estado_tabla.get("status") == "completed":
            continue

        # 1. Conteo y restricciones
        count = reader.get_count(esquema, nombre_tabla)
        constraints = reader.obtener_restricciones(esquema, nombre_tabla)

        # 2. Detectar columnas muertas (una vez por tabla)
        columnas_muertas, _ = reader.obtener_estadisticas_vacios(esquema, nombre_tabla)

        # 3. Extraer chunks, perfilar y acumular
        for df_raw in reader.extract_table_paginated(..., start_chunk=chunk_inicial, ...):
            profiler = DataProfiler(df_raw, nombre_tabla, config_tabla)
            df_clean, df_dirty, _, _ = profiler.analizar()
            acumular_csv_inventario(nombre_tabla, df_clean, df_dirty, output_timestamp)

            estado_tabla["last_completed_chunk"] = chunk_actual
            _guardar_checkpoint(checkpoint)  # Persiste después de CADA chunk

        estado_tabla["status"] = "completed"
        _guardar_checkpoint(checkpoint)

    reader.close()
```

**Puntos clave del flujo:**

| Paso | Acción | Tolerante a fallos |
|------|--------|-------------------|
| 1 | Carga checkpoint existente | Si no existe, crea estado base |
| 2 | Itera tablas del YAML | Cada tabla es independiente |
| 3 | Valida si ya completada | **Skip total** — no toca la tabla |
| 4 | Obtiene count + constraints | Si count=0, marca `completed` sin procesar |
| 5 | Detecta columnas muertas | Guarda en checkpoint para referencia |
| 6 | Extrae por chunks | Checkpoint se actualiza **cada chunk** |
| 7 | Perfila y separa CLEAN/DIRTY | En memoria, fila por fila |
| 8 | Acumula a CSV | Append sobre archivo existente |
| 9 | Marca tabla `completed` | Checkpoint final |

---

## 5. Acumulación a CSV — `load/csv_writer.py`

### 5.1. Escritura en modo append

```python
def acumular_csv_inventario(nombre_tabla, df_clean, df_dirty, timestamp, total_registros_tabla=None):
    ruta_clean = output_dir / f"{nombre_tabla_archivo}_clean_{timestamp}.csv"
    ruta_dirty = output_dir / f"{nombre_tabla_archivo}_dirty_{timestamp}.csv"

    if df_clean is not None and not df_clean.empty:
        df_clean_copia['TABLA_ORIGEN'] = nombre_tabla
        df_clean_copia['TIMESTAMP_CARGA'] = timestamp

        modo_append = os.path.exists(ruta_clean)
        df_clean_copia.to_csv(
            ruta_clean,
            mode='a',
            header=not modo_append,
            index=False,
            encoding='utf-8'
        )
```

**Trazabilidad**: cada fila incluye `TABLA_ORIGEN` y `TIMESTAMP_CARGA` para saber de dónde vino y cuándo se cargó.

### 5.2. Particionado automático

```python
CSV_ROW_LIMIT = 1_048_576  # Límite de Excel
MAX_ROWS_PER_FILE = CSV_ROW_LIMIT - 100  # Margen de seguridad

requiere_particionado = total_estimado > MAX_ROWS_PER_FILE

if requiere_particionado:
    output_dir = DATA_OUTPUT_DIR / nombre_tabla
    # Los archivos se crean como: tabla_001.csv, tabla_002.csv, ...
```

Si una tabla supera ~1M de filas, los CSVs se particionan automáticamente para mantener compatibilidad con Excel (1.048.576 filas es el límite de una hoja).

### 5.3. Normalización a minúsculas

```python
def _normalizar_texto_a_minuscula(df):
    columnas_texto = df.select_dtypes(include=['object', 'string']).columns
    for col in columnas_texto:
        df[col] = df[col].where(df[col].isna(), df[col].astype(str).str.lower())
    return df
```

Todo el texto se unifica a **minúsculas** para evitar falsos duplicados por capitalización. Los NULL se conservan.

---

## 6. Carga CSV → PostgreSQL — `cargar_csv_postgres.py` + `postgres_writer.py`

### 6.1. Interfaz CLI

```bash
python cargar_csv_postgres.py \
    --csv data_output/regional_clean_20260609_140236.csv \
    --tabla regional \
    --schema public \
    --truncate \
    --dry-run
```

| Argumento | Uso |
|-----------|-----|
| `--csv` | Ruta al archivo CSV (si solo es nombre, busca en `data_output/`) |
| `--tabla` | Tabla destino en PostgreSQL |
| `--schema` | Schema (default: public) |
| `--delimiter` | Separador CSV (default: `,`) |
| `--chunk-size` | Lote por INSERT (default: 5000) |
| `--truncate` | Trunca la tabla antes de insertar |
| `--dry-run` | Valida todo pero no inserta |

### 6.2. Inserción masiva con `execute_values`

```python
def insert_csv(self, csv_path, table_name, schema_name="public", ...):
    conn = self._connect()
    table_columns = self._get_table_columns(conn, schema_name, table_name)
    normalized_table_cols = {c.lower(): c for c in table_columns}

    reader = pd.read_csv(source, sep=delimiter, dtype=object, chunksize=chunk_size)

    for chunk in reader:
        # Validación de columnas en el primer chunk
        if first_chunk:
            csv_columns = list(chunk.columns)
            unknown = [c for c in csv_columns if c.lower() not in normalized_table_cols]
            if unknown:
                raise ValueError(f"Columnas del CSV no existen: {unknown}")

        chunk = chunk.where(pd.notnull(chunk), None)
        rows = [
            tuple(None if isinstance(v, str) and v.strip() == "" else v
                  for v in row)
            for row in chunk.itertuples(index=False, name=None)
        ]

        insert_sql = sql.SQL("INSERT INTO {}.{} ({}) VALUES %s").format(
            sql.Identifier(schema_name),
            sql.Identifier(table_name),
            sql.SQL(", ").join(sql.Identifier(col) for col in mapped_columns),
        )
        execute_values(cur, insert_sql.as_string(cur), rows, page_size=chunk_size)
```

**`execute_values`** es una extensión de psycopg2 que construye un solo `INSERT` con múltiples VALUES en lote. Es dramáticamente más rápido que inserts individuales (reducción de ~95% en viajes redonda a la DB).

### 6.3. Validaciones de seguridad

```python
def _validate_identifier(self, identifier, label):
    if not identifier or not _IDENTIFIER_RE.match(identifier):
        raise ValueError(f"{label} invalido: {identifier!r}")

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
```

Protección contra **SQL injection** en nombres de schema/tabla. Se valida que solo contengan caracteres alfanuméricos y `_`.

### 6.4. Manejo de vacíos → NULL

```python
@staticmethod
def _normalize_empty(value):
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value
```

Cualquier string vacío o whitespace se convierte a `NULL` PostgreSQL, manteniendo consistencia con el modelo de datos.

---

## 7. Resumen de decisiones técnicas

| Decisión | ¿Por qué? |
|----------|-----------|
| **Chunks de 50.000** | Balance entre memoria y performance de red |
| **Checkpoint por chunk** | Permite reanudar en el registro exacto donde falló |
| **minúsculas en texto** | Evita falsos duplicados por capitalización |
| **Separación CLEAN/DIRTY** | El negocio decide qué hacer con datos erróneos sin bloquear la carga de datos limpios |
| **Columnas muertas detectadas en origen** | Reduce tráfico Oracle→pipeline y evita que tablas con una columna 100% NULL se marquen enteras como DIRTY |
| **output_timestamp fijo por corrida** | Agrupa todos los CSVs de una ejecución bajo el mismo identificador |
| **`execute_values`** | Inserción masiva en PostgreSQL (~10x más rápido que inserts uno por uno) |
| **Dry-run** | El usuario valida CSV vs esquema Postgres antes de tocar datos |
| **Validación de identificadores** | Protege contra inyección SQL en nombres de tabla/schema |

---

## 8. Diagrama de estado de una tabla en el checkpoint

```
                  ┌─────────────┐
                  │   PENDING   │  (nunca tocada)
                  └──────┬──────┘
                         │
                         ▼
                  ┌─────────────┐
                  │ IN_PROGRESS │  (procesando chunks)
                  └──────┬──────┘
                   ┌─────┴──────┐
                   │            │
                   ▼            ▼
            ┌──────────┐  ┌──────────┐
            │COMPLETED │  │  FAILED  │
            └──────────┘  └──────────┘
                   │
                   │ (re-ejecución)
                   ▼
              Salta tabla
              (idempotencia)
```

En caso de `FAILED`, la re-ejecución del pipeline retoma la tabla desde el último chunk completado (`last_completed_chunk`), sin perder las filas ya procesadas. En caso de `COMPLETED`, el pipeline salta la tabla completamente — ni siquiera toca Oracle para esa tabla.
