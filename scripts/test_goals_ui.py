#!/usr/bin/env python3
"""UI check for the Goals page (Playwright, 390 and 1440). Own server.py instance from a temp copy; /api/goals* is mocked with page.route.
Second mode `e2e`: no mocks, the real goals() backend with the fake claude of scripts/test_goals.py (~1 min).
Run: /tmp/pwenv/bin/python scripts/test_goals_ui.py [shots dir] [e2e]"""
import json, os, re, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="flows-goals-"))
BIN, HOME = TMP / "bin", TMP / "home"; BIN.mkdir(); (HOME / "proj").mkdir(parents=True)
# the fake claude is the one in test_goals.py (taken from its source so the two stay in step)
(BIN / "claude").write_text(eval(re.search(r'\(BIN / "claude"\)\.write_text\((f""".*?""")\)', (REPO / "scripts/test_goals.py").read_text(), re.S).group(1), {"TMP": TMP}))
(BIN / "notify-send").write_text("#!/bin/sh\n")
for f in BIN.iterdir(): f.chmod(0o755)
d = TMP / "app"; d.mkdir()
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, d / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "PATH": f"{BIN}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(HOME), "FLOWS_DATA": str(d / "data")})
from playwright.sync_api import sync_playwright
args = [a for a in sys.argv[1:] if a != "e2e"]; E2E = "e2e" in sys.argv[1:]
SHOTS = Path(args[0] if args else TMP / "shots"); SHOTS.mkdir(parents=True, exist_ok=True)

def mock(page):
    G = {}
    def h(route):
        r = route.request; path = re.sub(r"^.*/api/goals", "", r.url.split("?")[0]).strip("/"); body = json.loads(r.post_data or "{}") if r.post_data else {}
        ok = lambda j, c=200: route.fulfill(status=c, content_type="application/json", body=json.dumps(j))
        if r.method == "GET" and not path: return ok([v for k, v in G.items() if k != "_"])
        if r.method == "POST" and not path:
            time.sleep(0.6)
            g = G["g1"] = {"id": "g1", "name": body["name"], "folder": body["folder"], "objective": body["objective"], "schedule": body.get("schedule"), "status": "intake",
                "questions": [{"id": "q1", "q": "¿Dónde está el Figma?", "hint": "Enlace al archivo"}, {"id": "q2", "q": "¿Qué backend usa?", "hint": ""}],
                "answers": {}, "acceptance": ["Compila sin errores", "Los tests pasan"], "iteration": 0, "max_iter": 5, "max_hours": 8, "run": "", "started": 0, "ended": 0, "history": [], "report": ""}
            return ok(g)
        id, _, what = path.partition("/"); g = G.get(id)
        if not g: return ok({"error": "not found"}, 404)
        if r.method == "DELETE": del G[id]; return ok({"ok": True})
        if r.method == "GET": return ok(g)
        if what == "answers": g.update(status="ready", answers=body["answers"], acceptance=body["acceptance"])
        elif what == "start": g.update(status="running", iteration=1, run="r1", started=time.time() - 600)
        elif what == "stop": g.update(status="stopped")
        elif what == "schedule": g["schedule"] = body["schedule"]
        elif what == "message": g["status"] = "running"; G.setdefault("_", {})["msg"] = body["text"]
        return ok(g)
    page.route("**/api/goals**", h)
    return G

try:
    for _ in range(50):
        try: socket.create_connection(("127.0.0.1", P), 0.2).close(); break
        except OSError: time.sleep(0.1)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for name, ca in (("390", p.devices["iPhone SE"] | {"viewport": {"width": 390, "height": 780}}), ("1440", {"viewport": {"width": 1440, "height": 900}})):
            ctx = b.new_context(**ca); pg = ctx.new_page(); errs = []
            pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda dl: dl.accept())
            if E2E:
                pg.goto(f"http://127.0.0.1:{P}/#goals/new")
                pg.fill("[name=name]", "Sonora " + name); pg.fill("[name=folder]", str(HOME / "proj")); pg.fill("[name=objective]", f"Build it TAG-{name}")
                pg.click("#gl-go"); pg.wait_for_selector("#gl-ans", timeout=60000)
                assert pg.locator("#gl-ans textarea").count() == 2 and pg.locator(".gl-acc").count() == 2
                pg.fill("[name=figma]", "https://figma.com/f/1"); pg.fill("[name=api]", "https://api.x")
                pg.click("#gl-ans .pri"); pg.click("[data-act=glStart]", timeout=10000)
                pg.wait_for_selector(".gl-pill[data-s=done]", timeout=120000)  # verifier fails once, iteration 2 passes (worker ticks every 20 s)
                pg.wait_for_selector(".gl-h.fail"); pg.wait_for_selector(".gl-h.pass"); assert pg.locator(".gl-h").count() == 2
                assert "goal/sonora-" in pg.inner_text(".gl-sub"), pg.inner_text(".gl-sub"); assert pg.locator(".gl a[href^='#session/']").count() == 1
                pg.screenshot(path=str(SHOTS / f"goals-e2e-done-{name}.png"), full_page=True)
                sw = pg.evaluate("[document.documentElement.scrollWidth, screen.width, innerWidth]"); assert sw[0] <= max(sw[1], sw[2]), sw
                assert not errs, errs; ctx.close(); continue
            G = mock(pg)
            pg.goto(f"http://127.0.0.1:{P}/#goals"); pg.wait_for_selector(".gl h1:has-text('Goals')"); pg.wait_for_selector(".gl-list .note")
            pg.click("a:has-text('Nuevo goal')")
            pg.fill("[name=name]", "Desarrollar Sonora"); pg.fill("[name=objective]", "Haz Sonora con el Figma y el backend"); pg.click(".gl-opt summary")
            pg.fill("[name=at]", "08:30"); pg.click(".as-day:has-text('L')")
            pg.click("#gl-go"); pg.wait_for_selector("#gl-busy:visible"); assert pg.is_disabled("#gl-go")
            pg.wait_for_selector("#gl-ans"); pg.screenshot(path=str(SHOTS / f"goals-intake-{name}.png"), full_page=True)
            pg.fill("[name=q1]", "figma.com/x"); pg.fill("[name=q2]", "Flask")
            pg.click("[data-act=glAccAdd]"); pg.locator(".gl-acc input").last.fill("Sin errores en consola"); pg.locator(".gl-acc [data-act=glAccDel]").first.click()
            assert pg.locator(".gl-acc").count() == 2
            pg.click("#gl-ans .pri"); pg.wait_for_selector("[data-act=glStart]"); assert G["g1"]["answers"]["q1"] == "figma.com/x" and "Los tests pasan" in G["g1"]["acceptance"]
            pg.click("[data-act=glStart]"); pg.wait_for_selector(".gl-pill[data-s=running]"); assert pg.locator("a[href='#session/r1']").count() == 1
            G["g1"].update(status="verifying", iteration=2, history=[{"n": 1, "verdict": "fail", "summary": "Faltan tests", "failing": ["Los tests pasan"], "ts": time.time()}])
            pg.wait_for_selector(".gl-pill[data-s=verifying]", timeout=12000); pg.wait_for_selector(".gl-h.fail")
            G["g1"].update(status="blocked")
            pg.wait_for_selector(".gl-pill[data-s=blocked]", timeout=12000); pg.fill("#gl-msg", "usa la clave X"); pg.screenshot(path=str(SHOTS / f"goals-blocked-{name}.png"), full_page=True)
            pg.click("#gl-say .pri"); pg.wait_for_selector(".gl-pill[data-s=running]"); assert G["_"]["msg"] == "usa la clave X"
            G["g1"].update(status="done", iteration=2, ended=time.time(), report="## Informe\n\n- **Hecho**: todo pasa\n", history=G["g1"]["history"] + [{"n": 2, "verdict": "pass", "summary": "Todo correcto", "failing": [], "ts": time.time()}])
            pg.wait_for_selector(".gl-pill[data-s=done]", timeout=12000); pg.wait_for_selector(".gl-rep h2:has-text('Informe')"); assert pg.locator(".gl-h").count() == 2
            pg.screenshot(path=str(SHOTS / f"goals-detail-{name}.png"), full_page=True)
            pg.click("[data-act=glSched]"); pg.fill("#gl-sheet [name=at]", ""); pg.click("#gl-sheet .pri"); pg.wait_for_function("!document.querySelector('#gl-sheet[open]')")
            assert G["g1"]["schedule"] is None
            pg.goto(f"http://127.0.0.1:{P}/#goals"); pg.wait_for_selector(".gl-row"); pg.screenshot(path=str(SHOTS / f"goals-list-{name}.png"), full_page=True)
            sw = pg.evaluate("[document.documentElement.scrollWidth, screen.width, innerWidth]"); assert sw[0] <= max(sw[1], sw[2]), sw
            pg.click(".gl-row"); pg.wait_for_selector("[data-act=glDel]")
            small = pg.evaluate("[...document.querySelectorAll('.gl button, .gl a, .gl input, .gl textarea')].filter(e => e.offsetParent && e.offsetHeight < 44 && !e.closest('summary')).map(e => e.tagName + e.className + e.offsetHeight)")
            assert not small, small
            pg.click("[data-act=glDel]"); pg.wait_for_selector(".gl-list .note"); assert "g1" not in G
            assert not errs, errs
            ctx.close()
        b.close()
    print("ok: test_goals_ui" + (" e2e" if E2E else ""))
finally:
    srv.terminate(); shutil.rmtree(TMP, ignore_errors=True)
