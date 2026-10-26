#!/usr/bin/env python3
"""
Мост: Serial (ESP8266 USB) <-> TCP localhost:3335 для OpenOCD remote_bitbang.

Использование:
  python3 uart/serial_bridge.py /dev/cu.usbserial-10 [baud]

Перед запуском:
  - Wemos прошит uart/esp8266_serial_bitbang/esp8266_serial_bitbang.ino
  - baud совпадает с Serial.begin() в скетче (по умолчанию 500000)
  - порт не занят Arduino IDE / Serial Monitor

Логи моста показывают, что реально летит в Wemos и обратно:
  TCP->SER — байты от OpenOCD (ожидаем 0x30..0x37, 'R', 'r'..'u')
  SER->TCP — ответы Wemos (0x30/0x31 на 'R')
Если SER->TCP весь 0x30 — TDO прижат к нулю; если 0x31 — к единице.
"""
import socket
import sys
import threading
import time
from collections import Counter

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/cu.usbserial-10"
BAUD = int(sys.argv[2]) if len(sys.argv) > 2 else 500000
TCP = 3335

print(f"[*] Serial {PORT} @ {BAUD} baud")
ser = serial.Serial(PORT, BAUD, timeout=0, write_timeout=1)
time.sleep(0.3)
ser.reset_input_buffer()

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", TCP))
srv.listen(1)
print(f"[*] Waiting for OpenOCD on localhost:{TCP} ...")
print("[*] После старта моста нажми RST на Wemos, если он не запустился.")

conn, addr = srv.accept()
conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
conn.settimeout(None)
print(f"[+] OpenOCD connected from {addr}")

stop = threading.Event()
lock = threading.Lock()
stats = {
    "tcp2ser": 0,
    "ser2tcp": 0,
    "cmds": Counter(),
    "first_tx": b"",
    "first_rx": b"",
    "last_rx": b"",
}
printed_tx = False
printed_rx = False


def hexdump(b):
    return " ".join(f"{x:02x}" for x in b)


def from_serial():
    global printed_rx
    while not stop.is_set():
        try:
            d = ser.read(256)
        except Exception as e:
            print(f"[!] serial read error: {e}")
            stop.set()
            return
        if d:
            with lock:
                stats["ser2tcp"] += len(d)
                if len(stats["first_rx"]) < 64:
                    stats["first_rx"] += d[: 64 - len(stats["first_rx"])]
                stats["last_rx"] = (stats["last_rx"] + d)[-8:]
                show = not printed_rx and stats["first_rx"]
                if show:
                    printed_rx = True
                    payload = hexdump(stats["first_rx"])
            if show:
                print(f"[first SER->TCP] {payload}")
            try:
                conn.sendall(d)
            except Exception:
                stop.set()
                return
        else:
            time.sleep(0.001)


def stats_loop():
    global printed_tx
    while not stop.is_set():
        time.sleep(2)
        with lock:
            tx = stats["tcp2ser"]
            rx = stats["ser2tcp"]
            cmds = stats["cmds"]
            first = stats["first_tx"]
            last_rx = stats["last_rx"]
            show = not printed_tx and first
            if show:
                printed_tx = True
                payload = hexdump(first)
            digits = sum(v for k, v in cmds.items() if 0x30 <= k <= 0x37)
            reads = cmds.get(ord("R"), 0)
            resets = sum(v for k, v in cmds.items() if 0x72 <= k <= 0x75)
            leds = cmds.get(ord("B"), 0) + cmds.get(ord("b"), 0)
            other = sum(cmds.values()) - digits - reads - resets - leds
        if show:
            print(f"[first TCP->SER] {payload}")
        print(
            f"[stats] TCP->SER {tx}B  SER->TCP {rx}B  "
            f"0-7={digits} R={reads} resets={resets} led={leds} other={other}  "
            f"lastSER=[{hexdump(last_rx)}]"
        )


threading.Thread(target=from_serial, daemon=True).start()
threading.Thread(target=stats_loop, daemon=True).start()

try:
    while not stop.is_set():
        try:
            d = conn.recv(256)
        except Exception as e:
            print(f"[!] tcp read error: {e}")
            break
        if not d:
            break
        with lock:
            stats["tcp2ser"] += len(d)
            for c in d:
                stats["cmds"][c] += 1
            if len(stats["first_tx"]) < 64:
                stats["first_tx"] += d[: 64 - len(stats["first_tx"])]
        try:
            ser.write(d)
        except Exception as e:
            print(f"[!] serial write error: {e}")
            break
finally:
    stop.set()
    time.sleep(0.2)
    try:
        conn.close()
    except Exception:
        pass
    try:
        ser.close()
    except Exception:
        pass
    with lock:
        print(
            f"[*] Done. TCP->SER {stats['tcp2ser']}B, "
            f"SER->TCP {stats['ser2tcp']}B"
        )
