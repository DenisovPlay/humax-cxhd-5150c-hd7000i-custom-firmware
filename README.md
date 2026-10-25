# Humax CXHD-5150C — карта проекта

Цель: оживить операторскую приставку OnLime (BCM7405, mipsel, лоадер Y5.06,
SysID 8050.8400) и получить Linux с root-доступом. Статус-документ:
`docs/V10_EXPERIMENTS.md` + `docs/LOADER_FULL_AUDIT.md`.

## Структура

### docs/ — только проверенные факты и сводки
- `HDF_FORMAT.md` — бинарный формат HDF (CRC, блоки, флаги)
- `LOADER_FULL_AUDIT.md` — полный аудит Y-лоадера: бут-цепочка, крипто,
  меню, бэкдоры, 13-секундное окно MICOM-watchdog
- `LOADER_Y411_RE.md` — реверс лоадера Y4.11 (ключи AES, EEPROM/MICOM)
- `V10_EXPERIMENTS.md` — хроника экспериментов v10-v13 + открытия
  (адрес 0x800B0000, формат gzip(ELF), стабы)
- `IA_ARCHIVE_FINDINGS.md`, `SATSAT_TELESPUTNIK.md` — разборы находок
- `our/` — наши рабочие логи (v6-v8, UART-сессии, письма, старые планы)
- `gemini/` — входящие отчёты Gemini (базы прошивок, порты, factcheck)
- `ixbt/dump.md` — дамп треда iXBT 60:4041 (RUCCAA, 1.00.48)

### firmwares/
- `genuine/` — родные прошивки: PRIMACOM 5100C 1.00.23, HD 7000i,
  ранний OnLime cxhd_5150c, 1.00.23 zip
- `custom/` — наши готовые к прошивке HDF (копия build/flash_kit)
- `ia_archive/` — 5 файлов с Internet Archive (внутри — лоадер Y4.11!)
- `foxsat/` — HD/HDR FOX T2 (mipsel-родственники, рабочие кастомы)
- `satsat/` — находки с satsat.info (7000i-дубликат, keybin2hdf)

### loaders/ — бинарники загрузчиков
- `loader_Y411_CCX_393k.bin` — полный Y-лоадер (эталон для реверса)
- `cfe_hdfoxt2.bin`, `cfe_foxsat_u754.bin`, `loader_from_hdfoxt2_type0.raw`
- `hdf_work/loader_full.asm` — полный аннотированный дизассемблинг Y4.11

### kernel/ — `stblinux-2.6.18-7.1/` дерево ядра (наши патчи — в build/*.sh)

### build/ — сборочные скрипты v2..v14
- `build_firmware_v14.sh` — актуальный (само-переносящийся стаб + строб)
- `flash_kit/` — экспериментальные HDF (t1-t9, d2a-d4, g1-g2, v10-v14)
  + README_FLASH_KIT.md с деревом решений
- `hdf_packer.py` — наш пакер/парсер HDF, `stub_v14.S` — PIC-стаб

### humax-gpl/
- `config_5150c/` — родной конфиг ядра+busybox для CXHD-5150C
- `sources/` — crosstools (тулчейн!), busybox, zlib, freetype и пр.
- `irhd_gpl/`, `HD-9000i_OpenSources/` — исходники родственных моделей

### tools/
- `humidify-ubuntu-1.0.4` — рабочий HDF-инструмент (запускать в docker)
- `opk/` — пакеты .opk: humidify_1.0.2, bsed, squashfs-tools, avinfo
- `lima/` — docker/colima окружение

### portal/ — эксперименты с ТВ-порталом ОнЛайм (DNS, panel, certs)

### uart/ — скрипты работы с UART/JTAG (uart_live.py, esp8266 JTAG, listen_stb)

### hdf_work/ — рабочие распаковки, ядра v7-v14, loader_full.asm, old_extracts/

## Ключевые факты (коротко)
- HDF: 20B заголовок + блоки; type 0x80=подпись, 1=код, 3=данные, 4=смена SysID
- Лоадер на буте НЕ проверяет крипту; образ копируется на 0x800B0000 и прыгается
- MICOM-watchdog ресетит через 13-15 с, если ядро его не кормит (I2C 0xE4)
- Скрытое меню приложения: Меню→Настройки→Система→Инфо о системе→
  ЖСКЗ ЖСЗ ЖС (Hidden Settings: Fusing Info, Operator Setting и др.)
- JTAG включён (FUSING INFO) — план А при тупике: ESP8266 + OpenOCD
