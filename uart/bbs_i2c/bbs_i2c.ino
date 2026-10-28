// BBS I2C bridge for Humax CXHD-5150C (BCM7213)
// Wemos D1 mini as USB-to-I2C master
// Connect: GPIO4 (pin "4") -> BBS SDA
//          GPIO5 (pin "5") -> BBS SCL
//          GND             -> BBS GND

#include <Wire.h>

void setup() {
  Serial.begin(115200);
  Wire.begin(4, 5); // SDA=GPIO4, SCL=GPIO5
  Wire.setClock(100000); // 100kHz standard I2C
  Wire.setClockStretchLimit(40000); // 40ms (default 230us — too short for BSC slave)
  delay(1000);
  Serial.println("\n=== BBS I2C Bridge ===");
  Serial.println("Commands:");
  Serial.println("  s - scan I2C bus (find devices)");
  Serial.println("  s2 - slow scan (10kHz)");
  Serial.println("  r <addr> <reg> <len> - read registers");
  Serial.println("  w <addr> <reg> <data> - write register");
  Serial.println("  p - probe known Broadcom BSC addresses");
  Serial.print("\n> ");
}

void i2c_scan(bool slow) {
  if (slow) {
    Wire.setClock(10000);
    Serial.println("Scanning I2C bus (10kHz)...");
  } else {
    Wire.setClock(100000);
    Serial.println("Scanning I2C bus (100kHz)...");
  }
  int found = 0;
  for (byte addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    byte err = Wire.endTransmission();
    if (err == 0) {
      Serial.print("  FOUND device at 0x");
      if (addr < 16) Serial.print("0");
      Serial.print(addr, HEX);
      Serial.print(" (");
      Serial.print(addr);
      Serial.println(")");
      found++;
    } else if (err == 4) {
      Serial.print("  ERROR at 0x");
      if (addr < 16) Serial.print("0");
      Serial.println(addr, HEX);
    }
    delay(2);
  }
  Serial.print("Done. Found ");
  Serial.print(found);
  Serial.println(" device(s).");
}

void probe_broadcom() {
  Serial.println("Probing known Broadcom BSC slave addresses...");
  // Broadcom BCM7xxx typical I2C slave addresses
  byte addrs[] = {0x08, 0x0A, 0x10, 0x20, 0x40, 0x48, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x68, 0x69, 0x6A, 0x6B};
  int n = sizeof(addrs) / sizeof(addrs[0]);
  for (int i = 0; i < n; i++) {
    Wire.beginTransmission(addrs[i]);
    byte err = Wire.endTransmission();
    Serial.print("  0x");
    if (addrs[i] < 16) Serial.print("0");
    Serial.print(addrs[i], HEX);
    Serial.print(": ");
    if (err == 0) Serial.println("ACK!");
    else if (err == 2) Serial.println("NACK");
    else if (err == 4) Serial.println("ERROR");
    else { Serial.print("err="); Serial.println(err); }
    delay(5);
  }
}

void i2c_read(byte addr, byte reg, int len) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  byte err = Wire.endTransmission(false); // repeated start
  if (err != 0) {
    Serial.print("TX error: ");
    Serial.println(err);
    return;
  }
  int got = Wire.requestFrom(addr, (uint8_t)len);
  Serial.print("Read 0x");
  if (addr < 16) Serial.print("0");
  Serial.print(addr, HEX);
  Serial.print(" reg 0x");
  if (reg < 16) Serial.print("0");
  Serial.print(reg, HEX);
  Serial.print(" [");
  Serial.print(got);
  Serial.print(" bytes]: ");
  while (Wire.available()) {
    byte b = Wire.read();
    if (b < 16) Serial.print("0");
    Serial.print(b, HEX);
    Serial.print(" ");
  }
  Serial.println();
}

void i2c_write(byte addr, byte reg, byte data) {
  Wire.beginTransmission(addr);
  Wire.write(reg);
  Wire.write(data);
  byte err = Wire.endTransmission();
  Serial.print("Write 0x");
  if (addr < 16) Serial.print("0");
  Serial.print(addr, HEX);
  Serial.print(" reg 0x");
  if (reg < 16) Serial.print("0");
  Serial.print(reg, HEX);
  Serial.print(" = 0x");
  if (data < 16) Serial.print("0");
  Serial.print(data, HEX);
  Serial.print(" -> ");
  Serial.println(err == 0 ? "OK" : "FAIL");
}

// parse hex: "0x1A" or "1A" or "26"
int parseVal(const char *s) {
  if (s[0] == '0' && (s[1] == 'x' || s[1] == 'X'))
    return strtol(s + 2, NULL, 16);
  // if all hex chars, treat as hex
  bool isHex = false;
  for (int i = 0; s[i]; i++) {
    if ((s[i] >= 'a' && s[i] <= 'f') || (s[i] >= 'A' && s[i] <= 'F')) {
      isHex = true;
      break;
    }
  }
  if (isHex) return strtol(s, NULL, 16);
  return atoi(s);
}

char cmd[64];
int cmdPos = 0;

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (cmdPos == 0) continue;
      cmd[cmdPos] = 0;
      cmdPos = 0;

      if (strcmp(cmd, "s") == 0) {
        i2c_scan(false);
      } else if (strcmp(cmd, "s2") == 0) {
        i2c_scan(true);
      } else if (strcmp(cmd, "p") == 0) {
        probe_broadcom();
      } else if (cmd[0] == 'r' && cmd[1] == ' ') {
        // r <addr> <reg> <len>
        char *p1 = cmd + 2;
        char *p2 = strchr(p1, ' ');
        if (p2) {
          *p2++ = 0;
          char *p3 = strchr(p2, ' ');
          int len = 1;
          if (p3) { *p3++ = 0; len = parseVal(p3); }
          i2c_read((byte)parseVal(p1), (byte)parseVal(p2), len);
        }
      } else if (cmd[0] == 'd' && cmd[1] == ' ') {
        // d <addr> <len> — raw read, no register address sent
        char *p1 = cmd + 2;
        char *p2 = strchr(p1, ' ');
        int len = 1;
        if (p2) { *p2++ = 0; len = parseVal(p2); }
        byte addr = (byte)parseVal(p1);
        int got = Wire.requestFrom(addr, (uint8_t)len);
        Serial.print("Raw read 0x");
        if (addr < 16) Serial.print("0");
        Serial.print(addr, HEX);
        Serial.print(" [");
        Serial.print(got);
        Serial.print(" bytes]: ");
        while (Wire.available()) {
          byte b = Wire.read();
          if (b < 16) Serial.print("0");
          Serial.print(b, HEX);
          Serial.print(" ");
        }
        Serial.println();
      } else if (cmd[0] == 'r' && cmd[1] == '2' && cmd[2] == ' ') {
        // r2 <addr> <regH> <regL> <len> — 16-bit register address read
        char *parts[4];
        char *p = cmd + 3;
        int n = 0;
        while (p && n < 4) { parts[n++] = p; p = strchr(p, ' '); if (p) *p++ = 0; }
        if (n >= 3) {
          byte addr = (byte)parseVal(parts[0]);
          byte rH = (byte)parseVal(parts[1]);
          byte rL = (byte)parseVal(parts[2]);
          int len = (n >= 4) ? parseVal(parts[3]) : 4;
          Wire.beginTransmission(addr);
          Wire.write(rH);
          Wire.write(rL);
          byte err = Wire.endTransmission(false);
          if (err != 0) {
            Serial.print("TX error: "); Serial.println(err);
          } else {
            int got = Wire.requestFrom(addr, (uint8_t)len);
            Serial.print("Read16 0x"); Serial.print(addr, HEX);
            Serial.print(" reg 0x"); if (rH<16) Serial.print("0");
            Serial.print(rH, HEX); if (rL<16) Serial.print("0");
            Serial.print(rL, HEX);
            Serial.print(" ["); Serial.print(got); Serial.print("]: ");
            while (Wire.available()) { byte b = Wire.read(); if (b<16) Serial.print("0"); Serial.print(b, HEX); Serial.print(" "); }
            Serial.println();
          }
        }
      } else if (cmd[0] == 't' && (cmd[1] == 0 || cmd[1] == ' ')) {
        // t [addr] — probe: write each byte 0x00-0xFF solo, report which NACK
        byte addr = 0x08;
        if (cmd[1] == ' ') addr = (byte)parseVal(cmd + 2);
        Serial.print("Probing write acceptance on 0x"); Serial.println(addr, HEX);
        int ack_count = 0;
        for (int i = 0; i < 256; i++) {
          Wire.beginTransmission(addr);
          Wire.write((byte)i);
          byte err = Wire.endTransmission();
          if (err == 0) {
            Serial.print("  0x"); if (i<16) Serial.print("0");
            Serial.print(i, HEX); Serial.print(":ACK ");
            ack_count++;
            if (ack_count % 8 == 0) Serial.println();
          }
          delay(1);
        }
        Serial.println();
        Serial.print("ACK count: "); Serial.println(ack_count);
        Serial.println("(256=all accepted, 0=address-only ACK)");
      } else if (cmd[0] == 'q' && (cmd[1] == 0 || cmd[1] == ' ')) {
        // q [addr] — write-then-read test: write byte, then read 4 back, for 0x00-0x0F
        byte addr = 0x08;
        if (cmd[1] == ' ') addr = (byte)parseVal(cmd + 2);
        Serial.print("Write-read test on 0x"); Serial.println(addr, HEX);
        for (int i = 0; i < 16; i++) {
          Wire.beginTransmission(addr);
          Wire.write((byte)i);
          byte err = Wire.endTransmission(true); // STOP, then new START for read
          Serial.print("  cmd 0x"); if (i<16) Serial.print("0"); Serial.print(i, HEX);
          if (err != 0) { Serial.print(" TX_ERR:"); Serial.println(err); continue; }
          delay(1);
          int got = Wire.requestFrom(addr, (uint8_t)4);
          Serial.print(" -> ["); Serial.print(got); Serial.print("]: ");
          while (Wire.available()) { byte b = Wire.read(); if (b<16) Serial.print("0"); Serial.print(b, HEX); Serial.print(" "); }
          Serial.println();
          delay(2);
        }
      } else if (cmd[0] == 'c' && cmd[1] == ' ') {
        // c <microseconds> — set clock stretch limit
        long us = atol(cmd + 2);
        Wire.setClockStretchLimit(us);
        Serial.print("Clock stretch limit: "); Serial.print(us); Serial.println(" us");
      } else if (cmd[0] == 'f' && (cmd[1] == 0)) {
        // f — frequency sweep read from 0x08
        Serial.println("Freq sweep on 0x08 reg 0x00:");
        long freqs[] = {10000, 50000, 100000, 400000};
        for (int i = 0; i < 4; i++) {
          Wire.setClock(freqs[i]);
          delay(5);
          Wire.beginTransmission(0x08);
          Wire.write((byte)0);
          byte err = Wire.endTransmission(false);
          Serial.print("  "); Serial.print(freqs[i]/1000); Serial.print("kHz: ");
          if (err != 0) { Serial.print("TX_ERR:"); Serial.println(err); continue; }
          int got = Wire.requestFrom((byte)0x08, (uint8_t)8);
          while (Wire.available()) { byte b = Wire.read(); if (b<16) Serial.print("0"); Serial.print(b, HEX); Serial.print(" "); }
          Serial.println();
        }
        Wire.setClock(100000);
      } else if (cmd[0] == 'w' && cmd[1] == ' ') {
        // w <addr> <reg> <data>
        char *p1 = cmd + 2;
        char *p2 = strchr(p1, ' ');
        if (p2) {
          *p2++ = 0;
          char *p3 = strchr(p2, ' ');
          if (p3) {
            *p3++ = 0;
            i2c_write((byte)parseVal(p1), (byte)parseVal(p2), (byte)parseVal(p3));
          }
        }
      } else {
        Serial.println("Commands: s s2 p r r2 d w t q f c");
      }
      Serial.print("> ");
    } else if (cmdPos < 62) {
      cmd[cmdPos++] = c;
    }
  }
}
