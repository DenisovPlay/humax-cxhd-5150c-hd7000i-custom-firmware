#!/usr/bin/env python3
"""Дампер Humax STB через серийный порт (протокол OAK/WDN).

Протокол (из FV3Dll.dll, обратный инжиниринг):
  PC→STB: 0x06 (CONNECT)
  STB→PC: ответ
  PC→STB: 0x06 (ACK, каждый байт подтверждается!)
  Цикл: STB→PC byte, PC→STB 0x06, ... chunk 0x2000 ...

Использование:
  python3 humax_serial_dump.py /dev/tty.usbserial-XXX [output.bin]
"""
import serial, sys, time

BAUD = 115200
ACK = 0x06
CHUNK = 0x2000
TOTAL = 0x62000  # 401408 bytes (default read size)

def dump(port="/dev/tty.usbserial-XXX", out="stb_dump.bin", total=TOTAL):
    s = serial.Serial(port, BAUD, bytesize=8, parity='N', stopbits=1, timeout=3)
    print(f"[*] Открыт {port} @ {BAUD}")
    print(f"[*] Читаю {total} байт ({total:#x})...")

    # CONNECT
    s.write(bytes([ACK]))
    print(f"[*] Отправлен CONNECT (0x06)")

    # Ждём первый ответ
    t0 = time.time()
    first = s.read(1)
    if not first:
        print("[!] Нет ответа от STB. Проверь подключение и режим Download.")
        print("[!] Нажми и держи кнопку на передней панели при включении.")
        s.close()
        return False
    print(f"[*] Первый ответ: {first.hex()} (через {time.time()-t0:.1f}с)")

    data = bytearray()
    last_progress = 0
    for chunk_start in range(0, total, CHUNK):
        chunk_data = bytearray()
        for i in range(CHUNK):
            # ACK предыдущего байта
            s.write(bytes([ACK]))
            # Читаем байт
            b = s.read(1)
            if not b:
                print(f"\n[!] Таймаут на байте {chunk_start+i}")
                break
            chunk_data.extend(b)
            # Прогресс
            done = chunk_start + i + 1
            pct = done * 100 // total
            if pct >= last_progress + 5:
                print(f"\r[*] {pct}% ({done}/{total})", end="", flush=True)
                last_progress = pct
        data.extend(chunk_data)
        if len(chunk_data) < CHUNK:
            break

    print(f"\n[*] Получено {len(data)} байт")
    with open(out, "wb") as f:
        f.write(data)
    print(f"[*] Сохранено в {out}")
    s.close()
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <serial_port> [output.bin]")
        print(f"  Example: {sys.argv[0]} /dev/tty.usbserial-A50285BI stb_flash.bin")
        sys.exit(1)
    port = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "stb_flash.bin"
    ok = dump(port, out)
    sys.exit(0 if ok else 1)
