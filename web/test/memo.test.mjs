// 메모(§8 항목61 4-b ⑤ 1차, 2026-10-18) — 답 → 줄, 줄 ↔ 편집기 문서, 번호, 쉬운 글
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { docToLines, linesToDoc, memoBlocks, memoFromAnswer, memoText, olNumbers } from '../src/next/memo.js'

const ANS = '# 회의 정리\n\n**결론**: 로그는 `30`일.\n\n## 할 일\n- [ ] 견적 비교\n- [x] 서버 신청\n- 메모\n  - 하위 항목\n1. 첫째\n2. 둘째\n> 하루 1회\n```\nx = 1\n  y = 2\n```'

test('KAIROS 답 → 메모 줄(제목 단계·할 일·목록 깊이·번호·인용·코드, 끝에 회색 출처)', () => {
  const L = memoFromAnswer(ANS, 'KAIROS · m · 10-18 20:00')
  assert.deepEqual(L.map(l => [l.k, l.t, l.done || false, l.lv || 0]), [
    ['h1', '회의 정리', false, 0], ['p', '결론: 로그는 30일.', false, 0], ['h2', '할 일', false, 0],
    ['todo', '견적 비교', false, 0], ['todo', '서버 신청', true, 0], ['ul', '메모', false, 0], ['ul', '하위 항목', false, 1],
    ['ol', '첫째', false, 0], ['ol', '둘째', false, 0], ['quote', '하루 1회', false, 0], ['code', 'x = 1', false, 0], ['code', '  y = 2', false, 0],
    ['p', 'KAIROS · m · 10-18 20:00', false, 0]])
  assert.deepEqual(L[1].runs, [[0, 2, null, true], [8, 2, null, false, null, true]])   // 굵게·글 속 코드
  assert.deepEqual(olNumbers(L).filter(Boolean), [1, 2])
})

test('줄 ↔ 편집기 문서 왕복 — 중첩 목록·할 일 체크·코드 블록·인용·부분 서식 그대로', () => {
  const L = memoFromAnswer(ANS)
  const doc = linesToDoc(L)
  assert.deepEqual(doc.content.map(n => n.type), ['heading', 'paragraph', 'heading', 'taskList', 'bulletList', 'orderedList', 'blockquote', 'codeBlock'])
  assert.equal(doc.content[4].content[0].content[1].type, 'bulletList')   // 하위 항목 = 안쪽 목록
  assert.deepEqual(docToLines(doc), L)
})

test('블록 묶기·쉬운 글', () => {
  const L = [{ k: 'code', t: 'a' }, { k: 'code', t: 'b' }, { k: 'p', t: 'c' }, { k: 'quote', t: 'q1' }, { k: 'quote', t: 'q2' }]
  assert.deepEqual(memoBlocks(L).map(b => [b.k, b.lines.length]), [['code', 2], ['p', 1], ['quote', 2]])
  assert.equal(memoText([{ k: 'h2', t: '제목' }, { k: 'todo', t: '할 일', done: true }, { k: 'ol', t: '하나' }, { k: 'ul', t: '안', lv: 1 }]), '## 제목\n☑ 할 일\n1. 하나\n  • 안')
})

test('2차 — 끌 단위(하위 항목·코드 덩어리)·옮기기·꺼내기·전환·줄 색', async () => {
  const { convertLine, lineUnit, moveUnit, recolorLine, takeUnit } = await import('../src/next/memo.js')
  const L = [{ k: 'p', t: 'a' }, { k: 'ul', t: 'b' }, { k: 'ul', t: 'b1', lv: 1 }, { k: 'ul', t: 'b2', lv: 2 }, { k: 'ul', t: 'c' }, { k: 'code', t: 'x' }, { k: 'code', t: 'y' }]
  assert.deepEqual(lineUnit(L, 1), [1, 4]); assert.deepEqual(lineUnit(L, 2), [2, 4]); assert.deepEqual(lineUnit(L, 6), [5, 7]); assert.deepEqual(lineUnit(L, 0), [0, 1])
  assert.deepEqual(moveUnit(L, [1, 4], 0).map(l => l.t), ['b', 'b1', 'b2', 'a', 'c', 'x', 'y'])
  assert.deepEqual(moveUnit(L, [0, 1], 5).map(l => l.t), ['b', 'b1', 'b2', 'c', 'a', 'x', 'y'])
  assert.equal(moveUnit(L, [1, 4], 2), L)   // 자기 자리 안
  const { rest, unit } = takeUnit(L, [2, 4])
  assert.deepEqual(unit, [{ k: 'ul', t: 'b1' }, { k: 'ul', t: 'b2', lv: 1 }]); assert.equal(rest.length, 5)
  assert.deepEqual(convertLine({ k: 'todo', t: 't', done: true, lv: 1, runs: [[0, 1, null, true]] }, 'code'), { k: 'code', t: 't' })
  assert.deepEqual(recolorLine({ k: 'p', t: 'abc', runs: [[1, 1, null, true]] }, { color: '#d44c47' }).runs, [[0, 1, '#d44c47', false], [1, 1, '#d44c47', true], [2, 1, '#d44c47', false]])
  assert.equal(recolorLine({ k: 'p', t: 'ab', runs: [[0, 2, '#d44c47', false]] }, { color: null }).runs, undefined)
})

// 2026-10-18 손맛 2차 — 구분선(---), 고른 줄 복사 옮기기, 커서 줄(Esc = 그 줄 고르기)
import { caretLine, lineBlocks, moveRange } from '../src/next/memo.js'
import { getSchema } from '@tiptap/core'
import { EditorState, TextSelection } from '@tiptap/pm/state'
import Document from '@tiptap/extension-document'
import Paragraph from '@tiptap/extension-paragraph'
import Text from '@tiptap/extension-text'
import Heading from '@tiptap/extension-heading'
import CodeBlock from '@tiptap/extension-code-block'
import HorizontalRule from '@tiptap/extension-horizontal-rule'
import { BulletList, ListItem } from '@tiptap/extension-list'

test('구분선 --- : 답에서 읽기·편집기 문서 왕복·쉬운 글', () => {
  const L = memoFromAnswer('위\n\n---\n\n아래')
  assert.deepEqual(L.map(l => l.k), ['p', 'hr', 'p'])
  assert.deepEqual(docToLines(linesToDoc(L)), L)
  assert.equal(memoText(L).split('\n')[1], '────────')
})

test('고른 줄 옮기기·복사(Alt)', () => {
  const L = ['a', 'b', 'c', 'd'].map(t => ({ k: 'p', t }))
  assert.deepEqual(moveRange(L, [0, 2], 4).map(l => l.t), ['c', 'd', 'a', 'b'])
  assert.deepEqual(moveRange(L, [0, 2], 4, true).map(l => l.t), ['a', 'b', 'c', 'd', 'a', 'b'])
})

test('커서 줄 번호 = docToLines 차례(제목·목록·코드 여러 줄·구분선)', () => {
  const schema = getSchema([Document, Paragraph, Text, Heading, CodeBlock, HorizontalRule, BulletList, ListItem])
  const lines = [{ k: 'h1', t: '제목' }, { k: 'ul', t: '하나' }, { k: 'code', t: 'x=1' }, { k: 'code', t: 'y=2' }, { k: 'hr', t: '' }, { k: 'p', t: '끝' }]
  const doc = schema.nodeFromJSON(linesToDoc(lines))
  const at = (needle, off = 0) => { let pos = null; doc.descendants((n, p) => { if (pos == null && n.isText && n.text.includes(needle)) pos = p + n.text.indexOf(needle) + off }); return pos }
  const line = pos => caretLine(EditorState.create({ doc, selection: TextSelection.create(doc, pos) }))
  assert.equal(line(at('제목')), 0); assert.equal(line(at('하나')), 1); assert.equal(line(at('x=1')), 2); assert.equal(line(at('y=2')), 3); assert.equal(line(at('끝')), 5)
  assert.equal(lineBlocks(doc).length, lines.length)
})

// 2026-10-18 손맛 3차 — 떨어진 줄 여러 개 고르기(Ctrl·Alt+Shift 클릭)
import { moveLines, pickLines, selIdx, selUnits } from '../src/next/memo.js'
test('떨어진 줄 고르기 → 번호·옮기기·복사·떼어 내기', () => {
  const ls = { s: 3, e: 4, more: [[0, 1]] }
  assert.deepEqual(selUnits(ls), [[0, 1], [3, 4]]); assert.deepEqual(selIdx(ls), [0, 3])
  const L = ['a', 'b', 'c', 'd', 'e'].map(t => ({ k: 'p', t }))
  assert.deepEqual(moveLines(L, [0, 3], 5).map(l => l.t), ['b', 'c', 'e', 'a', 'd'])
  assert.deepEqual(moveLines(L, [0, 3], 2, true).map(l => l.t), ['a', 'b', 'a', 'd', 'c', 'd', 'e'])
  assert.deepEqual(pickLines([{ k: 'ul', t: 'x', lv: 1 }, { k: 'ul', t: 'y', lv: 2 }], [0, 1]), [{ k: 'ul', t: 'x' }, { k: 'ul', t: 'y', lv: 1 }])
})
