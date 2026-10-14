#!/usr/bin/env python3
"""Dev package session view at 390 (iPhone, isMobile) and 1440: user/agent bubbles with distinct classes, tool steps folded
into closed groups that open/close by click and Enter, the live group names the step running now, status chip in the header,
no horizontal overflow, text >=16px, targets >=48px, and a pending decision opens a usable dialog.
Same temp-server + mocks as shots_dev.py. Run: /tmp/pwenv/bin/python scripts/test_dev_session.py  (exit 0 = ok)"""
import os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright
REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hadiya-sess-"))
(TMP / "bin").mkdir(); (TMP / "home").mkdir(); (TMP / "app").mkdir()
(TMP / "bin/claude").write_text("#!/bin/sh\nexit 0\n"); (TMP / "bin/claude").chmod(0o755)
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, TMP / "app" / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=TMP / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "PATH": f"{TMP / 'bin'}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(TMP / "home"), "HADIYA_DATA": str(TMP / "app/data")})
NOW, SID = time.time(), "20261012-120000-aaaa"
RUN = {"id": SID, "kind": "session", "owner": None, "name": "Rediseño de la tienda: catálogo y ficha de producto", "status": "working", "started": NOW - 900,
       "ended": None, "cost": 0.42, "session_id": "s", "project": "/home/andrea/Desktop/flows", "parent": None, "turn_done": False, "pending": {}, "subs": []}
def tool(n, name, inp, out):
    return [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{n}", "name": name, "input": inp}]}},
            {"type": "user", "message": {"content": [{"tool_use_id": f"t{n}", "type": "tool_result", "content": out}]}}]
def say(t): return {"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}}
EV = [{"type": "input", "text": "Rediseña el catálogo: tarjetas más claras y filtros arriba."}, say("Voy a mirar cómo está montado el catálogo."),
      *tool(1, "Glob", {"pattern": "src/**/*.tsx"}, "src/Catalog.tsx\nsrc/Product.tsx"), *tool(2, "Read", {"file_path": "src/Catalog.tsx"}, "export function Catalog() {}"),
      say("Propongo:\n\n- **Tarjetas** con foto y precio\n- **Filtros** arriba"),
      {"type": "result", "is_error": False, "result": "ok", "total_cost_usd": 0.42, "num_turns": 6, "duration_ms": 84000},
      {"type": "input", "text": "Sí, sigue con la ficha."}, say("Empiezo por la galería de fotos."),
      *tool(3, "Read", {"file_path": "src/Product.tsx"}, "export function Product() {}"), *tool(4, "Bash", {"command": "npm test -- product"}, "PASS")]
ASK = {"q": {"id": "q", "ts": NOW, "tool": "AskUserQuestion", "input": {"questions": [{"header": "Diseño", "question": "¿Qué paleta usamos?", "options": [{"label": "Papel claro"}, {"label": "Oscura"}]}]}}}
state = {"pending": {}}
def detail(r): r.fulfill(json={**RUN, "pending": state["pending"], "events": EV[int(parse_qs(urlparse(r.request.url).query).get("since", ["0"])[0]):], "total": len(EV), "config": {"permission_mode": "acceptEdits", "agents": 3, "cwd": "/home/andrea/Desktop/flows", "model": "opus"}})
SMALL = """sel => [...document.querySelectorAll(sel)].filter(e => e.offsetParent || e.closest('dialog[open]')).flatMap(e => {
  const r = e.getBoundingClientRect();
  return r.width && r.height && Math.min(r.width, r.height) < 48 ? [`${e.tagName}.${e.className} '${e.textContent.trim().slice(0, 20)}' ${Math.round(r.width)}x${Math.round(r.height)}`] : []; })"""
TINY = """sel => [...document.querySelectorAll(sel)].flatMap(root => [...root.querySelectorAll('*')]).filter(e =>
  e.checkVisibility() && e.getBoundingClientRect().width > 1 && [...e.childNodes].some(n => n.nodeType == 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 16)
  .map(e => `${e.tagName}.${e.className} '${e.textContent.trim().slice(0, 20)}' ${getComputedStyle(e).fontSize}`)"""
fails = []
def check(ok, msg):
    if not ok: fails.append(msg); print("FAIL", msg)
try:
    for _ in range(50):
        try: socket.create_connection(("127.0.0.1", P), 0.2).close(); break
        except OSError: time.sleep(0.1)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for size, ctxargs in (("390", p.devices["iPhone 13"] | {"viewport": {"width": 390, "height": 844}}), ("1440", {"viewport": {"width": 1440, "height": 900}})):
            ctx = b.new_context(**ctxargs); pg = ctx.new_page(); state["pending"] = {}
            pg.route("**/api/runs", lambda r: r.fulfill(json=[{**RUN, "pending": state["pending"]}]))
            pg.route(f"**/api/runs/{SID}*", detail)
            pg.goto(f"http://127.0.0.1:{P}/#session/{SID}"); pg.wait_for_selector(".logbox .say", timeout=15000); pg.wait_for_timeout(800)
            # bubbles: mine right and tinted, agent left on a card, markdown rendered
            me, ag = pg.locator(".log .me .you"), pg.locator(".log .say")
            check(me.count() == 2 and ag.count() == 3, f"{size}: {me.count()} user / {ag.count()} agent bubbles")
            bx = pg.evaluate("""() => { const u = document.querySelector('.log .you').getBoundingClientRect(), a = document.querySelector('.log .say').getBoundingClientRect(),
                l = document.querySelector('.logbox').getBoundingClientRect(), cs = e => getComputedStyle(document.querySelector(e)).backgroundColor;
                return {uRight: l.right - u.right, aLeft: a.left - l.left, ub: cs('.log .you'), ab: cs('.log .say')} }""")
            check(bx["uRight"] < 80 and bx["aLeft"] < 30 and bx["ub"] != bx["ab"], f"{size}: bubbles not right/left/distinct {bx}")
            check(pg.locator(".log .say :is(strong,b)").count() == 2, f"{size}: markdown not rendered")
            # steps: every group folded; the live one names the current step
            tr = pg.locator(".log .trail")
            check(tr.count() == 2 and pg.locator(".log .trail[open]").count() == 0, f"{size}: {tr.count()} step groups, {pg.locator('.log .trail[open]').count()} open")
            check(pg.locator(".log > .tool").count() == 0, f"{size}: loose tool rows outside a group")
            check("Now:" in tr.last.locator(":scope > summary").inner_text() and "npm test" in tr.last.locator(":scope > summary").inner_text(), f"{size}: live group says {tr.last.locator(':scope > summary').inner_text()!r}")
            s0 = tr.first.locator(":scope > summary")
            s0.click(); pg.wait_for_timeout(200); check(tr.first.evaluate("e => e.open"), f"{size}: click did not open the steps")
            s0.click(); pg.wait_for_timeout(200); check(not tr.first.evaluate("e => e.open"), f"{size}: click did not close the steps")
            s0.focus(); pg.keyboard.press("Enter"); pg.wait_for_timeout(200); check(tr.first.evaluate("e => e.open"), f"{size}: Enter did not open the steps")
            check(tr.first.locator(".tool").first.is_visible(), f"{size}: opened group shows no steps")
            pg.wait_for_timeout(2500); check(tr.first.evaluate("e => e.open"), f"{size}: opened group snapped shut on the live redraw")
            pg.keyboard.press("Enter"); pg.wait_for_timeout(200); check(not tr.first.evaluate("e => e.open"), f"{size}: Enter did not close the steps")
            # status chip
            chip = pg.locator("#s-head .hchip")
            check(chip.is_visible() and "Working" in chip.inner_text() and "npm test" in chip.inner_text(), f"{size}: status chip {chip.inner_text() if chip.count() else None!r}")
            if size == "390":  # page scrolls on phones: the header (and chip) must stay on screen
                pg.evaluate("scrollTo(0, document.documentElement.scrollHeight)"); pg.wait_for_timeout(300)
                check(chip.bounding_box()["y"] >= 0, f"390: status chip scrolled away")
                pg.evaluate("scrollTo(0, 0)")
            w = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"); check(w[0] <= w[1], f"{size}: horizontal overflow {w}")
            check(not (s := pg.evaluate(TINY, "#s-head, #s-body, #composer")), f"{size}: text <16px {s}")
            check(not (s := pg.evaluate(SMALL, "#s-head button, #s-head a, #s-body button, #s-body summary, #composer button, #composer textarea")), f"{size}: targets <48px {s}")
            # ⋯ Session menu
            pg.click(".setbtn"); pg.wait_for_timeout(300)
            w = pg.evaluate("[document.documentElement.scrollWidth, innerWidth]"); check(w[0] <= w[1], f"{size} Session menu: overflow {w}")
            check(not (s := pg.evaluate(SMALL, "#s-set button, #s-set select, #s-set input")), f"{size} Session menu: targets <48px {s}")
            pg.keyboard.press("Escape"); pg.wait_for_timeout(300)
            # a pending question: dialog visible, usable
            state["pending"] = ASK; pg.wait_for_selector("#decide[open]", timeout=10000); pg.wait_for_timeout(300)
            d = pg.evaluate("(d => { const r = d.getBoundingClientRect(); return {in: r.left >= 0 && r.right <= innerWidth + 1 && r.top >= 0, sw: d.scrollWidth, cw: d.clientWidth} })(document.querySelector('#decide'))")
            check(d["in"] and d["sw"] <= d["cw"], f"{size}: decision dialog {d}")
            check(not (s := pg.evaluate(SMALL, "#decide button, #decide label.opt")), f"{size} decision: targets <48px {s}")
            ctx.close()
        b.close()
finally:
    srv.terminate(); shutil.rmtree(TMP, ignore_errors=True)
print("ok" if not fails else f"{len(fails)} failures"); sys.exit(1 if fails else 0)
