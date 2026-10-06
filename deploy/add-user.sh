#!/usr/bin/env bash
# Usage (root): add-user.sh <linux_user>
set -euo pipefail

u="${1:-}"
[[ $EUID -eq 0 ]] || { echo "must run as root" >&2; exit 1; }
[[ "$u" =~ ^[a-z][a-z0-9_-]{1,30}$ ]] || { echo "usage: $0 <linux_user> (^[a-z][a-z0-9_-]{1,30}\$)" >&2; exit 1; }
[[ "$u" != flows && "$u" != root ]] || { echo "refusing reserved user: $u" >&2; exit 1; }

if id "$u" &>/dev/null; then
  echo "user $u exists"
else
  adduser --disabled-password --gecos '' "$u"
fi
chmod 700 "$(getent passwd "$u" | cut -d: -f6)"

# Matches DEPLOY.md: the server may run only the claude binary as $u (sudo >= 1.9.3 for CWD=).
f="/etc/sudoers.d/flows-$u"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
echo "flows ALL=($u) CWD=* NOPASSWD:SETENV: /usr/local/bin/claude" > "$tmp"
usermod -aG "$u" flows 2>/dev/null || true  # per-user upload/shot dirs are group-shared
visudo -cf "$tmp" >/dev/null
install -m 440 -o root -g root "$tmp" "$f"
echo "installed $f"

cat <<MSG

Next steps:
  sudo -u $u -i claude auth login
  sudo -u $u -i bash /opt/flows/deploy/setup-token-optimizer.sh   # fewer tokens per session
  sudo -u flows python3 /opt/flows/server.py adduser <flowsname> $u
MSG
