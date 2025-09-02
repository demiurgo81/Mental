import tkinter as tk
from tkinter import filedialog, messagebox
import re
import pymongo
import time
import os
from progressbar import ProgressBar
import logging

# Configuración de MongoDB
MONGO_URI = "mongodb+srv://demiurgo:requiem@demiurgo.oqf9p2y.mongodb.net/?retryWrites=true&w=majority&appName=demiurgo"
client = pymongo.MongoClient(MONGO_URI)
db = client['financierosJP']
collection = db['ExpresionesRegulares']

# Configuración de logging
def configurar_logging(carpeta_archivos):
    log_path = os.path.join(carpeta_archivos, 'log_procesamiento.log')
    logging.basicConfig(filename=log_path, level=logging.INFO, 
                        format='%(asctime)s - %(levelname)s - %(message)s')

# Función para seleccionar archivos
def seleccionar_archivos():
    archivos = filedialog.askopenfilenames(filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv")])
    return archivos

# Función para guardar expresiones regulares en MongoDB con su título y reemplazo
def guardar_expresion_regular(titulo, regex, reemplazo):
    try:
        collection.insert_one({"titulo": titulo, "regex": regex, "reemplazo": reemplazo, "timestamp": time.time()})
        messagebox.showinfo("Guardado", "Expresión regular y reemplazo guardados correctamente")
    except Exception as e:
        logging.error(f"Error al guardar la expresión regular: {e}")
        messagebox.showerror("Error", "No se pudo guardar la expresión regular")

# Función para aplicar expresiones regulares a coincidencias
def aplicar_expresiones(archivos, regex, reemplazo):
    carpeta_archivos = os.path.dirname(archivos[0])
    configurar_logging(carpeta_archivos)
    start_time = time.time()
    for archivo in archivos:
        try:
            with open(archivo, 'r', encoding='utf-8') as file:
                contenido = file.read()

            coincidencias = re.findall(regex, contenido)
            contenido = re.sub(regex, reemplazo, contenido, flags=re.MULTILINE)
            logging.info(f"{len(coincidencias)} coincidencias encontradas con {regex} en {os.path.basename(archivo)}")

            with open(archivo, 'w', encoding='utf-8') as file:
                file.write(contenido)

        except Exception as e:
            logging.error(f"Error procesando {archivo}: {e}")

    logging.info(f"Tiempo total de procesamiento: {time.time() - start_time:.2f} segundos")

# Función para aplicar expresiones regulares a no coincidencias
def aplicar_expresiones_inversas(archivos, regex, reemplazo):
    carpeta_archivos = os.path.dirname(archivos[0])
    configurar_logging(carpeta_archivos)
    start_time = time.time()
    for archivo in archivos:
        try:
            with open(archivo, 'r', encoding='utf-8') as file:
                contenido = file.read()

            patron_inverso = f"^(?!.*{regex}).*$"
            no_coincidencias = re.findall(patron_inverso, contenido, flags=re.MULTILINE)
            contenido = re.sub(patron_inverso, reemplazo, contenido, flags=re.MULTILINE)
            logging.info(f"{len(no_coincidencias)} no coincidencias encontradas con {regex} en {os.path.basename(archivo)}")

            with open(archivo, 'w', encoding='utf-8') as file:
                file.write(contenido)

        except Exception as e:
            logging.error(f"Error procesando {archivo}: {e}")

    logging.info(f"Tiempo total de procesamiento inverso: {time.time() - start_time:.2f} segundos")

# Mostrar barra de progreso
def mostrar_progreso(total):
    progress = ProgressBar(maxval=total).start()
    for i in range(total):
        progress.update(i + 1)
        time.sleep(0.1)
    progress.finish()

# Interfaz gráfica
class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Procesador de Expresiones Regulares")
        self.geometry("500x600")

        # Botón para seleccionar archivos
        self.btn_seleccionar = tk.Button(self, text="Seleccionar Archivos", command=self.seleccionar_archivos)
        self.btn_seleccionar.pack(pady=10)

        # Lista para mostrar archivos seleccionados
        self.listbox_archivos = tk.Listbox(self, height=6, width=60)
        self.listbox_archivos.pack(pady=5)

        # Campos para ingresar expresión regular y reemplazo
        self.label_regex = tk.Label(self, text="Ingrese Expresión Regular:")
        self.label_regex.pack(pady=5)
        self.entry_regex = tk.Entry(self, width=50)
        self.entry_regex.pack(pady=5)

        self.label_reemplazo = tk.Label(self, text="Ingrese Texto de Reemplazo:")
        self.label_reemplazo.pack(pady=5)
        self.entry_reemplazo = tk.Entry(self, width=50)
        self.entry_reemplazo.pack(pady=5)

        # Botones para aplicar expresiones
        self.btn_aplicar = tk.Button(self, text="Aplicar a Coincidencias", command=self.aplicar_a_coincidencias)
        self.btn_aplicar.pack(pady=10)

        self.btn_aplicar_inverso = tk.Button(self, text="Aplicar a No Coincidencias", command=self.aplicar_a_no_coincidencias)
        self.btn_aplicar_inverso.pack(pady=10)

        self.archivos = []

    def seleccionar_archivos(self):
        self.archivos = seleccionar_archivos()
        if self.archivos:
            self.listbox_archivos.delete(0, 'end')
            for archivo in self.archivos:
                self.listbox_archivos.insert('end', archivo)

    def aplicar_a_coincidencias(self):
        if not self.archivos:
            messagebox.showwarning("Advertencia", "Debe seleccionar al menos un archivo")
            return
        regex = self.entry_regex.get()
        reemplazo = self.entry_reemplazo.get()
        if regex:
            mostrar_progreso(len(self.archivos))
            aplicar_expresiones(self.archivos, regex, reemplazo)
        else:
            messagebox.showwarning("Advertencia", "Debe ingresar una expresión regular")

    def aplicar_a_no_coincidencias(self):
        if not self.archivos:
            messagebox.showwarning("Advertencia", "Debe seleccionar al menos un archivo")
            return
        regex = self.entry_regex.get()
        reemplazo = self.entry_reemplazo.get()
        if regex:
            mostrar_progreso(len(self.archivos))
            aplicar_expresiones_inversas(self.archivos, regex, reemplazo)
        else:
            messagebox.showwarning("Advertencia", "Debe ingresar una expresión regular")

if __name__ == "__main__":
    app = Aplicacion()
    app.mainloop()
