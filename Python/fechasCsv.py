import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import re
from datetime import datetime

# Función para detectar fechas en diferentes formatos
def detect_date_columns(df):
    date_columns = []
    possible_date_formats = [
        "%a %b %d %Y %H:%M:%S %Z%z"  # Ej: "Thu Sep 19 2024 23:00:00 GMT-0500"
    ]
    
    # Intentamos identificar columnas que puedan ser fechas
    for col in df.columns:
        is_date = False
        for fmt in possible_date_formats:
            try:
                # Intentamos convertir la columna entera al formato deseado
                pd.to_datetime(df[col], format=fmt, errors='raise')
                is_date = True
                break
            except:
                continue
        if is_date:
            date_columns.append(col)
    
    return date_columns

# Función para buscar fechas manualmente usando regex
def extract_date_from_string(date_str):
    # Expresión regular para extraer una fecha en el formato "Thu Sep 19 2024 23:00:00 GMT-0500"
    regex = r"\w{3} \w{3} \d{2} \d{4} \d{2}:\d{2}:\d{2} GMT[+-]\d{4}"
    match = re.search(regex, date_str)
    if match:
        # Si encontramos una coincidencia, tratamos de convertirla a formato de fecha
        try:
            return datetime.strptime(match.group(), "%a %b %d %Y %H:%M:%S GMT%z")
        except:
            return None
    return None

# Función para aplicar el nuevo formato de fecha
def reformat_dates(df, date_columns, new_format):
    warnings = 0
    for col in date_columns:
        for i, value in enumerate(df[col]):
            if pd.isna(value) or str(value).strip() == "":
                continue
            try:
                # Tratamos de extraer la fecha con la regex si no es reconocida automáticamente
                extracted_date = extract_date_from_string(str(value))
                if extracted_date:
                    df.at[i, col] = extracted_date.strftime(new_format)
                else:
                    warnings += 1
                    df.at[i, col] = ""  # Vaciar valor incorrecto si no podemos extraerla
            except:
                warnings += 1
                df.at[i, col] = ""
    return warnings

# Selección de archivo CSV
def select_csv():
    file_path = filedialog.askopenfilename(filetypes=[("CSV files", "*.csv")])
    if file_path:
        if is_file_in_use(file_path):
            messagebox.showwarning("Advertencia", "El archivo está en uso. Por favor, ciérrelo y vuelva a intentarlo.")
            return
        entry_csv_path.delete(0, tk.END)
        entry_csv_path.insert(0, file_path)

# Verificar si el archivo está en uso
def is_file_in_use(file_path):
    try:
        os.rename(file_path, file_path)
        return False
    except OSError:
        return True

# Función para guardar archivo modificado
def save_csv(df):
    save_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
    if save_path:
        df.to_csv(save_path, sep=';', index=False)
        messagebox.showinfo("Guardado", "Archivo guardado exitosamente.")

# Función principal que maneja el procesamiento de fechas
def process_csv():
    file_path = entry_csv_path.get()
    if not file_path:
        messagebox.showerror("Error", "Seleccione un archivo CSV.")
        return

    try:
        df = pd.read_csv(file_path, sep=';')
        date_columns = detect_date_columns(df)
        
        # Si no detectamos columnas de fechas automáticamente, solicitamos al usuario
        if not date_columns:
            if not messagebox.askyesno("Advertencia", "No se detectaron columnas con fechas automáticamente. ¿Desea seleccionar manualmente las columnas con fechas?"):
                return
            manual_select_columns(df)

        else:
            modify_date_columns(df, date_columns)

    except Exception as e:
        messagebox.showerror("Error", f"Error al procesar el archivo: {e}")

# Función para permitir selección manual de columnas de fechas
def manual_select_columns(df):
    select_columns_window = tk.Toplevel(root)
    select_columns_window.title("Seleccionar columnas con fechas")

    tk.Label(select_columns_window, text="Seleccione las columnas con fechas que desea modificar:").pack()
    var_list = []
    for col in df.columns:
        var = tk.BooleanVar()
        var.set(False)
        checkbox = tk.Checkbutton(select_columns_window, text=col, variable=var)
        checkbox.pack(anchor='w')
        var_list.append(var)

    def apply_changes():
        selected_columns = [df.columns[i] for i, var in enumerate(var_list) if var.get()]
        new_format = entry_date_format.get()

        if not selected_columns or not new_format:
            messagebox.showerror("Error", "Seleccione al menos una columna y defina el formato de fecha.")
            return

        warnings = reformat_dates(df, selected_columns, new_format)
        
        if warnings > 0:
            if not messagebox.askyesno("Advertencia", f"Se encontraron {warnings} valores inválidos. ¿Desea continuar?"):
                return

        save_csv(df)
        select_columns_window.destroy()

    tk.Label(select_columns_window, text="Formato de fecha (Ej: %Y/%m/%d):").pack()
    entry_date_format = tk.Entry(select_columns_window)
    entry_date_format.pack()

    tk.Button(select_columns_window, text="Aplicar", command=apply_changes).pack()

# Función para modificar columnas de fechas detectadas
def modify_date_columns(df, date_columns):
    select_columns_window = tk.Toplevel(root)
    select_columns_window.title("Seleccionar columnas con fechas")

    tk.Label(select_columns_window, text="Seleccione las columnas con fechas que desea modificar:").pack()
    var_list = []
    for col in date_columns:
        var = tk.BooleanVar()
        var.set(True)
        checkbox = tk.Checkbutton(select_columns_window, text=col, variable=var)
        checkbox.pack(anchor='w')
        var_list.append(var)

    def apply_changes():
        selected_columns = [date_columns[i] for i, var in enumerate(var_list) if var.get()]
        new_format = entry_date_format.get()

        if not selected_columns or not new_format:
            messagebox.showerror("Error", "Seleccione al menos una columna y defina el formato de fecha.")
            return

        warnings = reformat_dates(df, selected_columns, new_format)
        
        if warnings > 0:
            if not messagebox.askyesno("Advertencia", f"Se encontraron {warnings} valores inválidos. ¿Desea continuar?"):
                return

        save_csv(df)
        select_columns_window.destroy()

    tk.Label(select_columns_window, text="Formato de fecha (Ej: %Y/%m/%d):").pack()
    entry_date_format = tk.Entry(select_columns_window)
    entry_date_format.pack()

    tk.Button(select_columns_window, text="Aplicar", command=apply_changes).pack()

# Crear GUI principal
root = tk.Tk()
root.title("Conversor de Formatos de Fecha en CSV")

# Campo de selección de archivo
frame_csv = tk.Frame(root)
frame_csv.pack(pady=10)

tk.Label(frame_csv, text="Archivo CSV:").pack(side=tk.LEFT)
entry_csv_path = tk.Entry(frame_csv, width=50)
entry_csv_path.pack(side=tk.LEFT, padx=5)
tk.Button(frame_csv, text="Seleccionar", command=select_csv).pack(side=tk.LEFT)

# Botón de procesamiento
tk.Button(root, text="Procesar", command=process_csv).pack(pady=10)

# Ejecutar interfaz
root.mainloop()