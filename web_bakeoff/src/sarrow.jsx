// 시험: tldraw 위에 Magic Board식 직각 화살표(sarrow) — 구간마다 알약, 큐닷으로 뽑기, 포트점에 붙기.
// 데스크톱 core_routing의 A* 장애물 피하기는 이 시험 밖(ㄱ·ㄹ 자 기본 경로만).
import { createRoot } from 'react-dom/client'
import { Tldraw, ShapeUtil, BindingUtil, OverlayUtil, StateNode, SVGContainer, Polyline2d, Circle2d, Vec, T, createShapeId } from 'tldraw'
import { getIndices } from '@tldraw/utils'
import { routeAStar } from './astar.js'
import 'tldraw/tldraw.css'

const DIR = { left: [-1, 0], right: [1, 0], top: [0, -1], bottom: [0, 1] }
const STUB = 24
const isH = side => side === 'left' || side === 'right'
const port = (b, side) => ({ left: { x: b.minX, y: b.midY }, right: { x: b.maxX, y: b.midY },
  top: { x: b.midX, y: b.minY }, bottom: { x: b.midX, y: b.maxY } })[side]
// 점이 상자의 어느 변에 가장 가까운가(포트점 고르기)
const nearestSide = (b, p) => Object.keys(DIR).reduce((best, s) => {
  const d = Vec.Dist(port(b, s), p); return d < best[1] ? [s, d] : best }, [null, Infinity])[0]

// 직각 경로: 양 끝에서 STUB만큼 수직으로 나온 뒤 ㄱ 또는 ㄹ 자로 잇는다. manual = 사용자가 끈 구간 {k, axis, value}
export function route(p0, s0, p1, s1, manual) {
  const a = { x: p0.x + DIR[s0][0] * STUB, y: p0.y + DIR[s0][1] * STUB }
  const b = { x: p1.x + DIR[s1][0] * STUB, y: p1.y + DIR[s1][1] * STUB }
  let mid
  if (isH(s0) && isH(s1)) { const mx = (a.x + b.x) / 2; mid = [{ x: mx, y: a.y }, { x: mx, y: b.y }] }
  else if (!isH(s0) && !isH(s1)) { const my = (a.y + b.y) / 2; mid = [{ x: a.x, y: my }, { x: b.x, y: my }] }
  else if (isH(s0)) mid = [{ x: b.x, y: a.y }]
  else mid = [{ x: a.x, y: b.y }]
  const pts = simplify([p0, a, ...mid, b, p1])
  if (manual && manual.k > 0 && manual.k < pts.length - 2) {           // 끈 구간 다시 적용(안쪽 구간·같은 방향일 때만)
    const [q, r] = [pts[manual.k], pts[manual.k + 1]]
    const axis = Math.abs(q.y - r.y) < 0.01 ? 'y' : 'x'
    if (axis === manual.axis) { q[axis] = manual.value; r[axis] = manual.value }
  }
  return pts
}
function simplify(pts) {
  const out = []
  for (const p of pts) {
    if (out.length && Vec.Dist(out[out.length - 1], p) < 0.01) continue
    if (out.length >= 2) {
      const [a, b] = [out[out.length - 2], out[out.length - 1]]
      if ((Math.abs(a.x - b.x) < 0.01 && Math.abs(b.x - p.x) < 0.01) || (Math.abs(a.y - b.y) < 0.01 && Math.abs(b.y - p.y) < 0.01)) out.pop()
    }
    out.push({ ...p })
  }
  return out
}

// 화살표 다시 그리기 — 묶인 상자(또는 떠 있는 끝점)에서 경로를 계산
export function reroute(editor, arrowId) {
  const arrow = editor.getShape(arrowId); if (!arrow) return
  const ends = {}
  for (const b of editor.getBindingsFromShape(arrowId, 'sarrow')) {
    const bounds = editor.getShapePageBounds(b.toId)
    if (bounds) ends[b.props.terminal] = { p: port(bounds, b.props.side), s: b.props.side }
  }
  if (!ends.start) return
  if (!ends.end) {                                                      // 떠 있는 끝: 출발 방향에서 마주 보는 쪽으로 들어가게
    const f = arrow.props.free ?? ends.start.p
    ends.end = { p: f, s: isH(ends.start.s) ? (f.x < ends.start.p.x ? 'right' : 'left') : (f.y < ends.start.p.y ? 'bottom' : 'top') }
  }
  let pts = route(ends.start.p, ends.start.s, ends.end.p, ends.end.s, arrow.props.manual)
  // 장애물: 묶인 두 상자를 뺀 나머지 상자. 기본 경로가 하나라도 뚫고 지나가면 A*로(끈 구간은 이때 무시)
  const bound = new Set(editor.getBindingsFromShape(arrowId, 'sarrow').map(b => b.toId))
  const obstacles = editor.getCurrentPageShapes().filter(sh => sh.type === 'geo' && !bound.has(sh.id)).map(sh => editor.getShapePageBounds(sh.id))
  if (obstacles.some(o => pts.some((q, i) => i && segHitsRect(pts[i - 1], q, o)))) {
    const a = routeAStar(ends.start.p, DIR[ends.start.s], ends.end.p, DIR[ends.end.s], obstacles)
    if (a) pts = simplify(a)
  }
  const o = pts[0]
  editor.updateShape({ id: arrowId, type: 'sarrow', x: o.x, y: o.y, props: { pts: pts.map(p => ({ x: p.x - o.x, y: p.y - o.y })) } })
}

// 축정렬 선분이 상자(여유 4)를 지나가나
function segHitsRect(a, b, r) {
  const [x0, x1, y0, y1] = [Math.min(a.x, b.x), Math.max(a.x, b.x), Math.min(a.y, b.y), Math.max(a.y, b.y)]
  return x1 >= r.minX - 4 && x0 <= r.maxX + 4 && y1 >= r.minY - 4 && y0 <= r.maxY + 4
}

class SArrowUtil extends ShapeUtil {
  static type = 'sarrow'
  static props = { pts: T.arrayOf(T.object({ x: T.number, y: T.number })), manual: T.any, free: T.any }
  getDefaultProps() { return { pts: [{ x: 0, y: 0 }, { x: 100, y: 0 }], manual: null, free: null } }
  getGeometry(s) { return new Polyline2d({ points: s.props.pts.map(p => new Vec(p.x, p.y)) }) }
  canResize() { return false }
  hideResizeHandles() { return true }
  hideRotateHandle() { return true }
  hideSelectionBoundsFg() { return true }
  hideSelectionBoundsBg() { return true }
  canBind({ fromShape, bindingType }) { return bindingType === 'sarrow' && fromShape.type === 'sarrow' }   // 화살표가 다른 것에 묶일 땐 ok, 화살표에 묶이는 건 x
  // 알약: 양 끝 구간을 뺀 안쪽 구간마다 가운데에 손잡이
  getHandles(s) {
    const p = s.props.pts, out = [], idx = getIndices(p.length)
    for (let k = 1; k < p.length - 2; k++)
      out.push({ id: 'seg' + k, type: 'vertex', index: idx[k], x: (p[k].x + p[k + 1].x) / 2, y: (p[k].y + p[k + 1].y) / 2 })
    return out
  }
  onHandleDrag(s, { handle }) {
    const k = +handle.id.slice(3), pts = s.props.pts.map(p => ({ ...p }))
    const axis = Math.abs(pts[k].y - pts[k + 1].y) < 0.01 ? 'y' : 'x'
    pts[k][axis] = pts[k + 1][axis] = handle[axis]                       // 그 구간만 평행 이동, 이웃 구간은 길이만 바뀜
    return { props: { pts, manual: { k, axis, value: handle[axis] + s[axis] } } }
  }
  component(s) {
    const p = s.props.pts, d = 'M' + p.map(q => `${q.x},${q.y}`).join(' L')
    const [a, b] = [p[p.length - 2], p[p.length - 1]], ang = Math.atan2(b.y - a.y, b.x - a.x)
    const h = t => `${b.x - 14 * Math.cos(ang + t)},${b.y - 14 * Math.sin(ang + t)}`
    return <SVGContainer><path d={d} fill="none" stroke="#1e2b45" strokeWidth={2.5} strokeLinejoin="round" />
      <polygon points={`${b.x},${b.y} ${h(0.45)} ${h(-0.45)}`} fill="#1e2b45" /></SVGContainer>
  }
  getIndicatorPath(s) { const path = new Path2D(); s.props.pts.forEach((q, i) => i ? path.lineTo(q.x, q.y) : path.moveTo(q.x, q.y)); return path }
}

class SArrowBindingUtil extends BindingUtil {
  static type = 'sarrow'
  static props = { terminal: T.string, side: T.string }
  getDefaultProps() { return { terminal: 'start', side: 'right' } }
  onAfterChangeToShape({ binding }) { reroute(this.editor, binding.fromId) }       // 상자가 움직이면 다시 꺾기
  onBeforeDeleteToShape({ binding }) { this.editor.deleteShape(binding.fromId) }
}

// 큐닷(선택한 상자 네 변 가운데 밖) + 끄는 동안 대상 상자의 포트점
const drag = { on: false, target: null }
const isBox = s => s && s.type === 'geo'
class QcDotOverlayUtil extends OverlayUtil {
  static type = 'qcdot'
  options = { zIndex: 300 }
  isActive() { const e = this.editor; return drag.on || (e.isIn('select.idle') && isBox(e.getOnlySelectedShape())) }
  getOverlays() {
    const e = this.editor
    if (drag.on) return drag.target ? Object.keys(DIR).map(side => ({ id: 'port:' + side, type: 'qcdot', props: { side, kind: 'port', shapeId: drag.target } })) : []
    const s = e.getOnlySelectedShape()
    return Object.keys(DIR).map(side => ({ id: 'qc:' + side, type: 'qcdot', props: { side, kind: 'qc', shapeId: s.id } }))
  }
  pos(o) {
    const b = this.editor.getShapePageBounds(o.props.shapeId), p = port(b, o.props.side), z = this.editor.getZoomLevel()
    const off = o.props.kind === 'qc' ? 18 / z : 0
    return { x: p.x + DIR[o.props.side][0] * off, y: p.y + DIR[o.props.side][1] * off }
  }
  getGeometry(o) {
    if (o.props.kind !== 'qc') return null
    const r = 7 / this.editor.getZoomLevel(), p = this.pos(o)
    return new Circle2d({ x: p.x - r, y: p.y - r, radius: r, isFilled: true })
  }
  getCursor() { return 'cross' }
  render(ctx, overlays) {
    const z = this.editor.getZoomLevel()
    for (const o of overlays) {
      const p = this.pos(o)
      ctx.beginPath(); ctx.arc(p.x, p.y, (o.props.kind === 'qc' ? 5 : 6) / z, 0, Math.PI * 2)
      if (o.props.kind === 'qc') { ctx.fillStyle = '#2f80ed'; ctx.fill() }
      else { ctx.fillStyle = '#fff'; ctx.fill(); ctx.lineWidth = 2 / z; ctx.strokeStyle = '#2f80ed'; ctx.stroke() }
    }
  }
  onPointerDown(o) {
    const e = this.editor, from = o.props.shapeId, id = createShapeId()
    e.markHistoryStoppingPoint('qcdot')
    e.createShape({ id, type: 'sarrow', props: { free: e.inputs.getCurrentPagePoint().toJson() } })
    e.createBinding({ type: 'sarrow', fromId: id, toId: from, props: { terminal: 'start', side: o.props.side } })
    reroute(e, id); drag.on = true
    const onEvent = ev => {
      if (ev.type !== 'pointer') return
      const pt = e.inputs.getCurrentPagePoint()
      if (ev.name === 'pointer_move') {
        const hit = e.getShapeAtPoint(pt, { hitInside: true, margin: 10, filter: s => isBox(s) && s.id !== from })
        drag.target = hit?.id ?? null
        e.updateShape({ id, type: 'sarrow', props: { free: pt.toJson() } }); reroute(e, id)
      } else if (ev.name === 'pointer_up') {
        e.off('event', onEvent)
        if (drag.target) e.createBinding({ type: 'sarrow', fromId: id, toId: drag.target,
          props: { terminal: 'end', side: nearestSide(e.getShapePageBounds(drag.target), pt) } })
        drag.on = false; drag.target = null; reroute(e, id); e.select(id)
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
  if (sh.type === 'geo') { const b = editor.getShapePageBounds(sh.id); return [{ x: b.minX, y: b.minY }, { x: b.maxX, y: b.minY }, { x: b.maxX, y: b.maxY }, { x: b.minX, y: b.maxY }, { x: b.minX, y: b.minY }] }
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
    editor.deleteShape(line.id)
    for (const pts of keep) {
      const o = pts[0], idx = getIndices(pts.length)
      editor.createShape({ type: 'line', x: o.x, y: o.y, props: { ...line.props, points: Object.fromEntries(pts.map((p, i) => [idx[i], { id: idx[i], index: idx[i], x: p.x - o.x, y: p.y - o.y }])) } })
    }
  })
  return true
}
class TrimTool extends StateNode {
  static id = 'trim'
  onEnter() { this.editor.setCursor({ type: 'cross', rotation: 0 }) }
  onPointerDown() { trimAt(this.editor, this.editor.inputs.getCurrentPagePoint()) }
  onCancel() { this.editor.setCurrentTool('select') }
}

function build(editor) {
  if (editor.getCurrentPageShapeIds().size) return
  const box = (n, x, y, text) => editor.createShape({ id: createShapeId(n), type: 'geo', x, y,
    props: { w: 200, h: 90, geo: 'rectangle', fill: 'semi', color: 'blue', richText: { type: 'doc', content: [{ type: 'paragraph', content: [{ type: 'text', text }] }] } } })
  box('a', 0, 0, '입력'); box('b', 420, 220, '처리'); box('c', 60, 420, '출력')
  const id = createShapeId('ab')
  editor.createShape({ id, type: 'sarrow' })
  editor.createBinding({ type: 'sarrow', fromId: id, toId: createShapeId('a'), props: { terminal: 'start', side: 'right' } })
  editor.createBinding({ type: 'sarrow', fromId: id, toId: createShapeId('b'), props: { terminal: 'end', side: 'left' } })
  reroute(editor, id)
  // 시험 2: 화살표 길을 막는 상자(A*로 돌아가야 함) + 자를 선 둘
  box('d', 300, 100, '장애물')
  const line = (n, a, b) => editor.createShape({ id: createShapeId(n), type: 'line', x: a.x, y: a.y,
    props: { dash: 'solid', points: { a1: { id: 'a1', index: 'a1', x: 0, y: 0 }, a2: { id: 'a2', index: 'a2', x: b.x - a.x, y: b.y - a.y } } } })
  line('l1', { x: -60, y: 330 }, { x: 760, y: 330 }); line('l2', { x: 560, y: -40 }, { x: 560, y: 600 })
  reroute(editor, id)
  editor.zoomToFit()
}

createRoot(document.getElementById('root')).render(
  <><style>{`.tl-container{--tl-font-sans:'Pretendard',sans-serif}`}</style>
  <button id="trim" style={{ position: 'fixed', left: 320, top: 8, zIndex: 1000, font: '600 14px Pretendard', padding: '6px 12px' }}
    onClick={() => window.editor.setCurrentTool('trim')}>TRIM</button>
  <Tldraw persistenceKey="bakeoff-sarrow2" cameraOptions={{ wheelBehavior: 'zoom' }} tools={[TrimTool]} shapeUtils={[SArrowUtil]} bindingUtils={[SArrowBindingUtil]} overlayUtils={[QcDotOverlayUtil]}
    onMount={e => { window.editor = e; build(e)
      // 묶이지 않은 상자(장애물)가 움직여도 모든 화살표 길을 다시 찾는다
      e.sideEffects.registerAfterChangeHandler('shape', (prev, next) => {
        if (next.type === 'geo' && (prev.x !== next.x || prev.y !== next.y || prev.props.w !== next.props.w || prev.props.h !== next.props.h))
          for (const a of e.getCurrentPageShapes()) if (a.type === 'sarrow') reroute(e, a.id)
      }) }} /></>)
