# Humax CXHD-5150C — Linux Root Access Research

Reverse engineering project targeting the OnLime/Rostelecom-branded Humax CXHD-5150C
set-top box. Goal: obtain root Linux shell access on operator-locked hardware.

**Status:** active — device bricked (Y4.11 96% write → E-FE), JTAG recovery + direct Linux boot via JTAG ready.

## Важное для наших

Нормальной прошивки под OnLime ещё нет, процесс идёт всеми возможными путями, включая дизасембл слитых файлов, смежных моделей и прошивок, а также всевозможные методы получения дампа флеша. UART, JTAG и так далее. Принимаются все предложения. ЕСЛИ У ВАС ЕСТЬ ДАМПЫ ПРОШИВОК - МОЛЮ, СКИДЫВАЙТЕ ВСЁ В ПУЛ РЕКВЕСТЫ ИЛИ ИЩЬЮ. Сейчас - жду новый WEMOS, старый спалил :( Уточню, использовать ИИ МОЖНО, но смотрите что он вам там делает.

!!! ВНИМАНИЕ !!!
- НЕ БЕРИТЕ ОТСЮДА ПРОШИВКИ, ОНИ УБЬЮТ ВАШУ ПРИСТАВКУ. ДА, 100%. В НИХ НЕТ КЛЮЧА. ПРИСТАВКА ИХ СОЖРЁТ, НО ЛИБО ЗАСТРЯНЕТ НА ЛОГОТИПЕ ИЛИ БУДЕТ КРУТИТЬСЯ В ЦИКЛЕ.
- ДОЖДИТЕСЬ ЛИБО ПОЛНОГО РЕЛИЗА, ЛИБО ЕСЛИ У ВАС ЕСТЬ ЛЮБЫЕ .hdf ФАЙЛЫ, КОТОРЫХ ЕЩЁ НЕТ В РЕПОЗИТОРИИ - СКИНЬТЕ ИХ СЮДА (проверяйте по MD5, чтобы не было дублей).
- РЕАЛЬНО НИЧЕГО НЕ ШЕЙТЕ, ДАЖЕ ЕСЛИ НАЗВАНИЕ "ORIGINAL" или совпадает с вашим
- ПОДМЕНА SYSTEM ID НИЧЕГО НЕ ДАСТ - БЕЗ КЛЮЧЕЙ ОНО НЕ ЗАПУСТИТСЯ, А ДАМПА ДЛЯ ONLIME ВЕРСИИ НЕТ!
- ЕСТЬ ПРОГРАММАТОР - СНИМАЙТЕ ПОЛНЫЕ ДАМПЫ, ЕСЛИ ЕСТЬ ЖЕЛАНИЕ - ДОПИСЫВАЙТЕ ПОРТАЛ, ЧТОБЫ ДАМПИТЬ ЧЕРЕЗ НЕГО ИЛИ ВЫЙТИ В РУТ ДОСТУП! (портал дебага есть в репо, ставится через подмену DNS - гуглите, мануал есть в репе)

- [JTAGenum](https://github.com/DenisovPlay/JTAGenum) - JTAG определялка для WEMOS

andreydenisov25@gmail.com, t.me/@zeniflow_support - ПИШИТЕ СЮДА.

---

## Hardware

| Component | Details |
|-----------|---------|
| SoC | Broadcom BCM7405 (BMIPS4380, MIPS32 LE) |
| Loader | Y5.06 (Humax Y-series CCX family) |
| System ID | 8050.8400 (OnLime variant) |
| Flash | NAND, MTD layout confirmed |
| UART | BCM7405 UART0 (console), UART3 = MICOM |
| JTAG | Enabled (confirmed via FUSING INFO menu) |

---

## What Has Been Accomplished

### Firmware format fully reversed (HDF)
- 20-byte outer header + 12-byte block headers; CRC16/ARC throughout
- Double-wrapped: partition payload is itself an inner HDF file
- 262-byte partition header: `[01 00][256B blob][4B used_size]`
- Block flags: `0x00` = plaintext copy, `0x80` = LZRW1 compressed, `0x08` = AES encrypted
- Compression codec identified as LZRW1 (Ross Williams), extracted from `FV3Dll.dll`

### Y4.11 loader fully disassembled (999 functions, 72 576 instructions)
- Boot chain: `boot_app() → copier(0x800B0000) → jalr target`
- Copier copies only type-1 blocks, ignores `addr` field; destination always `0x800B0000`
- **No crypto checks at boot** — plaintext blocks load and execute without signature validation
- AES+SHA256 scheme: `sign = AES(SHA256(content), master_key)`; master key extracted
- Master key (Y4.11): `6ac5e95712d6cd298239c5c1e2540fbe`
- Signature slot written to EEPROM after successful update, not re-verified at boot

### Boot failure root cause identified ("blob-gate")
- The 262B partition header contains a 256-byte blob validated by the loader at boot
- Null blob → loader jumps to bootrom `0xBFE00000` → chip reset → 13–15 s cycle
- This is the sole reason our custom kernels do not persist past the logo screen
- Solution: obtain the blob from a Y5.06 CFE dump

### Serial update protocol decoded (WDN4OAK / FV3Dll.dll)
- Protocol: `PC → 0x06` (CONNECT), then `STB → byte / PC → 0x06` (ACK per byte)
- Total transfer size: `0x62000` bytes (401 408) in `0x2000`-byte chunks
- `UploadData` / `DownloadData` / `UploadSystemID` exports identified
- Python dump tool implemented: `tools/humax_serial_dump.py`

### MICOM identified as UART3 (not I2C)
- `open64("/dev/ttyS2")` + `B115200 CS8` confirmed from HD FOX T2 userland binary
- No periodic watchdog feeding required — the 15 s cycle is purely the blob-gate
- MICOM packet format: `[cmd][total_len][sub/seq][payload...][additive_checksum]`

### Custom kernel infrastructure built
- Cross-compiler: `mipsel-linux-uclibc` (stblinux toolchain)
- Kernel: `stblinux-2.6.18-7.1`, patched load address `0x800B0000`
- PIC self-relocating stub v15: disables BCM7405 SoC watchdog, copies image to
  `0x800AFAE0` (= `0x800B0000 − 0x520`) before jumping to kernel entry
- Entry point at `+0x508` per CCX app-header convention
- Initramfs with BusyBox, static IP, netconsole broadcast to `255.255.255.255:6666`

### Type-4 HDF block confirmed working on our Y5.06
- SysID changed to arbitrary values and restored — loader processes type-4 without
  signature verification

### v20 kernel built (Linux 2.6.18, BCM7405 mipsel)
- **`hdf_work/vmlinux_v20.elf`** — 2.7 MB ELF, entry `0x802AC000`, loads at `0x800B0000`
- Compiled with: kexec, USB host/storage, FAT32, self-relocating stub v15
- Purpose: load via JTAG `load_image` → Linux in RAM → `kexec` to any kernel from USB
- Bypasses loader, blob-gate, and all signature checks entirely
- **`hdf_work/custom_kernel_v20.bin`** — raw binary (2.5 MB)

### Y5.06 SysID confirmed: `0x80508400`
- `trigger_exact_sysid.hdf` (sysid_min=sysid_max=0x80508400) → flashed OK (P000→END)
- Y5.06 has no wildcard SysID path (FFFF/FFFF → E-ID, 0000/0000 → E-ID)
- Y4.11 wildcard path exists at `0x833917a0` but only in Y4.11 loader

---

## Current Status

### Device bricked (2026-10-25)
Attempted to reflash Y4.11 loader via USB HDF (`y411_loader_repacked.hdf`, sysid patched to
`0x00000000/0xFFFFFFFF`). Flashed 144/150 blocks (96%), then E-FE (Flash Erase/Write error)
on a bad NAND block. Result: partially-written Y4.11 loader — device cannot boot.
- MICOM alive (front-panel LED shows loading animation)
- BCM7405 ROM starts but Y4.11 crashes before UART init → UART silent
- JTAG confirmed enabled (FUSING INFO) → recoverable

### Recovery plan (ESP8266 Wemos D1 mini in transit)

**Option A — Direct Linux boot via JTAG (no NAND write, immediate):**
```bash
openocd -f uart/openocd_bcm7405.cfg
# then in telnet:
> halt
> load_image hdf_work/vmlinux_v20.elf
> resume 0x802AC000
# → Linux boots from RAM, no loader, no blob, no signatures
```
`vmlinux_v20.elf` (2.7 MB) is ready in `hdf_work/`. Contains kexec + USB + FAT32.
From running Linux: `kexec -l /mnt/usb/vmlinux.bin && kexec -e` to boot any kernel from USB stick.

**Option B — Restore NAND loader via JTAG:**
Write the full Y4.11 binary (`firmwares/ia_archive/extracted/FPXCCX10016_Y411/1.hdfbin-0-000000.raw`,
393 192 bytes) to CFE NAND partition. Only the last ~24 KB (blocks 144–149) are missing;
Option A is faster.

**Previous blocker (blob-gate)** — still applies for kernel persistence, but Option A's
kexec path lets us boot from USB indefinitely without touching NAND.

---

## Repository Structure

```
docs/
  HDF_FORMAT.md          — HDF binary format, byte-exact specification
  LOADER_FULL_AUDIT.md   — Complete Y4.11 disassembly audit, boot chain, backdoors
  LOADER_Y411_RE.md      — Y4.11 RE notes: AES keys, MICOM, CCX conventions
  V10_EXPERIMENTS.md     — Experiment log v10–v15, discoveries, failures

build/
  build_firmware_v15.sh  — Current build script (kernel + stub + HDF packer)
  stub_v15.S             — PIC relocating stub, SoC watchdog disable
  hdf_packer.py          — HDF pack/unpack tool

tools/
  humax_serial_dump.py   — WDN4OAK serial dump tool (CP2102 → Y5.06 CFE)
  wdn4oak/               — WDN4OAK installer files (FV3Dll.dll, WDN4OAK.exe)
  humidify-ubuntu-1.0.4  — Official HDF tool (run in Docker)

uart/
  jtagenum/              — JTAGenum.ino for Wemos D1 mini — finds JTAG pin mapping
  esp8266_remote_bitbang/ — OpenOCD remote_bitbang bridge firmware for Wemos D1 mini
  openocd_bcm7405.cfg    — OpenOCD config for BCM7405 MIPS EJTAG

firmwares/
  genuine/               — Stock firmware images (OnLime, PRIMACOM 5100C)
  ia_archive/            — Internet Archive finds (contains Y4.11 loader)
  foxsat/                — HD FOX T2 images (mipsel relative, custom fw works)

loaders/
  loader_Y411_CCX_393k.bin — Full Y4.11 loader binary (reference for RE)
  hdf_work/loader_full.asm — Annotated full disassembly

portal/                  — OnLime TV portal experiments (DNS, HbbTV panel)
kernel/stblinux-2.6.18-7.1/ — Kernel source tree with our patches
```

---

## Related Hardware

### Direct clones (same PCB, cross-flashable)

| Model | Operator | CAS | Notes |
|-------|----------|-----|-------|
| **Humax HD 7000i** (= CXHD-5151) | Dom.ru / ER-Telecom (RU) | Conax | Byte-for-byte identical HDF, differs by 6 bytes (SysID + CRC). Confirmed cross-flashable without hardware modification. Firmware versions: RUCCAA 1.00, 1.20. |
| **Humax CXHD-5100C** | Various EU cable operators | Conax | Same GPL kernel config cluster as CXHD-5150C. |
| **Humax CXHD-5000C** (-FI, -TELE2) | Tele2 FI/SE/EU | Conax | Same kernel branch; -TELE2 / -FI are operator SKUs. Stock firmware confirmed cross-flashable to HD 7000i profile. |
| **Humax DIGI+C HD** | DIGI (RO/HU) | Conax | Same kernel config cluster in GPL sources. |

All of the above share the BCM7405 mipsel SoC, HDF firmware container format,
Y-loader CCX family, and Linux 2.6.18 kernel tree. All findings from this project
apply directly.

### Irdeto variant (same loader family, different CAS)

| Model | Operator | CAS | Service ID | Notes |
|-------|----------|-----|-----------|-------|
| **Humax IRHD-5100C** (/TVT) | Ziggo (NL), TVT (RU/EU) | Irdeto | 7080 | Same HDF structure and Y-loader architecture. |
| **Humax IRHD-5050C** | Ziggo (NL) | Irdeto | — | Same loader family. |
| **Humax IHDR-5200C** | Various EU | Irdeto | 7081 | Dual-tuner PVR variant, same platform. |

### Reference platform (working custom firmware, same SoC)

| Model | Region | Notes |
|-------|--------|-------|
| **Humax HD FOX T2** | UK (Freeview DVB-T2) | BCM7405 mipsel. Active hummy.tv community with working custom firmware. Used in this project as the primary reference for HDF format, kernel load address (`0x80001000` ELF entry vs our `0x800B0000` CCX convention), MICOM protocol, and MTD layout. |
| **Humax HDR FOX T2** | UK (Freeview DVB-T2 PVR) | Same SoC as above. Rootfs fully extracted in this project; `humaxtv` binary used to reverse MICOM/ttyS2 protocol. |

The HD FOX T2 / HDR FOX T2 hummy.tv custom firmware (`nosettop` kernel cmdline arg,
`/etc/init.d` modifications) is the proven end-state we are replicating on the CXHD-5150C.

---

## JTAG Setup (Wemos D1 mini)

Two-step process:

**Step 1 — find pins** (`uart/jtagenum/JTAGenum.ino`):
Flash to Wemos, connect D1/D2/D5/D6/D7 to the JTAG header on the Humax board,
open Serial @ 115200. Send `i` for IDCODE scan; expected BCM7405 response has bit 0 = 1.
Send `s` for full pattern scan. Note the reported TCK/TMS/TDI/TDO mapping.

**Step 2 — dump** (`uart/esp8266_remote_bitbang/esp8266_remote_bitbang.ino`):
Fill in WIFI credentials and the pin mapping found in step 1. Flash. Run OpenOCD:

```bash
openocd -f uart/openocd_bcm7405.cfg
```

```
telnet localhost 4444
> halt
> dump_image cfe_y506.bin 0x80000000 0x80000
```

---

## Serial Dump (WDN4OAK protocol)

Connect CP2102: TX → STB RX, RX → STB TX, GND → GND.
Power on the STB while holding the front panel button to enter Download mode.

```bash
pip3 install pyserial
python3 tools/humax_serial_dump.py /dev/tty.usbserial-XXXX stb_cfe.bin
```

The tool auto-retries until the STB responds.

---

## Key Technical Notes

- The Y-loader **does not verify signatures at boot** — only during USB/OTA update
- The `origlen` field in block headers has no bounds check — potential overflow vector
- `keyidx` in block flags has no bounds check — out-of-bounds key selection
- MICOM watchdog is **not** a concern for a running Linux kernel unless the MICOM driver
  is absent; the boot cycle is caused solely by blob validation failure
- `nosettop` kernel command-line argument skips `humaxtv` and drops to console
  (confirmed on HD FOX T2; expected to work on CXHD-5150C)

---

## References

- BCM7405 BMIPS4380 MIPS32 architecture
- MIPS EJTAG specification v2.6+ (IR length 5)
- LZRW1 compression: Ross Williams, 1991 (public domain)
- JTAGenum: https://github.com/DenisovPlay/JTAGenum
- hummy.tv community research on HD FOX T2 / HDR FOX T2
- OpenOCD `remote_bitbang` driver
