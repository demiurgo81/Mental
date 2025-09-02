import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from tkinter import filedialog
import tkinter as tk

def replicate_excel_to_gsheet(excel_path, sheet_id):
    # Leer todas las hojas del archivo Excel
    xls = pd.ExcelFile(excel_path)
    
    # Autenticación con Google Sheets API
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    
    # Abrir el cuadro de diálogo para seleccionar el archivo Excel
    file_path = filedialog.askopenfilename(filetypes=[("Json", "*.json")])
    creds = Credentials.from_service_account_file(file_path, scopes=scopes)
    #creds = Credentials.from_service_account_file(r'D:\OneDrive\Documentos\Phyton\credentials.json', scopes=scopes)
    client = gspread.authorize(creds)

    try:
        # Intentar abrir el Google Sheet existente
        sheet = client.open_by_key(sheet_id)

        # Obtener el URL del Google Sheet
        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
        print(f"Google Sheet abierto: {sheet_url}")

        # Obtener todas las hojas de cálculo actuales del Google Sheet
        worksheets = sheet.worksheets()

        # Mantener la primera hoja y eliminar las demás
        for worksheet in worksheets[1:]:
            sheet.del_worksheet(worksheet)

        # Vaciar la primera hoja
        worksheet = worksheets[0]
        worksheet.clear()
        worksheet.update_title(xls.sheet_names[0])  # Renombrar la primera hoja con el nombre de la primera hoja del Excel

        # Iterar sobre cada hoja en el archivo Excel y replicarla en Google Sheets
        for i, sheet_name in enumerate(xls.sheet_names):
            # Leer la hoja en un DataFrame
            df = pd.read_excel(xls, sheet_name=sheet_name)
            
            # Convertir todos los Timestamps a cadenas de texto
            df = df.astype(str)
            
            # Reemplazar los NaN con una cadena vacía
            df = df.fillna('')

            if i == 0:
                # Si es la primera hoja, usar la hoja vacía existente
                worksheet = worksheets[0]
            else:
                # Crear una nueva hoja en el Google Sheet para las demás
                worksheet = sheet.add_worksheet(title=sheet_name, rows=df.shape[0]+1, cols=df.shape[1])

            # Convertir el DataFrame a una lista de listas
            data = df.values.tolist()

            # Añadir encabezados
            worksheet.update([df.columns.values.tolist()] + data)

        print(f"El archivo Excel se ha replicado exitosamente en la hoja de Google Sheet existente.")

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"No se encontró la hoja de cálculo con el ID {sheet_id}. Verifica que el ID sea correcto.")

# Inicializar Tkinter
root = tk.Tk()
root.withdraw()  # Ocultar la ventana principal de Tkinter

# Abrir el cuadro de diálogo para seleccionar el archivo Excel
file_path = filedialog.askopenfilename(filetypes=[("Excel Files", "*.xlsx")])

# ID de la hoja de Google Sheet existente
sheet_id = '1Nkam5B8sSjOPnnlwNlcMZd0aMr-qoQ0hpW16uTsxEZE' # Reemplaza con el ID correcto

# Replicar el archivo Excel a Google Sheet
replicate_excel_to_gsheet(file_path, sheet_id)
