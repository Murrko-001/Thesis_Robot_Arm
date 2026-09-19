#ifndef MOTOR_CONTROL_H
#define MOTOR_CONTROL_H

#include <Arduino.h>

#define HWSerial SerialUSB

void configureHardware();
void processJsonCommand(const String& inputJson);

#endif
