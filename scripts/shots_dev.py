#!/usr/bin/env python3
"""Screenshots of the dev package (home, one session, #plan, #assistant) at 390 (iPhone, isMobile) and 1440.
Runs server.py + index.html from the working tree in a temp copy (own port, HOME, data, fake `claude`); runs, plan and
assistant outbox are mocked with page.route so every page has content.
Run: /tmp/pwenv/bin/python scripts/shots_dev.py before|after [home session plan assistant]   -> data/shots/<prefix>-{home,session,plan,assistant}-{390,1440}.png"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "after"
OUT = REPO / "data" / "shots"; OUT.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="hadiya-shots-"))
(TMP / "bin").mkdir(); (TMP / "home").mkdir(); (TMP / "app").mkdir()
(TMP / "bin/claude").write_text("#!/bin/sh\nexit 0\n"); (TMP / "bin/claude").chmod(0o755)
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, TMP / "app" / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=TMP / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "PATH": f"{TMP / 'bin'}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(TMP / "home"), "HADIYA_DATA": str(TMP / "app/data")})

NOW = time.time()
def run(i, name, status, ago, **kw):
    return {"id": i, "kind": "session", "owner": None, "name": name, "status": status, "started": NOW - ago, "ended": None if status in ("working", "asking") else NOW - ago + 600,
            "cost": 0.42, "session_id": "s-" + i, "project": "/home/andrea/Desktop/flows", "parent": None, "turn_done": status != "working", "pending": {}, "subs": [], **kw}
SID = "20261012-120000-aaaa"
ASK = {"q": {"id": "q", "ts": NOW, "tool": "AskUserQuestion", "input": {"questions": [{"header": "Diseño", "question": "¿Qué paleta usamos para la web?", "options": [{"label": "Papel claro"}, {"label": "Oscura"}]}]}}}
RUNS = [run(SID, "Rediseño de la tienda: catálogo y ficha de producto", "working", 900, last="Empiezo por la galería de fotos."),
        run("20261012-110000-bbbb", "Factura de octubre para Matteria", "asking", 3000, pending=ASK, last="¿Qué paleta usamos para la web?"),
        run("20261012-100000-cccc", "Revisar el formulario de contacto", "idle", 7000, last="Hecho: el formulario valida el correo y envía una copia al cliente."),
        run("20261011-090000-dddd", "Copia de seguridad del servidor", "stopped", 90000, last="Copia guardada en /backups (2,3 GB)."),
        run("20261010-090000-eeee", "Migrar la base de datos de BFS", "stopped", 180000)]
def tool(n, name, inp, out):
    return [{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{n}", "name": name, "input": inp}]}},
            {"type": "user", "message": {"content": [{"tool_use_id": f"t{n}", "type": "tool_result", "content": out}]}}]
def say(t): return {"type": "assistant", "message": {"content": [{"type": "text", "text": t}]}}
EV = [{"type": "input", "text": "Rediseña el catálogo de la tienda: tarjetas más claras, filtros arriba y la ficha de producto con fotos grandes."},
      say("Voy a mirar cómo está montado el catálogo ahora."),
      *tool(1, "Glob", {"pattern": "src/**/*.tsx"}, "src/Catalog.tsx\nsrc/Product.tsx\nsrc/Filters.tsx"),
      *tool(2, "Read", {"file_path": "src/Catalog.tsx"}, "export function Catalog() {\n  return <Grid items={items} />\n}"),
      say("El catálogo usa una rejilla fija de 4 columnas. Propongo:\n\n- **Tarjetas** con foto, nombre y precio\n- **Filtros** en una barra arriba\n- Ficha con galería a pantalla completa"),
      *tool(3, "Edit", {"file_path": "src/Catalog.tsx", "old_string": "<Grid", "new_string": "<CardGrid"}, "ok"),
      *tool(4, "Bash", {"command": "npm test -- catalog", "description": "Run catalog tests"}, "PASS src/Catalog.test.tsx (6 tests)"),
      say("Hecho: el catálogo usa tarjetas nuevas y los tests pasan. ¿Sigo con la ficha de producto?"),
      {"type": "result", "is_error": False, "result": "ok", "total_cost_usd": 0.42, "num_turns": 6, "duration_ms": 84000},
      {"type": "input", "text": "Sí, sigue con la ficha."},
      say("Empiezo por la galería de fotos."),
      *tool(5, "Read", {"file_path": "src/Product.tsx"}, "export function Product() {}")]
DETAIL = {**RUNS[0], "events": EV, "config": {"permission_mode": "acceptEdits", "agents": 3, "cwd": "/home/andrea/Desktop/flows", "model": "opus"}, "total": len(EV)}
T = lambda n, g, due=None: {"name": n, "url": "https://trello.com/c/" + n, "group": g, "board": "Clientes", "list": "Haciendo", "due": due, "new": g == "today"}
PLAN = {"day": time.strftime("%Y-%m-%d"), "planned_at": NOW - 3600, "checked": NOW, "tasks": [
    T("Presupuesto Sonora", "overdue", "2026-10-10T10:00:00Z"), T("Maqueta home BFS", "today", "2026-10-12T10:00:00Z"),
    T("Llamar a Dr. Zhang", "doing"), T("Enviar copia a BFS", "done", "2026-10-12T08:00:00Z"), T("Factura Matteria", "week", "2026-10-15T10:00:00Z")]}
OUTBOX = [{"id": 1, "type": "reply", "text": "Buenos días. Hoy tienes **3 reuniones** y 2 correos importantes.", "ts": NOW - 4000},
          {"id": 2, "type": "notice", "text": "Brief de la mañana: el servidor de BFS respondió bien toda la noche.", "ts": NOW - 3000},
          {"id": 3, "type": "approval", "text": "¿Respondo a Matteria que la factura sale el lunes?", "ts": NOW - 2000, "approval_id": "a0"},
          {"id": 5, "type": "resolved", "approval_id": "a0", "allow": True, "ts": NOW - 1900},
          {"id": 4, "type": "approval", "text": "Quiero enviar el presupuesto a Sonora por correo. ¿Lo envío?", "ts": NOW - 60, "approval_id": "a1"}]

ASRUN = "20261012-080000-asis"
ASEV = [{"type": "input", "text": "qué tengo hoy", "ts": NOW - 120},
        *tool(6, "mcp__claude_ai_Google_Calendar__list_events", {"query": "hoy"}, "3 eventos"),
        *tool(7, "mcp__claude_ai_Gmail__search_threads", {"query": "is:unread"}, "2 hilos")]
ASDETAIL = {"id": ASRUN, "status": "working", "events": ASEV, "total": len(ASEV)}

def mock(pg):
    pg.route("**/api/assistant/settings", lambda r: r.fulfill(json={"auto": False, "jobs": [], "run": ASRUN}))
    pg.route(f"**/api/runs/{ASRUN}*", lambda r: r.fulfill(json={**ASDETAIL, "events": ASEV[int(r.request.url.partition("since=")[2] or 0):]}))
    pg.route("**/api/runs", lambda r: r.fulfill(json=RUNS))
    pg.route(f"**/api/runs/{SID}*", lambda r: r.fulfill(json={**DETAIL, "events": EV[int(parse_qs(urlparse(r.request.url).query).get("since", ["0"])[0]):]}))  # the client appends: send only new events
    pg.route("**/api/plan", lambda r: r.fulfill(json=PLAN))
    pg.route("**/api/assistant/outbox*", lambda r: r.fulfill(json=OUTBOX if "since=0" in r.request.url or "since=" not in r.request.url else []))

PAGES = [("home", "", "main"), ("session", f"#session/{SID}", ".logbox"), ("plan", "#plan", ".pl-row"), ("assistant", "#assistant", ".as-steps")]
PAGES = [x for x in PAGES if len(sys.argv) < 3 or x[0] in sys.argv[2:]]  # optional page names after the prefix
try:
    for _ in range(50):
        try: socket.create_connection(("127.0.0.1", P), 0.2).close(); break
        except OSError: time.sleep(0.1)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for size, ctxargs in (("390", p.devices["iPhone 13"] | {"viewport": {"width": 390, "height": 844}}), ("1440", {"viewport": {"width": 1440, "height": 900}})):
            ctx = b.new_context(**ctxargs); pg = ctx.new_page(); mock(pg)
            for name, h, sel in PAGES:
                pg.goto(f"http://127.0.0.1:{P}/{h}"); pg.wait_for_selector(sel, timeout=15000); pg.wait_for_timeout(1200)
                f = OUT / f"{PREFIX}-{name}-{size}.png"; pg.screenshot(path=str(f)); print(f)
            ctx.close()
        b.close()
finally:
    srv.terminate(); shutil.rmtree(TMP, ignore_errors=True)
