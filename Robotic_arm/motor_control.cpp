#include "motor_control.h"

void configureHardware() {
  pinMode(PIN_M_ENABLE, OUTPUT);
  setMotorsEnable(false);

  for (int i = 0; i < NUM_MOTORS; i++) {
    pinMode(STEP_PINS[i], OUTPUT);
    pinMode(DIR_PINS[i], OUTPUT);
  }
}

void setMotorsEnable(bool enable) {
  digitalWrite(PIN_M_ENABLE, enable ? LOW : HIGH);
}

/**
 * Simultánny, ale na parametroch nezávislý pohyb motorov pomocou millis/micros.
 */
void moveMotorsIndependently(MotorState motors[]) {
  setMotorsEnable(true);
  delay(STANDBY_WAKE_DELAY_MS);

  // 1. Zápis smerov a inicializácia časovačov pre aktívne motory
  for (int i = 0; i < NUM_MOTORS; i++) {
    if (motors[i].active) {
      digitalWrite(DIR_PINS[i], motors[i].direction);
      motors[i].lastStepTimeUs = micros();
    }
  }

  bool anyMotorActive = true;

  // 2. Hlavný cyklus - beží, kým aspoň jeden motor nedokončí svoje targetSteps
  while (anyMotorActive) {
    anyMotorActive = false;
    unsigned long currentTimeUs = micros();

    for (int i = 0; i < NUM_MOTORS; i++) {
      if (!motors[i].active) continue;

      if (motors[i].currentSteps < motors[i].targetSteps) {
        anyMotorActive = true; // Tento motor ešte neskončil, držíme cyklus nažive

        // Skontrolujeme, či motoru ubehol jeho špecifický delay
        if (currentTimeUs - motors[i].lastStepTimeUs >= (unsigned long)motors[i].stepDelayUs) {
          motors[i].lastStepTimeUs = currentTimeUs;
          motors[i].pinState = !motors[i].pinState;
          
          digitalWrite(STEP_PINS[i], motors[i].pinState ? HIGH : LOW);

          // Jeden krok je definovaný ako kompletný pulz (HIGH a potom LOW)
          if (!motors[i].pinState) {
            motors[i].currentSteps++;
          }
        }
      } else {
        // Motor dosiahol svoj vlastný step_count a vypína sa
        motors[i].active = false;
        digitalWrite(STEP_PINS[i], LOW);
      }
    }
  }

  setMotorsEnable(false);
}

void processJsonCommand(const String& inputJson) {
  StaticJsonDocument<500> doc;
  DeserializationError error = deserializeJson(doc, inputJson);

  if (error) {
    HWSerial.print("{\"status\":\"error\", \"message\":\"Invalid JSON: ");
    HWSerial.print(error.c_str());
    HWSerial.println("\"}");
    return;
  }

  JsonArray commands = doc["commands"];
  if (commands.isNull() || commands.size() == 0) {
    HWSerial.println("{\"status\":\"error\", \"message\":\"Missing 'commands' array.\"}");
    return;
  }

  MotorState motorStates[NUM_MOTORS]; // Implicitne false a 0
  bool hasValidMotors = false;

  // Spracovanie JSONu: Skupina po skupine
  for (JsonObject cmd : commands) {
    // Bezpečné načítanie inštrukcií s fallbackom pre danú skupinu
    long groupStepCount = DEFAULT_STEP_COUNT;
    if (cmd.containsKey("step_count")) {
      groupStepCount = cmd["step_count"].as<long>();
    }

    int groupStepDelay = DEFAULT_STEP_DELAY_US;
    if (cmd.containsKey("step_delay")) {
      groupStepDelay = cmd["step_delay"].as<int>();
    }

    int dirState = -1;
    const char* dirStr = cmd["direction"] | "";
    if (strcmp(dirStr, "UP") == 0) {
      dirState = HIGH;
    } else if (strcmp(dirStr, "DOWN") == 0) {
      dirState = LOW;
    }

    // Aplikovanie nastavení aktuálnej skupiny LEN na jej motory
    JsonArray motors = cmd["motors"];
    for (int motorNum : motors) {
      if (motorNum >= 1 && motorNum <= NUM_MOTORS && dirState != -1) {
        int idx = motorNum - 1;
        
        motorStates[idx].active = true;
        motorStates[idx].direction = dirState;
        motorStates[idx].targetSteps = groupStepCount;  // Každý motor dostane svoj target
        motorStates[idx].stepDelayUs = groupStepDelay;  // Každý motor dostane svoj delay
        motorStates[idx].currentSteps = 0;
        motorStates[idx].pinState = false;
        
        hasValidMotors = true;
      }
    }
  }

  if (!hasValidMotors) {
    HWSerial.println("{\"status\":\"error\", \"message\":\"No valid instructions.\"}");
    return;
  }

  HWSerial.println("{\"status\":\"executing\", \"message\":\"Moving groups independently.\"}");
  
  // Spustenie motorov
  moveMotorsIndependently(motorStates);

  HWSerial.println("{\"status\":\"completed\"}");
}