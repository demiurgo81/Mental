import tkinter as tk
from tkinter import ttk
from pymongo import MongoClient

# Conexión a MongoDB
connection_string = "mongodb://localhost:27017/?directConnection=true"
client = MongoClient(connection_string)
db = client["financialJP"]
collection = db["financialcodesPy"]

# Consulta los documentos de la colección
documents = list(collection.find())

# Crear ventana emergente
root = tk.Tk()
root.title("financialcodesPy")

# Crear tabla
table = ttk.Treeview(root, columns=["titulo", "estado"], show="headings")
table.heading("titulo", text="Título")
table.heading("estado", text="Estado")
table.column("titulo", width=100)
table.column("estado", width=100)

# Insertar datos en la tabla
for doc in documents:
    table.insert("", "end", values=(doc.get("titulo"), doc.get("estado")))

# Botón para insertar un nuevo documento
def insertar_documento():
    # Aquí debes implementar la lógica para insertar un nuevo documento en la colección
    # con los valores actuales del modelo (título y estado).
    pass

boton_insertar = tk.Button(root, text="Insertar nuevo documento", command=insertar_documento)
boton_insertar.pack()

# Mostrar tabla
table.pack()

root.mainloop()
