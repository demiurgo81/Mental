import tabula
import pandas as pd
import os
import tkinter as tk
from tkinter import filedialog
import logging

# Configura el logging para suprimir warnings de PDFBox
logging.getLogger("org.apache.pdfbox").setLevel(logging.ERROR)

# Crea una ventana emergente para seleccionar el archivo PDF
root = tk.Tk()
root.withdraw()  # Oculta la ventana principal

pdf_path = filedialog.askopenfilename(title="Selecciona un archivo PDF")

# Extrae todas las tablas del archivo PDF
df_list = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True)

# Encuentra el número máximo de columnas en las tablas extraídas
max_cols = max([df.shape[1] for df in df_list])

# Renombra las columnas de todas las tablas a encabezados genéricos y unifícalas
col_names = [f"col_{i+1}" for i in range(max_cols)]
df_unificado = pd.DataFrame(columns=col_names)

for df in df_list:
    df.columns = col_names[:df.shape[1]]  # Ajusta los nombres de las columnas según el número de columnas en df
    df_unificado = pd.concat([df_unificado, df], ignore_index=True)

# Crea un archivo Excel con el mismo nombre y ubicación que el PDF
output_excel_path = os.path.splitext(pdf_path)[0] + ".xlsx"

# Guarda cada tabla en una hoja del archivo Excel y la tabla unificada en una hoja "punion"
with pd.ExcelWriter(output_excel_path) as writer:
    for i, df in enumerate(df_list):
        sheet_name = f"Tabla_{i + 1}"
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    df_unificado.to_excel(writer, sheet_name="punion", index=False)

print(f"Las tablas se han guardado en {output_excel_path}")
