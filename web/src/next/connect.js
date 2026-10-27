// 3단계 화살표 — 붙는 규칙(데스크톱 `core_shapes` `_nearest_border`·`_shape_ports`·`_is_conn_host`, `core_view` `_border_snap_at`·`_qc_snap_target`를 옮김).
// 순수 함수(node 시험 대상, `tools/export_connect_cases.py`가 데스크톱 답을 뽑아 `test/connect.test.mjs`가 대조). 점 {x,y}.
// rectOf(it) = 도형 안 좌표의 바탕 사각형 [x,y,w,h] — 글 상자는 화면에서 잰 크기라 호출부가 준다(Editor의 textBox).
import { toLocal, toScene } from './xform.js'
import { symbolPath } from './symbols.js'
import { flatten } from './geom.js'

export const PORT_SNAP_PX = 18     // 데스크톱 `_PORT_SNAP_PX`(화면 px) — 포트(변 가운데) 먼저
export const BORDER_SNAP_PX = 14   // `_BORDER_SNAP_PX` — 없으면 테두리 아무 자리
export const QC_GAP_PX = 24        // `_QC_DOT_GAP_PX` — 큐닷은 외곽선에서 바깥으로 24
export const QC_GAP = 40           // `_QC_GAP` — 큐닷 클릭 복제의 원본과 간격(칠판 단위)
export const SIDES = ['t', 'r', 'b', 'l']   // `_shape_ports` 차례(상·우·하·좌)
export const OPP = { t: 'b', b: 't', l: 'r', r: 'l' }

// 화살표가 붙는 도형인가(`_is_conn_host`) — 상자·원·심볼·이미지·표·닫힌 다각형·글
export const ROUTE_BOX = new Set(['rect', 'ellipse', 'symbol', 'image', 'table', 'web', 'memo', 'doc', 'pdf'])   // `_ROUTE_BOX_TYPES`(길 찾기 장애물·연결 상자)
// 프레임 = 속 빈 틀(2026-10-23 사용자: 큐닷이 없어 화살표가 안 붙음) — 테두리에만 붙고, 안(빈 곳)은 안의 도형 몫. 길 찾기 장애물도 아님(ROUTE_BOX 밖 — 안의 화살표가 틀을 피해 돌지 않게)
export const isHollow = it => it?.type === 'frame'
export const isConnHost = it => !!it && (ROUTE_BOX.has(it.type) || (it.type === 'polygon' && it.closed) || it.type === 'text' || isHollow(it))
// 화살표 끝이 붙어 따라다닐 수 있는 것 = 위 도형 + 펜 궤적(데스크톱 `_conn_paths` — 양 끝 포트·궤적 어디든, 지속 연결 됨)
export const isBindHost = it => isConnHost(it) || it?.type === 'path'
// 끝이 '좌표로만' 붙는 것 = 선·화살표·열린 다각형(데스크톱 `_conn_lines` — 연결은 안 걸림)
export const isSnapLine = it => !!it && (it.type === 'line' || it.type === 'arrow' || it.type === 'sarrow' || (it.type === 'polygon' && !it.closed))

// ── 도형 안 좌표에서 가장 가까운 외곽선 점 + 바깥 법선 ──
function rectNearest([l, t, w, h], p) {
  const r = l + w, b = t + h
  if (p.x >= l && p.x <= r && p.y >= t && p.y <= b) {
    const dl = p.x - l, dr = r - p.x, dt = p.y - t, db = b - p.y, m = Math.min(dl, dr, dt, db)
    if (m === dl) return [{ x: l, y: p.y }, { x: -1, y: 0 }]
    if (m === dr) return [{ x: r, y: p.y }, { x: 1, y: 0 }]
    if (m === dt) return [{ x: p.x, y: t }, { x: 0, y: -1 }]
    return [{ x: p.x, y: b }, { x: 0, y: 1 }]
  }
  const qx = Math.min(Math.max(p.x, l), r), qy = Math.min(Math.max(p.y, t), b)
  let nx = qx === l && p.x < l ? -1 : qx === r && p.x > r ? 1 : 0, ny = qy === t && p.y < t ? -1 : qy === b && p.y > b ? 1 : 0
  if (!nx && !ny) ny = -1
  const L = Math.hypot(nx, ny) || 1
  return [{ x: qx, y: qy }, { x: nx / L, y: ny / L }]
}
function ellipseNearest([l, t, w, h], p) {   // 매개변수 각 뉴턴 4번(`_ellipse_nearest`)
  const cx = l + w / 2, cy = t + h / 2, a = w / 2, b = h / 2, ux = p.x - cx, uy = p.y - cy
  if (a < 1e-6 || b < 1e-6) return [{ x: cx, y: cy }, { x: 0, y: -1 }]
  let th = Math.atan2(a * uy, b * ux)
  for (let i = 0; i < 4; i++) {
    const ct = Math.cos(th), st = Math.sin(th), x = a * ct, y = b * st
    const f = (x - ux) * (-a * st) + (y - uy) * (b * ct), fp = a * a * st * st - a * ct * (x - ux) + b * b * ct * ct - b * st * (y - uy)
    if (Math.abs(fp) < 1e-9) break
    th -= f / fp
  }
  const ct = Math.cos(th), st = Math.sin(th), nx = ct / a, ny = st / b, L = Math.hypot(nx, ny) || 1
  return [{ x: cx + a * ct, y: cy + b * st }, { x: nx / L, y: ny / L }]
}
// 꺾은선 여러 개에서 가장 가까운 점, 법선은 그 변에 수직·가운데 c 반대쪽(`_symbol_nearest`·`_polygon_nearest`)
function polysNearest(polys, p, c) {
  let best = null, seg = null, bd = Infinity
  for (const poly of polys) for (let i = 0; i < poly.length - 1; i++) {
    const a = poly[i], b = poly[i + 1], abx = b.x - a.x, aby = b.y - a.y, den = abx * abx + aby * aby
    const t = den < 1e-12 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * abx + (p.y - a.y) * aby) / den)), q = { x: a.x + t * abx, y: a.y + t * aby }
    const d = (q.x - p.x) ** 2 + (q.y - p.y) ** 2
    if (d < bd) { bd = d; best = q; seg = [a, b] }
  }
  if (!best) return null
  let nx = -(seg[1].y - seg[0].y), ny = seg[1].x - seg[0].x
  if ((best.x - c.x) * nx + (best.y - c.y) * ny < 0) { nx = -nx; ny = -ny }
  const L = Math.hypot(nx, ny) || 1
  return [best, { x: nx / L, y: ny / L }]
}
// 변 가운데 넷(상·우·하·좌)·사각형 모서리면 법선을 축으로 고정(`_axis_forced_local_normal`)
const CARD = [{ x: 0, y: -1 }, { x: 1, y: 0 }, { x: 0, y: 1 }, { x: -1, y: 0 }]
function axisForce(it, [l, t, w, h], q, n) {
  const cx = l + w / 2, cy = t + h / 2, eps = 1e-4 * Math.max(w, h, 1), near = (x, y) => Math.abs(q.x - x) < eps && Math.abs(q.y - y) < eps
  const cards = [[cx, t], [l + w, cy], [cx, t + h], [l, cy]]
  for (let i = 0; i < 4; i++) if (near(...cards[i])) return CARD[i]
  if (it.type === 'rect') for (const [x, y] of [[l, t], [l + w, t], [l + w, t + h], [l, t + h]]) if (near(x, y)) return w >= h ? { x: x > cx ? 1 : -1, y: 0 } : { x: 0, y: y > cy ? 1 : -1 }
  return n
}

// 심볼 외곽선 → 도형 안 좌표 꺾은선들(곡선은 잘게 — 데스크톱 Qt 평탄화와 0.1 안쪽)
const CURVE_STEPS = 24
function parsePath(d) {
  const out = []; let sub = null, cur = null
  const tok = d.match(/[A-Za-z]|-?[\d.]+(?:e-?\d+)?/g) || []
  for (let i = 0; i < tok.length;) {
    const c = tok[i++], num = () => +tok[i++]
    if (c === 'M') { cur = { x: num(), y: num() }; sub = [cur]; out.push(sub) }
    else if (c === 'L') { cur = { x: num(), y: num() }; sub.push(cur) }
    else if (c === 'C') {
      const c1 = { x: num(), y: num() }, c2 = { x: num(), y: num() }, p3 = { x: num(), y: num() }, p0 = cur
      for (let k = 1; k <= CURVE_STEPS; k++) { const s = k / CURVE_STEPS, u = 1 - s
        sub.push({ x: u * u * u * p0.x + 3 * u * u * s * c1.x + 3 * u * s * s * c2.x + s * s * s * p3.x, y: u * u * u * p0.y + 3 * u * u * s * c1.y + 3 * u * s * s * c2.y + s * s * s * p3.y }) }
      cur = p3
    } else if (c === 'Z' || c === 'z') { if (sub?.length) sub.push({ ...sub[0] }) }
  }
  return out
}
const arcPts = (cx, cy, r, a0, a1) => Array.from({ length: CURVE_STEPS + 1 }, (_, k) => { const a = a0 + ((a1 - a0) * k) / CURVE_STEPS; return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) } })
export function symbolPolys(kind, rect, it) {   // it = 뒤집힌 심볼(`flip_h`·`flip_v`)이면 테두리도 상자 가운데 기준으로 뒤집음(2026-10-27 밤)
  const ps = symbolPolys0(kind, rect), [x, y, w, h] = rect, fx = !!it?.flip_h, fy = !!it?.flip_v
  return fx || fy ? ps.map(pl => pl.map(p => ({ x: fx ? 2 * x + w - p.x : p.x, y: fy ? 2 * y + h - p.y : p.y }))) : ps
}
function symbolPolys0(kind, [x, y, w, h]) {
  const off = ps => ps.map(p => ({ x: p.x + x, y: p.y + y }))
  if (kind === 'terminal') { const r = Math.min(h, w) / 2, H = Math.PI / 2   // symbols.js와 같은 모양(둥근 모서리 넷)
    return [off([...arcPts(w - r, r, r, -H, 0), ...arcPts(w - r, h - r, r, 0, H), ...arcPts(r, h - r, r, H, 2 * H), ...arcPts(r, r, r, 2 * H, 3 * H), { x: w - r, y: 0 }])] }
  if (kind === 'delay') { const sx = w * 0.62, r = h / 2
    return [off([{ x: 0, y: 0 }, { x: sx, y: 0 }, ...arcPts(sx, h / 2, r, -Math.PI / 2, Math.PI / 2), { x: 0, y: h }, { x: 0, y: 0 }])] }
  return parsePath(symbolPath(kind, w, h).d).map(off)
}

function nearestLocal(it, rect, q) {
  const [l, t, w, h] = rect, c = { x: l + w / 2, y: t + h / 2 }
  if (it.type === 'path') { const r = polysNearest(flatten(it.elements), q, c); if (r) return r }   // 펜 궤적(`_path_nearest` — 기준 = 궤적 바탕 상자 가운데)
  if (it.type === 'ellipse') { const [p, n] = ellipseNearest(rect, q); return [p, axisForce(it, rect, p, n)] }
  if (it.type === 'symbol') { const r = polysNearest(symbolPolys(it.kind, rect, it), q, c); if (r) return [r[0], axisForce(it, rect, r[0], r[1])] }
  if (it.type === 'polygon' && it.closed && it.pts?.length > 2) { const pts = it.pts.map(([x, y]) => ({ x, y })); const r = polysNearest([[...pts, pts[0]]], q, c); if (r) return r }
  const [p, n] = rectNearest(rect, q)
  return [p, it.type === 'polygon' ? n : axisForce(it, rect, p, n)]
}
// 칠판 점 → 외곽선 위 가장 가까운 점·바깥 법선(칠판 좌표, 회전·배율 반영)
export function nearestBorder(it, sp, rectOf) {
  const rect = rectOf(it), [q, n] = nearestLocal(it, rect, toLocal(it, sp))
  const p = toScene(it, q), e = toScene(it, { x: q.x + n.x, y: q.y + n.y }), L = Math.hypot(e.x - p.x, e.y - p.y) || 1
  return { p, n: { x: (e.x - p.x) / L, y: (e.y - p.y) / L } }
}
// 포트 넷(상·우·하·좌) = 변 가운데를 실제 외곽선에 투영(삼각형은 세 변 가운데 + 꼭짓점)
export function shapePorts(it, rectOf) {
  const [l, t, w, h] = rectOf(it), cx = l + w / 2, cy = t + h / 2
  const pts = it.type === 'symbol' && it.kind === 'triangle'
    ? [{ x: (l + w + l) / 2, y: (cy + t) / 2 }, { x: l + w, y: cy }, { x: (l + l + w) / 2, y: (t + h + cy) / 2 }, { x: l, y: cy }]
    : [{ x: cx, y: t }, { x: l + w, y: cy }, { x: cx, y: t + h }, { x: l, y: cy }]
  return pts.map((q, i) => ({ side: SIDES[i], ...nearestBorder(it, toScene(it, q), rectOf) }))
}
// 펜 궤적의 포트 = 양 끝 2점, 법선 = 바로 옆 점에서 바깥(`_path_endpoint_ports`)
export function pathEndPorts(it) {
  const pts = flatten(it.elements).flat(); if (pts.length < 2) return []
  const out = (p, ref, side) => { const a = toScene(it, p), b = toScene(it, ref), L = Math.hypot(a.x - b.x, a.y - b.y) || 1; return { side, p: a, n: { x: (a.x - b.x) / L, y: (a.y - b.y) / L } } }
  return [out(pts[0], pts[1], 's'), out(pts[pts.length - 1], pts[pts.length - 2], 'e')]
}
export const hostPorts = (it, rectOf) => (it.type === 'path' ? pathEndPorts(it) : shapePorts(it, rectOf))
// 선·화살표의 몸통 점열(칠판) — `_conn_polyline_scene`
export function linePolyline(it) {
  const S = v => toScene(it, v), P = ([x, y]) => ({ x, y })
  if (it.type === 'line') return [S({ x: it.line[0], y: it.line[1] }), S({ x: it.line[2], y: it.line[3] })]
  if (it.type === 'arrow') return it.ctrl1 ? flatten([['M', ...it.p1], ['C', ...it.ctrl1, ...it.ctrl2, ...it.p2]])[0].map(S) : [S(P(it.p1)), S(P(it.p2))]
  return (it.pts || []).map(P).map(S)
}
// 끝점 둘 + 바깥 방향(`_conn_endpoint_dirs`)
function lineEnds(it) {
  const pl = linePolyline(it); if (pl.length < 2) return []
  const u = (a, b) => { const L = Math.hypot(a.x - b.x, a.y - b.y) || 1; return { x: (a.x - b.x) / L, y: (a.y - b.y) / L } }
  return [{ p: pl[0], n: u(pl[0], pl[1]) }, { p: pl[pl.length - 1], n: u(pl[pl.length - 1], pl[pl.length - 2]) }]
}
// 몸통 가장 가까운 점 + 커서 쪽 수직(`_nearest_on_polyline`)
function onPolyline(pl, sp) {
  let best = null, bd = Infinity
  for (let i = 0; i < pl.length - 1; i++) {
    const a = pl[i], b = pl[i + 1], dx = b.x - a.x, dy = b.y - a.y, L2 = dx * dx + dy * dy
    const t = L2 < 1e-12 ? 0 : Math.max(0, Math.min(1, ((sp.x - a.x) * dx + (sp.y - a.y) * dy) / L2)), q = { x: a.x + dx * t, y: a.y + dy * t }
    const d = (sp.x - q.x) ** 2 + (sp.y - q.y) ** 2
    if (d < bd) { const L = Math.sqrt(L2) || 1; let n = L2 < 1e-12 ? { x: 0, y: -1 } : { x: -dy / L, y: dx / L }; if (n.x * (sp.x - q.x) + n.y * (sp.y - q.y) < 0) n = { x: -n.x, y: -n.y }; bd = d; best = { p: q, n } }
  }
  return best
}
// 큐닷 자리(칠판) — 포트에서 바깥 법선으로 화면 24px(`_qc_dot_rects`)
export const qcDots = (it, rectOf, z) => shapePorts(it, rectOf).map(({ side, p, n }) => ({ side, p: { x: p.x + (n.x * QC_GAP_PX) / z, y: p.y + (n.y * QC_GAP_PX) / z }, port: p, n }))

// 끄는 끝이 붙을 곳(`_border_snap_at`) — ① 포트 18px(도형·펜 궤적 끝, 같으면 나중 것) → 선·화살표 끝점(같으면 도형이 이김)
// ② 외곽선·궤적 14px → 선·화살표 몸통 ③ 없음. z = 화면 배율.
// → { id, p, n, port } | null — 선·화살표에 붙으면 id = null(좌표만, 연결 없음). hosts = 붙는 도형·펜 궤적(위에 그린 것이 뒤), lines = 선·화살표
export function snapAt(hosts, sp, z, rectOf, lines = []) {
  const dist = q => Math.hypot(q.x - sp.x, q.y - sp.y) * z
  let best = null, bd = PORT_SNAP_PX
  for (const it of hosts) for (const q of hostPorts(it, rectOf)) { const d = dist(q.p); if (d <= bd) { bd = d; best = { id: it._id, p: q.p, n: q.n, port: true } } }
  for (const it of lines) for (const q of lineEnds(it)) { const d = dist(q.p); if (d < bd) { bd = d; best = { id: null, p: q.p, n: q.n, port: true } } }   // ⚠ 동점은 도형(연결 정보가 더 많음)
  if (best) return best
  bd = BORDER_SNAP_PX
  for (const it of hosts) { const q = nearestBorder(it, sp, rectOf), d = dist(q.p); if (d <= bd) { bd = d; best = { id: it._id, p: q.p, n: q.n, port: false } } }
  for (const it of lines) { const q = onPolyline(linePolyline(it), sp); if (q) { const d = dist(q.p); if (d <= bd) { bd = d; best = { id: null, p: q.p, n: q.n, port: false } } } }
  return best
}
// 큐닷·포트점을 끌어 놓을 때(`_qc_snap_target`): 붙을 곳이 없으면 다른 도형 '안'에 놓은 것도 그 도형의 가장 가까운 포트로
export function dropTarget(hosts, sp, z, rectOf, srcId, lines = []) {
  const s = snapAt(hosts, sp, z, rectOf, lines); if (s) return s
  for (let i = hosts.length - 1; i >= 0; i--) {
    const it = hosts[i]; if (it._id === srcId || it.type === 'path' || isHollow(it)) continue   // 펜 궤적·프레임엔 '안'이 없음
    const [l, t, w, h] = rectOf(it), q = toLocal(it, sp)
    if (q.x < l || q.x > l + w || q.y < t || q.y > t + h) continue
    let best = null, bd = Infinity
    for (const pt of shapePorts(it, rectOf)) { const d = Math.hypot(pt.p.x - sp.x, pt.p.y - sp.y); if (d < bd) { bd = d; best = { id: it._id, p: pt.p, n: pt.n, port: true } } }
    return best
  }
  return null
}

// ── 묶음 통째 붙기(데스크톱 `_GroupBindProxy`) — 묶음 멤버 전체를 감싼 칠판 사각형을 '가상 상자' 하나로 다룬다.
// 가상 상자는 pos 0·회전 없음이라 안 좌표 = 칠판 좌표 → 위의 포트·외곽선·붙기 계산을 그대로 쓴다. 저장은 bindN_group + 0~1 비율(bindN_pt).
export function groupHost(items, gid, rectOf) {
  let l = Infinity, t = Infinity, r = -Infinity, b = -Infinity
  for (const m of items) {
    if (m.group_id !== gid) continue
    // 데스크톱 `_group_bbox_scene`은 멤버의 `_content_rect`(Qt boundingRect — 선 두께 절반, 원은 +1, 그림·표·보드·글은 0)를 감싼다
    const e = m.type === 'ellipse' ? (m.width || 0) / 2 + 1 : ['rect', 'symbol', 'polygon', 'path', 'line'].includes(m.type) ? (m.width || 0) / 2 : 0
    const [x0, y0, w0, h0] = rectOf(m), x = x0 - e, y = y0 - e, w = w0 + 2 * e, h = h0 + 2 * e
    for (const [a, c] of [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]) { const q = toScene(m, { x: a, y: c }); l = Math.min(l, q.x); t = Math.min(t, q.y); r = Math.max(r, q.x); b = Math.max(b, q.y) }
  }
  return l === Infinity ? null : { _id: 'g:' + gid, type: 'group', group: gid, pos: [0, 0], rect: [l, t, r - l, b - t] }
}
export const groupFrac = (g, p) => { const [l, t, w, h] = g.rect; return [w > 1e-6 ? (p.x - l) / w : 0.5, h > 1e-6 ? (p.y - t) / h : 0.5] }   // `mapFromScene`
export const groupPoint = (g, f) => { const [l, t, w, h] = g.rect; return { x: l + f[0] * w, y: t + f[1] * h } }   // `mapToScene`
// 화살표 끝 하나의 붙은 자리(칠판) — 도형이면 그 안 고정점, 묶음이면 지금 감싼 사각형의 비율 자리. 안 붙었으면 null
export function bindEnd(it, k, items, rectOf, byId) {
  const gid = it[k + '_group'], pt = it[k + '_pt']; if (!pt) return null
  if (gid) { const g = groupHost(items, gid, rectOf); return g && { host: g, p: groupPoint(g, pt) } }
  const id = it['_' + k], host = id != null && (byId ? byId.get(id) : items.find(x => x._id === id))
  return host ? { host, p: toScene(host, { x: pt[0], y: pt[1] }) } : null
}

// 칠판 점 → 도형 안 고정점(.ecad bindN_pt) / 그 반대
export const bindPt = (it, sp) => { const q = toLocal(it, sp); return [q.x, q.y] }
export const bindScene = (it, pt) => toScene(it, { x: pt[0], y: pt[1] })

// 큐닷 클릭 복제의 자리(`_qc_default_delta`) — 원본 칠판 상자에서 그 방향으로 (크기 + 40)
export function qcDelta(box, side) {
  return { r: [box.w + QC_GAP, 0], l: [-(box.w + QC_GAP), 0], b: [0, box.h + QC_GAP], t: [0, -(box.h + QC_GAP)] }[side]
}
// 칠판 상자의 변 가운데(`_edge_mid`)
export function edgeMid(box, side) {
  return { r: { x: box.x + box.w, y: box.y + box.h / 2 }, l: { x: box.x, y: box.y + box.h / 2 }, t: { x: box.x + box.w / 2, y: box.y }, b: { x: box.x + box.w / 2, y: box.y + box.h } }[side]
}
