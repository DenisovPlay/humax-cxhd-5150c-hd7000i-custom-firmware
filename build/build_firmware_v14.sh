#!/bin/bash
# ============================================================================
# Humax CXHD-5150C Custom Firmware Builder v14 (self-relocating stub)
#
# Отличия от v7 (которая дала E-AD) и v6 (прошилась, но не грузилась):
#   1. Ядро <= 2 МБ (партиция ядра = 0x100400..0x300000 = 2 МБ минус 0x400).
#      Ядро v6 было 4.1 МБ и обрезалось/заезжало на rootfs.
#   2. Адрес ядра снова 0x80100400 (как в v6). 0x80001000 (v7) = регион
#      бутлоадера во flash -> ошибка E-AD.
#   3. Включён код платформы Humax: -DHUMAX_PLATFORM_BASE -DHUMAX_PLATFORM_OCTO
#      (родная сборка: CONFIG_HUMAX_MODIFY=y, CONFIG_APPLICATION_OCTO=y).
#      В частности rac_setting(0)/l2_setting(0) для 7405B0.
#   4. Netconsole вшит в DEFAULT_KARGS/appendConsoleArg (prom.c), т.к. при
#      CONFIG_BLK_DEV_INITRD=y опция CONFIG_CMDLINE игнорируется.
#      Формат: netconsole=6666@192.168.1.99/eth0,6666@192.168.1.18/
#      (MAC приёмника не указан => broadcast, устойчиво к смене MAC у Mac).
#   5. Netconsole с повтором: если eth0 ещё не пробужден при module_init,
#      повтор на late_initcall.
#   6. Initramfs: udhcpc + статический фолбэк 192.168.1.99, telnetd,
#      UDP-маяки и полный dmesg на 192.168.1.18:6666, shell на консоли.
#
# Слушать на Mac:   nc -lu 6666
# ============================================================================
set -e

echo "=== Humax CXHD-5150C Custom Firmware Builder v8 ==="
echo ""

WORK=/build
CROSS_PREFIX=mipsel-linux-uclibc
MAC_IP=192.168.1.18          # Mac Андрея (сюда шлём netconsole/маяки)
STB_STATIC_IP=192.168.1.99   # статический IP приставки (фолбэк + src netconsole)

# Максимальный размер: партиция ядра 0x100400..0x300000 = 2 096 128 байт,
# небольшой запас. (Ядро в v6 было 4.1МБ и обрезалось/ломало rootfs.)
MAX_KERNEL_SIZE=2096000

# ---------------------------------------------------------------------------
# [1/8] Toolchain
# ---------------------------------------------------------------------------
echo "[1/8] Extracting crosstools..."
if [ ! -x /opt/toolchains/crosstools_hf-linux-2.6.18.0_gcc-4.2-11ts_uclibc-nptl-0.9.29-20070423_20090508/bin/${CROSS_PREFIX}-gcc ]; then
    cd /tmp
    cp /data/humax-gpl/sources/crosstools_hf-linux-2.6.18.0_gcc-4.2-11ts_uclibc-nptl-0.9.29-20070423_20090508.tar.bz2.bz2 ct.bz2
    bunzip2 -f ct.bz2
    mkdir -p /opt/toolchains
    tar xf ct -C /opt/toolchains
    rm -f ct
fi
CROSS_DIR=/opt/toolchains/crosstools_hf-linux-2.6.18.0_gcc-4.2-11ts_uclibc-nptl-0.9.29-20070423_20090508/bin
export PATH="${CROSS_DIR}:${PATH}"
echo "  CC: $(${CROSS_PREFIX}-gcc --version | head -1)"

# Код платформы Humax включается ПАТЧАМИ исходников (см. [5/8]), а не через
# EXTRA_CFLAGS: передача EXTRA_CFLAGS в командной строке make ломает
# "EXTRA_CFLAGS += -I ..." в суб-Makefile (arch/mips/brcmstb/lib не находит
# gcclib.h) — kbuild-ловушка 2.6.18.

# Старый kconfig (busybox 1.12 / ядро 2.6.18) требует TTY при вопросах о
# новых опциях: any pipe -> "aborted!". Оборачиваем в pty (см. oldconfig_pty.py).
oldconfig_tty() {
    python3 /data/build/oldconfig_pty.py "$@"
}

# ---------------------------------------------------------------------------
# [2/8] BusyBox (static, с telnetd/udhcpc/nc)
# ---------------------------------------------------------------------------
echo ""
echo "[2/8] Building BusyBox..."
mkdir -p $WORK
cd $WORK
if [ ! -f busybox-1.12.4/busybox ] || [ "${V8_FRESH_BB:-0}" = "1" ]; then
    rm -rf busybox-1.12.4
    gzip -dc < /data/humax-gpl/sources/busybox-1.12.4.tar.tar > /tmp/bb.tar 2>/dev/null || true
    tar xf /tmp/bb.tar
    rm -f /tmp/bb.tar
    cd busybox-1.12.4
    # старый uclibc-ld падает на '-lcrypt -lm' вместе с --gc-sections
    sed -i 's/-Wl,--gc-sections//g' Makefile scripts/trylink
    # Тощий busybox: allnoconfig + ~43 опции (initramfs 423K -> ~170K gz)
    make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- allnoconfig > /dev/null 2>&1
    python3 - <<'BBEOF'
import re
apps = ["STATIC", "ASH", "FEATURE_SH_IS_ASH", "ASH_JOB_CONTROL",
        "MOUNT", "MKDIR", "MKNOD", "CHMOD",
        "CAT", "ECHO", "LS", "CP", "RM",
        "GREP", "SED", "CUT",
        "UNAME", "DMESG", "PS", "KILL", "SLEEP",
        "IFCONFIG", "ROUTE", "PING", "NC", "TELNETD", "UDHCPC",
        "ENV"]
names = set(apps)
def strip_line(l):
    s = l.strip()
    if s.startswith("#") and " is not set" in s:
        return s[len("# CONFIG_"):-len(" is not set")]
    m = re.match(r"^CONFIG_([A-Z0-9_]+)=", s)
    return m.group(1) if m else None
lines = open(".config").readlines()
out = [l for l in lines if strip_line(l) not in names]
for a in apps:
    out.append("CONFIG_%s=y\n" % a)
open(".config", "w").writelines(out)
BBEOF
    oldconfig_tty make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- oldconfig > /dev/null 2>&1
    # зафиксировать конфиг последовательно (гонка silentoldconfig при -j ломает .config)
    make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- silentoldconfig < /dev/null > /dev/null 2>&1 || \
        oldconfig_tty make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- oldconfig > /dev/null 2>&1
    make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- -j1 prepare > /dev/null 2>&1 || true
    if [ "$(grep -c '=y' .config)" -lt 25 ]; then
        echo "ERROR: busybox .config неполный ($(grep -c '=y' .config) опций) — oldconfig не отработал"
        exit 1
    fi
    make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- -j$(nproc) > /tmp/bb_build.log 2>&1 || { tail -30 /tmp/bb_build.log; exit 1; }
fi
BB=$WORK/busybox-1.12.4/busybox
[ -f "$BB" ] || { echo "ERROR: busybox missing"; exit 1; }
echo "  BusyBox: $(ls -lh $BB | awk '{print $5}') $(file $BB | grep -o 'statically linked\|dynamically linked' | head -1)"

# ---------------------------------------------------------------------------
# [3/8] Rootfs для initramfs
# ---------------------------------------------------------------------------
echo ""
echo "[3/8] Creating initramfs rootfs..."
ROMFS=$WORK/romfs_v8
rm -rf $ROMFS
mkdir -p $ROMFS/{bin,sbin,etc,proc,sys,dev,tmp,var,var/run,var/log,usr,usr/bin,usr/sbin,mnt,root}

BB_INSTALL_OK=0
for i in $(seq 1 8); do
    if make -C $WORK/busybox-1.12.4 ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- CONFIG_PREFIX=$ROMFS install > /tmp/bb_install.log 2>&1; then
        BB_INSTALL_OK=1
        break
    fi
    grep -qE "Segmentation fault|Error 139|Error 127" /tmp/bb_install.log || break
    sleep 2
done
if [ "$BB_INSTALL_OK" != "1" ]; then
    echo "ERROR: busybox make install failed:"; tail -15 /tmp/bb_install.log; exit 1
fi
cp $BB $ROMFS/bin/busybox
chmod 755 $ROMFS/bin/busybox

# device nodes: /dev/console нужен ДО запуска /init; mdev выброшен для размера
mknod -m 600 $ROMFS/dev/console c 5 1 2>/dev/null || true
mknod -m 666 $ROMFS/dev/null    c 1 3 2>/dev/null || true
mknod -m 666 $ROMFS/dev/zero    c 1 5 2>/dev/null || true
mknod -m 666 $ROMFS/dev/ptmx    c 5 2 2>/dev/null || true
mknod -m 644 $ROMFS/dev/ttyS0   c 4 64 2>/dev/null || true
mknod -m 666 $ROMFS/dev/tty     c 5 0 2>/dev/null || true

cat > $ROMFS/etc/passwd << 'EOF'
root::0:0:root:/root:/bin/sh
EOF
echo "root:x:0:" > $ROMFS/etc/group
echo "humax" > $ROMFS/etc/hostname
printf '127.0.0.1\tlocalhost\n' > $ROMFS/etc/hosts
cat > $ROMFS/etc/profile << 'EOF'
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
export PS1='humax-v8# '
alias ll='ls -la'
EOF

cat > $ROMFS/etc/udhcpc.script << 'DHCP'
#!/bin/sh
case "$1" in
    bound|renew)
        ifconfig $interface $ip netmask ${subnet:-255.255.255.0} up
        [ -n "$router" ] && route add default gw $router dev $interface 2>/dev/null
        [ -n "$dns" ] && echo "nameserver $dns" > /etc/resolv.conf
        echo "udhcpc: got $ip on $interface"
        ;;
    deconfig)
        ifconfig $interface 0.0.0.0 up
        ;;
esac
DHCP
chmod +x $ROMFS/etc/udhcpc.script

cat > $ROMFS/init << INIT
#!/bin/sh
# HUMAX CXHD-5150C custom firmware v8
export PATH=/bin:/sbin:/usr/bin:/usr/sbin

mount -t proc proc /proc 2>/dev/null
mount -t sysfs sysfs /sys 2>/dev/null
mount -t ramfs ramfs /tmp 2>/dev/null
mount -t ramfs ramfs /var 2>/dev/null
mkdir -p /var/run /var/log /dev/pts /var/tmp
mount -t devpts devpts /dev/pts 2>/dev/null

echo ""
echo "***********************************************"
echo " HUMAX CXHD-5150C custom firmware v8 BOOTED"
echo " \$(uname -a)"
echo "***********************************************"

ifconfig lo 127.0.0.1 netmask 255.0.0.0 up 2>/dev/null
ifconfig eth0 up 2>/dev/null

# DHCP; при неудаче - статика
if ! udhcpc -i eth0 -s /etc/udhcpc.script -t 6 -T 3 -n -q >/dev/null 2>&1; then
    ifconfig eth0 ${STB_STATIC_IP} netmask 255.255.255.0 up 2>/dev/null
    route add default gw 192.168.1.1 2>/dev/null
    echo "net: static ${STB_STATIC_IP}"
fi

IP=\$(ifconfig eth0 2>/dev/null | grep 'inet addr' | head -1 | sed 's/.*addr:\([0-9.]*\).*/\1/')
echo "net: eth0 = \${IP:-none}"

# Полный dmesg на Mac одним UDP-пакетом-потоком
( sleep 2; dmesg | nc -u -w 5 ${MAC_IP} 6666 2>/dev/null ) &

# Живые маяки раз в 15 секунд
( while :; do
    echo "v8-ALIVE ip=\${IP:-?} uptime=\$(cut -d. -f1 /proc/uptime)s" | nc -u -w 1 ${MAC_IP} 6666 2>/dev/null
    sleep 15
  done ) &

# telnet-сервер (root без пароля)
telnetd -l /bin/sh 2>/dev/null && echo "telnetd: started on :23" || echo "telnetd: FAILED"

echo "=== ready: telnet \${IP:-${STB_STATIC_IP}} ==="

# Вечный shell на консоли (не даём init умереть)
while :; do
    /bin/sh </dev/console >/dev/console 2>&1
    sleep 2
done
INIT
chmod +x $ROMFS/init

echo "  romfs: $(du -sh $ROMFS | awk '{print $1}')"

# ---------------------------------------------------------------------------
# [4/8] Initramfs cpio
# ---------------------------------------------------------------------------
echo ""
echo "[4/8] Creating initramfs.cpio.gz..."
IR_OK=0
for i in $(seq 1 6); do
    cd $ROMFS
    find . -print0 | cpio --null -o -H newc 2>/dev/null | gzip -9 > $WORK/initramfs.cpio.gz
    ISIZE=$(stat -c%s $WORK/initramfs.cpio.gz 2>/dev/null || echo 0)
    [ "$ISIZE" -gt 100000 ] && { IR_OK=1; break; }
    echo "  attempt $i: cpio.gz=$ISIZE bytes (crash?), retrying..."
    sleep 2
done
[ "$IR_OK" = "1" ] || { echo "ERROR: initramfs too small ($ISIZE)"; exit 1; }
echo "  initramfs.cpio.gz: $ISIZE bytes"

# ---------------------------------------------------------------------------
# [5/8] Kernel source + патчи
# ---------------------------------------------------------------------------
echo ""
echo "[5/8] Preparing kernel source + patches..."
cd $WORK
if [ ! -d linux-src ] || [ "${V8_FRESH_KERNEL:-0}" = "1" ]; then
    [ -d linux-src ] && touch linux-src/.dirty
    rm -rf linux-src
    cp -a /data/kernel/stblinux-2.6.18-7.1 linux-src
    chmod -R u+w linux-src
fi
cd linux-src

# --- V11: ядро линкуется на 0x800B0000 — адрес, куда Y-лоадер грузит app-стрим ---
sed -i 's/^load-$(CONFIG_MIPS_BCM7405) := 0x80001000/load-$(CONFIG_MIPS_BCM7405) := 0x800B0000/' arch/mips/Makefile
grep -n 'load-$(CONFIG_MIPS_BCM7405)' arch/mips/Makefile | head -2

# --- Патч v13: ENTRY-STROBE в head.S (base64, без экранирования) ---
echo CmltcG9ydCByZSwgc3lzCmhzID0gImFyY2gvbWlwcy9rZXJuZWwvaGVhZC5TIgpzID0gb3BlbihocykucmVhZCgpCmlmICJWMTMgRU5UUlkgU1RST0JFIiBpbiBzOgogICAgcHJpbnQoIiAgaGVhZC5TOiBhbHJlYWR5IHBhdGNoZWQiKTsgc3lzLmV4aXQoMCkKbWFya2VyID0gIk5FU1RFRChrZXJuZWxfZW50cnksIDE2LCBzcCkiCmkgPSBzLmZpbmQobWFya2VyKQphc3NlcnQgaSA+PSAwLCAia2VybmVsX2VudHJ5IG5vdCBmb3VuZCIKbGluZV9lbmQgPSBzLmZpbmQoIlxuIiwgaSkgKyAxCnN0cm9iZSA9ICgKIlxuXHQjID09PSBWMTMgRU5UUlkgU1RST0JFOiB1bmNhY2hlZCBmaWxsIDB4YTY4MDAwMDAuLjB4YTc4MDAwMDAsIDEwIHBoYXNlcyA9PT1cbiIKIlx0LnNldCBwdXNoXG5cdC5zZXQgbm9yZW9yZGVyXG5cdC5zZXQgbm9hdFxuIgoiXHRsaVx0dDAsIDB4YTY4MDAwMDBcbiIKIlx0bGlcdHQzLCAxMFxuIgoiX3YxM19waGFzZTpcbiIKIlx0YW5kaVx0dDcsIHQzLCAxXG4iCiJcdGJlcXpcdHQ3LCBfdjEzX2JsYWNrXG4iCiJcdCBsaVx0dDEsIDB4MDBmZmZmZmZcbiIKIlx0bGlcdHQxLCAweDAwMDAwMDAwXG4iCiJfdjEzX2JsYWNrOlxuIgoiXHRtb3ZlXHR0MiwgdDBcbiIKIlx0bGlcdHQ0LCAweDQwMDAwMFxuIgoiX3YxM19maWxsOlxuIgoiXHRzd1x0dDEsIDAodDIpXG4iCiJcdGFkZGl1XHR0MiwgNFxuIgoiXHRhZGRpdVx0dDQsIC0xXG4iCiJcdGJuZXpcdHQ0LCBfdjEzX2ZpbGxcbiIKIlx0IG5vcFxuIgoiXHRsaVx0dDUsIDgwMDAwMFxuIgoiX3YxM19kZWxheTE6XG4iCiJcdGxpXHR0NiwgNTBcbiIKIl92MTNfZGVsYXkyOlxuIgoiXHRibmV6XHR0NiwgX3YxM19kZWxheTJcbiIKIlx0IGFkZGl1XHR0NiwgLTFcbiIKIlx0YWRkaXVcdHQ1LCAtMVxuIgoiXHRibmV6XHR0NSwgX3YxM19kZWxheTFcbiIKIlx0IG5vcFxuIgoiXHRhZGRpdVx0dDMsIC0xXG4iCiJcdGJuZXpcdHQzLCBfdjEzX3BoYXNlXG4iCiJcdCBub3BcbiIKIlx0LnNldCBwb3BcblxuIikKcyA9IHNbOmxpbmVfZW5kXSArIHN0cm9iZSArIHNbbGluZV9lbmQ6XQpvcGVuKGhzLCAidyIpLndyaXRlKHMpCnByaW50KCIgIGhlYWQuUzogZW50cnkgc3Ryb2JlIGluc2VydGVkIGFmdGVyIGtlcm5lbF9lbnRyeSIpCg== | base64 -d > /tmp/hs_patch.py
python3 /tmp/hs_patch.py || exit 1


python3 - <<'PYEOF'
import sys

def patch(path, old, new, name):
    with open(path) as f:
        s = f.read()
    if new in s:
        print("  %s: already patched" % name)
        return
    if old not in s:
        print("  ERROR: %s: pattern not found!" % name)
        sys.exit(1)
    s = s.replace(old, new, 1)
    with open(path, "w") as f:
        f.write(s)
    print("  %s: patched" % name)

# --- Патч 4 (ОТКАЗАЛСЯ): math-emu выключить нельзя - trap.c жёстко
#     ссылается на fpu_emulator_save/restore_context. Оставляем obj-y.

# --- Патч 1: prom.c — netconsole в DEFAULT_KARGS и appendConsoleArg ---
prom = "arch/mips/brcmstb/common/prom.c"
with open(prom) as f:
    _s = f.read()
if "NETCON_KARGS" in _s:
    print("  prom.c: already patched (NETCON_KARGS present)")
else:
    patch(prom,
'''#define RW_KARGS " rw"
#define DEFAULT_KARGS CONSOLE_KARGS RW_KARGS''',
'''#define RW_KARGS " rw"
#define NETCON_KARGS " netconsole=6666@__STB_IP__/eth0,6666@__MAC_IP__/"
#define DEFAULT_KARGS CONSOLE_KARGS RW_KARGS NETCON_KARGS''',
"prom.c DEFAULT_KARGS+netconsole")

patch(prom,
'''	pConsole = strstr(cmdArg, "console=");
	if (!pConsole) {
		if ((strlen(cmdArg) + strlen(CONSOLE_KARGS)) < COMMAND_LINE_SIZE) {
			strcat(cmdArg, CONSOLE_KARGS);
		}
		else {
			uart_puts("***** WARNINGS: No console= appended to kernel args: args is too long");
		}
	}
	
	return;''',
'''	pConsole = strstr(cmdArg, "console=");
	if (!pConsole) {
		if ((strlen(cmdArg) + strlen(CONSOLE_KARGS)) < COMMAND_LINE_SIZE) {
			strcat(cmdArg, CONSOLE_KARGS);
		}
		else {
			uart_puts("***** WARNINGS: No console= appended to kernel args: args is too long");
		}
	}

	if (!strstr(cmdArg, "netconsole=")) {
		if ((strlen(cmdArg) + strlen(NETCON_KARGS)) < COMMAND_LINE_SIZE) {
			strcat(cmdArg, NETCON_KARGS);
		}
	}

	return;''',
"prom.c appendConsoleArg+netconsole")

# --- Патч 0: включаем код платформы Humax (аналог -DHUMAX_PLATFORM_BASE /
#     -DHUMAX_PLATFORM_OCTO из родной сборки CONFIG_HUMAX_MODIFY=y,
#     CONFIG_APPLICATION_OCTO=y; см. cfg_extract/config/stblinux-2.6.18-7.1.config)
def enable_humax(path):
    with open(path) as f:
        s = f.read()
    orig = s
    s = s.replace("#if defined(HUMAX_PLATFORM_BASE) && defined(CONFIG_MIPS_BCM7405B0)",
                  "#if defined(CONFIG_MIPS_BCM7405B0)")
    s = s.replace("#if defined(HUMAX_PLATFORM_BASE) && defined(CONFIG_MIPS_BCM7325)",
                  "#if defined(CONFIG_MIPS_BCM7325)")
    s = s.replace("#if defined(HUMAX_PLATFORM_BASE) ", "#if 1 /*HUMAX*/")
    s = s.replace("#if defined(HUMAX_PLATFORM_BASE)", "#if 1 /*HUMAX*/")
    s = s.replace("#if defined(HUMAX_PLATFORM_OCTO)", "#if 1 /*HUMAX*/")
    if s != orig:
        with open(path, "w") as f:
            f.write(s)
        print("  %s: HUMAX platform code enabled" % path)
    else:
        print("  %s: no HUMAX ifdefs (ok)" % path)

for _f in ["arch/mips/brcmstb/common/prom.c",
           "arch/mips/brcmstb/common/rac.c",
           "arch/mips/brcmstb/common/brcm-pm.c",
           "arch/mips/brcmstb/brcm97405b0/board.c",
           "arch/mips/mm/c-r4k.c",
           "arch/mips/kernel/smtc.c"]:
    enable_humax(_f)

# --- Патч 3: boardmap.h — у Humax BRCM_FLASH_SIZE = CONFIG_MTD_PHYSMAP_LEN
#     (символ недоступен без MTD_CFI/JEDECPROBE/ROM). Хардкодим их дефолт 64 МБ.
_bm = "include/asm-mips/brcmstb/brcm97405b0/boardmap.h"
with open(_bm) as f:
    _lines = f.readlines()
_out, _done = [], 0
for _l in _lines:
    if "#if defined(HUMAX_PLATFORM_OCTO)" in _l:
        _out.append("#if 1 /* humax octo */\n"); _done += 1
    elif "CONFIG_MTD_PHYSMAP_LEN" in _l:
        _out.append("#define BRCM_FLASH_SIZE             0x04000000 /* 64MB humax default */\n"); _done += 1
    else:
        _out.append(_l)
if _done == 2:
    with open(_bm, "w") as f:
        f.writelines(_out)
    print("  boardmap.h: flash size hardcoded 64MB (humax default)")
elif "64MB humax default" in "".join(_lines):
    print("  boardmap.h: already patched")
else:
    print("  ERROR: boardmap.h: expected 2 lines, touched %d" % _done)
    sys.exit(1)

# --- Патч 2: netconsole.c — повторная попытка на late_initcall ---
patch("drivers/net/netconsole.c",
'''	if(netpoll_setup(&np))
		return -EINVAL;

	register_console(&netconsole);
	printk(KERN_INFO "netconsole: network logging started\\n");
	return 0;
}''',
'''	if(netpoll_setup(&np)) {
		printk(KERN_ERR "netconsole: netpoll_setup failed, will retry later\\n");
		return 0;
	}

	register_console(&netconsole);
	printk(KERN_INFO "netconsole: network logging started\\n");
	return 0;
}

static int late_init_netconsole(void)
{
	if(np.dev)
		return 0;
	if(!configured)
		return 0;
	if(netpoll_setup(&np)) {
		printk(KERN_ERR "netconsole: late retry failed\\n");
		return 0;
	}
	register_console(&netconsole);
	printk(KERN_INFO "netconsole: network logging started (late)\\n");
	return 0;
}
late_initcall(late_init_netconsole);''',
"netconsole.c late retry")
PYEOF

# Подставляем реальные IP в prom.c
sed -i "s/__MAC_IP__/${MAC_IP}/; s/__STB_IP__/${STB_STATIC_IP}/" arch/mips/brcmstb/common/prom.c
grep -n "NETCON_KARGS" arch/mips/brcmstb/common/prom.c | head -3

# --- Патч v11: FULL-SCREEN STROBE (late_initcall, до initramfs) ---
cat >> arch/mips/brcmstb/common/prom.c << 'V11EOF'

/* === V11: full-screen strobe beacon === */
#include <linux/delay.h>
static int __init v11_strobe(void)
{
	void __iomem *p;
	unsigned long a;
	int n;
	uart_puts("v11-strobe: start (kernel linked @0x800B0000)\n");
	for (n = 0; n < 30; n++) {
		for (a = 0x86800000; a < 0x88000000; a += 0x100000) {
			p = ioremap_nocache(a, 0x100000);
			if (p) {
				memset_io(p, (n & 1) ? 0xFF : 0x00, 0x100000);
				iounmap(p);
			}
		}
		uart_puts(n & 1 ? "v11:W\n" : "v11:B\n");
		mdelay(1200);
	}
	uart_puts("v11-strobe: done\n");
	return 0;
}
late_initcall(v11_strobe);
V11EOF
echo "  prom.c: v11 strobe appended"

# ---------------------------------------------------------------------------
# [6/8] Kernel config
# ---------------------------------------------------------------------------
echo ""
echo "[6/8] Configuring kernel..."
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- bcm97405b0-nand_defconfig > /dev/null 2>&1

# kconfig берёт ПЕРВОЕ вхождение символа в .config, поэтому append дубликатов
# не работает — сеттер удаляет старые строки и добавляет новые в конец.
python3 - <<'CFGEOF'
path = ".config"
with open(path) as f:
    lines = f.readlines()

# (symbol, value): value=None -> "# CONFIG_X is not set"
settings = [
    # --- v8 additions ---
    ("BLK_DEV_INITRD", "y"),
    ("INITRAMFS_SOURCE", '"/build/initramfs.cpio.gz"'),
    ("NETCONSOLE", "y"),
    ("MAGIC_SYSRQ", "y"),
    ("CC_OPTIMIZE_FOR_SIZE", "y"),
    # USB HID (мышь) вернём в v9, когда докажем загрузку
    ("HID", None),
    ("INPUT_EVDEV", None),
    ("INPUT_MOUSEDEV", None),
    # --- урезаем ради размера (ядро+initramfs <= 1.99 МБ) ---
    ("USB", None),            # весь USB-стек ~250КБ (не нужен для вывода)
    ("MODULES", None),        # загрузчик модулей не нужен
    ("KALLSYMS", None),       # символы декодируем оффлайн по vmlinux
    ("MIPS_FPU_EMULATOR", None),
    ("INET_DIAG", None),
    ("TCP_DIAG", None),
    ("NET_WIRELESS_RTNETLINK", None),
    ("SWAP", None),
    ("IP_MULTICAST", None),
    ("IKCONFIG", None),
    ("IKCONFIG_PROC", None),
    ("EXT2_FS", None),
    ("JFFS2_FS", None),       # дампы flash разберём оффлайн
    ("SYSVIPC", None),
    ("UDF_FS", None),
    ("ISO9660_FS", None),
    ("FAT_FS", None),
    ("MSDOS_FS", None),
    ("VFAT_FS", None),
    ("NTFS_FS", None),
    ("INOTIFY", None),
    ("INOTIFY_USER", None),
    ("IP_PNP", None),
    ("IP_PNP_DHCP", None),
    ("IP_PNP_BOOTP", None),
    ("IP_PNP_RARP", None),
    ("EPOLL", None),
    ("EMBEDDED", "y"),
    ("BASE_FULL", None),
    ("NET_KEY", None),
    ("IP_ADVANCED_ROUTER", None),
    ("IP_MULTIPLE_TABLES", None),
    ("INET_TUNNEL", None),
    ("TMPFS", None),
    ("ZLIB_DEFLATE", None),  # initramfs только распаковываем (inflate)
    ("FW_LOADER", None),
    ("PROC_SYSCTL", None),
    ("SYSCTL_SYSCALL", None),
    ("BCMINTEMAC_NETLINK", None),
    ("MTD_BLOCK_ROMBLOCK", None),
    ("ELF_CORE", None),
    ("LEGACY_PTYS", None),
    ("BLOCK", None),          # block layer не нужен: initramfs + /dev/mtdN
    ("MTD_BLOCK", None),
    ("SATA_SVW", None),
    ("ATA", None),            # иначе ATA=y select-ит SCSI
    ("USB_STORAGE", None),    # m тоже select-ит SCSI
    ("SCSI", None),
    ("BLK_DEV_SD", None),
    ("NFS_FS", None),
    ("NFSD", None),           # NFSD тянет LOCKD/SUNRPC/NFS-стек
    ("EXT3_FS", None),
    ("YAFFS_FS", None),       # 130КБ, NAND-фс не нужен (rootfs jffs2)
    ("USB_USBNET", None),
    ("USB_RTL8150", None),
    ("USB_PEGASUS", None),
    ("USB_MON", None),
    ("BRIDGE", None),
    ("BLK_DEV_LOOP", None),
    ("CRAMFS", None),
    ("SQUASHFS", None),
    ("PCI", None),
    ("BRCM_COMMON_PCI", None),
    ("BRCM_PM", None),
    ("WIRELESS_EXT", None),
    ("IPV6", None),
    ("SOUND", None),
    ("XFRM_USER", None),
    ("INET_XFRM_MODE_TRANSPORT", None),
    ("INET_XFRM_MODE_TUNNEL", None),
]

import re
def strip_line(l):
    s = l.strip()
    if s.startswith("#") and " is not set" in s:
        return s[len("# CONFIG_"):-len(" is not set")]
    m = re.match(r"^CONFIG_([A-Z0-9_]+)=", s)
    return m.group(1) if m else None

symset = {s for s, _ in settings}
out = []
for l in lines:
    name = strip_line(l)
    if name in symset:
        continue
    out.append(l)

for s, v in settings:
    if v is None:
        out.append("# CONFIG_%s is not set\n" % s)
    else:
        out.append("CONFIG_%s=%s\n" % (s, v))

with open(path, "w") as f:
    f.writelines(out)
print("  config setter: %d symbols updated" % len(settings))
CFGEOF

oldconfig_tty make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- oldconfig > /dev/null 2>&1
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- silentoldconfig < /dev/null > /dev/null 2>&1 || true

echo "  Key configs:"
grep -E "^CONFIG_(MIPS_BCM7405BX_NAND|BLK_DEV_INITRD|INITRAMFS_SOURCE|NETCONSOLE|CC_OPTIMIZE_FOR_SIZE|MTD_BRCMNAND|SERIAL_8250_CONSOLE)" .config
if ! grep -q '^CONFIG_INITRAMFS_SOURCE="/build' .config || ! grep -q "^CONFIG_NETCONSOLE=y" .config; then
    echo "ERROR: ключевые опции не применились (INITRAMFS_SOURCE/NETCONSOLE)"
    exit 1
fi

# ---------------------------------------------------------------------------
# [7/8] Build
# ---------------------------------------------------------------------------
echo ""
echo "[7/8] Building kernel (few minutes; с ретраями — qemu иногда роняет 32-битный cc)..."
KOK=0
for i in $(seq 1 15); do
    if make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- -j2 vmlinux > /tmp/kernel_build.log 2>&1; then
        KOK=1
        echo "  kernel build OK (attempt $i)"
        break
    fi
    if grep -qE "Segmentation fault|Error 139|Error 4|internal compiler error" /tmp/kernel_build.log; then
        echo "  attempt $i: compiler crash under qemu, retrying..."
        sleep 2
    else
        echo "BUILD FAILED (non-transient), tail:"
        tail -40 /tmp/kernel_build.log
        exit 1
    fi
done
[ "$KOK" = "1" ] || { echo "BUILD FAILED: too many compiler crashes"; tail -20 /tmp/kernel_build.log; exit 1; }

[ -f vmlinux ] || { echo "ERROR: no vmlinux"; exit 1; }

echo "  Проверка HUMAX-кода:"
HUMAX_OK=1
for f in arch/mips/brcmstb/common/prom.c arch/mips/brcmstb/common/rac.c arch/mips/brcmstb/brcm97405b0/board.c; do
    grep -q "/\*HUMAX\*/" $f || { echo "    $f: патч отсутствует!"; HUMAX_OK=0; }
done
[ "$HUMAX_OK" = "1" ] && echo "    OK: HUMAX_PLATFORM код включён (#if 1 /*HUMAX*/)"

${CROSS_PREFIX}-objcopy -O binary vmlinux vmlinux.bin
KSIZE=$(stat -c%s vmlinux.bin)
echo "  vmlinux:     $(ls -lh vmlinux | awk '{print $5}')"
echo "  vmlinux.bin: $KSIZE bytes"

ENTRY=$(${CROSS_PREFIX}-readelf -h vmlinux | grep "Entry point" | awk '{print $NF}')
LOAD=$(${CROSS_PREFIX}-readelf -lW vmlinux | grep "LOAD" | head -1 | awk '{print $3}')
echo "  entry=$ENTRY load=$LOAD"

# ВАЖНО (главная причина неработоспособности v6): в этом дереве kernel_entry
# слинкован в КОНЦЕ образа (__init_begin), начало образа (offset 0..0x400) -
# нули. Бутлоадер прыгает на начало загруженного образа -> мгновенный краш.
# Трамплин на offset 0: j kernel_entry (регистры CFE не трогаем).
ENTRY_DEC=$(printf "%d" $ENTRY)
INSTR=$((0x08000000 | ((ENTRY_DEC >> 2) & 0x03FFFFFF)))
printf "  trampoline: j 0x%08x = 0x%08x\n" $ENTRY_DEC $INSTR
B0=$((INSTR & 0xFF)); B1=$(((INSTR >> 8) & 0xFF)); B2=$(((INSTR >> 16) & 0xFF)); B3=$(((INSTR >> 24) & 0xFF))
printf "\\x$(printf '%02x' $B0)\\x$(printf '%02x' $B1)\\x$(printf '%02x' $B2)\\x$(printf '%02x' $B3)\\x00\\x00\\x00\\x00" > /tmp/trampoline.bin
cp vmlinux.bin vmlinux_patched.bin
dd if=/tmp/trampoline.bin of=vmlinux_patched.bin bs=1 count=8 conv=notrunc 2>/dev/null
echo "  первые 8 байт образа (трамплин): $(od -A n -t x1 -N 8 vmlinux_patched.bin)"
cp vmlinux_patched.bin vmlinux.bin

if [ "$KSIZE" -gt "$MAX_KERNEL_SIZE" ]; then
    echo ""
    echo "  !!! ЯДРО СЛИШКОМ БОЛЬШОЕ: $KSIZE > $MAX_KERNEL_SIZE"
    echo "  !!! Нужно урезать конфиг (см. /tmp/kernel_build.log, разделы)."
    ls -lh usr/initramfs_data.cpio.gz 2>/dev/null
    exit 2
fi

echo "  initramfs embedded: $(ls -lh usr/initramfs_data.cpio.gz 2>/dev/null | awk '{print $5}')"
${CROSS_PREFIX}-strings vmlinux | grep -c "v8-ALIVE" | xargs -I{} echo "  v8 init strings in kernel: {}"

# ---------------------------------------------------------------------------
# [8/8] HDF
# ---------------------------------------------------------------------------
echo ""
echo "[8/8] Packing HDF..."
# ═══ V14: само-переносящийся образ ═══
# stub собираем кросс-ассемблером, клеим [stub 0x600][vmlinux.bin],
# патчим SIZE (0x12345678) и ENTRY (0x21436587).
cp /data/build/stub_v14.S .
${CROSS_PREFIX}-as -march=mips32 -EL -o stub.o stub_v14.S || exit 1
${CROSS_PREFIX}-objcopy -O binary stub.o stub.bin || exit 1
SSTUB=$(stat -c%s stub.bin)
echo "  stub.bin: $SSTUB bytes (ожидаем 0x600=1536)"
[ "$SSTUB" -eq 1312 ] || { echo "ERROR: stub size $SSTUB != 1312 (0x520)"; exit 1; }

KSIZE=$(stat -c%s vmlinux.bin)
ENTRY=$(${CROSS_PREFIX}-readelf -h vmlinux | grep "Entry point" | awk '{print $NF}')
echo "  kernel: $KSIZE bytes, entry=$ENTRY"
echo -n "$ENTRY" > /tmp/entry.txt

python3 - <<'PEOF'
import struct
stub = bytearray(open("stub.bin","rb").read())
kern = open("vmlinux.bin","rb").read()
SIZE = 0x520 + len(kern)
ENTRY = int(open("/tmp/entry.txt").read().strip(), 16)

def patch_li(buf, marker_val, new_val, name):
    hi_o = (marker_val >> 16) & 0xFFFF
    lo_o = marker_val & 0xFFFF
    for off in range(0, len(buf) - 8, 4):
        w1 = int.from_bytes(buf[off:off+4], "little")
        w2 = int.from_bytes(buf[off+4:off+8], "little")
        if (w1 >> 26) == 0x0F and (w1 & 0xFFFF) == hi_o and (w2 >> 26) == 0x0D and (w2 & 0xFFFF) == lo_o:
            nh = (new_val >> 16) & 0xFFFF
            nl = new_val & 0xFFFF
            buf[off:off+4] = struct.pack("<I", (w1 & 0xFFFF0000) | nh)
            buf[off+4:off+8] = struct.pack("<I", (w2 & 0xFFFF0000) | nl)
            print("  patched %s @ stub+%#x: %#x -> %#x" % (name, off, marker_val, new_val))
            return
    raise SystemExit("ERROR: marker %s (%#x) not found" % (name, marker_val))

patch_li(stub, 0x12345678, SIZE, "SIZE")
patch_li(stub, 0x21436587, ENTRY, "ENTRY")
# фикс входных bal (старый as кодирует их криво через .org): bal 0x200 с PC=0 и PC=8
import struct as _s
stub[0:4]   = _s.pack("<I", 0x0411007F)   # bal 0x200 @0x000
stub[8:12]  = _s.pack("<I", 0x0411007D)   # bal 0x200 @0x008
print("  entry bals fixed (0x000/0x008 -> 0x200)")
image = bytes(stub) + kern
open("vmlinux_patched.bin","wb").write(image)
print("  v14 image: %d bytes (stub 0x520 + kern %d)" % (len(image), len(kern)))
PEOF

cp vmlinux_patched.bin /data/hdf_work/custom_kernel_v14.raw
cd /data/hdf_work
echo "  (упаковку делает хост, форма d2b)"

echo ""
echo "=== HDF structure ==="

echo ""
echo "=== BUILD COMPLETE ==="
ls -lh /data/hdf_work/custom_kernel_v14.raw
echo ""
echo "Ядро: $KSIZE байт (лимит $MAX_KERNEL_SIZE)"
echo "На флешку: cp custom_firmware_v8.hdf /Volumes/UNTITLED/cxhd_5150c_upgrade.hdf"
echo "Прошивка: CH- на передней панели + включение питания, ждать P000..P100..END"
echo "Слушать на Mac: nc -lu 6666   (netconsole + маяки + dmesg)"
