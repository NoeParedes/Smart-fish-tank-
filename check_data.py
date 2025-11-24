import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

print('=== DATOS RECIENTES ===')

print('\n📊 HUMEDAD:')
cursor.execute('SELECT * FROM lecturas_humedad ORDER BY fecha_hora DESC LIMIT 3')
for row in cursor.fetchall():
    print(f"  {row}")

print('\n🧪 CALIDAD:')
cursor.execute('SELECT * FROM lecturas_calidad ORDER BY fecha_hora DESC LIMIT 3')
for row in cursor.fetchall():
    print(f"  {row}")

print('\n📏 ULTRASONICO:')
cursor.execute('SELECT * FROM lecturas_ultrasonico ORDER BY fecha_hora DESC LIMIT 3')
for row in cursor.fetchall():
    print(f"  {row}")

# Verificar total de datos
print('\n=== TOTALES ===')
cursor.execute('SELECT COUNT(*) FROM lecturas_humedad')
print(f"Total humedad: {cursor.fetchone()[0]}")

cursor.execute('SELECT COUNT(*) FROM lecturas_calidad')
print(f"Total calidad: {cursor.fetchone()[0]}")

cursor.execute('SELECT COUNT(*) FROM lecturas_ultrasonico')
print(f"Total ultrasónico: {cursor.fetchone()[0]}")

conn.close()