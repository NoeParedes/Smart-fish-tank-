import sqlite3
from datetime import datetime, timedelta
import random

# Conectar a la base de datos
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

print("Iniciando creación de datos de ejemplo...")

# Limpiar tablas simplificadas existentes
tables = ['lecturas_humedad_simple', 'lecturas_temperatura_simple', 
          'lecturas_ultrasonico_simple', 'lecturas_calidad_simple']

for table in tables:
    try:
        cursor.execute(f'DELETE FROM {table}')
        print(f'Limpiadas tablas: {table}')
    except:
        print(f'Tabla {table} no existe, se creará.')

# Crear las tablas simplificadas
cursor.execute('''
    CREATE TABLE IF NOT EXISTS lecturas_humedad_simple (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        valor REAL,
        timestamp TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS lecturas_temperatura_simple (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        valor REAL,
        timestamp TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS lecturas_ultrasonico_simple (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        distance_cm REAL,
        timestamp TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS lecturas_calidad_simple (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        valor REAL,
        timestamp TEXT
    )
''')

print("Tablas creadas correctamente.")

# Generar datos de ejemplo para las últimas 2 semanas
end_date = datetime.now()
start_date = end_date - timedelta(days=14)
current = start_date

datos_insertados = 0

while current <= end_date:
    # Datos de humedad (45-65%)
    humedad = round(random.uniform(45, 65), 1)
    cursor.execute('INSERT INTO lecturas_humedad_simple (valor, timestamp) VALUES (?, ?)', 
                   (humedad, current.isoformat()))
    
    # Datos de temperatura (23-27°C)
    temperatura = round(random.uniform(23, 27), 1)
    cursor.execute('INSERT INTO lecturas_temperatura_simple (valor, timestamp) VALUES (?, ?)', 
                   (temperatura, current.isoformat()))
    
    # Datos del ultrasónico (16-24cm)
    distancia = round(random.uniform(16, 24), 1)
    cursor.execute('INSERT INTO lecturas_ultrasonico_simple (distance_cm, timestamp) VALUES (?, ?)', 
                   (distancia, current.isoformat()))
    
    # Datos de calidad (6.8-7.8 pH)
    ph = round(random.uniform(6.8, 7.8), 1)
    cursor.execute('INSERT INTO lecturas_calidad_simple (valor, timestamp) VALUES (?, ?)', 
                   (ph, current.isoformat()))
    
    datos_insertados += 4
    current += timedelta(hours=2)

conn.commit()

# Verificar datos insertados
print(f"\nDatos insertados exitosamente! Total de registros: {datos_insertados}")

for table in tables:
    cursor.execute(f'SELECT COUNT(*) FROM {table}')
    count = cursor.fetchone()[0]
    
    cursor.execute(f'SELECT * FROM {table} ORDER BY timestamp DESC LIMIT 3')
    samples = cursor.fetchall()
    
    print(f"\n{table}: {count} registros")
    print("Últimos 3 registros:")
    for sample in samples:
        print(f"  {sample}")

conn.close()
print("\n✅ Base de datos lista para generar reportes!")