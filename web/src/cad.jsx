// Magic Board 웹 칠판의 CAD 층 — 직각 화살표(sarrow: 구간 손잡이·끝점 다시 붙이기·지속 연결), 큐닷·포트점, TRIM.
// web_bakeoff/src/sarrow.jsx(2026-10-17 시험)에서 옮김. 데스크톱 core_shapes `_PolyArrowItem`·core_view `_border_snap_at`에 해당.
// 2026-10-17 사용자 요청("기본 도형 기능은 magic board를 많이 참고") — 붙는 규칙·길 찾기를 데스크톱과 같게:
//  - 끄는 끝은 포트(변 가운데)에 18px 안이면 그 포트로, 아니면 테두리 14px 안이면 그 자리로, 아니면 떠 있는 끝(안 붙음).
//  - 붙은 자리는 도형 안 고정점(비율 nx·ny) — 상자를 옮기거나 키워도 같은 자리.
//  - 미선택 상자는 테두리에 다가가면 포트점(예고), 선택한 상자는 큐닷. 둘 다 끌면 화살표.
//  - 끝점 손잡이를 끌어 다시 붙이거나 떼기. 길 찾기는 route.js(데스크톱 _route_ortho 그대로).
import { ShapeUtil, BindingUtil, OverlayUtil, StateNode, SVGContainer, Polyline2d, Circle2d, Vec, T, createShapeId } from 'tldraw'
import { getIndices } from '@tldraw/utils'
import { routeOrtho } from './route.js'
import { ink } from './shapes.jsx'

const DIR = { left: [-1, 0], right: [1, 0], top: [0, -1], bottom: [0, 1] }
const RATIO = { left: [0, 0.5], right: [1, 0.5], top: [0.5, 0], bottom: [0.5, 1] }
export const PORT_SNAP_PX = 18     // 데스크톱 _PORT_SNAP_PX(화면 px)
export const BORDER_SNAP_PX = 14   // 데스크톱 _BORDER_SNAP_PX
const CORNER_R = 10                // 꺾인 곳 둥글기(데스크톱 화살표 모서리 반경)
const STUB_MARGIN = 4              // 화살촉 + 모서리 + 여유 = 첫 꺾임까지 최소 직선(데스크톱 _min_stub_for)
const headLen = width => 8 + width * 2.4

const isBox = s => s && (s.type === 'geo' || s.type === 'esym')
const rectOf = b => ({ l: b.minX, t: b.minY, r: b.maxX, b: b.maxY })
// 붙은 자리(페이지 좌표) — nx·ny(도형 안 비율)가 있으면 그 자리, 없으면 변 가운데(옛 저장본)
export function anchorOf(bounds, props) {
  const [nx, ny] = props.nx != null ? [props.nx, props.ny] : RATIO[props.side]
  return { x: bounds.minX + nx * bounds.w, y: bounds.minY + ny * bounds.h }
}
const normalOf = side => (side ? { x: DIR[side][0], y: DIR[side][1] } : null)

// 테두리 위 가장 가까운 점과 그 변
export function nearestBorder(b, p) {
  const cx = Math.min(Math.max(p.x, b.minX), b.maxX), cy = Math.min(Math.max(p.y, b.minY), b.maxY)
  const opts = [['left', { x: b.minX, y: cy }], ['right', { x: b.maxX, y: cy }], ['top', { x: cx, y: b.minY }], ['bottom', { x: cx, y: b.maxY }]]
  return opts.reduce((best, o) => (Vec.Dist(o[1], p) < Vec.Dist(best[1], p) ? o : best))
}

// 끄는 끝이 붙을 곳 — 데스크톱 _border_snap_at: ① 포트 18px ② 테두리 14px ③ 없음. 같은 거리면 앞의 것(포트).
// → { shapeId, side, nx, ny, p } | null
export function snapAt(editor, pt, { exclude } = {}) {
  const z = editor.getZoomLevel(), boxes = editor.getCurrentPageShapes().filter(s => isBox(s) && s.id !== exclude)
  let best = null, bd = PORT_SNAP_PX
  for (const s of boxes) {
    const b = editor.getShapePageBounds(s.id); if (!b) continue
    for (const side of Object.keys(DIR)) {
      const [nx, ny] = RATIO[side], p = { x: b.minX + nx * b.w, y: b.minY + ny * b.h }, d = Vec.Dist(p, pt) * z
      if (d <= bd) { bd = d; best = { shapeId: s.id, side, nx, ny, p, port: true } }
    }
  }
  if (best) return best
  bd = BORDER_SNAP_PX
  for (const s of boxes) {
    const b = editor.getShapePageBounds(s.id); if (!b) continue
    const [side, p] = nearestBorder(b, pt), d = Vec.Dist(p, pt) * z
    if (d <= bd) { bd = d; best = { shapeId: s.id, side, nx: b.w ? (p.x - b.minX) / b.w : 0.5, ny: b.h ? (p.y - b.minY) / b.h : 0.5, p, port: false } }
  }
  return best
}

// 화살표 다시 그리기 — 붙은 끝은 도형의 고정점, 떠 있는 끝은 props.free0(시작)·free(끝) {x,y,side?}
export function reroute(editor, arrowId) {
  const arrow = editor.getShape(arrowId); if (!arrow) return
  const ends = {}, conn = [null, null], bound = new Set()
  for (const b of editor.getBindingsFromShape(arrowId, 'sarrow')) {
    const bounds = editor.getShapePageBounds(b.toId); if (!bounds) continue
    ends[b.props.terminal] = { p: anchorOf(bounds, b.props), n: normalOf(b.props.side) }
    conn[b.props.terminal === 'start' ? 0 : 1] = rectOf(bounds); bound.add(b.toId)
  }
  for (const [t, key] of [['start', 'free0'], ['end', 'free']]) {
    const f = arrow.props[key]
    if (ends[t] || !f) continue
    ends[t] = { p: { x: f.x, y: f.y }, n: normalOf(f.side) }
    const fb = f.shapeId && editor.getShapePageBounds(f.shapeId)   // 끄는 동안 붙을 상자 = 연결 도형으로(장애물로 두면 길이 출발 상자를 뚫음)
    if (fb) { conn[t === 'start' ? 0 : 1] = rectOf(fb); bound.add(f.shapeId) }
  }
  if (!ends.start || !ends.end) return
  const obstacles = editor.getCurrentPageShapes().filter(sh => isBox(sh) && !bound.has(sh.id)).map(sh => rectOf(editor.getShapePageBounds(sh.id)))
  let pts = routeOrtho(ends.start.p, ends.start.n, ends.end.p, ends.end.n, obstacles,
    { conn, minStub: [0, headLen(arrow.props.width) + CORNER_R + STUB_MARGIN] })
  const m = arrow.props.manual                                        // 끈 구간(안쪽, 같은 방향일 때만)
  if (m && m.k > 0 && m.k < pts.length - 2) {
    const [q, r] = [pts[m.k], pts[m.k + 1]], axis = Math.abs(q.y - r.y) < 0.01 ? 'y' : 'x'
    if (axis === m.axis) { q[axis] = m.value; r[axis] = m.value }
  }
  const o = pts[0], local = editor.getPointInParentSpace(arrowId, o)   // 보드 안 화살표는 x·y가 보드 기준
  editor.updateShape({ id: arrowId, type: 'sarrow', x: local.x, y: local.y, props: { pts: pts.map(p => ({ x: p.x - o.x, y: p.y - o.y })) } })
}

// 꺾인 곳을 둥글게(데스크톱 화살표 모양) — 반경은 이웃 구간 절반을 넘지 않게
export function roundedPath(p, r = CORNER_R) {
  let d = `M${p[0].x},${p[0].y}`
  for (let i = 1; i < p.length - 1; i++) {
    const a = p[i - 1], b = p[i], c = p[i + 1], rr = Math.min(r, Vec.Dist(a, b) / 2, Vec.Dist(b, c) / 2)
    const u = Vec.Sub(a, b).uni(), v = Vec.Sub(c, b).uni()
    d += ` L${b.x + u.x * rr},${b.y + u.y * rr} Q${b.x},${b.y} ${b.x + v.x * rr},${b.y + v.y * rr}`
  }
  const z = p[p.length - 1]
  return d + ` L${z.x},${z.y}`
}

// 끄는 동안 상태(포트점 그리기용) — 끄는 곳이 붙을 상자와 붙을 자리
const drag = { on: false, target: null, snap: null }
const setDrag = snap => { drag.on = true; drag.snap = snap; drag.target = snap?.shapeId ?? null }
const freeOf = (snap, pt) => (snap ? { x: snap.p.x, y: snap.p.y, side: snap.side, shapeId: snap.shapeId } : { x: pt.x, y: pt.y })   // shapeId: 끄는 동안 붙을 상자(장애물 아님)
const bindProps = (terminal, snap) => ({ terminal, side: snap.side, nx: snap.nx, ny: snap.ny })

export class SArrowUtil extends ShapeUtil {
  static type = 'sarrow'
  static props = { pts: T.arrayOf(T.object({ x: T.number, y: T.number })), manual: T.any, free: T.any, free0: T.any, color: T.string, width: T.number }
  getDefaultProps() { return { pts: [{ x: 0, y: 0 }, { x: 100, y: 0 }], manual: null, free: null, free0: null, color: '#1e2b45', width: 2.5 } }
  getGeometry(s) { return new Polyline2d({ points: s.props.pts.map(p => new Vec(p.x, p.y)) }) }
  canResize() { return false }
  hideResizeHandles() { return true }
  hideRotateHandle() { return true }
  hideSelectionBoundsFg() { return true }
  hideSelectionBoundsBg() { return true }
  canBind({ fromShape, bindingType }) { return bindingType === 'sarrow' && fromShape.type === 'sarrow' }   // 화살표가 다른 것에 묶일 땐 ok, 화살표에 묶이는 건 x
  // 끝점 손잡이 둘(다시 붙이기) + 알약: 양 끝 구간을 뺀 안쪽 구간마다 가운데에 손잡이
  getHandles(s) {
    const p = s.props.pts, idx = getIndices(p.length + 1)
    const out = [{ id: 'end0', type: 'vertex', index: idx[0], x: p[0].x, y: p[0].y },
      { id: 'end1', type: 'vertex', index: idx[p.length], x: p[p.length - 1].x, y: p[p.length - 1].y }]
    for (let k = 1; k < p.length - 2; k++)
      out.push({ id: 'seg' + k, type: 'vertex', index: idx[k], x: (p[k].x + p[k + 1].x) / 2, y: (p[k].y + p[k + 1].y) / 2 })
    return out
  }
  onHandleDragStart(s, { handle }) {
    if (!handle.id.startsWith('end')) return
    const terminal = handle.id === 'end0' ? 'start' : 'end'
    for (const b of this.editor.getBindingsFromShape(s.id, 'sarrow')) if (b.props.terminal === terminal) this.editor.deleteBinding(b.id)
  }
  onHandleDrag(s, { handle }) {
    if (handle.id.startsWith('end')) {
      const e = this.editor, pt = e.getShapePageTransform(s.id).applyToPoint(handle)
      const snap = snapAt(e, pt)
      setDrag(snap)
      e.updateShape({ id: s.id, type: 'sarrow', props: { [handle.id === 'end0' ? 'free0' : 'free']: freeOf(snap, pt), manual: null } })
      reroute(e, s.id)
      return
    }
    const k = +handle.id.slice(3), pts = s.props.pts.map(p => ({ ...p }))
    const axis = Math.abs(pts[k].y - pts[k + 1].y) < 0.01 ? 'y' : 'x'
    pts[k][axis] = pts[k + 1][axis] = handle[axis]                       // 그 구간만 평행 이동, 이웃 구간은 길이만 바뀜
    return { props: { pts, manual: { k, axis, value: handle[axis] + s[axis] } } }
  }
  onHandleDragEnd(s, { handle }) {
    if (!handle.id.startsWith('end')) return
    const e = this.editor, terminal = handle.id === 'end0' ? 'start' : 'end', snap = drag.snap
    drag.on = false; drag.snap = null; drag.target = null
    if (snap) e.createBinding({ type: 'sarrow', fromId: s.id, toId: snap.shapeId, props: bindProps(terminal, snap) })
    reroute(e, s.id)
  }
  component(s) {
    const { pts: p, width } = s.props, color = ink(this.editor, s, s.props.color)
    const [a, b] = [p[p.length - 2], p[p.length - 1]], ang = Math.atan2(b.y - a.y, b.x - a.x), L = headLen(width)
    const h = t => `${b.x - L * Math.cos(ang + t)},${b.y - L * Math.sin(ang + t)}`
    return <SVGContainer><path d={roundedPath(p)} fill="none" stroke={color} strokeWidth={width} strokeLinejoin="round" />
      <polygon points={`${b.x},${b.y} ${h(0.45)} ${h(-0.45)}`} fill={color} /></SVGContainer>
  }
  getIndicatorPath(s) { const path = new Path2D(); s.props.pts.forEach((q, i) => i ? path.lineTo(q.x, q.y) : path.moveTo(q.x, q.y)); return path }
}

export class SArrowBindingUtil extends BindingUtil {
  static type = 'sarrow'
  static props = { terminal: T.string, side: T.string, nx: T.any, ny: T.any }
  getDefaultProps() { return { terminal: 'start', side: 'right', nx: null, ny: null } }
  onAfterChangeToShape({ binding }) { reroute(this.editor, binding.fromId) }       // 상자가 움직이면 다시 꺾기
  onBeforeDeleteToShape({ binding }) { this.editor.deleteShape(binding.fromId) }
}

// 큐닷(선택한 상자 네 변 가운데 밖) · 포트점 예고(미선택 상자 테두리에 다가가면) · 끄는 동안 대상 상자의 포트점
export class QcDotOverlayUtil extends OverlayUtil {
  static type = 'qcdot'
  options = { zIndex: 300 }
  isActive() { const e = this.editor; return drag.on || e.isIn('select.idle') }
  getOverlays() {
    const e = this.editor
    if (drag.on) {
      if (!drag.target) return []
      const ports = Object.keys(DIR).map(side => ({ id: 'port:' + side, type: 'qcdot', props: { side, kind: 'port', shapeId: drag.target } }))
      return [...ports, { id: 'snap', type: 'qcdot', props: { kind: 'snap', at: drag.snap.p } }]
    }
    const out = [], sel = e.getOnlySelectedShape()
    if (isBox(sel)) out.push(...Object.keys(DIR).map(side => ({ id: 'qc:' + side, type: 'qcdot', props: { side, kind: 'qc', shapeId: sel.id } })))
    const pt = e.inputs.getCurrentPagePoint(), hov = snapAt(e, pt, { exclude: isBox(sel) ? sel.id : undefined })
    // 고른 것의 손잡이(화살표 끝점 등) 곁에선 예고점을 안 띄운다 — 안 그러면 끝점을 끌려다 새 화살표가 생긴다(손잡이가 먼저)
    const z = e.getZoomLevel(), nearHandle = e.getSelectedShapes().some(s => (e.getShapeHandles(s) || []).some(h =>
      Vec.Dist(e.getShapePageTransform(s.id).applyToPoint(h), pt) * z <= PORT_SNAP_PX))
    if (hov && !nearHandle) out.push({ id: 'hover', type: 'qcdot', props: { kind: 'hover', at: hov.p, snap: hov } })
    return out
  }
  pos(o) {
    if (o.props.at) return o.props.at
    const b = this.editor.getShapePageBounds(o.props.shapeId), [nx, ny] = RATIO[o.props.side], z = this.editor.getZoomLevel()
    const off = o.props.kind === 'qc' ? 18 / z : 0
    return { x: b.minX + nx * b.w + DIR[o.props.side][0] * off, y: b.minY + ny * b.h + DIR[o.props.side][1] * off }
  }
  getGeometry(o) {
    if (o.props.kind !== 'qc' && o.props.kind !== 'hover') return null
    const r = 7 / this.editor.getZoomLevel(), p = this.pos(o)
    return new Circle2d({ x: p.x - r, y: p.y - r, radius: r, isFilled: true })
  }
  getCursor() { return 'cross' }
  render(ctx, overlays) {
    const z = this.editor.getZoomLevel()
    for (const o of overlays) {
      const p = this.pos(o), k = o.props.kind
      ctx.beginPath(); ctx.arc(p.x, p.y, (k === 'qc' ? 5 : k === 'snap' ? 7 : 6) / z, 0, Math.PI * 2)
      if (k === 'qc' || k === 'snap') { ctx.fillStyle = '#2f80ed'; ctx.fill() }
      else { ctx.fillStyle = '#fff'; ctx.fill(); ctx.lineWidth = 2 / z; ctx.strokeStyle = '#2f80ed'; ctx.stroke() }
    }
  }
  onPointerDown(o) {
    const e = this.editor, id = createShapeId()
    // 시작: 큐닷이면 그 변 가운데, 포트점 예고면 그 자리
    const start = o.props.kind === 'qc' ? { shapeId: o.props.shapeId, side: o.props.side, nx: RATIO[o.props.side][0], ny: RATIO[o.props.side][1] } : o.props.snap
    e.markHistoryStoppingPoint('qcdot')
    e.createShape({ id, type: 'sarrow', props: { free: freeOf(null, e.inputs.getCurrentPagePoint()) } })
    e.createBinding({ type: 'sarrow', fromId: id, toId: start.shapeId, props: bindProps('start', start) })
    reroute(e, id); setDrag(null)
    const onEvent = ev => {
      if (ev.type !== 'pointer') return
      const pt = e.inputs.getCurrentPagePoint()
      if (ev.name === 'pointer_move') {
        const snap = snapAt(e, pt)
        const ok = snap && !(snap.shapeId === start.shapeId && Math.abs(snap.nx - start.nx) < 1e-3 && Math.abs(snap.ny - start.ny) < 1e-3)
        setDrag(ok ? snap : null)
        e.updateShape({ id, type: 'sarrow', props: { free: freeOf(drag.snap, pt) } }); reroute(e, id)
      } else if (ev.name === 'pointer_up') {
        e.off('event', onEvent)
        if (drag.snap) e.createBinding({ type: 'sarrow', fromId: id, toId: drag.snap.shapeId, props: bindProps('end', drag.snap) })
        drag.on = false; drag.target = null; drag.snap = null; reroute(e, id); e.select(id)
      }
    }
    e.on('event', onEvent)
    return true
  }
}

// ── TRIM: 선(line)을 누르면, 누른 자리를 둘러싼 두 교차점 사이를 잘라 낸다(교차가 없으면 선 통째로 지움).
// 자르는 칼 = 다른 선·화살표의 선분, 상자의 네 변.
const pagePts = (editor, sh) => {
  const m = editor.getShapePageTransform(sh.id)
  if (sh.type === 'line') return Object.values(sh.props.points).sort((a, b) => (a.index < b.index ? -1 : 1)).map(p => m.applyToPoint(p))
  if (sh.type === 'sarrow') return sh.props.pts.map(p => m.applyToPoint(p))
  if (isBox(sh)) { const b = editor.getShapePageBounds(sh.id); return [{ x: b.minX, y: b.minY }, { x: b.maxX, y: b.minY }, { x: b.maxX, y: b.maxY }, { x: b.minX, y: b.maxY }, { x: b.minX, y: b.minY }] }
  return []
}
function segX(p, q, a, b) {          // p-q와 a-b의 교차 → p-q 위 t(0~1), 없으면 null
  const r = { x: q.x - p.x, y: q.y - p.y }, s2 = { x: b.x - a.x, y: b.y - a.y }, den = r.x * s2.y - r.y * s2.x
  if (Math.abs(den) < 1e-9) return null
  const t = ((a.x - p.x) * s2.y - (a.y - p.y) * s2.x) / den, u = ((a.x - p.x) * r.y - (a.y - p.y) * r.x) / den
  return t > 1e-6 && t < 1 - 1e-6 && u >= -1e-6 && u <= 1 + 1e-6 ? t : null
}
export function trimAt(editor, pt) {
  const line = editor.getShapeAtPoint(pt, { margin: 8, hitInside: false, filter: s => s.type === 'line' })
  if (!line) return false
  const P = pagePts(editor, line)
  // 선 전체를 "거리 d"로 펴서 교차점들의 d와 누른 점의 d를 구한다
  const cum = [0]; for (let i = 1; i < P.length; i++) cum.push(cum[i - 1] + Vec.Dist(P[i - 1], P[i]))
  const cuts = []
  for (const other of editor.getCurrentPageShapes()) {
    if (other.id === line.id) continue
    const Q = pagePts(editor, other)
    for (let i = 1; i < P.length; i++) for (let j = 1; j < Q.length; j++) {
      const t = segX(P[i - 1], P[i], Q[j - 1], Q[j]); if (t != null) cuts.push(cum[i - 1] + t * (cum[i] - cum[i - 1]))
    }
  }
  let best = [Infinity, 0]
  for (let i = 1; i < P.length; i++) {
    const a = P[i - 1], b = P[i], L = Vec.Dist(a, b) || 1
    const t = Math.max(0, Math.min(1, ((pt.x - a.x) * (b.x - a.x) + (pt.y - a.y) * (b.y - a.y)) / (L * L)))
    const d = Vec.Dist(pt, { x: a.x + t * (b.x - a.x), y: a.y + t * (b.y - a.y) }); if (d < best[0]) best = [d, cum[i - 1] + t * L]
  }
  const dc = best[1], lo = Math.max(0, ...cuts.filter(c => c < dc)), hi = Math.min(cum[cum.length - 1], ...cuts.filter(c => c > dc))
  const at = d => { for (let i = 1; i < P.length; i++) if (d <= cum[i] + 1e-9) { const t = (d - cum[i - 1]) / ((cum[i] - cum[i - 1]) || 1); return { x: P[i - 1].x + t * (P[i].x - P[i - 1].x), y: P[i - 1].y + t * (P[i].y - P[i - 1].y) } } return P[P.length - 1] }
  const piece = (d0, d1) => [at(d0), ...P.filter((_, i) => cum[i] > d0 && cum[i] < d1), at(d1)]
  const keep = [lo > 1e-6 ? piece(0, lo) : null, hi < cum[cum.length - 1] - 1e-6 ? piece(hi, cum[cum.length - 1]) : null].filter(Boolean)
  editor.markHistoryStoppingPoint('trim')
  editor.run(() => {
    for (const pts of keep) {
      const o = pts[0], idx = getIndices(pts.length), local = editor.getPointInParentSpace(line.id, o)
      editor.createShape({ type: 'line', parentId: line.parentId, x: local.x, y: local.y, props: { ...line.props, points: Object.fromEntries(pts.map((p, i) => [idx[i], { id: idx[i], index: idx[i], x: p.x - o.x, y: p.y - o.y }])) } })
    }
    editor.deleteShape(line.id)
  })
  return true
}
export class TrimTool extends StateNode {
  static id = 'trim'
  onEnter() { this.editor.setCursor({ type: 'cross', rotation: 0 }) }
  onPointerDown() { trimAt(this.editor, this.editor.inputs.getCurrentPagePoint()) }
  onCancel() { this.editor.setCurrentTool('select') }
}

