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
