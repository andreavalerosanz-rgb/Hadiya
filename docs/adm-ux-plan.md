# Admin package ("prueba") UX plan — 2026-10-12

Scope: `body.adm` only (Spanish, Google Workspace, non-technical). Plan de hoy, Asistente and Goals are
dev-only on the server (403 for the admin package), so they are not added here; the session-readability work
below is the part of the complaint that applies to this package.

## Audit (before)
- Navigation hidden behind a "Menú" button; the menu repeats "Mis peticiones" (which is only an anchor on Home), "Ayuda", "Salir".
- Home stacks five blocks: title + lede, ask box, "Ideas rápidas" chips + examples, Pedir, and the full list of every request.
- "Te necesita" banners for *other* requests sit on top of the conversation you are reading.
- Session header shows the category ("Correo"), not what you asked; every tool step is its own grey line between replies.
- Many labels at 13–15px (status marks, meta, steps), several 44px targets.

## IA (after): three destinations, always visible
| Destination | What lives there |
|---|---|
| **Pedir** (Home) | ask box, attach/dictate, 4 idea chips → examples, Pedir; below, the 3 most recent requests + "Ver todas" |
| **Mis peticiones** | every request grouped: Te necesitan / En curso / Terminadas; tap → the conversation |
| **Ayuda** | how it works, what the marks mean, account (Salir) |

- Phone: bottom tab bar (icon + word, 64px); hidden inside a conversation, which has its own back link and composer.
- Desktop: the same three tabs in the top bar, no menu button.
- The "Te necesita" count lives as a badge on the Mis peticiones tab instead of banners on every page.

## Density rules
- One heading per screen, no lede paragraphs (moved to Ayuda).
- Conversation: your messages are orange-tinted bubbles on the right, replies white cards on the left; tool steps
  collapse into one "N pasos" line (open on tap), the live line names the current step.
- Status = one chip (word + mark), never raw text. Title = what you asked; category and time are the meta line.
- Text ≥16px everywhere, targets ≥48px on phones, one orange per screen (primary action or "Te necesita").
