#!/bin/bash
# Разведка Humax STB в локальной сети.
# Usage: ./scan.sh <IP приставки>
#    или ./scan.sh discover  — найти приставку в сети

set -e

if [ "$1" = "discover" ] || [ -z "$1" ]; then
    echo "=== Поиск устройств в сети ==="

    # Определить подсеть
    SUBNET=$(ip -4 route | grep -m1 'src' | awk '{print $1}' 2>/dev/null || \
             ifconfig | grep -A1 'en0' | grep 'inet ' | awk '{print $2}' | sed 's/\.[0-9]*$/.0\/24/')
    echo "Подсеть: ${SUBNET:-192.168.1.0/24}"

    echo -e "\n--- Ping sweep ---"
    nmap -sn "${SUBNET:-192.168.1.0/24}" 2>/dev/null | grep -E 'scan report|MAC'

    echo -e "\n--- UPnP SSDP discover ---"
    echo -e "M-SEARCH * HTTP/1.1\r\nHOST:239.255.255.250:1900\r\nMAN:\"ssdp:discover\"\r\nMX:3\r\nST:upnp:rootdevice\r\n\r\n" | \
        nc -u -w3 239.255.255.250 1900 2>/dev/null || echo "(nc не доступен, используй upnp_exploit.py discover)"

    echo -e "\nДля полного скана: $0 <IP>"
    exit 0
fi

TARGET="$1"
echo "=== Скан Humax STB: $TARGET ==="

echo -e "\n--- [1] TCP full port scan ---"
nmap -sV -p- --open -T4 "$TARGET"

echo -e "\n--- [2] UDP key ports ---"
sudo nmap -sU -p 53,67,68,1900,5353 "$TARGET" 2>/dev/null || \
    echo "(нужен sudo для UDP скана)"

echo -e "\n--- [3] UPnP device info ---"
# Попробовать стандартные UPnP порты
for PORT in 49152 49153 49154 8080 80; do
    URL="http://$TARGET:$PORT/description.xml"
    echo "Пробуем $URL..."
    RESP=$(curl -s --connect-timeout 2 "$URL" 2>/dev/null)
    if [ -n "$RESP" ]; then
        echo "НАЙДЕНО на порту $PORT:"
        echo "$RESP" | head -50
        echo
        break
    fi
done

echo -e "\n--- [4] OpenSSL vulnerability check ---"
# CCS injection (CVE-2014-0224)
for PORT in 443 8443; do
    echo "Проверка CCS injection на :$PORT..."
    echo | timeout 5 openssl s_client -connect "$TARGET:$PORT" 2>&1 | \
        grep -E 'Protocol|Cipher|Server certificate' || echo "(порт $PORT закрыт или нет TLS)"
done

echo -e "\n--- [5] Быстрая проверка типичных сервисов ---"
# Telnet
echo -n "Telnet (23): "
nc -z -w2 "$TARGET" 23 2>/dev/null && echo "ОТКРЫТ!" || echo "закрыт"

# FTP (tinyftp)
echo -n "FTP (21): "
nc -z -w2 "$TARGET" 21 2>/dev/null && echo "ОТКРЫТ!" || echo "закрыт"

# HTTP
echo -n "HTTP (80): "
nc -z -w2 "$TARGET" 80 2>/dev/null && echo "ОТКРЫТ!" || echo "закрыт"

# SSH
echo -n "SSH (22): "
nc -z -w2 "$TARGET" 22 2>/dev/null && echo "ОТКРЫТ!" || echo "закрыт"

echo -e "\n=== Готово ==="
echo "Следующий шаг: python3 upnp_exploit.py discover"
