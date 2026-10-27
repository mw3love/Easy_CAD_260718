// 2단계 기본 편집의 순수 계산 — 누른 곳에 무엇이 있나, 크기·회전·이동·복제·삭제·묶기·잠금·순서(데스크톱 `core_view`·`host_selection` 규칙).
// 아이템은 model.js 형식(.ecad + _id). 바꿀 땐 늘 새 배열·새 객체(되돌리기가 옛 배열을 그대로 들고 있게).
import { newId } from './model.js'
import { frameTag, frameTagFs, rowEdges } from './geom.js'
import { itemBounds } from './doc.js'
import { resolveRoutes, sarrowRouting } from './arrows.js'
import { setCurveEnd } from './arrowedit.js'
import { bindEnd } from './connect.js'

export { toLocal, toScene } from './xform.js'
import { toLocal, toScene } from './xform.js'

const segDist = (p, a, b) => {
  const dx = b.x - a.x, dy = b.y - a.y, L = dx * dx + dy * dy
  const t = L ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / L)) : 0
  return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy)
}
const polyDist = (p, pts) => { let d = Infinity; for (let i = 1; i < pts.length; i++) d = Math.min(d, segDist(p, pts[i - 1], pts[i])); return d }
const inPoly = (p, pts) => { let c = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const a = pts[i], b = pts[j]; if ((a.y > p.y) !== (b.y > p.y) && p.x < ((b.x - a.x) * (p.y - a.y)) / (b.y - a.y) + a.x) c = !c } return c }
const P = ([x, y]) => ({ x, y })
export { flatten } from './geom.js'   // 경로 요소 → 점열(geom.js로 옮김 — connect.js도 씀)
import { flatten } from './geom.js'

// 이 아이템이 칠판 점 p를 덮나 — tol = 화면 몇 px에 해당하는 칠판 길이. textBox(it) = 글 상자 {w,h}(화면 재기, 호출부가 줌)
// 속 빈 도형도 안쪽이 몸통(데스크톱 `_INTERIOR_HIT_TOOLS` = 선택 도구에서 안쪽 클릭 = 그 도형)
export function hits(it, p, tol, textBox) {
  const q = toLocal(it, p)
  const edge = (it.width || 1) / 2 + tol
  switch (it.type) {
    case 'rect': case 'ellipse': case 'symbol': case 'image': case 'table': case 'board': case 'web': case 'memo': case 'legend': case 'doc': case 'pdf': {
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
    case 'frame': { const [x, y, w, h] = it.rect, band = 3 + tol, fs = frameTagFs(it), tw = frameTag(it).length * fs * 0.75 + fs   // 테두리 띠 + 이름표(안쪽은 통과 — 위의 것을 고르고 그리기)
      if (q.x >= x && q.x <= x + tw && q.y >= y - fs * 1.8 && q.y <= y) return true
      return q.x >= x - band && q.x <= x + w + band && q.y >= y - band && q.y <= y + h + band && !(q.x > x + band && q.x < x + w - band && q.y > y + band && q.y < y + h - band) }
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
// 걸침은 감싼 사각형이 아니라 실제 선이 범위와 겹칠 때(데스크톱 `_base_shape().intersects`) — 대각·꺾인 화살표의 빈 모서리만 스쳐선 안 걸림
export function rubberSelect(items, a, b, textBox) {
  const r = { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(b.x - a.x), h: Math.abs(b.y - a.y) }, window = b.x >= a.x
  return items.filter(it => {
    if (it.locked) return false
    const s = sceneBox(it, textBox)
    return window ? s.x >= r.x && s.y >= r.y && s.x + s.w <= r.x + r.w && s.y + s.h <= r.y + r.h
      : s.x <= r.x + r.w && s.x + s.w >= r.x && s.y <= r.y + r.h && s.y + s.h >= r.y && crossesRect(outlinePieces(it, textBox), r)
  }).map(it => it._id)
}

// 보이는 외형(데스크톱 `_item_center_path`)을 칠판 좌표 점열 조각으로 + 닫힘(안쪽도 몸통) 여부. 심볼은 바탕 상자로 어림
export function outlinePieces(it, textBox) {
  const S = v => toScene(it, v), ring = (cx, cy, rx, ry) => Array.from({ length: 32 }, (_, k) => S({ x: cx + rx * Math.cos(k * Math.PI / 16), y: cy + ry * Math.sin(k * Math.PI / 16) }))
  switch (it.type) {
    case 'line': { const [x1, y1, x2, y2] = it.line; return { closed: false, pieces: [[S({ x: x1, y: y1 }), S({ x: x2, y: y2 })]] } }
    case 'sarrow': return { closed: false, pieces: [it.pts.map(P).map(S)] }
    case 'arrow': return { closed: false, pieces: flatten(it.ctrl1 ? [['M', ...it.p1], ['C', ...it.ctrl1, ...it.ctrl2, ...it.p2]] : [['M', ...it.p1], ['L', ...it.p2]]).map(pc => pc.map(S)) }
    case 'path': return { closed: !!it.fill, pieces: flatten(it.elements).map(pc => pc.map(S)) }
    case 'polygon': return { closed: !!it.closed, pieces: [it.pts.map(P).map(S)] }
    case 'badge': return { closed: true, pieces: [ring(0, 0, 17, 17)] }   // 데스크톱 `_BadgeItem._base_shape`(15 + 2)
    case 'ellipse': { const [x, y, w, h] = it.rect; return { closed: true, pieces: [ring(x + w / 2, y + h / 2, w / 2, h / 2)] } }
    default: {
      const [x, y, w, h] = it.type === 'text' ? [0, 0, textBox(it).w, textBox(it).h] : localRect(it)
      return { closed: true, pieces: [[[x, y], [x + w, y], [x + w, y + h], [x, y + h]].map(P).map(S)] }
    }
  }
}
// 선분이 사각형과 겹치나(Liang–Barsky)
function segHitsRect(a, b, r) {
  let t0 = 0, t1 = 1; const dx = b.x - a.x, dy = b.y - a.y
  for (const [p, q] of [[-dx, a.x - r.x], [dx, r.x + r.w - a.x], [-dy, a.y - r.y], [dy, r.y + r.h - a.y]]) {
    if (p === 0) { if (q < 0) return false; continue }
    const t = q / p
    if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t } else { if (t < t0) return false; if (t < t1) t1 = t }
  }
  return true
}
export function crossesRect(o, r) {
  for (const pc of o.pieces) {
    const pts = o.closed && pc.length > 2 ? [...pc, pc[0]] : pc
    if (pts.length === 1 && segHitsRect(pts[0], pts[0], r)) return true
    for (let i = 1; i < pts.length; i++) if (segHitsRect(pts[i - 1], pts[i], r)) return true
    if (o.closed && pc.length > 2 && inPoly({ x: r.x, y: r.y }, pc)) return true   // 범위가 닫힌 도형 안쪽에 통째로 든 경우
  }
  return false
}

// 묶음(group_id) 넓히기 — 하나를 고르면 같은 묶음 전부(데스크톱 `_sync_group_selection`)
export function expandGroups(items, ids) {
  const gids = new Set(items.filter(it => ids.includes(it._id) && it.group_id).map(it => it.group_id))
  return gids.size ? [...new Set([...ids, ...items.filter(it => gids.has(it.group_id)).map(it => it._id)])] : ids
}

// 보드 안에 든 것(가운데가 보드 안) — 보드를 옮기거나 지우면 같이(데스크톱 `_board_delete_scope`·끌 때)
export function boardContents(items, boardIds, textBox) {
  // 담는 틀 = AI 보드 + 프레임(「안의 것 같이 움직임」 켠 것 — 기본 켬, 2026-10-18 사용자: Lucid Magnetize). 가운데가 틀 안이면 안의 것
  const boxes = items.filter(it => boardIds.includes(it._id) && (it.type === 'board' || (it.type === 'frame' && it.magnet !== false))).map(it => ({ id: it._id, r: sceneBox(it, textBox), board: it.type === 'board' }))
  if (!boxes.length) return []
  const picked = items.filter(it => !boardIds.includes(it._id) && !it.locked).filter(it => {
    const s = sceneBox(it, textBox), cx = s.x + s.w / 2, cy = s.y + s.h / 2
    if (it.type === 'frame') return boxes.some(({ r }) => s.x >= r.x && s.y >= r.y && s.x + s.w <= r.x + r.w && s.y + s.h <= r.y + r.h)   // 프레임 안 프레임은 통째로 들어 있을 때만(겹친 이웃 프레임까지 딸려 오지 않게)
    return boxes.some(({ r, board }) => !(board && it.type === 'board') && cx >= r.x && cx <= r.x + r.w && cy >= r.y && cy <= r.y + r.h)   // 보드 안 보드는 따로(전과 같음), 프레임 안 보드는 같이
  })
  // 겹친 틀(2026-10-26 실검증 — 큰 프레임을 끌면 겹친 이웃 프레임의 물건까지 딸려 옴): 물건의 주인 = 가운데를 담은 틀 중 가장 작은 것, 주인이 같이 움직일 때만
  const holders = items.filter(it => it.type === 'board' || it.type === 'frame').map(it => ({ id: it._id, r: sceneBox(it, textBox) }))
  const going = new Set([...boxes.map(b => b.id), ...picked.map(it => it._id)])
  return picked.filter(it => {
    if (it.type === 'frame') return true
    const s = sceneBox(it, textBox), cx = s.x + s.w / 2, cy = s.y + s.h / 2
    const own = holders.filter(h => h.id !== it._id && cx >= h.r.x && cx <= h.r.x + h.r.w && cy >= h.r.y && cy <= h.r.y + h.r.h).sort((a, b) => a.r.w * a.r.h - b.r.w * b.r.h)[0]
    return !own || going.has(own.id)
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

export const groupItems = (items, ids) => { const g = 'g' + newId(); return upd(items, ids, it => ({ ...it, group_id: g, sym_name: undefined })) }   // sym_name = 내 심볼·아이콘 이름(2026-10-27) — 새로 묶거나 풀면 더는 그 심볼이 아님
export const ungroupItems = (items, ids) => upd(items, ids, it => ({ ...it, group_id: null, sym_name: undefined }))
export const toggleLock = (items, ids) => { const lock = !items.filter(it => ids.includes(it._id)).every(it => it.locked); return upd(items, ids, it => ({ ...it, locked: lock })) }
// 맨 앞/맨 뒤(데스크톱 bring_to_front/send_to_back — 고른 것끼리 차례는 유지)
export function zOrder(items, ids, front) {
  const pool = items.filter(it => it.type !== 'titleblock'), sel = items.filter(it => ids.includes(it._id)).sort((a, b) => (a.z ?? 0) - (b.z ?? 0))
  const top = Math.max(0, ...pool.map(it => it.z ?? 0)), bot = Math.min(0, ...pool.map(it => it.z ?? 0))
  const z = new Map(front ? sel.map((it, i) => [it._id, top + 1 + i]) : [...sel].reverse().map((it, i) => [it._id, bot - 1 - i]))
  return items.map(it => (z.has(it._id) ? { ...it, z: z.get(it._id) } : it))
}
// 좌우·상하 반전(Shift+H/V) — 고른 것들 전체 상자 가운데를 축으로
export const FLIP_BODY = new Set(['image', 'symbol'])   // 반전하면 모양까지 뒤집는 상자류(네모·원은 대칭이라 뺌)
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
      default: {   // 상자류 = 자리 + 회전 반대로, 그림·심볼은 모양도 뒤집음(`flip_h`·`flip_v` — 2026-10-27 밤 사용자: 하나만 골라도 진짜로), 글·메모·표는 글을 읽게 자리만
        const s = sceneBox(it, textBox), nx = horizontal ? 2 * c - (s.x + s.w) : s.x, ny = horizontal ? s.y : 2 * c - (s.y + s.h)
        const k = horizontal ? 'flip_h' : 'flip_v', next = { ...it, ...(it.rotation ? { rotation: (360 - it.rotation) % 360 } : {}), ...(FLIP_BODY.has(it.type) ? { [k]: !it[k] || undefined } : {}) }
        const s2 = sceneBox(next, textBox); return { ...next, pos: [px + nx - s2.x, py + ny - s2.y] } }
    }
  })
}

// 크기 바뀐 도형에 붙은 점 = 같은 비율 자리로(데스크톱 `_set_box_rect` "상대 위치 유지"). 안 하면 오른쪽·아래로 키울 때 붙은 점이
// 도형 안에 남아 화살표가 떨어지고 자동 길은 크게 돌아감(2026-10-20 사용자 화면). prev = 고치기 전 목록, 묶음 붙음(`_group`)은 이미 비율이라 뺌
export function keepBinds(prev, next) {
  const before = new Map(prev.map(it => [it._id, it])), box = it => it.rect || (it.type === 'path' && localRect(it)), moved = new Map()
  for (const it of next) {
    const o = before.get(it._id); if (!o || o === it || o.type !== it.type) continue
    const a = box(o), b = a && box(it)
    if (b && (a[0] !== b[0] || a[1] !== b[1] || a[2] !== b[2] || a[3] !== b[3])) moved.set(it._id, [a, b])
  }
  if (!moved.size) return next
  return next.map(it => {
    if (it.type !== 'sarrow' && it.type !== 'arrow') return it
    const o = before.get(it._id); let out = it
    for (const k of ['bind1', 'bind2']) {
      const m = moved.get(it['_' + k]), pt = it[k + '_pt']
      if (!m || it[k + '_group'] || !pt || (o && o[k + '_pt'] !== pt && JSON.stringify(o[k + '_pt']) !== JSON.stringify(pt))) continue   // 이번에 새로 붙인 점은 그대로
      const [[x0, y0, w0, h0], [x1, y1, w1, h1]] = m
      out = { ...out, [k + '_pt']: [x1 + (w0 ? (pt[0] - x0) / w0 : 0.5) * w1, y1 + (h0 ? (pt[1] - y0) / h0 : 0.5) * h1] }
    }
    return out
  })
}

// 화살표 따라가기 — 편집 뒤 붙은 화살표 꼭짓점을 문서에 반영(「자동 길」은 다시 꺾고, 아니면 양 끝만 따라감 — 데스크톱 reroute)
export function followArrows(items, rectOf) {
  const routes = resolveRoutes(items, rectOf)
  const byId = new Map(items.map(it => [it._id, it]))
  return items.map((it, i) => {
    if (it.type === 'arrow') {   // 곡선: 붙은 끝만 따라가고 제어점도 같은 만큼(그린 곡선 보존, 데스크톱 `_ArrowItem.reroute`)
      let o = it
      for (const [k, idx] of [['_bind1', 0], ['_bind2', 1]]) {
        const e = bindEnd(it, k.slice(1), items, rectOf, byId); if (!e) continue   // 도형 또는 묶음(비율 자리)
        const q = toLocal(o, e.p), cur = idx ? o.p2 : o.p1
        if (Math.abs(q.x - cur[0]) > 1e-6 || Math.abs(q.y - cur[1]) > 1e-6) o = setCurveEnd(o, idx, [q.x, q.y])
      }
      return o
    }
    if (it.type !== 'sarrow') return it
    if (routes.has(i)) return { ...it, pts: routes.get(i) }
    let pts = it.pts, changed = false
    const manual = sarrowRouting(it) === 'ortho' && !it.auto_route && it.pts.length >= 3   // 손으로 그린 직각 길(데스크톱 `reroute` manual_ortho)
    const last = it.pts.length - 1, local = e => e && [e.p.x - (it.pos?.[0] || 0), e.p.y - (it.pos?.[1] || 0)]
    const e0 = local(bindEnd(it, 'bind1', items, rectOf, byId)), e1 = local(bindEnd(it, 'bind2', items, rectOf, byId))
    // 양끝이 같은 만큼 움직였으면(같은 도형·같이 옮긴 두 도형) 길 전체를 평행이동 — 모양 그대로(데스크톱 `reroute`의 지름길)
    if (e0 && e1) {
      const d0 = [e0[0] - pts[0][0], e0[1] - pts[0][1]], d1 = [e1[0] - pts[last][0], e1[1] - pts[last][1]]
      if ((d0[0] || d0[1]) && Math.abs(d0[0] - d1[0]) < 1e-6 && Math.abs(d0[1] - d1[1]) < 1e-6) return { ...it, pts: pts.map(([x, y]) => [x + d0[0], y + d0[1]]) }
    }
    for (const [lp, idx] of [[e0, 0], [e1, last]]) {
      if (!lp || (Math.abs(lp[0] - pts[idx][0]) <= 1e-6 && Math.abs(lp[1] - pts[idx][1]) <= 1e-6)) continue
      const step = idx ? -1 : 1, nb = idx + step, cur = pts[idx], q = pts[nb]
      const next = pts.map(p => [...p]); next[idx] = lp
      if (manual) {   // 세로 끝 구간이면 x를, 가로면 y를 같이 → 직각 유지. 같은 줄에 선 점들은 다 같이(옆 점만 밀면 그다음 구간이 사선이 됐다 — 2026-10-18 사용자 화면)
        const ax = Math.abs(cur[0] - q[0]) <= Math.abs(cur[1] - q[1]) ? 0 : 1, old = q[ax]
        for (let j = nb; j !== last - idx && j >= 0 && j <= last && Math.abs(pts[j][ax] - old) < 1e-6; j += step) next[j][ax] = lp[ax]
      }
      pts = next; changed = true
    }
    return changed ? { ...it, pts } : it
  })
}

// ── 표 행·열 넣기·지우기(2026-10-18, 데스크톱에도 아직 없음 — 웹 먼저) ──
// op = 'rowAbove'|'rowBelow'|'colLeft'|'colRight'|'delRow'|'delCol', (r, c) = 기준 칸. 행 높이·열 폭은 그대로 두고 표가 늘거나 줄어든다(넣는 열 = 기준 열 폭)
export function tableOp(it, op, r, c) {
  const out = tableOpBody(it, op, r, c)
  if (out === it || (!it.cell_styles && !it.cell_runs)) return out
  const shift = (i, at, del) => (del ? (i === at ? -1 : i > at ? i - 1 : i) : i >= at ? i + 1 : i)   // 넣은/지운 줄 뒤는 한 칸 밀림, 지운 줄은 사라짐
  const move = map => { if (!map) return undefined; const ns = {}
    for (const [k, v] of Object.entries(map)) {
      let [rr, cc] = k.split(',').map(Number)
      if (op === 'rowAbove') rr = shift(rr, r); else if (op === 'rowBelow') rr = shift(rr, r + 1); else if (op === 'delRow') rr = shift(rr, r, true)
      else if (op === 'colLeft') cc = shift(cc, c); else if (op === 'colRight') cc = shift(cc, c + 1); else if (op === 'delCol') cc = shift(cc, c, true)
      if (rr >= 0 && cc >= 0) ns[`${rr},${cc}`] = v
    }
    return ns }
  return { ...out, ...(it.cell_styles ? { cell_styles: move(it.cell_styles) } : {}), ...(it.cell_runs ? { cell_runs: move(it.cell_runs) } : {}) }   // 칸 꾸밈·칸 부분 서식
}
function tableOpBody(it, op, r, c) {
  const [x, y, w, h] = it.rect, rows = it.rows, cols = it.cols, re = rowEdges(y, h, it), rh = Array.from({ length: rows }, (_, i) => re[i + 1] - re[i])
  const fr = it.col_widths?.length === cols ? it.col_widths : Array(cols).fill(1 / cols), cw = fr.map(f => f * w)
  let cells = Array.from({ length: rows }, (_, i) => Array.from({ length: cols }, (_, j) => it.cells?.[i]?.[j] || ''))
  const rowsOut = hs => { const H = hs.reduce((a, b) => a + b, 0); return { rect: [x, y, w, H], ...(it.row_heights ? { row_heights: hs.map(v => v / H) } : {}) } }   // 행 높이를 따로 정한 표만 비율을 들고 감
  if (op === 'rowAbove' || op === 'rowBelow') { const at = op === 'rowAbove' ? r : r + 1, hs = [...rh]; hs.splice(at, 0, rh[r]); cells.splice(at, 0, Array(cols).fill('')); return { ...it, rows: rows + 1, cells, ...rowsOut(hs) } }   // 새 행 = 기준 행 높이
  if (op === 'delRow') { if (rows <= 1) return it; const hs = rh.filter((_, i) => i !== r); cells.splice(r, 1); return { ...it, rows: rows - 1, cells, ...rowsOut(hs) } }
  if (op === 'colLeft' || op === 'colRight') {
    const at = op === 'colLeft' ? c : c + 1, nw = cw[c]; cells = cells.map(row => { const n = [...row]; n.splice(at, 0, ''); return n })
    const ws = [...cw]; ws.splice(at, 0, nw); const W = w + nw
    return { ...it, cols: cols + 1, cells, col_widths: ws.map(v => v / W), rect: [x, y, W, h] }
  }
  if (op === 'delCol') {
    if (cols <= 1) return it
    cells = cells.map(row => row.filter((_, j) => j !== c)); const ws = cw.filter((_, j) => j !== c), W = w - cw[c]
    return { ...it, cols: cols - 1, cells, col_widths: ws.map(v => v / W), rect: [x, y, W, h] }
  }
  return it
}

// ── 종이틀 쪽 순서(데스크톱 `pdf_export._reading_order` 옮김 + 칸 우선) ──
// boxes = [{ x, y, w, h, ... }] → 순서대로. 'rows' = 줄 우선(위 줄부터 왼쪽 → 오른쪽, 위 가장자리가 앞 줄 높이의 절반 안이면 같은 줄 — CAD 리습의 지그재그),
// 'cols' = 칸 우선(왼쪽 칸부터 위 → 아래, 왼쪽 가장자리가 앞 칸 폭의 절반 안이면 같은 칸)
export function readingOrder(boxes, mode = 'rows') {
  const R = mode === 'cols', a = b => (R ? b.x : b.y), s = b => (R ? b.w : b.h), o = b => (R ? b.y : b.x)
  const sorted = [...boxes].sort((p, q) => a(p) - a(q) || o(p) - o(q))
  const lines = []; let line = [], top = 0, size = 0
  for (const b of sorted) {
    if (line.length && a(b) > top + size * 0.5) { lines.push(line); line = [] }
    if (!line.length) { top = a(b); size = s(b) } else size = Math.min(size, s(b))
    line.push(b)
  }
  if (line.length) lines.push(line)
  return lines.flatMap(l => l.sort((p, q) => o(p) - o(q)))
}

// 프레임 순서(출력 쪽·슬라이드) — `no` 오름차순, 같으면 문서 순서. 화면 번호는 늘 1..n(지운 자리·겹친 번호가 남지 않게)
export function orderedFrames(items) {
  return items.map((it, i) => [it, i]).filter(([it]) => it.type === 'frame').sort((a, b) => (a[0].no ?? 1e9) - (b[0].no ?? 1e9) || a[1] - b[1]).map(([it]) => it)
}
export function setFrameOrder(items, ids) { const no = new Map(ids.map((id, i) => [id, i + 1])); return items.map(it => (no.has(it._id) ? { ...it, no: no.get(it._id) } : it)) }
