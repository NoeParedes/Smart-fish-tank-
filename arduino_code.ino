#include <Servo.h>

// Definición de Pines
const int PIN_SERVO = 3;
const int PIN_BOMBA1 = 7;
const int PIN_BOMBA2 = 6;

Servo miServo;

// Estado del sistema
bool modoManual = true; // true = Manual, false = Automático

// Estado de los actuadores
bool estadoServo = false;
bool estadoBomba1 = false;
bool estadoBomba2 = false;

String inputString = "";         // String para guardar los datos entrantes
bool stringComplete = false;  // Bandera para indicar si el string está completo

void setup() {
  // Inicializar Serial
  Serial.begin(9600);
  
  // Configurar pines
  miServo.attach(PIN_SERVO);
  pinMode(PIN_BOMBA1, OUTPUT);
  pinMode(PIN_BOMBA2, OUTPUT);
  
  // Estado inicial: Todo apagado
  miServo.write(0); // Cerrado
  digitalWrite(PIN_BOMBA1, LOW);
  digitalWrite(PIN_BOMBA2, LOW);
  
  Serial.println("Sistema Iniciado. Esperando comandos...");
}

void loop() {
  // Procesar comandos Seriales
  if (stringComplete) {
    procesarComando(inputString);
    // Limpiar string
    inputString = "";
    stringComplete = false;
  }
  
  // Lógica Automática (Solo si no está en modo manual)
  if (!modoManual) {
    ejecutarLogicaAutomatica();
  }
}

/*
  SerialEvent ocurre cuando llegan nuevos datos al puerto RX hardware.
  Esta rutina se ejecuta entre cada ejecución de loop(), así que usar delay dentro del loop puede retrasar la respuesta.
*/
void serialEvent() {
  while (Serial.available()) {
    // Obtener el nuevo byte:
    char inChar = (char)Serial.read();
    // Agregarlo al inputString:
    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }
}

void procesarComando(String comando) {
  comando.trim(); // Eliminar espacios en blanco
  
  if (comando == "MANUAL") {
    modoManual = true;
    Serial.println("Modo: MANUAL");
  }
  else if (comando == "AUTO") {
    modoManual = false;
    Serial.println("Modo: AUTOMATICO");
  }
  else if (modoManual) {
    // Solo procesar comandos de control si estamos en modo manual
    
    // M1: Servo (1=Abrir/90, 0=Cerrar/0)
    if (comando.startsWith("M1:")) {
      int val = comando.substring(3).toInt();
      if (val == 1) {
        miServo.write(90); // Abrir compuerta
        estadoServo = true;
        Serial.println("Servo: ABIERTO");
      } else {
        miServo.write(0); // Cerrar compuerta
        estadoServo = false;
        Serial.println("Servo: CERRADO");
      }
    }
    // M2: Bomba 1 (1=ON, 0=OFF)
    else if (comando.startsWith("M2:")) {
      int val = comando.substring(3).toInt();
      if (val == 1) {
        digitalWrite(PIN_BOMBA1, HIGH);
        estadoBomba1 = true;
        Serial.println("Bomba 1: ENCENDIDA");
      } else {
        digitalWrite(PIN_BOMBA1, LOW);
        estadoBomba1 = false;
        Serial.println("Bomba 1: APAGADA");
      }
    }
    // M3: Bomba 2 (1=ON, 0=OFF)
    else if (comando.startsWith("M3:")) {
      int val = comando.substring(3).toInt();
      if (val == 1) {
        digitalWrite(PIN_BOMBA2, HIGH);
        estadoBomba2 = true;
        Serial.println("Bomba 2: ENCENDIDA");
      } else {
        digitalWrite(PIN_BOMBA2, LOW);
        estadoBomba2 = false;
        Serial.println("Bomba 2: APAGADA");
      }
    }
  } else {
    Serial.println("Comando ignorado: Sistema en modo AUTOMATICO");
  }
}

void ejecutarLogicaAutomatica() {
  // Aquí iría la lógica de sensores
  // Por ejemplo: Si sensor de nivel bajo -> Activar Bomba 1
  // Por ahora, dejamos esto vacío o con un comportamiento simple de prueba
}
