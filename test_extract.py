import yaml
import logging
from extract.oracle_reader import OracleReader

# Configuracion de logs para el test
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def ejecutar_test_100_tablas():
    reader = OracleReader()
    
    # 1. Cargar la configuracion desde el YAML
    try:
        with open('config/tablas.yaml', 'r', encoding='utf-8') as f:
            config_maestra = yaml.safe_load(f)
        
        esquema = config_maestra.get('esquema_origen', 'SPE')
        todas_las_tablas = list(config_maestra.get('tablas', {}).keys())
        
        # Tomar solo las primeras 100
        muestra_tablas = todas_las_tablas[:100]
        logging.info(f"Iniciando test masivo: Procesando {len(muestra_tablas)} tablas del esquema {esquema}.")
        
    except Exception as e:
        logging.error(f"Error al cargar tablas.yaml: {e}")
        return

    # 2. Iterar y extraer
    procesadas = 0
    errores = 0

    for nombre_tabla in muestra_tablas:
        try:
            logging.info(f"--- Procesando [{procesadas + 1}/100]: {nombre_tabla} ---")
            
            # Extraemos los datos (usando el metodo universal de ROWNUM)
            df = reader.extract_table_paginated(esquema, nombre_tabla)
            
            if not df.empty:
                logging.info(f"Exito: {len(df)} filas recuperadas de {nombre_tabla}.")
            
            procesadas += 1
        except Exception as e:
            logging.error(f"Fallo en tabla {nombre_tabla}: {e}")
            errores += 1
            continue

    # 3. Reporte final del Test
    tablas_vacias = reader.get_reporte_vacias()
    
    print("\n" + "="*50)
    print("RESUMEN DEL TEST DE 100 TABLAS")
    print("="*50)
    print(f"Tablas intentadas: {len(muestra_tablas)}")
    print(f"Tablas procesadas con exito: {procesadas}")
    print(f"Tablas con errores: {errores}")
    print(f"Tablas vacias detectadas: {len(tablas_vacias)}")
    print("-"*50)
    print("Listado de tablas vacias encontradas:")
    for v in tablas_vacias:
        print(f" - {v}")
    print("="*50 + "\n")

    reader.close()

if __name__ == "__main__":
    ejecutar_test_100_tablas()