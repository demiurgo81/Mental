import tkinter as tk
import subprocess
from pymongo import MongoClient

# Conexión a MongoDB Atlas
atlas_connection_string = "mongodb+srv://demiurgo:requiem@demiurgo.oqf9p2y.mongodb.net/?retryWrites=true&w=majority&appName=demiurgo"
client = MongoClient(atlas_connection_string)
db = client["financierosJP"]
collection = db["pyCodesIndex"]

# Crear ventana emergente con Tkinter
root = tk.Tk()
root.title("Títulos de pyCodesIndex")

# Función para ejecutar el código Python
def execute_code(path):
    try:
        # Ejecutar el código Python
        result = subprocess.run(["python", path], capture_output=True, text=True)
        output = result.stdout
        if result.returncode == 0:
            print(f"Ejecución exitosa:\n{output}")
        else:
            print(f"Error al ejecutar el código:\n{output}")
    except Exception as e:
        print(f"Error: {e}")

# Función para cargar y mostrar los datos
def load_data():
    for widget in root.winfo_children():
        widget.destroy()
    
    titles_and_paths = [(doc["titulo"], doc["path"]) for doc in collection.find().sort("titulo", 1)]
    
    # Crear etiquetas para los títulos y botones para ejecutar el código
    for i, (title, path) in enumerate(titles_and_paths):
        tk.Label(root, text=title).grid(row=i, column=0, sticky="w")
        tk.Button(root, text="Ejecutar", command=lambda p=path: execute_code(p)).grid(row=i, column=1, sticky="w")

    # Botón de refrescar
    refresh_button = tk.Button(root, text="Refrescar", command=load_data)
    refresh_button.grid(row=len(titles_and_paths), column=0, columnspan=2)

# Inicializar la carga de datos
load_data()

# Ajustar el tamaño de la ventana
root.geometry("600x400")

root.mainloop()

