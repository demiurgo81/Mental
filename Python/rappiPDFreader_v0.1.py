import tkinter as tk
from tkinter import filedialog
import tabula

# Función para seleccionar un archivo PDF
def seleccionar_archivo():
    ruta_archivo = filedialog.askopenfilename(filetypes=[("Archivos PDF", "*.pdf")])
    if ruta_archivo:
        procesar_pdf(ruta_archivo)

# Función para procesar el archivo PDF
def procesar_pdf(ruta_archivo):
    try:
        # Extraer las tablas del PDF
        tablas = tabula.read_pdf(ruta_archivo, pages="all", multiple_tables=True)
        cantidad_tablas = len(tablas)

        # Contar registros en cada tabla
        registros_por_tabla = [len(tabla) for tabla in tablas]

        # Mostrar resultados en una ventana emergente
        mensaje = f"Se encontraron {cantidad_tablas} tablas en el archivo PDF.\n\n"
        for i, registros in enumerate(registros_por_tabla, start=1):
            mensaje += f"Tabla {i}: {registros} registros\n"

        ventana_resultados = tk.Tk()
        ventana_resultados.title("Resultados")
        etiqueta_resultados = tk.Label(ventana_resultados, text=mensaje, padx=10, pady=10)
        etiqueta_resultados.pack()
        ventana_resultados.mainloop()

    except Exception as e:
        print(f"Error al procesar el archivo PDF: {e}")

# Crear una ventana emergente para seleccionar el archivo
ventana_principal = tk.Tk()
ventana_principal.title("Seleccionar archivo PDF")
boton_seleccionar = tk.Button(ventana_principal, text="Seleccionar archivo", command=seleccionar_archivo)
boton_seleccionar.pack(padx=20, pady=20)
ventana_principal.mainloop()
