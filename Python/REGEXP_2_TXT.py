import tkinter as tk
from tkinter import filedialog
import re

def abrir_archivo():
    """Abre una ventana para seleccionar un archivo y aplica la expresión regular."""

    # Expresión regular ajustada para los archivos de transacciones
    regex = r"^\d{4}-\d{2}-\d{2}\s+.*\$?\-?\d{1,3}(,\d{3})*\.\d{2}\s+(?:[A-Za-z0-9\s\/\.]+\s+)?(?:[A-Za-z0-9\s\/\.]+\s+)?(?:[A-Za-z0-9\s\/\.]+\s+)?\d*\.?\d*%$"

    # Abrir ventana de selección de archivo
    archivo = filedialog.askopenfilename(
        initialdir="/",
        title="Seleccionar archivo",
        filetypes=(("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")),
    )

    if archivo:
        try:
            with open(archivo, "r") as f:
                contenido = f.readlines()

            # Aplicar la expresión regular a cada línea del archivo
            resultados = [linea.strip() for linea in contenido if re.match(regex, linea)]

            # Mostrar los resultados en una nueva ventana
            ventana_resultados = tk.Toplevel(ventana)
            ventana_resultados.title("Resultados")
            texto_resultados = tk.Text(ventana_resultados)
            texto_resultados.pack(expand=True, fill="both")
            for resultado in resultados:
                texto_resultados.insert(tk.END, resultado + "\n")
            texto_resultados.config(state=tk.DISABLED)

        except FileNotFoundError:
            tk.messagebox.showerror("Error", f"Archivo no encontrado: {archivo}")

# Crear ventana principal
ventana = tk.Tk()
ventana.title("Aplicación de Expresión Regular")

# Botón para abrir archivo
boton_abrir = tk.Button(ventana, text="Abrir Archivo", command=abrir_archivo)
boton_abrir.pack()

ventana.mainloop()