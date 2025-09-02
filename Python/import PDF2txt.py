import tkinter as tk
from tkinter import filedialog, messagebox
from PyPDF2 import PdfReader

def extract_plain_text(file_path):
    # Extract plain text from the PDF using PyPDF2
    reader = PdfReader(file_path)
    full_text = ""
    for page in reader.pages:
        # Check if page has extractable text
        try:
            page_text = page.extract_text()
            if page_text:
                full_text += page_text + "\n"
        except Exception as e:
            print(f"Error extracting text from page: {e}")
    return full_text

def save_plain_text(text):
    # Prompt user to save the plain text file
    file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
    if file_path:
        with open(file_path, "w", encoding="utf-8") as txt_file:
            txt_file.write(text)
        messagebox.showinfo("Success", f"Plain text saved successfully at {file_path}")

def process_pdf():
    # Let the user select a PDF file
    file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
    if file_path:
        # Extract plain text from the PDF
        plain_text = extract_plain_text(file_path)
        if plain_text.strip():
            save_plain_text(plain_text)
        else:
            messagebox.showwarning("No Text Found", "No text could be extracted from the PDF.")

# Set up the main application window
root = tk.Tk()
root.title("PDF Text Extractor")

process_btn = tk.Button(root, text="Select and Extract PDF", command=process_pdf)
process_btn.pack(pady=20)

root.mainloop()
