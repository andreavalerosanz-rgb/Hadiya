#!/usr/bin/env bash
# Build dist/hadiya-<dev|admin>_<ver>_all.deb
set -euo pipefail
pkg=${1:-dev}
case $pkg in dev|admin) ;; *) echo "usage: $0 [dev|admin]" >&2; exit 1;; esac
command -v dpkg-deb >/dev/null || { echo "dpkg-deb not found" >&2; exit 1; }

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
ver=$(git describe --tags --always --dirty)
ver=${ver#v}
git describe --tags >/dev/null 2>&1 || ver=0.0.0+g$ver   # no tags: bare hash
[[ $ver =~ ^[0-9]+(\.[0-9]+)*- ]] && ver=${ver/-/+}  # tag-N-gHASH -> tag+N-gHASH
ver=$(printf '%s' "$ver" | tr -c 'A-Za-z0-9.+~:\n-' '.')

name=hadiya-$pkg
other=hadiya-admin; [ "$pkg" = admin ] && other=hadiya-dev
stage=$(mktemp -d); trap 'rm -rf "$stage"' EXIT
app=$stage/opt/flows
install -d "$app/scripts" "$stage/DEBIAN" "$stage/usr/lib/systemd/user" \
  "$stage/usr/share/applications" \
  "$stage/usr/share/icons/hicolor/512x512/apps" "$stage/usr/share/icons/hicolor/192x192/apps"

cp server.py index.html PRODUCT.md DEPLOY.md "$app/"
cp -r icons deploy "$app/"
cp scripts/test_multiuser.py "$app/scripts/"
find "$app" \( -name __pycache__ -o -name '*.log' \) -prune -exec rm -rf {} +

sed "s/@PKG@/$pkg/g" deploy/hadiya-user.service > "$stage/usr/lib/systemd/user/hadiya.service"
cp deploy/hadiya.desktop "$stage/usr/share/applications/hadiya.desktop"
cp icons/icon-512.png "$stage/usr/share/icons/hicolor/512x512/apps/hadiya.png"
cp icons/icon-192.png "$stage/usr/share/icons/hicolor/192x192/apps/hadiya.png"

cat > "$stage/DEBIAN/control" <<EOC
Package: $name
Version: $ver
Architecture: all
Maintainer: Andrea Valero <andrea.valero@matteria.si>
Depends: python3 (>= 3.9)
Recommends: nodejs
Conflicts: $other, flows, flows-dev, flows-admin
Replaces: $other, flows, flows-dev, flows-admin
Provides: hadiya
Section: devel
Priority: optional
Description: Hadiya - local Claude Code workbench ($pkg edition)
 Local web app served at http://localhost:8787, run as each desktop user
 via a systemd user service.
 Requires the Claude CLI: npm install -g @anthropic-ai/claude-code
 then run: claude login
EOC

cat > "$stage/DEBIAN/postinst" <<'EOC'
#!/bin/sh
set -e
if [ "$1" = configure ]; then
  systemctl --global enable hadiya.service || true
  echo "Hadiya installed. Start it now with: systemctl --user start hadiya"
  echo "(or log out and in). If not done yet, run: claude login"
fi
exit 0
EOC
cat > "$stage/DEBIAN/prerm" <<'EOC'
#!/bin/sh
set -e
if [ "$1" = remove ] || [ "$1" = purge ]; then
  systemctl --global disable hadiya.service || true
fi
exit 0
EOC
chmod 755 "$stage/DEBIAN/postinst" "$stage/DEBIAN/prerm"

chmod -R u+rwX,go+rX,go-w "$stage"; chmod 755 "$stage" "$stage/DEBIAN/postinst" "$stage/DEBIAN/prerm"
mkdir -p dist
out=dist/${name}_${ver}_all.deb
dpkg-deb --root-owner-group --build "$stage" "$out"
echo "$out"
