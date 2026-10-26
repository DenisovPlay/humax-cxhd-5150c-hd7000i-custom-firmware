# Humax CXHD-5150C — Linux Root Access Research

Reverse engineering project targeting the OnLime/Rostelecom-branded Humax CXHD-5150C
set-top box. Goal: obtain root Linux shell access on operator-locked hardware.

**Status (2026-10-26):** active — the device is bricked (Y4.11 flash stopped at
144/150 blocks, E-FE on a bad NAND block). The JTAG programmer has arrived at the
Ozon pickup point and has not been collected yet. Current work: JTAG bring-up →
run our own code on the CPU → build our own loader → boot Linux from USB.
The Y-loader flash path is abandoned.

## Текущий фокус

Коротко для наших:

- **Приставка — кирпич.** Y4.11 прошился на 96% (144/150 блоков), дальше E-FE на
  бэд-блоке NAND. Живого загрузчика нет: UART молчит, до Download Mode дело не
  доходит. **Ничего не шьём.**
- **UART-дамп (WDN4OAK) снят с повестки.** Он требует живого загрузчика/Download
  Mode, а его нет. Инструмент и разбор протокола остаются в репо — вернёмся к ним,
  когда свой код поднимет UART.
- **Сейчас главное — JTAG.** Программатор (ESP8266 Wemos D1 mini) уже приехал в
  пункт выдачи Ozon, осталось забрать. План: OpenOCD → halt → выполнить свой код
  в DRAM → снять дампы → собрать свой загрузчик.
- **Цель — свой лоадер, а не Y-loader.** Грузим код через JTAG, из него
  инициализируем DRAM/NAND/USB и запускаем Linux 2.6 с флешки. Y4.11/Y5.06 больше
  не трогаем.
- **Что уже готово:** `hdf_work/vmlinux_v20.elf` (entry `0x802ac000`, load
  `0x800b0000`) с kexec, USB host/storage, FAT32 и initramfs. Грузится JTAG-ом,
  дальше `kexec` на ядро с USB.
- **Дампы похожих коробок** (HD FOX T2, FOXSAT-HDR — тот же BCM7405) используем как
  эталон инициализации USB/NAND/CFE.

Старые предупреждения в силе: чужие прошивки из репо не шить, ключей в них нет, без
дампа CFE (Y5.06) подмена SysID ничего не даёт. Если у вас есть `.hdf`, которых нет
в репозитории — присылайте (сверяйте MD5, чтобы не было дублей).

- [JTAGenum](https://github.com/DenisovPlay/JTAGenum) — JTAG определялка для WEMOS

andreydenisov25@gmail.com, t.me/@zeniflow_support — ПИШИТЕ СЮДА.

---

## Hardware

| Component | Details |
|-----------|---------|
| SoC | Broadcom BCM7405 (BMIPS4380, MIPS32 LE) |
| Loader | **partially flashed Y4.11** (144/150 blocks; original Y5.06 lost) |
| System ID | 8050.8400 (OnLime variant) |
| Flash | NAND, MTD layout confirmed |
| UART | BCM7405 UART0 (console), UART3 = MICOM |
| JTAG | Enabled (confirmed via FUSING INFO menu) |
| Programmer | ESP8266 Wemos D1 mini + OpenOCD `remote_bitbang` — at Ozon pickup |

---

## План восстановления и запуска своего кода

| Этап | Что делаем | Критерий успеха | Статус |
|------|------------|-----------------|--------|
| 0 | Забрать Wemos | плата на руках | ждёт Ozon |
| 1 | Поднять JTAG | OpenOCD видит TAP/IDCODE, `halt` работает, читаются регистры CP0 | конфиг готов |
| 2 | Свой код на CPU | payload в DRAM, запись маркера в память/порт, результат виден по JTAG или UART | следующий шаг |
| 3 | Дампы | DRAM, boot ROM, CFE/лоадер из NAND (если читается через CPU) | — |
| 4 | Свой загрузчик | DRAM + UART + NAND + USB, загрузка Linux | проектирование |
| 5 | Linux с USB | v20 грузится через JTAG → `kexec` на ядро с флешки | образ готов |
| 6 | Постоянная загрузка | свой лоадер в NAND, только после полного бэкапа | потом |

**Почему так.** Y-loader — единственное, что мешало: он проверяет 262-байтный
заголовок партиции и 256-байтный блоб, а без валидного блоба уходит в bootrom и
сбрасывает чип. JTAG и свой лоадер обходят и проверку, и сам Y-loader целиком —
нам не нужны ни подпись, ни блоб, ни Download Mode.

**Что даст свой лоадер.** Полный контроль над загрузкой: свой UART-консоль,
чтение NAND, USB host/storage, загрузка ELF/raw-ядра с флешки и передача управления
ядру. Первая ступень — минимальный Linux 2.6 (v20): он уже умеет USB/FAT32 и kexec,
из него можно прыгнуть на основной образ с флешки, не дожидаясь полностью своего
bare-metal лоадера. Дампы HD FOX T2 / FOXSAT-HDR (тот же BCM7405) используем как
эталон инициализации CFE/USB/NAND, а не как прошивку для записи.

---

## What Has Been Accomplished

### Firmware format fully reversed (HDF)
- 20-byte outer header + 12-byte block headers; CRC16/ARC throughout
- Double-wrapped: partition payload is itself an inner HDF file
- 262-byte partition header: `[01 00][256B blob][4B used_size]`
- Block flags: `0x00` = plaintext copy, `0x80` = LZRW1 compressed, `0x08` = AES encrypted
- Compression codec identified as LZRW1 (Ross Williams), extracted from `FV3Dll.dll`
- Packer: `build/hdf_packer.py`; CRC16 verified byte-exact against stock HDFs and
  all generated trigger/kits

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
- This is the sole reason our custom kernels did not persist past the logo screen
- Solution in the old plan: obtain the blob from a Y5.06 CFE dump
- **Not on the current critical path** — JTAG + custom loader bypasses this gate entirely

### Serial update protocol decoded (WDN4OAK / FV3Dll.dll) — deferred
- Protocol: `PC → 0x06` (CONNECT), then `STB → byte / PC → 0x06` (ACK per byte)
- Total transfer size: `0x62000` bytes (401 408) in `0x2000`-byte chunks
- `UploadData` / `DownloadData` / `UploadSystemID` exports identified
- Python dump tool: `tools/humax_serial_dump.py`
- **Unusable on the bricked box** (no loader → no Download Mode); kept for later

### MICOM identified as UART3 (not I2C)
- `open64("/dev/ttyS2")` + `B115200 CS8` confirmed from HD FOX T2 userland binary
- No periodic watchdog feeding required — the 15 s cycle is purely the blob-gate
- MICOM packet format: `[cmd][total_len][sub/seq][payload...][additive_checksum]`

### Custom kernel infrastructure built
- Cross-compiler: `mipsel-linux-uclibc` (stblinux toolchain)
- Kernel: `stblinux-2.6.18-7.1`, patched load address `0x800B0000`
- PIC self-relocating stub: copies image to `0x800AFAE0`
  (= `0x800B0000 − 0x520`) before jumping to kernel entry; `stub_v15.S` additionally
  disables the BCM7405 SoC watchdog
- Entry point at `+0x508` per CCX app-header convention
- Initramfs with BusyBox, static IP, netconsole broadcast to `255.255.255.255:6666`
- Build runs in Docker (`build/Dockerfile`); script expects the repo at `/data`
  and uses `/build` as the work directory

### v20 kernel built (Linux 2.6.18, BCM7405 mipsel)
- **`hdf_work/vmlinux_v20.elf`** — 2.7 MB ELF, entry `0x802AC000`, loads at `0x800B0000`
- Load segments: `0x800b0000` (text) and `0x80290000` (data/bss); entry points at
  `kernel_entry` near `__init_begin` — i.e. at the **end** of the image, not at its start
- Compiled with: kexec, USB host/storage, FAT32; the raw variant prepends the
  self-relocating stub
- Purpose: load via JTAG `load_image` → Linux in RAM → `kexec` to any kernel from USB
- **`hdf_work/custom_kernel_v20.bin`** — raw binary (2.5 MB), stub + kernel
- The raw variant is packed with `stub_v14.S` (no SoC-watchdog kill). The JTAG/ELF
  path does **not** execute the stub at all, so this only matters for the abandoned
  flash path. `stub_v15.S` adds the watchdog kill and is kept for a future build.

### Flash kits v10–v19 (historical)
- `build/flash_kit/` contains the full experiment set: type-4 SysID probes,
  zero-blob kernels, real-blob and humidify variants, full-rootfs image
- Type-4 HDF block confirmed working on our Y5.06: SysID changed to arbitrary values
  and restored — loader processes type-4 without signature verification
- These kits are kept as evidence/reference only; **do not flash them**

### Y5.06 SysID confirmed: `0x80508400`
- `build/trigger_exact_sysid.hdf` (sysid_min=sysid_max=0x80508400) → flashed OK (P000→END)
- Y5.06 has no wildcard SysID path (FFFF/FFFF → E-ID, 0000/0000 → E-ID)
- Y4.11 wildcard path exists at `0x833917a0` but only in the Y4.11 loader

---

## Current Status

### Device bricked (2026-10-25)
Attempted to reflash the Y4.11 loader via USB HDF (`build/y411_loader_repacked.hdf`, SysID
patched to `0x00000000/0xFFFFFFFF`). Flashed 144/150 blocks (96%), then E-FE
(Flash Erase/Write error) on a bad NAND block. Result: partially-written Y4.11
loader — device cannot boot.
- MICOM alive (front-panel LED shows loading animation)
- BCM7405 ROM starts but Y4.11 crashes before UART init → UART silent
- JTAG confirmed enabled (FUSING INFO) → recoverable

### Recovery strategy (2026-10-26)
**Primary — JTAG + own loader, no NAND writes:**
1. Collect the Wemos D1 mini, flash `uart/esp8266_remote_bitbang/`, connect JTAG.
2. `openocd -f uart/openocd_bcm7405.cfg` → `halt` → verify TAP/IDCODE and CP0.
3. Load a small payload into DRAM and prove execution (memory marker or UART output).
4. Dump DRAM / boot ROM / whatever NAND is reachable through the CPU.
5. Build the custom loader: DRAM init, UART console, NAND read, USB host, Linux image
   load, jump to entry.
6. Boot `vmlinux_v20.elf` via JTAG → `kexec` to a kernel from USB.

**Fallback — restore NAND (later):** write a full known-good loader back to the CFE
NAND partition. This needs a complete NAND dump or a matching image and is postponed
until after JTAG bring-up; the current device has no full dump.

---

## Build

The v20 script is written for the Docker image in `build/Dockerfile`:

```bash
docker build --platform linux/amd64 -t humax-build build
docker run --rm -it --platform linux/amd64 -v "$PWD:/data" \
  humax-build /data/build/build_firmware_v20.sh
```

Outputs:

- `hdf_work/vmlinux_v20.elf` — load with JTAG (`load_image` + `resume 0x802AC000`)
- `hdf_work/custom_kernel_v20.bin` — stub + kernel, raw image for the flash path

Notes:
- The script has hard-coded `/build` and `/data` paths; run it only in the container.
- The kernel partition limit is 2 MB, but `MAX_KERNEL_SIZE` is still 4 000 000 in the
  script (legacy check). The current v20 kernel is 2.5 MB and is **not** flashed.
- On Apple Silicon the container runs under amd64 emulation; the build script retries
  the compiler on QEMU crashes.

---

## JTAG Setup (Wemos D1 mini)

Two-step process:

**Step 1 — find pins** (`uart/jtagenum/JTAGenum.ino`):
Flash to Wemos, connect D1/D2/D5/D6/D7 to the JTAG header on the Humax board,
open Serial @ 115200. Send `i` for IDCODE scan; expected BCM7405 response has bit 0 = 1.
Send `s` for full pattern scan. Note the reported TCK/TMS/TDI/TDO mapping.

**Step 2 — connect with OpenOCD** (`uart/esp8266_remote_bitbang/esp8266_remote_bitbang.ino`):
Fill in WiFi credentials and the pin mapping found in step 1. Flash. Run:

```bash
openocd -f uart/openocd_bcm7405.cfg
```

```
telnet localhost 4444
> halt
> mdw 0xBFC00000 4
> load_image hdf_work/vmlinux_v20.elf
> resume 0x802AC000
```

⚠️ Do **not** connect VCC from the Wemos to the board; use the STB's own 3.3 V.
Do not assume pin 1 is TCK/TMS — check it with JTAGenum first.

---

## Serial Dump (WDN4OAK) — deferred

The protocol and tool are ready, but the method is **not usable on the current brick**:
it needs the loader to enter Download Mode, and the loader is gone. Revisit it when
the custom loader or v20 kernel brings UART up.

Reference for later:
```bash
pip3 install pyserial
python3 tools/humax_serial_dump.py /dev/tty.usbserial-XXXX stb_cfe.bin
```
Connect CP2102: TX → STB RX, RX → STB TX, GND → GND. Power on the STB while holding
the front panel button to enter Download mode.

---

## Repository Structure

```
docs/
  HDF_FORMAT.md              — HDF binary format, byte-exact specification
  LOADER_FULL_AUDIT.md       — Y4.11 disassembly audit, boot chain, backdoors
  LOADER_Y411_RE.md          — Y4.11 RE notes: AES keys, MICOM, CCX conventions
  V10_EXPERIMENTS.md         — experiment log v10–v15
  MICOM_PROTOCOL_AND_WDN4OAK.md — MICOM UART3, serial protocol, LZRW1
  EXHAUSTIVE_ASSET_AUDIT.md  — inventory of every project asset
  claude-loader/analys.md    — latest loader analysis: blob-gate, boot gates, ROP notes

build/
  build_firmware_v20.sh      — current kernel build (Docker)
  stub_v14.S / stub_v15.S    — PIC relocating stubs (v15 adds SoC watchdog kill)
  hdf_packer.py              — HDF pack/unpack tool
  flash_kit/                 — historical flash kits v10–v19 (do not flash)

tools/
  humax_serial_dump.py       — WDN4OAK serial dump tool (deferred)
  wdn4oak/                   — WDN4OAK installer files (FV3Dll.dll, WDN4OAK.exe)
  humidify-ubuntu-1.0.4      — official HDF tool (run in Docker)

uart/
  jtagenum/                  — JTAGenum.ino for Wemos D1 mini — finds JTAG pin mapping
  esp8266_remote_bitbang/    — OpenOCD remote_bitbang bridge firmware for Wemos
  openocd_bcm7405.cfg        — OpenOCD config for BCM7405 MIPS EJTAG

firmwares/
  genuine/                   — stock firmware images (OnLime, PRIMACOM 5100C)
  ia_archive/                — Internet Archive finds (contains the Y4.11 loader)
  foxsat/                    — HD FOX T2 images (mipsel relative, custom fw works)

loaders/
  cfe_hdfoxt2.bin            — HD FOX T2 CFE (mipsel reference)
  cfe_foxsat_u754.bin        — FOXSAT-HDR U7.54 loader (big-endian reference)
  loader_from_hdfoxt2_type0.raw — loader extracted from HD FOX T2 HDF

hdf_work/
  loader_full.asm            — annotated Y4.11 full disassembly
  vmlinux_v20.elf            — JTAG-loadable kernel (entry 0x802AC000)
  custom_kernel_v20.bin      — raw stub+kernel image (flash path)
  foxt2_rootfs/              — extracted HD FOX T2 rootfs

kernel/stblinux-2.6.18-7.1/  — kernel source tree with our patches
```

The full 393 192-byte Y4.11 loader is at
`firmwares/ia_archive/extracted/FPXCCX10016_Y411/1.hdfbin-0-000000.raw`.

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
| **Humax HD FOX T2** | UK (Freeview DVB-T2) | BCM7405 mipsel. Active hummy.tv community with working custom firmware. Primary reference for HDF format, CFE/USB/NAND init, MICOM protocol. |
| **Humax HDR FOX T2** | UK (Freeview DVB-T2 PVR) | Same SoC as above. Rootfs fully extracted in this project; `humaxtv` binary used to reverse MICOM/ttyS2 protocol. |

The HD FOX T2 / HDR FOX T2 hummy.tv custom firmware (`nosettop` kernel cmdline arg,
`/etc/init.d` modifications) is the proven end-state we are replicating on the CXHD-5150C.

---

## Key Technical Notes

- The Y-loader **does not verify signatures at boot** — only during USB/OTA update
- The `origlen` field in block headers has no bounds check — potential overflow vector
- `keyidx` in block flags has no bounds check — out-of-bounds key selection
- MICOM watchdog is **not** a concern for a running Linux kernel unless the MICOM driver
  is absent; the boot cycle is caused solely by blob validation failure
- `nosettop` kernel command-line argument skips `humaxtv` and drops to console
  (confirmed on HD FOX T2; expected to work on CXHD-5150C)
- In v20 the kernel's `kernel_entry` is linked at the **end** of the image
  (`0x802AC000`), while the image start is zeros. A loader that jumps to the image
  base must either load the ELF and use its entry point, or place a trampoline
  `j kernel_entry` at offset 0.
- JTAG loading does not need the HDF container at all: `load_image` maps ELF segments,
  `resume` starts at the entry point. The custom loader can do the same from USB.

---

## Known Issues / TODO

- `build/build_firmware_v20.sh` still packs the raw image with `stub_v14.S` (no WDT
  kill) and prints a stale "Builder v8" banner. Harmless for the JTAG/ELF path; switch
  to `stub_v15.S` (or rebuild) if a flashable v20 image is ever needed.
- The kernel-size check in the script is 4 MB while the actual partition is 2 MB.
- `tools/humax_serial_dump.py` never ACKs the first received byte, which likely
  deadlocks the byte-by-byte protocol; fix before using the serial path again.
- No full NAND dump exists yet; the NAND restore fallback is blocked until JTAG can
  read it or a matching image is found.

---

## References

- BCM7405 BMIPS4380 MIPS32 architecture
- MIPS EJTAG specification v2.6+ (IR length 5)
- LZRW1 compression: Ross Williams, 1991 (public domain)
- JTAGenum: https://github.com/DenisovPlay/JTAGenum
- hummy.tv community research on HD FOX T2 / HDR FOX T2
- OpenOCD `remote_bitbang` driver
