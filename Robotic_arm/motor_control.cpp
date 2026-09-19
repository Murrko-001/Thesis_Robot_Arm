#include "motor_control.h"
#include <ArduinoJson.h>

namespace {

constexpr int NUM_MOTORS = 3;
constexpr uint8_t PIN_M_ENABLE = 11;
constexpr uint8_t STEP_PINS[NUM_MOTORS] = {5, 7, 9};
constexpr uint8_t DIR_PINS[NUM_MOTORS] = {6, 8, 10};
constexpr long TOP_POSITION = 45000;
constexpr int DEFAULT_STEP_DELAY_US = 125;
constexpr int MAX_STEP_DELAY_US = 32767;
constexpr int STANDBY_WAKE_DELAY_MS = 5;

struct MotorState {
  long position = 0;
  long targetPosition = 0;
  int stepDelayUs = DEFAULT_STEP_DELAY_US;
  unsigned long lastStepTimeUs = 0;
  bool pinState = false;
};

// Positions survive commands, but reset on boot. Start all motors at the bottom.
MotorState motorStates[NUM_MOTORS];

void setMotorsEnable(bool enable) {
  digitalWrite(PIN_M_ENABLE, enable ? LOW : HIGH);
}

void reportError(const char* message) {
  HWSerial.print("{\"status\":\"error\",\"message\":\"");
  HWSerial.print(message);
  HWSerial.println("\"}");
}

const char* validateCommands(JsonArray commands) {
  if (commands.isNull() || commands.size() == 0) {
    return "Expected a non-empty commands array.";
  }

  for (JsonVariant value : commands) {
    if (!value.is<JsonObject>()) return "Each command must be an object.";
    JsonObject command = value.as<JsonObject>();
    if (command.containsKey("step_count") || command.containsKey("direction")) {
      return "Use position instead of step_count and direction.";
    }
    if (!command["position"].is<long>() || command["position"].as<long>() < 0 ||
        command["position"].as<long>() > TOP_POSITION) {
      return "Position must be an integer from 0 to 45000.";
    }
    if (command.containsKey("step_delay") &&
        (!command["step_delay"].is<int>() || command["step_delay"].as<int>() < 1 ||
         command["step_delay"].as<int>() > MAX_STEP_DELAY_US)) {
      return "Step delay must be an integer from 1 to 32767 microseconds.";
    }
    JsonArray motors = command["motors"].as<JsonArray>();
    if (motors.isNull() || motors.size() == 0) {
      return "Expected a non-empty motors array.";
    }
    for (JsonVariant motor : motors) {
      if (!motor.is<int>() || motor.as<int>() < 1 || motor.as<int>() > NUM_MOTORS) {
        return "Motor IDs must be integers from 1 to 3.";
      }
    }
  }
  return nullptr;
}

void stepMotor(int index, unsigned long now) {
  MotorState& motor = motorStates[index];
  if (now - motor.lastStepTimeUs < static_cast<unsigned long>(motor.stepDelayUs)) return;

  motor.lastStepTimeUs = now;
  motor.pinState = !motor.pinState;
  digitalWrite(STEP_PINS[index], motor.pinState ? HIGH : LOW);

  // Count complete pulses so the last step always leaves STEP low.
  if (!motor.pinState) {
    motor.position += motor.targetPosition > motor.position ? 1 : -1;
  }
}

// Move simultaneously with independent pulse timers; block until all targets are reached.
void moveMotorsIndependently() {
  bool moving = false;
  for (int i = 0; i < NUM_MOTORS; ++i) {
    const MotorState& motor = motorStates[i];
    if (motor.position == motor.targetPosition) continue;
    digitalWrite(DIR_PINS[i], motor.targetPosition > motor.position ? HIGH : LOW);
    moving = true;
  }
  if (!moving) return;

  setMotorsEnable(true);
  delay(STANDBY_WAKE_DELAY_MS);
  const unsigned long start = micros();
  for (MotorState& motor : motorStates) motor.lastStepTimeUs = start;

  while (moving) {
    moving = false;
    const unsigned long now = micros();
    for (int i = 0; i < NUM_MOTORS; ++i) {
      if (motorStates[i].position == motorStates[i].targetPosition) continue;
      stepMotor(i, now);
      moving = true;
    }
  }
  setMotorsEnable(false);
}

}  // namespace

void configureHardware() {
  pinMode(PIN_M_ENABLE, OUTPUT);
  setMotorsEnable(false);
  for (int i = 0; i < NUM_MOTORS; ++i) {
    pinMode(STEP_PINS[i], OUTPUT);
    digitalWrite(STEP_PINS[i], LOW);
    pinMode(DIR_PINS[i], OUTPUT);
  }
}

void processJsonCommand(const String& inputJson) {
  StaticJsonDocument<500> doc;
  if (deserializeJson(doc, inputJson)) {
    reportError("Invalid JSON or command too large.");
    return;
  }

  JsonArray commands = doc["commands"].as<JsonArray>();
  const char* error = validateCommands(commands);
  if (error) {
    reportError(error);
    return;
  }

  // Validate the entire request before changing targets. The last group wins.
  for (JsonObject command : commands) {
    for (int motorNumber : command["motors"].as<JsonArray>()) {
      MotorState& motor = motorStates[motorNumber - 1];
      motor.targetPosition = command["position"].as<long>();
      motor.stepDelayUs = command["step_delay"] | DEFAULT_STEP_DELAY_US;
    }
  }

  HWSerial.println("{\"status\":\"executing\"}");
  moveMotorsIndependently();
  HWSerial.println("{\"status\":\"completed\"}");
}
