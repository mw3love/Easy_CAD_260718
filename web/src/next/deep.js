// 딥모드 지면 배치(§8 항목66 2단계, 2026-10-25) — 편집장 계획(꼭지 목록)을 12칸 격자 지면에 놓는 순수 계산.
// 2차(같은 날 사용자 판정 「줄이 안 맞고 공간을 못 씀 · 16:9를 억지로?」 → 잡지·신문·벤토 격자 규칙 조사): 내용 먼저, 크기는 그다음.
// - 폭은 정하고 높이는 내용만큼(16:9 고집 버림 — 아주 길 때만 줄 경계에서 여러 장)
// - 줄 = 모듈: 한 줄 꼭지들의 높이가 비슷해지게 칸 수를 나눠 줌(신문 「반듯한 네모·갇힌 빈칸 금지」), 키 큰 꼭지 옆엔 작은 꼭지 둘을 위아래로 쌓음
// - 후보를 다 만들어 점수로 고름(Flipboard Duplo처럼 — 꼭지 8~9개라 동적 계획법으로 금방): 점수 = 갇힌 빈칸 + 칸 수가 모양 한도를 넘친 만큼 + 줄 사이 간격
// 꼭지 높이는 재는 함수(measure)를 받음 — 브라우저는 실제로 만든 물건 치수(deepboard.js), 시험은 가짜. 계획 차례는 그대로(줄 안·줄 사이).

export const DEEP = {
  W: 1600,          // 지면 폭(발표·인쇄 때 화면에 맞춰 줄고 늚 — 글은 이 폭 기준 메모 본문 14px)
  M: 48,            // 지면 안 바깥 여백
  G: 16,            // 칸 사이(가로·세로 같게 — 잡지 격자 「간격은 어디서나 같게」)
  K: 1,             // 본문 배율
  HEAD_GAP: 20,     // 머리(머리말·헤드라인) 아래
  MAX_H: 2400,      // 한 장 높이 한도(폭의 1.5배) — 넘으면 줄 경계에서 다음 장
  PAGE_GAP: 240,    // 여러 장일 때 장 사이
  ROW_MAX: 5,       // 한 줄에 꼭지 최대
}

/** 꼭지 칸 수 범위 [바닥, 한도] — 크기(주인공·보통·작게)와 모양으로. 바닥은 꼭 지킴(그래프 360px·단계 가로 늘어놓기), 한도는 넘으면 벌점(작은 꼭지가 줄을 통째로 먹어 속이 텅 빈 것) */
export function spanRange(sec) {
  const size = sec.size, shape = sec.shape, b = sec.body || {}
  let lo = size === '주인공' ? 6 : 3, hi = size === '주인공' ? 8 : size === '작게' ? 4 : 6
  if (shape === '그래프') { lo = Math.max(lo, 4); hi = Math.max(hi, 6) }
  if (shape === '단계 카드') { lo = Math.max(lo, (b.steps?.length || 4) >= 5 ? 8 : 6); hi = 12 }
  if (shape === '표') { lo = Math.max(lo, 5); hi = Math.max(hi, 8) }
  if (shape === '숫자 타일') { lo = Math.max(lo, (b.tiles?.length || 3) >= 3 ? 4 : 3); hi = Math.max(hi, 6) }
  if (shape === '출처 카드') hi = Math.min(hi, 4)
  return [Math.min(12, lo), Math.min(12, Math.max(lo, hi))]
}
/** 꼭지 모양 바꿔 보기(카피피팅 — 신문은 내용을 칸에 맞춰 다듬음): 숫자 = 나란히|위아래, 단계 = 한 줄|두 줄, 그래프 = 높게|낮게. 줄마다 높이가 가장 잘 맞는 것을 고름 */
export const variantsOf = sec => (sec.shape === '숫자 타일' ? ['row', 'col'] : sec.shape === '단계 카드' ? ['row', 'grid'] : sec.shape === '그래프' ? ['tall', 'short'] : [''])
// 그 폭에서 쓸 만한 모양인가 — 숫자 위아래 쌓기는 좁은 칸에서만(넓은 칸에서 쌓으면 타일 속이 텅 빔)
const variantOk = (sec, v, w) => !(v === 'col' && w > 520) && !(v === 'grid' && (sec.body?.steps?.length || 0) < 4)
// 위아래로 쌓을 수 있나 — 주인공·넓게 늘어놓는 모양(단계·표)은 혼자
const stackable = sec => sec.size !== '주인공' && sec.shape !== '단계 카드' && sec.shape !== '표'

// 한 줄(꼭지 a..b-1)의 칸 나누기 후보 중 가장 좋은 것 — slots: [[i] | [i, j]] 차례대로
function bestRow(secs, a, b, hOf, col) {
  const G = DEEP.G, cw = col * 12 + G * 11
  const parts = []   // 칸 묶음 나누기(하나씩 · 이웃 둘 쌓기) 모두
  const walk = (i, acc) => {
    if (i === b) { if (acc.length <= 4) parts.push(acc); return }
    walk(i + 1, [...acc, [i]])
    if (i + 1 < b && stackable(secs[i]) && stackable(secs[i + 1])) walk(i + 2, [...acc, [i, i + 1]])
  }
  walk(a, [])
  let best = null
  for (const slots of parts) {
    const R = slots.map(s => { const rs = s.map(i => spanRange(secs[i])); return [Math.max(...rs.map(r => r[0])), Math.max(...rs.map(r => r[1]))] })
    if (R.reduce((t, r) => t + r[0], 0) > 12) continue
    const spans = Array(slots.length), members = slots.flat(), vlist = members.map(i => variantsOf(secs[i]))
    const score = () => {   // 이 칸 수로 모양 조합마다
      const vs = Array(members.length).fill(0)
      for (;;) {
        const vOf = Object.fromEntries(members.map((i, m) => [i, vlist[m][vs[m]]]))
        const ok = slots.every((s, k) => s.every(i => variantOk(secs[i], vOf[i], spans[k] * col + (spans[k] - 1) * G)))
        const hs = !ok ? null : slots.map((s, k) => s.reduce((t, i) => t + hOf(i, spans[k], vOf[i]), 0) + (s.length - 1) * G), rh = hs ? Math.max(...hs) : 0
        let cost = hs ? cw * G : Infinity   // 줄 하나 = 간격 한 줄(줄이 많을수록 조금씩 손해 — 꼭지 하나씩 통째 줄로 쌓는 것 막기)
        if (hs) slots.forEach((s, k) => { const w = spans[k] * col + (spans[k] - 1) * G
          cost += (rh - hs[k]) * w   // 갇힌 빈칸
          cost += Math.max(0, spans[k] - R[k][1]) * (col + G) * hs[k] * 1.5 })   // 한도를 넘친 만큼(속이 텅 빈 넓은 칸)
        if (hs && (!best || cost < best.cost)) best = { cost, slots, spans: [...spans], rh, hs, v: vOf }
        let m = 0; while (m < vs.length && ++vs[m] >= vlist[m].length) vs[m++] = 0   // 다음 조합
        if (m === vs.length) break
      }
    }
    const pick = (k, left) => {   // 칸 수 고르기(합 12) — 칸 묶음마다 바닥부터
      if (k === slots.length - 1) { if (left >= R[k][0]) { spans[k] = left; score() } return }
      const rest = R.slice(k + 1).reduce((t, r) => t + r[0], 0)
      for (let s = R[k][0]; s <= left - rest; s++) { spans[k] = s; pick(k + 1, left - s) }
    }
    pick(0, 12)
  }
  return best
}

/** 줄 짜기 — 계획 차례 그대로, 모든 나누기 중 점수 합이 가장 작은 것(동적 계획법). [{ slots, spans, rh, hs, cost, v: { 꼭지: 모양 } }]. measure(i, w, k, 모양) */
export function deepRows(secs, measure, col, k = DEEP.K) {
  const cache = new Map(), G = DEEP.G
  const hOf = (i, span, v) => { const key = `${i}|${span}|${v}`; if (!cache.has(key)) cache.set(key, measure(i, span * col + (span - 1) * G, k, v)); return cache.get(key) }
  const n = secs.length, best = Array(n + 1).fill(null)
  best[0] = { cost: 0, rows: [] }
  for (let b = 1; b <= n; b++) for (let a = Math.max(0, b - DEEP.ROW_MAX); a < b; a++) {
    if (!best[a]) continue
    const r = bestRow(secs, a, b, hOf, col); if (!r) continue
    const c = best[a].cost + r.cost
    if (!best[b] || c < best[b].cost) best[b] = { cost: c, rows: [...best[a].rows, r] }
  }
  return best[n]?.rows || []
}

/** 지면 짜기 — 반환 { pages: [{ x, W, H, head, cells, k, G }], rows }. 칸 = { i, v: 모양, x, y, w, h, row, slot, top: 그 줄 위, rh: 줄 높이 } (장 안 좌표) */
export function deepLayout(plan, measure) {
  const secs = plan.sections || [], { W, M, G, K } = DEEP, cw = W - 2 * M, col = (cw - 11 * G) / 12
  const rows = deepRows(secs, measure, col, K)
  const pages = []
  let page = null, y = 0
  const open = () => { const headH = measure(-1, cw, K, pages.length); page = { x: pages.length * (W + DEEP.PAGE_GAP), W, H: 0, k: K, G, head: { x: M, y: M, w: cw, h: headH }, cells: [] }; y = M + headH + DEEP.HEAD_GAP; pages.push(page) }
  open()
  rows.forEach((r, ri) => {
    if (page.cells.length && y + r.rh + M > DEEP.MAX_H) open()
    let x = M
    r.slots.forEach((s, k) => { const w = r.spans[k] * col + (r.spans[k] - 1) * G
      let sy = y
      s.forEach(i => { const h = measure(i, w, K, r.v[i]); page.cells.push({ i, v: r.v[i], x, y: sy, w, h, row: ri, slot: k, top: y, rh: r.rh }); sy += h + G })
      x += w + G })
    y += r.rh + G
    page.H = y - G + M
  })
  return { rows, pages }
}

/** 갇힌 빈칸 비율 — 칸 묶음마다 (줄 높이 − 꼭지 높이 합) × 폭을 더해 줄 넓이 합으로 나눔(간격 빼고). 신문 「trapped white space」를 숫자로 */
export function deepWaste(page) {
  const slots = new Map()
  for (const c of page.cells) { const key = `${c.row}:${c.slot}`, s = slots.get(key) || { w: c.w, rh: c.rh, used: 0, n: 0 }; s.used += c.h; s.n++; slots.set(key, s) }
  let waste = 0, area = 0
  for (const s of slots.values()) { waste += (s.rh - s.used - (s.n - 1) * page.G) * s.w; area += s.rh * s.w }
  return area ? waste / area : 0
}

/** 상자끼리 겹침 — [[a, b]] (시험·화면 시험 공용, 맞닿음은 겹침 아님) */
export function overlaps(boxes, eps = 0.5) {
  const out = []
  for (let a = 0; a < boxes.length; a++) for (let b = a + 1; b < boxes.length; b++) {
    const A = boxes[a], B = boxes[b]
    if (A.x + A.w - eps > B.x && B.x + B.w - eps > A.x && A.y + A.h - eps > B.y && B.y + B.h - eps > A.y) out.push([a, b])
  }
  return out
}
/** 안에 있나(넘침 검사) */
export const inside = (a, frame, eps = 0.5) => a.x >= frame.x - eps && a.y >= frame.y - eps && a.x + a.w <= frame.x + frame.w + eps && a.y + a.h <= frame.y + frame.h + eps
