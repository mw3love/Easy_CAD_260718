// 딥모드 지면 배치(§8 항목66 2단계, 2026-10-25) — 편집장 계획(꼭지 목록)을 16:9 프레임 안 12칸 격자에 놓는 순수 계산.
// 데스크톱 `host_blocks.py`(§8 항목57~60)의 줄 맞춤·한 장 채우기를 줄여 옮김: AI는 꼭지의 모양·크기(주인공·보통·작게)만, 칸 수·자리는 앱이.
// 꼭지 높이는 재는 함수(measure)를 받음 — 브라우저는 실제로 만든 물건 치수(deepboard.js), 시험은 가짜. 줄 높이 = 그 줄에서 가장 큰 꼭지
// (시안이 줄 높이를 고정값으로 박아 글이 아래 줄을 덮었음 — 사용자 판정). 넘치면 간격·본문 → 폭(16:9 그대로 넓힘) → 그다음에만 여러 장.

export const DEEP = {
  W: [1600, 1920, 2240],    // 프레임 폭 차례(넓혀도 16:9 — 발표 화면에 맞춰 줄면 글이 작아지니 2240까지)
  M: 48,                    // 프레임 안 바깥 여백
  FIT: [[16, 1], [12, 0.92], [10, 0.85]],   // 한 장 채우기 차례 — (칸 사이, 본문 배율): 간격부터, 본문은 한 단계씩(데스크톱 `_BB_FIT_STEPS`와 같은 1 → 0.92 → 0.85 — 메모 본문 14px가 1600 폭 지면 바닥)
  HEAD_GAP: 20,             // 머리(제목·헤드라인) 아래
  PAGE_GAP: 240,            // 여러 장일 때 프레임 사이
}
export const ASPECT = 9 / 16

/** 꼭지 칸 수(12칸 중) — 크기 기본(주인공 6 · 보통 4 · 작게 3) + 모양마다 바닥(그래프는 360px 아래로 안 좁게, 단계는 가로로 늘어놓으니 넓게) */
export function deepSpan(sec) {
  const size = sec.size, shape = sec.shape, b = sec.body || {}
  let span = size === '주인공' ? 6 : size === '작게' ? 3 : 4
  if (shape === '그래프') span = Math.max(span, size === '주인공' ? 8 : 4)
  if (shape === '단계 카드') span = Math.max(span, (b.steps?.length || 4) >= 5 ? 8 : 6)
  if (shape === '표') span = Math.max(span, 5)
  if (shape === '숫자 타일') span = Math.max(span, (b.tiles?.length || 3) >= 3 ? 4 : 3)
  return Math.min(12, span)
}

/** 줄 짜기 — 계획 차례 그대로 12칸을 넘으면 다음 줄, 모자란 줄은 비율대로 늘려 12칸을 채움(빈 구멍 없이 신문처럼). [[{ i, span }]] */
export function deepRows(sections) {
  const rows = []
  let cur = [], used = 0
  sections.forEach((sec, i) => {
    const span = deepSpan(sec)
    if (cur.length && used + span > 12) { rows.push(cur); cur = []; used = 0 }
    cur.push({ i, span }); used += span
  })
  if (cur.length) rows.push(cur)
  return rows.map(row => { const sum = row.reduce((a, c) => a + c.span, 0); return row.map(c => ({ ...c, span: (c.span * 12) / sum })) })
}

// 한 번 놓기 — 프레임 왼쪽 위 (0,0) 기준. measure(i, w, k) = 꼭지 i를 폭 w·본문 배율 k로 만들었을 때 높이, i = -1이면 머리
function place(rows, measure, W, fit, page) {
  const [G, k] = DEEP.FIT[fit], M = DEEP.M, cw = W - 2 * M, col = (cw - 11 * G) / 12
  const headH = measure(-1, cw, k, page)
  let y = M + headH + DEEP.HEAD_GAP
  const cells = []
  for (const row of rows) {
    let x = M, rh = 0
    for (const { i, span } of row) {
      const w = span * col + (span - 1) * G, h = measure(i, w, k)
      cells.push({ i, x, y, w, h }); x += w + G; rh = Math.max(rh, h)
    }
    y += rh + G
  }
  const need = y - G + M
  return { W, H: Math.max(need, W * ASPECT), need, fit, k, G, head: { x: M, y: M, w: cw, h: headH }, cells }
}

// 벽돌 쌓기(예비 — 데스크톱 `_bb_masonry`와 같은 생각) — 줄은 그대로 짜되, 꼭지마다 12칸 중 지금 가장 낮은 자리(같으면 줄에서 정한 자리 가까이).
// 줄 맞춤에선 키 큰 꼭지 옆이 비어 한 장이 안 되던 것(시사 — 숫자 타일 옆 그래프)을 위로 끌어올림. 칸 수는 줄 맞춤 칸을 정수로(합 12)
function intSpans(row) {
  const fl = row.map(c => Math.floor(c.span + 1e-9)), rest = 12 - fl.reduce((a, b) => a + b, 0)
  row.map((c, j) => [c.span - fl[j], j]).sort((a, b) => b[0] - a[0]).slice(0, rest).forEach(([, j]) => fl[j]++)
  return fl
}
function placeMasonry(rows, measure, W, fit, page) {
  const [G, k] = DEEP.FIT[fit], M = DEEP.M, cw = W - 2 * M, col = (cw - 11 * G) / 12
  const headH = measure(-1, cw, k, page), top = M + headH + DEEP.HEAD_GAP, sky = Array(12).fill(top), cells = []
  for (const row of rows) {
    let want = 0
    intSpans(row).forEach((s, j) => {
      let c0 = 0, best = Infinity
      for (let c = 0; c + s <= 12; c++) { const y = Math.max(...sky.slice(c, c + s)), score = y * 1e3 + Math.abs(c - want); if (score < best) { best = score; c0 = c } }
      const y = Math.max(...sky.slice(c0, c0 + s)), w = s * col + (s - 1) * G, h = measure(row[j].i, w, k)
      cells.push({ i: row[j].i, x: M + c0 * (col + G), y, w, h })
      for (let c = c0; c < c0 + s; c++) sky[c] = y + h + G
      want += s
    })
  }
  const need = Math.max(...sky) - G + M
  return { W, H: Math.max(need, W * ASPECT), need, fit, k, G, head: { x: M, y: M, w: cw, h: headH }, cells, masonry: true }
}

/** 지면 짜기 — 한 장에 들어가는 첫 (폭, 조임)을 줄 맞춤으로 찾고, 안 되면 벽돌 쌓기로, 어디서도 안 되면 첫 폭·가장 조인 차례로 줄 단위로 여러 장.
 *  반환 { pages: [{ x, W, H, head, cells, k, G, fit, masonry? }], rows } — 장 x = 왼쪽 위(장끼리 옆으로), 칸 좌표는 그 장 안 */
export function deepLayout(plan, measure) {
  const rows = deepRows(plan.sections || [])
  for (const lay of [place, placeMasonry]) for (const W of DEEP.W) for (let f = 0; f < DEEP.FIT.length; f++) {
    const p = lay(rows, measure, W, f, 0)
    if (p.need <= W * ASPECT + 0.5) return { rows, pages: [{ ...p, x: 0, H: W * ASPECT }] }
  }
  // 여러 장 — 첫 폭·가장 조인 차례로, 줄을 차례로 담다가 넘치면 다음 장(줄 하나가 한 장보다 크면 그 장만 길어짐 — 넘침 대신 늘어남)
  const W = DEEP.W[0], F = DEEP.FIT.length - 1, pages = []
  let take = []
  const flush = () => { if (!take.length) return; const p = place(take, measure, W, F, pages.length); pages.push({ ...p, x: pages.length * (W + DEEP.PAGE_GAP) }); take = [] }
  for (const row of rows) {
    if (take.length && place([...take, row], measure, W, F, pages.length).need > W * ASPECT + 0.5) flush()
    take.push(row)
  }
  flush()
  return { rows, pages }
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
