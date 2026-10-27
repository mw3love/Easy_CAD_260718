// 흐름 3 — KAIROS 묻고 칠판에 붙이기. 진짜 KAIROS는 부르지 않는다(크레딧·답이 매번 다름) — /api/chat·/api/models를 가짜 답으로 바꿔 끼움.
// 진짜 호출은 손 확인 몫(`tests/test_part50`이 서버 쪽 실호출을 지킴).
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { boardName, openBoard, setCam, clickScene, liveDoc, waitSaved, DATA } from './helpers.js'

const ANSWER = '## 오늘 할 일\n- 계통도 고치기\n- **발표** 준비\n1. 첫째\n2. 둘째'

async function fakeKairos(page, seen) {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: { gpt: [{ id: 'fake-model', price: '' }] } } }))
  await page.route('**/api/chat', async r => { seen.push(r.request().postDataJSON()); await r.fulfill({ json: { content: ANSWER, model: 'fake-model', elapsed: 0.1 } }) })
}

test('묻고 → 답 → 칠판에 붙이기 = 메모, 새로고침해도 메모·대화 기록 그대로', async ({ page }) => {
  const seen = [], name = boardName('kairos')
  await fakeKairos(page, seen)
  await openBoard(page, name, { chat: true }); await setCam(page)
  const box = page.getByPlaceholder('물어보세요', { exact: false })
  await box.click(); await page.keyboard.type('오늘 할 일 정리해 줘'); await page.keyboard.press('Enter')
  await expect(page.getByText('계통도 고치기').first()).toBeVisible()
  expect(seen[0].messages.at(-1)).toMatchObject({ role: 'user', content: '오늘 할 일 정리해 줘' })
  await page.getByRole('button', { name: '칠판에 붙이기' }).click()
  await expect(page.getByRole('button', { name: '칠판에 붙임 ✓' })).toBeVisible()
  let memo = (await liveDoc(page)).items.find(it => it.type === 'memo')
  expect(memo.lines.map(l => l.k)).toEqual(expect.arrayContaining(['h2', 'ul', 'ol']))
  expect(JSON.stringify(memo.lines)).toContain('계통도 고치기')

  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  memo = (await liveDoc(page)).items.find(it => it.type === 'memo')
  expect(JSON.stringify(memo.lines)).toContain('계통도 고치기')
  await expect(page.getByText('오늘 할 일 정리해 줘').first()).toBeVisible()        // 대화 기록(서버 chatlog)
  await expect(page.getByRole('button', { name: '칠판에 붙임 ✓' })).toBeVisible()  // 붙인 표시도 남음
})

test('모델이 없어져 대신한 답 = 답 옆 「(대신)」 + 까닭, 전에 고른 모델이 목록에 없어도 「기본」으로 안 보임(2026-10-26 모델 대체)', async ({ page }) => {
  const name = boardName('kairosswap')
  await page.addInitScript(() => localStorage.setItem('magic-board-model', 'old-model'))
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: { gpt: [{ id: 'fake-model', price: '' }] } } }))
  await page.route('**/api/chat', r => r.fulfill({ json: { content: ANSWER, model: 'sub-model', swap: { from: 'old-model', to: 'sub-model', why: '없어짐' }, elapsed: 0.1 } }))
  await openBoard(page, name, { chat: true }); await setCam(page)
  await expect(page.locator('select[title^="대화 답에 쓸 모델"] option').first()).toHaveText('old-model')
  const box = page.getByPlaceholder('물어보세요', { exact: false })
  await box.click(); await page.keyboard.type('안녕'); await page.keyboard.press('Enter')
  const meta = page.getByTestId('answer-model').last()
  await expect(meta).toContainText('sub-model (대신)')
  await expect(meta).toHaveAttribute('title', /old-model.*없어져서.*sub-model/)
})

test('⚙ 모델 설정 = 일마다 그 종류의 모델만, 고르면 요청에 실리고 새로고침해도 기억, 「모두 자동으로」(2026-10-26)', async ({ page }) => {
  const seen = [], name = boardName('kairospick')
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: { gpt: [{ id: 'fake-model', price: '' }] },
    jobs: { report: 'claude-opus-5-5', image: 'gpt-image-2.5-flare', icon: 'claude-sonnet-5-5', live: 'gpt-6.1-sol' },
    choices: { llm: [{ id: 'claude-sonnet-5-5', maker: 'claude', price: '$2 / 10' }, { id: 'fake-model', maker: 'openai', price: '' }],
      image: [{ id: 'gpt-image-2.5-flare', maker: 'openai', price: '장당 약 10크레딧' }, { id: 'fal-ai/fast-sdxl', maker: 'stability-ai', price: '' }] } } }))
  await page.route('**/api/chat', async r => { seen.push(r.request().postDataJSON()); await r.fulfill({ json: { content: ANSWER, model: 'fake-model', elapsed: 0.1 } }) })
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.getByTestId('model-settings').click()
  const pop = page.getByTestId('model-settings-pop')
  await expect(pop.getByTestId('pick-report').locator('option').first()).toHaveText('자동 · claude-opus-5-5')
  await expect(pop.getByTestId('pick-deep_plan')).toHaveCount(0)   // 서버가 딥모드를 못 하면 칸도 없음
  await expect(pop.getByTestId('pick-image').locator('option')).toHaveText(['자동 · gpt-image-2.5-flare', 'gpt-image-2.5-flare  장당 약 10크레딧', 'fal-ai/fast-sdxl'])   // 그림 칸 = 그림 모델만
  await pop.getByTestId('pick-report').selectOption('claude-sonnet-5-5')
  await pop.getByTestId('pick-image').selectOption('fal-ai/fast-sdxl')
  await page.mouse.click(700, 400)   // 바깥 = 닫힘
  await expect(pop).toHaveCount(0)
  const box = page.getByPlaceholder('물어보세요', { exact: false })
  await box.click(); await page.keyboard.type('안녕'); await page.keyboard.press('Enter')
  await expect(page.getByText('계통도 고치기').first()).toBeVisible()
  expect(seen[0].models).toEqual({ report: 'claude-sonnet-5-5', image: 'fal-ai/fast-sdxl' })
  await page.reload()
  await page.getByTestId('model-settings').click()
  await expect(page.getByTestId('pick-report')).toHaveValue('claude-sonnet-5-5')
  await page.getByTestId('picks-reset').click()
  await expect(page.getByTestId('pick-report')).toHaveValue('')
  await expect(page.getByTestId('picks-reset')).toHaveCount(0)
})

test('칠판에서 메모를 고른 채 물으면 그 글이 같이 감', async ({ page }) => {
  const seen = [], name = boardName('kairosctx')
  await fakeKairos(page, seen)
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.getByRole('button', { name: '메모', exact: true }).click()
  await page.keyboard.type('송신소 점검 결과 이상 없음')
  await clickScene(page, 900, 600)
  const memo = (await liveDoc(page)).items.find(it => it.type === 'memo')
  await clickScene(page, memo.pos[0] + 60, memo.pos[1] + 15)   // 메모 고르기
  const box = page.getByPlaceholder('물어보세요', { exact: false })
  await box.click(); await page.keyboard.type('요약해 줘'); await page.keyboard.press('Enter')
  await expect(page.getByText('계통도 고치기').first()).toBeVisible()
  expect(JSON.stringify(seen[0].messages.at(-1).context || '')).toContain('송신소 점검 결과 이상 없음')
})

test('두 창이 같은 칠판에 각자 물어도 — 앞 창 대화가 안 지워지고 「지난 대화」로 남음(2026-10-26 점검)', async ({ browser }) => {
  const name = boardName('chat2win'), log = () => JSON.parse(readFileSync(join(DATA, `${name}.chat.json`), 'utf-8'))
  const ca = await browser.newContext(), cb = await browser.newContext()
  const pc = await ca.newPage(), phone = await cb.newPage()
  for (const p of [pc, phone]) { await fakeKairos(p, []); await openBoard(p, name, { chat: true }) }   // 둘 다 빈 기록을 읽은 뒤
  const ask = async (p, q) => { const box = p.getByPlaceholder('물어보세요', { exact: false }); await box.click(); await p.keyboard.type(q); await p.keyboard.press('Enter'); await expect(p.getByText('계통도 고치기').first()).toBeVisible() }
  await ask(pc, 'PC에서 물음')
  await expect.poll(() => JSON.stringify(log())).toContain('PC에서 물음')
  await ask(phone, '폰에서 물음')   // 폰은 PC 저장을 모름 — 전엔 여기서 PC 대화가 통째로 덮였음
  await expect.poll(() => JSON.stringify(log())).toContain('폰에서 물음')
  const d = log()
  expect(d.messages.map(m => m.content)).toContain('폰에서 물음')
  expect(d.past.map(p => p.title)).toContain('다른 창 · PC에서 물음')
  await expect(phone.getByRole('button', { name: /지난 대화/ })).toBeVisible()   // 폰 화면도 받아 옴
  await ask(pc, 'PC에서 이어 물음')   // PC가 이어 물어도 폰 대화가 남음
  await expect.poll(() => JSON.stringify(log())).toContain('PC에서 이어 물음')
  const e = log(), all = JSON.stringify(e)
  expect(all).toContain('폰에서 물음'); expect(all).toContain('PC에서 물음')
  expect(e.past.length).toBe(1)   // 옮겨 둔 대화가 조각조각 늘지 않음
  await ca.close(); await cb.close()
})

test('답을 기다리다 「취소」 — 바로 풀리고 까닭이 보이고, 다시 물을 수 있음(2026-10-26 점검: 멈추면 새로고침밖에 없었음)', async ({ page }) => {
  const name = boardName('chatstop')
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: { gpt: [{ id: 'fake-model', price: '' }] } } }))
  let first = true
  await page.route('**/api/chat', async r => { if (first) { first = false; return } await r.fulfill({ json: { content: ANSWER, model: 'fake-model', elapsed: 0.1 } }) })   // 첫 질문은 답이 영영 안 옴
  await openBoard(page, name, { chat: true })
  const box = page.getByPlaceholder('물어보세요', { exact: false })
  await box.click(); await page.keyboard.type('멈춘 질문'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('chat-busy')).toBeVisible()
  await page.getByTestId('chat-stop').click()
  await expect(page.getByTestId('chat-busy')).toBeHidden()
  await expect(page.getByText('취소했어요', { exact: false })).toBeVisible()
  await box.click(); await page.keyboard.type('다시 물음'); await page.keyboard.press('Enter')
  await expect(page.getByText('계통도 고치기').first()).toBeVisible()
})

test('길이 상한에 걸려 끊긴 답 — 「끊겼어요」 + 「이어서 쓰기」 = 끊긴 곳부터 이어 달라고 보냄(2026-10-27)', async ({ page }) => {
  const seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b)
    await r.fulfill({ json: seen.length === 1 ? { content: '존경하는 직원 여러분, 오늘', model: 'fake-model', elapsed: 9, cut: true } : { content: '이 자리에 모인 까닭은…', model: 'fake-model', elapsed: 4 } }) })
  await openBoard(page, boardName('cut'), { chat: true }); await setCam(page)
  await page.getByPlaceholder('물어보세요', { exact: false }).click(); await page.keyboard.type('연설문 길게 써 줘'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-cut')).toContainText('끊겼어요')
  await page.getByTestId('answer-cut-more').click()
  await expect(page.getByText('이 자리에 모인 까닭은').first()).toBeVisible()
  expect(seen[1].kind).toBe('chat')                                                  // 길 고르기 없이 대화로
  expect(seen[1].messages.at(-2)).toMatchObject({ role: 'assistant', content: '존경하는 직원 여러분, 오늘' })   // 끊긴 답을 앞 대화로
  expect(seen[1].messages.at(-1).content).toContain('이어서')
  await expect(page.getByTestId('answer-cut')).toHaveCount(1)
  await expect(page.getByTestId('answer-cut-more')).toHaveCount(0)                   // 맨 끝 답이 아니면 단추 없음
})
