# Анализ уязвимостей загрузчика Y4.11 — Claude session findings

Файл-буфер: все находки из RE-сессии, чтобы не потерять при сжатии контекста.
Исходник: `hdf_work/loader_full.asm` (74 575 строк, 999 функций, 393 192 байта).
База загрузки: `0x83350000` (BE MIPS, LE архитектура — поле всё равно BE).

---

## 1. origlen — нет проверки границ в копировщике (boot)

**Функция**: `0x83392260` (file offset `0x42260`)  
**Рейтинг**: ПОЛЕЗНО ПОСЛЕ ПОЛУЧЕНИЯ БЛОБА

Копировщик читает блочную таблицу из флеша, итерирует type-1 блоки:

```asm
0x83392448: addu $a0, $s6, $s4    ; dst = dst_base(0x800B0000) + accumulated_origlen
0x8339244c: lhu  $a2, 6($v1)      ; origlen из заголовка блока (max 0xFFFF)
0x83392450: jal  0x8339961c       ; memcpy(dst, payload, origlen)
0x83392454: addu $s4, $s4, $a2    ; accumulated_origlen += origlen — НЕТ ПРОВЕРКИ ГРАНИЦ
```

Точная строка переполнения (подтверждено):
```asm
0x83392488: ori  $v1, $zero, 0x80
0x8339248c: beq  $s2, $v1, 0x833924b4   ; type==0x80 → пропустить (подпись)
; иначе — все остальные типы:
0x833924ac: lhu  $v1, 6($v1)            ; origlen из таблицы (16-bit, max 0xFFFF)
0x833924b0: addu $s4, $s4, $v1          ; s4 += origlen — НЕТ ПРОВЕРКИ
```

Цикл: `s0(block_index) < s1(block_count)` → loop back to `0x833922c4`.
Блоков в таблице может быть до 0xFFFF (считывается BE 4-байтом с начала таблицы).

- $s4 накапливает сумму origlen без верхней границы
- Max origlen на блок = 0xFFFF (65 535 байт)
- Чтобы добраться до адреса загрузчика (`0x83350000` = физ `0x3350000`): offset от `0x800B0000` = 40 MB = ~640 блоков по 0xFFFF (или меньше блоков с origlen 0xFFFF если их 640)
- **Примитив**: write-anywhere-in-DRAM (записываем произвольный payload на любой адрес в ОЗУ, включая адрес загрузчика `0x83350000`)
- **Блокер**: для записи в флеш нужна валидная подпись (см. п.3); без блоба или ключа не работает
- **Когда полезно**: если получим дамп CFE/блоб → собственный подписанный HDF → craft origlen → перезаписать загрузчик/ОЗУ

---

## 2. keyidx — ложная тревога, не уязвимость

**Функция**: `0x8338d494` (file offset `0x3d494`)  
**Рейтинг**: НЕ УЯЗВИМО

```asm
0x8338d49c: andi $a2, $a2, 0xff    ; маска до 8 бит — защитная, лишняя
0x8338d4a8: sll  $v1, $v1, 4       ; keyidx * 16
0x8338d4b0-b4: base = 0x833df6a8  ; таблица ключей
0x8338d4b4: addu $a2, $t9, $v1    ; key_ptr = base + keyidx*16
```

keyidx берётся из `flags[10:8]` (3 бита, значения 0-7). Таблица ключей = ровно 8 записей × 16 байт = 128 байт. `andi 0xff` не помогает атакующему — вызывающий код уже ограничивает до 3 бит. OOB недостижим.

---

## 3. Обход подписи при отсутствии type-0x80 блока — ЗАБЛОКИРОВАН

**Функция**: `update_main` `0x833918ac` (file offset `0x418ac`)  
**Рейтинг**: НЕ РАБОТАЕТ — проверка есть

Перед записью type-0/1 блоков в флеш (dispatch `0x83391f70`):

```asm
0x83391f72: ori  $v1, $zero, 1
0x83391f74: lw   $at, 0x10($sp)       ; флаг sign_done
0x83391f78: beq  $at, $v1, 0x83391f9c ; если подписан — продолжить
; иначе:
0x83391f80-88: print "err.7"
0x83391f90: ori $v1, 0xf; j error_exit ; abort
```

`sp[0x10]` выставляется в 1 только в SIGN_DecryptFinal success path. Без type-0x80 блока `sp[0x10] = 0` → "err.7" + аборт. **Записать исполняемый код без валидной подписи невозможно.**

---

## 4. type-4 блок — уже работает, но ограничен

Меняет SysID без проверки подписи. Подтверждено в экспериментах v10 (наш Y5.06 принял). Не пишет исполняемый код, только SysID в EEPROM. Используем как "пробу пера" и для wildcard-сценария (см. п.7).

---

## 5. Serial Upload — READ-ONLY, НО ДАЁТ ДАМ CFE

**Функции**: `0x83393408` → `0x83393808`  
**Рейтинг**: КЛЮЧЕВОЙ ПУТЬ К БЛОБУ

"Upload" в OSD = передача содержимого флеша на ПК по UART. Протокол (STB-сторона):

```
PC → STB:  0x02 0x42 [chunk_len_hi][chunk_len_lo] [addr_b2][addr_b1][addr_b0] 0x03
STB → PC:  0x02 [chunk_len байт данных...] 0x03
```

- `0x83392a30` = ждёт 1 байт по UART, отвечает 0x06 (ACK)  
- `0x833929a8` = шлёт байт и ждёт ACK
- `0x833932f8(type, chunk_addr, chunk_len, buf)` = читает из флеша в буфер `0x833c78cc`
- Буфер затем побайтно уходит на PC через `0x833929a8`

Это и есть то, что реализует `WDN4OAK.exe` / `FV3Dll.dll::DownloadData`. Наш `tools/humax_serial_dump.py` делает ровно это с PC-стороны. **Дамп CFE-партиции = блоб Y5.06 = разблокировка boot.**

---

## 6. Точный адрес memcpy в копировщике

**Функция**: `0x83392260`, вызов memcpy: строка дизассемблера ~64723

```asm
0x83392448: addu $a0, $s6, $s4    ; dst = 0x800B0000 + accumulated_origlen
0x8339244c: move $a1, $s5          ; src = payload pointer
0x83392468: lhu  $a2, 6($v1)      ; len = origlen (16-bit из заголовка блока)
0x8339246c: jal  0x8339961c       ; memcpy(dst, src, origlen)
```

После успешной копии: `addu $s4, $s4, origlen` — сдвигаем курсор. dst при переполнении 32-bit wraparound: если s4 достигает 0xFFFFFFFF + origlen → dst оборачивается на 0x7FFFFFFF... или 0x00000000. На MIPS с физ. адресом выше 0x80000000 → kseg0 mapped.

---

## 6b. Стек update_main — карта для ROP (будущее)

**Функция**: `0x833918ac`, фрейм `-0x138` (312 байт)

Пролог через цепочку микрофункций `0x8339b42c` (push $fp/$s7/..$s0/$ra по одному, delay slot `ori $sp, $t4, 0`):

```
sp+0x110 : $v0 = return address ($ra, сохранён в v0 в первой инструкции)  ← цель ROP
sp+0x114 : $s0 (original)
sp+0x118 : $s1
sp+0x11c : $s2
sp+0x120 : $s3
sp+0x124 : $s4
sp+0x128 : $s5
sp+0x12c : $s6
sp+0x130 : $s7
sp+0x134 : $fp
--- локальные переменные ---
sp+0x00  : [pad / tmp]
sp+0x08  : result_code (временный)
sp+0x0c  : current data pointer
sp+0x10  : sign_done flag (0 → не проверена; 1 → OK)
sp+0x1c  : SHA context ptr (передаётся в 0x8339381c)
sp+0x3c  : SHA-hash output #1 (32 байта, если s4==0)
sp+0x5c  : SHA-hash output #2 (32 байта, если s4==1)
```

SHA: `0x8338d2c8` (init), `0x8338d2f0` (update, a0=payload, a1=origlen, a2=0x8000), `0x8338d340` (final).  
Контекст SHA — в глобальном BSS, не на стеке → переполнения нет.  
Копии хеша (sp+0x3c и sp+0x5c, по 32 байта) не достигают сохранённых регистров (разрыв до sp+0x110 = 49 байт).  
**ROP достижим только если найдём write-to-stack в update_main до sp+0x110 — пока не найдено.**

---

## 7. EEPROM[0xE2] testflag — ИЗУЧЕНО (2026-10-25, сессия 3)

**Wildcard SysID = FFFFFFFF/FFFFFFFF (не 0000.0000).**

Функция `0x833917a0` (type-4 SysID handler):
1. Читает `[0x833de7cc]` = SysID range LOW из блок-хедера (парсится `0x8338ffc0`)
2. Читает `[0x833de7d0]` = SysID range HIGH из блок-хедера
3. **Если ОБА == 0xFFFFFFFF (wildcard):**
   - `ori $a0, $zero, 1; jal 0x8337fc7c` → **ЗАПИСЫВАЕТ** 1 в `EEPROM[0xe2]` (DDI_EEPROM_Write)
   - Если запись неудачна: `printf "Cannot write test mode flag!!!!!!!"` (это message об ОШИБКЕ ЗАПИСИ)
   - В любом случае: `jal 0x83397304` → **boot_jump**
4. Если не wildcard: SysID range check (current_SysID in [low, high]?)

**Ключевые факты:**
- `0x8337fc7c` = WRITER обёртка: `DDI_EEPROM_Write(0xe2, &1, 1)` (не reader!)
- `0x8337fe74` = DDI_EEPROM_Write (строка с "[DDI_EEPROM_Write] Exceeded eeprom size" подтверждает)
- `EEPROM[0xe2]` при нормальной загрузке Y4.11 **НИКОГДА НЕ ЧИТАЕТСЯ** — нет DDI_EEPROM_Read с addr=0xe2
- Запись EEPROM[0xe2]=1 не влияет на следующие буты в Y4.11 (но может читаться юзерспейсом)

**Критическое свойство wildcard пути:**
`0x8338ffc0` = **хедер-парсер**, НЕ инсталлятор блока. boot_jump вызывается НА ТЕКУЩЕЙ УСТАНОВЛЕННОЙ ПАРТИЦИИ (до записи данных нового блока). При этом boot_jump вызывается **минуя проверку gp-0x7946** (CCheck gate) — это bypaass!

**Вывод:** Wildcard SysID type-4 = тест-режим/сервисный backdoor:
- Пишет EEPROM[0xe2]=1 (testflag для юзерспейса)
- Немедленно запускает то что уже установлено в флеше, обходя CCheck gate
- Если CCheck дал gp-0x7946!=0 (по какой-то причине) — **этот путь всё равно запускает ядро!**

**Как использовать:**
1. Прошить наше plaintext ядро (нормальный type-4 или type-1)
2. Отправить HDF с любым блоком где SysID range = `FF FF FF FF FF FF FF FF` (байты 8-15 хедера)
3. Loader парсит хедер → wildcard → EEPROM[0xe2]=1 → boot_jump на уже установленное ядро

---

## 8. 13-секундное окно — ЛУЧШИЙ ТЕКУЩИЙ ПУТЬ

Из `LOADER_FULL_AUDIT.md`:
- Цикл 13-15 с = MICOM watchdog (не blob-gate из загрузчика!)
- Загрузчик Y5.06 скорее всего делает то же что Y4.11 (идентичная кодовая база)
- В окне 13 с: ядро загружается (2-3 с), netconsole поднимается, UDP-дамп MTD0

Автодамп CFE через UDP:
```
# в initramfs init:
dd if=/dev/mtd0 bs=1450 | nc -u 255.255.255.255 6667  # broadcast CFE partition
```

CFE partition обычно 256-512 KB. При 100 Mbit Ethernet = 10 MB/s → дамп за < 0.1 с. Цикл повторяется — собираем фрагменты если нужно.

---

## 9. OSD Upload protocol — детальная карта

Полный handshake из дизассемблирования:

```
(PC → STB) 0x02 = STX
(PC → STB) 0x42 = 'B' = команда Read Flash
(PC → STB) HH LL = chunk_len (16-bit big-endian)
(PC → STB) A2 A1 A0 = flash_address (24-bit big-endian, т.е. до 16 MB)
(PC → STB) 0x03 = ETX

(STB → PC) 0x02
(STB → PC) [chunk_len байт из флеша начиная с flash_address]
(STB → PC) 0x03

По завершению всего: 0x02 0x43 0x03 (финальное подтверждение)
```

Эти константы жёстко зашиты: 0x02/0x42/0x03/0x43 (STX/B/ETX/C) в update_main dispatch.

---

## 11. НОВОЕ: blob-gate — где реально проверяется (2026-10-25, сессия 2)

### Ключевое открытие: gp-0x7e24 НИКОГДА не записывается

`boot_jump (0x83397304)`:
```asm
jal  0x83397270    ; boot_app — копировщик
jal  0x83396b24    ; blob_check → читает gp-0x7e24
move $v1, $v0
beqz $v1, kernel   ; v1==0 → 0x800B0000 (ядро)
                   ; v1!=0 → 0xbfe00000 (bootrom)
```

`blob_check (0x83396b24)` = ровно 3 инструкции:
```asm
lbu $v1, -0x7e24($gp)   ; читаем байт из BSS
move $v0, $v1
jr $ra
```

**gp = 0x833b7e08 → gp-0x7e24 = 0x833AFFE4 (в BSS)**

Поиск по всему бинарнику (393 192 байта): **ни одной записи в 0x833AFFE4** — ни gp-relative sb/sh/sw, ни прямой адресацией через lui+addiu. BSS инициализирован нулями → **флаг всегда 0 → boot_jump ВСЕГДА прыгает на ядро** (0x800B0000).

**Вывод: blob-gate через gp-0x7e24 В Y4.11 НЕ СУЩЕСТВУЕТ.**  
README говорит "нулевой blob → jump to bootrom" — это НЕТОЧНОСТЬ. Сам загрузчик Y4.11 не проверяет blob при загрузке. Copier также не проверяет (КРИПТО-ПРОВЕРОК НА БУТЕ НЕТ — подтверждено аудитом).

### Что тогда вызывает цикл 13-15с?

Цепочка доказательств:
- **stub_v15 отключает SoC watchdog** → цикл остался → SoC watchdog не причём
- **LOADER_FULL_AUDIT**: exception в ядре → exception handler лоадера → `BLOCKS FOREVER` (висит!), не цикл
- **MICOM**: "Linux не обязан кормить MICOM, nosettop живёт вечно"
- **Единственный оставшийся вариант**: MIPS exception в ядре → процессор прыгает на вектор 0xBFC00180 (в BOOTROM) → bootrom делает полный reset → цикл

Т.е.: наше ядро СТАРТУЕТ (прыжок есть), но крашится с MIPS-исключением **ДО того как инициализирует что-то полезное**. Каждый цикл = полный рестарт: bootrom (init DDR) → CFE → loader → ядро → crash → exception vector → reset → ~13с.

### Что вызывает крэш ядра?

Нет данных. Возможные причины:
1. BCM7405 не полностью инициализирован (CFE делала init который ядро не повторяет)
2. TLB/MMU настройки несовместимы с началом stblinux
3. Что-то ломается до setup_arch → до вывода на uart0

**Решение**: v13 с entry-strobe в ПЕРВЫХ инструкциях head.S (до setup_arch) + FB-полосы. Если полосы есть — ядро стартовало, бисекция места краша. Если нет — крашится ДО head.S (= прыжок на неправильный адрес или stub не работает).

### Где blob реально используется

Из V10_EXPERIMENTS.md строка 48-49:
```
Нулевой 256B-блоб → блоки без расшифровки (plaintext прошёл!)
Сток-блоб → расшифровка чужими ключами → мусор
```

**Blob = AES-ключ / индикатор шифрования, НЕ секьюрити-гейт.**  
Null blob в partition header = режим plaintext → копировщик копирует блоки raw → прыжок на ядро.  
Non-null blob = AES decrypt перед копированием → если ключ чужой → мусор в RAM → crash немедленно.

### Флаг gp-0x7946 перед вызовом boot_jump

Основной цикл (функция 0x83396584):
```
s0=0 → state machine loop:
  jal 0x8335d818(gp-0x7968, 0x7d0, 5, sp+4, 1)  ; NAND read
  sp+4 & 1 → s0 |= 1
  sp+4 & 4 → s0 |= 4
  if s0==5: break
else: error(0x12)

jal 0x83396f34(0x833df428)  ; partition load / download check
lbu $v1, -0x7946($gp)       ; gp-0x7946 = результат предыдущего
beqz $v1, → jal boot_jump   ; если 0 → нормальный boot
else → error(2) + error(5)  ; иначе ошибка
```

Флаг gp-0x7946: **ещё не нашли где устанавливается**. Вероятно в 0x83396f34 или 0x833925f8 при ошибке чтения partition.

---

## 13. ДОПОЛНИТЕЛЬНЫЙ АНАЛИЗ (2026-10-25, сессия 2 продолжение)

### Copier 0x83392260 — полный анализ

Входные аргументы: `a0 = flash_table_ptr`, `a1 = 0x800B0000`, `a2 = 0 (load_game_flag)`.

Считывает BE 4 байта из flash_table_ptr[0] = счётчик блоков s1.
Для каждого блока:
- Парсит 12-байтный header через `0x8339008c` → table entry в 0x833de7d8
- `s2 = table_entry[4] & 0xff` = тип блока
- Если bit15 заголовка SET и s2 != 1 → **error 3** (единственный error path!)
- Если bit15 NOT SET и s2 == 1 → **memcpy(0x800B0000+offset, src, size)**
- Если bit15 NOT SET и s2 != 1 → **пропускается** (не ошибка!)
- Если s2 == 0x80 → LZRW decompress

**Для наших plaintext блоков (s2=1, bit15=0): копируется без ошибки.**
Copier возвращает 0 → boot_app видит success → "Load Application".

### `0x83396f34` — полная трассировка (нормальная загрузка)

```
1. jal 0x833925f8(проверка 0xbf400000 magic)
   → на холодном старте нет magic → возвращает 1 (не download mode)

2. jal 0x83392b1c(sp+0xb, sp+0xc)
   → вызывает 0x833929a8(2) → читает UART, ждёт 0x06 ACK
   → нет serial → немедленно возвращает 1
   → 0x83392b1c возвращает 1 (error)

3. 0x83396f34 → jal 0x83396058(s0) = OTA-проверка
   → нет pending OTA → возвращает non-zero
   → 0x83396f34 ВОЗВРАЩАЕТСЯ НОРМАЛЬНО (без download, без OTA)

4. После возврата: lbu $v1, gp-0x7946; beqz → BOOT_JUMP
```

Вывод: при нормальной загрузке (нет serial, нет OTA) `0x83396f34` ничего не делает и возвращается.

### EEPROM[0xe2] / EEPROM[0x60] — где и когда

| Функция | Действие | Когда |
|---------|---------|-------|
| `0x8337fc7c` | **WRITE** 1 в EEPROM[0xe2] | wildcard SysID type-4 в update_main (OTA) |
| `0x8337fc40(val)` | WRITE `val` в EEPROM[0x60] | CCheck fail → пишет 2 |
| `0x833917a0` | wildcard: WRITE EEPROM[0xe2] + **jal boot_jump** | type-4 testflag handler; обходит gp-0x7946 |

`0x8337fe74` = DDI_EEPROM_Write (подтверждено строкой "[DDI_EEPROM_Write] Exceeded eeprom size").  
`0x8338002c` = DDI_EEPROM_Read (подтверждено строкой "[DDI_EEPROM_Read] Exceeded eeprom size").  
**Для нормальной загрузки: EEPROM[0xe2] не читается вообще (ни одного вызова DDI_EEPROM_Read с addr=0xe2).**
EEPROM[0x60] = 2 пишется только при CCheck failure (плохая CRC16 партиции).

### Indirect call 0x83352db8 = NAND I/O функция

Проверяет магию `0x45564E54` ("EVNT") в NAND struct[0xc].
Если ОК и тип ∈ {0,1,2,3} → вызывает `0x83354bfc(ptr, 0x7d0, type, output, flag)` = реальное NAND чтение.
Нет никаких crypto-проверок, нет blob-gate.

### Адрес 0x9fc40000 — одна ссылка во всём бинаре

Ровно одна `lui $t9, 0x9fc4` во всём Y4.11 (строка 69206).
Это BCM7405 NAND hardware buffer = KSEG1(0x1fc40000) = physical 0x1fc40000.
Либо NOR flash data area, либо NAND DMA buffer.
V10_EXPERIMENTS подтверждают: наши plaintext данные там появляются, CRC16 проходит.

### ПОЛНАЯ ТАБЛИЦА BOOT GATES

| Gate | Адрес | Что проверяет | Для нашего custom HDF |
|------|-------|--------------|----------------------|
| 0x833925f8 | 0xbf400000 magic | CRC-protected download flag | PASS: нет magic → normal boot |
| 0x833929a8 | UART ACK 0x06 | WDN4OAK serial handshake | PASS: нет serial → timeout |
| 0x83396058 | OTA pending check | Есть ли отложенный OTA | PASS: нет OTA |
| CCheck gp-0x7946 | 0x83396880 | CRC16 блоков партиции | PASS: correct CRC16 |
| blob_check gp-0x7e24 | 0x83396b24 | ВСЕГДА = 0 в Y4.11 | PASS: всегда kernel |
| copier 0x83392260 | block type check | s2==1 для plaintext | PASS: s2=1 → copy |

**ВСЕ GATE-Ы ПРОХОДЯТ. ЯДРО ИСПОЛНЯЕТСЯ.**

---

## 12. ФИНАЛ: gp-0x7946 = CRC16 партиции (2026-10-25, сессия 2)

### Функция 0x83396880 (CCheck — вызывается из 0x83396a30)

1. Копирует 0x68000 слов (1.7MB) из физ. адреса **0x9fc40000** в flash_table_ptr буфер
   (0x9fc40000 = BCM7405 NAND-контроллер или mapped window, загружен state machine)
2. Читает первые 4 байта BE как счётчик блоков s1
3. Для каждого из s1 блоков:
   - Вычисляет CRC16 через 0x833926d0
   - Сравнивает с сохранённым полем table[i].crc
   - Если ≠: **возвращает 2** (ошибка)
4. Если все блоки OK: **возвращает 0**

Результат → gp-0x7946 (в `0x83396a30`).

### Полная цепочка boot-gate РЕШЕНА

```
gp-0x7946 = CRC16(partition blocks)  → 0 если valid HDF (наш формат OK!)
gp-0x7e24 = НИКОГДА НЕ ПИШЕТСЯ     → всегда 0

boot_jump → blob_check(gp-0x7e24=0) → ВСЕГДА ядро (0x800B0000)
```

**ВЫВОД: НИКАКОГО BLOB-GATE В Y4.11 НЕТ.**  
Наш custom kernel с null blob **ЗАПУСКАЕТСЯ** без ошибки загрузчика.

### Что тогда вызывает цикл 13-15с?

Ядро исполняется, но крашится → MIPS exception → вектор 0xBFC00180 (bootrom) → чип-резет → цикл. Причина краша **НЕИЗВЕСТНА**.

README и MICOM_PROTOCOL.md ("blob-gate: нулевой blob фейлит проверку") — **ОШИБОЧНЫЙ ВЫВОД** (умозаключение из поведения, не из кода).

### Что РЕАЛЬНО не проверено (ответ на вопрос пользователя)

| Вопрос | Статус |
|--------|--------|
| Флэш проходит без crypto? | ✅ ПОДТВЕРЖДЕНО (plaintext blocks, CRC16 only) |
| Loader реджектит наш образ? | ✅ НЕТ — boot_jump всегда прыгает на 0x800B0000 |
| Ядро исполняется? | ✅ ДА — 13с = ядро работает потом крашится |
| Почему ядро крашится? | ❌ НЕИЗВЕСТНО — нет вывода с раннего head.S |
| UART0 выводит что-то из ядра? | ❌ НЕИЗВЕСТНО — не тестировалось |
| BCM7405 init state при прыжке? | ❌ НЕИЗВЕСТНО — что CFE успела настроить? |
| Stub корректно релоцирует? | ✅ В теории OK, не верифицировано на реале |
| EEPROM[0xE2] testflag (type-4) | ✅ ИЗУЧЕНО — wildcard SysID ПИШЕТ [0xe2] + boot_jump bypass (см. §7, §14) |

### Следующий шаг (единственный важный)

Добавить в `head.S` прямую запись в UART0 BCM7405 **в первых ~10 инструкциях**, до любого C-кода:
```asm
/* BCM7405 UART0 ULCR = 0x10406b00 + 0x0c, UTHR = 0x10406b00 */
li   $t0, 0xb0406b00   /* UART0 base, kseg1 uncached */
li   $t1, 0x58         /* 'X' */
sw   $t1, 0($t0)       /* TX byte */
```
Если 'X' появился в minicom — ядро живо, бисектим где падает.
Если тишина — stub не сработал или прыжок на мусор.

---

---

## 14. ПОЛНЫЙ АНАЛИЗ: 0x83354bfc + 0x9fc40000 (2026-10-25, сессия 3)

### 0x83354bfc — это NAND STATUS EVENT WAITER, не дата-ридер

Сигнатура: `f(a0=NAND_struct, a1=mask, a2=type, a3=output_ptr, t0=wait_flag)`

Логика:
```
1. Acquire semaphore (0x8335e48c(gp-0x7bdc))
2. v1 = NAND_struct[0x18]  ← текущий статус-битмаск
3. v1 &= mask (s2)
4. if type&2: условие = бит СБРОШЕН; else: бит УСТАНОВЛЕН
5. Если условие УЖЕ выполнено:
     *output_ptr = NAND_struct[0x18]; optionally clear bit; return s3
6. Если НЕ выполнено и wait_flag (s6) != 0:
     - NAND_struct[0x1c]++
     - Строим request struct на стеке: [0x00]=0, [0x04]=0, [0x0c]=NAND_struct, [0x10]=mask, [0x14]=type, [0x18]=s3
     - jal 0x83353f5c(NAND_struct+0x20, &request)  ← enqueue в linked list
     - jal 0x8335ad18(s3, 7, callback=0x83354d28, &request, wait_flag)  ← async wait
     - *output_ptr = request[0x20]  ← результат после ожидания
7. Release semaphore (0x8335e598)
8. return s3
```

**Вывод: это ожидатель событий NAND**, не bulk data reader. Ждёт пока конкретные биты в NAND_struct[0x18] изменятся (аппаратный interrupt или polling через callback `0x83354d28`).

- `0x83353f5c` = doubly-linked list insert (enqueue request)
- `0x83354040` = doubly-linked list remove (dequeue: next→prev wiring)
- `0x8335ad18` = async wait/dispatch: вызывает callback `0x83354d28` по событию, читает result из request[0x20]

### Откуда данные в 0x9fc40000

`0x9fc40000` = KSEG0(0x1fc40000) = physical `0x1fc40000`.

На BCM7405: `0x1fc00000..0x1fffffff` = Flash Memory Interface (FMI) window.  
При NAND-only дизайне CFE настраивает FMI NOR-emulation mode или NAND DMA:
- CFE копирует первый партиционный регион в mapped window 0x1fc00000
- Offset 0x40000 = 256KB — стандартный offset для CFE → partition1 в BCM7405 reference designs

**0x9fc40000 не заполняется загрузчиком** — он уже заполнен ДО прыжка в загрузчик:
- CFE/bootrom DMA-ирует NAND partition data в FMI window (0x1fc40000)
- Загрузчик читает оттуда через KSEG0 (0x9fc40000) как из обычной памяти

Подтверждение: в бинаре Y4.11 ровно ОДНА `lui $t9, 0x9fc4` (строка 69206, в CCheck).  
Нет ни одной функции записи в 0x9fc40000 или настройки DMA на этот адрес.  
CCheck просто делает `memcpy(flash_table_ptr, 0x9fc40000, 0x68000*4)` — читает как ROM.

### Async NAND event system (summary)

```
state machine → 0x8335d818 → 0x83352db8 → 0x83354bfc (event waiter)
                                               ↓
                                     enqueue в NAND_struct[0x20] list
                                               ↓
                               0x8335ad18(counter, 7, cb=0x83354d28, req, flag)
                                               ↓
                          когда NAND бит изменился: callback → req[0x20]=result
                                               ↓
                                    state machine accumulates bits
                                    когда s0==5: break → OTA check → boot
```

Биты s0: bit0 (`sp+4 & 1`) + bit2 (`sp+4 & 4`) = значение 5 = "partition ready".

---

## 10. ВЫВОДЫ

| Вектор | Статус | Что нужно |
|--------|--------|-----------|
| WDN4OAK serial dump | **Готов** | WEMOS + провода (в пути) |
| JTAG EJTAG dump | **Готов** | WEMOS + провода (в пути) |
| MICOM 13s window + netconsole | **Готов** | Сборка ядра с UDP-дампером |
| **Wildcard SysID type-4 bypass** | **НОВЫЙ** | HDF с SysID range=FFFFFFFF/FFFFFFFF; см. §7/§14 |
| origlen overflow (boot) | Будущее | Нужен блоб |
| Signature bypass | ❌ Нет пути | Нужен мастер-ключ Y5.06 |

**Критический путь**: Прошить plaintext ядро (v15) → отправить wildcard SysID trigger → loader bypass CCheck gate → ядро запускается.

Альтернативный путь к CFE dump (если ядро крашится, нужен blob анализ):
1. `tools/humax_serial_dump.py` через CP2102 (WDN4OAK, требует Download Mode)
2. JTAG через WEMOS D1 mini + OpenOCD (требует физического доступа к JTAG пинам)
3. MICOM 13s window: стандартный initramfs + `dd if=/dev/mtd0 | nc -u 255.255.255.255 6667`

**Новый приоритет:** попробовать wildcard SysID сразу — быстрый тест, не требует дополнительного оборудования.
