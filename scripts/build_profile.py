#!/usr/bin/env python3
"""Mine Claude/Hadiya logs into ~/.claude/flows-assistant/stats.md (raw input for the hand-curated profile.md).
Stdlib only. Never writes emails/tokens: prompts are scrubbed before sampling."""
import json, re, glob, os, collections
H = os.path.expanduser("~")
OUT = f"{H}/.claude/flows-assistant"
os.makedirs(OUT, exist_ok=True)
SECRET = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\b(sk|ghp|xox\w)-[\w-]+|(?i:(pass(word)?|pw|token|secret|clave)\s*[:=]?\s*\S+)")
CORR = re.compile(r"\b(no quiero|te dije|ya te|no hagas|nunca|siempre|don't|do not|i said|no lo|otra vez|again|stop|sin )\b", re.I)
TOPICS = {k: re.compile(v, re.I) for k, v in {
    "git/commit": r"\bcommit|\bpush\b|\bmerge\b|\bbranch|\brama\b",
    "deploy stage/prod": r"\bdeploy|\bstage\b|\bstaging\b|\bprod\b",
    "UI/mobile": r"\bmobile|\bmóvil|\bresponsive|\bscreenshot|\bdiseño|\bdesign",
    "wordpress": r"\bacf\b|\bwpml\b|\bwordpress\b|\bwp-|elementor",
    "agus": r"\bagus|agust[ií]n",
    "gmail": r"\bgmail|\bcorreo|\bemail|\bdraft|\bborrador",
    "calendar": r"\bcalendar|\bagenda|\breunión|\bmeeting",
    "translate": r"\btraduc|\btranslate|\bcatal[àa]|\bCA\b",
    "usage limit": r"usage limit|limit reached|resets? at",
    "subagents": r"\bsubagent|\bagentes?\b|\bparalel",
    "trello": r"\btrello",
    "figma": r"\bfigma",
    "short answers": r"\bcorto|\bbreve|\bshort|\bconcis|sin recap|\bresumen",
}.items()}
def proj(d):
    d = os.path.basename(d).lower()
    for k, n in [("matteria","Matteria"),("bfs","BFS"),("flows","Hadiya"),("phh","PHH"),("sonora","Sonora"),("drzhang","Dr. Zhang"),("residus","Residus"),("vikunja","Vikunja")]:
        if k in d: return n
    return "other"
prompts, seen = [], set()
def add(p, t):
    t = t.strip()
    if len(t) < 3 or t.startswith(("<", "Caveat", "[Request")) or (p, t) in seen: return
    seen.add((p, t)); prompts.append((p, t))
for f in glob.glob(f"{H}/.claude/projects/*/*.jsonl"):
    p = proj(os.path.dirname(f))
    for line in open(f, errors="ignore"):
        try: o = json.loads(line)
        except Exception: continue
        if o.get("type") == "user" and not o.get("isMeta") and not o.get("isSidechain"):
            c = o.get("message", {}).get("content")
            if isinstance(c, list): c = " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
            if isinstance(c, str): add(p, c)
for f in glob.glob("/home/andrea/Desktop/flows/data/runs/*.json"):
    try: r = json.load(open(f))
    except Exception: continue
    for e in r.get("events", []):
        if e.get("type") == "input" and isinstance(e.get("text"), str): add(proj(r.get("name") or r.get("cwd") or ""), e["text"])
out = [f"# raw stats ({len(prompts)} unique prompts)", "", "## per project"]
out += [f"- {k}: {v}" for k, v in collections.Counter(p for p, _ in prompts).most_common()]
out += ["", "## topics (prompts matching)"]
out += [f"- {k}: {sum(1 for _, t in prompts if rx.search(t))}" for k, rx in TOPICS.items()]
es = sum(1 for _, t in prompts if re.search(r"\b(que|el|la|quiero|para|con)\b", t, re.I))
out += ["", f"## language: ~{es} prompts with Spanish stopwords; median length {sorted(len(t) for _,t in prompts)[len(prompts)//2]} chars"]
corr = [t for _, t in prompts if CORR.search(t) and len(t) < 400]
out += ["", f"## corrections ({len(corr)} short prompts matched); sample", *[f"- {SECRET.sub('[x]', t)[:220]!r}" for t in corr[:150]]]
open(f"{OUT}/stats.md", "w").write("\n".join(out))
print(f"{len(prompts)} prompts, {len(corr)} corrections -> {OUT}/stats.md")
