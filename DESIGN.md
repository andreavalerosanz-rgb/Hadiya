---
name: Flows - Flows on paper (admin package)
description: Calm, light, one-column ask-and-talk assistant in plain Spanish; paper ground, white cards, ink text, Flows orange only where action or attention lives. Tokens below cover Part 2 only (body.adm); Part 1, the dev "cutting bench", records its own tokens in its prose tables.
colors:
  paper-ground: "#f4f2ee"
  card-white: "#ffffff"
  paper-line: "#e6e3dd"
  ink: "#1a1a1a"
  ink-mute: "#57534d"
  ink-wash: "rgba(26, 26, 26, 0.1)"
  flag-orange: "#ff5a1f"
  flag-orange-deep: "#e2470f"
  flag-orange-hover: "#ff7038"
  bench-ink: "#0d0d0d"
typography:
  display:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "44px"
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "24px"
    fontWeight: 700
    lineHeight: 1.2
  title:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.35
  body:
    fontFamily: "Barlow, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 400
    lineHeight: 1.55
  label:
    fontFamily: "Barlow Condensed, Arial Narrow, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.1em"
  action:
    fontFamily: "Barlow Condensed, Arial Narrow, system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "0.08em"
rounded:
  sm: "10px"
  md: "12px"
  tail: "4px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  page: "48px"
components:
  button-primary:
    backgroundColor: "{colors.flag-orange}"
    textColor: "{colors.bench-ink}"
    typography: "{typography.action}"
    rounded: "{rounded.md}"
    height: "48px"
    padding: "0 20px"
  button-primary-hover:
    backgroundColor: "{colors.flag-orange-hover}"
  pedir:
    backgroundColor: "{colors.flag-orange}"
    textColor: "{colors.bench-ink}"
    typography: "{typography.action}"
    rounded: "{rounded.md}"
    height: "56px"
  button-secondary:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "48px"
    padding: "0 20px"
  button-small:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "44px"
    padding: "0 12px"
  card:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
  chip-idea:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    height: "56px"
    padding: "0 14px"
  request-row:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    height: "64px"
    padding: "14px 16px"
  bubble-you:
    backgroundColor: "{colors.ink-wash}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "10px 14px"
  bubble-say:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
    padding: "14px 16px"
  composer:
    backgroundColor: "{colors.card-white}"
    textColor: "{colors.ink}"
    padding: "10px 16px"
  state-flag:
    backgroundColor: "{colors.flag-orange}"
    textColor: "{colors.bench-ink}"
    typography: "{typography.label}"
    padding: "5px 9px 9px"
---

> This file holds two worlds. Part 1 ("the cutting bench", dark, orange rail) serves the **dev** package. Part 2 ("Flows on paper", light, one column) serves the **admin** package, applied when `body` has class `adm` (`/api/me` package is `admin`); it borrows the bench's brand parts (orange, Barlow, reel logo, state marks, one perforated strip) and nothing else. The YAML frontmatter above describes Part 2 only.

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

# Design System: Flows on paper

Recorded from the built `index.html` (2026-10-02): the `body.adm` CSS block and the `adm*` functions at the end of the script. Everything is scoped to `body.adm`; the dev look is untouched. Frontmatter tokens are normative; the prose names them and gives roles. Paper values are the `--p-*` custom properties on `body.adm`; orange and fonts come from the shared `:root` tokens of Part 1 (`--flag`, `--flag-deep`, `--cond`, `--body`, `--perf`, `--grain`).

## Overview

**Creative North Star: "Flows on Paper"**

The same brand made calm and light. A warm paper ground, white cards with hairlines, ink text, and one orange that only ever says "press this" or "this needs you". Audience is office staff with no technical background on a phone or a desk PC; the product is a single column with one obvious action. It refuses both the dark techy bench and a generic app kit: no sidebar, no dashboards, no coloured categories.

The film world survives as a few brand parts, not as scenery: the reel logo, Barlow with Barlow Condensed caps for small labels, the Flows state marks (grease-pencil check, folded tape flag, hatch), and exactly one perforated orange strip under the top bar. Copy is Spanish, informal "tú", plain words; the product never shows tool names, models, folders, costs or permission jargon.

**Key Characteristics:**
- One column, mobile-first; on desktop the same column centered at about 680px.
- Orange appears only on the primary action, the "Te necesita" flag, focus, text selection and the perforated strip.
- State is always a mark plus a word, never colour alone.
- Flat paper: hairlines and a very soft card shadow; no hard offsets, no glow.
- Targets 44-56px; focus ring is 3px deep orange.

## Colors

A warm paper neutral with ink, and one orange held back for action and attention.

### Primary
- **Flag Orange** (`flag-orange`): primary button fill (Pedir, Enviar, Enviar respuesta, Sí adelante, Hacer una petición), the "Te necesita" tape flag, the unread dot on the menu button, the perforated strip, text selection. Text on it is always Bench Ink (`bench-ink`), never white.
- **Flag Orange Deep** (`flag-orange-deep`): focus ring (3px, 2px offset), caret, the dashed drop outline when dragging a file.
- **Flag Orange Hover** (`flag-orange-hover`): hover of the primary button.

### Neutral
- **Paper Ground** (`paper-ground`): page ground, top bar, sticky conversation header, theme-color.
- **Card White** (`card-white`): every card, chip, bubble, option, the composer and the dialog.
- **Paper Line** (`paper-line`): hairline borders and row dividers.
- **Ink** (`ink`): all text, the check, hatch and dash marks, selected borders, toasts. **Ink Mute** (`ink-mute`): secondary text, times, icons at rest, small labels.
- **Ink Wash** (`ink-wash`): the person's own message bubble.
- **Bench Ink** (`bench-ink`): the shared dev ink; used only for text on orange.

### Named Rules
**The Orange Is Action Rule.** Orange says "press" or "you are needed", or marks focus. Do not use it for decoration, headings, links, or secondary buttons, and keep the perforated strip as the single film echo.
**The Word Beside Mark Rule.** Every state is a mark plus its word; colour never carries state.

## Typography

**Body Font:** Barlow (400-600, fallback system-ui, sans-serif); headings use its 700.
**Label/Action Font:** Barlow Condensed (500-700, fallback Arial Narrow), uppercase with tracking, for small labels, state words, the primary button and the logo only.
Both load from Google Fonts at runtime (shared with the dev package).

**Character:** Plain, sturdy Barlow does the reading; the condensed caps are the signage voice, kept small and rare.

### Hierarchy
- **Display** (700, 34px phone / 44px from 821px, 1.1, -0.01em, balanced wrap): page titles "¿Qué necesitas?" and "Cómo funciona".
- **Headline** (700, 24px, 1.2): "Mis peticiones", dialog band title; conversation header title 28px phone / 32px desktop; help subheads 20px.
- **Title** (700, 19-22px, 1.25-1.35): dialog legends (19px), permission question (22px), steps (18px).
- **Body** (400-500, 17px, 1.55): base; textareas 17-18px; assistant prose 1.6 line height; lede max 60ch in Ink Mute; row text weight 500, 700 when the row needs you.
- **Label** (Barlow Condensed 600, 13px, +0.1em, uppercase): group labels above chips and example lists ("Ideas rápidas"). State words are 600 14px +0.08em (15px in the conversation header); the Pedir/primary button is 700 19px +0.08em; the logo is 700 26px +0.06em; the tape flag is 700 13px +0.1em.

### Named Rules
**The Caps Are Small Rule.** Condensed caps are for labels, state words, the logo and the primary button, never for headings or running text.
**The One Voice Rule.** No third family; emphasis is weight within Barlow.

## Layout

One centered column: `.a-col` max 680px, padding 24px 16px 48px on phones and 56px 24px 80px from 821px. The top bar and the alert banners share the 680px measure. Spacing rhythm: 6, 8, 10, 12, 14, 16, 20, 24px; sections separate by 22-44px.

Home, top to bottom: title "¿Qué necesitas?", a lede, a white card holding the textarea (min 120px) with Adjuntar and the mic below it, the label "Ideas rápidas", four idea chips in a 2x2 grid (all widths), the example list that opens under a pressed chip, a full-width 56px PEDIR, then "Mis peticiones" (44px gap above) as one white card of rows. Rows sort Te necesita, then Trabajando/En espera, then newest first; each row is text (two-line clamp) at left, "Correo · hace 5 min" right-aligned, and the state mark on its own line.

Conversation: a sticky header (back link "Mis peticiones", errand name as title, state mark, "Parar" at right while working or asking), a log with 14px gaps (own messages right-aligned at up to 85% width, assistant replies as white cards), a live status line, and a composer sticky at the bottom (inner width 648px, 632px on desktop). Menu: a toggle in the top bar opens one white card of links (Mis peticiones, Ayuda, Salir with the user name); the sidebar does not exist. Under 820px (or short landscape) dialog footers stack their buttons full width and the help mark column narrows from 150px to 130px.

## Elevation & Depth

Flat paper. Depth is hairline borders plus one very soft card shadow; only the dialog, toast and composer divider read as raised. No coloured shadows, no hard offsets.

### Shadow Vocabulary
- **Card** (`box-shadow: 0 1px 2px rgba(26,26,26,.04), 0 8px 18px -12px rgba(26,26,26,.18)`): every `.a-card`.
- **Dialog** (`0 20px 50px rgba(26,26,26,.3)` over a `rgba(26,26,26,.5)` backdrop).
- **Toast** (`0 10px 24px -8px rgba(26,26,26,.45)`), Ink fill.
- **Composer**: no shadow, a 1px top hairline.

### Named Rules
**The Paper Stays Flat Rule.** Surfaces are white on paper with a hairline; selection is an Ink border plus a 1px inset Ink ring, not a lift.

## Shapes

12px corners on cards, buttons, chips, options, bubbles and the dialog; 10px on small buttons, attachments and text inputs; chat bubbles square one corner to 4px at the speaker's side. The Flows marks are the only special silhouettes: the tape flag has a folded-tape bottom notch (`clip-path`, V cut to 76%), the hatch mark is a 16px rounded-3px square of 135-degree ink stripes, the grease check is a rounded 10-unit ink stroke. The top bar sits over a 12px orange strip with sprocket holes (`--perf`) on grain. Icons are authored inline SVG (the `icon()` map, 2-2.2 stroke); the logo is the `reel` icon plus "FLOWS" in condensed caps.

## Components

### Top bar
Paper ground, reel logo with the word in condensed caps (44px target) at left, a white "Menú" button (condensed caps, 12px radius) at right with an orange unread dot when a request needs you, and below it the single perforated orange strip. Open menu: the toggle reads "Cerrar", and a white card lists links with 52px rows and hairline dividers.

### Buttons
- **Primary:** Flag Orange, Bench Ink condensed caps 19px, 48px minimum height, 12px radius, no border or edge; hover goes to Flag Orange Hover. One per view where possible. Pedir is the same at 56px, full width, with a 20px top margin.
- **Secondary:** white, 1px Paper Line border that darkens to Ink Mute on hover.
- **Quiet:** text-only, underlined, 600, for "Decide tú" and "Sí, y no vuelvas a preguntar en esta petición".
- **Small:** white, 44px, 10px radius, icon plus label ("Adjuntar", mic, "Parar"); the mic turns Ink-filled when recording.
- Disabled or busy is 60% opacity.

### Ask card and idea chips
A white card whose border turns Ink on focus-within; the textarea is borderless inside. Idea chips (Correo, Documentos, Agenda, Otra cosa) are white 56px tiles with an icon and a 600 label; they toggle (`aria-pressed`), shown as an Ink border plus inset ring, and open a list of 48px example buttons (pencil icon); choosing one fills the textarea. Chips are not coloured per errand. Ctrl/Cmd+Enter presses Pedir.

### Request rows
Rows inside one card, 64px minimum, hairline dividers, hover `#faf9f7`. Ink 500 text, 700 when asking.

### State marks
Always mark plus word, small condensed caps in Ink Mute (Ink for the active states):
- **Listo**: grease-pencil check.
- **Te necesita**: orange folded tape flag with Bench Ink caps (the only coloured state).
- **Trabajando**: dot, pulsing 1.6s.
- **Pausado · escribe para seguir**: dash.
- **No se pudo**: hatch square.
- **En espera**: clock (usage limit reached).
A lead that ended after finishing its turn reads Listo, not Pausado.

### Conversation
Own messages are Ink Wash bubbles labelled "Tú" for screen readers; assistant text is a white bordered card with a small markdown subset (paragraphs, headings, nested lists, bold, links in Ink). Tool actions collapse to one Ink Mute line with an icon ("Buscando en tu correo: «Presupuesto»", "Un ayudante se encarga de: ..."); decisions appear as notes ("Respondiste: ..."). Tool results and raw output are never shown. Errors show a hatch mark and an instruction.

### Composer
Sticky white panel, hairline top: textarea (52px min), Adjuntar and mic left, orange "Enviar" at right (132px min). When the state is Listo the textarea border darkens to Ink Mute. On a phone the example chips are not involved; labels may collapse to icons.

### Alert and ask bar
A white bar with an Ink 1px border, the orange tape flag, a one-line ellipsised request name, and "Contestar" with an arrow at right; shown on every page except the request that needs you. A softer variant (Ink wash, hairline border) states that the account is not connected to Claude.

### Decision dialog
The only modal: a native dialog, white, 12px radius, width up to 560px, with a header band ("Necesito que decidas", errand and request name beneath, hairline below). Questions are 56px option cards (24px square check box with Ink border; selected = Ink border, inset ring, Ink-filled box) plus "Otra cosa" with a text field; the footer offers "Decide tú", "Más tarde" and an orange "Enviar respuesta". Permissions ask a plain question ("¿Puedo enviar este correo?") above a paper-ground letter card (Para / Asunto / body, hairline rows), an optional "¿por qué?" field for a No, then "No", an orange "Sí, adelante" and the quiet "Sí, y no vuelvas a preguntar en esta petición" on its own line.

### Help page
"Cómo funciona": lede, a white card with three numbered steps (condensed numerals in Ink Mute), "Qué puede hacer" and "Qué no puede hacer" white cards with bullet lists, "Qué significa cada marca" as a card of mark-plus-sentence rows, then an orange "Hacer una petición" button.

### Motion
State motion only: the 1.6s opacity pulse on Trabajando and the live line, 0.15s colour and border transitions. All animation and transition is off under `prefers-reduced-motion`.

### Copy
Spanish, informal "tú", plain words about correo, documentos and agenda. Say what is happening and what to do next ("Escribe abajo para intentarlo otra vez"). Buttons are verbs ("Pedir", "Enviar", "Contestar"). Ages "hace 5 min", "ayer"; dates via `es-ES`.

## Do's and Don'ts

### Do:
- **Do** pair every state with its mark and word, using the five Flows marks.
- **Do** keep text on orange in Bench Ink and put orange only on the primary action, the Te necesita flag, focus, selection and the one strip.
- **Do** build new surfaces from white cards with a 1px Paper Line border on Paper Ground, 12px radius, in the single 680px column.
- **Do** keep targets at least 44px and the 3px Flag Orange Deep focus ring.
- **Do** write new copy in plain Spanish "tú" and put the next step in every error.
- **Do** keep admin rules scoped to `body.adm`.

### Don't:
- **Don't** show tool names, model names, paths, costs or permission jargon; translate to a plain Spanish line.
- **Don't** convey state by colour alone, or invent per-errand colours.
- **Don't** add a second perforated strip, a sidebar, or dark panels to this world.
- **Don't** use condensed caps for headings or running text.
- **Don't** open a modal for anything but a blocking decision.

### Observed in the build, not canonized
One-off literals outside the tokens (placeholder `#6f6a63`, row hover `#faf9f7`, scrollbar `#c9c4bb`, the letter card repeating `#f4f2ee`) are drift to fold into tokens, not palette entries. Fonts load from Google Fonts with no local copy; offline the fallback is system-ui. No craft-floor refusals (kickers, glyph icons, offset shadows) were found in the admin block.
