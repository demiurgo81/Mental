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
logging.basicConfig(filename='log_procesamiento.log', level=logging.INFO, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Función para seleccionar archivos
def seleccionar_archivos():
    archivos = filedialog.askopenfilenames(filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv")])
    return archivos

# Función para guardar expresiones regulares en MongoDB
def guardar_expresion_regular(regex):
    try:
        collection.insert_one({"regex": regex, "timestamp": time.time()})
        messagebox.showinfo("Guardado", "Expresión regular guardada correctamente")
        actualizar_menu_expresiones()  # Actualizar menú tras guardar
    except Exception as e:
        logging.error(f"Error al guardar la expresión regular: {e}")
        messagebox.showerror("Error", "No se pudo guardar la expresión regular")

# Función para aplicar expresiones regulares a archivos seleccionados
def aplicar_expresiones(archivos, regex_list, replace_text):
    log_path = filedialog.asksaveasfilename(defaultextension=".log", filetypes=[("Log files", "*.log")])
    start_time = time.time()
    for archivo in archivos:
        try:
            with open(archivo, 'r', encoding='utf-8') as file:
                contenido = file.read()
            
            # Aplicar todas las expresiones regulares
            for regex in regex_list:
                coincidencias = re.findall(regex, contenido)
                # Aplicar reemplazo en todo el archivo
                contenido = re.sub(regex, replace_text, contenido, flags=re.MULTILINE)
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
    return [doc['regex'] for doc in collection.find().sort("timestamp", -1)]

# Función para actualizar el menú desplegable con expresiones regulares
def actualizar_menu_expresiones():
    expresiones_guardadas = obtener_expresiones_guardadas()
    menu_expresiones['menu'].delete(0, 'end')  # Limpiar menú
    for exp in expresiones_guardadas:
        menu_expresiones['menu'].add_command(label=exp, command=tk._setit(variable_regex, exp))

# Interfaz gráfica minimalista
class Aplicacion(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Procesador de Expresiones Regulares")
        self.geometry("500x500")

        # Botón para seleccionar archivos
        self.btn_seleccionar = tk.Button(self, text="Seleccionar Archivos", command=self.seleccionar_archivos)
        self.btn_seleccionar.pack(pady=10)

        # Lista para mostrar archivos seleccionados
        self.label_archivos = tk.Label(self, text="Archivos seleccionados:")
        self.label_archivos.pack(pady=5)
        self.listbox_archivos = tk.Listbox(self, height=6, width=60)
        self.listbox_archivos.pack(pady=5)

        # Campo para ingresar expresión regular
        self.label_regex = tk.Label(self, text="Ingrese Expresión Regular:")
        self.label_regex.pack(pady=5)
        self.entry_regex = tk.Entry(self, width=50)
        self.entry_regex.pack(pady=5)

        # Campo para ingresar texto de reemplazo
        self.label_replace = tk.Label(self, text="Ingrese Texto de Reemplazo:")
        self.label_replace.pack(pady=5)
        self.entry_replace = tk.Entry(self, width=50)
        self.entry_replace.pack(pady=5)

        # Botón para guardar expresión regular en MongoDB
        self.btn_guardar = tk.Button(self, text="Guardar Expresión", command=self.guardar_expresion)
        self.btn_guardar.pack(pady=10)

        # Menú desplegable para seleccionar expresiones regulares guardadas
        self.label_menu = tk.Label(self, text="Seleccionar Expresión Guardada:")
        self.label_menu.pack(pady=5)
        global variable_regex
        variable_regex = tk.StringVar(self)
        self.expresiones_guardadas = obtener_expresiones_guardadas()
        global menu_expresiones
        menu_expresiones = tk.OptionMenu(self, variable_regex, *self.expresiones_guardadas)
        menu_expresiones.pack(pady=5)

        # Botón para aplicar expresiones regulares
        self.btn_aplicar = tk.Button(self, text="Aplicar Expresiones", command=self.aplicar_expresiones)
        self.btn_aplicar.pack(pady=10)

        self.archivos = []

    def seleccionar_archivos(self):
        self.archivos = seleccionar_archivos()
        if self.archivos:
            self.listbox_archivos.delete(0, 'end')  # Limpiar la lista
            for archivo in self.archivos:
                self.listbox_archivos.insert('end', archivo)  # Mostrar los archivos seleccionados

    def guardar_expresion(self):
        regex = self.entry_regex.get()
        if regex:
            guardar_expresion_regular(regex)
        else:
            messagebox.showwarning("Advertencia", "Debe ingresar una expresión regular")

    def aplicar_expresiones(self):
        if not self.archivos:
            messagebox.showwarning("Advertencia", "Debe seleccionar al menos un archivo")
            return
        regex = variable_regex.get()
        replace_text = self.entry_replace.get()  # Obtener texto de reemplazo
        if regex:
            regex_list = [regex]  # Usar la expresión seleccionada
            mostrar_progreso(len(self.archivos))  # Mostrar progreso
            aplicar_expresiones(self.archivos, regex_list, replace_text)
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