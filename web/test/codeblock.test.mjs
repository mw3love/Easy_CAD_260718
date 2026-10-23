// 코드 블록(§8 항목61 4-b ③, 2026-10-18 사용자: 카드 안에) — AI 답의 코드 줄 = 고정폭 조각(.ecad runs 여섯째 칸), 들여쓰기 유지
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { answerToEcadText } from '../src/chatFormat.js'
import { richTextToRuns, runsToRichText } from '../src/ecadFormat.js'
import { runsToLines } from '../src/next/geom.js'

test('답의 코드 줄 → 고정폭 조각(들여쓰기·빈 줄 그대로, 탭은 띄어쓰기 넷)', () => {
  const { text, runs } = answerToEcadText('합 구하기:\n```python\ndef add(a, b):\n\n\treturn a + b\n```\n끝')
  assert.equal(text, '합 구하기:\ndef add(a, b):\n \n    return a + b\n끝')
  const mono = runs.filter(r => r[5] === true).map(([s, n]) => text.slice(s, s + n))
  assert.deepEqual(mono, ['def add(a, b):', ' ', '    return a + b'])
  const lines = runsToLines(text, runs)
  assert.ok(lines[1].every(p => p.mono) && lines[3][0].text === '    return a + b' && !lines[0][0].mono)
})

test('고정폭 조각 ↔ 편집기(TipTap code 표시) 왕복', () => {
  const runs = [[0, 3, '#ff0000', true], [3, 7, null, false, null, true]]   // 'abc' 빨강 굵게 + '  x = 1' 코드(앞 띄어쓰기 포함)
  const doc = runsToRichText('abc  x = 1', runs)
  assert.deepEqual(doc.content[0].content.map(n => n.marks?.map(m => m.type)), [['bold', 'textStyle'], ['code']])
  const back = richTextToRuns(doc)
  assert.equal(back.text, 'abc  x = 1')
  assert.deepEqual(back.runs, runs)
})

test('코드 + 굵게·색·형광펜·기울임이 같이 있어도 편집기 왕복에 안 빠짐(2026-10-23 — 전엔 코드면 나머지를 뗌)', () => {
  const runs = [[0, 3, '#ff0000', true, '#99ffd54f', true, 'i']]
  const doc = runsToRichText('abc', runs)
  assert.deepEqual(doc.content[0].content[0].marks.map(m => m.type).sort(), ['bold', 'code', 'italic', 'textStyle'])
  assert.deepEqual(richTextToRuns(doc).runs, runs)
})

test('글 속 `코드` = 고정폭 조각(따옴표는 뺌), 줄 바탕은 코드만 있는 줄에만', () => {
  const { text, runs } = answerToEcadText('이렇게 부르면 `3`이 나와요.\n`npm test`')
  assert.equal(text, '이렇게 부르면 3이 나와요.\nnpm test')
  const lines = runsToLines(text, runs)
  assert.deepEqual(lines[0].map(p => [p.text, !!p.mono]), [['이렇게 부르면 ', false], ['3', true], ['이 나와요.', false]])
  assert.ok(lines[1].every(p => p.mono))
})
