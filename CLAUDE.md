# Flows: working rules (fewer tokens first)

- Token Optimizer plugin is on (hooks run by themselves). Per person: `deploy/setup-token-optimizer.sh`. Check: `/token-optimizer:quick`; zombies: `/token-optimizer:health`.
- Flows compacts at 200k (`CLAUDE_CODE_AUTO_COMPACT_WINDOW` in `launch()`); keep it. Resume old work with `/token-optimizer:resume-checkpoint`, not by re-reading the repo.
- Find code with the codebase-memory graph (`search_graph`, `get_code_snippet`) before reading whole files. `server.py` and `index.html` are huge: read ranges.
- Delegate to a subagent only when it pays (parallel, independent, big output); cheapest model that does the job.
- Short answers, no recap of the diff. Screenshots only when the change is visual.
