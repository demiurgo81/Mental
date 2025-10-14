import pyodbc

conn_str = (
    "DRIVER={Client Access ODBC Driver (32-bit)};"
    "SYSTEM=192.168.60.228;"
    "UID=C38500432;"
    "PWD=Sofia25,.*;"
    "DATABASE=cabledta;"
)

try:
    conn = pyodbc.connect(conn_str)
    cursor = conn.cursor()
    print("✅ Conexión exitosa a AS400")

    # Cambia 'tu_tabla' por el nombre real de la tabla
    cursor.execute("SELECT * FROM cabledta.subsmstr FETCH FIRST 10 ROWS ONLY")
    for row in cursor.fetchall():
        print(row)

    cursor.close()
    conn.close()
    print("🔒 Conexión cerrada correctamente.")
except Exception as e:
    print("❌ Error al conectar:", e)
