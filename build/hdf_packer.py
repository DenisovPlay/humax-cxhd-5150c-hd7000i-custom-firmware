#!/usr/bin/env python3
"""Ручной пакер HDF-контейнеров для Humax (формат реверснут 2026-10-24).

Формат (проверен по байтам стока и humidify):
  Header (20 байт):
    [hdr_len:2 = 0x0012 (18, не считая поля длины)]
    [crc16:2  = CRC16/ARC(header[4:20])]
    [model:2  = 0x0004]
    [blocks:2]
    [sysid_min:4] [sysid_max:4]
    [data_len:4 = sum(2+blen) всех блоков]
  Блок:
    [blen:2 = 10 + len(payload)]          # без самого поля blen
    [crc16:2 = CRC16/ARC(flags+type+origlen+addr+payload)]
    [flags:1] [type:1] [origlen:2] [addr:4] [payload]
  Хвостовой checksum-блок стока: type=0x80, origlen=20, payload неизвестного
  рецепта (SHA-based, возможно keyed) — пакер умеет НЕ писать его вообще.

CRC16/ARC: poly 0x8005 (reflected 0xA001), init 0, refin/refout, xorout 0.
"""
import struct
import sys


def crc16arc(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc >> 1) ^ 0xA001) if crc & 1 else (crc >> 1)
    return crc & 0xFFFF


def make_block(payload, flags, typ, origlen, addr):
    body = struct.pack(">BBHI", flags, typ, origlen, addr) + payload
    blen = 10 + len(payload)
    return struct.pack(">HH", blen, crc16arc(body)) + body


def make_hdf(data, flags=0x00, typ=0x01, sysid=(0, 0xFFFFFFFF),
             chunk=32758, with_checksum_tail=None):
    """Собирает HDF из одного файла данных.

    with_checksum_tail: None — без хвостового блока (v9c);
                        bytes — произвольный payload хвостового блока.
    """
    blocks = []
    off = 0
    while off < len(data):
        piece = data[off:off + chunk]
        blocks.append(make_block(piece, flags, typ, len(piece), off))
        off += len(piece)
    if with_checksum_tail is not None:
        blocks.append(make_block(with_checksum_tail, 0x00, 0x80,
                                 len(with_checksum_tail), 0))
    body = b"".join(blocks)
    hdr_tail = struct.pack(">HHII", 4, len(blocks), sysid[0], sysid[1]) + \
        struct.pack(">I", len(body))
    # hdr_tail = [model:2][blocks:2][sysid_min:4][sysid_max:4][data_len:4] = байты 4..20
    hdr = struct.pack(">HH", 0x0012, crc16arc(hdr_tail)) + hdr_tail
    return hdr + body


def parse(path):
    d = open(path, "rb").read()
    hlen, hcrc, model, blocks = struct.unpack(">HHHH", d[:8])
    sysmin, sysmax, dlen = struct.unpack(">III", d[8:20])
    print("hdr: len=%d crc=%#06x(%s) model=%d blocks=%d sysid=%#x-%#x dlen=%d" %
          (hlen, hcrc, "OK" if crc16arc(d[4:20]) == hcrc else "BAD",
           model, blocks, sysmin, sysmax, dlen))
    off = 20
    for i in range(blocks):
        blen, bcrc, flags, typ, origlen, addr = struct.unpack(">HHBBHI", d[off:off + 12])
        payload = d[off + 12: off + 2 + blen]
        calc = crc16arc(d[off + 4:off + 2 + blen])
        if i < 2 or i >= blocks - 2:
            print(" blk %d: len=%d crc=%#06x(%s) flags=%#x type=%#x olen=%d addr=%#x dlen=%d" %
                  (i, blen, bcrc, "OK" if calc == bcrc else "BAD",
                   flags, typ, origlen, addr, len(payload)))
        off += 2 + blen
    print(" end @%d filesize=%d %s" % (off, len(d), "OK" if off == len(d) else "MISMATCH"))


if __name__ == "__main__":
    if sys.argv[1] == "parse":
        parse(sys.argv[2])
    elif sys.argv[1] == "pack":
        # pack <input.bin> <output.hdf> [flags_hex] [tail:none|20zero]
        inp, outp = sys.argv[2], sys.argv[3]
        flags = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x00
        tail = None
        if len(sys.argv) > 5 and sys.argv[5] == "20zero":
            tail = b"\x00" * 20
        data = open(inp, "rb").read()
        open(outp, "wb").write(make_hdf(data, flags=flags, with_checksum_tail=tail))
        print("packed %d -> %d bytes (%s tail)" %
              (len(data), 20 + 12 * ((len(data) + 32757) // 32758) + len(data) + (0 if tail is None else 32),
               "no" if tail is None else "20zero"))
