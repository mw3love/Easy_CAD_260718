// 바깥 글 붙여넣기 모양 고르기(2026-10-21) — 짧은 한 줄 = 글자, 여러 줄·마크다운 = 메모, 탭 표 = 표
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { LINE_MAX, looksMarkdown, textKind, tsvRows } from '../src/next/clipin.js'

test('짧은 한 줄 = 글자, 긴 줄·여러 줄 = 메모, 빈 글 = 없음', () => {
  assert.equal(textKind('회의 10시'), 'line')
  assert.equal(textKind('  회의 10시\r\n'), 'line')   // 끝 줄바꿈·앞뒤 빈칸은 무시
  assert.equal(textKind('가'.repeat(LINE_MAX + 1)), 'memo')
  assert.equal(textKind('첫 줄\n둘째 줄'), 'memo')
  assert.equal(textKind(' \n '), 'empty')
})

test('마크다운 표시가 있으면 한 줄이라도 메모(제목·목록·굵게)', () => {
  assert.equal(textKind('# 오늘 할 일'), 'memo')
  assert.equal(textKind('- 견적 비교'), 'memo')
  assert.equal(textKind('**결론**만 보기'), 'memo')
  assert.ok(looksMarkdown('설명\n\n| 가 | 나 |\n|---|---|\n| 1 | 2 |'))
  assert.ok(!looksMarkdown('그냥 글 - 중간에 줄표'))
})

test('탭 표(엑셀·한글) = 칸 목록, 칸 수가 다르거나 탭 없는 줄이 있으면 표 아님', () => {
  assert.deepEqual(tsvRows('이름\t값\r\n가\t1\r\n나\t2\r\n'), [['이름', '값'], ['가', '1'], ['나', '2']])
  assert.equal(textKind('이름\t값\n가\t1'), 'tsv')
  assert.equal(tsvRows('가\t1\n나'), null)
  assert.equal(tsvRows('가\t1\n나\t2\t3'), null)
  assert.deepEqual(tsvRows('가\t나\t다'), [['가', '나', '다']])   // 한 줄도 칸이 둘 이상이면 표
})
