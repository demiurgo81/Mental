import tabula
import pandas as pd
import os
import tkinter as tk
from tkinter import filedialog

# Crea una ventana emergente para seleccionar el archivo PDF
root = tk.Tk()
root.withdraw()  # Oculta la ventana principal

pdf_path = filedialog.askopenfilename(title="Selecciona un archivo PDF")

# Extrae todas las tablas del archivo PDF
df_list = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True)

# Crea un archivo Excel con el mismo nombre y ubicación que el PDF
output_excel_path = os.path.splitext(pdf_path)[0] + ".xlsx"

# Guarda cada tabla en una hoja del archivo Excel
with pd.ExcelWriter(output_excel_path) as writer:
    for i, df in enumerate(df_list):
        sheet_name = f"Tabla_{i + 1}"
        df.to_excel(writer, sheet_name=sheet_name, index=False)

print(f"Las tablas se han guardado en {output_excel_path}")
