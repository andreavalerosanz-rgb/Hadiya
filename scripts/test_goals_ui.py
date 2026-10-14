#!/usr/bin/env python3
"""UI check for the Goals page (Playwright, 390 and 1440). Own server.py instance from a temp copy; /api/goals* is mocked with page.route.
Second mode `e2e`: no mocks, the real goals() backend with the fake claude of scripts/test_goals.py (~1 min).
Run: /tmp/pwenv/bin/python scripts/test_goals_ui.py [shots dir] [e2e]"""
import json, os, re, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hadiya-goals-"))
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
                       env={**os.environ, "PATH": f"{BIN}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(HOME), "HADIYA_DATA": str(d / "data")})
from playwright.sync_api import sync_playwright
args = [a for a in sys.argv[1:] if a != "e2e"]; E2E = "e2e" in sys.argv[1:]
SHOTS = Path(args[0] if args else TMP / "shots"); SHOTS.mkdir(parents=True, exist_ok=True)

def mock(page):
    G = {}
    def h(route):
        r = route.request; path = re.sub(r"^.*/api/goals", "", r.url.split("?")[0]).strip("/"); body = json.loads(r.post_data or "{}") if r.post_data else {}
        ok = lambda j, c=200: route.fulfill(status=c, content_type="application/json", body=json.dumps(j))
        if r.method == "GET" and not path: return ok([v for k, v in G.items() if k != "_"])
        if r.method == "POST" and path == "draft":
            G.setdefault("_", {})["draft"] = body; time.sleep(0.4); return ok({"name": "Sonora app", "objective": "# Objetivo: Sonora\n\n## Entregable"})
        if r.method == "POST" and not path:
            time.sleep(0.6)
            g = G["g1"] = {"id": "g1", "name": body["name"], "folder": body["folder"], "objective": body["objective"], "schedule": body.get("schedule"), "status": "intake",
                "questions": [{"id": "q1", "q": "¿Dónde está el Figma?", "hint": "Enlace al archivo", "default": "Usa <el diseño> del README"}, {"id": "q2", "q": "¿Qué backend usa?", "hint": ""}], "after": body.get("after"), "from": "goal/previo" if body.get("after") else None,
                "answers": {}, "acceptance": ["Compila sin errores", "Los tests pasan"], "iteration": 0, "max_iter": body.get("max_iter", 5), "max_hours": body.get("max_hours", 8), "allow": body.get("allow", []), "outcome": None, "base_branch": "main", "slug": "sonora", "run": "", "started": 0, "ended": 0, "history": [], "report": ""}
            return ok(g)
        id, _, what = path.partition("/"); g = G.get(id)
        if what == "clone" and g:
            G.setdefault("_", {})["clone"] = body; n = G["g2"] = {**g, "id": "g2", "name": body["name"], "status": "ready", "after": None, "from": None, "outcome": None, "history": [], "report": "", "iteration": 0}; return ok(n)
        if not g: return ok({"error": "not found"}, 404)
        if r.method == "DELETE": del G[id]; return ok({"ok": True})
        if r.method == "GET" and what == "review":
            return ok({"branch": "goal/sonora", "exists": g.get("exists", True), "base_branch": "main", "base": "abc1234", "outcome": g["outcome"],
                "commits": [{"sha": "deadbeefcafe", "subject": "Añade pantalla <Login>"}], "files": [{"path": "src/app.py", "add": 12, "del": 3}], "truncated": False,
                "diff": "diff --git a/src/app.py b/src/app.py\n--- a/src/app.py\n+++ b/src/app.py\n@@ -1,2 +1,3 @@\n-old <b>\n+new <b>\n keep",
                "criteria": [{"c": "Compila sin errores", "ok": True, "evidence": "build ok"}, {"c": "Los tests pasan", "ok": False, "evidence": "2 fallan"}]})
        if r.method == "GET": return ok(g)
        if what == "answers": g.update(status="ready", answers=body["answers"], acceptance=body["acceptance"], **{k: body[k] for k in ("max_iter", "max_hours", "allow") if k in body}); G.setdefault("_", {})["ans"] = body
        elif what == "limits": g.update(body)
        elif what == "continue": g.update(status="running", lost=False); G.setdefault("_", {})["cont"] = body
        elif what in ("merge", "discard"): g["outcome"] = what + "d" if what == "merge" else "discarded"; G.setdefault("_", {})["end"] = what
        elif what == "start": g.update(status="waiting" if g.get("after") else "running", iteration=1, run="r1", started=time.time() - 600)
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
            pg.on("pageerror", lambda e: errs.append(str(e))); pg.on("dialog", lambda dl: dl.accept(dl.default_value) if dl.type == "prompt" else dl.accept())
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
            pg.wait_for_selector("[name=after]", state="attached"); time.sleep(0.3); assert not pg.locator("[name=after]").is_visible()  # no goals yet: field hidden
            pg.fill("[name=objective]", ""); pg.fill("[name=folder]", "/tmp"); pg.click("[data-act=glDraft]"); time.sleep(0.3)
            assert "draft" not in G.get("_", {}) and "escribe la idea" in pg.inner_text("body").lower()
            pg.fill("[name=objective]", "una app de música"); pg.click("[data-act=glDraft]");
            pg.wait_for_function("document.querySelector('[name=objective]').value.startsWith('# Objetivo')"); assert pg.input_value("[name=name]") == "Sonora app" and G["_"]["draft"] == {"folder": "/tmp", "idea": "una app de música"}
            pg.fill("[name=name]", "")
            pg.fill("[name=name]", "Desarrollar Sonora"); pg.fill("[name=objective]", "Haz Sonora con el Figma y el backend"); pg.click(".gl-opt >> nth=0 >> summary")
            pg.click(".gl-opt >> nth=1 >> summary"); pg.fill("[name=max_iter]", "7"); pg.fill("[name=max_hours]", "2.5"); pg.locator(".gl-al label:has-text('Gmail')").click()
            pg.fill("[name=at]", "08:30"); pg.click(".as-day:has-text('L')")
            pg.click("#gl-go"); pg.wait_for_selector("#gl-busy:visible"); assert pg.is_disabled("#gl-go")
            pg.wait_for_selector("#gl-ans"); assert (G["g1"]["max_iter"], G["g1"]["max_hours"], G["g1"]["allow"]) == (7, 2.5, ["Gmail"]), G["g1"]; pg.screenshot(path=str(SHOTS / f"goals-intake-{name}.png"), full_page=True)
            assert pg.get_attribute("[name=q1]", "placeholder") == "Por defecto: Usa <el diseño> del README" and pg.get_attribute("[name=q2]", "placeholder") is None and "valor por defecto" in pg.inner_text("#gl-ans")
            pg.fill("[name=q1]", "figma.com/x"); pg.fill("[name=q2]", "Flask")
            pg.click("[data-act=glAccAdd]"); pg.locator(".gl-acc input").last.fill("Sin errores en consola"); pg.locator(".gl-acc [data-act=glAccDel]").first.click()
            assert pg.locator(".gl-acc").count() == 2
            pg.click("#gl-ans summary"); pg.locator("#gl-ans .gl-al label:has-text('Trello')").click()
            pg.click("#gl-ans .pri"); pg.wait_for_selector("[data-act=glStart]"); assert G["_"]["ans"]["allow"] == ["Trello", "Gmail"] and G["_"]["ans"]["max_iter"] == 7, G["_"]["ans"]; assert G["g1"]["answers"]["q1"] == "figma.com/x" and "Los tests pasan" in G["g1"]["acceptance"]
            pg.click("[data-act=glStart]"); pg.wait_for_selector(".gl-pill[data-s=running]"); assert pg.locator("a[href='#session/r1']").count() == 1
            G["g1"].update(secs=1500, cost=1.234, live={"round": 2, "of": 5, "verifying": False, "brain": "working",
                "kids": [{"id": "c1", "name": "Pantalla <Login>", "status": "working", "model": "sonnet"}, {"id": "c2", "name": "Tests", "status": "asking", "model": "haiku"}],
                "acts": [{"ts": time.time(), "who": "Tests", "text": "Bash: pytest -q " + "x" * 200}, {"ts": time.time(), "who": "", "text": "Edit: src/<app>.py"}]})
            pg.wait_for_selector(".gl-live", timeout=12000)
            assert "ronda 2/5" in pg.inner_text(".gl-live h2").lower() and pg.locator(".gl-kids li").count() == 2 and pg.locator(".gl-kids i[data-s=asking]").count() == 1
            assert "<Login>" in pg.inner_text(".gl-kids") and pg.locator(".gl-kids b, .gl-acts b").count() == 0 and pg.locator(".gl-acts li").count() == 2 and "pytest -q" in pg.inner_text(".gl-acts")
            assert "$1.23" in pg.inner_text(".gl-facts") and "no es un cargo" in pg.inner_text(".gl-facts") and "25 min" in pg.inner_text(".gl-facts")
            sw = pg.evaluate("[document.documentElement.scrollWidth, screen.width, innerWidth]"); assert sw[0] <= max(sw[1], sw[2]), sw; pg.screenshot(path=str(SHOTS / f"goals-live-{name}.png"), full_page=True)
            G["g1"].update(status="verifying", live={**G["g1"]["live"], "verifying": True}); pg.wait_for_selector(".gl-live h2:text-matches('Verificando ronda 2/5','i')", timeout=12000)
            G["g1"].update(status="verifying", iteration=2, history=[{"n": 1, "verdict": "fail", "summary": "Faltan tests", "failing": ["Los tests pasan"], "ts": time.time()}])
            pg.wait_for_selector(".gl-pill[data-s=verifying]", timeout=12000); pg.wait_for_selector(".gl-h.fail")
            G["g1"].update(status="blocked")
            pg.wait_for_selector(".gl-pill[data-s=blocked]", timeout=12000); pg.fill("#gl-msg", "usa la clave X"); pg.screenshot(path=str(SHOTS / f"goals-blocked-{name}.png"), full_page=True)
            pg.click("#gl-say .pri"); pg.wait_for_selector(".gl-pill[data-s=running]"); assert G["_"]["msg"] == "usa la clave X"
            G["g1"].pop("live"); G["g1"].update(status="done", iteration=2, ended=time.time(), report="## Informe\n\n- **Hecho**: todo pasa\n", history=G["g1"]["history"] + [{"n": 2, "verdict": "pass", "summary": "Todo correcto", "failing": [], "ts": time.time()}])
            pg.wait_for_selector(".gl-pill[data-s=done]", timeout=12000); assert pg.locator(".gl-live").count() == 0; pg.wait_for_selector(".gl-rep h2:has-text('Informe')"); assert pg.locator(".gl-h").count() == 2
            pg.wait_for_selector(".gl-crit li.ko"); assert pg.locator(".gl-crit li.ok svg").count() == 1 and pg.locator(".gl-crit li.ko svg").count() == 1 and "2 fallan" in pg.inner_text(".gl-crit")
            assert "deadbee" in pg.inner_text(".gl-commits") and "<Login>" in pg.inner_text(".gl-commits") and "+12" in pg.inner_text(".gl-files"); assert pg.locator(".gl-diff .a").count() == 1 and pg.locator(".gl-diff .d").count() == 1 and pg.locator(".gl-diff b").count() == 0
            assert not pg.locator(".gl-diff").is_visible(); pg.click(".gl-rv summary"); assert pg.locator(".gl-diff").is_visible()
            for th in ("light", "dark"):
                pg.evaluate(f"document.documentElement.dataset.theme='{th}'")
                c = pg.evaluate("(() => { const s = getComputedStyle(document.querySelector('.gl-pill[data-s=done]')); return [s.color, s.backgroundColor] })()"); assert c[0] != c[1], (th, c)
                pg.screenshot(path=str(SHOTS / f"goals-review-{th}-{name}.png"), full_page=True)
            pg.evaluate("document.documentElement.dataset.theme='light'")
            pg.screenshot(path=str(SHOTS / f"goals-detail-{name}.png"), full_page=True)
            pg.click("[data-act=glLim]"); pg.fill("#gl-sheet [name=max_hours]", "12"); pg.locator("#gl-sheet .gl-al label:has-text('Drive')").click(); pg.click("#gl-sheet .pri"); pg.wait_for_function("!document.querySelector('#gl-sheet[open]')")
            assert G["g1"]["max_hours"] == 12 and G["g1"]["allow"] == ["Trello", "Gmail", "Google_Drive"]; assert "Google Drive" in pg.inner_text(".gl-facts")
            pg.click("[data-act=glMerge]"); pg.wait_for_selector(".gl-rv .gl-pill[data-o=merged]"); assert G["_"]["end"] == "merge" and pg.locator("[data-act=glMerge]").count() == 0
            G["g1"].update(status="failed", lost=True, outcome=None); pg.goto(f"http://127.0.0.1:{P}/#goals"); pg.wait_for_selector(".gl-row"); pg.click(".gl-row"); pg.click("[data-act=glRetake]")
            pg.wait_for_selector(".gl-pill[data-s=running]"); assert G["_"]["cont"] == {} and not G["g1"]["lost"]
            G["g1"].update(status="stopped"); pg.reload(); pg.fill("#gl-cont textarea", "añade tests"); pg.click("#gl-cont .pri"); pg.wait_for_selector(".gl-pill[data-s=running]"); assert G["_"]["cont"] == {"text": "añade tests"}
            G["g1"].update(status="done", outcome=None); pg.reload(); pg.click("[data-act=glDiscard]"); pg.wait_for_selector(".gl-pill[data-o=discarded]"); assert G["_"]["end"] == "discard"
            pg.click("[data-act=glSched]"); pg.fill("#gl-sheet [name=at]", ""); pg.click("#gl-sheet .pri"); pg.wait_for_function("!document.querySelector('#gl-sheet[open]')")
            assert G["g1"]["schedule"] is None
            pg.click("[data-act=glClone]"); pg.wait_for_selector(".gl-pill[data-s=ready]"); assert G["_"]["clone"] == {"name": "Desarrollar Sonora 2"} and "g2" in G and pg.url.endswith("#goals/g2")
            G["g2"].update(after="g1", **{"from": "goal/sonora"}); pg.reload(); pg.wait_for_selector("[data-act=glStart]"); assert "esperará" in pg.inner_text("[data-act=glStart]").lower() and "goal/sonora" in pg.inner_text(".gl-facts").lower(); assert pg.get_attribute(".gl-facts a", "href") == "#goals/g1"
            pg.click("[data-act=glStart]"); pg.wait_for_selector(".gl-pill[data-s=waiting]"); assert "goal/sonora" in pg.inner_text("[role=status]") and pg.locator("[data-act=glStop]").count() == 1
            pg.screenshot(path=str(SHOTS / f"goals-waiting-{name}.png"), full_page=True)
            G["g2"].update(status="running"); pg.wait_for_selector(".gl-pill[data-s=running]", timeout=12000); del G["g2"]; G["g1"].update(outcome=None, status="done")
            pg.goto(f"http://127.0.0.1:{P}/#goals/new"); pg.wait_for_selector("[name=after]:visible"); assert pg.locator("[name=after] option").count() == 2 and "Desarrollar Sonora" in pg.inner_text("[name=after]")
            pg.fill("[name=name]", "Fase 2"); pg.fill("[name=objective]", "sigue"); pg.select_option("[name=after]", "g1"); pg.screenshot(path=str(SHOTS / f"goals-new-{name}.png"), full_page=True)
            sw = pg.evaluate("[document.documentElement.scrollWidth, screen.width, innerWidth]"); assert sw[0] <= max(sw[1], sw[2]), sw
            pg.click("#gl-go"); pg.wait_for_selector("#gl-ans"); assert G["g1"]["after"] == "g1"
            G["g1"].update(cost=1.234, status="done")
            pg.goto(f"http://127.0.0.1:{P}/#goals"); pg.wait_for_selector(".gl-row"); assert "$1.23" in pg.inner_text(".gl-row"); pg.screenshot(path=str(SHOTS / f"goals-list-{name}.png"), full_page=True)
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
