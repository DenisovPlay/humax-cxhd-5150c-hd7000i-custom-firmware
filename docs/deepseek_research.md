# DeepSeek research — дампы, загрузчики, что упустили

Дата: 2026-10-26. Режим: только статический анализ файлов в репозитории; на железе ничего не запускалось.
Цель: найти в существующих дампах/загрузчиках то, что можно использовать для текущего плана —
JTAG → свой код на CPU → загрузка Linux с USB, без записи в NAND.

## TL;DR

1. **Главная находка: HD FOX T2 CFE — это полноценный загрузчик, который можно попробовать
   поднять через JTAG из RAM.** Он линкован на `0x87000000`, вход `0x87000840`, умеет UART-консоль
   `CFE>`, USB mass storage + FAT, ELF/raw/srec, TFTP, gzip. Если он заведётся на CXHD-5150C,
   это может дать консоль и загрузку нашего `vmlinux_v20.elf` с флешки **без записи в NAND**.
2. **Y4.11-лоадер — это CFI/NOR-сборка** (block lock/protected/erase, ATAPI HDD, DVB-C TDA10021),
   без NAND-строк. Наша коробка — NAND. Поэтому E-FE на 96% мог быть не только бэд-блоком,
   а несовместимостью драйвера флеша; **восстанавливать NAND этим лоадером не стоит**.
3. **Y5.06-лоадера в репозитории нет.** В стоковых HDF (OnLime/7000i/5100C) только type 1 + 0x80;
   type-0 (loader) есть только в FPXCCX10016 (Y4.11, MIPS BE, CFI), HD FOX T2 (CFE, MIPS LE)
   и LNR (ARM/Conexant, не наш SoC). Значит blob/ключ Y5.06 из HDF не достать — нужен полный
   дамп NAND/лоадера.
4. **Практический артефакт:** собран `hdf_work/cfe_hdfoxt2.elf` — CFE, обёрнутый в ELF32 LSB MIPS
   с entry `0x87000840` и PT_LOAD `0x87000000`, чтобы грузить OpenOCD-командой `load_image`.
   Это новый файл, существующие файлы не перезаписывались.

Ниже — доказательства, адреса, риски и пошаговый план проверки.

---

## 1. HD FOX T2 CFE: что это и почему это важно

Файл: [loaders/cfe_hdfoxt2.bin](../loaders/cfe_hdfoxt2.bin) (890 844 байта, `0xD97DC`).
Это decompressed CFE из type-0 блока [firmwares/foxsat/hd_fox_t2_upgrade.hdf](../firmwares/foxsat/hd_fox_t2_upgrade.hdf)
(в HDF он лежит сжатым; `humidify -x` даёт этот файл). CFE — MIPS32 **little-endian**.

### 1.1. Адрес загрузки и вход

Долго искал базу: код использует `lui` + `addiu` с абсолютными адресами. Например, строка
`"CFE_VERSION"` лежит по файловому смещению `0xAC080`; код грузит её как:

```asm
lui  $a0, 0x870b
addiu $a0, $a0, -0x3f80   ; = 0x870AC080
```

Отсюда база **`0x87000000`**, а не `0x80000000`/`0x1C000000`, как можно было предположить.
Проверено по нескольким строкам (`CFE_BOARDNAME`, `Obtain help for CFE commands`, `BOOT_CONSOLE`).
Первое слово файла — `0x1000020F` (LE) = `b 0x87000840`; это вектор сброса.

| Параметр | Значение |
|---|---|
| Load/link base | `0x87000000` |
| Entry | `0x87000840` |
| Конец образа | `0x870D97DC` (файл), BSS с `0x870D97E0` |
| BSS end | `0x87313040` |
| Стек, который ставит main | `0x873153F8` (heap `0x87315400`) |
| GP | `0x870E1790` |
| CFE version | `1.1.3` (строка `0xADB20`) |
| Board | `HD-FOX T2` (строка `0xAE6E8`) |
| SoC string | `BCM97405B1` (строка `0xAC068`) |

### 1.2. Путь входа (важно для JTAG)

`0x87000840`:

1. Пишет CP0 Status/Cause (`0x20500001`), трогает `0xB030B030`, `0xB0000104`.
2. `bal 0x87000F60` — ранний вывод/идентификация; `bal 0x87000A7C` — PIC-хелпер.
3. Смотрит бит `0x08000000` у `$ra`:
   - **если загружены в kseg0 (`0x87000000`) — бит 0, self-copy пропускается;**
   - если в kseg1 (`0x9FC00000`) — копирует себя из `0x9FC00000` в `0x87000000`
     и сравнивает `memcmp`; при несовпадении печатает `COPY FAILED!` и висит.
4. В kseg0-ветке: `0x870009A8` → очистка BSS (`0x870D97E0..0x87313040`),
   flush cache (`0x87001ABC`), затем `0x870009C4`: CP0, `gp=0x870E1790`,
   `sp=0x87FFFFD0`, прыжок на **`0x87002594`** (main).
5. main выставляет стек `0x873153F8` и вызывает `0x870031AC`, далее инициализация
   и консольный цикл.

**Вывод:** грузить CFE надо ровно на `0x87000000` и стартовать с `0x87000840`.
Если попытаться стартовать с `0x87000000`, сработает вектор и тоже уйдёт на `0x87000840`,
но лучше явно.

### 1.3. Консоль и UART

- CFE инициализирует 16550-совместимый UART на **`0xB0400B00`** (второй канал — `0xB0400B40`).
- Делитель `0x2C` (44) при типичной UART-частоте BCM7405 даёт **115200 8N1**; в строках также
  есть `console=ttyS0,115200`.
- Консольный цикл найден по xref на строку `"CFE> "` (`0x870AC0E4`): функция **`0x870034A8`**.
  Она берёт `PROMPT` (строка `0x870AC0DC`), подставляет `"CFE> "` и крутит ввод/вывод команд.
- Ранние вызовы `0x87000BE0` выглядят как хелперы (возвращают адрес `0xB0400B14`, но не пишут
  байт). Поэтому **баннер до инициализации драйвера может не появиться**; ждать `CFE>`
  после полной инициализации. Это единственное место, где статический анализ не даёт
  100% гарантии — проверять на железе.

### 1.4. Что CFE умеет (по строкам и таблицам)

Подтверждено строками:

- Команды/подсистемы: `help`, `ifconfig`, `ping`, `usb init`, `show usb`.
- USB: OHCI/USBD, mass storage, `usbdisk0`, FAT16, USB-serial.
- Сеть: BCM7038 internal Ethernet, TFTP (`tftp`, `octet`).
- Форматы загрузки: `raw`, `elf`, `srec`; gzip-декомпрессор; проверки ELF.
- Flash: `NAND`, `NOR`, `New CFI flash`, `hmx_flash`, `HUMAX CFI flash`; флеш-разметка
  `cfe/reserve/splash/nvram/eep_back/hdcp/macadr/ci+/dtcp/serial/pravate`.
- Обновление: HDF-имена `hd_fox_t2_*.hdf`, `Programming MICOM...`, `Programming EEPROM...`,
  `Download Progress`, `Press 'STANDBY' button to restart...`.
- Watchdog/reset: функция `0x87002888` пишет `0xB04007C0` и `0xB04007C8 = 0xC0337F98`,
  затем ждёт бит; это скорее reset/watchdog-последовательность, чем «кормление».

**Формат-таблица** (в `.data` около `0x870B51E0`/`0x870B5268`):

| Формат | Обработчик |
|---|---|
| `tftp` | сетевой загрузчик |
| `raw` | `0x87022A08` (ветка raw) / `0x87023D28` |
| `elf` | `0x87023AD8` |
| `srec` | `0x87024530` |

ELF-загрузчик `0x87023AD8` вызывает парсер `0x87023790`. Парсер проверяет:

- ELF magic `0x7F454C46`, class 1 (32-bit), data 1 (LSB);
- `e_machine == 8` (MIPS), `e_phentsize == 0x20`, `e_phnum != 0`;
- читает program headers, грузит PT_LOAD, возвращает `e_entry` через указатель.

**Это совместимо с нашим `vmlinux_v20.elf`** (ELF32 LSB MIPS, entry `0x802AC000`,
PT_LOAD `0x800B0000` и `0x80290000`). CFE должен уметь его загрузить — вопрос в том,
какие регистры/argv он выставит перед прыжком и переживёт ли board-specific init.

Raw-загрузчик `0x87023D28` по умолчанию грузит **`0x80010000`, 4 МБ** (если не задан
`BOOT_FLAGS`); для v20 это не подходит — используем ELF.

### 1.5. ELF-обёртка для OpenOCD

Создан новый файл: [hdf_work/cfe_hdfoxt2.elf](../hdf_work/cfe_hdfoxt2.elf) (894 940 байт):

- ELF32 LSB MIPS, `e_machine=8`, entry `0x87000840`;
- один PT_LOAD: offset `0x1000`, vaddr/paddr `0x87000000`, filesz `0xD97DC`;
- код побайтово совпадает с `loaders/cfe_hdfoxt2.bin`.

Проверка: `file` → `ELF 32-bit LSB executable, MIPS, MIPS32`; `llvm-objdump -h` видит
`PT_LOAD#0 000d97dc 87000000 TEXT`.

---

## 2. Как попробовать CFE через JTAG

Ниже — предлагаемый эксперимент, **не выполненный** (Wemos ещё не забран). Все операции —
только RAM, без записи в NAND.

```tcl
# OpenOCD, после init/halt
halt

# 1) на всякий случай выключить SoC watchdog (регистры из Y4.11/CFE)
mww 0xB04007FC 0
mww 0xB04007E8 0xFFFFFFFF
mww 0xB0404070 0
mww 0xB0404074 0

# 2) загрузить CFE
load_image hdf_work/cfe_hdfoxt2.elf

# 3) если OpenOCD не принял ELF без section headers:
# load_image loaders/cfe_hdfoxt2.bin 0x87000000 bin

# 4) старт
resume 0x87000840
```

На UART `115200 8N1` ожидать:

- идентификацию `BCM97405B1`, версию `1.1.3`, возможно `HD-FOX T2`;
- инициализацию flash/USB/сети (может ругаться на NAND/PHY — это нормально);
- приглашение `CFE>`.

Если появился `CFE>`:

```
help
usb init
show usb
```

Дальше — по тому, что покажет `help`. В бинаре подтверждены форматы `elf`, `raw`, `srec`,
устройства `usbdisk0` и `tftp`, поэтому вероятный сценарий: FAT16-флешка с `vmlinux_v20.elf`,
загрузка ELF и прыжок на `0x802AC000`. Точный синтаксис (`boot`, `load -elf`, `go` и т.п.)
надо смотреть в `help`; в строках его нет.

### 2.1. Если CFE не завёлся

Собрать факты, не паниковать:

- `halt`, `reg pc`, `reg sp`, `reg gp`; CP0 EPC/Cause/Status через OpenOCD (`mfc0`/`reg`).
- Если PC ушёл в `0xBFC00000`/`0xBFE00000` — сработал reset/bootrom; смотреть, что было до.
- Если висит в `0x87000A20` (`lui ra,0xbfc0; jr ra`) — это прыжок в bootrom, кто-то вызвал
  сброс; искать по стеку.
- Если висит в `0x87000A8C` — бесконечный цикл (ошибка/исключение).
- Если UART молчит, но PC в main — возможно, UART-база/частота не та; проверить
  `0xB0400B00`/`0xB0400B0C` и делитель.
- Если срабатывает watchdog — проверить `0xB04007C0`/`0xB04007E8`; возможно, CFE
  переинициализирует их позже.
- Если падает board init (flash/NAND/PHY) — попробовать патчить/пропускать соответствующие
  вызовы, но **не трогать NAND-запись**. Это уже отдельная итерация.

### 2.2. Ограничения и риски

- CFE — от **HD FOX T2** (`BCM97405B1`), а не от CXHD-5150C. Совпадает SoC-семейство,
  но плата/флеш/PHY/разводка могут отличаться.
- **Никаких команд `flash`, `program`, `download`, `ota`, `eeprom`, `micom`** — CFE умеет
  программировать NAND/MICOM/EEPROM под HD FOX T2; на нашей коробке это может убить
  остатки загрузчика/ключей. Только RAM-загрузка и `help`/USB/TFTP.
- CFE может автоматически пытаться boot с flash; если он повиснет до консоли — это
  ожидаемый риск, а не приговор. Тогда смотреть, можно ли пропатчить `BOOT_DEVICE`/`STARTUP`
  или обойти board init.
- CFE использует BSS `0x870D97E0..0x87313040`, стек `0x873153F8`. Наш v20 лежит
  `0x800B0000..0x8030A481` — пересечения нет. Но CFE-ELF-загрузчик тоже выделяет память
  из своего heap; при загрузке v20 это надо учитывать (2.7 МБ, должно поместиться).

---

## 3. Y4.11-лоадер: CFI/NOR, а не NAND — важное уточнение

Файл: [firmwares/ia_archive/extracted/FPXCCX10016_Y411/1.hdfbin-0-000000.raw](../firmwares/ia_archive/extracted/FPXCCX10016_Y411/1.hdfbin-0-000000.raw)
(393 192 байта, MIPS **big-endian**, база `0x83350000`, Nucleus RTOS; дизасм —
[hdf_work/loader_full.asm](../hdf_work/loader_full.asm)).

### 3.1. Признаки CFI/NOR

В строках лоадера есть CFI-специфичные вещи:

- `FlashCommonBlockLock failed!!`, `FlashCommonBlockUnlock failed!!`
- `Block (%d) (0x%x) Protected` / `Unprotected`
- `Clear Block Lock Bit Error`, `Voltage Range Error`, `Command Sequence Error`
- `Erase (%d) (0x%x)`, `Error in flash Erase Block`, `Error in Block Write`

Строк `NAND`, `bad block`, `MT29`, `K9` и т.п. **нет**. Зато есть `ATAPI`/HDD и DVB-C
демодулятор `TDA10021`, то есть это сборка для другого (вероятно, PVR/NOR) аппарата.

### 3.2. Почему это важно для E-FE

README объясняет E-FE «бэд-блоком NAND». Но если Y4.11 — CFI/NOR-сборка, то на NAND
она может валиться не на физическом бэд-блоке, а на **несовпадении драйвера/геометрии
флеша**: другие команды erase/write, другие block lock/protected, другой размер блока.
Тогда:

- E-FE — не обязательно «плохой блок»; это может быть ошибка драйвера на NAND;
- **не стоит** пытаться восстановить NAND этим же Y4.11-лоадером;
- для NAND нужен **Y5.06-лоадер** (или свой NAND-драйвер/программатор).

Это гипотеза, но она хорошо объясняет, почему 144 блока записались, а дальше пошёл E-FE.
Проверять по коду флеш-драйвера Y4.11 (CFI command set) и по фактическому NAND-контроллеру.

### 3.3. Что ещё есть в Y4.11 (строки, которых не было в отчётах)

- Стадии/гейты: `VInit`, `CCheck`, `E-ID`, `E-HC`, `E-HF`, `E-DC`, `E-AC`, `E-UT`, `E-AD`,
  `E-FE`, `E-FN`, `E-IC`, `E-AO`, `E-FT`, `E-OS`, `E-IS`, `E-ED`, `E-EE`, `E-NA`, `E-HW`.
- Обновление: `[INVOKED] DownloadToFlash`, `ucStartBlock/EndBlock`, `System ID Fail
  (c.%x:s.%x:e.%x)`, `*** Signature Check`, `SIGN_DecryptFinal`,
  `ERR_INVALID_SIGN`, `ERR_DECRYPT`, `ERR_HEADER_CRC`, `Application Block Number`,
  `wrong Header Block-(%d)`, `Current Block Type...`, `block : %d[%d]`.
- EEPROM/MICOM: `DDI_EEPROM_ReadTestModeFlag`, `DDI_EEPROM_ReadUpgradeFlag`,
  `Cannot write test mode flag!!!!!!!`, `DDI_MICOM_GetWakeupSrc`,
  `WakeupSrc[0x%x]`, `PrevPowerMode is Standby`, `DDI_EEPROM_TIMER_SRC_FOR_OTA,REC`.
- Нет строк вида «press key for recovery»/«UART console»; серийный download — это
  отдельная ветка `0x83392B1C`, ждущая `0x06` на UART (уже описана в
  [docs/claude-loader/analys.md](claude-loader/analys.md)). Частично записанный лоадер
  до неё, скорее всего, не доходит.

**Вывод:** Y4.11 — не «универсальный восстановитель»; это полноценная прошивка
с CFI/NOR-флешем и HDD. Для NAND-коробки он опасен.

---

## 4. Чего в репозитории нет (важный отрицательный результат)

Я разобрал block-таблицы всех HDF в `firmwares/` и `from_humax_webarchive/`:

| HDF | type-0 (loader) | Что это |
|---|---|---|
| `firmwares/genuine/onlime_early_cxhd_5150c.hdf` | **нет** | 706 блоков: type 1 + 0x80 (app/rootfs) |
| `firmwares/genuine/hd_7000i_upgrade.hdf` | **нет** | 706: type 1 + 0x80 |
| `firmwares/genuine/PRIMACOM_5100C/cxhd_5100c_upgrade.hdf` | **нет** | 699: type 1 + 0x80 |
| `firmwares/foxsat/hd_fox_t2_upgrade.hdf` | **28 блоков**, 890 844 Б | HD FOX T2 CFE (MIPS LE, `0x87000000`) |
| `firmwares/ia_archive/.../FPXCCX10016_Y411.hdf` | **13 блоков**, 393 192 Б | Y4.11 (MIPS BE, CFI/NOR) |
| `from_humax_webarchive/.../STB_LNR-TPVR...hdf` | **7 блоков**, 200 532 Б | ARM/Conexant, не наш SoC |

То есть **Y5.06-лоадера (NAND, CCX) в репозитории нет**. Stock-обновления содержат
только app/rootfs; загрузчик в них не кладут. Значит:

- blob/ключ Y5.06 из этих HDF не достать;
- нужен **полный дамп NAND** (программатор/JTAG + NAND-драйвер) или донорский Y5.06;
- старый план «взять blob из Y5.06 CFE» остаётся без источника.

### 4.1. LNR-лоадер — ARM, не наш

`STB_LNR-TPVR_MP_ALL_UPGRADE_20101.hdf` (type 0, 200 532 Б) после `humidify -x`:

- начало `13 00 00 EA` — ARM-ветка, строка `CNXT`, `Copyright Conexant Systems`;
- внутри HDF/OTA/erase/download для **ARM/Conexant**, не BCM7405.

К нашему SoC отношения не имеет. Это хороший пример: «type-0 loader» ≠ «MIPS Y-loader».

---

## 5. HDF/humidify: практические заметки

- `tools/humidify-ubuntu-1.0.4` — статический x86-64 Linux ELF; под macOS напрямую не идёт.
  Рабочий способ: Docker `ubuntu:14.04` с `--platform linux/amd64` (проверено, извлекает
  CFE/LNR). Docker daemon на этой машине пришлось поднимать через `colima` (потом остановлен).
- `humidify -x` извлёк LNR type-0 и CFE; для CFE результат совпал с `loaders/cfe_hdfoxt2.bin`.
- **Осторожно с размером:** на LNR HDF humidify создал `3.hdfbin-3-7e0000.raw` с логическим
  размером **4.29 ГБ** (sparse, на диске ~2 МБ) из-за скачка адреса блока. Если запускать
  `-x` на незнакомых HDF — проверять `du -h`/`df`; временные файлы лучше держать вне репо.
  В этой сессии временные extraction-файлы удалены.
- `humidify -l`/`-t` полезны для проверки CRC/структуры; `-x` — для type-0 лоадеров.

---

## 6. Совместимость v20 с CFE ELF-загрузчиком

`hdf_work/vmlinux_v20.elf`:

- ELF32 LSB MIPS, `e_machine=8`, `e_phentsize=0x20`;
- entry `0x802AC000` (`kernel_entry`), сегменты `0x800B0000` (filesz `0x1DE334`) и
  `0x80290000` (filesz `0x7A481`);
- `kernel_entry` в конце образа, начало — нули; CFE грузит по `e_entry`, так что трамплин
  не нужен.

CFE-парсер `0x87023790` как раз проверяет `class=1`, `data=1`, `e_machine=8`,
`e_phentsize=0x20`, читает PT_LOAD и возвращает entry. Это хорошее совпадение.

**Неизвестно:** какие `a0/a1/a2` выставит CFE перед прыжком и не будут ли они мусором
для `kernel_entry`. Если будут — fallback:

1. Сделать крошечный trampoline-ELF: entry в первой странице, обнулить `a0/a1/a2`,
   прыгнуть на `0x802AC000`; CFE грузит его как обычный ELF.
2. Или использовать raw-загрузчик с `BOOT_FLAGS`, если он позволяет задать load/entry
   (по умолчанию raw грузит `0x80010000`/4 МБ — не наш адрес).
3. Или вообще не грузить v20 через CFE: CFE — только консоль/полигон, а v20 залить
   JTAG-ом и `resume` (минуя CFE).

---

## 7. План проверки на железе (короткий)

1. Забрать Wemos, поднять OpenOCD, `halt`.
2. Выключить watchdog (регистры выше), загрузить `hdf_work/cfe_hdfoxt2.elf`, `resume 0x87000840`.
3. UART 115200: ждать `BCM97405B1`/`1.1.3`/`CFE>`.
4. Если консоль есть:
   - `help` — зафиксировать список команд и синтаксис;
   - `usb init`, `show usb` — проверить, видит ли флешку;
   - флешка **FAT16** с `vmlinux_v20.elf`; загрузить ELF, смотреть, куда прыгает и что с
     регистрами/ядром;
   - **не выполнять** `flash`/`program`/`download`/`ota`/`eeprom`/`micom`.
5. Если CFE не даёт консоль — записать PC/CP0, проверить watchdog, попробовать
   патчить/пропускать board init; не писать в NAND.
6. Если USB/TFTP не работают — использовать CFE только как UART-консоль/полигон,
   v20 грузить JTAG-ом; параллельно делать свой минимальный загрузчик по образцу
   CFE (UART/USB/FAT/ELF).
7. Для NAND-восстановления сначала нужен **полный дамп** (JTAG/программатор) и/или
   Y5.06/NAND-лоадер; Y4.11 для этого не использовать.

---

## 8. Что создано/изменено в этой сессии

- Новый файл: [hdf_work/cfe_hdfoxt2.elf](../hdf_work/cfe_hdfoxt2.elf) — CFE в ELF-обёртке
  для `load_image`. Исходники не менялись.
- Новый файл: этот отчёт.
- Временные extraction-файлы (LNR) удалены; Colima/Docker остановлены.
- Существующие `README.md`, `.gitignore`, прошивки, дампы не перезаписывались.

---

## 9. Открытые вопросы

- Переживёт ли CFE board-specific init на CXHD-5150C (NAND/PHY/strap)?
- Есть ли в CFE NAND-драйвер для нашего чипа, или он упадёт на flash init?
- Какие `a0/a1/a2` CFE выставляет Linux-ядру?
- Поддерживает ли CFE FAT32 или только FAT16? (в строках — FAT16)
- Есть ли в CFE команда `boot`/`load` с ELF или только автоматический boot по env?
- Y4.11 CFI/NOR-гипотеза: подтвердить по флеш-драйверу и NAND-контроллеру.
- Где взять Y5.06/NAND-лоадер: полный дамп, донор, или свой NAND-драйвер.

---

## Приложение A. Быстрые адреса CFE

| Что | Адрес |
|---|---|
| Reset vector | `0x87000000` → `0x87000840` |
| Entry | `0x87000840` |
| BSS clear | `0x87000A94` |
| Set gp/sp, jump main | `0x870009C4` |
| Main | `0x87002594` |
| Init | `0x870031AC` |
| Console loop (`CFE>`) | `0x870034A8` |
| UART driver init | `0x87004D34` (база `0xB0400B00`) |
| ELF loader | `0x87023AD8` |
| ELF parser | `0x87023790` |
| Raw loader | `0x87023D28` |
| Watchdog/reset | `0x87002888` (`0xB04007C0`/`0xC8`) |

## Приложение B. Быстрые строки CFE

| Строка | Адрес |
|---|---|
| `CFE_VERSION` | `0x870AC080` |
| `CFE_BOARDNAME` | `0x870AC08C` |
| `CFE_MEMORYSIZE` | `0x870AC0A0` |
| `CFE> ` | `0x870AC0E4` |
| `BOOT_CONSOLE` | `0x870AC518` |
| `BOOT_DEVICE` / `BOOT_FILE` / `BOOT_FLAGS` | `0x870ADA44` / `0x870ADA50` / `0x870ADA5C` |
| `1.1.3` | `0x870ADB20` |
| `HD-FOX T2` | `0x870AE6E8` |
| `console=ttyS0,115200` | `0x870AE770` |
| `usb init` / `show usb` | `0x870ACFF0` / `0x870AD084` |
| `elf` / `raw` / `srec` | `0x870ADB28` / `0x870ADB30` / `0x870ADB38` |

## Приложение C. Полезные оговорки

- Все адреса — **виртуальные в kseg0**; физически это `0x07000000 + offset` при загрузке
  в DRAM. OpenOCD с `load_image` по ELF работает с vaddr, этого достаточно.
- CFE может использовать MMU/TLB; после `halt`/`resume` не надо вручную менять CP0,
  если только не диагностируем.
- Если CFE начнёт писать в NAND — немедленно `halt`; лучше заранее не давать команды
  `flash`/`program`/`download`/`ota`.
