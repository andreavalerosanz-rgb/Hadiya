"""Windows launcher: start the Hadiya server if it isn't running, then open it in an Edge app window.
`--server` only starts the server (Startup folder, at login)."""
import os, socket, subprocess, sys, time, webbrowser
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("PORT", 8787))
URL = f"http://localhost:{PORT}/"


def up():
    try:
        socket.create_connection(("127.0.0.1", PORT), 0.5).close()
        return True
    except OSError:
        return False


if not up():
    (APP / "data").mkdir(exist_ok=True)
    log = open(APP / "data" / "server.log", "ab")
    subprocess.Popen([sys.executable, "-X", "utf8", str(APP / "server.py")], cwd=APP, stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, env={**os.environ, "PYTHONUTF8": "1"},
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)  # CREATE_NO_WINDOW would be ignored with DETACHED_PROCESS
    for _ in range(60):
        if up():
            break
        time.sleep(0.25)

if "--server" not in sys.argv:
    edge = [p for p in (os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")) if os.path.exists(p)]
    if edge:
        subprocess.Popen([edge[0], f"--app={URL}"])
    else:
        webbrowser.open(URL)
