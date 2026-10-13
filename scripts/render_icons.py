"""Rasterize icons/hadiya-*.svg into the PNGs Hadiya serves. Run: /tmp/pwenv/bin/python scripts/render_icons.py"""
from pathlib import Path
from urllib.parse import quote
from playwright.sync_api import sync_playwright
D = Path(__file__).resolve().parent.parent / "icons"
OUT = {"icon-512.png": ("tile", 512), "icon-192.png": ("tile", 192), "favicon-32.png": ("tile", 32),
       "icon-maskable-512.png": ("maskable", 512), "apple-touch-icon.png": ("maskable", 180)}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome")
    for name, (src, n) in OUT.items():
        pg = b.new_page(viewport={"width": n, "height": n})
        pg.set_content(f'<body style="margin:0"><img src="data:image/svg+xml,{quote((D / f"hadiya-{src}.svg").read_text())}" width={n} height={n}>')
        pg.wait_for_function("document.images[0].complete && document.images[0].naturalWidth")
        pg.screenshot(path=str(D / name), omit_background=True); pg.close()
