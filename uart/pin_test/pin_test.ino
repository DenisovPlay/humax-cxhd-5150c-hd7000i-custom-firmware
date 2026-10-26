// Тест пинов Wemos D1 mini — по очереди подаёт HIGH на каждый пин.
// Тыкай светодиодом (через 220 Ом) между пином и GND.
// Serial Monitor 115200: показывает какой пин сейчас HIGH.

const int PINS[] = {5, 4, 14, 12, 13, 16};  // D1 D2 D5 D6 D7 D0
const char* NAMES[] = {"D1/GPIO5", "D2/GPIO4", "D5/GPIO14", "D6/GPIO12", "D7/GPIO13", "D0/GPIO16"};
const int N = 6;

void setup() {
    Serial.begin(115200);
    for (int i = 0; i < N; i++) pinMode(PINS[i], OUTPUT);
    Serial.println("\n=== Pin test: HIGH 2s each ===");
}

void loop() {
    for (int i = 0; i < N; i++) {
        // все LOW
        for (int j = 0; j < N; j++) digitalWrite(PINS[j], LOW);
        // один HIGH
        digitalWrite(PINS[i], HIGH);
        Serial.printf("HIGH: %s\n", NAMES[i]);
        delay(2000);
    }
}
