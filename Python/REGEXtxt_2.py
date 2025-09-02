import re
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import pymongo
import os

# Función para reemplazar caracteres especiales y convertir a mayúsculas
def reemplazar_especiales(texto):
    # Diccionario de reemplazos
    reemplazos = {
        'ñ': 'n', 'Ñ': 'N',
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u', 'ü': 'u',
        'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U', 'Ü': 'U'
    }

    # Reemplazo utilizando una expresión regular
    regex = re.compile('|'.join(re.escape(key) for key in reemplazos.keys()))
    return regex.sub(lambda match: reemplazos[match.group(0)], texto).upper()

# Función para cargar y procesar archivos seleccionados
def procesar_archivos():
    archivos = filedialog.askopenfilenames(filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv")])
    if not archivos:
        messagebox.showwarning("Advertencia", "No se seleccionaron archivos.")
        return
    
    for archivo in archivos:
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                contenido = f.read()
            
            # Aplicar reemplazo de caracteres especiales y conversión a mayúsculas
            contenido_transformado = reemplazar_especiales(contenido)
            
            # Guardar el archivo transformado
            ruta_guardado = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv")])
            if ruta_guardado:
                with open(ruta_guardado, 'w', encoding='utf-8') as f:
                    f.write(contenido_transformado)
                messagebox.showinfo("Éxito", f"El archivo se guardó correctamente en {ruta_guardado}")
        
        except Exception as e:
            messagebox.showerror("Error", f"Error al procesar el archivo {archivo}: {e}")

# Función para conectar y guardar expresiones regulares en MongoDB Atlas
def guardar_en_mongodb():
    cliente = pymongo.MongoClient("mongodb+srv://demiurgo:requiem@demiurgo.oqf9p2y.mongodb.net/?retryWrites=true&w=majority&appName=demiurgo")
    db = cliente["financierosJP"]
    coleccion = db["ExpresionesRegulares"]

    expresion = entry_regex.get()
    if not expresion:
        messagebox.showwarning("Advertencia", "No se ingresó ninguna expresión regular.")
        return

    # Guardar expresión regular en la base de datos
    try:
        coleccion.insert_one({"expresion_regular": expresion})
        messagebox.showinfo("Éxito", "Expresión regular guardada correctamente.")
    except Exception as e:
        messagebox.showerror("Error", f"Error al guardar en MongoDB: {e}")

# Interfaz gráfica principal
def crear_interfaz():
    ventana = tk.Tk()
    ventana.title("Procesamiento de Archivos con Expresiones Regulares")
    ventana.geometry("500x300")
    
    # Etiqueta y campo de entrada para la expresión regular
    label_regex = tk.Label(ventana, text="Expresión regular:")
    label_regex.pack(pady=10)
    
    global entry_regex
    entry_regex = tk.Entry(ventana, width=50)
    entry_regex.pack(pady=10)
    
    # Botón para seleccionar archivos y aplicar procesamiento
    boton_seleccionar = tk.Button(ventana, text="Seleccionar y Procesar Archivos", command=procesar_archivos)
    boton_seleccionar.pack(pady=10)
    
    # Botón para guardar la expresión regular en MongoDB
    boton_guardar = tk.Button(ventana, text="Guardar Expresión Regular en MongoDB", command=guardar_en_mongodb)
    boton_guardar.pack(pady=10)
    
    # Botón adicional para reemplazar caracteres especiales y convertir a mayúsculas
    boton_transformar = tk.Button(ventana, text="Aplicar Reemplazo y Conversión a Mayúsculas", command=procesar_archivos)
    boton_transformar.pack(pady=10)
    
    ventana.mainloop()

# Iniciar la interfaz gráfica
crear_interfaz()