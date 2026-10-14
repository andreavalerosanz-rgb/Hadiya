#!/usr/bin/env bash
# Build dist/hadiya-linux_<ver>.tar.gz (per-user install.sh inside; the .deb stays for system-wide installs)
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
. "$root/scripts/version.sh"

stage=$(mktemp -d); trap 'rm -rf "$stage"' EXIT
app=$stage/Hadiya
install -d "$app"
cp server.py index.html kanban.html "$app/"
printf "%s\n" "$ver" > "$app/VERSION"
cp -r icons deploy "$app/"
cp linux/install.sh "$app/install.sh"; chmod +x "$app/install.sh"
find "$app" \( -name __pycache__ -o -name '*.log' \) -prune -exec rm -rf {} +

mkdir -p dist
out=dist/hadiya-linux_${ver}.tar.gz
tar -czf "$out" -C "$stage" Hadiya
echo "$out"
