#!/bin/bash
set -e

echo "=== Humax CXHD-5150C Custom Firmware Builder v7 ==="
echo "  Key fix: correct load address 0x80001000 + trampoline to kernel_entry"
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
rm -rf busybox-1.12.4
gzip -dc < /data/humax-gpl/sources/busybox-1.12.4.tar.tar > /tmp/bb.tar 2>/dev/null || true
tar xf /tmp/bb.tar
rm -f /tmp/bb.tar

cd busybox-1.12.4
cp /data/build/busybox_minimal.config .config
yes "" | make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- oldconfig > /dev/null 2>&1 || true
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- -j$(nproc) 2>&1 | tail -5

if [ ! -f busybox ]; then
    echo "ERROR: BusyBox build failed!"
    exit 1
fi

make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- CONFIG_PREFIX=$ROMFS install 2>&1 | tail -3
echo "  BusyBox binary: $(ls -lh busybox | awk '{print $5}')"

# Force-copy actual busybox binary (make install sometimes creates a wrapper)
cp busybox $ROMFS/bin/busybox
chmod 755 $ROMFS/bin/busybox
echo "  Installed: $(ls -lh $ROMFS/bin/busybox | awk '{print $5}')"
echo "  File type: $(file $ROMFS/bin/busybox)"

# Step 4: Init scripts
echo ""
echo "[4/7] Creating init scripts..."

cat > $ROMFS/etc/inittab << 'INITTAB'
::sysinit:/etc/init.d/rcS
::respawn:/bin/sh
::ctrlaltdel:/sbin/reboot
::shutdown:/bin/umount -a -r
INITTAB

cat > $ROMFS/etc/init.d/rcS << 'RCS'
#!/bin/sh
echo "========================================"
echo " Humax CXHD-5150C Custom Firmware v0.7"
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
mknod -m 660 /dev/mem c 1 1 2>/dev/null || true

echo "Kernel: $(uname -a)"
cat /proc/cpuinfo 2>/dev/null | head -5

echo ""
echo "Network interfaces:"
ls /sys/class/net/ 2>/dev/null || echo "  (no sysfs)"

echo "Configuring network..."
ifconfig lo 127.0.0.1 up 2>/dev/null || true

for iface in eth0 eth1; do
    if ifconfig $iface up 2>/dev/null; then
        echo "Interface $iface is UP"
        udhcpc -i $iface -s /etc/udhcpc.script -t 5 -T 3 -n -q 2>/dev/null &
    fi
done

# Static fallback
(sleep 15
 for iface in eth0 eth1; do
   ifconfig $iface 2>/dev/null | grep -q 'inet addr' && continue
   ifconfig $iface 192.168.1.100 netmask 255.255.255.0 up 2>/dev/null && \
     route add default gw 192.168.1.1 dev $iface 2>/dev/null && \
     echo "Static: 192.168.1.100 on $iface" && break
 done) &

echo "Starting telnetd..."
telnetd -l /bin/sh -p 23 2>/dev/null || echo "telnetd FAILED"

echo "========================================"
echo " Ready! telnet <ip> 23"
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

# Step 5: Create initramfs
echo ""
echo "[5/7] Creating initramfs cpio..."

# Force copy real busybox binary right before cpio
cp $WORK/busybox-1.12.4/busybox $ROMFS/bin/busybox
chmod 755 $ROMFS/bin/busybox
sync
echo "  busybox final check: $(ls -lh $ROMFS/bin/busybox | awk '{print $5}') $(file $ROMFS/bin/busybox | awk -F: '{print $2}')"
echo "  romfs total: $(du -sh $ROMFS | awk '{print $1}')"

cd $ROMFS
find . -print0 | cpio --null -o -H newc 2>/dev/null | gzip -9 > $WORK/initramfs.cpio.gz
ISIZE=$(ls -lh $WORK/initramfs.cpio.gz | awk '{print $5}')
echo "  initramfs: $ISIZE"

# Verify it's not empty
ISIZE_BYTES=$(stat -c%s $WORK/initramfs.cpio.gz)
if [ "$ISIZE_BYTES" -lt 10000 ]; then
    echo "ERROR: initramfs too small ($ISIZE_BYTES bytes), busybox missing!"
    echo "  romfs contents:"
    ls -la $ROMFS/bin/
    exit 1
fi

# Step 6: Build kernel
echo ""
echo "[6/7] Building kernel..."
cd $WORK
rm -rf linux-src
cp -a /data/kernel/stblinux-2.6.18-7.1 linux-src
cd linux-src

make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- bcm97405b0-nand_initrd_defconfig 2>&1 | tail -2

# Embed initramfs
sed -i "s|^CONFIG_INITRAMFS_SOURCE=.*|CONFIG_INITRAMFS_SOURCE=\"${WORK}/initramfs.cpio.gz\"|" .config
grep -q 'CONFIG_BLK_DEV_INITRD=y' .config || echo 'CONFIG_BLK_DEV_INITRD=y' >> .config

# Enable serial console driver
sed -i 's/# CONFIG_SERIAL_8250_CONSOLE is not set/CONFIG_SERIAL_8250_CONSOLE=y/' .config 2>/dev/null || true

# Enable netconsole
sed -i 's/# CONFIG_NETCONSOLE is not set/CONFIG_NETCONSOLE=y/' .config 2>/dev/null || true

# Kernel command line with netconsole
sed -i 's|^CONFIG_CMDLINE=.*|CONFIG_CMDLINE="rw console=uart,mmio,0x10400b00,115200n8 netconsole=@/,6666@192.168.1.18/"|' .config

yes "" | make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- oldconfig > /dev/null 2>&1

echo "  Key configs:"
grep 'CONFIG_INITRAMFS_SOURCE' .config
grep 'CONFIG_CMDLINE=' .config
grep 'CONFIG_NETCONSOLE' .config | head -1
grep 'CONFIG_BCMINTEMAC_7038' .config | head -1

# Build
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- clean > /dev/null 2>&1
echo "  Building vmlinux (takes a few minutes)..."
make ARCH=mips CROSS_COMPILE=${CROSS_PREFIX}- -j$(nproc) vmlinux 2>&1 | tail -5

if [ ! -f vmlinux ]; then
    echo "ERROR: Kernel build failed!"
    exit 1
fi

# Verify initramfs
echo ""
echo "  Initramfs in kernel:"
ls -lh usr/initramfs_data.cpio.gz 2>/dev/null || echo "  NOT FOUND!"

# Get entry point
ENTRY=$(${CROSS_PREFIX}-readelf -h vmlinux | grep "Entry" | awk '{print $NF}')
echo "  Entry point: $ENTRY"

# Get load address (lowest VMA)
LOAD=$(${CROSS_PREFIX}-readelf -l vmlinux | grep "LOAD" | head -1 | awk '{print $3}')
echo "  Load address: $LOAD"

# Create raw binary
${CROSS_PREFIX}-objcopy -O binary vmlinux vmlinux.bin
echo "  vmlinux.bin: $(ls -lh vmlinux.bin | awk '{print $5}')"

# BusyBox check
BB_COUNT=$(${CROSS_PREFIX}-strings vmlinux | grep -c "BusyBox" || true)
echo "  BusyBox strings in kernel: ${BB_COUNT:-0}"

# Step 7: Create trampoline and HDF
echo ""
echo "[7/7] Creating HDF with trampoline..."

# Calculate jump target
ENTRY_DEC=$(printf "%d" $ENTRY)
LOAD_DEC=$(printf "%d" $LOAD)
OFFSET=$((ENTRY_DEC - LOAD_DEC))
printf "  Entry offset: 0x%x\n" $OFFSET

# Create MIPS 'j kernel_entry' trampoline
# j instruction: opcode=2, target = (addr >> 2) & 0x03FFFFFF
# Full encoding: (2 << 26) | target
ENTRY_SHIFTED=$((ENTRY_DEC >> 2))
TARGET=$((ENTRY_SHIFTED & 0x03FFFFFF))
INSTR=$((0x08000000 | TARGET))

printf "  Jump instruction: 0x%08x\n" $INSTR

# Write trampoline using printf (works on any system)
B0=$((INSTR & 0xFF))
B1=$(((INSTR >> 8) & 0xFF))
B2=$(((INSTR >> 16) & 0xFF))
B3=$(((INSTR >> 24) & 0xFF))
printf "\\x$(printf '%02x' $B0)\\x$(printf '%02x' $B1)\\x$(printf '%02x' $B2)\\x$(printf '%02x' $B3)\\x00\\x00\\x00\\x00" > /tmp/trampoline.bin
echo "  Trampoline bytes:"
od -A x -t x1 /tmp/trampoline.bin

# Patch trampoline into vmlinux.bin at offset 0
cp vmlinux.bin vmlinux_patched.bin
dd if=/tmp/trampoline.bin of=vmlinux_patched.bin bs=1 count=8 conv=notrunc 2>/dev/null
echo "  Patched vmlinux.bin with trampoline"

# Verify first bytes
echo "  First 16 bytes of patched binary:"
od -A x -t x4 -N 16 vmlinux_patched.bin

# Copy to hdf_work
cp vmlinux_patched.bin /data/hdf_work/custom_kernel_v7.raw

cd /data/hdf_work

# Create HDF: kernel at 0x80001000 (correct link address!)
LOAD_ADDR=$(echo $LOAD | sed 's/^0x//')
echo "  HDF load address: $LOAD_ADDR"

/data/humidify-ubuntu-1.0.4 -c /data/build/custom_firmware_v7.hdf 8050.8400 -r \
    custom_kernel_v7.raw:1:${LOAD_ADDR} \
    dummy_hdr_rootfs.raw:1:80600000 \
    dummy_rootfs.raw:1:80600400

echo ""
echo "  === HDF structure ==="
/data/humidify-ubuntu-1.0.4 -l /data/build/custom_firmware_v7.hdf 2>&1

echo ""
echo "=== BUILD COMPLETE ==="
ls -lh /data/build/custom_firmware_v7.hdf
