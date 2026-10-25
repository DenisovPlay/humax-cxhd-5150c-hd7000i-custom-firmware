#!/usr/bin/env python3
"""Local OnLime/Humax portal for STB debugging.

Ports:
  80   HTTP  -> launcher page (mimics humax.onlime.ru)
  443  HTTPS -> launcher page
  5000 HTTP  -> debug panel
  5001 HTTPS -> debug panel

Every request from the STB is written to panel_log.txt / events.jsonl.
Live dashboard: http://192.168.1.18:5000/dashboard
"""
import argparse
import base64
import datetime
import json
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL_DIR = os.path.join(HERE, "panel")
CERT_DIR = os.path.join(HERE, "certs")
CERT_FILE = os.path.join(CERT_DIR, "humax.pem")
LOG_FILE = os.path.join(HERE, "panel_log.txt")
EVENTS_FILE = os.path.join(HERE, "events.jsonl")
DNS_LOG = os.path.join(HERE, "dns_log.txt")
CONFIG_FILE = os.path.join(HERE, "panel_config.json")
UPLOAD_DIR = os.path.join(HERE, "uploads")
FW_FILE = os.path.join(PANEL_DIR, "fw.hdf")
FW_GATE_FILE = os.path.join(HERE, "logs", "FW_GATE_OPEN")
FW_TOKEN = "fw.hdf"


def fw_gate_open():
    return os.path.exists(FW_GATE_FILE)

DEFAULT_CONFIG = {
    "launcher_target": "http://humax.onlime.ru:5080/",
    "stb_ip": "192.168.1.21",
    "panel_name": "OnLime local debug panel",
}

GIF_1PX = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")

_events = deque(maxlen=5000)
_event_lock = threading.Lock()
_next_id = [1]
START_TS = time.time()


# ---------------------------------------------------------------- config

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except Exception:
        pass
    return cfg


def save_config(cfg):
    tmp = CONFIG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CONFIG_FILE)


# ---------------------------------------------------------------- logging

def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def decode_body(raw):
    if not raw:
        return "", False
    try:
        text = raw.decode("utf-8")
        return text, False
    except UnicodeDecodeError:
        return base64.b64encode(raw).decode("ascii"), True


def human_event(ev):
    out = ["--- %s %s %s %s [%s:%s] id=%s%s"
           % (ev["ts"], ev["client"], ev["method"], ev["url"],
              ev["scheme"], ev["port"], ev["id"],
              " STB" if ev.get("is_stb") else "")]
    for key, value in ev.get("headers", []):
        out.append("    %s: %s" % (key, value))
    if ev.get("body"):
        out.append("    BODY[%d]: %s" % (ev.get("body_len", 0), ev["body"]))
    if ev.get("report") is not None:
        text = json.dumps(ev["report"], ensure_ascii=False, indent=2)
        out.append("    REPORT: " + text.replace("\n", "\n    "))
    if ev.get("note"):
        out.append("    NOTE: %s" % ev["note"])
    out.append("")
    return "\n".join(out) + "\n"


def log_event(ev):
    with _event_lock:
        eid = _next_id[0]
        _next_id[0] += 1
        ev["id"] = eid
        _events.append(ev)
        line = json.dumps(ev, ensure_ascii=False)
        try:
            with open(EVENTS_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(human_event(ev))
        except Exception:
            pass
    return eid


def tail_lines(path, count):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [line.rstrip("\n") for line in lines[-count:]]
    except FileNotFoundError:
        return []
    except Exception as exc:
        return ["(cannot read %s: %s)" % (path, exc)]


# ---------------------------------------------------------------- TLS cert

def ensure_cert():
    if os.path.exists(CERT_FILE):
        return
    os.makedirs(CERT_DIR, exist_ok=True)
    key = os.path.join(CERT_DIR, "humax.key")
    crt = os.path.join(CERT_DIR, "humax.crt")
    conf = os.path.join(CERT_DIR, "openssl.cnf")
    with open(conf, "w", encoding="utf-8") as f:
        f.write("""[req]
distinguished_name = dn
x509_extensions = v3_req
prompt = no

[dn]
CN = humax.onlime.ru
O = Local Debug
C = RU

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth

[alt_names]
DNS.1 = humax.onlime.ru
DNS.2 = www.humax.onlime.ru
DNS.3 = localhost
DNS.4 = humaxtvportal.com
DNS.5 = www.humaxtvportal.com
IP.1 = 192.168.1.18
IP.2 = 127.0.0.1
""")
    subprocess.run([
        "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", key, "-out", crt, "-days", "3650",
        "-config", conf, "-extensions", "v3_req",
    ], check=True)
    with open(CERT_FILE, "wb") as out:
        with open(key, "rb") as f:
            out.write(f.read())
        with open(crt, "rb") as f:
            out.write(f.read())


def make_tls_context():
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT_FILE)
    try:
        ctx.minimum_version = ssl.TLSVersion.TLSv1
    except Exception:
        pass
    for cipher_spec in ("ALL:!aNULL:!eNULL", "DEFAULT"):
        try:
            ctx.set_ciphers(cipher_spec)
            break
        except Exception:
            continue
    try:
        ctx.options |= getattr(ssl, "OP_NO_COMPRESSION", 0)
    except Exception:
        pass
    return ctx


# ---------------------------------------------------------------- launcher

def launcher_page(cfg):
    target = str(cfg.get("launcher_target", DEFAULT_CONFIG["launcher_target"]))
    proto = "https:" if target.lower().startswith("https://") else "http:"
    port = 5001 if proto == "https:" else 5080
    try:
        parsed = urlsplit(target)
        if parsed.port:
            port = parsed.port
    except Exception:
        pass
    prefer = "true" if proto == "https:" else "false"
    # Same structure as the real OnLime launcher page.
    return """<!DOCTYPE html>
<html>
    <body>
        <input type="hidden" id="http" name="http" value="5080">
        <input type="hidden" id="https" name="https" value="5001">
        <input type="hidden" id="prefer_https" name="prefer_https" value="%s">
        <p><a href="%s">local panel</a></p>
    </body>
    <script type="text/javascript">
        var protocol="%s";
        var port=%d;
        var URL=protocol+"//"+location.hostname+":"+port+location.pathname+location.search;
        location.replace(URL);
    </script>
</html>
""" % (prefer, target, proto, port)


# ---------------------------------------------------------------- handler

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "OnLimeLocal/1.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self._handle()

    def do_HEAD(self):
        self._handle()

    def do_POST(self):
        self._handle()

    def do_PUT(self):
        self._handle()

    def do_OPTIONS(self):
        self._handle()

    # ------------------------------------------------------------ helpers

    def _read_body(self):
        length = self.headers.get("Content-Length")
        if not length:
            return b""
        try:
            size = int(length)
        except ValueError:
            return b""
        if size <= 0:
            return b""
        return self.rfile.read(min(size, 512 * 1024))

    def _send(self, code, body=b"", ctype="text/html; charset=utf-8", extra=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Connection", "close")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass
        self.close_connection = True

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False),
                   "application/json; charset=utf-8")

    def _serve_file(self, relpath):
        root = os.path.realpath(PANEL_DIR)
        target = os.path.realpath(os.path.join(root, relpath.lstrip("/")))
        if target != root and not target.startswith(root + os.sep):
            return False
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if not os.path.isfile(target):
            return False
        ext = os.path.splitext(target)[1].lower()
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".gif": "image/gif",
            ".ico": "image/x-icon",
        }.get(ext, "application/octet-stream")
        with open(target, "rb") as f:
            data = f.read()
        self._send(200, data, ctype)
        return True

    def _event_base(self):
        scheme = getattr(self.server, "scheme", "http")
        port = self.server.server_port
        parsed = urlsplit(self.path)
        return {
            "ts": now_iso(),
            "client": self.client_address[0],
            "scheme": scheme,
            "port": port,
            "method": self.command,
            "url": self.path,
            "path": parsed.path or "/",
            "query": parsed.query,
            "headers": [[key, value] for key, value in self.headers.items()],
            "ua": self.headers.get("User-Agent", ""),
            "body_len": 0,
        }

    # ------------------------------------------------------------ routing

    def _handle(self):
        cfg = load_config()
        parsed = urlsplit(self.path)
        path = parsed.path or "/"
        query = parsed.query
        scheme = getattr(self.server, "scheme", "http")
        port = self.server.server_port

        if self.command in ("POST", "PUT", "PATCH"):
            raw_body = self._read_body()
        else:
            raw_body = b""

        ev = self._event_base()
        ev["is_stb"] = (ev["client"] == cfg.get("stb_ip"))

        # ---------- binary upload from the STB panel ----------
        if path == "/api/upload":
            q = parse_qs(query, keep_blank_values=True)
            name = os.path.basename(q.get("name", ["upload.bin"])[0]) or "upload.bin"
            try:
                off = max(0, int(q.get("off", ["0"])[0]))
            except Exception:
                off = 0
            data = raw_body
            if q.get("hex", ["0"])[0] in ("1", "true", "yes"):
                try:
                    data = bytes.fromhex(raw_body.decode("ascii", "ignore"))
                except Exception:
                    data = b""
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            target = os.path.join(UPLOAD_DIR, name)
            try:
                mode = "r+b" if os.path.exists(target) else "wb"
                with open(target, mode) as f:
                    f.seek(off)
                    f.write(data)
                size = os.path.getsize(target)
                ev["note"] = "upload %s off=%d len=%d total=%d" % (
                    name, off, len(data), size)
                log_event(ev)
                self._json({"ok": True, "name": name, "off": off,
                            "len": len(data), "size": size})
            except Exception as exc:
                ev["note"] = "upload failed %s: %s" % (name, exc)
                log_event(ev)
                self._json({"ok": False, "error": str(exc)}, 500)
            return

        body_text, body_is_b64 = decode_body(raw_body)
        if body_text:
            ev["body"] = body_text
            ev["body_len"] = len(raw_body)
            if body_is_b64:
                ev["body_b64"] = True

        ctype = self.headers.get("Content-Type", "")

        # CORS preflight
        if self.command == "OPTIONS":
            self._send(204, b"", "text/plain")
            return

        host = (self.headers.get("Host") or "").lower()

        # ---------- Humax TV Portal mimic (system info collector) ----------
        if path == "/Home/TVApps":
            if self.command == "POST":
                form = {}
                if body_text:
                    try:
                        form = parse_qs(body_text, keep_blank_values=True)
                    except Exception:
                        form = {}
                ev["report"] = {k: (v[0] if len(v) == 1 else v)
                                for k, v in form.items()}
                ev["note"] = "humaxtvportal system info"
                log_event(ev)
                self._send(200, "<!DOCTYPE html><html><body><h2>OK</h2>"
                                "<p>system info received</p></body></html>")
                return
            if self.command in ("GET", "HEAD") and self._serve_file("humaxtv.html"):
                log_event(ev)
                return

        # ---------- API ----------
        if path == "/api/report":
            report = None
            if raw_body:
                if "json" in ctype.lower() or raw_body.lstrip()[:1] in (b"{", b"["):
                    try:
                        report = json.loads(raw_body.decode("utf-8"))
                    except Exception:
                        report = None
                if report is None:
                    try:
                        form = parse_qs(raw_body.decode("utf-8", "replace"),
                                        keep_blank_values=True)
                        report = {k: (v[0] if len(v) == 1 else v)
                                  for k, v in form.items()}
                    except Exception:
                        report = None
            if report is None and query:
                form = parse_qs(query, keep_blank_values=True)
                if "data" in form:
                    try:
                        report = json.loads(form["data"][0])
                    except Exception:
                        report = {k: (v[0] if len(v) == 1 else v)
                                  for k, v in form.items()}
                else:
                    report = {k: (v[0] if len(v) == 1 else v)
                              for k, v in form.items()}
            if report is None:
                report = {"raw": body_text}
            ev["report"] = report
            eid = log_event(ev)
            self._json({"ok": True, "id": eid, "stb": ev["is_stb"]})
            return

        if path == "/api/beacon":
            ev["note"] = "beacon " + query
            log_event(ev)
            self._send(200, GIF_1PX, "image/gif")
            return

        if path == "/api/note":
            note = ""
            if raw_body:
                note = body_text
            elif query:
                note = parse_qs(query, keep_blank_values=True).get("text", [""])[0]
            ev["note"] = note
            log_event(ev)
            page = ("<!DOCTYPE html><html><body><h2>Note saved</h2>"
                    "<pre>%s</pre><p><a href=\"/\">back to panel</a></p>"
                    "</body></html>") % note.replace("&", "&amp;").replace("<", "&lt;")
            self._send(200, page)
            return

        if path == "/api/events":
            since = 0
            try:
                since = int(parse_qs(query).get("since", ["0"])[0])
            except Exception:
                since = 0
            with _event_lock:
                selected = [item for item in _events if item["id"] > since]
            selected = selected[:1000]
            next_id = selected[-1]["id"] if selected else since
            self._json({"events": selected, "next": next_id,
                        "count": len(selected)})
            return

        if path == "/api/dns":
            self._json({"lines": tail_lines(DNS_LOG, 300), "mtime": os.path.getmtime(DNS_LOG)
                        if os.path.exists(DNS_LOG) else 0})
            return

        if path == "/api/status":
            with _event_lock:
                last_stb = None
                for item in reversed(_events):
                    if item.get("is_stb"):
                        last_stb = item
                        break
                total = len(_events)
            self._json({
                "uptime": int(time.time() - START_TS),
                "ports": getattr(self.server, "all_ports", []),
                "config": cfg,
                "events": total,
                "last_stb": last_stb,
                "now": now_iso(),
            })
            return

        if path == "/api/config":
            if self.command in ("POST", "PUT"):
                data = {}
                if raw_body:
                    try:
                        data = json.loads(raw_body.decode("utf-8"))
                    except Exception:
                        data = {k: v[0] for k, v in
                                parse_qs(raw_body.decode("utf-8", "replace"),
                                         keep_blank_values=True).items()}
                for key in ("launcher_target", "stb_ip", "panel_name"):
                    if key in data:
                        cfg[key] = data[key]
                target = str(cfg.get("launcher_target", ""))
                if not (target.startswith("http://") or target.startswith("https://")):
                    self._json({"ok": False, "error": "launcher_target must be http(s)://"}, 400)
                    return
                save_config(cfg)
                ev["note"] = "config update: " + json.dumps(
                    {k: cfg.get(k) for k in ("launcher_target", "stb_ip", "panel_name")},
                    ensure_ascii=False)
                log_event(ev)
            self._json({"ok": True, "config": cfg})
            return

        if path == "/api/clear":
            with _event_lock:
                _events.clear()
                try:
                    with open(EVENTS_FILE, "w", encoding="utf-8"):
                        pass
                except Exception:
                    pass
            ev["note"] = "events cleared"
            log_event(ev)
            self._json({"ok": True})
            return

        # ---------- dashboard ----------
        if path in ("/dashboard", "/dashboard/"):
            if not self._serve_file("dashboard.html"):
                self._send(404, "dashboard.html missing", "text/plain")
            return

        if path == "/favicon.ico":
            self._send(204, b"", "text/plain")
            return

        # ---------- firmware download gate (matches any path containing fw.hdf) ----------
        if FW_TOKEN in path:
            open_state = "OPEN" if fw_gate_open() else "closed"
            ev["note"] = "FW HIT %s port=%s gate=%s" % (path, port, open_state)
            log_event(ev)
            try:
                with open(os.path.join(HERE, "logs", "FW_HITS.log"), "a",
                          encoding="utf-8") as f:
                    f.write("%s %s %s %s\n" % (ev["ts"], ev["client"], path,
                                               open_state))
            except Exception:
                pass
            if self.command in ("GET", "HEAD") and fw_gate_open():
                try:
                    with open(FW_FILE, "rb") as f:
                        data = f.read()
                    self._send(200, data, "application/octet-stream")
                except Exception:
                    self._send(500, b"fw file error", "text/plain")
            else:
                self._send(503, b"fw gate closed", "text/plain")
            return

        # ---------- humaxtvportal.com on 80/443 ----------
        if "humaxtvportal.com" in host:
            if self.command in ("GET", "HEAD") and self._serve_file("humaxtv.html"):
                log_event(ev)
                return
            ev["note"] = "humaxtvportal request"
            log_event(ev)
            self._send(200, "<!DOCTYPE html><html><body><h2>OK</h2></body></html>")
            return

        # ---------- launcher on 80/443 ----------
        if getattr(self.server, "kind", "panel") == "launcher":
            ev["note"] = "launcher page"
            log_event(ev)
            self._send(200, launcher_page(cfg))
            return

        # ---------- panel on 5000/5001 ----------
        if self.command == "GET" or self.command == "HEAD":
            rel = "index.html" if path in ("", "/") else path
            if self._serve_file(rel):
                log_event(ev)
                return
        log_event(ev)
        self._send(404, "<!DOCTYPE html><html><body><h2>404</h2>"
                        "<p>Local debug panel. Try <a href=\"/\">/</a> "
                        "or <a href=\"/dashboard\">/dashboard</a>.</p>"
                        "</body></html>")


# ---------------------------------------------------------------- servers

class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ssl.SSLError, ConnectionResetError, BrokenPipeError)):
            print("TLS/connection error from %s: %s" % (client_address[0], exc), flush=True)
            return
        print("server error from %s:" % (client_address[0],), flush=True)
        traceback.print_exc()


def start_server(name, scheme, port, tls_ctx, kind):
    srv = Server(("0.0.0.0", port), Handler)
    srv.scheme = scheme
    srv.kind = kind
    srv.all_ports = ALL_PORTS
    if tls_ctx is not None:
        srv.socket = tls_ctx.wrap_socket(srv.socket, server_side=True)
    thread = threading.Thread(target=srv.serve_forever, name=name, daemon=True)
    thread.start()
    print("listening %s://0.0.0.0:%d" % (scheme, port), flush=True)
    return srv


ALL_PORTS = []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--http-launcher", type=int, default=80)
    ap.add_argument("--https-launcher", type=int, default=443)
    ap.add_argument("--http-panel", type=int, default=5080)
    ap.add_argument("--https-panel", type=int, default=5001)
    ap.add_argument("--no-tls", action="store_true")
    args = ap.parse_args()

    os.makedirs(PANEL_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)

    tls_ctx = None
    if not args.no_tls:
        ensure_cert()
        tls_ctx = make_tls_context()

    ALL_PORTS.extend([args.http_launcher, args.https_launcher,
                      args.http_panel, args.https_panel])

    start_server("http-launcher", "http", args.http_launcher, None, "launcher")
    if tls_ctx is not None:
        start_server("https-launcher", "https", args.https_launcher, tls_ctx, "launcher")
    start_server("http-panel", "http", args.http_panel, None, "panel")
    if tls_ctx is not None:
        start_server("https-panel", "https", args.https_panel, tls_ctx, "panel")

    cfg = load_config()
    print("READY launcher_target=%s stb_ip=%s" % (cfg["launcher_target"], cfg["stb_ip"]), flush=True)
    print("dashboard: http://192.168.1.18:%d/dashboard" % args.http_panel, flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
