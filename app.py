from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
import sqlite3
from datetime import datetime, timedelta, time, timezone
import os
import json
import paho.mqtt.client as mqtt
import matplotlib
matplotlib.use('Agg')  # Backend sin GUI
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import io
import base64
import numpy as np
from statistics import mean, stdev
from config import (
    DATABASE,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC_HUMEDAD,
    MQTT_TOPIC_ULTRASONICO,
    MQTT_TOPIC_CALIDAD,
    CAMERA_DEFAULT_URL
)

app = Flask(__name__)
app.secret_key = 'secret_key'
app.config['SESSION_TYPE'] = 'filesystem'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # True solo si usas HTTPS

# Context processor global: variables de usuario + configuración cámara
@app.context_processor
def inject_user_context():
    return {
        'tipo_usuario': session.get('tipo_usuario'),
        'nombre_usuario': session.get('nombre_usuario'),
        'camera_default_url': CAMERA_DEFAULT_URL
    }

# Configuración centralizada en config.py (DATABASE, MQTT, CAMERA_DEFAULT_URL)

# Cache en memoria del último mensaje recibido del broker
latest_sensor_data = {
    "humedad_suelo": None,
    "raw": None,
    "nivel": None,
    "calidad": None,
    "timestamp": None
}

# Función para conectar a la base de datos
def get_db_connection():
    try:
        connection = sqlite3.connect(DATABASE)
        connection.row_factory = sqlite3.Row  # Para acceder a columnas por nombre
        return connection
    except Exception as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

# Función para inicializar la base de datos
def init_db():
    crear_nueva = not os.path.exists(DATABASE)
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        
        # Crear tablas
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre VARCHAR(100) NOT NULL,
                correo VARCHAR(150) UNIQUE NOT NULL,
                contrasena VARCHAR(255) NOT NULL,
                tipo_usuario TEXT CHECK(tipo_usuario IN ('admin', 'usuario')) NOT NULL DEFAULT 'usuario',
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aspersores (
                id_aspersor INTEGER PRIMARY KEY AUTOINCREMENT,
                id_usuario INTEGER NOT NULL,
                nombre VARCHAR(100) NOT NULL,
                ubicacion VARCHAR(255),
                estado TEXT CHECK(estado IN ('activo', 'inactivo')) NOT NULL DEFAULT 'inactivo',
                camera_url VARCHAR(255),
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_usuario) REFERENCES usuarios(id_usuario) ON DELETE CASCADE
            )
        ''')
        
        # Agregar columna camera_url si la tabla ya existe
        try:
            cursor.execute("ALTER TABLE aspersores ADD COLUMN camera_url VARCHAR(255)")
        except sqlite3.OperationalError:
            pass  # La columna ya existe
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS programaciones_riego (
                id_programacion INTEGER PRIMARY KEY AUTOINCREMENT,
                id_aspersor INTEGER NOT NULL,
                hora_inicio DATETIME NOT NULL,
                duracion_minutos INTEGER NOT NULL,
                fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_aspersor) REFERENCES aspersores(id_aspersor) ON DELETE CASCADE
            )
        ''')
        
        # Tablas separadas por tipo de sensor
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lecturas_humedad (
                id_lectura INTEGER PRIMARY KEY AUTOINCREMENT,
                id_aspersor INTEGER NOT NULL,
                humedad REAL,
                raw REAL,
                fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_aspersor) REFERENCES aspersores(id_aspersor) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lecturas_ultrasonico (
                id_lectura INTEGER PRIMARY KEY AUTOINCREMENT,
                id_aspersor INTEGER NOT NULL,
                nivel REAL,
                fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_aspersor) REFERENCES aspersores(id_aspersor) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lecturas_calidad (
                id_lectura INTEGER PRIMARY KEY AUTOINCREMENT,
                id_aspersor INTEGER NOT NULL,
                calidad REAL,
                fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_aspersor) REFERENCES aspersores(id_aspersor) ON DELETE CASCADE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS lecturas_calidad (
                id_lectura INTEGER PRIMARY KEY AUTOINCREMENT,
                id_aspersor INTEGER NOT NULL,
                calidad REAL,
                fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (id_aspersor) REFERENCES aspersores(id_aspersor) ON DELETE CASCADE
            )
        ''')
        
        if crear_nueva:
            # Insertar usuarios de prueba solo si la BD es nueva
            cursor.execute('''
                INSERT INTO usuarios (nombre, correo, contrasena, tipo_usuario) VALUES 
                ('Admin Principal', 'admin@irrigo.com', '123', 'admin'),
                ('Usuario Demo', 'usuario@irrigo.com', '123', 'usuario'),
                ('Jaime Farfan', 'jfarfan@utec.edu.pe', '123', 'usuario')
            ''')
        
        connection.commit()
        cursor.close()
        connection.close()
        if crear_nueva:
            print("Base de datos inicializada correctamente")

# Inicializar la base de datos al arrancar
init_db()

# Generar o reutilizar un aspersor por defecto para las lecturas MQTT
default_aspersor_id = None

def ensure_default_aspersor():
    """Garantiza que exista un aspersor para asociar las lecturas MQTT y devuelve su id."""
    global default_aspersor_id
    if default_aspersor_id is not None:
        return default_aspersor_id

    connection = get_db_connection()
    if not connection:
        print("No se pudo obtener conexión para crear aspersor por defecto")
        return None

    cursor = connection.cursor()
    try:
        cursor.execute("SELECT id_aspersor FROM aspersores ORDER BY id_aspersor LIMIT 1")
        row = cursor.fetchone()
        if row:
            default_aspersor_id = row['id_aspersor']
        else:
            # Asegurar que exista algún usuario (toma el primero o crea admin básico)
            cursor.execute("SELECT id_usuario FROM usuarios ORDER BY id_usuario LIMIT 1")
            user = cursor.fetchone()
            if user:
                owner_id = user['id_usuario']
            else:
                cursor.execute("""
                    INSERT INTO usuarios (nombre, correo, contrasena, tipo_usuario)
                    VALUES ('Admin Principal', 'admin@irrigo.com', '123', 'admin')
                """)
                owner_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO aspersores (id_usuario, nombre, ubicacion, estado)
                VALUES (?, 'Aspersor Principal', 'Generado automáticamente', 'inactivo')
            """, (owner_id,))
            default_aspersor_id = cursor.lastrowid
            connection.commit()
    except Exception as e:
        print(f"Error asegurando aspersor por defecto: {e}")
    finally:
        cursor.close()
        connection.close()

    return default_aspersor_id


def store_sensor_reading(humedad_value=None, raw_value=None, nivel_value=None, calidad_value=None):
    """Guarda lecturas del broker en tablas separadas por sensor."""
    aspersor_id = ensure_default_aspersor()
    if aspersor_id is None:
        return

    if all(v is None for v in [humedad_value, raw_value, nivel_value, calidad_value]):
        return

    connection = get_db_connection()
    if not connection:
        print("No se pudo guardar lectura: sin conexión a BD")
        return

    try:
        cursor = connection.cursor()
        if humedad_value is not None:
            cursor.execute("""
                INSERT INTO lecturas_humedad (id_aspersor, humedad)
                VALUES (?, ?)
            """, (aspersor_id, humedad_value))
        if raw_value is not None:
            cursor.execute("""
                INSERT INTO lecturas_humedad (id_aspersor, raw)
                VALUES (?, ?)
            """, (aspersor_id, raw_value))
        if nivel_value is not None:
            cursor.execute("""
                INSERT INTO lecturas_ultrasonico (id_aspersor, nivel)
                VALUES (?, ?)
            """, (aspersor_id, nivel_value))
        if calidad_value is not None:
            cursor.execute("""
                INSERT INTO lecturas_calidad (id_aspersor, calidad)
                VALUES (?, ?)
            """, (aspersor_id, calidad_value))
        connection.commit()
    except Exception as e:
        print(f"Error guardando lectura de sensor: {e}")
    finally:
        cursor.close()
        connection.close()


# --- MQTT Listener ---
mqtt_client = None
_startup_done = False

def start_mqtt_listener():
    """Se suscribe al tópico MQTT y guarda las lecturas en la BD."""
    global mqtt_client
    if mqtt_client is not None:
        return mqtt_client

    client = mqtt.Client(
        client_id="irrigation_webapp",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2
    )

    def on_connect(cl, userdata, flags, reason_code, properties=None):
        print(f"MQTT conectado (reason_code={reason_code})")
        cl.subscribe(MQTT_TOPIC_HUMEDAD)
        cl.subscribe(MQTT_TOPIC_ULTRASONICO)
        cl.subscribe(MQTT_TOPIC_CALIDAD)

    def on_message(cl, userdata, msg):
        try:
            payload = msg.payload.decode('utf-8')
            data = json.loads(payload)
            humedad = raw_value = nivel = calidad = None

            if msg.topic == MQTT_TOPIC_HUMEDAD:
                # Soportar múltiples formatos: {"humedad_suelo": X}, {"value": X}, {"humedad": X}
                humedad = (data.get('humedad_suelo') or 
                          data.get('value') or 
                          data.get('humedad'))
                raw_value = data.get('raw')
                latest_sensor_data['humedad_suelo'] = humedad
                latest_sensor_data['raw'] = raw_value
            elif msg.topic == MQTT_TOPIC_ULTRASONICO:
                # Soportar múltiples posibles claves del payload del sensor ultrasonico
                # Ejemplos aceptados: {"nivel": X}, {"distancia": X}, {"distance_cm": X}, {"distance": X}
                nivel = (data.get('nivel') or
                         data.get('distancia') or
                         data.get('distance_cm') or
                         data.get('distance'))
                # Si aún no se obtuvo, intentar detectar primer valor numérico
                if nivel is None:
                    for v in data.values():
                        if isinstance(v, (int, float)):
                            nivel = v
                            break
                if nivel is None:
                    print(f"MQTT ultrasonico: payload sin clave reconocida {data}")
                latest_sensor_data['nivel'] = nivel
            elif msg.topic == MQTT_TOPIC_CALIDAD:
                # Soportar múltiples formatos: {"calidad": X}, {"valor": X}, {"value": X}
                calidad = (data.get('calidad') or 
                          data.get('valor') or 
                          data.get('value'))
                latest_sensor_data['calidad'] = calidad

            latest_sensor_data['timestamp'] = datetime.now(timezone.utc).isoformat()

            store_sensor_reading(humedad_value=humedad,
                                 raw_value=raw_value,
                                 nivel_value=nivel,
                                 calidad_value=calidad)
            print(f"MQTT mensaje recibido en {msg.topic}: {data}")
        except Exception as e:
            print(f"Error procesando mensaje MQTT: {e}")

    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        mqtt_client = client
        print(f"Escuchando MQTT en {MQTT_BROKER}:{MQTT_PORT} tópico {MQTT_TOPIC_HUMEDAD}")
    except Exception as e:
        print(f"No se pudo conectar al broker MQTT: {e}")

    return mqtt_client


def startup_tasks():
    """Inicia el listener MQTT y prepara el aspersor por defecto."""
    global _startup_done
    if _startup_done:
        return
    # Evitar arranque doble con el reloader en modo debug
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    ensure_default_aspersor()
    start_mqtt_listener()
    _startup_done = True


@app.route('/myprofile')
def myprofile():
    nombre_usuario = session['nombre_usuario']
    tipo_usuario = session['tipo_usuario']
    if 'id_usuario' in session:
        id_usuario = session['id_usuario']
        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT nombre, correo, tipo_usuario, fecha_creacion
                FROM usuarios 
                WHERE id_usuario = ?
            """, (id_usuario,))
            usuario = cursor.fetchone()
            cursor.close()
            connection.close()
            
            return render_template(
                    'myprofile.html',
                    usuario=usuario,  # Datos del usuario desde la base de datos
                    nombre_usuario=session['nombre_usuario'],  # Desde la sesión
                    tipo_usuario=session['tipo_usuario']       # Desde la sesión
                )
        return "Usuario no encontrado", 404
    return redirect('/login')


@app.route('/update_user_info', methods=['PUT'])
def update_user_info():
    if 'id_usuario' in session:  # Verificar si el usuario está autenticado
        data = request.get_json()
        id_usuario = session['id_usuario']
        nombre = data.get('nombre')
        correo = data.get('correo')


        try:
            connection = get_db_connection()
            cursor = connection.cursor()

            if nombre and correo:
                cursor.execute("""
                    UPDATE usuarios 
                    SET nombre = ?, correo = ? 
                    WHERE id_usuario = ?
                """, (nombre, correo, id_usuario))
            elif nombre:
                cursor.execute("""
                    UPDATE usuarios 
                    SET nombre = ? 
                    WHERE id_usuario = ?
                """, (nombre, id_usuario))
            elif correo:
                cursor.execute("""
                    UPDATE usuarios 
                    SET correo = ? 
                    WHERE id_usuario = ?
                """, (correo, id_usuario))

            connection.commit()
            cursor.close()
            connection.close()

            return jsonify({"message": "Información actualizada exitosamente"}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Acceso no autorizado"}), 401

# Ruta para la página de inicio
@app.route('/')
def index():
    return render_template('index.html')

# Compatibilidad con /index.html
@app.route('/index.html')
def index_html():
    return redirect(url_for('index'))

# Ruta para la página de suscripción
@app.route('/subscription')
def subscription():
    selected_plan = request.args.get('plan', '')
    return render_template('subscription.html', selected_plan=selected_plan)

# API para procesar solicitudes de suscripción
@app.route('/api/subscription', methods=['POST'])
def api_subscription():
    try:
        data = request.get_json()
        
        # Extraer datos del formulario
        full_name = data.get('fullName')
        email = data.get('email')
        phone = data.get('phone')
        document_id = data.get('documentId')
        address = data.get('address')
        aquarium_type = data.get('aquariumType')
        tank_size = data.get('tankSize')
        comments = data.get('comments', '')
        plan = data.get('plan')
        price = data.get('price')
        payment_method = data.get('paymentMethod')
        stripe_token = data.get('stripeToken', '')
        
        # Validar datos requeridos
        if not all([full_name, email, phone, document_id, address, aquarium_type, tank_size, plan, price, payment_method]):
            return jsonify({"error": "Faltan campos requeridos"}), 400
        
        # Conectar a la base de datos
        connection = get_db_connection()
        if not connection:
            return jsonify({"error": "Error de conexión a la base de datos"}), 500
        
        try:
            cursor = connection.cursor()
            
            # Crear tabla de solicitudes si no existe
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS solicitudes_suscripcion (
                    id_solicitud INTEGER PRIMARY KEY AUTOINCREMENT,
                    nombre_completo VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    telefono VARCHAR(20) NOT NULL,
                    documento_id VARCHAR(50) NOT NULL,
                    direccion TEXT NOT NULL,
                    tipo_acuario VARCHAR(50) NOT NULL,
                    tamaño_tanque VARCHAR(50) NOT NULL,
                    comentarios TEXT,
                    plan_seleccionado VARCHAR(20) NOT NULL,
                    precio_mensual DECIMAL(10,2) NOT NULL,
                    metodo_pago VARCHAR(20) NOT NULL,
                    stripe_token VARCHAR(255),
                    estado VARCHAR(20) DEFAULT 'pendiente',
                    fecha_solicitud TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insertar la solicitud
            cursor.execute('''
                INSERT INTO solicitudes_suscripcion 
                (nombre_completo, email, telefono, documento_id, direccion, 
                 tipo_acuario, tamaño_tanque, comentarios, plan_seleccionado, 
                 precio_mensual, metodo_pago, stripe_token)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (full_name, email, phone, document_id, address, aquarium_type, 
                  tank_size, comments, plan, float(price), payment_method, stripe_token))
            
            connection.commit()
            solicitud_id = cursor.lastrowid
            
            # Aquí puedes agregar lógica adicional como:
            # - Envío de emails de confirmación
            # - Procesamiento de pagos con Stripe
            # - Notificaciones al equipo de ventas
            
            return jsonify({
                "success": True, 
                "message": "Solicitud procesada exitosamente",
                "solicitud_id": solicitud_id
            }), 200
            
        except Exception as e:
            print(f"Error al procesar solicitud: {e}")
            return jsonify({"error": "Error al procesar la solicitud"}), 500
        finally:
            cursor.close()
            connection.close()
            
    except Exception as e:
        print(f"Error general en API subscription: {e}")
        return jsonify({"error": "Error interno del servidor"}), 500

# Ruta para iniciar sesión
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        correo = request.form['correo']
        contrasena = request.form['contrasena']
        connection = get_db_connection()

        if connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id_usuario, nombre, contrasena, tipo_usuario FROM usuarios WHERE correo = ?", (correo,))
            row = cursor.fetchone()
            cursor.close()
            connection.close()

            print(f"DEBUG - Correo ingresado: {correo}")
            print(f"DEBUG - Usuario encontrado: {row}")
            
            if row and row['contrasena'] == contrasena:  # Sin hash
                session['id_usuario'] = row['id_usuario']
                session['nombre_usuario'] = row['nombre']
                session['tipo_usuario'] = row['tipo_usuario']
                print(f"DEBUG - Login exitoso para: {row['nombre']}")
                return redirect(url_for('dashboard'))
            else:
                print(f"DEBUG - Login fallido")
                flash('Correo o contraseña incorrectos')
        else:
            print("DEBUG - No se pudo conectar a la base de datos")
            flash('Error de conexión a la base de datos')
    return render_template('login.html')

# Ruta para obtener todas las lecturas almacenadas
@app.route('/get_sensor_data', methods=['GET'])
def get_sensor_data():
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT 'humedad' AS tipo_sensor, id_aspersor, humedad AS valor, fecha_hora
            FROM lecturas_humedad
            WHERE humedad IS NOT NULL
            UNION ALL
            SELECT 'raw' AS tipo_sensor, id_aspersor, raw AS valor, fecha_hora
            FROM lecturas_humedad
            WHERE raw IS NOT NULL
            UNION ALL
            SELECT 'nivel' AS tipo_sensor, id_aspersor, nivel AS valor, fecha_hora
            FROM lecturas_ultrasonico
            WHERE nivel IS NOT NULL
            UNION ALL
            SELECT 'calidad' AS tipo_sensor, id_aspersor, calidad AS valor, fecha_hora
            FROM lecturas_calidad
            WHERE calidad IS NOT NULL
            ORDER BY fecha_hora ASC
        """)
        data = cursor.fetchall()
        cursor.close()
        connection.close()
        # Convertir a tipos serializables
        return jsonify([dict(row) for row in data])
    return jsonify({"error": "Error al obtener datos"}), 500


@app.route('/get_latest_sensor_data', methods=['GET'])
def get_latest_sensor_data():
    """Devuelve el último valor recibido del broker MQTT."""
    has_data = not (
        latest_sensor_data['humedad_suelo'] is None and
        latest_sensor_data['raw'] is None and
        latest_sensor_data['nivel'] is None and
        latest_sensor_data['calidad'] is None
    )
    # Siempre devolver 200 para simplificar consumo en frontend
    return jsonify({
        "humedad_suelo": latest_sensor_data['humedad_suelo'],
        "raw": latest_sensor_data['raw'],
        "nivel": latest_sensor_data['nivel'],
        "calidad": latest_sensor_data['calidad'],
        "timestamp": latest_sensor_data['timestamp'],
        "has_data": has_data,
        # compatibilidad con el JS existente
        "moisture1": latest_sensor_data['humedad_suelo'],
        "moisture2": latest_sensor_data['humedad_suelo'],
        "waterLevel": latest_sensor_data['raw'],
    })


@app.route('/sensor_data/humedad', methods=['GET'])
def sensor_data_humedad():
    """Devuelve las últimas lecturas de humedad almacenadas."""
    limit = request.args.get('limit', 50)
    try:
        limit = int(limit)
    except ValueError:
        limit = 50

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT humedad AS valor, fecha_hora AS timestamp
            FROM lecturas_humedad
            WHERE humedad IS NOT NULL
            ORDER BY fecha_hora DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify([{"valor": r["valor"], "timestamp": r["timestamp"]} for r in rows])
    return jsonify({"error": "Error al obtener lecturas de humedad"}), 500

@app.route('/sensor_data/ultrasonico', methods=['GET'])
def sensor_data_ultrasonico():
    """Devuelve las últimas lecturas del sensor ultrasónico."""
    limit = request.args.get('limit', 50)
    try:
        limit = int(limit)
    except ValueError:
        limit = 50

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT nivel AS distance_cm, fecha_hora AS timestamp
            FROM lecturas_ultrasonico
            WHERE nivel IS NOT NULL
            ORDER BY fecha_hora DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify([{"distance_cm": r["distance_cm"], "timestamp": r["timestamp"]} for r in rows])
    return jsonify({"error": "Error al obtener lecturas del sensor ultrasónico"}), 500

@app.route('/sensor_data/temperatura', methods=['GET'])
def sensor_data_temperatura():
    """Devuelve las últimas lecturas de temperatura."""
    limit = request.args.get('limit', 50)
    try:
        limit = int(limit)
    except ValueError:
        limit = 50

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT temperatura AS valor, fecha_hora AS timestamp
            FROM lecturas_temperatura
            WHERE temperatura IS NOT NULL
            ORDER BY fecha_hora DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify([{"valor": r["valor"], "timestamp": r["timestamp"]} for r in rows])
    return jsonify({"error": "Error al obtener lecturas de temperatura"}), 500

@app.route('/sensor_data/calidad', methods=['GET'])
def sensor_data_calidad():
    """Devuelve las últimas lecturas de calidad del agua."""
    limit = request.args.get('limit', 50)
    try:
        limit = int(limit)
    except ValueError:
        limit = 50

    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT calidad AS valor, fecha_hora AS timestamp
            FROM lecturas_calidad
            WHERE calidad IS NOT NULL
            ORDER BY fecha_hora DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify([{"valor": r["valor"], "timestamp": r["timestamp"]} for r in rows])
    return jsonify({"error": "Error al obtener lecturas de calidad del agua"}), 500

@app.route('/get_valve_states', methods=['GET'])
def get_valve_states():
    # Asegúrate de que el usuario esté autenticado
 # Recupera el ID del usuario desde la sesión
    connection = get_db_connection()
    if connection:
        try:
            # Obtener los estados de las primeras dos válvulas (aspersores) del usuario autenticado
            cursor = connection.cursor()
            cursor.execute("""
                SELECT estado
                FROM aspersores
                WHERE id_usuario = 2
                ORDER BY id_aspersor ASC
                LIMIT 2
            """)
            valves = cursor.fetchall()
            cursor.close()
            connection.close()

            # Verificar si hay suficientes válvulas registradas
            if len(valves) >= 2:
                valve1 = valves[0]['estado'] == 'activo'
                valve2 = valves[1]['estado'] == 'activo'
                # La bomba está activa si al menos una válvula está activa
                pump = valve1 or valve2
                return jsonify({"valve1": valve1, "valve2": valve2, "pump": pump}), 200
            else:
                return jsonify({"error": "No hay suficientes aspersores registrados para este usuario."}), 400

        except Error as e:
            print(f"Error al obtener los estados de las válvulas: {e}")
            return jsonify({"error": "Error al consultar la base de datos."}), 500
    else:
        return jsonify({"error": "No se pudo conectar a la base de datos."}), 500


@app.route('/save_sensor_data', methods=['POST'])
def save_sensor_data():
    if request.method == 'POST':
        data = request.get_json()  # Recibir datos en formato JSON
        id_aspersor = data.get('id_aspersor')  # Identificador del aspersor
        tipo_sensor = data.get('tipo_sensor')  # Tipo de sensor (humedad, temperatura, etc.)
        valor_sensor = data.get('valor_sensor')  # Valor leído por el sensor

        # Verificar que todos los campos están presentes
        if not id_aspersor or not tipo_sensor or valor_sensor is None:
            return jsonify({"error": "Datos incompletos"}), 400

        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("""
                    INSERT INTO datos_sensores (id_aspersor, tipo_sensor, valor_sensor)
                    VALUES (?, ?, ?)
                """, (id_aspersor, tipo_sensor, valor_sensor))
                connection.commit()
                cursor.close()
                connection.close()
                return jsonify({"message": "Datos guardados exitosamente"}), 201
            except Exception as e:
                print(f"Error al guardar los datos del sensor: {e}")
                return jsonify({"error": "Error al guardar los datos"}), 500
        else:
            return jsonify({"error": "Error al conectar con la base de datos"}), 500

# Ruta para el dashboard (compartido)
@app.route('/dashboard')
def dashboard():
    if 'id_usuario' in session:
        # Si el usuario es administrador, recupera información adicional
        usuarios = []
        if session['tipo_usuario'] == 'admin':
            connection = get_db_connection()
            if connection:
                cursor = connection.cursor()
                cursor.execute("SELECT id_usuario, nombre, correo, tipo_usuario FROM usuarios WHERE tipo_usuario = 'usuario'")
                usuarios = cursor.fetchall()
                cursor.close()
                connection.close()
        
        # Renderiza el dashboard con usuarios si es admin
        return render_template('dashboard.html', 
                               nombre_usuario=session['nombre_usuario'], 
                               tipo_usuario=session['tipo_usuario'], 
                               usuarios=usuarios)
    else:
        return redirect(url_for('login'))

# Ruta para crear un nuevo usuario
@app.route('/crear_usuario', methods=['GET', 'POST'])
def crear_usuario():
    if 'id_usuario' in session and session['tipo_usuario'] == 'admin':
        if request.method == 'POST':
            # Intentar obtener datos desde `request.json` (fetch) o `request.form` (formulario estándar)
            data = request.json if request.is_json else request.form
            nombre = data.get('nombre')
            correo = data.get('correo')
            contrasena = data.get('contrasena')

            if not nombre or not correo or not contrasena:
                flash('Todos los campos son obligatorios.', 'error')
                return redirect(url_for('users'))

            # Conectar a la base de datos y agregar el usuario
            connection = get_db_connection()
            if connection:
                cursor = connection.cursor()
                try:
                    cursor.execute(
                        "INSERT INTO usuarios (nombre, correo, contrasena, tipo_usuario) VALUES (?, ?, ?, 'usuario')",
                        (nombre, correo, contrasena)
                    )
                    connection.commit()
                    return jsonify({'message': 'Usuario creado exitosamente.'}), 200
                except Exception as e:
                    return jsonify({'error': f'Error al crear el usuario: {str(e)}'}), 500
                finally:
                    cursor.close()
                    connection.close()

        return render_template(
            'users.html',
            nombre_usuario=session.get('nombre_usuario'),
            tipo_usuario=session.get('tipo_usuario')
        )
    else:
        return redirect(url_for('login'))


# Ruta para el dashboard del usuario
@app.route('/usuario')
def usuario_dashboard():
    if 'id_usuario' in session and session['tipo_usuario'] == 'usuario':
        return render_template('usuario_dashboard.html')
    else:
        return redirect(url_for('login'))

# Ruta para cerrar sesión
@app.route('/dashboard/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))



@app.route('/tables')
def tables():
    # Verificación de acceso: solo administradores
    if 'id_usuario' not in session or session.get('tipo_usuario') != 'admin':
        flash('Acceso restringido a administradores.', 'error')
        return redirect(url_for('dashboard'))
    connection = get_db_connection()
    tablas = []
    selected_table = request.args.get('table')
    columnas = []
    filas = []

    if connection:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT name 
            FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        tablas = [row['name'] for row in cursor.fetchall()]
        # Solo consultar si la tabla solicitada existe para evitar inyección
        if selected_table in tablas:
            try:
                cursor.execute(f"PRAGMA table_info({selected_table})")
                columnas = [row['name'] for row in cursor.fetchall()]
                cursor.execute(f"SELECT * FROM {selected_table} LIMIT 200")
                filas = cursor.fetchall()
            except Exception as e:
                print(f"Error al consultar tabla {selected_table}: {e}")
        cursor.close()
        connection.close()

    return render_template('tables.html',
                           tablas=tablas,
                           selected_table=selected_table if selected_table in tablas else None,
                           columnas=columnas,
                           filas=filas)


@app.route('/reset_datos_sensores', methods=['POST'])
def reset_datos_sensores():
    """Elimina todas las filas de la tabla datos_sensores."""
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM datos_sensores")
            connection.commit()
            cursor.close()
        except Exception as e:
            print(f"Error al limpiar datos_sensores: {e}")
        finally:
            connection.close()
    return redirect(url_for('tables', table='datos_sensores'))

@app.route('/reset_lecturas/<sensor_table>', methods=['POST'])
def reset_lecturas(sensor_table):
    """Elimina todas las filas de una tabla de lecturas específica."""
    allowed = {'lecturas_humedad', 'lecturas_ultrasonico', 'lecturas_calidad'}
    if sensor_table not in allowed:
        return redirect(url_for('tables'))

    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute(f"DELETE FROM {sensor_table}")
            connection.commit()
            cursor.close()
        except Exception as e:
            print(f"Error al limpiar {sensor_table}: {e}")
        finally:
            connection.close()
    return redirect(url_for('tables', table=sensor_table))
@app.route('/charts')
def charts():
    sensor_type = request.args.get('sensor')  # Obtener el tipo de sensor desde la URL
    return render_template('charts.html', sensor_type=sensor_type)

#SCHEDULE
@app.route('/save_schedule', methods=['POST'])
def save_schedule():
    if 'id_usuario' not in session:
        return jsonify({"error": "Usuario no autenticado"}), 401

    id_aspersor = request.form.get('id_aspersor')
    hora_inicio = request.form.get('hora_inicio')
    duracion_minutos = request.form.get('duracion_minutos')
    frecuencia = request.form.get('frecuencia')

    if not id_aspersor or not hora_inicio or not duracion_minutos or not frecuencia:
        return jsonify({"error": "Datos incompletos"}), 400

    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("""
                INSERT INTO programaciones_riego (id_aspersor, hora_inicio, duracion_minutos, frecuencia)
                VALUES (?, ?, ?, ?)
            """, (id_aspersor, hora_inicio, duracion_minutos, frecuencia))
            connection.commit()
            cursor.close()
            connection.close()
            flash("Programación guardada exitosamente.", "success")
            return redirect(url_for('calendar', id_aspersor=id_aspersor))
        except Exception as e:
            print(f"Error al guardar la programación: {e}")
            flash("Error al guardar la programación.", "error")
            return redirect(url_for('schedule_irrigation', id_aspersor=id_aspersor))
    else:
        flash("Error al conectar con la base de datos.", "error")
        return redirect(url_for('schedule_irrigation', id_aspersor=id_aspersor))
    
@app.route('/get_schedules', methods=['GET'])
def get_schedules():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT id_programacion, id_aspersor, hora_inicio, duracion_minutos
                FROM programaciones_riego
            """)
            schedules = cursor.fetchall()
            cursor.close()
            connection.close()

            # Convertir campos complejos a tipos básicos
            for schedule in schedules:
                # Convertir `hora_inicio` (DATETIME) a una cadena en formato HH:MM:SS
                if isinstance(schedule['hora_inicio'], datetime):
                    schedule['hora_inicio'] = schedule['hora_inicio'].strftime('%Y-%m-%d %H:%M:?')

                # Asegurar que `duracion_minutos` sea un entero
                schedule['duracion_minutos'] = int(schedule['duracion_minutos'])

            return jsonify(schedules), 200
        except Exception as e:
            print(f"Error al obtener programaciones: {e}")
            return jsonify({"error": "Error al obtener programaciones."}), 500
    else:
        return jsonify({"error": "Error al conectar a la base de datos."}), 500


@app.route('/users', methods=['GET', 'POST'])
def users():
    if 'id_usuario' not in session or session['tipo_usuario'] != 'admin':
        return redirect(url_for('login'))
    
    connection = get_db_connection()

    # Manejar creación de usuario si la solicitud es POST
    if request.method == 'POST':
        data = request.json
        nombre = data.get('nombre')
        correo = data.get('correo')
        contrasena = data.get('contrasena')

        if not (nombre and correo and contrasena):
            return jsonify({"error": "Todos los campos son obligatorios"}), 400

        try:
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO usuarios (nombre, correo, contrasena, tipo_usuario) VALUES (?, ?, ?, 'usuario')",
                (nombre, correo, contrasena)
            )
            connection.commit()
            cursor.close()
            return jsonify({"message": "Usuario creado exitosamente"}), 201
        except Exception as e:
            return jsonify({"error": f"Error al crear el usuario: {str(e)}"}), 500

    # Obtener usuarios para mostrar en la plantilla
    cursor = connection.cursor()
    cursor.execute("SELECT id_usuario, nombre, correo FROM usuarios WHERE tipo_usuario = 'usuario'")
    usuarios = cursor.fetchall()
    cursor.close()
    connection.close()

    return render_template(
        'users.html',
        usuarios=usuarios,
        nombre_usuario=session['nombre_usuario'],
        tipo_usuario=session['tipo_usuario']
    )



@app.route('/layout-static')
def layout_static():
    return render_template('layout-static.html')

@app.route('/layout-sidenav-light')
def layout_sidenav_light(): 
    return render_template('layout-sidenav-light.html')


@app.route('/404')
def error_404():
    return render_template('404.html')

@app.route('/401')
def error_401():
    return render_template('401.html')

@app.route('/500')
def error_500():
    return render_template('500.html')




@app.route('/calendar/<int:id_aspersor>')
def calendar(id_aspersor):
    nombre_usuario = session['nombre_usuario']
    tipo_usuario = session['tipo_usuario']
    return render_template('calendar.html', id_aspersor=id_aspersor, nombre_usuario=nombre_usuario,tipo_usuario=tipo_usuario)

@app.route('/get_programaciones/<int:id_aspersor>')
def get_programaciones(id_aspersor):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT id_programacion, hora_inicio, duracion_minutos, fecha_creacion
            FROM programaciones_riego
            WHERE id_aspersor = ?
        """, (id_aspersor,))
        programaciones = cursor.fetchall()
        cursor.close()
        connection.close()

        # Formatear `hora_inicio` (DATETIME) y otros campos si es necesario
        for programacion in programaciones:
            if 'hora_inicio' in programacion and programacion['hora_inicio'] is not None:
                # Convertir `hora_inicio` (DATETIME) a cadena en formato legible
                programacion['hora_inicio'] = programacion['hora_inicio'].strftime('%Y-%m-%d %H:%M:?')

            if 'fecha_creacion' in programacion and programacion['fecha_creacion'] is not None:
                # Convertir `fecha_creacion` (TIMESTAMP) a cadena
                programacion['fecha_creacion'] = programacion['fecha_creacion'].strftime('%Y-%m-%d %H:%M:?')

        return jsonify(programaciones), 200
    except Exception as e:
        print(f"Error al obtener programaciones: {e}")
        return jsonify({"error": "Error al obtener programaciones."}), 500

@app.route('/save_irrigation_schedule', methods=['POST'])
def save_irrigation_schedule():
    try:
        data = request.get_json()
        id_aspersor = data.get('id_aspersor')
        hora_inicio = data.get('hora_inicio')  # Formato esperado: 'YYYY-MM-DD HH:MM:SS'
        duracion_minutos = data.get('duracion_minutos')

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            INSERT INTO programaciones_riego (id_aspersor, hora_inicio, duracion_minutos)
            VALUES (?, ?, ?)
        """, (id_aspersor, hora_inicio, duracion_minutos))
        connection.commit()
        cursor.close()
        connection.close()

        return jsonify({"message": "Programación de riego guardada exitosamente!"}), 200
    except Error as e:
        return jsonify({"error": str(e)}), 500



@app.route('/get_aspersor_nombre/<int:id_aspersor>')
def get_aspersor_nombre(id_aspersor):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("""
            SELECT nombre FROM aspersores WHERE id_aspersor = ?
        """, (id_aspersor,))
        aspersor = cursor.fetchone()
        cursor.close()
        connection.close()

        if aspersor:
            return jsonify({"nombre": aspersor['nombre']})
        else:
            return jsonify({"error": "Aspersor no encontrado"}), 404
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.route('/delete_programacion/<int:id_programacion>', methods=['DELETE'])
def delete_programacion(id_programacion):
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM programaciones_riego WHERE id_programacion = ?", (id_programacion,))
        connection.commit()
        cursor.close()
        connection.close()
        return jsonify({"success": True})
    except Error as e:
        return jsonify({"error": str(e)}), 500


@app.route('/crear_aspersor/<int:id_usuario>', methods=['POST'])
def crear_aspersor(id_usuario):
    print(f"DEBUG - Inicio crear_aspersor, id_usuario de URL: {id_usuario}")
    print(f"DEBUG - Session data: {dict(session)}")
    
    if 'id_usuario' not in session:
        print("DEBUG - No hay sesión activa, redirigiendo a login")
        return redirect(url_for('login'))

    tipo_usuario = session['tipo_usuario']
    usuario_actual = session['id_usuario']

    print(f"DEBUG - Creando aspersor para id_usuario: {id_usuario}")
    print(f"DEBUG - Usuario que crea: {usuario_actual} (tipo: {tipo_usuario})")

    # Validar permisos
    if tipo_usuario != 'admin' and id_usuario != usuario_actual:
        print(f"DEBUG - Permiso denegado: {tipo_usuario} != 'admin' y {id_usuario} != {usuario_actual}")
        flash('No tienes permiso para crear aspersores para este usuario.', 'error')
        return redirect(url_for('aspersores'))

    # Obtener datos del formulario
    nombre = request.form.get('nombre')
    ubicacion = request.form.get('ubicacion')
    camera_url = request.form.get('camera_url', '').strip()  # Opcional
    
    # Si no se proporciona URL de cámara, usar la URL por defecto centralizada
    if not camera_url:
        camera_url = CAMERA_DEFAULT_URL

    print(f"DEBUG - Datos del formulario - Nombre: {nombre}, Ubicacion: {ubicacion}, Camera URL: {camera_url}")

    if not nombre or not ubicacion:
        flash('Todos los campos son obligatorios.', 'error')
        return redirect(url_for('aspersores', id_usuario=id_usuario))

    connection = get_db_connection()
    if not connection:
        print("DEBUG - Error al conectar con la base de datos")
        flash('Error al conectar con la base de datos.', 'error')
        return redirect(url_for('aspersores'))

    try:
        cursor = connection.cursor()
        print(f"DEBUG - Ejecutando INSERT con valores: id_usuario={id_usuario}, nombre={nombre}, ubicacion={ubicacion}, camera_url={camera_url}")
        cursor.execute("""
            INSERT INTO aspersores (id_usuario, nombre, ubicacion, camera_url)
            VALUES (?, ?, ?, ?)
        """, (id_usuario, nombre, ubicacion, camera_url))
        connection.commit()
        
        print(f"DEBUG - Aspersor creado exitosamente para usuario {id_usuario}")
        
        cursor.close()
        connection.close()

        flash('Aspersor creado exitosamente.', 'success')
        
        # Si es admin y está creando para otro usuario, redirige a users
        # Si es usuario normal o admin creando para sí mismo, redirige a aspersores
        if tipo_usuario == 'admin' and id_usuario != usuario_actual:
            print(f"DEBUG - Admin creando para otro usuario, redirigiendo a /users")
            return redirect(url_for('users'))
        else:
            print(f"DEBUG - Redirigiendo a aspersores del usuario {id_usuario}")
            return redirect(url_for('aspersores', id_usuario=id_usuario))
    except Exception as e:
        print(f"ERROR - al crear aspersor: {e}")
        import traceback
        traceback.print_exc()
        flash('Error al crear el aspersor.', 'error')
        if tipo_usuario == 'admin':
            return redirect(url_for('users'))
        else:
            return redirect(url_for('aspersores'))


@app.route('/aspersores/', defaults={'id_usuario': None}, methods=['GET'])
@app.route('/aspersores/<int:id_usuario>', methods=['GET'])
def aspersores(id_usuario):
    if 'id_usuario' not in session:
        return redirect(url_for('login'))

    tipo_usuario = session['tipo_usuario']
    usuario_actual = session['id_usuario']

    print(f"DEBUG - Accediendo a aspersores. Usuario: {usuario_actual}, Tipo: {tipo_usuario}, ID solicitado: {id_usuario}")

    # Verificar permisos
    if id_usuario is None:
        # Si es admin y no se especifica ID, mostrar TODOS los aspersores
        if tipo_usuario == 'admin':
            id_usuario = 'all'  # Marcador para mostrar todos
        else:
            id_usuario = usuario_actual  # Usuario normal solo ve los suyos
    elif tipo_usuario != 'admin' and id_usuario != usuario_actual:
        flash('No tienes permiso para ver estos aspersores.', 'error')
        return redirect(url_for('aspersores'))

    connection = get_db_connection()
    if not connection:
        flash('Error al conectar con la base de datos.', 'error')
        return redirect(url_for('aspersores'))

    try:
        cursor = connection.cursor()
        
        # Si es admin sin ID específico, mostrar todos los aspersores con info del usuario
        if id_usuario == 'all':
            print("DEBUG - Admin viendo TODOS los aspersores")
            cursor.execute("""
                SELECT a.id_aspersor, a.nombre, a.ubicacion, a.estado, a.id_usuario, a.camera_url, u.nombre as nombre_usuario
                FROM aspersores a
                LEFT JOIN usuarios u ON a.id_usuario = u.id_usuario
                ORDER BY a.id_usuario, a.id_aspersor
            """)
            aspersores = cursor.fetchall()
            mostrar_todos = True
        else:
            print(f"DEBUG - Mostrando aspersores del usuario {id_usuario}")
            cursor.execute("""
                SELECT a.id_aspersor, a.nombre, a.ubicacion, a.estado, a.id_usuario, a.camera_url, u.nombre as nombre_usuario
                FROM aspersores a
                LEFT JOIN usuarios u ON a.id_usuario = u.id_usuario
                WHERE a.id_usuario = ?
                ORDER BY a.id_aspersor
            """, (id_usuario,))
            aspersores = cursor.fetchall()
            mostrar_todos = False
            
        cursor.close()
        connection.close()

        print(f"DEBUG - Se encontraron {len(aspersores)} aspersores")

        id_usuario_visto = None if mostrar_todos else id_usuario
        return render_template('sprinklers.html',
                       aspersores=aspersores,
                       nombre_usuario=session['nombre_usuario'],
                       tipo_usuario=tipo_usuario,
                       mostrar_todos=mostrar_todos,
                       id_usuario_visto=id_usuario_visto)
    except Exception as e:
        print(f"Error al obtener aspersores: {e}")
        flash('Error al obtener los aspersores.', 'error')
        return redirect(url_for('aspersores'))

@app.route('/eliminar_aspersor', methods=['POST'])
def eliminar_aspersor():
    if 'id_usuario' in session:  # Verificar si el usuario está autenticado
        id_usuario = session['id_usuario']
        data = request.get_json()  # Obtener datos del cuerpo de la solicitud
        id_aspersor = data.get('id_aspersor')

        if not id_aspersor:
            return jsonify({"error": "Falta el ID del aspersor"}), 400

        connection = get_db_connection()
        if connection:
            try:
                # Eliminar el aspersor
                cursor = connection.cursor()
                cursor.execute("""
                    DELETE FROM aspersores
                    WHERE id_aspersor = ? 
                """, (id_aspersor,))
                connection.commit()
                cursor.close()
                connection.close()

                return jsonify({"message": "Aspersor eliminado correctamente"}), 200
            except mysql.connector.Error as e:
                print(f"Error al eliminar el aspersor: {e}")
                return jsonify({"error": "Error al eliminar el aspersor"}), 500
        else:
            return jsonify({"error": "Error al conectar con la base de datos"}), 500
    else:
        return jsonify({"error": "Acceso no autorizado"}), 401


@app.route('/actualizar_aspersor', methods=['POST'])
def actualizar_aspersor():
    if 'id_usuario' in session:  # Verificar si el usuario está autenticado
        nombre_usuario = session['nombre_usuario']
        tipo_usuario = session['tipo_usuario']
        id_usuario = session['id_usuario']

        if request.content_type == 'application/json':
            data = request.get_json()
        else:
            data = request.form

        # Obtener los datos enviados por el cliente
        id_aspersor = data.get('id_aspersor')
        nombre = data.get('nombre')
        ubicacion = data.get('ubicacion')
        camera_url = data.get('camera_url', '').strip()  # Opcional

        # Validar que los datos necesarios estén presentes
        if not id_aspersor or not nombre or not ubicacion:
            flash('Datos incompletos. Asegúrate de que todos los campos están llenos.', 'error')
            return redirect(url_for('aspersores'))

        # Conexión a la base de datos para actualizar el aspersor
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("""
                    UPDATE aspersores 
                    SET nombre = ?, ubicacion = ?, camera_url = ?
                    WHERE id_aspersor = ? 
                """, (nombre, ubicacion, camera_url if camera_url else None, id_aspersor))
                connection.commit()
                cursor.close()
            except Error as e:
                print(f"Error al actualizar el aspersor: {e}")
                return jsonify({"message": "Error al actualizar el aspersor. Por favor, inténtalo de nuevo.", "status": "error"}), 500
            finally:
                connection.close()

        # Después de actualizar, recuperar la lista de aspersores actualizada
        connection = get_db_connection()
        aspersores = []
        if connection:
            cursor = connection.cursor()
            cursor.execute("""
                SELECT id_aspersor, nombre, ubicacion, estado
                FROM aspersores
                WHERE id_usuario = ?
            """, (id_usuario,))
            aspersores = cursor.fetchall()
            cursor.close()
            connection.close()

        # Redirigir a la página de aspersores con los datos actualizados
        return jsonify({"message": "Aspersor actualizado exitosamente.", "status": "success"}), 200

    else:
        # Si el usuario no está autenticado, redirigir al inicio de sesión
        flash('Por favor, inicia sesión para continuar.', 'error')
        return redirect(url_for('login'))

@app.route('/actualizar_estado_aspersor', methods=['POST'])
def actualizar_estado_aspersor():
    if 'id_usuario' in session:  # Asegurarse de que el usuario está logueado
        data = request.get_json()
        aspersor_id = data.get('id_aspersor')
        nuevo_estado = data.get('estado')

        connection = get_db_connection()
        if connection:
            cursor = connection.cursor()
            print((nuevo_estado,aspersor_id))
            cursor.execute("UPDATE aspersores SET estado = ? WHERE id_aspersor = ?", (nuevo_estado, aspersor_id))
            connection.commit()
            cursor.close()
            connection.close()

        return jsonify({"message": "Estado actualizado exitosamente"}), 200

    return jsonify({"error": "Acceso no autorizado"}), 401


@app.route('/eliminar_usuario', methods=['POST'])
def eliminar_usuario():
    if 'id_usuario' in session:  # Verificar si el usuario está autenticado
        id_usuario = session['id_usuario']
        data = request.get_json()  # Obtener datos del cuerpo de la solicitud
        id_usuario_a_eliminar = data.get('id_usuario')

        if not id_usuario_a_eliminar:
            return jsonify({"error": "Falta el ID del usuario"}), 400

        connection = get_db_connection()
        if connection:
            try:
                # Eliminar el usuario
                cursor = connection.cursor()
                cursor.execute("""
                    DELETE FROM usuarios
                    WHERE id_usuario = ?
                """, (id_usuario_a_eliminar,))
                connection.commit()
                cursor.close()
                connection.close()

                return jsonify({"message": "Usuario eliminado correctamente"}), 200
            except mysql.connector.Error as e:
                print(f"Error al eliminar el usuario: {e}")
                return jsonify({"error": "Error al eliminar el usuario"}), 500
        else:
            return jsonify({"error": "Error al conectar con la base de datos"}), 500
    else:
        return jsonify({"error": "Acceso no autorizado"}), 401


@app.route('/cambiar_modo', methods=['POST'])
def cambiar_modo():
    data = request.get_json()
    modo = data.get('modo')

    if modo not in ['automatico', 'manual']:
        return jsonify({"error": "Modo no válido"}), 400

    # Aquí puedes agregar la lógica para manejar el modo automático/manual
    # Por ejemplo, guardar el estado en la base de datos o en la sesión

    return jsonify({"message": f"Modo cambiado a {modo}"}), 200

@app.route('/camara/<int:id_aspersor>', methods=['GET'])
def ver_camara(id_aspersor):
    if 'id_usuario' not in session:
        return redirect(url_for('login'))
    
    connection = get_db_connection()
    if not connection:
        flash('Error al conectar con la base de datos.', 'error')
        return redirect(url_for('aspersores'))
    
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT a.nombre, a.camera_url, a.id_usuario 
            FROM aspersores a 
            WHERE a.id_aspersor = ?
        """, (id_aspersor,))
        aspersor = cursor.fetchone()
        cursor.close()
        connection.close()
        
        if not aspersor:
            flash('Aspersor no encontrado.', 'error')
            return redirect(url_for('aspersores'))
        
        # Verificar permisos
        if session['tipo_usuario'] != 'admin' and aspersor['id_usuario'] != session['id_usuario']:
            flash('No tienes permiso para ver esta cámara.', 'error')
            return redirect(url_for('aspersores'))
        
        return render_template('camera.html', 
                             aspersor=aspersor,
                             id_aspersor=id_aspersor,
                             nombre_usuario=session['nombre_usuario'],
                             tipo_usuario=session['tipo_usuario'])
    except Exception as e:
        print(f"Error al obtener información del aspersor: {e}")
        flash('Error al obtener la información del aspersor.', 'error')
        return redirect(url_for('aspersores'))

# Función para generar gráficos para PDF
def generar_grafico_sensor(datos, titulo, ylabel, color='#0369A1', formato_fecha='%H:%M'):
    if not datos:
        return None
    
    plt.style.use('default')
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Procesar datos
    fechas = [datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00')) for item in datos]
    valores = [float(item.get('valor', item.get('distance_cm', 0))) for item in datos]
    
    ax.plot(fechas, valores, color=color, linewidth=2, marker='o', markersize=4)
    ax.fill_between(fechas, valores, alpha=0.3, color=color)
    
    ax.set_title(titulo, fontsize=14, fontweight='bold', pad=20)
    ax.set_xlabel('Tiempo', fontsize=12)
    ax.set_ylabel(ylabel, fontsize=12)
    ax.grid(True, alpha=0.3)
    
    # Formatear fechas en el eje X
    if len(fechas) > 0:
        if (fechas[-1] - fechas[0]).days > 1:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m %H:%M'))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter(formato_fecha))
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    # Guardar como bytes
    buffer = io.BytesIO()
    plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
    buffer.seek(0)
    image_data = buffer.getvalue()
    buffer.close()
    plt.close()
    
    return image_data

# Función para calcular estadísticas
def calcular_estadisticas(datos):
    if not datos:
        return {}
    
    valores = [float(item.get('valor', item.get('distance_cm', 0))) for item in datos]
    
    return {
        'promedio': round(mean(valores), 2) if valores else 0,
        'maximo': round(max(valores), 2) if valores else 0,
        'minimo': round(min(valores), 2) if valores else 0,
        'desviacion': round(stdev(valores), 2) if len(valores) > 1 else 0,
        'total_lecturas': len(valores)
    }

# Ruta para generar reporte PDF
@app.route('/generar_reporte')
def generar_reporte():
    if 'id_usuario' not in session:
        return redirect(url_for('login'))
    
    tipo_usuario = session.get('tipo_usuario', 'usuario')
    nombre_usuario = session.get('nombre_usuario', 'Usuario')
    
    # Obtener parámetros
    dias = request.args.get('dias', 7, type=int)
    fecha_limite = datetime.now() - timedelta(days=dias)
    
    conn = sqlite3.connect('icc_database.db')
    conn.row_factory = sqlite3.Row
    
    # Buffer para el PDF
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch)
    story = []
    styles = getSampleStyleSheet()
    
    # Estilos personalizados
    titulo_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontSize=24,
        textColor=colors.HexColor('#0369A1'),
        spaceAfter=30,
        alignment=1  # Centrado
    )
    
    subtitulo_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#0F4C75'),
        spaceAfter=20
    )
    
    # Título principal
    story.append(Paragraph('🐠 AquaZen - Reporte de Monitoreo', titulo_style))
    story.append(Paragraph(f'Sistema de Acuicultura Inteligente', styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Información del reporte
    info_data = [
        ['Generado para:', nombre_usuario],
        ['Tipo de usuario:', tipo_usuario.title()],
        ['Período analizado:', f'Últimos {dias} días'],
        ['Fecha de generación:', datetime.now().strftime('%d/%m/%Y %H:%M')]
    ]
    
    info_table = Table(info_data, colWidths=[2*inch, 3*inch])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#E0F2FE')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#B4D4DA'))
    ]))
    story.append(info_table)
    story.append(Spacer(1, 30))
    
    # Obtener datos de sensores
    sensores_config = {
        'humedad': {
            'nombre': 'Humedad Relativa',
            'unidad': '%',
            'color': '#059669',
            'rango_optimo': (40, 70),
            'campo_valor': 'humedad',
            'campo_fecha': 'fecha_hora'
        },
        'ultrasonico': {
            'nombre': 'Nivel del Agua',
            'unidad': 'cm',
            'color': '#2563EB',
            'rango_optimo': (15, 25),
            'campo_valor': 'nivel',
            'campo_fecha': 'fecha_hora'
        },
        'calidad': {
            'nombre': 'Calidad del Agua',
            'unidad': 'pH',
            'color': '#7C3AED',
            'rango_optimo': (6.5, 8.0),
            'campo_valor': 'calidad',
            'campo_fecha': 'fecha_hora'
        }
    }
    
    # Resumen ejecutivo para admin
    if tipo_usuario == 'admin':
        story.append(Paragraph('📊 Resumen Ejecutivo', subtitulo_style))
        
        resumen_data = [['Sensor', 'Estado', 'Promedio', 'Lecturas', 'Observaciones']]
        
        for sensor, config in sensores_config.items():
            tabla_sensor = f'lecturas_{sensor}'
            try:
                print(f"DEBUG RESUMEN: Consultando tabla {tabla_sensor}")
                cursor = conn.execute(f"""
                    SELECT {config['campo_valor']} as valor, {config['campo_fecha']} as timestamp
                    FROM {tabla_sensor} 
                    ORDER BY {config['campo_fecha']} DESC
                    LIMIT 50
                """)
                
                datos = [dict(row) for row in cursor.fetchall()]
                print(f"DEBUG RESUMEN: {sensor} - Se encontraron {len(datos)} registros")
                stats = calcular_estadisticas(datos)
                
                if stats and stats['total_lecturas'] > 0:
                    promedio = stats['promedio']
                    rango_min, rango_max = config['rango_optimo']
                    
                    if rango_min <= promedio <= rango_max:
                        estado = '✅ Óptimo'
                    elif promedio < rango_min:
                        estado = '⚠️ Bajo'
                    else:
                        estado = '⚠️ Alto'
                    
                    observacion = f"Rango: {rango_min}-{rango_max} {config['unidad']}"
                else:
                    estado = '❌ Sin datos'
                    promedio = 'N/A'
                    observacion = 'Sin lecturas en el período'
                
                resumen_data.append([
                    config['nombre'],
                    estado,
                    f"{promedio} {config['unidad']}" if promedio != 'N/A' else 'N/A',
                    str(stats.get('total_lecturas', 0)),
                    observacion
                ])
            except:
                resumen_data.append([
                    config['nombre'],
                    '❌ Error',
                    'N/A',
                    '0',
                    'Error al acceder a datos'
                ])
        
        resumen_table = Table(resumen_data, colWidths=[2*inch, 1*inch, 1*inch, 1*inch, 1.5*inch])
        resumen_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0369A1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#B4D4DA')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')])
        ]))
        story.append(resumen_table)
        story.append(Spacer(1, 30))
    
    # Análisis detallado por sensor
    for sensor, config in sensores_config.items():
        if tipo_usuario == 'usuario' and sensor == 'calidad':
            continue  # Los usuarios no ven datos de calidad
        
        story.append(Paragraph(f'📈 {config["nombre"]}', subtitulo_style))
        
        tabla_sensor = f'lecturas_{sensor}'
        try:
            print(f"DEBUG: Consultando tabla {tabla_sensor}")
            cursor = conn.execute(f"""
                SELECT {config['campo_valor']} as valor, {config['campo_fecha']} as timestamp
                FROM {tabla_sensor} 
                ORDER BY {config['campo_fecha']} DESC
                LIMIT 100
            """)
            
            datos = [dict(row) for row in cursor.fetchall()]
            print(f"DEBUG: {sensor} - Se encontraron {len(datos)} registros")
            
            if datos:
                print(f"DEBUG: {sensor} - Primer registro: {datos[0]}")
            else:
                print(f"DEBUG: {sensor} - No se encontraron datos")
            
            
            if datos:
                # Generar gráfico
                imagen_grafico = generar_grafico_sensor(
                    datos, 
                    f'{config["nombre"]} - Últimos {dias} días',
                    f'{config["nombre"]} ({config["unidad"]})',
                    config['color']
                )
                
                if imagen_grafico:
                    # Guardar imagen temporalmente con ruta absoluta
                    import os
                    temp_dir = os.path.dirname(os.path.abspath(__file__))
                    img_path = os.path.join(temp_dir, f'temp_chart_{sensor}.png')
                    
                    with open(img_path, 'wb') as f:
                        f.write(imagen_grafico)
                    
                    # Agregar imagen al PDF
                    story.append(Image(img_path, width=6*inch, height=3.6*inch))
                    story.append(Spacer(1, 10))
                
                # Estadísticas
                stats = calcular_estadisticas(datos)
                
                stats_data = [
                    ['Métrica', 'Valor'],
                    ['Promedio', f"{stats['promedio']} {config['unidad']}"],
                    ['Máximo', f"{stats['maximo']} {config['unidad']}"],
                    ['Mínimo', f"{stats['minimo']} {config['unidad']}"],
                    ['Total de lecturas', str(stats['total_lecturas'])]
                ]
                
                if tipo_usuario == 'admin' and stats['total_lecturas'] > 1:
                    stats_data.append(['Desviación estándar', f"{stats['desviacion']} {config['unidad']}"])
                
                stats_table = Table(stats_data, colWidths=[2*inch, 2*inch])
                stats_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#D1D5DB'))
                ]))
                story.append(stats_table)
            else:
                story.append(Paragraph('No hay datos disponibles para este período.', styles['Normal']))
        except Exception as e:
            story.append(Paragraph(f'Error al procesar datos de {config["nombre"]}: {str(e)}', styles['Normal']))
        
        story.append(Spacer(1, 30))
    
    # Recomendaciones (solo para admin)
    if tipo_usuario == 'admin':
        story.append(Paragraph('💡 Recomendaciones y Alertas', subtitulo_style))
        
        recomendaciones = []
        
        for sensor, config in sensores_config.items():
            tabla_sensor = f'lecturas_{sensor}'
            try:
                cursor = conn.execute(f"""
                    SELECT {config['campo_valor']} as valor, {config['campo_fecha']} as timestamp
                    FROM {tabla_sensor} 
                    WHERE {config['campo_fecha']} >= ? 
                    ORDER BY {config['campo_fecha']} DESC
                    LIMIT 10
                """, (fecha_limite.isoformat(),))
                
                datos = [dict(row) for row in cursor.fetchall()]
                stats = calcular_estadisticas(datos)
                
                if stats and stats['total_lecturas'] > 0:
                    promedio = stats['promedio']
                    rango_min, rango_max = config['rango_optimo']
                    
                    if promedio < rango_min:
                        recomendaciones.append(f"⚠️ {config['nombre']}: Valor bajo ({promedio} {config['unidad']}). Revisar sistema.")
                    elif promedio > rango_max:
                        recomendaciones.append(f"⚠️ {config['nombre']}: Valor alto ({promedio} {config['unidad']}). Ajustar parámetros.")
                    else:
                        recomendaciones.append(f"✅ {config['nombre']}: Funcionando correctamente.")
            except:
                recomendaciones.append(f"⚠️ {config['nombre']}: Error al evaluar datos.")
        
        if not recomendaciones:
            recomendaciones.append("✅ Todos los sistemas funcionan dentro de parámetros normales.")
        
        for rec in recomendaciones:
            story.append(Paragraph(rec, styles['Normal']))
            story.append(Spacer(1, 10))
    
    # Footer
    story.append(Spacer(1, 30))
    story.append(Paragraph('---', styles['Normal']))
    story.append(Paragraph(
        'Reporte generado automáticamente por AquaZen IoT System',
        styles['Normal']
    ))
    
    # Construir PDF
    doc.build(story)
    
    # Limpiar archivos temporales DESPUÉS de construir el PDF
    import glob
    import os
    temp_dir = os.path.dirname(os.path.abspath(__file__))
    temp_files = glob.glob(os.path.join(temp_dir, 'temp_chart_*.png'))
    for temp_file in temp_files:
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception as e:
            print(f"Error al eliminar archivo temporal {temp_file}: {e}")
    
    conn.close()
    
    # Preparar respuesta
    buffer.seek(0)
    filename = f'AquaZen_Reporte_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf'
    )

if __name__ == '__main__':
    startup_tasks()
    app.run(debug=True)
