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

# Asigna un encabezado genérico a todas las tablas
generic_headers = [f"coltabla_{i}" for i in range(1, max(len(df.columns) for df in df_list) + 1)]

# Crea un DataFrame vacío con los encabezados genéricos
empty_df = pd.DataFrame(columns=generic_headers)

# Guarda cada tabla en una hoja del archivo Excel
with pd.ExcelWriter(output_excel_path) as writer:
    for i, df in enumerate(df_list):
        sheet_name = f"Tabla_{i + 1}"
        df.columns = generic_headers[:len(df.columns)]  # Asigna los encabezados genéricos
        empty_df.to_excel(writer, sheet_name=sheet_name, index=False)
        df.to_excel(writer, sheet_name=sheet_name, startrow=1, index=False)

print(f"Las tablas se han guardado en {output_excel_path} con encabezados genéricos.")

# Reemplaza los encabezados existentes con los valores de la primera fila
with pd.ExcelWriter(output_excel_path, mode='a', engine='openpyxl') as writer:
    for sheet_name in writer.sheets:
        if sheet_name.startswith("Tabla_"):
            df = pd.read_excel(writer, sheet_name=sheet_name)
            df.columns = df.iloc[0]  # Usa la primera fila como nuevos encabezados
            df = df[1:]  # Elimina la primera fila (encabezados antiguos)
            df.to_excel(writer, sheet_name=sheet_name, index=False, header=False)

print(f"Se han reemplazado los encabezados existentes en {output_excel_path}.")
