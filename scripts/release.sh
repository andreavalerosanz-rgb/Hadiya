#!/usr/bin/env bash
# Build the three packages and publish a GitHub release v<ver>. Usage: scripts/release.sh [--dry-run]
# --dry-run prints every command and runs nothing. Publishing needs `gh auth login` and is outward-facing: run it on purpose.
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
dry=0; [ "${1:-}" = "--dry-run" ] && dry=1
run() { if [ $dry = 1 ]; then printf '+ %s\n' "$*"; else "$@"; fi; }

. scripts/version.sh   # sets $ver, the same one the build-* scripts write to VERSION
[ $dry = 1 ] || [ -z "$(git status --porcelain)" ] || { echo "working tree not clean" >&2; exit 1; }

for b in win mac linux; do run bash "scripts/build-$b.sh"; done
assets=(dist/hadiya-windows_"$ver".zip dist/hadiya-macos_"$ver".zip dist/hadiya-linux_"$ver".tar.gz)
if [ $dry = 0 ]; then for a in "${assets[@]}"; do [ -f "$a" ] || { echo "missing $a" >&2; exit 1; }; done; fi

run gh release create "v$ver" "${assets[@]}" --title "Hadiya $ver" --generate-notes
