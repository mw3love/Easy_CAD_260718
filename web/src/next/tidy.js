// 「정리해 줘」 ② 레고형 정리정돈(§8 항목61, 2026-10-19) — 순수 계산(`npm test`). AI(서버 `board_tidy`)는 묶음 목록만, 자리는 여기서.
// 원래 자리(조각들의 바깥 상자 왼쪽 위)에서 묶음마다 프레임을 바둑판으로(묶음 수에 따라 1~3열), 프레임 안에선 조각을 크기 그대로 줄 맞춤(폭 넘으면 줄바꿈).

import { bindPt, hostPorts, nearestBorder } from './connect.js'
import { toScene } from './xform.js'

// 정리정돈 말 — 서버 `easycad/ai/board_chat.TIDY_WORDS`와 같은 글(시험 `tests/test_part62_tidy.py`가 둘을 맞춰 봄). 맞으면 칠판 조각 목록을 같이 보냄
export const TIDY_RE = /정돈|분류해|묶어\s*(줘|주세요|봐|서|놓)|모아\s*(줘|주세요|놓|서)|주제별|종류별|그룹(으로|별|지어)|끼리\s*(묶|모아)|레고/

export const TIDY = { GAP: 16, PAD: 24, FGAP: 72, NOTE_GAP: 8 }

// 한 프레임 안 — units = [{ w, h }] → { w, h(안쪽), at: [{ x, y }] }(안쪽 왼쪽 위 기준). 폭 = 가장 넓은 조각과 넓이로 정한 폭(가로가 조금 긴 덩어리) 중 큰 것
export function packUnits(units, minW = 0) {
  const { GAP } = TIDY, area = units.reduce((a, u) => a + (u.w + GAP) * (u.h + GAP), 0)
  const W = Math.max(minW, ...units.map(u => u.w), Math.sqrt(area) * 1.5)
  const at = []; let x = 0, y = 0, rowH = 0, w = 0
  for (const u of units) {
    if (x > 0 && x + u.w > W) { y += rowH + GAP; x = 0; rowH = 0 }
    at.push({ x, y }); x += u.w + GAP; rowH = Math.max(rowH, u.h); w = Math.max(w, x - GAP)
  }
  return { w: Math.max(w, minW), h: y + rowH, at }
}

// 묶음들 → 프레임 자리. sections = [{ units: [{ w, h }], noteW, noteH }] → { frames: [{ x, y, w, h, inner: { x, y }, at }], w, h }(origin 기준 칠판 좌표)
export function tidyLayout(sections, origin) {
  const { PAD, FGAP, NOTE_GAP } = TIDY
  const boxes = sections.map(s => {
    const p = packUnits(s.units, s.noteW || 0), top = s.noteH ? s.noteH + NOTE_GAP : 0
    return { w: p.w + 2 * PAD, h: top + p.h + 2 * PAD, top, at: p.at }
  })
  const n = boxes.length, cols = n <= 1 ? 1 : n <= 4 ? 2 : 3
  const colW = [], rowH = []
  boxes.forEach((b, i) => { const c = i % cols, r = Math.floor(i / cols); colW[c] = Math.max(colW[c] || 0, b.w); rowH[r] = Math.max(rowH[r] || 0, b.h) })
  const xs = colW.map((_, c) => colW.slice(0, c).reduce((a, v) => a + v + FGAP, 0)), ys = rowH.map((_, r) => rowH.slice(0, r).reduce((a, v) => a + v + FGAP, 0))
  const frames = boxes.map((b, i) => { const x = origin.x + xs[i % cols], y = origin.y + ys[Math.floor(i / cols)]
    return { x, y, w: b.w, h: b.h, note: { x: x + PAD, y: y + PAD }, inner: { x: x + PAD, y: y + PAD + b.top }, at: b.at } })
  return { frames, w: xs.at(-1) + colW.at(-1), h: ys.at(-1) + rowH.at(-1) }
}

// 정돈 뒤 직각 화살표의 붙은 변 다시 고르기 — 위아래였던 두 조각이 나란히 서면 옛 변(아래 → 위)에 붙은 채라 길이 프레임 밖으로 돌아갔음.
// 두 끝이 모두 옮긴 도형에 붙었고 두 변이 서로 마주 보지 않을 때만, 서로 가장 가까운 포트 짝으로(마주 보면 사용자가 붙인 자리 그대로).
// unitOf(도형 id → 덩어리 번호)가 같으면 그대로 — 한 덩어리는 통째로 옮겨 서로 자리가 안 바뀜(2026-10-23: 사용자가 일부러 돌려 붙인 화살표까지 바꿨음)
export function faceArrows(items, movedIds, rectOf, unitOf = null) {
  const byId = new Map(items.map(it => [it._id, it])), moved = new Set(movedIds)
  const toward = (e, q) => e.n.x * (q.x - e.p.x) + e.n.y * (q.y - e.p.y) > 1e-6
  return items.map(it => {
    if (it.type !== 'sarrow' || it.bind1_group || it.bind2_group || !it.bind1_pt || !it.bind2_pt) return it
    const h1 = byId.get(it._bind1), h2 = byId.get(it._bind2)
    if (!h1 || !h2 || h1 === h2 || !moved.has(h1._id) || !moved.has(h2._id)) return it
    if (unitOf && unitOf.has(h1._id) && unitOf.get(h1._id) === unitOf.get(h2._id)) return it
    const e1 = { p: toScene(h1, { x: it.bind1_pt[0], y: it.bind1_pt[1] }) }, e2 = { p: toScene(h2, { x: it.bind2_pt[0], y: it.bind2_pt[1] }) }
    e1.n = nearestBorder(h1, e1.p, rectOf).n; e2.n = nearestBorder(h2, e2.p, rectOf).n
    if (toward(e1, e2.p) && toward(e2, e1.p)) return it
    let best = null, bd = Infinity
    for (const a of hostPorts(h1, rectOf)) for (const b of hostPorts(h2, rectOf)) {
      if (!toward(a, b.p) || !toward(b, a.p)) continue
      const d = Math.hypot(a.p.x - b.p.x, a.p.y - b.p.y); if (d < bd) { bd = d; best = [a.p, b.p] }
    }
    return best ? { ...it, bind1_pt: bindPt(h1, best[0]), bind2_pt: bindPt(h2, best[1]) } : it
  })
}

// 바둑판이 다른 것과 겹치면 아래로 비킴(원래 자리에서 가장 가까운 아래) — boxes = 안 옮기는 것들의 칠판 상자
export function clearSpot(origin, w, h, boxes, gap = TIDY.FGAP) {
  let y = origin.y
  for (let k = 0; k < 50; k++) {
    const hit = boxes.filter(b => origin.x < b.x + b.w && b.x < origin.x + w && y < b.y + b.h && b.y < y + h)
    if (!hit.length) break
    y = Math.max(...hit.map(b => b.y + b.h)) + gap
  }
  return { x: origin.x, y }
}
