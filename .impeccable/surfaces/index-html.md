---
version: 1
slug: "index-html"
primary_target: "index.html"
related_targets: []
---

# Surface: Flows for the admin package ("La ventanilla")

Scope: index.html when /api/me says package "admin". Mode: Operate. The dev package UI (cutting bench) stays untouched.
Audience: office staff with no technical knowledge, on a desk PC in office daylight or on a phone. Job: ask an assistant, in plain Spanish, to do errands in their Google mail, documents and calendar, and answer when it needs a decision. Only "ask and talk": no workflows, queue, models, parallel agents, folders or permissions jargon.
Constraints: one index.html, no build step, vanilla JS; same server API; Spanish copy; WCAG AA; works at 390px.

## Direction contract
THESIS: Asking is taking a number at the counter: you say what you need, get your ticket, someone attends you and calls you when it's your turn to decide. Refuses the centered chatbot box with suggestion chips.
OWN-WORLD: Enamel-blue ticket dispenser body (#1f4fd1) owning the top of home; big colored dispenser keys per errand (Correo red #d93d2b, Documentos green #0f8a5f, Agenda amber #f2a900, Otra cosa ink #111a2e); thermal-white tickets with torn edge and a big ticket number; cool laminate counter ground #e9edf3; navy LED turn board (#111a2e) with dot-matrix numbers and fixed columns; hyperlegible humanist sans at generous sizes.
STORY: The person sees four keys and a box, presses Correo or writes, presses Pedir, a ticket prints with their number, the assistant attends; when it needs them the board and header say "Te necesita" and a plain question with big Sí/No answers appears; done tickets get punched.
FIRST VIEWPORT: Desktop: dispenser block left two thirds (headline "¿Qué necesitas?", textarea, four keys in a row, Pedir button bottom right of the block); LED turn board right third (Nº | Asunto | Estado). Mobile: dispenser full width, board below. Signature interaction: on Pedir the ticket slides out of the dispenser slot before the conversation opens.
FORM: La ventanilla, position 5 of my ordered list; seed key 05a5e458. Raises: right-aligned times on every ticket (cassette j-card); header always names where you are, "Turno 014 · Correo · Te necesita" (lexicon); past requests as a whole-cell grid of punched stubs (convention catalog); turn board with fixed columns, rows change, columns never move (split-flap).
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved
Login page (server.py LOGIN_HTML) is shared by all packages before sign-in; still English and in the dev look.
