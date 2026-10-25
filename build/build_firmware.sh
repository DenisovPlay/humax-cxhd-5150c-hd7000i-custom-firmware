#!/bin/bash
set -e

echo "=== Humax CXHD-5150C Custom Firmware Builder ==="
echo ""

WORK=/build
CROSS_PREFIX=mipsel-linux-uclibc
CROSS_DIR=""

# Step 1: Extract crosstools
echo "[1/6] Extracting crosstools..."
if [ ! -d /opt/toolchains ]; then
    cd /tmp
    cp /data/humax-gpl/sources/crosstools_hf-linux-2.6.18.0_gcc-4.2-11ts_uclibc-nptl-0.9.29-20070423_20090508.tar.bz2.bz2 ct.bz2
    bunzip2 -f ct.bz2
    mkdir -p /opt/toolchains
    tar xf ct -C /opt/toolchains
    rm -f ct
    echo "  Crosstools extracted."
else
    echo "  Crosstools already extracted."
fi

# Find the compiler
CROSS_CC=$(find /opt/toolchains -name "${CROSS_PREFIX}-gcc" -type f 2>/dev/null | head -1)
if [ -z "$CROSS_CC" ]; then
    echo "ERROR: Cannot find ${CROSS_PREFIX}-gcc"
    echo "Available compilers:"
    find /opt/toolchains -name "*-gcc" -type f 2>/dev/null
    exit 1
fi
CROSS_DIR=$(dirname "$CROSS_CC")
export PATH="${CROSS_DIR}:${PATH}"
echo "  Compiler: $CROSS_CC"
echo "  Testing: $($CROSS_CC --version | head -1)"

# Step 2: Create minimal rootfs
echo ""
echo "[2/6] Creating minimal rootfs..."
ROMFS=$WORK/romfs
rm -rf $ROMFS
mkdir -p $ROMFS/{bin,sbin,etc,etc/init.d,proc,sys,dev,tmp,var,var/run,var/log,usr,usr/bin,usr/sbin,lib,mnt,root}

# Step 3: Build BusyBox
echo ""
echo "[3/6] Building BusyBox..."
if [ ! -f $WORK/busybox-1.12.4/.built ]; then
    cd $WORK
    if [ ! -d busybox-1.12.4 ]; then
        gzip -dc < /data/humax-gpl/sources/busybox-1.12.4.tar.tar > /tmp/bb.tar 2>/dev/null || true
        tar xf /tmp/bb.tar
        rm -f /tmp/bb.tar
    fi
    cd busybox-1.12.4

    # Use our minimal config
    cp /data/build/busybox_minimal.config .config
    yes "" | make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- oldconfig > /dev/null 2>&1 || true

    make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- -j$(nproc) 2>&1 | tail -5

    if [ ! -f busybox ]; then
        echo "ERROR: BusyBox build failed"
        exit 1
    fi

    make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- CONFIG_PREFIX=$ROMFS install
    touch .built
    echo "  BusyBox built and installed to rootfs."
else
    cd $WORK/busybox-1.12.4
    make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- CONFIG_PREFIX=$ROMFS install
    echo "  BusyBox already built, installed to rootfs."
fi

# Step 4: Create init scripts and configuration
echo ""
echo "[4/6] Creating init scripts..."

# /etc/inittab
cat > $ROMFS/etc/inittab << 'INITTAB'
::sysinit:/etc/init.d/rcS
::respawn:/sbin/getty -L ttyS0 115200 vt100
::respawn:/bin/sh
::ctrlaltdel:/sbin/reboot
::shutdown:/bin/umount -a -r
INITTAB

# /etc/init.d/rcS
cat > $ROMFS/etc/init.d/rcS << 'RCS'
#!/bin/sh
echo "========================================"
echo " Humax CXHD-5150C Custom Firmware v0.1"
echo " BCM7405 mipsel"
echo "========================================"
echo ""

# Mount essential filesystems
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t tmpfs tmpfs /tmp
mount -t tmpfs tmpfs /var

mkdir -p /var/run /var/log /dev/pts
mount -t devpts devpts /dev/pts

# Create device nodes
echo "Creating device nodes..."
mdev -s 2>/dev/null || true
mknod -m 666 /dev/null c 1 3 2>/dev/null || true
mknod -m 666 /dev/zero c 1 5 2>/dev/null || true
mknod -m 666 /dev/random c 4 1 2>/dev/null || true
mknod -m 666 /dev/urandom c 1 9 2>/dev/null || true
mknod -m 600 /dev/console c 5 1 2>/dev/null || true
mknod -m 666 /dev/tty c 5 0 2>/dev/null || true
mknod -m 666 /dev/ttyS0 c 4 64 2>/dev/null || true
mknod -m 666 /dev/ttyS1 c 4 65 2>/dev/null || true

# Show system info
echo ""
echo "Kernel: $(uname -a)"
echo "Uptime: $(cat /proc/uptime)"
echo ""
cat /proc/cpuinfo 2>/dev/null | head -10
echo ""

# Network setup
echo "Configuring network..."
ifconfig lo 127.0.0.1 up 2>/dev/null || true
ifconfig eth0 up 2>/dev/null || true

# Try DHCP first, fall back to static
if command -v udhcpc >/dev/null 2>&1; then
    echo "Starting DHCP..."
    udhcpc -i eth0 -s /etc/udhcpc.script -t 5 -T 3 -n -q 2>/dev/null &
fi

# Also set a static fallback IP after a delay
(sleep 10; ifconfig eth0 | grep -q 'inet addr' || ifconfig eth0 192.168.1.100 netmask 255.255.255.0 up) &

# Start telnetd
echo "Starting telnet daemon on port 23..."
telnetd -l /bin/sh -p 23 2>/dev/null || telnetd 2>/dev/null || echo "telnetd failed to start"

echo ""
echo "========================================"
echo " System ready!"
echo " Connect via: telnet <ip> 23"
echo "========================================"
echo ""
RCS
chmod +x $ROMFS/etc/init.d/rcS

# DHCP client script
cat > $ROMFS/etc/udhcpc.script << 'DHCP'
#!/bin/sh
case "$1" in
    bound|renew)
        ifconfig $interface $ip netmask $subnet up
        if [ -n "$router" ]; then
            route add default gw $router dev $interface
        fi
        if [ -n "$dns" ]; then
            echo "nameserver $dns" > /etc/resolv.conf
        fi
        echo "DHCP: got $ip on $interface"
        ;;
esac
DHCP
chmod +x $ROMFS/etc/udhcpc.script

# /etc/passwd and /etc/group
echo "root::0:0:root:/root:/bin/sh" > $ROMFS/etc/passwd
echo "root:x:0:" > $ROMFS/etc/group
echo "root::0:0:0::::" > $ROMFS/etc/shadow

# /etc/hostname
echo "humax" > $ROMFS/etc/hostname

# /etc/profile
cat > $ROMFS/etc/profile << 'PROFILE'
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
export HOME=/root
export PS1='humax# '
alias ll='ls -la'
PROFILE

# Create linuxrc (for initrd boot)
cat > $ROMFS/linuxrc << 'LINUXRC'
#!/bin/sh
exec /sbin/init
LINUXRC
chmod +x $ROMFS/linuxrc

# /init for initramfs
cp $ROMFS/linuxrc $ROMFS/init
chmod +x $ROMFS/init

echo "  Init scripts created."

# Step 5: Build kernel
echo ""
echo "[5/6] Building kernel..."
cd $WORK
if [ ! -d linux-src ]; then
    cp -a /data/kernel/stblinux-2.6.18-7.1 linux-src
fi
cd linux-src

# Use the NAND initrd defconfig as base
cp arch/mips/configs/bcm97405b0-nand_initrd_defconfig .config

# Customize: point initramfs to our rootfs
sed -i "s|CONFIG_INITRAMFS_SOURCE=.*|CONFIG_INITRAMFS_SOURCE=\"$ROMFS\"|" .config

# Enable serial console
sed -i 's/# CONFIG_SERIAL_8250_CONSOLE is not set/CONFIG_SERIAL_8250_CONSOLE=y/' .config 2>/dev/null || true

# Enable USB HID (mouse/keyboard)
sed -i 's/# CONFIG_USB_HID is not set/CONFIG_USB_HID=y/' .config 2>/dev/null || true
sed -i 's/# CONFIG_HID is not set/CONFIG_HID=y/' .config 2>/dev/null || true
sed -i 's/# CONFIG_INPUT_MOUSEDEV is not set/CONFIG_INPUT_MOUSEDEV=y/' .config 2>/dev/null || true
sed -i 's/# CONFIG_INPUT_EVDEV is not set/CONFIG_INPUT_EVDEV=y/' .config 2>/dev/null || true

# Refresh config
yes "" | make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- oldconfig > /dev/null 2>&1

echo "  Building vmlinux..."
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- -j$(nproc) vmlinux 2>&1 | tail -20

if [ ! -f vmlinux ]; then
    echo "ERROR: Kernel build failed"
    exit 1
fi

echo "  Kernel built: $(ls -lh vmlinux | awk '{print $5}')"

# Create raw binary
${CROSS_PREFIX}-objcopy -O binary vmlinux vmlinux.bin
echo "  Raw binary: $(ls -lh vmlinux.bin | awk '{print $5}')"

# Step 6: Create HDF firmware file
echo ""
echo "[6/6] Creating HDF firmware..."

# Create kernel segment file with correct naming for humidify
# Address 0x80100400 is where the kernel binary is loaded
cp vmlinux.bin /data/hdf_work/custom_kernel.raw

# Create HDF using humidify
cd /data/hdf_work
chmod +x /data/humidify-ubuntu-1.0.4

# Create firmware with system ID 8050.8400
/data/humidify-ubuntu-1.0.4 -c /data/build/custom_firmware.hdf 8050.8400 \
    custom_kernel.raw:1:80100400

echo ""
echo "=== Build Complete ==="
echo "Firmware: /data/build/custom_firmware.hdf"
ls -lh /data/build/custom_firmware.hdf
echo ""
echo "Flash instructions:"
echo "  1. Copy custom_firmware.hdf to USB as 'cxhd_5150c_upgrade.hdf'"
echo "  2. Insert USB into STB"
echo "  3. Hold CH- on front panel"
echo "  4. Power on STB"
echo "  5. Wait for P000->P100->END"
