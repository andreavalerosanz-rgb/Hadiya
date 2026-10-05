# Deploy: one shared Flows server for several people

Multi-user mode turns on when `data/users.json` exists. Without that file, Flows works the way it always has: one user, no sign-in.
In multi-user mode, each person gets their own sign-in, workflows, runs, queue, plan usage and push. Every `claude` process runs as that person's own Linux user, through `sudo`.

## 1. Server prerequisites
- Linux, `python3` (3.9+), `sudo` 1.9.3 or later (needed for `-D` / `CWD=*`). Check with `sudo -V`.
- Node plus the Claude CLI, installed **system-wide** so every user can run it: `sudo npm install -g @anthropic-ai/claude-code`. Then `which claude` should print `/usr/local/bin/claude`, which must be on sudo's `secure_path`. Per-user installs in `~/.local/bin` won't work.
- Optional: `npx` on the system PATH, if people use the browser (Playwright) steps.

## 2. Users
```sh
sudo adduser --system --group --home /opt/flows flows    # the server's own user
sudo -u flows git clone <repo> /opt/flows/app            # /opt/flows/app must stay world-traversable (755)
sudo adduser alice && sudo chmod 700 /home/alice          # one Linux user per person
sudo usermod -aG alice flows                              # server joins alice's private group: shares data/users/alice/ only
```
Why the group: uploads and screenshots live in `data/users/<name>/{uploads,shots}/<run>`. Flows makes those folders `flows:<their group>`, mode `2770` (setgid). Their agent can then read attachments and write screenshots, and nobody else can. At startup Flows sets `data/` and `data/users/` to `711`, and everything else in `data/` to owner-only. After you add a group membership, restart the service.

## 3. sudoers (`sudo visudo -f /etc/sudoers.d/flows`)
```
Runas_Alias FLOWS_USERS = alice, bob
flows ALL=(FLOWS_USERS) CWD=* NOPASSWD:SETENV: /usr/local/bin/claude
```
This allows the `claude` binary only, and only as the listed users. `CWD=*` lets Flows start the agent in the project folder (`sudo -D`), and `SETENV` passes `CLAUDE_CODE_ENABLE_ASK_USER_QUESTION_TOOL=true`. To check it: `sudo -u flows sudo -n -u alice -H -D /home/alice -- /usr/local/bin/claude --version`.
Don't set `Defaults requiretty` for `flows`.

## 4. Each person signs in to Claude once
Over SSH, as themselves: `ssh alice@server`, then `claude login` (or `claude` and `/login`). Their credentials stay in their own `~/.claude`. If a run ever reports it isn't logged in, Flows shows a banner asking them to do this.

## 5. Flows accounts
Run these as the server user, so the files stay owned by `flows`:
```sh
cd /opt/flows/app
sudo -u flows python3 server.py adduser alice alice --admin   # <flows name> <linux user> [--admin]
sudo -u flows python3 server.py adduser bob bob
sudo -u flows python3 server.py passwd bob                    # also signs bob out everywhere
sudo -u flows python3 server.py deluser bob
```
Restart the service after the first `adduser`, because that switches on multi-user mode. Admins also get the remote-access panel.
Project folders must be inside the person's home (`~` means their home).

## 6. Run it (systemd), bound to 127.0.0.1
`/etc/systemd/system/flows.service`:
```ini
[Service]
User=flows
WorkingDirectory=/opt/flows/app
Environment=FLOWS_HOSTS=flows.example.com
ExecStart=/usr/bin/python3 server.py
Restart=on-failure
[Install]
WantedBy=multi-user.target
```
`sudo systemctl enable --now flows`. `FLOWS_HOSTS` is the public hostname or hostnames (comma-separated) that the proxy forwards. Without it, the Host check refuses the request.

## 7. HTTPS in front: never serve the sign-in over plain http on the internet
Only ever expose Flows through TLS. Pick one:
- **Caddy**: `caddy reverse-proxy --from flows.example.com --to 127.0.0.1:8787`. It gets the certificate and sends `X-Forwarded-Proto: https`, so the session cookie is marked `Secure`.
- **Cloudflare named tunnel**: `cloudflared tunnel create flows`, then route `flows.example.com` to `http://127.0.0.1:8787`, then `cloudflared tunnel run flows`.

Don't open port 8787 in the firewall. Sign-ins are rate-limited (5 failures per name and 50 overall per 15 minutes), and sessions last 30 days.

## Packages (`dev`, `admin`)
A package decides what someone's agents can reach. The server enforces it on every `claude` it starts, whatever the UI sent.
- `dev` (default): everything, as before.
- `admin`: Google Workspace only (Drive, Gmail, Calendar connectors). There are no file, shell, browser or other MCP tools, and Full auto is turned off.

Per person: `sudo -u flows python3 server.py adduser carla carla --package admin`. Per install: `FLOWS_PACKAGE=admin`. Check it with `python3 scripts/test_packages.py`.

## Install on any Linux PC (.deb)
`scripts/build-deb.sh dev` or `scripts/build-deb.sh admin` builds `dist/flows-<pkg>_<ver>_all.deb`. Then:
- `sudo apt install ./dist/flows-admin_*.deb` puts the app in `/opt/flows`, adds a systemd user service, and adds an app-menu launcher that opens a Chrome app window.
- `systemctl --user start flows` (it starts by itself at every later login), then `claude login`. Data goes in `~/.local/share/flows`.

Phone, or any PC without the .deb: open Flows through Phone access (LAN, Tailscale or tunnel) or a server set up as above, and choose "Install app" or "Add to Home Screen". Flows is already a PWA.
Versions come from git tags: `git tag v1.0 && scripts/build-deb.sh`.

## Local model (a second provider, for when Claude runs out of tokens)

The local model is turned off for now; set `FLOWS_LOCAL_MODEL=1` in the service environment to turn it back on.

Flows can start `claude` against a local Anthropic-compatible endpoint instead of your Claude subscription.
Pick **Claude / Modelo local** on the home screen; new sessions and runs use the choice, a running session keeps its own.
When Claude hits its usage limit, the session shows **Continuar con el modelo local**, which switches and resumes it.

1. Install Ollama (https://ollama.com) and start it (it listens on `http://127.0.0.1:11434`).
2. Pull the model you want: `ollama pull <tag>`. Look up the Kimi tag in the Ollama library; Flows has no default and does not guess one.
3. In Flows, home → *Ajustes del modelo local*: set the server address (default above) and the model tag, then *Guardar y comprobar*.
   The dot turns green when the server answers and has that tag. Settings are stored in `data/provider.json`.

Caveats:
- Full Kimi K2/K3 is a ~1T-parameter MoE: it does not run on a laptop with 4 GB VRAM / 15 GB RAM. Use a smaller model, or a tag that Ollama serves remotely.
- Every subagent, whatever model it asks for (haiku/sonnet/opus), runs on that one tag.
- Local models are weaker at tool use than Claude; resuming a Claude session on one carries its history over but may behave worse.
- Multi-user: only an admin can change the provider; it applies to everyone.

## Conectores locales (servidores MCP de este PC)

The home screen has a **Conectores locales** card: MCP servers that run on this PC (stdio command or http URL) and are added to every `claude` Flows starts, for every package.
They work with the local model too, which is the point: when the provider is "Modelo local" the claude.ai connectors (Gmail, Drive, Calendar) are off, but local MCP servers still work.

- *Añadir conector*: name, type, command + arguments (or URL), and optional `CLAVE=valor` lines (env vars for stdio, headers for http). *Probar* starts it and lists its tools; *Guardar* stores it in `data/connectors.json` (mode 0600).
- Example, filesystem server: name `fs`, command `npx -y @modelcontextprotocol/server-filesystem /home/andrea/Documents` (needs Node/npx).
- Each enabled connector is pre-allowed as `mcp__<name>`. Secret values (env/headers) go to `claude` as environment variables, never in the command line.
- Stdio commands run as the Linux user of the person who started the session. Only an admin can change connectors; they apply to everyone.

## Flows Link (archivos del dispositivo)

Flows runs on the server, but you may be sitting at a laptop. **Flows Link** is a small program for that laptop. It shares folders you choose with the server's agents, live: they read, search and edit your files where they are. The laptop opens no port. It keeps one outbound HTTPS long-poll to Flows (`/api/link/poll`), runs each file operation itself, and posts the result back (`/api/link/reply`). That works through Tailscale, the Cloudflare tunnel or a proxy, and from behind any NAT.

It is one file, `link/flows_link.py`: Python 3.9+, standard library only, for Linux, macOS and Windows. Flows serves it at `https://<your flows>/link/flows_link.py`. That download is public and holds no secrets.

**1. Pair, once.** In Flows, home → *Mis dispositivos* → *Vincular dispositivo* → *Crear código*. The code works once and expires in 10 minutes. On the laptop:
```sh
python3 flows_link.py pair https://flows.example.com ABCD-EFGH      # Windows: py flows_link.py …
python3 flows_link.py share ~/proyectos/web                         # [--name web] [--read-only] [--allow-exec]
python3 flows_link.py folders                                       # what is shared;  unshare <name> to stop
python3 flows_link.py run                                           # stays connected, logs every operation
```
The device token is stored in `~/.config/flows-link/config.json` (Linux), `~/Library/Application Support/flows-link/config.json` (macOS) or `%APPDATA%\flows-link\config.json` (Windows), with mode 0600. Set `FLOWS_LINK_CONFIG` to use another file. While `run` is running it picks up `share`/`unshare` within one poll. It reconnects with backoff, and it exits if the device is revoked.

**Start at login**
- Linux (systemd user unit `~/.config/systemd/user/flows-link.service`, then `systemctl --user enable --now flows-link`):
  ```ini
  [Unit]
  Description=Flows Link
  [Service]
  ExecStart=/usr/bin/python3 %h/flows_link.py run
  Restart=always
  RestartSec=10
  [Install]
  WantedBy=default.target
  ```
- macOS: Python from python.org, or `xcode-select --install`. Create `~/Library/LaunchAgents/si.matteria.flows-link.plist`, then run `launchctl load ~/Library/LaunchAgents/si.matteria.flows-link.plist`:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
  <plist version="1.0"><dict>
    <key>Label</key><string>si.matteria.flows-link</string>
    <key>ProgramArguments</key><array><string>/usr/local/bin/python3</string><string>/Users/YOU/flows_link.py</string><string>run</string></array>
    <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>/tmp/flows-link.log</string><key>StandardErrorPath</key><string>/tmp/flows-link.log</string>
  </dict></plist>
  ```
  macOS asks before a program reads Documents, Desktop or Downloads. Run `run` once by hand and allow it, or share folders outside those three.
- Windows: install Python from python.org (tick "Add python.exe to PATH"; it also installs the `py`/`pyw` launcher). Then in `cmd`:
  `schtasks /Create /SC ONLOGON /TN "Flows Link" /TR "pyw.exe \"%USERPROFILE%\flows_link.py\" run"`
  If that needs admin rights, put a shortcut to `pyw.exe "%USERPROFILE%\flows_link.py" run` in `shell:startup` instead.

**What the agents get.** If you have paired a device, every `claude` that Flows starts gets an MCP server named `device` (`python3 server.py link-mcp`), pre-allowed as `mcp__device`. Its tools are `device_list_folders`, `device_list`, `device_stat`, `device_read` (images come back as images), `device_write`, `device_edit` (an exact, unique string replace), `device_mkdir`, `device_move`, `device_delete` (moves to `<folder>/.flows-trash/`), `device_glob`, `device_grep`, `device_exec`, plus `device_pull`/`device_push` to copy a file (up to 20 MB) between the device and the server. The lead agent's prompt says these paths are not on the server. If the device is offline, a call fails within 60 s with "el dispositivo no está conectado". The `admin` package never gets these tools.

**Security model**
- The device token is the only key to the laptop. The server stores only its SHA-256 (`data/link.json`, mode 0600) and compares it in constant time. *Revocar* in the card deletes it, and the device's open poll and pending calls fail immediately.
- Pairing codes have 8 characters (~39 bits), work once and expire in 10 minutes. They are kept in memory only. After 20 wrong codes in 15 minutes, across all clients, pairing is refused until the window passes.
- The client accepts `https://` only, with certificates verified and redirects refused. Plain `http://` is allowed only to localhost or a Tailscale address (100.64.0.0/10), where WireGuard encrypts the traffic.
- The server queues each operation for one device only and accepts a reply only from that device. It forwards only operations on folders that device reported, and it refuses writes to read-only folders and commands where they're off. Each `claude` process gets its own MCP secret, which stops working when the process ends. Multi-user: each person sees and uses only their own devices.
- **The client checks every request again, whatever the server sends.** Folders must be shared, paths must be relative, and after resolving every symlink the path must still be inside the shared folder (`..`, absolute paths, drive letters and symlinks pointing out are refused, and such symlinks are never listed or searched). Read-only folders refuse every write. `.git`, `node_modules` and `.flows-trash` are skipped when walking.
- **`--allow-exec` caveat.** Commands are off unless you share a folder with `--allow-exec`, and they can't be combined with `--read-only`. Once on, a command runs as **your user on the laptop**. It starts in that folder but can read or change anything you can, so the folder boundary doesn't hold for it. Only turn it on if you trust everything that can start an agent on that Flows server.

## Archivos (server files from any device)

The **Archivos** page (sidebar, or `#files`) lets you work with files from the phone or laptop you connect from. **Servidor** browses your home folder on this PC: preview text files, download a file or a whole folder as a .zip, upload files or folders (with drag and drop), create folders, rename or move, and delete. **Usar como carpeta del proyecto** puts the open folder in the project-folder field on Home. **Este dispositivo** uploads from and downloads to the device in any browser. On Chrome or Edge on a computer, it can also open a local folder, copy it to the server (default `~/flows-sync/<name>`) and bring back what changed there. It asks before overwriting a file that changed on both sides. Flows remembers the folder, and reopening it asks for permission again. Home and the session composer also have **Desde el servidor**, which attaches a server file to a message.

API (`/api/files/…`, the same sign-in, Host and `X-Flow` checks as the rest):
- `GET list?path=&hidden=1&deep=1`: lists one folder with folders first. Dotfiles show only with `hidden=1`. `deep=1` lists every file below the folder, skipping node_modules and .git.
- `GET read?path=`: the text of a file up to 1 MB. `GET download?path=`: a file, or a folder as a zip streamed while it's built. The zip leaves out node_modules, .git and the trash, and is capped at 500 MB (above that, 413).
- `POST upload?path=<folder>&name=<relative/path>[&overwrite=1][&mtime=]`: the raw body, written to disk in 1 MB chunks, so large files never sit in memory. Missing folders are created. An existing file is refused (409) unless `overwrite=1`.
- `POST mkdir {path}`, `POST rename {path, to}`, `POST delete {path}`. Delete moves the item into `~/.flows-trash/<time>-<name>`. Nothing is ever removed for good, so empty that folder by hand.

Every path is resolved with symlinks followed, and it's refused (403) unless it stays inside the home folder. That covers `..`, absolute paths, and links that point outside. A symlink that points outside is still listed, but it can't be opened.

**Multi-user decision:** file operations run as the server's own Linux user. They are **not** relayed through sudo. Under the setup above, the server runs as `flows`, so files it created in alice's home would belong to `flows`, and her `700` home isn't readable to it anyway. Doing it right would mean adding a second sudo-allowed helper next to `claude`, and that is a wider sudoers rule than this feature is worth. So the files API is on in single-user mode, and in multi-user mode only for an **admin whose Linux user is the server's user** (for example, Flows run as `andrea` with `andrea` as an admin). Everyone else gets a 403, and the page and its buttons are hidden for them (`/api/me` → `files: false`). They can still give files to agents as session attachments, or use the Flows Link app.
