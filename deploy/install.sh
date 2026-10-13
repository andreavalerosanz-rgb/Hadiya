#!/usr/bin/env bash
# Usage (root, from anywhere): [PORT=8787] deploy/install.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "must run as root" >&2; exit 1; }

src="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

id flows &>/dev/null || useradd --system --home-dir /opt/flows --shell /usr/sbin/nologin flows

mkdir -p /opt/flows
cp -a "$src"/. /opt/flows/
rm -rf /opt/flows/data /opt/flows/.git /opt/flows/dist /opt/flows/__pycache__  # never ship the dev box's sessions
mkdir -p /opt/flows/data
chown -R flows:flows /opt/flows/data
chmod 700 /opt/flows/data

sed "s/PORT=8787/PORT=${PORT:-8787}/" "$src/deploy/hadiya.service" > /etc/systemd/system/hadiya.service
systemctl daemon-reload
systemctl disable --now flows 2>/dev/null || true  # the unit before the Hadiya rename (same port)
systemctl enable --now hadiya

cat <<MSG

hadiya installed and running on 127.0.0.1:${PORT:-8787}.
IMPORTANT: put HTTPS in front BEFORE exposing the login (Caddy: deploy/Caddyfile,
or a Cloudflare named tunnel). Never expose port 8787 over plain HTTP.
Add users with: deploy/add-user.sh <linux_user>
MSG
