#!/usr/bin/env bash
# Build dist/hadiya-macos_<ver>.zip
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
. "$root/scripts/version.sh"

stage=$(mktemp -d); trap 'rm -rf "$stage"' EXIT
app=$stage/Hadiya
install -d "$app/mac"
cp server.py index.html kanban.html "$app/"
printf "%s\n" "$ver" > "$app/VERSION"
cp -r icons "$app/"
cp mac/install.sh "$app/mac/"
cp "mac/Instalar Hadiya.command" "$app/"
find "$app" \( -name __pycache__ -o -name '*.log' \) -prune -exec rm -rf {} +

mkdir -p dist
out=dist/hadiya-macos_${ver}.zip
rm -f "$out"
# zip keeps the executable bits (python -m zipfile would drop them and the .command would not open)
(cd "$stage" && zip -qr "$root/$out" Hadiya)
echo "$out"
