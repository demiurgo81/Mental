import tkinter as tk
from tkinter import filedialog, messagebox
import pandas as pd
import tabula
import re
from datetime import datetime

def extract_pdf_data(file_path):
    # Extract tables from the PDF using tabula
    tables = tabula.read_pdf(file_path, pages='all', multiple_tables=True)

    extracted_data = []
    for df in tables:
        # Validate that the table has exactly 9 columns
        if len(df.columns) == 9:
            # If any row has fewer than 9 fields, pad it with empty strings
            df = df.apply(lambda x: x if len(x) == 9 else x.append(pd.Series([""] * (9 - len(x)))), axis=1)
            extracted_data.append(df)

    # Combine all extracted tables into one DataFrame, ignoring the original indices
    if extracted_data:
        full_data = pd.concat(extracted_data, ignore_index=True)
        return full_data
    else:
        return None

def clean_data(df):
    # Keep only alphanumeric characters, spaces, dots, and commas in 'cadena carácter' fields
    df.iloc[:, [0, 2, 5]] = df.iloc[:, [0, 2, 5]].apply(lambda x: x.str.upper().str.replace(r'[^A-Z0-9 .,]', '', regex=True))
    
    # Convert number fields to contain only numbers, dots, and commas
    df.iloc[:, [3, 4, 6, 7, 8]] = df.iloc[:, [3, 4, 6, 7, 8]].apply(lambda x: x.replace(r'[^0-9.,]', '', regex=True))

    # Strip leading/trailing spaces and collapse multiple spaces into one
    df = df.apply(lambda x: x.str.strip().str.replace(r'\s+', ' ', regex=True) if x.dtype == "object" else x)

    # Convert 'Fecha' column to the desired format (dd/mm/yyyy) and timezone GMT-5
    df.iloc[:, 1] = pd.to_datetime(df.iloc[:, 1], errors='coerce').dt.strftime('%d/%m/%Y')
    
    return df

def save_csv(df, separator):
    # Prompt user to save the file
    file_path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
    if file_path:
        # Save the DataFrame to a CSV file
        df.to_csv(file_path, index=False, sep=separator, encoding='utf-8')
        messagebox.showinfo("Success", f"File saved successfully at {file_path}")

def process_pdf():
    file_path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
    if file_path:
        # Extract and clean data
        data = extract_pdf_data(file_path)
        if data is not None:
            data = clean_data(data)
            # Show success message with details
            messagebox.showinfo("Extraction Complete", f"Total records extracted: {len(data)}")
            # Ask for separator option
            separator = separator_var.get()
            save_csv(data, separator)
        else:
            messagebox.showwarning("No Tables Found", "No tables with exactly 9 columns were found in the PDF.")

# Set up the main application window
root = tk.Tk()
root.title("PDF Transaction Extractor")

separator_var = tk.StringVar(value=';')

tk.Label(root, text="Select CSV Separator:").pack(pady=10)
separator_entry = tk.Entry(root, textvariable=separator_var).pack(pady=5)

process_btn = tk.Button(root, text="Process PDF", command=process_pdf)
process_btn.pack(pady=20)

root.mainloop()
