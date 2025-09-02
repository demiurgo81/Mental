import tkinter as tk
from tkinter import filedialog, messagebox
from PyPDF2 import PdfReader
import sys
import os

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def extract_plain_text(file_path):
    reader = PdfReader(file_path)
    full_text = ""
    for page in reader.pages:
        try:
            if text := page.extract_text():
                full_text += text + "\n"
        except Exception as e:
            print(f"Error: {e}")
    return full_text

def save_plain_text(text):
    file_path = filedialog.asksaveasfilename(
        defaultextension=".txt",
        filetypes=[("Text files", "*.txt")],
        title="Guardar texto extraído"
    )
    if file_path:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
            messagebox.showinfo("Éxito", f"Archivo guardado en:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar:\n{e}")

def process_pdf():
    file_path = filedialog.askopenfilename(
        title="Seleccionar PDF",
        filetypes=[("PDF files", "*.pdf")]
    )
    if file_path:
        try:
            text = extract_plain_text(file_path)
            if text.strip():
                save_plain_text(text)
            else:
                messagebox.showwarning("Advertencia", "PDF sin texto extraíble")
        except Exception as e:
            messagebox.showerror("Error crítico", f"Error procesando PDF:\n{e}")

if __name__ == "__main__":
    root = tk.Tk()
    root.title("PDF Text Extractor Portable")
    #root.iconbitmap(resource_path("icon.ico"))  # Opcional: añade un icono
    
    tk.Label(
        root,
        text="Seleccione un archivo PDF para extraer su texto",
        padx=20,
        pady=10
    ).pack()
    
    tk.Button(
        root,
        text="Abrir PDF y extraer texto",
        command=process_pdf,
        padx=10,
        pady=5
    ).pack(pady=20)
    
    root.mainloop()