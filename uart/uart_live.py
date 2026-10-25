#!/usr/bin/env python3
"""Живой детектор UART-пинов (устойчивый к переэнумерации USB и любым ошибкам).

Запуск:  python3 /Users/andrey/Desktop/humax/uart/uart_live.py
Экран:   baud=... B/s print=...% |визуализация|
         *** READABLE baud=... *** — найден читаемый текст (говори Андрею).
Совет: щуп через резистор 1 кОм; GND на экран платы; касания короткие.
"""
import os, sys, termios, time, struct, fcntl, select

PORT = os.environ.get("UART_PORT", "/dev/cu.usbserial-0001")
IOSSIOSPEED = 0x80045402
HERE = os.path.dirname(os.path.abspath(__file__))
BAUDS = [460800, 921600, 230400, 500000, 250000, 153600, 76800,
         57600, 38400, 19200, 9600, 1562500]
ROTATE = 1.2  # сек на скорость

def try_open(baud):
    """Открыть порт на скорости; вернуть fd или None (не бросать!)."""
    try:
        fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        a = termios.tcgetattr(fd)
        a[0] = 0; a[1] = 0; a[3] = 0
        a[2] = (a[2] | termios.CLOCAL | termios.CREAD | termios.CS8) & ~(termios.PARENB | termios.CSTOPB)
        a[4] = a[5] = termios.B115200
        termios.tcsetattr(fd, termios.TCSANOW, a)
        fcntl.ioctl(fd, IOSSIOSPEED, struct.pack("I", baud))
        termios.tcflush(fd, termios.TCIOFLUSH)
        return fd
    except OSError as e:
        try: os.close(fd)
        except OSError: pass
        sys.stderr.write("\n[open %d failed: %s]\n" % (baud, e))
        return None

def pretty(data, n=48):
    out = []
    for b in data[-n:]:
        out.append(chr(b) if 32 <= b < 127 else ("·" if b == 0 else "#"))
    return "".join(out)

print("UART live detector (resilient). RXD->1k->pad, GND->shield. Ctrl+C — выход.", flush=True)
found = set()
baud = BAUDS[0]
fd = None
buf = b""
t_baud = time.time()
err_shown = 0

while True:
    # --- держим порт открытым, переподключаемся при любой проблеме ---
    if fd is None:
        fd = try_open(baud)
        if fd is None:
            if time.time() - err_shown > 3:
                sys.stdout.write("\r[порт недоступен, ретраю... (%s)]          " % PORT)
                sys.stdout.flush()
                err_shown = time.time()
            time.sleep(0.4)
            continue
        t_baud = time.time(); buf = b""

    # --- ротация скоростей ---
    if time.time() - t_baud >= ROTATE:
        os.close(fd); fd = None
        baud = BAUDS[(BAUDS.index(baud) + 1) % len(BAUDS)]
        continue

    # --- чтение ---
    try:
        r, _, _ = select.select([fd], [], [], 0.12)
        if r:
            got = os.read(fd, 65536)
            if got:
                buf += got
            else:
                raise OSError("eof")
    except OSError as e:
        sys.stderr.write("\n[device reset: %s — переподключаюсь]\n" % e)
        try: os.close(fd)
        except OSError: pass
        fd = None
        time.sleep(0.3)
        continue

    # --- индикация ---
    tail = buf[-4096:]
    printable = sum(1 for b in tail if 32 <= b < 127 or b in (10, 13))
    frac = printable / len(tail) if tail else 0.0
    uniq = len({b for b in tail if 32 <= b < 127})
    has_words = b"  " in tail or b"\n" in tail or b"\r" in tail
    rate = len(buf) / max(time.time() - t_baud, 0.1)
    sys.stdout.write("\rbaud=%-8d %6.0f B/s  print=%3.0f%%  uniq=%2d  |%s|   "
                     % (baud, rate, frac * 100, uniq, pretty(buf)))
    sys.stdout.flush()

    if len(tail) > 200 and frac > 0.5 and uniq >= 20 and has_words and baud not in found:
        found.add(baud)
        fn = os.path.join(HERE, "found_%d.bin" % baud)
        with open(fn, "wb") as f:
            f.write(tail)
        print("\n\n*** READABLE! baud=%d — сохранил uart/found_%d.bin — СКАЖИ АНДРЕЮ ***\n" % (baud, baud), flush=True)

    time.sleep(0.1)
