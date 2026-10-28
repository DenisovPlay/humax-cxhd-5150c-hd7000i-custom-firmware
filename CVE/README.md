# CVE Toolkit — Humax CXHD-5150C / HD FOX T2

Инструменты для эксплуатации уязвимостей прошивки на рабочей приставке.
Платформа: BCM7213, MIPS32 LE, Linux 2.6.18, uClibc 0.9.29, нет ASLR.

## Порядок атаки

```
1. scan.sh          → разведка (nmap, UPnP, SSL)
2. upnp_exploit.py  → UPnP discovery + SQL injection (без MitM)
3. server.py        → DNS hijack + HTTP exploit + reverse shell listener
4. opera_exploit.html → страница-эксплойт для Opera 9.80/Presto
5. shellcode.py     → генератор MIPS32 LE shellcode
6. reverse_shell.c  → исходник connect-back shell для кросс-компиляции
7. post_exploit.sh  → дамп mtd, ключей, отправка на сервер
```

## CVE по компонентам

### Opera 9.80 / Presto (браузер, root) — ГЛАВНЫЙ ВЕКТОР
| CVE | Тип | Доставка |
|-----|-----|----------|
| CVE-2012-6468 | Heap overflow (HTTP response) | MitM портала / HbbTV |
| CVE-2012-6470 | Memory corruption (GIF) | `<img>` на exploit-странице |
| CVE-2013-1638 | RCE (SVG clipPaths) | `<svg>` на exploit-странице |
| CVE-2013-1637 | RCE (DOM events) | JS на exploit-странице |
| CVE-2012-6465 | Memory corruption (SVG) | `<svg>` на exploit-странице |

### OpenSSL 1.0.0a — MitM enabler
| CVE | Использование |
|-----|--------------|
| **CVE-2014-0224** | CCS injection → MitM HTTPS → подмена портала |
| CVE-2012-2110 | ASN.1 buffer overflow (если STB парсит внешние сертификаты) |
| CVE-2014-0195 | DTLS buffer overrun → RCE (если DTLS используется) |
| CVE-2010-3864 | TLS extension heap overflow (multi-threaded) |

**Heartbleed (CVE-2014-0160) НЕ применим** — только ветка 1.0.1+.

### libpng 1.2.25
| CVE | CVSS | Доставка |
|-----|------|----------|
| **CVE-2010-1205** | 9.8 | Crafted PNG через браузер/DLNA/HbbTV |

### libcurl 7.19.6
| CVE | Условие |
|-----|---------|
| CVE-2013-2174 | `curl_easy_unescape()` с нашим URL |
| CVE-2019-5436 | TFTP heap overflow (если STB использует TFTP) |

### FreeType ~6.3.18
| CVE | Доставка |
|-----|----------|
| CVE-2010-1797 | CFF font через CSS `@font-face` |
| CVE-2011-3256 | Type 1 font через SVG / CSS |

### uClibc 0.9.29
| CVE | Использование |
|-----|--------------|
| **CVE-2022-30295** | Предсказуемый DNS TXID → DNS poisoning без ARP spoof |

### UPnP/DLNA (humaxtv)
| Техника | Источник |
|---------|---------|
| SQL injection → SQLite → MIPS overflow | Cutlip, Black Hat 2012 |
| Format string (%s%s%s, 76 штук в humaxtv) | Строки бинарника |
| File upload через DMS | `/mnt/hd2/upload` |

## Цепочки атак

### Цепочка A: DNS poison → Opera RCE (самая простая)
```
dns_poison.py (CVE-2022-30295)
  → подмена *.humaxtvportal.com на наш IP
  → server.py раздаёт opera_exploit.html
  → Opera RCE → reverse shell (root)
  → post_exploit.sh
```

### Цепочка B: CCS MitM → Opera RCE (для HTTPS-портала)
```
CCS injection (CVE-2014-0224) через openssl/mitmproxy
  → MitM HTTPS-соединения к порталу
  → подмена страницы на exploit
  → Opera RCE → root
```

### Цепочка C: UPnP SQL injection → MIPS overflow (без MitM)
```
upnp_exploit.py → SSDP discover
  → SOAP SQLi через ContentDirectory Search
  → SQLite group_concat → buffer overflow
  → MIPS ROP/shellcode → root
```

### Цепочка D: HbbTV broadcast (без сети жертвы)
```
DVB-T передатчик (SDR + GNU Radio)
  → transport stream с HbbTV URL
  → STB загружает exploit app автоматически
  → Opera RCE → root
```

## Требования

- Python 3.8+
- nmap
- Metasploit (msfvenom для генерации shellcode)
- Опционально: bettercap/mitmproxy, Ghidra, SDR (для HbbTV)
- MIPS cross-compiler для reverse_shell.c: `apt install gcc-mipsel-linux-gnu`
