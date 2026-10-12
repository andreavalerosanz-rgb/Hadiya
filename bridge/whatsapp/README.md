# Flows WhatsApp bridge

Talks to the Flows Asistente through your own "Message yourself" chat. Uses unofficial Baileys (`7.0.0-rc14`), needs Node ≥ 20.

## Run
```
cd /home/andrea/Desktop/flows/bridge/whatsapp
npm install          # once
node index.mjs       # first run prints a QR (also PNG at data/uploads/20261009-184432-d679/whatsapp-qr.png)
```
Scan: WhatsApp → Settings → Linked devices → Link a device. Then write to yourself ("Tú" chat). Env: `FLOWS_URL` (default http://localhost:8787); token from `data/assistant.json`.
Background: copy `flows-whatsapp.service` to `~/.config/systemd/user/` and `systemctl --user enable --now flows-whatsapp` (after pairing).
Re-pair: stop it, `rm -rf auth/`, run again. Test: `npm test` (mocked Flows + socket, no WhatsApp).

## Rules baked in
- Only the own JID is read or written; every other chat/group/status is dropped before its content is touched. No read receipts, no presence.
- Bot messages start with `🤖 ` and their ids are remembered, so they are never re-forwarded.
- Approvals: `🤖 ¿Permitir? …` → reply sí/si/yes/ok or no (or quote the message). With several pending: `sí 2` / `no 2`.
- `auth/` holds the WhatsApp session (chmod 700, gitignored). Anyone who reads it controls your WhatsApp account.
