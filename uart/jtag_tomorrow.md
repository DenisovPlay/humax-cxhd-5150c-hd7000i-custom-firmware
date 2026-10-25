# ЗАВТРА: JTAG-дамп за 30 минут — пошаговый план

## ЭТАП 0: Сегодня вечером (5 минут)
- [x] OpenOCD установлен (0.12.0)
- [ ] Установить Arduino IDE + ESP8266 support (если нет)
- [ ] Открыть uart/esp8266_remote_bitbang/esp8266_remote_bitbang.ino
- [ ] Вписать WiFi SSID и пароль (строки WIFI_SSID / WIFI_PASS)
- [ ] (опционально) подключить D1 Mini по USB и прошить скетч заранее

## ЭТАП 1: Прошивка ESP8266 (если не сделал вчера)
1. Подключи D1 Mini к Mac через USB Type-C
2. В Arduino IDE: Tools → Board → LOLIN(WEMS) D1 R2 & mini
3. Tools → Port → /dev/tty.usbserial-*
4. Upload (кнопка со стрелкой →)
5. Открой Serial Monitor (115200) — увидишь IP адрес ESP8266

## ЭТАП 2: Подключение к JTAG (5 минут)
Чёрная 2×4 гребёнка на плате (единственная распаянная):

```
D1 Mini → Приставка
─────────────────────
D5 (GPIO14) → TCK  
D6 (GPIO12) → TDI
D7 (GPIO13) → TMS
D2 (GPIO4)  → TDO
D0 (GPIO16) → TRST (может быть не нужен)
GND         → GND
```

⚠️ VCC НЕ ПОДКЛЮЧАЙ! (3.3V от приставки, не от D1 Mini)

### Если не знаешь какой пин TCK/TDI/TMS/TDO:
Запуши JTAGenum скетч (uart/esp8266_remote_bitbang/JTAGenum/) — он
переберёт все комбинации автоматически и скажет где что.

## ЭТАП 3: Дамп CFE (10 минут)
```bash
# В терминале 1: узнаем IP ESP8266 из Serial Monitor (или роутер)
export ESP_IP=192.168.1.XXX  # ← замени на реальный IP!

# Подключаемся и дампируем весь флеш (32 МБ — можно всё):
openocd -f /Users/andrey/Desktop/humax/uart/openocd_bcm7405.cfg \
  -c "init; halt; dump_image /Users/andrey/Desktop/humax/hdf_work/full_flash.bin 0xBFC00000 0x2000000; exit"
```

## ЭТАП 4: Если дамп получен (5 минут)
```bash
# Проверка что это наш лоадер:
strings full_flash.bin | grep -i "loader\|Y5\|humax"

# Поиск мастер-ключа (по паттернам из Y4.11):
python3 -c "
d = open('full_flash.bin','rb').read()
# AES S-box
i = d.find(bytes.fromhex('637c777bf26b6fc5'))
print('AES S-box @', hex(i) if i >= 0 else 'не найден')
# SHA-256 K table
j = d.find(bytes.fromhex('428a2f9871374491'))
print('SHA-256 K @', hex(j) if j >= 0 else 'не найдена')
"
```

## ЭТАП 5: Если нужно — полная карта JTAG через JTAGenum
Если стандартный пинаут не сработал:
1. Прошей JTAGenum скетч
2. Serial Monitor покажет все найденные JTAG-пины
3. Обнови пины в основном скетче
4. Перепрошей и продолжай с ЭТАПА 3
