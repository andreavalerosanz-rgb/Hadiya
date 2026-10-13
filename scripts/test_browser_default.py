#!/usr/bin/env python3
"""Self-check: a new session with no allowed_tools gets the Playwright MCP (headless, isolated); an explicit list without it does not.
Temp copy of server.py + fake `claude` (like test_brain.py). Run: python3 scripts/test_browser_default.py"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="flows-bdef-"))
BIN, LOG, d = TMP / "bin", TMP / "argv.log", TMP / "app"
BIN.mkdir(); d.mkdir()
(BIN / "claude").write_text(f"""#!/usr/bin/env python3
import json, sys
open({str(LOG)!r}, "a").write(json.dumps(sys.argv) + "\\n")
print(json.dumps({{"type": "system", "subtype": "init", "session_id": "fake"}}), flush=True)
for line in sys.stdin:
    print(json.dumps({{"type": "result", "is_error": False, "result": "ok", "total_cost_usd": 0}}), flush=True)
""")
(BIN / "claude").chmod(0o755)
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, d / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=d, env={**os.environ, "HOME": str(TMP), "PATH": f"{BIN}:{os.environ['PATH']}", "PORT": str(P)},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start(body):
    n = len(LOG.read_text().splitlines()) if LOG.exists() else 0
    req = Request(f"http://127.0.0.1:{P}/api/sessions", data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json", "X-Flow": "1"})
    urlopen(req, timeout=10).read()
    for _ in range(100):
        if LOG.exists() and len(LOG.read_text().splitlines()) > n:
            return json.loads(LOG.read_text().splitlines()[n])
        time.sleep(0.1)
    raise AssertionError("claude never started")


try:
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", P), 0.2).close(); break
        except OSError:
            time.sleep(0.1)
    a = start({"message": "hi"})
    cfg = a[a.index("--mcp-config") + 1]
    assert "@playwright/mcp" in cfg and "--headless" in cfg and "--isolated" in cfg and "mcp__playwright" in a[a.index("--allowedTools") + 1]
    b = start({"message": "hi", "allowed_tools": "Read"})  # user unticked the browser
    assert "--mcp-config" not in b and "mcp__playwright" not in " ".join(b)
    print("ok")
finally:
    srv.terminate(); shutil.rmtree(TMP, ignore_errors=True)
