import cx_Oracle
import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox

# Función para conectarse a Oracle
def conectar_a_bd():
    try:
        dsn = cx_Oracle.makedsn("100.126.98.25", 1850, service_name="PDB_IVRCONV")
        connection = cx_Oracle.connect(user="PDB_CRONUS", password="C7ar0_2o2s", dsn=dsn)
        return connection
    except cx_Oracle.DatabaseError as e:
        messagebox.showerror("Error de conexión", f"No se pudo conectar a la base de datos: {e}")
        return None

# Función para ejecutar la consulta
def ejecutar_consulta(query, conn):
    try:
        cursor = conn.cursor()
        cursor.execute(query)
        # Recuperar los datos de la consulta
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        df = pd.DataFrame(rows, columns=columns)
        return df
    except cx_Oracle.DatabaseError as e:
        messagebox.showerror("Error en la consulta", f"No se pudo ejecutar la consulta: {e}")
        return None


# Función para guardar los resultados en un CSV
def guardar_csv(df):
    if df is not None:
        file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if file_path:
            try:
                # Exportar con el separador ';'
                df.to_csv(file_path, sep=';', index=False, encoding='utf-8', date_format='%d/%m/%Y')
                messagebox.showinfo("Éxito", "Archivo CSV guardado correctamente.")
            except Exception as e:
                messagebox.showerror("Error al guardar", f"No se pudo guardar el archivo: {e}")

# Función que se ejecuta al presionar el botón "Consultar"
def realizar_consulta():
    query = entry_query.get("1.0", tk.END).strip()
    if query:
        conn = conectar_a_bd()
        if conn:
            df = ejecutar_consulta(query, conn)
            guardar_csv(df)
            conn.close()

# Interfaz gráfica usando tkinter
root = tk.Tk()
root.title("Consultas Oracle a CSV")

# Campo para ingresar la consulta
label_query = tk.Label(root, text="Ingrese su consulta SQL:")
label_query.pack(pady=10)

entry_query = tk.Text(root, height=10, width=80)
entry_query.pack(padx=10, pady=10)

# Botón para ejecutar la consulta
btn_consultar = tk.Button(root, text="Consultar y Exportar", command=realizar_consulta)
btn_consultar.pack(pady=20)

root.mainloop()