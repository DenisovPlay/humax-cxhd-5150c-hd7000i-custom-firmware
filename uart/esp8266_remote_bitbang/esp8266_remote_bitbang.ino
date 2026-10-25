/*
 * ESP8266 (Wemos D1 mini) — JTAG-адаптер для OpenOCD по протоколу remote_bitbang.
 *
 * OpenOCD (Mac) --WiFi TCP:3335--> ESP8266 --bit-bang--> EJTAG Humax CXHD-5150C
 *
 * Настройка:
 *   1. Впиши WIFI_SSID / WIFI_PASS.
 *   2. Впиши пины JTAG по результатам скана JTAGenum (TCK/TDI/TMS/TDO).
 *   3. В OpenOCD: adapter driver remote_bitbang; remote_bitbang host <ip>; port 3335
 *
 * Протокол (OpenOCD src/jtag/drivers/remote_bitbang.c), по одному символу:
 *   'c' TCK-импульс с TMS=0 TDI=0     'd' TMS=0 TDI=1
 *   'e' TCK-импульс с TMS=1 TDI=0     'f' TMS=1 TDI=1
 *   'R' прочитать TDO -> ответить '0' или '1'
 *   'r'/'s' SRST 0/1                  't'/'u' TRST 0/1
 *   'B'/'b' индикация (игнорируем)    'Q' закрыть соединение
 */

#include <ESP8266WiFi.h>

// ==================== НАСТРОЙКИ ====================
const char* WIFI_SSID = "TVOI_WIFI";
const char* WIFI_PASS = "TVOI_PAROL";
const int   TCP_PORT  = 3335;

// Пины Wemos D1 mini (заполнить по результатам JTAGenum!):
// D1=5  D2=4  D5=14  D6=12  D7=13  D0=16   (GPIO0/2 только если надо, GPIO15 не использовать)
#define PIN_TCK 14   // D5
#define PIN_TDI 12   // D6
#define PIN_TMS 13   // D7
#define PIN_TDO 4    // D2 (вход)
#define PIN_TRST 16  // D0, -1 если не подключен
#define PIN_SRST -1   // не подключен

// ==================== БЫСТРЫЕ GPIO ====================
static inline void jhigh(int pin) { GPOS = (1UL << pin); }
static inline void jlow(int pin)  { GPOC = (1UL << pin); }
static inline int  jread(int pin) { return (GPIN & (1UL << pin)) ? 1 : 0; }

static void jsetup(int pin, bool out) {
    if (pin < 0) return;
    pinMode(pin, out ? OUTPUT : INPUT);
    if (out) jlow(pin);
}

WiFiServer server(TCP_PORT);
WiFiClient client;

static inline void clock_pulse(bool tms, bool tdi) {
    if (tms) jhigh(PIN_TMS); else jlow(PIN_TMS);
    if (tdi) jhigh(PIN_TDI); else jlow(PIN_TDI);
    // TDI/TMS защёлкиваются по фронту TCK
    jhigh(PIN_TCK);
    jlow(PIN_TCK);
}

void setup() {
    Serial.begin(115200);
    jsetup(PIN_TCK, true);
    jsetup(PIN_TDI, true);
    jsetup(PIN_TMS, true);
    jsetup(PIN_TDO, false);
    jsetup(PIN_TRST, true);
    if (PIN_TRST >= 0) jhigh(PIN_TRST);      // TRST не активен (idle high)
    jlow(PIN_TCK);

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("\nConnecting");
    while (WiFi.status() != WL_CONNECTED) { delay(300); Serial.print("."); }
    Serial.printf("\nOK. IP: %s  port: %d\n", WiFi.localIP().toString().c_str(), TCP_PORT);
    server.begin();
    server.setNoDelay(true);
}

void loop() {
    if (!client || !client.connected()) {
        if (client) client.stop();
        client = server.available();
        if (!client) { delay(10); return; }
        client.setNoDelay(true);
        Serial.println("OpenOCD connected");
    }
    // вычитать всё, что пришло
    int n = client.available();
    while (n-- > 0) {
        char ch = (char)client.read();
        switch (ch) {
        case 'c': clock_pulse(0, 0); break;
        case 'd': clock_pulse(0, 1); break;
        case 'e': clock_pulse(1, 0); break;
        case 'f': clock_pulse(1, 1); break;
        case 'R': client.write(jread(PIN_TDO) ? '1' : '0'); break;
        case 'r': if (PIN_SRST >= 0) jlow(PIN_SRST); break;
        case 's': if (PIN_SRST >= 0) jhigh(PIN_SRST); break;
        case 't': if (PIN_TRST >= 0) jlow(PIN_TRST); break;
        case 'u': if (PIN_TRST >= 0) jhigh(PIN_TRST); break;
        case 'B': case 'b': break;           // индикация — игнор
        case 'Q': client.stop(); Serial.println("closed"); return;
        default: break;                      // неизвестное — игнор
        }
    }
}
