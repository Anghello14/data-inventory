# data-inventory — ETL Base Profesional y Reutilizable

Pipeline ETL genérico en Python 3.10+ para extraer, perfilar y auditar tablas Oracle.  
Diseñado para que cualquier desarrollador lo adapte a su tabla cambiando solo configuración y mínima lógica.

---

## Estructura del Proyecto

```
├── config/
│   ├── settings.py           # DSN, rutas, carga .env
│   └── etl_config.yaml       # Configuración de tablas (EDITABLE AQUÍ)
├── extract/
│   ├── __init__.py
│   └── oracle_reader.py      # OracleReader: conexión, lectura desde Oracle
├── transform/
│   ├── __init__.py
│   └── profiler.py           # DataProfiler: validación, segregación CLEAN/DIRTY
├── load/
│   ├── __init__.py
│   └── excel_csv.py          # ExcelWriter: salida a Excel (extensible)
├── etl/
│   ├── __init__.py
│   └── pipeline.py           # ETLPipeline: orquestador genérico
├── tests/                    # Tests unitarios
├── logs/                     # Logs de ejecución (auto-generado)
├── data_output/              # Archivos Excel de salida (auto-generado)
├── main.py                   # Punto de entrada
├── requirements.txt
└── README.md
```

---

## Requisitos

- Python 3.10+
- Oracle Instant Client (para modo thick del driver `oracledb`)

---

## Instalación

```bash
# 1. Clonar y entrar al proyecto
cd data-inventory

# 2. Crear y activar entorno virtual
python -m venv .venv
source .venv/bin/activate           # Linux/macOS
# o
.venv\Scripts\activate              # Windows

# 3. Instalar dependencias
pip install -r requirements.txt
```

---

## Configuración

### 1. Variables de entorno (`.env`)

Crear un archivo `.env` en la raíz con tus credenciales Oracle:

```env
ORACLE_USER=mi_usuario
ORACLE_PASS=mi_contraseña
ORACLE_HOST=servidor.com
ORACLE_PORT=1521
ORACLE_SERVICE=MI_SVC
ORACLE_CLIENT_PATH=/opt/oracle/instantclient_21_x
```

### 2. Definir tus tablas (`config/etl_config.yaml`)

Editar `etl_config.yaml` y agregar una sección por tabla:

```yaml
esquema_origen: SPE

tablas:
  MI_TABLA:
    descripcion: "Tabla que voy a auditar"
    pk: ID                           # Columna clave primaria (o null si no existe)
    not_null:                        # Columnas que no pueden ser nulas
      - ID
      - NOMBRE
    sensible: false                  # ¿Contiene datos personales?
    exclude_from_profiling:          # Columnas pesadas a omitir del perfilado
      - DESCRIPCION_LARGA
      - DATOS_BINARIOS
    validaciones_campos:             # Validaciones personalizadas
      CORREO: email
      EDAD: integer
```

---

## Uso Rápido

### Ejecución simple

```bash
python main.py
```

Esto procesa todas las tablas definidas en `etl_config.yaml` y genera un Excel por tabla en `data_output/`.

### Uso programático

```python
from etl.pipeline import ETLPipeline

# Crear y ejecutar pipeline para UNA tabla
pipeline = ETLPipeline(
    nombre_tabla="MI_TABLA",
    config_tabla={
        "pk": "ID",
        "not_null": ["ID", "NOMBRE"],
        "sensible": False,
        "validaciones_campos": {"CORREO": "email"}
    },
    esquema="SPE"
)

df_clean, df_dirty = pipeline.ejecutar()
```

---

## Personalización por Tabla

### Opción 1: Editar validaciones en YAML

```yaml
tablas:
  TABLA_A:
    pk: ID
    validaciones_campos:
      EMAIL: email
      TELEFONO: integer
      FECHA: date
```

### Opción 2: Subclasear ExcelWriter (transformar datos antes de escribir)

Crear `load/my_writer.py`:

```python
from load.excel_csv import ExcelWriter

class MiExcelWriter(ExcelWriter):
    def _preprocesar_clean(self, df):
        # Renombrar columnas, convertir tipos, etc
        df = df.rename(columns={"VIEJO_NOMBRE": "NUEVO_NOMBRE"})
        return df
```

Usar en `main.py`:

```python
from load.my_writer import MiExcelWriter

writer = MiExcelWriter(nombre_tabla)
writer.escribir(df_clean, df_dirty, df_summary, df_nulls)
```

### Opción 3: Subclasear ETLPipeline (lógica personalizada)

```python
from etl.pipeline import ETLPipeline

class MiPipeline(ETLPipeline):
    def _transform(self):
        super()._transform()
        # Agregar lógica adicional aquí
        logging.info("Transformación personalizada completada")
```

---

## Salida

### Archivos generados

```
data_output/
├── INVENTARIO_TABLA_A.xlsx
├── INVENTARIO_TABLA_B.xlsx
└── ...
```

### Pestañas de cada Excel

| Pestaña | Contenido |
|---------|-----------|
| `ANALISIS_TECNICO` | Resumen: filas totales, peso, calidad, sensibilidad |
| `DETALLE_COLUMNAS` | Inventario de tipos (Oracle/Pandas → PostgreSQL/MongoDB) |
| `CLEAN` | Registros que pasaron todas las validaciones |
| `DIRTY` | Registros rechazados (con motivo) |

---

## Componentes Principales

### `extract/oracle_reader.py` — OracleReader

Conexión y lectura de Oracle:

```python
reader = OracleReader()
df = reader.extract_tabla("MI_TABLA", esquema="SPE", limite=None)
```

Métodos:
- `extract_tabla(tabla, esquema, limite)` — interfaz simple
- `extract_table(esquema, tabla, limite)` — nombre formal
- `get_count(esquema, tabla)` — conteo rápido
- `obtener_restricciones(esquema, tabla)` — PK, FK, UNIQUE

### `transform/profiler.py` — DataProfiler

Análisis de datos:

```python
profiler = DataProfiler(df, "MI_TABLA", config_tabla)
df_clean, df_dirty, df_summary, df_nulls = profiler.analizar()
```

Validaciones automáticas:
- Duplicados en PK
- Nulos en campos NOT NULL
- Caracteres corruptos (encoding)
- Email (si está en `validaciones_campos`)

### `load/excel_csv.py` — ExcelWriter

Escritura flexible:

```python
writer = ExcelWriter("MI_TABLA")
writer.escribir(df_clean, df_dirty, df_summary, df_nulls)
```

Extensible: subclasear `_preprocesar_clean()` y `_preprocesar_dirty()` para transformar datos.

### `etl/pipeline.py` — ETLPipeline

Orquestador genérico:

```python
pipeline = ETLPipeline("MI_TABLA", config_tabla, esquema="SPE")
df_clean, df_dirty = pipeline.ejecutar()
stats = pipeline.get_estadisticas()
```

---

## Logs

Cada ejecución genera un log en `logs/pipeline_YYYYMMDD_HHMMSS.log`.  
Nivel configurable en `config/etl_config.yaml` bajo `logs.nivel`.

---

## Tests

```bash
python -m pytest tests/ -v
```

Tests incluyen:
- Validaciones de DataProfiler
- Escritura de ExcelWriter
- Integración básica de ETLPipeline

---

## FAQ

**P: ¿Cómo cambio la tabla a auditar?**  
R: Edita `config/etl_config.yaml` y cambia el nombre de la tabla o crea una nueva sección.

**P: ¿Puedo agregar validaciones personalizadas?**  
R: Sí. En `etl_config.yaml`, usa `validaciones_campos` para email/integer. Para lógica compleja, subclasea `DataProfiler`.

**P: ¿Qué pasa si tengo columnas muy pesadas?**  
R: Agrega el nombre a `exclude_from_profiling` en el YAML. OracleReader las traerá como NULL.

**P: ¿Es obligatorio usar ETLPipeline?**  
R: No. Puedes usar `OracleReader`, `DataProfiler` y `ExcelWriter` por separado si lo necesitas.

---

## Arquitectura

```
main.py
  ├─ Lee etl_config.yaml
  ├─ Itera tablas
  └─ Para cada tabla:
      ├─ ETLPipeline.ejecutar()
      │   ├─ OracleReader.extract_tabla()
      │   ├─ DataProfiler.analizar()
      │   └─ ExcelWriter.escribir()
      └─ Logs a console y archivo
```

---

## Soporte

Contacta con el equipo si encuentras problemas o necesitas nuevas validaciones.
