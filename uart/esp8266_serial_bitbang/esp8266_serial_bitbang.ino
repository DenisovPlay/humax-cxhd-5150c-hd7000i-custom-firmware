/*
 * ESP8266 JTAG remote_bitbang — Serial (USB) режим, без WiFi.
 *
 * На маке:
 *   python3 uart/serial_bridge.py /dev/cu.usbserial-10
 * Затем OpenOCD подключается к localhost:3335.
 *
 * ВАЖНО: этот UART — транспорт протокола. Никаких Serial.print в loop(),
 * иначе они попадут в OpenOCD и сломают remote_bitbang.
 *
 * Протокол OpenOCD 0.12 (src/jtag/drivers/remote_bitbang.c):
 *   '0'..'7' — выставить уровни: bit2=TCK, bit1=TMS, bit0=TDI
 *   'R'      — прочитать TDO, ответить '0' или '1'
 *   'r'..'u' — reset: bit1=TRST, bit0=SRST (1 = asserted/low, 0 = released/high)
 *   'B'/'b'  — LED, игнорируем
 *   'Q'      — quit, игнорируем
 */

// Названия — ровно как на шелкографии LOLIN D1 mini V4.0.0.
#define PIN_TCK  14   // 14 SCK  (правая) → Humax 9  (TCK)
#define PIN_TDI  12   // 12 MISO (правая) → Humax 3  (TDI)
#define PIN_TMS  13   // 13 MOSI (правая) → Humax 7  (TMS)
#define PIN_TDO   4   // 4 SDA   (левая)  → Humax 5  (TDO)
#define PIN_TRST 16   // 16      (правая) → Humax 1  (TRST)
#define PIN_SRST -1   // не подключен

static inline void jhigh(int pin) {
    if (pin < 0) return;
    if (pin == 16) { digitalWrite(16, HIGH); return; }
    GPOS = (1UL << pin);
}

static inline void jlow(int pin) {
    if (pin < 0) return;
    if (pin == 16) { digitalWrite(16, LOW); return; }
    GPOC = (1UL << pin);
}

static inline int jread(int pin) {
    if (pin < 0) return 0;
    if (pin == 16) return digitalRead(16) ? 1 : 0;
    return (GPI & (1UL << pin)) ? 1 : 0;
}

static void jsetup(int pin, bool out) {
    if (pin < 0) return;
    pinMode(pin, out ? OUTPUT : INPUT);
    if (out) jlow(pin);
}

void setup() {
    Serial.begin(500000);          // должен совпадать с BAUD в serial_bridge.py
    Serial.setDebugOutput(false);  // не пускать отладку ядра в протокольный UART

    jsetup(PIN_TCK, true);
    jsetup(PIN_TDI, true);
    jsetup(PIN_TMS, true);
    jsetup(PIN_TDO, false);
    // Слабая внутренняя подтяжка TDO к 3.3 В: линия не должна плавать.
    if (PIN_TDO >= 0) pinMode(PIN_TDO, INPUT_PULLUP);
    jsetup(PIN_TRST, true);

    if (PIN_TRST >= 0) jhigh(PIN_TRST);  // TRST не активен
    jlow(PIN_TCK);
}

void loop() {
    while (Serial.available()) {
        char ch = (char)Serial.read();

        // Главное: OpenOCD присылает '0'..'7', а не 'c'..'f'.
        if (ch >= '0' && ch <= '7') {
            int v = ch - '0';
            // Сначала данные, потом фронт TCK.
            if (v & 2) jhigh(PIN_TMS); else jlow(PIN_TMS);
            if (v & 1) jhigh(PIN_TDI); else jlow(PIN_TDI);
            if (v & 4) jhigh(PIN_TCK); else jlow(PIN_TCK);
            continue;
        }

        switch (ch) {
        case 'R':
            Serial.write(jread(PIN_TDO) ? '1' : '0');
            break;

        case 'r': case 's': case 't': case 'u': {
            int v = ch - 'r';
            // OpenOCD: 1 = assert reset, поэтому активный уровень — LOW.
            if (PIN_TRST >= 0) {
                if (v & 2) jlow(PIN_TRST); else jhigh(PIN_TRST);
            }
            if (PIN_SRST >= 0) {
                if (v & 1) jlow(PIN_SRST); else jhigh(PIN_SRST);
            }
            break;
        }

        case 'B': case 'b':   // LED
        case 'Q':             // quit
        default:
            break;
        }
    }
}
