import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox

# Solicitar al usuario seleccionar un archivo Excel
root = tk.Tk()
root.withdraw()
file_path = filedialog.askopenfilename(filetypes=[("Excel files", "*.xlsx")])

try:
    # Leer el archivo Excel
    df = pd.read_excel(file_path, sheet_name=None)

    # Verificar si hay tablas con 7 columnas
    valid_tables = []
    for sheet_name, table in df.items():
        if table.shape[1] == 7:
            valid_tables.append(sheet_name)

    if not valid_tables:
        messagebox.showerror("Error", "No se encontraron tablas con 7 columnas.")
    else:
        # Unificar registros de todas las tablas
        unification_df = pd.concat([df[table] for table in valid_tables])

        # Crear una nueva hoja llamada "unificacion"
        writer = pd.ExcelWriter(file_path, engine='openpyxl')
        writer.book = writer.book  # Load existing workbook
        unification_df.to_excel(writer, sheet_name='unificacion', index=False)
        writer.save()

        messagebox.showinfo("Éxito", "La tabla 'unificacion' se ha creado correctamente.")

except Exception as e:
    messagebox.showerror("Error", f"Ocurrió un error: {str(e)}")
