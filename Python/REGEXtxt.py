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
        actualizar_menu_expresiones()  # Actualizar menú tras guardar
    except Exception as e:
        logging.error(f"Error al guardar la expresión regular: {e}")
        messagebox.showerror("Error", "No se pudo guardar la expresión regular")

# Función para aplicar expresiones regulares a archivos seleccionados
def aplicar_expresiones(archivos, regex, reemplazo):
    carpeta_archivos = os.path.dirname(archivos[0])  # Obtener la carpeta de los archivos seleccionados
    configurar_logging(carpeta_archivos)  # Configurar el log en la carpeta de los archivos
    start_time = time.time()
    for archivo in archivos:
        try:
            with open(archivo, 'r', encoding='utf-8') as file:
                contenido = file.read()
            
            # Aplicar expresión regular y reemplazo
            coincidencias = re.findall(regex, contenido)
            contenido = re.sub(regex, reemplazo, contenido, flags=re.MULTILINE)
            logging.info(f"{len(coincidencias)} coincidencias encontradas con {regex} en {os.path.basename(archivo)}")

            # Guardar cambios en el archivo
            with open(archivo, 'w', encoding='utf-8') as file:
                file.write(contenido)
            
            logging.info(f"Archivo {os.path.basename(archivo)} procesado correctamente")

        except Exception as e:
            logging.error(f"Error procesando {archivo}: {e}")
            continue

    end_time = time.time()
    tiempo_procesamiento = end_time - start_time
    logging.info(f"Tiempo total de procesamiento: {tiempo_procesamiento:.2f} segundos")

# Función para mostrar la barra de progreso
def mostrar_progreso(total):
    progress = ProgressBar(maxval=total).start()
    for i in range(total):
        progress.update(i+1)
        time.sleep(0.1)
    progress.finish()

# Función para obtener expresiones regulares guardadas en MongoDB
def obtener_expresiones_guardadas():
    return collection.find().sort("timestamp", -1)

# Función para actualizar el menú desplegable con expresiones regulares
def actualizar_menu_expresiones():
    expresiones_guardadas = obtener_expresiones_guardadas()
    menu_expresiones['menu'].delete(0, 'end')  # Limpiar menú
    for exp in expresiones_guardadas:
        titulo = exp['titulo']
        menu_expresiones['menu'].add_command(label=titulo, command=lambda e=exp: mostrar_expresion(e))

# Función para mostrar la expresión regular y su reemplazo en la interfaz
def mostrar_expresion(expresion):
    entry_regex.delete(0, 'end')
    entry_reemplazo.delete(0, 'end')
    entry_regex.insert(0, expresion['regex'])
    entry_reemplazo.insert(0, expresion['reemplazo'])

# Interfaz gráfica minimalista
class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Procesador de Expresiones Regulares")
        self.geometry("500x600")

        # Botón para seleccionar archivos
        self.btn_seleccionar = tk.Button(self, text="Seleccionar Archivos", command=self.seleccionar_archivos)
        self.btn_seleccionar.pack(pady=10)

        # Lista para mostrar archivos seleccionados
        self.label_archivos = tk.Label(self, text="Archivos seleccionados:")
        self.label_archivos.pack(pady=5)
        self.listbox_archivos = tk.Listbox(self, height=6, width=60)
        self.listbox_archivos.pack(pady=5)

        # Campo para ingresar título
        self.label_titulo = tk.Label(self, text="Título de la Expresión Regular:")
        self.label_titulo.pack(pady=5)
        self.entry_titulo = tk.Entry(self, width=50)
        self.entry_titulo.pack(pady=5)

        # Campo para ingresar expresión regular
        self.label_regex = tk.Label(self, text="Ingrese Expresión Regular:")
        self.label_regex.pack(pady=5)
        global entry_regex
        entry_regex = tk.Entry(self, width=50)
        entry_regex.pack(pady=5)

        # Campo para ingresar texto de reemplazo
        self.label_reemplazo = tk.Label(self, text="Ingrese Texto de Reemplazo:")
        self.label_reemplazo.pack(pady=5)
        global entry_reemplazo
        entry_reemplazo = tk.Entry(self, width=50)
        entry_reemplazo.pack(pady=5)

        # Botón para guardar expresión regular en MongoDB
        self.btn_guardar = tk.Button(self, text="Guardar Expresión", command=self.guardar_expresion)
        self.btn_guardar.pack(pady=10)

        # Menú desplegable para seleccionar expresiones regulares guardadas
        self.label_menu = tk.Label(self, text="Seleccionar Expresión Guardada:")
        self.label_menu.pack(pady=5)
        global menu_expresiones
        menu_expresiones = tk.OptionMenu(self, tk.StringVar(), ())
        menu_expresiones.pack(pady=5)

        # Botón para aplicar expresiones regulares
        self.btn_aplicar = tk.Button(self, text="Aplicar Expresión Regular", command=self.aplicar_expresiones_a_archivos)
        self.btn_aplicar.pack(pady=10)

        self.archivos = []

    def seleccionar_archivos(self):
        self.archivos = seleccionar_archivos()
        if self.archivos:
            self.listbox_archivos.delete(0, 'end')  # Limpiar la lista
            for archivo in self.archivos:
                self.listbox_archivos.insert('end', archivo)  # Mostrar los archivos seleccionados

    def guardar_expresion(self):
        titulo = self.entry_titulo.get()
        regex = entry_regex.get()
        reemplazo = entry_reemplazo.get()
        if titulo and regex:
            guardar_expresion_regular(titulo, regex, reemplazo)
        else:
            messagebox.showwarning("Advertencia", "Debe ingresar un título y una expresión regular")

    def aplicar_expresiones_a_archivos(self):
        if not self.archivos:
            messagebox.showwarning("Advertencia", "Debe seleccionar al menos un archivo")
            return
        regex = entry_regex.get()
        reemplazo = entry_reemplazo.get()
        if regex:
            mostrar_progreso(len(self.archivos))  # Mostrar progreso
            aplicar_expresiones(self.archivos, regex, reemplazo)
        else:
            messagebox.showwarning("Advertencia", "Debe seleccionar una expresión regular")

# Ejemplos de expresiones regulares
ejemplos_regex = [
    r'[a-z]',  # Reemplazar letras minúsculas por mayúsculas
    r'[^a-zA-Z0-9 .,;:!?\'\"-]',  # Eliminar caracteres que no sean letras, números, puntos, comas o espacios
]

if __name__ == "__main__":
    app = Aplicacion()
    actualizar_menu_expresiones()  # Inicializa el menú desplegable con las expresiones guardadas
    app.mainloop()