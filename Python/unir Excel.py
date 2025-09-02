import tkinter as tk
from tkinter import filedialog
import pandas as pd

def seleccionar_archivos():
    """Abrir ventana de diálogo para seleccionar archivos Excel"""
    archivos = filedialog.askopenfilenames(title="Selecciona archivos Excel (.xlsx)",
                                           filetypes=[("Archivos Excel", "*.xlsx")])
    return list(archivos)

def unificar_tablas(archivos):
    """Unificar tablas de los archivos seleccionados"""
    # Leer la primera tabla para establecer el esquema de columnas
    df_base = pd.read_excel(archivos[0], sheet_name="Registros")
    columnas_base = set(df_base.columns)

    # Unificar tablas, conservando el formato de columnas
    df_unificada = df_base
    for archivo in archivos[1:]:
        df = pd.read_excel(archivo, sheet_name="Registros")
        columnas_df = set(df.columns)
        # Añadir columnas faltantes con valores vacíos
        for col in columnas_base - columnas_df:
            df[col] = ""
        # Ajustar el orden de las columnas para coincidir con el esquema base
        df = df[[col for col in columnas_base if col in df.columns]]
        df_unificada = pd.concat([df_unificada, df], ignore_index=True)

    return df_unificada

def guardar_resultado(df_unificada):
    """Guardar la tabla unificada en un nuevo archivo Excel"""
    archivo_salida = filedialog.asksaveasfilename(title="Guardar archivo unificado",
                                                  defaultextension=".xlsx",
                                                  filetypes=[("Archivos Excel", "*.xlsx")])
    if archivo_salida:
        df_unificada.to_excel(archivo_salida, sheet_name="Registros", index=False)

def main():
    root = tk.Tk()
    root.title("Unificador de Tablas Excel")

    label = tk.Label(root, text="Selecciona archivos Excel (.xlsx) para unificar")
    label.pack(padx=10, pady=10)

    boton_seleccionar = tk.Button(root, text="Seleccionar Archivos", command=lambda: [
        archivos_seleccionados = seleccionar_archivos(),
        label.config(text=f"Archivos seleccionados: {len(archivos_seleccionados)}"),
        boton_unificar.config(state="normal")
    ])
    boton_seleccionar.pack(padx=10, pady=10)

    boton_unificar = tk.Button(root, text="Unificar Tablas", command=lambda: [
        df_unificada = unificar_tablas(archivos_seleccionados),
        guardar_resultado(df_unificada),
        label.config(text="Proceso completado. Archivo unificado guardado.")
    ])
    boton_unificar.pack(padx=10, pady=10)
    boton_unificar.config(state="disabled")

    root.mainloop()

if __name__ == "__main__":
    main()
