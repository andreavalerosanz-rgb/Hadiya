#!/usr/bin/env python3
"""Kanban UI (index.html #kanban + kanban.html) at 1440 and 390 (iPhone, isMobile): create/edit board, share link, open board,
add/edit card, attachment, move by drag & drop and by button, guest mode (name prompt, `by`, no delete), polling, no horizontal
overflow, text >=16px, targets >=48px. The kanban API is an in-memory fake behind page.route (contract in the goal brief).
Shots: data/shots/kanban-*.png. Run: /tmp/pwenv/bin/python scripts/test_kanban_ui.py  (exit 0 = ok)
--real: also drive kanban.html against the real backend of a temp server (needs the server.py kanban API)."""
import base64, json, os, re, shutil, socket, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse
from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parent.parent
SHOTS = REPO / "data/shots"; SHOTS.mkdir(parents=True, exist_ok=True)
TMP = Path(tempfile.mkdtemp(prefix="flows-kanban-"))
(TMP / "bin").mkdir(); (TMP / "home").mkdir(); (TMP / "app").mkdir()
(TMP / "bin/claude").write_text("#!/bin/sh\nexit 0\n"); (TMP / "bin/claude").chmod(0o755)
for f in ("server.py", "index.html", "kanban.html"):
    shutil.copy(REPO / f, TMP / "app" / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0)); P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=TMP / "app", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "PATH": f"{TMP / 'bin'}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(TMP / "home"), "FLOWS_DATA": str(TMP / "app/data")})
URL = f"http://127.0.0.1:{P}"
KHTML = (REPO / "kanban.html").read_text()
CHECK = """() => {
  const vis = e => e.offsetParent && e.getBoundingClientRect().width > 1 && e.getBoundingClientRect().height > 1 && !e.closest('dialog:not([open])');
  const d = e => `${e.tagName}.${e.className}'${e.textContent.trim().slice(0, 18)}'`;
  const tiny = [...document.querySelectorAll('body *')].filter(e => vis(e) && [...e.childNodes].some(n => n.nodeType == 3 && n.textContent.trim()) && parseFloat(getComputedStyle(e).fontSize) < 16).map(e => d(e) + getComputedStyle(e).fontSize);
  const small = [...document.querySelectorAll('button, a[href], input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea, summary')].filter(vis).filter(e => {
    const r = e.getBoundingClientRect(); return Math.min(r.width, r.height) < 48 && !e.closest('[hidden]'); }).map(e => { const r = e.getBoundingClientRect(); return d(e) + Math.round(r.width) + 'x' + Math.round(r.height); });
  return {font: getComputedStyle(document.body).fontFamily, ow: document.documentElement.scrollWidth - innerWidth, sw: document.documentElement.scrollWidth - screen.width, tiny, small};
}"""
fails = []
def check(ok, msg):
    if not ok: fails.append(msg); print("FAIL", msg)
def floor(pg, where):
    r = pg.evaluate(CHECK)
    check("Barlow" in r["font"], f"{where}: font {r['font']}")
    check(r["ow"] <= 0 and r["sw"] <= 0, f"{where}: horizontal overflow {r['ow']}/{r['sw']}")
    check(not r["tiny"], f"{where}: text<16 {r['tiny'][:6]}")
    check(not r["small"], f"{where}: targets<48 {r['small'][:6]}")


class Fake:
    """In-memory kanban backend: owner /api/kanban/..., guest /k/<token>/api/..."""
    def __init__(self):
        self.boards, self.cards, self.files, self.n, self.share_gets, self.posts = {}, [], {}, 0, 0, []
    def nid(self):
        self.n += 1; return f"x{self.n}"
    def pub(self, b):
        return {**b, "count": sum(c["board"] == b["id"] for c in self.cards)}
    def handle(self, route):
        rq = route.request; u = urlparse(rq.url); path = unquote(u.path); m = rq.method
        body = json.loads(rq.post_data or "{}") if m in ("POST", "PATCH") else {}
        if re.fullmatch(r"/k/[^/]+", path):
            return route.fulfill(body=KHTML, content_type="text/html")
        if path == "/kanban.html":
            return route.fulfill(body=KHTML, content_type="text/html")
        js = lambda o, st=200: route.fulfill(status=st, json=o)
        if path == "/api/kanban/share":
            if m == "POST": self.tunnel = body["on"]; return js({"url": None, "tunnel": True})
            self.share_gets += 1
            return js({"url": "https://flows-demo.trycloudflare.com" if getattr(self, "tunnel", False) and self.share_gets > 2 else None, "tunnel": getattr(self, "tunnel", False)})
        if path == "/api/kanban/boards":
            if m == "GET": return js([self.pub(b) for b in self.boards.values()])
            b = {"id": self.nid(), "name": body["name"], "token": "tok" + self.nid(), "columns": [{"id": self.nid(), "name": n} for n in body.get("columns") or ["Por hacer", "En curso", "Hecho"]]}
            self.boards[b["id"]] = b; return js(self.pub(b))
        g = re.fullmatch(r"/api/kanban/boards/([^/]+)(/token)?", path)
        if g and (g[2] or m != "GET"):
            b = self.boards.get(g[1])
            if not b: return js({"error": "no existe"}, 404)
            if g[2]: b["token"] = "tok" + self.nid(); return js(self.pub(b))
            if m == "DELETE": del self.boards[b["id"]]; return js({"ok": True})
            if "name" in body: b["name"] = body["name"]
            if "columns" in body:
                keep = {c.get("id") for c in body["columns"]}
                if any(c["board"] == b["id"] and c["col"] not in keep for c in self.cards): return js({"error": "La columna tiene tarjetas"}, 400)
                b["columns"] = [{"id": c.get("id") or self.nid(), "name": c["name"]} for c in body["columns"]]
            return js(self.pub(b))
        g = re.fullmatch(r"/api/kanban/boards/([^/]+)(/.*)?", path) or re.fullmatch(r"/k/([^/]+)/api(/.*)?", path)
        guest = path.startswith("/k/")
        b = next((x for x in self.boards.values() if x["token"] == g[1]), None) if guest else self.boards.get(g[1])
        if not b: return js({"error": "no existe"}, 404)
        rest = g[2] or ""
        if rest == "" and m == "GET":
            return js({"board": {k: b[k] for k in ("id", "name", "columns")}, "cards": [c for c in self.cards if c["board"] == b["id"]], "guest": guest})
        if rest == "/cards" and m == "POST":
            self.posts.append(body)
            col = body.get("col") or b["columns"][0]["id"]; ps = [c["pos"] for c in self.cards if c["col"] == col]
            c = {"id": self.nid(), "board": b["id"], "col": col, "title": body["title"], "desc": body.get("desc", ""), "due": body.get("due", ""), "prio": body.get("prio", "media"),
                 "files": [], "pos": max(ps, default=0) + 1, "by": body.get("by", ""), "created": time.time(), "updated": time.time()}
            self.cards.append(c); return js(c)
        g2 = re.fullmatch(r"/cards/([^/]+)(?:/files(?:/(.+))?)?", rest)
        c = next((x for x in self.cards if x["id"] == g2[1] and x["board"] == b["id"]), None) if g2 else None
        if not c: return js({"error": "no existe"}, 404)
        if "/files" in rest:
            if m == "POST":
                data = base64.b64decode(body["data"]); self.files[(c["id"], body["name"])] = data
                c["files"] = [f for f in c["files"] if f["name"] != body["name"]] + [{"name": body["name"], "size": len(data)}]; return js(c)
            if m == "GET": return route.fulfill(body=self.files[(c["id"], g2[2])], content_type="application/octet-stream")
            if guest: return js({"error": "solo el dueño"}, 403)
            c["files"] = [f for f in c["files"] if f["name"] != g2[2]]; return js(c)
        if m == "PATCH": c.update({k: v for k, v in body.items() if k in ("title", "desc", "due", "prio", "col", "pos")}); return js(c)
        if m == "DELETE":
            if guest: return js({"error": "solo el dueño"}, 403)
            self.cards.remove(c); return js({"ok": True})
        return js({"error": "?"}, 405)


def col_of(fake, title):
    c = next(c for c in fake.cards if c["title"] == title); b = fake.boards[c["board"]]
    return next(x["name"] for x in b["columns"] if x["id"] == c["col"])

def owner(b, p, size, ca):
    fake = Fake(); ctx = b.new_context(**ca); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    ctx.route(re.compile(r".*/(api/kanban|k/|kanban\.html)"), fake.handle)
    ctx.add_init_script("window.confirm = () => true")
    pg.goto(f"{URL}/#kanban"); pg.wait_for_selector("#kb-list .as-m.note")
    # Más lists Kanban
    pg.goto(f"{URL}/"); pg.wait_for_selector(".dnav"); pg.click(".dnav [data-act=more]")
    pg.click("#more a[href='#kanban']"); pg.wait_for_selector("#kb-list .as-m.note")
    check(pg.locator(".dnav [data-act=more][aria-current]").count() == 1, f"{size}: Más not current on #kanban")
    # create board (default columns)
    pg.click("[data-act=kbEdit]"); pg.fill("#kb-f [name=name]", "Incidencias web")
    check(pg.locator("#gl-accs input").count() == 3, f"{size}: default columns")
    floor(pg, f"{size} new board sheet"); pg.screenshot(path=str(SHOTS / f"kanban-newboard-{size}.png"))
    pg.click("#kb-f .as-btn.pri"); pg.wait_for_selector(".kb-row")
    check("Incidencias web" in pg.inner_text(".kb-row") and "0 tarjetas" in pg.inner_text(".kb-row"), f"{size}: board row")
    # edit: rename + add a column
    pg.click(".kb-row [data-act=kbEdit]"); pg.fill("#kb-f [name=name]", "Incidencias"); pg.click("[data-act=kbColAdd]")
    pg.locator("#gl-accs input").last.fill("Revisión"); pg.click("#kb-f .as-btn.pri"); pg.wait_for_function("document.querySelector('.kb-row')?.textContent.includes('Revisión')")
    bid = next(iter(fake.boards)); check([c["name"] for c in fake.boards[bid]["columns"]] == ["Por hacer", "En curso", "Hecho", "Revisión"], f"{size}: columns after edit")
    # share: tunnel off -> on -> url after polling
    pg.click(".kb-row [data-act=kbShare]"); pg.wait_for_selector("#kb-link", timeout=15000)
    check(pg.input_value("#kb-link") == f"https://flows-demo.trycloudflare.com/k/{fake.boards[bid]['token']}", f"{size}: share link {pg.input_value('#kb-link')}")
    check("reinicia" in pg.inner_text("#kb-sheet"), f"{size}: restart note")
    floor(pg, f"{size} share sheet"); pg.screenshot(path=str(SHOTS / f"kanban-share-{size}.png"))
    pg.click("#kb-sheet [data-act=kbX]")
    old = fake.boards[bid]["token"]; pg.click(".kb-row [data-act=kbRotate]"); pg.wait_for_timeout(300)
    check(fake.boards[bid]["token"] != old, f"{size}: rotate token")
    floor(pg, f"{size} list"); pg.screenshot(path=str(SHOTS / f"kanban-list-{size}.png"))
    # open the board (owner)
    pg.click(".kb-row a:has-text('Abrir')"); pg.wait_for_url("**/kanban.html?b=*"); pg.wait_for_selector(".col")
    check(pg.locator("a[href='/#kanban']").count() == 1, f"{size}: owner back link")
    mobile = size == "390"
    check(pg.locator(".col:visible").count() == (1 if mobile else 4), f"{size}: visible columns")
    # add a card (overdue)
    pg.click(".col:visible [data-new]"); pg.fill("#f [name=title]", "La web no carga en Safari"); pg.fill("#f [name=desc]", "Pasa en iPhone.")
    pg.fill("#f [name=due]", "2026-01-05"); pg.select_option("#f [name=prio]", "alta"); pg.click("#save")
    pg.wait_for_selector(".card:has-text('La web no carga')")
    check(pg.locator(".card .due.late").count() == 1 and pg.locator(".card .prio[data-p=alta]").count() == 1, f"{size}: card meta (overdue, prio)")
    # edit it + attachment + owner delete controls
    pg.click(".card:has-text('La web no carga') .open"); pg.wait_for_selector("#dlg[open]")
    check(pg.is_visible("#delcard"), f"{size}: owner sees Borrar tarjeta")
    pg.set_input_files("#file", {"name": "captura.png", "mimeType": "image/png", "buffer": b"\x89PNG fake"})
    pg.wait_for_selector("#files a:has-text('captura.png')")
    check(pg.locator("#files [data-delfile]").count() == 1, f"{size}: owner sees delete attachment")
    floor(pg, f"{size} card dialog"); pg.screenshot(path=str(SHOTS / f"kanban-dialog-{size}.png"))
    pg.fill("#f [name=title]", "La web no carga en Safari iOS"); pg.click("#save"); pg.wait_for_selector("#dlg:not([open])", state="attached")
    pg.wait_for_selector(".card:has-text('Safari iOS')")
    check(fake.cards[0]["title"] == "La web no carga en Safari iOS", f"{size}: edit saved")
    check(pg.locator(".card:has-text('Safari iOS') .meta").inner_text().count("1") >= 1, f"{size}: attachment count on card")
    # move by button (dialog)
    pg.click(".card:has-text('Safari iOS') .open"); pg.click("#mv [data-mv]"); pg.wait_for_timeout(300)
    check(col_of(fake, "La web no carga en Safari iOS") == "En curso", f"{size}: move by button -> {col_of(fake, 'La web no carga en Safari iOS')}")
    check(pg.locator("#mv [data-mv]").count() == 2, f"{size}: move buttons redrawn")
    pg.click("#dlg [data-close] >> nth=1")
    if not mobile:
        # a second card, then drag & drop: Safari card to Por hacer above it, then reorder
        pg.click(".col[aria-label='Por hacer'] [data-new]"); pg.fill("#f [name=title]", "Logo pixelado"); pg.click("#save"); pg.wait_for_selector(".card:has-text('Logo pixelado')")
        pg.locator(".card:has-text('Safari iOS') .open").drag_to(pg.locator(".card:has-text('Logo pixelado') .open"), target_position={"x": 20, "y": 5})
        pg.wait_for_timeout(400)
        a, l = (next(c for c in fake.cards if c["title"].startswith(t)) for t in ("La web", "Logo"))
        check(col_of(fake, a["title"]) == "Por hacer" and a["pos"] < l["pos"], f"{size}: drag to other column above ({a['pos']} vs {l['pos']})")
        titles = pg.locator(".col[aria-label='Por hacer'] .card b").all_inner_texts()
        check(titles == ["La web no carga en Safari iOS", "Logo pixelado"], f"{size}: order after drop {titles}")
        pg.locator(".card:has-text('Safari iOS') .open").drag_to(pg.locator(".col[aria-label='Revisión']"))
        pg.wait_for_timeout(400); check(col_of(fake, a["title"]) == "Revisión", f"{size}: drag to empty last column")
        check(pg.locator(".card:has-text('Safari iOS') .due.late").count() == 0, f"{size}: no overdue mark in last column")
        # poll picks up a card made elsewhere
        fake.cards.append({**l, "id": "ext", "title": "Desde fuera", "pos": 9})
        pg.wait_for_selector(".card:has-text('Desde fuera')", timeout=13000)
    else:
        check(pg.locator(".tabs [aria-pressed=true]").inner_text().startswith("En curso"), f"{size}: tab follows moved card")
        pg.click(".tabs button:has-text('Por hacer')"); check(pg.locator(".col.on").get_attribute("aria-label") == "Por hacer", f"{size}: tab switch")
        pg.click(".tabs button:has-text('En curso')")
    floor(pg, f"{size} board owner"); pg.screenshot(path=str(SHOTS / f"kanban-board-{size}.png"), full_page=True)
    # owner deletes the card
    pg.click(".card .open:visible >> nth=0"); n = len(fake.cards); pg.click("#delcard"); pg.wait_for_timeout(300)
    check(len(fake.cards) == n - 1, f"{size}: delete card")
    check(not errs, f"{size}: JS errors {errs}")
    ctx.close(); return fake

def guest(b, size, ca):
    fake = Fake(); bid = "b1"
    fake.boards[bid] = {"id": bid, "name": "Incidencias", "token": "tokG", "columns": [{"id": "c1", "name": "Por hacer"}, {"id": "c2", "name": "En curso"}, {"id": "c3", "name": "Hecho"}]}
    fake.cards.append({"id": "k1", "board": bid, "col": "c1", "title": "Cambiar el banner", "desc": "", "due": "", "prio": "urgente", "files": [{"name": "banner.jpg", "size": 2048}], "pos": 1, "by": "Luis", "created": time.time(), "updated": time.time()})
    fake.files[("k1", "banner.jpg")] = b"x" * 2048
    ctx = b.new_context(**ca); pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    ctx.route(re.compile(r".*/(api/kanban|k/|kanban\.html)"), fake.handle)
    pg.goto(f"{URL}/k/tokG"); pg.wait_for_selector("#who[open]")
    floor(pg, f"{size} guest name"); pg.screenshot(path=str(SHOTS / f"kanban-guest-name-{size}.png"))
    pg.fill("#wf [name=name]", "Ana"); pg.click("#wf .btn.pri"); pg.wait_for_selector("#who:not([open])", state="attached")
    check(pg.locator("a[href*='#'], a[href='/']").count() == 0, f"{size}: guest sees Flows links")
    check("Tú: Ana" in pg.text_content("header"), f"{size}: guest name in header")
    check("por Luis" in pg.inner_text(".card"), f"{size}: por <by>")
    pg.click(".col:visible [data-new]"); pg.fill("#f [name=title]", "Revisar textos"); pg.click("#save"); pg.wait_for_selector(".card:has-text('Revisar textos')")
    check(fake.posts and fake.posts[-1].get("by") == "Ana", f"{size}: POST by {fake.posts}")
    check("por Ana" in pg.inner_text(".card:has-text('Revisar textos')"), f"{size}: card shows por Ana")
    pg.click(".card:has-text('Cambiar el banner') .open"); pg.wait_for_selector("#dlg[open]")
    check(not pg.is_visible("#delcard") and pg.locator("#files [data-delfile]").count() == 0, f"{size}: guest sees delete controls")
    check(pg.locator("#files a[download]").get_attribute("href") == "/k/tokG/api/cards/k1/files/banner.jpg", f"{size}: download href")
    pg.set_input_files("#file", {"name": "nota.txt", "mimeType": "text/plain", "buffer": b"hola"}); pg.wait_for_selector("#files a:has-text('nota.txt')")
    floor(pg, f"{size} guest dialog"); pg.screenshot(path=str(SHOTS / f"kanban-guest-dialog-{size}.png"))
    pg.click("#mv [data-mv]"); pg.wait_for_timeout(300)
    check(next(c for c in fake.cards if c["id"] == "k1")["col"] == "c2", f"{size}: guest move by button")
    pg.click("#dlg [data-close] >> nth=1")
    floor(pg, f"{size} guest board"); pg.screenshot(path=str(SHOTS / f"kanban-guest-{size}.png"), full_page=True)
    # a bad link
    pg.goto(f"{URL}/k/nope"); pg.wait_for_selector("text=ya no es válido")
    check(not errs, f"{size}: guest JS errors {errs}")
    ctx.close()

def real(b):
    """kanban.html against the real backend of the temp server (owner board created through the API)."""
    def call(m, path, body=None):
        r = urllib.request.Request(URL + path, method=m, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json", "X-Flow": "1"})
        return json.load(urllib.request.urlopen(r))
    bd = call("POST", "/api/kanban/boards", {"name": "Real"})
    ctx = b.new_context(viewport={"width": 1440, "height": 900}); pg = ctx.new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
    for base, who in ((f"/kanban.html?b={bd['id']}", "owner"), (f"/k/{bd['token']}", "guest")):
        pg.goto(URL + base); pg.wait_for_selector(".col")
        if who == "guest": pg.fill("#wf [name=name]", "Ana"); pg.click("#wf .btn.pri")
        pg.click(".col [data-new] >> nth=0"); pg.fill("#f [name=title]", f"Real {who}"); pg.click("#save"); pg.wait_for_selector(f".card:has-text('Real {who}')")
        pg.click(f".card:has-text('Real {who}') .open"); pg.set_input_files("#file", {"name": "a.txt", "mimeType": "text/plain", "buffer": b"hola"}); pg.wait_for_selector("#files a:has-text('a.txt')")
        pg.click("#mv [data-mv]"); pg.wait_for_timeout(400); pg.click("#dlg [data-close] >> nth=1")
    g = call("GET", f"/api/kanban/boards/{bd['id']}")
    cs = {c["title"]: c for c in g["cards"]}
    check(set(cs) == {"Real owner", "Real guest"} and all(c["col"] == bd["columns"][1]["id"] and c["files"] for c in cs.values()), f"real: cards {g['cards']}")
    check(cs.get("Real guest", {}).get("by") == "Ana", "real: guest by")
    check(not errs, f"real: JS errors {errs}")
    ctx.close()

try:
    for _ in range(50):
        try: socket.create_connection(("127.0.0.1", P), 0.2).close(); break
        except OSError: time.sleep(0.1)
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        for size, ca in (("1440", {"viewport": {"width": 1440, "height": 900}}), ("390", p.devices["iPhone 13"] | {"viewport": {"width": 390, "height": 844}})):
            owner(b, p, size, ca); guest(b, size, ca)
        if "--real" in sys.argv: real(b)
        b.close()
finally:
    srv.terminate()
print("FAILED" if fails else "ok"); sys.exit(1 if fails else 0)
