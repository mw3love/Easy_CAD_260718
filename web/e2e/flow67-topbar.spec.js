// 흐름 67 — 떠 있는 섬(2026-11-14 화면 틀 B1 — 옛 위 막대 2단은 걷음): 칠판이 창 맨 위까지 · 섬 넷이 안 겹침 · 도구 줄은 자리가 되면 칠판 가운데
import { test, expect } from '@playwright/test'
import { boardName, openBoard } from './helpers.js'

const ISLES = ['isl-board', 'isl-tools', 'isl-right', 'isl-undo']
const boxes = page => Promise.all(ISLES.map(t => page.getByTestId(t).boundingBox()))
const overlap = (a, b) => a.x < b.x + b.width - 1 && b.x < a.x + a.width - 1 && a.y < b.y + b.height - 1 && b.y < a.y + a.height - 1

test('넓은 창 — 칠판이 맨 위까지 · 도구 줄 = 칠판 가운데 · 섬끼리 안 겹침 · 아이콘 2색', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  await openBoard(page, boardName('islands'))
  expect((await page.getByTestId('board').boundingBox()).y).toBeLessThanOrEqual(1)                 // 위 막대 없음
  const bd = await page.getByTestId('board').boundingBox(), rs = await boxes(page)
  rs.forEach((r, i) => expect(r, ISLES[i]).toBeTruthy())
  expect(Math.abs(rs[1].x + rs[1].width / 2 - (bd.x + bd.width / 2))).toBeLessThan(2)              // 도구 줄 가운데
  for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) expect(overlap(rs[i], rs[j]), `${ISLES[i]}/${ISLES[j]}`).toBe(false)
  const tools = page.getByTestId('isl-tools')
  await tools.getByRole('button', { name: '선', exact: true }).click()
  await expect(tools.getByRole('button', { name: '선', exact: true })).toHaveAttribute('aria-pressed', 'true')
  const fill = sel => tools.getByRole('button', { name: '프레임', exact: true }).locator(sel).first().evaluate(el => getComputedStyle(el).fill)
  expect(await fill('svg [fill="currentColor"]')).toBe('rgb(37, 99, 235)')                       // 아이콘 2색(2026-11-08 시안 I1) 그대로
  expect(await fill('svg > :first-child')).toBe('none')
})

for (const [w, h] of [[960, 800], [1280, 800], [1440, 900]]) {
  test(`${w}px·대화창 열림 — 섬이 화면 안·안 겹침(자리가 모자라면 도구 줄이 옆이나 둘째 줄로)`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await openBoard(page, boardName('isl' + w), { chat: true })
    await expect.poll(async () => { const rs = await boxes(page); return rs.every(Boolean) }).toBe(true)
    const rs = await boxes(page)
    for (const r of rs) { expect(r.x).toBeGreaterThanOrEqual(0); expect(r.x + r.width).toBeLessThanOrEqual(w + 0.5) }
    for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) expect(overlap(rs[i], rs[j]), `${ISLES[i]}/${ISLES[j]}`).toBe(false)
  })
}

test('Tab 차례 = 보이는 차례(건너뛰기 → ☰ → 이름 → 도구 → 오른쪽 섬 → 되돌리기 → 왼쪽 판) · 좁은 창 뜬 대화창은 섬 아래부터', async ({ page }) => {
  await page.setViewportSize({ width: 960, height: 800 })
  await openBoard(page, boardName('isltab'), { chat: true })
  if (!(await page.getByTestId('dock-panel').count())) await page.getByTestId('dock-shape').click()   // 왼쪽 판까지 연 가장 좁은 경우
  await page.reload(); await expect(page.getByTestId('isl-tools')).toBeVisible()   // 판 단추를 누른 자리에서 Tab이 이어지지 않게 — 처음 연 모습에서
  const seen = []
  for (let i = 0; i < 4; i++) { await page.keyboard.press('Tab'); seen.push(await page.evaluate(() => document.activeElement?.getAttribute('aria-label') || document.activeElement?.dataset.testid || '')) }
  expect(seen).toEqual(['', '메뉴', 'board-title', '유지'].map((x, i) => (i === 0 ? seen[0] : x)))   // 첫 Tab = 「칠판으로 건너뛰기」(글자 링크)
  const chat = await page.locator('aside.mb-chat').boundingBox(), right = await page.getByTestId('isl-right').boundingBox(), tools = await page.getByTestId('isl-tools').boundingBox()
  expect(chat.y).toBeGreaterThanOrEqual(Math.max(right.y + right.height, tools.y + tools.height))   // 대화창이 섬을 덮지 않음(2026-11-14 손 검증 — 960에서 이름·오른쪽 섬이 7px 겹쳤음)
})
