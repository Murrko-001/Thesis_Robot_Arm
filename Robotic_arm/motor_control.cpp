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
 * Simultaneous, independent motor movement driven by micros() non-blocking timers.
 */
void moveMotorsIndependently(MotorState motors[]) {
  setMotorsEnable(true);
  delay(STANDBY_WAKE_DELAY_MS);

  // 1. Set directions and initialize timers for active motors
  for (int i = 0; i < NUM_MOTORS; i++) {
    if (motors[i].active) {
      digitalWrite(DIR_PINS[i], motors[i].direction);
      motors[i].lastStepTimeUs = micros();
    }
  }

  bool anyMotorActive = true;

  // 2. Main execution loop - runs until every motor completes its targetSteps
  while (anyMotorActive) {
    anyMotorActive = false;
    unsigned long currentTimeUs = micros();

    for (int i = 0; i < NUM_MOTORS; i++) {
      if (!motors[i].active) continue;

      if (motors[i].currentSteps < motors[i].targetSteps) {
        anyMotorActive = true; // Keep loop alive while at least one motor is stepping

        // Check if the motor's specific step delay has elapsed
        if (currentTimeUs - motors[i].lastStepTimeUs >= (unsigned long)motors[i].stepDelayUs) {
          motors[i].lastStepTimeUs = currentTimeUs;
          motors[i].pinState = !motors[i].pinState;
          
          digitalWrite(STEP_PINS[i], motors[i].pinState ? HIGH : LOW);

          // One complete step is defined as a full pulse transition (HIGH then LOW)
          if (!motors[i].pinState) {
            motors[i].currentSteps++;
          }
        }
      } else {
        // Motor reached its target step count and disables itself
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

  MotorState motorStates[NUM_MOTORS]; // Implicitly initialized to false and 0
  bool hasValidMotors = false;

  // Process JSON: Command group by group
  for (JsonObject cmd : commands) {
    // Safe extraction of group movement settings with fallback defaults
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

    // Apply current group settings ONLY to its target motors
    JsonArray motors = cmd["motors"];
    for (int motorNum : motors) {
      if (motorNum >= 1 && motorNum <= NUM_MOTORS && dirState != -1) {
        int idx = motorNum - 1;
        
        motorStates[idx].active = true;
        motorStates[idx].direction = dirState;
        motorStates[idx].targetSteps = groupStepCount;  // Each motor receives its own step target
        motorStates[idx].stepDelayUs = groupStepDelay;  // Each motor receives its own delay
        motorStates[idx].currentSteps = 0;
        motorStates[idx].pinState = false;
        
        hasValidMotors = true;
      }
    }
  }

  if (!hasValidMotors) {
    HWSerial.println("{\"status\":\"error\", \"message\":\"No valid instructions provided.\"}");
    return;
  }

  HWSerial.println("{\"status\":\"executing\", \"message\":\"Moving groups independently.\"}");
  
  // Execute motor movement
  moveMotorsIndependently(motorStates);

  HWSerial.println("{\"status\":\"completed\"}");
}