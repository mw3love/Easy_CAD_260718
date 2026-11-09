// 흐름 69 — ✨ AI 칩(2026-11-09 사용자 — 클로드 아티팩트 넷, 시안 A + E1): 고르면 오른쪽 위 「AI」 칩 → 작은 창 = 큰 단추 넷 + 입력.
// 단추 한 번 = 고르기만(서버 안 부름) · Enter = 실행 · 문서 = 읽기용 한 장이 칠판에 바로 붙음 · 단추 없이 말만 = 하나면 그 물건 말풍선 · 끄는 중엔 칩 숨김.
// KAIROS는 가짜(/api/chat).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, toPage } from './helpers.js'

const html = t => `<!doctype html><html><head><title>${t}</title></head><body><h1>${t}</h1></body></html>`

async function twoMemos(page) {
  for (const [t, x] of [['# 송신소 점검\n- 안테나 정상', 1500], ['# 다음 할 일\n- 예비 송신기 시험', 1900]]) {
    await page.getByRole('button', { name: '메모', exact: true }).click(); await page.keyboard.type(t.replace(/\n/g, ' ')); await clickScene(page, x, 900)
  }
  return (await liveDoc(page)).items.filter(it => it.type === 'memo')
}

test('AI 칩 — 고르면 뜸 · 단추 한 번은 고르기만 · Enter = 문서(읽기용 한 장) → 칠판에 붙음', async ({ page }) => {
  const name = boardName('aichip'), seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b)
    await r.fulfill({ json: { kind: 'report', content: '정리 문서', title: '점검 정리', html: html('점검 정리'), docs: [{ style: 'read', html: html('점검 정리'), title: '점검 정리' }], model: 'claude-opus-5-5', elapsed: 3 } }) })
  await openBoard(page, name, { chat: false }); await setCam(page)
  await expect(page.getByTestId('ai-chip')).toHaveCount(0)                          // 아무것도 안 고름 = 칩 없음
  const memos = await twoMemos(page)
  await page.keyboard.press('Control+a')
  const chip = page.getByTestId('ai-chip'); await expect(chip).toBeVisible()
  await chip.click()
  const panel = page.getByTestId('ai-panel'); await expect(panel).toContainText('고른 것 2개')
  await panel.locator('[data-kind="doc"]').click()
  await expect(panel.locator('[data-kind="doc"]')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('ai-input')).toHaveAttribute('placeholder', /문서 — 바라는 점/)
  await page.waitForTimeout(300); expect(seen).toHaveLength(0)                         // 한 번 누르기 = 고르기만(E1)
  await page.getByTestId('ai-input').press('Enter')
  await expect.poll(() => seen.length).toBe(1)
  expect(seen[0].kind).toBe('report')
  expect(seen[0].messages.at(-1).content).toContain('읽기용')                          // 서버 `style_of` = 읽기용 한 장만
  expect(JSON.stringify(seen[0].messages.at(-1).context || '')).toContain('예비 송신기 시험')   // 고른 것이 재료
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'doc').length).toBe(1)   // 칠판에 바로 붙음
  expect(memos).toHaveLength(2)
  await page.screenshot({ path: 'test-results/ai-chip-doc.png' })
})

test('AI 칩 — 단추 없이 말만: 하나면 그 물건 말풍선으로 · Esc = 닫힘 · 끄는 중엔 칩 숨김', async ({ page }) => {
  const name = boardName('aichip2'), seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b)
    await r.fulfill({ json: { content: '할 일은 예비 송신기 시험 하나예요', model: 'gpt-6.1-sol', elapsed: 1 } }) })
  await openBoard(page, name, { chat: false }); await setCam(page)
  const memos = await twoMemos(page), m = memos[0]
  await clickScene(page, m.pos[0] + 60, m.pos[1] + 15)
  const chip = page.getByTestId('ai-chip'); await expect(chip).toBeVisible()
  await chip.click(); await page.keyboard.press('Escape')
  await expect(page.getByTestId('ai-panel')).toHaveCount(0); await expect(chip).toBeVisible()
  await chip.click(); await page.getByTestId('ai-input').fill('할 일만 알려 줘'); await page.getByTestId('ai-input').press('Enter')
  await expect(page.getByTestId('bubble')).toBeVisible()
  await expect(page.getByTestId('bubble-q')).toHaveText('할 일만 알려 줘')
  await expect(page.getByTestId('bubble-a')).toContainText('예비 송신기 시험')
  expect(seen[0].kind).toBe('bubble')
  await page.getByTestId('bubble-close').click()
  // 끄는 중 = 칩 숨김, 놓으면 다시
  const a = await toPage(page, m.pos[0] + 60, m.pos[1] + 15)
  await page.mouse.move(a.x, a.y); await page.mouse.down(); await page.mouse.move(a.x + 40, a.y + 30, { steps: 5 })
  await expect(chip).toHaveCount(0)
  await page.mouse.up(); await expect(chip).toBeVisible()
})

test('AI 칩 — 오른쪽 위 속성 카드와 안 겹침(겹치면 카드 왼쪽으로 비킴)', async ({ page }) => {
  await openBoard(page, boardName('aichip3'), { chat: false }); await setCam(page)
  const [m] = await twoMemos(page)
  await clickScene(page, m.pos[0] + 60, m.pos[1] + 15)
  const card = page.getByTestId('props-card'), chip = page.getByTestId('ai-chip'); await expect(card).toBeVisible()
  const board = await page.getByTestId('board').boundingBox(), cb = await card.boundingBox()
  // 메모 오른쪽 위 끝을 속성 카드 한가운데 아래로(칩이 그 자리에 뜨게)
  await page.evaluate(([m, x, y]) => { const c = window.__mb.getCam(); window.__mb.setCam({ ...c, x: x - (m.pos[0] + m.rect[2]) * c.z, y: y + 40 - m.pos[1] * c.z }) }, [m, cb.x - board.x + cb.width - 10, cb.y - board.y + 20])
  await expect(chip).toBeVisible()
  await expect.poll(async () => { const a = await chip.boundingBox(), b = await card.boundingBox(); return a.x + a.width <= b.x || a.y >= b.y + b.height }).toBe(true)
  await chip.click(); await expect(page.getByTestId('ai-panel')).toBeVisible()
})
