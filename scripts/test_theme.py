#!/usr/bin/env python3
"""Light/dark theme across packages: dev pages, admin (Pedir, conversation, Ayuda) and the login page, at 390 (iPhone) and 1440,
in both themes. Checks: <html data-theme> matches, no horizontal overflow, WCAG AA contrast on every visible text node (4.5:1,
3:1 for large text), and the toggles (Más, Ayuda, login corner) persist across reload. Kanban has its own check in test_kanban_ui.py.
Run: /tmp/pwenv/bin/python scripts/test_theme.py [shots dir]   Exit 0 = ok."""
import os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="flows-theme-"))
SHOTS = Path(sys.argv[1]) if len(sys.argv) > 1 else None
(TMP / "bin").mkdir(); (TMP / "home").mkdir(); (TMP / "app").mkdir(); (TMP / "ldata").mkdir()
# fake claude: one markdown answer per message
(TMP / "bin/claude").write_text(r'''#!/usr/bin/env python3
import json, sys
out = lambda o: (print(json.dumps(o)), sys.stdout.flush())
out({"type": "system", "subtype": "init", "session_id": "fake"})
for line in sys.stdin:
    if json.loads(line).get("type") != "user": continue
    t = "Hoy tienes **2 correos** importantes:\n\n1. **Marta** envía el presupuesto.\n2. **Luis** mueve la reunión."
    out({"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}})
    out({"type": "result", "is_error": False, "result": t, "total_cost_usd": 0})
''')
(TMP / "bin/claude").chmod(0o755)
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, TMP / "app" / f)
(TMP / "ldata/users.json").write_text('{"ana": {"unix": "ana", "package": "admin", "pw": "x$y"}}')


def port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def serve(data, **env):
    p = port()
    srv = subprocess.Popen([sys.executable, "server.py"], cwd=TMP / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           env={**os.environ, "PATH": f"{TMP / 'bin'}:{os.environ['PATH']}", "PORT": str(p), "HOME": str(TMP / "home"), "FLOWS_DATA": str(data), **env})
    for _ in range(50):
        try: socket.create_connection(("127.0.0.1", p), 0.2).close(); break
        except OSError: time.sleep(0.1)
    return srv, f"http://127.0.0.1:{p}/"


SID = "20261012-120000-aaaa"
RUN = {"id": SID, "kind": "session", "name": "Rediseño", "status": "idle", "started": time.time() - 900, "ended": None, "cost": 0.1, "project": "/tmp",
       "parent": None, "pending": {}, "subs": [], "last": "Hecho."}
DEV = ["", "#session/" + SID, "#plan", "#assistant", "#goals", "#kanban", "#agents", "#projects", "#guide", "#templates", "#phone"]
# visible text nodes whose color vs effective background is under AA; skips text over images/gradients it can't resolve
CHECK = r"""() => {
  const rgb = c => { const m = c.match(/[\d.]+/g); return m ? m.map(Number) : [0, 0, 0, 0]; };
  const lum = ([r, g, b]) => { const f = v => (v /= 255) <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  const mix = (a, b) => { const al = a[3] ?? 1; return [0, 1, 2].map(i => a[i] * al + b[i] * (1 - al)); };
  const bgOf = e => { const layers = []; for (let n = e; n; n = n.parentElement) { const s = getComputedStyle(n), c = rgb(s.backgroundColor);
      if (s.backgroundImage != 'none' && !/radial/.test(s.backgroundImage) && n != e) return null;
      if ((c[3] ?? 1) > 0) { layers.push(c); if ((c[3] ?? 1) >= 1) break; } }
    let b = [255, 255, 255]; for (const l of layers.reverse()) b = mix(l, b); return b; };
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 1 && r.height > 1 && s.visibility != 'hidden' && s.opacity != '0'
      && !e.closest('.sr,[hidden],dialog:not([open]),details:not([open])>:not(summary),svg,script,style'); };
  const bad = [], w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let t; (t = w.nextNode());) {
    const e = t.parentElement; if (!t.textContent.trim() || !e || !vis(e)) continue;
    const s = getComputedStyle(e), bg = bgOf(e); if (!bg) continue;
    const fg = mix(rgb(s.color), bg), L = [lum(fg), lum(bg)].sort((a, b) => b - a), ratio = (L[0] + .05) / (L[1] + .05);
    const fs = parseFloat(s.fontSize), big = fs >= 24 || (fs >= 18.66 && +s.fontWeight >= 700);
    if (ratio < (big ? 3 : 4.5)) bad.push(`${e.tagName.toLowerCase()}.${String(e.className).trim().split(/\s+/)[0]} "${t.textContent.trim().slice(0, 24)}" ${ratio.toFixed(2)}`);
  }
  return {theme: document.documentElement.dataset.theme || 'light', ow: document.documentElement.scrollWidth - innerWidth, bad: [...new Set(bad)]};
}"""
fails = []


def check(pg, where, theme):
    pg.wait_for_timeout(400)
    r = pg.evaluate(CHECK)
    for bad, msg in ((r["theme"] != theme, f"theme {r['theme']}"), (r["ow"] > 0, f"overflow {r['ow']}"), (r["bad"], f"contrast {r['bad'][:5]}")):
        if bad: fails.append(where); print("FAIL", where, theme, msg)


def shot(pg, name):
    if SHOTS: SHOTS.mkdir(parents=True, exist_ok=True); pg.screenshot(path=str(SHOTS / f"{name}.png"))


dev, DEV_URL = serve(TMP / "app/data")
adm, ADM_URL = serve(TMP / "adata", FLOWS_PACKAGE="admin")
login, LOGIN_URL = serve(TMP / "ldata")
try:
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for size, ca in (("390", p.devices["iPhone 13"] | {"viewport": {"width": 390, "height": 844}}), ("1440", {"viewport": {"width": 1440, "height": 900}})):
            for theme in ("light", "dark"):
                ctx = b.new_context(**ca)
                ctx.add_init_script(f"if(!sessionStorage.seeded){{sessionStorage.seeded=1;localStorage.theme='{theme}'}}")
                pg = ctx.new_page()
                pg.on("pageerror", lambda e: (fails.append("js"), print("FAIL js", e)))
                pg.route("**/api/runs", lambda r: r.fulfill(json=[RUN]))
                for h in DEV:
                    pg.goto(DEV_URL + h); pg.wait_for_timeout(1200); check(pg, f"dev {size} {h or 'home'}", theme)
                    if h in ("", "#session/" + SID): shot(pg, f"dev-{'home' if not h else 'session'}-{theme}-{size}")
                pg.goto(DEV_URL); pg.wait_for_timeout(800)
                pg.locator("[data-act=more] >> visible=true").first.click(); pg.wait_for_selector("#more[open]")
                check(pg, f"dev {size} Más", theme); shot(pg, f"dev-mas-{theme}-{size}")
                pg.unroute("**/api/runs")
                # admin: Pedir, a conversation, Ayuda
                pg.goto(ADM_URL); pg.wait_for_selector("#a-msg"); check(pg, f"adm {size} pedir", theme); shot(pg, f"adm-pedir-{theme}-{size}")
                pg.fill("#a-msg", "Resume los correos de hoy"); pg.click(".a-pedir"); pg.wait_for_url("**#session/*")
                pg.wait_for_selector(".a-say:has-text('2 correos')", timeout=15000); check(pg, f"adm {size} chat", theme); shot(pg, f"adm-chat-{theme}-{size}")
                pg.goto(ADM_URL + "#guide"); pg.wait_for_selector(".a-acct [data-act=theme]"); check(pg, f"adm {size} ayuda", theme)
                pg.goto(LOGIN_URL); pg.wait_for_selector("#u"); check(pg, f"login {size}", theme); shot(pg, f"login-{theme}-{size}")
                ctx.close()
            # toggles flip and persist across reload (one fresh light context per surface)
            for url, open_, sel in ((DEV_URL, lambda pg: (pg.locator("[data-act=more] >> visible=true").first.click(), pg.wait_for_selector("#more[open]")), "#more [data-act=theme]"),
                                    (ADM_URL + "#guide", lambda pg: pg.wait_for_selector(".a-acct [data-act=theme]"), ".a-acct [data-act=theme]"),
                                    (LOGIN_URL, lambda pg: pg.wait_for_selector("#tt"), "#tt")):
                ctx = b.new_context(**ca); pg = ctx.new_page(); pg.goto(url); pg.wait_for_timeout(800); open_(pg)
                t = pg.locator(sel)
                ok = t.get_attribute("aria-pressed") == "false"
                bx = t.bounding_box(); ok &= min(bx["width"], bx["height"]) >= 48
                t.click(); ok &= pg.evaluate("document.documentElement.dataset.theme") == "dark" and t.get_attribute("aria-pressed") == "true"
                pg.reload(); pg.wait_for_timeout(800); ok &= pg.evaluate("document.documentElement.dataset.theme") == "dark"
                open_(pg); pg.locator(sel).click(); pg.reload(); pg.wait_for_timeout(500)
                ok &= pg.evaluate("document.documentElement.dataset.theme") is None and pg.evaluate("localStorage.theme") == "light"
                if not ok: fails.append("toggle"); print("FAIL toggle", size, url)
                ctx.close()
        b.close()
finally:
    for s in (dev, adm, login): s.terminate()
print("FAILED" if fails else "ok"); sys.exit(1 if fails else 0)
