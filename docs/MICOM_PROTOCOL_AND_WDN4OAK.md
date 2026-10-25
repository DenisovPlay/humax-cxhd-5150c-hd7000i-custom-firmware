# MICOM-протокол + WDN4OAK + Lzrw1 — финальный разбор «до костей» (2026-10-25)

## 1. MICOM = /dev/ttyS2 @ 115200 (ДОКАЗАНО по humaxtv FOX T2)

### Транспорт
```
open64("/dev/ttyS2", 0x880)        // write-only
open64("/dev/ttyS2", 0x801)        // read-only
termios: c_iflag=4, c_cflag=0x18B2 (= CS8|CREAD|CLOCAL|B115200)
tcsetattr(fd, TCSANOW=0x540E, &t)  → tcflush(fd, 0)
```
**UART3 BCM7405** (0x10400b80, третий 16550). Не I2C!

### Формат пакета (из micom_tx @ 0x90D4FC)
```
[cmd][total_len][sub/seq][payload...][checksum]
checksum = (Σ bytes[1..len-1]) & 0xFF   // аддитивная, пишется в конец
write(fd, packet, len)                   // ОДИН write на пакет
```

### Реестр команд (по xref'ам на micom_tx в humaxtv)
| cmd | раз | типичное назначение (по контексту) |
|---|---|---|
| 0x01 | 3 | системные (старт/версия) |
| 0x02 | 6 | дисплей/LED (самая частая) |
| 0x03 | 1 | — |
| 0x05 | 2 | инициализация (sub=0x17/0x02) |
| 0x06 | 1 | — |
| 0x0E | 1 | — |
| 0x12 | 1 | — |
| 0x13 | 1 | — |
| 0x17 | 1 | — |
| 0x87 | — | код успешного ответа (в response[2]) |

### ГЛАВНОЕ: кормление watchdog из userspace НЕТ!
Единственный write на ttyS2 во всём 6.9MB humaxtv — внутри micom_tx.
Периодических отправок нет. **Linux не обязан кормить сторож.**
(Согласуется с hummy.tv: nosettop-загрузки живут вечно.)

### Вывод для нашей коробки
Раз сторож не нужен живому ядру → наш 13-15с цикл = **лоадер отвергает
образ на этапе копирования** → прыжок в bootrom 0xBFE00000 → ребут →
цикл. Это **блоб-гейт**: нулевой 256B-блоб фейлит проверку.
(v15: SoC-watchdog отключён, цикл остался → сторож не при чём!)

## 2. WDN4OAK+ распакован (8 инсталляторов = 8 дубликатов!)

InstallShield3 cab → idecomp (python, github lephilousophe/idecomp):
```
tools/wdn4oak/FV3Dll.dll   — библиотека протокола
tools/wdn4oak/WDN4OAK.exe  — GUI (Delphi, 115200/9600bps, COM-порт)
```

### FV3Dll.dll экспортирует (objdump):
```
DownloadData     — прошивка STB через COM-порт
UploadData       — ЧТЕНИЕ ДАННЫХ ИЗ STB (!!!)
UploadSystemID   — чтение System ID из STB
GetIRDModel      — определение модели
HnfToHDF, RawToHnf, V3HnfToHnf — конвертеры форматов
```
Строки: «Humax STB Connection...», «PC to STB»/«STB to PC»,
«Transferring STB action mode...», **«Transferring and Receiving STB
EEPROM data...»** — серийный дамп EEPROM через COM!

**Это канал чтения без JTAG** — если наш Y5.06 поддерживает серийный
протокол (в таблице ошибок есть E-ut «UART RX/TX Time Out» — значит,
UART-загрузка в семье ЕСТЬ!).

## 3. Lzrw1 = кодек флага 0x80 (НЕ zlib!)

FV3Dll.dll содержит LZRW1 (Росс Уильямс, public domain):
«Lzrw1 : successfully compressed/decompressed at».
Это тот самый кодек, которым humidify сжимает блоки HDF с флагом 0x80.
Обычный zlib его не берёт (мы проверяли — «incorrect header check»).

## 4. HD-FOX T2 L7.27 (loaders/cfe_hdfoxt2.bin) — наш mipsel-родственник

- «Programming MICOM...» / «Programming EEPROM...» — лоадер умеет
  программировать MICOM и EEPROM (фабричный сервис!)
- «USB Serial Port», «usb2serial», «16550 DUART» — серийная загрузка
- «console=ttyS0,115200» — дефолтный cmdline ядра от лоадера!
- «Boot block checksum is invalid» — проверка boot block
- Полный download/upload UI в OSD («Download Progress», «Uploading...»)

## 5. IA type-3 конфиги — БД каналов
PTCCX10103 type-3 @0x130000: `[06 00 00 03][BE16-пары частот]...`
= счётчик + таблица частот (транспондеров). Не критично.

## 6. СЕРИЙНЫЙ ПРОТОКОЛ OAK — ДЕКОДИРОВАН ПОЛНОСТЬЮ (FV3Dll.dll дизасм)

### Переменные протокола (глобалы DLL):
```
[0x4588C0] MODE   : 0=idle, 1=connected, 2=xfer, 3=eeprom, 4=done, 6=error
[0x4588C1] STATE  : счётчик шагов handshake / приёма
[0x4588C2] CONN   : флаг подключения
[0x4588C3] TX_BYTE: одиночный байт на отправку
[0x4588C4] SIZE   : оставшийся размер передачи (32-bit, убывает)
[0x4588C8] CHUNK  : 0x2000 (8192 = 8КБ)
[0x4588CC] RX_CNT : счётчик принятых байт в чанке
TOTAL = 0x62000 = 401408 байт (весь читаемый объём)
```

### Протокол (байт-в-байт с ACK):
```
PC → STB: 0x06               (CONNECT — вход в режим)
STB → PC: <ответ>            (лоадер подтверждает вход)
Цикл чтения по 0x2000:
  STB → PC: data_byte
  PC → STB: 0x06             (ACK на КАЖДЫЙ байт!)
  ... × 0x2000 ...
  SIZE -= 0x2000
  PC → STB: 0x06             (подтверждение чанка)
Прогресс = (0x62000 - SIZE) × 100 / 0x62000
```

### Экспортные функции FV3Dll.dll:
- DownloadData → прошивка в STB (тот же протокол, данные → STB)
- UploadData → **заглушка (ret) в этой версии** — нереализована
- UploadSystemID → читает System ID (маленький дамп через тот же механизм)
- GetIRDModel → определение модели (запрос → ответ)

### Инструмент готов: `tools/humax_serial_dump.py`
```bash
pip3 install pyserial
python3 tools/humax_serial_dump.py /dev/tty.usbserial-XXX stb_flash.bin
```

### Как подключить:
1. CP2102: TX→RX_приставки, RX→TX_приставки, GND→GND
2. Включи приставку с зажатой кнопкой (режим Download)
3. Запусти дампер — он отправит 0x06 и начнёт читать

```
Вкл → лоадер → читает kernel-партицию → 262B hdr валиден (маркер 01 00)
→ копирует стрим на 0x800B0000 (по Y4.11-копировщику)
→ [НОВОЕ] проверяет 256B-блоб против содержимого → FAIL (нули!)
→ jalr 0xBFE00000 (bootrom) → чип-резет → 13-15с цикл
```
- Чужой сток с настоящим блобом → блоб ОК, но расшифровка мусор
  → exception handler лоадера «blocks forever» → статичный логотип
- Наш plaintext с нулевым блобом → блоб-фейл → bootrom-цикл
- **Промежуточного состояния нет** — блоб это бинарный гейт

### Пути вперёд (приоритет):
1. **JTAG-дамп CFE** (ESP8266 в пути) → рецепт блоба из Y5.06
2. **WDN4OAK через CP2102 на UART1** — серийный UploadData → дамп CFE без JTAG
   (подключить CP2102 к UART-пинам, запустить WDN4OAK.exe под wine/Crossover,
   попробовать в режиме Download при старте)
3. Вскрыть FV3Dll.dll дизасмом (x86) → серийный протокол → свой инструмент на Mac
