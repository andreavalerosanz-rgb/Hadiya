#!/usr/bin/env python3
"""Self-check for Goals: intake -> answers -> start -> fake brain goal_report -> verifier fail -> iteration 2 -> pass -> done + notice;
max_iter -> failed + notice; blocked -> message -> running; the deploy guard on permission checks; a recurring schedule firing.
Runs server.py from a temp copy on a free port, HOME and data in a temp dir, a fake `claude` on PATH.
Run: python3 scripts/test_goals.py   (~2 min: the worker ticks every 20 s)"""
import json, os, shutil, socket, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

REPO = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="hadiya-goals-"))
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
    if "You write the Objective" in prompt:
        idea = re.search(r"Idea: (.*)", prompt).group(1)
        out({{"type": "result", "is_error": False, "result": json.dumps({{"name": "Drafted " + idea[:80], "objective": "# Objetivo: " + idea}}), "total_cost_usd": 0.25}})
        raise SystemExit
    tag = re.search(r"TAG-(\\w+)", prompt).group(1)
    if "independent verifier" in prompt:
        f = T / ("v-" + tag)
        n = int(f.read_text()) + 1 if f.exists() else 1
        f.write_text(str(n))
        ok = n > 1 and "ALWAYSFAIL" not in prompt
        res = {{"verdict": "pass" if ok else "fail", "summary": "checked " + str(n), "failing": [] if ok else ["e2e login broken " + str(n)],
               "criteria": [{{"c": "tests pass", "ok": ok, "evidence": "ran pytest"}}, "junk"]}}
        if "BADVERDICT" in prompt:  # a verdict of the wrong shape
            res = {{"verdict": "fail", "failing": 5}}
    else:
        res = {{"questions": [{{"id": "figma", "q": "Figma URL?", "hint": "figma.com/...", "default": "use placeholders"}}, {{"id": "api", "q": "Backend API base URL?"}}],
               "acceptance": ["tests pass", "lint passes"]}}
    out({{"type": "result", "is_error": False, "result": "Here: " + json.dumps(res), "total_cost_usd": 0.25}})
    raise SystemExit
(T / "argv.log").open("a").write(json.dumps(sys.argv + [os.environ.get("HADIYA_GOAL", "")]) + "\\n")
def api(tool, args):
    req = Request("http://127.0.0.1:" + os.environ["HADIYA_PORT"] + "/api/brain/" + tool, data=json.dumps(args).encode(), method="POST",
                  headers={{"Content-Type": "application/json", "X-Flow": "1", "X-Brain": os.environ["HADIYA_BRAIN_TOKEN"]}})
    return json.loads(urlopen(req).read())["text"]
def reply(text):
    out({{"type": "assistant", "message": {{"content": [{{"type": "text", "text": text}}]}}}})
    out({{"type": "result", "is_error": False, "result": text, "total_cost_usd": 0.5}})
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
                    "git merge main", "git checkout main && git merge goal/sonora-main", "git commit -m x && git push origin goal/sonora-main",
                    "git push -u origin goal/sonora-main 2>&1 | tail -3", "git -C /p push -u origin goal/sonora-main",
                    "cat vercel.json", 'git commit -m "fix ssh"', "ls src/mail/", "ssh host", "npm run x && vercel --prod", 'git "push" origin HEAD:main',
                    "curl -X POST http://127.0.0.1:" + os.environ["HADIYA_PORT"] + "/api/goals/x/limits"):
            n += 1
            out({{"type": "control_request", "request_id": f"r{{n}}", "request": {{"subtype": "can_use_tool", "tool_name": "Bash", "input": {{"command": cmd}}}}}})
            resp = json.loads(sys.stdin.readline())
            (T / "guard.log").open("a").write(cmd + " => " + resp["response"]["response"]["behavior"] + "\\n")
        for tool in ("mcp__claude_ai_Trello__trelloWriteCard", "mcp__claude_ai_Gmail__send_message", "mcp__claude_ai_Trello__trelloReadCard"):
            n += 1
            out({{"type": "control_request", "request_id": f"r{{n}}", "request": {{"subtype": "can_use_tool", "tool_name": tool, "input": {{}}}}}})
            resp = json.loads(sys.stdin.readline())
            (T / "guard.log").open("a").write(tool + " => " + resp["response"]["response"]["behavior"] + "\\n")
    if os.environ.get("HADIYA_ASSISTANT"):  # the assistant (WhatsApp) drives goals with its own tools
        reply(api("goal_answer", {{"id": text.split()[-1], "answers": {{"figma": "from whatsapp"}}}}) if "ANSWER" in text else api("goal_list", {{}}))
        continue
    wb = T / ("was-blocked-" + (re.search(r"TAG-(\\w+)", text) or [0, ""])[1])  # each goal tag blocks once
    blocked = "BLOCKME" in text and not wb.exists()
    if blocked:
        wb.write_text("1")
    out({{"type": "assistant", "message": {{"content": [{{"type": "tool_use", "id": "t1", "name": "Bash", "input": {{"command": "pytest -q"}}}}]}}}})
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
                       env={**os.environ, "PATH": f"{BIN}:{os.environ['PATH']}", "PORT": str(P), "HOME": str(HOME), "HADIYA_DATA": str(d / "data"),
                           **{f"GIT_{w}_{k}": v for w in ("AUTHOR", "COMMITTER") for k, v in (("NAME", "t"), ("EMAIL", "t@t"))}})


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
    assert [q["default"] for q in g["questions"]] == ["use placeholders", ""], g["questions"]
    argv = json.loads((TMP / "oneshot.log").read_text().splitlines()[0])  # intake: sonnet, may look at git
    assert argv[argv.index("--model") + 1] == "sonnet" and "Bash(git branch:*)" in argv[argv.index("--allowedTools") + 1], argv
    assert call("POST", "/api/goals", {"name": "x", "folder": "/no/such", "objective": "y"})[0] == 400
    s, x = call("POST", "/api/goals", {"name": "Sonora main", "folder": str(PROJ), "objective": "y"})
    assert s == 400 and "branch name" in x["error"], (s, x)  # the branch name is taken in this folder
    assert call("POST", f"/api/goals/{g['id']}/start")[0] == 400  # intake not answered yet
    s, g = call("POST", f"/api/goals/{g['id']}/answers", {"answers": {"figma": "https://figma.com/f/1", "api": "https://api.x"},
                                                       "acceptance": ["tests pass", "lint passes", "GUARD"]})
    assert s == 200 and g["status"] == "ready" and g["answers"]["api"] == "https://api.x", g
    s, g = call("POST", f"/api/goals/{g['id']}/start")
    assert s == 200 and g["status"] == "running" and g["run"] and g["iteration"] == 1, g
    g = wait(g["id"], "done")
    assert abs(g["cost"] - (0.25 * 3 + 0.5)) < 1e-6 and g["secs"] >= 0 and "live" not in g, g  # intake + 2 verifier calls + the brain run
    row = [x for x in call("GET", "/api/goals")[1] if x["id"] == g["id"]][0]
    assert row["cost"] == g["cost"] and "live" not in row, row
    assert "Figma URL?: https://figma.com/f/1" in [e["text"] for e in call("GET", f"/api/runs/{g['run']}")[1]["events"] if e["type"] == "input"][0]
    assert g["iteration"] == 2 and [h["verdict"] for h in g["history"]] == ["fail", "pass"], g
    assert g["history"][0]["failing"] == ["e2e login broken 1"], g["history"]
    bash = dict(l.split(" => ") for l in (TMP / "guard.log").read_text().splitlines()[:19])
    assert [c for c, v in bash.items() if v == "allow"] == ["git push -u origin goal/sonora-main", "pytest -q", "git merge main",
            "git commit -m x && git push origin goal/sonora-main", "git push -u origin goal/sonora-main 2>&1 | tail -3",
            "git -C /p push -u origin goal/sonora-main", "cat vercel.json", 'git commit -m "fix ssh"', "ls src/mail/"], bash
    assert g["history"][0]["criteria"] == [{"c": "tests pass", "ok": False, "evidence": "ran pytest"}], g["history"][0]  # junk entries dropped
    assert g["history"][1]["criteria"][0]["ok"] is True and call("GET", f"/api/goals/{g['id']}/review")[1]["criteria"] == g["history"][1]["criteria"]
    # limits: clamped, allow filtered to the known services, any status but verifying
    s, x = call("POST", f"/api/goals/{g['id']}/limits", {"max_iter": 99, "max_hours": 0.1, "allow": ["Trello", "Bogus"]})
    assert s == 200 and (x["max_iter"], x["max_hours"], x["allow"]) == (20, 0.5, ["Trello"]), x
    x = call("POST", f"/api/goals/{g['id']}/limits", {"max_iter": 5, "max_hours": 8, "allow": []})[1]
    assert (x["max_iter"], x["max_hours"], x["allow"]) == (5, 8, []), x
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

    # a brain run that vanishes is "Session lost" (not out of time); Continue resumes it on the same branch
    lo = new("BLOCKMElost")
    call("POST", f"/api/goals/{lo['id']}/answers", {"answers": {}})
    call("POST", f"/api/goals/{lo['id']}/start")
    lo = wait(lo["id"], "blocked")
    assert call("DELETE", f"/api/runs/{lo['run']}")[0] == 200
    lo = wait(lo["id"], "failed", t=40)  # next worker tick
    assert lo["lost"] is True and "Session lost" in lo["report"] and "Out of time" not in lo["report"], lo["report"]
    s, lo = call("POST", f"/api/goals/{lo['id']}/continue", {"text": "use tabs"})
    assert s == 200 and lo["status"] == "running" and lo["lost"] is False and lo["iteration"] == 1, lo
    first = [e["text"] for e in call("GET", f"/api/runs/{lo['run']}")[1]["events"] if e["type"] == "input"][0]
    assert "check it out, don't recreate" in first and "Notes from the user: use tabs" in first and "Session lost" in first, first
    wait(lo["id"], "done")

    # a verdict of the wrong shape fails the round cleanly (not stuck verifying)
    bv = new("BADVERDICT", max_iter=1)
    call("POST", f"/api/goals/{bv['id']}/answers", {"answers": {}})
    call("POST", f"/api/goals/{bv['id']}/start")
    bv = wait(bv["id"], "failed")
    assert bv["history"][0]["failing"][0].startswith("verifier error"), bv["history"]

    # blocked -> notice -> message resumes it
    b = new("BLOCKME")
    call("POST", f"/api/goals/{b['id']}/answers", {"answers": {}})
    call("POST", f"/api/goals/{b['id']}/start")
    b = wait(b["id"], "blocked")
    assert "BLOCKED" in notices(b["id"])[0]["text"] and "need the API key" in b["report"], b
    l = b["live"]
    assert l["round"] == 1 and l["of"] == 5 and l["brain"] in ("idle", "working") and l["kids"] == [] and 0 < len(l["acts"]) <= 5, l
    assert any("Bash: pytest -q" in a["text"] for a in l["acts"]), l
    assert call("POST", f"/api/goals/{b['id']}/start")[0] == 400 and call("POST", f"/api/goals/{b['id']}/answers", {})[0] == 400  # blocked: message instead
    assert call("POST", f"/api/goals/{b['id']}/message", {"text": "key is abc"})[1]["status"] == "running"
    b = wait(b["id"], "verifying", "running", "done")
    assert "[User] key is abc" in [e["text"] for e in call("GET", f"/api/runs/{b['run']}")[1]["events"] if e["type"] == "input"]
    b = wait(b["id"], "done")
    n0, c0, s0 = len(b["history"]), b["cost"], b["secs"]
    assert call("POST", f"/api/goals/{b['id']}/continue", {})[1]["status"] == "running" and call("POST", f"/api/goals/{b['id']}/continue", {})[0] == 400
    b = wait(b["id"], "done")
    assert len(b["history"]) == n0 + 1 and b["history"][0]["n"] == 1, b["history"]  # history kept, the new round appended
    assert b["cost"] > c0 and b["secs"] >= s0, (b["cost"], c0)  # the old brain still counts; time carries over

    # intake defaults: blank and "I don't know" fall back to the question's default, a real answer wins
    df = new("dflt")
    call("POST", f"/api/goals/{df['id']}/answers", {"answers": {"api": "I don't know"}})
    df = call("POST", f"/api/goals/{df['id']}/start")[1]
    first = [e["text"] for e in call("GET", f"/api/runs/{df['run']}")[1]["events"] if e["type"] == "input"][0]
    assert "Figma URL?: use placeholders" in first and "Backend API base URL?: (no answer: decide yourself" in first, first
    wait(df["id"], "done")

    # draft the objective
    s, x = call("POST", "/api/goals/draft", {"folder": str(PROJ), "idea": "a login page"})
    assert s == 200 and x["name"] == "Drafted a login page" and x["objective"] == "# Objetivo: a login page", x
    for bad in ({"folder": str(PROJ), "idea": " "}, {"folder": "/no/such", "idea": "x"}, {"idea": "x"}, {"folder": str(PROJ), "idea": "BADJSON"},
                {"folder": str(PROJ), "idea": "x" * 4001}):
        assert call("POST", "/api/goals/draft", bad)[0] == 400, bad

    # clone: a ready deep copy, no run/history/link; the branch name must be free
    s, c = call("POST", f"/api/goals/{b['id']}/clone")
    assert s == 200 and c["name"] == b["name"] + " (copia)" and c["status"] == "ready" and c["id"] != b["id"], c
    assert c["history"] == [] and c["run"] is None and c["after"] is None and c["objective"] == b["objective"] and c["questions"] == b["questions"], c
    assert c["acceptance"] == b["acceptance"] and c["max_iter"] == b["max_iter"] and "outcome" not in c and "base" not in c, c
    call("POST", f"/api/goals/{c['id']}/answers", {"answers": {"figma": "copy only"}})
    assert call("GET", f"/api/goals/{b['id']}")[1]["answers"].get("figma") != "copy only"
    assert call("POST", f"/api/goals/{b['id']}/clone", {"name": b["name"]})[0] == 400  # same branch as the source
    assert call("POST", f"/api/goals/{b['id']}/clone")[0] == 400  # same as the first clone
    assert call("POST", f"/api/goals/{c['id']}/start")[0] == 200
    wait(c["id"], "done")

    # linked goals: wait for the previous one, then branch from it; cancel if it fails; stop works while waiting
    pv = new("BLOCKMEprev")
    call("POST", f"/api/goals/{pv['id']}/answers", {"answers": {}})
    call("POST", f"/api/goals/{pv['id']}/start")
    pv = wait(pv["id"], "blocked")
    assert call("POST", "/api/goals", {"name": "z", "folder": str(PROJ), "objective": "y", "after": "nope"})[0] == 400
    def follower(tag, prev):
        x = new(tag, after=prev["id"])
        assert x["after"] == prev["id"] and x["from"] == "goal/" + prev["slug"], x
        call("POST", f"/api/goals/{x['id']}/answers", {"answers": {}})
        return x
    st = follower("stopme", pv)
    assert call("POST", f"/api/goals/{st['id']}/start")[1]["status"] == "waiting"
    assert call("POST", f"/api/goals/{st['id']}/start")[0] == 400 and call("POST", f"/api/goals/{st['id']}/answers", {})[0] == 400
    assert call("POST", f"/api/goals/{st['id']}/stop")[1]["status"] == "stopped"
    ch = follower("chain", pv)
    assert call("POST", f"/api/goals/{ch['id']}/start")[1]["status"] == "waiting"
    pf = new("ALWAYSFAILprev")
    call("POST", f"/api/goals/{pf['id']}/answers", {"answers": {}})
    call("POST", f"/api/goals/{pf['id']}/start")
    cx = follower("cancelme", pf)
    call("POST", f"/api/goals/{cx['id']}/start")
    call("POST", f"/api/goals/{pv['id']}/message", {"text": "key is abc"})
    ch = wait(ch["id"], "done", t=90)  # the worker tick starts it once the previous is done
    first = [e["text"] for e in call("GET", f"/api/runs/{ch['run']}")[1]["events"] if e["type"] == "input"][0]
    assert "Create the branch goal/sonora-chain from goal/sonora-blockmeprev" in first, first
    cx = wait(cx["id"], "failed", t=90)
    assert "Cancelled" in cx["report"] and cx["run"] is None and len(notices(cx["id"])) == 1, cx

    # review / merge / discard on a real repo
    R = HOME / "repo"
    R.mkdir()
    def sh(*a):
        subprocess.run(["git", "-C", str(R), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)
    sh("init", "-b", "main")
    (R / "a.txt").write_text("one\n")
    sh("add", "."), sh("commit", "-m", "base")
    def gitgoal(tag):
        x = new(tag, folder=str(R))
        call("POST", f"/api/goals/{x['id']}/answers", {"answers": {}})
        x = call("POST", f"/api/goals/{x['id']}/start")[1]
        assert x["base_branch"] == "main" and len(x["base"]) == 40, x
        x = wait(x["id"], "done")
        sh("checkout", "-b", "goal/sonora-" + tag.lower())  # what the brain would have done
        (R / (tag + ".txt")).write_text("two\nthree\n")
        sh("add", "."), sh("commit", "-m", "add " + tag)
        sh("checkout", "main")
        return x
    gm = gitgoal("gitm")
    v = call("GET", f"/api/goals/{gm['id']}/review")[1]
    assert v["exists"] and v["base_branch"] == "main" and [c["subject"] for c in v["commits"]] == ["add gitm"], v
    assert v["files"] == [{"path": "gitm.txt", "add": 2, "del": 0}] and "+three" in v["diff"] and not v["truncated"] and v["outcome"] is None, v
    assert call("GET", f"/api/goals/{g['id']}/review")[1]["exists"] is False  # a goal on a non-repo folder: empty, no error
    (R / "dirty.txt").write_text("x")
    s, x = call("POST", f"/api/goals/{gm['id']}/merge")
    assert s == 400 and "Uncommitted changes" in x["error"], x
    (R / "dirty.txt").unlink()
    sh("checkout", "-b", "other")
    s, x = call("POST", f"/api/goals/{gm['id']}/merge")
    assert s == 400 and "Check out main first" in x["error"], x
    sh("checkout", "main")
    s, x = call("POST", f"/api/goals/{gm['id']}/merge")
    assert s == 200 and x["outcome"] == "merged" and (R / "gitm.txt").exists(), x
    gd = gitgoal("gitd")
    sh("checkout", "goal/sonora-gitd")
    assert call("POST", f"/api/goals/{gd['id']}/discard")[0] == 400  # checked out
    sh("checkout", "main")
    assert call("POST", f"/api/goals/{gd['id']}/discard")[1]["outcome"] == "discarded"
    assert "goal/sonora-gitd" not in subprocess.run(["git", "-C", str(R), "branch"], capture_output=True, text=True).stdout and not (R / "gitd.txt").exists()
    assert call("GET", f"/api/goals/{gd['id']}/review")[1]["exists"] is False
    # re-run with the goal branch left checked out: it is not the base; discard reports a git failure instead of marking it
    gr = gitgoal("gitr")
    sh("checkout", "goal/sonora-gitr")
    x = call("POST", f"/api/goals/{gr['id']}/start")[1]
    assert x["base_branch"] == "main" and x["base"] == gr["base"], x
    wait(gr["id"], "done")
    sh("checkout", "main")
    sh("worktree", "add", str(HOME / "wt"), "goal/sonora-gitr")
    s, x = call("POST", f"/api/goals/{gr['id']}/discard")
    assert s == 400 and call("GET", f"/api/goals/{gr['id']}")[1]["outcome"] is None, (s, x)
    sh("worktree", "remove", "--force", str(HOME / "wt"))
    assert call("POST", f"/api/goals/{gr['id']}/discard")[1]["outcome"] == "discarded"
    # a goal allowed to use Trello may write to it, others may not (the fake brain asks the guard for three MCP tools)
    ga = new("GUARDallow", allow=["Trello"])
    assert ga["allow"] == ["Trello"]
    call("POST", f"/api/goals/{ga['id']}/answers", {"answers": {}, "acceptance": ["GUARD"]})
    call("POST", f"/api/goals/{ga['id']}/start")
    wait(ga["id"], "done")
    assert (TMP / "guard.log").read_text().splitlines()[-3:] == ["mcp__claude_ai_Trello__trelloWriteCard => allow",
                                                                   "mcp__claude_ai_Gmail__send_message => deny", "mcp__claude_ai_Trello__trelloReadCard => allow"]
    assert "You may use these outside services: Trello" in [e["text"] for e in call("GET", f"/api/runs/{call('GET', '/api/goals/' + ga['id'])[1]['run']}")[1]["events"] if e["type"] == "input"][0]

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
                           capture_output=True, text=True, env={**os.environ, "HADIYA_PORT": "1", "HADIYA_BRAIN_TOKEN": "x", **env})
        return {t["name"] for t in json.loads(p.stdout)["result"]["tools"]}
    assert "goal_report" in tools(HADIYA_GOAL="1") and not {"goal_create", "set_job"} & tools(HADIYA_GOAL="1")
    assert {"goal_create", "goal_list", "set_job"} <= tools(HADIYA_ASSISTANT="1") and "goal_report" not in tools(HADIYA_ASSISTANT="1")
    assert {x["id"] for x in call("GET", "/api/goals")[1]} >= {g["id"], b["id"], w["id"]}
    print("goals OK")
finally:
    srv.terminate()
    srv.wait()
    if sys.exc_info()[0]:
        print("server log:", (TMP / "server.log").read_text()[-3000:])
    shutil.rmtree(TMP, ignore_errors=True)
