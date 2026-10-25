#!/bin/sh
# Start the local Humax/OnLime portal stack. Must run as root (ports 53/80/443).
set -u
HERE=/Users/andrey/Desktop/humax/humax-gpl
cd "$HERE" || exit 1

if [ "$(id -u)" != "0" ]; then
    echo "ERROR: run as root: sudo $0" >&2
    exit 1
fi

mkdir -p logs certs panel

echo "[start] stopping old processes"
pkill -f "dns_spy.py" 2>/dev/null || true
pkill -f "dns_poison.py" 2>/dev/null || true
pkill -f "portal_trap.py" 2>/dev/null || true
pkill -f "portal_server.py" 2>/dev/null || true
sleep 0.5

echo "[start] starting DNS poison on :53"
echo "[start] starting portal server on :80/:443/:5080/:5001"
/usr/bin/python3 "$HERE/start_services.py"
sleep 1

echo "[start] processes:"
ps -o pid,user,command -p "$(cat "$HERE/logs/dns.pid")" 2>/dev/null || true
ps -o pid,user,command -p "$(cat "$HERE/logs/portal.pid")" 2>/dev/null || true

echo "[start] listeners:"
lsof -nP -iUDP:53 -iTCP:80 -iTCP:443 -iTCP:5080 -iTCP:5001 2>/dev/null | grep -E "LISTEN|UDP" || true

echo "[start] quick checks:"
dig +short @127.0.0.1 humax.onlime.ru 2>/dev/null || true
curl -s -o /dev/null -w "  http launcher: %{http_code}\n" -H "Host: humax.onlime.ru" http://127.0.0.1/ || true
curl -s -o /dev/null -w "  http panel:    %{http_code}\n" http://127.0.0.1:5080/ || true
curl -sk -o /dev/null -w "  https panel:   %{http_code}\n" https://127.0.0.1:5001/ || true

echo "[start] done. dashboard: http://192.168.1.18:5080/dashboard"
