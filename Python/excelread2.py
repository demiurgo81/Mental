import tabula
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
            # Mostrar las tablas encontradas en una ventana emergente
            for i, df in enumerate(df_list):
                if messagebox.askyesno("Tabla encontrada", f"¿Deseas guardar la tabla {i+1} como JSON?"):
                    # Convertir la tabla a formato JSON
                    json_data = df.to_json(orient="records")
                    
                    # Crear un archivo JSON en la misma carpeta que el archivo PDF
                    base_path, _ = os.path.splitext(pdf_file)
                    json_file = f"{base_path}_tabla{i+1}.json"
                    
                    with open(json_file, "w") as f:
                        f.write(json_data)
                    
                    messagebox.showinfo("Info", f"Tabla {i+1} guardada como {json_file}")
    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un error al procesar el archivo PDF:\n{str(e)}")

if __name__ == "__main__":
    main()
