#!/usr/bin/env python3
"""Update entry in the UI: dev Más dialog and adm Ayuda show "Hadiya <ver>" always and the download link only when newer;
390 + 1440, light + dark, no overflow, link target >=48px. Run: /tmp/pwenv/bin/python scripts/test_update_ui.py [shots dir]"""
import os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
fails = []
def check(ok, msg):
    if not ok: fails.append(msg); print("FAIL", msg)

def serve(pkg):
    tmp = Path(tempfile.mkdtemp(prefix="hadiya-updui-"))
    for d in ("bin", "home", "app"): (tmp / d).mkdir()
    (tmp / "bin/claude").write_text("#!/bin/sh\nexit 0\n"); (tmp / "bin/claude").chmod(0o755)
    for f in ("server.py", "index.html"): shutil.copy(REPO / f, tmp / "app" / f)
    with socket.socket() as s: s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]
    srv = subprocess.Popen([sys.executable, "server.py"], cwd=tmp / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={
        **os.environ, "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(tmp / "home"), "HADIYA_DATA": str(tmp / "app/data"),
        **({"HADIYA_PACKAGE": "admin"} if pkg == "adm" else {})})
    for _ in range(50):
        try: socket.create_connection(("127.0.0.1", P), 0.2).close(); break
        except OSError: time.sleep(0.1)
    return srv, P, tmp

UPD = {True: {"current": "1.2.0", "latest": "1.3.0", "newer": True, "url": "https://example.com/hadiya-linux_1.3.0.tar.gz", "notes_url": "https://example.com/rel"},
       False: {"current": "1.2.0", "latest": "1.2.0", "newer": False, "url": None, "notes_url": None}}
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for pkg in ("dev", "adm"):
            srv, P, tmp = serve(pkg)
            try:
                for size, args in (("390", p.devices["iPhone 13"] | {"viewport": {"width": 390, "height": 844}}), ("1440", {"viewport": {"width": 1440, "height": 900}})):
                    for theme in ("light", "dark"):
                        for newer in (True, False):
                            tag = f"{pkg}-{size}-{theme}-{'new' if newer else 'same'}"
                            ctx = b.new_context(**args); pg = ctx.new_page()
                            pg.add_init_script(f"localStorage.theme='{theme}'")
                            pg.route("**/api/update", lambda r, q=None, n=newer: r.fulfill(json=UPD[n]))
                            pg.goto(f"http://127.0.0.1:{P}/" + ("#guide" if pkg == "adm" else ""))
                            if pkg == "dev":
                                pg.wait_for_selector("[data-act=more]", timeout=15000)
                                pg.wait_for_timeout(1500)
                                pg.locator("[data-act=more]:visible").first.click()
                                root = pg.locator("#more")
                                dot = pg.locator("[data-act=more] .upd-dot").count()
                                check(bool(dot) == newer, f"{tag}: dot={dot}")
                            else:
                                pg.wait_for_selector(".a-acct", timeout=15000); pg.wait_for_timeout(1500); root = pg.locator(".a-acct")
                            check("Hadiya 1.2.0" in root.inner_text(), f"{tag}: current version missing")
                            link = root.locator(".upd a")
                            check((link.count() == 1) == newer, f"{tag}: link count {link.count()}")
                            if newer and link.count():
                                bx = link.bounding_box()
                                check("1.3.0" in link.inner_text() and link.get_attribute("href").endswith("1.3.0.tar.gz"), f"{tag}: link text/href")
                                check(bx["height"] >= 48, f"{tag}: link height {bx['height']}")
                            w = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
                            check(w[0] <= w[1], f"{tag}: overflow {w}")
                            if SHOTS and newer: pg.screenshot(path=str(SHOTS / f"upd-{tag}.png"))
                            ctx.close()
            finally:
                srv.terminate(); shutil.rmtree(tmp, ignore_errors=True)
finally:
    pass
print("FAILED" if fails else "ok"); sys.exit(1 if fails else 0)
