import tabula
import tkinter as tk
from tkinter import messagebox
from tkinter.filedialog import askopenfilename

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
                messagebox.showinfo(f"Tabla {i+1}", df.to_string(index=False))
    except Exception as e:
        messagebox.showerror("Error", f"Ocurrió un error al procesar el archivo PDF:\n{str(e)}")

if __name__ == "__main__":
    main()