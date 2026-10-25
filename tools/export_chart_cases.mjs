// 그래프 대조 시험 재료(§8 항목66 1단계) — 웹 `chart.js`가 만든 결과를 `tests/fixtures/chart_cases.json`에 적는다.
// 데스크톱 `canvas/core_chart.py`가 같은 표에서 같은 숫자·같은 조각을 내는지 `tests/test_part72_chart.py`가 비교. 웹 chart.js를 고치면 다시 돌림:
//   node tools/export_chart_cases.mjs
import { writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chartData, chartScene, chartWhys, isChart } from '../web/src/next/chart.js'

const t = (cells, chart, extra = {}) => ({ type: 'table', rows: cells.length, cols: cells[0].length, header: false, rect: [0, 0, 360, 240], cells, chart, ...extra })
const BLEU = [['번역기', 'BLEU'], ['ByteNet', '23.75'], ['GNMT + RL', '24.6'], ['ConvS2S', '25.16'], ['Transformer (big)', '28.4']]
const CASES = [
  t(BLEU, 'col'), t(BLEU, 'row'), t(BLEU, 'line'), t(BLEU, 'pie'),
  t(BLEU, 'col', { rect: [10, 20, 520, 300] }),
  t([['나라', '비중'], ['중국', '40%'], ['홍콩', '25%'], ['대만', '20%'], ['베트남', '15%']], 'pie'),
  t([['달', '2025', '2026'], ['1월', '10', '12'], ['2월', '11', '15'], ['3월', '9', '16'], ['4월', '13', '18']], 'col'),
  t([['달', '2025', '2026'], ['1월', '10', '12'], ['2월', '11', '15'], ['3월', '', '16'], ['4월', '13', '18']], 'line'),
  t([['구간', '손익'], ['1분기', '-1,200'], ['2분기', '350'], ['3분기', '2,480'], ['4분기', '-90']], 'col'),
  t([['구간', '손익'], ['1분기', '-1,200'], ['2분기', '350'], ['3분기', '2,480']], 'row'),
  t([['품목', '수출액(억 달러)'], ['메모리 반도체', '125,000'], ['시스템 반도체', '48,200'], ['디스플레이', '9,050']], 'row'),
  t([['10'], ['20'], ['15']], 'col'),
  t([['이름', '메모'], ['가', '나']], 'col'),
  t([['아주아주 긴 항목 이름입니다 정말로', '값'], ['짧은', '0.25'], ['또 다른 긴 이름의 항목', '0.5']], 'col', { header: true, rect: [0, 0, 300, 200] }),
]
const out = CASES.map(it => ({ it, data: chartData(it), whys: chartWhys(it), isChart: isChart(it), scene: chartScene(it) }))
const file = join(dirname(fileURLToPath(import.meta.url)), '..', 'tests', 'fixtures', 'chart_cases.json')
writeFileSync(file, JSON.stringify(out, null, 1) + '\n')
console.log(`${out.length}가지 → ${file}`)
