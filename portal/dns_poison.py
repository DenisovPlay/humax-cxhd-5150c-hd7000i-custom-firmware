#!/usr/bin/env python3
"""DNS forwarder with local overrides for the Humax/OnLime STB.

humax.onlime.ru (A) -> this Mac, so the STB loads the local panel.
Everything else is forwarded to the router (192.168.1.1).
Log: dns_log.txt next to this file.
"""
import argparse
import os
import re
import socket
import struct
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(HERE, "dns_log.txt")
LOG_LOCK = threading.Lock()

DEFAULT_UPSTREAM = "192.168.1.1"
DEFAULT_LOCAL_IP = "192.168.1.18"
OVERRIDES = {
    "humax.onlime.ru": DEFAULT_LOCAL_IP,
    "www.humax.onlime.ru": DEFAULT_LOCAL_IP,
    "humaxtvportal.com": DEFAULT_LOCAL_IP,
    "www.humaxtvportal.com": DEFAULT_LOCAL_IP,
}
WILDCARD = True  # answer junk host tokens (http:, 192.168.1.18:5080, "", 192.168.*) with local_ip


def is_wild_target(name):
    """The STB upgrade plugin strtok-splits URLs and resolves the scheme token
    as a hostname (e.g. 'http:', '192.168.1.18:5080', ''). Answer those locally."""
    if not name:
        return True
    if ":" in name:
        return True
    if name.startswith("192.168."):
        return True
    if not re.match(r"^[A-Za-z0-9._-]+$", name):
        return True
    return False


def log(line):
    ts = time.strftime("%H:%M:%S")
    with LOG_LOCK:
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write("%s %s\n" % (ts, line))
        except Exception:
            pass
    print("%s %s" % (ts, line), flush=True)


def parse_name(data, off, depth=0):
    if depth > 8:
        return "", off
    labels = []
    while off < len(data):
        length = data[off]
        if length == 0:
            off += 1
            break
        if length & 0xC0:
            if off + 1 >= len(data):
                break
            ptr = ((length & 0x3F) << 8) | data[off + 1]
            name, _ = parse_name(data, ptr, depth + 1)
            if name:
                labels.append(name)
            off += 2
            break
        labels.append(data[off + 1:off + 1 + length].decode("ascii", "replace"))
        off += 1 + length
    return ".".join(labels), off


def parse_question(data):
    """Return (lowercase name, qtype, qclass, offset after question) or None."""
    if len(data) < 12:
        return None
    i = 12
    labels = []
    while i < len(data):
        length = data[i]
        if length == 0:
            i += 1
            break
        if length & 0xC0:
            ptr = ((length & 0x3F) << 8) | data[i + 1] if i + 1 < len(data) else 0
            name, _ = parse_name(data, ptr)
            if name:
                labels.append(name)
            i += 2
            break
        if i + 1 + length > len(data):
            return None
        labels.append(data[i + 1:i + 1 + length].decode("ascii", "replace"))
        i += 1 + length
    if i + 4 > len(data):
        return None
    qtype, qclass = struct.unpack("!HH", data[i:i + 4])
    return ".".join(labels).lower(), qtype, qclass, i + 4


def header_flags(query, rcode=0):
    rd = query[2] & 0x01
    return 0x8000 | (rd << 8) | 0x0080 | (rcode & 0x0F)


def make_a_response(query, ip, ttl=5):
    q = parse_question(query)
    if not q:
        return None
    _name, _qtype, _qclass, qend = q
    header = query[:2] + struct.pack("!HHHHH", header_flags(query), 1, 1, 0, 0)
    question = query[12:qend]
    # name pointer to offset 12, type A, class IN, ttl, rdlength 4
    answer = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, ttl, 4) + socket.inet_aton(ip)
    return header + question + answer


def make_nodata_response(query):
    q = parse_question(query)
    if not q:
        return None
    _name, _qtype, _qclass, qend = q
    header = query[:2] + struct.pack("!HHHHH", header_flags(query), 1, 0, 0, 0)
    return header + query[12:qend]


def make_servfail_response(query):
    if len(query) < 12:
        return None
    return query[:2] + struct.pack("!HHHHH", header_flags(query, 2), 0, 0, 0, 0)


def handle(data, addr, sock, upstream, local_ip):
    q = parse_question(data)
    if q:
        name, qtype, _qclass, _qend = q
        tag = "%s Q %s type=%d" % (addr[0], name, qtype)
        if name in OVERRIDES:
            if qtype == 1:  # A
                resp = make_a_response(data, local_ip)
                if resp:
                    sock.sendto(resp, addr)
                    log(tag + " -> %s (local)" % local_ip)
                    return
            elif qtype in (28, 64, 65):  # AAAA / SVCB / HTTPS -> NODATA, force IPv4
                resp = make_nodata_response(data)
                if resp:
                    sock.sendto(resp, addr)
                    log(tag + " -> NODATA")
                    return
        elif WILDCARD and qtype == 1 and is_wild_target(name):
            resp = make_a_response(data, local_ip)
            if resp:
                sock.sendto(resp, addr)
                log(tag + " -> %s (wild)" % local_ip)
                return
        log(tag)
    else:
        log("%s Q <malformed>" % addr[0])

    up = None
    try:
        up = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        up.settimeout(3.0)
        up.sendto(data, (upstream, 53))
        resp, _ = up.recvfrom(65535)
        sock.sendto(resp, addr)
    except Exception as exc:
        log("%s ERR %s" % (addr[0], exc))
        resp = make_servfail_response(data)
        if resp:
            try:
                sock.sendto(resp, addr)
            except Exception:
                pass
    finally:
        if up is not None:
            try:
                up.close()
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=53)
    ap.add_argument("--upstream", default=DEFAULT_UPSTREAM)
    ap.add_argument("--local-ip", default=DEFAULT_LOCAL_IP)
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", args.port))
    log("DNS poison listening on 0.0.0.0:%d upstream=%s overrides=%s"
        % (args.port, args.upstream, ", ".join(sorted(OVERRIDES))))
    while True:
        data, addr = sock.recvfrom(65535)
        threading.Thread(target=handle, args=(data, addr, sock, args.upstream, args.local_ip),
                         daemon=True).start()


if __name__ == "__main__":
    main()
