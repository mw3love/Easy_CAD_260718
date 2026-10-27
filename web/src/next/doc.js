// 직접 만드는 칠판의 문서 = .ecad 그대로(데스크톱 `easycad/fileio/document.py` 형식). 웹은 이걸 바꾸지 않고 그린다.
import { paperWH } from './geom.js'

export const emptyDoc = () => ({ format: 'easycad-doc', version: 1, items: [] })

export function parseDoc(text) {
  const d = JSON.parse(text)
  if (d.format !== 'easycad-doc' || !Array.isArray(d.items)) throw new Error('.ecad 문서가 아닙니다')
  return d
}

// 그리는 차례 — z 오름차순, 같으면 저장 차례(데스크톱 QGraphicsScene과 같음)
export const drawOrder = items => items.map((it, i) => [it, i]).sort((a, b) => (a[0].z ?? 0) - (b[0].z ?? 0) || a[1] - b[1])

// 아이템의 칠판 좌표 상자(회전 무시, 대략) — 전체 보기·보드 소속 판정용
export function itemBounds(it) {
  const [px, py] = it.pos || [0, 0], s = it.scale || 1
  const box = (x0, y0, x1, y1) => ({ x: px + x0 * s, y: py + y0 * s, w: (x1 - x0) * s, h: (y1 - y0) * s })
  const fromPts = pts => { const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]); return box(Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)) }
  switch (it.type) {
    case 'sarrow': case 'polygon': return fromPts(it.pts)
    case 'arrow': return fromPts([it.p1, it.p2, ...(it.ctrl1 ? [it.ctrl1, it.ctrl2] : [])])
    case 'line': return fromPts([[it.line[0], it.line[1]], [it.line[2], it.line[3]]])
    case 'path': return fromPts(it.elements.flatMap(e => { const o = []; for (let i = 1; i < e.length; i += 2) o.push([e[i], e[i + 1]]); return o }))
    case 'text': { const lines = String(it.text || '').split('\n'), px = (it.font || 12) * 96 / 72; return box(0, 0, Math.max(...lines.map(l => l.length)) * px * 0.9 + 8, lines.length * px * 1.33 + 8) }
    case 'badge': return box(-17, -17, 17, 17)
    case 'titleblock': { const [w, h] = paperWH(it.size, it.orient); return box(0, 0, w, h) }
    default: { const [x, y, w, h] = it.rect || [0, 0, 0, 0]; return box(x, y, x + w, y + h) }
  }
}

export function docBounds(items) {
  if (!items.length) return null
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
  for (const it of items) { const b = itemBounds(it); x0 = Math.min(x0, b.x); y0 = Math.min(y0, b.y); x1 = Math.max(x1, b.x + b.w); y1 = Math.max(y1, b.y + b.h) }
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 }
}

// 보드 안에 있나 — 가운데가 보드 사각형 안(데스크톱 "소속은 위치로"). 보드 안 잉크는 밝은 칠판 규칙(흰→검정)을 안 탄다.
export function boardMembership(items) {
  const boards = items.filter(it => it.type === 'board').map(itemBounds)
  return items.map(it => {
    if (it.type === 'board' || !boards.length) return false
    const b = itemBounds(it), cx = b.x + b.w / 2, cy = b.y + b.h / 2
    return boards.some(r => cx >= r.x && cx <= r.x + r.w && cy >= r.y && cy <= r.y + r.h)
  })
}

// 서버(감시 PC, `web/server.py`) 저장 — `/api/doc/<이름>` = `<이름>.ecad`
export const DOC_NAME = (new URLSearchParams(typeof location === 'undefined' ? '' : location.search).get('board') || 'main').replace(/[^\w\-가-힣]/g, '').slice(0, 64) || 'main'
const URL_ = `/api/doc/${encodeURIComponent(DOC_NAME)}`
export async function loadServerDoc() {
  try {
    const r = await fetch(URL_, { cache: 'no-store' })
    if (r.status === 404) return { server: true, doc: null }
    if (!r.ok) return { server: false }
    return { server: true, doc: parseDoc(await r.text()) }
  } catch { return { server: false } }
}
export async function saveServerDoc(doc) {
  const r = await fetch(URL_, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(doc) })
  if (!r.ok) return false
  try { return (await r.json()).rev ?? true } catch { return true }   // 통째 저장 = 판 번호 +1(다른 브라우저가 받아 감)
}

// ── 공동작업 1단계(§8 항목61 ⓕ, 2026-10-18) — 공용 비밀번호·부분 저장·받아 오기·접속자·게시(서버 `web/server.py`·`collab.py`) ──
const B = encodeURIComponent(DOC_NAME), J = { 'Content-Type': 'application/json' }
const post = (u, body) => fetch(u, { method: 'POST', headers: J, body: JSON.stringify(body) })
export const VIEW_TOKEN = (new URLSearchParams(typeof location === 'undefined' ? '' : location.search).get('view') || '').replace(/[^\w-]/g, '').slice(0, 64)
export const api = {
  // 팀 서버(§8 항목67)면 + { team(관리자 = null), board_ok(이 칠판을 써도 되나), home(우리 팀 첫 칠판) }
  session: async (board = DOC_NAME) => { try { const r = await fetch(`/api/session?board=${encodeURIComponent(board)}`, { cache: 'no-store' }); return r.ok ? await r.json() : { auth: false, ok: true, none: true } } catch { return { auth: false, ok: true, none: true } } },
  login: async password => (await post('/api/login', { password })).ok,
  patch: async body => { const r = await post(`/api/patch/${B}`, body); return r.ok ? (await r.json()).rev : null },
  since: async (rev, wait = 0) => { const r = await fetch(`/api/since/${B}?rev=${rev}${wait ? `&wait=${wait}` : ''}`, { cache: 'no-store' }); return r.status === 200 ? parseDoc(await r.text()) : null },   // wait = 바뀔 때까지 서버가 기다림(롱 폴링)
  leave: id => { try { fetch(`/api/presence/${B}`, { method: 'POST', headers: J, body: JSON.stringify({ id, leave: true }), keepalive: true }) } catch { /* 닫히는 중 — 못 보내면 15초 뒤 빠짐 */ } },   // 창 닫힘 = 접속자에서 바로 빠짐(keepalive = 닫혀도 보냄)
  presence: async (id, name, sel = [], edit = '') => { try { const r = await post(`/api/presence/${B}`, { id, name, sel, edit }); return r.ok ? await r.json() : null } catch { return null } },   // → { people: 이름들, others: [{ id, name, sel, edit }] }
  getPublish: async () => { try { const r = await fetch(`/api/publish/${B}`, { cache: 'no-store' }); return r.ok ? (await r.json()).token : null } catch { return null } },
  setPublish: async (on, renew = false) => { const r = await post(`/api/publish/${B}`, { on, renew }); return r.ok ? (await r.json()).token : null },
  // 편집 초대 링크(2026-10-19 — 노션 「공유」): 얻기 → { token, password(서버에 비밀번호가 있나) }, 켜기·끄기·새 링크, 링크로 들어오기
  getInvite: async () => { try { const r = await fetch(`/api/invite/${B}`, { cache: 'no-store' }); return r.ok ? await r.json() : null } catch { return null } },
  setInvite: async (on, renew = false) => { const r = await post(`/api/invite/${B}`, { on, renew }); return r.ok ? (await r.json()).token : null },
  join: async token => { try { return (await post('/api/join', { board: B, token })).ok } catch { return false } },
  boards: async () => { try { const r = await fetch('/api/boards', { cache: 'no-store' }); return r.ok ? (await r.json()).boards || [] : [] } catch { return [] } },   // 칠판 목록(최근 고친 것부터) — 위 막대 「칠판」
  pub: async (token, rev = -1, wait = 0) => { const r = await fetch(`/api/pub/${token}?rev=${rev}${wait ? `&wait=${wait}` : ''}`, { cache: 'no-store' }); if (r.status === 204) return { same: true }; if (!r.ok) return { gone: true }; const d = parseDoc(await r.text()); return { doc: d } },
}
