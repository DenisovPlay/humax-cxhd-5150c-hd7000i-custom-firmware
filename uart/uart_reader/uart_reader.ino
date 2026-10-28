// UART Reader for Humax CXHD-5150C boot ROM capture
// Wemos D1 mini: GPIO3 (RX) <- STB UART TX
//                GND         <- STB GND
// Serial Monitor: 2000000 baud, No Line Ending

void setup() {
  Serial.begin(2000000);
  Serial.println("\n=== UART Reader ready ===");
  Serial.println("Waiting for data on RX...\n");
}

void loop() {
  while (Serial.available()) {
    Serial.write(Serial.read());
  }
}
