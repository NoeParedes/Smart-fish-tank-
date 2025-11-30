/*
 * SISTEMA DE CONTROL AUTOMATIZADO DE PECERA
 * Arduino Mega 2560 + ESP32 via UART + MQTT
 * Máquina de estados con control por teclado y web
 * VERSIÓN CORREGIDA - Lógica invertida de relés
 */

// ========== LIBRERÍAS ==========
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Keypad.h>
#include <Servo.h>
#include <ArduinoJson.h>

// ========== DEFINICIÓN DE PINES ==========

// LCD I2C (dirección 0x27 o 0x3F)
#define LCD_ADDRESS 0x27
#define LCD_COLS 16
#define LCD_ROWS 2
// SDA = Pin 20 (Arduino Mega)
// SCL = Pin 21 (Arduino Mega)

// Actuadores
#define SERVO_COMPUERTA 3      // Servo motor compuerta alimentación
#define BOMBA_VACIADO 7        // Bomba para vaciar pecera
#define BOMBA_LLENADO 6        // Bomba para llenar pecera

// LÓGICA DE RELÉS (invertida)
#define RELE_ON HIGH           // Relé activado = HIGH
#define RELE_OFF LOW           // Relé desactivado = LOW

// Sensor Ultrasónico HC-SR04
#define TRIGGER_PIN 9
#define ECHO_PIN 10

// Sensores Analógicos
#define SENSOR_LIQUIDO A0      // Sensor de nivel de líquido
#define SENSOR_TDS A1          // Sensor TDS (calidad del agua)

// UART hacia ESP32
#define UART_ESP32 Serial1     // TX1=18, RX1=19
#define UART_BAUD 115200

// Teclado Matricial 4x4
#define ROWS 4
#define COLS 4
byte rowPins[ROWS] = {38, 40, 42, 44}; // F1 F2 F3 F4
byte colPins[COLS] = {46, 48, 50, 52}; // C1 C2 C3 C4

// ========== CONFIGURACIÓN DE PERIFÉRICOS ==========

// Inicializar LCD I2C
LiquidCrystal_I2C lcd(LCD_ADDRESS, LCD_COLS, LCD_ROWS);

// Servo motor para compuerta de alimentación
Servo servoCompuerta;

// Configurar teclado matricial
char teclas[ROWS][COLS] = {
  {'1','2','3','A'},
  {'4','5','6','B'},
  {'7','8','9','C'},
  {'*','0','#','D'}
};
Keypad keypad = Keypad(makeKeymap(teclas), rowPins, colPins, ROWS, COLS);

// ========== MÁQUINA DE ESTADOS ==========
enum Estado {
  MODO_MENU,
  MODO_AUTOMATICO,
  MODO_VACIAR,
  MODO_LLENAR,
  MODO_RENOVACION_AUTO  // Renovación automática por TDS alto
};

Estado estado = MODO_MENU;

// ========== VARIABLES GLOBALES ==========

// Control de teclado
String buffer = "";

// Modo Automático
unsigned long tiempoAutoAnterior = 0;
const unsigned long INTERVALO_AUTO = 10000;  // 10 segundos
const int ANGULO_ALIMENTACION = 45;  // Grados de giro del servo
const int ANGULO_INICIAL = 0;  // Posición inicial del servo
const unsigned long TIEMPO_SERVO = 1000;  // Tiempo para movimiento del servo

// Modo Vaciado
bool vaciando = false;
int distanciaAnterior = 999;
unsigned long tiempoEstable = 0;
const unsigned long TIEMPO_ESTABILIDAD = 3000;  // 3 segundos
const int UMBRAL_CAMBIO = 1;  // 1 cm de diferencia

// Modo Llenado
bool llenando = false;
const int DISTANCIA_OBJETIVO = 3;  // 3 cm = nivel lleno
const int UMBRAL_SENSOR_LIQUIDO = 500;  // Umbral analógico para detección

// Control de calidad del agua (TDS)
const int UMBRAL_TDS_MAX = 300;  // PPM máximo antes de renovar agua
unsigned long tiempoUltimaRevisionTDS = 0;
const unsigned long INTERVALO_REVISION_TDS = 10000;  // Revisar cada 10 segundos

// Renovación automática de agua
bool renovandoAgua = false;
bool faseVaciado = true;  // true = vaciando, false = llenando

// ========== COMUNICACIÓN MQTT/ESP32 ==========
const unsigned long SAMPLE_INTERVAL_MS = 2000;  // Enviar datos cada 2 segundos
unsigned long lastSample = 0;
String incomingCommand = "";

// ========== EVENTOS EXCEPCIONALES ==========
struct EventoExcepcional {
  unsigned long horaEjecucion;  // millis() cuando debe ejecutarse (0 = inmediato)
  String tipoEvento;            // "BOMBA6", "BOMBA7", "SERVO"
  int duracion;                 // Duración en ms (-1 = indefinido)
  bool activo;                  // Si está programado
  bool ejecutando;              // Si está ejecutándose actualmente
  int id;                       // ID único del evento
};

#define MAX_EVENTOS 10
EventoExcepcional eventosExcepcionales[MAX_EVENTOS];
int numEventos = 0;
int contadorIdEventos = 0;  // Para asignar IDs únicos

// Temperatura del agua para cálculo de TDS
const float WATER_TEMP_C = 25.0;

// ========== SETUP ==========
void setup() {
  // Inicializar comunicación serial
  Serial.begin(115200);
  UART_ESP32.begin(UART_BAUD);  // UART hacia ESP32
  Serial.println("Sistema de Control de Pecera Iniciado");
  Serial.println("UART ESP32 configurado en TX1=18, RX1=19");
  Serial.println("*** LÓGICA DE RELÉS CORREGIDA ***");
  
  // Configurar pines de salida
  servoCompuerta.attach(SERVO_COMPUERTA);
  servoCompuerta.write(ANGULO_INICIAL);  // Posición inicial
  pinMode(BOMBA_VACIADO, OUTPUT);
  pinMode(BOMBA_LLENADO, OUTPUT);
  pinMode(TRIGGER_PIN, OUTPUT);
  
  // Configurar pines de entrada
  pinMode(ECHO_PIN, INPUT);
  pinMode(SENSOR_LIQUIDO, INPUT);
  pinMode(SENSOR_TDS, INPUT);
  
  // Asegurar que todo esté apagado (IMPORTANTE: usar lógica correcta de relés)
  servoCompuerta.write(ANGULO_INICIAL);
  digitalWrite(BOMBA_VACIADO, RELE_OFF);   // CORREGIDO: OFF = LOW
  digitalWrite(BOMBA_LLENADO, RELE_OFF);   // CORREGIDO: OFF = LOW
  digitalWrite(TRIGGER_PIN, LOW);
  
  Serial.println("Bombas inicializadas: APAGADAS (LOW)");
  
  // Inicializar LCD I2C
  Wire.begin();
  lcd.init();
  lcd.backlight();
  lcd.clear();
  lcd.print("Iniciando...");
  delay(1000);
  
  // Verificar sensores
  verificarSensores();
  
  // Inicializar eventos excepcionales
  for (int i = 0; i < MAX_EVENTOS; i++) {
    eventosExcepcionales[i].activo = false;
    eventosExcepcionales[i].ejecutando = false;
    eventosExcepcionales[i].id = -1;
  }
  
  // Mostrar menú inicial
  mostrarMenu();
  
  Serial.println("Sistema listo. Esperando comandos MQTT...");
}

// ========== LOOP PRINCIPAL ==========
void loop() {
  leerTeclado();   // Permite cambiar de estado en cualquier momento
  leerComandosMQTT();  // Leer comandos desde ESP32
  ejecutarEventosExcepcionales();  // Verificar eventos programados
  enviarDatosSensores();  // Enviar datos a MQTT periódicamente
  
  switch (estado) {
    case MODO_MENU:
      // En el menú, simplemente espera comandos
      break;
      
    case MODO_AUTOMATICO:
      ejecutarAutomatico();
      break;
      
    case MODO_VACIAR:
      ejecutarVaciado();
      break;
      
    case MODO_LLENAR:
      ejecutarLlenado();
      break;
      
    case MODO_RENOVACION_AUTO:
      ejecutarRenovacionAutomatica();
      break;
  }
}

// ========== FUNCIONES DE TECLADO ==========

void leerTeclado() {
  char tecla = keypad.getKey();
  
  if (tecla) {
    Serial.print("Tecla presionada: ");
    Serial.println(tecla);
    
    if (tecla == '*') {
      // Ejecutar comando acumulado
      ejecutarComando(buffer);
      buffer = "";
    } else if (tecla == '#') {
      // Limpiar buffer
      buffer = "";
      lcd.clear();
      lcd.print("Buffer limpiado");
      delay(500);
      mostrarMenu();
    } else {
      // Acumular dígito
      buffer += tecla;
      Serial.print("Buffer: ");
      Serial.println(buffer);
    }
  }
}

void ejecutarComando(String cmd) {
  Serial.print("Ejecutando comando: ");
  Serial.println(cmd);
  
  if (cmd == "1") {
    // Modo Automático
    estado = MODO_AUTOMATICO;
    lcd.clear();
    lcd.print("Modo Automatico");
    lcd.setCursor(0, 1);
    lcd.print("Activo");
    tiempoAutoAnterior = millis();
    tiempoUltimaRevisionTDS = millis();
    Serial.println("-> Estado: AUTOMATICO");
  }
  else if (cmd == "2") {
    // Modo Vaciado
    estado = MODO_VACIAR;
    lcd.clear();
    lcd.print("Renovando");
    lcd.setCursor(0, 1);
    lcd.print("ecosistema...");
    iniciarVaciado();
    Serial.println("-> Estado: VACIAR");
  }
  else if (cmd == "3") {
    // Modo Llenado
    estado = MODO_LLENAR;
    lcd.clear();
    lcd.print("Llenando");
    lcd.setCursor(0, 1);
    lcd.print("ecosistema...");
    iniciarLlenado();
    Serial.println("-> Estado: LLENAR");
  }
  else if (cmd == "4") {
    // Volver al menú
    detenerTodo();
    estado = MODO_MENU;
    mostrarMenu();
    Serial.println("-> Estado: MENU");
  }
  else if (cmd == "5") {
    // Reinicio completo del sistema
    reiniciarSistema();
  }
  else {
    // Comando no reconocido
    lcd.clear();
    lcd.print("Comando invalido");
    delay(1000);
    mostrarMenu();
  }
}

// ========== MODO AUTOMÁTICO ==========

void ejecutarAutomatico() {
  // Revisar calidad del agua (TDS) periódicamente
  if (millis() - tiempoUltimaRevisionTDS >= INTERVALO_REVISION_TDS) {
    tiempoUltimaRevisionTDS = millis();
    
    int tds = leerTDS();
    Serial.print("Revisión TDS: ");
    Serial.print(tds);
    Serial.println(" ppm");
    
    // Si TDS supera el umbral, iniciar renovación automática
    if (tds > UMBRAL_TDS_MAX) {
      Serial.println("¡ALERTA! TDS alto - Iniciando renovación automática");
      lcd.clear();
      lcd.print("ALERTA: TDS alto");
      lcd.setCursor(0, 1);
      lcd.print(tds);
      lcd.print(" ppm > ");
      lcd.print(UMBRAL_TDS_MAX);
      delay(2000);
      
      // Cambiar a modo renovación automática
      estado = MODO_RENOVACION_AUTO;
      iniciarRenovacionAutomatica();
      return;
    }
  }
  
  // Activar servo compuerta cada 10 segundos (alimentación)
  if (millis() - tiempoAutoAnterior >= INTERVALO_AUTO) {
    tiempoAutoAnterior = millis();
    
    Serial.println("Activando compuerta de alimentación...");
    
    // Actualizar LCD
    lcd.clear();
    lcd.print("Alimentando...");
    lcd.setCursor(0, 1);
    lcd.print("Girando 45");
    lcd.print((char)223);  // Símbolo de grados
    
    // Girar servo 45 grados
    servoCompuerta.write(ANGULO_ALIMENTACION);
    delay(TIEMPO_SERVO);  // Esperar a que termine el movimiento
    
    // Volver a posición inicial
    servoCompuerta.write(ANGULO_INICIAL);
    delay(500);
    
    // Mostrar nivel de agua y TDS
    int distancia = medirDistancia();
    int tds = leerTDS();
    lcd.clear();
    lcd.print("Modo Automatico");
    lcd.setCursor(0, 1);
    lcd.print("N:");
    lcd.print(distancia);
    lcd.print("cm TDS:");
    lcd.print(tds);
  }
}

// ========== MODO VACIADO ==========

void iniciarVaciado() {
  Serial.println("Iniciando vaciado...");
  digitalWrite(BOMBA_VACIADO, RELE_ON);   // CORREGIDO: ON = HIGH
  Serial.println("Bomba vaciado: ENCENDIDA (HIGH)");
  vaciando = true;
  distanciaAnterior = medirDistancia();
  tiempoEstable = millis();
  
  Serial.print("Distancia inicial: ");
  Serial.print(distanciaAnterior);
  Serial.println(" cm");
}

void ejecutarVaciado() {
  if (!vaciando) return;
  
  int distanciaActual = medirDistancia();
  int nivelLiquido = analogRead(SENSOR_LIQUIDO);
  
  Serial.print("Distancia: ");
  Serial.print(distanciaActual);
  Serial.print(" cm | Anterior: ");
  Serial.print(distanciaAnterior);
  Serial.print(" cm | Sensor: ");
  Serial.println(nivelLiquido);
  
  // Actualizar LCD con progreso
  lcd.setCursor(0, 1);
  lcd.print("Vaciando ");
  lcd.print(distanciaActual);
  lcd.print("cm  ");
  
  // Verificar si la distancia se ha estabilizado (dejó de cambiar)
  if (abs(distanciaActual - distanciaAnterior) < UMBRAL_CAMBIO) {
    // Distancia estable
    if (millis() - tiempoEstable >= TIEMPO_ESTABILIDAD) {
      // Estable por 3 segundos = pecera vacía
      digitalWrite(BOMBA_VACIADO, RELE_OFF);  // CORREGIDO: OFF = LOW
      Serial.println("Bomba vaciado: APAGADA (LOW)");
      vaciando = false;
      
      Serial.println("Vaciado completo");
      lcd.clear();
      lcd.print("Listo para");
      lcd.setCursor(0, 1);
      lcd.print("rellenar");
      
      delay(2000);
      mostrarMenu();
      estado = MODO_MENU;
    }
  } else {
    // Distancia cambió, actualizar referencia
    distanciaAnterior = distanciaActual;
    tiempoEstable = millis();
  }
  
  delay(500);  // Medir cada 0.5 segundos
}

// ========== MODO LLENADO ==========

void iniciarLlenado() {
  Serial.println("Iniciando llenado...");
  digitalWrite(BOMBA_LLENADO, RELE_ON);   // CORREGIDO: ON = HIGH
  Serial.println("Bomba llenado: ENCENDIDA (HIGH)");
  llenando = true;
}

void ejecutarLlenado() {
  if (!llenando) return;
  
  int distancia = medirDistancia();
  int nivelLiquido = analogRead(SENSOR_LIQUIDO);
  bool sensorDetecta = (nivelLiquido > UMBRAL_SENSOR_LIQUIDO);
  
  Serial.print("Distancia: ");
  Serial.print(distancia);
  Serial.print(" cm | Sensor liquido: ");
  Serial.print(nivelLiquido);
  Serial.print(" | Detecta: ");
  Serial.println(sensorDetecta ? "SI" : "NO");
  
  // Actualizar progreso en LCD
  lcd.setCursor(0, 1);
  lcd.print("Llenando ");
  lcd.print(distancia);
  lcd.print("cm");
  
  // Verificar si alcanzó el nivel objetivo
  if (distancia <= DISTANCIA_OBJETIVO || sensorDetecta) {
    digitalWrite(BOMBA_LLENADO, RELE_OFF);  // CORREGIDO: OFF = LOW
    Serial.println("Bomba llenado: APAGADA (LOW)");
    llenando = false;
    
    Serial.println("Llenado completo");
    lcd.clear();
    lcd.print("Ecosistema listo");
    lcd.setCursor(0, 1);
    lcd.print("Nivel: ");
    lcd.print(distancia);
    lcd.print(" cm");
    
    delay(3000);
    
    // Volver al modo automático
    estado = MODO_AUTOMATICO;
    lcd.clear();
    lcd.print("Modo Automatico");
    lcd.setCursor(0, 1);
    lcd.print("Activo");
    tiempoAutoAnterior = millis();
  }
  
  delay(500);  // Verificar cada 0.5 segundos
}

// ========== FUNCIONES AUXILIARES ==========

void mostrarMenu() {
  // Mensaje dinámico para la primera fila
  String mensajeOpciones = "1*AUT 2*VAC 3*FULL 4*MEN 5*REINICIO     ";
  
  // Obtener nombre del estado actual
  String estadoActual = obtenerNombreEstado();
  
  // Mensaje para la segunda fila
  String lineaInferior = "Act: " + estadoActual + " - Elija";
  
  lcd.clear();
  
  // Mostrar scroll horizontal del mensaje de opciones
  for (int i = 0; i <= mensajeOpciones.length() - LCD_COLS; i++) {
    lcd.setCursor(0, 0);
    lcd.print(mensajeOpciones.substring(i, i + LCD_COLS));
    
    lcd.setCursor(0, 1);
    lcd.print(lineaInferior);
    
    delay(300);  // Velocidad del scroll
    
    // Verificar si se presiona alguna tecla durante el scroll
    char tecla = keypad.getKey();
    if (tecla) {
      // Si hay tecla, procesar y salir del scroll
      if (tecla == '*') {
        ejecutarComando(buffer);
        buffer = "";
        return;
      } else if (tecla == '#') {
        buffer = "";
        lcd.clear();
        lcd.print("Buffer limpiado");
        delay(500);
        mostrarMenu();
        return;
      } else {
        buffer += tecla;
        Serial.print("Buffer: ");
        Serial.println(buffer);
      }
    }
  }
  
  // Mantener el mensaje final visible
  lcd.setCursor(0, 0);
  lcd.print(mensajeOpciones.substring(0, LCD_COLS));
  lcd.setCursor(0, 1);
  lcd.print(lineaInferior);
  
  Serial.println("Menu mostrado");
}

// Función auxiliar para obtener el nombre del estado actual
String obtenerNombreEstado() {
  switch (estado) {
    case MODO_MENU:
      return "MENU";
    case MODO_AUTOMATICO:
      return "AUTO";
    case MODO_VACIAR:
      return "VACIAR";
    case MODO_LLENAR:
      return "LLENAR";
    case MODO_RENOVACION_AUTO:
      return "RENOV";
    default:
      return "DESC";
  }
}

int medirDistancia() {
  // Generar pulso de 10us en TRIGGER
  digitalWrite(TRIGGER_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIGGER_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIGGER_PIN, LOW);
  
  // Medir duración del pulso ECHO
  long duracion = pulseIn(ECHO_PIN, HIGH, 30000);  // Timeout 30ms
  
  // Calcular distancia en cm
  // Velocidad del sonido: 340 m/s = 0.034 cm/us
  // Distancia = (tiempo * velocidad) / 2
  int distancia = duracion * 0.034 / 2;
  
  // Validar lectura
  if (distancia == 0 || distancia > 400) {
    Serial.println("Advertencia: Lectura ultrasónico fuera de rango");
    return distanciaAnterior;  // Retornar última lectura válida
  }
  
  return distancia;
}

int leerTDS() {
  // Leer sensor TDS (Total Dissolved Solids)
  int valorTDS = analogRead(SENSOR_TDS);
  
  // Convertir a PPM (Parts Per Million)
  // Ajustar según calibración del sensor
  float voltaje = valorTDS * (5.0 / 1024.0);
  float ppm = (133.42 * voltaje * voltaje * voltaje 
             - 255.86 * voltaje * voltaje 
             + 857.39 * voltaje) * 0.5;
  
  return (int)ppm;
}

int leerSensorLiquido() {
  // Leer sensor de nivel de líquido analógico
  int valor = analogRead(SENSOR_LIQUIDO);
  Serial.print("Sensor liquido: ");
  Serial.println(valor);
  return valor;
}

void verificarSensores() {
  Serial.println("=== Verificando sensores ===");
  
  // Verificar LCD I2C
  lcd.clear();
  lcd.print("Test LCD OK");
  Serial.println("LCD I2C: OK");
  delay(1000);
  
  // Verificar sensor ultrasónico
  int dist = medirDistancia();
  lcd.clear();
  lcd.print("Ultrason: ");
  lcd.print(dist);
  lcd.print("cm");
  Serial.print("Ultrasonico: ");
  Serial.print(dist);
  Serial.println(" cm");
  delay(1000);
  
  // Verificar sensor de líquido
  int liquido = analogRead(SENSOR_LIQUIDO);
  lcd.clear();
  lcd.print("Sensor liq: ");
  lcd.print(liquido);
  Serial.print("Sensor liquido: ");
  Serial.println(liquido);
  delay(1000);
  
  // Verificar sensor TDS
  int tds = leerTDS();
  lcd.clear();
  lcd.print("TDS: ");
  lcd.print(tds);
  lcd.print(" ppm");
  Serial.print("TDS: ");
  Serial.print(tds);
  Serial.println(" ppm");
  delay(1000);
  
  Serial.println("=== Verificacion completa ===");
}

void detenerTodo() {
  // Apagar todos los actuadores
  servoCompuerta.write(ANGULO_INICIAL);  // Volver a posición inicial
  digitalWrite(BOMBA_VACIADO, RELE_OFF);   // CORREGIDO: OFF = LOW
  digitalWrite(BOMBA_LLENADO, RELE_OFF);   // CORREGIDO: OFF = LOW
  
  Serial.println("Bombas apagadas: VACIADO=LOW, LLENADO=LOW");
  
  // Resetear flags
  vaciando = false;
  llenando = false;
  renovandoAgua = false;
  
  Serial.println("Todos los actuadores detenidos");
}

// ========== MODO RENOVACIÓN AUTOMÁTICA ==========

void iniciarRenovacionAutomatica() {
  Serial.println("=== INICIANDO RENOVACION AUTOMATICA ===");
  lcd.clear();
  lcd.print("Renovacion Auto");
  lcd.setCursor(0, 1);
  lcd.print("Iniciando...");
  delay(1000);
  
  renovandoAgua = true;
  faseVaciado = true;
  
  // Iniciar vaciado
  digitalWrite(BOMBA_VACIADO, RELE_ON);  // CORREGIDO: ON = HIGH
  Serial.println("Bomba vaciado: ENCENDIDA (HIGH)");
  distanciaAnterior = medirDistancia();
  tiempoEstable = millis();
  
  lcd.clear();
  lcd.print("Fase 1: Vaciado");
  Serial.println("Fase 1: Vaciando agua contaminada");
}

void ejecutarRenovacionAutomatica() {
  if (!renovandoAgua) return;
  
  if (faseVaciado) {
    // FASE 1: VACIADO
    int distanciaActual = medirDistancia();
    
    Serial.print("Vaciado - Distancia: ");
    Serial.print(distanciaActual);
    Serial.println(" cm");
    
    // Actualizar LCD
    lcd.setCursor(0, 1);
    lcd.print("Vaciando ");
    lcd.print(distanciaActual);
    lcd.print("cm  ");
    
    // Verificar si se estabilizó (vacío)
    if (abs(distanciaActual - distanciaAnterior) < UMBRAL_CAMBIO) {
      if (millis() - tiempoEstable >= TIEMPO_ESTABILIDAD) {
        // Vaciado completo - pasar a llenado
        digitalWrite(BOMBA_VACIADO, RELE_OFF);  // CORREGIDO: OFF = LOW
        Serial.println("Bomba vaciado: APAGADA (LOW)");
        faseVaciado = false;
        
        Serial.println("Vaciado completo - Iniciando llenado");
        lcd.clear();
        lcd.print("Fase 2: Llenado");
        delay(1000);
        
        // Iniciar llenado
        digitalWrite(BOMBA_LLENADO, RELE_ON);  // CORREGIDO: ON = HIGH
        Serial.println("Bomba llenado: ENCENDIDA (HIGH)");
      }
    } else {
      distanciaAnterior = distanciaActual;
      tiempoEstable = millis();
    }
  } else {
    // FASE 2: LLENADO
    int distancia = medirDistancia();
    int nivelLiquido = analogRead(SENSOR_LIQUIDO);
    bool sensorDetecta = (nivelLiquido > UMBRAL_SENSOR_LIQUIDO);
    
    Serial.print("Llenado - Distancia: ");
    Serial.print(distancia);
    Serial.print(" cm | Sensor: ");
    Serial.println(nivelLiquido);
    
    // Actualizar LCD
    lcd.setCursor(0, 1);
    lcd.print("Llenando ");
    lcd.print(distancia);
    lcd.print("cm");
    
    // Verificar si alcanzó nivel objetivo
    if (distancia <= DISTANCIA_OBJETIVO || sensorDetecta) {
      digitalWrite(BOMBA_LLENADO, RELE_OFF);  // CORREGIDO: OFF = LOW
      Serial.println("Bomba llenado: APAGADA (LOW)");
      renovandoAgua = false;
      
      Serial.println("=== RENOVACION COMPLETA ===");
      lcd.clear();
      lcd.print("Renovacion");
      lcd.setCursor(0, 1);
      lcd.print("Completa!");
      delay(2000);
      
      // Verificar TDS del agua nueva
      int tdsNuevo = leerTDS();
      lcd.clear();
      lcd.print("TDS nuevo:");
      lcd.setCursor(0, 1);
      lcd.print(tdsNuevo);
      lcd.print(" ppm");
      delay(2000);
      
      // Volver al modo automático
      estado = MODO_AUTOMATICO;
      lcd.clear();
      lcd.print("Modo Automatico");
      lcd.setCursor(0, 1);
      lcd.print("Activo");
      tiempoAutoAnterior = millis();
      tiempoUltimaRevisionTDS = millis();
    }
  }
  
  delay(500);
}

// ========== FUNCIÓN DE REINICIO ==========

void reiniciarSistema() {
  Serial.println("========================================");
  Serial.println("       REINICIANDO SISTEMA COMPLETO");
  Serial.println("========================================");
  
  // Mostrar animación de reinicio
  lcd.clear();
  lcd.print("  REINICIANDO");
  lcd.setCursor(0, 1);
  lcd.print("    SISTEMA");
  delay(1000);
  
  // Detener todos los actuadores
  detenerTodo();
  
  // Resetear todas las variables
  buffer = "";
  tiempoAutoAnterior = 0;
  distanciaAnterior = 999;
  tiempoEstable = 0;
  tiempoUltimaRevisionTDS = 0;
  vaciando = false;
  llenando = false;
  renovandoAgua = false;
  faseVaciado = true;
  
  // Animación de progreso
  lcd.clear();
  lcd.print("Deteniendo...");
  for (int i = 0; i < 16; i++) {
    lcd.setCursor(i, 1);
    lcd.print(".");
    delay(100);
  }
  
  lcd.clear();
  lcd.print("Reiniciando...");
  for (int i = 0; i < 16; i++) {
    lcd.setCursor(i, 1);
    lcd.print(".");
    delay(100);
  }
  
  // Verificar sensores nuevamente
  Serial.println("Re-verificando sensores...");
  verificarSensores();
  
  // Volver al estado inicial
  estado = MODO_MENU;
  
  lcd.clear();
  lcd.print("  REINICIO");
  lcd.setCursor(0, 1);
  lcd.print("  COMPLETO!");
  delay(1500);
  
  // Mostrar menú
  mostrarMenu();
  
  Serial.println("========================================");
  Serial.println("   Sistema reiniciado exitosamente");
  Serial.println("========================================");
}

// ========== COMUNICACIÓN MQTT/ESP32 ==========

void leerComandosMQTT() {
  // Leer comandos del ESP32 via UART
  while (UART_ESP32.available()) {
    char c = UART_ESP32.read();
    if (c == '\n') {
      procesarComandoMQTT(incomingCommand);
      incomingCommand = "";
    } else {
      incomingCommand += c;
    }
  }
}

void procesarComandoMQTT(String cmd) {
  cmd.trim();
  Serial.print("Comando MQTT recibido: ");
  Serial.println(cmd);
  
  // Parsear JSON
  StaticJsonDocument<256> doc;
  DeserializationError error = deserializeJson(doc, cmd);
  
  if (error) {
    Serial.print("Error parseando JSON: ");
    Serial.println(error.c_str());
    return;
  }
  
  String tipo = doc["tipo"] | "";
  
  if (tipo == "AUTOMATICO") {
    ejecutarComando("1");
  }
  else if (tipo == "VACIAR") {
    ejecutarComando("2");
  }
  else if (tipo == "RELLENAR") {
    ejecutarComando("3");
  }
  else if (tipo == "REINICIAR") {
    ejecutarComando("5");
  }
  else if (tipo == "EXCEPCIONAL") {
    // Programar evento excepcional
    unsigned long horaEjec = doc["hora"] | 0;  // 0 = inmediato
    String evento = doc["evento"] | "";
    int duracion = doc["duracion"] | -1;  // -1 = indefinido
    
    programarEventoExcepcional(horaEjec, evento, duracion);
  }
  else if (tipo == "CANCELAR") {
    // Cancelar evento en ejecución
    int eventoId = doc["id"] | -1;
    String eventoTipo = doc["evento"] | "";
    
    if (eventoId >= 0) {
      cancelarEventoPorId(eventoId);
    } else if (eventoTipo != "") {
      cancelarEventoPorTipo(eventoTipo);
    } else {
      cancelarTodosEventos();
    }
  }
  else {
    Serial.println("Comando MQTT desconocido");
  }
}

void programarEventoExcepcional(unsigned long hora, String evento, int duracion) {
  if (numEventos >= MAX_EVENTOS) {
    Serial.println("ERROR: Máximo de eventos alcanzado");
    enviarErrorMQTT("MAX_EVENTOS_ALCANZADO");
    return;
  }
  
  // Asignar ID único al evento
  int eventoId = contadorIdEventos++;
  
  eventosExcepcionales[numEventos].horaEjecucion = hora;
  eventosExcepcionales[numEventos].tipoEvento = evento;
  eventosExcepcionales[numEventos].duracion = duracion;
  eventosExcepcionales[numEventos].activo = true;
  eventosExcepcionales[numEventos].ejecutando = false;
  eventosExcepcionales[numEventos].id = eventoId;
  
  Serial.print("Evento programado [ID:");
  Serial.print(eventoId);
  Serial.print("]: ");
  Serial.print(evento);
  
  if (hora == 0) {
    Serial.print(" - INMEDIATO");
  } else {
    Serial.print(" a las ");
    Serial.print(hora);
    Serial.print(" ms");
  }
  
  if (duracion == -1) {
    Serial.println(" - INDEFINIDO");
  } else {
    Serial.print(" por ");
    Serial.print(duracion);
    Serial.println(" ms");
  }
  
  // Enviar confirmación a MQTT
  enviarConfirmacionEvento(eventoId, evento, hora, duracion);
  
  numEventos++;
}

void ejecutarEventosExcepcionales() {
  unsigned long tiempoActual = millis();
  
  for (int i = 0; i < numEventos; i++) {
    if (!eventosExcepcionales[i].activo) continue;
    
    // Verificar si es hora de ejecutar (hora 0 = inmediato)
    if (tiempoActual >= eventosExcepcionales[i].horaEjecucion) {
      String evento = eventosExcepcionales[i].tipoEvento;
      int duracion = eventosExcepcionales[i].duracion;
      int eventoId = eventosExcepcionales[i].id;
      
      // Si no está ejecutando, iniciarlo
      if (!eventosExcepcionales[i].ejecutando) {
        Serial.print("Iniciando evento excepcional [ID:");
        Serial.print(eventoId);
        Serial.print("]: ");
        Serial.println(evento);
        
        eventosExcepcionales[i].ejecutando = true;
        
        // Activar el actuador correspondiente
        if (evento == "BOMBA6") {
          digitalWrite(BOMBA_LLENADO, RELE_ON);  // CORREGIDO: ON = HIGH
          Serial.println("Bomba llenado: ENCENDIDA (HIGH)");
          lcd.clear();
          lcd.print("Evento: BOMBA6");
          lcd.setCursor(0, 1);
          if (duracion == -1) {
            lcd.print("INDEFINIDO");
          } else {
            lcd.print("Activa ");
            lcd.print(duracion / 1000);
            lcd.print("s");
          }
        }
        else if (evento == "BOMBA7") {
          digitalWrite(BOMBA_VACIADO, RELE_ON);  // CORREGIDO: ON = HIGH
          Serial.println("Bomba vaciado: ENCENDIDA (HIGH)");
          lcd.clear();
          lcd.print("Evento: BOMBA7");
          lcd.setCursor(0, 1);
          if (duracion == -1) {
            lcd.print("INDEFINIDO");
          } else {
            lcd.print("Activa ");
            lcd.print(duracion / 1000);
            lcd.print("s");
          }
        }
        else if (evento == "SERVO") {
          lcd.clear();
          lcd.print("Evento: SERVO");
          lcd.setCursor(0, 1);
          lcd.print("Alimentando...");
          servoCompuerta.write(ANGULO_ALIMENTACION);
          
          // Si es indefinido, mantener posición
          if (duracion == -1) {
            lcd.setCursor(0, 1);
            lcd.print("Pos: ");
            lcd.print(ANGULO_ALIMENTACION);
            lcd.print((char)223);
          }
        }
        
        // Si tiene duración definida, guardar hora de inicio
        if (duracion != -1) {
          eventosExcepcionales[i].horaEjecucion = tiempoActual;
        }
        
        // Notificar inicio a MQTT
        enviarNotificacionEvento(eventoId, evento, "INICIADO");
      }
      
      // Si está ejecutando y tiene duración definida, verificar si debe terminar
      if (eventosExcepcionales[i].ejecutando && duracion != -1) {
        if (tiempoActual - eventosExcepcionales[i].horaEjecucion >= (unsigned long)duracion) {
          // Terminar evento
          finalizarEvento(i);
        }
      }
      
      // Si tiene duración indefinida (-1), se mantiene hasta recibir cancelación
    }
  }
}

void finalizarEvento(int indice) {
  String evento = eventosExcepcionales[indice].tipoEvento;
  int eventoId = eventosExcepcionales[indice].id;
  
  Serial.print("Finalizando evento [ID:");
  Serial.print(eventoId);
  Serial.print("]: ");
  Serial.println(evento);
  
  // Desactivar actuador
  if (evento == "BOMBA6") {
    digitalWrite(BOMBA_LLENADO, RELE_OFF);  // CORREGIDO: OFF = LOW
    Serial.println("Bomba llenado: APAGADA (LOW)");
  }
  else if (evento == "BOMBA7") {
    digitalWrite(BOMBA_VACIADO, RELE_OFF);  // CORREGIDO: OFF = LOW
    Serial.println("Bomba vaciado: APAGADA (LOW)");
  }
  else if (evento == "SERVO") {
    servoCompuerta.write(ANGULO_INICIAL);
  }
  
  // Marcar evento como completado
  eventosExcepcionales[indice].activo = false;
  eventosExcepcionales[indice].ejecutando = false;
  
  // Notificar finalización a MQTT
  enviarNotificacionEvento(eventoId, evento, "FINALIZADO");
  
  Serial.println("Evento finalizado");
}

void cancelarEventoPorId(int eventoId) {
  Serial.print("Cancelando evento ID: ");
  Serial.println(eventoId);
  
  for (int i = 0; i < numEventos; i++) {
    if (eventosExcepcionales[i].id == eventoId && eventosExcepcionales[i].activo) {
      finalizarEvento(i);
      Serial.println("Evento cancelado exitosamente");
      return;
    }
  }
  
  Serial.println("ERROR: Evento no encontrado");
  enviarErrorMQTT("EVENTO_NO_ENCONTRADO");
}

void cancelarEventoPorTipo(String tipo) {
  Serial.print("Cancelando eventos de tipo: ");
  Serial.println(tipo);
  
  bool encontrado = false;
  for (int i = 0; i < numEventos; i++) {
    if (eventosExcepcionales[i].tipoEvento == tipo && 
        eventosExcepcionales[i].activo && 
        eventosExcepcionales[i].ejecutando) {
      finalizarEvento(i);
      encontrado = true;
    }
  }
  
  if (encontrado) {
    Serial.println("Eventos cancelados exitosamente");
  } else {
    Serial.println("No se encontraron eventos activos de ese tipo");
  }
}

void cancelarTodosEventos() {
  Serial.println("Cancelando TODOS los eventos activos");
  
  for (int i = 0; i < numEventos; i++) {
    if (eventosExcepcionales[i].activo && eventosExcepcionales[i].ejecutando) {
      finalizarEvento(i);
    }
  }
  
  Serial.println("Todos los eventos cancelados");
}

void enviarDatosSensores() {
  if (millis() - lastSample < SAMPLE_INTERVAL_MS) return;
  lastSample = millis();
  
  // Leer sensores
  int distancia = medirDistancia();
  int nivelLiquido = analogRead(SENSOR_LIQUIDO);
  float nivelPorcentaje = map(nivelLiquido, 0, 1023, 0, 100);
  int tdsRaw = analogRead(SENSOR_TDS);
  float tdsPpm = computeTdsPpm(tdsRaw, WATER_TEMP_C);
  
  // Obtener última tecla presionada (si hay)
  char ultimaTecla = keypad.getKey();
  String teclaStr = ultimaTecla ? String(ultimaTecla) : "NONE";
  
  // Enviar datos de ultrasonido
  if (distancia >= 0 && distancia < 400) {
    sendFrame("ULT", buildUltrasonicJson(distancia));
  }
  
  // Enviar datos de sensor de líquido
  sendFrame("LIQ", buildLiquidoJson(nivelPorcentaje, nivelLiquido));
  
  // Enviar datos de TDS
  sendFrame("TDS", buildTdsJson(tdsPpm, tdsRaw));
  
  // Enviar estado del teclado (si se presionó)
  if (ultimaTecla) {
    sendFrame("KEY", buildTecladoJson(teclaStr));
  }
  
  // Enviar estado general del sistema
  sendFrame("SYS", buildEstadoSistemaJson());
}

void sendFrame(String sensor, String jsonData) {
  String frame = "[" + sensor + "]" + jsonData;
  UART_ESP32.println(frame);
  Serial.print("Enviado a ESP32: ");
  Serial.println(frame);
}

String buildUltrasonicJson(int distancia) {
  StaticJsonDocument<128> doc;
  doc["sensor"] = "ultrasonico";
  doc["distancia_cm"] = distancia;
  doc["timestamp"] = millis();
  
  String output;
  serializeJson(doc, output);
  return output;
}

String buildLiquidoJson(float porcentaje, int raw) {
  StaticJsonDocument<128> doc;
  doc["sensor"] = "liquido";
  doc["nivel_pct"] = porcentaje;
  doc["raw"] = raw;
  doc["timestamp"] = millis();
  
  String output;
  serializeJson(doc, output);
  return output;
}

String buildTdsJson(float ppm, int raw) {
  StaticJsonDocument<128> doc;
  doc["sensor"] = "tds";
  doc["ppm"] = ppm;
  doc["raw"] = raw;
  doc["calidad"] = (ppm > UMBRAL_TDS_MAX) ? "MALA" : "BUENA";
  doc["timestamp"] = millis();
  
  String output;
  serializeJson(doc, output);
  return output;
}

String buildTecladoJson(String tecla) {
  StaticJsonDocument<128> doc;
  doc["sensor"] = "teclado";
  doc["tecla"] = tecla;
  doc["timestamp"] = millis();
  
  String output;
  serializeJson(doc, output);
  return output;
}

String buildEstadoSistemaJson() {
  StaticJsonDocument<256> doc;
  doc["sensor"] = "sistema";
  doc["estado"] = obtenerNombreEstado();
  doc["bomba6"] = digitalRead(BOMBA_LLENADO);
  doc["bomba7"] = digitalRead(BOMBA_VACIADO);
  doc["servo_pos"] = servoCompuerta.read();
  doc["eventos_activos"] = contarEventosActivos();
  doc["timestamp"] = millis();
  
  String output;
  serializeJson(doc, output);
  return output;
}

int contarEventosActivos() {
  int count = 0;
  for (int i = 0; i < numEventos; i++) {
    if (eventosExcepcionales[i].activo) count++;
  }
  return count;
}

float computeTdsPpm(int rawValue, float temperature) {
  // Convertir valor analógico a voltaje
  float voltage = rawValue * (5.0 / 1024.0);
  
  // Compensación por temperatura
  float compensationCoefficient = 1.0 + 0.02 * (temperature - 25.0);
  float compensationVoltage = voltage / compensationCoefficient;
  
  // Calcular TDS en ppm
  float tdsValue = (133.42 * compensationVoltage * compensationVoltage * compensationVoltage 
                   - 255.86 * compensationVoltage * compensationVoltage 
                   + 857.39 * compensationVoltage) * 0.5;
  
  return tdsValue;
}

// ========== FUNCIONES DE NOTIFICACIÓN MQTT ==========

void enviarConfirmacionEvento(int id, String evento, unsigned long hora, int duracion) {
  StaticJsonDocument<256> doc;
  doc["tipo"] = "CONFIRMACION_EVENTO";
  doc["id"] = id;
  doc["evento"] = evento;
  doc["hora"] = hora;
  doc["duracion"] = duracion;
  doc["estado"] = "PROGRAMADO";
  doc["timestamp"] = millis();
  
  String output;
  serializeJson(doc, output);
  sendFrame("CFM", output);
}

void enviarNotificacionEvento(int id, String evento, String estado) {
  StaticJsonDocument<256> doc;
  doc["tipo"] = "NOTIFICACION_EVENTO";
  doc["id"] = id;
  doc["evento"] = evento;
  doc["estado"] = estado;  // "INICIADO" o "FINALIZADO"
  doc["timestamp"] = millis();
  
  String output;
  serializeJson(doc, output);
  sendFrame("NOT", output);
}

void enviarErrorMQTT(String error) {
  StaticJsonDocument<128> doc;
  doc["tipo"] = "ERROR";
  doc["mensaje"] = error;
  doc["timestamp"] = millis();
  
  String output;
  serializeJson(doc, output);
  sendFrame("ERR", output);
}