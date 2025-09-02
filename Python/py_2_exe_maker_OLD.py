import os
import sys
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox

python_base = sys.base_prefix
# Obtener el directorio de instalación de Python
python_base = sys.base_prefix

# Construir las rutas de Tcl y Tk dinámicamente
tcl_dir = os.path.join(python_base, 'tcl', 'tcl8.6')
tk_dir = os.path.join(python_base, 'tcl', 'tk8.6')

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

    # Update status
    status_label.config(text="Generating executable...", fg="blue")
    window.update_idletasks()

    try:
        # Build the PyInstaller command
        output_dir = os.path.dirname(py_file)
        exe_name = os.path.basename(py_file).replace('.py', '.exe')
        exe_output_path = os.path.join(output_dir, exe_name)  # Set the full path for the output exe
        
        pyinstaller_command = [
            'python', '-m', 'PyInstaller',
            '--onefile',
            '--noconfirm',
            '--distpath', output_dir,  # Set the output directory
            '--name', exe_name,        # Name the executable based on the Python file
            #'--paths', tcl_dir,
            #'--paths', tk_dir,
            py_file
        ]

        # Run the PyInstaller command and capture output
        result = subprocess.run(pyinstaller_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if result.returncode == 0:
            status_label.config(text=f"Executable created: {exe_output_path}", fg="green")
        else:
            status_label.config(text="Error in creating executable.", fg="red")
            messagebox.showerror("Error", result.stderr)
    except Exception as e:
        status_label.config(text="An unexpected error occurred.", fg="red")
        messagebox.showerror("Error", str(e))


# Initialize the Tkinter window
window = tk.Tk()
window.title("Python to EXE Converter")
window.geometry("500x200")

# Create a string variable to store the selected Python file path
py_file_path = tk.StringVar()

# Create the GUI components
select_button = tk.Button(window, text="Select Python Script", command=select_py_file)
select_button.pack(pady=10)

status_label = tk.Label(window, text="No file selected.", fg="black")
status_label.pack(pady=5)

convert_button = tk.Button(window, text="Create Executable", command=create_exe)
convert_button.pack(pady=10)

# Start the Tkinter event loop
window.mainloop()