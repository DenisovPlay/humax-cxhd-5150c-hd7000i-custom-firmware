#!/bin/sh
# Stop the local Humax/OnLime portal stack.
set -u
HERE=/Users/andrey/Desktop/humax/humax-gpl
cd "$HERE" || exit 1

if [ "$(id -u)" != "0" ]; then
    echo "ERROR: run as root: sudo $0" >&2
    exit 1
fi

pkill -f "portal_server.py" 2>/dev/null || true
pkill -f "dns_poison.py" 2>/dev/null || true
sleep 0.5
echo "[stop] stopped panel + DNS poison (dns_spy.py, if any, was already replaced)"
