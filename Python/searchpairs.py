import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import re
from difflib import SequenceMatcher
import os

# Función para instalar bibliotecas si no están instaladas
try:
    import openpyxl
except ImportError:
    os.system('pip install openpyxl')

def seleccionar_archivo():
    archivo = filedialog.askopenfilename(
        title="Seleccione un archivo Excel o CSV", 
        filetypes=[("Excel files", "*.xlsx"), ("CSV files", "*.csv")]
    )
    return archivo

def obtener_hojas(archivo):
    if archivo.endswith('.xlsx'):
        xls = pd.ExcelFile(archivo, engine='openpyxl')  # Usar el engine openpyxl
    elif archivo.endswith('.xls'):
        xls = pd.ExcelFile(archivo, engine='xlrd')  # Usar xlrd para archivos .xls
    else:
        raise ValueError("Formato de archivo no soportado.")
    return xls.sheet_names

def cargar_datos(archivo, hoja=None):
    if archivo.endswith('.xlsx'):
        df = pd.read_excel(archivo, sheet_name=hoja)
    else:
        df = pd.read_csv(archivo)
    return df

def limpiar_cadena(cadena):
    cadena = cadena.upper()  # Convertir a mayúsculas
    cadena = re.sub(r'[^A-Z0-9 ]', '', cadena)  # Eliminar caracteres especiales
    cadena = cadena.strip()  # Eliminar espacios al inicio y final
    cadena = re.sub(r'\s+', ' ', cadena)  # Reemplazar espacios duplicados por uno
    return cadena

def calcular_similitud(cadena1, cadena2):
    matcher = SequenceMatcher(None, cadena1.split(), cadena2.split())
    return matcher.ratio() * 100

def procesar_columnas(columna1, columna2, progress_bar):
    resultados = []
    total = len(columna1)
    
    for i, valor1 in enumerate(columna1):
        valor1_limpio = limpiar_cadena(valor1)
        similitudes = []

        for valor2 in columna2:
            valor2_limpio = limpiar_cadena(valor2)
            similitud = calcular_similitud(valor1_limpio, valor2_limpio)
            similitudes.append((valor2, similitud))

        # Ordenar por similitud y tomar los tres mejores resultados
        similitudes_ordenadas = sorted(similitudes, key=lambda x: x[1], reverse=True)[:3]

        # Extraer resultados (si hay menos de 3, rellenar con valores vacíos)
        mejor_coincidencia = similitudes_ordenadas[0] if len(similitudes_ordenadas) > 0 else ('', 0)
        segunda_mejor_coincidencia = similitudes_ordenadas[1] if len(similitudes_ordenadas) > 1 else ('', 0)
        tercera_mejor_coincidencia = similitudes_ordenadas[2] if len(similitudes_ordenadas) > 2 else ('', 0)

        resultados.append([
            valor1,
            mejor_coincidencia[0], mejor_coincidencia[1],
            segunda_mejor_coincidencia[0], segunda_mejor_coincidencia[1],
            tercera_mejor_coincidencia[0], tercera_mejor_coincidencia[1]
        ])

        # Actualizar la barra de progreso
        progress_bar['value'] = (i + 1) / total * 100
        progress_bar.update_idletasks()
    
    return resultados

def exportar_resultados(resultados, archivo_salida, separador):
    columnas = [
        "Valor Columna 1",
        "Mejor Coincidencia Columna 2", "Porcentaje de Similitud 1",
        "Segunda Mejor Coincidencia", "Porcentaje de Similitud 2",
        "Tercera Mejor Coincidencia", "Porcentaje de Similitud 3"
    ]
    df_resultados = pd.DataFrame(resultados, columns=columnas)
    df_resultados.to_csv(archivo_salida, index=False, sep=separador)
    messagebox.showinfo("Exportación completada", f"Resultados exportados a {archivo_salida}")

def seleccionar_hojas_columnas():
    root = tk.Tk()
    root.title("Seleccione Hojas, Columnas y Separador")

    # Variables para almacenar selecciones
    hoja1_var = tk.StringVar()
    columna1_var = tk.StringVar()
    hoja2_var = tk.StringVar()
    columna2_var = tk.StringVar()
    separador_var = tk.StringVar(value=",")  # Valor por defecto: coma

    # Función para actualizar las columnas disponibles tras seleccionar una hoja
    def actualizar_columnas1(event):
        hoja1 = hoja1_var.get()
        df1 = cargar_datos(archivo1, hoja1)
        columnas1_cb['values'] = df1.columns.tolist()
        columnas1_cb.current(0)

    def actualizar_columnas2(event):
        hoja2 = hoja2_var.get()
        df2 = cargar_datos(archivo2, hoja2)
        columnas2_cb['values'] = df2.columns.tolist()
        columnas2_cb.current(0)

    # Seleccionar archivo 1
    archivo1 = seleccionar_archivo()
    hojas1 = obtener_hojas(archivo1)

    # Seleccionar archivo 2
    archivo2 = seleccionar_archivo()
    hojas2 = obtener_hojas(archivo2)

    # Combobox para archivo 1 (hojas y columnas)
    ttk.Label(root, text="Archivo 1 - Hoja:").grid(row=0, column=0, padx=10, pady=10)
    hojas1_cb = ttk.Combobox(root, textvariable=hoja1_var, values=hojas1)
    hojas1_cb.grid(row=0, column=1, padx=10, pady=10)
    hojas1_cb.bind("<<ComboboxSelected>>", actualizar_columnas1)

    ttk.Label(root, text="Archivo 1 - Columna:").grid(row=1, column=0, padx=10, pady=10)
    columnas1_cb = ttk.Combobox(root, textvariable=columna1_var)
    columnas1_cb.grid(row=1, column=1, padx=10, pady=10)

    # Combobox para archivo 2 (hojas y columnas)
    ttk.Label(root, text="Archivo 2 - Hoja:").grid(row=2, column=0, padx=10, pady=10)
    hojas2_cb = ttk.Combobox(root, textvariable=hoja2_var, values=hojas2)
    hojas2_cb.grid(row=2, column=1, padx=10, pady=10)
    hojas2_cb.bind("<<ComboboxSelected>>", actualizar_columnas2)

    ttk.Label(root, text="Archivo 2 - Columna:").grid(row=3, column=0, padx=10, pady=10)
    columnas2_cb = ttk.Combobox(root, textvariable=columna2_var)
    columnas2_cb.grid(row=3, column=1, padx=10, pady=10)

    # Campo para seleccionar el separador
    ttk.Label(root, text="Separador CSV:").grid(row=4, column=0, padx=10, pady=10)
    separador_entry = ttk.Entry(root, textvariable=separador_var)
    separador_entry.grid(row=4, column=1, padx=10, pady=10)

    # Barra de progreso
    progress_bar = ttk.Progressbar(root, orient="horizontal", length=300, mode="determinate")
    progress_bar.grid(row=5, column=0, columnspan=2, pady=20)

    # Función para procesar después de la selección
    def procesar_seleccion():
        hoja1 = hoja1_var.get()
        columna1 = columna1_var.get()
        hoja2 = hoja2_var.get()
        columna2 = columna2_var.get()
        separador = separador_var.get()

        df1 = cargar_datos(archivo1, hoja1)
        df2 = cargar_datos(archivo2, hoja2)

        resultados = procesar_columnas(df1[columna1].astype(str), df2[columna2].astype(str), progress_bar)

        archivo_salida = filedialog.asksaveasfilename(
            defaultextension=".csv", 
            filetypes=[("CSV files", "*.csv")], 
            title="Guardar archivo de resultados"
        )
        exportar_resultados(resultados, archivo_salida, separador)

        root.quit()

    # Botón para procesar la selección
    procesar_btn = ttk.Button(root, text="Procesar", command=procesar_seleccion)
    procesar_btn.grid(row=6, column=0, columnspan=2, pady=10)

    root.mainloop()

if __name__ == "__main__":
    seleccionar_hojas_columnas();