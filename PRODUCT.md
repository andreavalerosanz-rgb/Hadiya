# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
One person: a WordPress developer (Matteria) working on a Linux desktop, building LAMP sites (WordPress themes, Bootstrap, Sass) from Figma designs. They run Flows locally next to their editor and a local WP install, launch agent work, then glance back to monitor or steer it while doing other work.

## Product Purpose
Flows is a local control room for Claude Code running on the user's own Claude subscription. It lets them compose multi-step agent workflows from ready-made task blocks, launch live orchestrator sessions where a lead agent fans work out to parallel subagents, and monitor/steer everything as it runs ("add more agents", "skip the footer"). Success: a Figma frame becomes a working, reviewed WP template with little typing, and the user always knows what each agent is doing and what needs them.

## Positioning
It drives the real `claude` CLI headlessly (subscription auth, the user's installed plugins and MCP servers such as Figma), so every block is a genuine Claude Code session in a real project folder, not a toy sandbox. Parallelism is conversational: the lead agent can be told to go faster mid-run.

## Operating Context
- Runs at http://localhost:8787 from `~/Desktop/flows` (python3 stdlib server + one index.html).
- Projects are WP themes, e.g. `~/Desktop/matteria/web/matteria.si/wp-content/themes/matteria`, `~/Desktop/PHH/web/wp-content/themes/phhtheme`.
- Figma access via the official Figma MCP (`mcp__plugin_figma_figma`), authenticated once via `/mcp` in the CLI.
- Typical build tools: npm scripts, sass, php -l, git.

## Capabilities and Constraints
- Workflows: ordered steps; each step = prompt with `{{input}}` / `{{prev}}`, model, permission mode, allowed tools, working dir. A step answering `FAIL: …` stops the run. A step may be a "team" step that uses subagents.
- Orchestrator sessions: long-lived lead agent via stream-json stdin; subagents launched with the Agent tool run in the background; user can message at any time; stopped sessions resume via `--resume`.
- Cost shown is the CLI's API-equivalent estimate, not a real charge on the subscription.
- Local-only, single user; no auth. Server binds 127.0.0.1 and requires an `X-Flow` header on writes.
- No build step, no dependencies: plain HTML/CSS/JS in one file.

## Evidence on Hand
Real workflows and runs in `data/`. No testimonials, users or metrics exist; none should be invented.

## Product Principles
1. Less typing: presets, toggles and blocks before raw prompts and tool strings; raw fields stay available under "advanced".
2. Plain language for power: permissions read as capabilities ("Can edit files", "Can run the build"), never only as CLI flags.
3. Always show what's happening and what needs the user.
4. Safe by default: read-only unless a block clearly needs to edit or run commands.
