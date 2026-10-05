#!/usr/bin/env python3
"""Flows Link: let the agents of your Flows server work on folders of this device, live.

  python3 flows_link.py pair https://flows.example.com ABCD-EFGH [--name portatil]
  python3 flows_link.py share ~/proyectos/web [--name web] [--read-only] [--allow-exec]
  python3 flows_link.py unshare web
  python3 flows_link.py folders
  python3 flows_link.py run

Python 3.9+, standard library only, Linux / macOS / Windows. It opens no port: it keeps one outbound
HTTPS long-poll to the server, runs each file operation itself, confined to the folders you shared (every
path is checked again here, whatever the server sends), and posts the result back.
Config: $FLOWS_LINK_CONFIG, else <your config dir>/flows-link/config.json (mode 0600: it holds the device token).
"""
import base64, ipaddress, json, os, re, shutil, socket, subprocess, sys, threading, time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

VERSION = "1"
SKIP = {".git", "node_modules", ".flows-trash", "__pycache__", ".svn", ".hg"}  # never walked by list/glob/grep
TRASH = ".flows-trash"
MAX_TEXT, MAX_FILE, MAX_BIN, MAX_OUT = 256 << 10, 10 << 20, 20 << 20, 100 << 10
TAILNET = (ipaddress.ip_network("100.64.0.0/10"), ipaddress.ip_network("fd7a:115c:a1e0::/48"))


# ---------- config ----------
def cfg_path():
    if os.environ.get("FLOWS_LINK_CONFIG"):
        return Path(os.environ["FLOWS_LINK_CONFIG"]).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "flows-link" / "config.json"


def load():
    f = cfg_path()
    c = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    c.setdefault("folders", [])
    return c


def save(c):
    f = cfg_path()
    f.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = f.with_name(f.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # never readable by others, not even for a moment
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(c, fh, indent=1)
    os.replace(tmp, f)
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def check_url(url):
    """https anywhere; plain http only to this machine or a Tailscale address (WireGuard-encrypted)."""
    u = urlsplit(url)
    if u.scheme == "https" and u.hostname:
        return
    if u.scheme != "http" or not u.hostname:
        raise SystemExit(f"Dirección no válida: {url} (usa https://…)")
    try:
        ips = {ipaddress.ip_address(a[4][0].split("%")[0]) for a in socket.getaddrinfo(u.hostname, u.port or 80)}
    except (OSError, ValueError) as e:
        raise SystemExit(f"No encuentro {u.hostname}: {e}")
    if not ips or not all(ip.is_loopback or any(ip in n for n in TAILNET) for ip in ips):
        raise SystemExit("Por seguridad, http:// solo vale para localhost o una IP de Tailscale (100.64.0.0/10). Usa https://.")


class NoRedirect(HTTPRedirectHandler):  # a redirect could carry the token somewhere else (or to http)
    def redirect_request(self, *a):
        raise URLError("the server answered with a redirect; use its final https:// address")


OPENER = build_opener(NoRedirect)


def post(c, path, body, timeout=40, auth=True):
    hd = {"Content-Type": "application/json", "X-Flow": "1", "User-Agent": "flows-link/" + VERSION}
    if auth:
        hd["Authorization"] = "Bearer " + c["token"]
    req = Request(c["server"] + path, data=json.dumps(body).encode(), method="POST", headers=hd)
    with OPENER.open(req, timeout=timeout) as f:
        return json.loads(f.read() or b"{}")


# ---------- confinement: the only way any op reaches the disk ----------
class Refused(Exception):
    pass


def folder(c, name):
    for f in c["folders"]:
        if f["name"] == name:
            return f
    raise Refused(f"folder '{name}' is not shared on this device")


def inside(f, rel, link=False):
    """(root, resolved path) or Refused. Relative paths only; after resolving every symlink the result must
    still be the root or under it. link: resolve only the parent, so move/delete act on a symlink itself."""
    rel = str(rel or "").replace("\\", "/").rstrip("/")
    if rel.startswith("/") or re.match(r"^[A-Za-z]:", rel) or "\x00" in rel:
        raise Refused("absolute paths are not allowed: give a path relative to the shared folder")
    root = Path(f["path"]).resolve()
    head, _, name = rel.rpartition("/")
    if link and name not in ("", ".", ".."):
        p = (root / head).resolve() / name
        par = p.parent
    else:
        p = par = (root / rel).resolve()
    if par != root and root not in par.parents:
        raise Refused("that path is outside the shared folder (.. or a symlink pointing out)")
    return root, p


def relp(root, p):
    return p.relative_to(root).as_posix() if p != root else "."


def writable(f):
    if f.get("read_only"):
        raise Refused(f"folder '{f['name']}' is shared read-only")


def walk(root, base):
    """Files and dirs under base (no symlinked dirs, no SKIP dirs, no symlinks pointing out)."""
    for d, dirs, files in os.walk(base, followlinks=False):
        dirs[:] = sorted(x for x in dirs if x not in SKIP and not os.path.islink(os.path.join(d, x)))
        for x in dirs:
            yield Path(d, x), True
        for x in sorted(files):
            if not escapes(root, Path(d, x)):
                yield Path(d, x), False


def escapes(root, p):
    """A symlink whose target is outside the root (never listed, read or followed)."""
    if not p.is_symlink():
        return False
    t = p.resolve()
    return t != root and root not in t.parents


def glob_re(pat):
    out, i = "", 0
    while i < len(pat):
        if pat.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pat.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pat[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pat[i] == "?":
            out, i = out + "[^/]", i + 1
        elif pat[i] == "{" and "}" in pat[i:]:
            j = pat.index("}", i)
            out, i = out + "(?:" + "|".join(re.escape(a) for a in pat[i + 1:j].split(",")) + ")", j + 1
        else:
            out, i = out + re.escape(pat[i]), i + 1
    return re.compile(out + r"\Z")


def matcher(pat):
    """A pattern without / matches file names at any depth; with /, the path relative to the search base."""
    rx = glob_re(pat)
    return (lambda rel: bool(rx.match(rel))) if "/" in pat else (lambda rel: bool(rx.match(rel.rsplit("/", 1)[-1])))


def is_binary(raw):
    return b"\x00" in raw[:8192]


# ---------- the operations ----------
def op_list(c, f, a):
    root, p = inside(f, a.get("path"))
    if not p.is_dir():
        raise Refused("not a folder")
    lim, out = max(1, min(int(a.get("limit") or 500), 5000)), []
    it = walk(root, p) if a.get("recursive") else ((x, x.is_dir()) for x in sorted(p.iterdir()) if x.name not in SKIP and not escapes(root, x))
    for x, isd in it:
        if len(out) >= lim:
            return {"entries": out, "truncated": True}
        try:
            st = x.stat()
        except OSError:
            continue
        out.append({"path": relp(root, x) if a.get("recursive") else x.name, "dir": isd, "size": 0 if isd else st.st_size, "mtime": int(st.st_mtime)})
    return {"entries": out, "truncated": False}


def op_stat(c, f, a):
    root, p = inside(f, a.get("path"))
    if not p.exists():
        return {"exists": False}
    st = p.stat()
    return {"exists": True, "dir": p.is_dir(), "size": st.st_size, "mtime": int(st.st_mtime)}


def op_read(c, f, a):
    root, p = inside(f, a.get("path"))
    if not p.is_file():
        raise Refused("no such file")
    size = p.stat().st_size
    if a.get("binary"):
        if size > MAX_BIN:
            raise Refused(f"file is {size} bytes; the limit is {MAX_BIN}")
        return {"binary": True, "size": size, "data": base64.b64encode(p.read_bytes()).decode()}
    if size > MAX_FILE:
        raise Refused(f"file is {size} bytes; too big to read as text (limit {MAX_FILE}); use device_grep or device_pull")
    raw = p.read_bytes()
    if is_binary(raw):
        return {"binary": True, "size": size}
    lines = raw.decode("utf-8", "replace").splitlines()
    start = max(1, int(a.get("offset") or 1))
    lim = max(1, min(int(a.get("limit") or 2000), 20000))
    sel, n, cut = [], 0, False
    for ln in lines[start - 1:start - 1 + lim]:
        n += len(ln) + 1
        if n > MAX_TEXT:
            cut = True
            break
        sel.append(ln)
    return {"binary": False, "size": size, "start": start, "lines": sel, "total_lines": len(lines),
            "truncated": cut or start - 1 + len(sel) < len(lines)}


def op_write(c, f, a):
    writable(f)
    root, p = inside(f, a.get("path"))
    if p == root or p.is_dir():
        raise Refused("that is a folder")
    raw = base64.b64decode(a["data"]) if a.get("data") is not None else str(a.get("content") or "").encode("utf-8")
    new = not p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(raw)
    return {"bytes": len(raw), "created": new}


def op_edit(c, f, a):
    writable(f)
    root, p = inside(f, a.get("path"))
    if not p.is_file():
        raise Refused("no such file")
    old, new = str(a.get("old_string") or ""), str(a.get("new_string") or "")
    if not old or old == new:
        raise Refused("old_string must be non-empty and differ from new_string")
    with open(p, encoding="utf-8", newline="") as fh:  # newline="": keep CRLF files as they are
        text = fh.read()
    n = text.count(old)
    if not n:
        raise Refused("old_string not found in the file (it must match exactly, whitespace included)")
    if n > 1 and not a.get("replace_all"):
        raise Refused(f"old_string appears {n} times: add surrounding context to make it unique, or set replace_all")
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text.replace(old, new) if a.get("replace_all") else text.replace(old, new, 1))
    return {"replaced": n if a.get("replace_all") else 1}


def op_mkdir(c, f, a):
    writable(f)
    root, p = inside(f, a.get("path"))
    p.mkdir(parents=True, exist_ok=True)
    return {"ok": True}


def op_move(c, f, a):
    writable(f)
    root, src = inside(f, a.get("path"), link=True)
    _, dst = inside(f, a.get("to"), link=True)
    if src == root or not src.exists() and not src.is_symlink():
        raise Refused("no such file or folder")
    if dst.exists():
        raise Refused("the destination already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))
    return {"to": relp(root, dst)}


def op_delete(c, f, a):
    """Never really deleted: moved into <folder>/.flows-trash/ (empty it yourself)."""
    writable(f)
    root, p = inside(f, a.get("path"), link=True)
    if p == root or p == root / TRASH:
        raise Refused("refusing to delete the shared folder itself")
    if not p.exists() and not p.is_symlink():
        raise Refused("no such file or folder")
    t = root / TRASH / (time.strftime("%Y%m%d-%H%M%S-") + p.name)
    t.parent.mkdir(exist_ok=True)
    shutil.move(str(p), str(t))
    return {"trash": relp(root, t)}


def op_glob(c, f, a):
    root, base = inside(f, a.get("path"))
    m, out, lim = matcher(str(a.get("pattern") or "*")), [], max(1, min(int(a.get("limit") or 1000), 5000))
    for x, isd in walk(root, base):
        if not isd and m(x.relative_to(base).as_posix()):
            out.append(relp(root, x))
            if len(out) >= lim:
                return {"files": out, "truncated": True}
    return {"files": out, "truncated": False}


def op_grep(c, f, a):
    root, base = inside(f, a.get("path"))
    try:
        rx = re.compile(str(a.get("pattern") or ""), re.I if a.get("ignore_case") else 0)
    except re.error as e:
        raise Refused(f"bad regular expression: {e}")
    m = matcher(str(a["glob"])) if a.get("glob") else None
    lim, only = max(1, min(int(a.get("limit") or 200), 2000)), bool(a.get("files_only"))
    out, files, seen = [], 0, set()
    cands = [(base, False)] if base.is_file() else walk(root, base)
    for x, isd in cands:
        if isd or (m and not m(x.relative_to(base).as_posix() if x != base else x.name)):
            continue
        files += 1
        if files > 20000:
            return {"matches": out, "truncated": True}
        try:
            if x.stat().st_size > 2 << 20:
                continue
            raw = x.read_bytes()
        except OSError:
            continue
        if is_binary(raw):
            continue
        for i, ln in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
            if rx.search(ln):
                r = relp(root, x)
                if only:
                    if r not in seen:
                        seen.add(r)
                        out.append(r)
                    break
                out.append(f"{r}:{i}:{ln[:300]}")
                if len(out) >= lim:
                    return {"matches": out, "truncated": True}
    return {"matches": out, "truncated": False}


def op_exec(c, f, a):
    if not f.get("exec"):
        raise Refused(f"commands are off for folder '{f['name']}' (share it with --allow-exec to turn them on)")
    root, d = inside(f, a.get("path"))
    if not d.is_dir():
        raise Refused("not a folder")
    to = max(1, min(int(a.get("timeout") or 60), 300))
    try:
        r = subprocess.run(str(a.get("command") or ""), shell=True, cwd=str(d), capture_output=True, timeout=to, stdin=subprocess.DEVNULL)
        code, so, se = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        code, so, se = None, e.stdout or b"", (e.stderr or b"") + f"\n(timed out after {to} s)".encode()
    cut = lambda b: b.decode("utf-8", "replace")[-MAX_OUT:]
    return {"code": code, "stdout": cut(so), "stderr": cut(se)}


OPS = {"list": op_list, "stat": op_stat, "read": op_read, "write": op_write, "edit": op_edit, "mkdir": op_mkdir,
       "move": op_move, "delete": op_delete, "glob": op_glob, "grep": op_grep, "exec": op_exec}


def do(c, op):
    fn = OPS.get(op.get("op"))
    if not fn:
        raise Refused(f"unknown operation {op.get('op')!r}")
    return fn(c, folder(c, op.get("folder")), op.get("args") or {})


# ---------- commands ----------
def say(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def describe(f):
    return f"{f['name']} → {f['path']} (" + ("solo lectura" if f.get("read_only") else "lectura y escritura") + (", COMANDOS PERMITIDOS" if f.get("exec") else "") + ")"


EXEC_WARN = ("AVISO: en «{}» los agentes del servidor pueden ejecutar CUALQUIER comando con tu usuario de este equipo "
             "(el directorio de trabajo está en la carpeta, pero un comando puede leer o cambiar todo lo que tú puedas). "
             "Actívalo solo si confías en todo lo que corre en ese servidor.")


def cmd_pair(url, code, name=None):
    url = url.rstrip("/")
    check_url(url)
    c = load()
    try:
        r = post({"server": url}, "/api/link/pair", {"code": code, "name": name or socket.gethostname(), "platform": sys.platform}, auth=False)
    except HTTPError as e:
        raise SystemExit("No se pudo vincular: " + (json.loads(e.read() or b"{}").get("error") or str(e)))
    except (URLError, OSError) as e:
        raise SystemExit(f"No se puede conectar con {url}: {e}")
    c.update(server=url, token=r["token"], id=r["id"], name=r["name"])
    save(c)
    print(f"Vinculado como «{r['name']}». Comparte una carpeta con:  python3 {Path(sys.argv[0]).name} share <carpeta>\n"
          f"y luego:  python3 {Path(sys.argv[0]).name} run\n(Configuración en {cfg_path()})")


def cmd_share(path, name=None, read_only=False, allow_exec=False):
    if read_only and allow_exec:
        raise SystemExit("--allow-exec no tiene sentido con --read-only: un comando puede escribir igualmente")
    p = Path(path).expanduser().resolve()
    if not p.is_dir():
        raise SystemExit(f"No es una carpeta: {p}")
    if p == Path(p.anchor):
        raise SystemExit("No se puede compartir la raíz del disco")
    name = name or re.sub(r"[^A-Za-z0-9._-]", "-", p.name)[:40] or "carpeta"
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,40}", name):
        raise SystemExit("Nombre no válido: letras, cifras, . _ - (máx. 40)")
    c = load()
    c["folders"] = [f for f in c["folders"] if f["name"] != name]
    c["folders"].append({"name": name, "path": str(p), "read_only": bool(read_only), "exec": bool(allow_exec)})
    save(c)
    print("Compartida:", describe(c["folders"][-1]))
    if p == Path.home():
        print("Ojo: has compartido toda tu carpeta personal.")
    if allow_exec:
        print(EXEC_WARN.format(name))
    print("Si `run` ya está en marcha, lo verá en unos segundos.")


def cmd_unshare(name):
    c = load()
    n = len(c["folders"])
    c["folders"] = [f for f in c["folders"] if f["name"] != name]
    save(c)
    print("Dejada de compartir." if len(c["folders"]) < n else f"No había ninguna carpeta «{name}».")


def cmd_folders():
    c = load()
    print(f"Servidor: {c.get('server') or '(sin vincular)'}  ·  dispositivo: {c.get('name') or '-'}")
    for f in c["folders"]:
        print(" ", describe(f))
    if not c["folders"]:
        print("  (ninguna carpeta compartida)")


def handle(c, op, slots):
    a = op.get("args") or {}
    say(f"{op.get('op')} {op.get('folder')}/{a.get('path') or ''}".rstrip("/") + (f" → {a.get('to')}" if a.get("to") else "")
        + (f"  $ {a.get('command')}" if op.get("op") == "exec" else ""))
    try:
        body = {"id": op.get("id"), "ok": True, "result": do(c, op)}
    except Refused as e:
        body = {"id": op.get("id"), "ok": False, "error": str(e)}
        say("  rechazado:", e)
    except Exception as e:
        body = {"id": op.get("id"), "ok": False, "error": f"{type(e).__name__}: {e}"}
    try:
        for n in range(3):
            try:
                post(c, "/api/link/reply", body, timeout=60)
                break
            except (URLError, OSError):
                time.sleep(1 + n)
    finally:
        slots.release()


def cmd_run():
    c = load()
    if not c.get("token"):
        raise SystemExit(f"Este equipo no está vinculado: python3 {Path(sys.argv[0]).name} pair <url> <código>")
    check_url(c["server"])
    for f in c["folders"]:
        if f.get("exec"):
            print(EXEC_WARN.format(f["name"]))
    if not c["folders"]:
        print("Aviso: no compartes ninguna carpeta todavía (usa `share`).")
    slots, wait, up = threading.Semaphore(8), 1, None
    say(f"Conectando a {c['server']}…")
    while True:
        try:
            c = {**load(), "server": c["server"]}  # picks up `share` / `unshare` while running; never a new server
            r = post(c, "/api/link/poll", {"folders": [{k: f[k] for k in ("name", "path", "read_only", "exec")} for f in c["folders"]],
                                            "version": VERSION, "platform": sys.platform}, timeout=60)
            if up is not True:
                say(f"● Conectado a {c['server']} como «{c.get('name')}» · " + (", ".join(describe(f) for f in c["folders"]) or "sin carpetas"))
                up = True
            wait = 1
            for op in r.get("ops") or []:
                slots.acquire()
                threading.Thread(target=handle, args=(c, op, slots), daemon=True).start()
        except HTTPError as e:
            if e.code == 401:
                raise SystemExit("El servidor ha revocado este dispositivo. Vincúlalo de nuevo con `pair`.")
            if up is not False:
                say(f"○ El servidor respondió {e.code}; reintento…")
                up = False
            time.sleep(wait)
            wait = min(wait * 2, 60)
        except (URLError, OSError, ValueError) as e:
            if up is not False:
                say(f"○ Sin conexión ({getattr(e, 'reason', e)}); reintento con espera creciente…")
                up = False
            time.sleep(wait)
            wait = min(wait * 2, 60)


def main(argv):
    args, flags, opts = [], set(), {}
    it = iter(argv)
    for x in it:
        if x in ("--read-only", "--allow-exec"):
            flags.add(x)
        elif x == "--name":
            opts["name"] = next(it, None)
        elif x.startswith("--name="):
            opts["name"] = x[7:]
        else:
            args.append(x)
    cmd, rest = (args[0] if args else ""), args[1:]
    if cmd == "pair" and len(rest) == 2:
        return cmd_pair(rest[0], rest[1], opts.get("name"))
    if cmd == "share" and len(rest) == 1:
        return cmd_share(rest[0], opts.get("name"), "--read-only" in flags, "--allow-exec" in flags)
    if cmd == "unshare" and len(rest) == 1:
        return cmd_unshare(rest[0])
    if cmd in ("folders", "list") and not rest:
        return cmd_folders()
    if cmd == "run" and not rest:
        try:
            return cmd_run()
        except KeyboardInterrupt:
            print("\nDesconectado.")
            return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
