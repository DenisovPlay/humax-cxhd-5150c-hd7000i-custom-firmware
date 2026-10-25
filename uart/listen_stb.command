#!/bin/bash
# Прослушка приставки Humax CXHD-5150C (MAC 08:eb:74:8c:c8:c0).
# Запуск: двойной клик по файлу (или bash listen_stb.command)
# Затем ПЕРЕДЁРНУТЬ питание приставки и смотреть вывод ~60 секунд.
#
# Что ловим:
#  - DHCP DISCOVER / ARP / любые пакеты от приставки  → ядро v8 ЖИВО
#  - UDP на порт 6666 — это netconsole и маяки "v8-ALIVE" (тогда же смотреть
#    полный dmesg прямо здесь)
echo "=== Слушаем эфир от приставки 08:eb:74:8c:c8:c0. Передёрните питание! ==="
echo "=== Ctrl+C — выход ==="
sudo tcpdump -i en0 -n -e ether host 08:eb:74:8c:c8:c0 or udp port 6666 2>/dev/null || \
  sudo tcpdump -i en0 -n ether host 08:eb:74:8c:c8:c0
