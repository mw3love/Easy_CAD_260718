// 공동작업 1단계(§8 항목61 ⓕ, 2026-10-18) — 브라우저 쪽 맞추기 계산(순수, `npm test`). 서버 합치기 규칙은 `web/collab.py`.
// 「기준」 = 마지막으로 서버와 맞춘 도형들(uid → 글로 굳힌 값). 고친 뒤엔 기준과 다른 것만 보내고(부분 저장),
// 남이 바꾼 것을 받으면 그 위에 아직 안 보낸 내 변경을 다시 얹는다 — 서로 다른 도형을 고치면 둘 다 남는다.

// 모델 도형 → 보낼 꼴(.ecad 도형 + uid, 화살표 연결은 상대 uid). _로 시작하는 칸은 안 보냄
export function toWire(it) {
  const o = {}
  for (const [k, v] of Object.entries(it)) if (!k.startsWith('_')) o[k] = v
  o.uid = it._id
  for (const k of ['bind1', 'bind2']) if ('_' + k in it) o[k] = it['_' + k] ?? null
  return o
}
export function fromWire(w) {
  const o = { ...w, _id: w.uid }; delete o.uid
  for (const k of ['bind1', 'bind2']) if (k in o) { const v = o[k]; delete o[k]; if (typeof v === 'string' || v === null) o['_' + k] = v }
  return o
}

// 기준 만들기 — uid → JSON 글
export const snapshot = items => new Map(items.map(it => [it._id, JSON.stringify(toWire(it))]))
const metaOf = model => { const o = {}; for (const [k, v] of Object.entries(model)) if (k !== 'items' && k !== 'rev' && !k.startsWith('_')) o[k] = v; return JSON.stringify(o) }
export const snapshotModel = model => ({ items: snapshot(model.items), meta: metaOf(model) })

// 기준과 다른 것 = 보낼 부분 저장 { upsert, delete, meta? } (바뀐 게 없으면 null)
export function diffModel(base, model) {
  const upsert = [], seen = new Set()
  for (const it of model.items) { seen.add(it._id); const w = JSON.stringify(toWire(it)); if (base.items.get(it._id) !== w) upsert.push(JSON.parse(w)) }
  const del = [...base.items.keys()].filter(u => !seen.has(u))
  const meta = metaOf(model), metaChanged = meta !== base.meta
  if (!upsert.length && !del.length && !metaChanged) return null
  return { upsert, delete: del, ...(metaChanged ? { meta: JSON.parse(meta) } : {}) }
}

// 부분 저장 얹기(모델 꼴) — 있는 도형은 그 자리에서 바꾸고, 새것은 끝에, 지운 것은 뺌
export function applyToItems(items, patch) {
  const pos = new Map(items.map((it, i) => [it._id, i])), out = items.slice()
  for (const w of patch.upsert || []) { const it = fromWire(w), i = pos.get(it._id); if (i == null) { pos.set(it._id, out.length); out.push(it) } else out[i] = it }
  const del = new Set(patch.delete || [])
  return del.size ? out.filter(it => !del.has(it._id)) : out
}

// 남의 변경 받기 — remote(서버에서 받은 모델) 위에 내가 아직 안 보낸 변경(기준 대비)을 다시 얹은 모델
export function rebase(remote, local, base) {
  const mine = diffModel(base, local)
  if (!mine) return remote
  const items = applyToItems(remote.items, mine)
  return { ...remote, ...(mine.meta || {}), items, rev: remote.rev }
}

// ── 되돌리기 = 도형 단위(2026-10-18 공동작업) — 칠판 통째로 되돌리면 그사이 남이 고친 것까지 지워진다.
// 한 칸 = { before: Map(id → { it, i } | null), after: Map(id → { it, i } | null) } — 바뀐 도형만(참조가 같으면 안 바뀐 것)
export function itemDelta(prev, next) {
  const before = new Map(), after = new Map(), P = new Map(prev.map((it, i) => [it._id, [it, i]])), N = new Map(next.map((it, i) => [it._id, [it, i]]))
  for (const [id, [it, i]] of P) { const n = N.get(id); if (!n) { before.set(id, { it, i }); after.set(id, null) } else if (n[0] !== it && JSON.stringify(n[0]) !== JSON.stringify(it)) { before.set(id, { it, i }); after.set(id, { it: n[0], i: n[1] }) } }
  for (const [id, [it, i]] of N) if (!P.has(id)) { before.set(id, null); after.set(id, { it, i }) }
  return { before, after }
}
// 칸 합치기(같은 열쇠로 연달아 고침) — 처음 before + 마지막 after
export function mergeDelta(a, b) {
  for (const [id, v] of b.before) if (!a.before.has(id)) a.before.set(id, v)
  for (const [id, v] of b.after) a.after.set(id, v)
  return a
}
// 한쪽(before 또는 after)을 지금 도형들에 얹기 — null = 지움, 없던 것은 원래 자리 근처에 끼움
export function applyDelta(items, side) {
  let out = items.slice()
  const pos = () => new Map(out.map((it, i) => [it._id, i]))
  let p = pos()
  const del = new Set([...side].filter(([, v]) => v == null).map(([id]) => id))
  if (del.size) { out = out.filter(it => !del.has(it._id)); p = pos() }
  const ins = []
  for (const [id, v] of side) { if (!v) continue; const i = p.get(id); if (i != null) out[i] = v.it; else ins.push(v) }
  ins.sort((a, b) => a.i - b.i).forEach(v => out.splice(Math.min(v.i, out.length), 0, v.it))
  return out
}
