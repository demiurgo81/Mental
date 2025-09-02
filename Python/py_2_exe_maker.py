import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox

def select_py_file():
    py_file = filedialog.askopenfilename(
        title="Select Python Script",
        filetypes=[("Python Files", "*.py")]
    )
    if py_file:
        py_file_path.set(py_file)
        status_label.config(text=f"Selected: {os.path.basename(py_file)}")

def create_exe():
    py_file = py_file_path.get()

    if not py_file or not py_file.endswith('.py'):
        messagebox.showerror("Error", "Please select a valid Python (.py) file.")
        return

    status_label.config(text="Generating executable...", fg="blue")
    window.update_idletasks()

    try:
        # Obtener rutas Tcl y Tk usando 'set'
        tcl_dir = window.tk.eval('info library')          # Ruta de Tcl
        tk_dir = window.tk.eval('set ::tk_library')       # Ruta de Tk (corregido)
        
        output_dir = os.path.dirname(py_file)
        exe_name = os.path.basename(py_file).replace('.py', '.exe')
        
        pyinstaller_command = [
            'python', '-m', 'PyInstaller',
            '--onefile',
            '--noconfirm',
            '--distpath', output_dir,
            '--name', exe_name,
            '--paths', tcl_dir,
            '--paths', tk_dir,
            py_file
        ]

        result = subprocess.run(
            pyinstaller_command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )

        if result.returncode == 0:
            final_path = os.path.join(output_dir, exe_name)
            status_label.config(text=f"Executable created: {final_path}", fg="green")
        else:
            status_label.config(text="Error in creating executable.", fg="red")
            messagebox.showerror("Error", result.stderr)
    except Exception as e:
        status_label.config(text="An unexpected error occurred.", fg="red")
        messagebox.showerror("Error", str(e))

# Configuración de la ventana
window = tk.Tk()
window.title("Python to EXE Converter")
window.geometry("500x200")

py_file_path = tk.StringVar()

select_button = tk.Button(window, text="Select Python Script", command=select_py_file)
select_button.pack(pady=10)

status_label = tk.Label(window, text="No file selected.", fg="black")
status_label.pack(pady=5)

convert_button = tk.Button(window, text="Create Executable", command=create_exe)
convert_button.pack(pady=10)

window.mainloop()