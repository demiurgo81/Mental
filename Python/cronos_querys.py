import cx_Oracle
import pandas as pd
import os
import logging
from pymongo import MongoClient
from datetime import datetime

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('execution_trace.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Conexión a MongoDB (Versión Final Corregida)
def connect_mongodb():
    try:
        logger.info("Iniciando conexión a MongoDB Atlas...")
        
        # Configuración de conexión
        atlas_uri = "mongodb+srv://demiurgo:requiem@demiurgo.oqf9p2y.mongodb.net/"
        client = MongoClient(
            atlas_uri,
            appname="Cronos_Processor",
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=10000
        )
        
        # Verificación de conexión activa
        client.admin.command('ping')
        logger.info("Conexión a MongoDB establecida correctamente")
        
        # Validación de base de datos y colección
        if "Cronos_AUX" not in client.list_database_names():
            raise ValueError("Base de datos 'Cronos_AUX' no encontrada")
            
        db = client["Cronos_AUX"]
        
        if "Cronos_Querys" not in db.list_collection_names():
            raise ValueError("Colección 'Cronos_Querys' no existe")
        
        return db["Cronos_Querys"]
        
    except Exception as e:
        logger.error(f"Fallo en conexión MongoDB: {str(e)}")
        return None

# Conexión a Oracle (Versión Final)
def connect_oracle():
    try:
        logger.info("Estableciendo conexión Oracle...")
        
        dsn = cx_Oracle.makedsn(
            "100.126.98.25", 
            1850, 
            service_name="PDB_IVRCONV"
        )
        
        connection = cx_Oracle.connect(
            user="PDB_CRONUS",
            password="C7ar0_2o2s",
            dsn=dsn,
            encoding="UTF-8"
        )
        
        logger.info("Conexión Oracle validada")
        return connection
        
    except Exception as e:
        logger.error(f"Error en conexión Oracle: {str(e)}")
        return None

# Procesamiento principal (Versión Final Funcional)
def main_process():
    mongo_collection = None
    oracle_conn = None
    
    try:
        logger.info("\n" + "="*50)
        logger.info(" INICIO DE EJECUCIÓN ".center(50))
        logger.info("="*50 + "\n")
        
        # Paso 1: Conexión MongoDB
        mongo_collection = connect_mongodb()
        if mongo_collection is None:  # Corrección clave aquí
            raise RuntimeError("Conexión MongoDB no disponible")
        
        # Paso 2: Obtener consultas
        logger.info("Buscando consultas en MongoDB...")
        queries = list(mongo_collection.find({}))
        
        if not queries:
            logger.warning("No se encontraron documentos en la colección")
            return False
            
        logger.info(f"Encontradas {len(queries)} consultas a procesar")
        
        # Paso 3: Conexión Oracle
        oracle_conn = connect_oracle()
        if oracle_conn is None:
            raise RuntimeError("Conexión Oracle no disponible")
        
        # Paso 4: Procesar cada consulta
        for idx, query_doc in enumerate(queries, 1):
            try:
                logger.info("\n" + f" Procesando consulta {idx}/{len(queries)} ".center(50, "-"))
                
                # Validación de campos
                required_fields = {'query', 'path', 'csv'}
                missing_fields = required_fields - query_doc.keys()
                if missing_fields:
                    logger.error(f"Documento {idx} incompleto. Campos faltantes: {', '.join(missing_fields)}")
                    continue
                
                query = query_doc['query']
                output_dir = query_doc['path']
                filename = query_doc['csv']
                
                # Paso 5: Ejecutar consulta Oracle
                logger.info(f"Ejecutando consulta:\n{query[:200]}...")
                df = pd.read_sql(query, oracle_conn)
                
                if df.empty:
                    logger.warning("Consulta no devolvió resultados")
                    continue
                    
                # Paso 6: Generar archivo CSV
                full_path = os.path.join(output_dir, filename)
                os.makedirs(output_dir, exist_ok=True)
                
                df.to_csv(
                    full_path,
                    sep=';',
                    index=False,
                    encoding='utf-8-sig',
                    date_format='%Y-%m-%d'
                )
                
                logger.info(f"Archivo generado exitosamente: {full_path}")
                logger.info(f"Registros exportados: {len(df)}")
                
            except Exception as e:
                logger.error(f"Error procesando consulta {idx}: {str(e)}")
                continue
                
        return True
        
    except Exception as e:
        logger.error(f"Error crítico en proceso principal: {str(e)}")
        return False
    finally:
        # Cierre seguro de conexiones
        if oracle_conn:
            try:
                oracle_conn.close()
                logger.info("Conexión Oracle cerrada correctamente")
            except Exception as e:
                logger.error(f"Error cerrando Oracle: {str(e)}")
        
        logger.info("\n" + "="*50)
        logger.info(" EJECUCIÓN FINALIZADA ".center(50))
        logger.info("="*50)

# Punto de entrada
if __name__ == "__main__":
    start_time = datetime.now()
    success = main_process()
    duration = datetime.now() - start_time
    
    logger.info(f"\nTiempo total de ejecución: {duration}")
    logger.info(f"Estado final: {'ÉXITO' if success else 'FALLO'}")