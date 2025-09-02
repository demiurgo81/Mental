import tkinter as tk
from tkinter import filedialog, messagebox
import re
import os
import time
from progressbar import ProgressBar
import logging

# Configuración de logging
def configurar_logging(carpeta_archivos):
    log_path = os.path.join(carpeta_archivos, 'log_extraccion.log')
    logging.basicConfig(filename=log_path, level=logging.INFO, 
                        format='%(asctime)s - %(levelname)s - %(message)s')

# Función para seleccionar archivos
def seleccionar_archivos():
    archivos = filedialog.askopenfilenames(filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv")])
    return archivos

# Función para extraer coincidencias de archivos y generar un nuevo archivo con los datos extraídos
def extraer_y_generar_archivo(archivos, regex, carpeta_salida):
    configurar_logging(carpeta_salida)
    archivo_salida = os.path.join(carpeta_salida, f"extraccion_{int(time.time())}.txt")
    start_time = time.time()

    with open(archivo_salida, 'w', encoding='utf-8') as salida:
        salida.write("Datos extraídos:\n\n")  # Cabecera del archivo de salida

        for archivo in archivos:
            try:
                with open(archivo, 'r', encoding='utf-8') as file:
                    contenido = file.read()
                
                # Extraer coincidencias
                coincidencias = re.findall(regex, contenido, flags=re.MULTILINE)
                logging.info(f"{len(coincidencias)} coincidencias encontradas en {os.path.basename(archivo)}")
                
                if coincidencias:
                    salida.write(f"Archivo: {os.path.basename(archivo)}\n")
                    for coincidencia in coincidencias:
                        salida.write(f"{coincidencia}\n")
                    salida.write("\n")  # Separador entre archivos

            except Exception as e:
                logging.error(f"Error procesando {archivo}: {e}")

    tiempo_total = time.time() - start_time
    logging.info(f"Extracción completada en {tiempo_total:.2f} segundos")
    messagebox.showinfo("Extracción completada", f"Los datos extraídos se guardaron en:\n{archivo_salida}")

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
        self.title("Extractor de Expresiones Regulares")
        self.geometry("500x600")

        # Botón para seleccionar archivos
        self.btn_seleccionar = tk.Button(self, text="Seleccionar Archivos", command=self.seleccionar_archivos)
        self.btn_seleccionar.pack(pady=10)

        # Lista para mostrar archivos seleccionados
        self.listbox_archivos = tk.Listbox(self, height=6, width=60)
        self.listbox_archivos.pack(pady=5)

        # Campo para ingresar expresión regular
        self.label_regex = tk.Label(self, text="Ingrese Expresión Regular:")
        self.label_regex.pack(pady=5)
        self.entry_regex = tk.Entry(self, width=50)
        self.entry_regex.pack(pady=5)

        # Botón para seleccionar carpeta de salida
        self.btn_carpeta = tk.Button(self, text="Seleccionar Carpeta de Salida", command=self.seleccionar_carpeta_salida)
        self.btn_carpeta.pack(pady=10)
        self.label_carpeta = tk.Label(self, text="Carpeta de salida no seleccionada", fg="red")
        self.label_carpeta.pack(pady=5)

        # Botón para extraer coincidencias
        self.btn_extraer = tk.Button(self, text="Extraer Coincidencias", command=self.extraer_coincidencias)
        self.btn_extraer.pack(pady=10)

        self.archivos = []
        self.carpeta_salida = None

    def seleccionar_archivos(self):
        self.archivos = seleccionar_archivos()
        if self.archivos:
            self.listbox_archivos.delete(0, 'end')
            for archivo in self.archivos:
                self.listbox_archivos.insert('end', archivo)

    def seleccionar_carpeta_salida(self):
        self.carpeta_salida = filedialog.askdirectory()
        if self.carpeta_salida:
            self.label_carpeta.config(text=f"Carpeta de salida: {self.carpeta_salida}", fg="green")
        else:
            self.label_carpeta.config(text="Carpeta de salida no seleccionada", fg="red")

    def extraer_coincidencias(self):
        if not self.archivos:
            messagebox.showwarning("Advertencia", "Debe seleccionar al menos un archivo")
            return
        if not self.carpeta_salida:
            messagebox.showwarning("Advertencia", "Debe seleccionar una carpeta de salida")
            return
        regex = self.entry_regex.get()
        if regex:
            mostrar_progreso(len(self.archivos))
            extraer_y_generar_archivo(self.archivos, regex, self.carpeta_salida)
        else:
            messagebox.showwarning("Advertencia", "Debe ingresar una expresión regular")

if __name__ == "__main__":
    app = Aplicacion()
    app.mainloop()