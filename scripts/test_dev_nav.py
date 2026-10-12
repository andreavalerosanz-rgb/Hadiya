#!/usr/bin/env python3
"""Dev package nav + paper identity at 390 (iPhone, isMobile) and 1440: the 5 destinations, Más lists the rest, each one
navigates, no horizontal overflow, nav/home text >=16px and targets >=48px, Barlow, paper background.
Same temp-server + mocks as shots_dev.py. Run: /tmp/pwenv/bin/python scripts/test_dev_nav.py  (exit 0 = ok)"""
import os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="flows-nav-"))
(TMP / "bin").mkdir(); (TMP / "home").mkdir(); (TMP / "app").mkdir()
(TMP / "bin/claude").write_text("#!/bin/sh\nexit 0\n"); (TMP / "bin/claude").chmod(0o755)
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, TMP / "app" / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=TMP / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "PATH": f"{TMP / 'bin'}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(TMP / "home"), "FLOWS_DATA": str(TMP / "app/data")})
NOW = time.time()
RUNS = [{"id": f"20261012-1{i}0000-aaaa", "kind": "session", "name": n, "status": st, "started": NOW - 900 * i, "ended": None, "cost": 0.1,
         "project": "/home/andrea/Desktop/flows", "parent": None, "pending": {}, "subs": [], "pinned": NOW if n == "Copia de seguridad" else None, "last": "Una línea de estado bastante larga para ver si la tarjeta corta bien el texto en el móvil."}
        for i, (n, st) in enumerate([("Rediseño de la tienda: catálogo y ficha de producto", "working"), ("Factura de octubre", "idle"), ("Copia de seguridad", "stopped")])]

MAIN = [("Inicio", ""), ("Plan", "#plan"), ("Asistente", "#assistant"), ("Goals", "#goals")]
MORE = [("Kanban", "#kanban"), ("Agentes", "#agents"), ("Proyectos", "#projects"), ("Guía", "#guide"), ("Plantillas", "#templates"), ("Teléfono", "#phone")]
SMALL = """sel => [...document.querySelectorAll(sel)].filter(e => e.offsetParent || e.closest('dialog[open]')).flatMap(e => {
  const r = e.getBoundingClientRect(), out = [];
  if (r.width && r.height && Math.min(r.width, r.height) < 48) out.push(`${e.tagName}.${e.className} '${e.textContent.trim().slice(0, 20)}' ${Math.round(r.width)}x${Math.round(r.height)}`);
  return out; })"""
TINY = """sel => [...document.querySelectorAll(sel)].flatMap(root => [...root.querySelectorAll('*')]).filter(e =>
  e.offsetParent && e.getBoundingClientRect().width > 1 && [...e.childNodes].some(n => n.nodeType == 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 16)
  .map(e => `${e.tagName}.${e.className} '${e.textContent.trim().slice(0, 20)}' ${getComputedStyle(e).fontSize}`)"""
fails = []
def check(ok, msg):
    if not ok: fails.append(msg); print("FAIL", msg)

def no_overflow(pg, where):
    w = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
    check(w[0] <= w[1], f"{where}: horizontal overflow {w}")

try:
    for _ in range(50):
        try: socket.create_connection(("127.0.0.1", P), 0.2).close(); break
        except OSError: time.sleep(0.1)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for size, ctxargs in (("390", p.devices["iPhone 13"] | {"viewport": {"width": 390, "height": 844}}), ("1440", {"viewport": {"width": 1440, "height": 900}})):
            ctx = b.new_context(**ctxargs); pg = ctx.new_page()
            pg.route("**/api/runs", lambda r: r.fulfill(json=RUNS))
            pg.goto(f"http://127.0.0.1:{P}/"); pg.wait_for_selector(".hcard", timeout=15000)
            check(pg.locator("#hp-h ~ .hcard").count() == 1 and pg.locator("#hc-h ~ .hcard").count() == 2, f"{size}: pinned section missing or session duplicated")
            pg.locator("#hp-h ~ .hcard").click(); pg.wait_for_url("**#session/*"); pg.goto(f"http://127.0.0.1:{P}/"); pg.wait_for_selector(".hcard")
            # identity
            st = pg.evaluate("[getComputedStyle(document.body).fontFamily, getComputedStyle(document.body).backgroundColor]")
            check("Barlow" in st[0], f"{size}: body font {st[0]}")
            check(st[1] == "rgb(244, 242, 238)", f"{size}: body background {st[1]}")
            # the 5 destinations
            labels = pg.eval_on_selector_all(".dnav a, .dnav [data-act=more]", "es => es.filter(e => e.offsetParent).map(e => e.textContent.trim())")
            check([l.split()[0] for l in labels] == [m[0] for m in MAIN] + ["Más"], f"{size}: nav shows {labels}")
            no_overflow(pg, f"{size} home")
            check(not (s := pg.evaluate(SMALL, ".dnav a, .dnav button, .hcard, .sopts>summary")), f"{size} home: targets <48px {s}")
            check(not (s := pg.evaluate(TINY, ".dnav, .hcards, .sopts>summary")), f"{size} home: text <16px {s}")
            for name, h in MAIN:
                pg.click(f".dnav a[href='#{h.lstrip('#')}']" if h else ".dnav a[href='#']"); pg.wait_for_timeout(400)
                check(pg.evaluate("location.hash") == h, f"{size}: {name} -> {pg.evaluate('location.hash')}")
                check(pg.locator(".dnav [aria-current=page]").first.inner_text().strip().startswith(name), f"{size}: {name} not marked current")
                no_overflow(pg, f"{size} {name}")
            # Más
            for name, h in MORE:
                pg.click(".dnav [data-act=more]"); pg.wait_for_selector("#more[open]")
                if name == MORE[0][0]:
                    items = pg.eval_on_selector_all("#more .more-nav a", "es => es.map(e => e.textContent.trim())")
                    check(all(any(i.startswith(m) for i in items) for m, _ in MORE), f"{size}: Más lists {items}")
                    check(not (s := pg.evaluate(SMALL, "#more .more-nav a, #more .more-h button")), f"{size} Más: targets <48px {s}")
                    check(not (s := pg.evaluate(TINY, "#more .more-nav")), f"{size} Más: text <16px {s}")
                    no_overflow(pg, f"{size} Más open")
                pg.click(f"#more .more-nav a[href='{h}']"); pg.wait_for_timeout(400)
                check(pg.evaluate("location.hash") == h and not pg.evaluate("document.querySelector('#more').open"), f"{size}: Más {name} -> {pg.evaluate('location.hash')}")
                check(pg.locator(".dnav [data-act=more]").get_attribute("aria-current") == "page", f"{size}: Más not marked current on {name}")
                no_overflow(pg, f"{size} {name}")
            # inside a session: phone hides the tab bar but keeps a clear way back
            pg.goto(f"http://127.0.0.1:{P}/#session/{RUNS[0]['id']}"); pg.wait_for_timeout(1200)
            if size == "390":
                check(pg.locator(".sback").is_visible(), "390 session: no back link")
                pg.click(".sback"); pg.wait_for_timeout(400)
                check(pg.evaluate("location.hash") == "", f"390 session back -> {pg.evaluate('location.hash')}")
            else:
                check(pg.locator(".dnav").is_visible(), "1440 session: rail nav hidden")
            ctx.close()
        b.close()
finally:
    srv.terminate(); shutil.rmtree(TMP, ignore_errors=True)
print("ok" if not fails else f"{len(fails)} failures"); sys.exit(1 if fails else 0)
