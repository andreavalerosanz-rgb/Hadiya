#!/usr/bin/env python3
"""Plan and Asistente as visual components, at 390 (iPhone, isMobile) and 1440: task cards with status chips in collapsible
timeline sections (today open, week folded), chat bubbles (you / assistant), notice + approval cards with chips, the latest
turn's tool calls as a collapsible steps card, the assistant status chip. Layout: no overflow vs screen width, text >=16px,
targets >=48px, Barlow, paper. Interaction: sections/steps toggle by click and keyboard and keep their state across redraws;
approving a card flips its chip. Same temp server + mocks as shots_dev.py. Run: /tmp/pwenv/bin/python scripts/test_dev_plan_assistant.py"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="flows-pa-"))
(TMP / "bin").mkdir(); (TMP / "home").mkdir(); (TMP / "app").mkdir()
(TMP / "bin/claude").write_text("#!/bin/sh\nexit 0\n"); (TMP / "bin/claude").chmod(0o755)
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, TMP / "app" / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=TMP / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "PATH": f"{TMP / 'bin'}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(TMP / "home"), "FLOWS_DATA": str(TMP / "app/data")})
NOW = time.time()
T = lambda n, g, due=None: {"name": n, "url": "https://trello.com/c/x", "group": g, "board": "Clientes", "list": "Haciendo", "due": due, "new": False}
PLAN = {"day": time.strftime("%Y-%m-%d"), "planned_at": NOW - 3600, "checked": NOW, "tasks": [
    T("Presupuesto Sonora", "overdue", "2026-10-10T10:00:00Z"), T("Maqueta home BFS", "today", "2026-10-12T10:00:00Z"),
    T("Llamar a Dr. Zhang", "doing"), T("Enviar copia a BFS", "done", "2026-10-12T08:00:00Z"), T("Factura Matteria", "week", "2026-10-15T10:00:00Z")]}
OUTBOX = [{"id": 1, "type": "reply", "text": "Hoy tienes **3 reuniones**.", "ts": NOW - 4000},
          {"id": 2, "type": "notice", "text": "Brief: todo en orden.", "ts": NOW - 3000},
          {"id": 3, "type": "approval", "text": "¿Envío el presupuesto a Sonora?", "ts": NOW - 60, "approval_id": "a1"}]
RUN = "20261012-080000-asis"
tool = lambda n, name, inp: {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{n}", "name": name, "input": inp}]}}
EV = [{"type": "input", "text": "qué tengo hoy", "ts": NOW - 120}, tool(1, "mcp__claude_ai_Google_Calendar__list_events", {"query": "hoy"}), tool(2, "Read", {"file_path": "/tmp/a.md"})]
MINE = [{"text": "qué tengo hoy", "ts": NOW - 4100}]
approved = []

def mock(pg):
    pg.route("**/api/plan", lambda r: r.fulfill(json=PLAN))
    pg.route("**/api/assistant/outbox*", lambda r: r.fulfill(json=OUTBOX if "since=0" in r.request.url else []) if "wait=0" in r.request.url else (time.sleep(1), r.fulfill(json=[]))[1])
    pg.route("**/api/assistant/settings", lambda r: r.fulfill(json={"auto": True, "jobs": [], "run": RUN}))
    pg.route("**/api/assistant/approve", lambda r: (approved.append(json.loads(r.request.post_data)), r.fulfill(json={"ok": True}))[1])
    pg.route(f"**/api/runs/{RUN}*", lambda r: r.fulfill(json={"id": RUN, "status": "working", "total": len(EV), "events": EV[int(r.request.url.partition("since=")[2] or 0):]}))

SMALL = """sel => [...document.querySelectorAll(sel)].filter(e => e.offsetParent).map(e => [e, e.getBoundingClientRect()])
  .filter(([e, r]) => Math.min(r.width, r.height) < 48).map(([e, r]) => `${e.tagName}.${e.className} ${Math.round(r.width)}x${Math.round(r.height)}`)"""
TINY = """sel => [...document.querySelectorAll(sel)].flatMap(root => [...root.querySelectorAll('*')]).filter(e =>
  e.offsetParent && e.getBoundingClientRect().width > 1 && [...e.childNodes].some(n => n.nodeType == 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 16)
  .map(e => `${e.tagName}.${e.className} '${e.textContent.trim().slice(0, 20)}' ${getComputedStyle(e).fontSize}`)"""
fails = []
def check(ok, msg):
    if not ok: fails.append(msg); print("FAIL", msg)
def layout(pg, where, root):
    w = pg.evaluate("[document.documentElement.scrollWidth, screen.width, innerWidth]")
    check(w[0] <= min(w[1], w[2]), f"{where}: horizontal overflow {w}")
    st = pg.evaluate("[getComputedStyle(document.body).fontFamily, getComputedStyle(document.body).backgroundColor]")
    check("Barlow" in st[0] and st[1] == "rgb(244, 242, 238)", f"{where}: font/background {st}")
    check(not (s := pg.evaluate(TINY, root)), f"{where}: text <16px {s}")
    check(not (s := pg.evaluate(SMALL, f"{root} a, {root} button, {root} summary, {root} textarea")), f"{where}: targets <48px {s}")
opened = lambda pg, sel: pg.evaluate(f"document.querySelector('{sel}').open")

try:
    for _ in range(50):
        try: socket.create_connection(("127.0.0.1", P), 0.2).close(); break
        except OSError: time.sleep(0.1)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for size, ctxargs in (("390", p.devices["iPhone 13"] | {"viewport": {"width": 390, "height": 844}}), ("1440", {"viewport": {"width": 1440, "height": 900}})):
            ctx = b.new_context(**ctxargs); pg = ctx.new_page(); mock(pg); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            # ---- Plan
            pg.goto(f"http://127.0.0.1:{P}/#plan"); pg.wait_for_selector(".pl-row", timeout=15000)
            check(pg.eval_on_selector_all("details.pl-g", "l => l.map(e => e.id)") == ["pl-today", "pl-done", "pl-week"], f"{size} plan: section order")
            check(opened(pg, "#pl-today") and not opened(pg, "#pl-week") and not opened(pg, "#pl-done"), f"{size} plan: today open, rest folded")
            chips = pg.eval_on_selector_all("#pl-today .pl-row .stc", "l => l.map(e => e.dataset.s + ':' + e.textContent)")
            check(chips == ["overdue:Vencida", "today:Hoy", "doing:En curso"], f"{size} plan: chips {chips}")
            check(pg.locator("#pl-today ol.tl > li .tl-at").count() == 3, f"{size} plan: timeline markers")
            layout(pg, f"{size} plan", ".pl")
            pg.click("#pl-week summary"); pg.focus("#pl-done summary"); pg.keyboard.press("Enter"); pg.focus("#pl-today summary"); pg.keyboard.press("Space")
            check(opened(pg, "#pl-week") and opened(pg, "#pl-done") and not opened(pg, "#pl-today"), f"{size} plan: click/keyboard toggles")
            check(pg.locator("#pl-done .stc[data-s=done]").inner_text() == "Hecha" and pg.locator("#pl-week .stc").inner_text() == "Planificada", f"{size} plan: done/planned chips")
            layout(pg, f"{size} plan open", ".pl")
            pg.evaluate("clearTimeout(timer); planPage()"); pg.wait_for_timeout(500)
            check(opened(pg, "#pl-week") and opened(pg, "#pl-done") and not opened(pg, "#pl-today"), f"{size} plan: state kept after redraw")
            # ---- Asistente
            pg.evaluate(f"localStorage.setItem('flows.as.mine', {json.dumps(json.dumps(MINE))}); localStorage.removeItem('flows.as.ans')")
            pg.goto(f"http://127.0.0.1:{P}/#assistant"); pg.wait_for_selector(".as-steps", timeout=15000)
            check(pg.locator(".as-m.me").count() == 1 and pg.locator(".as-m.bot").count() == 1, f"{size} as: bubbles")
            bx = [pg.locator(s).bounding_box() for s in (".as-m.me", ".as-m.bot", "#as-list")]
            check(bx[0]["x"] + bx[0]["width"] > bx[2]["x"] + bx[2]["width"] - 2 and bx[1]["x"] < bx[2]["x"] + 2, f"{size} as: you right, assistant left")
            check(pg.evaluate("getComputedStyle(document.querySelector('.as-m.me')).backgroundColor") != pg.evaluate("getComputedStyle(document.querySelector('.as-m.bot')).backgroundColor"), f"{size} as: bubble colours")
            check(pg.locator(".as-card.note .stc").inner_text() == "Aviso", f"{size} as: notice chip")
            check(pg.locator(".as-card.ask .stc[data-s=pending]").inner_text() == "Pendiente", f"{size} as: approval pending chip")
            st = pg.eval_on_selector_all("#as-st .stc", "l => l.map(e => e.textContent)")
            check(st == ["Trabajando", "Full auto"], f"{size} as: status {st}")
            check(pg.locator(".as-steps .tl > li").count() == 2 and not opened(pg, "#as-steps"), f"{size} as: 2 folded steps")
            order = pg.eval_on_selector_all("#as-list > *", "l => l.map(e => e.className.split(' ').pop())")
            check(order == ["me", "bot", "note", "as-steps", "ask"], f"{size} as: steps after the turn that started them {order}")
            layout(pg, f"{size} as", ".as")
            pg.click("#as-steps summary"); check(opened(pg, "#as-steps"), f"{size} as: steps open on click")
            pg.evaluate("asDraw()"); check(opened(pg, "#as-steps"), f"{size} as: steps open after redraw")
            pg.focus("#as-steps summary"); pg.keyboard.press("Enter"); check(not opened(pg, "#as-steps"), f"{size} as: steps close by keyboard")
            pg.evaluate("asDraw()"); check(not opened(pg, "#as-steps"), f"{size} as: steps closed after redraw")
            pg.keyboard.press("Tab"); pg.focus("#as-steps summary"); pg.keyboard.press("Space"); check(opened(pg, "#as-steps"), f"{size} as: steps open by Space")
            layout(pg, f"{size} as steps open", ".as")
            pg.click(".as-card.ask button:has-text('Permitir')")
            pg.wait_for_selector(".as-card.ask .stc[data-s=allow]", timeout=5000)
            check(pg.locator(".as-card.ask .stc").inner_text() == "Permitido" and pg.locator(".as-card.ask button").count() == 0, f"{size} as: approved chip")
            check(approved[-1] == {"approval_id": "a1", "allow": True}, f"{size} as: approve request {approved[-1:]}")
            check(not errs, f"{size}: page errors {errs}")
            ctx.close()
        b.close()
finally:
    srv.terminate(); shutil.rmtree(TMP, ignore_errors=True)
print("ok" if not fails else f"{len(fails)} failures"); sys.exit(1 if fails else 0)
