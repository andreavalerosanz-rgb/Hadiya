---
version: 1
slug: "index-html"
primary_target: "index.html"
related_targets: []
---

# Surface: Flows for the admin package ("prueba")

Scope: index.html when /api/me says package "admin". Mode: Operate. The dev package UI (cutting bench) stays untouched.
Audience: office staff with no technical knowledge, mostly on a phone. Job: ask an assistant, in plain Spanish, for errands in Gmail, Drive and Calendar, and answer when it needs a decision. Only "ask and talk".
Constraints: one index.html, no build step; same server API; Spanish; WCAG AA; mobile-first (390px is the design width); low design intensity.
History: "La ventanilla" (blue ticket-counter world, seed 05a5e458) was built and then rejected by the user as generic and off-brand; the black bench palette was rejected as too techy for this audience.

## Direction contract
THESIS: Flows on paper: the same brand made calm and light, one column, one obvious action. Refuses both the dark techy bench and a generic app kit.
OWN-WORLD: Paper ground #f4f2ee, white cards with hairline #e6e3dd, ink text #1a1a1a / mute #57534d; Flows flag orange #ff5a1f only on the primary action and "Te necesita"; Barlow body, Barlow Condensed caps for small labels only; Flows reel logo; Flows state marks (grease-pencil check for Listo, folded tape flag for Te necesita); one thin perforated orange strip under the top bar as the only film echo.
STORY: Open, read "¿Qué necesitas?", type or tap Correo/Documentos/Agenda/Otra cosa for an example, press Pedir; the request appears in Mis peticiones; open it to chat; a flag says when it needs you; answer Sí/No in plain words.
FIRST VIEWPORT: Phone: top bar (logo, menu); "¿Qué necesitas?" title; textarea card; four quick-idea chips in 2x2; full-width orange Pedir; "Mis peticiones" list beneath (state mark, name, time). Desktop: the same column centered (~680px).
FORM: user-steered surface after re-roll (palette "Papel y naranja", structure "Pedir arriba, lista abajo"); surface seed key cbac649f (rolled 2026-10-02 with `concept-seed --scope surface --mode operate --candidate-count 7`; the user then steered to their own palette and structure, replacing direction 05a5e458 still recorded in .impeccable/build/state.json).
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
