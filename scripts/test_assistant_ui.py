#!/usr/bin/env python3
"""UI check for the Flows Asistente web chat and the Plan de hoy page (Playwright, 390 and 1440). Runs server.py from a temp copy on a free port, HOME and data in a temp dir, a fake `claude` on PATH.
Run: /tmp/pwenv/bin/python scripts/test_assistant_ui.py   [shots dir as argv[1]]"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="flows-assistant-"))
BIN, LOG, HOME = TMP / "bin", TMP / "argv.log", TMP / "home"
BIN.mkdir()
(HOME / ".claude/flows-assistant").mkdir(parents=True)
(HOME / ".claude/flows-assistant/profile.md").write_text("Andrea likes short answers. PROFILE-MARK")
(BIN / "claude").write_text(f"""#!/usr/bin/env python3
import json, os, sys
open({str(LOG)!r}, "a").write(json.dumps(sys.argv + [os.environ.get("FLOWS_ASSISTANT", "")]) + "\\n")
if os.environ.get("FLOWS_BRAIN_TOKEN"):
    open({str(TMP / "token")!r}, "w").write(os.environ["FLOWS_BRAIN_TOKEN"])
out = lambda o: (print(json.dumps(o)), sys.stdout.flush())
def reply(text):
    out({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": text}}]}}}})
    out({{"type": "result", "is_error": False, "result": text, "total_cost_usd": 0}})
out({{"type": "system", "subtype": "init", "session_id": "fake"}})
n = 0
for line in sys.stdin:
    m = json.loads(line)
    if m.get("type") != "user":
        continue
    c = m["message"]["content"]
    if "EMAIL" in c:
        n += 1
        out({{"type": "control_request", "request_id": f"r{{n}}", "request": {{"subtype": "can_use_tool",
             "tool_name": "mcp__claude_ai_Gmail__send_message", "input": {{"to": "x@y.z"}}}}}})
        resp = json.loads(sys.stdin.readline())
        reply("mail " + resp["response"]["response"]["behavior"])
    else:
        reply("NOTHING" if "SILENT" in c else "echo: " + c)
""")
(BIN / "claude").chmod(0o755)
d = TMP / "app"
d.mkdir()
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, d / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "PATH": f"{BIN}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(HOME), "FLOWS_DATA": str(d / "data")})



from playwright.sync_api import sync_playwright
T = lambda n, g, due=None: {"name": n, "url": "https://trello.com/c/" + n, "group": g, "board": "B", "list": "L", "due": due, "new": g == "today"}
PLAN = {"day": "2026-10-12", "planned_at": time.time() - 3600, "checked": time.time(), "tasks": [T("Presupuesto", "overdue", "2026-10-10T10:00:00Z"), T("Maqueta", "today", "2026-10-12T10:00:00Z"), T("Factura", "week", "2026-10-15T10:00:00Z")]}
SHOTS = Path(sys.argv[1] if len(sys.argv) > 1 else TMP / "shots"); SHOTS.mkdir(parents=True, exist_ok=True)
try:
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", P), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    url = f"http://127.0.0.1:{P}/#assistant"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for name, ctxargs in (("390", p.devices["iPhone SE"] | {"viewport": {"width": 390, "height": 780}}), ("1440", {"viewport": {"width": 1440, "height": 900}})):
            ctx = b.new_context(**ctxargs); pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.goto(url); pg.wait_for_selector("#as-form")
            pg.fill("#as-msg", "hola"); pg.click("#as-form button")
            pg.wait_for_selector(".as-m.bot:has-text('echo: hola')", timeout=15000)
            pg.fill("#as-msg", "send EMAIL"); pg.click("#as-form button")
            pg.wait_for_selector(".as-m.ask >> nth=-1 >> button:has-text('Permitir')", timeout=15000)
            pg.screenshot(path=str(SHOTS / f"asistente-{name}.png"))
            pg.click(".as-m.ask >> nth=-1 >> button:has-text('Permitir')")
            pg.wait_for_function("[...document.querySelectorAll('.as-m.ask')].pop().textContent.includes('Permitido')")
            assert pg.locator(".as-m.ask >> nth=-1 >> button").count() == 0 and "permitido" in pg.locator(".as-m.ask").last.inner_text().lower()
            # answered from another client (fresh localStorage): this page syncs through the "resolved" item
            pg.fill("#as-msg", "send EMAIL 2"); pg.click("#as-form button")
            pg.wait_for_selector(".as-m.ask >> nth=-1 >> button:has-text('Denegar')", timeout=15000)
            ctx2 = b.new_context(**ctxargs); pg2 = ctx2.new_page(); pg2.goto(url)
            pg2.click(".as-m.ask >> nth=-1 >> button:has-text('Denegar')")
            pg.wait_for_function("[...document.querySelectorAll('.as-m.ask')].pop().textContent.includes('Denegado')", timeout=15000)
            assert pg.locator(".as-m.ask >> nth=-1 >> button").count() == 0; ctx2.close()
            pg.reload(); pg.wait_for_selector(".as-m.me"); assert pg.locator(".as-m.ask >> nth=-1 >> button").count() == 0  # answered state survives
            pg.on("dialog", lambda d: d.accept())
            assert pg.locator("#as-head button, #as-head a").count() == 1  # one header action: Ajustes
            pg.click("#as-head [data-act=asJobs]"); pg.wait_for_selector("#as-sheet[open] #as-cfg .as-sw")
            assert pg.locator("#as-sheet a[href^='#session/']").count() == 1 and not pg.is_visible("#as-jobform")  # new-task form folded
            pg.click("#as-sheet [data-act=asAuto]"); pg.wait_for_selector("#as-sheet .as-sw[aria-checked=true]"); assert pg.is_visible("#as-warn")
            pg.click("#as-sheet [data-act=asAuto]"); pg.wait_for_selector("#as-sheet .as-sw[aria-checked=false]")
            pg.click("#as-new summary"); pg.fill("[name=at]", "7:45"); pg.click(".as-day:has-text(\"L\")"); pg.fill("[name=prompt]", "Resumen de la mañana")
            pg.click("#as-jobform button.pri"); pg.wait_for_selector(".as-job:has-text('07:45')")
            pg.screenshot(path=str(SHOTS / f"asistente-tareas-{name}.png"))
            pg.click(".as-job:has-text('07:45') button"); pg.wait_for_selector(".as-job:has-text('07:45')", state="detached")
            small = pg.evaluate("[...document.querySelectorAll('#as-sheet button, #as-sheet a, #as-sheet summary, #as-sheet input:not([type=checkbox]), .as-day')].filter(e => e.offsetParent && e.offsetHeight < 48).map(e => e.className + e.offsetHeight)")
            assert not small, small
            pg.click("#as-sheet [data-act=asClose]")
            sw = pg.evaluate("[document.documentElement.scrollWidth, screen.width, innerWidth]"); assert sw[0] <= max(sw[1], sw[2]), sw
            small = pg.evaluate("[...document.querySelectorAll('.as button, .as a, .as textarea')].filter(e => e.offsetParent && (e.offsetHeight < 48)).map(e => e.className + e.offsetHeight)")
            assert not small, small
            assert pg.evaluate("Math.min(...[...document.querySelectorAll('.as-m p, .as-form textarea')].map(e => parseFloat(getComputedStyle(e).fontSize)))") >= 16
            # Plan de hoy: today's section open (overdue + today), next week folded, one meta line per card
            pg.route("**/api/plan", lambda r: r.fulfill(json=PLAN))
            pg.goto(url.replace("#assistant", "#plan")); pg.wait_for_selector(".pl-row")
            assert pg.locator(".pl-g h2").evaluate_all("l => l.map(e => e.textContent)") == ["Hoy 2", "Próximos 7 días 1"]
            assert not pg.is_visible(".pl-row:has-text('Factura')") and pg.locator(".pl-row small").first.inner_text().count("·") == 1
            pg.click("#pl-week summary"); assert pg.is_visible(".pl-row:has-text('Factura')")
            pg.screenshot(path=str(SHOTS / f"plan-{name}.png"), full_page=True)
            sw = pg.evaluate("[document.documentElement.scrollWidth, screen.width, innerWidth]"); assert sw[0] <= max(sw[1], sw[2]), sw
            small = pg.evaluate("[...document.querySelectorAll('.pl a, .pl summary')].filter(e => e.offsetHeight < 48).map(e => e.className + e.offsetHeight)")
            assert not small, small
            assert pg.evaluate("Math.min(...[...document.querySelectorAll('.pl-row span, .pl-sub')].map(e => parseFloat(getComputedStyle(e).fontSize)))") >= 15
            pg.unroute("**/api/plan"); pg.route("**/api/plan", lambda r: r.fulfill(json={**PLAN, "tasks": []}))
            pg.reload(); pg.wait_for_selector(".pl-none:has-text('Nada pendiente')")
            assert not errs, errs
            ctx.close()
        b.close()
    print("ok: test_assistant_ui")
finally:
    srv.terminate()
    shutil.rmtree(TMP, ignore_errors=True)
