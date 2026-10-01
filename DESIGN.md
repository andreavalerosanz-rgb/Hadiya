---
name: Flows - La ventanilla (admin package)
description: Ask-and-talk assistant as a ticket counter. Tokens below cover Part 2 only (body.adm); Part 1, the dev "cutting bench", records its own tokens in its prose tables.
colors:
  enamel-blue: "#1f4fd1"
  enamel-blue-deep: "#163a9c"
  enamel-blue-lit: "#2a5ae0"
  blue-tint: "#dce5ff"
  key-red: "#d93d2b"
  key-red-deep: "#a32a1b"
  key-green: "#0f8a5f"
  key-green-deep: "#09603f"
  key-amber: "#f2a900"
  key-amber-deep: "#b07b00"
  navy-ink: "#111a2e"
  navy-ink-2: "#26324d"
  laminate-ground: "#e9edf3"
  rack-white: "#f5f7fa"
  thermal-paper: "#fdfcf7"
  laminate-line: "#c4ccd9"
  slate-mute: "#4b556b"
  led-amber: "#ffb43a"
  led-off: "#1e2945"
  ok-green: "#0b7350"
  bad-red: "#b32a1c"
typography:
  display:
    fontFamily: "Atkinson Hyperlegible Next, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "52px"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.02em"
  headline:
    fontFamily: "Atkinson Hyperlegible Next, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "28px"
    fontWeight: 800
    lineHeight: 1.15
  title:
    fontFamily: "Atkinson Hyperlegible Next, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "21px"
    fontWeight: 800
    lineHeight: 1.1
  body:
    fontFamily: "Atkinson Hyperlegible Next, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Atkinson Hyperlegible Next, Atkinson Hyperlegible, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.35
  led:
    fontFamily: "Doto, ui-monospace, monospace"
    fontSize: "32px"
    fontWeight: 800
    lineHeight: 1
rounded:
  sm: "6px"
  md: "10px"
  lg: "12px"
  xl: "14px"
  panel: "18px"
  dispenser: "26px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "10px"
  md: "14px"
  lg: "18px"
  xl: "28px"
  page: "36px"
components:
  dispenser:
    backgroundColor: "{colors.enamel-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.dispenser}"
    padding: "30px 32px 56px"
  key-mail:
    backgroundColor: "{colors.key-red}"
    textColor: "#ffffff"
    rounded: "{rounded.xl}"
    padding: "14px 14px 0"
  key-docs:
    backgroundColor: "{colors.key-green}"
    textColor: "#ffffff"
    rounded: "{rounded.xl}"
  key-cal:
    backgroundColor: "{colors.key-amber}"
    textColor: "{colors.navy-ink}"
    rounded: "{rounded.xl}"
  key-other:
    backgroundColor: "{colors.navy-ink}"
    textColor: "#ffffff"
    rounded: "{rounded.xl}"
  pedir:
    backgroundColor: "{colors.thermal-paper}"
    textColor: "{colors.navy-ink}"
    rounded: "{rounded.lg}"
    height: "64px"
    padding: "0 36px"
  button-primary:
    backgroundColor: "{colors.enamel-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.lg}"
    height: "52px"
    padding: "0 20px"
  button-primary-hover:
    backgroundColor: "{colors.enamel-blue-lit}"
  button-secondary:
    backgroundColor: "#ffffff"
    textColor: "{colors.navy-ink}"
    rounded: "{rounded.lg}"
    height: "52px"
  ticket:
    backgroundColor: "{colors.thermal-paper}"
    textColor: "{colors.navy-ink}"
    rounded: "{rounded.sm}"
    padding: "16px 22px"
  turn-board:
    backgroundColor: "{colors.navy-ink}"
    textColor: "#e6ebf5"
    rounded: "{rounded.panel}"
    padding: "22px 20px 16px"
  stub:
    backgroundColor: "{colors.thermal-paper}"
    textColor: "{colors.navy-ink}"
    padding: "16px 18px 18px"
    height: "188px"
  composer:
    backgroundColor: "{colors.thermal-paper}"
    textColor: "{colors.navy-ink}"
    padding: "14px 36px 16px"
  state-asking:
    backgroundColor: "{colors.key-amber}"
    textColor: "{colors.navy-ink}"
    rounded: "{rounded.pill}"
---

> This file holds two worlds. Part 1 ("the cutting bench", dark, orange rail) serves the **dev** package. Part 2 ("La ventanilla", light, ticket counter) serves the **admin** package, applied when `body` has class `adm` (`/api/me` package is `admin`). The YAML frontmatter above describes Part 2 only.

# Part 1 - dev package

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

---

# Part 2 - admin package

# Design System: Flows, "La ventanilla"

Recorded from the built `index.html` (2026-10-01): the `body.adm` CSS block and the `adm*` module at the end of the script. Scoped entirely to `body.adm`; the dev look is untouched. Frontmatter tokens are normative; the prose names them and gives roles.

## Overview

**Creative North Star: "The Ticket Counter"**

Asking is taking a number at a counter: you say what you need, get a ticket, someone attends you, and you are called when it is your turn to decide. Audience is office staff with no technical background, on a desk PC in daylight or a phone at 390px. The surface refuses the centered chatbot box with suggestion chips; the first thing on home is a physical dispenser with four keys and a slot, and a lit turn board beside it.

The world is light and laminated: a cool laminate ground, an enamel-blue dispenser body, thermal-white tickets with a torn bottom edge, and one navy LED board with dot-matrix numbers. Type is a hyperlegible humanist sans at generous sizes (18px base). Everything is Spanish, in plain words; the product never shows tool names, models, folders, or permission jargon.

**Key Characteristics:**
- Colour is job-coded: each errand has one key colour (Correo red, Documentos green, Agenda amber, Otra cosa navy) that follows it from key to ticket chip to log icon.
- State is always icon plus word, never colour alone.
- Pressable things have a thick bottom edge (4-6px darker enamel) like a physical key; flat things do not.
- Tickets carry a big tabular number; the number is the person's handle for a request ("Turno 014").
- Minimum touch target about 48px; focus ring is 3px navy (white on blue surfaces).

## Colors

A cool blue-grey counter with four saturated key colours and one amber LED; the blue is the brand, the amber is the "you are needed" signal.

### Primary
- **Enamel Blue** (`enamel-blue`): dispenser body, primary buttons, the "Nueva petición" button, links on paper (deep variant), caret and accent-color, "Atendiendo" state, selected stub and selected option ring.
- **Enamel Blue Deep** (`enamel-blue-deep`): the extruded bottom edge of blue keys and buttons, ticket numbers in the rack, link text on white.
- **Enamel Blue Lit** (`enamel-blue-lit`): hover of blue buttons.
- **Blue Tint** (`blue-tint`): text on blue (lede, hints) and the person's own message bubble.

### Secondary (errand keys, each with a `-deep` edge)
- **Key Red** (`key-red`): Correo. Also the active mic.
- **Key Green** (`key-green`): Documentos.
- **Key Amber** (`key-amber`): Agenda, and the "Te necesita" pill, alert band, ask bar and text selection. Text on amber is always Navy Ink.
- **Navy Ink** (`navy-ink`): Otra cosa key, the turn board, toasts, default text.

### Neutral
- **Laminate Ground** (`laminate-ground`): page ground and theme-color.
- **Rack White** (`rack-white`): the sidebar.
- **Thermal Paper** (`thermal-paper`): tickets, stubs, composer, decision dialog body, the Pedir key, example chips; warm off-white against the cool ground.
- **Laminate Line** (`laminate-line`) and **Slate Mute** (`slate-mute`): hairlines and dashed perforations; secondary text and times.
- **LED Amber** / **LED Off** (`led-amber`, `led-off`): lit and unlit segments of the dot-matrix number.
- **OK Green** / **Bad Red** (`ok-green`, `bad-red`): text-grade "Listo" and "No se pudo" (darker than the key greens/reds for AA on light grounds).

### Named Rules
**The Key-Colour Rule.** An errand has exactly one colour from the four keys; it is reused for that errand's chip and log icon and nowhere else. Do not use key colours as status colours.
**The Amber Means You Rule.** Amber on a surface means a person is needed. Do not use it decoratively.
**The Word Beside Colour Rule.** Every state is an icon plus its word; colour only reinforces.

## Typography

**Display / Body Font:** Atkinson Hyperlegible Next (fallbacks Atkinson Hyperlegible, system-ui, sans-serif), weights 400-800, loaded from Google Fonts when the admin package starts.
**LED Font:** Doto 800 (fallback ui-monospace), for LED numbers only.

**Character:** Open, unambiguous letterforms at large sizes; weight 800 does all the emphasis work, so there is no second family. Doto is the one ornament, reserved for ticket numbers on the board.

### Hierarchy
- **Display** (800, 52px, 1.05, -0.02em; 38px under 820px): the dispenser question "¿Qué necesitas?"; help page title 46px.
- **Headline** (800, 28-30px, 1.15-1.2): conversation header line, stubs heading, dialog band title; 23px on phones.
- **Title** (800, 21-24px): turn board heading, key names (21px), Pedir (24px), dialog legends (21px).
- **Body** (400-600, 18px, 1.55): base; assistant text 19px / 1.6, max 68ch; ticket text 19px.
- **Label** (700, 14-17px): times, state words, column heads (14px uppercase, +0.06em, board only), ticket "Turno" (17px). Tabular numerals on every number.
- **LED** (Doto 800, 32px; 72px in the empty board; 28 / 60px on phones): a ghost "888" in LED Off sits behind the lit digits.

### Named Rules
**The One Weight Rule.** Emphasis is weight 800 versus 400-600 in the same family; do not add a display face.
**The LED Only Rule.** Doto appears only inside `.a-led` number displays.

## Layout

Rack sidebar 280px plus main. Home is a two-column grid (`1.7fr` dispenser, `minmax(360px, 1fr)` turn board, 28px gap, 36px page padding, max 1500px) with the stubs grid spanning the full width below. Between 821px and 1100px the board drops under the dispenser; at 820px and below (or short landscape) the rack becomes a top bar with a menu toggle, padding drops to 14px, and everything is one column.

The dispenser is a container (`container-type: inline-size`): the four keys are a row of four, and at 760px container width or less they become a 2x2 grid, the Pedir button takes a full row, and the Adjuntar label shortens. This follows the block, not the viewport.

The turn board has fixed columns, 64px (Nº) / flexible (Asunto) / 114px (Estado), 112px on phones; rows change, columns never move. Stubs are a whole-cell grid, `auto-fill minmax(230px, 1fr)` (160px on phones), cells divided by 2px dashed perforation lines, min height 188px.

Conversation column is max 920px centered; the header line is sticky at the top and the composer is sticky at the bottom (inner width 848px). Spacing rhythm: 8, 10, 14, 18, 28, 36px. Right-align every time stamp.

## Elevation & Depth

Hybrid: physical objects (dispenser, board, dialog, ticket) get one soft, large, low-opacity navy shadow; pressable objects get depth from a solid darker bottom edge instead of a shadow.

### Shadow Vocabulary
- **Dispenser lift** (`box-shadow: 0 24px 38px -24px rgba(17,26,46,.6)`, plus a 6px deep-blue bottom border): the block on home.
- **Board lift** (`0 18px 30px -20px rgba(17,26,46,.7)`): the LED board.
- **Ticket drop** (`filter: drop-shadow(0 8px 12px rgba(17,26,46,.2))`): thermal tickets, applied as a filter so it follows the torn edge.
- **Composer lift** (`0 -14px 24px -14px rgba(17,26,46,.28)`): sticky bottom composer.
- **Dialog** (`0 30px 70px rgba(17,26,46,.45)`) over a `rgba(17,26,46,.55)` backdrop.
- **Key press edge** (4-6px solid deep colour bottom border): keys and primary buttons; presses down 3px on `:active`.

### Named Rules
**The Press Edge Rule.** If you can press it and it is a primary object, it has a solid bottom edge in the deep shade of its colour. Shadows are for objects you read, not objects you press.

## Shapes

Soft enamel corners: 12px buttons, 14px keys, 18px board, 26px (top) dispenser, 16-20px dialogs, 10px chips and options, pill (999px) only for the "Te necesita" state. Tickets have a 6px top radius and a torn bottom edge cut with a conic-gradient mask (9px teeth). Perforation is a recurring form: 2px dashed `laminate-line` for the ticket header rule, the stubs grid, and letter rows; a punched stub has a 24px hole (inset shadow, ground colour). The dispenser has a dark slot (14px, 72% wide, max 380px) at its bottom edge. Icons are authored inline SVG, 2-2.2 stroke.

## Components

### Dispenser and keys
The blue block that owns the top of home: headline, lede, a thermal-paper textarea (20px, inset shadow), four keys, an examples tray, then the action bar. A key is a coloured tile with icon, name (21px, 800, no wrapping) and a paper-coloured strip carrying a short plain label ("Resumir, buscar, contestar"). Keys toggle (`aria-pressed`): pressed shows a blue plus white double ring and opens a tray of example sentences; choosing one fills the textarea. Hover lifts 2px (hover-capable devices only); active presses down 3px.

### Pedir
The dispenser's one action: paper-coloured, 64px tall, 24px/800, a ticket icon in blue, with a 5px grey-blue bottom edge. Disabled/busy is 60% opacity. Ctrl/Cmd+Enter also presses it. Adjuntar and the mic are ghost buttons (white outline on blue).

### Buttons
- **Primary** (`button-primary`): enamel blue, white 18px/700, 52px min height, 12px radius, 4px deep bottom edge.
- **Secondary**: white with a 2px line border, border goes navy on hover.
- **Quiet**: text-only, underlined, 600; for "Parar" and "Decide tú".
- **Ghost**: white outline, only on blue surfaces.

### Printed ticket and the signature interaction
A thermal-paper slip: "Turno" plus a 46px number at left, time at right (right-aligned), a dashed rule, the errand chip, the request text at 19px. On Pedir the ticket prints from the dispenser slot: it slides down 700ms (`cubic-bezier(.16, 1, .3, 1)`), holds 150ms, then the page navigates to the conversation. With reduced motion it appears without sliding. The same ticket (no animation) heads every conversation and renders the three help steps.

### LED turn board
Navy panel titled "Turnos": a header row (Nº / Asunto / Estado) then one row per live request, ordered Te necesita, Atendiendo, En espera, Listo, newest first within each. Each row: LED number, subject (two-line clamp) with "errand · hace N min", and the state mark. "Te necesita" rows get a lighter navy fill. On a quiet day the board shows a 72px LED with the next number and a sentence: "Tu próximo número será el 004".

### Stubs grid
"Tus resguardos": finished or paused requests as whole cells with number (30px), right-aligned age, errand chip, two-line subject, and state at the bottom. Completed ("Listo") stubs are punched with a hole; paused and failed ones are not.

### Conversation header guide line
A sticky line that always names where you are: "Turno 014 · Correo · Te necesita" (30px, state at 24px), with "Parar" at right while working or asking. A status line under the log restates the state in a full sentence.

### Plain-language activity lines
Each tool action collapses to one line: an errand-coloured icon square plus a Spanish verb phrase ("Buscando en tu correo: «Presupuesto»"); subagents are "Un ayudante se encarga de: ...". Tool results, costs and raw output are never shown. The person's message is a tint bubble labelled "Tú"; the assistant's text is open prose (no bubble) with a small markdown subset.

### Composer
Sticky paper panel: label "Responder o pedir algo más", textarea, Adjuntar and mic (secondary) at left, Enviar (primary) at right. When the state is Listo the panel gains a 4px OK Green top rule. On phones the labels hide and the buttons become icons plus a full-width Enviar.

### Decision dialog (questions and permissions)
The only modal: a native dialog, paper body under a blue band ("Necesito que decidas", turn and errand below). Questions are large option cards (radio or checkbox in a 26px box, plus "Otra cosa" with a text field); a footer offers "Decide tú", "Más tarde" and "Enviar respuesta". Permissions ask a plain question ("¿Puedo enviar este correo?") above a letter card (Para / Asunto / body, dashed rows), an optional reason field for a No, and the buttons "No", "Sí, adelante" and a quiet "Sí, y no vuelvas a preguntar en esta petición". On other pages an amber alert band or ask bar links back to the decision.

### Help tickets
"Cómo funciona": three ticket slips (Paso 1-3) in a row, then two white cards "Qué puede hacer" (OK Green check) and "Qué no puede hacer" (Bad Red x), then a primary "Hacer una petición" button.

### State vocabulary
Always icon plus word: **Atendiendo** (blue, pulsing dot), **Te necesita** (amber pill, pulsing bell), **Listo** (OK Green, check), **Pausado · escribe para seguir** (slate, pause), **No se pudo** (Bad Red, x), **En espera** (slate, clock; usage limit reached). A lead that ended after finishing its turn reads Listo, not Pausado.

### Motion
State motion only: 1.6s opacity pulse on Atendiendo and Te necesita icons, key lift/press, 0.15s colour transitions, and the ticket slide. All CSS animation and transition is disabled under `prefers-reduced-motion`; the ticket slide is skipped in script.

### Copy
Spanish, informal "tú", plain words. Say what is happening in the person's terms (correo, documentos, agenda), not tool, model, folder or permission names. Errors say what to do next ("Escribe abajo para intentarlo otra vez"). Spanish date and time via `es-ES`; relative ages "hace 5 min", "ayer".

## Do's and Don'ts

### Do:
- **Do** pair every state with its icon and word, and put the errand key colour on the chip and the log icon for that errand.
- **Do** give primary pressable objects the solid deep-colour bottom edge; give read-only objects the soft shadow.
- **Do** keep the board's columns fixed and only change rows; keep times right-aligned on tickets, stubs and the sidebar.
- **Do** keep text on amber in Navy Ink and text on thermal paper in Navy Ink or Slate Mute.
- **Do** keep targets at least about 48px and show the focus ring (3px navy; white on blue).
- **Do** use dashed perforation for dividers inside ticket-like objects.

### Don't:
- **Don't** show tool names, model names, paths, costs or permission jargon to this audience; translate them to a plain Spanish line.
- **Don't** convey state by colour alone.
- **Don't** use key colours for anything but their errand, or amber for anything but "a person is needed".
- **Don't** use Doto outside LED numbers, or add a second text face.
- **Don't** put admin rules on `:root`; they stay scoped to `body.adm` so the dev bench is unaffected.
- **Don't** open a modal for anything but a blocking decision.

### Observed in the build, not canonized
Raw hex values used once or twice outside the token set (board text tints `#e6ebf5`, `#c9d3e6`, `#a9b6cf`, `#9fb0cf`, `#a9c1ff`, `#7fe0b4`; board fills `#18233d`, `#1a2541`; `#aab5ca`, `#5b6477`, `#fbe9e6`, `#f1f5ff`, `#0a1430`) are drift to fold into tokens, not new palette entries. The login page (`LOGIN_HTML`) is shared before sign-in and is still English and in the dev look. The two fonts load from Google Fonts at runtime with no local copy; offline the fallback is system-ui and ui-monospace.
