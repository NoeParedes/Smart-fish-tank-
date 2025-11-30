import os

# Archivo central de configuración.
# Puedes cambiar aquí las IPs y puertos y reiniciar la app.

# Base de datos
DATABASE = os.environ.get('DATABASE_FILE', 'icc_database.db')

# MQTT
MQTT_BROKER = os.environ.get('MQTT_BROKER', '192.168.18.215')  # IP del broker actual
MQTT_PORT = int(os.environ.get('MQTT_PORT', 1883))

# Tópicos unificados
MQTT_TOPIC_SENDER = os.environ.get('MQTT_TOPIC_SENDER', 'AquaZen/sender')
MQTT_TOPIC_CATCHER = os.environ.get('MQTT_TOPIC_CATCHER', 'AquaZen/catcher')

# Cámara (stream ESP32)
CAMERA_DEFAULT_URL = os.environ.get('CAMERA_DEFAULT_URL', 'http://172.20.10.3:81/stream')

# Agrupados opcionalmente
MQTT_TOPICS = {
    'sender': MQTT_TOPIC_SENDER,
    'catcher': MQTT_TOPIC_CATCHER,
}
