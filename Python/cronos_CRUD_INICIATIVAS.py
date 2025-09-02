import cx_Oracle
import tkinter as tk
from tkinter import ttk, messagebox
import os

class IniciativaApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Gestión de Iniciativas")
        self.root.geometry("1200x800")
        
        # Configurar variables de entorno para Tcl/Tk
        os.environ['TCL_LIBRARY'] = r'C:\Python312\tcl\tcl8.6'
        os.environ['TK_LIBRARY'] = r'C:\Python312\tcl\tk8.6'
        
        self.font = ('Arial', 10)
        self.title_font = ('Arial', 12, 'bold')
        
        self.create_widgets()
        self.search()

    def create_widgets(self):
        # Frame de búsqueda
        search_frame = ttk.Frame(self.root)
        search_frame.pack(pady=10, padx=10, fill=tk.X)
        
        ttk.Label(search_frame, text="Buscar:", font=self.font).pack(side=tk.LEFT)
        self.search_entry = ttk.Entry(search_frame, width=50, font=self.font)
        self.search_entry.pack(side=tk.LEFT, padx=5)
        self.search_entry.bind('<KeyRelease>', lambda e: self.search())
        
        # Botón Nuevo
        ttk.Button(search_frame, text="Nueva Iniciativa", 
                  command=self.new_iniciativa).pack(side=tk.RIGHT)
        
        # Treeview
        self.tree = ttk.Treeview(self.root, columns=('ID', 'Nombre', 'PEP', 'CodProyecto', 
                                                   'CodGerente', 'Evidencia', 'Lider'), 
                               show='headings')
        
        # Configurar columnas
        columns = [
            ('ID', 50), ('Nombre', 250), ('PEP', 150), ('CodProyecto', 100),
            ('CodGerente', 100), ('Evidencia', 200), ('Lider', 200)
        ]
        for col, width in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, anchor=tk.W)
            
        self.tree.pack(fill=tk.BOTH, expand=1, padx=10, pady=5)
        
        # Eventos
        self.tree.bind('<Double-1>', self.edit_selected)

    def search(self, event=None):
        search_term = f"%{self.search_entry.get()}%"
        
        try:
            connection = conectar_a_bd()
            cursor = connection.cursor()
            
            cursor.execute("""
                SELECT ID, NOMBRE, PEP, CODPROYECTO, CODGERENTE, EVIDENCIA, LIDER_INICIATIVA
                FROM DF_INICIATIVA
                WHERE NOMBRE LIKE :1 OR PEP LIKE :2
                ORDER BY ID
            """, (search_term, search_term))
            
            self.clear_tree()
            
            for row in cursor:
                self.tree.insert('', 'end', values=row)
            
        except cx_Oracle.DatabaseError as e:
            messagebox.showerror("Error", f"Error al buscar datos: {e}")
        finally:
            if 'connection' in locals():
                connection.close()

    def clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def new_iniciativa(self):
        self.open_form("Nueva Iniciativa")
        
    def edit_selected(self, event):
        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0], 'values')
            self.open_form("Editar Iniciativa", values[0])

    def open_form(self, title, iniciativa_id=None):
        form = tk.Toplevel(self.root)
        form.title(title)
        form.geometry("500x400")
        
        fields = [
            ('Nombre', 'entry', None),
            ('PEP', 'entry', None),
            ('CodProyecto', 'entry', 'number'),
            ('CodGerente', 'entry', 'number'),
            ('Evidencia', 'entry', None),
            ('Lider', 'entry', None)
        ]
        
        entries = {}
        for field in fields:
            frame = ttk.Frame(form)
            frame.pack(fill=tk.X, padx=10, pady=5)
            
            ttk.Label(frame, text=f"{field[0]}:", width=15, anchor=tk.W).pack(side=tk.LEFT)
            
            if field[1] == 'entry':
                entry = ttk.Entry(frame, width=30)
                if field[2] == 'number':
                    entry.config(validate='key', 
                               validatecommand=(form.register(self.validate_number), '%P'))
                entry.pack(side=tk.LEFT, expand=1)
                entries[field[0].lower()] = entry
                
        # Cargar datos si es edición
        if iniciativa_id:
            try:
                connection = conectar_a_bd()
                cursor = connection.cursor()
                cursor.execute("""
                    SELECT NOMBRE, PEP, CODPROYECTO, CODGERENTE, EVIDENCIA, LIDER_INICIATIVA
                    FROM DF_INICIATIVA WHERE ID = :1
                """, (iniciativa_id,))
                
                data = cursor.fetchone()
                fields_to_load = ['nombre', 'pep', 'codproyecto', 'codgerente', 'evidencia', 'lider']
                
                for i, field in enumerate(fields_to_load):
                    value = data[i] if data[i] is not None else ""
                    entries[field].delete(0, tk.END)
                    entries[field].insert(0, str(value))
                    
            except cx_Oracle.DatabaseError as e:
                messagebox.showerror("Error", f"Error al cargar datos: {e}")
            finally:
                connection.close()
        
        # Botones
        btn_frame = ttk.Frame(form)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Guardar", 
                  command=lambda: self.save_iniciativa(entries, form, iniciativa_id)).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancelar", 
                  command=form.destroy).pack(side=tk.LEFT)

    def validate_number(self, value):
        return value.isdigit() or value == ""

    def save_iniciativa(self, entries, form, iniciativa_id=None):
        data = {
            'nombre': entries['nombre'].get().strip(),
            'pep': entries['pep'].get().strip(),
            'codproyecto': entries['codproyecto'].get().strip(),
            'codgerente': entries['codgerente'].get().strip(),
            'evidencia': entries['evidencia'].get().strip(),
            'lider': entries['lider'].get().strip()
        }
        
        # Validación
        if not data['nombre'] or not data['codproyecto']:
            messagebox.showwarning("Validación", "Nombre y Código de Proyecto son obligatorios")
            return
            
        try:
            connection = conectar_a_bd()
            cursor = connection.cursor()
            
            if iniciativa_id:
                cursor.execute("""
                    UPDATE DF_INICIATIVA 
                    SET NOMBRE = :1, PEP = :2, CODPROYECTO = :3, 
                        CODGERENTE = :4, EVIDENCIA = :5, LIDER_INICIATIVA = :6
                    WHERE ID = :7
                """, (
                    data['nombre'],
                    data['pep'] or None,
                    int(data['codproyecto']),
                    int(data['codgerente']) if data['codgerente'] else None,
                    data['evidencia'] or None,
                    data['lider'] or None,
                    iniciativa_id
                ))
            else:
                cursor.execute("""
                    INSERT INTO DF_INICIATIVA 
                    (NOMBRE, PEP, CODPROYECTO, CODGERENTE, EVIDENCIA, LIDER_INICIATIVA)
                    VALUES (:1, :2, :3, :4, :5, :6)
                """, (
                    data['nombre'],
                    data['pep'] or None,
                    int(data['codproyecto']),
                    int(data['codgerente']) if data['codgerente'] else None,
                    data['evidencia'] or None,
                    data['lider'] or None
                ))
            
            connection.commit()
            messagebox.showinfo("Éxito", "Operación realizada correctamente")
            form.destroy()
            self.search()
            
        except cx_Oracle.DatabaseError as e:
            messagebox.showerror("Error", f"Error de base de datos: {e}")
            connection.rollback()
        except ValueError as e:
            messagebox.showerror("Error", f"Datos numéricos inválidos: {e}")
        finally:
            if 'connection' in locals():
                connection.close()

def conectar_a_bd():
    try:
        dsn = cx_Oracle.makedsn("100.126.98.25", 1850, service_name="PDB_IVRCONV")
        return cx_Oracle.connect(
            user="PDB_CRONUS",
            password="C7ar0_2o2s",
            dsn=dsn
        )
    except cx_Oracle.DatabaseError as e:
        messagebox.showerror("Error de conexión", f"Error: {e}")
        return None

if __name__ == "__main__":
    root = tk.Tk()
    app = IniciativaApp(root)
    root.mainloop()