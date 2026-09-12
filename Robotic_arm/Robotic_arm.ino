#include "motor_control.h"


void setup() {
  HWSerial.begin(115200);
  while (!HWSerial && millis() < 3000);
  
  configureHardware();
  HWSerial.println("{\"status\":\"board_ready\", \"motors_active\": 3}");
}


void loop() {
  if (HWSerial.available()) {
    String input = HWSerial.readStringUntil('\n');
    input.trim();
    
    if (input.length() > 0) {
      processJsonCommand(input);
    }
  }
}
