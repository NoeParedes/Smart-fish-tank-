// mega_multi_sensors.ino
#include <Arduino.h>

// Ultrasónico
const int TRIG_PIN = 9;
const int ECHO_PIN = 10;

// Humedad analógica
const int HUMIDITY_PIN = A0;
const int HUMIDITY_WET = 320;   // Ajusta con tu sensor sumergido
const int HUMIDITY_DRY = 860;   // Ajusta con el sensor totalmente seco

// Calidad (TDS)
const int TDS_PIN = A1;
const float VREF = 5.0;
const float ADC_RES = 1023.0;
const float WATER_TEMP_C = 25.0;      // Ajusta si tienes un sensor de temperatura real

const unsigned long SAMPLE_INTERVAL_MS = 3000;
unsigned long lastSample = 0;

long measureDistanceCm() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000UL); // timeout ≈5 m
  if (duration == 0) return -1;
  return duration / 58;
}

int readHumidityRaw() {
  return analogRead(HUMIDITY_PIN);
}

float convertHumidityPercent(int raw) {
  float pct = map(raw, HUMIDITY_WET, HUMIDITY_DRY, 100, 0);
  return constrain(pct, 0, 100);
}

int readTdsRaw() {
  return analogRead(TDS_PIN);
}

float computeTdsPpm(int raw, float tempC) {
  float voltage = (raw * VREF) / ADC_RES;
  float compensation = 1.0 + 0.02 * (tempC - 25.0);
  float compensatedVoltage = voltage / compensation;
  float tds = (133.42 * pow(compensatedVoltage, 3) - 255.86 * pow(compensatedVoltage, 2) + 857.39 * compensatedVoltage) * 0.5;
  return max(tds, 0.0f);
}

void sendFrame(const char* label, const String& json) {
  Serial1.print(label);
  Serial1.print("|");
  Serial1.println(json);
  Serial.print(label);
  Serial.print(" -> ");
  Serial.println(json);
}

String buildUltrasonicJson(float distanceCm) {
  String json = "{\"distance_cm\":";
  json += String(distanceCm, 1);
  json += ",\"nivel\":";
  json += String(distanceCm, 1);
  json += "}";
  return json;
}

String buildHumidityJson(float humidityPct, int raw) {
  String json = "{\"humedad_suelo\":";
  json += String(humidityPct, 1);
  json += ",\"raw\":";
  json += raw;
  json += "}";
  return json;
}

String buildTdsJson(float tdsPpm, int raw) {
  String json = "{\"calidad\":";
  json += String(tdsPpm, 0);
  json += ",\"tds_raw\":";
  json += raw;
  json += "}";
  return json;
}

void setup() {
  Serial.begin(115200);
  Serial1.begin(115200);       // UART hacia ESP32 (TX1=18, RX1=19)
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);
  digitalWrite(TRIG_PIN, LOW);
  Serial.println("Mega listo. Midiendo sensores...");
}

void loop() {
  if (millis() - lastSample < SAMPLE_INTERVAL_MS) return;
  lastSample = millis();

  long distance = measureDistanceCm();
  int humidityRaw = readHumidityRaw();
  float humidityPct = convertHumidityPercent(humidityRaw);
  int tdsRaw = readTdsRaw();
  float tdsPpm = computeTdsPpm(tdsRaw, WATER_TEMP_C);

  if (distance >= 0) {
    sendFrame("ULT", buildUltrasonicJson(distance));
  } else {
    Serial.println("Ultrasonico: sin eco");
  }

  sendFrame("HUM", buildHumidityJson(humidityPct, humidityRaw));
  sendFrame("TDS", buildTdsJson(tdsPpm, tdsRaw));
}