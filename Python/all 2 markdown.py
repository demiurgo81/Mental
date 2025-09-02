import os
import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import shutil
import zipfile

# Función para verificar si el archivo es compatible
def is_supported_file(file_path):
    supported_extensions = {
        ".pdf", ".pptx", ".docx", ".xlsx", ".html", ".csv", ".json", ".xml", ".zip"
    }
    _, ext = os.path.splitext(file_path)
    return ext.lower() in supported_extensions

# Función para procesar archivos ZIP
def process_zip(file_path, output_dir):
    with zipfile.ZipFile(file_path, 'r') as zip_ref:
        zip_ref.extractall(output_dir)
    return output_dir

# Función principal para convertir el archivo a Markdown
def convert_to_markdown(input_file, output_dir):
    try:
        # Verificar si el archivo es compatible
        if not is_supported_file(input_file):
            raise ValueError("El archivo seleccionado no es compatible.")

        # Crear un directorio temporal para procesar el archivo
        temp_dir = os.path.join(os.getcwd(), "temp_markitdown")
        os.makedirs(temp_dir, exist_ok=True)

        # Procesar archivos ZIP
        if input_file.endswith(".zip"):
            input_file = process_zip(input_file, temp_dir)

        # Construir el nombre del archivo de salida
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(output_dir, f"{base_name}.md")

        # Asegurarse de que las rutas estén entrecomilladas para manejar espacios
        input_file_quoted = f'"{input_file}"'
        output_file_quoted = f'"{output_file}"'

        # Usar markitdown para la conversión
        command = f"markitdown {input_file_quoted} -o {output_file_quoted}"
        print(f"Ejecutando comando: {command}")  # Depuración: muestra el comando en la consola
        subprocess.run(command, shell=True, check=True)

        messagebox.showinfo("Éxito", "La conversión a Markdown se realizó correctamente.")
    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un error durante la conversión: {str(e)}")
    finally:
        # Limpiar el directorio temporal
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

# Función para abrir el diálogo de selección de archivo
def select_file():
    file_path = filedialog.askopenfilename(
        title="Seleccionar archivo",
        filetypes=(
            ("Archivos compatibles", "*.pdf *.pptx *.docx *.xlsx *.html *.csv *.json *.xml *.zip"),
            ("Todos los archivos", "*.*")
        )
    )
    if file_path:
        input_file.set(file_path)

# Función para abrir el diálogo de selección de carpeta de salida
def select_output_dir():
    output_dir = filedialog.askdirectory(title="Seleccionar carpeta de salida")
    if output_dir:
        output_directory.set(output_dir)

# Función para iniciar la conversión
def start_conversion():
    input_path = input_file.get()
    output_path = output_directory.get()

    if not input_path:
        messagebox.showwarning("Advertencia", "Por favor, selecciona un archivo de entrada.")
        return

    if not output_path:
        messagebox.showwarning("Advertencia", "Por favor, selecciona una carpeta de salida.")
        return

    convert_to_markdown(input_path, output_path)

# Configuración de la interfaz gráfica
root = tk.Tk()
root.title("Convertidor a Markdown")

# Variables para almacenar las rutas
input_file = tk.StringVar()
output_directory = tk.StringVar()

# Etiquetas y botones
tk.Label(root, text="Archivo de entrada:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
tk.Entry(root, textvariable=input_file, width=50).grid(row=0, column=1, padx=10, pady=5)
tk.Button(root, text="Seleccionar archivo", command=select_file).grid(row=0, column=2, padx=10, pady=5)

tk.Label(root, text="Carpeta de salida:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
tk.Entry(root, textvariable=output_directory, width=50).grid(row=1, column=1, padx=10, pady=5)
tk.Button(root, text="Seleccionar carpeta", command=select_output_dir).grid(row=1, column=2, padx=10, pady=5)

tk.Button(root, text="Convertir a Markdown", command=start_conversion).grid(row=2, column=1, pady=20)

# Ejecutar la interfaz gráfica
root.mainloop()