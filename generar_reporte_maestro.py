import pandas as pd
import os
import logging
from pathlib import Path

from config.settings import DATA_OUTPUT_DIR

# Configuración de rutas
RUTA_RESULTADOS = DATA_OUTPUT_DIR
ARCHIVO_MAESTRO = RUTA_RESULTADOS / "REPORTE_MAESTRO_MIGRACION_SPE.xlsx"

def consolidar_inventario():
    # Asegurar que la ruta existe
    if not RUTA_RESULTADOS.exists():
        print(f"Error: La ruta {RUTA_RESULTADOS} no existe.")
        return

    lista_analisis = []
    lista_columnas = []
    
    # Filtrar solo archivos .xlsx reales y omitir archivos temporales (~$)
    archivos = [f for f in os.listdir(RUTA_RESULTADOS) 
                if f.startswith("INVENTARIO_") 
                and f.endswith(".xlsx") 
                and not f.startswith("~$")]
    
    print(f"Detectados {len(archivos)} archivos. Iniciando consolidación...")

    for nombre_archivo in archivos:
        ruta_full = RUTA_RESULTADOS / nombre_archivo
        
        try:
            # Leer Pestaña de Análisis Técnico
            with pd.ExcelFile(ruta_full) as xls:
                # 1. Procesar Resumen Técnico
                df_resumen = pd.read_excel(xls, sheet_name='ANALISIS_TECNICO')
                lista_analisis.append(df_resumen)
                
                # 2. Procesar Detalle de Columnas para el Diccionario
                df_cols = pd.read_excel(xls, sheet_name='DETALLE_COLUMNAS')
                # Solo tomamos lo necesario para el mapeo
                df_mapeo = df_cols[['TIPO_ORACLE_PANDAS', 'SUGERENCIA_POSTGRES', 'SUGERENCIA_MONGODB']].copy()
                lista_columnas.append(df_mapeo)
                
            print(f" OK: {nombre_archivo}")

        except Exception as e:
            print(f" ERROR en {nombre_archivo}: El archivo podría estar corrupto o abierto. Saltando...")
            continue

    if not lista_analisis:
        print("No se pudo procesar ningún archivo válido.")
        return

    # 3. Crear el DataFrame Maestro de Tablas
    df_maestro_tablas = pd.concat(lista_analisis, ignore_index=True)

    # 4. Crear el Diccionario Maestro de Tipos (Valores únicos y limpios)
    df_maestro_tipos = pd.concat(lista_columnas, ignore_index=True)
    df_maestro_tipos = df_maestro_tipos.drop_duplicates().sort_values(by='TIPO_ORACLE_PANDAS')

    # 5. Guardar el Gran Maestro
    try:
        with pd.ExcelWriter(ARCHIVO_MAESTRO, engine='openpyxl') as writer:
            df_maestro_tablas.to_excel(writer, sheet_name='INVENTARIO_GENERAL', index=False)
            df_maestro_tipos.to_excel(writer, sheet_name='DICCIONARIO_TIPOS_DATOS', index=False)
        print(f"\n EXCEL MAESTRO GENERADO: {ARCHIVO_MAESTRO}")
    except PermissionError:
        print(f"\n ERROR: No se pudo guardar. Cierra el archivo '{ARCHIVO_MAESTRO}' si lo tienes abierto.")

if __name__ == "__main__":
    consolidar_inventario()