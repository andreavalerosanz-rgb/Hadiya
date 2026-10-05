# Design: Flows ("the cutting bench")

Recorded from the built `index.html` (2026-09-28). Operate-mode tool, single dark world.

## World
A film cutting bench flattened into a screen. Workflows and sessions are strips of film on one
perforated **rail**; steps and subagents are **frames**; presets are **trims** hung on pins in a bin.

## Palette (tokens on `:root`)
| token | value | role |
|---|---|---|
| `--ink` | `#0d0d0d` | ground, frames, text on orange |
| `--char` / `--panel` / `--spool` / `--line` | `#151515` `#1b1b1b` `#2b2b2b` `#3a3a38` | rack, trims, hairlines |
| `--flag` / `--flag-deep` | `#ff5a1f` `#e2470f` | the only accent: rail field, primary action, live/attention state |
| `--punch` / `--punch-2` | `#f4f2ee` `#e6e3dd` | punched windows: all running copy, forms, logs |
| `--edge` / `--mute` / `--ink-mute` | `#ecebe7` `#a6a39c` `#57534d` | text on black / secondary on black / secondary on white |

Rules: text on orange is always `--ink` (white on orange fails contrast). Anything you read at length sits in a white window.

## Type
- `Barlow Condensed` 500–700, uppercase, +0.06–0.12em tracking: labels, titles, buttons, status.
- `Barlow` 400–600: body copy and agent text.
- System mono: prompts, paths, tool args, output only.

## Components
- **Rail**: grain-orange field, sprocket rows top and bottom (`--perf`). `.rail.live` rolls the sprockets: the one motion that means "something is running".
- **Frame**: ink cell holding a white `.win` (icon, title, meta, status line). States are marks, never just colour:
  done = orange grease check · running = orange gate band · failed = hatched window + label ·
  idle = folded tape flag "YOUR TURN" · queued/stopped = dimmed window with a punched corner. Selected = white ring.
- **Trim**: a hanging preset (pin, film with sprocket edges, white window); swings on hover; click splices it in.
- **Buttons**: `.btn-p` orange tape with sprocket dots (one per view), `.btn-s` orange outline, `.btn-q` hairline, `.ic` icon square.
- **Capability tape** (`.capt`): plain-language permission checkbox; checked = ink ring + orange box. Danger variant is hatched.
- **Stepper**: −/+ with a big condensed numeral (parallel agents).
- **Log**: YOU bubbles in ink, tool rows (icon + name + arg), collapsible outputs, subagent hand-off lines.
- **Icons**: authored inline SVG, 24 grid, 1.75 stroke, round caps (`P` map in the script). No emoji.

- **Splice point** (`.splice`): round ink/orange **+** between frames; opens the step picker drawer at that position.
- **Legend** (`.legend`): one line under every rail naming the marks, led by what clicking does.
- **Decision popup** (`dialog.decide`): native modal, punched-white body under a mini orange rail band. Questions render as option tapes (radio or checkbox, plus "Something else"); permission checks show the exact command with Deny / Always allow in this session / Allow once. The only modal in the app, because the agent is blocked until you answer.
- **Alert** (`.alert`): full-width orange grain band linking to a session that needs a decision; the tab title shows the count too.
- **Run bar / composer**: sticky bottom panel for the action that moves work forward (Run, Send). It turns orange-ringed on "your turn" and is not sticky on phones.
- **Screenshot strip** (`.shots`): Playwright captures as small ink-framed thumbnails.

## Motion
Only state motion: sprocket roll (live), blinking status mark, trim swing, 2px frame lift. All off under `prefers-reduced-motion`.

## Layout
Rack sidebar 264px + main; rail bleeds full width; windows max 1096px. Under 820px the rack stacks on top, and the rail and trims scroll horizontally.
