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

## Kanban: share links
A board's share link is `<public URL>/k/<token>`. Whoever has it can see, add, edit and move that board's cards and attach files, without pairing or signing in; nothing else in Flows. "New link" makes a new token and the old link stops working.
- **Quick tunnel** (default, nothing to set up): the share switch turns on the Phone-access Cloudflare tunnel. Its `*.trycloudflare.com` address changes every time it starts, so links sent before a restart stop working: send them again.
- **Stable URL**: a named Cloudflare tunnel. `cloudflared tunnel login`, `cloudflared tunnel create flows-kanban`, `cloudflared tunnel route dns flows-kanban kanban.example.com`, then run it to `http://127.0.0.1:8790` (Flows port + 3) as a service: `cloudflared tunnel run --url http://127.0.0.1:8790 flows-kanban`. Start Flows with `FLOWS_PUBLIC_URL=https://kanban.example.com`: it opens that port as a phone listener (pairing still guards everything except `/k/`) and the share links use that URL. Never point a tunnel at 8787 itself.

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

## 7. Token Optimizer (fewer tokens per session)
Each person installs the plugin once, as themselves: `sudo -u alice -i bash /opt/flows/deploy/setup-token-optimizer.sh`. Its hooks (checkpoint before compaction, output compression, quality score) then run inside every Flows session they own. Dashboard: `python3 <plugin>/skills/token-optimizer/scripts/measure.py dashboard`.
