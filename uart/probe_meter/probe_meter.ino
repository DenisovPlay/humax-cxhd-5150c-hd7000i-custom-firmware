/*
 * Wemos-«мультиметр» для JTAG-разъёма Humax.
 *
 * Что умеет:
 *   1) Прозвонка (continuity): 4 SDA --[1 кОм]-- точка A, 12 MISO -- точка B.
 *      cont=0 -> точки соединены; cont=1 -> нет.
 *   2) Вольтметр: A0 -- проверяемая точка, печатает напряжение 0..3.3 В.
 *
 * ВАЖНО:
 *   - 4 SDA подключать к точке ТОЛЬКО через резистор 1 кОм (защита от КЗ).
 *   - A0 не подавать больше 3.3 В.
 *   - Общая земля Wemos и Humax обязательна.
 *   - Не использовать одновременно с OpenOCD/мостом.
 */

const uint8_t OUT_PIN  = 4;    // 4 SDA
const uint8_t IN_PIN   = 12;   // 12 MISO
const uint8_t VOLT_PIN = A0;   // A0

void setup() {
    Serial.begin(115200);
    pinMode(OUT_PIN, OUTPUT);
    digitalWrite(OUT_PIN, LOW);
    pinMode(IN_PIN, INPUT_PULLUP);
    pinMode(VOLT_PIN, INPUT);

    Serial.println();
    Serial.println("=== Wemos probe: continuity + A0 voltmeter ===");
    Serial.println("cont=0 -> 4 SDA/12 MISO замкнуты (через 1к на 4 SDA!)");
    Serial.println("A0 = напряжение на A0 (0..3.3 В)");
    Serial.println();
}

void loop() {
    int cont = digitalRead(IN_PIN);
    int raw  = analogRead(VOLT_PIN);
    float v  = raw * 3.3f / 1023.0f;

    Serial.printf("cont=%d (%s)   A0=%4d  %.2f V\n",
                  cont, cont == 0 ? "closed" : "open", raw, v);
    delay(300);
}
