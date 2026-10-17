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
  return r.ok
}
