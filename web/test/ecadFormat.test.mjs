// node --test web/test — .ecad 값 변환·직각 경로 순수 함수
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { cssColor, pathD, runsToRichText } from '../src/ecadFormat.js'
import { routeAStar } from '../src/astar.js'

test('Qt ARGB 색 → CSS (불투명은 #rrggbb, 반투명은 rgba)', () => {
  assert.equal(cssColor('#ff1f1f1f'), '#1f1f1f')
  assert.equal(cssColor('#50da7756'), 'rgba(218,119,86,0.314)')
  assert.equal(cssColor('#da7756'), '#da7756')
  assert.equal(cssColor(null), null)
})

test('runs → 줄마다 문단, 부분 강조 구절만 색·굵게, 바탕 굵기는 굵은 조각에서도 유지', () => {
  const doc = runsToRichText('앞 단어를\n모든 단어를 한 번에 보자', [[6, 11, '#da7756', true]], 800)
  assert.equal(doc.content.length, 2)
  const line2 = doc.content[1].content
  assert.deepEqual(line2.map(n => n.text), ['모든 단어를 한 번에', ' 보자'])
  const hot = line2[0].marks
  assert.ok(hot.some(m => m.type === 'textStyle' && m.attrs.color === '#da7756' && m.attrs.fontWeight === '800'))
  assert.ok(line2[1].marks.some(m => m.attrs.fontWeight === '800' && m.attrs.color === null))
})

test('형광펜(runs 다섯째 값) → backgroundColor', () => {
  const doc = runsToRichText('abc', [[1, 1, null, false, '#80ffeb3b']])
  const b = doc.content[0].content[1]
  assert.equal(b.text, 'b')
  assert.equal(b.marks[0].attrs.backgroundColor, 'rgba(255,235,59,0.502)')
})

test('pathD — 닫힌 사각형만 사각형, 열린 ㄷ자·빗금은 아님', () => {
  const rect = [['M', 0, 0], ['L', 10, 0], ['L', 10, 5], ['L', 0, 5], ['L', 0, 0]]
  assert.equal(pathD(rect).isRect, true)
  assert.equal(pathD([['M', 0, 0], ['L', 0, 5], ['L', 10, 5], ['L', 10, 0]]).isRect, false)
  assert.equal(pathD([['M', 0, 8], ['L', 6, 0]]).isRect, false)
  const p = pathD([['M', 100, 50], ['C', 110, 50, 120, 60, 120, 70]])
  assert.deepEqual([p.x0, p.y0, p.w, p.h], [100, 50, 20, 20])
  assert.equal(p.d, 'M0.00,0.00 C10.00,0.00 20.00,10.00 20.00,20.00')
})

test('A* — 장애물을 피해 축정렬로, 끝은 포트에 정확히', () => {
  const obs = [{ minX: 80, maxX: 160, minY: -40, maxY: 40 }]
  const pts = routeAStar({ x: 0, y: 0 }, [1, 0], { x: 240, y: 0 }, [-1, 0], obs)
  assert.deepEqual(pts[0], { x: 0, y: 0 })
  assert.deepEqual(pts.at(-1), { x: 240, y: 0 })
  for (let i = 1; i < pts.length; i++) assert.ok(pts[i].x === pts[i - 1].x || pts[i].y === pts[i - 1].y, '대각선 없음')
  const hits = pts.some((q, i) => i && Math.min(q.x, pts[i - 1].x) < 160 && Math.max(q.x, pts[i - 1].x) > 80 && Math.min(q.y, pts[i - 1].y) < 40 && Math.max(q.y, pts[i - 1].y) > -40)
  assert.equal(hits, false, '장애물을 지나가지 않음')
})

import { cssToArgb, parseD, richTextToRuns } from '../src/ecadFormat.js'

test('CSS 색 → Qt ARGB', () => {
  assert.equal(cssToArgb('#1f1f1f'), '#ff1f1f1f')
  assert.equal(cssToArgb('rgba(218,119,86,0.314)'), '#50da7756')
  assert.equal(cssToArgb('#fff'), '#ffffffff')
  assert.equal(cssToArgb('transparent'), '#00000000')
  assert.equal(cssToArgb('var(--x)'), null)
})

test('서식 글 왕복 — runs → 서식 글 → runs가 같다(바탕 굵기 800은 조각으로 안 셈)', () => {
  const text = '앞 단어를 기다리지 말고,\n모든 단어를 한 번에 보자'
  const runs = [[15, 11, '#da7756', true], [27, 2, null, false, '#80ffeb3b']]   // 둘째 줄 「모든 단어를 한 번에」·「보자」
  for (const base of [400, 800]) {
    const back = richTextToRuns(runsToRichText(text, runs, base), base)
    assert.equal(back.text, text)
    assert.deepEqual(back.runs, runs)
  }
})

test('esym 경로 d → .ecad 요소(늘림·옮김)', () => {
  assert.deepEqual(parseD('M0.00,0.00 L100.00,50.00 C1,2 3,4 5,6', 2, 1, 10, 20),
    [['M', 10, 20], ['L', 210, 70], ['C', 12, 22, 16, 24, 20, 26]])
})
