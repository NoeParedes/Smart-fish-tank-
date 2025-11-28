// esp32_mqtt_bridge.ino
#include <WiFi.h>
#include <PubSubClient.h>

const char* ssid = "omar";
const char* password = "12345678";

const char* mqtt_server = "172.20.10.6";
const int   mqtt_port   = 1883;

const char* topic_ultrasonico = "pecera/ultrasonico";
const char* topic_humedad     = "pecera/humedad";
const char* topic_calidad     = "pecera/calidad";

const int RX_PIN = 16;
const int TX_PIN = 17;

WiFiClient espClient;
PubSubClient client(espClient);
HardwareSerial SerialU(2);

const char* clientId = "ESP32_Pecera_01";

unsigned long lastAttempt = 0;
unsigned long reconnectDelay = 2000;
const unsigned long RECONNECT_DELAY_MAX = 30000;

struct TopicRoute {
  const char* label;
  const char* topic;
};

TopicRoute routes[] = {
  {"ULT", topic_ultrasonico},
  {"HUM", topic_humedad},
  {"TDS", topic_calidad}
};

void setup_wifi() {
  Serial.print("Conectando a "); Serial.println(ssid);
  WiFi.begin(ssid, password);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi conectado. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi: fallo al conectar (timeout)");
  }
}

void reconnect_mqtt_if_needed() {
  if (WiFi.status() != WL_CONNECTED || client.connected()) return;

  unsigned long now = millis();
  if (now - lastAttempt < reconnectDelay) return;

  Serial.println("Intentando conectar MQTT...");
  lastAttempt = now;
  if (client.connect(clientId)) {
    Serial.println("MQTT conectado!");
    reconnectDelay = 2000;
  } else {
    Serial.print("MQTT fallo, estado=");
    Serial.println(client.state());
    reconnectDelay = min(RECONNECT_DELAY_MAX, reconnectDelay * 2);
  }
}

String readLineFromSerialU() {
  static String line = "";
  while (SerialU.available()) {
    char c = (char)SerialU.read();
    if (c == '\n') {
      String out = line;
      line = "";
      return out;
    } else if (c != '\r') {
      line += c;
      if (line.length() > 256) line = line.substring(line.length() - 256);
    }
  }
  return String("");
}

const char* resolveTopic(const String& label) {
  for (TopicRoute& route : routes) {
    if (label.equalsIgnoreCase(route.label)) {
      return route.topic;
    }
  }
  return nullptr;
}

void publishFrame(const String& label, const String& payload) {
  const char* topic = resolveTopic(label);
  if (!topic) {
    Serial.print("Etiqueta desconocida '");
    Serial.print(label);
    Serial.println("' -> ignorado");
    return;
  }
  if (!client.connected()) {
    Serial.println("MQTT desconectado, no se publica");
    return;
  }
  bool ok = client.publish(topic, payload.c_str());
  Serial.print("MQTT ");
  Serial.print(topic);
  Serial.println(ok ? " OK" : " FALLÓ");
}

void setup() {
  Serial.begin(115200);
  SerialU.begin(115200, SERIAL_8N1, RX_PIN, TX_PIN);
  Serial.println("ESP32 puente UART→MQTT");
  client.setServer(mqtt_server, mqtt_port);
  setup_wifi();
}

void loop() {
  client.loop();
  reconnect_mqtt_if_needed();

  String frame = readLineFromSerialU();
  if (frame.length() == 0) {
    delay(5);
    return;
  }

  frame.trim();
  int sep = frame.indexOf('|');
  if (sep < 0) {
    Serial.println("Trama sin separador '|', ignorada");
    return;
  }

  String label = frame.substring(0, sep);
  String payload = frame.substring(sep + 1);

  Serial.print("UART ");
  Serial.print(label);
  Serial.print(" -> ");
  Serial.println(payload);

  publishFrame(label, payload);
}