#!/usr/bin/env python3
"""Full TCP connect scan of the STB, low impact."""
import concurrent.futures
import socket
import sys
import time

HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.21"
START = int(sys.argv[2]) if len(sys.argv) > 2 else 1
END = int(sys.argv[3]) if len(sys.argv) > 3 else 65535
TIMEOUT = float(sys.argv[4]) if len(sys.argv) > 4 else 0.20
WORKERS = int(sys.argv[5]) if len(sys.argv) > 5 else 250


def check(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(TIMEOUT)
    try:
        if s.connect_ex((HOST, port)) == 0:
            return port
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass
    return None


def main():
    t0 = time.time()
    found = []
    print("scanning %s ports %d-%d timeout=%.2f workers=%d" %
          (HOST, START, END, TIMEOUT, WORKERS), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for result in ex.map(check, range(START, END + 1), chunksize=100):
            if result:
                found.append(result)
                print("OPEN %d" % result, flush=True)
    print("done in %.1fs, open: %s" % (time.time() - t0, found or "none"), flush=True)


if __name__ == "__main__":
    main()
