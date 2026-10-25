#!/usr/bin/env python3
"""Portal trap: HTTP(:80) + HTTPS(:443, self-signed) servers that log every request
from the STB to portal_log.txt and reply 200 with a neutral page."""
import http.server, socketserver, ssl, os, sys, datetime, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PLOG = open(HERE + "/portal_log.txt", "a", buffering=1)
CERT = HERE + "/trap.pem"

if not os.path.exists(CERT):
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", CERT,
                    "-nodes", "-days", "365", "-subj", "/CN=humax.onlime.ru",
                    "-out", CERT], check=True, capture_output=True)

class H(http.server.BaseHTTPRequestHandler):
    def _log(self):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        PLOG.write(f"--- {ts} {self.client_address[0]} {self.command} {self.path}\n")
        for k, v in self.headers.items():
            PLOG.write(f"    {k}: {v}\n")
        cl = self.headers.get("Content-Length")
        if cl:
            body = self.rfile.read(int(cl))
            PLOG.write(f"    BODY[{len(body)}]: {body[:2000]!r}\n")
        PLOG.flush()
        print(f"{ts} {self.command} {self.path} from {self.client_address[0]}", flush=True)

    def _reply(self):
        self._log()
        page = b"<html><head><title>OnLime</title></head><body>OK</body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    do_GET = do_POST = do_HEAD = do_PUT = do_OPTIONS = _reply

    def log_message(self, *a):
        pass

class Srv(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

which = sys.argv[1]
if which == "http":
    Srv(("0.0.0.0", 80), H).serve_forever()
else:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT)
    s = Srv(("0.0.0.0", 443), H)
    s.socket = ctx.wrap_socket(s.socket, server_side=True)
    s.serve_forever()
