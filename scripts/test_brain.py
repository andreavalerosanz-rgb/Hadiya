#!/usr/bin/env python3
"""Self-check for the Second Brain: brain-mcp, /api/brain auth and scoping, child questions routed to the brain.
Runs server.py from a temp copy on a free port with a fake `claude` on PATH (like test_multiuser.py).
Run: python3 scripts/test_brain.py"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hadiya-brain-"))
BIN, LOG = TMP / "bin", TMP / "argv.log"
BIN.mkdir()
(BIN / "claude").write_text(f"""#!/usr/bin/env python3
import json, os, sys
open({str(LOG)!r}, "a").write(json.dumps(sys.argv) + "\\n")
if os.environ.get("HADIYA_BRAIN_TOKEN"):
    open({str(TMP / "token")!r}, "w").write(os.environ["HADIYA_BRAIN_TOKEN"] + " " + os.environ["HADIYA_PORT"])
out = lambda o: (print(json.dumps(o)), sys.stdout.flush())
def reply(text):
    out({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": "did " + text[:30]}}]}}}})
    out({{"type": "result", "is_error": False, "result": "ok", "total_cost_usd": 0}})
out({{"type": "system", "subtype": "init", "session_id": "fake"}})
for line in sys.stdin:
    m = json.loads(line)
    if m.get("type") == "user":
        c = m["message"]["content"]
        if "ASK" in c:
            out({{"type": "control_request", "request_id": "q1", "request": {{"subtype": "can_use_tool", "tool_name": "AskUserQuestion",
                 "input": {{"questions": [{{"question": "Color?", "options": [{{"label": "red"}}, {{"label": "blue"}}]}}]}}}}}})
        else:
            reply(c)
    elif m.get("type") == "control_response":
        reply("answered " + json.dumps(m["response"]["response"].get("updatedInput", {{}}).get("answers")))
""")
(BIN / "claude").chmod(0o755)
d = TMP / "app"
d.mkdir()
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, d / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=d, env={**os.environ, "PATH": f"{BIN}:{os.environ['PATH']}", "PORT": str(P)},
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def call(method, path, body=None, brain=None):
    h = {"Content-Type": "application/json", "X-Flow": "1", **({"X-Brain": brain} if brain is not None else {})}
    req = Request(f"http://127.0.0.1:{P}{path}", data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def wait(rid, ok):
    for _ in range(200):
        s, r = call("GET", f"/api/runs/{rid}")
        if s == 200 and ok(r):
            return r
        time.sleep(0.1)
    raise AssertionError(f"run {rid} never got there: {r}")


try:
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", P), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    B = call("POST", "/api/sessions", {"message": "build a site", "brain": True, "agents": 2,
                                       "allowed_tools": "Read", "permission_mode": "acceptEdits", "model": "opus"})[1]["id"]
    wait(B, lambda r: r["status"] == "idle")
    assert [r for r in call("GET", "/api/runs")[1] if r["id"] == B][0]["brain"] is True
    tok, port = (TMP / "token").read_text().split()
    argv = json.loads(LOG.read_text().splitlines()[0])
    assert "brain-mcp" in argv[argv.index("--mcp-config") + 1] and tok not in " ".join(argv) and "mcp__hadiya" in " ".join(argv)
    assert "Second Brain of this project" in argv[argv.index("--append-system-prompt") + 1]

    # auth: no token, a wrong one, and a valid one outside /api/brain
    assert call("POST", "/api/brain/list_sessions", {})[0] == 403
    assert call("POST", "/api/brain/list_sessions", {}, brain="nope")[0] == 403
    assert call("GET", "/api/runs", brain=tok)[0] == 403
    assert call("POST", "/api/brain/list_sessions", {}, brain=tok) == (200, {"text": "No sessions yet."})

    # brain-mcp over stdio: initialize, tools/list, then start a child through it
    mcp = subprocess.Popen([sys.executable, str(d / "server.py"), "brain-mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                           env={**os.environ, "HADIYA_BRAIN_TOKEN": tok, "HADIYA_PORT": port, "HADIYA_DATA": "/nonexistent"})
    rpc = lambda i, m, prm={}: (mcp.stdin.write(json.dumps({"jsonrpc": "2.0", "id": i, "method": m, "params": prm}) + "\n"),
                                mcp.stdin.flush(), json.loads(mcp.stdout.readline()))[2]
    assert rpc(1, "initialize", {"protocolVersion": "2025-06-18"})["result"]["serverInfo"]["name"] == "hadiya"
    mcp.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    names = [t["name"] for t in rpc(2, "tools/list")["result"]["tools"]]
    assert names == ["start_session", "list_sessions", "read_session", "send_message", "answer_question", "stop_session"], names
    assert rpc(3, "nope")["error"]["code"] == -32601
    res = rpc(4, "tools/call", {"name": "start_session", "arguments": {"message": "ASK about colors", "name": "Web", "cwd": "/tmp"}})["result"]
    assert not res["isError"], res
    C = res["content"][0]["text"].split()[-1].rstrip(".")
    assert rpc(5, "tools/call", {"name": "read_session", "arguments": {"id": "x"}})["result"]["isError"]
    mcp.stdin.close()
    mcp.wait()

    c = wait(C, lambda r: r["status"] == "asking")
    assert c["parent"] == B and c["name"] == "Web"
    assert c["config"] == {"permission_mode": "acceptEdits", "allowed_tools": "Read", "caps": None, "sub_models": None,
                           "agents": 3, "cwd": "/tmp", "model": "sonnet"}, c["config"]
    b = wait(B, lambda r: any(e.get("from") == C for e in r["events"]))
    q = [e for e in b["events"] if e.get("from") == C][0]
    assert q["type"] == "input" and q["text"].startswith(f'[Hadiya] Session "Web" ({C}) asks you (question_id q1)') and "Color?" in q["text"]

    # scoping: a session of the user's own that the brain didn't start is invisible to it
    S = call("POST", "/api/sessions", {"message": "mine"})[1]["id"]
    assert call("POST", "/api/brain/read_session", {"id": S}, brain=tok)[0] == 404
    assert call("POST", "/api/brain/send_message", {"id": S, "text": "x"}, brain=tok)[0] == 404
    assert C in call("POST", "/api/brain/list_sessions", {}, brain=tok)[1]["text"]

    ans = {"id": C, "question_id": "q1", "answers": {"Color?": "red"}}
    assert call("POST", "/api/brain/answer_question", ans, brain=tok) == (200, {"text": "Answered."})
    s, e = call("POST", "/api/brain/answer_question", ans, brain=tok)
    assert s == 400 and "already answered" in e["error"], e
    c = wait(C, lambda r: r["status"] == "idle")
    a = [e for e in c["events"] if e["type"] == "answer"][0]
    assert a["by"] == "brain" and a["answers"] == {"Color?": "red"}
    b = wait(B, lambda r: any("finished its turn" in (e.get("text") or "") for e in r["events"]))
    assert 'did answered {"Color?": "red"}' in [e for e in b["events"] if "finished its turn" in (e.get("text") or "")][0]["text"]
    t = call("POST", "/api/brain/read_session", {"id": C, "since": 0}, brain=tok)[1]["text"]
    assert "question q1" in t and "answer q1 by brain" in t and "next since=" in t, t
    # a child of a deleted brain asks the user again (no crash, no forward)
    call("DELETE", f"/api/runs/{B}")
    assert call("POST", "/api/brain/list_sessions", {}, brain=tok)[0] == 403
    call("POST", f"/api/sessions/{C}/message", {"text": "ASK again"})
    wait(C, lambda r: r["status"] == "asking")
finally:
    srv.terminate()

# the admin package can't have a brain
os.environ.update(HADIYA_PACKAGE="admin", HADIYA_DATA=str(TMP / "pkg"))
sys.path.insert(0, str(d))
import server
try:
    server.start_session({"message": "x", "brain": True}, None)
    raise AssertionError("brain allowed in the admin package")
except ValueError:
    pass
shutil.rmtree(TMP, ignore_errors=True)
print("brain self-check: all passed")
