#!/usr/bin/env python3
"""Self-check for Flows Asistente: bearer API, message -> outbox reply, approvals in confirm mode, /auto on, jobs firing,
the job MCP tools, voice notes (fake transcriber), inbound and outbound files, the brief notice. Runs server.py from a temp copy on a free port, HOME and data in a temp dir, a fake `claude` on PATH.
Run: python3 scripts/test_assistant.py   (takes ~30 s: the job worker ticks every 20 s)"""
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
    text = c if isinstance(c, str) else c[0]["text"]
    if "MAKE" in text:  # MAKEFILE <path>: the agent writes a file during its turn
        _, path = text.split("MAKE", 1)[1].split(" ", 1)
        open(path.split()[0], "w").write("%PDF-1.4 test")
        reply("made")
    elif "EMAIL" in c:
        n += 1
        out({{"type": "control_request", "request_id": f"r{{n}}", "request": {{"subtype": "can_use_tool",
             "tool_name": "mcp__claude_ai_Gmail__send_message", "input": {{"to": "x@y.z"}}}}}})
        resp = json.loads(sys.stdin.readline())
        reply("mail " + resp["response"]["response"]["behavior"])
    else:
        reply("NOTHING" if "SILENT" in text else "echo: " + text)
""")
(BIN / "claude").chmod(0o755)
(BIN / "stt").write_text("#!/bin/sh\ncat \"$1\" >/dev/null && echo 'hola desde el audio'\n")  # fake transcriber: the file path is its last argument
(BIN / "stt").chmod(0o755)
d = TMP / "app"
d.mkdir()
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, d / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=d, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       env={**os.environ, "PATH": f"{BIN}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(HOME), "FLOWS_DATA": str(d / "data"), "FLOWS_TRANSCRIBE": str(BIN / "stt")})


def call(method, path, body=None, token=None, h=None):
    h = {"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {"X-Flow": "1"}), **(h or {})}
    req = Request(f"http://127.0.0.1:{P}{path}", data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urlopen(req, timeout=70) as r:
            return r.status, json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


since = 0


def next_item(tok, kind=None):
    """The next outbox item (of this kind), long-polling."""
    global since
    for _ in range(10):
        s, items = call("GET", f"/api/assistant/outbox?since={since}&wait=15", token=tok)
        assert s == 200, items
        for x in items:
            since = x["id"]
            if x["type"] == kind or (kind is None and x["type"] != "resolved"):
                return x
    raise AssertionError(f"no {kind} in the outbox")


try:
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", P), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    TOK = json.loads((d / "data/assistant.json").read_text())["token"]
    assert call("GET", "/api/assistant/settings", token="wrong")[0] == 403
    s, cfg = call("GET", "/api/assistant/settings", token=TOK)
    assert s == 200 and cfg["auto"] is False and {j["id"] for j in cfg["jobs"]} == {"brief", "heartbeat"}, cfg

    # message -> outbox reply (bridge channel)
    assert call("POST", "/api/assistant/message", {"text": "hola", "channel": "whatsapp", "from": "+34600"}, token=TOK) == (200, {"ok": True})
    x = next_item(TOK)
    assert x["type"] == "reply" and x["text"] == "echo: [whatsapp +34600] hola", x
    argv = json.loads(LOG.read_text().splitlines()[0])
    prompt, allowed = argv[argv.index("--append-system-prompt") + 1], argv[argv.index("--allowedTools") + 1]
    assert "Flows Asistente" in prompt and "PROFILE-MARK" in prompt, prompt[:300]
    assert "AskUserQuestion" in argv[argv.index("--disallowedTools") + 1] and argv[-1] == "1"
    assert "mcp__claude_ai_Gmail__search_threads" in allowed and "send_message" not in allowed and "mcp__flows" in allowed
    # the web UI uses the same endpoints with normal Flows auth (X-Flow on the laptop)
    assert call("GET", "/api/assistant/settings")[1]["run"]

    # confirm mode: an outward action waits for an approval in the outbox
    call("POST", "/api/assistant/message", {"text": "send EMAIL"}, token=TOK)
    x = next_item(TOK)
    assert x["type"] == "approval" and x["approval_id"] == "r1" and "send_message" in x["text"], x
    assert call("POST", "/api/assistant/approve", {"approval_id": "r1", "allow": True}, token=TOK) == (200, {"ok": True})
    assert next_item(TOK)["text"] == "mail allow"
    res = [x for x in call("GET", "/api/assistant/outbox?since=0&wait=0", token=TOK)[1] if x["type"] == "resolved"]
    assert [(x["approval_id"], x["allow"]) for x in res] == [("r1", True)], res  # every client learns it was answered
    assert call("POST", "/api/assistant/approve", {"approval_id": "r1", "allow": True}, token=TOK)[0] == 400  # already answered
    call("POST", "/api/assistant/message", {"text": "EMAIL again"}, token=TOK)
    x = next_item(TOK)
    assert x["type"] == "approval" and x["approval_id"] == "r2", x
    call("POST", "/api/assistant/approve", {"approval_id": "r2", "allow": False}, token=TOK)
    assert next_item(TOK)["text"] == "mail deny"

    # full auto: no approval
    call("POST", "/api/assistant/message", {"text": "/auto on"}, token=TOK)
    assert next_item(TOK)["type"] == "notice" and call("GET", "/api/assistant/settings", token=TOK)[1]["auto"] is True
    call("POST", "/api/assistant/message", {"text": "EMAIL auto"}, token=TOK)
    x = next_item(TOK)
    assert (x["type"], x["text"]) == ("reply", "mail allow"), x
    assert call("POST", "/api/assistant/settings", {"auto": False}, token=TOK)[1]["auto"] is False

    # the assistant's own job tools (brain-mcp, FLOWS_ASSISTANT=1)
    btok = (TMP / "token").read_text()
    s, r = call("POST", "/api/brain/set_job", {"id": "rem", "at": "23:59", "date": "2099-01-01", "prompt": "X"}, h={"X-Brain": btok})
    assert s == 200 and "rem" in r["text"], r
    assert "rem" not in call("POST", "/api/brain/remove_job", {"id": "rem"}, h={"X-Brain": btok})[1]["text"]
    out = subprocess.run([sys.executable, str(d / "server.py"), "brain-mcp"], input='{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n',
                         capture_output=True, text=True, env={**os.environ, "FLOWS_ASSISTANT": "1"}).stdout
    assert "set_job" in out
    out = subprocess.run([sys.executable, str(d / "server.py"), "brain-mcp"], input='{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n',
                         capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k != "FLOWS_ASSISTANT"}).stdout
    assert "start_session" in out and "set_job" not in out
    assert call("POST", "/api/assistant/settings", {"jobs": [{"at": "25:00", "prompt": "x"}]}, token=TOK)[0] == 400

    # voice note: transcribed and passed on with the [voz] prefix; junk audio is refused
    import base64
    b64 = lambda b: base64.b64encode(b).decode()
    s, r = call("POST", "/api/assistant/message", {"audio": b64(b"OggS" + b"\0" * 40), "channel": "whatsapp", "from": "+34600"}, token=TOK)
    assert s == 200 and r["text"] == "[voz] hola desde el audio", (s, r)
    assert next_item(TOK)["text"] == "echo: [whatsapp +34600] [voz] hola desde el audio"
    assert call("POST", "/api/assistant/message", {"audio": b64(b"MZ not audio"), "channel": "whatsapp"}, token=TOK)[0] == 400

    # inbound files: sanitised name, saved under data/uploads/<run>/, the assistant gets the path and the caption
    run = call("GET", "/api/assistant/settings", token=TOK)[1]["run"]
    pdf = {"name": "../../etc/in forme.pdf", "data": b64(b"%PDF-1.4 hello")}
    assert call("POST", "/api/assistant/message", {"text": "mira", "channel": "whatsapp", "files": [pdf]}, token=TOK)[0] == 200
    x = next_item(TOK)
    saved = d / "data/uploads" / run / "in forme.pdf"
    assert saved.read_bytes() == b"%PDF-1.4 hello" and "mira" in x["text"] and str(saved) in x["text"], x
    for bad in ({"name": "a.exe", "data": b64(b"MZ")}, {"name": "fake.pdf", "data": b64(b"not a pdf")},
                {"name": "big.txt", "data": b64(b"x" * ((16 << 20) + 1))}):
        assert call("POST", "/api/assistant/message", {"text": "x", "channel": "whatsapp", "files": [bad]}, token=TOK)[0] == 400, bad

    # outbound: a file the assistant wrote during its turn comes out as a `file` item (bad types stay home); send_file tool
    call("POST", "/api/assistant/message", {"text": f"MAKEFILE {d}/data/uploads/{run}/informe.pdf"}, token=TOK)
    x = next_item(TOK, "file")
    assert x["text"] == "informe.pdf" and x["path"] == f"{d}/data/uploads/{run}/informe.pdf", x
    call("POST", "/api/assistant/message", {"text": f"MAKEFILE {d}/data/uploads/{run}/virus.exe"}, token=TOK)
    assert next_item(TOK, "reply")["text"] == "made"
    time.sleep(1)
    assert not [y for y in call("GET", f"/api/assistant/outbox?since={since}&wait=0", token=TOK)[1] if y["type"] == "file"]
    s, r = call("POST", "/api/brain/send_file", {"name": "notas.md", "content": "# hola"}, h={"X-Brain": btok})
    assert s == 200 and "notas.md" in r["text"] and (d / "data/uploads" / run / "notas.md").read_text() == "# hola", r
    assert call("POST", "/api/brain/send_file", {"name": "x.exe", "content": "x"}, h={"X-Brain": btok})[0] == 400

    # the default brief: Mon-Fri 08:30, covers calendar, mail and Flows sessions; when it fires, a notice reaches the bridge
    brief = next(j for j in cfg["jobs"] if j["id"] == "brief")
    assert (brief["at"], brief["days"]) == ("08:30", [0, 1, 2, 3, 4]) and all(k in brief["prompt"] for k in ("Calendar", "Gmail", "Flows sessions")), brief
    fire = {**brief, "at": "00:00", "date": time.strftime("%Y-%m-%d"), "last": "2000-01-01 00:00", "days": list(range(7))}
    assert call("POST", "/api/assistant/settings", {"jobs": [fire]}, token=TOK)[0] == 200
    x = next_item(TOK, "notice")
    assert x["text"].startswith("echo: [Job brief] Daily brief") , x

    # jobs: one-off reminders due now fire on the next worker tick; NOTHING stays silent
    today = time.strftime("%Y-%m-%d")
    jobs = [{"id": "t1", "at": "00:00", "date": today, "prompt": "ping", "last": "2000-01-01 00:00"},
            {"id": "t2", "at": "00:00", "date": today, "prompt": "SILENT", "last": "2000-01-01 00:00"},
            {"id": "later", "at": "23:59", "prompt": "not yet"}]
    assert call("POST", "/api/assistant/settings", {"jobs": jobs}, token=TOK)[0] == 200
    x = next_item(TOK, "notice")
    assert x["text"] == "echo: [Job t1] ping", x
    time.sleep(2)
    s, rest = call("GET", f"/api/assistant/outbox?since={since}&wait=0", token=TOK)
    assert not any("NOTHING" in y["text"] for y in rest), rest
    assert [j["id"] for j in call("GET", "/api/assistant/settings", token=TOK)[1]["jobs"]] == ["later"]  # one-offs removed
    print("ok: test_assistant")
finally:
    srv.terminate()
    shutil.rmtree(TMP, ignore_errors=True)
