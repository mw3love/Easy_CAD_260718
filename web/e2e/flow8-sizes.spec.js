// 흐름 8 — 창 크기 셋: 위 막대가 한 줄·화면 밖으로 안 나감·버튼이 다 보임, 좁은 창은 대화창이 칠판 위에 뜸(왼쪽 판은 처음엔 접혀 레일만), 왼쪽 판 칸·접기는 새로고침 뒤에도 기억
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, waitSaved } from './helpers.js'

for (const [w, h] of [[960, 800], [1366, 768], [1600, 900]]) {
  test(`${w}px — 위 막대 한 줄·버튼 다 보임·대화창 자리`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await openBoard(page, boardName('size' + w), { chat: true })
    const bar = page.locator('#root > div > div').first()
    const r = await bar.boundingBox()
    expect(r.height).toBeLessThan(64)                                    // 두 줄로 늘면 칠판이 밀림(2026-10-19 겪음)
    const out = await page.evaluate(vw => [...document.querySelectorAll('#root > div > div:first-child button')]
      .map(b => [b.getAttribute('aria-label'), b.getBoundingClientRect()]).filter(([, q]) => q.right > vw + 0.5 || q.left < -0.5).map(([n]) => n), w)
    expect(out).toEqual([])                                              // 화면 밖으로 밀린 버튼 없음
    const board = await page.getByTestId('board').boundingBox()
    if (w < 1440) expect(board.width).toBeGreaterThan(w - 60)            // 좁은 창: 대화창은 칠판 위에 뜸(칠판 = 창 폭 − 왼쪽 레일 52, 판은 처음엔 접힘)
    else expect(board.width).toBeLessThan(w - 200)                       // 넓은 창: 오른쪽에 나란히
  })
}

test('왼쪽 판 — 칸 바꾸기 · 열린 칸 다시 누르면 접힘(칠판 넓어짐) · 새로고침 뒤에도 그대로 · 미니맵은 늘 판 아래(2026-10-23 사용자)', async ({ page }) => {
  const name = boardName('dock')
  await openBoard(page, name); await setCam(page)
  await expect(page.getByTestId('dock-shape')).toHaveAttribute('aria-pressed', 'true')   // 넓은 창 처음 = 도형 칸
  await page.getByTestId('dock-frame').click()
  await expect(page.getByTestId('frames-empty')).toBeVisible()                      // 프레임이 없으면 안내
  await page.getByRole('button', { name: '프레임', exact: true }).click(); await clickScene(page, 100, 100)   // 위 막대 「프레임」 클릭만 = 16:9 프레임
  await waitSaved(page)
  const card = page.getByTestId('frames-card')
  await expect(card.getByRole('button', { name: '▶ 발표' })).toBeVisible()
  await expect(card.getByTitle('접기')).toHaveCount(0)                              // 카드마다 접기는 없음
  await expect(page.getByTestId('dock-panel').getByText('미니맵')).toBeVisible()
  const w0 = (await page.getByTestId('board').boundingBox()).width
  await page.getByTestId('dock-frame').click()                                      // 열린 칸 = 접기
  await expect(page.getByTestId('dock-panel')).toHaveCount(0)
  expect((await page.getByTestId('board').boundingBox()).width).toBeGreaterThan(w0 + 180)   // 판 192만큼
  await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  await expect(page.getByTestId('dock-panel')).toHaveCount(0)                       // 접은 것 기억
  await page.getByTestId('dock-layer').click(); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  await expect(page.getByTestId('dock-layer')).toHaveAttribute('aria-pressed', 'true')   // 연 칸도 기억
  const panel = page.getByTestId('dock-panel'), r = await page.getByTestId('dock-resize').boundingBox()   // 폭 조절 — 192(미니맵 기준)~400, 미니맵이 판 폭을 따라감
  expect(Math.round((await panel.boundingBox()).width)).toBe(192)
  await page.mouse.move(r.x + 4, r.y + 300); await page.mouse.down(); await page.mouse.move(r.x + 104, r.y + 300, { steps: 5 }); await page.mouse.up()
  expect(Math.round((await panel.boundingBox()).width)).toBe(292)
  expect(Math.round((await panel.locator('canvas').boundingBox()).width)).toBe(292 - 16)
  await page.mouse.move(r.x + 104, r.y + 300); await page.mouse.down(); await page.mouse.move(r.x - 300, r.y + 300, { steps: 5 }); await page.mouse.up()
  expect(Math.round((await panel.boundingBox()).width)).toBe(192)                   // 최소 아래로는 안 줄어듦
  await page.mouse.move(r.x + 4, r.y + 300); await page.mouse.down(); await page.mouse.move(r.x + 54, r.y + 300, { steps: 3 }); await page.mouse.up()
  await page.getByTestId('dock-resize').dblclick()
  expect(Math.round((await panel.boundingBox()).width)).toBe(192)                   // 두 번 누르면 기본 폭
})
