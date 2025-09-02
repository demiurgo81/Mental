import tkinter as tk
import subprocess
from pymongo import MongoClient
import os
from tkinter import filedialog  # Importación agregada para filedialog

atlas_connection_string = "mongodb+srv://demiurgo:requiem@demiurgo.oqf9p2y.mongodb.net/?retryWrites=true&w=majority&appName=demiurgo"
client = MongoClient(atlas_connection_string)
db = client["financierosJP"]
collection = db["pyCodesIndex"]

root = tk.Tk()
root.title("Títulos de pyCodesIndex")

def execute_code(path):
    try:
        result = subprocess.run(["python", path], capture_output=True, text=True)
        output = result.stdout
        if result.returncode == 0:
            print(f"Ejecución exitosa:\n{output}")
        else:
            print(f"Error al ejecutar el código:\n{output}")
    except Exception as e:
        print(f"Error: {e}")

def load_data():
    for widget in root.winfo_children():
        widget.destroy()

    # Botón "Actualizar Rutas Raíz"
    tk.Button(
        root,
        text="Actualizar Rutas Raíz",
        command=update_root_path,
        bg="lightblue",
        pady=5
    ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

    titles_and_paths = [(doc["titulo"], doc["path"]) for doc in collection.find().sort("titulo", 1)]
    for i, (title, path) in enumerate(titles_and_paths, start=1):
        tk.Label(root, text=title).grid(row=i, column=0, sticky="w")
        tk.Button(root, text="Ejecutar", command=lambda p=path: execute_code(p)).grid(row=i, column=1, sticky="w")

    refresh_button = tk.Button(root, text="Refrescar", command=load_data)
    refresh_button.grid(row=len(titles_and_paths) + 1, column=0, columnspan=2)

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
        new_root = os.path.normpath(new_root)

        for doc in documents:
            old_path = doc.get("path", "")
            if not old_path:
                continue

            print(f"\nProcesando documento:")
            print(f"ID: {doc['_id']}")
            print(f"Título: {doc.get('titulo', 'Sin título')}")
            print(f"Path actual: {old_path}")

            filename = os.path.basename(old_path)
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
            tk.messagebox.showinfo(
                "Actualización completada",
                f"Se actualizaron {update_count} rutas de archivos.\n\n"
                f"Detalles:\n\n" + "\n\n".join(update_details)
            )
        else:
            tk.messagebox.showwarning(
                "Sin actualizaciones",
                "No se realizaron actualizaciones. Verifica los logs para más detalles."
            )
    except Exception as e:
        print(f"Error general: {str(e)}")
        tk.messagebox.showerror("Error", f"Error al actualizar las rutas: {str(e)}")

root.geometry("600x400")
load_data()
root.mainloop()