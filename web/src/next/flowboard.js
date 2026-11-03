// 🔷 도형 그리기(2026-11-03 사용자 — 「송신소 계통도 그려 줘」 = 고칠 수 있는 상자 + 붙은 화살표). 순수 — 칠판 물건만 만든다.
// 자리는 서버가 데스크톱 흐름도 규칙으로 계산(`easycad/ai/board_diagram.place` → `flow_spec.layout`) — 여기는 그 자리에 물건을 짓기만.
// 모양·색은 데스크톱 `host_fileio._build_flowspec_items`와 같게: 담당 띠 = 옅은 색 채운 패스(길 찾기 장애물 아님), 상자 = 띠 색 테두리 + 옅은 바탕,
// 가장 중요한 단계(focus) 하나만 코랄, 글자 = 기본 잉크(어두운 화면에선 흰색으로 바뀜), 화살표 = 「자동 길」 직각 + 두 끝 붙음(상자를 옮기면 따라옴).
import { newId } from './model.js'
import { textW } from './chart.js'
import { resolveRoutes } from './arrows.js'
import { polylineAt } from './geom.js'

export const LANE_COLORS = ['#4a8fd9', '#3ea37a', '#8a6fd1', '#c9a227', '#2a9fb0', '#c2577f']   // 데스크톱 `_FLOW_LANE_COLORS`
const CORAL = '#da7756', INK = '#ff1f1f1f'
const BAND_A = 30, BOX_A = 56, FOCUS_A = 80, BAND_EDGE_A = 120   // 데스크톱 `_FLOW_BAND_ALPHA` 등(0~255)
const SHAPE = { start: 'terminal', end: 'terminal', decision: 'decision', data: 'data', document: 'document', database: 'database' }   // 나머지 = 네모
export const PAD = 40   // 프레임 안쪽 여백
const LABEL_PT = 12, HEAD_PT = 11, PX = 4 / 3

const hex2 = a => Math.round(a).toString(16).padStart(2, '0')
const argb = (c, a = 255) => '#' + hex2(a) + c.slice(1).toLowerCase()
// 흰 종이 위에 a만큼 칠한 색(불투명) — 상자 바탕. 반투명이면 어두운 화면에서 바탕이 비쳐 검은 글이 묻혔음(2026-11-03 실검증, 채운 도형 글은 어두운 화면에서도 그대로라)
const onWhite = (c, a) => '#ff' + [1, 3, 5].map(i => hex2(255 - (255 - parseInt(c.slice(i, i + 2), 16)) * a / 255)).join('')
const base = (pos, extra) => ({ pos, scale: 1, rotation: 0, z: 0, origin: [0, 0], locked: false, group_id: null, layer_id: null, _id: newId(), ...extra })

// 둥근 네모 패스(모서리 r — 베지어 근사)
function roundRect(w, h, r) {
  const k = r * 0.5523
  return [['M', r, 0], ['L', w - r, 0], ['C', w - r + k, 0, w, r - k, w, r], ['L', w, h - r], ['C', w, h - r + k, w - r + k, h, w - r, h],
    ['L', r, h], ['C', r - k, h, 0, h - r + k, 0, h - r], ['L', 0, r], ['C', 0, r - k, r - k, 0, r, 0], ['Z']]
}
// 상자 안 좌표의 변 가운데(r·l·t·b) — 화살표가 붙는 자리(.ecad `bindN_pt`)
const sidePt = ([, , w, h], s) => ({ r: [w, h / 2], l: [0, h / 2], t: [w / 2, 0], b: [w / 2, h] })[s]
const FWD = { LR: ['r', 'l'], RL: ['l', 'r'], TD: ['b', 't'], BT: ['t', 'b'] }

/** 화살표마다 붙을 변 [앞, 뒤] — 데스크톱과 같은 규칙: 흐름 방향 변끼리, 꺾은 덩어리를 넘어가면 아래 → 위(세로 흐름이면 오른쪽 → 왼쪽),
 *  되돌아가는 고리는 흐름 옆 변끼리(가로 흐름이면 아래 → 아래), 갈림길에서 앞으로 나가는 연결이 둘 이상이면 하나만 앞 꼭짓점·나머지는 위·아래 꼭짓점(「예」「아니오」가 한 점에서 겹치지 않게). */
export function linkSides(place) {
  const d = place.direction || 'LR', horiz = d === 'LR' || d === 'RL', by = new Map(place.steps.map(s => [s.id, s])), rk = place.ranks || {}
  const sides = place.links.map(k => {
    const a = by.get(k.from), b = by.get(k.to)
    if ((b.seg || 0) > (a.seg || 0)) return horiz ? ['b', 't'] : ['r', 'l']
    if ((rk[k.to] ?? 0) <= (rk[k.from] ?? 0)) return horiz ? ['b', 'b'] : ['r', 'r']
    return FWD[d] || FWD.LR
  })
  // 갈림길: 나가는 연결마다 다른 꼭짓점 — 들어오는 끝이 쓴 꼭짓점은 비우고, 가까운 것부터 원래 변(흐름 방향)을 가지며, 겹치면 가는 쪽에 가장 가까운 빈 꼭짓점.
  // 데스크톱은 앞으로 나가는 둘만 위·아래로 나눔 — 둘 다 다음 줄로 꺾어 내려가면 아래 꼭짓점에서 겹쳤음(2026-11-03 진짜 KAIROS 「점검 순서」)
  const ctr = s => { const [x, y, w, h] = s.box; return [x + w / 2, y + h / 2] }, NRM = { r: [1, 0], l: [-1, 0], t: [0, -1], b: [0, 1] }
  // 라벨 달린 갈래도 같게(2026-11-03 실조건 공개 칠판 20번 — 「상용전원」의 「전원 공급」 둘·「방향성 결합기」의 「출력 샘플」과 급전선이 한 점에서 앞 구간을 같이 써
  // 형제 선이 라벨 위로 지나갔음). 라벨 없는 갈래(조직도 아래 갈래 같은 묶음선)는 그대로
  const labeledFork = outs => outs.some(([k], j) => outs.some(([k2, i2], j2) => j2 !== j && sides[i2][0] === sides[outs[j][1]][0] && (k.text || k2.text)))
  for (const s of place.steps) {
    const outs = place.links.map((k, i) => [k, i]).filter(([k]) => k.from === s.id)
    if (outs.length < 2 || (s.kind !== 'decision' && !labeledFork(outs))) continue
    const used = new Set(place.links.map((k, i) => (k.to === s.id ? sides[i][1] : null)).filter(Boolean)), [cx, cy] = ctr(s)
    const dir = ([k]) => { const [x, y] = ctr(by.get(k.to)), dx = x - cx, dy = y - cy, n = Math.hypot(dx, dy) || 1; return [dx / n, dy / n, Math.hypot(dx, dy)] }
    const order = [...outs].sort((a, b) => ((rk[a[0].to] ?? 0) <= (rk[s.id] ?? 0)) - ((rk[b[0].to] ?? 0) <= (rk[s.id] ?? 0)) || dir(a)[2] - dir(b)[2])   // 앞으로 가는 것 먼저, 가까운 것 먼저
    for (const o of order) {
      const want = sides[o[1]][0]
      if (!used.has(want)) { used.add(want); continue }
      const [ux, uy] = dir(o), free = Object.keys(NRM).filter(v => !used.has(v))
      if (!free.length) continue
      const pick = free.reduce((a, v) => (NRM[v][0] * ux + NRM[v][1] * uy > NRM[a][0] * ux + NRM[a][1] * uy ? v : a))
      sides[o[1]] = [pick, sides[o[1]][1]]; used.add(pick)
    }
  }
  return sides
}

/** 꺾은 덩어리 사이 통로를 지나는 화살표가 여럿이고 가로 구간이 겹치면 높이(세로 흐름이면 x)를 나눠 줌 → 화살표마다 경유지 [dx, dy](두 끝 가운데 기준 — arrows.js `route_hints`) 또는 null.
 *  2026-11-03 사용자: 「수배전 → 전력 증폭기」와 「신호 분배 → 변조기」가 같은 높이로 포개져 한 선처럼 보이고, 라벨 「전원 공급」 뒤로 남의 선이 지나갔음(라벨은 제 선만 비움).
 *  검토한 대안: 라벨 밑을 지나는 모든 선 비우기 — 글은 깨끗해져도 어느 화살표 라벨인지 모르는 건 그대로라 버림. */
export function channelHints(place, ends, ox = 0, oy = 0) {
  const d = place.direction || 'LR', c = d === 'LR' || d === 'RL' ? 1 : 0, f = 1 - c, by = new Map(place.steps.map(s => [s.id, s]))
  const out = place.links.map(() => null), groups = new Map()
  // 통로와 끝 사이에 다른 상자가 있으면(같은 덩어리 안 아래·위 줄) 그 화살표는 돌아가야 해 통로를 못 씀 — 길 찾기에 맡김
  const blocked = (s, at, after) => place.steps.some(o => o !== s && (o.seg || 0) === (s.seg || 0) && o.box[f] <= at && at <= o.box[f] + o.box[f + 2] && (after ? o.box[c] > s.box[c] : o.box[c] < s.box[c]))
  place.links.forEach((k, i) => {
    const a = by.get(k.from), b = by.get(k.to)
    if (!ends[i] || (b.seg || 0) !== (a.seg || 0) + 1) return
    const [o0, o1] = [ox, oy]
    if (blocked(a, ends[i].A[f] - [o0, o1][f], true) || blocked(b, ends[i].B[f] - [o0, o1][f], false)) return
    groups.set(a.seg || 0, [...(groups.get(a.seg || 0) || []), i])
  })
  // 덩어리가 차지하는 교차축 범위(상자 + 그 상자가 든 띠)
  const span = sg => {
    let lo = Infinity, hi = -Infinity
    for (const s of place.steps.filter(x => (x.seg || 0) === sg)) {
      const s0 = s.box[c], s1 = s.box[c] + s.box[c + 2]
      const lane = (place.lanes || []).find(l => l.rect[c] <= s0 && s1 <= l.rect[c] + l.rect[c + 2])
      lo = Math.min(lo, lane ? lane.rect[c] : s0); hi = Math.max(hi, lane ? lane.rect[c] + lane.rect[c + 2] : s1)
    }
    return [lo, hi]
  }
  const o = [ox, oy][c], STUB = 26, STEP = 22, ROOM = 20
  for (const [sg, ids] of groups) {
    const iv = ids.map(i => { const p = ends[i].A[f], q = ends[i].B[f]; return { i, lo: Math.min(p, q), hi: Math.max(p, q) } }).sort((x, y) => x.lo - y.lo || x.hi - y.hi)
    const tracks = []   // 줄마다 마지막 끝
    for (const v of iv) {
      let t = tracks.findIndex(e => e < v.lo - ROOM)
      if (t < 0) { t = tracks.length; tracks.push(0) }
      tracks[t] = v.hi; v.t = t
    }
    if (tracks.length < 2) continue
    const chan = (span(sg)[1] + span(sg + 1)[0]) / 2 + o
    const top = Math.max(...ids.map(i => ends[i].A[c])) + STUB, bot = Math.min(...ids.map(i => ends[i].B[c])) - STUB
    const n = tracks.length, step = Math.max(0, Math.min(STEP, (bot - top) / (n - 1)))
    const mid = Math.min(Math.max(chan, top + step * (n - 1) / 2), bot - step * (n - 1) / 2)
    for (const v of iv) {
      const { A, B } = ends[v.i], m = [(A[0] + B[0]) / 2, (A[1] + B[1]) / 2], h = [0, 0]
      h[c] = mid + (v.t - (n - 1) / 2) * step - m[c]
      out[v.i] = h
    }
  }
  return out
}

/** 라벨 달린 짧은 화살표(옆 상자로 곧게) 틈을 남의 세로선이 지나면 그 선에 다른 세로 통로를 줌(처음 지을 때만, 경유지 `route_hints`) —
 *  통로 = 지나는 높이에서 상자(여유 12)·라벨 틈(여유 6)에 안 걸리는 x 중 원래 자리에서 가장 가까운 곳. 못 찾거나 바꿔도 걸리면 그대로.
 *  2026-11-03 실조건(공개 칠판 19·20번): 아래 줄 → 위 줄 되돌림 선(「제어」·「상태 보고·원격제어」)이 「출력 샘플」·「변조된 RF」 틈(119)을 세로로 지나 라벨 둘 자리가 없었음. */
export function clearLabelGaps(items, x0, x1) {
  const fs = HEAD_PT * PX, heads = items.filter(it => it.type === 'text').map(it => {   // 띠 이름표 글자도 피함(왼쪽 바깥 통로가 이름 위를 지날 수 있음)
    const lines = String(it.text).split('\n'); return { l: it.pos[0], t: it.pos[1], r: it.pos[0] + Math.max(...lines.map(t => textW(t, fs))) + 8, b: it.pos[1] + lines.length * fs * 1.3 + 8 }
  })
  const boxes = items.filter(it => it.flow_step).map(it => ({ l: it.pos[0], t: it.pos[1], r: it.pos[0] + it.rect[2], b: it.pos[1] + it.rect[3] })).concat(heads)
  const arrows = () => { const r = resolveRoutes(items); return items.map((it, i) => (it.type === 'sarrow' ? { it, pts: r.get(i) || it.pts } : null)).filter(Boolean) }
  const gapsOf = as => as.filter(a => a.it.labels?.[0]?.text && a.pts.length === 2 && Math.abs(a.pts[0][1] - a.pts[1][1]) < 0.5)
    .map(a => ({ a: a.it, y: a.pts[0][1], l: Math.min(a.pts[0][0], a.pts[1][0]), r: Math.max(a.pts[0][0], a.pts[1][0]) }))
  const crossing = (a, gaps) => a.pts.slice(1).map((q, j) => [a.pts[j], q]).filter(([p, q]) => Math.abs(p[0] - q[0]) < 0.5)
    .find(([p, q]) => gaps.some(g => g.a !== a.it && g.l + 4 < p[0] && p[0] < g.r - 4 && Math.min(p[1], q[1]) < g.y && g.y < Math.max(p[1], q[1])))
  let as = arrows()
  for (const a of as) {
    if (a.it.route_hints?.length) continue
    const gaps = gapsOf(as), hit = crossing(a, gaps); if (!hit) continue
    const lo = Math.min(hit[0][1], hit[1][1]), hi = Math.max(hit[0][1], hit[1][1]), sx = hit[0][0]
    const ok = x => !boxes.some(b => b.l - 12 < x && x < b.r + 12 && b.t < hi && lo < b.b) && !gaps.some(g => g.l - 6 < x && x < g.r + 6 && lo < g.y && g.y < hi)
    let best = null
    for (let x = Math.ceil(x0); x <= x1; x += 4) if (ok(x) && (best == null || Math.abs(x - sx) < Math.abs(best - sx))) best = x
    if (best == null) continue
    const A = a.pts[0], B = a.pts[a.pts.length - 1], old = a.it.route_hints
    a.it.route_hints = [[best - (A[0] + B[0]) / 2 - a.it.pos[0], (lo + hi) / 2 - (A[1] + B[1]) / 2 - a.it.pos[1]]]
    const next = arrows(), me = next.find(n => n.it === a.it)
    if (crossing(me, gapsOf(next))) a.it.route_hints = old
    else as = next
  }
  return items
}

/** 라벨을 제 선 위 빈자리로(처음 지을 때만 — 손으로 옮긴 라벨은 안 건드림): 가운데(또는 갈림길 옆)부터 조금씩 앞뒤로 옮겨 보며
 *  남의 화살표 선·상자·먼저 놓은 라벨·화살촉에 안 걸리는 첫 자리. 다 걸리면 그대로.
 *  2026-11-03 실조건(공개 칠판 19번): 곧게 내려가는 「전원 공급」 라벨 밑을 남의 가로선이 지나갔고 「출력 샘플」·「제어」 라벨이 서로 겹쳤음.
 *  검토한 대안: 남의 선도 라벨 자리만큼 끊기·사각 바탕 — 2026-10-18에 버림(선이 끊겨 보이고 그림을 가림, render.jsx `halo`). */
export function placeLabels(items) {
  const routes = resolveRoutes(items), LH = LABEL_PT * PX * 1.3 + 10, fs = LABEL_PT * PX
  const rect = (p, w) => ({ l: p.x - w / 2, r: p.x + w / 2, t: p.y - LH / 2, b: p.y + LH / 2 })
  const meet = (a, b) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b
  const boxes = items.filter(it => it.flow_step).map(it => ({ l: it.pos[0], t: it.pos[1], r: it.pos[0] + it.rect[2], b: it.pos[1] + it.rect[3] }))
  const arrows = items.map((it, i) => (it.type === 'sarrow' ? { it, pts: (routes.get(i) || it.pts).map(([x, y]) => ({ x: x + it.pos[0], y: y + it.pos[1] })) } : null)).filter(Boolean)
  const segs = a => a.pts.slice(1).map((q, j) => ({ l: Math.min(q.x, a.pts[j].x) - 1, r: Math.max(q.x, a.pts[j].x) + 1, t: Math.min(q.y, a.pts[j].y) - 1, b: Math.max(q.y, a.pts[j].y) + 1 }))
  const taken = []
  for (const A of arrows) {
    const L = A.it.labels?.[0]; if (!L?.text) continue
    const w = Math.max(...L.text.split('\n').map(t => textW(t, fs))) + 8, others = arrows.filter(o => o !== A).flatMap(segs)
    const total = A.pts.slice(1).reduce((s, q, j) => s + Math.hypot(q.x - A.pts[j].x, q.y - A.pts[j].y), 0)
    const ok = t => {
      const { p, n } = polylineAt(A.pts, t), r = rect(p, w), ext = Math.abs(n.y) > 0.5 ? w / 2 : LH / 2   // 법선이 세로 = 가로 구간 → 라벨 폭만큼
      return t * total >= ext + 4 && (1 - t) * total >= ext + 16 && !others.some(s => meet(r, s)) && !boxes.some(b => meet(r, b)) && !taken.some(b => meet(r, b))
    }
    const t0 = L.t ?? 0.5, cands = [t0]
    for (let k = 1; k <= 9; k++) cands.push(t0 - 0.05 * k, t0 + 0.05 * k)
    const t = cands.filter(x => x > 0.02 && x < 0.98).find(ok)
    if (t != null) L.t = Math.round(t * 1000) / 1000
    taken.push(rect(polylineAt(A.pts, L.t ?? 0.5).p, w))
  }
  return items
}

/** 서버 자리(`place`) → { frame, items } — 프레임 왼쪽 위 (X, Y). 물건마다 `flow_of` = 프레임 _id(다시 지을 때 지울 것).
 *  opt = { id: 프레임 _id(다시 지을 때 그대로), no, z(물건), zb(프레임 — 맨 뒤), spec: 설계서 글(이어 고치기 재료 — 프레임에 적어 둠) } */
export function flowItems(place, X, Y, { id = newId(), no = 1, z = 1, zb = -1, spec = '' } = {}) {
  const ox = X + PAD, oy = Y + PAD, out = [], laneIx = new Map()
  ;(place.lanes || []).forEach(l => { if (!laneIx.has(l.key)) laneIx.set(l.key, laneIx.size) })
  const colorOf = lane => LANE_COLORS[(laneIx.get(lane) ?? 0) % LANE_COLORS.length]
  for (const l of place.lanes || []) {   // 띠 + 이름표(띠 앞쪽 칸 가운데)
    const c = colorOf(l.key), [x, y, w, h] = l.rect, [hx, hy, hw, hh] = l.head
    out.push(base([ox + x, oy + y], { type: 'path', elements: roundRect(w, h, 10), pen: argb(c, BAND_EDGE_A), width: 1, fill: argb(c, BAND_A), freehand: false, style: 1, z, flow_of: id }))
    const lines = String(l.name).split('\n'), fs = HEAD_PT * PX, tw = Math.max(...lines.map(t => textW(t, fs))), th = lines.length * fs * 1.3
    out.push(base([ox + hx + (hw - tw) / 2 - 4, oy + hy + (hh - th) / 2 - 4], { type: 'text', text: l.name, color: argb(c), font: HEAD_PT, bg: null, weight: 700, z: z + 1, flow_of: id }))
  }
  const box = new Map()
  for (const s of place.steps) {
    const [x, y, w, h] = s.box, c = colorOf(s.lane), focus = s.id === place.focus, kind = SHAPE[s.kind]
    const it = base([ox + x, oy + y], { type: kind ? 'symbol' : 'rect', ...(kind ? { kind } : {}), rect: [0, 0, w, h],
      pen: argb(focus ? CORAL : c), width: focus ? 3 : 2, fill: onWhite(focus ? CORAL : c, focus ? FOCUS_A : BOX_A), style: 1,
      label: { text: s.text, color: INK, font: LABEL_PT, bg: null }, z: z + 2, flow_of: id, flow_step: s.id })
    out.push(it); box.set(s.id, it)
  }
  const sides = linkSides(place), kinds = new Map(place.steps.map(s => [s.id, s.kind]))
  const ends = place.links.map((k, i) => {
    const a = box.get(k.from), b = box.get(k.to); if (!a || !b) return null
    const [sa, sb] = sides[i], pa = sidePt(a.rect, sa), pb = sidePt(b.rect, sb)
    return { a, b, pa, pb, A: [a.pos[0] + pa[0], a.pos[1] + pa[1]], B: [b.pos[0] + pb[0], b.pos[1] + pb[1]] }
  })
  const hints = channelHints(place, ends, ox, oy)
  place.links.forEach((k, i) => {
    if (!ends[i]) return
    const { a, b, pa, pb, A, B } = ends[i], len = Math.abs(B[0] - A[0]) + Math.abs(B[1] - A[1])
    // 「예」「아니오」는 갈림길 바로 옆에(가운데면 긴 선 한복판에 뜸 — 데스크톱 `_conn_t`)
    const t = kinds.get(k.from) === 'decision' && len > 0 ? Math.min(0.5, 34 / len) : 0.5
    out.push(base([0, 0], { type: 'sarrow', pts: [A, B], color: INK, width: 2, head: true, head_start: false, head_scale: 1, style: 1, auto_route: true, routing: 'ortho', curve_r: 10, route_hints: hints[i] ? [hints[i]] : [],
      labels: k.text ? [{ text: k.text, color: INK, font: LABEL_PT, bg: null, t, off: 0 }] : [],
      _bind1: a._id, bind1_pt: pa, bind1_group: null, _bind2: b._id, bind2_pt: pb, bind2_group: null, z: z + 1, flow_of: id }))
  })
  clearLabelGaps(out, ox, ox + place.width)
  placeLabels(out)
  const W = place.width + 2 * PAD, H = place.height + 2 * PAD
  const frame = { ...base([X, Y], { type: 'frame', rect: [0, 0, W, H], name: place.title || '도형', no, z: zb }), _id: id, flow_spec: spec }
  return { frame: { ...frame, flow_sig: flowSig(out, X, Y) }, items: out }
}

// 지은 모습 지문(프레임 기준 자리 — 프레임째 옮기면 그대로, 손으로 고치면 달라짐 → 이어 고치기는 덮어쓰지 않고 옆에 새로). 화살표 꼭짓점은 길 찾기가 바꾸니 뺌
export const flowSig = (pcs, X, Y) => JSON.stringify(pcs.map(p => (p.type === 'sarrow' ? [p.type, p.labels?.map(l => l.text), p.color, p.width]
  : [p.type, p.kind, Math.round(p.pos[0] - X), Math.round(p.pos[1] - Y), p.rect?.map(Math.round), p.text, p.label?.text, p.fill, p.pen, p.color])))
