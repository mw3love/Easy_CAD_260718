// 범례(§8 항목61 4-b ④, 2026-10-18) — 선 종류 모으기·색 이름·만들기·다시 모으기(이름 지킴)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { buildLegend, colorName, defaultName, legendEntries, legendState } from '../src/next/legend.js'

const L = (pen, width = 2, style = 1, extra = {}) => ({ type: 'line', line: [0, 0, 10, 0], pen, width, style, ...extra })
let n = 0
const mk = x => ({ _id: 'x' + ++n, scale: 1, rotation: 0, ...x })

test('색 + 모양 + 굵기가 같은 것끼리 한 줄, 많이 쓴 순서 — 투명·채운 도형·판서·범례 자신은 뺌', () => {
  const items = [L('#ffff7f00', 2.9), L('#ffff7f00', 2.94), L('#ff000000', 0.3), L('#ff000000', 0.3, 2),
    { type: 'sarrow', pts: [[0, 0], [5, 5]], color: '#ff0000ff', width: 2, style: 1 },
    L('#00000000'), { type: 'polygon', pts: [], closed: true, fill: '#ffffffff', pen: '#ffff0000', width: 1 },
    L('#ff00ff00', 2, 1, { layer_id: 'pen-notes' }), L('#ffff7f00', 2.9, 1, { legend_key: 'k' }), { type: 'rect', pen: '#ff123456', width: 1 }]
  const es = legendEntries(items)
  assert.deepEqual(es.map(e => [e.color, e.style, e.width, e.count]), [['#ffff7f00', 1, 2.9, 2], ['#ff000000', 1, 0.3, 1], ['#ff000000', 2, 0.3, 1], ['#ff0000ff', 1, 2, 1]])
  assert.equal(es[3].arrow, true)
})

test('색 이름(쉬운 말)·처음 이름', () => {
  assert.deepEqual(['#ffff7f00', '#ff000000', '#ffffffff', '#ffbfbfbf', '#ff00ffff', '#ff0000ff', '#ffff00ff', '#ff00ff00', '#ffff0000'].map(colorName),
    ['주황', '검정', '흰색', '회색', '하늘', '파랑', '자홍', '초록', '빨강'])
  assert.equal(defaultName({ color: '#ff000000', style: 3, width: 0.3 }), '검정 · 점선 · 0.3px')
})

test('만들기 = 틀 + 제목 + 줄마다 견본 선·이름(한 묶음), 다시 모으면 적어 둔 이름·자리·크기 그대로', () => {
  const es = legendEntries([L('#ffff7f00', 2.9), L('#ffff7f00', 2.9), L('#ff00ffff', 2.9, 2)])   // 주황 2번 = 첫 줄
  const its = buildLegend(es, { x: 100, y: 50 }, 2, null, mk, 7)
  assert.equal(its.length, 2 + 2 * 2)
  assert.equal(new Set(its.map(i => i.group_id)).size, 1)
  const [frame, , line0, text0] = its
  assert.deepEqual(frame.pos, [100, 50]); assert.equal(frame.legend, 2); assert.equal(frame.z, 7)
  assert.equal(line0.pen, '#ffff7f00'); assert.equal(line0.width, 2.9); assert.equal(text0.text, '주황 · 실선 · 2.9px')
  const edited = its.map(i => (i === text0 ? { ...i, text: 'SDI 케이블' } : i))
  const st = legendState(edited, frame.group_id)
  assert.deepEqual(st.at, { x: 100, y: 50 }); assert.equal(st.scale, 2)
  const again = buildLegend(legendEntries([L('#ff00ffff', 2.9, 2), L('#ffff7f00', 2.9), L('#ffff7f00', 2.9), L('#ffff0000', 1)]), st.at, st.scale, st.names, mk)
  assert.deepEqual(again.filter(i => i.type === 'text' && i.legend_key).map(i => i.text), ['SDI 케이블', '하늘 · 파선 · 2.9px', '빨강 · 실선 · 1px'])
})

test('어두운 주황 = 갈색, 처음 이름이 겹치면 색 코드를 붙여 구별', () => {
  assert.equal(colorName('#ffcd6928'), '갈색')
  const its = buildLegend(legendEntries([L('#ffff0000', 2), L('#ffee1111', 2)]), { x: 0, y: 0 }, 1, null, mk)
  assert.deepEqual(its.filter(i => i.type === 'text' && i.legend_key).map(i => i.text), ['빨강 · 실선 · 2px #ee1111', '빨강 · 실선 · 2px #ff0000'])
})
