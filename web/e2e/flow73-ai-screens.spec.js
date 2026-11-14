// 흐름 73 — 화면 검사 6단계(AI 화면, 2026-11-10): 회의 「버리기」 = 확인 창 · 비싼 일(이 장 움직이게) = 크레딧 확인 창(취소하면 안 보냄) ·
// 질문지 탭 ← → Home End · AI 오류 = 쉬운 말(대화창·말풍선 「다시 보내기」) · 말풍선 ✕ 이름 · 답 ⋯ = 공용 메뉴. 진짜 KAIROS는 안 부름.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage, routeCall, askChat } from './helpers.js'

const models = page => page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'm', motion: 'claude-opus-5-5' } } }))

test('회의 「버리기」 = 확인 창(구간 수 · 서버 사본) — 취소하면 그대로, 버리기면 사라짐', async ({ page }) => {
  const name = boardName('meetask')
  await openBoard(page, name); await setCam(page)
  await page.evaluate(n => localStorage.setItem(`mb-meet:${n}`, JSON.stringify({ at: { x: 0, y: 0 }, s: 1, t0: Date.now(), dur: 5, segs: [{ speaker: '1', text: '하나', start_ms: 0, end_ms: 900 }, { speaker: '2', text: '둘', start_ms: 1000, end_ms: 1900 }] })), name)
  await page.reload()
  const live = page.getByTestId('meeting-live')
  await expect(live).toHaveAttribute('data-state', 'saved')
  await page.getByTestId('meeting-live-drop').click()
  const ask = page.getByTestId('meeting-drop-ask')
  await expect(ask).toContainText('받아 적은 회의를 버릴까요?'); await expect(ask).toContainText('2구간 · 서버 사본도 지워져요')
  await page.keyboard.press('Escape')
  await expect(ask).toHaveCount(0); await expect(live).toBeVisible()
  await page.getByTestId('meeting-live-drop').click(); await page.getByTestId('meeting-drop-ok').click()
  await expect(live).toHaveCount(0)
  expect(await page.evaluate(n => localStorage.getItem(`mb-meet:${n}`), name)).toBeNull()
})

test('이 장 움직이게 = 크레딧 확인 창(남은 크레딧) — 취소하면 /api/chat 안 감, 만들기면 감', async ({ page }) => {
  const seen = []
  await models(page)
  await page.route('**/api/credits', r => r.fulfill({ json: { remaining: 12345, quota: 50000 } }))
  await page.route('**/api/chat', r => { seen.push(r.request().postDataJSON()); return r.fulfill({ json: { kind: 'motion', content: '움직이게 했어요', title: '송신소', html: '<p>x</p>', steps: 1, model: 'claude-opus-5-5', elapsed: 1, credits: 300 } }) })
  await openBoard(page, boardName('costask'), { chat: true }); await setCam(page, { x: 0, y: 0, z: 0.25 })
  await page.evaluate(d => window.__mb.ed.slidesBoard(d), { title: '전파', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'] },
    { title: '송신소', layout: '글머리', bullets: ['만든다', '쏜다'] }, { title: '끝', layout: '마무리', bullets: ['b'] }] })
  const fr = (await liveDoc(page)).items.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no)[1]
  await page.keyboard.press('Escape')
  const open = async () => { const p = await toPage(page, fr.pos[0] + 6, fr.pos[1] + 6); await page.mouse.click(p.x, p.y); await page.mouse.click(p.x, p.y, { button: 'right' })
    await page.getByRole('menuitem', { name: /이 장 움직이게…/ }).click() }
  await open()
  const ask = page.getByTestId('cost-ask')
  await expect(ask).toContainText('약 270~520크레딧이 들어요'); await expect(ask).toContainText('장을 움직이게 만들어요(3~4분)')
  await expect(page.getByTestId('cost-ask-left')).toHaveText('남은 크레딧 12,345(서버 키)')
  await ask.getByRole('button', { name: '취소' }).click()
  await expect(ask).toHaveCount(0)
  await page.waitForTimeout(400); expect(seen.length).toBe(0)
  await open(); await page.getByTestId('cost-ask-ok').click()
  await expect.poll(() => seen.length).toBe(1); expect(seen[0].kind).toBe('motion')
})

test('질문지 탭 — ← → Home End로 옮김 · 지금 탭만 Tab으로 · 질문 칸 = tabpanel(그 탭 이름)', async ({ page }) => {
  await models(page)
  await page.route('**/api/chat', r => (routeCall(r.request().postDataJSON()) ? r.fulfill({ json: { kind: 'go', to: 'slides' } }) : r.fulfill({ status: 500, json: { error: 'x' } })))
  await openBoard(page, boardName('asktabs'), { chat: true })
  await askChat(page, '송신소 소개 자료 만들어 줘')
  const tabs = page.getByTestId('ask-tab')
  await expect(tabs.first()).toHaveAttribute('aria-selected', 'true')
  const n = await tabs.count()
  expect(await tabs.evaluateAll(ts => ts.map(t => t.tabIndex))).toEqual([0, ...Array(n - 1).fill(-1)])
  await tabs.first().focus(); await page.keyboard.press('ArrowRight')
  await expect(tabs.nth(1)).toBeFocused(); await expect(tabs.nth(1)).toHaveAttribute('aria-selected', 'true')
  await page.keyboard.press('End'); await expect(tabs.last()).toBeFocused(); await expect(tabs.last()).toHaveAttribute('data-tab', 'review')
  await page.keyboard.press('ArrowRight'); await expect(tabs.first()).toBeFocused()       // 끝에서 → = 처음으로
  await page.keyboard.press('ArrowLeft'); await expect(tabs.last()).toBeFocused()
  await page.keyboard.press('Home'); await expect(tabs.first()).toBeFocused()
  const panel = page.getByRole('tabpanel')
  await expect(panel).toHaveAccessibleName(await tabs.first().innerText())
})

test('AI 오류 = 쉬운 말 — 연결 끊김 · 바쁨(429), 답 ⋯ = 공용 메뉴', async ({ page }) => {
  let mode = 'ok'
  await models(page)
  await page.route('**/api/chat', r => (mode === 'down' ? r.abort('failed') : mode === 'busy' ? r.fulfill({ status: 429, json: { error: 'Error code: 429 - resource_exhausted' } })
    : r.fulfill({ json: { content: '답이에요', model: 'fake-model', elapsed: 0.1 } })))
  await openBoard(page, boardName('aierr'), { chat: true })
  await askChat(page, '안녕')
  await page.getByTestId('answer-menu').click()
  const menu = page.getByTestId('answer-menu-list')
  await expect(menu.getByRole('menuitem')).toHaveText(['↩ 여기서 이어 묻기', '⑂ 새 대화로 분기', '↻ 다시 만들기 (크레딧이 다시 들어요)', '복사'])
  await expect(menu.getByRole('menuitem').first()).toBeFocused()
  await page.keyboard.press('Escape'); await expect(menu).toHaveCount(0); await expect(page.getByTestId('answer-menu')).toBeFocused()
  mode = 'down'; await askChat(page, '끊긴 질문')
  await expect(page.getByText('서버에 연결이 안 돼요 — 인터넷을 확인하고 다시 보내 주세요')).toBeVisible()
  await expect(page.getByText('Failed to fetch')).toHaveCount(0)
  mode = 'busy'; await page.getByRole('button', { name: '질문 다시 고치기' }).click(); await page.getByPlaceholder('물어보세요', { exact: false }).press('Enter')
  await expect(page.getByText('KAIROS가 바빠요 — 잠시 뒤 다시 보내 주세요')).toBeVisible()
})

test('말풍선 — ✕ 이름 · 오류 = 쉬운 말(role=alert) + 「다시 보내기」 = 마지막 질문 다시 · 대화 칸 role=log', async ({ page }) => {
  let fail = true; const seen = []
  await models(page)
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return fail ? r.abort('failed') : r.fulfill({ json: { kind: 'bubble', content: '작은 메모예요.', model: 'fake-model', elapsed: 0.1 } }) })
  await openBoard(page, boardName('bubbleerr'), { chat: true }); await setCam(page)
  await page.evaluate(async () => { const d = window.__mb.toEcad(); d.items.push({ type: 'memo', pos: [0, 0], rect: [0, 0, 220, 40], lines: [{ k: 'p', t: '점검 메모' }] }); await window.__mb.open('data:application/json,' + encodeURIComponent(JSON.stringify(d))) })
  await setCam(page)
  const b = await page.locator('svg text', { hasText: '점검 메모' }).first().boundingBox()
  await page.mouse.click(b.x + 4, b.y + b.height / 2, { button: 'right' })
  await page.getByText('댓글…', { exact: true }).click()
  const bub = page.getByTestId('bubble')
  await expect(bub.getByRole('button', { name: '댓글 닫기' })).toBeVisible()
  await expect(bub.getByRole('log')).toHaveCount(1)
  await page.getByTestId('bubble-input').fill('@KAIROS 이게 뭐야'); await page.getByTestId('bubble-input').press('Enter')
  const err = page.getByTestId('bubble-err')
  await expect(err).toHaveAttribute('role', 'alert')
  await expect(err).toContainText('서버에 연결이 안 돼요 — 인터넷을 확인하고 다시 보내 주세요')
  fail = false; await page.getByTestId('bubble-retry').click()
  await expect(page.getByTestId('bubble-a')).toHaveText(/작은 메모예요/)
  await expect(page.getByTestId('bubble-q')).toHaveCount(1)                                     // 실패한 질문을 두 번 쌓지 않음
  expect(seen.at(-1).messages).toEqual([{ role: 'user', content: '시험: @KAIROS 이게 뭐야' }])
  await page.getByRole('button', { name: '댓글 닫기' }).click(); await expect(bub).toHaveCount(0)
})
