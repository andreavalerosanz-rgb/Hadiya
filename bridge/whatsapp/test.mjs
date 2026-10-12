import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { start } from './index.mjs'

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-'))
fs.writeFileSync(dir + '/a.json', '{"token":"T"}')
const ME = '34600@s.whatsapp.net'
const calls = [], sentWA = []
let outbox = [{ id: 1, type: 'reply', text: 'hola' }, { id: 2, type: 'approval', text: 'borrar x', approval_id: 'A1' }]
const fakeFetch = async (u, opt) => {
  const p = u.replace('http://f', '')
  assert.equal(opt.headers.Authorization, 'Bearer T')
  if (p.startsWith('/api/assistant/outbox')) {
    const since = +p.split('=')[1]
    const items = outbox.filter(x => x.id > since)
    if (!items.length) await new Promise(r => setTimeout(r, 50))
    return { ok: true, json: async () => items }
  }
  const b = JSON.parse(opt.body)
  calls.push([p, b])
  return { ok: true, json: async () => (b.audio ? { ok: true, text: 'hola voz' } : {}) }
}
const sock = { ev: new EventEmitter(), user: { id: '34600:7@s.whatsapp.net', lid: '99:7@lid' }, async sendMessage(jid, c) { sentWA.push([jid, c.text, c]); return { key: { id: 'S' + sentWA.length } } } }
sock.ev.on = sock.ev.addListener.bind(sock.ev)
const up = (jid, fromMe, text, id, extra) => sock.ev.emit('messages.upsert', { type: 'notify', messages: [{ key: { remoteJid: jid, fromMe, id }, message: extra || { conversation: text } }] })
const tick = () => new Promise(r => setTimeout(r, 100))

await start({ flowsUrl: 'http://f', authDir: dir + '/auth', tokenFile: dir + '/a.json', makeSock: async () => sock, download: async m => Buffer.from(m.message.fake || 'DATA'), fetch: fakeFetch, pollMs: 1000, backoffMs: 10, log() {} })
sock.ev.emit('connection.update', { connection: 'open' })
await new Promise(r => setTimeout(r, 700))

// outbox -> only own JID, prefixed
assert.deepEqual(sentWA.map(s => s[0]), [ME, ME])
assert.equal(sentWA[0][1], '🤖 hola')
assert.match(sentWA[1][1], /^🤖 ¿Permitir\? borrar x\nResponde sí \/ no$/)

up(ME, true, '/auto on', 'U1'); await tick()
assert.deepEqual(calls.pop(), ['/api/assistant/message', { text: '/auto on', channel: 'whatsapp', from: ME }])
up('99@lid', true, 'por lid', 'U2'); await tick()
assert.equal(calls.pop()[1].text, 'por lid')

// ignored: other chat (even fromMe), group, status, someone else's message in self chat, own bot message
const n = calls.length, w = sentWA.length
up('1555@s.whatsapp.net', true, 'hi', 'X1'); up('1555@s.whatsapp.net', false, 'hi', 'X2')
up('123-456@g.us', true, 'hi', 'X3'); up('status@broadcast', true, 'hi', 'X4'); up(ME, false, 'hi', 'X5')
up(ME, true, '🤖 eco', 'X6'); up(ME, true, 'x', 'S1') // S1 = id of a message we sent
await tick(); assert.equal(calls.length, n); assert.equal(sentWA.length, w)

// "sí" -> approve (not forwarded as a message)
up(ME, true, 'sí', 'U3'); await tick()
assert.deepEqual(calls.pop(), ['/api/assistant/approve', { approval_id: 'A1', allow: true }])
assert.equal(sentWA.every(s => s[0] === ME), true)

// two pending: a plain "no" applies to the latest and says so; a longer sentence is chat, not a denial; a quoted reply picks its own
outbox.push({ id: 3, type: 'approval', text: 'a', approval_id: 'B1' }, { id: 4, type: 'approval', text: 'b', approval_id: 'B2' }, { id: 5, type: 'approval', text: 'z', approval_id: 'B3' })
await new Promise(r => setTimeout(r, 200))
up(ME, true, 'no me lo mandes así', 'U4'); await tick()
assert.deepEqual(calls.pop(), ['/api/assistant/message', { text: 'no me lo mandes así', channel: 'whatsapp', from: ME }])
up(ME, true, 'No.', 'U5'); await tick()
assert.deepEqual(calls.pop(), ['/api/assistant/approve', { approval_id: 'B3', allow: false }])
assert.match(sentWA.at(-1)[1], /Denegado \(solo la última: z; quedan 2/)
up(ME, true, 'no 2', 'U5b'); await tick()
assert.deepEqual(calls.pop(), ['/api/assistant/approve', { approval_id: 'B2', allow: false }])
const b1msg = sentWA.findIndex(s => s[1].includes('[1] a')) + 1
up(ME, true, 'ok', 'U6', { extendedTextMessage: { text: 'ok', contextInfo: { stanzaId: 'S' + b1msg } } }); await tick()
assert.deepEqual(calls.pop(), ['/api/assistant/approve', { approval_id: 'B1', allow: true }])
// resolved elsewhere: dropped from pending, nothing sent; unknown types ignored; a later "sí" is plain chat
outbox.push({ id: 6, type: 'approval', text: 'c', approval_id: 'C1' }, { id: 7, type: 'resolved', approval_id: 'C1', allow: true }, { id: 8, type: 'weird', text: 'x' })
await new Promise(r => setTimeout(r, 200))
assert.equal(sentWA.filter(s => /\bc\b/.test(s[1]) || s[1].includes('weird') || s[1].endsWith('x')).length, 1)  // only the approval prompt itself
up(ME, true, 'sí', 'U7'); await tick()
assert.equal(calls.pop()[0], '/api/assistant/message')
// voice note -> audio sent to the server (it transcribes), transcript echoed; bad mime / too big refused
const media = (id, extra) => up(ME, true, '', id, extra)
media('V1', { audioMessage: { mimetype: 'audio/ogg; codecs=opus', ptt: true, fileLength: 5, fake: 'OGGDATA' } }); await tick()
const v = calls.pop()
assert.equal(v[0], '/api/assistant/message'); assert.equal(Buffer.from(v[1].audio, 'base64').toString(), 'DATA'); assert.equal(v[1].channel, 'whatsapp')
assert.match(sentWA.at(-1)[1], /🎙️/)
const n2 = calls.length
media('V2', { audioMessage: { mimetype: 'video/mp4', fileLength: 5 } }); media('V3', { audioMessage: { mimetype: 'audio/ogg', fileLength: 9 << 20 } })
media('V4', { documentMessage: { mimetype: 'application/x-msdownload', fileName: 'a.exe', fileLength: 5 } })
await tick(); assert.equal(calls.length, n2); assert.match(sentWA.at(-1)[1], /No acepto/)
// photos and documents: caption goes as text, the name is rebuilt from the mime type (no path tricks)
media('P1', { imageMessage: { mimetype: 'image/jpeg', caption: 'mira', fileLength: 5 } }); await tick()
let f = calls.pop()[1]; assert.equal(f.text, 'mira'); assert.match(f.files[0].name, /^archivo\.jpg$/)
media('D1', { documentMessage: { mimetype: 'application/pdf', fileName: '../../etc/pa ss<wd>.sh', fileLength: 5, caption: 'léelo' } }); await tick()
f = calls.pop()[1]; assert.equal(f.text, 'léelo'); assert.equal(f.files[0].name, 'pa ss_wd_.pdf')
// outbound files: only from <data>/uploads, only allowed types, images as image, others as document
fs.mkdirSync(dir + '/uploads/run1', { recursive: true })
fs.writeFileSync(dir + '/uploads/run1/informe.pdf', 'PDF'); fs.writeFileSync(dir + '/uploads/run1/f.png', 'PNG'); fs.writeFileSync(dir + '/secret.pdf', 'X')
outbox.push({ id: 9, type: 'file', name: 'informe.pdf', path: dir + '/uploads/run1/informe.pdf' }, { id: 10, type: 'file', name: 'f.png', path: dir + '/uploads/run1/f.png' },
  { id: 11, type: 'file', name: 'secret.pdf', path: dir + '/secret.pdf' }, { id: 12, type: 'file', name: 'x', path: dir + '/uploads/../secret.pdf' })
await new Promise(r => setTimeout(r, 300))
const files = sentWA.filter(s => s[2].document || s[2].image)
assert.equal(files.length, 2); assert.equal(files[0][2].mimetype, 'application/pdf'); assert.equal(files[0][2].fileName, 'informe.pdf'); assert.ok(files[1][2].image)
assert.equal(sentWA.every(s => s[0] === ME), true)
console.log('ok')
process.exit(0)
