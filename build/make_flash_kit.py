#!/usr/bin/env python3
"""Флеш-кит «пробуем всё» (2026-10-24, режим полной свободы прошивок).

Опирается на:
  - формат HDF из hdf_packer.py (проверен байт-в-байт по стоку)
  - type-4 блок смены SysID (эталон qnM_FTFE10601_merge.HDF:
    [000e][crc16][flags=00][type=04][origlen=0004][addr=0][SysID BE])
  - 262B заголовок партиции: [01 00][256B blob][used_size BE = 0x400+inner]
  - v9c показал: checksum-хвосты не обязательны для прошивки
"""
import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hdf_packer import crc16arc, make_block, make_hdf  # noqa: E402

HUM = "/Users/andrey/Desktop/humax"
OUT = os.path.join(HUM, "build", "flash_kit")
os.makedirs(OUT, exist_ok=True)

KERNEL = open(os.path.join(HUM, "hdf_work", "custom_kernel_v8.raw"), "rb").read()
SYSID_BOX = 0x80508400     # текущий SysID коробки (OnLime Y5.06)
SYSID_5100C = 0x805C5D00   # PRIMACOM CXHD-5100C 1.00.23
SYSID_7000I = 0x805C8700   # HD 7000i


def hdf_file(blocks, sysmin, sysmax):
    body = b"".join(blocks)
    hdr_tail = struct.pack(">HHII", 4, len(blocks), sysmin, sysmax) + \
        struct.pack(">I", len(body))
    hdr = struct.pack(">HH", 0x0012, crc16arc(hdr_tail)) + hdr_tail
    return hdr + body


def type4_block(new_sysid):
    return make_block(struct.pack(">I", new_sysid), 0x00, 0x04, 4, 0)


def hdr262(inner_size, blob=b"\x00" * 256):
    return b"\x01\x00" + blob + struct.pack(">I", 0x400 + inner_size)


def inner_hdf(data, flags=0x00):
    return make_hdf(data, flags=flags, typ=0x01, sysid=(0, 0xFFFFFFFF),
                    chunk=32758, with_checksum_tail=None)


def w(name, data):
    p = os.path.join(OUT, name)
    open(p, "wb").write(data)
    print(f"{name:38s} {len(data):>9} bytes")


# ── T1: проба поддержки type-4 (no-op: SysID = текущий) ─────────────────
w("t1_type4_NOOP_probe.hdf",
  hdf_file([type4_block(SYSID_BOX)], SYSID_BOX, SYSID_BOX))

# ── T2: смена SysID коробки → 5100C (в флеше уже лежит PRIMACOM!) ────────
w("t2_type4_to_5100C.hdf",
  hdf_file([type4_block(SYSID_5100C)], SYSID_BOX, SYSID_BOX))

# ── T3: смена SysID → 7000i ──────────────────────────────────────────────
w("t3_type4_to_7000i.hdf",
  hdf_file([type4_block(SYSID_7000I)], SYSID_BOX, SYSID_BOX))

# ── T9: спасательный: вернуть 8050.8400, диапазон ШИРОКИЙ ────────────────
w("t9_type4_RESTORE_wide.hdf",
  hdf_file([type4_block(SYSID_BOX)], 0x00000000, 0xFFFFFFFF))

# ── D2a: ядро v8 с нулевым блобом (расшифровка не нужна?) ────────────────
inner = inner_hdf(KERNEL, flags=0x00)
w("d2a_zeroblob_plain_kernel.hdf",
  hdf_file([make_block(hdr262(len(inner)), 0x00, 0x01, len(inner) and 262 or 262, 0x80100000),
            make_block(inner[:32758], 0x00, 0x01, 32758, 0x80100400)] +
           [make_block(inner[o:o + 32758], 0x00, 0x01, len(inner[o:o + 32758]),
                       0x80100400 + o) for o in range(0, len(inner), 32758)][1:],
           SYSID_BOX, SYSID_BOX))

# ── D2b: то же + нулевой rootfs-заголовок с минимальным внутренним HDF ───
mini = inner_hdf(b"HUMAX", flags=0x00)
w("d2b_zeroblob_kernel_and_rootfs.hdf",
  hdf_file([make_block(hdr262(len(inner)), 0x00, 0x01, 262, 0x80100000)] +
           [make_block(inner[o:o + 32758], 0x00, 0x01, len(inner[o:o + 32758]),
                       0x80100400 + o) for o in range(0, len(inner), 32758)] +
           [make_block(hdr262(len(mini)), 0x00, 0x01, 262, 0x80300000),
            make_block(mini, 0x00, 0x01, len(mini), 0x80300400)],
           SYSID_BOX, SYSID_BOX))

# ── D4: как D2a, но блоки внутреннего HDF с флагом 0x80 (zlib) ──────────
import zlib
kz = zlib.compress(KERNEL, 9)
w("d4_zeroblob_zlibflag_kernel.hdf",
  hdf_file([make_block(hdr262(len(inner)), 0x00, 0x01, 262, 0x80100000)] +
           [make_block(kz[o:o + 32758], 0x80, 0x01, len(kz[o:o + 32758]),
                       0x80100400 + o) for o in range(0, len(kz), 32758)],
           SYSID_BOX, SYSID_BOX))

# ── T7: только внутренний HDF ядра, БЕЗ 262B-заголовка ───────────────────
w("t7_kernel_only_no_hdr.hdf",
  hdf_file([make_block(inner[o:o + 32758], 0x00, 0x01, len(inner[o:o + 32758]),
                       0x80100400 + o) for o in range(0, len(inner), 32758)],
           SYSID_BOX, SYSID_BOX))

print("\nГотово:", OUT)
