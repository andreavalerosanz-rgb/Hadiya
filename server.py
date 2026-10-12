#!/usr/bin/env python3
"""Local orchestrator for Claude Code: multi-step workflows + live lead/subagent sessions.

Each step runs `claude -p` using your logged-in CLI (subscription auth).
Run: python3 server.py  ->  http://localhost:8787
"""
import base64, gzip, hashlib, hmac, json, os, pwd, re, secrets, shlex, shutil, socket, subprocess, sys, tempfile, threading, time, uuid
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.request import Request, urlopen

ID = {"type": "string", "description": "The session id"}
BRAIN_TOOLS = [
    {"name": "start_session", "description": "Start a Flows session (a lead agent with its own subagents) for one workstream. "
     "It gets your permissions and folder; the message is its whole brief, so make it self-contained.",
     "inputSchema": {"type": "object", "required": ["message"], "properties": {
         "message": {"type": "string", "description": "The brief: goal, exact paths, constraints, contracts with other workstreams, how to verify, what to report"},
         "name": {"type": "string", "description": "Short name shown to the user"},
         "cwd": {"type": "string", "description": "Project folder (default: yours)"},
         "model": {"type": "string", "description": "Lead model: sonnet (default) for normal work, opus only for hard design, debugging or architecture"}}}},
    {"name": "list_sessions", "description": "Your sessions: status, pending questions and their last message.",
     "inputSchema": {"type": "object", "properties": {}}},
    {"name": "read_session", "description": "A session's recent transcript: messages, tool calls, errors, questions and answers. "
     "Returns the `since` to pass next time to read only what is new.",
     "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": ID, "since": {"type": "integer", "description": "Event index to start from (default: the last 15 events)"}}}},
    {"name": "send_message", "description": "Send a message to a session: next instructions, information from other sessions, corrections.",
     "inputSchema": {"type": "object", "required": ["id", "text"], "properties": {"id": ID, "text": {"type": "string"}}}},
    {"name": "answer_question", "description": "Answer a session's pending question (AskUserQuestion). Permission checks stay with the user.",
     "inputSchema": {"type": "object", "required": ["id", "question_id"], "properties": {
         "id": ID, "question_id": {"type": "string"},
         "answers": {"type": "object", "additionalProperties": {"type": "string"}, "description": "Question text -> chosen option label or free answer"},
         "allow": {"type": "boolean", "description": "false declines the question (default true)"},
         "message": {"type": "string", "description": "Why, when declining"}}}},
    {"name": "stop_session", "description": "Stop a session's process. A later message resumes it.",
     "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": ID}}},
    {"name": "set_job", "description": "Add or replace a scheduled job or a one-off reminder. At its time you get its prompt as a "
     "[Job <id>] message; your reply reaches the user as a notice (reply exactly NOTHING to stay silent). Returns all jobs.",
     "inputSchema": {"type": "object", "required": ["at", "prompt"], "properties": {
         "id": {"type": "string", "description": "Id of the job to replace (default: a new job)"},
         "at": {"type": "string", "description": "Local time(s) HH:MM, comma-separated: 08:30 or 09:00,11:00"},
         "days": {"type": "array", "items": {"type": "integer"}, "description": "Weekdays, 0 = Monday … 6 = Sunday (default: every day)"},
         "date": {"type": "string", "description": "YYYY-MM-DD for a one-off reminder: runs once that day, then it is removed"},
         "prompt": {"type": "string", "description": "What to do or remind the user of"}}}},
    {"name": "remove_job", "description": "Remove a scheduled job or reminder. Returns the remaining jobs.",
     "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}},
    {"name": "list_jobs", "description": "Your scheduled jobs and reminders.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "send_file", "description": "Send the user a small text file (.txt, .csv or .md) as an attachment in their chat. For other "
     "types (PDF, images, Office) have a session write the file into your uploads folder.",
     "inputSchema": {"type": "object", "required": ["name", "content"], "properties": {"name": {"type": "string"}, "content": {"type": "string"}}}},
    {"name": "goal_report", "description": "Report on your Goal. verdict \"done\" when you believe every acceptance criterion is met and all "
     "checks pass: an independent verifier then checks it and any failures come back to you as a [Goal] message. verdict \"blocked\" "
     "only when you can't go on without the user (a missing credential or access): say what you need in summary.",
     "inputSchema": {"type": "object", "required": ["verdict", "summary"], "properties": {
         "verdict": {"type": "string", "enum": ["done", "blocked"]}, "summary": {"type": "string"},
         "failing": {"type": "array", "items": {"type": "string"}, "description": "What is still not working, if anything"}}}},
    {"name": "goal_create", "description": "Create a Goal: an autonomous loop that works on a project folder until an independent verifier passes it. "
     "Returns the intake questions to relay to the user (takes ~30 s); then goal_answer and goal_start.",
     "inputSchema": {"type": "object", "required": ["name", "folder", "objective"], "properties": {
         "name": {"type": "string"}, "folder": {"type": "string", "description": "Absolute project folder"},
         "objective": {"type": "string", "description": "What to build or check, with every link the user gave"},
         "schedule": {"type": "object", "description": "Recurring runs: {at: \"HH:MM\", days?: [0-6, 0 = Monday]}"}}}},
    {"name": "goal_answer", "description": "Save the user's answers to a Goal's intake questions (question id -> answer); the Goal becomes ready.",
     "inputSchema": {"type": "object", "required": ["id", "answers"], "properties": {
         "id": {"type": "string"}, "answers": {"type": "object", "additionalProperties": {"type": "string"}},
         "acceptance": {"type": "array", "items": {"type": "string"}, "description": "Replaces the proposed acceptance criteria"}}}},
    {"name": "goal_start", "description": "Start a ready Goal. It works alone and the user is notified when it is done, failed or blocked.",
     "inputSchema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "string"}}}},
    {"name": "goal_message", "description": "Pass the user's answer to a blocked Goal (it resumes), or an extra instruction to a running one.",
     "inputSchema": {"type": "object", "required": ["id", "text"], "properties": {"id": {"type": "string"}, "text": {"type": "string"}}}},
    {"name": "goal_list", "description": "The user's Goals: status, iteration, questions, last report.", "inputSchema": {"type": "object", "properties": {}}},
]
ASSIST_TOOLS = {"set_job", "remove_job", "list_jobs", "send_file", "goal_create", "goal_answer", "goal_start", "goal_message", "goal_list"}


def brain_mcp():
    """`server.py brain-mcp`: the Second Brain's tools as an MCP server on stdio (newline JSON-RPC). Each call goes to
    /api/brain/<tool> on Flows with the brain's token. It runs as the owner's Linux user: no Flows data access here."""
    def call(name, args):
        req = Request(f"http://127.0.0.1:{os.environ['FLOWS_PORT']}/api/brain/{name}", data=json.dumps(args).encode(), method="POST",
                      headers={"Content-Type": "application/json", "X-Flow": "1", "X-Brain": os.environ["FLOWS_BRAIN_TOKEN"]})
        try:
            with urlopen(req, timeout=120) as f:
                return json.loads(f.read())["text"], False
        except HTTPError as e:
            return json.loads(e.read() or b"{}").get("error") or str(e), True
        except Exception as e:
            return f"Flows is unreachable: {e}", True
    for line in sys.stdin:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        m, prm = msg.get("method"), msg.get("params") or {}
        if "id" not in msg:  # notifications (initialized, cancelled)
            continue
        if m == "initialize":
            res = {"protocolVersion": prm.get("protocolVersion") or "2024-11-05", "capabilities": {"tools": {}},
                   "serverInfo": {"name": "flows", "version": "1"}}
        elif m == "tools/list":
            res = {"tools": [t for t in BRAIN_TOOLS if (os.environ.get("FLOWS_ASSISTANT") or t["name"] not in ASSIST_TOOLS)
                             and (os.environ.get("FLOWS_GOAL") or t["name"] != "goal_report")]}
        elif m == "tools/call":
            text, err = call(prm.get("name"), prm.get("arguments") or {})
            res = {"content": [{"type": "text", "text": text}], "isError": err}
        elif m == "ping":
            res = {}
        else:
            print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": f"Unknown method {m}"}}), flush=True)
            continue
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}), flush=True)


if __name__ == "__main__" and sys.argv[1:2] == ["brain-mcp"]:  # before anything below touches the data dir
    raise SystemExit(brain_mcp())

ROOT = Path(__file__).parent
DATA = Path(os.environ.get("FLOWS_DATA") or ROOT / "data")  # the .deb sets ~/.local/share/flows
# Multi-user mode (see DEPLOY.md) is on when data/users.json exists: logins, per-user data, and every
# `claude` runs as that person's Linux user via sudo. Without the file: single user, no login, as always.
USERS_FILE = DATA / "users.json"
MULTI = USERS_FILE.exists()
if MULTI:
    os.umask(0o077)  # runs, sessions, workflows: readable by the server user only
RUNS = DATA / "runs"


def write_atomic(path, text):
    """Write via a temp file + rename, so a crash mid-save leaves the old file, never an empty one."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    with open(tmp, "w") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.chmod(tmp, path.stat().st_mode & 0o7777)  # keep the old file's permissions
    except FileNotFoundError:
        pass
    os.replace(tmp, path)

RUNS.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD = 20 << 20
MAX_IMAGE = 3_750_000  # the API refuses images over 5 MB of base64; bigger ones go by path
PORT = int(os.environ.get("PORT", 8787))
HOSTS = ("localhost", "127.0.0.1", *filter(None, os.environ.get("FLOWS_HOSTS", "").split(",")))  # public names behind a proxy


def load_users():
    return json.loads(USERS_FILE.read_text()) if USERS_FILE.exists() else {}


def hash_pw(pw, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 600_000).hex()


def check_pw(pw, stored):
    return hmac.compare_digest(hash_pw(pw, stored.split("$")[0]), stored)


def unix_home(owner):
    return pwd.getpwnam(load_users()[owner]["unix"]).pw_dir


def udir(owner, kind, rid="", make=False):
    """data/<kind>/<run> (single user), or data/users/<owner>/<kind>/<run>: group-owned by the owner's
    primary group, setgid, so their agent can read uploads and write screenshots (DEPLOY.md)."""
    base = DATA / "users" / owner if owner else DATA
    d = base / kind / rid
    if make:
        d.mkdir(parents=True, exist_ok=True)
        if owner:
            gid = pwd.getpwnam(load_users()[owner]["unix"]).pw_gid
            for x in {base, base / kind, d}:
                os.chown(x, -1, gid)
                os.chmod(x, 0o2770)
    return d


def workdir(owner, path):
    """The project folder: ~ is the owner's home, and in multi-user mode it must stay inside it."""
    path = path or "~"
    if not owner:
        return os.path.expanduser(path)
    home = unix_home(owner)
    d = os.path.normpath(os.path.join(home, "" if path == "~" else path[2:] if path.startswith("~/") else path))
    if os.path.commonpath([home, d]) != home:
        raise ValueError(f"The project folder must be inside {home}")
    return d


# Packages: what someone's agents can reach. "dev" = everything. "admin" = Google Workspace only:
# no file, shell or browser tools, and no other MCP server. Per person (users.json "package"),
# else per install (FLOWS_PACKAGE, set by the .deb).
GOOGLE = ("mcp__claude_ai_Google_Drive", "mcp__claude_ai_Gmail", "mcp__claude_ai_Google_Calendar")
PACKAGES = {"dev": None, "admin": {"tools": "Agent,ToolSearch,AskUserQuestion", "mcp": GOOGLE, "note": (
    "You help someone with no technical background with their Google Workspace: Gmail, Google Drive and Google Calendar. "
    "Those are your only tools and they are deferred: before saying you can't reach their mail, files or calendar, "
    "load them with ToolSearch (e.g. \"gmail\", \"drive\", \"calendar\") and use them. "
    "Answer in the person's language, in plain everyday words, with no technical terms, tool names or code. "
    "Before sending, saving or changing anything, say exactly what you will do; the person approves it in a popup.")}}


def package(owner):
    p = (load_users()[owner].get("package") if owner else None) or os.environ.get("FLOWS_PACKAGE") or "dev"
    return p if p in PACKAGES else "admin"  # a typo must not grant everything


def allowed(owner, tool):
    """May this person's package use the tool at all? (Asked tools outside it are refused, never shown.)"""
    pk = PACKAGES[package(owner)]
    return not pk or tool in pk["tools"].split(",") + ["Task"] or str(tool).startswith(pk["mcp"])


def fence(owner, cmd):
    """Clamp a `claude` command line to the owner's package, whatever the step or session asked for."""
    pk = PACKAGES[package(owner)]
    if not pk:
        return cmd
    out, it = [], iter(cmd)
    for a in it:
        if a == "--permission-mode":
            next(it)
            a = "--permission-mode=default"  # bypass would let every MCP tool through
        elif a == "--allowedTools":
            a = "--allowedTools=" + ",".join(t for t in next(it).split(",") if allowed(owner, t.strip()))
        elif a == "--mcp-config":  # Playwright
            next(it)
            continue
        elif a == "--append-system-prompt":
            a = "--append-system-prompt=" + next(it) + "\n\n" + pk["note"]
            pk = {**pk, "note": ""}  # used up
        out.append(a)
    # ponytail: user/project settings could still pre-allow a non-Google MCP tool; the sudo users of an admin
    # package have a fresh ~/.claude. --strict-mcp-config would be tighter but also drops the claude.ai connectors.
    return out + ["--tools=" + pk["tools"]] + (["--append-system-prompt=" + pk["note"]] if pk["note"] else [])  # built-ins: Read, Bash, Edit, WebFetch… all gone


def launch(owner, cmd, cwd, extra=None):
    """Start `claude`. Multi-user: as the owner's Linux user through sudo (it relays our SIGTERM on cancel/stop)."""
    # Long sessions grew to 400k tokens and every turn re-read all of it. Compact at ~200k instead of near 1M.
    extra = {"CLAUDE_CODE_AUTO_COMPACT_WINDOW": os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW", "200000"), **(extra or {})}
    cmd = fence(owner, cmd)
    if MULTI and not owner:  # e.g. a run left over from single-user mode: never run it as the server user
        raise ValueError("This run has no owner")
    if owner:
        # the extra vars go by name (SETENV in sudoers), not VAR=value: sudo's command line is visible in ps
        # to every user, and FLOWS_BRAIN_TOKEN is a secret
        cmd = ["sudo", "-n", "-u", load_users()[owner]["unix"], "-H", "-D", cwd,
               *(["--preserve-env=" + ",".join(extra)] if extra else []), "--", *cmd]
        cwd = None  # the server user can't enter their home; sudo -D does it as them
    return subprocess.Popen(cmd, cwd=cwd, env={**ENV, **(extra or {})}, text=True, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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

usages = {}  # owner (None in single-user mode) -> their subscription's limits: everyone has their own plan


def use(owner):
    if owner not in usages:
        f = usage_file(owner)
        usages[owner] = json.loads(f.read_text()) if f.exists() else {}
    return usages[owner]


def usage_file(owner):
    return DATA / "usage" / f"{owner}.json" if owner else DATA / "usage.json"


def save_usage(owner):
    usage_file(owner).parent.mkdir(exist_ok=True)
    write_atomic(usage_file(owner), json.dumps(use(owner)))


def note_usage(ev, owner):
    """Keep the latest subscription limits (5-hour / weekly utilization) that the CLI reports."""
    info, usage = ev.get("rate_limit_info") or {}, use(owner)
    if info:
        usage.update({"windows": info.get("unifiedWindows") or usage.get("windows"), "status": info.get("status"),
                      "type": info.get("rateLimitType"), "resetsAt": info.get("resetsAt"), "ts": ev.get("ts") or time.time()})
        save_usage(owner)


def note_auth(res, owner):
    """Remember whether the owner's CLI is logged in (a result asking to /login says it isn't)."""
    ok = not (res.get("is_error") and re.search(r"/login|not logged in|invalid api key", str(res.get("result")), re.I))
    if use(owner).get("auth", True) != ok:
        use(owner)["auth"] = ok
        save_usage(owner)


def limited_until(owner):
    """Epoch when the subscription limit resets, or 0 if we may run now."""
    usage = use(owner)
    t = usage.get("resetsAt") or 0
    return t if usage.get("status") == "rejected" and t > time.time() else 0


def hit_limit(res, owner):
    """Did this turn end because the usage limit ran out? Records the reset time so the queue waits for it."""
    text = str((res or {}).get("result") or "")
    if not (res and res.get("is_error")):
        return False
    if limited_until(owner):
        return True
    if not re.search(r"usage limit|hit your limit|limit reached|rate.?limit", text, re.I):
        return False
    # no reset time from the CLI: parse "limit reached|<epoch>", else retry in 15 min
    m = re.search(r"\|(\d{10})", text)
    use(owner).update(status="rejected", resetsAt=int(m.group(1)) if m else time.time() + 900)
    save_usage(owner)
    return True


ORCH = """You are the lead orchestrator of a team of subagents.
- When the work splits into independent sub-tasks, delegate them with the Agent tool. Each subagent starts from a fresh ~30k-token context, so answer questions and do small or single-file tasks yourself.
- Run up to {n} subagents in parallel: launch them in a single message.
- Don't re-read or re-check what a subagent already verified; trust its report unless something looks off.
- Give each subagent a self-contained prompt: exact file paths, what to do, how to verify, what to report back.
- Never let two subagents edit the same file at the same time. Do tiny or strictly sequential work yourself.
- When subagents finish, integrate and verify their work (build, lint) before reporting.
- The user may message you at any time to change the parallelism limit or redirect you. Always follow the latest instruction; if asked to go faster, split remaining work further and launch more subagents right away.
{models}"""

BRAIN = """You are the Second Brain of this project: you run it end to end by coordinating Flows sessions, each a lead agent with its own subagents. Your tools for that are the `flows` MCP tools: load them with ToolSearch ("flows") before the first use.
- Plan first. Split the project into workstreams that don't edit the same files, and start one session per workstream with start_session and a self-contained brief: goal, exact paths, constraints, contracts with other workstreams, how to verify, what to report.
- Run at most {n} sessions at once.
- You'll receive [Flows] messages when a session asks something or finishes a turn. Answer questions by your own judgment with answer_question, review results (read_session), relay what other sessions need with send_message, and give next instructions.
- Ask the user (AskUserQuestion) only for decisions that are really theirs: taste, scope, money, credentials, anything irreversible or outward-facing.
- Don't do the implementation or the checking yourself: you have no terminal or editor. Every file or image you read stays in your context and is re-read on each of your turns, so never Read images or files over ~200 lines; ask a session for a short report instead.
- At the end verify the whole thing works and report to the user briefly. Answer in the user's language. Keep it tight."""
ASSISTANT = """You are Flows Asistente, the user's personal assistant. They reach you by chat (web or WhatsApp): reply in at most 3 short plain lines (more only if they ask for detail), in the language they write in (they mix Spanish, English and Catalan).
- Their Gmail, Google Calendar, Google Drive and Trello are connected; load those tools with ToolSearch ("gmail", "calendar", "drive", "trello") before saying you can't reach them. Reading is free. Sending or forwarding mail, creating or deleting events, Trello writes, publishing, deploying and anything destructive go through an approval the user gives on their phone: just call the tool (don't ask in text first) and say in a line what you did.
- Code or project work: start a Flows session with the `flows` MCP tools (ToolSearch "flows") in the right project folder (see ~/.claude/flows-projects/*.md) with a self-contained brief. [Flows] messages tell you when a session finishes or asks: pass the outcome on in a line or two.
- Reminders and routines: the `flows` tools set_job, remove_job, list_jobs ("apúntame a las 15 X" = set_job with today's date, at 15:00). [Job <id>] messages are jobs firing: do the job and reply with what the user should know, or exactly NOTHING if nothing needs them.
- You have no terminal or editor: file and code work goes to sessions. Don't read big files.
- Files for the user: `send_file` for small text/CSV/Markdown; for PDFs, images or Office files have a session write the file into your uploads folder (path in the session's system note). Files the user sends arrive as "Attached files: <path>" (and "[voz]" marks a transcribed voice note, so expect transcription slips).
- Goals ("develop project X until it's done", "nightly QA of X"): goal_create with the folder and everything the user gave, relay its intake questions, then goal_answer and goal_start. A Goal works alone and its done/failed/blocked notices reach the user by themselves; goal_message passes their answer to a blocked one; goal_list.
- "/auto on" lets you act without approvals, "/auto off" goes back to asking."""
# What the assistant may use without an approval (also inherited by the sessions it starts).
READONLY = ",".join(["Read,Glob,Grep,WebSearch,WebFetch,ToolSearch"] + [f"mcp__claude_ai_{k}__{t}" for k, ts in {
    "Gmail": "search_threads get_thread get_message list_labels list_drafts get_draft create_draft update_draft",
    "Google_Calendar": "list_events get_event list_calendars search_events suggest_time",
    "Google_Drive": "search_files read_file_content download_file_content get_file_metadata get_file_permissions list_recent_files",
    "Trello": "trelloReadBoard trelloReadCard trelloReadChecklist trelloReadInbox trelloReadList trelloReadMember trelloReadPlanner "
              "trelloReadWorkspace trelloSearch"}.items() for t in ts.split()])
CHILD = ("This session is part of a project coordinated by the Second Brain: your AskUserQuestion questions go to it. "
         "Ask it about decisions, contracts with other sessions or anything unclear. When you finish, end with a concise "
         "report of what you did, how you verified it and open issues.")

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
    write_atomic((RUNS / f"{r['id']}.json"), json.dumps(r))


def wf_file(owner):
    return DATA / "workflows" / f"{owner}.json" if owner else DATA / "workflows.json"


def load_wfs(owner):
    return json.loads(wf_file(owner).read_text()) if wf_file(owner).exists() else {}


def save_wfs(w, owner):
    wf_file(owner).parent.mkdir(exist_ok=True)
    write_atomic(wf_file(owner), json.dumps(w, indent=2))


# Claude Code subagents: ~/.claude/agents/<name>.md, YAML frontmatter + directives. Often symlinks into
# the user's own repo: edits go through the link, so the repo file is what changes.
def claude_dir(owner):
    # ponytail: multi-user reads/writes the owner's home as the server user; needs a sudo helper if homes are 700
    return Path(unix_home(owner) if owner else Path.home()) / ".claude"


def front(text):
    """(frontmatter, body) of an agent or SKILL.md. Only the YAML these files use: scalars, quoted
    scalars, `[a, b]` and `- item` lists, `>`/`|` blocks."""
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    if not m:
        return {}, text
    meta, key = {}, None
    for line in m.group(1).splitlines():
        s = line.strip()
        if not s or s[0] == "#":
            continue
        if key and line[0] in " \t":  # belongs to the key above: a list item or a folded line
            if s[:2] == "- ":
                meta[key] = (meta[key] or []) + [s[2:].strip()]
            else:
                meta[key] = (meta[key] + " " + s).strip()
            continue
        key, _, v = (x.strip() for x in line.partition(":"))
        if v[:1] == "[":
            v = [x.strip().strip("'\"") for x in v.strip("[]").split(",") if x.strip()]
        elif v in (">", "|", ">-", "|-"):
            v = ""
        elif len(v) > 1 and v[0] == v[-1] == "'":
            v = v[1:-1].replace("''", "'")
        elif len(v) > 1 and v[0] == v[-1] == '"':
            v = json.loads(v)
        meta[key] = v
    return meta, m.group(2)


def yaml_str(v):
    """Plain when YAML reads it back unchanged, else double-quoted (JSON is valid YAML)."""
    return json.dumps(v, ensure_ascii=False) if not v or re.search(r":\s|\s#|^[-?:,\[\]{}#&*!|>'\"%@`\s]|\s$", v) else v


def agent_info(f):
    meta, body = front(f.read_text())
    return {"name": f.stem, "description": meta.get("description", ""), "model": meta.get("model", ""),
            "tools": meta.get("tools", ""), "skills": meta.get("skills") or [], "file": str(f.resolve()), "link": f.is_symlink()}, meta, body


def list_agents(owner):
    d = claude_dir(owner) / "agents"
    return [agent_info(f)[0] for f in sorted(d.glob("*.md")) if f.is_file() and re.fullmatch(r"[a-z0-9-]+", f.stem)]


def list_skills(owner):
    out = []
    for f in sorted((claude_dir(owner) / "skills").glob("*/SKILL.md")):
        meta = front(f.read_text())[0]
        out.append({"name": meta.get("name") or f.parent.name, "description": " ".join(str(meta.get("description", "")).split())})
    return out


def agent_api(owner, m, name, body):
    if not re.fullmatch(r"[a-z0-9-]+", name):
        raise ValueError("Nombre: solo minúsculas, números y guiones")
    d = claude_dir(owner) / "agents"
    f = d / f"{name}.md"
    if not (m == "PUT" and body.get("new")) and not f.is_symlink() and not f.is_file():
        raise KeyError(name)
    if m == "GET":
        info, _, text = agent_info(f)
        return {**info, "body": text}
    if m == "DELETE":
        kept = f.resolve() if f.is_symlink() else None
        f.unlink()  # a symlink: only the link goes, the repo file stays
        return {"ok": True, "kept": kept and str(kept)}
    if m != "PUT":
        raise KeyError(m)
    desc = " ".join(str(body.get("description") or "").split())
    if not desc:
        raise ValueError("Falta la descripción: es lo que usa el agente principal para elegirlo")
    if body.get("new"):
        # New agents go where the others are linked from (the user's agents repo), linked the same way.
        repo = next((x.resolve().parent for x in d.glob("*.md") if x.is_symlink() and x.is_file()), None)
        if f.exists() or f.is_symlink() or (repo and (repo / f.name).exists()):
            raise ValueError(f"Ya existe un agente llamado {name}")
        meta = {}
        d.mkdir(parents=True, exist_ok=True)
        if repo:
            (repo / f.name).touch()
            f.symlink_to(repo / f.name)
    else:
        meta = front(f.read_text())[0]  # keep keys the editor doesn't show (effort, maxTurns, …)
    skills = [s for s in body.get("skills") or [] if re.fullmatch(r"[A-Za-z0-9:_-]+", str(s))]
    meta = {"name": name, **meta, "description": desc, "tools": " ".join(str(body.get("tools") or "").split()),
            "model": str(body.get("model") or "").strip(), "skills": skills}
    head = []
    for k, v in meta.items():
        if isinstance(v, list):
            head += [f"{k}:"] + [f"  - {yaml_str(str(x))}" for x in v] if v else []
        elif str(v):
            head.append(f"{k}: {yaml_str(str(v))}")
    f.write_text("---\n" + "\n".join(head) + "\n---\n" + str(body.get("body") or "").strip() + "\n")  # follows the link
    return agent_info(f)[0]


# Projects: a session belongs to the git root of its folder (else the folder itself). Each project has a short
# Markdown context in ~/.claude/flows-projects/<slug>.md that its sessions read first and keep up to date.
PROJECT = ("Project context: {f} is shared by every session working on {p}. Read it first if it exists. Before ending a turn "
           "that changed something durable (goal, decisions, state, next steps, conventions), update it concisely: keep it short "
           "and rewrite stale parts instead of appending forever. If it doesn't exist yet, create it starting with \"# {name}\".")


def project_of(path):
    # ponytail: multi-user, the server user can't see into a 700 home, so it falls back to the folder itself
    p = Path(path)
    return str(next((d for d in (p, *p.parents) if (d / ".git").exists()), p))


def project_slug(path):
    return (re.sub(r"[^a-z0-9]+", "-", Path(path).name.lower()).strip("-")[:40] or "root") + "-" + hashlib.sha1(path.encode()).hexdigest()[:6]


def project_file(owner, path):
    return claude_dir(owner) / "flows-projects" / f"{project_slug(path)}.md"


WP_NOTE = ("This is a WordPress project. Before any work, invoke the Skill tool with skill `wp-plugin-development` and follow it; "
           "act as an expert WordPress developer (WP coding standards, hooks, sanitize/escape/nonces, i18n).")


def wp_auto(path):
    """Does the folder look like WordPress? (core, a theme or a plugin, at the top or in ./theme/)"""
    d = Path(path)
    try:
        if (d / "wp-config.php").exists() or (d / "wp-content").is_dir():
            return True
        for base in (d, d / "theme"):
            for f in [*base.glob("*.css")][:5]:
                if "Theme Name:" in f.read_text(errors="ignore")[:2000]:
                    return True
            for f in [*base.glob("*.php")][:20]:
                if "Plugin Name:" in f.read_text(errors="ignore")[:2000]:
                    return True
    except OSError:
        pass
    return False


def wp_flag(owner, cwd):
    """WordPress mode of a folder: the user's choice in flows-projects/<slug>.json, else auto-detected."""
    path = project_of(workdir(owner, cwd))
    try:
        on = json.loads(project_file(owner, path).with_suffix(".json").read_text()).get("wordpress")
    except (OSError, ValueError):
        on = None
    auto = wp_auto(path)
    return {"on": auto if on is None else bool(on), "auto": auto, "set": on is not None, "path": path}


def wp_set(owner, cwd, on):
    f = project_file(owner, project_of(workdir(owner, cwd))).with_suffix(".json")
    f.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(f, json.dumps({"wordpress": bool(on)}))


def run_project(r):
    if "project" not in r:  # runs from before projects existed
        try:
            r["project"] = project_of(workdir(r.get("owner"), r["config"].get("cwd")))
        except (ValueError, KeyError):
            r["project"] = None
    return r["project"]


def projects(owner, slug=None):
    """The owner's projects, newest session first, with their sessions and context (an excerpt when listing)."""
    out = {}
    for r in sorted(runs.values(), key=lambda r: r["started"], reverse=True):
        if r.get("owner") != owner or r.get("kind") != "session" or not run_project(r):
            continue
        s = project_slug(r["project"])
        j = out.setdefault(s, {"slug": s, "name": Path(r["project"]).name or r["project"], "path": r["project"], "sessions": []})
        j["sessions"].append({**{k: r.get(k) for k in ("id", "name", "status", "started", "ended", "pinned", "brain", "parent")},
                              **({"status": "waiting"} if r.get("waiting") else {}), "last":r["events"][-1].get("ts") if r["events"] else r["started"]})
    for j in out.values() if not slug else [out[slug]]:
        f = project_file(owner, j["path"])
        try:
            j["context"], j["mtime"] = f.read_text(), f.stat().st_mtime
        except OSError:
            j["context"], j["mtime"] = "", None
        j["wordpress"] = wp_flag(owner, j["path"])
        if not slug:
            j["context"] = j["context"][:300]
    return out[slug] if slug else list(out.values())


def render(template, inp, prev, site=""):
    return template.replace("{{input}}", inp).replace("{{prev}}", prev).replace("{{site}}", site)


def browser(cmd, tools, r):
    """Attach Playwright (headless Chrome) when the step may use the browser.
    Returns a system-prompt note pinning screenshots to data/shots/<run> (relative names resolve to the project)."""
    if "mcp__playwright" not in tools:
        return ""
    out = udir(r.get("owner"), "shots", r["id"], make=True)
    cmd += ["--mcp-config", json.dumps({"mcpServers": {"playwright": {"command": "npx", "args": [
        "-y", "@playwright/mcp@0.0.82", "--headless", "--isolated", "--ignore-https-errors", "--output-dir", str(out)]}}})]
    return (f"When you take browser screenshots, always pass an absolute filename inside {out}/ "
            f"(e.g. {out}/home-1440.png). Never save screenshots into the project.")


def keep_shots_out(ev, cwd, r, seen):
    """Models sometimes save screenshots with a bare filename, which Playwright writes into the project.
    Move those into data/shots/<run> once the tool has finished, so projects stay clean."""
    m = ev.get("message")
    for x in (m.get("content") if isinstance(m, dict) else None) or []:
        if not isinstance(x, dict):
            continue
        if x.get("type") == "tool_use" and str(x.get("name", "")).endswith("browser_take_screenshot"):
            name = (x.get("input") or {}).get("filename") or ""
            if name and not os.path.isabs(name):
                seen[x["id"]] = name
        elif x.get("type") == "tool_result" and x.get("tool_use_id") in seen:
            src = Path(cwd) / seen.pop(x["tool_use_id"])
            dst = udir(r.get("owner"), "shots", r["id"]) / src.name
            try:  # multi-user: the server can't reach into the owner's home, so the file stays put
                if src.suffix.lower() in (".png", ".jpg", ".jpeg") and src.is_file() and not dst.exists():
                    udir(r.get("owner"), "shots", r["id"], make=True)
                    src.replace(dst)
            except OSError:
                pass


def outbox(r):
    """Files the agent wrote into data/uploads/<run>/ that no event lists yet become its chat attachments."""
    known = {f["name"] for e in r["events"] for f in e.get("files") or []}
    try:
        new = sorted((f for f in udir(r.get("owner"), "uploads", r["id"]).iterdir() if f.is_file() and f.name not in known),
                     key=lambda f: f.stat().st_mtime)
        files = [{"name": f.name, "image": bool(image_type(f.open("rb").read(12)))} for f in new]
    except OSError:
        return []
    if files:
        r["events"].append({"type": "attach", "files": files, "ts": time.time()})
    return files


def image_type(raw):
    """Media type from the file's magic bytes (a wrong media_type makes the API reject the whole message)."""
    for magic, t in ((b"\x89PNG", "image/png"), (b"\xff\xd8\xff", "image/jpeg"), (b"GIF8", "image/gif")):
        if raw.startswith(magic):
            return t
    return "image/webp" if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else None


def save_files(r, files):
    """Check every upload, then write them to data/uploads/<run>/ (basename only, deduped).
    files: [{name, data: base64}] -> [{name, path, media, b64?}]"""
    files = files or []
    for f in files:
        if len(f.get("data") or "") * 3 // 4 > MAX_UPLOAD:
            raise ValueError(f"{Path(str(f.get('name'))).name} is over {MAX_UPLOAD >> 20} MB")
    out = []
    for f in files:
        raw = base64.b64decode(f.get("data") or "")
        name = re.sub(r"[^\w.\- ]", "_", Path(str(f.get("name") or "")).name).strip(". ")[-120:] or "file"
        d = udir(r.get("owner"), "uploads", r["id"], make=True)
        dst, n = d / name, 1
        while dst.exists():
            n += 1
            dst = d / f"{Path(name).stem}-{n}{Path(name).suffix}"
        dst.write_bytes(raw)
        if r.get("owner"):
            os.chmod(dst, 0o640)  # the owner's agent reads it through the group
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
    for k in ("shots", "uploads"):
        shutil.rmtree(udir(r.get("owner"), k, rid), ignore_errors=True)


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
            notes.append(browser(cmd, tools, r))
            if any(notes):
                cmd += ["--append-system-prompt", "\n\n".join(filter(None, notes))]
            s = {"name": step.get("name") or f"Step {i + 1}", "status": "running",
                 "started": time.time(), "events": []}
            with lock:
                if r["status"] != "running":
                    return
                r["steps"].append(s)
            cwd = workdir(r.get("owner"), step.get("cwd") or r["workflow"].get("cwd"))
            p = launch(r.get("owner"), cmd, cwd)
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
                keep_shots_out(ev, cwd, r, seen)
                if ev.get("type") == "rate_limit_event":
                    note_usage(ev, r.get("owner"))
                if ev.get("type") == "result":
                    res = ev
                    note_auth(ev, r.get("owner"))
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
                elif r["status"] == "running" and hit_limit(res, r.get("owner")):
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


def start_run(wf_id, inp, owner):
    wf = load_wfs(owner)[wf_id]
    r = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4], "workflow_id": wf_id, "owner": owner,
         "name": wf["name"], "input": inp, "status": "running", "started": time.time(),
         "ended": None, "cost": 0, "steps": [], "workflow": wf}
    with lock:
        runs[r["id"]] = r
    threading.Thread(target=execute, args=(r,), daemon=True).start()
    return r["id"]


# ---------- orchestrator sessions: one long-lived `claude` process fed via stdin ----------

brains = {}  # secret token -> Second Brain run id. In memory: every spawn mints a new one


def spawn(r):
    c = r["config"]
    # stdio prompt tool: questions (AskUserQuestion) and permission checks come back to us as control_requests
    cmd = ["claude", "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--permission-prompt-tool", "stdio", "--permission-mode", c.get("permission_mode") or "default",
           "--allowedTools", ",".join(filter(None, ["Agent,Task", c.get("allowed_tools"), r.get("brain") and "mcp__flows"])),
           "--add-dir", str(udir(r.get("owner"), "uploads", make=True))]  # so attached files are readable from any project folder
    if c.get("model"):
        cmd += ["--model", c["model"]]
    note = browser(cmd, c.get("allowed_tools") or "", r)
    extra = {"CLAUDE_CODE_ENABLE_ASK_USER_QUESTION_TOOL": "true"}
    if r.get("brain"):  # its tools: brain_mcp, run by claude, calling back into this server with the token (env only, never argv)
        tok = secrets.token_urlsafe(32)
        for k in [k for k, v in brains.items() if v == r["id"]]:
            del brains[k]
        brains[tok] = r["id"]
        extra.update(FLOWS_BRAIN_TOKEN=tok, FLOWS_PORT=str(PORT))
        cmd += ["--mcp-config", json.dumps({"mcpServers": {"flows": {  # a second --mcp-config (Playwright) adds up
            "command": sys.executable or "python3", "args": [str((ROOT / "server.py").resolve()), "brain-mcp"]}}})]
        lead = BRAIN.format(n=c.get("agents") or 3)
        if r.get("assistant"):  # it asks the user in its replies; AskUserQuestion would block WhatsApp
            lead = ASSISTANT + profile(r.get("owner"))
            extra["FLOWS_ASSISTANT"] = "1"
        if r.get("goal"):  # autonomous: nobody answers AskUserQuestion; goal_report "blocked" is its way to the user
            lead += "\n\n" + GOAL_RULES
            extra["FLOWS_GOAL"] = "1"
        cmd += ["--disallowedTools", "Bash,Edit,Write,NotebookEdit" + (",AskUserQuestion" if r.get("assistant") or r.get("goal") else "")]  # it coordinates; sessions do the work
    else:
        lead = ORCH.format(n=c.get("agents") or 3, models=sub_models_rule(c.get("sub_models"))) + ("\n\n" + CHILD if r.get("parent") else "")
    out = udir(r.get("owner"), "uploads", r["id"], make=True)
    note += (f"\n\nTo send the user a file in the chat, write it into {out}/ (plain filename, no subfolders). "
             "It appears as a downloadable attachment under your message when your turn ends." + (" You can't write files yourself: use send_file, or tell a session to." if r.get("assistant") else ""))
    if package(r.get("owner")) == "dev" and run_project(r):
        f, pj = project_file(r.get("owner"), r["project"]), r["project"]
        if not r.get("owner") and not f.exists():  # multi-user: their own claude creates it, so they own it
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(f"# {Path(pj).name or pj}\n\nFolder: {pj}\n")
        note += "\n\n" + PROJECT.format(f=f, p=pj, name=Path(pj).name or pj)
        if wp_flag(r.get("owner"), pj)["on"]:
            note += "\n\n" + WP_NOTE
    cmd +=["--append-system-prompt", "\n\n".join(filter(None, [lead, note]))]
    if r.get("session_id"):
        cmd += ["--resume", r["session_id"]]
        r["cost_base"] = r["cost"]  # new process reports cost from zero
    p = launch(r.get("owner"), cmd, workdir(r.get("owner"), c.get("cwd")), extra)
    procs[r["id"]] = p
    threading.Thread(target=pump, args=(r, p), daemon=True).start()
    return p


def pump(r, p):
    seen, cwd = {}, workdir(r.get("owner"), r["config"].get("cwd"))
    for line in p.stdout:
        try:
            ev = json.loads(line)
        except ValueError:
            ev = {"type": "raw", "text": line.rstrip()}
        ev["ts"] = time.time()
        keep_shots_out(ev, cwd, r, seen)
        t, sub = ev.get("type"), ev.get("subtype")
        if t == "rate_limit_event":
            note_usage(ev, r.get("owner"))
        if t == "control_request":
            req = ev.get("request") or {}
            if req.get("subtype") != "can_use_tool":
                write(p, {"type": "control_response", "response": {
                    "subtype": "error", "request_id": ev.get("request_id"), "error": "unsupported by Flows"}})
                continue
            if not allowed(r.get("owner"), req.get("tool_name")):
                write(p, {"type": "control_response", "response": {"subtype": "success", "request_id": ev.get("request_id"), "response": {
                    "behavior": "deny", "message": f"Not available in the {package(r.get('owner'))} package of Flows."}}})
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
            if goal_of(r) and q["tool"] != "AskUserQuestion":  # a Goal runs unattended: allow, except outward actions
                no = goal_denies(q["tool"], q["input"], G[goal_of(r)]["slug"])
                answer(r, {"id": q["id"], "allow": not no, "message": no}, by="goal")
                continue
            a = assistant_of(r)
            if a and q["tool"] != "AskUserQuestion":
                if st(a.get("owner"))["auto"]:
                    answer(r, {"id": q["id"], "allow": True}, by="auto")
                    continue
                post(a.get("owner"), "approval", ("" if a is r else r["name"] + ": ") + f"{q['tool']} "
                     + json.dumps(q["input"], ensure_ascii=False)[:800], approval_id=q["id"])
            if q["tool"] == "AskUserQuestion" and tell_brain(r, f"asks you (question_id {q['id']}):\n"
                    f"{json.dumps(q['input'].get('questions'), ensure_ascii=False)}\nAnswer it with answer_question. "
                    "If it is genuinely the user's decision, ask the user with AskUserQuestion first."):
                continue
            notify(r, "; ".join(x.get("question", "") for x in q["input"].get("questions") or []) if q["tool"] == "AskUserQuestion"
                   else f"Allow {q['tool']}?")
            continue
        done = said = made = None
        with lock:
            was = r["status"]
            r["events"].append(ev)
            if t == "system" and sub == "background_tasks_changed":
                r["bg"] = len(ev.get("tasks") or [])
            if t == "system" and sub == "init":
                r["session_id"] = ev.get("session_id")
            if t == "result":
                made = outbox(r)
                said = r.get("assistant") and str(ev.get("result") or "").strip()
                job = next((e.get("from") or "" for e in reversed(r["events"]) if e.get("type") == "input"), "").startswith("job:")
                if said and job and said.strip(" .").upper() == "NOTHING":
                    said = None
                note_auth(ev, r.get("owner"))
                if hit_limit(ev, r.get("owner")):
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
            if r.get("parent") and was in ("working", "asking") and r["status"] == "idle":
                done = last_text(r, 1200)
        if done is not None:
            tell_brain(r, "finished its turn:\n" + done)
        if said:
            post(r.get("owner"), "notice" if job else "reply", said)
        for f in (made or []) if r.get("assistant") else []:
            wa_file(r, f["name"])
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
        failed = r["status"] == "failed" and last_text(r, 3000)
    if failed is not False:
        tell_brain(r, "failed: its process ended with an error. Last message:\n" + failed)


def tell_brain(r, text):
    """Pass a child session's question or turn end to its Second Brain, if it still exists. In a thread: send() may
    spawn the brain and wait, and must never block the child's pump or run under `lock`."""
    b = r.get("parent") and runs.get(r["parent"])
    if b and b.get("goal") and G.get(b["goal"], {}).get("status") not in ("running", "verifying", "blocked"):
        return b  # a stopped or finished goal: don't respawn its brain
    if b:
        threading.Thread(target=send, args=(b, f"[Flows] Session \"{r['name']}\" ({r['id']}) {text}"), kwargs={"src": r["id"]}, daemon=True).start()
    return b


def last_text(r, n):
    """The lead's last text message, cut to n characters."""
    for e in reversed(r["events"]):
        m = e.get("message")
        if e.get("type") == "assistant" and not e.get("parent_tool_use_id") and isinstance(m, dict) and isinstance(m.get("content"), list):
            t = "\n".join(x.get("text") or "" for x in m["content"] if isinstance(x, dict) and x.get("type") == "text").strip()
            if t:
                return t[:n] + ("…" if len(t) > n else "")
    return ""


def send(r, text, agents=None, sub_models=None, files=(), src=None):
    """files: saved uploads from save_files. Images go as image blocks, and every file's path is listed.
    src: the child session a [Flows] message to a Second Brain is about."""
    with lock:
        if agents:
            r["config"]["agents"] = agents
        if sub_models:  # saved for respawns; the message itself tells the running lead
            r["config"]["sub_models"] = sub_models
        fresh = r["id"] not in procs
        p = procs.get(r["id"]) or spawn(r)
        ev = {"type": "input", "text": text, "ts": time.time()}
        if files:
            ev["files"] = [{"name": f["name"], "image": bool(f["media"])} for f in files]
        if src:
            ev["from"] = src
        r["events"].append(ev)
        r.pop("waiting", None)
        r["status"], r["turn_done"], r["ended"] = ("asking" if r.get("pending") else "working"), False, None
    content = text
    if files:
        content = [{"type": "text", "text": "\n\n".join(filter(None, [text, "Attached files: " + ", ".join(f["path"] for f in files)]))}] + [
            {"type": "image", "source": {"type": "base64", "media_type": f["media"], "data": f["b64"]}} for f in files if f["b64"]]
    if fresh:
        # The claude.ai connectors (Gmail, Drive, Calendar…) connect ~0.5s after start. A first turn sent
        # earlier sees no deferred tools, so ToolSearch is switched off for it and the agent says it has no access.
        # ponytail: fixed delay; replace with a readiness signal if the CLI ever emits one for stream-json input.
        time.sleep(3)
    write(p, {"type": "user", "message": {"role": "user", "content": content}})


def write(p, obj):
    with wlock:
        p.stdin.write(json.dumps(obj) + "\n")
        p.stdin.flush()


def answer(r, body, by=None):
    """Reply to a pending question or permission check. body: {id, allow, answers?, always?, message?}
    by: "brain" when the Second Brain answers its child's question."""
    with lock:
        q = r.get("pending", {}).pop(body["id"], None)
        if not q:  # e.g. the user and the Second Brain both answered
            raise ValueError("That question was already answered")
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
                            "message": body.get("message"), "ts": time.time(), **({"by": by} if by else {})})
        if r["status"] == "asking" and not r["pending"]:
            r["status"] = "working"
    write(p, {"type": "control_response", "response": {"subtype": "success", "request_id": body["id"], "response": resp}})
    a = assistant_of(r)
    if a and q["tool"] != "AskUserQuestion":  # lets every client of the assistant drop or grey out the approval
        post(a.get("owner"), "resolved", "", approval_id=body["id"], allow=bool(body.get("allow")))


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


def start_session(body, owner, brain=None, assistant=False, src=None, goal=None):
    """brain: the Second Brain run starting this session as its child. The child gets the brain's permissions;
    only the folder (still inside the owner's home) and the model can differ."""
    text = body.get("message", "").strip()
    if body.get("brain") and package(owner) != "dev":
        raise ValueError("The Second Brain is only in the dev package")
    workdir(owner, body.get("cwd"))  # refuse a folder outside their home before the session exists
    c = {k: body.get(k) for k in ("cwd", "model", "permission_mode", "allowed_tools", "agents", "caps", "sub_models")}
    if brain:
        c = {**{k: brain["config"].get(k) for k in ("permission_mode", "allowed_tools", "caps", "sub_models")}, "agents": 3,
             "cwd": body.get("cwd") or brain["config"].get("cwd"), "model": body.get("model") or "sonnet"}  # not the brain's opus: children were ~80% of a brain project's cost
    r = {"id": time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4], "kind": "session", "owner": owner,
         "name": str(body.get("name") or "")[:60] or (text.splitlines()[0][:60] if text else "Session"), "status": "working",
         "started": time.time(), "ended": None, "cost": 0, "events": [], "session_id": None, "config": c}
    run_project(r)
    if body.get("brain") and not brain:
        r["brain"] = True
    if brain:
        r["parent"] = brain["id"]
    if assistant:
        r["assistant"] = True
    if goal:
        r["goal"] = goal
        G[goal]["run"] = r["id"]  # before its first message: it may call goal_report at once
    files = save_files(r, body.get("files"))
    with lock:
        runs[r["id"]] = r
    send(r, text, files=files, src=src)
    return r["id"]


def stop_session(r):
    with lock:
        r["status"] = "stopped"
        r.pop("waiting", None)
        if r["id"] in procs:
            procs[r["id"]].terminate()


def transcript(r, since, cap=4000):
    """Compact text of a session's events from index `since` (lead only, subagents' inner work skipped)."""
    out, n, evs = [], since, r["events"]
    short = lambda x, k: (x if isinstance(x, str) else json.dumps(x, ensure_ascii=False))[:k]
    for n in range(since, len(evs)):
        e, line = evs[n], []
        m = e.get("message")
        c = [x for x in (m.get("content") if isinstance(m, dict) and isinstance(m.get("content"), list) else []) if isinstance(x, dict)]
        t = e.get("type")
        if e.get("parent_tool_use_id"):
            pass
        elif t == "assistant":
            line = [f"assistant: {short(x['text'], 3000)}" if x.get("type") == "text" else
                    f"tool {x.get('name')}: {short(x.get('input'), 200)}" for x in c if x.get("type") in ("text", "tool_use")]
        elif t == "user":
            line = [f"tool error: {short(x.get('content'), 300)}" for x in c if x.get("type") == "tool_result" and x.get("is_error")]
        elif t == "input":
            line = [f"message{' about ' + e['from'] if e.get('from') else ''}: {short(e.get('text'), 3000)}"]
        elif t == "ask":
            line = [f"question {e.get('id')} ({e.get('tool')}): {short(e.get('input'), 1500)}"]
        elif t == "answer":
            line = [f"answer {e.get('id')} by {e.get('by') or 'user'}: {'allowed' if e.get('allow') else 'declined'} {short(e.get('answers') or e.get('message') or '', 1000)}"]
        elif t == "result":
            line = ["turn finished" + (" with an error: " + short(e.get("result"), 500) if e.get("is_error") else "")]
        if out and sum(map(len, out + line)) > cap:
            return "\n".join(out + [f"(more: read again with since={n})"]), n
        out += line
    return "\n".join(out) or "(nothing new)", len(evs)


def brain_api(b, tool, a):
    """The Second Brain's tools (brain_mcp calls them as /api/brain/<tool>): only ever on its own child sessions.
    Returns the text the brain reads. KeyError: not one of its sessions; ValueError: refused."""
    if tool == "start_session":
        g = G.get(b.get("goal") or "")
        if b.get("goal") and not (g and g["run"] == b["id"] and g["status"] == "running"):
            raise ValueError("This goal is no longer running.")
        n = b["config"].get("agents") or 3
        with lock:
            live = sum(1 for r in runs.values() if r.get("parent") == b["id"] and r["status"] in ("working", "asking"))
        if live >= n:
            raise ValueError(f"{live} of your sessions are already working (your limit is {n}). Wait for one to finish its turn.")
        if not str(a.get("message") or "").strip():
            raise ValueError("start_session needs a `message`: the session's whole brief.")
        rid = start_session({k: a.get(k) for k in ("message", "name", "cwd", "model")}, b.get("owner"), b)
        return f"Started session {rid}."
    if tool == "list_sessions":
        with lock:
            kids = [{"id": r["id"], "name": r["name"], "status": r["status"],
                     "questions": [{"question_id": q["id"], "tool": q["tool"], "input": json.dumps(q["input"], ensure_ascii=False)[:300]} for q in (r.get("pending") or {}).values()],
                     "last_message": last_text(r, 300)} for r in runs.values() if r.get("parent") == b["id"]]
        return json.dumps(kids, ensure_ascii=False, indent=1) if kids else "No sessions yet."
    if tool in ("set_job", "remove_job", "list_jobs") and b.get("assistant"):
        o = b.get("owner")
        if tool != "list_jobs":
            set_jobs(o, [j for j in st(o)["jobs"] if j["id"] != a.get("id")] + ([a] if tool == "set_job" else []))
        return json.dumps(st(o)["jobs"], ensure_ascii=False)
    if tool == "goal_report" and b.get("goal"):
        return goal_reported(b["goal"], b["id"], a)
    if tool.startswith("goal_") and b.get("assistant"):
        return goal_tool(b.get("owner"), tool, a)
    if tool == "send_file" and b.get("assistant"):
        raw = str(a.get("content") or "").encode()[:1 << 20]
        if not wa_ok(str(a.get("name")), raw) or Path(str(a.get("name"))).suffix.lower() not in (".txt", ".csv", ".md"):
            raise ValueError("send_file takes a .txt, .csv or .md name and its text")
        return "Saved; it is sent to the user when your turn ends: " + save_files(runs[b["id"]], [{"name": a["name"], "data": base64.b64encode(raw).decode()}])[0]["name"]
    r = runs.get(str(a.get("id")))
    if not r or r.get("parent") != b["id"]:
        raise KeyError(a.get("id"))
    if tool == "read_session":
        with lock:
            since = a.get("since")
            text, nxt = transcript(r, max(0, int(since) if since is not None else len(r["events"]) - 15))
        return f"Status: {r['status']}\n{text}\n(next since={nxt})"
    if tool == "send_message":
        send(r, str(a.get("text") or ""))
        return "Sent."
    if tool == "answer_question":
        q = (r.get("pending") or {}).get(a.get("question_id"))
        if q and q["tool"] != "AskUserQuestion":
            raise ValueError("That is a permission check: only the user can answer it.")
        answer(r, {"id": a.get("question_id"), "allow": a.get("allow", True) is not False, "answers": a.get("answers") or {},
                   "message": a.get("message")}, by="brain")
        return "Answered."
    if tool == "stop_session":
        stop_session(r)
        return "Stopped."
    raise KeyError(tool)


# ---------- notifications: native on this desktop, Web Push to subscribed phones ----------
PUSH_FILE = DATA / "push.json"
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
        write_atomic(PUSH_FILE, json.dumps(push))
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
            write_atomic(PUSH_FILE, json.dumps(push))
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
        for s in [s for s in push["subs"].values() if s.get("owner") == r.get("owner")]:
            threading.Thread(target=push_one, args=(s["sub"], payload), daemon=True).start()


# ---------- queue: tasks that start one at a time, and pause while the usage limit is out ----------
QUEUE_FILE = DATA / "queue.json"
queue = json.loads(QUEUE_FILE.read_text()) if QUEUE_FILE.exists() else []
RESUME = "Continue where you left off. (Resumed automatically after the usage limit reset.)"


def save_queue():
    write_atomic(QUEUE_FILE, json.dumps(queue))


def own(rid, user):
    """The run, if this user owns it (KeyError, so a 404, otherwise)."""
    r = runs[rid]
    if r.get("owner") != user:
        raise KeyError(rid)
    return r


def enqueue(body, owner):
    """body: {kind: "workflow", wf_id, input}, {kind: "session", ...start_session body}
    or {kind: "message", run_id, text, files?}: sent to that session once it is free."""
    item = {**body, "id": uuid.uuid4().hex[:8], "added": time.time(), "owner": owner}
    k = body.get("kind")
    if k == "session":
        workdir(owner, body.get("cwd"))
    item["name"] = (load_wfs(owner)[body["wf_id"]]["name"] if k == "workflow" else
                    (body.get("text") or "Message").strip().splitlines()[0][:60] if k == "message" and own(body["run_id"], owner) else
                    (body.get("message") or "Session").strip().splitlines()[0][:60])
    with lock:
        queue.append(item)
        save_queue()
    return item["id"]


def busy(r):
    return r["status"] in ("running", "waiting", "working", "asking") or r.get("waiting")


def tick():
    """Each owner's queue runs one task at a time and pauses while their own usage limit is out."""
    with lock:
        waiting = [r for r in runs.values() if bool(r.get("owner")) == MULTI and not limited_until(r.get("owner")) and (r["status"] == "waiting" or
                   (r.get("waiting") and r["status"] in ("idle", "stopped", "failed")))]
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
            if not r or r.get("owner") != q.get("owner"):
                queue.remove(q)
            elif bool(q.get("owner")) == MULTI and q["run_id"] not in sent and not busy(r) and not limited_until(r.get("owner")):
                sent.add(q["run_id"])
                queue.remove(q)
                due.append((r, q))
        save_queue()
    for r, q in due:
        send(r, q.get("text", ""), files=save_files(r, q.get("files")))
    with lock:
        free = lambda o: not limited_until(o) and not any(r.get("queued") and busy(r) and r.get("owner") == o for r in runs.values())
        tasks = [q for q in queue if q.get("kind") != "message" and bool(q.get("owner")) == MULTI and free(q.get("owner"))]
        if not tasks:
            return
        item = tasks[0]
        queue.remove(item)
        save_queue()
    o = item.get("owner")
    rid = start_run(item["wf_id"], item.get("input", ""), o) if item.get("kind") == "workflow" else start_session(item, o)
    runs[rid]["queued"] = True


GREETED = DATA / "greeted.txt"


def good_morning():
    """At 6am local, once a day (the date is kept on disk, so a restart doesn't repeat it), each user gets a session saying buenos días."""
    now = time.localtime()
    today = time.strftime("%Y-%m-%d", now)
    if now.tm_hour != 6 or (GREETED.exists() and GREETED.read_text() == today):
        return
    GREETED.write_text(today)
    for o in (load_users() if MULTI else [None]):
        enqueue({"kind": "session", "name": "Buenos días", "message": "¡Buenos días, Claude!"}, o)


# ---------- Flows Asistente: one Second Brain per user, reachable from any channel (web, WhatsApp bridge) ----------
# data/assistant.json: {token, owner, users: {owner or "": {run, auto, jobs, outbox, n}}}. The bridge sends
# `Authorization: Bearer <token>` and acts as `owner`.
# shortcut: one bridge token, for the single user (or the "owner" set by hand in multi-user); per-user tokens when needed.
AFILE = DATA / "assistant.json"
A = json.loads(AFILE.read_text()) if AFILE.exists() else {}
acond = threading.Condition()  # guards A; outbox long-polls wait on it
alock = threading.Lock()  # one assistant spawn at a time
twlock = threading.Lock()  # one transcription at a time (RAM)
HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d(,([01]\d|2[0-3]):[0-5]\d)*")
BRIEF = ("Daily brief, exactly 5 short lines (this overrides the 3-line limit): 1) today's Google Calendar events with times, 2) the important "
         "unread Gmail (sender and subject), 3) the Flows sessions waiting for the user or failed (list the Flows sessions), then 4-5) the "
         "one or two things that matter most today. Reading only, no approvals.")
OLD_BRIEFS = ("Daily brief: today's Google Calendar, the important unread Gmail, and the unticked items in "
              "~/.claude/projects/*/memory/pending-tasks.md. A few short lines.",)
DEFAULT_JOBS = [
    {"id": "brief", "at": "08:30", "days": [0, 1, 2, 3, 4], "prompt": BRIEF},
    {"id": "heartbeat", "at": "09:00,11:00,13:00,15:00,17:00,19:00", "prompt": "Heartbeat: does anything need the user now? An urgent "
     "unread email, an event in the next 2 hours, one of your Flows sessions waiting or failed. Say it in a line or two, else reply exactly NOTHING."},
]


def save_a():
    write_atomic(AFILE, json.dumps(A, ensure_ascii=False))
    os.chmod(AFILE, 0o600)


def clean_job(j):
    """Validate a job from the UI, the bridge or the assistant: {id, at: "HH:MM[,HH:MM…]", days?: [0-6], date?, prompt}."""
    at = re.sub(r"\s", "", str(j.get("at") or ""))
    if not HHMM.fullmatch(at) or not str(j.get("prompt") or "").strip():
        raise ValueError("A job needs `at` (HH:MM, or several comma-separated) and a `prompt`")
    if j.get("date") and not re.fullmatch(r"\d{4}-\d\d-\d\d", str(j["date"])):
        raise ValueError("`date` is YYYY-MM-DD")
    out = {"id": re.sub(r"[^\w-]", "", str(j.get("id") or ""))[:40] or uuid.uuid4().hex[:6], "at": at, "prompt": str(j["prompt"])[:4000],
           "last": str(j.get("last") or time.strftime("%Y-%m-%d %H:%M"))}  # times already past today don't fire right away
    if j.get("days") is not None:
        out["days"] = sorted({int(d) for d in j["days"] if 0 <= int(d) <= 6})
    if j.get("date"):
        out["date"] = str(j["date"])
    return out


# Files that may cross WhatsApp in either direction: extension -> magic prefixes (None: plain text, no NUL bytes).
WA_TYPES = {".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",), ".png": (b"\x89PNG",), ".gif": (b"GIF8",), ".webp": (b"RIFF",),
            ".pdf": (b"%PDF",), ".docx": (b"PK",), ".xlsx": (b"PK",), ".pptx": (b"PK",), ".txt": None, ".csv": None, ".md": None}
WA_MAX = 16 << 20  # WhatsApp itself caps documents far higher; this keeps the bridge's memory small
VOICE_MAX = 8 << 20
VOICE_MAGIC = (b"OggS", b"ID3", b"RIFF", b"\xff\xfb", b"\xff\xf3")  # ogg/opus voice notes, mp3, wav; m4a has "ftyp" at 4


def wa_ok(name, raw):
    magic = WA_TYPES.get(Path(name).suffix.lower(), False)
    if magic is False or len(raw) > WA_MAX:
        return False
    return b"\0" not in raw[:4096] if magic is None else raw.startswith(magic)


def wa_file(r, name):
    """Hand a file the assistant wrote to its uploads folder to the channels (the bridge sends it to WhatsApp)."""
    f = udir(r.get("owner"), "uploads", r["id"]) / name
    try:
        if f.is_file() and f.stat().st_size <= WA_MAX and wa_ok(name, f.read_bytes()):
            post(r.get("owner"), "file", name, path=str(f))
    except OSError:
        pass


def transcribe(raw):
    """Voice note -> text in a throwaway process, so the model's RAM is freed as soon as it is done.
    FLOWS_TRANSCRIBE overrides the command (it gets the audio file path as its last argument)."""
    if not (raw.startswith(VOICE_MAGIC) or raw[4:8] == b"ftyp") or len(raw) > VOICE_MAX:
        raise ValueError("Unsupported or too large voice note")
    venv = DATA / "whisper-venv/bin/python"
    cmd = shlex.split(os.environ.get("FLOWS_TRANSCRIBE") or f"{venv if venv.exists() else sys.executable} {ROOT / 'scripts/transcribe.py'}")
    with tempfile.NamedTemporaryFile(suffix=".audio") as t, twlock:
        t.write(raw)
        t.flush()
        try:
            out = subprocess.run(cmd + [t.name], capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ValueError(f"Could not transcribe the voice note: {e}")
    if out.returncode or not out.stdout.strip():
        raise ValueError("Could not transcribe the voice note")
    return out.stdout.strip()[:4000]


def st(owner):
    """The owner's assistant state, created with the default jobs on first use."""
    with acond:
        s = A.setdefault("users", {}).get(owner or "")
        if s is None:
            s = A["users"][owner or ""] = {"run": None, "auto": False, "outbox": [], "n": 0, "jobs": [clean_job(j) for j in DEFAULT_JOBS]}
            save_a()
        return s


def set_jobs(owner, jobs):
    jobs = [clean_job(j) for j in jobs]
    with acond:
        st(owner)["jobs"] = jobs
        save_a()


def post(owner, kind, text, **kw):
    """Add to the owner's outbox ("reply", "notice", "approval", "resolved") and wake the long-polls. Notices also go to Web Push."""
    s = st(owner)
    with acond:
        s["n"] += 1
        s["outbox"] = s["outbox"][-199:] + [{"id": s["n"], "type": kind, "text": text, "ts": time.time(), **kw}]
        save_a()
        acond.notify_all()
    if kind == "notice":
        notify(runs.get(s["run"] or "") or {"id": "", "name": "Asistente", "owner": owner}, text)


def assistant_of(r):
    """The assistant run that r is, or that started r."""
    for x in (r, runs.get(r.get("parent") or "")):
        if x and x.get("assistant"):
            return x


def profile(owner):
    try:
        return "\n\nWhat you know about the user:\n" + (claude_dir(owner) / "flows-assistant" / "profile.md").read_text()[:8000]
    except OSError:
        return ""


def assistant_send(owner, text, src=None):
    """Send to the owner's assistant, starting it the first time (or after it was deleted). Reaped ones resume in send()."""
    s = st(owner)
    with alock:
        r = runs.get(s["run"] or "")
        if r:
            return send(r, text, src=src)
        rid = start_session({"message": text, "brain": True, "name": "Asistente", "permission_mode": "acceptEdits",
                             "allowed_tools": READONLY}, owner, assistant=True, src=src)
        with acond:
            s["run"] = rid
            save_a()


def job_slot(j, now):
    """The "YYYY-MM-DD HH:MM" slot job (or goal schedule) j is due for now, or None (not today, or that slot already ran)."""
    day = time.strftime("%Y-%m-%d", now)
    slot = f"{day} " + max((t for t in j["at"].split(",") if t <= time.strftime("%H:%M", now)), default="")
    return slot if j.get("date", day) == day and now.tm_wday in j.get("days", range(7)) and slot[-1] != " " and j["last"] < slot else None


def run_jobs(now=None):
    """Each job fires once per HH:MM slot on its days (or its date: one-off), as a [Job] message to the assistant."""
    now = now or time.localtime()
    day, due = time.strftime("%Y-%m-%d", now), []
    with acond:
        for o, s in A.get("users", {}).items():
            for j in list(s["jobs"]):
                slot = job_slot(j, now)
                if j.get("date", day) < day:
                    s["jobs"].remove(j)  # a reminder whose day went by while Flows was off
                elif slot:
                    j["last"] = slot
                    if j.get("date"):
                        s["jobs"].remove(j)
                    due.append((o or None, j))
        if due:
            save_a()
    for o, j in due:
        assistant_send(o, f"[Job {j['id']}] {j['prompt']}", src="job:" + j["id"])


if not A.get("token"):
    A["token"] = secrets.token_urlsafe(32)
    save_a()
for _s in A.get("users", {}).values():  # the first default brief didn't cover Flows sessions
    for _j in _s["jobs"]:
        if _j["id"] == "brief" and _j["prompt"] in OLD_BRIEFS:
            _j["prompt"] = BRIEF
            save_a()
if not MULTI:
    st(None)


# ---------- Goals: autonomous loops that work until an independent verifier passes them ----------
# data/goals.json: {id: goal}. Intake (one-shot claude) asks the user what it needs once; then a Second Brain run flagged
# `goal` works alone, calls goal_report when done, a fresh one-shot verifier checks it, failures go back as the next
# iteration until it passes or max_iter / max_hours run out. done/failed/blocked -> assistant notice (WhatsApp + Web Push).
GFILE = DATA / "goals.json"
G = json.loads(GFILE.read_text()) if GFILE.exists() else {}
glock = threading.RLock()
for _g in G.values():
    if _g["status"] == "verifying":  # the verifier died with the server: the idle nudge has the brain report again
        _g["status"] = "running"
GOAL_RULES = """This is an autonomous Goal: the user is away and won't answer questions. Work to the end on your own.
- Git: all work goes on the goal branch named in the [Goal] message (create it from the current branch if it doesn't exist). Sessions may edit, install dependencies, run tests, commit on that branch and push it, only as `git push -u origin <goal branch>`. Never merge into main, deploy, publish, or message or email anyone: say so in every session's brief.
- Plan, then run sessions. Quality is part of done: sessions add or update unit and integration tests, run the linters and the project's quality standards, and write and run Playwright front-end tests for any UI. Answer your sessions' questions yourself.
- When you believe every acceptance criterion is met and all checks pass, call the flows tool goal_report with verdict "done" and end your turn. An independent verifier then checks the work; its failures come back as a [Goal] message: fix them and report again.
- Only if you truly can't continue without the user (a missing credential or access), call goal_report with verdict "blocked" saying exactly what you need, and end your turn. Their reply comes as a [User] message."""
INTAKE = """You prepare an autonomous coding Goal that will then run with no more questions to the user.
Folder: {folder}
Objective: {objective}
Look at the folder briefly (README, package files, test and lint config, git remote) to see what exists. Then output ONLY a JSON object:
{{"questions": [{{"id": "q1", "q": "the question", "hint": "an example, or where to find it"}}], "acceptance": ["criterion"]}}
questions: only what you can't find yourself and the work really needs (design or Figma URL, backend repo or API base URL and docs, credentials and env vars, how to run the app, test and lint commands if unclear, anything ambiguous in the objective). At most 8, short, in the objective's language.
acceptance: 3 to 8 concrete, checkable criteria, including that the tests and lint pass, and the Playwright front-end tests when there is a UI."""
VERIFY = """You are an independent verifier. An agent says the Goal below is done: check it yourself and trust nothing it claims. Don't edit, commit or push anything.
Folder: {folder} (the work is on git branch {branch})
{brief}
The agent's report: {summary}
Run the project's test suites, the linters and the Playwright tests if there are any, and check every acceptance criterion. Then output ONLY a JSON object:
{{"verdict": "pass" or "fail", "summary": "one or two lines", "failing": ["each unmet criterion or failing check, short and specific"]}}"""
# shortcut: a regex over the command, not a sandbox; a determined agent can get around it. Upgrade to a real egress/git-hook guard if goals run untrusted code.
GOAL_DENY = re.compile(r"\bgit\b[^;&|]*\s(checkout|switch|branch\s+-[fDM])\s+(-\S+\s+)*(main|master)\b|\b(gh\s+pr\s+merge|npm\s+publish|yarn\s+publish|pnpm\s+publish|"
                       r"twine\s+upload|docker\s+push|kubectl\s+(apply|delete)|helm\s+(install|upgrade)|terraform\s+(apply|destroy)|vercel|netlify\s+deploy|"
                       r"firebase\s+deploy|fly\s+deploy|wrangler\s+(deploy|publish)|cap\s+deploy|ssh|scp|sftp|sendmail|mailx?)\b|rsync\b[^;&|]*:")


def goal_denies(tool, inp, slug):
    """Why an unattended Goal session may not use this tool with this input, or None."""
    cmd = str(inp.get("command") or "")
    # every push must be exactly `git push [-u] <remote> goal/<slug>` (no refspec onto another branch, no force)
    pushes = re.findall(r"\bgit\b[^;&|]*?\spush\b[^;&|]*", cmd)
    ok = re.compile(r"git\s+push(\s+(-u|--set-upstream))?\s+[\w.-]+\s+(HEAD:)?(refs/heads/)?goal/" + re.escape(slug) + r"\s*")
    if tool == "Bash" and (GOAL_DENY.search(cmd) or not all(ok.fullmatch(x) for x in pushes)):
        return "Not allowed in a Goal: no deploys, publishing, remote shells, merges into main, or pushes other than `git push -u origin <the goal branch>`. Report it in goal_report instead."
    if tool.startswith("mcp__claude_ai_") and tool not in READONLY.split(","):
        return "Not allowed in a Goal: it must not message, email or change anything outside the project."
    return None


def save_g():
    write_atomic(GFILE, json.dumps(G, ensure_ascii=False))
    os.chmod(GFILE, 0o600)  # intake answers may hold credentials


def goal_of(r):
    """The Goal id of r, or of the brain that started r."""
    for x in (r, runs.get(r.get("parent") or "")):
        if x and x.get("goal"):
            return x["goal"]


# shortcut: prefix deny rules; Bash can still write files (tests must be able to), so "read-only" means no edit tools and no
# git writes or deploys. Upgrade to a throwaway worktree for the verifier if it ever changes what it checks.
ONESHOT_DENY = "Edit,Write,NotebookEdit,AskUserQuestion," + ",".join(f"Bash({c}:*)" for c in (
    "git push", "git commit", "git merge", "git rebase", "git reset", "git checkout", "git switch", "git stash", "git tag",
    "gh", "npm publish", "vercel", "netlify", "firebase", "ssh", "scp", "rsync"))


def oneshot(owner, cwd, prompt, model, tools, timeout):
    """A fresh `claude -p` that must answer with a JSON object; it can't edit files."""
    cmd = ["claude", "-p", "--output-format", "json", "--model", model, "--allowedTools", tools, "--disallowedTools", ONESHOT_DENY]
    p = launch(owner, cmd, workdir(owner, cwd))
    try:
        out, _ = p.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
        raise ValueError("timed out")
    try:
        res = json.loads(out.strip().splitlines()[-1])
        return json.loads(re.search(r"\{.*\}", str(res.get("result") or ""), re.S).group(0))
    except (ValueError, IndexError, AttributeError):
        raise ValueError("no JSON in its answer: " + out.strip()[-300:])


def clean_schedule(s):
    """{at: "HH:MM[,…]", days?: [0-6]} like an assistant job, or None."""
    if not s:
        return None
    return {k: v for k, v in clean_job({**s, "prompt": "-"}).items() if k in ("at", "days", "last")}


def goal_get(owner, gid):
    g = G[gid]
    if g.get("owner") != owner:
        raise KeyError(gid)
    return g


def goal_brief(g):
    return ("Objective: " + g["objective"] + "\nContext from the user:\n"
            + ("\n".join(f"- {q['q']}: {g['answers'].get(q['id'], '(no answer)')}" for q in g["questions"]) or "(none)")
            + "\nAcceptance criteria:\n" + "\n".join("- " + a for a in g["acceptance"]))


def goal_create(owner, body):
    name, objective = str(body.get("name") or "").strip()[:60], str(body.get("objective") or "").strip()[:8000]
    folder = str(workdir(owner, body.get("folder")))
    if not name or not objective or not body.get("folder"):
        raise ValueError("A goal needs name, folder and objective")
    if not os.path.isdir(folder):
        raise ValueError(f"No such folder: {folder}")
    g = {"id": uuid.uuid4().hex[:8], "owner": owner, "name": name, "slug": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "goal",
         "folder": folder, "objective": objective, "schedule": clean_schedule(body.get("schedule")), "status": "intake",
         "questions": [], "answers": {}, "acceptance": [], "iteration": 0, "max_iter": 5, "max_hours": 8, "run": None,
         "started": None, "ended": None, "history": [], "report": "", "last": None, "created": time.time()}
    try:
        j = oneshot(owner, folder, INTAKE.format(folder=folder, objective=objective), "haiku", "Read,Glob,Grep", 100)
        g["questions"] = [{"id": str(q.get("id") or f"q{i}"), "q": str(q.get("q") or ""), "hint": str(q.get("hint") or "")}
                          for i, q in enumerate(j.get("questions") or [], 1) if q.get("q")][:8]
        g["acceptance"] = [str(a) for a in j.get("acceptance") or []][:8]
    except (ValueError, OSError, AttributeError, TypeError) as e:  # the user can still answer with what they know and write the criteria
        g["report"] = f"Intake failed ({e}); add the context and acceptance criteria yourself."
    with glock:
        G[g["id"]] = g
        save_g()
    return g


def goal_answers(g, body):
    with glock:
        if g["status"] in ("running", "verifying"):
            raise ValueError("The goal is running: send a message instead")
        g["answers"].update({str(k): str(v)[:4000] for k, v in (body.get("answers") or {}).items()})
        if body.get("acceptance") is not None:
            g["acceptance"] = [str(a) for a in body["acceptance"] if str(a).strip()][:20]
        g["status"] = "ready"
        save_g()
    return g


def goal_start(g):
    with glock:
        if g["status"] in ("intake", "running", "verifying"):
            raise ValueError("Answer the intake questions first" if g["status"] == "intake" else "The goal is already running")
        g.update(status="running", iteration=1, started=time.time(), ended=None, history=[], report="")
        save_g()
    msg = (f"[Goal] {g['name']}\nFolder: {g['folder']}\nBranch: goal/{g['slug']}\n{goal_brief(g)}\n"
           f"Limits: {g['max_iter']} verification rounds or {g['max_hours']} h in total. Start now.")
    start_session({"message": msg, "brain": True, "name": "Goal: " + g["name"], "cwd": g["folder"], "permission_mode": "acceptEdits",
                   "allowed_tools": "Read,Glob,Grep,WebSearch,WebFetch,ToolSearch"}, g.get("owner"), goal=g["id"])
    with glock:
        save_g()
    return g


def goal_kill(g):
    """Stop the goal's brain and its sessions."""
    for r in [r for r in list(runs.values()) if g["run"] and g["run"] in (r["id"], r.get("parent"))]:
        stop_session(r)


def goal_finish(g, status, line):
    """done/failed/blocked: record it and tell the user in 3 short lines (notice -> WhatsApp bridge + Web Push)."""
    with glock:  # the status changes last: whoever sees it can already find the notice and the stopped sessions
        if g["status"] not in ("running", "verifying"):  # e.g. the time limit and the verifier at once, or stopped meanwhile
            return
        h = (time.time() - (g["started"] or time.time())) / 3600
        g["report"] = "\n".join([f"Goal {g['name']}: {status.upper()} · {g['iteration']} iteration{'s' * (g['iteration'] != 1)} · {h:.1f} h",
                                 f"Branch goal/{g['slug']}", line[:300]])
        g["last"] = {"status": status, "ts": time.time(), "report": g["report"]}
        if status != "blocked":
            goal_kill(g)
            g["ended"] = time.time()
        post(g.get("owner"), "notice", g["report"], goal=g["id"])
        g["status"] = status
        save_g()


def goal_reported(gid, rid, a):
    """The goal brain's goal_report. done -> independent verifier in a thread; blocked -> wait for the user."""
    g = G.get(gid)
    if not g or g["run"] != rid or g["status"] != "running":
        raise ValueError("This goal isn't running (stopped, finished or already verifying)")
    summary, failing = str(a.get("summary") or "")[:2000], [str(x)[:300] for x in a.get("failing") or []][:20]
    if a.get("verdict") == "blocked":
        goal_finish(g, "blocked", "Needs: " + summary)
        return "Recorded: the user is notified. End your turn; their answer comes as a [User] message."
    with glock:
        g["status"] = "verifying"
        save_g()
    threading.Thread(target=goal_verify, args=(g, summary), daemon=True).start()
    return "Recorded: an independent verifier is checking now. End your turn; its result comes as a [Goal] message if anything fails."


def goal_verify(g, summary):
    n = g["iteration"]
    try:
        v = oneshot(g.get("owner"), g["folder"], VERIFY.format(folder=g["folder"], branch="goal/" + g["slug"], brief=goal_brief(g), summary=summary),
                    "sonnet", "Read,Glob,Grep,Bash", 3600)
        ok, why, failing = v.get("verdict") == "pass", str(v.get("summary") or "")[:1000], [str(x)[:300] for x in v.get("failing") or []][:20]
    except (ValueError, OSError) as e:
        ok, why, failing = False, "The verifier didn't finish", [f"verifier error: {e}"[:300]]
    with glock:
        if g["status"] != "verifying" or g["iteration"] != n:  # stopped or deleted meanwhile
            return
        g["history"].append({"n": n, "verdict": "pass" if ok else "fail", "summary": why, "failing": failing, "ts": time.time()})
        out = time.time() - g["started"] > g["max_hours"] * 3600
        if not ok and n < g["max_iter"] and not out:
            g["iteration"], g["status"] = n + 1, "running"
        save_g()
    if ok:
        return goal_finish(g, "done", why)
    if g["status"] != "running":
        return goal_finish(g, "failed", "Pending: " + "; ".join(failing[:3]) if failing else why)
    send(runs[g["run"]], f"[Goal] Iteration {n + 1} of {g['max_iter']}. The independent verifier says: {why}\nFailing:\n"
         + "\n".join("- " + x for x in failing) + "\nFix these, re-run the checks, then call goal_report again.")


def goal_message(g, text):
    text = str(text or "").strip()
    if not text:
        raise ValueError("Empty message")
    with glock:
        if g["status"] not in ("blocked", "running", "verifying"):
            raise ValueError("The goal isn't running: start it first")
        if g["status"] == "blocked":
            g["status"] = "running"
        save_g()
    send(runs[g["run"]], "[User] " + text)
    return g


def goal_stop(g):
    with glock:
        if g["status"] in ("running", "verifying", "blocked"):
            g.update(status="stopped", ended=time.time())
            save_g()
    goal_kill(g)
    return g


def goal_tick(now=None):
    """Worker: limits, a nudge for a brain idle with nothing running, and scheduled runs."""
    now = now or time.localtime()
    fire, nudge, over = [], [], []
    with glock:
        for g in G.values():
            r = runs.get(g["run"] or "")
            if g["status"] in ("running", "verifying") and (time.time() - g["started"] > g["max_hours"] * 3600 or g["run"] and not r):
                over.append(g)
            elif g["status"] == "running" and r and r["status"] in ("idle", "stopped") and not r.get("waiting") and time.time() - r["events"][-1]["ts"] > 600 \
                    and not any(x.get("parent") == r["id"] and x["status"] in ("working", "asking") for x in runs.values()):
                nudge.append(r)
            sch = g.get("schedule")
            slot = sch and job_slot(sch, now)
            if slot:
                sch["last"] = slot
                if g["status"] not in ("intake", "running", "verifying", "blocked"):  # recurring: reuse the intake answers
                    fire.append(g)
        if fire:
            save_g()
    for g in over:
        last = (g["history"] or [{}])[-1].get("failing") or []
        goal_finish(g, "failed", f"Out of time ({g['max_hours']} h)." + (" Pending: " + "; ".join(last[:3]) if last else ""))
    for r in nudge:
        threading.Thread(target=send, args=(r, "[Goal] Nothing is running. Continue toward the objective, or call goal_report if it is done or you are blocked."), daemon=True).start()
    for g in fire:
        goal_start(g)


def goal_tool(owner, tool, a):
    """The assistant's goal_* tools (WhatsApp): same as the API."""
    if tool == "goal_list":
        with glock:
            return json.dumps([{k: g[k] for k in ("id", "name", "folder", "status", "iteration", "questions", "schedule", "report")}
                               for g in G.values() if g.get("owner") == owner], ensure_ascii=False)
    g = goal_create(owner, a) if tool == "goal_create" else goal_get(owner, str(a.get("id")))
    if tool == "goal_answer":
        goal_answers(g, a)
    elif tool == "goal_start":
        goal_start(g)
    elif tool == "goal_message":
        goal_message(g, a.get("text"))
    elif tool != "goal_create":
        raise KeyError(tool)
    return json.dumps({k: g[k] for k in ("id", "name", "status", "questions", "acceptance", "report")}, ensure_ascii=False)


# ---------- plan del día (Trello) ----------
# The day starts at 6am: that's when today's plan is drawn up. After that it's re-read every
# minute, so a card that lands on any board shows up (marked "new") without waiting for tomorrow.
# ponytail: polling, Trello webhooks need a public URL; switch if the board count grows a lot.
PLAN_FILE = DATA / "plan.json"
plan = json.loads(PLAN_FILE.read_text()) if PLAN_FILE.exists() else {}
DONE_LIST = re.compile(r"done|hecho|fet\b|terminad|complet", re.I)
DOING_LIST = re.compile(r"doing|in process|en curso|today|hoy", re.I)


def trello(path):
    env = dict(l.split("=", 1) for l in (Path.home() / ".config/flows/trello.env").read_text().split() if "=" in l)
    with urlopen(f"https://api.trello.com/1/{path}{'&' if '?' in path else '?'}key={env['TRELLO_KEY']}&token={env['TRELLO_TOKEN']}", timeout=20) as f:
        return json.load(f)


def plan_tasks(boards, day, since):
    """Open cards that are today's work: overdue, due today, under way (started or in a doing list), or due this week."""
    from datetime import datetime
    local = lambda s: s and datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone()
    out = []
    for b in boards:
        lists = {l["id"]: l["name"] for l in b["lists"]}
        for c in b["cards"]:
            ln = lists.get(c["idList"], "")
            if c["dueComplete"] or DONE_LIST.search(ln):
                continue
            due, start = local(c["due"]), local(c["start"])
            group = ("overdue" if due and due.date() < day else "today" if due and due.date() == day
                     else "doing" if (start and start.date() <= day) or DOING_LIST.search(ln)
                     else "week" if due and (due.date() - day).days <= 7 else None)
            if group:
                out.append({"id": c["id"], "name": c["name"], "board": b["name"], "list": ln, "url": c["shortUrl"], "group": group,
                            "due": due and due.isoformat(), "new": int(c["id"][:8], 16) > since})  # a card's id starts with its creation time
    return sorted(out, key=lambda t: (t["due"] or "9", t["board"]))


def plan_tick():
    from datetime import datetime, timedelta
    day = (datetime.now() - timedelta(hours=6)).date()  # before 6am it's still yesterday's plan
    boards = trello("members/me/boards?filter=open&fields=name&lists=open&list_fields=name")
    for b in boards:
        b["cards"] = trello(f"boards/{b['id']}/cards?filter=open&fields=name,due,start,dueComplete,idList,shortUrl")
    if plan.get("day") != str(day):
        plan.update(day=str(day), planned_at=time.time())
    plan.update(tasks=plan_tasks(boards, day, plan["planned_at"]), checked=time.time(), error="")
    write_atomic(PLAN_FILE, json.dumps(plan))


def plan_worker():
    while True:
        try:
            plan_tick()
        except Exception as e:
            plan["error"] = str(e)
        time.sleep(60)


IDLE_SECS = 60 * int(os.environ.get("FLOWS_IDLE_MIN", "20"))


def reap_idle():
    """Each live session holds ~0.5-1.5 GB (claude + MCP servers + Playwright Chrome); dozens of idle ones froze the PC.
    End the process after IDLE_SECS idle; the session stays idle and the next message resumes it."""
    now = time.time()
    with lock:
        for rid, p in list(procs.items()):
            r = runs.get(rid)
            if r and r["status"] == "idle" and p not in restarting and now - ((r["events"] or [{}])[-1].get("ts") or now) > IDLE_SECS:
                restart(r, p)


def worker():
    while True:
        try:
            good_morning()
            run_jobs()
            goal_tick()
            reap_idle()
            tick()
        except Exception as e:
            print("queue:", e)
        time.sleep(20)


# ---------- phone access ----------
# Trust comes from the socket, never from headers: the 127.0.0.1:PORT listener is the laptop.
# Phone traffic arrives on separate listeners (Wi-Fi IP, and a tunnel-only port) whose handler
# requires a paired-device cookie on every request. Only the laptop can pair, revoke, or toggle.
REMOTE_FILE = DATA / "remote.json"
remote = json.loads(REMOTE_FILE.read_text()) if REMOTE_FILE.exists() else {}
remote.setdefault("devices", {})  # sha256(token) -> {name, created, last}
TUNNEL_PORT = PORT + 2
TAILNET_PORT = PORT + 1  # phone-only listener that `tailscale serve` forwards to
listeners = {}  # "lan" / "tunnel" -> {srv, url, proc?}
pairing = {}    # the single active code: {code, exp, tries}
CODE_TTL, CODE_TRIES, DEVICE_DAYS = 300, 5, 90


def save_remote():
    write_atomic(REMOTE_FILE, json.dumps(remote, indent=1))
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
        t = listeners["tunnel"] = {"srv": srv, "proc": None, "url": None}

        def read():
            # Spawned here, not in the request thread: PDEATHSIG fires when the forking *thread* exits.
            proc = t["proc"] = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{TUNNEL_PORT}"],
                                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, preexec_fn=die_with_parent)
            if listeners.get("tunnel") is not t:  # turned off before we got here
                proc.terminate()
            for line in proc.stdout:
                m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if m and not t["url"]:
                    t["url"] = m.group(0)
            proc.wait()
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
form{padding:18px 20px 22px}label{display:block;font-size:16px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;color:#57534d;margin:12px 0 6px}
input{width:100%;box-sizing:border-box;border:1px solid #cfcac2;border-radius:3px;padding:11px 12px;font:inherit;background:#fff}
#code{font:700 30px/1 ui-monospace,monospace;letter-spacing:.35em;text-align:center}
button{margin-top:18px;width:100%;border:0;border-radius:3px;background:#ff5a1f;color:#0d0d0d;padding:13px;min-height:48px;font:700 17px/1 system-ui;letter-spacing:.08em;text-transform:uppercase}
p{margin:0 0 4px;font-size:16px;color:#57534d}#err{color:#c2410c;min-height:1.4em;margin-top:10px}</style></head><body><main>
<div class="band">Pair with Flows</div><form id="f"><p>On your computer open Flows, go to <b>Phone access</b> and create a pairing code.</p>
<label for="code">Pairing code</label><input id="code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" required>
<label for="name">Name this device</label><input id="name" value="My phone" maxlength="40">
<button>Pair this device</button><div id="err" role="alert"></div></form></main><script>
const f=document.getElementById('f'),c=document.getElementById('code'),m=/code=(\\d{6})/.exec(location.hash);
if(m){c.value=m[1];history.replaceState(null,'',location.pathname);}
f.onsubmit=async e=>{e.preventDefault();const r=await fetch('/api/pair',{method:'POST',headers:{'Content-Type':'application/json','X-Flow':'1'},body:JSON.stringify({code:c.value,name:document.getElementById('name').value})});
const j=await r.json().catch(()=>({}));if(r.ok)location.replace('/');else document.getElementById('err').textContent=j.error||'Could not pair';};
if(m)f.requestSubmit();</script></body></html>"""

# ---------- multi-user logins: hashed session tokens in data/sessions.json ----------
SESS_FILE = DATA / "sessions.json"
logins = json.loads(SESS_FILE.read_text()) if SESS_FILE.exists() else {}  # sha256(token) -> {user, salt, exp}
fails = {}  # user name, or "*" for everyone -> times of recent failed logins
SESSION_DAYS, FAIL_WINDOW = 30, 900


def save_logins():
    write_atomic(SESS_FILE, json.dumps(logins))
    os.chmod(SESS_FILE, 0o600)


def locked(k):
    fails[k] = [t for t in fails.get(k, []) if t > time.time() - FAIL_WINDOW]
    return len(fails[k]) >= (50 if k == "*" else 5)


LOGIN_HTML = PAIR_HTML.split(b"<main>")[0].replace(b"Pair with Flows", b"Sign in to Flows") + b"""<main>
<div class="band">Sign in to Flows</div><form id="f"><label for="u">User</label><input id="u" autocomplete="username" autocapitalize="none" required>
<label for="p">Password</label><input id="p" type="password" autocomplete="current-password" required>
<button>Sign in</button><div id="err" role="alert"></div></form></main><script>
const f=document.getElementById('f');f.onsubmit=async e=>{e.preventDefault();const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json','X-Flow':'1'},body:JSON.stringify({user:f.u.value,password:f.p.value})});
const j=await r.json().catch(()=>({}));if(r.ok)location.reload();else document.getElementById('err').textContent=j.error||'Could not sign in';};</script></body></html>"""


sub_scan = {}  # run id -> (events scanned, {tool_use_id: {id, desc, status}})


def subs_of(r):
    """The lead's subagents and their state, same rules as tasksOf() in index.html. Scans only new events."""
    evs = r.get("events") or []
    n, T = sub_scan.get(r["id"], (0, {}))
    if n > len(evs):
        n, T = 0, {}
    for e in evs[n:]:
        m = e.get("message")
        c = [x for x in (m.get("content") if isinstance(m, dict) else None) or [] if isinstance(x, dict)]
        t = e.get("type")
        if t == "assistant" and not e.get("parent_tool_use_id"):
            for x in c:
                if x.get("type") == "tool_use" and x.get("name") in ("Agent", "Task"):
                    T[x["id"]] = {"id": x["id"], "desc": (x.get("input") or {}).get("description") or "Subagent", "status": "running"}
        elif t == "system" and e.get("subtype") == "task_notification" and e.get("tool_use_id") in T:
            T[e["tool_use_id"]]["status"] = "done" if e.get("status") == "completed" else e.get("status")
        elif t == "user":
            for x in c:
                if x.get("type") == "tool_result" and x.get("tool_use_id") in T and "Async agent launched" not in json.dumps(x.get("content")):
                    T[x["tool_use_id"]]["status"] = "failed" if x.get("is_error") else "done"
    sub_scan[r["id"]] = (len(evs), T)
    return list(T.values())


def slim(ev):
    """Wire copy of an event: drop base64 image data, cap tool_result text (stored event untouched)."""
    ev = {k: v for k, v in ev.items() if k != "tool_use_result"}  # unused by client, duplicates the result (incl. base64)
    m = ev.get("message")
    c = m.get("content") if isinstance(m, dict) else None
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

    def who(self):
        """Multi-user: the signed-in user, or None. A password change or deluser ends their sessions."""
        tok = SimpleCookie(self.headers.get("Cookie", "")).get("flows_session")
        s = tok and logins.get(hashlib.sha256(tok.value.encode()).hexdigest())
        u = s and load_users().get(s["user"])
        return s["user"] if u and s["exp"] > time.time() and u["pw"].split("$")[0] == s["salt"] else None

    def login(self, body):
        name, pw = str(body.get("user") or ""), str(body.get("password") or "")
        if locked(name) or locked("*"):
            return self.send(429, {"error": "Too many failed sign-ins. Try again in 15 minutes."})
        u = load_users().get(name)
        if not check_pw(pw, (u or {}).get("pw") or "x$") or not u:  # hash anyway: no timing hint that a user exists
            for k in (name, "*"):
                fails[k].append(time.time())
            return self.send(403, {"error": "Wrong user or password"})
        tok = secrets.token_urlsafe(32)
        with lock:
            logins.update({k: v for k, v in logins.items() if v["exp"] > time.time()} | {
                hashlib.sha256(tok.encode()).hexdigest(): {"user": name, "salt": u["pw"].split("$")[0], "exp": time.time() + SESSION_DAYS * 86400}})
            save_logins()
        secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" or self.server is listeners.get("tunnel", {}).get("srv") else ""
        return self.send(200, {"ok": True}, headers=[("Set-Cookie", f"flows_session={tok}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_DAYS * 86400}{secure}")])

    def route(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        p = self.path.split("?")[0].strip("/").split("/")
        m = self.command
        u = self.user = None
        if p[:2] == ["api", "assistant"] and self.headers.get("Authorization", "").startswith("Bearer "):
            # the WhatsApp bridge, a local process: laptop listener only
            if self.remote or not hmac.compare_digest(self.headers["Authorization"][7:].strip(), A["token"]):
                return self.send(403, {"error": "forbidden"})
            try:
                return self.assistant(m, p, body, A.get("owner"))
            except KeyError:
                return self.send(404, {"error": "not found"})
            except (ValueError, TypeError) as e:
                return self.send(400, {"error": str(e)})
            except Exception as e:
                return self.send(500, {"error": str(e)})
        tok = self.headers.get("X-Brain")
        if tok is not None or p[:2] == ["api", "brain"]:
            # A Second Brain's MCP server (brain_mcp): its token signs it in as the brain, for its own /api/brain only.
            # Laptop listener only, and the same Host / X-Flow checks as the browser.
            b = runs.get(brains.get(tok or ""))
            if (not b or self.remote or p[:2] != ["api", "brain"] or len(p) != 3 or m != "POST" or self.headers.get("X-Flow") != "1"
                    or self.headers.get("Host", "").split(":")[0] not in ("localhost", "127.0.0.1")):
                return self.send(403, {"error": "forbidden"})
            try:
                return self.send(200, {"text": brain_api(b, p[2], body)})
            except KeyError:
                return self.send(404, {"error": "No such session among yours"})
            except (ValueError, TypeError) as e:
                return self.send(400, {"error": str(e)})
            except Exception as e:
                return self.send(500, {"error": str(e)})
        if MULTI:  # signed-in users on every listener; the phone pairing below is single-user only
            if not self.remote and self.headers.get("Host", "").split(":")[0] not in HOSTS:
                return self.send(403, {"error": "bad host"})
            if m != "GET" and self.headers.get("X-Flow") != "1":
                return self.send(403, {"error": "missing X-Flow header"})
            if m == "POST" and p == ["api", "login"]:
                return self.login(body)
            u = self.user = self.who()
            public = m == "GET" and (p in (["manifest.json"], ["sw.js"]) or (len(p) == 2 and p[0] == "icons"))
            if not u and not public:
                if m == "GET" and p == [""]:
                    return self.send(200, LOGIN_HTML, "text/html; charset=utf-8")
                return self.send(401, {"error": "Sign in first"})
            if m == "POST" and p == ["api", "logout"]:
                tok = SimpleCookie(self.headers.get("Cookie", "")).get("flows_session")
                with lock:
                    logins.pop(hashlib.sha256(tok.value.encode()).hexdigest(), None)
                    save_logins()
                return self.send(200, {"ok": True}, headers=[("Set-Cookie", "flows_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0")])
            if p[:2] == ["api", "remote"] and not load_users()[u].get("admin"):
                return self.send(403, {"error": "Only an admin can manage remote access"})
        elif self.remote:
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
                f = udir(u, "shots", own(Path(p[1]).name, u)["id"]) / Path(p[2]).name  # basename only: no path traversal
                if f.suffix in (".png", ".jpeg", ".jpg") and f.is_file():
                    return self.send(200, f.read_bytes(), "image/png" if f.suffix == ".png" else "image/jpeg")
                return self.send(404, {"error": "no such screenshot"})
            if m == "GET" and len(p) == 3 and p[0] == "uploads":
                base = udir(u, "uploads").resolve()
                f = (base / own(Path(unquote(p[1])).name, u)["id"] / Path(unquote(p[2])).name).resolve()
                if f.parent.parent != base or not f.is_file():
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
            if m == "GET" and p == ["api", "me"]:
                if not u:
                    return self.send(200, {"user": None, "admin": True, "claude_logged_in": True, "package": package(None)})
                home = unix_home(u)
                # the server usually can't look inside a 700 home: then go by what their last run said
                auth = os.path.exists(f"{home}/.claude/.credentials.json") if os.access(home, os.X_OK) else use(u).get("auth", True)
                return self.send(200, {"user": u, "admin": bool(load_users()[u].get("admin")), "claude_logged_in": auth, "package": package(u)})
            if p == ["api", "plan"] and m == "GET":
                if u and not load_users()[u].get("admin"):  # one Trello account: the server owner's
                    return self.send(403, {"error": "Only an admin can see the plan"})
                return self.send(200, plan)
            if p[:2] == ["api", "workflows"]:
                wfs = load_wfs(u)
                if m == "GET" and len(p) == 2:
                    return self.send(200, wfs)
                if m == "PUT" and len(p) == 3:
                    wfs[p[2]] = body
                    save_wfs(wfs, u)
                    return self.send(200, {"ok": True})
                if m == "DELETE" and len(p) == 3:
                    wfs.pop(p[2], None)
                    save_wfs(wfs, u)
                    return self.send(200, {"ok": True})
                if m == "POST" and len(p) == 4 and p[3] == "run":
                    return self.send(200, {"id": start_run(p[2], body.get("input", ""), u)})
            if p[:2] in (["api", "agents"], ["api", "skills"]):
                if package(u) != "dev":
                    return self.send(403, {"error": "Los agentes solo están en el paquete dev"})
                if m == "GET" and p == ["api", "skills"]:
                    return self.send(200, list_skills(u))
                if m == "GET" and p == ["api", "agents"]:
                    return self.send(200, list_agents(u))
                if len(p) == 3:
                    return self.send(200, agent_api(u, m, p[2], body))
            if p == ["api", "wp"] and package(u) == "dev":  # WordPress mode of any folder, before it has a session
                cwd = parse_qs(self.path.partition("?")[2]).get("cwd", ["~"])[0] if m == "GET" else body.get("cwd")
                if m == "PUT":
                    wp_set(u, cwd, body.get("on"))
                return self.send(200, wp_flag(u, cwd))
            if p[:2] == ["api", "projects"]:
                with lock:
                    if m == "GET" and len(p) == 2:
                        return self.send(200, projects(u))
                    j = projects(u, p[2]) if len(p) == 3 else {}[0]  # KeyError: not one of theirs
                if m == "GET":
                    return self.send(200, j)
                if m == "PUT" and "wordpress" in body:
                    wp_set(u, j["path"], body["wordpress"])
                    return self.send(200, {"ok": True})
                if m == "PUT":
                    f = project_file(u, j["path"])
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text(str(body.get("context") or "").strip() + "\n")
                    return self.send(200, {"ok": True})
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
                        if push["subs"].get(ep, {}).get("owner") == u:
                            push["subs"].pop(ep, None)
                    else:
                        push["subs"][ep] = {"sub": body["sub"], "name": str(body.get("name") or "Phone")[:40], "owner": u}
                    write_atomic(PUSH_FILE, json.dumps(push))
                    return self.send(200, {"ok": True})
            if m == "GET" and p == ["api", "usage"]:
                return self.send(200, use(u))
            if p[:2] == ["api", "queue"]:
                if m == "GET" and len(p) == 2:
                    return self.send(200, {"items": [{k: v for k, v in q.items() if k != "files"} for q in queue if q.get("owner") == u],
                                           "limited_until": limited_until(u)})
                if m == "POST" and len(p) == 2:
                    return self.send(200, {"id": enqueue(body, u)})
                if m == "DELETE" and len(p) == 3:
                    with lock:
                        queue[:] = [q for q in queue if q["id"] != p[2] or q.get("owner") != u]
                        save_queue()
                    return self.send(200, {"ok": True})
            if p[:2] == ["api", "runs"]:
                with lock:
                    if m == "GET" and len(p) == 2:
                        skip = ("steps", "workflow", "input", "events", "config")
                        return self.send(200, sorted(
                            ({**{k: v for k, v in r.items() if k not in skip}, **({"subs": subs_of(r)} if r.get("kind") == "session" else {})}
                             for r in runs.values() if r.get("owner") == u),
                            key=lambda r: r["started"], reverse=True))
                    if m == "GET" and len(p) == 3:
                        r = own(p[2], u)
                        if "events" in r:  # sessions grow large: client polls with ?since=<count>
                            since = int(self.path.partition("since=")[2] or 0)
                            return self.send(200, {**r, "events": [slim(e) for e in r["events"][since:]], "total": len(r["events"])})
                        return self.send(200, r)
                    if m == "POST" and len(p) == 4 and p[3] == "cancel":
                        own(p[2], u)
                        if runs[p[2]]["status"] == "waiting":
                            runs[p[2]].update(status="cancelled", ended=time.time())
                            save_run(runs[p[2]])
                        if runs[p[2]]["status"] == "running":
                            runs[p[2]]["status"] = "cancelled"
                            if p[2] in procs:
                                procs[p[2]].terminate()
                        return self.send(200, {"ok": True})
                    if m == "DELETE" and len(p) == 3:
                        delete_run(own(p[2], u)["id"])
                        return self.send(200, {"ok": True})
            if p[:2] == ["api", "assistant"]:
                return self.assistant(m, p, body, u)
            if p[:2] == ["api", "goals"]:
                return self.goals(m, p, body, u)
            if p[:2] == ["api", "sessions"] and m == "POST":
                if len(p) == 2:
                    return self.send(200, {"id": start_session(body, u)})
                r = own(p[2], u)
                if p[3:] == ["message"]:
                    send(r, body.get("text", ""), body.get("agents"), body.get("sub_models"), save_files(r, body.get("files")))
                    return self.send(200, {"ok": True})
                if p[3:] == ["model"]:
                    set_model(r, body.get("model") or "")
                    return self.send(200, {"ok": True})
                if p[3:] == ["config"]:
                    return self.send(200, {"applied": configure(r, body)})
                if p[3:] == ["answer"]:
                    answer(r, body)
                    return self.send(200, {"ok": True})
                if p[3:] == ["pin"]:
                    r["pinned"] = time.time() if body.get("on") else None
                    save_run(r)
                    return self.send(200, {"ok": True})
                if p[3:] == ["rename"]:
                    r["name"] = str(body.get("name") or "").strip()[:60] or r["name"]
                    save_run(r)
                    return self.send(200, {"ok": True})
                if p[3:] == ["stop"]:
                    stop_session(r)
                    return self.send(200, {"ok": True})
            self.send(404, {"error": "not found"})
        except KeyError:
            self.send(404, {"error": "not found"})
        except ValueError as e:  # too-large or malformed upload
            self.send(400, {"error": str(e)})
        except Exception as e:
            self.send(500, {"error": str(e)})

    def assistant(self, m, p, body, u):
        """/api/assistant/*: message, outbox (long-poll), approve, settings. Same for the web UI and the bridge."""
        if package(u) != "dev":
            return self.send(403, {"error": "The assistant is only in the dev package"})
        s = st(u)
        if m == "POST" and p[2:] == ["message"]:
            text, ch = str(body.get("text") or "").strip(), str(body.get("channel") or "web")
            if body.get("audio"):  # voice note (base64): the assistant gets the transcript
                text = "[voz] " + transcribe(base64.b64decode(body["audio"]))
            files = []
            if body.get("files"):
                r = runs.get(s["run"] or "")
                if not r:
                    raise ValueError("Send a text message first so the assistant has a chat to attach files to")
                for f in body["files"][:5]:
                    raw = base64.b64decode(f.get("data") or "")
                    if not wa_ok(str(f.get("name")), raw):
                        raise ValueError(f"{Path(str(f.get('name'))).name}: file type or size not accepted")
                files = save_files(r, body["files"][:5])
                text = text or "(sin texto)"
            if not text:
                raise ValueError("Empty message")
            auto = re.fullmatch(r"/auto\s+(on|off)", text, re.I)
            if auto:
                with acond:
                    s["auto"] = auto[1].lower() == "on"
                    save_a()
                post(u, "notice", "Full auto: I act without asking." if s["auto"] else "Confirm mode: I ask before sending, deleting or publishing.")
            else:
                msg = text if ch == "web" else f"[{ch}{' ' + str(body['from']) if body.get('from') else ''}] {text}"
                if files:
                    send(runs[s["run"]], msg, files=files)
                else:
                    assistant_send(u, msg)
            return self.send(200, {"ok": True, **({"text": text} if body.get("audio") else {})})
        if m == "GET" and p[2:] == ["outbox"]:
            q = parse_qs(self.path.partition("?")[2])
            since = int(q.get("since", ["0"])[0])
            with acond:
                acond.wait_for(lambda: s["outbox"] and s["outbox"][-1]["id"] > since, min(60.0, float(q.get("wait", ["25"])[0])))
                out = [x for x in s["outbox"] if x["id"] > since]
            return self.send(200, out)
        if m == "POST" and p[2:] == ["approve"]:
            aid = str(body.get("approval_id") or "")
            with lock:
                r = next((x for x in runs.values() if aid in (x.get("pending") or {}) and x.get("owner") == u and assistant_of(x)), None)
            if not r:
                raise ValueError("No such pending approval (already answered?)")
            answer(r, {"id": aid, "allow": bool(body.get("allow")), "message": body.get("message")})
            return self.send(200, {"ok": True})
        if p[2:] == ["settings"]:
            if m == "POST" and "jobs" in body:
                set_jobs(u, body["jobs"])
            if m == "POST" and "auto" in body:
                with acond:
                    s["auto"] = bool(body["auto"])
                    save_a()
            return self.send(200, {"auto": s["auto"], "jobs": s["jobs"], "run": s["run"]})
        raise KeyError(p)

    def goals(self, m, p, body, u):
        """/api/goals[/<id>[/answers|start|stop|message|schedule]]"""
        if package(u) != "dev":
            return self.send(403, {"error": "Goals are only in the dev package"})
        if len(p) == 2:
            if m == "POST":
                return self.send(200, goal_create(u, body))
            with glock:
                return self.send(200, sorted((g for g in G.values() if g.get("owner") == u), key=lambda g: g["created"], reverse=True))
        g = goal_get(u, p[2])
        if m == "GET" and len(p) == 3:
            return self.send(200, g)
        if m == "DELETE" and len(p) == 3:
            goal_stop(g)
            with glock:
                G.pop(g["id"], None)
                save_g()
            return self.send(200, {"ok": True})
        act = {"answers": lambda: goal_answers(g, body), "start": lambda: goal_start(g), "stop": lambda: goal_stop(g),
               "message": lambda: goal_message(g, body.get("text"))}
        if m == "POST" and p[3:] == ["schedule"]:
            with glock:
                g["schedule"] = clean_schedule(body.get("schedule"))
                save_g()
            return self.send(200, g)
        if m == "POST" and len(p) == 4 and p[3] in act:
            return self.send(200, act[p[3]]())
        raise KeyError(p)

    do_GET = do_POST = do_PUT = do_DELETE = route


class RH(H):
    remote = True


def admin_cli(cmd, name, *rest):
    """python3 server.py adduser <name> <unix_user> [--admin] [--package admin] | passwd <name> | deluser <name>"""
    import getpass
    us = load_users()
    if cmd == "deluser":
        us.pop(name)
    else:
        if cmd == "adduser":
            if not re.fullmatch(r"[a-z0-9_-]{1,32}", name) or name in us:
                raise SystemExit("name: 1-32 of a-z 0-9 _ - and not taken")
            pwd.getpwnam(rest[0])  # the Linux user must exist
            us[name] = {"unix": rest[0], "admin": "--admin" in rest}
            if "--package" in rest:
                us[name]["package"] = rest[rest.index("--package") + 1]
                if us[name]["package"] not in PACKAGES:
                    raise SystemExit(f"package: one of {', '.join(PACKAGES)}")
        pw = getpass.getpass(f"Password for {name}: ")
        if len(pw) < 10 or pw != getpass.getpass("Again: "):
            raise SystemExit("Passwords must match and be at least 10 characters")
        us[name]["pw"] = hash_pw(pw)  # a new salt also ends their open sessions
    write_atomic(USERS_FILE, json.dumps(us, indent=1))
    os.chmod(USERS_FILE, 0o600)
    print("Saved. Restart Flows if this created data/users.json (turns on multi-user mode).")


if __name__ == "__main__":
    if sys.argv[1:2] and sys.argv[1] in ("adduser", "passwd", "deluser"):
        try:
            admin_cli(*sys.argv[1:])
        except (TypeError, IndexError, KeyError) as e:
            raise SystemExit(f"{admin_cli.__doc__}\n({e!r})")
        raise SystemExit
    if MULTI:  # the owners' agents must reach data/users/<name>/ but list nothing on the way
        for d in (DATA, DATA / "users"):
            d.mkdir(exist_ok=True)
            os.chmod(d, 0o711)
        for f in DATA.iterdir():  # everything else (runs, keys, sessions): server user only
            if f.name != "users":
                os.chmod(f, f.stat().st_mode & 0o700)
    print(f"Flows on http://localhost:{PORT}" + (f" ({len(load_users())} users, sign-in required)" if MULTI else ""))
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
    if (Path.home() / ".config/flows/trello.env").exists():
        threading.Thread(target=plan_worker, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
