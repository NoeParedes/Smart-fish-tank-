import os

# Archivo central de configuración.
# Puedes cambiar aquí las IPs y puertos y reiniciar la app.

# Base de datos
DATABASE = os.environ.get('DATABASE_FILE', 'icc_database.db')

# MQTT
MQTT_BROKER = os.environ.get('MQTT_BROKER', '192.168.18.215')  # Cambia aquí la IP del broker
MQTT_PORT = int(os.environ.get('MQTT_PORT', 1883))
MQTT_TOPIC_HUMEDAD = os.environ.get('MQTT_TOPIC_HUMEDAD', 'pecera/humedad')
MQTT_TOPIC_ULTRASONICO = os.environ.get('MQTT_TOPIC_ULTRASONICO', 'pecera/ultrasonico')
MQTT_TOPIC_CALIDAD = os.environ.get('MQTT_TOPIC_CALIDAD', 'pecera/calidad')

# Cámara (stream ESP32)
CAMERA_DEFAULT_URL = os.environ.get('CAMERA_DEFAULT_URL', 'http://172.20.10.3:81/stream')

# Agrupados opcionalmente
MQTT_TOPICS = {
    'humedad': MQTT_TOPIC_HUMEDAD,
    'ultrasonico': MQTT_TOPIC_ULTRASONICO,
    'calidad': MQTT_TOPIC_CALIDAD,
}
