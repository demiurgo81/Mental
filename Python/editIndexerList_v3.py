import tkinter as tk
from tkinter import simpledialog, filedialog, messagebox
from pymongo import MongoClient
import os

# Conexión a MongoDB Atlas
atlas_connection_string = "mongodb+srv://demiurgo:requiem@demiurgo.oqf9p2y.mongodb.net/?retryWrites=true&w=majority&appName=demiurgo"
client = MongoClient(atlas_connection_string)
db = client["financierosJP"]
collection = db["pyCodesIndex"]

def edit_document(doc_id):
    doc = collection.find_one({"_id": doc_id})
    if doc:
        edit_window = tk.Toplevel(root)
        edit_window.grab_set()
        edit_window.title("Editar documento")
        new_title = simpledialog.askstring("Editar título", "Nuevo título:", initialvalue=doc["titulo"], parent=edit_window)
        if new_title:
            file_path = filedialog.askopenfilename(filetypes=[("Python files", "*.py")])
            if file_path:
                with open(file_path, "r") as file:
                    new_script = file.read()
                    new_path = os.path.abspath(file_path)

                collection.update_one({"_id": doc["_id"]}, {"$set": {"titulo": new_title, "path": new_path, "script": new_script}})
                print(f"Documento actualizado: {new_title}")
                update_window()
            else:
                print("Selección de archivo cancelada.")
        else:
            print("Edición cancelada o título vacío.")

def insert_document():
    insert_window = tk.Toplevel(root)
    insert_window.grab_set()
    insert_window.title("Insertar documento")
    new_title = simpledialog.askstring("Crear script chingón", "Título:", parent=insert_window)
    if new_title:
        collection.insert_one({"titulo": new_title})
        print(f"Nuevo documento insertado: {new_title}")
        update_window()
    else:
        print("Inserción cancelada o título vacío.")

def update_root_path():
    print("\nEstado inicial de la base de datos:")
    for doc in collection.find():
        print(f"ID: {doc['_id']}")
        print(f"Título: {doc.get('titulo', 'Sin título')}")
        print(f"Path actual: {doc.get('path', 'Sin path')}")
        print("-" * 50)
    
    new_root = filedialog.askdirectory(title="Seleccionar nueva carpeta raíz")
    if not new_root:
        print("Selección de carpeta cancelada")
        return

    try:
        cursor = collection.find({"path": {"$exists": True}})
        documents = list(cursor)
        print(f"\nEncontrados {len(documents)} documentos con campo 'path'")
        
        update_count = 0
        update_details = []

        # Normalizar el nuevo path raíz
        new_root = os.path.normpath(new_root)
        
        for doc in documents:
            old_path = doc.get("path", "")
            if not old_path:
                continue

            print(f"\nProcesando documento:")
            print(f"ID: {doc['_id']}")
            print(f"Título: {doc.get('titulo', 'Sin título')}")
            print(f"Path actual: {old_path}")
            
            # Obtener solo el nombre del archivo
            filename = os.path.basename(old_path)
            
            # Construir nueva ruta
            new_path = os.path.join(new_root, filename)
            new_path = os.path.normpath(new_path)
            print(f"Nueva ruta a establecer: {new_path}")
            
            try:
                result = collection.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"path": new_path}}
                )
                print(f"Resultado de actualización: matched={result.matched_count}, modified={result.modified_count}")
                
                if result.modified_count > 0:
                    update_count += 1
                    update_details.append(f"Documento: {doc.get('titulo', 'Sin título')}\n"
                                       f"Path anterior: {old_path}\n"
                                       f"Nuevo path: {new_path}")
                    print("¡Actualización exitosa!")
                else:
                    print("No se realizó la actualización")
                    
            except Exception as update_error:
                print(f"Error en actualización individual: {str(update_error)}")
                continue

        print("\nEstado final de la base de datos:")
        for doc in collection.find():
            print(f"ID: {doc['_id']}")
            print(f"Título: {doc.get('titulo', 'Sin título')}")
            print(f"Path nuevo: {doc.get('path', 'Sin path')}")
            print("-" * 50)
        
        if update_count > 0:
            messagebox.showinfo(
                "Actualización completada", 
                f"Se actualizaron {update_count} rutas de archivos.\n\n"
                f"Detalles:\n\n" + "\n\n".join(update_details)
            )
        else:
            messagebox.showwarning(
                "Sin actualizaciones", 
                "No se realizaron actualizaciones. Verifica los logs para más detalles."
            )

    except Exception as e:
        print(f"Error general: {str(e)}")
        messagebox.showerror("Error", f"Error al actualizar las rutas: {str(e)}")
        
def update_window():
    for widget in root.winfo_children():
        widget.destroy()

    tk.Button(
        root, 
        text="Actualizar Rutas Raíz", 
        command=update_root_path,
        bg="lightblue",
        pady=5
    ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

    titles_and_ids = [(doc.get("titulo", "Sin título"), doc["_id"], doc.get("path", "Sin ruta")) 
                      for doc in collection.find()]

    for i, (title, doc_id, path) in enumerate(titles_and_ids, start=1):
        tk.Label(root, text=title).grid(row=i, column=0, padx=5, pady=2)
        tk.Button(
            root, 
            text="Editar",
            command=lambda d=doc_id: edit_document(d)
        ).grid(row=i, column=1, padx=5, pady=2)
        
        if path != "Sin ruta":
            tk.Label(
                root, 
                text=path, 
                wraplength=350, 
                justify=tk.LEFT
            ).grid(row=i+1, column=0, columnspan=2, padx=5)

    tk.Button(
        root, 
        text="Insertar", 
        command=insert_document
    ).grid(row=len(titles_and_ids)*2+1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

# Crear ventana principal
root = tk.Tk()
root.title("Scripts Chingones")

# Configurar ventana
width = 400
height = 600
x = root.winfo_screenwidth() // 2 - width // 2
y = root.winfo_screenheight() // 2 - height // 2
root.geometry('{}x{}+{}+{}'.format(width, height, x, y))

# Inicializar
update_window()
root.mainloop()