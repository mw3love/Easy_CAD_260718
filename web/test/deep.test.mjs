// 딥모드 지면 배치(§8 항목66 2단계 2차) — 칸 범위·줄 = 모듈(동적 계획법)·모양 바꿔 보기·쌓기·여러 장. 높이는 가짜 measure — 실제 치수는 e2e flow31
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { DEEP, deepLayout, deepWaste, graphTiles, inside, overlaps, spanRange, variantsOf } from '../src/next/deep.js'
import { DEEP_STYLES, STYLE_KEYS, recommendStyle } from '../src/next/deepstyle.js'

const load = t => JSON.parse(readFileSync(new URL(`./fixtures/deep_${t}.json`, import.meta.url), 'utf-8'))
const chars = sec => JSON.stringify(sec.body || {}).length
// 가짜 높이 — 글자 수 × 글 넓이 ÷ 폭 + 머리(폭이 좁으면 길어짐), 숫자 col = 세 배 높고 좁게, 단계 grid = 두 배
const fake = plan => (i, w, k, v) => (i < 0 ? 110 : (40 + (chars(plan.sections[i]) * 14 * 14) / w) * (v === 'col' ? 2.6 : v === 'grid' ? 1.8 : v === 'short' ? 0.7 : 1) * k)
const boxes = pg => pg.cells.map(c => ({ x: c.x, y: c.y, w: c.w, h: c.h }))

test('칸 범위 — 크기 기본 + 모양 바닥·한도', () => {
  assert.deepEqual(spanRange({ size: '주인공', shape: '주인공 글' }), [6, 8])
  assert.deepEqual(spanRange({ size: '작게', shape: '확인 문제' }), [3, 4])
  assert.deepEqual(spanRange({ size: '작게', shape: '그래프' }), [4, 6])
  assert.deepEqual(spanRange({ size: '보통', shape: '단계 카드', body: { steps: [1, 2, 3, 4, 5] } }), [8, 12])
  assert.deepEqual(spanRange({ size: '작게', shape: '출처 카드' }), [3, 4])
  assert.deepEqual(variantsOf({ shape: '숫자 타일' }), ['row', 'col'])
  assert.deepEqual(variantsOf({ shape: '용어 풀이' }), [''])
})

test('주제 셋 — 차례 그대로 · 줄마다 12칸 · 겹침 0 · 지면 안 · 높이는 내용만큼(16:9 아님)', () => {
  for (const t of ['paper', 'tx', 'news']) {
    const plan = load(t), lay = deepLayout(plan, fake(plan)), cw = DEEP.W - 2 * DEEP.M
    assert.deepEqual(lay.pages.flatMap(pg => pg.cells.map(c => c.i)), plan.sections.map((_, i) => i), t)
    for (const pg of lay.pages) {
      assert.deepEqual(overlaps(boxes(pg)), [], t)
      for (const b of boxes(pg)) assert.ok(inside(b, { x: 0, y: 0, w: pg.W, h: pg.H }), `${t} 넘침`)
      const rowsW = new Map(); for (const c of pg.cells) rowsW.set(`${c.row}:${c.slot}`, c.w)
      const byRow = new Map(); for (const [k, w] of rowsW) { const r = k.split(':')[0]; byRow.set(r, (byRow.get(r) || []).concat(w)) }
      for (const ws of byRow.values()) assert.ok(Math.abs(ws.reduce((a, b) => a + b, 0) + (ws.length - 1) * DEEP.G - cw) < 1e-6, `${t} 줄 폭`)
      assert.ok(Math.abs(pg.H - (Math.max(...pg.cells.map(c => c.top + c.rh)) + DEEP.M)) < 1e-6, t)   // 아래 = 마지막 줄 + 여백
    }
  }
})

test('줄 = 모듈 — 키 큰 꼭지 옆엔 작은 꼭지 둘을 쌓고, 숫자는 좁으면 위아래로', () => {
  const plan = { sections: [{ size: '보통', shape: '숫자 타일', body: { tiles: [1, 2, 3] } }, { size: '주인공', shape: '그래프' }, { size: '작게', shape: '확인 문제' }, { size: '작게', shape: '용어 풀이' }, { size: '보통', shape: '글' }] }
  const H = { 0: { row: 120, col: 330 }, 1: 330, 2: 150, 3: 150, 4: 160 }
  const lay = deepLayout(plan, (i, w, k, v) => (i < 0 ? 80 : typeof H[i] === 'object' ? H[i][v] : H[i]))
  const pg = lay.pages[0], c0 = pg.cells.find(c => c.i === 0)
  assert.equal(c0.v, 'col')                                                            // 그래프 옆 = 위아래로 쌓은 숫자
  assert.equal(c0.row, pg.cells.find(c => c.i === 1).row)
  assert.ok(deepWaste(pg) < 0.1)
  assert.deepEqual(overlaps(boxes(pg)), [])
})

test('아주 길면 줄 경계에서 여러 장 — 빠진 꼭지·장 겹침 없음', () => {
  const plan = load('paper'), lay = deepLayout(plan, (i, w, k, v) => fake(plan)(i, w, k, v) * (i < 0 ? 1 : 14))
  assert.ok(lay.pages.length >= 2)
  assert.deepEqual(lay.pages.flatMap(pg => pg.cells.map(c => c.i)).sort((a, b) => a - b), plan.sections.map((_, i) => i))
  for (const pg of lay.pages) assert.ok(pg.H <= DEEP.MAX_H || pg.cells.every(c => c.row === pg.cells[0].row))
  assert.deepEqual(overlaps(lay.pages.map(pg => ({ x: pg.x, y: 0, w: pg.W, h: pg.H }))), [])
})

test('디자인 묶음 넷(3-1) — 묶음 간격·여백으로 줄 폭이 맞고 겹침 0, 주인공·칸 더 주기·사용자가 정한 꼭지 모양을 지킴', () => {
  for (const s of STYLE_KEYS) for (const t of ['paper', 'tx', 'news']) {
    const plan = load(t), L = DEEP_STYLES[s].layout, P = { ...DEEP, ...L }, lay = deepLayout(plan, fake(plan), L), cw = P.W - 2 * P.M
    assert.deepEqual(lay.pages.flatMap(pg => pg.cells.map(c => c.i)), plan.sections.map((_, i) => i), `${s} ${t}`)
    for (const pg of lay.pages) {
      assert.deepEqual(overlaps(boxes(pg)), [], `${s} ${t}`)
      assert.equal(pg.head.x, P.M, `${s} 여백`)
      const ws = new Map(); for (const c of pg.cells) ws.set(`${c.row}:${c.slot}`, [c.row, c.w])
      const byRow = new Map(); for (const [r, w] of ws.values()) byRow.set(r, (byRow.get(r) || []).concat(w))
      for (const w of byRow.values()) assert.ok(Math.abs(w.reduce((a, b) => a + b, 0) + (w.length - 1) * P.G - cw) < 1e-6, `${s} ${t} 줄 폭`)
    }
  }
  assert.deepEqual(spanRange({ size: '주인공', shape: '주인공 글' }, { ...DEEP, ...DEEP_STYLES.magazine.layout }), [7, 9])
  assert.deepEqual(spanRange({ size: '보통', shape: '그래프' }, { ...DEEP, ...DEEP_STYLES.info.layout }), [5, 7])
  const plan = load('news'), ti = plan.sections.findIndex(sec => sec.shape === '숫자 타일')
  for (const v of ['row', 'col']) assert.equal(deepLayout(plan, fake(plan), { fix: { [ti]: v } }).pages.flatMap(pg => pg.cells).find(c => c.i === ti).v, v)
})

test('처음 고르기 추천(3-2) — 보고 = 신문 · 발표 = 잡지 · 숫자 꼭지 셋 이상 = 인포그래픽 · 나머지 차분', () => {
  const num = { sections: [{ shape: '그래프' }, { shape: '숫자 타일' }, { shape: '그래프' }, { shape: '글' }] }
  assert.equal(recommendStyle({ 무엇에: '보고·결정' }, num)[0], 'news')
  assert.equal(recommendStyle({ 누구에게: '윗사람(보고)' })[0], 'news')
  assert.equal(recommendStyle({ 무엇에: '발표' }, num)[0], 'magazine')
  assert.equal(recommendStyle({ 무엇에: '알아서' }, num)[0], 'info')
  assert.equal(recommendStyle({}, load('paper'))[0], 'calm')
})

test('숫자가 모자란 그래프 = 숫자 타일(3-3 실조건 — 두 점 꺾은선)', () => {
  const two = { rows: [['시점', '주민등록인구(명)'], ['2025년 12월 말', '1724856 [8]'], ['2026년 9월 말', '1716229 [1]']], header: true, kind: 'line' }
  assert.deepEqual(graphTiles(two), [['1,724,856명', '2025년 12월 말', 8], ['1,716,229명', '2026년 9월 말', 1]])
  assert.equal(graphTiles({ ...two, rows: [...two.rows, ['2027년', '1700000 [2]']] }), null)          // 셋이면 그래프 그대로
  assert.equal(graphTiles({ rows: [['연령대', '순이동(명)']], header: true }), null)                     // 숫자가 없으면 설명 카드 몫
  const multi = { rows: [['해', '수출(억 달러)', '수입(억 달러)'], ['2025', '603 [1]', '-12.5 [2]']], header: true }
  assert.deepEqual(graphTiles(multi), [['603억 달러', '2025 · 수출', 1], ['-12.5억 달러', '2025 · 수입', 2]])
  assert.equal(graphTiles({ rows: [['a', 'b', 'c', 'd'], ['x', '1', '2', '3'], ['y', '4', '5', '6']], header: true }), null)   // 타일이 넷 넘으면 그래프
})
