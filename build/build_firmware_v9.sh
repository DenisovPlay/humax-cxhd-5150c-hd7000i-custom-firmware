#!/bin/bash
# ============================================================================
# Humax CXHD-5150C Custom Firmware Builder v9
#
# ОТКРЫТИЕ (2026-10-24, спасибо треду hummy.tv 6583 и dilpish):
#   payload на 0x80100400 в СТОКЕ — сам по себе HDF-файл (вложенный контейнер):
#     * заголовок 18 байт (Model 4, SysID 0000.0000-ffff.ffff = «любой»)
#     * блоки type 1 с flags 0x89 (0x80=сжатие | 0x08=шифрование)
#   Бутлоадер парсит kernel-партицию КАК HDF. Сырой vmlinux.bin из v6/v8
#   валился на первом же байте («00 12»-заголовка нет) -> вис на сплеше.
#
# v9: берём ЯДРО v8 (уже с трамплином j kernel_entry на offset 0) и заворачиваем
#   его во вложенный HDF (блоки flags 0 — без сжатия и без шифрования).
#   Если бут не требует флага шифрования/подписи — ядро загрузится.
#
# Варианты:
#   V9_FLAGS_MODE=raw  (по умолчанию): внутренние блоки flags 0
#   V9_FLAGS_MODE=zlib              : внутренние блоки flags 0x80 (zlib)
#
# Запуск (в контейнере humax-build или ubuntu:14.04 c монтированным /data):
#   bash /data/build/build_firmware_v9.sh
# ============================================================================
set -e
HUM=/data/tools/humidify-ubuntu-1.0.4
chmod +x $HUM 2>/dev/null || true

MODE="${V9_FLAGS_MODE:-raw}"
KERNEL=/data/hdf_work/custom_kernel_v8.raw   # ядро v8 с трамплином
[ -f "$KERNEL" ] || { echo "ERROR: $KERNEL не найден (сначала собери v8)"; exit 1; }
KSIZE=$(stat -c%s "$KERNEL")
echo "=== v9 builder: ядро v8 ($KSIZE байт), режим блоков: $MODE ==="
[ "$KSIZE" -le 2096128 ] || { echo "ERROR: ядро больше партиции"; exit 1; }

cd /data/hdf_work

# --- 1. Внутренний HDF (то, что ляжет на 0x100400) ---
INNER_NAME=custom_kernel_v9_inner_raw.hdf
COMPRESS_FLAG="-r"
[ "$MODE" = "zlib" ] && { INNER_NAME=custom_kernel_v9_inner_zlib.hdf; COMPRESS_FLAG=""; }

$HUM -c $INNER_NAME 0000.0000-ffff.ffff $COMPRESS_FLAG \
    "$(basename $KERNEL):1:0"

echo "--- Внутренний HDF:"
$HUM -l $INNER_NAME 2>&1 | grep -vE "^HDF Tool|^$"

# Проверка флагов: raw -> Flags 0; zlib -> Flags 0x80 (0x89 у стока мы
# воспроизвести не можем — там шифрование бутлоадера).
FLAGS_GOT=$($HUM -l $INNER_NAME 2>/dev/null | awk 'NR>7 {print $4; exit}')
echo "flags внутренних блоков: $FLAGS_GOT (у стока 0x89)"

# --- 2. Внешний HDF (структура как у v6c, которая прошивается) ---
OUT=/data/build/custom_firmware_v9_$MODE.hdf
cp $INNER_NAME inner_v9.raw

$HUM -c $OUT 8050.8400 -r \
    inner_v9.raw:1:80100400 \
    dummy_hdr_rootfs.raw:1:80600000 \
    dummy_rootfs.raw:1:80600400

echo ""
echo "=== Внешний HDF:"
$HUM -l $OUT 2>&1 | grep -vE "^HDF Tool|^$"
echo ""
ls -lh $OUT
echo ""
echo "Готово: cp $OUT /Volumes/UNTITLED/cxhd_5150c_upgrade.hdf"
echo "Прошивать: CH- + питание, ждать END. Слушать: nc -lu 6666"
