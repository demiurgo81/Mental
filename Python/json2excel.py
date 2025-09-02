import pandas as pd
from tkinter import Tk
from tkinter.filedialog import askopenfilename, asksaveasfilename
import os

# Solicitar al usuario seleccionar un archivo JSON
Tk().withdraw()  # Ocultar la ventana principal de Tkinter
json_file = askopenfilename(filetypes=[("JSON files", "*.json")])

try:
    # Leer el contenido del archivo JSON
    df = pd.read_json(json_file)

    # Crear un archivo Excel con el mismo nombre y ubicación
    base_path, _ = os.path.splitext(json_file)
    excel_file = f"{base_path}.xlsx"
    df.to_excel(excel_file, index=False)

    print(f"Archivo Excel guardado como {excel_file}")
except Exception as e:
    print(f"Error al procesar el archivo JSON: {str(e)}")
