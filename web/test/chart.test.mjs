// 그래프 = 표 + 모양(§8 항목66 1단계) — 숫자 읽기·모양 막기·그릴 조각
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { chartData, chartScene, chartWhy, chartWhys, isChart, niceTicks, numOf, fitText, textW } from '../src/next/chart.js'

const table = (cells, extra = {}) => ({ type: 'table', rows: cells.length, cols: cells[0].length, header: false, rect: [0, 0, 360, 240], cells, ...extra })
const BLEU = table([['번역기', 'BLEU'], ['ByteNet', '23.75'], ['GNMT + RL', '24.6'], ['ConvS2S', '25.16'], ['Transformer (big)', '28.4']])

test('칸 글 → 숫자: 쉼표·단위·앞 기호는 버리고, 숫자가 둘이면 못 읽음', () => {
  assert.equal(numOf('1,234'), 1234)
  assert.equal(numOf('45%'), 45)
  assert.equal(numOf('$3.5'), 3.5)
  assert.equal(numOf('약 1.2억'), 1.2)
  assert.equal(numOf('-0.5'), -0.5)
  assert.equal(numOf(' 28.4 BLEU'), 28.4)
  assert.equal(numOf('1~3'), null)
  assert.equal(numOf('2017-2022'), null)
  assert.equal(numOf(''), null)
  assert.equal(numOf('없음'), null)
})

test('첫 열 = 항목, 첫 행이 글이면 계열 이름', () => {
  const d = chartData(BLEU)
  assert.deepEqual(d.cats, ['ByteNet', 'GNMT + RL', 'ConvS2S', 'Transformer (big)'])
  assert.equal(d.series.length, 1)
  assert.equal(d.series[0].name, 'BLEU')
  assert.deepEqual(d.series[0].values, [23.75, 24.6, 25.16, 28.4])
})

test('머리 행 없이 숫자만 = 이름 없는 계열, 숫자 없는 열은 계열이 아님', () => {
  const d = chartData(table([['1월', '10', '비고'], ['2월', '12', '']]))
  assert.deepEqual(d.cats, ['1월', '2월'])
  assert.equal(d.series.length, 1)
  assert.equal(d.series[0].name, '')
})

test('% 단위는 계열 단위로', () => {
  const d = chartData(table([['나라', '비중'], ['중국', '40%'], ['미국', '35%'], ['기타', '25%']]))
  assert.equal(d.series[0].unit, '%')
})

test('원 그래프는 합쳐서 전체가 되는 몫에만 — 점수 비교는 막힘(시안의 BLEU)', () => {
  const why = chartWhys(BLEU)
  assert.equal(why.col, ''); assert.equal(why.row, ''); assert.equal(why.line, '')
  assert.match(why.pie, /몫/)
  assert.equal(chartWhys(table([['나라', '비중'], ['중국', '40'], ['미국', '60']])).pie, '')            // 이름이 「비중」
  assert.equal(chartWhys(table([['나라', '몫'], ['중국', '40%'], ['미국', '60%']])).pie, '')
  assert.equal(chartWhys(table([['나라', '수출'], ['중국', '40%'], ['미국', '60%']])).pie, '')           // 합 100인 %
  assert.match(chartWhys(table([['나라', '비중'], ['중국', '-4'], ['미국', '60']])).pie, /음수/)
  assert.match(chartWhys(table([['항목', 'A', 'B'], ['x', '1', '2'], ['y', '3', '4']])).pie, /하나/)
})

test('숫자가 없으면 모양 전부 막힘, 꺾은선은 항목 둘 이상', () => {
  const why = chartWhys(table([['이름', '메모'], ['가', '나']]))
  for (const k of ['col', 'row', 'line', 'pie']) assert.match(why[k], /숫자/)
  assert.equal(why.table, '')
  assert.match(chartWhy(chartData(table([['가', '3']])), 'line'), /둘 이상/)
})

test('isChart — 모양이 있어도 숫자를 다 지우면 표로', () => {
  assert.equal(isChart({ ...BLEU, chart: 'col' }), true)
  assert.equal(isChart(BLEU), false)
  assert.equal(isChart({ ...BLEU, chart: 'pie' }), false)                  // 안 맞는 모양 = 표로 그림
  assert.equal(isChart(table([['가', '나']], { chart: 'col' })), false)
})

test('눈금 — 0 포함·고른 간격', () => {
  assert.deepEqual(niceTicks(23.75, 28.4), [0, 10, 20, 30])
  assert.deepEqual(niceTicks(-5, 12), [-5, 0, 5, 10, 15])
  assert.deepEqual(niceTicks(0, 0), [0, 0.25, 0.5, 0.75, 1])
})

test('그릴 조각 — 세로 막대는 항목마다 막대 하나, 숫자 칸을 고치면 막대 높이가 바뀜', () => {
  const sc = chartScene({ ...BLEU, chart: 'col' }), bars = sc.filter(p => p.t === 'path')
  assert.equal(bars.length, 4)
  assert.equal(sc[0].t, 'rect')                                             // 흰 종이 카드
  const h = it => { const ys = chartScene(it).filter(p => p.t === 'path')[3].d.match(/-?\d+(\.\d+)?/g).map(Number).filter((_, i) => i % 2); return Math.max(...ys) - Math.min(...ys) }
  const big = { ...BLEU, chart: 'col', cells: BLEU.cells.map((r, i) => (i === 4 ? [r[0], '14.2'] : r)) }
  assert.ok(h(big) < h({ ...BLEU, chart: 'col' }))                          // 28.4 → 14.2 = 막대가 짧아짐
  for (const k of ['row', 'line']) assert.ok(chartScene({ ...BLEU, chart: k }).length > 6, k)
  const pie = chartScene(table([['나라', '비중'], ['중국', '40'], ['미국', '35'], ['기타', '25']], { chart: 'pie' }))
  assert.equal(pie.filter(p => p.t === 'path').length, 3)
  assert.ok(pie.some(p => p.t === 'text' && p.s === '40%'))
})

test('여러 계열 = 색 견본 머리, 막대마다 마우스 올림 글', () => {
  const sc = chartScene(table([['달', '2025', '2026'], ['1월', '10', '12'], ['2월', '11', '15']], { chart: 'col' }))
  assert.equal(sc.filter(p => p.t === 'rect' && p.w === 10).length, 2)
  assert.ok(sc.filter(p => p.t === 'path').every(p => /: /.test(p.tip)))
})

test('글 폭 어림·자르기', () => {
  assert.equal(textW('가나', 10), 20)
  assert.equal(fitText('아주 긴 항목 이름입니다', 10, 40).endsWith('…'), true)
  assert.equal(fitText('짧음', 10, 40), '짧음')
})

import { chartChoices, chartGuess } from '../src/next/chart.js'
test('기본 모양 짐작 — 비중 = 원, 시간 흐름 = 꺾은선, 긴 이름 = 가로 막대, 그 밖 세로 막대, 숫자 없음 = 없음', () => {
  assert.equal(chartGuess(BLEU), 'row')   // 「Transformer (big)」이 길어서
  assert.equal(chartGuess(table([['팀', '점수'], ['가', '3'], ['나', '5']])), 'col')
  assert.equal(chartGuess(table([['나라', '비중'], ['중국', '40%'], ['홍콩', '35%'], ['대만', '25%']])), 'pie')
  assert.equal(chartGuess(table([['연도', '매출'], ['2023', '10'], ['2024년', '12'], ['2025', '15']])), 'line')
  assert.equal(chartGuess(table([['달', '비'], ['1월', '3'], ['2월', '5'], ['3월', '4']])), 'line')
  assert.equal(chartGuess(table([['분기', '값'], ['1분기', '3'], ['2분기', '5']])), 'col')   // 둘뿐이면 막대
  assert.equal(chartGuess(table([['이름', '설명'], ['가', '좋음'], ['나', '나쁨']])), '')
  assert.deepEqual(chartChoices(table([['팀', '점수'], ['가', '3'], ['나', '5']])), ['col', 'row', 'line'])   // 원은 막힘
  assert.deepEqual(chartChoices(table([['이름', '설명'], ['가', '좋음']])), [])
})
