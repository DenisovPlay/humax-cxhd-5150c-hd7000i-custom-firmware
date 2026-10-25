#!/usr/bin/env python3
"""Start the DNS poison and portal server as detached daemons.

macOS `nohup` fails under `do shell script` ("can't detach from console"),
so use Popen(start_new_session=True) which is equivalent to setsid().
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(HERE, "logs")


def start(name, script):
    log_path = os.path.join(LOGS, name + ".out")
    pid_path = os.path.join(LOGS, name + ".pid")
    os.makedirs(LOGS, exist_ok=True)
    log = open(log_path, "ab", 0)
    cmd = ["/usr/bin/python3", os.path.join(HERE, script)]
    proc = subprocess.Popen(
        cmd,
        cwd=HERE,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=log,
        start_new_session=True,
        close_fds=True,
    )
    with open(pid_path, "w") as f:
        f.write(str(proc.pid))
    print("%s pid=%d cmd=%s" % (name, proc.pid, " ".join(cmd)), flush=True)
    return proc


def main():
    dns = start("dns", "dns_poison.py")
    portal = start("portal", "portal_server.py")
    time.sleep(2.0)
    ok = True
    for name, proc in (("dns", dns), ("portal", portal)):
        code = proc.poll()
        if code is None:
            print("%s alive pid=%d" % (name, proc.pid), flush=True)
        else:
            print("%s EXITED rc=%s (see logs/%s.out)" % (name, code, name), flush=True)
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
