#!/usr/bin/env python3
"""UX checks for the admin package ("Flows on paper"), Playwright, phone 390 (isMobile) and desktop 1440, Chrome + Firefox.
Runs server.py from a temp copy on a free port with FLOWS_PACKAGE=admin and a fake `claude` on PATH.
Checks: no JS errors, no sideways scroll, text >=16px, touch targets >=48px on the phone, every destination in <=2 clicks
from home, and the main flow Pedir -> Mis peticiones.
Run: /tmp/pwenv/bin/python scripts/test_adm_ux.py [shots dir] [--shots-only PREFIX]"""
import os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
args = [a for a in sys.argv[1:] if not a.startswith("--")]
SHOTS_ONLY = sys.argv[sys.argv.index("--shots-only") + 1] if "--shots-only" in sys.argv else None
if SHOTS_ONLY in args:
    args.remove(SHOTS_ONLY)
TMP = Path(tempfile.mkdtemp(prefix="flows-adm-"))
SHOTS = Path(args[0]) if args else TMP / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)
BIN, HOME = TMP / "bin", TMP / "home"
BIN.mkdir(); HOME.mkdir()
# fake claude: searches the mail, reads a thread, asks a question when told to, then answers in markdown
(BIN / "claude").write_text(r'''#!/usr/bin/env python3
import json, sys
out = lambda o: (print(json.dumps(o)), sys.stdout.flush())
tool = lambda i, n, inp: out({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": i, "name": n, "input": inp}]}})
res = lambda i: out({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": i, "content": "raw tool output " * 40}]}})
out({"type": "system", "subtype": "init", "session_id": "fake"})
n = 0
for line in sys.stdin:
    m = json.loads(line)
    if m.get("type") != "user":
        continue
    c = m["message"]["content"]
    c = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict))
    n += 1
    out({"type": "assistant", "message": {"content": [{"type": "text", "text": "Voy a mirar tu correo de hoy."}]}})
    tool(f"t{n}a", "mcp__claude_ai_Gmail__search_threads", {"query": "newer_than:1d"}); res(f"t{n}a")
    tool(f"t{n}b", "mcp__claude_ai_Gmail__get_thread", {"subject": "Presupuesto reforma oficina"}); res(f"t{n}b")
    tool(f"t{n}c", "mcp__claude_ai_Google_Calendar__list_events", {}); res(f"t{n}c")
    if "PREGUNTA" in c:
        out({"type": "control_request", "request_id": f"q{n}", "request": {"subtype": "can_use_tool", "tool_name": "AskUserQuestion",
             "input": {"questions": [{"question": "¿Respondo a Marta o solo te lo resumo?", "options": [{"label": "Solo resumen"}, {"label": "Prepara un borrador"}]}]}}})
        sys.stdin.readline()
        continue  # stays "Te necesita" until answered
    text = ("Hoy has recibido **4 correos** importantes:\n\n1. **Marta López** te envía el presupuesto de la reforma (12.400 €).\n"
            "   - Pide respuesta antes del viernes.\n2. **Banco** confirma la transferencia.\n3. **Luis** propone mover la reunión al jueves.\n"
            "4. **Hacienda**: aviso de notificación pendiente.\n\n¿Quieres que prepare un borrador para Marta?")
    out({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})
    out({"type": "result", "is_error": False, "result": text, "total_cost_usd": 0})
''')
(BIN / "claude").chmod(0o755)
d = TMP / "app"; d.mkdir()
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, d / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "PATH": f"{BIN}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(HOME),
                            "FLOWS_DATA": str(d / "data"), "FLOWS_PACKAGE": "admin"})
URL = f"http://127.0.0.1:{P}/"
# second instance in multi-user mode, only to see the login page
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); LP = s.getsockname()[1]
(TMP / "ldata").mkdir()
(TMP / "ldata" / "users.json").write_text('{"ana": {"unix": "ana", "package": "admin", "pw": "x$y"}}')
lsrv = subprocess.Popen([sys.executable, "server.py"], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env={**os.environ, "PORT": str(LP), "HOME": str(HOME), "FLOWS_DATA": str(TMP / "ldata")})
LOGIN_URL = f"http://127.0.0.1:{LP}/"

# every visible piece of text, every visible control; reports offenders by a short selector
AUDIT = r"""(mobile) => {
  const sel = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className == 'string' ? '.' + e.className.trim().split(/\s+/).join('.') : '');
  const vis = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility != 'hidden' && s.display != 'none' && !e.closest('.sr,[hidden],dialog:not([open]),details:not([open])>:not(summary)'); };
  const small = [], tiny = [];
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let t; (t = w.nextNode());) {
    const e = t.parentElement;
    if (!t.textContent.trim() || !e || !vis(e) || e.closest('svg,script,style')) continue;
    const fs = parseFloat(getComputedStyle(e).fontSize);
    if (fs < 16) small.push(sel(e) + ' ' + fs + 'px "' + t.textContent.trim().slice(0, 30) + '"');
  }
  if (mobile) for (const e of document.querySelectorAll('a[href],button,input:not([type=hidden]):not([type=radio]):not([type=checkbox]),textarea,select,summary,label.opt')) {
    if (!vis(e) || e.closest('.a-say p,.a-say li')) continue;  // links inside a reply's sentences: WCAG inline exception
    const r = e.getBoundingClientRect();
    if (r.height < 47.5 || r.width < 47.5) tiny.push(sel(e) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
  }
  const over = document.documentElement.scrollWidth - (mobile ? screen.width : innerWidth);
  return {small: [...new Set(small)].slice(0, 8), tiny: [...new Set(tiny)].slice(0, 8), over};
}"""

fails = []
def check(cond, msg):
    if not cond:
        fails.append(msg); print("FAIL", msg)

from playwright.sync_api import sync_playwright
try:
    for port in (P, LP):
        for _ in range(80):
            try:
                socket.create_connection(("127.0.0.1", port), 0.2).close(); break
            except OSError:
                time.sleep(0.1)
    with sync_playwright() as p:
        engines = [("chrome", lambda: p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"]))]
        if not SHOTS_ONLY:
            engines.append(("firefox", lambda: p.firefox.launch()))
        for eng, launch in engines:
            b = launch()
            phone = {"viewport": {"width": 390, "height": 844}, "screen": {"width": 390, "height": 844}, "device_scale_factor": 2,
                     "has_touch": True, "user_agent": p.devices["iPhone 13"]["user_agent"]}
            if eng == "chrome":
                phone["is_mobile"] = True  # Firefox has no isMobile emulation
            for name, ctxargs in (("mobile", phone), ("desktop", {"viewport": {"width": 1440, "height": 900}})):
                tag = f"{eng}/{name}"
                mobile = name == "mobile"
                ctx = b.new_context(**ctxargs, locale="es-ES"); pg = ctx.new_page(); errs = []
                pg.on("pageerror", lambda e: errs.append(str(e)))
                def audit(where):
                    pg.wait_for_timeout(300)
                    a = pg.evaluate(AUDIT, mobile)
                    check(a["over"] <= 0, f"{tag} {where}: sideways scroll {a['over']}px")
                    check(not a["small"], f"{tag} {where}: text under 16px {a['small']}")
                    check(not a["tiny"], f"{tag} {where}: targets under 48px {a['tiny']}")
                def nav(label):  # one click on a main destination, whatever the layout
                    pg.get_by_role("link", name=label, exact=False).locator("visible=true").first.click()
                pg.goto(URL); pg.wait_for_selector("#a-msg")
                # Pedir: one request that finishes, one that asks
                if eng == "chrome" and name == "mobile":
                    pg.fill("#a-msg", "Hazme un resumen de mi semana PREGUNTA"); pg.click(".a-pedir")
                    pg.wait_for_url("**#session/*"); pg.wait_for_selector(".a-askbar", timeout=15000)
                    pg.goto(URL); pg.wait_for_selector("#a-msg")
                if SHOTS_ONLY:
                    pg.screenshot(path=str(SHOTS / f"adm-{SHOTS_ONLY}-{name}-pedir.png"), full_page=True)
                else:
                    audit("home")
                pg.fill("#a-msg", f"Resume los correos que he recibido hoy ({eng} {name})")
                pg.click(".a-pedir")
                pg.wait_for_url("**#session/*")
                pg.wait_for_selector(".a-say:has-text('4 correos')", timeout=15000)
                if SHOTS_ONLY:
                    pg.screenshot(path=str(SHOTS / f"adm-{SHOTS_ONLY}-{name}-sesion.png"), full_page=True)
                else:
                    audit("session")
                    check(pg.locator("text=raw tool output").count() == 0, f"{tag}: raw tool output shown")
                # -> Mis peticiones: the new request is listed
                if SHOTS_ONLY:
                    pg.locator("text=Mis peticiones >> visible=true").first.click(); pg.wait_for_timeout(500)
                    pg.screenshot(path=str(SHOTS / f"adm-{SHOTS_ONLY}-{name}-peticiones.png"), full_page=True)
                    ctx.close(); continue
                nav("Peticiones")
                pg.wait_for_selector(f".a-row:has-text('({eng} {name})')")
                check(pg.locator(".a-row.asking").count() >= 1, f"{tag}: the asking request is not flagged in the list")
                audit("peticiones")
                pg.screenshot(path=str(SHOTS / f"{eng}-{name}-peticiones.png"), full_page=True)
                # every destination in <=2 clicks from home
                for dest, ready in (("Peticiones", ".a-rows"), ("Ayuda", ".a-help")):
                    pg.goto(URL); pg.wait_for_selector("#a-msg"); nav(dest); pg.wait_for_selector(ready)
                    if dest == "Ayuda":
                        audit("ayuda")
                pg.goto(URL); pg.wait_for_selector("#a-msg"); nav("Peticiones")
                pg.locator(".a-row.asking").first.click(); pg.wait_for_selector(".a-askbar")  # 2 clicks: answer a question
                pg.wait_for_timeout(500)
                if not pg.locator("dialog.decide[open]").count():  # the question opens by itself; the bar reopens it
                    pg.click(".a-askbar")
                pg.wait_for_selector("dialog.decide[open]")
                audit("decision")
                pg.keyboard.press("Escape")
                pg.goto(URL); pg.wait_for_selector("#a-msg")
                pg.click(".a-chip >> nth=0"); pg.wait_for_selector(".a-ex button")  # ideas: 1 click
                nav("Pedir"); pg.wait_for_selector("#a-msg")
                check(not errs, f"{tag}: JS errors {errs}")
                print("ok", tag)
                ctx.close()
            # login page: multi-user instance (users.json present), shown before anyone signs in
            for name, ctxargs in (() if SHOTS_ONLY else (("mobile", phone), ("desktop", {"viewport": {"width": 1440, "height": 900}}))):
                ctx = b.new_context(**ctxargs, locale="es-ES"); pg = ctx.new_page()
                pg.goto(LOGIN_URL); pg.wait_for_selector("#u"); pg.wait_for_timeout(1500)
                a = pg.evaluate(AUDIT, name == "mobile")
                tag = f"{eng}/{name} login"
                check(a["over"] <= 0, f"{tag}: sideways scroll {a['over']}px")
                check(not a["small"], f"{tag}: text under 16px {a['small']}")
                check(not a["tiny"], f"{tag}: targets under 48px {a['tiny']}")
                info = pg.evaluate("[getComputedStyle(document.body).backgroundColor, document.fonts.check('16px Barlow'), document.body.innerText.includes('Contrase')]")
                check(info == ["rgb(244, 242, 238)", True, True], f"{tag}: paper bg / Barlow / Spanish copy, got {info}")
                if eng == "chrome":
                    pg.screenshot(path=str(SHOTS / f"login-after-{name}.png"), full_page=True)
                ctx.close()
            print("ok", eng, "login")
            b.close()
finally:
    srv.terminate(); lsrv.terminate()
    shutil.rmtree(TMP / "app", ignore_errors=True)
print("shots in", SHOTS)
if fails:
    print(len(fails), "failures"); sys.exit(1)
print("all ok")
