#!/usr/bin/env python3
"""Self-check for the kanban: owner boards/cards/columns/files, guests via /k/<token> on a phone listener
(no pairing, one board only, no deletes, no /api/*), token rotation, persistence, multi-user isolation.
Runs server.py from a temp copy on a free port; FLOWS_PUBLIC_URL turns on the public phone listener (PORT+3).
Run: python3 scripts/test_kanban.py"""
import base64, getpass, json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="flows-kanban-"))
BIN = TMP / "bin"
BIN.mkdir()
# fake cloudflared: prints a quick-tunnel URL and idles, so the tunnel-only listener runs with nothing public
(BIN / "cloudflared").write_text("#!/bin/sh\necho 'INF |  https://fake-kanban.trycloudflare.com  |'\nexec sleep 600\n")
(BIN / "cloudflared").chmod(0o755)
ENV = {**{k: v for k, v in os.environ.items() if k not in ("FLOWS_PACKAGE", "FLOWS_DATA")}, "PATH": f"{BIN}:{os.environ['PATH']}"}
PAGE = (REPO / "kanban.html").read_bytes()


def copy(name):
    d = TMP / name
    d.mkdir()
    shutil.copy(REPO / "server.py", d / "server.py")
    shutil.copy(REPO / "index.html", d / "index.html")  # real one: the "/" checks prove guests get the pairing page instead
    (d / "kanban.html").write_bytes(PAGE)
    return d


def free():
    while True:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        try:
            with socket.socket() as s:
                s.bind(("127.0.0.1", port + 3))
            return port
        except OSError:
            pass


def start(d, port=None):
    port = port or free()
    p = subprocess.Popen([sys.executable, "server.py"], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         env={**ENV, "PORT": str(port), "HOME": str(TMP), "FLOWS_PUBLIC_URL": "https://kb.example.com"})
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port + 3), 0.2).close()
            return p, port
        except OSError:
            time.sleep(0.1)
    raise SystemExit("server did not start")


def call(port, method, path, body=None, cookie=None, flow=True, raw=False, host="127.0.0.1"):
    h = {"Content-Type": "application/json", **({"X-Flow": "1"} if flow else {}), **({"Cookie": cookie} if cookie else {})}
    req = Request(f"http://{host}:{port}{path}", data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urlopen(req, timeout=10) as r:
            data = r.read()
            return r.status, (data if raw or "json" not in r.headers["Content-Type"] else json.loads(data)), r.headers
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), e.headers


def ok(port, method, path, body=None, cookie=None):
    s, r, _ = call(port, method, path, body, cookie)
    assert s == 200, (method, path, s, r)
    return r


# ---------------- single user ----------------
d = copy("single")
srv, P = start(d)
G = P + 3  # the public (tunnel) listener: unpaired, so only /k/ works there
try:
    assert call(P, "POST", "/api/kanban/boards", {"name": "x"}, flow=False)[0] == 403
    assert call(P, "POST", "/api/kanban/boards", {"name": ""})[0] == 400
    b = ok(P, "POST", "/api/kanban/boards", {"name": "Oficina"})
    assert [c["name"] for c in b["columns"]] == ["Por hacer", "En curso", "Hecho"] and b["owner"] == ""
    todo, doing, done = (c["id"] for c in b["columns"])
    B = f"/api/kanban/boards/{b['id']}"
    lst = ok(P, "GET", "/api/kanban/boards")
    assert len(lst) == 1 and lst[0]["count"] == 0 and lst[0]["token"] == b["token"]
    assert ok(P, "GET", "/api/kanban/share") == {"url": "https://kb.example.com", "tunnel": False}

    # cards: add, validate, list, move, edit
    c1 = ok(P, "POST", B + "/cards", {"title": "Llamar al cliente", "due": "2026-10-20", "prio": "alta"})
    assert c1["col"] == todo and c1["prio"] == "alta" and c1["pos"] == 1 and c1["files"] == []
    c2 = ok(P, "POST", B + "/cards", {"title": "Factura"})
    assert c2["prio"] == "media" and c2["pos"] == 2 and c2["due"] == ""
    for bad in ({"desc": "no title"}, {"title": "x" * 201}, {"title": "a", "due": "20-10-2026"}, {"title": "a", "due": "2026-02-30"},
                {"title": "a", "prio": "max"}, {"title": "a", "col": "nope"}, {"title": "a", "pos": "x"}):
        assert call(P, "POST", B + "/cards", bad)[0] == 400, bad
    c1 = ok(P, "PATCH", f"{B}/cards/{c1['id']}", {"col": doing})
    assert c1["col"] == doing and c1["pos"] == 1
    c2 = ok(P, "PATCH", f"{B}/cards/{c2['id']}", {"col": doing, "pos": 0.5, "desc": "IVA", "title": "Factura 2"})
    v = ok(P, "GET", B)
    assert [c["id"] for c in v["cards"]] == [c2["id"], c1["id"]] and v["guest"] is False and "token" not in v["board"]
    assert call(P, "PATCH", f"{B}/cards/{c2['id']}", {"title": ""})[0] == 400

    # attachments
    data = b"<script>alert(1)</script>"
    c1 = ok(P, "POST", f"{B}/cards/{c1['id']}/files", {"name": "../../evil name?.html", "data": base64.b64encode(data).decode()})
    fname = c1["files"][0]["name"]
    assert "/" not in fname and "?" not in fname and c1["files"][0]["size"] == len(data), c1["files"]
    s, raw, h = call(P, "GET", f"{B}/cards/{c1['id']}/files/{fname.replace(' ', '%20')}", raw=True)
    assert s == 200 and raw == data and h["Content-Disposition"].startswith("attachment") and h["X-Content-Type-Options"] == "nosniff"
    assert h["Content-Type"] == "application/octet-stream"
    assert call(P, "GET", f"{B}/cards/{c1['id']}/files/..%2F..%2Fkanban.json")[0] == 404
    assert call(P, "POST", f"{B}/cards/{c1['id']}/files", {"name": "a.txt", "data": "!!notb64"})[0] == 400
    big = base64.b64encode(b"0" * (10 << 20) + b"0").decode()
    assert call(P, "POST", f"{B}/cards/{c1['id']}/files", {"name": "big.bin", "data": big})[0] == 400
    assert (d / "data/kanban" / b["id"] / c1["id"] / fname).read_bytes() == data

    # columns PATCH: rename, add, removing a non-empty column fails, removing an empty one works
    cols = ok(P, "GET", B)["board"]["columns"]
    b2 = ok(P, "PATCH", B, {"name": "Oficina 2", "columns": [{**cols[0], "name": "Pendiente"}, cols[1], cols[2], {"name": "Bloqueado"}]})
    assert [c["name"] for c in b2["columns"]] == ["Pendiente", "En curso", "Hecho", "Bloqueado"] and b2["name"] == "Oficina 2"
    assert call(P, "PATCH", B, {"columns": [cols[0], cols[2]]})[0] == 400  # "En curso" still has cards
    assert call(P, "PATCH", B, {"columns": [{"id": "forged", "name": "x"}]})[0] == 400
    assert call(P, "PATCH", B, {"columns": []})[0] == 400
    assert [c["name"] for c in ok(P, "PATCH", B, {"columns": b2["columns"][:3]})["columns"]] == ["Pendiente", "En curso", "Hecho"]

    # guests, on the public phone listener (not paired)
    K = f"/k/{b['token']}"
    s, page, h = call(G, "GET", K)
    assert s == 200 and page == PAGE and "text/html" in h["Content-Type"]
    gv = ok(G, "GET", K + "/api")
    assert gv["guest"] is True and len(gv["cards"]) == 2 and "token" not in gv["board"]
    gc = ok(G, "POST", K + "/api/cards", {"title": "De Marta", "by": "Marta", "col": done})
    assert gc["by"] == "Marta" and gc["col"] == done
    gc = ok(G, "PATCH", f"{K}/api/cards/{gc['id']}", {"col": todo, "pos": 3, "prio": "urgente", "desc": "ok"})
    assert gc["col"] == todo and gc["prio"] == "urgente"
    gc = ok(G, "POST", f"{K}/api/cards/{gc['id']}/files", {"name": "foto.jpg", "data": base64.b64encode(b"jpg").decode()})
    assert call(G, "GET", f"{K}/api/cards/{gc['id']}/files/foto.jpg", raw=True)[1] == b"jpg"
    assert call(G, "POST", K + "/api/cards", {"title": "x"}, flow=False)[0] == 403
    assert call(G, "DELETE", f"{K}/api/cards/{gc['id']}")[0] == 403
    assert call(G, "DELETE", f"{K}/api/cards/{gc['id']}/files/foto.jpg")[0] == 403
    for path in ("/api/kanban/boards", f"/api/kanban/boards/{b['id']}", "/api/runs", "/api/me", "/api/kanban/share", "/kanban.html"):
        assert call(G, "GET", path)[0] == 401, path
    assert b"kanban" not in call(G, "GET", "/", raw=True)[1]  # the pairing page, nothing else
    assert call(G, "POST", "/api/kanban/boards", {"name": "x"})[0] == 401
    assert call(G, "GET", f"{K}/../../api/runs")[0] in (401, 404)
    assert call(G, "GET", f"{K}/api/../../api/kanban/boards")[0] in (401, 404)
    # a card of another board through this token
    other = ok(P, "POST", "/api/kanban/boards", {"name": "Privado", "columns": ["A"]})
    oc = ok(P, "POST", f"/api/kanban/boards/{other['id']}/cards", {"title": "secreto"})
    assert call(G, "PATCH", f"{K}/api/cards/{oc['id']}", {"title": "hack"})[0] == 404
    assert call(G, "GET", f"{K}/api/cards/{oc['id']}/files/x")[0] == 404
    assert call(P, "PATCH", f"{B}/cards/{oc['id']}", {"title": "hack"})[0] == 404
    for bad in ("/k/nope", "/k/nope/api", "/k/", "/k", f"/k/{b['token']}x/api"):
        assert call(G, "GET", bad)[0] == 404, bad
    assert call(G, "POST", "/k/nope/api/cards", {"title": "x"})[0] == 404

    # the listeners the quick tunnel and Wi-Fi access forward to: guests get their board, nothing else without pairing
    assert ok(P, "POST", "/api/kanban/share", {"on": True})["tunnel"] is True
    for _ in range(50):
        if ok(P, "GET", "/api/kanban/share")["url"]:
            break
        time.sleep(0.1)
    assert ok(P, "GET", "/api/remote")["tunnel"]["url"] == "https://fake-kanban.trycloudflare.com"
    ok(P, "POST", "/api/remote/lan", {"on": True})
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
        sk.connect(("10.255.255.255", 1))
        lan = sk.getsockname()[0]
    for host, port in (("127.0.0.1", P + 2), (lan, P)):
        s, page, h = call(port, "GET", K, host=host)
        assert s == 200 and page == PAGE and "text/html" in h["Content-Type"], (host, port, s)
        assert call(port, "GET", K + "/api", host=host)[1]["guest"] is True
        tc = call(port, "POST", K + "/api/cards", {"title": f"via {port}"}, host=host)[1]
        assert call(port, "PATCH", f"{K}/api/cards/{tc['id']}", {"col": doing}, host=host)[1]["col"] == doing
        assert call(port, "POST", K + "/api/cards", {"title": "x"}, flow=False, host=host)[0] == 403
        assert b"kanban" not in call(port, "GET", "/", raw=True, host=host)[1].lower()  # the pairing page, not index.html
        for path in ("/api/runs", "/api/kanban/boards", f"/kanban.html?b={b['id']}", f"/api/kanban/boards/{b['id']}"):
            assert call(port, "GET", path, host=host)[0] == 401, (host, port, path)
        assert call(port, "POST", "/api/kanban/share", {"on": False}, host=host)[0] == 401
        ok(P, "DELETE", f"{B}/cards/{tc['id']}")
    ok(P, "POST", "/api/remote/lan", {"on": False})
    assert ok(P, "POST", "/api/kanban/share", {"on": False}) == {"url": "https://kb.example.com", "tunnel": False}

    # owner deletes; rotate kills the old link
    assert ok(P, "DELETE", f"{B}/cards/{gc['id']}/files/foto.jpg")["files"] == []
    ok(P, "DELETE", f"{B}/cards/{gc['id']}")
    assert call(P, "GET", f"{B}/cards/{gc['id']}/files/foto.jpg")[0] == 404
    tok = ok(P, "POST", B + "/token")["token"]
    assert tok != b["token"] and call(G, "GET", K + "/api")[0] == 404 and call(G, "GET", f"/k/{tok}/api")[0] == 200
    ok(P, "DELETE", f"/api/kanban/boards/{other['id']}")
    assert call(P, "GET", f"/api/kanban/boards/{other['id']}")[0] == 404 and oc["id"] not in json.loads((d / "data/kanban.json").read_text())["cards"]
    assert oct((d / "data/kanban.json").stat().st_mode & 0o777) == "0o600"
finally:
    srv.terminate()
    srv.wait()

# persistence after a restart
srv, P = start(d, P)
try:
    v = ok(P, "GET", B)
    assert v["board"]["name"] == "Oficina 2" and [c["title"] for c in v["cards"]] == ["Factura 2", "Llamar al cliente"], v
    assert v["cards"][1]["files"][0]["name"] == fname and ok(P + 3, "GET", f"/k/{tok}/api")["board"]["id"] == b["id"]
finally:
    srv.terminate()
    srv.wait()

# ---------------- multi-user: each owner sees only their own boards ----------------
d = copy("multi")
ME, PW = getpass.getuser(), "correct horse battery"
for name in ("alice", "bob"):
    r = subprocess.run([sys.executable, "server.py", "adduser", name, ME], cwd=d, input=f"{PW}\n{PW}\n", text=True,
                       capture_output=True, start_new_session=True, env=ENV)
    assert r.returncode == 0, r.stderr
srv, P = start(d)
try:
    assert call(P, "GET", "/api/kanban/boards")[0] == 401
    A, Bc = (call(P, "POST", "/api/login", {"user": u, "password": PW})[2]["Set-Cookie"].split(";")[0] for u in ("alice", "bob"))
    ba = ok(P, "POST", "/api/kanban/boards", {"name": "de alice"}, A)
    ok(P, "POST", "/api/kanban/boards", {"name": "de bob"}, Bc)
    assert [x["name"] for x in ok(P, "GET", "/api/kanban/boards", cookie=A)] == ["de alice"] and ba["owner"] == "alice"
    assert [x["name"] for x in ok(P, "GET", "/api/kanban/boards", cookie=Bc)] == ["de bob"]
    assert call(P, "GET", f"/api/kanban/boards/{ba['id']}", cookie=Bc)[0] == 404
    assert call(P, "POST", f"/api/kanban/boards/{ba['id']}/cards", {"title": "x"}, Bc)[0] == 404
    assert call(P, "POST", "/api/kanban/share", {"on": True}, Bc)[0] == 403  # not an admin
    # guests need no login, even in multi-user mode
    assert ok(P + 3, "POST", f"/k/{ba['token']}/api/cards", {"title": "guest"})["by"] == ""
    assert ok(P, "GET", f"/api/kanban/boards/{ba['id']}", cookie=A)["cards"][0]["title"] == "guest"
finally:
    srv.terminate()
    srv.wait()
shutil.rmtree(TMP, ignore_errors=True)
print("kanban: all checks passed")
