import tabula
import pandas as pd
import tkinter as tk
from tkinter import messagebox
from tkinter.filedialog import askopenfilename
import json
import os

def main():
    # Solicitar al usuario que seleccione un archivo PDF
    pdf_file = askopenfilename(filetypes=[("PDF files", "*.pdf")])
    
    try:
        # Extraer las tablas del archivo PDF
        df_list = tabula.read_pdf(pdf_file, pages="all", multiple_tables=True)
        
        if not df_list:
            messagebox.showinfo("Info", "No se encontraron tablas en el archivo PDF.")
        else:
            # Mostrar las tablas encontradas y preguntar al usuario si desea guardarlas
            for i, df in enumerate(df_list):
                print(f"Tabla {i+1}:\n{df}\n")
                guardar = input("¿Deseas guardar esta tabla? (s/n): ")
                if guardar.lower() == "s":
                    # Convertir la tabla a formato JSON
                    json_data = df.to_json(orient="records")
                    
                    # Crear un archivo JSON en la misma carpeta que el archivo PDF
                    base_path, _ = os.path.splitext(pdf_file)
                    json_file = f"{base_path}_tabla{i+1}.json"
                    
                    with open(json_file, "w") as f:
                        f.write(json_data)
                    
                    print(f"Tabla {i+1} guardada como {json_file}\n")
    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un error al procesar el archivo PDF:\n{str(e)}")

if __name__ == "__main__":
    main()nonlocal