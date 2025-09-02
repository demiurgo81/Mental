# Importa la biblioteca pymongo
import pymongo

# Configura la cadena de conexión a tu clúster de MongoDB Atlas
uri = "mongodb+srv://demiurgo:requiem@demiurgo.oqf9p2y.mongodb.net/?retryWrites=true&w=majority&appName=demiurgo"

# Crea una conexión al clúster
client = pymongo.MongoClient(uri)

# Selecciona la base de datos y la colección
db = client.financierosJP
collection = db.pyCodesIndex

# Realiza una consulta (por ejemplo, obtén todos los documentos)
results = collection.find()

# Imprime los resultados
for doc in results:
    print(doc)
