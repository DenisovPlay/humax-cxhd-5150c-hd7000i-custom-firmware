#!/usr/bin/env python3
"""UART-логгер Humax CXHD-5150C через CP2102 (без зависимостей).

- Читает /dev/cu.usbserial-0001 (или $UART_PORT) на 115200 8N1.
- Всё принятое пишет в uart_rx.log (в каталоге скрипта) с таймстампами.
- TX: пишет содержимое uart_tx.cmd (по строке за раз, поддерживает \\xNN),
  после отправки файл очищает.
- Автопереподключение: адаптер может переэнумерироваться при включении
  приставки — скрипт сам откроет порт заново.
"""
import os
import re
import termios
import time
import select
import fcntl

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = os.environ.get("UART_PORT", "/dev/cu.usbserial-0001")
BAUD = int(os.environ.get("UART_BAUD", "115200"))
RX_LOG = os.path.join(HERE, "uart_rx.log")
TX_CMD = os.path.join(HERE, "uart_tx.cmd")
LOCK = os.path.join(HERE, "uart.pid")

# termios скорости
SPEEDS = {9600: termios.B9600, 19200: termios.B19200, 38400: termios.B38400,
          57600: termios.B57600, 115200: termios.B115200}

pid = os.getpid()
with open(LOCK, "w") as f:
    f.write(str(pid))
rxlog = open(RX_LOG, "ab", buffering=0)

def log_meta(msg):
    rxlog.write(("\n=== %s %s ===\n" % (time.strftime("%H:%M:%S"), msg)).encode())

log_meta("LOGGER START pid=%d port=%s baud=%d" % (pid, PORT, BAUD))

def open_port():
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    speed = SPEEDS.get(BAUD, termios.B115200)
    attrs[0] = 0            # iflag: raw
    attrs[1] = 0            # oflag: raw
    attrs[2] = attrs[2] & ~(termios.PARENB | termios.CSTOPB | termios.CSIZE) | termios.CS8 | termios.CLOCAL | termios.CREAD
    attrs[3] = 0            # lflag: raw, без эха
    attrs[4] = speed
    attrs[5] = speed
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd

def unescape(s):
    return re.sub(rb"\\x([0-9a-fA-F]{2})", lambda m: bytes([int(m.group(1), 16)]), s)

fd = None
buf = b""
last_meta = 0
while True:
    if fd is None:
        try:
            fd = open_port()
            log_meta("PORT OPEN")
        except OSError as e:
            now = time.time()
            if now - last_meta > 5:
                log_meta("PORT OPEN FAILED: %s" % e)
                last_meta = now
            time.sleep(1)
            continue
    try:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            data = os.read(fd, 65536)
            if data:
                ts = time.strftime("%H:%M:%S")
                rxlog.write(("[%s] " % ts).encode() + data.replace(b"\r", b"\n") + (b"\n" if not data.endswith(b"\n") else b""))
        # TX-команды
        if os.path.exists(TX_CMD):
            try:
                content = open(TX_CMD, "rb").read().strip()
            except OSError:
                content = b""
            if content:
                os.remove(TX_CMD)
                for line in content.split(b"\n"):
                    line = unescape(line.strip())
                    if not line:
                        continue
                    os.write(fd, line + b"\r")
                    log_meta("TX: %r" % line)
                    time.sleep(0.05)
    except OSError as e:
        log_meta("READ ERROR: %s — reopens" % e)
        try:
            os.close(fd)
        except OSError:
            pass
        fd = None
        time.sleep(1)
