#!/usr/bin/env bash
# Turn this PC into an always-on Hadiya server for its own user (the .deb install, systemd user service).
# Usage: sudo deploy/server-setup.sh [--tailscale] [--tunnel-token TOKEN] [--no-sleep]
#   --tailscale           install Tailscale, `tailscale up`, and let the user run `tailscale serve` (Hadiya toggles it)
#   --tunnel-token TOKEN  Cloudflare named tunnel (your domain): install cloudflared and run it as a user service.
#                         In the Cloudflare dashboard, route the hostname to http://127.0.0.1:8790 (HADIYA_PUBLIC_PORT).
#   --no-sleep            never suspend/hibernate (a server that sleeps is unreachable)
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
U=${SUDO_USER:?run with sudo from your own account}
H=$(getent passwd "$U" | cut -d: -f6)
TS= TOKEN= NOSLEEP=
while [[ $# -gt 0 ]]; do case $1 in
  --tailscale) TS=1;; --tunnel-token) TOKEN=${2:?}; shift;; --no-sleep) NOSLEEP=1;;
  *) echo "unknown option $1" >&2; exit 1;; esac; shift; done
as_user() { sudo -u "$U" XDG_RUNTIME_DIR=/run/user/$(id -u "$U") "$@"; }

# 1. Start Hadiya at boot, without anyone logging in
loginctl enable-linger "$U"
as_user systemctl --user enable hadiya

# 2. Tailscale: private access from anywhere
if [[ $TS ]]; then
  command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh
  tailscale up
  tailscale set --operator="$U"  # Hadiya runs `tailscale serve` as $U
fi

# 3. Public domain over a Cloudflare named tunnel
if [[ $TOKEN ]]; then
  if ! command -v cloudflared >/dev/null; then
    a=$(dpkg --print-architecture); f=$(mktemp --suffix=.deb)
    curl -fsSL -o "$f" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$a.deb"
    apt-get install -y "$f"; rm -f "$f"
  fi
  install -d -o "$U" -g "$U" -m 700 "$H/.config/flows"
  install -o "$U" -g "$U" -m 600 /dev/null "$H/.config/flows/tunnel.env"
  echo "TUNNEL_TOKEN=$TOKEN" > "$H/.config/flows/tunnel.env"  # never on a command line
  install -d -o "$U" -g "$U" "$H/.config/systemd/user" "$H/.config/systemd/user/hadiya.service.d"
  cat > "$H/.config/systemd/user/hadiya-tunnel.service" <<EOF
[Unit]
Description=Hadiya public tunnel (Cloudflare)
After=hadiya.service

[Service]
EnvironmentFile=%h/.config/flows/tunnel.env
ExecStart=$(command -v cloudflared) tunnel --no-autoupdate run
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
  cat > "$H/.config/systemd/user/hadiya.service.d/public.conf" <<EOF
[Service]
Environment=HADIYA_PUBLIC_PORT=8790
EOF
  chown -R "$U:$U" "$H/.config/systemd/user"
  as_user systemctl --user daemon-reload
  as_user systemctl --user enable --now hadiya-tunnel
fi

# 4. Never sleep
[[ $NOSLEEP ]] && systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

as_user systemctl --user restart hadiya
echo "Hecho. Hadiya arranca con el PC (usuario $U)."
[[ $TS ]] && echo "Tailscale: activa el acceso en Hadiya → Acceso remoto → Tailscale."
[[ $TOKEN ]] && echo "Dominio: comprueba en Cloudflare que el hostname apunta a http://127.0.0.1:8790."
exit 0
