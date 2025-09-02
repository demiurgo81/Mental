import tkinter as tk
from tkinter import simpledialog, filedialog
from pymongo import MongoClient
import os

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
        if new_title:
            # Crear ventana emergente para seleccionar un archivo
            file_path = filedialog.askopenfilename(filetypes=[("Python files", "*.py")])
            if file_path:
                with open(file_path, "r") as file:
                    new_script = file.read()
                    new_path = os.path.abspath(file_path)

                # Actualizar el documento en la colección
                collection.update_one({"_id": doc_id}, {"$set": {"titulo": new_title, "path": new_path, "script": new_script}})
                print(f"Documento actualizado: {new_title}")
                update_window()  # Actualizar la ventana
            else:
                print("Selección de archivo cancelada.")
        else:
            print("Edición cancelada o título vacío.")

def insert_document():
    # Crear ventana emergente para insertar un nuevo documento
    insert_window = tk.Toplevel(root)
    insert_window.grab_set()  # Mantener la ventana emergente en primer plano
    insert_window.title("Insertar documento")
    new_title = simpledialog.askstring("Crear script chingón", "Título:", parent=insert_window)
    if new_title:
        # Insertar el nuevo documento en la colección
        collection.insert_one({"titulo": new_title})
        print(f"Nuevo documento insertado: {new_title}")
        update_window()  # Actualizar la ventana
    else:
        print("Inserción cancelada o título vacío.")

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
