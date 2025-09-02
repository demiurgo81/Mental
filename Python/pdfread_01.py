import tabula
import pandas as pd
import tkinter as tk
from tkinter import messagebox
from tkinter.filedialog import askopenfilename
import json
import os

def guardar_tablas_en_json(df_list, json_file):
    # Convertir todas las tablas a formato JSON
    json_data = [df.to_dict(orient="records") for df in df_list]
    
    # Guardar todas las tablas en un único archivo JSON
    with open(json_file, "w") as f:
        json.dump(json_data, f, indent=2)

def mostrar_muestra_tabla(df):
    # Mostrar los primeros 5 registros y las 6 primeras columnas
    muestra = df.iloc[:5, :6]
    return muestra

def seleccionar_tablas(df_list):
    # Crear una ventana emergente para que el usuario seleccione las tablas
    root = tk.Tk()
    root.withdraw()  # Ocultar la ventana principal
    
    tablas_seleccionadas = []
    for i, df in enumerate(df_list):
        muestra = mostrar_muestra_tabla(df)
        guardar = messagebox.askyesno(f"Tabla {i+1}", f"¿Deseas guardar la tabla {i+1}?\n\n{muestra.to_string(index=False)}")
        if guardar:
            tablas_seleccionadas.append(df)
    
    return tablas_seleccionadas

def main():
    # Solicitar al usuario que seleccione un archivo PDF
    pdf_file = askopenfilename(filetypes=[("PDF files", "*.pdf")])
    
    try:
        # Extraer las tablas del archivo PDF
        df_list = tabula.read_pdf(pdf_file, pages="all", multiple_tables=True)
        
        if not df_list:
            messagebox.showinfo("Info", "No se encontraron tablas en el archivo PDF.")
        else:
            tablas_seleccionadas = seleccionar_tablas(df_list)
            if tablas_seleccionadas:
                # Crear un archivo JSON en la misma carpeta que el archivo PDF
                base_path, _ = os.path.splitext(pdf_file)
                json_file = f"{base_path}_tablas.json"
                guardar_tablas_en_json(tablas_seleccionadas, json_file)
                print(f"Tablas seleccionadas guardadas en {json_file}\n")
            else:
                print("No se seleccionaron tablas para guardar.\n")
    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un error al procesar el archivo PDF:\n{str(e)}")

if __name__ == "__main__":
    main()
