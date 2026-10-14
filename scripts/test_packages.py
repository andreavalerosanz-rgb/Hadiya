"""python3 scripts/test_packages.py — the admin package clamps every claude command line."""
import os, sys
os.environ["FLOWS_PACKAGE"] = "admin"  # pre-rename name still read
os.environ["HADIYA_DATA"] = "/tmp/hadiya-test-packages"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import server as s

cmd = s.fence(["claude", "-p", "--permission-mode", "bypassPermissions",
                     "--allowedTools", "Agent,Task,Bash,Read,mcp__plugin_figma_figma,mcp__claude_ai_Gmail__get_thread",
                     "--mcp-config", "{}", "--model", "haiku"])
note = "--append-system-prompt=" + s.PACKAGES["admin"]["note"]
assert cmd == ["claude", "-p", "--permission-mode=default", "--allowedTools=Agent,Task,mcp__claude_ai_Gmail__get_thread",
               "--model", "haiku", "--tools=Agent,ToolSearch,AskUserQuestion", note], cmd
cmd = s.fence(["claude", "--append-system-prompt", "ORCH"])
assert cmd == ["claude", "--append-system-prompt=ORCH\n\n" + s.PACKAGES["admin"]["note"], "--tools=Agent,ToolSearch,AskUserQuestion"], cmd
assert s.allowed("mcp__claude_ai_Google_Drive__create_file") and s.allowed("AskUserQuestion")
assert not any(s.allowed(t) for t in ("Bash", "Edit", "mcp__claude_ai_Trello__x", "mcp__playwright__browser_click"))
os.environ["HADIYA_PACKAGE"] = "dev"  # the new name wins over FLOWS_PACKAGE
assert s.fence(["claude", "--allowedTools", "Bash"]) == ["claude", "--allowedTools", "Bash"]
os.environ["HADIYA_PACKAGE"] = "typo"
assert s.package() == "admin"
print("ok")
