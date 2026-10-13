#!/usr/bin/env python3
"""Self-check for multi-user mode (and that single-user mode is unchanged).
Runs server.py from a temp copy of the repo on a free port, with a fake `claude` and a fake `sudo` on PATH.
Run: python3 scripts/test_multiuser.py"""
import base64, getpass, json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO = Path(__file__).resolve().parent.parent
ME = getpass.getuser()  # both test accounts map to this Linux user; the sudo shim only records -u
TMP = Path(tempfile.mkdtemp(prefix="hadiya-test-"))
BIN, LOG = TMP / "bin", TMP / "calls.log"
BIN.mkdir()

(BIN / "claude").write_text(f"""#!/usr/bin/env python3
import getpass, json, os, sys, time
log = lambda s: open({str(LOG)!r}, "a").write(s + "\\n")
out = lambda o: (print(json.dumps(o)), sys.stdout.flush())
def reply(text):
    log(f"claude pid={{os.getpid()}} text={{text[:40]!r}}")
    if "SLEEP" in text:
        time.sleep(60)
    out({{"type": "result", "is_error": False, "result": f"ok cwd={{os.getcwd()}} user={{getpass.getuser()}}", "total_cost_usd": 0}})
if "--input-format" in sys.argv:  # session: stream-json on stdin
    out({{"type": "system", "subtype": "init", "session_id": "fake"}})
    for line in sys.stdin:
        m = json.loads(line)
        if m.get("type") == "user":
            c = m["message"]["content"]
            reply(c if isinstance(c, str) else c[0]["text"])
else:
    reply(sys.stdin.read())
""")
(BIN / "sudo").write_text(f"""#!/usr/bin/env python3
import os, sys
open({str(LOG)!r}, "a").write("sudo " + " ".join(sys.argv[1:4]) + "\\n")
a, env, cwd = sys.argv[1:], dict(os.environ), None
while a and a[0].startswith("-") and a[0] != "--":
    o = a.pop(0)
    if o in ("-u", "-D"):
        v = a.pop(0)
        cwd = v if o == "-D" else cwd
while "=" in a[0]:  # like real sudo: VAR=value only before "--"
    k, v = a.pop(0).split("=", 1)
    env[k] = v
if a[:1] == ["--"]:
    a.pop(0)
os.chdir(cwd)
os.execvpe(a[0], a, env)
""")
for f in BIN.iterdir():
    f.chmod(0o755)
ENVX = {**os.environ, "PATH": f"{BIN}:{os.environ['PATH']}"}


def copy(name):
    d = TMP / name
    d.mkdir()
    for f in ("server.py", "index.html"):
        shutil.copy(REPO / f, d / f)
    return d


def start(d):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    p = subprocess.Popen([sys.executable, "server.py"], cwd=d, env={**ENVX, "PORT": str(port)},
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return p, port
        except OSError:
            time.sleep(0.1)
    raise SystemExit("server did not start")


def call(port, method, path, body=None, cookie=None, flow=True):
    h = {"Content-Type": "application/json", **({"X-Flow": "1"} if flow else {}), **({"Cookie": cookie} if cookie else {})}
    req = Request(f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urlopen(req, timeout=10) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if "json" in r.headers["Content-Type"] else raw), r.headers
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"{}"), e.headers


def wait(port, rid, cookie, ok):
    for _ in range(100):
        s, r, _ = call(port, "GET", f"/api/runs/{rid}", cookie=cookie)
        if s == 200 and ok(r):
            return r
        time.sleep(0.1)
    raise AssertionError(f"run {rid} never got there: {r}")


def gone(pid):
    for _ in range(50):
        try:
            os.kill(pid, 0)
            if "Z" in Path(f"/proc/{pid}/stat").read_text().split()[2]:
                return True  # zombie: exited, not yet reaped
        except (ProcessLookupError, FileNotFoundError):
            return True
        time.sleep(0.1)
    return False


def last_pid():
    return int([l for l in LOG.read_text().splitlines() if l.startswith("claude pid=")][-1].split("pid=")[1].split()[0])


def adduser(d, *args, pw="correct horse battery"):
    r = subprocess.run([sys.executable, "server.py", "adduser", *args], cwd=d, input=f"{pw}\n{pw}\n", text=True,
                       capture_output=True, start_new_session=True)  # no controlling tty: getpass reads stdin
    assert r.returncode == 0, r.stderr


# ---------------- multi-user ----------------
d = copy("multi")
adduser(d, "alice", ME, "--admin")
adduser(d, "bob", ME)
assert oct((d / "data" / "users.json").stat().st_mode & 0o777) == "0o600"
srv, P = start(d)
try:
    assert call(P, "GET", "/api/runs")[0] == 401
    s, page, _ = call(P, "GET", "/")
    assert s == 200 and b"Entrar en Hadiya" in page
    assert call(P, "POST", "/api/login", {"user": "alice", "password": "correct horse battery"}, flow=False)[0] == 403
    assert call(P, "POST", "/api/login", {"user": "alice", "password": "nope"})[0] == 403

    def login(u):
        s, _, h = call(P, "POST", "/api/login", {"user": u, "password": "correct horse battery"})
        assert s == 200 and "HttpOnly" in h["Set-Cookie"] and "SameSite=Strict" in h["Set-Cookie"]
        return h["Set-Cookie"].split(";")[0]
    A, B = login("alice"), login("bob")
    assert call(P, "GET", "/api/me", cookie=A)[1]["user"] == "alice" and call(P, "GET", "/api/me", cookie=A)[1]["admin"]
    assert call(P, "GET", "/api/me", cookie=B)[1]["admin"] is False
    assert call(P, "GET", "/api/remote", cookie=B)[0] == 403 and call(P, "GET", "/api/remote", cookie=A)[0] == 200

    # workflows are per user
    wf = {"name": "Hello", "steps": [{"name": "one", "prompt": "hi {{input}}"}]}
    assert call(P, "PUT", "/api/workflows/w1", wf, A)[0] == 200
    assert call(P, "GET", "/api/workflows", cookie=B)[1] == {}
    assert "w1" in call(P, "GET", "/api/workflows", cookie=A)[1]
    assert call(P, "POST", "/api/workflows/w1/run", {"input": "x"}, B)[0] == 404

    # a run executes as the owner's Linux user, in their home
    rid = call(P, "POST", "/api/workflows/w1/run", {"input": "x"}, A)[1]["id"]
    r = wait(P, rid, A, lambda r: r["status"] == "done")
    assert f"cwd={Path.home()}" in r["steps"][0]["result"], r
    assert f"sudo -n -u {ME}" in LOG.read_text()
    assert [x["id"] for x in call(P, "GET", "/api/runs", cookie=A)[1]] == [rid]
    assert call(P, "GET", "/api/runs", cookie=B)[1] == []
    for m, path in [("GET", f"/api/runs/{rid}"), ("POST", f"/api/runs/{rid}/cancel"), ("DELETE", f"/api/runs/{rid}"),
                    ("GET", f"/shots/{rid}/x.png"), ("POST", f"/api/sessions/{rid}/stop")]:
        assert call(P, m, path, {} if m == "POST" else None, B)[0] == 404, path

    # sessions with an upload: only the owner can fetch it; the dir is shared with the owner's group
    f = {"name": "a.txt", "data": base64.b64encode(b"hello").decode()}
    sid = call(P, "POST", "/api/sessions", {"message": "hi", "files": [f]}, A)[1]["id"]
    wait(P, sid, A, lambda r: r["status"] == "idle")
    assert call(P, "GET", f"/uploads/{sid}/a.txt", cookie=A)[1] == b"hello"
    assert call(P, "GET", f"/uploads/{sid}/a.txt", cookie=B)[0] == 404
    assert oct((d / "data" / "users" / "alice" / "uploads" / sid).stat().st_mode & 0o7777) == "0o2770"
    assert call(P, "POST", f"/api/sessions/{sid}/message", {"text": "hijack"}, B)[0] == 404
    assert call(P, "POST", "/api/queue", {"kind": "message", "run_id": sid, "text": "hijack"}, B)[0] == 404
    assert call(P, "POST", "/api/sessions", {"message": "hi", "cwd": "/etc"}, A)[0] == 400
    qid = call(P, "POST", "/api/queue", {"kind": "workflow", "wf_id": "w1"}, A)[1]["id"]
    assert call(P, "GET", "/api/queue", cookie=B)[1]["items"] == []
    call(P, "DELETE", f"/api/queue/{qid}", cookie=B)
    assert [q["id"] for q in call(P, "GET", "/api/queue", cookie=A)[1]["items"]] == [qid]
    call(P, "DELETE", f"/api/queue/{qid}", cookie=A)

    # cancel and stop really end the claude process
    call(P, "PUT", "/api/workflows/w2", {"name": "Slow", "steps": [{"prompt": "SLEEP"}]}, A)
    rid2 = call(P, "POST", "/api/workflows/w2/run", {"input": ""}, A)[1]["id"]
    time.sleep(1)
    pid = last_pid()
    assert call(P, "POST", f"/api/runs/{rid2}/cancel", {}, A)[0] == 200
    assert gone(pid), "cancel left claude running"
    wait(P, rid2, A, lambda r: r["status"] == "cancelled")
    call(P, "POST", f"/api/sessions/{sid}/message", {"text": "SLEEP"}, A)
    time.sleep(1)
    pid = last_pid()
    call(P, "POST", f"/api/sessions/{sid}/stop", {}, A)
    assert gone(pid), "stop left claude running"

    # logout, and the lockout after repeated wrong passwords
    call(P, "POST", "/api/logout", {}, B)
    assert call(P, "GET", "/api/runs", cookie=B)[0] == 401
    codes = [call(P, "POST", "/api/login", {"user": "bob", "password": "bad"})[0] for _ in range(6)]
    assert codes == [403] * 5 + [429], codes
finally:
    srv.terminate()

# ---------------- single user: no users.json, no login, no sudo ----------------
d = copy("single")
LOG.write_text("")
srv, P = start(d)
try:
    assert call(P, "GET", "/api/runs")[0] == 200
    assert call(P, "GET", "/api/me")[1]["user"] is None
    assert b"Entrar en Hadiya" not in call(P, "GET", "/")[1]
    call(P, "PUT", "/api/workflows/w1", {"name": "Hello", "steps": [{"prompt": "hi"}]})
    rid = call(P, "POST", "/api/workflows/w1/run", {"input": ""})[1]["id"]
    wait(P, rid, None, lambda r: r["status"] == "done")
    assert "sudo" not in LOG.read_text() and (d / "data" / "workflows.json").exists()
    sid = call(P, "POST", "/api/sessions", {"message": "hi", "files": [{"name": "a.txt", "data": "aGk="}]})[1]["id"]
    wait(P, sid, None, lambda r: r["status"] == "idle")
    assert call(P, "GET", f"/uploads/{sid}/a.txt")[1] == b"hi" and (d / "data" / "uploads" / sid / "a.txt").exists()
finally:
    srv.terminate()
shutil.rmtree(TMP, ignore_errors=True)
print("multi-user self-check: all passed")
