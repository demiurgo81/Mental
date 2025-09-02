import csv
import os
from tkinter import Tk, filedialog
from PyPDF2 import PdfReader

def extract_pdf_table(pdf_path):
    # Abrir el archivo PDF
    with open(pdf_path, 'rb') as file:
        reader = PdfReader(file)

        # Extraer la tabla
        table_data = []
        for page_num in range(1, len(reader.pages)):
            page = reader.pages[page_num]
            table_rows = page.extract_text().split('\n')

            if 'Tarjeta' in table_rows[0]:
                for row in table_rows[1:]:
                    if row.strip():
                        row_data = [cell.strip() for cell in row.split('\t')]
                        table_data.append(row_data)

    return table_data

def save_to_csv(table_data, save_path):
    with open(save_path, 'w', newline='') as file:
        writer = csv.writer(file, delimiter=';')

        # Escribir los encabezados
        writer.writerow(['Tarjeta', 'Fecha', 'Descripción', 'Valor transacción', 'Capital facturado del periodo',
                        'Cuotas', 'Capital pendiente por facturar', 'Tasa M.V', 'Tasa E.A'])

        # Escribir los datos de la tabla
        for row in table_data:
            # Formatear los valores numéricos
            row[3] = row[3].replace('$', '').replace(',', '.')
            row[4] = row[4].replace('$', '').replace(',', '.')
            row[6] = row[6].replace('$', '').replace(',', '.')
            row[7] = row[7].replace('%', '').replace(',', '.')
            row[8] = row[8].replace('%', '').replace(',', '.')

            writer.writerow(row)

    print(f"El archivo CSV se ha guardado en: {save_path}")

def main():
    # Abrir el explorador de archivos para seleccionar el archivo PDF
    root = Tk()
    root.withdraw()
    pdf_path = filedialog.askopenfilename(title="Selecciona el archivo PDF", filetypes=[("Archivos PDF", "*.pdf")])

    if pdf_path:
        # Extraer la tabla del PDF
        table_data = extract_pdf_table(pdf_path)

        # Guardar la tabla en un archivo CSV
        save_path = filedialog.asksaveasfilename(title="Guardar archivo CSV", defaultextension=".csv",
                                                filetypes=[("Archivos CSV", "*.csv")])
        if save_path:
            save_to_csv(table_data, save_path)

if __name__ == "__main__":
    main()