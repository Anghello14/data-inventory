# Quick Start — ETL Base en 5 pasos

Aquí te mostramos cómo usar la base ETL para auditar tu tabla en menos de 5 minutos.

---

## Paso 1: Configurar credenciales (`.env`)

Crear archivo `.env` en la raíz del proyecto:

```env
ORACLE_USER=tu_usuario
ORACLE_PASS=tu_contraseña
ORACLE_HOST=servidor.com
ORACLE_PORT=1521
ORACLE_SERVICE=MI_SVC
ORACLE_CLIENT_PATH=/opt/oracle/instantclient_21_x
```

---

## Paso 2: Instalar dependencias

```bash
pip install -r requirements.txt
```

---

## Paso 3: Agregar tu tabla al config

Editar `config/etl_config.yaml`:

```yaml
esquema_origen: SPE

tablas:
  MI_TABLA:
    descripcion: "Mi tabla que quiero auditar"
    pk: ID                          # Clave primaria
    not_null:
      - ID
      - NOMBRE
    sensible: false
    exclude_from_profiling: []
    validaciones_campos: {}
```

---

## Paso 4: Ejecutar

```bash
python main.py
```

**Output:**
- `data_output/INVENTARIO_MI_TABLA.xlsx` — Excel con 4 pestañas (análisis, columnas, clean, dirty)

---

## Paso 5 (Opcional): Personalizar por tabla

### 5a: Validaciones adicionales

```yaml
tablas:
  MI_TABLA:
    # ... config anterior ...
    validaciones_campos:
      CORREO: email           # Valida formato email
      EDAD: integer           # Valida que sea entero
```

### 5b: Excluir columnas pesadas

```yaml
tablas:
  MI_TABLA:
    exclude_from_profiling:
      - DESCRIPCION_LARGA
      - DATOS_BINARIOS
      - IMAGEN
```

### 5c: Transformar datos antes de escribir Excel

Crear archivo `load/my_transformer.py`:

```python
from load.excel_csv import ExcelWriter

class MiExcelWriter(ExcelWriter):
    def _preprocesar_clean(self, df):
        # Aquí transformas los datos limpios
        df['PROCESADO_EN'] = pd.Timestamp.now()
        df = df.rename(columns={"VIEJO": "NUEVO"})
        return df
```

Usar en `main.py`:

```python
from load.my_transformer import MiExcelWriter

# Cambiar esta línea en etl/pipeline.py, método _load():
writer = MiExcelWriter(self.nombre_tabla)  # En lugar de ExcelWriter
```

---

## Ejemplo Real: Auditar tabla CLIENTES

### config/etl_config.yaml

```yaml
esquema_origen: SPE

tablas:
  CLIENTES:
    descripcion: "Tabla de clientes con validaciones de calidad"
    pk: ID_CLIENTE
    not_null:
      - ID_CLIENTE
      - NOMBRE
      - EMAIL
    sensible: true              # Tiene datos personales
    exclude_from_profiling:
      - FOTO_CLIENTE
      - DATOS_JSON
    validaciones_campos:
      EMAIL: email
      TELEFONO: integer
```

### Ejecutar

```bash
python main.py
```

### Resultado

```
data_output/INVENTARIO_CLIENTES.xlsx
```

Dentro del Excel:
- **ANALISIS_TECNICO**: "500,000 registros, 450,000 limpios (90%), peso 120 MB"
- **DETALLE_COLUMNAS**: "EMAIL: object → TEXT, TELEFONO: int64 → INTEGER, ..."
- **CLEAN**: 450,000 registros válidos (sin duplicados, sin nulos, emails correctos)
- **DIRTY**: 50,000 registros con motivo del rechazo (ej: "DUPLICADO_EN_PK_ID_CLIENTE | FORMATO_EMAIL_INVALIDO_EN_EMAIL")

---

## Acciones Comunes

### ¿Cómo valido una columna con formato específico?

Agregar a `validaciones_campos`:

```yaml
validaciones_campos:
  CODIGO_POSTAL: regex:^\d{5}$      # (futuro: validar con regex)
  EMAIL: email
  EDAD: integer
```

**Nota**: Por ahora soportamos `email` e `integer`. Para otros formatos, subclasea `DataProfiler` en `transform/profiler.py`.

### ¿Cómo agrego una columna calculada al Excel?

```python
class MiExcelWriter(ExcelWriter):
    def _preprocesar_clean(self, df):
        df['CALIDAD_FILA'] = 'BUENA'
        df['FECHA_PROCESAMIENTO'] = pd.Timestamp.now()
        return df
```

### ¿Cómo cambio el directorio de salida?

En `config/etl_config.yaml`:

```yaml
salida:
  directorio: /tmp/mis_auditorias
  formato: excel
```

### ¿Cómo agrego otra tabla?

Solo copiar y cambiar en `config/etl_config.yaml`:

```yaml
tablas:
  TABLA_1:
    pk: ID
    # ...
  TABLA_2:              # Nueva tabla
    pk: CODIGO
    # ...
```

Ejecutar `python main.py` y procesa ambas.

---

## Troubleshooting

| Error | Solución |
|-------|----------|
| `FileNotFoundError: .env` | Crear `.env` con credenciales Oracle |
| `ConnectionError: Oracle` | Verificar ORACLE_CLIENT_PATH existe y credenciales |
| `KeyError: 'PK'` | Verificar `config/etl_config.yaml` tiene estructura correcta |
| `No module named 'oracledb'` | Ejecutar `pip install -r requirements.txt` |

---

## Ejemplo Programático

Si necesitas más control, usa el API directamente:

```python
from etl.pipeline import ETLPipeline

config = {
    'pk': 'ID',
    'not_null': ['NOMBRE'],
    'sensible': False,
    'validaciones_campos': {'EMAIL': 'email'}
}

pipeline = ETLPipeline("MI_TABLA", config, esquema="SPE")
df_clean, df_dirty = pipeline.ejecutar()

# Acceder a estadísticas
stats = pipeline.get_estadisticas()
print(f"Calidad: {stats['INDICE_CALIDAD']}")
print(f"Registros limpios: {stats['FILAS_LIMPIAS']}")
```

---

**¿Preguntas?** Ver `README.md` o contacta al equipo.
