#!/usr/bin/env bash
# Try multi-user Hadiya on this PC, next to the personal one on 8787:
#   sudo deploy/central-test.sh <your_linux_user>
# Central server on 127.0.0.1:8800 (/opt/flows, user flows). Accounts: <you> (dev, admin) and "prueba" (admin package).
# Undo: sudo systemctl disable --now hadiya; sudo rm -rf /opt/flows /etc/systemd/system/hadiya.service /etc/sudoers.d/flows-*; sudo deluser --remove-home prueba
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
me=${1:?usage: sudo $0 <your_linux_user>}
src="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# the claude CLI must be system-wide for sudo's secure_path (DEPLOY.md §1)
[[ -x /usr/local/bin/claude ]] || install -m 755 "$(readlink -f "$(getent passwd "$me" | cut -d: -f6)/.local/bin/claude")" /usr/local/bin/claude
PORT=8800 "$src/deploy/install.sh"
"$src/deploy/add-user.sh" "$me"
"$src/deploy/add-user.sh" prueba

flows() { sudo -u flows python3 /opt/flows/server.py "$@"; }
echo; echo "Hadiya password for $me:"; flows adduser "$me" "$me" --admin
echo; echo "Hadiya password for prueba:"; flows adduser prueba prueba --package admin
systemctl restart hadiya
sudo -u flows sudo -n -u prueba -H -D /home/prueba -- /usr/local/bin/claude --version

echo; echo "Now sign prueba in to Claude (the browser link it prints works from any machine):"
sudo -u prueba -i /usr/local/bin/claude auth login || echo "Later: sudo -u prueba -i claude auth login"
echo; echo "Open http://localhost:8800 — $me in one window, prueba in a private window."
