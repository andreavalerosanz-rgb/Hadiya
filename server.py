#!/usr/bin/env python3
"""Local orchestrator for Claude Code: multi-step workflows + live lead/subagent sessions.

Each step runs `claude -p` using your logged-in CLI (subscription auth).
Run: python3 server.py  ->  http://localhost:8787
"""
import base64, gzip, hashlib, hmac, json, os, re, secrets, shutil, socket, subprocess, threading, time, uuid
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).parent
RUNS = ROOT / "data" / "runs"
SHOTS = ROOT / "data" / "shots"
UPLOADS = ROOT / "data" / "uploads"  # files attached to session messages, data/uploads/<run>/<name>
RUNS.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(exist_ok=True)
MAX_UPLOAD = 20 << 20
MAX_IMAGE = 3_750_000  # the API refuses images over 5 MB of base64; bigger ones go by path
WF_FILE = ROOT / "data" / "workflows.json"
PORT = int(os.environ.get("PORT", 8787))
# Drop API keys so the CLI uses the subscription login, and any parent Claude
# session's vars so child runs don't piggyback on (or break) the host's auth.
ENV = {k: v for k, v in os.environ.items()
       if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDECODE")
       and not k.startswith("CLAUDE_CODE_")}

lock = threading.Lock()
restarting = set()  # processes we ended on purpose to pick up new permissions
wlock = threading.Lock()  # one writer at a time on a session's stdin
runs, procs = {}, {}

for f in RUNS.glob("*.json"):
    r = json.loads(f.read_text())
    if r["status"] == "running":
        r["status"] = "interrupted"
    if r["status"] in ("working", "idle", "asking"):
        r["status"] = "stopped"  # resumable: next message respawns with --resume
        r["pending"] = {}  # questions die with their process
    runs[r["id"]] = r

USAGE_FILE = ROOT / "data" / "usage.json"
usage = json.loads(USAGE_FILE.read_text()) if USAGE_FILE.exists() else {}


def note_usage(ev):
    """Keep the latest subscription limits (5-hour / weekly utilization) that the CLI reports."""
    info = ev.get("rate_limit_info") or {}
    if info:
        usage.update({"windows": info.get("unifiedWindows") or usage.get("windows"), "status": info.get("status"),
                      "type": info.get("rateLimitType"), "resetsAt": info.get("resetsAt"), "ts": ev.get("ts") or time.time()})
        USAGE_FILE.write_text(json.dumps(usage))


def limited_until():
    """Epoch when the subscription limit resets, or 0 if we may run now."""
    t = usage.get("resetsAt") or 0
    return t if usage.get("status") == "rejected" and t > time.time() else 0


def hit_limit(res):
    """Did this turn end because the usage limit ran out? Records the reset time so the queue waits for it."""
    text = str((res or {}).get("result") or "")
    if not (res and res.get("is_error")):
        return False
    if limited_until():
        return True
    if not re.search(r"usage limit|hit your limit|limit reached|rate.?limit", text, re.I):
        return False
    # no reset time from the CLI: parse "limit reached|<epoch>", else retry in 15 min
    m = re.search(r"\|(\d{10})", text)
    usage.update(status="rejected", resetsAt=int(m.group(1)) if m else time.time() + 900)
    USAGE_FILE.write_text(json.dumps(usage))
    return True


ORCH = """You are the lead orchestrator of a team of subagents.
- Split the work into independent sub-tasks and delegate them with the Agent tool.
- Run up to {n} subagents in parallel: launch them in a single message.
- Give each subagent a self-contained prompt: exact file paths, what to do, how to verify, what to report back.
- Never let two subagents edit the same file at the same time. Do tiny or strictly sequential work yourself.
- When subagents finish, integrate and verify their work (build, lint) before reporting.
- The user may message you at any time to change the parallelism limit or redirect you. Always follow the latest instruction; if asked to go faster, split remaining work further and launch more subagents right away.
{models}"""

SUB_MODELS = {
    "auto": """- Pick each subagent's model with the Agent tool's `model` parameter, for the best quality per cost:
  - "haiku": mechanical, well-specified work: finding/reading files, renames, small edits that follow an exact spec, running build/lint, screenshots and simple checks.
  - "sonnet": normal implementation: a template part or Sass partial from a clear spec, bug fixes with a known cause, code review.
  - "opus": hard work: translating an ambiguous design, tricky debugging, architecture, refactors across many files.
  - "fable": only the hardest, highest-stakes reasoning where the others have failed.
  Use the cheapest model that will do the task well. If a subagent's result is poor, retry once with the next model up. When you launch subagents, say in one short line which model each got and why.""",
    "inherit": "- Launch subagents without a `model` parameter so they use your own model.",
}


def sub_models_rule(policy):
    policy = policy or "auto"
    return SUB_MODELS.get(policy) or f'- Launch every subagent with the Agent tool\'s `model` parameter set to "{policy}".'


def save_run(r):
    if r.get("deleted"):  # a finishing process must not bring a deleted run back
        return
    (RUNS / f"{r['id']}.json").write_text(json.dumps(r))


def load_wfs():
    return json.loads(WF_FILE.read_text()) if WF_FILE.exists() else {}


def save_wfs(w):
    WF_FILE.write_text(json.dumps(w, indent=2))


def render(template, inp, prev, site=""):
    return template.replace("{{input}}", inp).replace("{{prev}}", prev).replace("{{site}}", site)


def browser(cmd, tools, run_id):
    """Attach Playwright (headless Chrome) when the step may use the browser.
    Returns a system-prompt note pinning screenshots to data/shots/<run> (relative names resolve to the project)."""
    if "mcp__playwright" not in tools:
        return ""
    out = SHOTS / run_id
    out.mkdir(parents=True, exist_ok=True)
    cmd += ["--mcp-config", json.dumps({"mcpServers": {"playwright": {"command": "npx", "args": [
        "-y", "@playwright/mcp@0.0.82", "--headless", "--isolated", "--ignore-https-errors", "--output-dir", str(out)]}}})]
    return (f"When you take browser screenshots, always pass an absolute filename inside {out}/ "
            f"(e.g. {out}/home-1440.png). Never save screenshots into the project.")


def keep_shots_out(ev, cwd, run_id, seen):
    """Models sometimes save screenshots with a bare filename, which Playwright writes into the project.
    Move those into data/shots/<run> once the tool has finished, so projects stay clean."""
    for x in (ev.get("message") or {}).get("content") or []:
        if not isinstance(x, dict):
            continue
        if x.get("type") == "tool_use" and str(x.get("name", "")).endswith("browser_take_screenshot"):
            name = (x.get("input") or {}).get("filename") or ""
            if name and not os.path.isabs(name):
                seen[x["id"]] = name
        elif x.get("type") == "tool_result" and x.get("tool_use_id") in seen:
            src = Path(cwd) / seen.pop(x["tool_use_id"])
            dst = SHOTS / run_id / src.name
            if src.suffix.lower() in (".png", ".jpg", ".jpeg") and src.is_file() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.replace(dst)


def image_type(raw):
    """Media type from the file's magic bytes (a wrong media_type makes the API reject the whole message)."""
    for magic, t in ((b"\x89PNG", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF8", "image/gif")):
        if raw.startswith(magic):
            return t
    return "image/webp" if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else None


def save_files(rid, files):
    """Check every upload, then write them to data/uploads/<run>/ (basename only, deduped).
    files: [{name, data: base64}] -> [{name, path, media, b64?}]"""
    files = files or []
    for f in files:
        if len(f.get("data") or "") * 3 // 4 > MAX_UPLOAD:
            raise ValueError(f"{Path(str(f.get('name'))).name} is over {MAX_UPLOAD >> 20} MB")
    out, d = [], UPLOADS / rid
    for f in files:
        raw = base64.b64decode(f.get("data") or "")
        name = re.sub(r"[^\w.\- ]", "_", Path(str(f.get("name") or "")).name).strip(". ")[-120:] or "file"
        d.mkdir(parents=True, exist_ok=True)
        dst, n = d / name, 1
        while dst.exists():
            n += 1
            dst = d / f"{Path(name).stem}-{n}{Path(name).suffix}"
        dst.write_bytes(raw)
        media = image_type(raw)
        out.append({"name": dst.name, "path": str(dst), "media": media,
                    "b64": base64.b64encode(raw).decode() if media and len(raw) <= MAX_IMAGE else None})
    return out


def delete_run(rid):
    """Stop the run or session if it is live, then drop it with its log, screenshots and uploads."""
    r = runs.pop(rid)
    r["deleted"] = True
    if r["status"] == "running":
        r["status"] = "cancelled"
    elif r["status"] in ("working", "idle", "asking"):
        r["status"] = "stopped"
    p = procs.pop(rid, None)
    if p:
        p.terminate()
    (RUNS / f"{rid}.json").unlink(missing_ok=True)
    for d in (SHOTS, UPLOADS):
        shutil.rmtree(d / rid, ignore_errors=True)


def execute(r):
    """Runs the workflow's steps, starting after those already done (a run resumed after the usage limit)."""
    done = len(r["steps"])
    prev = r["steps"][-1]["result"] if done else ""
    try:
        for i, step in enumerate(r["workflow"]["steps"][done:], done):
            cmd = ["claude", "-p", "--output-format", "stream-json", "--verbose",
                   "--permission-mode", step.get("permission_mode") or "default"]
            if step.get("model"):
                cmd += ["--model", step["model"]]
            tools = step.get("allowed_tools") or ""
            notes = []
            if step.get("agents"):  # team step: lead agent fans out to parallel subagents
                notes.append(ORCH.format(n=step["agents"], models=sub_models_rule(step.get("sub_models"))))
                tools = ",".join(filter(None, ["Agent,Task", tools]))
            if tools:
                cmd += ["--allowedTools", tools]
            notes.append(browser(cmd, tools, r["id"]))
            if any(notes):
                cmd += ["--append-system-prompt", "\n\n".join(filter(None, notes))]
            s = {"name": step.get("name") or f"Step {i + 1}", "status": "running",
                 "started": time.time(), "events": []}
            with lock:
                if r["status"] != "running":
                    return
                r["steps"].append(s)
            cwd = os.path.expanduser(step.get("cwd") or r["workflow"].get("cwd") or "~")
            p = subprocess.Popen(cmd, cwd=cwd, env=ENV, text=True, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            procs[r["id"]] = p
            # stdin avoids the ~128KB argv limit when {{prev}} is large
            p.stdin.write(render(step["prompt"], r["input"], prev, r["workflow"].get("site") or ""))
            p.stdin.close()
            res, seen = None, {}
            for line in p.stdout:
                try:
                    ev = json.loads(line)
                except ValueError:
                    ev = {"type": "raw", "text": line.rstrip()}
                ev["ts"] = time.time()
                keep_shots_out(ev, cwd, r["id"], seen)
                if ev.get("type") == "rate_limit_event":
                    note_usage(ev)
                if ev.get("type") == "result":
                    res = ev
                with lock:
                    s["events"].append(ev)
            p.wait()
            with lock:
                s["ended"] = time.time()
                # A step can abort the run by answering "FAIL: <reason>".
                if res and not res.get("is_error") and not (res.get("result") or "").startswith("FAIL:"):
                    s.update(status="done", result=res.get("result", ""),
                             cost=res.get("total_cost_usd") or 0)
                    r["cost"] += s["cost"]
                    prev = s["result"]
                elif r["status"] == "running" and hit_limit(res):
                    r["steps"].pop()  # redone from scratch when the limit resets
                    r["status"] = "waiting"
                    return
                else:
                    s["status"] = "cancelled" if r["status"] == "cancelled" else "failed"
                    if r["status"] == "running":
                        r["status"] = "failed"
                    return
        with lock:
            r["status"] = "done"
    except Exception as e:
        with lock:
            r["status"], r["error"] = "failed", str(e)
    finally:
        procs.pop(r["id"], None)
        with lock:
            r["ended"] = time.time()
            save_run(r)


def start_run(wf_id, inp):
    wf = load_wfs()[wf_id]
    r = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4], "workflow_id": wf_id,
         "name": wf["name"], "input": inp, "status": "running", "started": time.time(),
         "ended": None, "cost": 0, "steps": [], "workflow": wf}
    with lock:
        runs[r["id"]] = r
    threading.Thread(target=execute, args=(r,), daemon=True).start()
    return r["id"]


# ---------- orchestrator sessions: one long-lived `claude` process fed via stdin ----------

def spawn(r):
    c = r["config"]
    # stdio prompt tool: questions (AskUserQuestion) and permission checks come back to us as control_requests
    cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--permission-prompt-tool", "stdio", "--permission-mode", c.get("permission_mode") or "default",
           "--allowedTools", ",".join(filter(None, ["Agent,Task", c.get("allowed_tools")])),
           "--add-dir", str(UPLOADS)]  # so attached files are readable from any project folder
    if c.get("model"):
        cmd += ["--model", c["model"]]
    note = browser(cmd, c.get("allowed_tools") or "", r["id"])
    cmd += ["--append-system-prompt", "\n\n".join(filter(None, [ORCH.format(n=c.get("agents") or 3, models=sub_models_rule(c.get("sub_models"))), note]))]
    if r.get("session_id"):
        cmd += ["--resume", r["session_id"]]
        r["cost_base"] = r["cost"]  # new process reports cost from zero
    p = subprocess.Popen(cmd, cwd=os.path.expanduser(c.get("cwd") or "~"), text=True,
                         env={**ENV, "CLAUDE_CODE_ENABLE_ASK_USER_QUESTION_TOOL": "true"},
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    procs[r["id"]] = p
    threading.Thread(target=pump, args=(r, p), daemon=True).start()
    return p


def pump(r, p):
    seen, cwd = {}, os.path.expanduser(r["config"].get("cwd") or "~")
    for line in p.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            ev = {"type": "raw", "text": line.rstrip()}
        ev["ts"] = time.time()
        keep_shots_out(ev, cwd, r["id"], seen)
        t, sub = ev.get("type"), ev.get("subtype")
        if t == "rate_limit_event":
            note_usage(ev)
        if t == "control_request":
            req = ev.get("request") or {}
            if req.get("subtype") != "can_use_tool":
                write(p, {"type": "control_response", "response": {
                    "subtype": "error", "request_id": ev.get("request_id"), "error": "unsupported by Flows"}})
                continue
            with lock:
                r.setdefault("pending", {})[ev["request_id"]] = {
                    "id": ev["request_id"], "tool": req.get("tool_name"), "input": req.get("input") or {},
                    "suggestions": req.get("permission_suggestions"), "ts": ev["ts"]}
                r["events"].append({"type": "ask", "id": ev["request_id"], "tool": req.get("tool_name"),
                                    "input": req.get("input") or {}, "ts": ev["ts"]})
                if r["status"] in ("working", "idle"):
                    r["status"] = "asking"
                save_run(r)
            q = r["pending"][ev["request_id"]]
            notify(r, "; ".join(x.get("question", "") for x in q["input"].get("questions") or []) if q["tool"] == "AskUserQuestion"
                   else f"Allow {q['tool']}?")
            continue
        with lock:
            r["events"].append(ev)
            if t == "system" and sub == "background_tasks_changed":
                r["bg"] = len(ev.get("tasks") or [])
            if t == "system" and sub == "init":
                r["session_id"] = ev.get("session_id")
            if t == "result":
                if hit_limit(ev):
                    r["waiting"] = True  # the queue worker sends "continue" once the limit resets
                r["turn_done"] = True
                r["cost"] = r.get("cost_base", 0) + (ev.get("total_cost_usd") or 0)
            elif t in ("assistant", "user"):
                r["turn_done"] = False
            if r["status"] in ("working", "idle", "asking"):
                r["status"] = ("asking" if r.get("pending") else
                               "idle" if r.get("turn_done") and not r.get("bg") else "working")
            if r["status"] == "idle" and r.pop("reload", False):
                restart(r, p)
            if t == "result":
                save_run(r)
    p.wait()
    with lock:
        if procs.get(r["id"]) is p:
            procs.pop(r["id"])
        if p in restarting:  # permission change: stay idle, next message resumes with the new flags
            restarting.discard(p)
        elif r["status"] != "stopped":
            r["status"] = "stopped" if p.returncode == 0 else "failed"
        r["pending"] = {}
        r["ended"] = time.time()
        save_run(r)


def send(r, text, agents=None, sub_models=None, files=()):
    """files: saved uploads from save_files. Images go as image blocks, and every file's path is listed."""
    with lock:
        if agents:
            r["config"]["agents"] = agents
        if sub_models:  # saved for respawns; the message itself tells the running lead
            r["config"]["sub_models"] = sub_models
        p = procs.get(r["id"]) or spawn(r)
        ev = {"type": "input", "text": text, "ts": time.time()}
        if files:
            ev["files"] = [{"name": f["name"], "image": bool(f["media"])} for f in files]
        r["events"].append(ev)
        r.pop("waiting", None)
        r["status"], r["turn_done"], r["ended"] = ("asking" if r.get("pending") else "working"), False, None
    content = text
    if files:
        content = [{"type": "text", "text": "\n\n".join(filter(None, [text, "Attached files: " + ", ".join(f["path"] for f in files)]))}] + [
            {"type": "image", "source": {"type": "base64", "media_type": f["media"], "data": f["b64"]}} for f in files if f["b64"]]
    write(p, {"type": "user", "message": {"role": "user", "content": content}})


def write(p, obj):
    with wlock:
        p.stdin.write(json.dumps(obj) + "\n")
        p.stdin.flush()


def answer(r, body):
    """Reply to a pending question or permission check. body: {id, allow, answers?, always?, message?}"""
    with lock:
        q = r.get("pending", {}).pop(body["id"])
        p = procs[r["id"]]
        if q["tool"] == "AskUserQuestion" and body.get("allow"):
            resp = {"behavior": "allow", "updatedInput": {**q["input"], "answers": body.get("answers") or {}}}
        elif body.get("allow"):
            resp = {"behavior": "allow", "updatedInput": q["input"]}
            if body.get("all"):  # every use of this tool (or MCP server), e.g. all shell commands
                tool = q["tool"].rsplit("__", 1)[0] if q["tool"].startswith("mcp__") else q["tool"]
                resp["updatedPermissions"] = [{"type": "addRules", "rules": [{"toolName": tool}],
                                               "behavior": "allow", "destination": "session"}]
                c = r["config"]
                c["allowed_tools"] = ",".join(filter(None, [c.get("allowed_tools"), tool]))
                if tool == "Bash":
                    c["caps"] = sorted(set((c.get("caps") or []) + ["shell"]))
            elif body.get("always") and q.get("suggestions"):
                # scope to this session only: never write rules into the project's settings files
                resp["updatedPermissions"] = [{**u, "destination": "session"} for u in q["suggestions"]]
        else:
            resp = {"behavior": "deny", "message": body.get("message") or "The user declined."}
        r["events"].append({"type": "answer", "id": body["id"], "tool": q["tool"], "allow": bool(body.get("allow")),
                            "answers": body.get("answers"), "always": bool(body.get("always")), "all": bool(body.get("all")),
                            "message": body.get("message"), "ts": time.time()})
        if r["status"] == "asking" and not r["pending"]:
            r["status"] = "working"
    write(p, {"type": "control_response", "response": {"subtype": "success", "request_id": body["id"], "response": resp}})


def set_model(r, model):
    """Switch the lead agent's model. A live process switches on its next turn; otherwise it's used at respawn."""
    with lock:
        r["config"]["model"] = model
        r["events"].append({"type": "model", "model": model, "ts": time.time()})
        save_run(r)
        p = procs.get(r["id"])
    if p:
        write(p, {"type": "control_request", "request_id": uuid.uuid4().hex,
                  "request": {"subtype": "set_model", "model": model or "default"}})


def restart(r, p):
    """End the lead process so the next message respawns it (--resume) with the current config."""
    restarting.add(p)
    p.terminate()


def configure(r, body):
    """Change a session's permissions. Applied now if the lead is idle or stopped, else when its turn ends."""
    with lock:
        r["config"].update({k: body[k] for k in ("allowed_tools", "permission_mode", "caps") if k in body})
        r["events"].append({"type": "perms", "caps": body.get("caps"), "ts": time.time()})
        save_run(r)
        p = procs.get(r["id"])
        if not p:
            return "next-message"
        if r["status"] == "idle":
            restart(r, p)
            return "now"
        r["reload"] = True
        return "after-turn"


def start_session(body):
    text = body.get("message", "").strip()
    r = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4], "kind": "session",
         "name": text.splitlines()[0][:60] if text else "Session", "status": "working",
         "started": time.time(), "ended": None, "cost": 0, "events": [], "session_id": None,
         "config": {k: body.get(k) for k in ("cwd", "model", "permission_mode", "allowed_tools", "agents", "caps", "sub_models")}}
    files = save_files(r["id"], body.get("files"))
    with lock:
        runs[r["id"]] = r
    send(r, text, files=files)
    return r["id"]


# ---------- notifications: native on this desktop, Web Push to subscribed phones ----------
PUSH_FILE = ROOT / "data" / "push.json"
push = json.loads(PUSH_FILE.read_text()) if PUSH_FILE.exists() else {}
push.setdefault("subs", {})  # endpoint -> {sub, name}
try:  # the only non-stdlib piece; without it phones just don't get push
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if "vapid" not in push:
        push["vapid"] = ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
        PUSH_FILE.write_text(json.dumps(push))
    VAPID = serialization.load_pem_private_key(push["vapid"].encode(), None)
except ImportError:
    VAPID = None
SW_JS = """self.addEventListener('push', e => { const d = e.data ? e.data.json() : {};
  e.waitUntil(self.registration.showNotification(d.title || 'Flows', {body: d.body, tag: d.tag, renotify: true, data: {url: d.url || '/'}})); });
// the app shell never caches: when the computer is unreachable, say so instead of a browser error page
const OFFLINE = `<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0d0d0d">
<body style="margin:0;min-height:100vh;display:grid;place-items:center;background:#0d0d0d;color:#ecebe7;font:16px/1.5 system-ui;text-align:center;padding:24px;box-sizing:border-box">
<main><h1 style="font-size:22px;letter-spacing:.04em;text-transform:uppercase;margin:0 0 8px">Can't reach Flows</h1>
<p style="color:#a6a39c;margin:0 0 20px">Your computer is asleep, offline, or Flows isn't running. Check Tailscale is on for both devices.</p>
<button onclick="location.reload()" style="border:0;border-radius:3px;background:#ff5a1f;color:#0d0d0d;padding:14px 22px;font:700 16px system-ui;text-transform:uppercase;letter-spacing:.08em">Try again</button></main>`;
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(clients.claim()));
self.addEventListener('fetch', e => { if (e.request.mode == 'navigate')
  e.respondWith(fetch(e.request).catch(() => new Response(OFFLINE, {headers: {'Content-Type': 'text/html; charset=utf-8'}}))); });
self.addEventListener('notificationclick', e => { e.notification.close();
  e.waitUntil(clients.matchAll({type: 'window'}).then(ws => { const w = ws[0];
    return w ? w.focus().then(() => w.navigate(e.notification.data.url)) : clients.openWindow(e.notification.data.url); })); });"""
MANIFEST = {"id": "/", "name": "Flows", "short_name": "Flows", "description": "Claude Code workbench",
            "start_url": "/", "scope": "/", "display": "standalone", "background_color": "#0d0d0d", "theme_color": "#0d0d0d",
            "icons": [{"src": f"/icons/icon-{n}.png", "sizes": f"{n}x{n}", "type": "image/png", "purpose": "any maskable"} for n in (192, 512)]}


def b64u(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def unb64u(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def raw_pub(key):
    return key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def hkdf(salt, ikm, info, n):
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:n]  # n <= 32: one block is enough


def encrypt(sub, payload):
    """RFC 8291 aes128gcm body for one subscription."""
    ua_pub, auth = unb64u(sub["keys"]["p256dh"]), unb64u(sub["keys"]["auth"])
    eph = ec.generate_private_key(ec.SECP256R1())
    shared = eph.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub))
    as_pub, salt = raw_pub(eph), os.urandom(16)
    ikm = hkdf(auth, shared, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    cek = hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    return salt + (4096).to_bytes(4, "big") + bytes([65]) + as_pub + AESGCM(cek).encrypt(nonce, payload + b"\x02", None)


def vapid_auth(endpoint):
    u = urlsplit(endpoint)
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    claims = b64u(json.dumps({"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + 43200,
                              "sub": "mailto:flows@localhost"}).encode())
    r, s = decode_dss_signature(VAPID.sign(f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256())))
    return f"vapid t={head}.{claims}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}, k={b64u(raw_pub(VAPID))}"


def push_one(sub, payload):
    req = Request(sub["endpoint"], data=encrypt(sub, payload), method="POST", headers={
        "Authorization": vapid_auth(sub["endpoint"]), "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream", "TTL": "86400", "Urgency": "high"})
    try:
        urlopen(req, timeout=15).close()
    except Exception as e:
        if getattr(e, "code", None) in (404, 410):  # the phone unsubscribed or the browser dropped it
            push["subs"].pop(sub["endpoint"], None)
            PUSH_FILE.write_text(json.dumps(push))
        else:
            print("push:", e)


def notify(r, body):
    """A session is waiting on the user: tell this desktop and every subscribed phone."""
    title = f"Flows needs you: {r['name']}"
    try:
        subprocess.Popen(["notify-send", "-a", "Flows", "-i", "dialog-question", title, body[:300]],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass
    if VAPID:
        payload = json.dumps({"title": title, "body": body[:300], "tag": r["id"], "url": f"/#session/{r['id']}"}).encode()
        for s in list(push["subs"].values()):
            threading.Thread(target=push_one, args=(s["sub"], payload), daemon=True).start()


# ---------- queue: tasks that start one at a time, and pause while the usage limit is out ----------
QUEUE_FILE = ROOT / "data" / "queue.json"
queue = json.loads(QUEUE_FILE.read_text()) if QUEUE_FILE.exists() else []
RESUME = "Continue where you left off. (Resumed automatically after the usage limit reset.)"


def save_queue():
    QUEUE_FILE.write_text(json.dumps(queue))


def enqueue(body):
    """body: {kind: "workflow", wf_id, input}, {kind: "session", ...start_session body}
    or {kind: "message", run_id, text, files?}: sent to that session once it is free."""
    item = {**body, "id": uuid.uuid4().hex[:8], "added": time.time()}
    k = body.get("kind")
    item["name"] = (load_wfs()[body["wf_id"]]["name"] if k == "workflow" else
                    (body.get("text") or "Message").strip().splitlines()[0][:60] if k == "message" and runs[body["run_id"]] else
                    (body.get("message") or "Session").strip().splitlines()[0][:60])
    with lock:
        queue.append(item)
        save_queue()
    return item["id"]


def busy(r):
    return r["status"] in ("running", "waiting", "working", "asking") or r.get("waiting")


def tick():
    if limited_until():
        return
    with lock:
        waiting = [r for r in runs.values() if r["status"] == "waiting" or
                   (r.get("waiting") and r["status"] in ("idle", "stopped", "failed"))]
        for r in waiting:
            if r.get("kind") == "session":
                r["status"] = "stopped" if r["status"] == "failed" else r["status"]
            else:
                r["status"], r["ended"] = "running", None
                threading.Thread(target=execute, args=(r,), daemon=True).start()
    for r in waiting:
        if r.get("kind") == "session":
            send(r, RESUME)
    with lock:  # queued messages: the oldest one per session, once that session is free
        due, sent = [], set()
        for q in [q for q in queue if q.get("kind") == "message"]:
            r = runs.get(q["run_id"])
            if not r:
                queue.remove(q)
            elif q["run_id"] not in sent and not busy(r):
                sent.add(q["run_id"])
                queue.remove(q)
                due.append((r, q))
        save_queue()
    for r, q in due:
        send(r, q.get("text", ""), files=save_files(r["id"], q.get("files")))
    with lock:
        tasks = [q for q in queue if q.get("kind") != "message"]
        if not tasks or any(r.get("queued") and busy(r) for r in runs.values()):
            return
        item = tasks[0]
        queue.remove(item)
        save_queue()
    rid = start_run(item["wf_id"], item.get("input", "")) if item.get("kind") == "workflow" else start_session(item)
    runs[rid]["queued"] = True


def worker():
    while True:
        try:
            tick()
        except Exception as e:
            print("queue:", e)
        time.sleep(20)


# ---------- phone access ----------
# Trust comes from the socket, never from headers: the 127.0.0.1:PORT listener is the laptop.
# Phone traffic arrives on separate listeners (Wi-Fi IP, and a tunnel-only port) whose handler
# requires a paired-device cookie on every request. Only the laptop can pair, revoke, or toggle.
REMOTE_FILE = ROOT / "data" / "remote.json"
remote = json.loads(REMOTE_FILE.read_text()) if REMOTE_FILE.exists() else {}
remote.setdefault("devices", {})  # sha256(token) -> {name, created, last}
TUNNEL_PORT = PORT + 2
TAILNET_PORT = PORT + 1  # phone-only listener that `tailscale serve` forwards to
listeners = {}  # "lan" / "tunnel" -> {srv, url, proc?}
pairing = {}    # the single active code: {code, exp, tries}
CODE_TTL, CODE_TRIES, DEVICE_DAYS = 300, 5, 90


def save_remote():
    REMOTE_FILE.write_text(json.dumps(remote, indent=1))
    os.chmod(REMOTE_FILE, 0o600)


def lan_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
        sk.connect(("10.255.255.255", 1))  # no packet is sent; just picks the outbound interface
        return sk.getsockname()[0]


def serve(addr, handler):
    srv = ThreadingHTTPServer(addr, handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def stop(name):
    x = listeners.pop(name, None)
    if x:
        if x.get("proc"):
            x["proc"].terminate()
        x["srv"].shutdown()
        x["srv"].server_close()


def set_lan(on):
    if on and "lan" not in listeners:
        ip = lan_ip()
        listeners["lan"] = {"srv": serve((ip, PORT), RH), "url": f"http://{ip}:{PORT}"}
    elif not on:
        stop("lan")
    remote["lan"] = bool(on)
    save_remote()


def die_with_parent():
    """Linux: the kernel sends the tunnel SIGTERM if Flows exits for any reason (even kill -9),
    so a public address never outlives the server."""
    import ctypes, signal
    ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, signal.SIGTERM)  # PR_SET_PDEATHSIG


def set_tunnel(on):
    if on and "tunnel" not in listeners:
        exe = shutil.which("cloudflared") or os.path.expanduser("~/.local/bin/cloudflared")
        srv = serve(("127.0.0.1", TUNNEL_PORT), RH)
        proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{TUNNEL_PORT}"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, preexec_fn=die_with_parent)
        t = listeners["tunnel"] = {"srv": srv, "proc": proc, "url": None}

        def read():
            for line in proc.stdout:
                m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if m and not t["url"]:
                    t["url"] = m.group(0)
        threading.Thread(target=read, daemon=True).start()
    elif not on:
        stop("tunnel")


def ts(*args, timeout=10):
    """Run the tailscale CLI; returns (ok, output)."""
    exe = shutil.which("tailscale")
    if not exe:
        return False, "not installed"
    try:
        r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except subprocess.TimeoutExpired as e:
        said = ((e.stdout or b"") + (e.stderr or b"")).decode(errors="replace").strip() if isinstance(e.stdout, bytes) else (e.stdout or "") + (e.stderr or "")
        return False, said.strip() or "tailscale did not answer in time"


def tailnet_status():
    st = {"installed": bool(shutil.which("tailscale")), "running": False, "on": "tailnet" in listeners,
          "url": None, "error": remote.get("tailnet_error")}
    ok, out = ts("status", "--json", timeout=4) if st["installed"] else (False, "")
    if ok:
        j = json.loads(out)
        st["running"] = j.get("BackendState") == "Running"
        name = (j.get("Self") or {}).get("DNSName", "").rstrip(".")
        st["https"] = bool(j.get("CertDomains"))
        if name and st["on"]:
            st["url"] = f"https://{name}" if remote.get("tailnet_mode") == "https" else f"http://{name}:{TAILNET_PORT}"
    return st


def set_tailnet(on):
    """Serve the phone listener on this machine's tailnet HTTPS name. `tailscale serve --bg` persists
    inside tailscaled, so after a reboot only our listener needs to come back (done at startup)."""
    remote.pop("tailnet_error", None)
    if on:
        if "tailnet" not in listeners:
            listeners["tailnet"] = {"srv": serve(("127.0.0.1", TAILNET_PORT), RH)}
        # HTTPS needs "HTTPS certificates" enabled for the tailnet; without it `serve --https` hangs, so
        # fall back to plain HTTP on the tailnet (still WireGuard-encrypted between your devices).
        ok, out = ts("status", "--json", timeout=4)
        https = ok and bool(json.loads(out).get("CertDomains"))
        mode = "https" if https else "http"
        ts("serve", "--https=443", "off")
        ts("serve", f"--http={TAILNET_PORT}", "off")
        ok, out = ts("serve", "--bg", "--https=443" if https else f"--http={TAILNET_PORT}",  # not :80, often a local Apache
                     f"http://127.0.0.1:{TAILNET_PORT}", timeout=20)
        remote["tailnet_mode"] = mode
        if not ok:
            stop("tailnet")
            remote["tailnet_error"] = out[-600:] or "tailscale serve failed"
            on = False
    else:
        ts("serve", "--https=443", "off")
        ts("serve", f"--http={TAILNET_PORT}", "off")
        stop("tailnet")
    remote["tailnet"] = bool(on)
    save_remote()


def remote_status():
    code = pairing if pairing.get("exp", 0) > time.time() else {}
    return {"tailnet": tailnet_status(),
            "lan": {"on": "lan" in listeners, "url": listeners.get("lan", {}).get("url")},
            "tunnel": {"on": "tunnel" in listeners, "url": listeners.get("tunnel", {}).get("url"),
                       "available": bool(shutil.which("cloudflared") or os.path.exists(os.path.expanduser("~/.local/bin/cloudflared")))},
            "code": {"code": code.get("code"), "exp": code.get("exp")} if code else None,
            "devices": [{"id": k[:10], **v} for k, v in remote["devices"].items()]}


def new_code():
    pairing.clear()
    pairing.update(code=f"{secrets.randbelow(10 ** 6):06d}", exp=time.time() + CODE_TTL, tries=0)
    return pairing["code"]


PAIR_HTML = b"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0d0d0d"><title>Pair with Flows</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0d0d0d;color:#ecebe7;font:16px/1.5 system-ui,sans-serif;padding:16px;box-sizing:border-box}
main{width:100%;max-width:380px;background:#f4f2ee;color:#0d0d0d;border-radius:3px;overflow:hidden}
.band{background:#ff5a1f;padding:14px 20px;font:700 22px/1.1 "Arial Narrow",system-ui;letter-spacing:.06em;text-transform:uppercase}
form{padding:18px 20px 22px}label{display:block;font-size:13px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#57534d;margin:12px 0 6px}
input{width:100%;box-sizing:border-box;border:1px solid #cfcac2;border-radius:3px;padding:11px 12px;font:inherit;background:#fff}
#code{font:700 30px/1 ui-monospace,monospace;letter-spacing:.35em;text-align:center}
button{margin-top:18px;width:100%;border:0;border-radius:3px;background:#ff5a1f;color:#0d0d0d;padding:13px;font:700 17px/1 system-ui;letter-spacing:.08em;text-transform:uppercase}
p{margin:0 0 4px;font-size:14px;color:#57534d}#err{color:#c2410c;min-height:1.4em;margin-top:10px}</style></head><body><main>
<div class="band">Pair with Flows</div><form id="f"><p>On your computer open Flows, go to <b>Phone access</b> and create a pairing code.</p>
<label for="code">Pairing code</label><input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" required>
<label for="name">Name this device</label><input id="name" value="My phone" maxlength="40">
<button>Pair this device</button><div id="err" role="alert"></div></form></main><script>
const f=document.getElementById('f'),c=document.getElementById('code'),m=/code=(\\d{6})/.exec(location.hash);
if(m){c.value=m[1];history.replaceState(null,'',location.pathname);}
f.onsubmit=async e=>{e.preventDefault();const r=await fetch('/api/pair',{method:'POST',headers:{'Content-Type':'application/json','X-Flow':'1'},body:JSON.stringify({code:c.value,name:document.getElementById('name').value})});
const j=await r.json().catch(()=>({}));if(r.ok)location.replace('/');else document.getElementById('err').textContent=j.error||'Could not pair';};
if(m)f.requestSubmit();</script></body></html>"""


def slim(ev):
    """Wire copy of an event: drop base64 image data, cap tool_result text (stored event untouched)."""
    ev = {k: v for k, v in ev.items() if k != "tool_use_result"}  # unused by client, duplicates the result (incl. base64)
    c = (ev.get("message") or {}).get("content")
    if not isinstance(c, list):
        return ev
    cut = lambda t: t[:6000] + "\n…" if isinstance(t, str) and len(t) > 6000 else t
    def item(it):
        if not (isinstance(it, dict) and it.get("type") == "tool_result"):
            return it
        x = it.get("content")
        if isinstance(x, str):
            return {**it, "content": cut(x)}
        if not isinstance(x, list):
            return it
        out = []
        for y in x:
            if isinstance(y, dict) and y.get("type") == "image" and isinstance(y.get("source"), dict):
                y = {**y, "source": {**y["source"], "data": ""}}
            elif isinstance(y, dict) and y.get("type") == "text":
                y = {**y, "text": cut(y.get("text"))}
            elif isinstance(y, str):
                y = cut(y)
            out.append(y)
        return {**it, "content": out}
    return {**ev, "message": {**ev["message"], "content": [item(i) for i in c]}}


class H(BaseHTTPRequestHandler):
    remote = False  # RH (phone listeners) flips this
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="application/json", headers=()):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        if len(body) > 1024 and "gzip" in self.headers.get("Accept-Encoding", "") and re.match(r"text/|application/(json|javascript|manifest)", ctype):
            body = gzip.compress(body, 5)
            headers = [*headers, ("Content-Encoding", "gzip"), ("Vary", "Accept-Encoding")]
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if not any(k.lower() == "cache-control" for k, _ in headers):
            self.send_header("Cache-Control", "no-store")
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def device(self):
        """The paired device behind this request, or None."""
        tok = SimpleCookie(self.headers.get("Cookie", "")).get("flows_device")
        if not tok:
            return None
        key = hashlib.sha256(tok.value.encode()).hexdigest()
        d = remote["devices"].get(key)
        if d and time.time() - d.get("last", 0) > 600:  # throttle writes
            d["last"] = time.time()
            save_remote()
        return d

    def pair(self, body):
        code = str(body.get("code", "")).strip()
        ok = pairing.get("exp", 0) > time.time() and hmac.compare_digest(code, pairing.get("code", ""))
        if not ok:
            if pairing:
                pairing["tries"] += 1
                if pairing["tries"] >= CODE_TRIES:
                    pairing.clear()  # too many guesses: the code is burned
            return self.send(403, {"error": "That code is wrong or expired. Create a new one on your computer."})
        pairing.clear()
        tok = secrets.token_urlsafe(32)
        remote["devices"][hashlib.sha256(tok.encode()).hexdigest()] = {
            "name": str(body.get("name") or "Phone")[:40], "created": time.time(), "last": time.time()}
        save_remote()
        https = [listeners.get("tunnel", {}).get("srv")] + ([listeners.get("tailnet", {}).get("srv")] if remote.get("tailnet_mode") == "https" else [])
        secure = "; Secure" if self.server in https else ""
        cookie = f"flows_device={tok}; HttpOnly; SameSite=Strict; Path=/; Max-Age={DEVICE_DAYS * 86400}{secure}"
        return self.send(200, {"ok": True}, headers=[("Set-Cookie", cookie)])

    def route(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        p = self.path.split("?")[0].strip("/").split("/")
        m = self.command
        if self.remote:
            # Phone listeners: nothing but the pairing page until this device is paired. The install
            # files hold no data and browsers fetch the manifest and icons without cookies, so they're open.
            public = m == "GET" and (p in (["manifest.json"], ["sw.js"]) or (len(p) == 2 and p[0] == "icons"))
            if not public and not self.device():
                if m == "GET" and p in ([""], ["pair"]):
                    return self.send(200, PAIR_HTML, "text/html; charset=utf-8")
                if m == "POST" and p == ["api", "pair"] and self.headers.get("X-Flow") == "1":
                    return self.pair(body)
                return self.send(401, {"error": "Pair this device first"})
            if p == ["api", "pair"]:  # a stale pairing page on a device that is already paired: just go in
                return self.send(200, {"ok": True})
            if p == ["pair"]:
                return self.send(302, b"", headers=[("Location", "/")])
            if p[:2] == ["api", "remote"]:
                return self.send(403, {"error": "Phone access is managed from your computer"})
        # Laptop listener: block DNS rebinding (Host). Everywhere: block cross-site
        # requests (the custom header forces a CORS preflight we never answer).
        elif self.headers.get("Host", "").split(":")[0] not in ("localhost", "127.0.0.1"):
            return self.send(403, {"error": "bad host"})
        if m != "GET" and self.headers.get("X-Flow") != "1":
            return self.send(403, {"error": "missing X-Flow header"})
        try:
            if p[:2] == ["api", "remote"]:
                if m == "GET" and len(p) == 2:
                    return self.send(200, remote_status())
                if m == "POST" and p[2:] == ["code"]:
                    return self.send(200, {"code": new_code(), "exp": pairing["exp"]})
                if m == "POST" and p[2:] == ["lan"]:
                    set_lan(body.get("on"))
                    return self.send(200, remote_status())
                if m == "POST" and p[2:] == ["tailnet"]:
                    set_tailnet(body.get("on"))
                    return self.send(200, remote_status())
                if m == "POST" and p[2:] == ["tunnel"]:
                    set_tunnel(body.get("on"))
                    return self.send(200, remote_status())
                if m == "POST" and p[2:] == ["revoke"]:
                    for k in [k for k in remote["devices"] if k[:10] == body.get("id")]:
                        del remote["devices"][k]
                    save_remote()
                    return self.send(200, remote_status())
            if m == "GET" and len(p) == 3 and p[0] == "shots":
                f = (SHOTS / Path(p[1]).name / Path(p[2]).name)  # basename only: no path traversal
                if f.suffix in (".png", ".jpeg", ".jpg") and f.is_file():
                    return self.send(200, f.read_bytes(), "image/png" if f.suffix == ".png" else "image/jpeg")
                return self.send(404, {"error": "no such screenshot"})
            if m == "GET" and len(p) == 3 and p[0] == "uploads":
                f = (UPLOADS / Path(unquote(p[1])).name / Path(unquote(p[2])).name).resolve()
                if f.parent.parent != UPLOADS.resolve() or not f.is_file():
                    return self.send(404, {"error": "no such file"})
                raw = f.read_bytes()
                # images inline; anything else downloads, so an uploaded .html can never run on this origin
                return self.send(200, raw, image_type(raw) or "application/octet-stream", [("X-Content-Type-Options", "nosniff")] + (
                    [] if image_type(raw) else [("Content-Disposition", "attachment")]))
            if m == "GET" and p == [""]:
                raw = (ROOT / "index.html").read_bytes()
                et = '"%s"' % hashlib.md5(raw).hexdigest()[:16]
                hd = [("ETag", et), ("Cache-Control", "no-cache")]
                if self.headers.get("If-None-Match") == et:
                    return self.send(304, b"", "text/html; charset=utf-8", hd)
                return self.send(200, raw, "text/html; charset=utf-8", hd)
            if p[:2] == ["api", "workflows"]:
                wfs = load_wfs()
                if m == "GET" and len(p) == 2:
                    return self.send(200, wfs)
                if m == "PUT" and len(p) == 3:
                    wfs[p[2]] = body
                    save_wfs(wfs)
                    return self.send(200, {"ok": True})
                if m == "DELETE" and len(p) == 3:
                    wfs.pop(p[2], None)
                    save_wfs(wfs)
                    return self.send(200, {"ok": True})
                if m == "POST" and len(p) == 4 and p[3] == "run":
                    return self.send(200, {"id": start_run(p[2], body.get("input", ""))})
            if m == "GET" and p == ["sw.js"]:
                return self.send(200, SW_JS.encode(), "text/javascript", [("Service-Worker-Allowed", "/")])
            if m == "GET" and len(p) == 2 and p[0] == "icons":
                f = ROOT / "icons" / Path(p[1]).name
                if f.suffix == ".png" and f.is_file():
                    return self.send(200, f.read_bytes(), "image/png")
                return self.send(404, {"error": "no such icon"})
            if m == "GET" and p == ["manifest.json"]:
                return self.send(200, MANIFEST, "application/manifest+json")
            if p == ["api", "push"]:
                if m == "GET":
                    return self.send(200, {"key": b64u(raw_pub(VAPID)) if VAPID else "", "enabled": bool(VAPID)})
                if m == "POST":
                    ep = body.get("endpoint") or (body.get("sub") or {}).get("endpoint") or ""
                    if not ep.startswith("https://"):
                        return self.send(400, {"error": "bad subscription"})
                    if body.get("off"):
                        push["subs"].pop(ep, None)
                    else:
                        push["subs"][ep] = {"sub": body["sub"], "name": str(body.get("name") or "Phone")[:40]}
                    PUSH_FILE.write_text(json.dumps(push))
                    return self.send(200, {"ok": True})
            if m == "GET" and p == ["api", "usage"]:
                return self.send(200, usage)
            if p[:2] == ["api", "queue"]:
                if m == "GET" and len(p) == 2:
                    return self.send(200, {"items": [{k: v for k, v in q.items() if k != "files"} for q in queue],
                                           "limited_until": limited_until()})
                if m == "POST" and len(p) == 2:
                    return self.send(200, {"id": enqueue(body)})
                if m == "DELETE" and len(p) == 3:
                    with lock:
                        queue[:] = [q for q in queue if q["id"] != p[2]]
                        save_queue()
                    return self.send(200, {"ok": True})
            if p[:2] == ["api", "runs"]:
                with lock:
                    if m == "GET" and len(p) == 2:
                        skip = ("steps", "workflow", "input", "events", "config")
                        return self.send(200, sorted(
                            ({k: v for k, v in r.items() if k not in skip} for r in runs.values()),
                            key=lambda r: r["started"], reverse=True))
                    if m == "GET" and len(p) == 3:
                        r = runs[p[2]]
                        if "events" in r:  # sessions grow large: client polls with ?since=<count>
                            since = int(self.path.partition("since=")[2] or 0)
                            return self.send(200, {**r, "events": [slim(e) for e in r["events"][since:]], "total": len(r["events"])})
                        return self.send(200, r)
                    if m == "POST" and len(p) == 4 and p[3] == "cancel":
                        if runs[p[2]]["status"] == "waiting":
                            runs[p[2]].update(status="cancelled", ended=time.time())
                            save_run(runs[p[2]])
                        if runs[p[2]]["status"] == "running":
                            runs[p[2]]["status"] = "cancelled"
                            if p[2] in procs:
                                procs[p[2]].terminate()
                        return self.send(200, {"ok": True})
                    if m == "DELETE" and len(p) == 3:
                        delete_run(p[2])
                        return self.send(200, {"ok": True})
            if p[:2] == ["api", "sessions"] and m == "POST":
                if len(p) == 2:
                    return self.send(200, {"id": start_session(body)})
                r = runs[p[2]]
                if p[3:] == ["message"]:
                    send(r, body.get("text", ""), body.get("agents"), body.get("sub_models"), save_files(r["id"], body.get("files")))
                    return self.send(200, {"ok": True})
                if p[3:] == ["model"]:
                    set_model(r, body.get("model") or "")
                    return self.send(200, {"ok": True})
                if p[3:] == ["config"]:
                    return self.send(200, {"applied": configure(r, body)})
                if p[3:] == ["answer"]:
                    answer(r, body)
                    return self.send(200, {"ok": True})
                if p[3:] == ["stop"]:
                    with lock:
                        r["status"] = "stopped"
                        r.pop("waiting", None)
                        if p[2] in procs:
                            procs[p[2]].terminate()
                    return self.send(200, {"ok": True})
            self.send(404, {"error": "not found"})
        except KeyError:
            self.send(404, {"error": "not found"})
        except ValueError as e:  # too-large or malformed upload
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": str(e)})

    do_GET = do_POST = do_PUT = do_DELETE = route


class RH(H):
    remote = True


if __name__ == "__main__":
    print(f"Flows on http://localhost:{PORT}")
    if remote.get("tailnet"):
        listeners["tailnet"] = {"srv": serve(("127.0.0.1", TAILNET_PORT), RH)}  # tailscaled keeps its serve config
        print(f"Tailscale phone listener on 127.0.0.1:{TAILNET_PORT}")

    def lan_when_ready():  # at boot the Wi-Fi may come up after us: keep trying
        while remote.get("lan") and "lan" not in listeners:
            try:
                set_lan(True)
                print(f"Phone access on {listeners['lan']['url']}")
            except OSError:
                time.sleep(10)
    threading.Thread(target=lan_when_ready, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
