#!/usr/bin/env bash
# Hadiya for macOS: per-user install into ~/Library/Application Support/Hadiya, no admin. Safe to re-run (upgrades the app, keeps data).
# Python: a real python3 >= 3.9 if there is one (Homebrew / python.org / Command Line Tools), else a private copy via uv (no admin, no Homebrew).
# Test knobs: HADIYA_SKIP_CLAUDE=1, HADIYA_NO_SERVICE=1.
set -euo pipefail
src=$(cd "$(dirname "$0")/.." && pwd)   # the unzipped package: app files + mac/
home=$HOME/Library/Application\ Support/Hadiya
app=$home/app
data=$home/data
label=com.hadiya.server
plist=$HOME/Library/LaunchAgents/$label.plist
launcher=$HOME/Applications/Hadiya.app
[ -f "$src/server.py" ] || { echo "Descomprime el zip completo antes de instalar." >&2; exit 1; }
export PATH=$HOME/.local/bin:$PATH
mkdir -p "$app" "$data"

echo "1/4 Python"
py=
good() { [ -x "$1" ] && "$1" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; }
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3; do
  good "$c" && { py=$c; break; }
done
# /usr/bin/python3 is a stub that pops up a "install developer tools" dialog unless the tools are present
[ -z "$py" ] && xcode-select -p >/dev/null 2>&1 && good /usr/bin/python3 && py=/usr/bin/python3
if [ -z "$py" ]; then
  command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
  uv python install 3.12
  py=$(uv python find 3.12)
fi
echo "   $py"

echo "2/4 Claude Code"
if [ -z "${HADIYA_SKIP_CLAUDE:-}" ] && ! command -v claude >/dev/null; then
  curl -fsSL https://claude.ai/install.sh | bash   # official native installer, per user
  command -v claude >/dev/null || { echo "No se pudo instalar Claude Code." >&2; exit 1; }
fi

echo "3/4 Hadiya"
[ -n "${HADIYA_NO_SERVICE:-}" ] || launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
rm -rf "$app/icons"
cp -R "$src/server.py" "$src/index.html" "$src/kanban.html" "$src/VERSION" "$src/icons" "$app/"
xattr -dr com.apple.quarantine "$app" 2>/dev/null || true
mkdir -p "$HOME/Library/LaunchAgents" "$launcher/Contents/MacOS" "$launcher/Contents/Resources"
cat > "$plist" <<EOP
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>$py</string><string>-X</string><string>utf8</string><string>$app/server.py</string></array>
  <key>WorkingDirectory</key><string>$app</string>
  <key>EnvironmentVariables</key><dict>
    <key>HADIYA_DATA</key><string>$data</string>
    <key>HADIYA_PACKAGE</key><string>dev</string>
    <key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$data/server.log</string><key>StandardErrorPath</key><string>$data/server.log</string>
</dict></plist>
EOP
# app launcher: a tiny .app that opens the (already running) server in a Chromium app window, else the default browser
cat > "$launcher/Contents/MacOS/Hadiya" <<'EOL'
#!/bin/bash
url=http://localhost:8787/
for _ in $(seq 40); do curl -sf -o /dev/null "$url" && break; sleep 0.5; done
for b in "Google Chrome" "Microsoft Edge" "Brave Browser" Chromium; do
  if open -Ra "$b" 2>/dev/null; then exec open -na "$b" --args "--app=$url"; fi
done
exec open "$url"
EOL
chmod +x "$launcher/Contents/MacOS/Hadiya"
cat > "$launcher/Contents/Info.plist" <<'EOP'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Hadiya</string><key>CFBundleDisplayName</key><string>Hadiya</string>
  <key>CFBundleIdentifier</key><string>com.hadiya.launcher</string><key>CFBundleExecutable</key><string>Hadiya</string>
  <key>CFBundleIconFile</key><string>Hadiya</string><key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
EOP
if command -v iconutil >/dev/null && command -v sips >/dev/null; then   # icon is cosmetic: never fail the install over it
  (set_dir=$(mktemp -d)/Hadiya.iconset; mkdir -p "$set_dir"
   for s in 16 32 128 256 512; do sips -z $s $s "$app/icons/icon-512.png" --out "$set_dir/icon_${s}x$s.png" >/dev/null
     sips -z $((s*2)) $((s*2)) "$app/icons/icon-512.png" --out "$set_dir/icon_${s}x${s}@2x.png" >/dev/null; done
   iconutil -c icns "$set_dir" -o "$launcher/Contents/Resources/Hadiya.icns") || true
fi

echo "4/4 Servicio"
if [ -z "${HADIYA_NO_SERVICE:-}" ]; then
  launchctl bootstrap "gui/$(id -u)" "$plist"   # RunAtLoad starts it now and at every login
  if [ -z "${HADIYA_SKIP_CLAUDE:-}" ] && ! claude auth status >/dev/null 2>&1; then
    echo "Inicia sesion con tu cuenta de Claude en el navegador que se va a abrir."
    claude auth login
  fi
  open "$launcher"
fi
echo "Listo (version $(cat "$app/VERSION")). Hadiya esta en Aplicaciones (carpeta de tu usuario) y se abre sola al iniciar sesion."
