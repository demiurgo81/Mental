import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import os
import sys

def get_base_path():
    """Obtiene la ruta base del ejecutable desempaquetado"""
    try:
        base_path = sys._MEIPASS  # Ruta temporal al desempaquetar
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return base_path

def create_executable():
    script_path = filedialog.askopenfilename(
        title="Seleccionar script Python",
        filetypes=[("Python files", "*.py")]
    )
    if not script_path:
        return

    # Rutas críticas
    base_path = get_base_path()
    python_exe = os.path.join(base_path, "Python", "python.exe")
    pyinstaller_script = os.path.join(base_path, "Lib", "site-packages", "PyInstaller", "__main__.py")

    # Directorio de salida
    output_dir = os.path.join(base_path, "Generated_Executables")
    os.makedirs(output_dir, exist_ok=True)

    # Comando para PyInstaller
    command = [
        python_exe,
        pyinstaller_script,
        "--onefile",
        "--noconsole",
        f"--distpath={output_dir}",
        f"--workpath={os.path.join(output_dir, 'build')}",
        f"--specpath={output_dir}",
        "--clean",
        script_path
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8"
        )
        messagebox.showinfo("Éxito", f"Ejecutable generado en:\n{output_dir}")
    except subprocess.CalledProcessError as e:
        error_msg = f"Error al empaquetar:\n{e.stderr}" if e.stderr else str(e)
        messagebox.showerror("Error crítico", error_msg)

if __name__ == "__main__":
    root = tk.Tk()
    root.title("MetaPackager Portable")
    tk.Button(
        root,
        text="Seleccionar script y generar ejecutable",
        command=create_executable,
        padx=20,
        pady=10
    ).pack(pady=50)
    root.mainloop()