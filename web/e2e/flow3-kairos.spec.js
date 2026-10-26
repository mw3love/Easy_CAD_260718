// 흐름 3 — KAIROS 묻고 칠판에 붙이기. 진짜 KAIROS는 부르지 않는다(크레딧·답이 매번 다름) — /api/chat·/api/models를 가짜 답으로 바꿔 끼움.
// 진짜 호출은 손 확인 몫(`tests/test_part50`이 서버 쪽 실호출을 지킴).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, waitSaved } from './helpers.js'

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
