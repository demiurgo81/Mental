import tkinter as tk
from tkinter import filedialog
import tabula
from pymongo import MongoClient

def seleccionar_archivo():
    archivo = filedialog.askopenfilename(filetypes=[("Archivos PDF", "*.pdf")])
    if archivo:
        # Conexión a MongoDB Atlas
        uri = "mongodb+srv://demiurgo:requiem@demiurgo.oqf9p2y.mongodb.net/?retryWrites=true&w=majority"
        client = MongoClient(uri)
        db = client["financierosJP"]

        # Extracción de tablas desde el archivo PDF
        tablas = tabula.read_pdf(archivo, pages="all", multiple_tables=True)

        # Insertar registros en la colección
        for tabla in tablas:
            for fila in tabla.itertuples():
                documento = {
                    "tipo": fila[1],
                    "fecha": fila[2],
                    "descripcion": fila[3],
                    "valor": fila[4],
                    "capital": fila[5],
                    "cuotas": fila[6],
                    "pendiente": fila[7],
                    "tasaMV": fila[8],
                    "tasaEA": fila[9],
                }
                db[archivo].insert_one(documento)

        print("Registros insertados correctamente en la colección.")
    else:
        print("No se seleccionó ningún archivo.")

root = tk.Tk()
root.withdraw()
seleccionar_archivo()
