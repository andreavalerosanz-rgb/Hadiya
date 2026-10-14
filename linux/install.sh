#!/usr/bin/env bash
# Hadiya for Linux: per-user install, no root. Safe to re-run (upgrades the app, keeps data).
# App: ~/.local/share/hadiya/app, data: ~/.local/share/hadiya (same as the .deb's service). Test knobs: HADIYA_SKIP_CLAUDE=1, HADIYA_NO_SERVICE=1.
set -euo pipefail
src=$(cd "$(dirname "$0")" && pwd)
share=$HOME/.local/share
app=$share/hadiya/app
[ -f "$src/server.py" ] || { echo "Ejecuta install.sh desde la carpeta descomprimida." >&2; exit 1; }
command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' ||
  { echo "Hace falta Python 3.9 o mas nuevo (sudo apt install python3 / dnf install python3)." >&2; exit 1; }
command -v curl >/dev/null || { echo "Hace falta curl." >&2; exit 1; }
svc() { [ -n "${HADIYA_NO_SERVICE:-}" ] || systemctl --user "$@"; }

echo "1/3 Claude Code"
export PATH=$HOME/.local/bin:$PATH
if [ -z "${HADIYA_SKIP_CLAUDE:-}" ] && ! command -v claude >/dev/null; then
  curl -fsSL https://claude.ai/install.sh | bash   # official native installer, per user
  command -v claude >/dev/null || { echo "No se pudo instalar Claude Code." >&2; exit 1; }
fi

echo "2/3 Hadiya"
svc stop hadiya.service 2>/dev/null || true
rm -rf "$app/icons" "$app/deploy"; mkdir -p "$app"   # cp -r into an existing dir would nest it
cp -r "$src/server.py" "$src/index.html" "$src/kanban.html" "$src/VERSION" "$src/icons" "$src/deploy" "$app/"
unit=$HOME/.config/systemd/user; mkdir -p "$unit" "$share/applications"
sed -e "s#/opt/hadiya#$app#" -e 's/@PKG@/dev/g' "$app/deploy/hadiya-user.service" > "$unit/hadiya.service"
cp "$app/deploy/hadiya.desktop" "$share/applications/hadiya.desktop"
for s in 192 512; do
  mkdir -p "$share/icons/hicolor/${s}x$s/apps"; cp "$app/icons/icon-$s.png" "$share/icons/hicolor/${s}x$s/apps/hadiya.png"
done

echo "3/3 Servicio"
svc daemon-reload; svc enable --now hadiya.service
svc restart hadiya.service   # enable --now does nothing if it was already running

if [ -z "${HADIYA_SKIP_CLAUDE:-}" ] && ! claude auth status >/dev/null 2>&1; then
  echo "Inicia sesion con tu cuenta de Claude en el navegador que se va a abrir."
  claude auth login
fi
echo "Listo (version $(cat "$app/VERSION")). Abre Hadiya desde el menu de aplicaciones o en http://localhost:8787"
