#!/usr/bin/env python3
"""Сканер бод-рейтов для неопознанного UART-сигнала (macOS, CP2102).
Каждые ~2.2с переключает скорость (macOS IOSSIOSPEED — любые значения),
пишет принятые сырые байты в scan_<baud>.bin. После нескольких
передёргиваний питания анализируем файлы: у правильного бода высокий
процент печатных ASCII."""
import os, sys, termios, time, struct, fcntl, select

PORT = os.environ.get("UART_PORT", "/dev/cu.usbserial-0001")
IOSSIOSPEED = 0x80045402
HERE = os.path.dirname(os.path.abspath(__file__))
# порядок: сначала вероятные нестандартные, потом стандартные
BAUDS = [460800, 921600, 230400, 500000, 250000, 153600, 76800,
         57600, 38400, 19200, 9600, 1562500]

def open_at(baud):
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    a = termios.tcgetattr(fd)
    a[0] = 0; a[1] = 0; a[3] = 0
    a[2] = (a[2] | termios.CLOCAL | termios.CREAD | termios.CS8) & ~(termios.PARENB | termios.CSTOPB)
    a[4] = a[5] = termios.B115200
    termios.tcsetattr(fd, termios.TCSANOW, a)
    fcntl.ioctl(fd, IOSSIOSPEED, struct.pack("I", baud))
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd

print("scanner start, rotating bauds every 2s; ctrl+C to stop", flush=True)
while True:
    for baud in BAUDS:
        try:
            fd = open_at(baud)
        except OSError as e:
            print("open fail @%d: %s" % (baud, e), flush=True)
            time.sleep(1)
            continue
        t0, data = time.time(), b""
        while time.time() - t0 < 2.0:
            r, _, _ = select.select([fd], [], [], 0.2)
            if r:
                try:
                    data += os.read(fd, 65536)
                except OSError:
                    break
        os.close(fd)
        if data:
            fn = os.path.join(HERE, "scan_%d.bin" % baud)
            with open(fn, "ab") as f:
                f.write(data)
        printable = sum(1 for b in data if 32 <= b < 127 or b in (10, 13))
        frac = printable / len(data) if data else 0.0
        print("baud=%-8d bytes=%-6d printable=%.0f%%" % (baud, len(data), frac * 100), flush=True)
