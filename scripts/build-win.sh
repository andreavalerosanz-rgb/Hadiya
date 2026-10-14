#!/usr/bin/env bash
# Build dist/hadiya-windows_<ver>.zip
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
. "$root/scripts/version.sh"

stage=$(mktemp -d); trap 'rm -rf "$stage"' EXIT
app=$stage/Hadiya

install -d "$app/icons" "$app/windows"

# Copy core files
cp server.py index.html kanban.html "$app/"
printf "%s\n" "$ver" > "$app/VERSION"
cp -r icons/* "$app/icons/"
cp -r windows/* "$app/windows/"
find "$app" \( -name __pycache__ -o -name '*.log' \) -prune -exec rm -rf {} +

# Generate hadiya.ico from favicon-32.png and icon-192.png
python3 - "$root/icons/favicon-32.png" "$root/icons/icon-192.png" "$app/windows/hadiya.ico" <<'PYEOF'
import struct
import sys

def read_png_dimensions(path):
    """Extract width and height from PNG IHDR chunk."""
    with open(path, 'rb') as f:
        # PNG signature: 89 50 4E 47 0D 0A 1A 0A
        sig = f.read(8)
        if sig != b'\x89PNG\r\n\x1a\n':
            raise ValueError(f"{path} is not a PNG file")
        # IHDR chunk: length (4) + 'IHDR' (4) + data (13)
        chunk_len = f.read(4)
        chunk_type = f.read(4)
        if chunk_type != b'IHDR':
            raise ValueError(f"First chunk is not IHDR")
        width = struct.unpack('>I', f.read(4))[0]
        height = struct.unpack('>I', f.read(4))[0]
    return width, height

def read_png_data(path):
    """Read entire PNG file as bytes."""
    with open(path, 'rb') as f:
        return f.read()

png1 = sys.argv[1]
png2 = sys.argv[2]
ico_out = sys.argv[3]

w1, h1 = read_png_dimensions(png1)
w2, h2 = read_png_dimensions(png2)
png1_data = read_png_data(png1)
png2_data = read_png_data(png2)

# ICO header: reserved (2), type=1 (2), count=2 (2)
ico_data = struct.pack('<HHH', 0, 1, 2)

# ICONDIRENTRY for PNG1
width1 = 0 if w1 == 256 else w1
height1 = 0 if h1 == 256 else h1
entry1_size = len(png1_data)
entry1_offset = 6 + 2*16  # ICONDIR + 2 entries
ico_data += struct.pack('<BBBBHHI', width1, height1, 0, 0, 1, 32, entry1_size)
ico_data += struct.pack('<I', entry1_offset)

# ICONDIRENTRY for PNG2
width2 = 0 if w2 == 256 else w2
height2 = 0 if h2 == 256 else h2
entry2_size = len(png2_data)
entry2_offset = entry1_offset + entry1_size
ico_data += struct.pack('<BBBBHHI', width2, height2, 0, 0, 1, 32, entry2_size)
ico_data += struct.pack('<I', entry2_offset)

# Append PNG data
ico_data += png1_data + png2_data

with open(ico_out, 'wb') as f:
    f.write(ico_data)
PYEOF

# Create top-level wrapper batch file with CRLF
printf '@echo off\r\ncall "%%~dp0windows\\install-hadiya.cmd"\r\n' > "$app/Instalar Hadiya.cmd"

# Convert line endings to CRLF for .cmd and .ps1 files
find "$app" -type f \( -name "*.cmd" -o -name "*.ps1" \) -print0 | xargs -0 sed -i 's/\r\?$/\r/'

mkdir -p dist
out=dist/hadiya-windows_${ver}.zip

# Create zip archive
if command -v zip >/dev/null; then
  (cd "$stage" && zip -qr "$root/$out" Hadiya)
else
  python3 -m zipfile -c "$out" -C "$stage" Hadiya
fi

echo "$out"
