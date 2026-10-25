// 딥모드 지면 배치(§8 항목66 2단계) — 칸 수·줄 짜기·한 장 채우기·여러 장. 높이는 가짜 measure(글 길이 ÷ 폭) — 실제 치수는 e2e flow31
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { ASPECT, DEEP, deepLayout, deepRows, deepSpan, inside, overlaps } from '../src/next/deep.js'

const load = t => JSON.parse(readFileSync(new URL(`./fixtures/deep_${t}.json`, import.meta.url), 'utf-8'))
const chars = sec => JSON.stringify(sec.body || {}).length
// 가짜 높이 — 글자 수 × 글 넓이 ÷ 폭 + 머리, 본문 배율 k에 비례(폭이 좁으면 길어짐)
const fake = (plan, mul = 1) => (i, w, k) => (i < 0 ? 110 * k : (40 + (chars(plan.sections[i]) * 14 * 14) / w) * k * mul)
const boxes = pg => pg.cells.map(c => ({ x: c.x, y: c.y, w: c.w, h: c.h }))

test('칸 수 — 크기 기본 + 모양 바닥', () => {
  assert.equal(deepSpan({ size: '주인공', shape: '주인공 글' }), 6)
  assert.equal(deepSpan({ size: '작게', shape: '확인 문제' }), 3)
  assert.equal(deepSpan({ size: '작게', shape: '그래프' }), 4)
  assert.equal(deepSpan({ size: '주인공', shape: '그래프' }), 8)
  assert.equal(deepSpan({ size: '보통', shape: '단계 카드', body: { steps: [1, 2, 3, 4, 5] } }), 8)
  assert.equal(deepSpan({ size: '보통', shape: '표' }), 5)
})

test('줄 — 차례 그대로, 줄마다 12칸을 꽉 채움', () => {
  for (const t of ['paper', 'tx', 'news']) {
    const rows = deepRows(load(t).sections)
    assert.deepEqual(rows.flat().map(c => c.i), load(t).sections.map((_, i) => i), t)
    for (const r of rows) assert.ok(Math.abs(r.reduce((a, c) => a + c.span, 0) - 12) < 1e-9, t)
  }
})

test('주제 셋 — 겹침 0 · 프레임 밖 0 · 줄 높이 = 그 줄 가장 큰 꼭지 · 16:9', () => {
  for (const t of ['paper', 'tx', 'news']) {
    const plan = load(t), lay = deepLayout(plan, fake(plan))
    for (const pg of lay.pages) {
      assert.deepEqual(overlaps(boxes(pg)), [], t)
      for (const b of boxes(pg)) assert.ok(inside(b, { x: 0, y: 0, w: pg.W, h: pg.H }), `${t} 넘침`)
      assert.ok(Math.abs(pg.H - pg.W * ASPECT) < 1 || pg.need > pg.W * ASPECT, t)
      const ys = [...new Set(pg.cells.map(c => c.y))].sort((a, b) => a - b)   // 다음 줄 위 = 앞 줄 가장 큰 꼭지 아래 + 칸 사이
      ys.slice(1).forEach((y, r) => { const prev = pg.cells.filter(c => c.y === ys[r]); assert.ok(Math.abs(y - (ys[r] + Math.max(...prev.map(c => c.h)) + pg.G)) < 1e-6, t) })
    }
  }
})

test('한 장 채우기 — 넘치면 간격·본문부터, 그다음 폭, 그래도 안 되면 여러 장(겹침 없이 옆으로)', () => {
  const plan = load('paper')
  assert.equal(deepLayout(plan, fake(plan, 0.5)).pages[0].fit, 0)                    // 넉넉 = 조이지 않음
  let lay = deepLayout(plan, fake(plan, 2))
  assert.equal(lay.pages.length, 1)
  assert.ok(lay.pages[0].fit > 0 || lay.pages[0].W > DEEP.W[0])                      // 조이거나 넓혀서 한 장
  lay = deepLayout(plan, fake(plan, 6))                                               // 아주 많음 = 여러 장
  assert.ok(lay.pages.length >= 2)
  assert.deepEqual(lay.pages.flatMap(pg => pg.cells.map(c => c.i)).sort((a, b) => a - b), plan.sections.map((_, i) => i))   // 빠진 꼭지 없음
  assert.deepEqual(overlaps(lay.pages.map(pg => ({ x: pg.x, y: 0, w: pg.W, h: pg.H }))), [])
})

test('벽돌 쌓기 — 줄 맞춤이 어디서도 안 될 때만, 겹침 없이 키 큰 꼭지 옆을 채움', () => {
  const plan = { sections: [{ size: '보통', shape: '숫자 타일' }, { size: '주인공', shape: '그래프' }, { size: '보통', shape: '글' }, { size: '보통', shape: '글' }, { size: '보통', shape: '글' }] }
  const H = [100, 1100, 300, 300, 300]   // 그래프만 아주 큼 — 줄 맞춤이면 둘째 줄이 그래프 밑으로
  const lay = deepLayout(plan, (i, w, k) => (i < 0 ? 80 : H[i] * k))
  const pg = lay.pages[0]
  assert.equal(lay.pages.length, 1)
  assert.ok(pg.masonry)
  assert.deepEqual(overlaps(boxes(pg)), [])
  for (const b of boxes(pg)) assert.ok(inside(b, { x: 0, y: 0, w: pg.W, h: pg.H }))
  assert.ok(pg.cells.find(c => c.i === 2).y < pg.cells.find(c => c.i === 1).y + pg.cells.find(c => c.i === 1).h)   // 셋째 꼭지가 그래프 옆으로 올라옴
})
