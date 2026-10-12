#!/usr/bin/env python3
"""Self-check for Goals: intake -> answers -> start -> fake brain goal_report -> verifier fail -> iteration 2 -> pass -> done + notice;
max_iter -> failed + notice; blocked -> message -> running; the deploy guard on permission checks; a recurring schedule firing.
Runs server.py from a temp copy on a free port, HOME and data in a temp dir, a fake `claude` on PATH.
Run: python3 scripts/test_goals.py   (~40 s: the worker ticks every 20 s)"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="flows-goals-"))
BIN, HOME, PROJ = TMP / "bin", TMP / "home", TMP / "home/proj"
BIN.mkdir()
PROJ.mkdir(parents=True)
# Fake claude. One-shot (-p, prompt on stdin): intake -> questions; verifier -> fail on its 1st call per goal tag, then pass
# (ALWAYSFAIL: always fail). Stream (a goal brain): every user message -> goal_report done (BLOCKME first time: blocked).
(BIN / "claude").write_text(f"""#!/usr/bin/env python3
import json, os, re, sys
from pathlib import Path
from urllib.request import Request, urlopen
T = Path({str(TMP)!r})
out = lambda o: (print(json.dumps(o)), sys.stdout.flush())
if "--input-format" not in sys.argv:
    prompt = sys.stdin.read()
    (T / "oneshot.log").open("a").write(json.dumps(sys.argv) + "\\n")
    if "BADJSON" in prompt or "BADSHAPE" in prompt:  # intake answers that aren't usable
        out({{"type": "result", "is_error": False, "result": "sorry, no JSON" if "BADJSON" in prompt else '{{"questions": ["a", 3]}}'}})
        raise SystemExit
    tag = re.search(r"TAG-(\\w+)", prompt).group(1)
    if "independent verifier" in prompt:
        f = T / ("v-" + tag)
        n = int(f.read_text()) + 1 if f.exists() else 1
        f.write_text(str(n))
        ok = n > 1 and "ALWAYSFAIL" not in prompt
        res = {{"verdict": "pass" if ok else "fail", "summary": "checked " + str(n), "failing": [] if ok else ["e2e login broken " + str(n)]}}
    else:
        res = {{"questions": [{{"id": "figma", "q": "Figma URL?", "hint": "figma.com/..."}}, {{"id": "api", "q": "Backend API base URL?"}}],
               "acceptance": ["tests pass", "lint passes"]}}
    out({{"type": "result", "is_error": False, "result": "Here: " + json.dumps(res)}})
    raise SystemExit
(T / "argv.log").open("a").write(json.dumps(sys.argv + [os.environ.get("FLOWS_GOAL", "")]) + "\\n")
def api(tool, args):
    req = Request("http://127.0.0.1:" + os.environ["FLOWS_PORT"] + "/api/brain/" + tool, data=json.dumps(args).encode(), method="POST",
                  headers={{"Content-Type": "application/json", "X-Flow": "1", "X-Brain": os.environ["FLOWS_BRAIN_TOKEN"]}})
    return json.loads(urlopen(req).read())["text"]
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
    if "GUARD" in text and text.startswith("[Goal] "):  # permission checks go through the goal guard, not to the user
        for cmd in ("git push origin main", "git push -u origin goal/sonora-main", "npm run deploy && vercel --prod", "pytest -q",
                    "git push origin goal/sonora-main:main", "git push origin goal/other", "git -C . push --force origin goal/sonora-main",
                    "git merge main", "git checkout main && git merge goal/sonora-main", "git commit -m x && git push origin goal/sonora-main"):
            n += 1
            out({{"type": "control_request", "request_id": f"r{{n}}", "request": {{"subtype": "can_use_tool", "tool_name": "Bash", "input": {{"command": cmd}}}}}})
            resp = json.loads(sys.stdin.readline())
            (T / "guard.log").open("a").write(cmd + " => " + resp["response"]["response"]["behavior"] + "\\n")
    if os.environ.get("FLOWS_ASSISTANT"):  # the assistant (WhatsApp) drives goals with its own tools
        reply(api("goal_answer", {{"id": text.split()[-1], "answers": {{"figma": "from whatsapp"}}}}) if "ANSWER" in text else api("goal_list", {{}}))
        continue
    blocked = "BLOCKME" in text and not (T / "was-blocked").exists()
    if blocked:
        (T / "was-blocked").write_text("1")
    reply(api("goal_report", {{"verdict": "blocked" if blocked else "done", "summary": "need the API key" if blocked else "all green"}}))
""")
(BIN / "claude").chmod(0o755)
(BIN / "notify-send").write_text("#!/bin/sh\n")  # no desktop pop-ups from the test
(BIN / "notify-send").chmod(0o755)
d = TMP / "app"
d.mkdir()
for f in ("server.py", "index.html"):
    shutil.copy(REPO / f, d / f)
with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    P = s.getsockname()[1]
srv = subprocess.Popen([sys.executable, "server.py"], cwd=d, stdout=open(TMP / "server.log", "w"), stderr=subprocess.STDOUT,
                       env={**os.environ, "PATH": f"{BIN}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(HOME), "FLOWS_DATA": str(d / "data")})


def call(method, path, body=None):
    req = Request(f"http://127.0.0.1:{P}{path}", data=json.dumps(body).encode() if body is not None else None, method=method,
                  headers={"Content-Type": "application/json", "X-Flow": "1"})
    try:
        with urlopen(req, timeout=70) as r:
            return r.status, json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def wait(gid, *status, t=30):
    for _ in range(t * 5):
        g = call("GET", f"/api/goals/{gid}")[1]
        if g["status"] in status:
            return g
        time.sleep(0.2)
    raise AssertionError(f"{gid} stuck in {g['status']} (wanted {status}): {g}")


def notices(gid):
    return [x for x in call("GET", "/api/assistant/outbox?since=0&wait=0")[1] if x["type"] == "notice" and x.get("goal") == gid]


def new(tag, **kw):
    s, g = call("POST", "/api/goals", {"name": f"Sonora {tag}", "folder": str(PROJ), "objective": f"Build it TAG-{tag}", **kw})
    assert s == 200 and g["status"] == "intake", g
    return g


try:
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", P), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)

    # create -> questions; answers -> ready; start; verifier fails once -> iteration 2 -> pass -> done + notice
    g = new("main")
    assert [q["id"] for q in g["questions"]] == ["figma", "api"] and g["acceptance"] == ["tests pass", "lint passes"], g
    assert call("POST", "/api/goals", {"name": "x", "folder": "/no/such", "objective": "y"})[0] == 400
    assert call("POST", f"/api/goals/{g['id']}/start")[0] == 400  # intake not answered yet
    s, g = call("POST", f"/api/goals/{g['id']}/answers", {"answers": {"figma": "https://figma.com/f/1", "api": "https://api.x"},
                                                       "acceptance": ["tests pass", "lint passes", "GUARD"]})
    assert s == 200 and g["status"] == "ready" and g["answers"]["api"] == "https://api.x", g
    s, g = call("POST", f"/api/goals/{g['id']}/start")
    assert s == 200 and g["status"] == "running" and g["run"] and g["iteration"] == 1, g
    g = wait(g["id"], "done")
    assert g["iteration"] == 2 and [h["verdict"] for h in g["history"]] == ["fail", "pass"], g
    assert g["history"][0]["failing"] == ["e2e login broken 1"], g["history"]
    assert "DONE" in g["report"] and "goal/sonora-main" in g["report"] and len(g["report"].splitlines()) == 3, g["report"]
    assert [x["text"] for x in notices(g["id"])] == [g["report"]], notices(g["id"])
    argv = json.loads((TMP / "argv.log").read_text().splitlines()[0])
    assert argv[-1] == "1" and "AskUserQuestion" in argv[argv.index("--disallowedTools") + 1], argv
    assert "autonomous Goal" in argv[argv.index("--append-system-prompt") + 1]
    run = call("GET", f"/api/runs/{g['run']}")[1]
    sent = [e["text"] for e in run["events"] if e["type"] == "input"]
    assert "https://api.x" in sent[0] and "Branch: goal/sonora-main" in sent[0] and "e2e login broken 1" in sent[1], sent
    assert run["status"] == "stopped", run["status"]  # the brain is ended when the goal finishes
    guard = (TMP / "guard.log").read_text().splitlines()
    assert guard == ["git push origin main => deny", "git push -u origin goal/sonora-main => allow", "npm run deploy && vercel --prod => deny",
                     "pytest -q => allow", "git push origin goal/sonora-main:main => deny", "git push origin goal/other => deny",
                     "git -C . push --force origin goal/sonora-main => deny", "git merge main => allow",
                     "git checkout main && git merge goal/sonora-main => deny", "git commit -m x && git push origin goal/sonora-main => allow"], guard
    assert not [x for x in call("GET", "/api/assistant/outbox?since=0&wait=0")[1] if x["type"] == "approval"]

    deny = json.loads((TMP / "oneshot.log").read_text().splitlines()[-1])
    deny = deny[deny.index("--disallowedTools") + 1]
    assert "Edit" in deny and "Write" in deny and "Bash(git push:*)" in deny and "Bash(git commit:*)" in deny, deny  # verifier: no edits, no git writes

    # intake failure (no JSON, or the wrong shape): still a usable goal, not a 500
    for bad in ("BADJSON", "BADSHAPE"):
        s, x = call("POST", "/api/goals", {"name": bad, "folder": str(PROJ), "objective": bad})
        assert s == 200 and x["status"] == "intake" and x["questions"] == [] and "Intake failed" in x["report"], (s, x)
        assert call("POST", f"/api/goals/{x['id']}/answers", {"answers": {}, "acceptance": ["works"]})[1]["status"] == "ready"
        call("DELETE", f"/api/goals/{x['id']}")

    # max_iter: the verifier always fails -> 5 iterations -> failed + notice with what is pending
    f = new("ALWAYSFAIL")
    call("POST", f"/api/goals/{f['id']}/answers", {"answers": {}})
    call("POST", f"/api/goals/{f['id']}/start")
    f = wait(f["id"], "failed", t=60)
    assert f["iteration"] == 5 and len(f["history"]) == 5 and all(h["verdict"] == "fail" for h in f["history"]), f
    n = notices(f["id"])
    assert len(n) == 1 and "FAILED" in n[0]["text"] and "Pending: e2e login broken 5" in n[0]["text"], n

    # blocked -> notice -> message resumes it
    b = new("BLOCKME")
    call("POST", f"/api/goals/{b['id']}/answers", {"answers": {}})
    call("POST", f"/api/goals/{b['id']}/start")
    b = wait(b["id"], "blocked")
    assert "BLOCKED" in notices(b["id"])[0]["text"] and "need the API key" in b["report"], b
    assert call("POST", f"/api/goals/{b['id']}/message", {"text": "key is abc"})[1]["status"] == "running"
    b = wait(b["id"], "verifying", "running", "done")
    assert "[User] key is abc" in [e["text"] for e in call("GET", f"/api/runs/{b['run']}")[1]["events"] if e["type"] == "input"]
    wait(b["id"], "done")

    # stop, delete, 404s
    s, x = call("POST", f"/api/goals/{b['id']}/message", {"text": "more"})
    assert s == 400, x  # not running any more
    assert call("POST", f"/api/goals/{f['id']}/stop")[1]["status"] == "failed"  # finished goals stay as they were

    # recurring: a due schedule starts the goal again with the stored answers (no intake), worker tick <= 20 s
    s, g2 = call("POST", f"/api/goals/{g['id']}/schedule", {"schedule": {"at": time.strftime("%H:%M"), "last": "2000-01-01 00:00"}})
    assert s == 200 and g2["schedule"]["at"] == time.strftime("%H:%M"), g2
    for _ in range(225):  # one worker tick (20 s) plus slack
        g2 = call("GET", f"/api/goals/{g['id']}")[1]
        if g2["run"] != g["run"]:
            break
        time.sleep(0.2)
    assert g2["run"] != g["run"] and g2["schedule"]["last"] > "2000", g2  # fired, and won't fire again for this slot
    g2 = wait(g["id"], "done")
    assert g2["run"] != g["run"] and g2["history"][-1]["verdict"] == "pass" and len(notices(g["id"])) == 2, g2
    assert call("POST", f"/api/goals/{g['id']}/schedule", {"schedule": None})[1]["schedule"] is None

    assert call("DELETE", f"/api/goals/{f['id']}")[0] == 200 and call("GET", f"/api/goals/{f['id']}")[0] == 404
    # the assistant's goal tools, and which brains see which MCP tools
    w = new("wa")
    call("POST", "/api/assistant/message", {"text": "ANSWER " + w["id"]})
    for _ in range(100):
        out = [x["text"] for x in call("GET", "/api/assistant/outbox?since=0&wait=1")[1] if x["type"] == "reply"]
        if out:
            break
    assert '"status": "ready"' in out[0] and call("GET", f"/api/goals/{w['id']}")[1]["answers"] == {"figma": "from whatsapp"}, out
    def tools(**env):
        p = subprocess.run([sys.executable, str(d / "server.py"), "brain-mcp"], input='{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n',
                           capture_output=True, text=True, env={**os.environ, "FLOWS_PORT": "1", "FLOWS_BRAIN_TOKEN": "x", **env})
        return {t["name"] for t in json.loads(p.stdout)["result"]["tools"]}
    assert "goal_report" in tools(FLOWS_GOAL="1") and not {"goal_create", "set_job"} & tools(FLOWS_GOAL="1")
    assert {"goal_create", "goal_list", "set_job"} <= tools(FLOWS_ASSISTANT="1") and "goal_report" not in tools(FLOWS_ASSISTANT="1")
    assert {x["id"] for x in call("GET", "/api/goals")[1]} == {g["id"], b["id"], w["id"]}
    print("goals OK")
finally:
    srv.terminate()
    srv.wait()
    if sys.exc_info()[0]:
        print("server log:", (TMP / "server.log").read_text()[-3000:])
    shutil.rmtree(TMP, ignore_errors=True)
