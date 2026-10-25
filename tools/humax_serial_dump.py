#!/usr/bin/env python3
"""Дампер Humax STB — циклический (ждёт пока ты поднесёшь пины).

Крутилка: отправляет 0x06 каждые 2с и слушает. Как только получен ответ —
переходит к чтению дампа.

  python3 humax_serial_dump.py /dev/tty.usbserial-0001 [output.bin]
"""
import serial, sys, time

ACK = 0x06
TOTAL = 0x62000  # 401408 bytes

def dump(port, out, total=TOTAL, baud=115200):
    s = serial.Serial(port, baud, bytesize=8, parity='N', stopbits=1, timeout=0.5)
    print(f"[*] {port} @ {baud} — ожидаю подключение (поднеси пины)...")
    s.reset_input_buffer()
    s.reset_output_buffer()

    # ─── Фаза 1: циклический CONNECT до ответа ───
    attempt = 0
    first_byte = None
    while True:
        attempt += 1
        s.write(bytes([ACK]))
        s.flush()
        # слушаем 1.5с
        deadline = time.time() + 1.5
        buf = bytearray()
        while time.time() < deadline:
            b = s.read(1)
            if b:
                buf.extend(b)
                if len(buf) >= 1:
                    first_byte = buf[0]
                    break
        if first_byte is not None:
            break
        # каждые 10 попыток — статус
        if attempt % 10 == 0:
            print(f"\r[*] Попытка {attempt}... (поднеси TX/RX к пинам и включи приставку)", end="", flush=True)
        time.sleep(0.5)  # пауза между попытками

    print(f"\n[+] Ответ получен: {first_byte:#04x} (попытка {attempt})")
    print(f"[*] Начинаю чтение {total} байт...")
    s.timeout = 3  # увеличиваем таймаут для данных

    data = bytearray(first_byte.to_bytes(1, 'big'))
    last_pct = 0
    t0 = time.time()

    for offset in range(1, total):
        b = s.read(1)
        if not b:
            elapsed = time.time() - t0
            print(f"\n[!] Таймаут на байте {offset} ({offset:#x}), прошло {elapsed:.1f}с")
            break
        data.extend(b)
        s.write(bytes([ACK]))

        pct = (offset + 1) * 100 // total
        if pct >= last_pct + 2:
            speed = (offset + 1) / max(0.001, time.time() - t0)
            print(f"\r[*] {pct:3d}% ({offset+1}/{total}) {speed:.0f} B/s", end="", flush=True)
            last_pct = pct

    elapsed = time.time() - t0
    print(f"\n[*] Получено {len(data)} байт за {elapsed:.1f}с")

    if len(data) > 0:
        with open(out, "wb") as f:
            f.write(data)
        print(f"[*] Сохранено: {out} ({len(data)} байт)")
        print(f"[*] Первые 64: {data[:64].hex()}")
        for magic, name in [(b"\x00\x12", "HDF"), (b"hsqs", "SquashFS"),
                            (b"\x1f\x8b", "GZIP"), (b"\x7fELF", "ELF"),
                            (b"CFE", "CFE")]:
            pos = data.find(magic)
            if pos >= 0:
                print(f"[*] Магия {name} на оффсете {pos:#x}")
    s.close()
    return len(data) > 100

if __name__ == "__main__":
    if len(sys.argv) < 2:
        import glob
        ports = (glob.glob("/dev/tty.usbserial-*") +
                 glob.glob("/dev/tty.SLAB*") +
                 glob.glob("/dev/tty.usbmodem*"))
        if ports:
            print(f"Найдены порты: {ports}")
            print(f"Usage: {sys.argv[0]} <port> [output.bin]")
        else:
            print("Порты не найдены. Подключи CP2102.")
        sys.exit(1)

    port = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "stb_flash.bin"
    baud = int(sys.argv[3]) if len(sys.argv) > 3 else 115200

    ok = dump(port, out, baud=baud)
    sys.exit(0 if ok else 1)
