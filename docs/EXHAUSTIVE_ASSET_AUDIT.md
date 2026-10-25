# ИСЧЕРПЫВАЮЩИЙ АУДИТ ВСЕХ АКТИВОВ ПРОЕКТА (2026-10-25, по требованию «прямо ВСЁ»)

## 1. Матрица «файл → глубина разбора»

| Актив | Что это | Глубина |
|---|---|---|
| loaders/loader_Y411_CCX_393k.bin | Y4.11-лоадер CCX (BE) | ★★★ полный дизасм (loader_full.asm, 999 функций, аудит) |
| loaders/cfe_hdfoxt2.bin | HD-FOX T2 лоадер (mipsel!) | ★★ структура/строки; == loader_from_hdfoxt2 (дубликат, MD5 совпал) |
| loaders/cfe_foxsat_u754.bin | FOXSAT лоадер (BE) | ★ структура только |
| N75 boot.img | CFE 2005 (boot/tftp/reboot, CP0-сетап) | ★★ строки+вход |
| FOX T2 rootfs (foxt2_rootfs/) | ПОЛНЫЙ распакованный сток | ★★★ скрипты/inittab/MICOM — см. §3 |
| FOX T2 kernel_hdr.bin (ELF) | gzip-ядра FOX T2 | ★★★ линк 0x80001000, entry 0x80390000 |
| firmwares/genuine/onlime_early | 7000i с патчем SysID (6 байт diff) | ★★★ = ранний «оригинал» юзера |
| PRIMACOM/7000i HDF | стоки 5100C/7000i | ★★★ поблочно, блобы, chk |
| 5000T/9200T/NPGTTF/LNR | webarchive model 3/4 | ★★★ структура+форматы (WEBARCHIVE_FINDINGS) |
| FPX app 4.2MB | расшифрованный CCX-образ | ★★ заголовок+вход; MICOM-часть НЕ разобрана |
| IA config (type 3) стримы | БД каналов | ✗ НЕ разбирались (низкий приоритет) |
| WDN4OAK ×8 | InstallShield, RS-232 загрузчик | ✗ НЕ распакованы |
| bcmdriver.ko (FOX T2) | драйвер Broadcom | ★ строки; MICOM-строк нет |
| humaxtv (FOX T2) | главный app | ★★ MICOM-строки; дизасм НЕ делался |

## 2. Семейные конвенции (все источники, окончательно)

- **Формат образа**: `[8 нулей][lui $t0,0x800B; addiu $t0,0x508; jr][поля][CFE-баннер ×2 endianness][код@+0x508]` — подтверждено ТРИЖДЫ (CCX app, FPX app, 9200T app)
- **Вход +0x508** = mtc0-сетап: Status(BEV), Cause, **Config=0x2D8C2**, стек, gp, j main
- **Бут-копировщик** (Y4.11, построчно): только type 1, dst=0x800B0000+Σolen,
  flags 0x80→codec+decrypt, 0x00→raw memcpy, type 0x80 пропуск, КРИПТО-ПРОВЕРОК НЕТ
- **262B заголовок партиции**: `[01 00][256B blob][used_size BE]` — 5000T/5100C/7000i/наши
- **20B checksum** = `[16B keyed?][SHA1(стрим)[-4:]]` — подтверждено на 4+2 оракулах
- **5000T-урок**: flags=0x00 payload может быть непрозрачным — лоадер не глядит
- **Блоб**: НЕ хеш, НЕ keys-в-открытую → зашифрован коробочным ключом

## 3. FOX T2 rootfs — заводская механика (главное из распаковки)

```
/etc/inittab:
  ::sysinit:/etc/init.d/rcS
  ::once:/sbin/reboot /dev/null        ← РЕБУТ после прохода init (если humaxtv умер — ЦИКЛ!)
  #ttyS0::respawn:/bin/sh              ← (debug-ветка закомментирована)
S90settop: exec /usr/bin/humaxtv       ← exec: падение humaxtv = конец rcS → reboot
  + if grep -q "nosettop" /proc/cmdline: exit 0   ← СТОКОВЫЙ обход app = консоль
```
- **Механизм сток-цикла = inittab `once:reboot`** (не MICOM!): humaxtv умер → rcS
  закончился → init выполнил once-reboot. Наш случай — раньше (до userspace).
- MICOM: в humaxtv есть `micom_rxtx`, `MICOM_KEY_Event_Task` — общение с передней
  панелью через /dev/brcm0 (bcmdriver.ko). Формат команд НЕ разобран (дизасм humaxtv).
- /sbin/watchdog = busybox-апплет (в стоке на /dev/watchdog).
- Разбор rootfs: unsquashfs 3.1r2 native (собран из deb-архива, tools/unsquashfs-3.1r2-native;
  ВАЖНО: у старого unsquashfs НЕ работает -d, извлекает в ./squashfs-root!)

## 4. Ключевые выводы для нашей коробки (сводка)

1. Наш цикл — ДО userspace (наш initramfs без stock-init) → остаются 2 гипотезы:
   a) **блоб-гейт**: нулевой блоб фейлит проверку → лоадер не прыгает → сам рестартует по таймауту;
   b) прыжок есть, но умираем на CP0/Config-сетапе (v16: добавить mtc0-сетап по 9200T).
2. MICOM: кормление в стоке делает humaxtv (userspace) — значит ЯДРО (наш Linux)
   может вообще не быть обязано кормить MICOM, пока не запущен app... ЛОАДЕР кормит
   сам — поэтому его статичные состояния вечны. Если наш образ прыгает — кормильца
   нет → MICOM-таймаут → резет 13-15с. Оба варианта лечатся: (a) ключ блоба (JTAG),
   (b) CP0-сетап + MICOM-pet из ядра (протокол — дизасм micom_rxtx в humaxtv!).
3. `nosettop` — доказанный стоковый cmdline-обход app (для будущей кастомной сборки).

## 5. Что осталось неразобранным (честный список)

- WDN4OAK (8 версий, InstallShield) — серийный протокол лоадера
- humaxtv micom_rtx ДИЗАССЕМБЛИРОВАНИЕ (формат команд MICOM!)
- FPX app stream — полный (там тоже MICOM-клиент, BE-вариант)
- IA type-3 конфиги (БД каналов)
- cfe_foxsat/cfe_hdfoxt2 — полный аудит (менее приоритетно: другие семьи)
