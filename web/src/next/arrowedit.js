// 3-2 화살표 손질 — 데스크톱 `_PolyArrowItem` 알약(구간 평행 이동)·나눠 끌기·경유지 길, `_ArrowItem` 휨 손잡이·붙을 때 S자. 순수 함수(node 시험 대상).
// 꼭짓점은 화살표 안 좌표 [[x,y],…], z = 화면 배율(화면 px 규칙을 칠판 단위로 바꿀 때).
import { dedup } from '../route.js'

export const SEG_HANDLE_PX = 12   // 알약 반 길이(화면 px, `_SEG_HANDLE_PX`)
export const SEG_MIN_PX = 26      // 이보다 짧은 구간엔 알약 없음(`_SEG_MIN_PX`)
export const SEG_HIT_PX = 10      // 고른 직각 화살표의 구간 위로 치는 거리(`_segment_add_at`)
const SEG_SNAP_PX = 7             // 구간을 끌 때 양 끝·이웃 축에 붙는 거리(`_drag_segment_to`)
export const BEND_TS = [1 / 3, 2 / 3]

const horiz = (a, b) => Math.abs(b[1] - a[1]) <= Math.abs(b[0] - a[0])   // 수평 구간인가(`_segment_orientation`)

// 알약 자리 — 직각 화살표의 화면 26px 넘는 구간마다 가운데 [{ i, mid:[x,y], horizontal }]
export function segmentHandles(pts, z, scale = 1) {
  const out = [], min = SEG_MIN_PX / (z * scale)
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i], b = pts[i + 1]
    if (Math.hypot(b[0] - a[0], b[1] - a[1]) < min) continue
    out.push({ i, mid: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], horizontal: horiz(a, b) })
  }
  return out
}
// 가장 가까운 구간 → { i, proj:[x,y], d }
export function nearestSegment(pts, q) {
  let best = null
  for (let i = 0; i < pts.length - 1; i++) {
    const [ax, ay] = pts[i], [bx, by] = pts[i + 1], dx = bx - ax, dy = by - ay, L = dx * dx + dy * dy
    const t = L ? Math.max(0, Math.min(1, ((q.x - ax) * dx + (q.y - ay) * dy) / L)) : 0, proj = [ax + t * dx, ay + t * dy]
    const d = Math.hypot(q.x - proj[0], q.y - proj[1])
    if (!best || d < best.d) best = { i, proj, d }
  }
  return best
}
// 구간 위 투영점이 그 구간 알약 안인가(`_point_on_segment_pill`)
export function onPill(pts, i, proj, z, scale = 1) {
  const h = segmentHandles(pts, z, scale).find(x => x.i === i); if (!h) return false
  return (h.horizontal ? Math.abs(proj[0] - h.mid[0]) : Math.abs(proj[1] - h.mid[1])) <= SEG_HANDLE_PX / (z * scale)
}
// 알약 아닌 자리를 가리킬 때 미리보기 알약 — 가까운 절반의 가운데(`_segment_subdivide_preview_point`)
export function subdividePreview(pts, i, proj) {
  const a = pts[i], b = pts[i + 1], m = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], k = horiz(a, b) ? 0 : 1
  return Math.abs(proj[k] - a[k]) <= Math.abs(proj[k] - b[k]) ? [(a[0] + m[0]) / 2, (a[1] + m[1]) / 2] : [(m[0] + b[0]) / 2, (m[1] + b[1]) / 2]
}

// 구간 끌기 시작(`_begin_segment_drag`) — 끝점에 닿은 구간이면 끝점을 지키려 복제 꼭짓점을 끼움. → { pts, lo, hi, horizontal }
export function beginSegment(pts, i) {
  const p = pts.map(q => [...q]), horizontal = horiz(p[i], p[i + 1])
  // 이웃 구간이 끄는 구간과 나란하면(같은 줄에서 되돌아가는 짧은 출구 등) 끄는 순간 그 이웃이 사선이 된다 — 끝점처럼 꼭짓점을 한 벌 끼워
  // 직각 연결 구간을 새로 만든다(2026-10-18 사용자 화면: 펜 궤적 출구가 왼쪽 → 오른쪽으로 되돌아간 길의 알약을 끌자 사선)
  const par = (a, b) => (a[0] !== b[0] || a[1] !== b[1]) && horiz(a, b) === horizontal
  let lo = i, hi = i + 1
  if (lo === 0 || par(p[lo - 1], p[lo])) { p.splice(lo, 0, [...p[lo]]); lo++; hi++ }
  if (hi === p.length - 1 || par(p[hi], p[hi + 1])) p.splice(hi, 0, [...p[hi]])
  return { pts: p, lo, hi, horizontal }
}
// 알약 아닌 자리를 끌기(`_begin_subdivide_drag`) — 알약 자리에 꼭짓점 두 벌(고정 + 이동)을 끼우고 가까운 절반만 끎
export function beginSubdivide(pts, i, near, z, scale = 1) {
  const h = segmentHandles(pts, z, scale).find(x => x.i === i); if (!h) return null
  const p = pts.map(q => [...q]), a = p[i], b = p[i + 1], k = h.horizontal ? 0 : 1
  if (Math.abs(near[k] - a[k]) <= Math.abs(near[k] - b[k])) { p.splice(i + 1, 0, [...h.mid], [...h.mid]); return beginSegment(p, i) }
  p.splice(i + 1, 0, [...h.mid], [...h.mid]); return beginSegment(p, i + 2)
}
// 끄는 중(`_drag_segment_to`) — 구간을 수직 방향으로만, 양 끝·이웃 축 7px 안이면 붙음
export function dragSegment(seg, q, z, scale = 1) {
  const { lo, hi, horizontal } = seg, p = seg.pts.map(v => [...v]), k = horizontal ? 1 : 0, snap = SEG_SNAP_PX / (z * scale)
  const cand = [p[0][k], p[p.length - 1][k]]
  if (lo - 1 >= 0) cand.push(p[lo - 1][k])
  if (hi + 1 <= p.length - 1) cand.push(p[hi + 1][k])
  let c = horizontal ? q.y : q.x
  for (const t of cand) if (Math.abs(c - t) < snap) { c = t; break }
  p[lo][k] = c; p[hi][k] = c
  return p
}
// 끝(`_end_segment_drag`) — 겹친 점·한 줄 위 점 정리
export const endSegment = pts => { const d = dedup(pts.map(([x, y]) => ({ x, y }))).map(q => [q.x, q.y]); return d.length >= 2 ? d : pts }

// 경유지 꼭짓점 정리(`_dedup_hint`) — 경유지는 한 줄 위여도 남김(다시 잡을 수 있게)
export function dedupHint(pts, flags, eps = 1e-6) {
  const op = [pts[0]], of = [flags[0]]
  for (let i = 1; i < pts.length; i++) {
    const p = pts[i], q = op[op.length - 1]
    if (Math.abs(p.x - q.x) <= eps && Math.abs(p.y - q.y) <= eps) { of[of.length - 1] = of[of.length - 1] || flags[i]; continue }
    op.push(p); of.push(flags[i])
  }
  let i = 1
  while (i < op.length - 1) {
    if (of[i]) { i++; continue }
    const a = op[i - 1], b = op[i], c = op[i + 1]
    if (Math.abs((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)) <= eps) { op.splice(i, 1); of.splice(i, 1) } else i++
  }
  return op
}

// ── 곡선 화살표(`_ArrowItem`) ──
const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
export function curvePoint(it, t) {
  if (!it.ctrl1) return lerp(it.p1, it.p2, t)
  const u = 1 - t, [p1, c1, c2, p2] = [it.p1, it.ctrl1, it.ctrl2, it.p2]
  return [u * u * u * p1[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t * t * t * p2[0], u * u * u * p1[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t * t * t * p2[1]]
}
// 끝점 옮기기(`_set_endpoint`) — 그 쪽 제어점도 같은 만큼(그린 곡선 보존)
export function setCurveEnd(it, idx, p) {
  const k = idx ? 'p2' : 'p1', c = idx ? 'ctrl2' : 'ctrl1', d = [p[0] - it[k][0], p[1] - it[k][1]]
  return { ...it, [k]: [...p], ...(it[c] ? { [c]: [it[c][0] + d[0], it[c][1] + d[1]] } : {}) }
}
// 휨 손잡이 which(1 = t 1/3, 2 = t 2/3)가 target을 지나게 그 제어점을 역산(`_solve_ctrl`), 직선에 가까우면 다시 직선
export function bendCurve(it, which, target, width = 2, scale = 1) {
  let o = { ...it }
  if (!o.ctrl1) o = { ...o, ctrl1: lerp(o.p1, o.p2, BEND_TS[0]), ctrl2: lerp(o.p1, o.p2, BEND_TS[1]) }
  const [p1, p2] = [o.p1, o.p2]
  if (which === 1) o.ctrl1 = [(27 * target[0] - 8 * p1[0] - 6 * o.ctrl2[0] - p2[0]) / 12, (27 * target[1] - 8 * p1[1] - 6 * o.ctrl2[1] - p2[1]) / 12]
  else o.ctrl2 = [(27 * target[0] - p1[0] - 6 * o.ctrl1[0] - 8 * p2[0]) / 12, (27 * target[1] - p1[1] - 6 * o.ctrl1[1] - 8 * p2[1]) / 12]
  const th = Math.max(6, width * 2) / scale, s1 = lerp(p1, p2, BEND_TS[0]), s2 = lerp(p1, p2, BEND_TS[1])
  if (Math.hypot(o.ctrl1[0] - s1[0], o.ctrl1[1] - s1[1]) < th && Math.hypot(o.ctrl2[0] - s2[0], o.ctrl2[1] - s2[1]) < th) { o.ctrl1 = null; o.ctrl2 = null }
  return o
}
// 끝을 도형에 붙였을 때 S자로 다시 휨(`_recompute_snap_curve`) — n0·n1 = 두 끝의 바깥 법선(없으면 null)
export function snapCurve(it, n0, n1) {
  const [p1, p2] = [it.p1, it.p2], dx = p2[0] - p1[0], dy = p2[1] - p1[1], dist = Math.hypot(dx, dy)
  if ((!n0 && !n1) || dist < 8) return { ...it, ctrl1: null, ctrl2: null }
  const k = Math.max(30, Math.min(dist * 0.5, 200)), e1 = n0 || { x: dx / dist, y: dy / dist }, e2 = n1 || { x: -e1.x, y: -e1.y }
  return { ...it, ctrl1: [p1[0] + e1.x * k, p1[1] + e1.y * k], ctrl2: [p2[0] + e2.x * k, p2[1] + e2.y * k] }
}

// ── 화살표 라벨(데스크톱 `_ConnectorLabel`) ──
export const LABEL_SIDE_GAP = 2   // `_LABEL_SIDE_GAP` — 옆으로 뺀 라벨과 선 사이
// 점 → 꺾은선 위 길이 비율 t와 왼쪽 법선 쪽 부호 있는 거리(`_project_to_path`). pts = [{x,y}]
export function projectToPath(pts, p) {
  let total = 0; const segs = []
  for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y); segs.push([pts[i - 1], pts[i], d]); total += d }
  if (total < 1e-9) return { t: 0.5, off: 0 }
  let best = null, run = 0
  for (const [a, b, d] of segs) {
    if (d < 1e-9) continue
    const dx = b.x - a.x, dy = b.y - a.y, tt = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / (d * d))), px = a.x + dx * tt, py = a.y + dy * tt
    const dist = Math.hypot(p.x - px, p.y - py)
    if (!best || dist < best[0]) best = [dist, run + d * tt, (-dy * (p.x - px) + dx * (p.y - py)) / d]
    run += d
  }
  return { t: best[1] / total, off: best[2] }
}
// 옆 거리를 세 자리 중 하나로(`_snap_label_off`): 선 위(0) / 왼쪽 / 오른쪽 — 반 너비 + 2, 그 절반 안이면 선 위
export function snapLabelOff(n, rawOff, w, h) {
  const D = Math.abs(n.x) * w / 2 + Math.abs(n.y) * h / 2 + LABEL_SIDE_GAP
  return Math.abs(rawOff) < D * 0.5 ? 0 : rawOff > 0 ? D : -D
}
// 곡선(직선 포함) 화살표에 투영 — 매개변수 120토막 중 가장 가까운 t, 거리 = 그 자리 왼쪽 법선 성분(`_project_to_curve`)
export function projectToCurve(it, p) {
  let bt = 0.5, bd = Infinity
  for (let i = 0; i <= 120; i++) { const q = curvePoint(it, i / 120), d = (p.x - q[0]) ** 2 + (p.y - q[1]) ** 2; if (d < bd) { bd = d; bt = i / 120 } }
  const a = curvePoint(it, Math.max(0, bt - 1e-3)), b = curvePoint(it, Math.min(1, bt + 1e-3)), q = curvePoint(it, bt), tx = b[0] - a[0], ty = b[1] - a[1], L = Math.hypot(tx, ty)
  const n = L < 1e-9 ? { x: 0, y: -1 } : { x: -ty / L, y: tx / L }
  return { t: bt, off: (p.x - q[0]) * n.x + (p.y - q[1]) * n.y }
}
