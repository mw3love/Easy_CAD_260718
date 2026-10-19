// 범례(§8 항목61 4-b ④, 2026-10-18) — 선 종류 모으기·색 이름·만들기·다시 모으기(이름 지킴)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { colorName, legendEntries, restyleLegendRow, syncLegends } from '../src/next/legend.js'

const L = (pen, width = 2, style = 1, extra = {}) => ({ type: 'line', line: [0, 0, 10, 0], pen, width, style, ...extra })

test('색 + 모양 + 굵기가 같은 것끼리 한 줄, 많이 쓴 순서 — 투명·채운 도형·판서·범례 자신은 뺌', () => {
  const items = [L('#ffff7f00', 2.9), L('#ffff7f00', 2.94), L('#ff000000', 0.3), L('#ff000000', 0.3, 2),
    { type: 'sarrow', pts: [[0, 0], [5, 5]], color: '#ff0000ff', width: 2, style: 1 },
    L('#00000000'), { type: 'polygon', pts: [], closed: true, fill: '#ffffffff', pen: '#ffff0000', width: 1 },
    L('#ff00ff00', 2, 1, { layer_id: 'pen-notes' }), L('#ffff7f00', 2.9, 1, { legend_key: 'k' }), { type: 'rect', pen: '#ff123456', width: 1 }]
  const es = legendEntries(items)
  assert.deepEqual(es.map(e => [e.color, e.style, e.width, e.count]), [['#ffff7f00', 1, 2.9, 2], ['#ff000000', 1, 0.3, 1], ['#ff000000', 2, 0.3, 1], ['#ff0000ff', 1, 2, 1]])
  assert.equal(es[3].arrow, true)
})

test('색 이름(쉬운 말)', () => {
  assert.deepEqual(['#ffff7f00', '#ff000000', '#ffffffff', '#ffbfbfbf', '#ff00ffff', '#ff0000ff', '#ffff00ff', '#ff00ff00', '#ffff0000'].map(colorName),
    ['주황', '검정', '흰색', '회색', '하늘', '파랑', '자홍', '초록', '빨강'])
})

test('어두운 주황 = 갈색', () => {
  assert.equal(colorName('#ffcd6928'), '갈색')
})

test('범례 2판 — 저장 길목에서 줄을 도면에 맞춤(바뀐 게 없으면 같은 아이템 그대로)', () => {
  const ln = { _id: 'a', type: 'line', line: [0, 0, 10, 0], pen: '#ffff0000', width: 2, style: 1 }
  const lg = { _id: 'L', type: 'legend', rect: [0, 0, 10, 10], rows: [], names: {} }
  const out = syncLegends([ln, lg]), L = out.find(i => i._id === 'L')
  assert.deepEqual(L.rows.map(r => r.key), ['ffff0000|1|2'])
  const again = syncLegends(out); assert.equal(again[1], L)   // 같으면 새로 안 만듦(저장할 것도 없음)
  assert.equal(syncLegends([ln])[0], ln)   // 범례가 없으면 손대지 않음
})

test('범례 줄 일괄 바꾸기 — 그 선 전부(화살표는 color, 선은 pen), 적어 둔 이름은 새 열쇠로', () => {
  const items = [
    { _id: 'a', type: 'line', pen: '#ffff0000', width: 2, style: 1 },
    { _id: 'b', type: 'sarrow', color: '#ffff0000', width: 2, style: 1 },
    { _id: 'c', type: 'line', pen: '#ff0000ff', width: 2, style: 1 },
    { _id: 'L', type: 'legend', names: { 'ffff0000|1|2': '전원' } }]
  const out = restyleLegendRow(items, 'ffff0000|1|2', { width: 5, style: 2 })
  assert.deepEqual(out.slice(0, 3).map(i => [i.width, i.style]), [[5, 2], [5, 2], [2, 1]])
  assert.deepEqual(out[3].names, { 'ffff0000|2|5': '전원' })
  const col = restyleLegendRow(items, 'ffff0000|1|2', { color: '#ff00ff00' })
  assert.deepEqual([col[0].pen, col[1].color], ['#ff00ff00', '#ff00ff00'])
})
