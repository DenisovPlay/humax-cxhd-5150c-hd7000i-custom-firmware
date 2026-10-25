#!/bin/bash
set -e

echo "=== Humax CXHD-5150C Custom Firmware Builder v2 ==="
echo ""

WORK=/build
CROSS_PREFIX=mipsel-linux-uclibc

# Step 1: Extract crosstools
echo "[1/7] Extracting crosstools..."
if [ ! -d /opt/toolchains ]; then
    cd /tmp
    cp /data/humax-gpl/sources/crosstools_hf-linux-2.6.18.0_gcc-4.2-11ts_uclibc-nptl-0.9.29-20070423_20090508.tar.bz2.bz2 ct.bz2
    bunzip2 -f ct.bz2
    mkdir -p /opt/toolchains
    tar xf ct -C /opt/toolchains
    rm -f ct
fi
CROSS_DIR=/opt/toolchains/crosstools_hf-linux-2.6.18.0_gcc-4.2-11ts_uclibc-nptl-0.9.29-20070423_20090508/bin
export PATH="${CROSS_DIR}:${PATH}"
echo "  OK: $(${CROSS_PREFIX}-gcc --version | head -1)"

# Step 2: Create minimal rootfs
echo ""
echo "[2/7] Creating rootfs..."
ROMFS=$WORK/romfs
rm -rf $ROMFS
mkdir -p $ROMFS/{bin,sbin,etc,etc/init.d,proc,sys,dev,tmp,var,var/run,var/log,usr,usr/bin,usr/sbin,lib,mnt,root}

# Step 3: Build BusyBox
echo ""
echo "[3/7] Building BusyBox..."
cd $WORK
if [ ! -d busybox-1.12.4 ]; then
    gzip -dc < /data/humax-gpl/sources/busybox-1.12.4.tar.tar > /tmp/bb.tar 2>/dev/null || true
    tar xf /tmp/bb.tar
    rm -f /tmp/bb.tar
fi
cd busybox-1.12.4
cp /data/build/busybox_minimal.config .config
yes "" | make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- oldconfig > /dev/null 2>&1 || true
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- -j$(nproc) 2>&1 | tail -3
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- CONFIG_PREFIX=$ROMFS install 2>&1 | tail -3
echo "  BusyBox: $(ls -lh busybox | awk '{print $5}')"

# Step 4: Init scripts
echo ""
echo "[4/7] Creating init scripts..."

cat > $ROMFS/etc/inittab << 'INITTAB'
::sysinit:/etc/init.d/rcS
::respawn:/sbin/getty -L ttyS0 115200 vt100
::respawn:/bin/sh
::ctrlaltdel:/sbin/reboot
::shutdown:/bin/umount -a -r
INITTAB

cat > $ROMFS/etc/init.d/rcS << 'RCS'
#!/bin/sh
echo "========================================"
echo " Humax CXHD-5150C Custom Firmware v0.2"
echo " BCM7405 mipsel - stblinux-2.6.18"
echo "========================================"

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t tmpfs tmpfs /tmp
mount -t tmpfs tmpfs /var
mkdir -p /var/run /var/log /dev/pts
mount -t devpts devpts /dev/pts 2>/dev/null || true

mdev -s 2>/dev/null || true
mknod -m 666 /dev/null c 1 3 2>/dev/null || true
mknod -m 666 /dev/zero c 1 5 2>/dev/null || true
mknod -m 666 /dev/urandom c 1 9 2>/dev/null || true
mknod -m 600 /dev/console c 5 1 2>/dev/null || true
mknod -m 666 /dev/tty c 5 0 2>/dev/null || true
mknod -m 666 /dev/ttyS0 c 4 64 2>/dev/null || true

echo "Kernel: $(uname -a)"
cat /proc/cpuinfo 2>/dev/null | head -5

echo "Configuring network..."
ifconfig lo 127.0.0.1 up 2>/dev/null || true
ifconfig eth0 up 2>/dev/null || true
udhcpc -i eth0 -s /etc/udhcpc.script -t 5 -T 3 -n -q 2>/dev/null &
(sleep 15; ifconfig eth0 | grep -q 'inet addr' || ifconfig eth0 192.168.1.100 netmask 255.255.255.0 up) &

echo "Starting telnetd..."
telnetd -l /bin/sh -p 23 2>/dev/null || telnetd 2>/dev/null || echo "telnetd FAILED"

echo "========================================"
echo " System ready! telnet <ip> 23"
echo "========================================"
RCS
chmod +x $ROMFS/etc/init.d/rcS

cat > $ROMFS/etc/udhcpc.script << 'DHCP'
#!/bin/sh
case "$1" in
    bound|renew)
        ifconfig $interface $ip netmask $subnet up
        [ -n "$router" ] && route add default gw $router dev $interface
        [ -n "$dns" ] && echo "nameserver $dns" > /etc/resolv.conf
        echo "DHCP: got $ip on $interface"
        ;;
esac
DHCP
chmod +x $ROMFS/etc/udhcpc.script

echo "root::0:0:root:/root:/bin/sh" > $ROMFS/etc/passwd
echo "root:x:0:" > $ROMFS/etc/group
echo "humax" > $ROMFS/etc/hostname
cat > $ROMFS/etc/profile << 'EOF'
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
export PS1='humax# '
EOF

cat > $ROMFS/init << 'INIT'
#!/bin/sh
exec /sbin/init
INIT
chmod +x $ROMFS/init
cp $ROMFS/init $ROMFS/linuxrc
chmod +x $ROMFS/linuxrc

echo "  Done."

# Step 5: Create initramfs cpio archive
echo ""
echo "[5/7] Creating initramfs cpio..."
cd $ROMFS
find . | cpio -o -H newc 2>/dev/null | gzip -9 > $WORK/initramfs.cpio.gz
echo "  initramfs: $(ls -lh $WORK/initramfs.cpio.gz | awk '{print $5}')"

# Step 6: Build kernel with embedded initramfs
echo ""
echo "[6/7] Building kernel..."
cd $WORK
if [ ! -d linux-src ]; then
    cp -a /data/kernel/stblinux-2.6.18-7.1 linux-src
fi
cd linux-src

# Use NAND initrd defconfig as base
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- bcm97405b0-nand_initrd_defconfig 2>&1 | tail -3

# Point initramfs to our cpio archive (not directory — more reliable)
sed -i "s|^CONFIG_INITRAMFS_SOURCE=.*|CONFIG_INITRAMFS_SOURCE=\"${WORK}/initramfs.cpio.gz\"|" .config

# Make sure initrd/initramfs support is enabled
grep -q 'CONFIG_BLK_DEV_INITRD=y' .config || echo 'CONFIG_BLK_DEV_INITRD=y' >> .config

# Enable serial console
sed -i 's/# CONFIG_SERIAL_8250_CONSOLE is not set/CONFIG_SERIAL_8250_CONSOLE=y/' .config 2>/dev/null || true

# Enable USB HID
sed -i 's/# CONFIG_USB_HID is not set/CONFIG_USB_HID=y/' .config 2>/dev/null || true
sed -i 's/# CONFIG_HID is not set/CONFIG_HID=y/' .config 2>/dev/null || true

# Enable netconsole for remote debugging
sed -i 's/# CONFIG_NETCONSOLE is not set/CONFIG_NETCONSOLE=y/' .config 2>/dev/null || true

# Refresh
yes "" | make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- oldconfig > /dev/null 2>&1

# Verify initramfs config
echo "  INITRAMFS config:"
grep INITRAMFS .config
grep BLK_DEV_INITRD .config

# Clean and build
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- clean > /dev/null 2>&1
echo "  Building vmlinux (this takes a few minutes)..."
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- -j$(nproc) vmlinux 2>&1 | tail -10

if [ ! -f vmlinux ]; then
    echo "ERROR: Kernel build failed!"
    exit 1
fi

# Verify initramfs was embedded
echo ""
echo "  Checking initramfs embedding..."
if [ -f usr/initramfs_data.cpio.gz ]; then
    echo "  initramfs_data.cpio.gz: $(ls -lh usr/initramfs_data.cpio.gz | awk '{print $5}')"
else
    echo "  WARNING: initramfs_data.cpio.gz not found, checking alternative..."
    ls -la usr/ | grep -i init
fi

# Check for busybox string in kernel binary
${CROSS_PREFIX}-strings vmlinux | grep -c busybox > /dev/null 2>&1 && \
    echo "  VERIFIED: BusyBox strings found in vmlinux" || \
    echo "  WARNING: No BusyBox strings in vmlinux - initramfs may not be embedded"

VMLINUX_SIZE=$(ls -lh vmlinux | awk '{print $5}')
echo "  vmlinux: $VMLINUX_SIZE"

${CROSS_PREFIX}-objcopy -O binary vmlinux vmlinux.bin
BIN_SIZE=$(ls -lh vmlinux.bin | awk '{print $5}')
echo "  vmlinux.bin: $BIN_SIZE"

# Step 7: Create HDF firmware
echo ""
echo "[7/7] Creating HDF..."

# Copy kernel binary for HDF creation
cp vmlinux.bin /data/hdf_work/custom_kernel.raw

cd /data/hdf_work

# Create HDF with system ID 8050.8400
# Address 0x80100400 = kernel load address (matching original firmware)
/data/humidify-ubuntu-1.0.4 -c /data/build/custom_firmware_v2.hdf 8050.8400 \
    custom_kernel.raw:1:80100400

echo ""
echo "=== BUILD COMPLETE ==="
ls -lh /data/build/custom_firmware_v2.hdf
echo ""
echo "To flash: copy as cxhd_5150c_upgrade.hdf to USB, CH- + power on"
