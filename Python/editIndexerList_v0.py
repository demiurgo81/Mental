import tkinter as tk
from tkinter import simpledialog
from pymongo import MongoClient

# Conexión a MongoDB Atlas
atlas_connection_string = "mongodb+srv://demiurgo:requiem@demiurgo.oqf9p2y.mongodb.net/?retryWrites=true&w=majority&appName=demiurgo"
client = MongoClient(atlas_connection_string)
db = client["financierosJP"]
collection = db["pyCodesIndex"]

def edit_document(doc_id):
    # Obtener el documento por su _id
    doc = collection.find_one({"_id": doc_id})
    if doc:
        # Crear ventana emergente para editar el documento
        new_title = simpledialog.askstring("Editar título", "Nuevo título:", initialvalue=doc["titulo"])
        new_path = simpledialog.askstring("Editar path", "Nuevo path:", initialvalue=doc["path"])
        new_script = simpledialog.askstring("Editar script", "Nuevo script:", initialvalue=doc["script"])

        if new_title and new_path and new_script:
            # Actualizar el documento en la colección
            collection.update_one({"_id": doc_id}, {"$set": {"titulo": new_title, "path": new_path, "script": new_script}})
            print(f"Documento actualizado: {new_title}")
        else:
            print("Edición cancelada o campos vacíos.")

def insert_document():
    # Crear ventana emergente para insertar un nuevo documento
    new_title = simpledialog.askstring("Crear script chingón", "Título:")
    new_path = simpledialog.askstring("Crear script chingón", "Path:")
    new_script = simpledialog.askstring("Crear script chingón", "Script:")

    if new_title and new_path and new_script:
        # Insertar el nuevo documento en la colección
        collection.insert_one({"titulo": new_title, "path": new_path, "script": new_script})
        print(f"Nuevo documento insertado: {new_title}")
    else:
        print("Inserción cancelada o campos vacíos.")

# Crear ventana principal con Tkinter
root = tk.Tk()
root.title("Scripts Chingones")

# Obtener títulos y _ids de la colección
titles_and_ids = [(doc["titulo"], doc["_id"]) for doc in collection.find()]

# Crear etiquetas para los títulos y botones para editar
for i, (title, doc_id) in enumerate(titles_and_ids):
    tk.Label(root, text=title).grid(row=i, column=0)
    tk.Button(root, text="Editar", command=lambda d=doc_id: edit_document(d)).grid(row=i, column=1)

# Botón para insertar nuevo documento
tk.Button(root, text="Insertar", command=insert_document).grid(row=len(titles_and_ids), column=0, columnspan=2)

root.mainloop()
