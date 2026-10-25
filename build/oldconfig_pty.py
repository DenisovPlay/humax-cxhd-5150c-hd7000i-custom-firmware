#!/usr/bin/env python3
"""Запускает команду в pty и кормит её переводами строки (default answers).
Нужно для древних kconfig (busybox 1.12, linux 2.6.18), которые требуют
терминал на входе при появлении новых опций ('Console input/output is
redirected' -> exit 1). Завершается, когда потомок умирает."""
import os, pty, select, sys, time

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: oldconfig_pty.py <command> [args...]")
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp(sys.argv[1], sys.argv[1:])
        os._exit(127)
    deadline = time.time() + 600
    while time.time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.1)
        if r:
            try:
                data = os.read(fd, 65536)
                if not data:
                    break
            except OSError:
                break
            continue
        # нет вывода - можно отправить default-answer
        try:
            os.write(fd, b"\n")
        except OSError:
            break
        wp, status = os.waitpid(pid, os.WNOHANG)
        if wp == pid:
            # процесс завершился; добираем статус
            try:
                os.close(fd)
            except OSError:
                pass
            sys.exit(os.waitstatus_to_exitcode(status) if hasattr(sys, "waitstatus_to_exitcode") else (status >> 8))
    sys.exit(0)

main()
