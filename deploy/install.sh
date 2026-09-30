#!/usr/bin/env bash
# Usage (root, from anywhere): deploy/install.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "must run as root" >&2; exit 1; }

src="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

id flows &>/dev/null || useradd --system --home-dir /opt/flows --shell /usr/sbin/nologin flows

mkdir -p /opt/flows
cp -a "$src"/. /opt/flows/
mkdir -p /opt/flows/data
chown -R flows:flows /opt/flows/data
chmod 700 /opt/flows/data

install -m 644 "$src/deploy/flows.service" /etc/systemd/system/flows.service
systemctl daemon-reload
systemctl enable --now flows

cat <<MSG

flows installed and running on 127.0.0.1:8787.
IMPORTANT: put HTTPS in front BEFORE exposing the login (Caddy: deploy/Caddyfile,
or a Cloudflare named tunnel). Never expose port 8787 over plain HTTP.
Add users with: deploy/add-user.sh <linux_user>
MSG
