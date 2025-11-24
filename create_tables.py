import sqlite3

conn = sqlite3.connect('database.db')
cursor = conn.cursor()

print('Creando tablas originales...')

# Crear tabla lecturas_humedad
cursor.execute('''
    CREATE TABLE IF NOT EXISTS lecturas_humedad (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        humedad REAL NOT NULL,
        fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')

# Crear tabla lecturas_calidad
cursor.execute('''
    CREATE TABLE IF NOT EXISTS lecturas_calidad (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        calidad REAL NOT NULL,
        fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')

# Crear tabla lecturas_ultrasonico
cursor.execute('''
    CREATE TABLE IF NOT EXISTS lecturas_ultrasonico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nivel REAL NOT NULL,
        fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')

# Crear tabla lecturas_temperatura (aunque no la usemos ahora)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS lecturas_temperatura (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        temperatura REAL NOT NULL,
        fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')

conn.commit()

print('Tablas creadas exitosamente!')

# Eliminar las tablas _simple
print('Eliminando tablas _simple...')
try:
    cursor.execute('DROP TABLE IF EXISTS lecturas_humedad_simple')
    cursor.execute('DROP TABLE IF EXISTS lecturas_calidad_simple')
    cursor.execute('DROP TABLE IF EXISTS lecturas_ultrasonico_simple')
    cursor.execute('DROP TABLE IF EXISTS lecturas_temperatura_simple')
    conn.commit()
    print('Tablas _simple eliminadas!')
except Exception as e:
    print(f'Error al eliminar tablas: {e}')

conn.close()