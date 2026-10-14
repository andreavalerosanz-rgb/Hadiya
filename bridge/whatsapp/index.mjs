// WhatsApp <-> Hadiya Asistente bridge. Lives ONLY in the user's "message yourself" chat.
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const TAG = '🤖 '
// The whole message must be the answer ("sí", "no 2"): "no me lo mandes así" is a normal message, not a denial.
const YN = /^(?:(s[ií]|yes|ok|vale|y)|(no|nope|n))[\s.!]*(?:#?(\d+))?[\s.!]*$/iu
const MAX_FILE = 16 << 20, MAX_VOICE = 8 << 20
// Media is accepted by declared mime type only; the extension comes from here, never from the sender's file name.
const MIME_EXT = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif', 'application/pdf': 'pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx', 'text/plain': 'txt', 'text/csv': 'csv', 'text/markdown': 'md' }
const EXT_MIME = Object.fromEntries(Object.entries(MIME_EXT).map(([m, e]) => [e, m]))
const VOICE = /^audio\/(ogg|mpeg|mp4|wav|x-wav|aac)\b/
const sleep = ms => new Promise(r => setTimeout(r, ms))
const bare = j => (j || '').replace(/:\d+@/, '@') // "34600:12@s.whatsapp.net" -> "34600@s.whatsapp.net"
const quiet = { level: 'silent', child: () => quiet, trace() {}, debug() {}, info() {}, warn() {}, error() {} }

export async function start(o = {}) {
  const url = o.url || process.env.HADIYA_URL || process.env.FLOWS_URL || 'http://localhost:8787'
  const authDir = o.authDir || path.join(HERE, 'auth')
  const tokenFile = o.tokenFile || '/home/andrea/Desktop/flows/data/assistant.json'
  const qrPng = o.qrPng || process.env.WA_QR_PNG || '/home/andrea/Desktop/flows/data/uploads/20261009-184432-d679/whatsapp-qr.png'
  const doFetch = o.fetch || fetch
  const backoffMs = o.backoffMs ?? 1000
  const pollMs = o.pollMs ?? 70000
  const log = o.log || (m => console.log(new Date().toISOString(), m))
  fs.mkdirSync(authDir, { recursive: true, mode: 0o700 }); fs.chmodSync(authDir, 0o700)
  const sinceFile = path.join(authDir, 'since.json') // survive restarts without replaying old replies

  let sock, own = new Set(), ownJid = null, open = false, stopped = false, tries = 0
  let since = 0
  try { since = JSON.parse(fs.readFileSync(sinceFile, 'utf8')).since | 0 } catch {}
  const sent = new Set()          // ids of messages we sent (loop prevention)
  const pending = []              // {n, approval_id, msgId, text}

  const api = async (method, p, body, signal) => {
    const token = JSON.parse(fs.readFileSync(tokenFile, 'utf8')).token
    const r = await doFetch(url + p, {
      method, signal,
      headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: body && JSON.stringify(body),
    })
    if (!r.ok) throw new Error(`${method} ${p} -> ${r.status} ${(await r.json().catch(() => ({}))).error || ''}`.trim())
    return r.json().catch(() => ({}))
  }

  // The ONLY place that talks to WhatsApp. Destination is hardcoded to the own JID.
  const sendRaw = async content => {
    if (!open || !ownJid) throw new Error('not connected')
    const m = await sock.sendMessage(ownJid, content)
    if (m?.key?.id) sent.add(m.key.id)
    return m?.key?.id
  }
  const send = text => sendRaw({ text: TAG + text })

  const decide = async (p, allow, note = '') => {
    pending.splice(pending.indexOf(p), 1)
    await api('POST', '/api/assistant/approve', { approval_id: p.approval_id, allow })
    await send((allow ? '✅ Permitido' : '🚫 Denegado') + note).catch(() => {})
  }

  // Incoming voice note / photo / document from the self-chat -> the assistant (server transcribes and stores).
  async function onMedia(m, msg) {
    const v = msg.audioMessage, f = msg.imageMessage || msg.documentMessage || msg.documentWithCaptionMessage?.message?.documentMessage
    const mime = ((v || f).mimetype || '').toLowerCase().split(';')[0].trim()
    const size = +((v || f).fileLength || 0)
    try {
      if (v ? !VOICE.test(mime) || size > MAX_VOICE : !MIME_EXT[mime] || size > MAX_FILE) return send('No acepto ese tipo de archivo o es demasiado grande (máx. 16 MB: fotos, PDF, Office, texto; audios hasta 8 MB).')
      const buf = await (o.download || realDownload)(m)
      if (buf.length > (v ? MAX_VOICE : MAX_FILE)) return send('Archivo demasiado grande.')
      const body = { channel: 'whatsapp', from: ownJid, text: f?.caption || '' }
      if (v) body.audio = buf.toString('base64')
      else {
        const base = path.basename(f.fileName || 'archivo').replace(/\.[^.]*$/, '').replace(/[^\w\- ]/g, '_').trim().slice(0, 60) || 'archivo'
        body.files = [{ name: `${base}.${MIME_EXT[mime]}`, data: buf.toString('base64') }]
      }
      const r = await api('POST', '/api/assistant/message', body)
      if (v && r.text) await send('🎙️ ' + r.text.slice(0, 300))
    } catch (e) { log('media: ' + e.message); await send('No he podido procesar el ' + (v ? 'audio' : 'archivo') + ': ' + e.message.replace(/^.*-> \d+ /, '')).catch(() => {}) }
  }

  async function onMessage(m) {
    const jid = m.key?.remoteJid
    // Anything outside the self-chat is dropped before looking at its content.
    if (!m.key?.fromMe || !own.has(bare(jid))) return
    if (sent.has(m.key.id)) return
    const msg = m.message
    if (msg?.audioMessage || msg?.imageMessage || msg?.documentMessage || msg?.documentWithCaptionMessage) return onMedia(m, msg)
    const text = (msg?.conversation || msg?.extendedTextMessage?.text || '').trim()
    if (!text || text.startsWith('🤖')) return

    const yn = pending.length && text.match(YN)
    if (yn) {
      const allow = !!yn[1], quoted = msg?.extendedTextMessage?.contextInfo?.stanzaId
      const p = pending.find(x => x.msgId === quoted) || (yn[3] ? pending.find(x => x.n === +yn[3]) : pending.at(-1))
      if (p) return decide(p, allow, !quoted && !yn[3] && pending.length > 1 ? ` (solo la última: ${p.text.slice(0, 60)}; quedan ${pending.length - 1}, cita su mensaje para responderlas)` : '')
      return send('No encuentro esa pendiente.')
    }
    await api('POST', '/api/assistant/message', { text, channel: 'whatsapp', from: ownJid })
  }

  async function deliver(it) {
    if (it.type === 'approval') {
      const n = Math.max(0, ...pending.map(p => p.n)) + 1
      const p = { n, approval_id: it.approval_id, text: it.text }
      pending.push(p)
      const label = pending.length > 1 ? `[${n}] ` : ''
      p.msgId = await send(`¿Permitir? ${label}${it.text}\nResponde sí / no`)
    } else if (it.type === 'resolved') {  // answered elsewhere (web, auto): stop waiting for a reply to it
      const i = pending.findIndex(p => p.approval_id === it.approval_id)
      if (i >= 0) pending.splice(i, 1)
    } else if (it.type === 'file') {  // written by the assistant; only from the Hadiya uploads folder, only allowed types
      const root = path.resolve(path.dirname(tokenFile), 'uploads') + path.sep
      const f = path.resolve(String(it.path || ''))
      const ext = path.extname(f).slice(1).toLowerCase(), mimetype = EXT_MIME[ext]
      if (!f.startsWith(root) || !mimetype || !fs.statSync(f).isFile() || fs.statSync(f).size > MAX_FILE) return log('file skipped: ' + it.text)
      const data = fs.readFileSync(f), fileName = path.basename(f)
      await sendRaw(mimetype.startsWith('image/') ? { image: data, caption: TAG + fileName } : { document: data, mimetype, fileName })
    } else if (['reply', 'notice'].includes(it.type)) await send(it.text)  // unknown types are ignored
  }

  async function outboxLoop() {
    while (!stopped) {
      if (!open) { await sleep(500); continue }
      try {
        const items = await api('GET', `/api/assistant/outbox?since=${since}`, null, AbortSignal.timeout(pollMs))
        for (const it of Array.isArray(items) ? items : items.items || []) {
          await deliver(it)
          since = Math.max(since, it.id)
          fs.writeFileSync(sinceFile, JSON.stringify({ since }))
        }
      } catch (e) { log('outbox: ' + e.message); await sleep(backoffMs * 3) }
    }
  }

  async function connect() {
    sock = await o.makeSock(authDir, quiet)
    let asked = false  // one pairing code per socket
    sock.ev.on('messages.upsert', ({ messages, type }) => {
      if (type !== 'notify') return
      for (const m of messages) onMessage(m).catch(e => log('message: ' + e.message))
    })
    sock.ev.on('connection.update', async u => {
      if (u.qr && !asked && process.env.PAIR_PHONE && !sock.authState?.creds?.registered) {
        asked = true
        try {
          const code = await sock.requestPairingCode(process.env.PAIR_PHONE)
          log('PAIRING CODE: ' + code)
          fs.writeFileSync(path.join(path.dirname(qrPng), 'whatsapp-code.txt'), code + '\n')
        } catch (e) { log('pairing code: ' + e.message) }
      }
      if (u.qr) {
        const QR = (await import('qrcode')).default
        console.log(await QR.toString(u.qr, { type: 'terminal', small: true }))
        try { fs.mkdirSync(path.dirname(qrPng), { recursive: true }); await QR.toFile(qrPng, u.qr, { width: 400 }); log('QR also at ' + qrPng) } catch {}
      }
      if (u.connection === 'open') {
        open = true; tries = 0
        own = new Set([bare(sock.user.id), bare(sock.user.lid)].filter(Boolean))
        ownJid = bare(sock.user.id)
        log('connected as ' + ownJid)
        try { fs.unlinkSync(qrPng) } catch {}
      }
      if (u.connection === 'close') {
        open = false
        const code = u.lastDisconnect?.error?.output?.statusCode
        if (code === 401) { log('LOGGED OUT: delete bridge/whatsapp/auth/ and start again to re-scan the QR'); stopped = true; o.onFatal?.(); return }
        if (stopped) return
        const wait = Math.min(backoffMs * 2 ** tries++, 60000)
        log(`closed (${code}), reconnecting in ${wait}ms`)
        await sleep(wait)
        connect().catch(e => log('reconnect: ' + e.message))
      }
    })
  }

  await connect()
  outboxLoop()
  return { stop: () => { stopped = true; sock?.end?.() }, _sock: () => sock, _pending: pending }
}

async function realDownload(m) {
  const B = await import('@whiskeysockets/baileys')
  return B.downloadMediaMessage(m, 'buffer', {}, { logger: quiet, reuploadRequest: async x => x })
}

async function realSock(authDir, logger) {
  const B = await import('@whiskeysockets/baileys')
  const makeWASocket = B.default.default || B.default
  const { state, saveCreds } = await B.useMultiFileAuthState(authDir)
  const s = makeWASocket({ auth: state, logger, markOnlineOnConnect: false, syncFullHistory: false })
  s.ev.on('creds.update', saveCreds)
  return s
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  start({ makeSock: realSock, onFatal: () => process.exit(1) })
}
