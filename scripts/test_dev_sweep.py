#!/usr/bin/env python3
"""Dev package sweep: every page (home, session, plan, assistant, goals, kanban, Más pages) at 390 (iPhone) and 1440 has Barlow, paper
background, no horizontal overflow, visible text >=16px and buttons/links/inputs >=48px. Exit 0 = ok.
Run: /tmp/pwenv/bin/python scripts/test_dev_sweep.py"""
import os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hadiya-sweep-"))
(TMP / "bin").mkdir(); (TMP / "home").mkdir(); (TMP / "app").mkdir()
(TMP / "bin/claude").write_text("#!/bin/sh\nexit 0\n"); (TMP / "bin/claude").chmod(0o755)
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, TMP / "app" / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=TMP / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "PATH": f"{TMP / 'bin'}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(TMP / "home"), "HADIYA_DATA": str(TMP / "app/data")})
SID = "20261012-120000-aaaa"
RUN = {"id": SID, "kind": "session", "name": "Rediseño", "status": "idle", "started": time.time() - 900, "ended": None, "cost": 0.1, "project": "/tmp",
       "parent": None, "pending": {}, "subs": [], "last": "Hecho."}
PAGES = ["", "#session/" + SID, "#plan", "#assistant", "#goals", "#kanban", "#agents", "#projects", "#guide", "#templates", "#phone"]
CHECK = """() => {
  const vis = e => e.offsetParent && e.getBoundingClientRect().width > 1 && e.getBoundingClientRect().height > 1 && !e.closest('dialog:not([open])');
  const d = e => `${e.tagName}.${e.className}'${e.textContent.trim().slice(0, 18)}'`;
  const tiny = [...document.querySelectorAll('body *')].filter(e => vis(e) && [...e.childNodes].some(n => n.nodeType == 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 16).map(e => d(e) + getComputedStyle(e).fontSize);
  const small = [...document.querySelectorAll('button, a[href], input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea, summary')].filter(vis).filter(e => {
    const r = e.getBoundingClientRect(); return Math.min(r.width, r.height) < 48 && !e.closest('[hidden]'); }).map(e => { const r = e.getBoundingClientRect(); return d(e) + (e.getAttribute("data-act")||"") + Math.round(r.width) + 'x' + Math.round(r.height); });
  const cs = getComputedStyle(document.body);
  return {font: cs.fontFamily, bg: cs.backgroundColor, ow: document.documentElement.scrollWidth - innerWidth, tiny, small};
}"""
fails = []
try:
    for _ in range(50):
        try: socket.create_connection(("127.0.0.1", P), 0.2).close(); break
        except OSError: time.sleep(0.1)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for size, ca in (("390", p.devices["iPhone 13"] | {"viewport": {"width": 390, "height": 844}}), ("1440", {"viewport": {"width": 1440, "height": 900}})):
            pg = b.new_context(**ca).new_page()
            pg.route("**/api/runs", lambda r: r.fulfill(json=[RUN]))
            for h in PAGES:
                pg.goto(f"http://127.0.0.1:{P}/{h}"); pg.wait_for_timeout(1500)
                r = pg.evaluate(CHECK); w = f"{size} {h or 'home'}"
                for bad, msg in ((not r["font"].startswith("Barlow"), r["font"]), (r["bg"] != "rgb(244, 242, 238)", r["bg"]), (r["ow"] > 0, f"overflow {r['ow']}"),
                                 (r["tiny"], f"text<16 {r['tiny'][:6]}"), (r["small"], f"targets<48 {r['small'][:6]}")):
                    if bad: fails.append(w); print("FAIL", w, msg)
        b.close()
finally:
    srv.terminate()
print("FAILED" if fails else "ok"); sys.exit(1 if fails else 0)
