import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import pandas as pd
import os
import numpy as np
from openpyxl.utils import get_column_letter

class ExcelMergeApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Excel Merge Tool")
        self.root.geometry("600x400")
        
        self.files_selected = []
        self.common_sheets = []
        
        # Crear y configurar el marco principal
        self.main_frame = ttk.Frame(root, padding="10")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Botón para seleccionar archivos
        self.select_button = ttk.Button(
            self.main_frame,
            text="Seleccionar Archivos Excel",
            command=self.select_files
        )
        self.select_button.grid(row=0, column=0, pady=10, sticky=tk.W)
        
        # Lista de archivos seleccionados
        self.files_label = ttk.Label(self.main_frame, text="Archivos seleccionados:")
        self.files_label.grid(row=1, column=0, pady=5, sticky=tk.W)
        
        self.files_listbox = tk.Listbox(self.main_frame, width=70, height=8)
        self.files_listbox.grid(row=2, column=0, pady=5)
        
        # Combobox para seleccionar hoja común
        self.sheet_label = ttk.Label(self.main_frame, text="Seleccionar hoja común:")
        self.sheet_label.grid(row=3, column=0, pady=5, sticky=tk.W)
        
        self.sheet_combo = ttk.Combobox(self.main_frame, state="readonly")
        self.sheet_combo.grid(row=4, column=0, pady=5, sticky=tk.W)
        
        # Botón para unificar
        self.merge_button = ttk.Button(
            self.main_frame,
            text="Unificar Archivos",
            command=self.merge_files,
            state="disabled"
        )
        self.merge_button.grid(row=5, column=0, pady=20)
        
    def clean_column_name(self, column_name):
        """Limpia y valida el nombre de la columna"""
        # Convertir a string si no lo es
        column_name = str(column_name).strip()
        # Reemplazar caracteres problemáticos
        forbidden_chars = ['[', ']', '*', '?', '/', '\\']
        for char in forbidden_chars:
            column_name = column_name.replace(char, '_')
        return column_name

    def select_files(self):
        files = filedialog.askopenfilenames(
            title="Seleccionar archivos Excel",
            filetypes=[("Excel files", "*.xlsx")]
        )
        
        if not files:
            return
            
        self.files_selected = files
        self.files_listbox.delete(0, tk.END)
        
        for file in files:
            self.files_listbox.insert(tk.END, os.path.basename(file))
        
        all_sheets = []
        for file in files:
            xl = pd.ExcelFile(file)
            all_sheets.append(set(xl.sheet_names))
        
        self.common_sheets = list(set.intersection(*all_sheets))
        
        self.sheet_combo['values'] = self.common_sheets
        if self.common_sheets:
            self.sheet_combo.set(self.common_sheets[0])
            self.merge_button['state'] = 'normal'
        else:
            messagebox.showerror(
                "Error",
                "No se encontraron hojas con nombres comunes en los archivos seleccionados"
            )

    def get_column_width(self, column):
        """Calcula el ancho óptimo para una columna manejando diferentes tipos de datos"""
        try:
            # Convertir todos los valores a string, manejando NaN y None
            str_values = column.fillna('').astype(str)
            # Obtener la longitud máxima
            max_length = max(str_values.str.len().max(), 0)
            return max_length + 2  # Añadir un poco de padding
        except:
            return 15  # Valor por defecto si hay algún error

    def merge_files(self):
        if not self.files_selected or not self.sheet_combo.get():
            return
            
        selected_sheet = self.sheet_combo.get()
        
        try:
            # Lista para almacenar los DataFrames procesados
            processed_dfs = []
            all_headers = set()
            
            # Primera pasada: recolectar todos los encabezados y limpiarlos
            for file in self.files_selected:
                df = pd.read_excel(file, sheet_name=selected_sheet)
                # Limpiar nombres de columnas
                df.columns = [self.clean_column_name(col) for col in df.columns]
                all_headers.update(df.columns)
            
            # Ordenar los encabezados
            all_headers = sorted(list(all_headers))
            
            # Segunda pasada: procesar cada archivo
            for file in self.files_selected:
                df = pd.read_excel(file, sheet_name=selected_sheet)
                # Limpiar nombres de columnas
                df.columns = [self.clean_column_name(col) for col in df.columns]
                
                # Agregar columnas faltantes
                for header in all_headers:
                    if header not in df.columns:
                        df[header] = np.nan
                
                # Asegurar el orden de las columnas
                df = df[all_headers]
                processed_dfs.append(df)
            
            # Concatenar todos los DataFrames
            merged_df = pd.concat(processed_dfs, ignore_index=True)
            
            # Guardar el resultado
            save_path = filedialog.asksaveasfilename(
                defaultextension=".xlsx",
                initialfile="tabla_unificada.xlsx",
                filetypes=[("Excel files", "*.xlsx")]
            )
            
            if save_path:
                # Crear un nuevo ExcelWriter con el motor openpyxl
                writer = pd.ExcelWriter(save_path, engine='openpyxl')
                
                # Guardar el DataFrame
                merged_df.to_excel(writer, index=False, sheet_name='Datos Unificados')
                
                # Obtener la hoja de trabajo
                worksheet = writer.sheets['Datos Unificados']
                
                # Ajustar el ancho de las columnas
                for idx, column in enumerate(merged_df.columns, 1):
                    column_width = min(self.get_column_width(merged_df[column]), 50)
                    worksheet.column_dimensions[get_column_letter(idx)].width = column_width
                
                # Guardar y cerrar el archivo
                writer.close()
                
                messagebox.showinfo(
                    "Éxito",
                    f"Archivo guardado exitosamente en:\n{save_path}"
                )
                
        except Exception as e:
            messagebox.showerror("Error", f"Error al unificar archivos:\n{str(e)}")
            raise  # Esto nos ayudará a ver el error completo en la consola

def main():
    root = tk.Tk()
    app = ExcelMergeApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()