import pandas as pd
import os
import logging
from pathlib import Path
from config.settings import DATA_OUTPUT_DIR

# Configuración de rutas
RUTA_RESULTADOS = DATA_OUTPUT_DIR
ARCHIVO_MAESTRO = RUTA_RESULTADOS / "REPORTE_MAESTRO_MIGRACION_SPE.xlsx"

def consolidar_inventario(tablas_vacias, tablas_masivas, tablas_pocos_registros, detalle_constraints):
    """
    Consolida todos los hallazgos del pipeline en un único Reporte Maestro.
    """
    if not RUTA_RESULTADOS.exists():
        logging.error(f"La ruta {RUTA_RESULTADOS} no existe.")
        return

    lista_analisis = []
    lista_columnas = []
    
    # 1. Procesar archivos generados (Inventarios individuales)
    archivos = [f for f in os.listdir(RUTA_RESULTADOS) 
                if f.startswith("INVENTARIO_") 
                and f.endswith(".xlsx") 
                and not f.startswith("~$")]
    
    logging.info(f"Consolidando {len(archivos)} archivos de inventario...")

    for nombre_archivo in archivos:
        ruta_full = RUTA_RESULTADOS / nombre_archivo
        try:
            with pd.ExcelFile(ruta_full) as xls:
                # Resumen de calidad y peso
                if 'ANALISIS_TECNICO' in xls.sheet_names:
                    df_res = pd.read_excel(xls, sheet_name='ANALISIS_TECNICO')
                    lista_analisis.append(df_res)
                
                # Mapeo de tipos de datos (Lectura profunda)
                if 'DETALLE_COLUMNAS' in xls.sheet_names:
                    df_cols = pd.read_excel(xls, sheet_name='DETALLE_COLUMNAS')
                    # Capturamos todas las columnas de tipos para el catálogo maestro
                    df_mapeo = df_cols[['TIPO_ORACLE_PANDAS', 'SUGERENCIA_POSTGRES', 'SUGERENCIA_MONGODB']].copy()
                    lista_columnas.append(df_mapeo)
        except Exception as e:
            logging.error(f"Error procesando {nombre_archivo}: {e}")

    # 2. Preparar DataFrames de los Objetos Recolectados
    df_vacias = pd.DataFrame(tablas_vacias) if tablas_vacias else pd.DataFrame(columns=['nombre', 'registros'])
    df_masivas = pd.DataFrame(tablas_masivas) if tablas_masivas else pd.DataFrame(columns=['nombre', 'registros'])
    df_pocos = pd.DataFrame(tablas_pocos_registros) if tablas_pocos_registros else pd.DataFrame(columns=['nombre', 'registros'])
    
    # 3. Procesar Detalle de Constraints
    df_constraints = pd.DataFrame(detalle_constraints) if detalle_constraints else pd.DataFrame()
    
    # Tabla adicional: Totales de integridad
    resumen_constraints = []
    if not df_constraints.empty:
        resumen_constraints = [{
            'TIPO_RESTRICCION': 'PRIMARY KEY (PK)',
            'TOTAL_ENCONTRADAS': len(df_constraints[df_constraints['PK'] != 'N/A']),
            'DESCRIPCION': 'Identificadores únicos de tabla'
        }, {
            'TIPO_RESTRICCION': 'FOREIGN KEY (FK)',
            'TOTAL_ENCONTRADAS': len(df_constraints[df_constraints['FK'] != 'N/A']),
            'DESCRIPCION': 'Relaciones de integridad referencial'
        }, {
            'TIPO_RESTRICCION': 'UNIQUE',
            'TOTAL_ENCONTRADAS': len(df_constraints[df_constraints['UNIQUE'] != 'N/A']),
            'DESCRIPCION': 'Restricciones de unicidad'
        }, {
            'TIPO_RESTRICCION': 'CHECK',
            'TOTAL_ENCONTRADAS': len(df_constraints[df_constraints['CHECK'] != 'N/A']),
            'DESCRIPCION': 'Validaciones de dominio de datos'
        }]
    df_resumen_const = pd.DataFrame(resumen_constraints)

    # 4. Consolidar Catálogo de Tipos (Deduplicado)
    if lista_columnas:
        df_maestro_tipos = pd.concat(lista_columnas, ignore_index=True)
        df_maestro_tipos = df_maestro_tipos.drop_duplicates().sort_values(by='TIPO_ORACLE_PANDAS')
    else:
        df_maestro_tipos = pd.DataFrame(columns=['TIPO_ORACLE_PANDAS', 'SUGERENCIA_POSTGRES', 'SUGERENCIA_MONGODB'])

    # 5. Escritura del Reporte Maestro Final
    try:
        with pd.ExcelWriter(ARCHIVO_MAESTRO, engine='openpyxl') as writer:
            # Pestaña Principal
            if lista_analisis:
                pd.concat(lista_analisis, ignore_index=True).to_excel(writer, sheet_name='INVENTARIO_GENERAL', index=False)
            
            # Pestaña de Tipos
            df_maestro_tipos.to_excel(writer, sheet_name='CATALOGO_TIPOS_DATOS', index=False)
            
            # Pestañas de Constraints (Solicitadas)
            if not df_constraints.empty:
                df_constraints.to_excel(writer, sheet_name='DETALLE_CONSTRAINTS', index=False)
                df_resumen_const.to_excel(writer, sheet_name='RESUMEN_INTEGRIDAD', index=False)
            
            # Pestañas de Hallazgos Especiales
            df_vacias.to_excel(writer, sheet_name='TABLAS_VACIAS', index=False)
            df_masivas.to_excel(writer, sheet_name='TABLAS_MASIVAS', index=False)
            df_pocos.to_excel(writer, sheet_name='TABLAS_POCOS_REGISTROS', index=False)

        logging.info(f"REPORTE MAESTRO GENERADO EXITOSAMENTE: {ARCHIVO_MAESTRO.name}")
    except Exception as e:
        logging.error(f"Error al guardar el Reporte Maestro: {e}")