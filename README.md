# data-inventory

Pipeline ETL en Python 3.10+ para generar un inventario técnico de las tablas del esquema Oracle **SPE**.  
Produce archivos Excel individuales por tabla y un Reporte Maestro consolidado con hallazgos de calidad, tipos de datos y restricciones de integridad.

Existen dos variantes del pipeline según el volumen de la tabla:

| Pipeline | Script | Estrategia |
|---|---|---|
| **Normal** | `main.py` | Transfiere datos, perfila filas (CLEAN / DIRTY) |
| **Masivas** | `main_masivas.py` | Solo metadatos del diccionario Oracle, sin transferir filas |

---

## Estructura del proyecto

```
├── config/
│   ├── settings.py              # DSN, rutas de salida, carga de variables .env
│   ├── tablas.yaml              # Tablas normales: PK, destino sugerido, sensibilidad
│   └── tablas_masivas.yaml      # Tablas masivas (> 1M filas): misma estructura
├── extract/
│   ├── __init__.py
│   ├── oracle_reader.py         # OracleReader: conexión, conteo, restricciones y extracción
│   └── oracle_reader_masivas.py # OracleReader masivas: solo metadatos y conteo de nulos
├── transform/
│   ├── __init__.py
│   ├── profiler.py              # DataProfiler: segregación CLEAN/DIRTY, mapeo de tipos
│   └── profiler_masivas.py      # DataProfiler masivas: análisis sobre metadatos
├── load/
│   ├── __init__.py
│   ├── excel_writer.py          # Escritura Excel (4 pestañas: análisis, columnas, clean, dirty)
│   └── excel_writer_masivas.py  # Escritura Excel masivas (2 pestañas: análisis, columnas)
├── logs/                        # Logs de cada ejecución (auto-generado)
├── tests/
│   └── __init__.py
├── main.py                      # Orquestador del pipeline normal
├── main_masivas.py              # Orquestador del pipeline masivas
├── generar_reporte_maestro.py   # Consolida inventarios normales en Reporte Maestro
├── generar_reporte_maestro_masivo.py  # Consolida inventarios masivos en Reporte Maestro
├── crear_yaml.py                # Genera config/tablas.yaml desde tablas.txt
├── reconstruir_reporte_anterior.py   # Utilidad de recuperación de reporte desde logs
├── tablas.txt                   # Listado plano de tablas (insumo para crear_yaml.py)
├── requirements.txt
└── README.md
```

---

## Requisitos

- Python 3.10+
- Oracle Instant Client (requerido para modo *thick* del driver `oracledb`)

---

## Instalación

```bash
# 1. Crear y activar entorno virtual
python -m venv .venv
.venv\Scripts\activate           # Windows
source .venv/bin/activate        # Linux/macOS

# 2. Instalar dependencias
pip install -r requirements.txt
```

---

## Configuración

Las credenciales de Oracle se definen en un archivo **`.env`** en la raíz del proyecto (nunca se sube al repositorio):

```env
ORACLE_USER=mi_usuario
ORACLE_PASS=mi_contraseña
ORACLE_HOST=mi_servidor
ORACLE_PORT=1521
ORACLE_SERVICE=MI_SVC
ORACLE_CLIENT_PATH=C:/oracle/instantclient_21_x
```

| Variable             | Descripción                                      |
|----------------------|--------------------------------------------------|
| `ORACLE_USER`        | Usuario de base de datos                         |
| `ORACLE_PASS`        | Contraseña                                       |
| `ORACLE_HOST`        | Host del servidor Oracle                         |
| `ORACLE_PORT`        | Puerto TNS (normalmente `1521`)                  |
| `ORACLE_SERVICE`     | Nombre del servicio Oracle                       |
| `ORACLE_CLIENT_PATH` | Ruta al Oracle Instant Client (modo thick)       |

### Definición de tablas (`config/tablas.yaml` / `config/tablas_masivas.yaml`)

Cada tabla se configura con:

```yaml
esquema_origen: SPE
tablas:
  NOMBRE_TABLA:
    descripcion: "Descripción de la tabla"
    destino_sugerido: POSTGRESQL   # o MONGODB
    sensible: true                 # true si contiene datos personales o críticos
```

Para regenerar `tablas.yaml` desde el archivo plano `tablas.txt`:

```bash
python crear_yaml.py
```

---

## Uso

```bash
# Pipeline normal (tablas con menos de 1,000,000 registros)
python main.py

# Pipeline masivas (tablas con más de 1,000,000 registros)
python main_masivas.py
```

Ambos pipelines son **idempotentes**: si el archivo Excel de una tabla ya existe en el directorio de salida, la tabla se omite automáticamente.

---

## Salida

| Directorio            | Contenido                                                      |
|-----------------------|----------------------------------------------------------------|
| `data_output/`        | `INVENTARIO_<TABLA>.xlsx` + `REPORTE_MAESTRO_MIGRACION_SPE.xlsx` |
| `data_output_masivas/`| `INVENTARIO_<TABLA>.xlsx` + `REPORTE_MAESTRO_MIGRACION_SPE_MASIVAS.xlsx` |
| `logs/`               | `pipeline_<timestamp>.log` y `pipeline_masivas_<timestamp>.log` |

### Pestañas del Excel individual (pipeline normal)

| Pestaña            | Contenido                                              |
|--------------------|--------------------------------------------------------|
| `ANALISIS_TECNICO` | Resumen ejecutivo: filas, peso, calidad, sensibilidad  |
| `DETALLE_COLUMNAS` | Inventario de columnas con tipos Oracle, PG, Mongo     |
| `CLEAN`            | Registros sin errores de integridad                    |
| `DIRTY`            | Registros con errores y motivo de rechazo              |

### Pestañas del Reporte Maestro

| Pestaña                   | Contenido                                    |
|---------------------------|----------------------------------------------|
| `INVENTARIO_GENERAL`      | Consolidado de todos los ANALISIS_TECNICO    |
| `CATALOGO_TIPOS_DATOS`    | Mapeo deduplicado Oracle → PostgreSQL/MongoDB |
| `DETALLE_CONSTRAINTS`     | PK, FK, UNIQUE, CHECK por tabla              |
| `RESUMEN_INTEGRIDAD`      | Totales de restricciones encontradas         |
| `TABLAS_VACIAS`           | Tablas sin registros                         |
| `TABLAS_MASIVAS`          | Tablas con más de 1,000,000 filas            |
| `TABLAS_POCOS_REGISTROS`  | Tablas con menos de 100 filas                |

Los logs se escriben en `logs/etl.log` y también en la consola.

## Tests

```bash
# Ejecutar todos los tests (no requiere conexión a Oracle)
python -m pytest tests/ -v
```

## Componentes principales

### `extract/oracle_reader.py` — `OracleReader`
- Conexión mediante SQLAlchemy + `oracledb` en modo *thin* (sin Oracle Client).
- Lectura paginada con `OFFSET/FETCH`.
- Filtros por rango de fechas (`read_by_date`) o por lote (`read_by_lote`).
- Uso como context manager para gestión automática de recursos.

### `transform/profiler.py` — `DataProfiler`
- Calcula nulos, cardinalidad, estadísticas descriptivas, longitudes de texto.
- Exporta el perfil a CSV, JSON o Excel.

### `load/csv_writer.py` — `CsvWriter`
- Escribe DataFrames a CSV con separador configurable.
- Soporta escritura en chunks (fragmentos numerados).
- Genera manifiesto JSON con SHA-256, filas, columnas y timestamp de cada archivo.
