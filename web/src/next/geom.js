// 직접 만드는 칠판(§8 항목61 「바뀐 결정」, 2026-10-17)의 그리기 계산 — 데스크톱 `core_shapes.py`의 paint 규칙을 옮김.
// 순수 함수(node 시험 대상). 점 {x,y}.

export const PT = 96 / 72          // Qt 글자 pt → 화면 px(96dpi)
export const TEXT_MARGIN = 4       // QTextDocument 기본 여백(글 상자·라벨)
export const APP_FONT = "'Segoe UI', 'Malgun Gothic', sans-serif"   // 데스크톱 기본 글꼴(윈도우)
export const BOARD_FONT = "'Pretendard', 'Malgun Gothic', sans-serif"
// 글꼴 세로 치수(em 비율) — 첫 줄 기준선 = 여백 + ascent, 줄 간격 = lineSpacing(Qt QFontMetrics와 같은 뜻)
export const METRICS = { app: { ascent: 1.077, lineSpacing: 1.328 }, board: { ascent: 0.95, lineSpacing: 1.193 } }

// Qt 펜 모양 → SVG 점선(펜 굵기 배수, 데스크톱 QPen 기본 무늬): 1 실선 2 대시 3 점 4 대시점 5 대시점점, 0 = 선 없음
export function dashArray(style, width) {
  const w = Math.max(1, width || 1)
  const pat = { 2: [4, 2], 3: [1, 2], 4: [4, 2, 1, 2], 5: [4, 2, 1, 2, 1, 2] }[style]
  return pat ? pat.map(v => v * w).join(' ') : undefined
}

// 아이템 변환(데스크톱 QGraphicsItem: pos 다음 origin을 중심으로 rotation·scale)
export function itemTransform(it) {
  const [x, y] = it.pos || [0, 0], r = it.rotation || 0, s = it.scale || 1, [ox, oy] = it.origin || [0, 0]
  let t = `translate(${x},${y})`
  if (r || s !== 1) t += ` translate(${ox},${oy})${r ? ` rotate(${r})` : ''}${s !== 1 ? ` scale(${s})` : ''} translate(${-ox},${-oy})`
  return t
}

// 화살촉 — 데스크톱 `_head_size`(굵기×3.2, 바닥 11) × 배율, 꼭짓점 셋(tip, 각 ±150°)
export const headSize = (width, scale = 1) => Math.max(width * 3.2, 11) * (scale || 1)
export function headTriangle(tip, angle, size) {
  const a1 = angle + (150 * Math.PI) / 180, a2 = angle - (150 * Math.PI) / 180
  return [tip, { x: tip.x + size * Math.cos(a1), y: tip.y + size * Math.sin(a1) }, { x: tip.x + size * Math.cos(a2), y: tip.y + size * Math.sin(a2) }]
}

// 직각 화살표 몸통 — 화살촉 있는 끝의 마지막 구간을 head×0.85만큼 당김(`_trimmed_body_pts`)
export function trimmedPts(pts, size, headEnd, headStart) {
  const out = pts.map(p => ({ ...p })), cut = size * 0.85
  const pull = (a, b) => { const L = Math.hypot(b.x - a.x, b.y - a.y); if (L < 1e-6) return b; const t = Math.max(0, 1 - cut / L); return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t } }
  if (pts.length >= 2) {
    if (headEnd) out[out.length - 1] = pull(pts[pts.length - 2], pts[pts.length - 1])
    if (headStart) out[0] = pull(pts[1], pts[0])
  }
  return out
}

// 둥근 꺾임 경로(`_rounded_polyline_path`) — 반경은 이웃 두 변 절반으로 줄임, 0이면 직각
export function roundedPath(pts, radius) {
  if (pts.length < 3 || !radius) return 'M' + pts.map(p => `${p.x},${p.y}`).join(' L')
  let d = `M${pts[0].x},${pts[0].y}`
  for (let i = 1; i < pts.length - 1; i++) {
    const a = pts[i - 1], c = pts[i], b = pts[i + 1]
    const la = Math.hypot(c.x - a.x, c.y - a.y), lb = Math.hypot(b.x - c.x, b.y - c.y), r = Math.min(radius, la / 2, lb / 2)
    if (r < 1e-3) { d += ` L${c.x},${c.y}`; continue }
    d += ` L${c.x + ((a.x - c.x) / la) * r},${c.y + ((a.y - c.y) / la) * r} Q${c.x},${c.y} ${c.x + ((b.x - c.x) / lb) * r},${c.y + ((b.y - c.y) / lb) * r}`
  }
  return d + ` L${pts[pts.length - 1].x},${pts[pts.length - 1].y}`
}

// roundedPath와 같은 둥근 꺾임을 점열로(모서리마다 steps 토막) — 띠 테두리 계산용
export function roundedPts(pts, radius, steps = 8) {
  if (pts.length < 3 || !radius) return pts
  const out = [pts[0]]
  for (let i = 1; i < pts.length - 1; i++) {
    const a = pts[i - 1], c = pts[i], b = pts[i + 1]
    const la = Math.hypot(c.x - a.x, c.y - a.y), lb = Math.hypot(b.x - c.x, b.y - c.y), r = Math.min(radius, la / 2, lb / 2)
    if (r < 1e-3) { out.push(c); continue }
    const s0 = { x: c.x + ((a.x - c.x) / la) * r, y: c.y + ((a.y - c.y) / la) * r }, e0 = { x: c.x + ((b.x - c.x) / lb) * r, y: c.y + ((b.y - c.y) / lb) * r }
    for (let k = 0; k <= steps; k++) { const t = k / steps, u = 1 - t; out.push({ x: u * u * s0.x + 2 * u * t * c.x + t * t * e0.x, y: u * u * s0.y + 2 * u * t * c.y + t * t * e0.y }) }
  }
  out.push(pts[pts.length - 1])
  return out
}

// 꺾은선을 폭 2·hw로 그었을 때의 바깥 윤곽 다각형(꺾임 = 맞댐, 끝 = 반원 또는 잘라냄) — 선 띠의 테두리(데스크톱 QPainterPathStroker 띠).
// 마스크(흰·검정)를 쓰지 않고 모양을 계산한다 — 어두운 화면 확장이 마스크 색을 바꿔 깨진 적이 있다(pitfalls).
export function strokeOutline(pts, hw, capStart = true, capEnd = true, steps = 8) {
  const p = pts.filter((q, i) => i === 0 || Math.hypot(q.x - pts[i - 1].x, q.y - pts[i - 1].y) > 1e-6)
  const ring = (c, from, to, u, v) => { const o = []; for (let k = 0; k <= steps; k++) { const t = from + ((to - from) * k) / steps; o.push({ x: c.x + hw * (Math.cos(t) * u.x + Math.sin(t) * v.x), y: c.y + hw * (Math.cos(t) * u.y + Math.sin(t) * v.y) }) } return o }
  if (p.length < 2) return p.length ? ring(p[0], 0, 2 * Math.PI, { x: 1, y: 0 }, { x: 0, y: 1 }).slice(0, -1) : []
  const n = p.length, nor = [], dir = []
  for (let i = 0; i < n - 1; i++) { const dx = p[i + 1].x - p[i].x, dy = p[i + 1].y - p[i].y, L = Math.hypot(dx, dy); dir.push({ x: dx / L, y: dy / L }); nor.push({ x: -dy / L, y: dx / L }) }
  const side = sg => p.map((q, i) => {
    const a = nor[Math.max(0, i - 1)], b = nor[Math.min(n - 2, i)]
    let mx = a.x + b.x, my = a.y + b.y; const ml = Math.hypot(mx, my)
    if (ml < 1e-6) { mx = a.x; my = a.y } else { mx /= ml; my /= ml }
    const k = Math.min(hw / Math.max(mx * a.x + my * a.y, 0.25), hw * 4)   // 맞댐 길이(되꺾이면 4배까지만)
    return { x: q.x + mx * k * sg, y: q.y + my * k * sg }
  })
  const L = side(1), R = side(-1), last = n - 2
  const neg = v => ({ x: -v.x, y: -v.y })
  const endCap = capEnd ? ring(p[n - 1], 0, Math.PI, nor[last], dir[last]).slice(1, -1) : []
  const startCap = capStart ? ring(p[0], 0, Math.PI, neg(nor[0]), neg(dir[0])).slice(1, -1) : []
  return [...L, ...endCap, ...R.reverse(), ...startCap]
}

// 꺾은선 위 길이 비율 t 지점과 왼쪽 단위 법선(`_PolyArrowItem._point_at_t`)
export function polylineAt(pts, t) {
  const segs = []; let total = 0
  for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y); segs.push([pts[i - 1], pts[i], d]); total += d }
  if (total < 1e-9) return { p: { ...pts[0] }, n: { x: 0, y: -1 } }
  const target = Math.max(0, Math.min(1, t)) * total
  let run = 0
  for (let i = 0; i < segs.length; i++) {
    const [a, b, d] = segs[i]
    if (run + d >= target || i === segs.length - 1) {
      const tt = d > 1e-9 ? (target - run) / d : 0
      return { p: { x: a.x + (b.x - a.x) * tt, y: a.y + (b.y - a.y) * tt }, n: d > 1e-9 ? { x: -(b.y - a.y) / d, y: (b.x - a.x) / d } : { x: 0, y: -1 } }
    }
    run += d
  }
  return { p: { ...pts[pts.length - 1] }, n: { x: 0, y: -1 } }
}

// 3차 베지어 점 — 곡선 화살표(`_ArrowItem._point_at`, t는 곡선 매개변수)
export function bezierAt(p0, c1, c2, p3, t) {
  const u = 1 - t
  return { x: u * u * u * p0.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t * t * t * p3.x,
           y: u * u * u * p0.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t * t * t * p3.y }
}
// 곡선 위 t 지점과 왼쪽 법선(유한차분, `_point_at_t_normal`)
export function curveAt(p0, c1, c2, p3, t) {
  const dt = 1e-3, a = bezierAt(p0, c1, c2, p3, Math.max(0, t - dt)), b = bezierAt(p0, c1, c2, p3, Math.min(1, t + dt))
  const tx = b.x - a.x, ty = b.y - a.y, L = Math.hypot(tx, ty)
  return { p: bezierAt(p0, c1, c2, p3, t), n: L < 1e-9 ? { x: 0, y: -1 } : { x: -ty / L, y: tx / L } }
}
// 베지어 [t0,t1] 부분 곡선의 제어점(드 카스텔조) — 화살촉 쪽 몸통을 자를 때
export function bezierSub(p0, c1, c2, p3, t0, t1) {
  const lerp = (a, b, t) => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t })
  const split = (P, t) => {   // [P0..P3] → 오른쪽 조각
    const [a, b, c, d] = P, ab = lerp(a, b, t), bc = lerp(b, c, t), cd = lerp(c, d, t), abc = lerp(ab, bc, t), bcd = lerp(bc, cd, t), m = lerp(abc, bcd, t)
    return { left: [a, ab, abc, m], right: [m, bcd, cd, d] }
  }
  let P = [p0, c1, c2, p3]
  if (t1 < 1) P = split(P, t1).left
  if (t0 > 0) P = split(P, t0 / Math.max(t1, 1e-9)).right
  return P
}

// 글 + runs([시작, 길이, 색, 굵게, 배경?]) → 줄마다 조각 [{text, color, bold, bg}]
export function runsToLines(text, runs) {
  const n = text.length, attr = new Array(n).fill(null)
  for (const [s, len, color, bold, bg] of runs || [])
    for (let i = Math.max(0, s); i < Math.min(n, s + len); i++) attr[i] = { color: color || null, bold: !!bold, bg: bg || null }
  const same = (a, b) => (a?.color ?? null) === (b?.color ?? null) && !!a?.bold === !!b?.bold && (a?.bg ?? null) === (b?.bg ?? null)
  const lines = []
  let pos = 0
  for (const line of text.split('\n')) {
    const parts = []
    for (let i = 0; i < line.length;) {
      const a = attr[pos + i]; let j = i + 1
      while (j < line.length && same(attr[pos + j], a)) j++
      parts.push({ text: line.slice(i, j), color: a?.color ?? null, bold: !!a?.bold, bg: a?.bg ?? null }); i = j
    }
    lines.push(parts)
    pos += line.length + 1
  }
  return lines
}

// 표 열 경계(`_col_edges_local`) — 열 폭 비율 누적, 마지막은 오른쪽 끝에 고정
export function colEdges(x, w, colWidths) {
  const out = [x]; let acc = x
  for (const cw of colWidths) { acc += cw * w; out.push(acc) }
  out[out.length - 1] = x + w
  return out
}

// 용지틀 치수(mm 단위 = 칠판 단위) — 데스크톱 PAPER_SIZES_MM, 가로면 w·h 교환
export const PAPER = { A4: [210, 297], A3: [297, 420], A2: [420, 594], A1: [594, 841], A0: [841, 1189] }
export const paperWH = (size, orient) => { const [w, h] = PAPER[size] || PAPER.A2; return orient === 'landscape' ? [h, w] : [w, h] }
export const TB_ROWS = [
  [1.2, [['발주처 / 프로젝트', 'client', 3], ['도면번호', 'number', 2]]],
  [1.2, [['도면명', 'title', 3], ['축척', 'scale', 2]]],
  [1.0, [['작성', 'author', 2], ['검토', 'reviewer', 2], ['날짜', 'date', 1]]],
]

// 도형 안 라벨 폭 비율(`_label_inset_ratio`) — 상자 0.85, 원 0.72, 심볼 종류별
export function labelInset(type, kind) {
  if (type === 'ellipse') return 0.72
  if (type !== 'symbol') return 0.85
  if (kind === 'triangle') return 0.5
  if (kind === 'decision') return 0.6
  if (['database', 'document', 'display', 'delay'].includes(kind)) return 0.72
  if (kind === 'manual_op') return 0.7
  if (['mw_side', 'mw_front', 'mesh_filled', 'mesh_hollow'].includes(kind)) return 0.55
  if (kind === 'cp_ring') return 0.4
  if (kind === 'dtv') return 0.2
  if (kind === 'lightning') return 0.3
  return 0.78
}
// 도형 안 라벨 기준점(`_label_anchor` — 원기둥·문서·삼각형만 광학 보정)
export function labelAnchor(type, kind, r) {
  const [x, y, w, h] = r, c = { x: x + w / 2, y: y + h / 2 }
  if (type !== 'symbol') return c
  if (kind === 'database') return { x: c.x, y: c.y + Math.min(h * 0.18, w * 0.5) * 0.7 }
  if (kind === 'document') return { x: c.x, y: c.y - h * 0.06 }
  if (kind === 'triangle') return { x: x + w / 3, y: c.y }
  return c
}

// 라벨 자리 비우기 — 꺾은선에서 사각형들({x,y,w,h})과 겹치는 구간을 빼고 남은 조각들(데스크톱 `_visible_polyline_path`·`_seg_rect_interval`).
// 색을 바꾸는 마스크 대신 계산으로 자르므로 브라우저 다크 모드가 색을 바꿔도 늘 끊김. → [[{x,y},…], …]
function segRect(a, b, r) {   // Liang-Barsky: 선분 a→b가 r 안을 지나는 t 구간 | null
  const dx = b.x - a.x, dy = b.y - a.y; let t0 = 0, t1 = 1
  for (const [p, q] of [[-dx, a.x - r.x], [dx, r.x + r.w - a.x], [-dy, a.y - r.y], [dy, r.y + r.h - a.y]]) {
    if (Math.abs(p) < 1e-12) { if (q < 0) return null; continue }
    const t = q / p
    if (p < 0) { if (t > t1) return null; if (t > t0) t0 = t } else { if (t < t0) return null; if (t < t1) t1 = t }
  }
  return t0 > t1 ? null : [t0, t1]
}
export function cutPolyline(pts, rects) {
  if (!rects?.length) return [pts]
  const out = []; let cur = null
  const at = (a, b, t) => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t })
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i], b = pts[i + 1], iv = rects.map(r => segRect(a, b, r)).filter(Boolean).sort((u, v) => u[0] - v[0])
    const merged = []
    for (const v of iv) { const m = merged[merged.length - 1]; if (m && v[0] <= m[1]) m[1] = Math.max(m[1], v[1]); else merged.push([...v]) }
    let c = 0
    for (const [i0, i1] of merged) {
      if (i0 > c + 1e-6) { const s = at(a, b, c); if (!cur || c > 1e-6) { cur = [s]; out.push(cur) } cur.push(at(a, b, i0)) }
      cur = null; c = Math.max(c, i1)
    }
    if (c < 1 - 1e-6) { if (!cur || c > 1e-6) { cur = [at(a, b, c)]; out.push(cur) } cur.push(b) }
  }
  return out.filter(q => q.length >= 2)
}

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

// 표 행 경계(길이 rows+1) — .ecad 표 `row_heights`(표 높이 대비 비율, 웹 먼저 2026-10-18 — 데스크톱은 보존만, 행 같은 높이로 그림). 없으면 같은 높이
export function rowEdges(y, h, it) {
  const n = it.rows, fr = it.row_heights?.length === n ? it.row_heights : null, out = [y]; let acc = y
  for (let i = 0; i < n; i++) { acc += (fr ? fr[i] : 1 / n) * h; out.push(acc) }
  out[n] = y + h
  return out
}
export const colFracs = it => (it.col_widths?.length === it.cols ? it.col_widths : Array(it.cols).fill(1 / it.cols))

// 프레임(.ecad `frame`, 웹 먼저 2026-10-18 — 「종이틀」 대신: 드래그로 감싼 영역 = 출력 한 쪽·슬라이드 한 장). ratio = 가로:세로(긴 쪽 기준 — 세로로 길면 뒤집어 씀)
export const FRAME_RATIOS = { '16:9': 16 / 9, '4:3': 4 / 3, A4: 297 / 210, '1:1': 1 }
export const frameTagFs = it => Math.max(12, Math.min(it.rect[2], it.rect[3]) * 0.03)   // 틀 위 이름표 글자 크기(틀 크기 따라)
export const frameTag = it => `${it.no ?? ''}${it.name ? ' · ' + it.name : ''}` || '프레임'
