"""python3 scripts/test_projects.py — projects: git root vs plain folder, stable unique slugs, context file place."""
import os, shutil, sys, tempfile
from pathlib import Path
home = Path(tempfile.mkdtemp())
os.environ["HOME"], os.environ["FLOWS_DATA"] = str(home), str(home / "data")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server as s

repo, plain = home / "work" / "My Repo", home / "notes"
(repo / ".git").mkdir(parents=True); (repo / "src" / "deep").mkdir(parents=True); plain.mkdir()
assert s.project_of(str(repo / "src" / "deep")) == str(repo) == s.project_of(str(repo))
assert s.project_of(str(plain)) == str(plain)
(repo / "sub").mkdir(); (repo / "sub" / ".git").write_text("gitdir: ..")  # a submodule/worktree is its own project
assert s.project_of(str(repo / "sub")) == str(repo / "sub")
a, b = s.project_slug(str(repo)), s.project_slug(str(home / "other" / "My Repo"))
assert a.startswith("my-repo-") and a != b and a == s.project_slug(str(repo)), (a, b)
assert s.project_slug("/") .startswith("root-")
assert s.project_file(str(repo)) == home / ".claude" / "flows-projects" / f"{a}.md"
r = {"id": "x", "kind": "session", "owner": None, "started": 1, "status": "idle", "events": [], "config": {"cwd": str(repo / "src")}}
s.runs["x"] = r
assert s.run_project(r) == str(repo) and s.projects()[0]["sessions"][0]["id"] == "x"
assert s.projects(a)["path"] == str(repo)
(repo / "style.css").write_text("/*\nTheme Name: X\n*/")
assert s.wp_flag(str(repo)) == {"on": True, "auto": True, "set": False, "path": str(repo)}
s.wp_set(str(repo), False)
assert not s.wp_flag(str(repo))["on"] and s.wp_flag(str(repo))["set"] and not s.wp_flag(str(plain))["on"]
shutil.rmtree(home)
print("ok")
