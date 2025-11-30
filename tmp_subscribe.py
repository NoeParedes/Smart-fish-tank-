import time
import paho.mqtt.client as mqtt

broker = "192.168.34.100"
topics = ["pecera/humedad", "pecera/ultrasonico", "pecera/calidad"]

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

def on_connect(cl, userdata, flags, reason_code, properties=None):
    print(f"[diag] conectado rc={reason_code}")
    for topic in topics:
        cl.subscribe(topic)
        print(f"[diag] suscrito a {topic}")


def on_message(cl, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
    except UnicodeDecodeError:
        payload = msg.payload.decode("latin1", errors="ignore")
    print(f"[diag] {msg.topic}: {payload}")

client.on_connect = on_connect
client.on_message = on_message
client.connect(broker, 1883, 60)
client.loop_start()
try:
    time.sleep(10)
finally:
    client.loop_stop()
    client.disconnect()
    print("[diag] fin")
