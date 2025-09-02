import pandas as pd
from tkinter import Tk, filedialog
from datetime import datetime
import os

def seleccionar_archivos():
    # Crear una ventana para la selección de archivos
    root = Tk()
    root.withdraw()  # Ocultar la ventana principal
    archivos = filedialog.askopenfilenames(filetypes=[("Archivos de Excel", "*.xlsx *.xls")])
    return archivos

def unir_hojas_punion(archivos):
    data_frames = []
    for archivo in archivos:
        xls = pd.ExcelFile(archivo)
        if "punion" in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name="punion")
            data_frames.append(df)
    
    # Unir todos los DataFrames
    if data_frames:
        df_concatenado = pd.concat(data_frames, ignore_index=True)
    else:
        df_concatenado = pd.DataFrame()
    
    return df_concatenado

def guardar_archivo(df, ruta):
    if not df.empty:
        # Crear el nombre del archivo con la fecha y hora actual
        fecha_hora_actual = datetime.now().strftime("%Y%m%d%H%M")
        nombre_archivo = f"RAPPI_{fecha_hora_actual}.xlsx"
        ruta_completa = os.path.join(ruta, nombre_archivo)
        
        # Guardar el DataFrame en un archivo Excel
        df.to_excel(ruta_completa, index=False, sheet_name="punion")
        print(f"Archivo guardado como {ruta_completa}")
    else:
        print("No se encontraron hojas con el nombre 'punion' en los archivos seleccionados.")

def main():
    archivos = seleccionar_archivos()
    if archivos:
        df_concatenado = unir_hojas_punion(archivos)
        # Obtener la ruta del primer archivo seleccionado
        ruta = os.path.dirname(archivos[0])
        guardar_archivo(df_concatenado, ruta)
    else:
        print("No se seleccionaron archivos.")

if __name__ == "__main__":
    main()
