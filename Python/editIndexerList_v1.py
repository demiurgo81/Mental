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
        edit_window = tk.Toplevel(root)
        edit_window.grab_set()  # Mantener la ventana emergente en primer plano
        edit_window.title("Editar documento")
        new_title = simpledialog.askstring("Editar título", "Nuevo título:", initialvalue=doc["titulo"], parent=edit_window)
        new_path = simpledialog.askstring("Editar path", "Nuevo path:", initialvalue=doc["path"], parent=edit_window)
        new_script = simpledialog.askstring("Editar script", "Nuevo script:", initialvalue=doc["script"], parent=edit_window)

        if new_title and new_path and new_script:
            # Actualizar el documento en la colección
            collection.update_one({"_id": doc_id}, {"$set": {"titulo": new_title, "path": new_path, "script": new_script}})
            print(f"Documento actualizado: {new_title}")
            update_window()  # Actualizar la ventana
        else:
            print("Edición cancelada o campos vacíos.")

def insert_document():
    # Crear ventana emergente para insertar un nuevo documento
    insert_window = tk.Toplevel(root)
    insert_window.grab_set()  # Mantener la ventana emergente en primer plano
    insert_window.title("Insertar documento")
    new_title = simpledialog.askstring("Crear script chingón", "Título:", parent=insert_window)
    new_path = simpledialog.askstring("Crear script chingón", "Path:", parent=insert_window)
    new_script = simpledialog.askstring("Crear script chingón", "Script:", parent=insert_window)

    if new_title and new_path and new_script:
        # Insertar el nuevo documento en la colección
        collection.insert_one({"titulo": new_title, "path": new_path, "script": new_script})
        print(f"Nuevo documento insertado: {new_title}")
        update_window()  # Actualizar la ventana
    else:
        print("Inserción cancelada o campos vacíos.")

def update_window():
    # Actualizar la ventana con los títulos y _ids de la colección
    for widget in root.winfo_children():
        widget.destroy()

    titles_and_ids = [(doc["titulo"], doc["_id"]) for doc in collection.find()]
    for i, (title, doc_id) in enumerate(titles_and_ids):
        tk.Label(root, text=title).grid(row=i, column=0)
        tk.Button(root, text="Editar", command=lambda d=doc_id: edit_document(d)).grid(row=i, column=1)

    tk.Button(root, text="Insertar", command=insert_document).grid(row=len(titles_and_ids), column=0, columnspan=2)

# Crear ventana principal con Tkinter
root = tk.Tk()
root.title("Scripts Chingones")

# Centrar la ventana en la pantalla
root.update_idletasks()
width = root.winfo_width()
height = root.winfo_height()
x = root.winfo_screenwidth() // 2 - width // 2
y = root.winfo_screenheight() // 2 - height // 2
root.geometry('{}x{}+{}+{}'.format(width, height, x, y))

# Obtener títulos y _ids de la colección
update_window()

root.mainloop()