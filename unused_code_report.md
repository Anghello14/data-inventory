# Reporte de Código Muerto y No Usado

## 1. `main.py`

### Línea 7 — `from pathlib import Path`
**Import sin uso.** El constructor `Path()` nunca se invoca. Todas las operaciones con Path (`exists()`, `open()`, `parent`, `with_suffix()`, `replace()`) son sobre **instancias** provenientes de `DATA_OUTPUT_DIR`. Se puede eliminar sin riesgo.

### Línea 181 — `df_input = df_raw`
**Alias de variable redundante.** `df_raw` viene del generador `extract_table_paginated()` y se reasigna inmediatamente a `df_input` solo para pasarlo a `DataProfiler()` en la línea 183. Se puede pasar `df_raw` directamente y eliminar la asignación.

### Líneas 60-64 — Clave `dead_columns_checked` en `_obtener_estado_tabla()`
**Se escribe pero nunca se lee.** El campo se setea a `True` en la línea 141 pero nunca se consulta en ningún condicional. Las columnas muertas **siempre** se recalculan (líneas 138-139), convirtiendo este campo en estado muerto dentro del checkpoint. Se puede eliminar tanto de la plantilla de estado como de la escritura en línea 141.

---

## 2. `config/settings.py`

### Línea 15 — `LOGS_DIR = BASE_DIR / "logs"`
**Definida pero nunca importada** por ningún otro módulo. Tanto `main.py:17` como `cargar_csv_postgres.py:33` hardcodean `os.makedirs("logs", exist_ok=True)` y `f"logs/pipeline_..."` en vez de usar `from config.settings import LOGS_DIR`. La variable solo se usa localmente en el bucle `for folder in [DATA_OUTPUT_DIR, LOGS_DIR]` (línea 18). Considerar usarla en todo el proyecto o eliminarla.

---

## 3. `transform/profiler.py` y `main.py` — `df_summary` y `df_nulls` nunca consumidos

### `profiler.py:104-137` computa datos que nadie usa
`analizar()` construye y retorna 4 DataFrames: `df_clean`, `df_dirty`, `df_summary`, `df_nulls`. Los dos últimos implican:

- **104-122**: Reporte de detalle de columnas (tipo, sugerencias MongoDB/PostgreSQL, nulos, estado). Son **19 líneas** que producen `df_nulls`.
- **124-137**: Resumen ejecutivo con tamaño estimado, filas limpias/sucias, columnas muertas, índice de calidad. Son **12 líneas** que producen `df_summary`.

### `main.py:184` desempaqueta y descarta
```python
df_clean, df_dirty, df_summary, df_nulls = profiler.analizar()
```

`df_summary` y `df_nulls` jamás se referencian después. El código original planeado en `ETL_PIPELINE_RESUMEN.md:274` ya los marcaba con `_`:
```python
df_clean, df_dirty, _, _ = profiler.analizar()
```

**Impacto:** ~30 líneas ejecutándose en cada chunk de cada tabla sin que su resultado se use. Si se elimina la creación de `df_summary` y `df_nulls` (o se marca su retorno como `None`), se ahorra tiempo y memoria proporcional a la cantidad de tablas procesadas.

---

## 4. `extract/oracle_reader.py`

### Líneas 90-93 y 165-169 — Tupla `_BINARY_TYPES` duplicada
**Duplicación de código, no es código muerto pero es un code smell.** La tupla `(DB_TYPE_BLOB, DB_TYPE_RAW, DB_TYPE_LONG_RAW)` está definida idénticamente dentro de `obtener_estadisticas_vacios()` y `extract_table_paginated()`. Extraer a una constante a nivel de módulo para evitar divergencia.

---

## Tabla Resumen

| Archivo | Línea(s) | Problema | Severidad |
|---|---|---|---|
| `main.py` | 7 | Import sin uso: `Path` | Baja |
| `main.py` | 181 | `df_input = df_raw` redundante | Baja |
| `main.py` | 184 | `df_summary` / `df_nulls` desempaquetados y nunca usados | **Media** |
| `main.py` | 60, 63, 141 | `dead_columns_checked` escrito nunca leído | Baja |
| `transform/profiler.py` | 104-137 | Cómputo de `df_summary` y `df_nulls` que nadie consume | **Media** |
| `config/settings.py` | 15 | `LOGS_DIR` definido pero ningún otro módulo lo importa | Baja |
| `extract/oracle_reader.py` | 90-93, 165-169 | `_BINARY_TYPES` duplicado | Baja |
