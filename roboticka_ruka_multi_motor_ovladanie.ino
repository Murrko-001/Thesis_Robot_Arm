// Automatické mapovanie USB pre SAMD21
#if defined(ARDUINO_ARCH_SAMD)
  #define HWSerial SerialUSB
#else
  #define HWSerial Serial
#endif

#define NUM_MOTORS 8
#define M_ENABLE 11

const uint8_t stepPins[NUM_MOTORS] = {5, 7, 9, 12, A0, A2, A4, 2};
const uint8_t dirPins[NUM_MOTORS]  = {6, 8, 10, 14, A1, A3, A5, 3};

const long STEPS_PER_MOVE = 10000;
const int STEP_DELAY = 125; 

void setup() {
  HWSerial.begin(115200);
  while (!HWSerial && millis() < 3000);
  HWSerial.println("--- START: 8-Motor Interface (Auto Stand-by) ---");

  pinMode(M_ENABLE, OUTPUT);
  // ZMENA: Zapneme dosku do stavu STAND-BY (motory su vypnute a tiche)
  digitalWrite(M_ENABLE, HIGH); 

  for (int i = 0; i < NUM_MOTORS; i++) {
    pinMode(stepPins[i], OUTPUT);
    pinMode(dirPins[i], OUTPUT);
  }
}

void moveMotorsSimultaneously(int directions[]) {
  // 1. Zobudenie motorov (zapnutie prúdu)
  digitalWrite(M_ENABLE, LOW);
  delay(5); // Dáme driverom 5 milisekúnd na stabilizáciu magnetického poľa

  // 2. Nastavenie smeru
  for (int i = 0; i < NUM_MOTORS; i++) {
    if (directions[i] != -1) {
      digitalWrite(dirPins[i], directions[i]);
    }
  }

  // 3. Samotný pohyb
  for (long step = 0; step < STEPS_PER_MOVE; step++) {
    for (int i = 0; i < NUM_MOTORS; i++) {
      if (directions[i] != -1) digitalWrite(stepPins[i], HIGH);
    }
    
    delayMicroseconds(STEP_DELAY); 
    
    for (int i = 0; i < NUM_MOTORS; i++) {
      if (directions[i] != -1) digitalWrite(stepPins[i], LOW);
    }
    
    delayMicroseconds(STEP_DELAY);
  }

  // 4. Uspatie motorov (vypnutie prúdu - motory stíchnu)
  digitalWrite(M_ENABLE, HIGH);
}

void loop() {
  if (HWSerial.available()) {
    String input = HWSerial.readStringUntil('\n');
    input.trim();
    input.toUpperCase();

    int motorDirections[NUM_MOTORS];
    for (int i = 0; i < NUM_MOTORS; i++) motorDirections[i] = -1; 
    bool willMove = false;

    int startIndex = 0;
    while (startIndex < input.length()) {
      int spaceIndex = input.indexOf(' ', startIndex);
      String token;
      
      if (spaceIndex == -1) {
        token = input.substring(startIndex);
        startIndex = input.length();
      } else {
        token = input.substring(startIndex, spaceIndex);
        startIndex = spaceIndex + 1;
      }

      int separatorIndex = token.indexOf(':');
      if (separatorIndex > 0) {
        String motorList = token.substring(0, separatorIndex);
        String command = token.substring(separatorIndex + 1);

        int dirState = -1;
        if (command == "UP") dirState = HIGH;
        else if (command == "DOWN") dirState = LOW;

        if (dirState != -1) {
          for (int i = 0; i < NUM_MOTORS; i++) {
            String motorID = String(i + 1);
            if (motorList.indexOf(motorID) >= 0) {
              motorDirections[i] = dirState;
              willMove = true;
            }
          }
        }
      }
    }

    if (willMove) {
      HWSerial.println("ACK: Zobudzam motory a vykonavam -> " + input);
      moveMotorsSimultaneously(motorDirections);
      HWSerial.println("Hotovo. Motory spia.");
    } else {
      HWSerial.println("ERR: Zly format. Skus napr. '12:UP 3:DOWN'");
    }
  }
}