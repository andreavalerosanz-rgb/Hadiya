# Deploy: Hadiya on your own PC

Hadiya is single-user: each person installs it on their own computer, with their own Claude login. There is no sign-in; the laptop listener answers `localhost` only, and phones get in by pairing (Phone access).

## Install on any Linux PC (.deb)
`scripts/build-deb.sh dev` or `scripts/build-deb.sh admin` builds `dist/hadiya-<pkg>_<ver>_all.deb`. Then:
- `sudo apt install ./dist/hadiya-admin_*.deb` puts the app in `/opt/hadiya`, adds a systemd user service, and adds an app-menu launcher that opens a Chrome app window.
- `systemctl --user start hadiya` (it starts by itself at every later login), then `claude login`. Data goes in `~/.local/share/hadiya`.

Phone: open Hadiya through Phone access (LAN, Tailscale or tunnel) and choose "Install app" or "Add to Home Screen". Hadiya is already a PWA.
Versions come from git tags: `git tag v1.0 && scripts/build-deb.sh`.

## Packages (`dev`, `admin`)
A package decides what the agents can reach. The server enforces it on every `claude` it starts, whatever the UI sent. It is set per install: `HADIYA_PACKAGE` (the .deb sets it).
- `dev` (default): everything.
- `admin`: Google Workspace only (Drive, Gmail, Calendar connectors). There are no file, shell, browser or other MCP tools, and Full auto is turned off.

Check it with `python3 scripts/test_packages.py`.

## Kanban: share links
A board's share link is `<public URL>/k/<token>`. Whoever has it can see, add, edit and move that board's cards and attach files, without pairing; nothing else in Hadiya. "New link" makes a new token and the old link stops working.
- **Quick tunnel** (default, nothing to set up): the share switch turns on the Phone-access Cloudflare tunnel. Its `*.trycloudflare.com` address changes every time it starts, so links sent before a restart stop working: send them again.
- **Stable URL**: a named Cloudflare tunnel. `cloudflared tunnel login`, `cloudflared tunnel create hadiya-kanban`, `cloudflared tunnel route dns hadiya-kanban kanban.example.com`, then run it to `http://127.0.0.1:8790` (Hadiya port + 3) as a service: `cloudflared tunnel run --url http://127.0.0.1:8790 hadiya-kanban`. Start Hadiya with `HADIYA_PUBLIC_URL=https://kanban.example.com`: it opens that port as a phone listener (pairing still guards everything except `/k/`) and the share links use that URL. Never point a tunnel at 8787 itself.

## Token Optimizer (fewer tokens per session)
Install the plugin once: `bash /opt/hadiya/deploy/setup-token-optimizer.sh`. Its hooks (checkpoint before compaction, output compression, quality score) then run inside every Hadiya session. Dashboard: `python3 <plugin>/skills/token-optimizer/scripts/measure.py dashboard`.

## Rename Flows → Hadiya (2026-10)
Settings read `HADIYA_<X>` first, then the old `FLOWS_<X>`, so existing units keep working. Still kept on purpose: `~/.claude/flows-*`, `~/.config/flows/trello.env`, `data/` file names and the `flows_device` cookie (paired phones stay paired). The brain MCP server is now `hadiya` (tools `mcp__hadiya__*`).

Personal install (user units, repo in `~/Desktop/flows`). Run it detached, because stopping `flows` kills every session, including the one that runs the command:
```sh
cd ~/Desktop/flows
sed 's/^Description=Flows/Description=Hadiya/' ~/.config/systemd/user/flows.service > ~/.config/systemd/user/hadiya.service
sed 's/^Description=Flows/Description=Hadiya/' ~/.config/systemd/user/flows-whatsapp.service > ~/.config/systemd/user/hadiya-whatsapp.service
systemctl --user daemon-reload
systemd-run --user --unit hadiya-migrate sh -c 'systemctl --user disable --now flows-whatsapp flows; systemctl --user enable --now hadiya hadiya-whatsapp'
systemctl --user status hadiya hadiya-whatsapp --no-pager   # then, once happy: rm ~/.config/systemd/user/flows.service ~/.config/systemd/user/flows-whatsapp.service
```
(Copying the installed units keeps their local `Environment=` lines, e.g. `PAIR_PHONE`.) Rollback: the same `systemd-run` with the names swapped.

.deb installs: the `hadiya-dev`/`hadiya-admin` packages replace `flows-dev`/`flows-admin`; after `apt install`, run `systemctl --user enable --now hadiya` once. The app moves to `/opt/hadiya`, and the unit moves `~/.local/share/flows` to `~/.local/share/hadiya` on its first start.

## Local model (a second provider, for when Claude runs out of tokens)

The local model is turned off for now; set `HADIYA_LOCAL_MODEL=1` (or the old `FLOWS_LOCAL_MODEL=1` in the service environment to turn it back on.

Hadiya can start `claude` against a local Anthropic-compatible endpoint instead of your Claude subscription.
Pick **Claude / Modelo local** in Más → *Conexiones*; new sessions and runs use the choice, a running session keeps its own.
When Claude hits its usage limit, the session shows **Continuar con el modelo local**, which switches and resumes it.

1. Install Ollama (https://ollama.com) and start it (it listens on `http://127.0.0.1:11434`).
2. Pull the model you want: `ollama pull <tag>`. Look up the Kimi tag in the Ollama library; Hadiya has no default and does not guess one.
3. In Hadiya, Más → *Conexiones* → *Ajustes del modelo local*: set the server address (default above) and the model tag, then *Guardar y comprobar*.
   The dot turns green when the server answers and has that tag. Settings are stored in `data/provider.json`.

Caveats:
- Full Kimi K2/K3 is a ~1T-parameter MoE: it does not run on a laptop with 4 GB VRAM / 15 GB RAM. Use a smaller model, or a tag that Ollama serves remotely.
- Every subagent, whatever model it asks for (haiku/sonnet/opus), runs on that one tag.
- Local models are weaker at tool use than Claude; resuming a Claude session on one carries its history over but may behave worse.

## Conectores locales (servidores MCP de este PC)

Más → *Conexiones* has a **Conectores locales** card: MCP servers that run on this PC (stdio command or http URL) and are added to every `claude` Hadiya starts, for every package.
They work with the local model too, which is the point: when the provider is "Modelo local" the claude.ai connectors (Gmail, Drive, Calendar) are off, but local MCP servers still work.

- *Añadir conector*: name, type, command + arguments (or URL), and optional `CLAVE=valor` lines (env vars for stdio, headers for http). *Probar* starts it and lists its tools; *Guardar* stores it in `data/connectors.json` (mode 0600).
- Example, filesystem server: name `fs`, command `npx -y @modelcontextprotocol/server-filesystem /home/andrea/Documents` (needs Node/npx).
- Each enabled connector is pre-allowed as `mcp__<name>`. Secret values (env/headers) go to `claude` as environment variables, never in the command line.
- Stdio commands run as your Linux user.

## Hadiya Link (archivos del dispositivo)

Hadiya runs on the server, but you may be sitting at a laptop. **Hadiya Link** is a small program for that laptop. It shares folders you choose with the server's agents, live: they read, search and edit your files where they are. The laptop opens no port. It keeps one outbound HTTPS long-poll to Hadiya (`/api/link/poll`), runs each file operation itself, and posts the result back (`/api/link/reply`). That works through Tailscale, the Cloudflare tunnel or a proxy, and from behind any NAT.

It is one file, `link/flows_link.py`: Python 3.9+, standard library only, for Linux, macOS and Windows. Hadiya serves it at `https://<your hadiya>/link/flows_link.py`. That download is public and holds no secrets.

**1. Pair, once.** In Hadiya, Más → *Conexiones* → *Mis dispositivos* → *Vincular dispositivo* → *Crear código*. The code works once and expires in 10 minutes. On the laptop:
```sh
python3 flows_link.py pair https://hadiya.example.com ABCD-EFGH      # Windows: py flows_link.py …
python3 flows_link.py share ~/proyectos/web                         # [--name web] [--read-only] [--allow-exec]
python3 flows_link.py folders                                       # what is shared;  unshare <name> to stop
python3 flows_link.py run                                           # stays connected, logs every operation
```
The device token is stored in `~/.config/flows-link/config.json` (Linux), `~/Library/Application Support/flows-link/config.json` (macOS) or `%APPDATA%\flows-link\config.json` (Windows), with mode 0600. Set `FLOWS_LINK_CONFIG` to use another file. While `run` is running it picks up `share`/`unshare` within one poll. It reconnects with backoff, and it exits if the device is revoked.

**Start at login**
- Linux (systemd user unit `~/.config/systemd/user/flows-link.service`, then `systemctl --user enable --now flows-link`):
  ```ini
  [Unit]
  Description=Hadiya Link
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
  `schtasks /Create /SC ONLOGON /TN "Hadiya Link" /TR "pyw.exe \"%USERPROFILE%\flows_link.py\" run"`
  If that needs admin rights, put a shortcut to `pyw.exe "%USERPROFILE%\flows_link.py" run` in `shell:startup` instead.

**What the agents get.** If you have paired a device, every `claude` that Hadiya starts gets an MCP server named `device` (`python3 server.py link-mcp`), pre-allowed as `mcp__device`. Its tools are `device_list_folders`, `device_list`, `device_stat`, `device_read` (images come back as images), `device_write`, `device_edit` (an exact, unique string replace), `device_mkdir`, `device_move`, `device_delete` (moves to `<folder>/.flows-trash/`), `device_glob`, `device_grep`, `device_exec`, plus `device_pull`/`device_push` to copy a file (up to 20 MB) between the device and the server. The lead agent's prompt says these paths are not on the server. If the device is offline, a call fails within 60 s with "el dispositivo no está conectado". The `admin` package never gets these tools.

**Security model**
- The device token is the only key to the laptop. The server stores only its SHA-256 (`data/link.json`, mode 0600) and compares it in constant time. *Revocar* in the card deletes it, and the device's open poll and pending calls fail immediately.
- Pairing codes have 8 characters (~39 bits), work once and expire in 10 minutes. They are kept in memory only. After 20 wrong codes in 15 minutes, across all clients, pairing is refused until the window passes.
- The client accepts `https://` only, with certificates verified and redirects refused. Plain `http://` is allowed only to localhost or a Tailscale address (100.64.0.0/10), where WireGuard encrypts the traffic.
- The server queues each operation for one device only and accepts a reply only from that device. It forwards only operations on folders that device reported, and it refuses writes to read-only folders and commands where they're off. Each `claude` process gets its own MCP secret, which stops working when the process ends.
- **The client checks every request again, whatever the server sends.** Folders must be shared, paths must be relative, and after resolving every symlink the path must still be inside the shared folder (`..`, absolute paths, drive letters and symlinks pointing out are refused, and such symlinks are never listed or searched). Read-only folders refuse every write. `.git`, `node_modules` and `.flows-trash` are skipped when walking.
- **`--allow-exec` caveat.** Commands are off unless you share a folder with `--allow-exec`, and they can't be combined with `--read-only`. Once on, a command runs as **your user on the laptop**. It starts in that folder but can read or change anything you can, so the folder boundary doesn't hold for it. Only turn it on if you trust everything that can start an agent on that Hadiya server.

## Archivos (server files from any device)

The **Archivos** page (Más → *Archivos*, or `#files`) lets you work with files from the phone or laptop you connect from. **Servidor** browses your home folder on this PC: preview text files, download a file or a whole folder as a .zip, upload files or folders (with drag and drop), create folders, rename or move, and delete. **Usar como carpeta del proyecto** puts the open folder in the project-folder field on Home. **Este dispositivo** uploads from and downloads to the device in any browser. On Chrome or Edge on a computer, it can also open a local folder, copy it to the server (default `~/hadiya-sync/<name>`) and bring back what changed there. It asks before overwriting a file that changed on both sides. Hadiya remembers the folder, and reopening it asks for permission again. Home and the session composer also have **Desde el servidor**, which attaches a server file to a message.

API (`/api/files/…`, the same Host, pairing and `X-Flow` checks as the rest):
- `GET list?path=&hidden=1&deep=1`: lists one folder with folders first. Dotfiles show only with `hidden=1`. `deep=1` lists every file below the folder, skipping node_modules and .git.
- `GET read?path=`: the text of a file up to 1 MB. `GET download?path=`: a file, or a folder as a zip streamed while it's built. The zip leaves out node_modules, .git and the trash, and is capped at 500 MB (above that, 413).
- `POST upload?path=<folder>&name=<relative/path>[&overwrite=1][&mtime=]`: the raw body, written to disk in 1 MB chunks, so large files never sit in memory. Missing folders are created. An existing file is refused (409) unless `overwrite=1`.
- `POST mkdir {path}`, `POST rename {path, to}`, `POST delete {path}`. Delete moves the item into `~/.flows-trash/<time>-<name>`. Nothing is ever removed for good, so empty that folder by hand.

Every path is resolved with symlinks followed, and it's refused (403) unless it stays inside the home folder. That covers `..`, absolute paths, and links that point outside. A symlink that points outside is still listed, but it can't be opened.

## Always-on server (`deploy/server-setup.sh`)
For a PC that serves Hadiya around the clock (the .deb install, systemd user service): `sudo deploy/server-setup.sh [--tailscale] [--tunnel-token TOKEN] [--no-sleep]`.
- Always: `loginctl enable-linger`, so `hadiya` starts at boot without anyone logging in.
- `--tailscale`: installs Tailscale, runs `tailscale up` and lets your user run `tailscale serve` (Phone access → Tailscale toggles it).
- `--tunnel-token`: a Cloudflare named tunnel on your own domain, as the user service `hadiya-tunnel` (token in `~/.config/flows/tunnel.env`, mode 0600, never on a command line), and `HADIYA_PUBLIC_PORT=8790` for `hadiya`. In the Cloudflare dashboard, route the hostname to `http://127.0.0.1:8790`. That port is the public listener: pairing guards everything on it except the Kanban share links (`/k/`), the Link client endpoints and the `flows_link.py` download. It is the same listener `HADIYA_PUBLIC_URL` opens for Kanban.
- `--no-sleep`: masks suspend and hibernate.
