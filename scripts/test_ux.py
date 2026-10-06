"""python3 scripts/test_ux.py [base_url] — layout regression on the longest real session (needs a running server and `pip install playwright`).
One line per failed check, exit 1 if any. Screenshots of failures only, to data/shots/<run>/ (never into the repo)."""
import json, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8787"
SHOTS = Path(__file__).resolve().parent.parent / "data" / "shots" / time.strftime("ux-%Y%m%d-%H%M%S")
DESKTOP, FAILS = [(1024, 768), (1440, 900), (1920, 1080)], []

def get(path):
    return json.load(urllib.request.urlopen(urllib.request.Request(BASE + path, headers={"X-Flow": "1"}), timeout=20))

def check(page, ok, label):
    if ok: return
    FAILS.append(label); SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / (label.split(":")[0].replace(" ", "-").replace("/", "") + ".png")))

def js(page, expr): return page.evaluate(expr)

def rect(page, sel):
    return js(page, f"(()=>{{const e=document.querySelector({json.dumps(sel)});if(!e)return null;const r=e.getBoundingClientRect();return {{top:r.top,bottom:r.bottom,width:r.width,height:r.height}}}})()")

def desktop(page, sid):
    page.set_viewport_size({"width": 1440, "height": 900}); page.goto(f"{BASE}/#session/{sid}"); page.wait_for_selector(".logbox", timeout=15000)
    for w, h in DESKTOP:  # resize live, no reload: catches stale layout
        page.set_viewport_size({"width": w, "height": h}); page.wait_for_timeout(250)
        tag = f"{w}x{h}"
        log, comp, rack = rect(page, ".logbox"), rect(page, "#composer"), rect(page, "#rack")
        check(page, log and log["height"] >= .45 * h, f"{tag}: log {log and round(log['height'])}px < 45% of the window")
        check(page, comp and comp["bottom"] <= h + 1, f"{tag}: composer below the fold")
        check(page, js(page, "(m=>m.scrollHeight<=m.clientHeight+1)(document.querySelector('main'))") and js(page, "document.scrollingElement.scrollHeight<=innerHeight+1"), f"{tag}: more than one scroller")
        check(page, js(page, "document.documentElement.scrollWidth") <= w, f"{tag}: horizontal overflow")
        check(page, rack and rack["width"] <= .4 * w + 1, f"{tag}: rack {rack and round(rack['width'])}px > 40vw")
    # drag the rack wide at 1440, shrink to 1024: it must clamp and the log keep its room
    page.set_viewport_size({"width": 1440, "height": 900}); page.wait_for_timeout(200)
    h = rect(page, "#rack-drag")
    if h and h["width"] > 0:
        page.mouse.move(h["width"] / 2 + js(page, "document.querySelector('#rack').offsetWidth") - 4, 450); page.mouse.down(); page.mouse.move(700, 450, steps=4); page.mouse.up()
        page.set_viewport_size({"width": 1024, "height": 768}); page.wait_for_timeout(300)
        rack, log = rect(page, "#rack"), rect(page, ".logbox")
        check(page, rack["width"] <= .4 * 1024 + 1, f"drag then 1024: rack {round(rack['width'])}px not clamped")
        check(page, log["height"] >= .45 * 768, "drag then 1024: log too short")
    else:
        check(page, False, "rack-drag handle is not visible on desktop")
    # keyboard resize on the separator (wide enough window)
    page.set_viewport_size({"width": 1440, "height": 900}); page.wait_for_timeout(200)
    page.evaluate("localStorage.removeItem('rackW')"); page.reload(); page.wait_for_selector("#rack-drag")
    w0 = rect(page, "#rack")["width"]; page.focus("#rack-drag"); page.keyboard.press("ArrowRight"); page.wait_for_timeout(100)
    check(page, rect(page, "#rack")["width"] > w0, "rack separator ignores the → key")
    # titles: 2-line clamp + tooltip
    t = js(page, "(a=>a&&{t:a.title,c:getComputedStyle(a.querySelector(':scope>span:not(.st):not(.brn)')).webkitLineClamp})(document.querySelector('.rowi a.item[href^=\"#session/\"]'))")
    check(page, not t or (t["t"] and t["c"] == "2"), "rack titles: no tooltip or no 2-line clamp")
    # under 1180px the rack folds to icons
    page.set_viewport_size({"width": 1024, "height": 768}); page.wait_for_timeout(200)
    check(page, rect(page, "#rack")["width"] <= 80, "1024: rack did not collapse to icons")

PHONES = ["iPhone SE", "Pixel 7"]  # real emulation: mobile UA, touch, DPR, meta viewport (a resized desktop window hides overflow)
ROUTES = ["", "#plan", "#agents", "#agents/new", "#projects", "#guide", "#templates", "#phone"]
# offenders: elements past the screen edge that no clipping/scrolling ancestor contains; screen.width, not innerWidth,
# because a phone widens the layout viewport to fit overflowing content
OVERFLOW = """()=>{const W=screen.width,sel=e=>e.tagName.toLowerCase()+(e.id?'#'+e.id:'')+(typeof e.className=='string'&&e.className.trim()?'.'+e.className.trim().split(/\\s+/).slice(0,3).join('.'):'');
const bad=[];for(const e of document.querySelectorAll('body *')){const r=e.getBoundingClientRect();if(!r.width||r.right<=W+1)continue;
let a=e.parentElement,clip=false;while(a&&a!=document.body){if(/auto|scroll|hidden|clip/.test(getComputedStyle(a).overflowX)){clip=true;break}a=a.parentElement}
if(!clip&&!(e.parentElement.getBoundingClientRect().right>W+1&&e.parentElement!=document.body))bad.push(sel(e)+' (right '+Math.round(r.right)+'px)')}
return {sw:document.scrollingElement.scrollWidth,W,bad:bad.slice(0,3)}}"""

def no_overflow(page, tag):
    o = js(page, OVERFLOW)
    check(page, o["sw"] <= o["W"] and not o["bad"], f"{tag}: horizontal overflow {o['sw']}px > {o['W']}px: {', '.join(o['bad']) or '?'}")

def sessions():
    runs = [r for r in get("/api/runs") if r.get("kind") == "session"]
    return sorted((r["id"] for r in runs), key=lambda i: len(get(f"/api/runs/{i}").get("events", [])), reverse=True)

def mobile(page, sid, dev, others):
    H = page.viewport_size["height"]
    for h in ROUTES + ["#wf/" + w for w in list(get("/api/workflows"))[:1]]:
        page.goto(f"{BASE}/{h}"); page.wait_for_timeout(1000); no_overflow(page, f"{dev} {h or 'home'}")
        if not h:
            page.click(".rack-toggle"); page.wait_for_timeout(300); no_overflow(page, f"{dev} menu open"); page.click(".rack-toggle")
    for s in others:  # long URLs, code, tables, MCP tool names
        page.goto(f"{BASE}/#session/{s}"); page.wait_for_selector(".logbox", timeout=15000); page.wait_for_timeout(800); no_overflow(page, f"{dev} session {s}")
    page.goto(f"{BASE}/#session/{sid}"); page.wait_for_selector(".logbox", timeout=15000); page.wait_for_timeout(500)
    no_overflow(page, f"{dev} session {sid}")
    rows = js(page, "[...document.querySelectorAll('.log .tool,.log .trail')].map(e=>e.getBoundingClientRect().height)")
    if rows: check(page, sum(rows) / len(rows) <= 56, f"{dev}: tool/trail rows average {round(sum(rows) / len(rows))}px > 56")
    comp = rect(page, "#composer")
    check(page, comp and comp["height"] <= .15 * H and comp["bottom"] <= H + 1, f"{dev}: composer {comp and round(comp['height'])}px tall or below the fold")
    js(page, "(()=>{const l=document.querySelector('.logbox');l.scrollTop=0;scrollTo(0,0)})()"); page.wait_for_timeout(300)
    jump = page.query_selector(".jump")
    check(page, jump and jump.is_visible(), f"{dev}: no jump-to-latest control away from the end")
    if jump and jump.is_visible():
        jump.click(); page.wait_for_timeout(500)
        check(page, js(page, "(l=>l.scrollHeight-l.scrollTop-l.clientHeight<80)(document.querySelector('.logbox'))") or js(page, "scrollY+innerHeight>=document.documentElement.scrollHeight-80"), f"{dev}: jump-to-latest did not reach the end")
    d = page.query_selector("details.out")
    if d:
        d.evaluate("e=>e.open=true"); page.wait_for_timeout(2500)
        check(page, js(page, "!!document.querySelector('details.out[open]')"), f"{dev}: an opened output snapped shut on the live redraw")
    small = js(page, "[...document.querySelectorAll('body *')].filter(e=>e.childNodes.length&&[...e.childNodes].some(n=>n.nodeType==3&&n.textContent.trim())&&e.offsetParent&&parseFloat(getComputedStyle(e).fontSize)<12).length")
    check(page, small == 0, f"{dev}: {small} text elements under 12px")
    short = js(page, "[...document.querySelectorAll('a[href],button')].filter(e=>e.offsetParent&&e.getBoundingClientRect().height>0&&e.getBoundingClientRect().height<44&&!e.closest('.logbox,pre,.log,[hidden]')).length")
    check(page, short == 0, f"{dev}: {short} links/buttons under 44px high")
    # composer: chips open + long unbroken text
    page.fill("#msg", "https://github.com/" + "a" * 120 + " " + "palabra " * 40); page.click(".composer .plus"); page.wait_for_timeout(300)
    no_overflow(page, f"{dev} composer with chips + long text")
    comp = rect(page, "#composer"); check(page, comp and comp["bottom"] <= H + 1, f"{dev}: composer pushed below the fold")
    page.fill("#msg", "")
    for sel, what in [(".setbtn", "Session sheet"), ("[data-act=togglePerms]", "permissions sheet")]:  # the second opens from the first
        b = page.query_selector(sel)
        check(page, b and b.is_visible(), f"{dev}: no {what} button")
        if b and b.is_visible(): b.click(); page.wait_for_timeout(400); no_overflow(page, f"{dev} {what}")
    page.reload(); page.wait_for_selector(".logbox", timeout=15000)
    page.set_viewport_size({"width": H, "height": page.viewport_size["width"]}); page.wait_for_timeout(400)
    no_overflow(page, f"{dev} landscape session")
    page.goto(f"{BASE}/"); page.wait_for_timeout(800); no_overflow(page, f"{dev} landscape home")

with sync_playwright() as p:
    try: b = p.chromium.launch(channel="chrome")  # system Chrome first: the bundled build may be missing or stale
    except Exception: b = p.chromium.launch()
    ids = sessions(); assert ids, "no sessions to test against"
    sid = ids[0]; ctx = b.new_context(); page = ctx.new_page(); desktop(page, sid); ctx.close()
    for dev in PHONES:
        ctx = b.new_context(**p.devices[dev]); mobile(ctx.new_page(), sid, dev, ids[1:6]); ctx.close()
    b.close()
for f in FAILS: print("FAIL", f)
if FAILS: sys.exit(1)
print("ok", sid)
