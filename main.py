import yaml
import logging
import time
import os
import json
from datetime import datetime
from pathlib import Path

from extract.oracle_reader import OracleReader
from transform.profiler import DataProfiler
from load.csv_writer import acumular_csv_inventario
from config.settings import DATA_OUTPUT_DIR

# --- CONFIGURACIÓN DE LOGS ---
timestamp_run = datetime.now().strftime("%Y%m%d_%H%M%S")
log_filename = f"logs/pipeline_{timestamp_run}.log"
os.makedirs("logs", exist_ok=True)
CHECKPOINT_FILE = DATA_OUTPUT_DIR / "_etl_checkpoint.json"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)


def _cargar_checkpoint():
    estado_base = {
        "output_timestamp": None,
        "tables": {}
    }

    if not CHECKPOINT_FILE.exists():
        return estado_base

    try:
        with CHECKPOINT_FILE.open('r', encoding='utf-8') as f:
            estado = json.load(f)
        if not isinstance(estado, dict):
            return estado_base
        estado.setdefault("output_timestamp", None)
        estado.setdefault("tables", {})
        return estado
    except Exception as e:
        logging.warning(f"No se pudo leer checkpoint. Se iniciará uno nuevo. Detalle: {e}")
        return estado_base


def _guardar_checkpoint(estado):
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = CHECKPOINT_FILE.with_suffix('.tmp')
    with tmp_file.open('w', encoding='utf-8') as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    tmp_file.replace(CHECKPOINT_FILE)


def _obtener_estado_tabla(estado, nombre_tabla):
    tablas = estado.setdefault("tables", {})
    if nombre_tabla not in tablas:
        tablas[nombre_tabla] = {
            "status": "pending",
            "last_completed_chunk": 0,
            "dead_columns": [],
            "dead_columns_checked": False
        }
    return tablas[nombre_tabla]

def ejecutar_inventario_completo():
    # Orquesta el pipeline completo: lee config YAML, itera tabla por tabla,
    # extrae datos desde Oracle, los perfila, y acumula registros a CSVs (CLEAN, DIRTY).
    inicio_proceso = time.time()
    
    # Separador visual de inicio
    logging.info("="*60)
    logging.info(f" INICIO DE EJECUCIÓN - ID: {timestamp_run}")
    logging.info("="*60)

    # Checkpoint de idempotencia: conserva avance por tabla/chunk y timestamp de salida.
    checkpoint = _cargar_checkpoint()
    output_timestamp = checkpoint.get("output_timestamp")
    if not output_timestamp:
        output_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        checkpoint["output_timestamp"] = output_timestamp
        _guardar_checkpoint(checkpoint)
    logging.info(f"ID de salida CSV (idempotente): {output_timestamp}")
    
    # Instancia única de conexión a Oracle; se reutiliza para todas las tablas del ciclo
    reader = OracleReader()

    try:
        with open('config/tablas.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        esquema = config.get('esquema_origen', 'SPE')
        tablas = config.get('tablas', {})
        total = len(tablas)

        for i, (nombre_tabla, config_tabla) in enumerate(tablas.items(), 1):
            # Separador visual por tabla (Consola y Log)
            print(f"\n{'='*70}")
            logging.info(f" PROCESANDO {i}/{total}: {nombre_tabla}")
            print(f"{'='*70}")

            try:
                estado_tabla = _obtener_estado_tabla(checkpoint, nombre_tabla)
                if estado_tabla.get("status") == "completed":
                    logging.info("STATUS: YA COMPLETADA EN CHECKPOINT. Se omite por idempotencia.")
                    continue

                # 1. OBTENCIÓN DE CONTEO Y METADATOS (Constraints)
                count = reader.get_count(esquema, nombre_tabla)
                constraints = reader.obtener_restricciones(esquema, nombre_tabla)

                # VALIDACIÓN: TABLAS VACÍAS
                if count == 0:
                    logging.info(f"STATUS: TABLA VACÍA. Registrando...")
                    estado_tabla["status"] = "completed"
                    _guardar_checkpoint(checkpoint)
                    continue

                # VALIDACIÓN: POCOS REGISTROS (< 100) - Se procesan pero se marcan
                if count < 100:
                    logging.info(f"TABLA CON POCOS REGISTROS: {nombre_tabla} ({count})")

                # 2. EXTRACCIÓN Y PROCESAMIENTO EN CHUNKS
                # Conservamos todas las columnas de la fuente para que el CSV final
                # represente la estructura real de la tabla. El filtrado de LOBs/
                # binarios ya ocurre en OracleReader, así que no hace falta excluir
                # columnas de texto como DESCRIPCION en esta etapa.

                # 3. PERFILADO (Usamos el df_input por chunk)
                # Inyectar la PK real al config de la tabla para que el profiler la valide
                if constraints.get('PK') == 'N/A':
                    config_tabla['pk'] = None
                else:
                    config_tabla['pk'] = constraints['PK']

                # Recalcular SIEMPRE al inicio para evitar arrastrar detecciones viejas
                # desde checkpoint cuando cambian reglas o datos en origen.
                columnas_muertas, porcentaje_vacio_por_columna = reader.obtener_estadisticas_vacios(esquema, nombre_tabla)
                estado_tabla["dead_columns"] = columnas_muertas
                estado_tabla["dead_columns_checked"] = True
                _guardar_checkpoint(checkpoint)

                cantidad_muertas = len(columnas_muertas)
                if cantidad_muertas == 0:
                    logging.info(f"[{nombre_tabla}] Columnas muertas detectadas: 0")
                else:
                    logging.info(
                        f"[{nombre_tabla}] Columnas muertas detectadas: {cantidad_muertas} | "
                        f"Nombres: {columnas_muertas}"
                    )

                if porcentaje_vacio_por_columna:
                    resumen_vacios = " | ".join(
                        f"{col}={pct:.2f}%"
                        for col, pct in sorted(
                            porcentaje_vacio_por_columna.items(),
                            key=lambda item: item[1],
                            reverse=True,
                        )
                    )
                    logging.info(f"[{nombre_tabla}] Porcentaje de vacío por columna: {resumen_vacios}")

                chunk_inicial = int(estado_tabla.get("last_completed_chunk", 0) or 0)
                if chunk_inicial > 0:
                    logging.info(f"[{nombre_tabla}] Reanudando desde chunk {chunk_inicial + 1}.")

                estado_tabla["status"] = "in_progress"
                _guardar_checkpoint(checkpoint)

                procesado_al_menos_un_chunk = False
                chunk_actual = chunk_inicial
                for df_raw in reader.extract_table_paginated(
                    esquema,
                    nombre_tabla,
                    chunk_size=50000,
                    start_chunk=chunk_inicial,
                    excluded_columns=estado_tabla.get("dead_columns", []),
                ):
                    procesado_al_menos_un_chunk = True
                    df_input = df_raw

                    profiler = DataProfiler(df_input, nombre_tabla, config_tabla)
                    df_clean, df_dirty, df_summary, df_nulls = profiler.analizar()

                    # 4. ESCRITURA (Usamos los resultados del perfilado optimizado)
                    acumular_csv_inventario(
                        nombre_tabla,
                        df_clean,
                        df_dirty,
                        output_timestamp,
                        total_registros_tabla=count,
                    )

                    chunk_actual += 1
                    estado_tabla["last_completed_chunk"] = chunk_actual
                    _guardar_checkpoint(checkpoint)

                if not procesado_al_menos_un_chunk:
                    logging.info(f"STATUS: SIN DATOS TRAS EXTRACCIÓN")
                    estado_tabla["status"] = "completed"
                    _guardar_checkpoint(checkpoint)
                    continue

                estado_tabla["status"] = "completed"
                _guardar_checkpoint(checkpoint)
                logging.info(f"STATUS: EXITOSO. Datos acumulados a CSVs.")
                
            except Exception as e:
                estado_tabla = _obtener_estado_tabla(checkpoint, nombre_tabla)
                estado_tabla["status"] = "failed"
                _guardar_checkpoint(checkpoint)
                logging.error(f"ERROR en tabla {nombre_tabla}: {str(e)}")

        logging.info(f"RESUMEN FINAL: Pipeline completado en {round((time.time()-inicio_proceso)/60, 2)} min.")
        logging.info("="*60)

    except Exception as e:
        # Error no controlado que rompe el flujo global (ej. fallo de configuración)
        logging.error(f"FALLO CRÍTICO EN EL FLUJO: {str(e)}")
    finally:
        # Garantiza el cierre de la conexión Oracle sin importar si hubo error
        reader.close()

if __name__ == "__main__":
    ejecutar_inventario_completo()