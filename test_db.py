import sqlite3
from datetime import datetime, timedelta
import random

# Conectar a la base de datos
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Ver las tablas existentes
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tablas = cursor.fetchall()
print('Tablas existentes:')
for tabla in tablas:
    print(f'- {tabla[0]}')

# Ver estructura de una tabla
print('\nEstructura de lecturas_humedad:')
try:
    cursor.execute('PRAGMA table_info(lecturas_humedad)')
    columnas = cursor.fetchall()
    for col in columnas:
        print(f'- {col[1]} ({col[2]})')
except:
    print('Tabla no existe')

# Generar datos de ejemplo para las últimas 2 semanas
end_date = datetime.now()
start_date = end_date - timedelta(days=14)
current = start_date

print('\nGenerando datos de ejemplo...')

try:
    while current <= end_date:
        # Datos de humedad (40-70%)
        humedad = round(random.uniform(45, 65), 1)
        cursor.execute('INSERT INTO lecturas_humedad (valor, timestamp) VALUES (?, ?)', 
                       (humedad, current.isoformat()))
        
        # Datos de temperatura (22-28°C)
        temperatura = round(random.uniform(23, 27), 1)
        cursor.execute('INSERT INTO lecturas_temperatura (valor, timestamp) VALUES (?, ?)', 
                       (temperatura, current.isoformat()))
        
        # Datos del ultrasónico (15-25cm)
        distancia = round(random.uniform(16, 24), 1)
        cursor.execute('INSERT INTO lecturas_ultrasonico (distance_cm, timestamp) VALUES (?, ?)', 
                       (distancia, current.isoformat()))
        
        # Datos de calidad (6.5-8.0 pH)
        ph = round(random.uniform(6.8, 7.8), 1)
        cursor.execute('INSERT INTO lecturas_calidad (valor, timestamp) VALUES (?, ?)', 
                       (ph, current.isoformat()))
        
        current += timedelta(hours=2)

    conn.commit()
    print('Datos de ejemplo generados exitosamente!')
except Exception as e:
    print(f'Error: {e}')

conn.close()