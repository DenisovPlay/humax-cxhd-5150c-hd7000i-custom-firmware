#!/bin/sh
# Read-only status check for the local Humax/OnLime portal stack.
set -u
HERE=/Users/andrey/Desktop/humax/humax-gpl
cd "$HERE" || exit 1

echo "=== processes ==="
ps aux | grep -E "dns_poison.py|portal_server.py|dns_spy.py|portal_trap.py" | grep -v grep || echo "(none)"

echo "=== listeners ==="
lsof -nP -iUDP:53 -iTCP:80 -iTCP:443 -iTCP:5080 -iTCP:5001 2>/dev/null | grep -E "LISTEN|UDP" || echo "(none)"

echo "=== DNS override ==="
dig +short @127.0.0.1 humax.onlime.ru 2>/dev/null || echo "(dig failed)"

echo "=== HTTP launcher ==="
curl -s -H "Host: humax.onlime.ru" http://127.0.0.1/ | head -20

echo "=== HTTP panel ==="
curl -s -o /dev/null -w "HTTP %{http_code}, %{size_download} bytes\n" http://127.0.0.1:5080/

echo "=== HTTPS panel ==="
curl -sk -o /dev/null -w "HTTP %{http_code}, %{size_download} bytes\n" https://127.0.0.1:5001/

echo "=== last STB events ==="
tail -40 events.jsonl 2>/dev/null || echo "(no events yet)"

echo "=== DNS log tail ==="
tail -20 dns_log.txt 2>/dev/null || echo "(no DNS log yet)"
