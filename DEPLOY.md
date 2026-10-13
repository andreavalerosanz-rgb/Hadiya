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
