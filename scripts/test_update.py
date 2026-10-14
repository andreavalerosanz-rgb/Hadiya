#!/usr/bin/env python3
"""/api/update against a fake GitHub (HADIYA_UPDATE_API): newer, same, 404, timeout. Run: python3 scripts/test_update.py (exit 0 = ok)"""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.request import urlopen

REPO = Path(__file__).resolve().parent.parent
MODE = {"m": "newer"}
ASSET = {"win32": "hadiya-windows_9.9.9.zip", "darwin": "hadiya-macos_9.9.9.zip"}.get(sys.platform, "hadiya-linux_9.9.9.tar.gz")

class G(BaseHTTPRequestHandler):
    def handle(self):
        try: super().handle()
        except OSError: pass  # the timeout case: the client hung up
    def log_message(self, *a): pass
    def do_GET(self):
        m = MODE["m"]
        if m == "404": return self.send_error(404)
        if m == "timeout": time.sleep(8)
        tag = "v1.0.0" if m == "same" else "v9.9.9"
        body = json.dumps({"tag_name": tag, "html_url": "https://x/rel", "assets": [{"name": ASSET.replace("9.9.9", tag[1:]), "browser_download_url": "https://x/" + ASSET}]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

def free():
    with socket.socket() as s: s.bind(("127.0.0.1", 0)); return s.getsockname()[1]

fake = HTTPServer(("127.0.0.1", 0), G); threading.Thread(target=fake.serve_forever, daemon=True).start()
tmp = Path(tempfile.mkdtemp(prefix="hadiya-upd-"))
(tmp / "app").mkdir(); (tmp / "home").mkdir()
for f in ("server.py", "index.html"): shutil.copy(REPO / f, tmp / "app" / f)
(tmp / "app/VERSION").write_text("1.0.0\n")
fails = []
def check(ok, msg):
    if not ok: fails.append(msg); print("FAIL", msg)

def run(mode):
    MODE["m"] = mode; P = free()
    srv = subprocess.Popen([sys.executable, "server.py"], cwd=tmp / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={
        **os.environ, "PORT": str(P), "HOME": str(tmp / "home"), "HADIYA_DATA": str(tmp / "app/data"), "HADIYA_UPDATE_API": f"http://127.0.0.1:{fake.server_port}"})
    try:
        for _ in range(50):
            try: socket.create_connection(("127.0.0.1", P), 0.2).close(); break
            except OSError: time.sleep(0.1)
        return json.load(urlopen(f"http://127.0.0.1:{P}/api/update", timeout=15))
    finally: srv.terminate()

try:
    j = run("newer"); check(j["current"] == "1.0.0" and j["latest"] == "9.9.9" and j["newer"] and j["url"] == "https://x/" + ASSET and j["notes_url"] == "https://x/rel", f"newer {j}")
    j = run("same"); check(not j["newer"] and j["latest"] == "1.0.0", f"same {j}")
    j = run("404"); check(not j["newer"] and "error" not in j and j["latest"] is None, f"404 {j}")
    j = run("timeout"); check(not j["newer"] and j.get("error"), f"timeout {j}")
    (tmp / "app/VERSION").write_text("dev\n")
    j = run("newer"); check(not j["newer"] and j["current"] == "dev", f"dev {j}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("FAILED" if fails else "ok"); sys.exit(1 if fails else 0)
