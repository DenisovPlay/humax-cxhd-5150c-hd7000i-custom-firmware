#!/usr/bin/env python3
"""DNS spy/forwarder: logs every query from the LAN, forwards to upstream 192.168.1.1.
Run as root (port 53). Log: dns_log.txt next to this file."""
import socket, threading, time, sys

UPSTREAM = ("192.168.1.1", 53)
LOG = open(sys.path[0] + "/dns_log.txt", "a", buffering=1)

def qname(data):
    try:
        i = 12; labels = []
        while i < len(data):
            L = data[i]
            if L == 0: break
            labels.append(data[i+1:i+1+L].decode("utf-8", "replace"))
            i += 1 + L
        qtype = int.from_bytes(data[i+1:i+3], "big") if i+3 <= len(data) else 0
        return ".".join(labels), qtype
    except Exception:
        return "?", 0

def handle(data, addr, sock):
    name, qt = qname(data)
    ts = time.strftime("%H:%M:%S")
    LOG.write(f"{ts} {addr[0]} Q {name} type={qt}\n")
    print(f"{ts} {addr[0]} Q {name} type={qt}", flush=True)
    try:
        up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        up.settimeout(3)
        up.sendto(data, UPSTREAM)
        resp, _ = up.recvfrom(4096)
        sock.sendto(resp, addr)
        up.close()
    except Exception as e:
        LOG.write(f"{ts} {addr[0]} ERR {e}\n")

def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 53))
    print("DNS spy listening on 0.0.0.0:53, upstream 192.168.1.1", flush=True)
    while True:
        data, addr = sock.recvfrom(4096)
        threading.Thread(target=handle, args=(data, addr, sock), daemon=True).start()

main()
