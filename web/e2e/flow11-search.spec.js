// 흐름 11 — 웹 검색 답 담기(§8 항목61 ② 담는 법): 종류 표시·반대로 다시 묻기·붙이면 요약 메모 + 출처 카드 + 번호 화살표 한 묶음. KAIROS는 가짜 답.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, dragScene, liveDoc, waitSaved } from './helpers.js'

const SEARCH = { content: '## KBS 소식\n- 사장 후보가 셋으로 좁혀졌어요.[1]\n- 감사에서 17건이 나왔어요.[3]', model: 'sonar-pro', elapsed: 3.4, kind: 'search',
  sources: [{ n: 1, url: 'https://news.kbs.co.kr/a', title: '사장 후보 3인', date: '2026-10-19' }, { n: 3, url: 'https://www.edaily.co.kr/b', title: '감사 17건', date: '' }] }
const CHAT = { content: '검색 없이 답하면 이래요.', model: 'fake-model', elapsed: 0.2, kind: 'chat' }

test('검색 답 → 표시·출처 → 붙이면 한 묶음(메모 + [n] 카드 둘 + 화살표 둘) → 같이 움직이고 새로고침해도 그대로 → 대화로 다시', async ({ page }) => {
  const seen = [], name = boardName('search')
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b); await r.fulfill({ json: b.kind === 'chat' ? CHAT : SEARCH }) })
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.getByPlaceholder('물어보세요', { exact: false }).click()
  await page.keyboard.type('오늘 KBS 뉴스 알려줘'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-kind')).toHaveText('🔎 웹 검색')
  await expect(page.getByTestId('answer-sources').locator('a')).toHaveCount(2)
  expect(seen[0].kind).toBeUndefined()                                   // 처음엔 서버가 짐작

  await page.getByRole('button', { name: '칠판에 붙이기' }).click()
  await expect(page.getByText('칠판에서 고른 것', { exact: false })).toHaveCount(0)   // 붙인 묶음은 고른 채로 보이되 다음 질문엔 안 실림(2026-10-19 점검)
  let d = await liveDoc(page)
  const memo = d.items.find(it => it.type === 'memo'), webs = d.items.filter(it => it.type === 'web'), arrows = d.items.filter(it => it.type === 'sarrow')
  expect(webs.map(w => w.title)).toEqual(['[1] 사장 후보 3인', '[3] 감사 17건'])   // 메모 본문의 [n]과 짝
  expect(webs.every(w => !w.frameable)).toBe(true)                       // 가벼운 제목 카드(칸 안 페이지 없음)
  const mi = d.items.indexOf(memo)
  expect(arrows.map(a => [a.bind1, a.bind2])).toEqual(webs.map(w => [mi, d.items.indexOf(w)]))
  expect(new Set([memo, ...webs, ...arrows].map(it => it.group_id)).size).toBe(1)
  expect(memo.group_id).toBeTruthy()

  // 메모를 끌면 묶음이 같이
  const p0 = webs[0].pos
  await dragScene(page, { x: memo.pos[0] + 100, y: memo.pos[1] + 30 }, { x: memo.pos[0] + 100, y: memo.pos[1] + 230 })
  d = await liveDoc(page)
  expect(d.items.find(it => it.type === 'web').pos).toEqual([p0[0], p0[1] + 200])

  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  d = await liveDoc(page)
  expect(d.items.filter(it => it.type === 'web')).toHaveLength(2)
  expect(d.items.filter(it => it.type === 'sarrow').every(a => a.bind1 != null && a.bind2 != null)).toBe(true)
  await expect(page.getByTestId('answer-sources').locator('a')).toHaveCount(2)   // 대화 기록에도 출처가 남음

  await page.getByTestId('redo-menu').click()                            // 「다시 ▾」를 펼쳐야 다른 종류가 보임
  await page.getByRole('button', { name: '대화로 다시' }).click()
  await expect(page.getByTestId('answer-kind')).toHaveText('💬 대화')
  expect(seen.at(-1).kind).toBe('chat')
  await expect(page.getByTestId('answer-sources')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '칠판에 붙이기' })).toBeVisible()   // 새 답이라 붙인 표시가 풀림
})
