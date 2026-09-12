#ifndef MOTOR_CONTROL_H
#define MOTOR_CONTROL_H

#include <Arduino.h>
#include <ArduinoJson.h>

#define HWSerial SerialUSB

#define NUM_MOTORS 3
#define PIN_M_ENABLE 11

const uint8_t STEP_PINS[NUM_MOTORS] = {5, 7, 9};
const uint8_t DIR_PINS[NUM_MOTORS]  = {6, 8, 10};

const long DEFAULT_STEP_COUNT = 10000;
const int DEFAULT_STEP_DELAY_US = 125;
const int STANDBY_WAKE_DELAY_MS = 5;

struct MotorState {
  bool active = false;
  int direction = -1;
  long targetSteps = 0;
  long currentSteps = 0;
  int stepDelayUs = DEFAULT_STEP_DELAY_US;
  unsigned long lastStepTimeUs = 0;
  bool pinState = false;
};

void configureHardware();
void setMotorsEnable(bool enable);
void moveMotorsIndependently(MotorState motors[]);
void processJsonCommand(const String& inputJson);

#endif