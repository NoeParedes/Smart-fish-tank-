/*
 * ESP32 - PUENTE MQTT PARA SISTEMA AQUAZEN
 * Conexión: Arduino Mega ↔ ESP32 ↔ MQTT Broker
 * RX2=16, TX2=17 (UART2 hacia Arduino Mega)
 * VERSIÓN MEJORADA: Corrige JSON sin comillas en claves
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ========== CONFIGURACIÓN WiFi ==========
const char* ssid = "JOSE LUIS M ";
const char* password = "lorenasofia";

// ========== CONFIGURACIÓN MQTT ==========
const char* mqtt_server = "192.168.18.215";
const int mqtt_port = 1883;
const char* mqtt_client_id = "AquaZen_ESP32";

// Tópicos MQTT
const char* topic_catcher = "AquaZen/catcher";
const char* topic_sender = "AquaZen/sender";

// ========== CONFIGURACIÓN UART ==========
#define UART_MEGA Serial2
#define UART_BAUD 115200
#define RXD2 16
#define TXD2 17

// ========== OBJETOS ==========
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// ========== VARIABLES ==========
String incomingFromMega = "";
unsigned long lastReconnectAttempt = 0;
unsigned long lastStatusReport = 0;
const unsigned long STATUS_INTERVAL = 30000;

// ========== SETUP ==========
void setup() {
  Serial.begin(115200);
  Serial.println("\n=================================");
  Serial.println("   ESP32 AquaZen MQTT Bridge");
  Serial.println("   VERSIÓN MEJORADA");
  Serial.println("=================================");
  
  UART_MEGA.begin(UART_BAUD, SERIAL_8N1, RXD2, TXD2);
  Serial.println("UART configurado: RX=16, TX=17");
  
  setupWiFi();
  
  mqttClient.setServer(mqtt_server, mqtt_port);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setBufferSize(1024);  // Aumentar buffer
  
  Serial.println("Sistema listo");
  Serial.println("=================================\n");
}

// ========== LOOP PRINCIPAL ==========
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi desconectado. Reconectando...");
    setupWiFi();
  }
  
  if (!mqttClient.connected()) {
    unsigned long now = millis();
    if (now - lastReconnectAttempt > 5000) {
      lastReconnectAttempt = now;
      if (reconnectMQTT()) {
        lastReconnectAttempt = 0;
      }
    }
  } else {
    mqttClient.loop();
  }
  
  leerDatosDelMega();
  enviarEstadoSistema();
}

// ========== CONFIGURACIÓN WiFi ==========
void setupWiFi() {
  delay(10);
  Serial.println("\n--- Conectando a WiFi ---");
  Serial.print("SSID: ");
  Serial.println(ssid);
  
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);
  
  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 30) {
    delay(500);
    Serial.print(".");
    intentos++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✓ WiFi conectado");
    Serial.print("  IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("  RSSI: ");
    Serial.print(WiFi.RSSI());
    Serial.println(" dBm");
  } else {
    Serial.println("\n✗ Error: No se pudo conectar a WiFi");
    Serial.println("  Verificar credenciales y señal");
  }
}

// ========== RECONEXIÓN MQTT ==========
bool reconnectMQTT() {
  Serial.print("Conectando a MQTT broker: ");
  Serial.print(mqtt_server);
  Serial.print(":");
  Serial.println(mqtt_port);
  
  if (mqttClient.connect(mqtt_client_id)) {
    Serial.println("✓ MQTT conectado");
    
    if (mqttClient.subscribe(topic_catcher)) {
      Serial.print("  Suscrito a: ");
      Serial.println(topic_catcher);
    } else {
      Serial.println("  ✗ Error al suscribirse");
    }
    
    StaticJsonDocument<128> doc;
    doc["tipo"] = "CONEXION";
    doc["estado"] = "ONLINE";
    doc["ip"] = WiFi.localIP().toString();
    doc["rssi"] = WiFi.RSSI();
    doc["timestamp"] = millis();
    
    String output;
    serializeJson(doc, output);
    mqttClient.publish(topic_sender, output.c_str());
    
    return true;
  } else {
    Serial.print("✗ Error de conexión MQTT, rc=");
    Serial.println(mqttClient.state());
    return false;
  }
}

// ========== FUNCIÓN PARA CORREGIR JSON SIN COMILLAS ==========
String corregirJSON(String json) {
  // Si ya tiene comillas dobles en las claves, no hacer nada
  if (json.indexOf("\"tipo\"") >= 0) {
    Serial.println("  JSON ya tiene formato correcto");
    return json;
  }
  
  Serial.println("  Corrigiendo formato JSON...");
  
  // Reemplazar claves sin comillas por claves con comillas
  json.replace("tipo:", "\"tipo\":");
  json.replace("evento:", "\"evento\":");
  json.replace("duracion:", "\"duracion\":");
  json.replace("hora:", "\"hora\":");
  json.replace("id:", "\"id\":");
  json.replace("estado:", "\"estado\":");
  json.replace("mensaje:", "\"mensaje\":");
  
  // Agregar comillas a valores string (detectar valores entre comas o antes de })
  // Patrón: "clave":VALOR (donde VALOR no empieza con número, true, false, null, { o [)
  
  // Método simplificado: buscar patrones específicos
  json.replace(":EXCEPCIONAL", ":\"EXCEPCIONAL\"");
  json.replace(":BOMBA6", ":\"BOMBA6\"");
  json.replace(":BOMBA7", ":\"BOMBA7\"");
  json.replace(":SERVO", ":\"SERVO\"");
  json.replace(":AUTOMATICO", ":\"AUTOMATICO\"");
  json.replace(":VACIAR", ":\"VACIAR\"");
  json.replace(":RELLENAR", ":\"RELLENAR\"");
  json.replace(":REINICIAR", ":\"REINICIAR\"");
  json.replace(":CANCELAR", ":\"CANCELAR\"");
  
  Serial.print("  JSON corregido: ");
  Serial.println(json);
  
  return json;
}

// ========== CALLBACK MQTT (Recibir comandos) - CON CORRECCIÓN DE JSON ==========
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  Serial.print("\n[MQTT] Mensaje recibido en: ");
  Serial.println(topic);
  Serial.print("  Longitud: ");
  Serial.println(length);
  
  // Limpiar buffer y convertir payload a String
  String mensaje = "";
  mensaje.reserve(length + 1);  // Pre-asignar memoria
  
  for (unsigned int i = 0; i < length; i++) {
    char c = (char)payload[i];
    // Filtrar caracteres no imprimibles excepto espacios y caracteres JSON válidos
    if (c >= 32 && c <= 126) {
      mensaje += c;
    }
  }
  
  mensaje.trim();  // Eliminar espacios al inicio y final
  
  Serial.print("  Contenido original: ");
  Serial.println(mensaje);
  
  // Validar que sea del tópico correcto y que el mensaje sea válido
  if (String(topic) == topic_catcher && mensaje.length() > 0) {
    
    // NUEVO: Intentar corregir JSON sin comillas
    String mensajeCorregido = corregirJSON(mensaje);
    
    // Validar que sea JSON válido después de la corrección
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, mensajeCorregido);
    
    if (error) {
      Serial.print("  ✗ JSON inválido incluso después de corrección: ");
      Serial.println(error.c_str());
      Serial.print("  Mensaje rechazado: ");
      Serial.println(mensajeCorregido);
      
      // Enviar error a MQTT
      StaticJsonDocument<256> errorDoc;
      errorDoc["tipo"] = "ERROR";
      errorDoc["mensaje"] = "JSON inválido recibido";
      errorDoc["error"] = error.c_str();
      errorDoc["original"] = mensaje;
      errorDoc["timestamp"] = millis();
      
      String errorMsg;
      serializeJson(errorDoc, errorMsg);
      mqttClient.publish(topic_sender, errorMsg.c_str());
      return;
    }
    
    // JSON válido, reenviar al Arduino Mega (usar versión corregida)
    UART_MEGA.println(mensajeCorregido);
    Serial.println("  ✓ Comando validado y enviado al Mega");
    
    // Confirmar recepción a MQTT
    StaticJsonDocument<256> ackDoc;
    ackDoc["tipo"] = "ACK";
    ackDoc["mensaje"] = "Comando validado y reenviado";
    ackDoc["comando"] = doc["tipo"].as<String>();
    ackDoc["timestamp"] = millis();
    
    String ack;
    serializeJson(ackDoc, ack);
    mqttClient.publish(topic_sender, ack.c_str());
  }
}

// ========== LEER DATOS DEL ARDUINO MEGA ==========
void leerDatosDelMega() {
  while (UART_MEGA.available()) {
    char c = UART_MEGA.read();
    
    if (c == '\n') {
      if (incomingFromMega.length() > 0) {
        procesarMensajeMega(incomingFromMega);
        incomingFromMega = "";
      }
    } else if (c >= 32 && c <= 126) {  // Solo caracteres imprimibles
      incomingFromMega += c;
    }
  }
}

// ========== PROCESAR MENSAJE DEL MEGA ==========
void procesarMensajeMega(String mensaje) {
  Serial.print("[MEGA] ");
  Serial.println(mensaje);
  
  int inicioCorchete = mensaje.indexOf('[');
  int finCorchete = mensaje.indexOf(']');
  
  if (inicioCorchete >= 0 && finCorchete > inicioCorchete) {
    String tipoSensor = mensaje.substring(inicioCorchete + 1, finCorchete);
    String jsonData = mensaje.substring(finCorchete + 1);
    jsonData.trim();
    
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, jsonData);
    
    if (!error) {
      bool publicado = mqttClient.publish(topic_sender, jsonData.c_str());
      
      if (publicado) {
        Serial.print("  → Publicado en MQTT [");
        Serial.print(tipoSensor);
        Serial.println("]");
      } else {
        Serial.println("  ✗ Error al publicar en MQTT");
      }
    } else {
      Serial.print("  ✗ Error parseando JSON: ");
      Serial.println(error.c_str());
    }
  } else {
    // Mensaje sin formato de frame, validar JSON antes de publicar
    StaticJsonDocument<512> doc;
    DeserializationError error = deserializeJson(doc, mensaje);
    
    if (!error) {
      mqttClient.publish(topic_sender, mensaje.c_str());
    }
  }
}

// ========== ENVIAR ESTADO DEL SISTEMA ==========
void enviarEstadoSistema() {
  unsigned long ahora = millis();
  
  if (ahora - lastStatusReport >= STATUS_INTERVAL) {
    lastStatusReport = ahora;
    
    StaticJsonDocument<256> doc;
    doc["tipo"] = "ESTADO_ESP32";
    doc["wifi_conectado"] = (WiFi.status() == WL_CONNECTED);
    doc["mqtt_conectado"] = mqttClient.connected();
    doc["ip"] = WiFi.localIP().toString();
    doc["rssi"] = WiFi.RSSI();
    doc["uptime"] = millis() / 1000;
    doc["heap_libre"] = ESP.getFreeHeap();
    doc["timestamp"] = millis();
    
    String output;
    serializeJson(doc, output);
    
    if (mqttClient.connected()) {
      mqttClient.publish(topic_sender, output.c_str());
      Serial.println("[INFO] Estado del sistema enviado a MQTT");
    }
  }
}