#!/usr/bin/env python3
"""
Build a minimal HDF with sysid_min=sysid_max=0xFFFFFFFF.

Loader path (Y4.11 / Y5.06):
  0x833918ac → 0x8838ffc0 (parse outer header)
             → 0x833917a0 (sysid check: both==0xFFFFFFFF → wildcard)
             → 0x8337fc7c  (write EEPROM[0xe2]=1)
             → 0x83397304  (boot_jump — bypasses gp-0x7946 CCheck gate)

USB delivery: cp cxhd_5150c_upgrade.hdf /Volumes/UNTITLED/
              Hold CH- on front panel, power on, wait P000..END.
"""
import struct, sys

def crc16arc(data):
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = ((crc >> 1) ^ 0xA001) if crc & 1 else (crc >> 1)
    return crc & 0xFFFF

def make_hdf_wildcard():
    # Minimal block: flags=0x00, type=0x01, origlen=0, addr=0, no payload
    body = struct.pack(">BBHI", 0x00, 0x01, 0x0000, 0x00000000)
    blen = 10  # = 10 + len(payload=0)
    block = struct.pack(">HH", blen, crc16arc(body)) + body

    # Outer header: model=4, 1 block, sysid_min=sysid_max=0xFFFFFFFF
    hdr_tail = struct.pack(">HHII", 4, 1, 0xFFFFFFFF, 0xFFFFFFFF) + struct.pack(">I", len(block))
    hdr = struct.pack(">HH", 0x0012, crc16arc(hdr_tail)) + hdr_tail

    return hdr + block

if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "wildcard_trigger.hdf"
    hdf = make_hdf_wildcard()
    with open(out, "wb") as f:
        f.write(hdf)
    print(f"Written {len(hdf)} bytes → {out}")
    print(f"Hex: {hdf.hex()}")
    # sanity: outer header fields
    hdr_tail = hdf[4:20]
    crc_stored = struct.unpack(">H", hdf[2:4])[0]
    crc_calc   = 0
    for b in hdr_tail:
        crc_calc ^= b
        for _ in range(8):
            crc_calc = ((crc_calc >> 1) ^ 0xA001) if crc_calc & 1 else (crc_calc >> 1)
    print(f"Header CRC stored={crc_stored:#06x} calc={crc_calc:#06x} {'OK' if crc_stored==crc_calc else 'MISMATCH'}")
    sysid_min = struct.unpack(">I", hdf[8:12])[0]
    sysid_max = struct.unpack(">I", hdf[12:16])[0]
    print(f"sysid_min={sysid_min:#010x} sysid_max={sysid_max:#010x}")
