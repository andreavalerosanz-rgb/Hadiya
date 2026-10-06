"""python3 scripts/test_agents.py — agents editor: through symlinks, keeps unknown keys, no path tricks."""
import os, shutil, sys, tempfile
from pathlib import Path
home = Path(tempfile.mkdtemp())
os.environ["HOME"], os.environ["FLOWS_DATA"] = str(home), str(home / "data")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server as s

repo, d = home / "repo", home / ".claude" / "agents"
repo.mkdir(); d.mkdir(parents=True)
(repo / "a.md").write_text("---\nname: a\ndescription: >\n  Use for x: y\n  and z\nmodel: haiku\neffort: high\nskills:\n  - k\n---\nDo it.\n")
(d / "a.md").symlink_to(repo / "a.md")
assert s.list_agents(None) == [{"name": "a", "description": "Use for x: y and z", "model": "haiku", "tools": "",
                                "skills": ["k"], "file": str(repo / "a.md"), "link": True}]
s.agent_api(None, "PUT", "a", {"description": "Use for: q", "tools": "Read, Bash(git log:*)", "model": "", "skills": [], "body": "New"})
assert (d / "a.md").is_symlink() and s.front((repo / "a.md").read_text()) == (
    {"name": "a", "description": "Use for: q", "effort": "high", "tools": "Read, Bash(git log:*)"}, "New\n")
s.agent_api(None, "PUT", "b", {"new": True, "description": "B", "body": ""})  # new ones land in the repo, linked
assert (d / "b.md").resolve() == repo / "b.md"
for bad in ("../x", "A", "a.md", ""):
    try:
        s.agent_api(None, "GET", bad, {}); raise AssertionError(bad)
    except ValueError:
        pass
try:
    s.agent_api(None, "PUT", "b", {"new": True, "description": "again"}); raise AssertionError("dup")
except ValueError:
    pass
assert s.agent_api(None, "DELETE", "b", {}) == {"ok": True, "kept": str(repo / "b.md")} and (repo / "b.md").exists()
try:
    s.agent_api(None, "GET", "b", {}); raise AssertionError("gone")
except KeyError:
    pass
shutil.rmtree(home)
print("ok")
