// 🔷 도형 그리기(2026-11-03 사용자 — 「송신소 계통도 그려 줘」 = 고칠 수 있는 상자 + 붙은 화살표). 순수 — 칠판 물건만 만든다.
// 자리는 서버가 데스크톱 흐름도 규칙으로 계산(`easycad/ai/board_diagram.place` → `flow_spec.layout`) — 여기는 그 자리에 물건을 짓기만.
// 모양·색은 데스크톱 `host_fileio._build_flowspec_items`와 같게: 담당 띠 = 옅은 색 채운 패스(길 찾기 장애물 아님), 상자 = 띠 색 테두리 + 옅은 바탕,
// 가장 중요한 단계(focus) 하나만 코랄, 글자 = 기본 잉크(어두운 화면에선 흰색으로 바뀜), 화살표 = 「자동 길」 직각 + 두 끝 붙음(상자를 옮기면 따라옴).
import { newId } from './model.js'
import { textW } from './chart.js'

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
  for (const s of place.steps.filter(x => x.kind === 'decision')) {
    const outs = place.links.map((k, i) => [k, i]).filter(([k]) => k.from === s.id)
    if (outs.length < 2) continue
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
  place.links.forEach((k, i) => {
    const a = box.get(k.from), b = box.get(k.to); if (!a || !b) return
    const [sa, sb] = sides[i], pa = sidePt(a.rect, sa), pb = sidePt(b.rect, sb)
    const A = [a.pos[0] + pa[0], a.pos[1] + pa[1]], B = [b.pos[0] + pb[0], b.pos[1] + pb[1]], len = Math.abs(B[0] - A[0]) + Math.abs(B[1] - A[1])
    // 「예」「아니오」는 갈림길 바로 옆에(가운데면 긴 선 한복판에 뜸 — 데스크톱 `_conn_t`)
    const t = kinds.get(k.from) === 'decision' && len > 0 ? Math.min(0.5, 34 / len) : 0.5
    out.push(base([0, 0], { type: 'sarrow', pts: [A, B], color: INK, width: 2, head: true, head_start: false, head_scale: 1, style: 1, auto_route: true, routing: 'ortho', curve_r: 10, route_hints: [],
      labels: k.text ? [{ text: k.text, color: INK, font: LABEL_PT, bg: null, t, off: 0 }] : [],
      _bind1: a._id, bind1_pt: pa, bind1_group: null, _bind2: b._id, bind2_pt: pb, bind2_group: null, z: z + 1, flow_of: id }))
  })
  const W = place.width + 2 * PAD, H = place.height + 2 * PAD
  const frame = { ...base([X, Y], { type: 'frame', rect: [0, 0, W, H], name: place.title || '도형', no, z: zb }), _id: id, flow_spec: spec }
  return { frame: { ...frame, flow_sig: flowSig(out, X, Y) }, items: out }
}

// 지은 모습 지문(프레임 기준 자리 — 프레임째 옮기면 그대로, 손으로 고치면 달라짐 → 이어 고치기는 덮어쓰지 않고 옆에 새로). 화살표 꼭짓점은 길 찾기가 바꾸니 뺌
export const flowSig = (pcs, X, Y) => JSON.stringify(pcs.map(p => (p.type === 'sarrow' ? [p.type, p.labels?.map(l => l.text), p.color, p.width]
  : [p.type, p.kind, Math.round(p.pos[0] - X), Math.round(p.pos[1] - Y), p.rect?.map(Math.round), p.text, p.label?.text, p.fill, p.pen, p.color])))
