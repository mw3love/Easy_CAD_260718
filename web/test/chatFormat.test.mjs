// node --test web/test — KAIROS 대화창 순수 함수(§8 항목61 ⓒ)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { aiError, answerToRichText, contextText, freeSpot, nearSpot, iconName, inlineParts, parseAnswer, sourceLine } from '../src/chatFormat.js'

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
  assert.equal(doc.content[2].content[0].marks[0].attrs.color, '#6e737c')
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
  assert.deepEqual(runs.at(-1), [text.indexOf('KAIROS'), 'KAIROS · m · 10-18 12:00'.length, '#6e737c', false])
})


test('**굵게 속 `코드`**도 코드 조각 — 백틱이 글자로 남지 않음(2026-10-19)', () => {
  assert.deepEqual(inlineParts('**`pathlib`로 바꿉니다.** 끝'), [{ text: 'pathlib', bold: true, code: true }, { text: '로 바꿉니다.', bold: true }, { text: ' 끝', bold: false }])
})

import { answerTable } from '../src/chatFormat.js'
test('답 표 → 칠판 표 칸: 줄 길이 맞춤·굵게·출처 번호 뺌', () => {
  const t = answerTable([['모델', '점수'], ['**GPT**', '28.4 [1]'], ['나', '25.1[2, 3]', '덤']])
  assert.deepEqual(t.cells, [['모델', '점수', ''], ['GPT', '28.4', ''], ['나', '25.1', '덤']])
  assert.deepEqual(t.refs, [1, 2, 3])
})

test('아이콘 이름 — 요청에서 「아이콘·SVG·그려 줘」를 뗌(2026-10-27, 속성 카드 제목)', () => {
  assert.equal(iconName('안테나 아이콘 그려 줘'), '안테나')
  assert.equal(iconName('마이크 SVG로 만들어줘'), '마이크')
  assert.equal(iconName('선 그림으로 고양이 그려 줘'), '고양이')
  assert.equal(iconName('송신탑 아이콘 하나 그려줘'), '송신탑')
  assert.equal(iconName('카메라 아이콘을 그려주세요.'), '카메라')
  assert.equal(iconName('파라볼라 안테나'), '파라볼라 안테나')
  assert.equal(iconName('SVG 아이콘 만들어줘'), '')
})

test('가까운 빈자리 — 큰 묶음(발표 자료 8장)도 앞 묶음과 안 겹침(2026-11-06)', () => {
  const A = { x: 0, y: 0, w: 5120, h: 5500 }, hitA = p => p.x < A.x + A.w && p.x + 5120 > A.x && p.y < A.y + A.h && p.y + 5500 > A.y
  const p = nearSpot({ x: 2600, y: 2800 }, [A], 5120, 5500, { pad: 48, step: 96 })
  assert.equal(hitA(p), false)
  assert.deepEqual(nearSpot({ x: 100, y: 100 }, [], 50, 50), { x: 75, y: 75 })   // 빈 곳은 그 자리
})

test('AI 오류 → 쉬운 한 줄(2026-11-10 6단계)', () => {
  assert.equal(aiError(new TypeError('Failed to fetch')), '서버에 연결이 안 돼요 — 인터넷을 확인하고 다시 보내 주세요')
  assert.equal(aiError(new Error('서버 응답 502')), '서버에 연결이 안 돼요 — 인터넷을 확인하고 다시 보내 주세요')
  assert.equal(aiError(new Error('KAIROS에 요청이 너무 잦아요 — 잠시 뒤 다시 해 주세요 (Error code: 429)')), 'KAIROS가 바빠요 — 잠시 뒤 다시 보내 주세요')
  assert.equal(aiError('Error 402: insufficient credits'), '크레딧이 모자라요 — 🔑 내 키를 넣어 주세요')
  assert.equal(aiError(new Error('서버 응답 500')), '서버에서 오류가 났어요 — 다시 보내 주세요 (서버 응답 500)')
  assert.equal(aiError(new Error('🔑 내 KAIROS 키가 필요해요')), '🔑 내 KAIROS 키가 필요해요')   // 키 칸을 여는 표시라 그대로
  assert.equal(aiError(new Error('그림 파일을 못 받았어요')), '그림 파일을 못 받았어요')         // 우리가 쓴 한글은 그대로
  assert.match(aiError(new Error('x'.repeat(100))), /^KAIROS 처리 중 오류가 났어요 — 다시 보내 주세요 \(x{60}…\)$/)
})
