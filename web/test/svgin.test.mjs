// SVG → 도형 대조 — 데스크톱 `fileio/svg_import.py` 답(`tools/export_svg_cases.py`)과 svgin.js가 같은지(§8 항목63 1단계)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { svgItems, svgFits, svgPreview, looksSvg } from '../src/next/svgin.js'

const cases = JSON.parse(readFileSync(new URL('./fixtures/svg_cases.json', import.meta.url)))
const TOL = 1e-6

// 숫자는 TOL 안, 나머지(종류·글·명령 글자·닫힘)는 그대로
function close(a, b, at) {
  if (typeof a === 'number' && typeof b === 'number') return assert.ok(Math.abs(a - b) <= TOL, `${at}: ${a} vs ${b}`)
  if (Array.isArray(a) || Array.isArray(b)) {
    assert.ok(Array.isArray(a) && Array.isArray(b) && a.length === b.length, `${at}: 길이 ${JSON.stringify(a)?.slice(0, 200)} vs ${JSON.stringify(b)?.slice(0, 200)}`)
    return a.forEach((x, i) => close(x, b[i], `${at}[${i}]`))
  }
  if (a && typeof a === 'object') {
    assert.deepEqual(Object.keys(a).sort(), Object.keys(b).sort(), `${at}: 칸`)
    for (const k of Object.keys(a)) close(a[k], b[k], `${at}.${k}`)
    return
  }
  assert.equal(a, b, at)
}

test('SVG 사례마다 데스크톱과 같은 도형(손으로 쓴 것 + KAIROS가 만든 아이콘)', () => {
  assert.ok(cases.length >= 40)
  for (const c of cases) {
    const { items } = svgItems(c.svg, c.long, c.long == null ? null : { x: c.center[0], y: c.center[1] })
    close(items, c.items, c.name)
  }
})

test('끌어 놓은 SVG — 우리가 읽는 모양이면 도형, 옮기기·되풀이·그라디언트가 있으면 그림', () => {
  for (const c of cases.filter(c => c.name.startsWith('AI '))) assert.ok(svgFits(c.svg), c.name)
  assert.equal(svgFits('<svg viewBox="0 0 10 10"><g transform="translate(5 0)"><rect width="2" height="2"/></g></svg>'), false)
  assert.equal(svgFits('<svg viewBox="0 0 10 10"><defs><linearGradient id="a"/></defs><rect width="2" height="2" fill="url(#a)"/></svg>'), false)
  assert.equal(svgFits('<svg viewBox="0 0 10 10"><use href="#x"/></svg>'), false)
  assert.equal(svgFits('<svg viewBox="0 0 10 10"></svg>'), false)   // 도형 없음
})

test('숫자가 모자란 경로는 거기까지만(데스크톱은 파일 전체 실패 — 웹은 부분 성공)', () => {
  const { items } = svgItems('<svg viewBox="0 0 10 10"><path d="M1 1 L5 5 L7"/></svg>')
  assert.deepEqual(items[0].elements, [['M', 1, 1], ['L', 5, 5]])
})

test('아이콘 미리보기 = 칠판에 들어갈 도형 그대로(요소 수 같음·가는 선), SVG 코드 붙여넣기 알아보기', () => {
  for (const c of cases.filter(c => c.name.startsWith('AI '))) {
    const pv = svgPreview(c.svg), n = (pv.match(/<(line|rect|ellipse|polygon|polyline|path|text)\b/g) || []).length
    assert.equal(n, svgItems(c.svg).items.length, c.name)
    assert.ok(svgFits(pv), c.name)   // 미리보기 자체도 우리가 읽는 모양
  }
  assert.match(svgPreview('<svg viewBox="0 0 10 10"><text x="1" y="5">A&amp;B</text></svg>'), /A&amp;B/)
  assert.ok(looksSvg('<?xml version="1.0"?>\n<svg viewBox="0 0 1 1"><rect/></svg>\n'))
  assert.ok(!looksSvg('svg 코드 예: <svg></svg>'))
})
