// 2단계 기본 편집의 순수 계산 — 누른 곳에 무엇이 있나, 크기·회전·이동·복제·삭제·묶기·잠금·순서(데스크톱 `core_view`·`host_selection` 규칙).
// 아이템은 model.js 형식(.ecad + _id). 바꿀 땐 늘 새 배열·새 객체(되돌리기가 옛 배열을 그대로 들고 있게).
import { newId } from './model.js'
import { itemBounds } from './doc.js'
import { resolveRoutes } from './arrows.js'

const rad = d => (d * Math.PI) / 180

// 칠판 좌표 → 아이템 안 좌표(pos 다음 origin 중심 회전·배율의 역)
export function toLocal(it, p) {
  const [x, y] = it.pos || [0, 0], [ox, oy] = it.origin || [0, 0], r = rad(-(it.rotation || 0)), s = it.scale || 1
  let qx = p.x - x - ox, qy = p.y - y - oy
  ;[qx, qy] = [qx * Math.cos(r) - qy * Math.sin(r), qx * Math.sin(r) + qy * Math.cos(r)]
  return { x: qx / s + ox, y: qy / s + oy }
}
export function toScene(it, p) {
  const [x, y] = it.pos || [0, 0], [ox, oy] = it.origin || [0, 0], r = rad(it.rotation || 0), s = it.scale || 1
  let qx = (p.x - ox) * s, qy = (p.y - oy) * s
  ;[qx, qy] = [qx * Math.cos(r) - qy * Math.sin(r), qx * Math.sin(r) + qy * Math.cos(r)]
  return { x: qx + ox + x, y: qy + oy + y }
}

const segDist = (p, a, b) => {
  const dx = b.x - a.x, dy = b.y - a.y, L = dx * dx + dy * dy
  const t = L ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L)) : 0
  return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy)
}
const polyDist = (p, pts) => { let d = Infinity; for (let i = 1; i < pts.length; i++) d = Math.min(d, segDist(p, pts[i - 1], pts[i])); return d }
const inPoly = (p, pts) => { let c = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const a = pts[i], b = pts[j]; if ((a.y > p.y) !== (b.y > p.y) && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) c = !c } return c }
const P = ([x, y]) => ({ x, y })
// 경로 요소를 점열로(곡선은 12토막)
export function flatten(elements) {
  const out = []; let cur = null, sub = []
  for (const e of elements) {
    if (e[0] === 'M') { if (sub.length) out.push(sub); sub = [cur = { x: e[1], y: e[2] }] }
    else if (e[0] === 'L') sub.push(cur = { x: e[1], y: e[2] })
    else if (e[0] === 'C') {
      const p0 = cur, c1 = { x: e[1], y: e[2] }, c2 = { x: e[3], y: e[4] }, p3 = { x: e[5], y: e[6] }
      for (let k = 1; k <= 12; k++) { const t = k / 12, u = 1 - t; sub.push({ x: u * u * u * p0.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t * t * t * p3.x, y: u * u * u * p0.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t * t * t * p3.y }) }
      cur = p3
    }
  }
  if (sub.length) out.push(sub)
  return out
}

// 이 아이템이 칠판 점 p를 덮나 — tol = 화면 몇 px에 해당하는 칠판 길이. textBox(it) = 글 상자 {w,h}(화면 재기, 호출부가 줌)
// 속 빈 도형도 안쪽이 몸통(데스크톱 `_INTERIOR_HIT_TOOLS` = 선택 도구에서 안쪽 클릭 = 그 도형)
export function hits(it, p, tol, textBox) {
  const q = toLocal(it, p)
  const edge = (it.width || 1) / 2 + tol
  switch (it.type) {
    case 'rect': case 'ellipse': case 'symbol': case 'image': case 'table': case 'board': {
      const [x, y, w, h] = it.rect
      if (it.type === 'ellipse') { const rx = w / 2 + edge, ry = h / 2 + edge, dx = q.x - x - w / 2, dy = q.y - y - h / 2; return (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry) <= 1 }
      return q.x >= x - edge && q.x <= x + w + edge && q.y >= y - edge && q.y <= y + h + edge
    }
    case 'text': { const b = textBox(it); return q.x >= -tol && q.x <= b.w + tol && q.y >= -tol && q.y <= b.h + tol }
    case 'badge': return Math.hypot(q.x, q.y) <= 17 + tol
    case 'line': { const [x1, y1, x2, y2] = it.line; return segDist(q, { x: x1, y: y1 }, { x: x2, y: y2 }) <= Math.max(edge, 4 * tol / 4) }
    case 'sarrow': return polyDist(q, it.pts.map(P)) <= edge + tol
    case 'arrow': {
      const pts = it.ctrl1 ? flatten([['M', ...it.p1], ['C', ...it.ctrl1, ...it.ctrl2, ...it.p2]])[0] : [P(it.p1), P(it.p2)]
      return polyDist(q, pts) <= edge + tol
    }
    case 'polygon': { const pts = it.pts.map(P); return (it.closed && inPoly(q, pts)) || polyDist(q, it.closed ? [...pts, pts[0]] : pts) <= edge }
    case 'path': { const subs = flatten(it.elements); return subs.some(s => (it.fill && inPoly(q, s)) || polyDist(q, s) <= edge) }
    case 'titleblock': { const b = itemBounds(it), loc = { x: q.x, y: q.y }, w = b.w / (it.scale || 1), h = b.h / (it.scale || 1)   // 용지틀은 테두리 띠만(안쪽은 통과 — 위에 그리기)
      const band = 3 + tol; return (loc.x >= -band && loc.x <= w + band && loc.y >= -band && loc.y <= h + band) && !(loc.x > band && loc.x < w - band && loc.y > band && loc.y < h - band - 33) }
    default: return false
  }
}

// 누른 곳의 맨 위 아이템(그리는 차례의 반대) — 잠긴 것은 못 잡음(데스크톱: 잠금 = 선택 안 됨)
export function topHit(items, p, tol, textBox) {
  const order = items.map((it, i) => [it, i]).sort((a, b) => (a[0].z ?? 0) - (b[0].z ?? 0) || a[1] - b[1])
  for (let k = order.length - 1; k >= 0; k--) { const it = order[k][0]; if (!it.locked && hits(it, p, tol, textBox)) return it }
  return null
}

// 아이템의 칠판 좌표 상자(회전 반영 — 네 모서리를 돌려 감싼 상자). textBox로 글 크기 보정
export function sceneBox(it, textBox) {
  let loc
  if (it.type === 'text') { const b = textBox(it); loc = { x: 0, y: 0, w: b.w, h: b.h } }
  else { const b = itemBounds({ ...it, pos: [0, 0], rotation: 0, scale: 1 }); loc = b }
  const cs = [[loc.x, loc.y], [loc.x + loc.w, loc.y], [loc.x + loc.w, loc.y + loc.h], [loc.x, loc.y + loc.h]].map(([x, y]) => toScene(it, { x, y }))
  const xs = cs.map(c => c.x), ys = cs.map(c => c.y)
  return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) }
}
export const unionBox = boxes => {
  const x0 = Math.min(...boxes.map(b => b.x)), y0 = Math.min(...boxes.map(b => b.y))
  return { x: x0, y: y0, w: Math.max(...boxes.map(b => b.x + b.w)) - x0, h: Math.max(...boxes.map(b => b.y + b.h)) - y0 }
}

// 범위 선택(데스크톱): 왼→오 끌기 = 완전히 안에 든 것, 오→왼 = 걸친 것. 잠긴 것 제외
export function rubberSelect(items, a, b, textBox) {
  const r = { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(b.x - a.x), h: Math.abs(b.y - a.y) }, window = b.x >= a.x
  return items.filter(it => {
    if (it.locked) return false
    const s = sceneBox(it, textBox)
    return window ? s.x >= r.x && s.y >= r.y && s.x + s.w <= r.x + r.w && s.y + s.h <= r.y + r.h
      : s.x <= r.x + r.w && s.x + s.w >= r.x && s.y <= r.y + r.h && s.y + s.h >= r.y
  }).map(it => it._id)
}

// 묶음(group_id) 넓히기 — 하나를 고르면 같은 묶음 전부(데스크톱 `_sync_group_selection`)
export function expandGroups(items, ids) {
  const gids = new Set(items.filter(it => ids.includes(it._id) && it.group_id).map(it => it.group_id))
  return gids.size ? [...new Set([...ids, ...items.filter(it => gids.has(it.group_id)).map(it => it._id)])] : ids
}

// 보드 안에 든 것(가운데가 보드 안) — 보드를 옮기거나 지우면 같이(데스크톱 `_board_delete_scope`·끌 때)
export function boardContents(items, boardIds, textBox) {
  const boards = items.filter(it => boardIds.includes(it._id) && it.type === 'board').map(it => sceneBox(it, textBox))
  if (!boards.length) return []
  return items.filter(it => it.type !== 'board' && !boardIds.includes(it._id)).filter(it => {
    const s = sceneBox(it, textBox), cx = s.x + s.w / 2, cy = s.y + s.h / 2
    return boards.some(r => cx >= r.x && cx <= r.x + r.w && cy >= r.y && cy <= r.y + r.h)
  }).map(it => it._id)
}

const upd = (items, ids, f) => { const set = new Set(ids); return items.map(it => (set.has(it._id) ? f(it) : it)) }
export const moveItems = (items, ids, dx, dy) => upd(items, ids, it => ({ ...it, pos: [(it.pos?.[0] || 0) + dx, (it.pos?.[1] || 0) + dy] }))

// 크기 바꾸기 — handle: 'tl'|'tr'|'br'|'bl'(모서리) 'l'|'r'|'t'|'b'(변). q = 아이템 안 좌표의 포인터. 이미지는 모서리에서 비율 고정(데스크톱 `_constrain_box_rect`)
export function resizeRect(rect, handle, q, { keepRatio = false, min = 4 } = {}) {
  let [x0, y0, w, h] = rect, x1 = x0 + w, y1 = y0 + h
  if (handle.includes('l')) x0 = Math.min(q.x, x1 - min)
  if (handle.includes('r')) x1 = Math.max(q.x, x0 + min)
  if (handle.includes('t')) y0 = Math.min(q.y, y1 - min)
  if (handle.includes('b')) y1 = Math.max(q.y, y0 + min)
  if (keepRatio && handle.length === 2 && w > 0 && h > 0) {
    const k = Math.max((x1 - x0) / w, (y1 - y0) / h), nw = w * k, nh = h * k
    if (handle.includes('l')) x0 = x1 - nw; else x1 = x0 + nw
    if (handle.includes('t')) y0 = y1 - nh; else y1 = y0 + nh
  }
  return [x0, y0, x1 - x0, y1 - y0]
}
// 사각형을 새 사각형으로 늘릴 때 안의 점 옮기기(다각형 pts·경로·포트 비율 유지)
const mapPt = (from, to) => ([x, y]) => [to[0] + ((x - from[0]) / (from[2] || 1)) * to[2], to[1] + ((y - from[1]) / (from[3] || 1)) * to[3]]
export function applyRect(it, rect) {
  if (it.type === 'polygon') return { ...it, rect, pts: it.pts.map(mapPt(it.rect, rect)) }
  if (it.type === 'path') { const b = itemBounds({ ...it, pos: [0, 0], scale: 1 }), from = [b.x, b.y, b.w, b.h], m = mapPt(from, rect)
    return { ...it, elements: it.elements.map(e => { const o = [e[0]]; for (let i = 1; i < e.length; i += 2) o.push(...m([e[i], e[i + 1]])); return o }) } }
  return { ...it, rect }
}
// 경로의 바탕 사각형(크기 손잡이 기준)
export function localRect(it) {
  if (it.rect) return it.rect
  const b = itemBounds({ ...it, pos: [0, 0], rotation: 0, scale: 1 }); return [b.x, b.y, b.w, b.h]
}

// 회전 — 가운데 기준(데스크톱 setTransformOriginPoint(rect 가운데)), Shift = 15° 단위
export function rotateTo(it, angleDeg, snap) {
  const [x, y, w, h] = localRect(it), a = snap ? Math.round(angleDeg / 15) * 15 : angleDeg
  const o = [x + w / 2, y + h / 2]
  // origin을 바꾸면 화면 자리가 움직이므로 pos로 메움(같은 점이 같은 자리에 남게)
  const before = toScene(it, { x: o[0], y: o[1] }), after = toScene({ ...it, origin: o }, { x: o[0], y: o[1] })
  return { ...it, origin: o, rotation: ((a % 360) + 360) % 360, pos: [(it.pos?.[0] || 0) + before.x - after.x, (it.pos?.[1] || 0) + before.y - after.y] }
}

// 복제(새 _id, 묶음은 새 묶음으로, 화살표 연결은 함께 복제된 것끼리만 이어줌) — dx,dy만큼 옮김
export function duplicate(items, ids, dx = 0, dy = 0) {
  const set = new Set(ids), map = new Map(), gmap = new Map()
  const copies = items.filter(it => set.has(it._id)).map(it => {
    const c = structuredClone(it); c._id = newId(); map.set(it._id, c._id)
    if (c.group_id) { if (!gmap.has(c.group_id)) gmap.set(c.group_id, 'g' + newId()); c.group_id = gmap.get(c.group_id) }
    c.pos = [(c.pos?.[0] || 0) + dx, (c.pos?.[1] || 0) + dy]
    return c
  })
  for (const c of copies) for (const k of ['_bind1', '_bind2']) if (c[k] !== undefined) c[k] = map.get(c[k]) ?? null
  const topZ = Math.max(0, ...items.map(it => it.z ?? 0))
  copies.forEach((c, i) => { if (c.type !== 'board') c.z = topZ + 1 + i })
  return { items: [...items, ...copies], ids: copies.map(c => c._id) }
}

export function removeItems(items, ids) {
  const set = new Set(ids)
  return items.filter(it => !set.has(it._id)).map(it => {   // 지운 도형에 붙어 있던 화살표 끝은 끊김(데스크톱: 화살표는 남음)
    let o = it
    for (const k of ['_bind1', '_bind2']) if (o[k] && set.has(o[k])) o = { ...o, [k]: null, [k.slice(1) + '_pt']: null }
    return o
  })
}

export const groupItems = (items, ids) => { const g = 'g' + newId(); return upd(items, ids, it => ({ ...it, group_id: g })) }
export const ungroupItems = (items, ids) => upd(items, ids, it => ({ ...it, group_id: null }))
export const toggleLock = (items, ids) => { const lock = !items.filter(it => ids.includes(it._id)).every(it => it.locked); return upd(items, ids, it => ({ ...it, locked: lock })) }
// 맨 앞/맨 뒤(데스크톱 bring_to_front/send_to_back — 고른 것끼리 차례는 유지)
export function zOrder(items, ids, front) {
  const pool = items.filter(it => it.type !== 'titleblock'), sel = items.filter(it => ids.includes(it._id)).sort((a, b) => (a.z ?? 0) - (b.z ?? 0))
  const top = Math.max(0, ...pool.map(it => it.z ?? 0)), bot = Math.min(0, ...pool.map(it => it.z ?? 0))
  const z = new Map(front ? sel.map((it, i) => [it._id, top + 1 + i]) : [...sel].reverse().map((it, i) => [it._id, bot - 1 - i]))
  return items.map(it => (z.has(it._id) ? { ...it, z: z.get(it._id) } : it))
}
// 좌우·상하 반전(Shift+H/V) — 고른 것들 전체 상자 가운데를 축으로
export function mirror(items, ids, horizontal, textBox) {
  const sel = items.filter(it => ids.includes(it._id)); if (!sel.length) return items
  const u = unionBox(sel.map(it => sceneBox(it, textBox))), c = horizontal ? u.x + u.w / 2 : u.y + u.h / 2
  const fx = v => (horizontal ? 2 * c - v : v), fy = v => (horizontal ? v : 2 * c - v)
  return upd(items, ids, it => {
    const [px, py] = it.pos || [0, 0]
    const P2 = ([x, y]) => [fx(x + px) - px, fy(y + py) - py]
    switch (it.type) {
      case 'polygon': { const pts = it.pts.map(P2), xs = pts.map(p => p[0]), ys = pts.map(p => p[1]); return { ...it, pts, rect: [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)] } }
      case 'path': return { ...it, elements: it.elements.map(e => { const o = [e[0]]; for (let i = 1; i < e.length; i += 2) o.push(...P2([e[i], e[i + 1]])); return o }) }
      case 'line': { const [a, b] = [P2([it.line[0], it.line[1]]), P2([it.line[2], it.line[3]])]; return { ...it, line: [...a, ...b] } }
      case 'sarrow': return { ...it, pts: it.pts.map(P2) }
      case 'arrow': return { ...it, p1: P2(it.p1), p2: P2(it.p2), ctrl1: it.ctrl1 && P2(it.ctrl1), ctrl2: it.ctrl2 && P2(it.ctrl2) }
      default: { const s = sceneBox(it, textBox), nx = horizontal ? 2 * c - (s.x + s.w) : s.x, ny = horizontal ? s.y : 2 * c - (s.y + s.h); return { ...it, pos: [px + nx - s.x, py + ny - s.y] } }   // 상자류는 자리만(모양 대칭)
    }
  })
}

// 화살표 따라가기 — 편집 뒤 붙은 화살표 꼭짓점을 문서에 반영(「자동 길」은 다시 꺾고, 아니면 양 끝만 따라감 — 데스크톱 reroute)
export function followArrows(items) {
  const routes = resolveRoutes(items)
  const byId = new Map(items.map(it => [it._id, it]))
  return items.map((it, i) => {
    if (it.type !== 'sarrow') return it
    if (routes.has(i)) return { ...it, pts: routes.get(i) }
    let pts = it.pts, changed = false
    for (const [k, idx] of [['_bind1', 0], ['_bind2', it.pts.length - 1]]) {
      const host = it[k] && byId.get(it[k]), pt = it[k.slice(1) + '_pt']
      if (!host || !pt) continue
      const sp = toScene(host, { x: pt[0], y: pt[1] }), lp = [sp.x - (it.pos?.[0] || 0), sp.y - (it.pos?.[1] || 0)]
      if (Math.abs(lp[0] - pts[idx][0]) > 1e-6 || Math.abs(lp[1] - pts[idx][1]) > 1e-6) { pts = pts.map((p, j) => (j === idx ? lp : p)); changed = true }
    }
    return changed ? { ...it, pts } : it
  })
}
