// node --test web/test — KAIROS 대화창 순수 함수(§8 항목61 ⓒ)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { answerToRichText, contextText, freeSpot, inlineParts, parseAnswer, sourceLine } from '../src/chatFormat.js'

test('답 글 읽기 — 표(| 가 | 나 |): 붙은 줄 한 덩어리, |---| 이면 첫 줄 머리글(2026-10-20)', () => {
  const ln = parseAnswer('날씨 요약\n| 항목 | 내일 |\n|---|:---:|\n| 기온 | **9~18℃** |\n| 오전 | 비 |\n\n끝')
  assert.deepEqual(ln.map(l => l.kind), ['p', 'table', 'gap', 'p'])
  assert.deepEqual(ln[1], { kind: 'table', header: true, rows: [['항목', '내일'], ['기온', '**9~18℃**'], ['오전', '비']] })
  assert.equal(parseAnswer('| a | b |\n| c | d |')[0].header, false)   // 구분 줄 없으면 머리글 아님
  assert.equal(parseAnswer('a | b')[0].kind, 'p')                       // 양 끝 | 가 없으면 글
})

test('답 글 읽기 — 제목·목록·굵게·빈 줄 한 칸·코드펜스 줄 뺌', () => {
  const ln = parseAnswer('## 결론\n\n\n**PTP**는 시계 규약이다.\n- 하나\n2. 둘\n```\ncode\n```\n')
  assert.deepEqual(ln.map(l => l.kind), ['h', 'gap', 'p', 'li', 'li', 'code'])
  assert.deepEqual(ln[2].parts, [{ text: 'PTP', bold: true }, { text: '는 시계 규약이다.', bold: false }])
  assert.equal(ln[3].mark, '•')
  assert.equal(ln[4].mark, '2.')
})

test('카드 글 — 굵게는 bold 표시, 목록은 앞에 표, 끝에 회색 출처 줄', () => {
  const doc = answerToRichText('# 제목\n- **가**나', 'KAIROS · m · 10-17 14:02')
  assert.equal(doc.content.length, 3)
  assert.deepEqual(doc.content[0].content[0].marks, [{ type: 'bold' }])
  assert.deepEqual(doc.content[1].content.map(n => n.text), ['• ', '가', '나'])
  assert.deepEqual(doc.content[1].content[1].marks, [{ type: 'bold' }])
  assert.equal(doc.content[2].content[0].marks[0].attrs.color, '#8a8f98')
  assert.equal(answerToRichText('').content.length, 1)   // 빈 답도 문서 모양은 지킨다
})

test('출처 줄 시각', () => {
  assert.equal(sourceLine('gpt-6.1-sol', new Date(2026, 9, 17, 9, 5).getTime()), 'KAIROS · gpt-6.1-sol · 10-17 09:05')
})

test('빈자리 — 빈 화면은 왼쪽 위, 막힌 곳은 피함, 화면이 꽉 차면 모든 것의 오른쪽', () => {
  const view = { x: 0, y: 0, w: 1000, h: 800 }
  assert.deepEqual(freeSpot(view, [], 300, 200), { x: 24, y: 24 })
  const p = freeSpot(view, [{ x: 0, y: 0, w: 400, h: 300 }], 300, 200)
  assert.ok(p.x >= 400 + 12 || p.y >= 300 + 12, JSON.stringify(p))
  const full = freeSpot(view, [{ x: -50, y: -50, w: 1100, h: 900 }], 300, 200)
  assert.equal(full.x, 1050 + 48)
})

test('고른 것 글 — 빈 것·겹친 것 빼고 줄마다 하나', () => {
  assert.equal(contextText(['가\n나', '', '가\n나', ' 다 ']), '- 가 / 나\n- 다')
})

import { answerToEcadText } from '../src/chatFormat.js'

test('answerToEcadText — 굵게·제목·목록·출처 줄이 .ecad runs로', () => {
  const { text, runs } = answerToEcadText('# 제목\n\n- **핵심** 하나\n보통', 'KAIROS · m · 10-18 12:00')
  assert.equal(text, '제목\n\n• 핵심 하나\n보통\nKAIROS · m · 10-18 12:00')
  assert.deepEqual(runs[0], [0, 2, null, true])                     // 제목 = 굵게
  assert.deepEqual(runs[1], [text.indexOf('핵심'), 2, null, true])   // **핵심**
  assert.deepEqual(runs.at(-1), [text.indexOf('KAIROS'), 'KAIROS · m · 10-18 12:00'.length, '#8a8f98', false])
})


test('**굵게 속 `코드`**도 코드 조각 — 백틱이 글자로 남지 않음(2026-10-19)', () => {
  assert.deepEqual(inlineParts('**`pathlib`로 바꿉니다.** 끝'), [{ text: 'pathlib', bold: true, code: true }, { text: '로 바꿉니다.', bold: true }, { text: ' 끝', bold: false }])
})
