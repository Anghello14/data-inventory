# data-inventory

Pipeline ETL en Python 3.10+ para analizar las tablas de la base de datos SPE.
El output consiste en archivos CSV con el inventario detallado y el perfilamiento
de calidad de los registros, acompañados de un manifiesto JSON.

## Estructura del proyecto

```
├── config/
│   ├── settings.py        # DSN, rutas, parámetros por defecto
│   └── tablas.yaml        # Definición de tablas: PK, col_fecha, col_lote
├── extract/
│   ├── __init__.py
│   └── oracle_reader.py   # Clase OracleReader con paginación
├── transform/
│   ├── __init__.py
│   └── profiler.py        # Generación de reporte de calidad
├── load/
│   ├── __init__.py
│   └── csv_writer.py      # Escritura CSV + generación de manifiesto
├── tests/
│   ├── __init__.py
│   ├── test_settings.py
│   ├── test_oracle_reader.py
│   ├── test_profiler.py
│   └── test_csv_writer.py
├── main.py                # Orquestación del proceso completo
├── conftest.py            # Configuración de pytest
├── requirements.txt
├── .gitignore
└── README.md
```

## Requisitos

- Python 3.10+
- Oracle Instant Client (solo si se usa modo *thick* del driver `oracledb`)

## Instalación

```bash
# 1. Crear y activar entorno virtual
python3 -m venv .venv
source .venv/bin/activate        # Linux/macOS
.venv\Scripts\activate           # Windows

# 2. Instalar dependencias
pip install -r requirements.txt
```

## Configuración

Las credenciales de Oracle se pasan mediante **variables de entorno** (nunca se
almacenan en el repositorio):

| Variable         | Descripción                  | Default        |
|------------------|------------------------------|----------------|
| `ORACLE_USER`    | Usuario de base de datos     | `usuario`      |
| `ORACLE_PASSWORD`| Contraseña                   | `contraseña`   |
| `ORACLE_HOST`    | Host del servidor Oracle     | `localhost`    |
| `ORACLE_PORT`    | Puerto TNS                   | `1521`         |
| `ORACLE_SERVICE` | Nombre del servicio Oracle   | `ORCL`         |
| `ORACLE_SCHEMA`  | Esquema por defecto          | igual a USER   |
| `BATCH_SIZE`     | Filas por página de extracción | `10000`      |
| `LOG_LEVEL`      | Nivel de logging             | `INFO`         |

```bash
export ORACLE_USER=mi_usuario
export ORACLE_PASSWORD=mi_contraseña
export ORACLE_HOST=mi_servidor
export ORACLE_SERVICE=MI_SVC
```

### Definición de tablas (`config/tablas.yaml`)

Edita el archivo para agregar o quitar tablas del pipeline:

```yaml
tablas:
  - nombre: MI_TABLA
    schema: MI_ESQUEMA
    pk:
      - ID_CAMPO
    col_fecha: FECHA_CREACION
    col_lote: LOTE_CARGA
    activa: true
```

## Uso

```bash
# Procesar todas las tablas activas (lectura completa)
python main.py

# Filtrar por rango de fechas
python main.py --fecha-inicio 2024-01-01 --fecha-fin 2024-03-31

# Filtrar por lote
python main.py --lote 20240101

# Procesar solo una tabla
python main.py --tabla CLIENTES
```

Los archivos de salida se generan en `output/`:

- `data_<tabla>.csv` — datos extraídos
- `perfil_<tabla>.csv` — métricas de calidad por columna
- `manifest.json` — metadatos de todos los archivos generados

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
