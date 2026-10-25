# Реверс-инжиниринг Humax Y-лоадера (Y4.11, семейство CCX)

Источник: `research_for_other_hdfs/ia_humax/extracted/6tm_FPXCCX10016_Y411/1.hdfbin-0-000000.raw`
(393 192 байта, стрим type 0 из FPXCCX10016_Y411.hdf, Internet Archive).

## Идентификация

- **MIPS32 big-endian** (BE-платформа BCM7405 — как FOXSAT, не как наш mipsel!)
- База загрузки: **0x83350000** (подтверждено гистограммой lui+addiu ссылок)
- Вход: offset 8: `lui $t0,0x8335; addiu $t0,0x508; jr $t0`
- Заголовок CFE-типа: байт-свопнутая копия "Copyright (c) 1989-1999 NEC" (double-endian banner)
- `Loader Version %c%01x.%02x` → наш Y5.06 из того же кодового семейства
- Это НЕ чистый Broadcom CFE — монолитный Humax-лоадер (DDI-драйверы, MICOM, тюнер, I2C, флеш, HDF-механика)

## Архитектура безопасности (ГЛАВНОЕ)

**Схема СИММЕТРИЧНАЯ (AES + SHA), НЕ RSA!**

### Ключи в .rodata
- file offset 0x5fb80, 16 байт: **мастер-ключ AES-128** `6ac5e95712d6cd298239c5c1e2540fbe`
- file offset 0x5fb90, 0x80 байт: **8 зашифрованных AES-128 ключей** (по одному на тип данных/индекс)
- Лениво расшифровываются в BSS 0x833df6a8 по индексу: `AESbuf(BSS+idx*16, blob[idx*16..], master, 16)`
- Крипто-таблицы: AES S-box @0x52740, rcon @0x52734, SHA-256 K @0x5fc10, CRC32 @0x5316c

### Проверка подписи (код 0x41b00-0x41e80, VA 0x83391bxx)
```
SIGN_DecryptUpdate(data, len)   # 0x8338d2f0, вызывается на каждый чанк 0x8000
    → хеш-контекст (SHA-256, state в gp-области)
SIGN_DecryptFinal(sign32, 32)   # 0x8338d340
    digest  = SHA256-final          → буфер A (0x833c788c)
    chk     = AESbuf(sign32, master_key)  → буфер B (0x833c78ac)
    return  memcmp32(A, B)          # 0x83398fb0
```
Т.е. **sign = AES(SHA256(контент), ключ)** — подделываемо при знании ключа!

### Пути в коде
- `*** Signature Check` (строка 0x52b48, tab-префикс!) ← xref 0x41cac
- Печать 32 байт подписи по `%02x` перед проверкой
- `[INVOKED] DownloadToFlash` ← 0x413a8; `Programming... %d` ← 0x414c8
- `System ID Fail (c.%x:s.%x:e.%x)` ← 0x41858 — формат c=class? s=sysid e=? (три значения!)
- `Cannot write test mode flag!!!!!!!` ← 0x417ec — ТЕСТ-МОД пишется в EEPROM/MICOM
- Поблочный цикл: `Current Block Type`, `wrong Header Block-(%d)` ← 0x41924, `Decompress...`, `ERR_DECRYPT` ← 0x41b94
- `Application Block Number (0x%08X)` ← 0x42084, `>>> Application Down (%d)...` ← 0x420b8
- Функция 0x83390ffc: верификация флеша через uncached-окно **0xbfc00000+**, лимит 0x20000,
  "Fail to verify" (0x52940), "Error in Data Compare" ← 0x412f4

### Флаги HDF-блоков (расшифровка!)
- 0x80 = zlib-сжатие
- 0x08 = шифрование AES
- **младшие 3 бита = индекс ключа 0..7** (вращение по 8 ключам из блоба!)
- Внутренние HDF стока 5100C: флаги 0x08..0x0f и 0x88..0x8f — ровно эта схема

## EEPROM = MICOM (I2C)

- `DDI_EEPROM_Read/Write` → `MMAC_IIC_Read/Write` → устройства **micom0 / micom1**
  (строки @0x4d934+, код 0x30238/0x3026c) — EEPROM эмулируют фронт-панельные МК!
- Два банка, адресация 13-бит (offset & 0x1fff), банк выбирается по offset >= 0x2000
- Чанки по 0x20, retry 0x64, адрес устройства из таблицы по gp-0x7eb4
- Известные оффсеты Y4.11: **0x0c/16B** (sign — совпадает с «16B keyed» частью checksum 20B!),
  0x60/1B, 0xd4/4B (PowerMode), 0xe2/1B, 0xe4/1B
- Функции: ReadSysId, ReadLoaderVer, ReadHdfVer, ReadUpgradeFlag, **ReadTestModeFlag**,
  ReadLoaderSign, ReadAppSign, ReadGameSign (строки 0x4d0b0-0x4d6e0)

## Структура HDF CCX-семейства (отличия от нашего 5150C)

- Адреса блоков ОТНОСИТЕЛЬНЫЕ (0x0..0x40xxxx), не абсолютные 0x80100000+
- type 0x00 = стрим лоадера (обновление CFE!), type 0x01 = приложение, type 0x03 = конфиг/БД каналов
- checksum-блоки 32B (FPX/PT) или 128B (ffccx 2006) — эволюция формата
- checksum пишет humidify 1.0.4 СВОЙ (32B) — читается, но НЕ совместим с 5100C-стоком (20B)

## Проверено на нашем стоке (PRIMACOM 1.00.23, 5100C)

- 4 стрима: [262B hdr @0x80100000] [kernel inner HDF @0x80100400] [262B hdr @0x80300000] [rootfs inner HDF]
- Каждый checksum20 = **[16B keyed][SHA1(стрим)[-4:]]** — SHA-хвост подтверждён на всех 4
- Внутренние HDF: SysID 0000.0000-ffff.ffff (любой), блоки с шифрованием (0x08) + индекс ключа
- 256B-блобы в 262B-заголовках УНИКАЛЬНЫ у каждого файла/партиции (не family-wide!) —
  контентозависимые: подпись/ключи стрима. 256B = 2048 бит (RSA-2048?) или 16×AES-128 блоков
- Ключи Y4.11 НЕ подходят к 5100C (проверено: AES ECB/CBC × 17 ключей × md5/sha1/sha256) —
  у нашего подсемейства свой мастер-ключ → добывать из дампа НАШЕГО CFE

## Выводы и план

1. **Подпись НЕ RSA-стена** — AES+SHA с ключами в лоадере. Достаточно сдампить наш CFE (JTAG)
   → найти мастер-ключ/блоб по смещениям-аналогам → подделывать checksum-блоки и заголовки.
2. **Новый вектор — I2C/MICOM через BBS-колодку**: ESP8266 может выступить I2C-мастером
   (SDA/SCL/GND — 4 пина, распиновка известна из Gemini-отчёта). Цели: SysID, signs, TestModeFlag.
   Препятствие: EEPROM эмулирует MICOM — нужен его I2C-протокол (вероятно стандартные
   read/write по word-address, см. структуру вызова MMAC_IIC_Read).
3. Оффсеты Y4.11 не обязаны совпадать с Y5.06 — точную карту даст дамп нашего лоадера.
4. JTAG-приоритет при приходе ESP8266: dump CFE 0-0x100000 → ключи → генерация валидных HDF.

Инструменты: /tmp/disas.py (capstone BE mips), /tmp/xref*.py, /tmp/try_decomp.py,
строки: /tmp/loader_strings.txt. Venv капстоуна: /tmp/capvenv.
