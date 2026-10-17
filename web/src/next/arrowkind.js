// 화살표 종류 바꾸기(직선·곡선·직각) — 데스크톱 `host_context._floating_set_arrow_kind`·`_make_swapped_arrow`·`_ArrowItem.apply_curved`.
// 직선·곡선 = 곡선 화살표(arrow, 제어점 없음/있음), 직각 = sarrow(옛 파일의 곧은 길 sarrow도 「직선」으로 보임). 순수 함수.
import { applyRouting } from './arrows.js'
import { nearestBorder } from './connect.js'
import { toLocal, toScene } from './xform.js'

export function arrowKindOf(it) {
  if (it.type === 'sarrow') return (it.routing ?? (it.auto_route ? 'ortho' : 'straight')) === 'straight' ? 'straight' : 'ortho'
  if (it.type === 'arrow') return it.ctrl1 ? 'curved' : 'straight'
  return null
}

const BOW_FRAC = 0.22   // `_BOW_FRAC` — 안 붙은 화살표를 휠 때 부풀리는 정도
// 휘게(`apply_curved`): 붙은 끝은 외곽선 법선으로 나가는 S자, 둘 다 떠 있으면 선분 수직으로 반대로 부풀린 S
export function applyCurved(it, items, rectOf) {
  const [p1, p2] = [it.p1, it.p2], dx = p2[0] - p1[0], dy = p2[1] - p1[1], dist = Math.hypot(dx, dy)
  if (dist < 8) return it
  const ux = dx / dist, uy = dy / dist, byId = id => id && items.find(x => x._id === id)
  const nrm = (k, p) => { const h = byId(it['_' + k]); if (!h || !it[k + '_pt']) return null; const sp = toScene(it, { x: p[0], y: p[1] }), n = nearestBorder(h, sp, rectOf).n, o = toLocal(it, { x: 0, y: 0 }), v = toLocal(it, n); return { x: v.x - o.x, y: v.y - o.y } }
  const n1 = nrm('bind1', p1), n2 = nrm('bind2', p2)
  if (!n1 && !n2) {
    const off = dist * BOW_FRAC, nx = -uy, ny = ux
    return { ...it, ctrl1: [p1[0] + ux * dist / 3 + nx * off, p1[1] + uy * dist / 3 + ny * off], ctrl2: [p2[0] - ux * dist / 3 - nx * off, p2[1] - uy * dist / 3 - ny * off] }
  }
  const k = Math.max(30, Math.min(dist * 0.5, 200)), e = n1 || { x: ux, y: uy }, b = n2 || { x: -e.x, y: -e.y }
  return { ...it, ctrl1: [p1[0] + e.x * k, p1[1] + e.y * k], ctrl2: [p2[0] + b.x * k, p2[1] + b.y * k] }
}

// 종류 바꾸기 — 같은 _id·끝점·색·굵기·선 모양·화살촉·연결·라벨 유지. 직각으로 가면 「자동 길」로 다시 찾음, 곡선으로 가면 휘게.
// curveR = 직각으로 바꿀 때 모서리(데스크톱 sticky current_curve_r). → 새 아이템(같으면 그대로)
export function swapArrowKind(it, kind, items, rectOf, curveR = 10) {
  if (arrowKindOf(it) === kind) return it
  const keep = { _id: it._id, color: it.color, width: it.width, style: it.style, head: it.head, head_start: it.head_start, head_scale: it.head_scale, z: it.z,
    locked: it.locked, group_id: it.group_id, layer_id: it.layer_id, labels: it.labels || (it.label ? [{ t: 0.5, off: 0, ...it.label }] : undefined),
    _bind1: it._bind1, bind1_pt: it.bind1_pt, bind1_group: it.bind1_group ?? null, _bind2: it._bind2, bind2_pt: it.bind2_pt, bind2_group: it.bind2_group ?? null }
  const [a, b] = it.type === 'sarrow' ? [it.pts[0], it.pts[it.pts.length - 1]] : [it.p1, it.p2]
  const A = toScene(it, { x: a[0], y: a[1] }), B = toScene(it, { x: b[0], y: b[1] }), base = { pos: [0, 0], scale: 1, rotation: 0, origin: [0, 0] }
  const others = next => items.map(x => (x._id === it._id ? next : x))
  if (kind === 'ortho') {   // 곧은 길 sarrow면 routing만(`set_routing`), 곡선 화살표면 새 sarrow(직선·곡선 고르기는 늘 곡선 화살표 종류로 — 데스크톱과 같음)
    let n = it.type === 'sarrow' ? { ...it } : { ...keep, ...base, type: 'sarrow', pts: [[A.x, A.y], [B.x, B.y]], curve_r: curveR }
    n = { ...n, routing: 'ortho', auto_route: true, route_hints: [] }
    if (!n.labels) delete n.labels
    return { ...n, pts: applyRouting(n, others(n), rectOf) }
  }
  let n = it.type === 'arrow' ? { ...it } : { ...keep, ...base, type: 'arrow', p1: [A.x, A.y], p2: [B.x, B.y], ctrl1: null, ctrl2: null }
  if (!n.labels) delete n.labels
  return kind === 'curved' ? applyCurved(n, others(n), rectOf) : { ...n, ctrl1: null, ctrl2: null }
}
