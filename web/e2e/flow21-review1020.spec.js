// 흐름 21 — 10-20 사용자 검토: 번호 = 남은 가장 큰 수 + 1 · 미니맵 % = 100% · Alt+Z 고른 것만 · 펜은 끌기 없음 ·
// 대화창 「다시 ▾」 셋 · 새 대화·지난 대화 · 🔑 내 키(머리말로만). 진짜 KAIROS는 안 부름(flow3처럼 가짜 답).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, toPage, clickScene, liveDoc } from './helpers.js'

const btn = (page, name) => page.getByRole('button', { name, exact: true })

async function fakeKairos(page, seen) {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: { gpt: [{ id: 'fake-model', price: '' }] } } }))
  await page.route('**/api/chat', async r => { seen.push({ body: r.request().postDataJSON(), headers: r.request().headers() })
    await r.fulfill({ json: { content: `답 ${seen.length}`, model: 'fake-model', elapsed: 0.1 } }) })
}
async function ask(page, q) {
  const box = page.getByPlaceholder('물어보세요', { exact: false })
  await box.click(); await page.keyboard.type(q); await page.keyboard.press('Enter')
}

test('번호 — 3을 지우면 다음은 다시 3, 중간 2를 지우면 4', async ({ page }) => {
  await openBoard(page, boardName('badge')); await setCam(page)
  await page.keyboard.press('7')
  for (const x of [0, 80, 160]) await clickScene(page, x, 0)
  const nums = async () => (await liveDoc(page)).items.filter(it => it.type === 'badge').map(it => it.number).sort((a, b) => a - b)
  expect(await nums()).toEqual([1, 2, 3])
  await page.keyboard.press('Escape')
  await clickScene(page, 160, 0); await page.keyboard.press('Delete')          // 3 지움
  await page.keyboard.press('7'); await clickScene(page, 240, 0)
  expect(await nums()).toEqual([1, 2, 3])
  await page.keyboard.press('Escape')
  await clickScene(page, 80, 0); await page.keyboard.press('Delete')           // 가운데 2 지움
  await page.keyboard.press('7'); await clickScene(page, 320, 0)
  expect(await nums()).toEqual([1, 3, 4])
})

test('미니맵 % = 100%(화면 가운데 기준) · Alt+Z = 메모 하나 골라도 고른 것만 맞춤', async ({ page }) => {
  await openBoard(page, boardName('mmzoom')); await setCam(page, { x: 400, y: 200, z: 0.5 })
  await page.getByRole('button', { name: '50%' }).click()
  expect((await page.evaluate(() => window.__mb.getCam())).z).toBe(1)
  await setCam(page)
  await btn(page, '메모').click()                                           // 만들면 고른 채
  await setCam(page, { x: -6000, y: -6000, z: 1 })
  await page.keyboard.press('Alt+z')
  await expect(page.getByTestId('memo-editor')).toHaveCount(0)              // 글로 안 들어감
  const m = (await liveDoc(page)).items.find(it => it.type === 'memo'), p = await toPage(page, m.pos[0], m.pos[1])
  const b = await page.getByTestId('board').boundingBox()
  expect(p.x).toBeGreaterThan(b.x); expect(p.x).toBeLessThan(b.x + b.width) // 화면 안으로
})

test('펜 버튼은 끌어도 아무것도 안 놓임', async ({ page }) => {
  await openBoard(page, boardName('pendrag')); await setCam(page)
  const b = await btn(page, '펜').boundingBox(), q = await toPage(page, 200, 200)
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await page.mouse.down()
  await page.mouse.move(q.x, q.y, { steps: 10 }); await page.mouse.up()
  expect((await liveDoc(page)).items).toHaveLength(0)
  await expect(btn(page, '펜')).not.toHaveAttribute('aria-pressed', 'true')   // 도구도 안 바뀜
})

test('대화창 — 「다시 ▾」는 답하는 방식 셋만 · 새 대화 = 앞 대화 안 실림 · 지난 대화 다시 열기', async ({ page }) => {
  const seen = []
  await fakeKairos(page, seen)
  await openBoard(page, boardName('threads'), { chat: true })
  await ask(page, '첫 대화 질문'); await expect(page.getByText('답 1')).toBeVisible()
  await page.getByTestId('redo-menu').click()
  await expect(page.getByRole('button', { name: '웹 검색으로 다시' })).toBeVisible()
  await expect(page.getByRole('button', { name: '칠판에서 다시' })).toBeVisible()
  for (const n of ['정리 문서로 다시', '정리정돈으로 다시', '그림으로 다시']) await expect(page.getByRole('button', { name: n })).toHaveCount(0)
  await page.getByRole('button', { name: /새 대화/ }).click()
  await expect(page.getByText('첫 대화 질문')).toHaveCount(0)
  await ask(page, '둘째 대화 질문'); await expect(page.getByText('답 2')).toBeVisible()
  expect(seen[1].body.messages.map(m => m.content)).toEqual(['둘째 대화 질문'])   // 앞 대화가 안 실림
  await page.getByRole('button', { name: /지난 대화 1/ }).click()
  await page.getByTestId('past-list').getByRole('button', { name: /첫 대화 질문/ }).click()
  await expect(page.getByText('첫 대화 질문')).toBeVisible()
  await expect(page.getByRole('button', { name: /지난 대화 1/ })).toBeVisible()  // 둘째 대화는 목록으로
  await page.reload()                                                         // 서버에 남음
  await expect(page.getByText('첫 대화 질문')).toBeVisible()
  await page.getByRole('button', { name: /지난 대화 1/ }).click()
  await expect(page.getByTestId('past-list')).toContainText('둘째 대화 질문')
})

test('🔑 내 키 — 넣으면 물을 때 머리말로만, 지우면 서버 키', async ({ page }) => {
  const seen = []
  await fakeKairos(page, seen)
  await openBoard(page, boardName('mykey'), { chat: true })
  await page.getByRole('button', { name: /서버 키/ }).click()
  const box = page.getByTestId('key-box')
  await box.locator('input').fill('한글키')
  await expect(box.getByRole('button', { name: '저장' })).toBeDisabled()     // 키 모양이 아니면 못 넣음
  await box.locator('input').fill('my-own-key-1234'); await box.getByRole('button', { name: '저장' }).click()
  await expect(page.getByRole('button', { name: /내 키/ })).toBeVisible()
  await ask(page, '키 시험'); await expect(page.getByText('답 1')).toBeVisible()
  expect(seen[0].headers['x-kairos-key']).toBe('my-own-key-1234')
  expect(JSON.stringify(seen[0].body)).not.toContain('my-own-key-1234')
  await page.getByRole('button', { name: /내 키/ }).click(); await page.getByTestId('key-box').getByRole('button', { name: '지우기' }).click()
  await ask(page, '다시'); await expect(page.getByText('답 2')).toBeVisible()
  expect(seen[1].headers['x-kairos-key']).toBeUndefined()
})
