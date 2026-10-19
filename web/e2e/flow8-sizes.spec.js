// 흐름 8 — 창 크기 셋: 위 막대가 한 줄·화면 밖으로 안 나감·버튼이 다 보임, 좁은 창은 대화창이 칠판 위에 뜸, 카드 접기는 새로고침 뒤에도 기억
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
    if (w < 1440) expect(board.width).toBeGreaterThan(w - 4)             // 좁은 창: 대화창은 칠판 위에 뜸(칠판은 창 폭 그대로)
    else expect(board.width).toBeLessThan(w - 200)                       // 넓은 창: 오른쪽에 나란히
  })
}

test('카드 접기는 새로고침 뒤에도 그대로', async ({ page }) => {
  const name = boardName('fold')
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '프레임', exact: true }).click(); await clickScene(page, 100, 100)   // 클릭만 = 16:9 프레임(프레임 카드는 프레임이 있을 때만 뜸)
  await waitSaved(page)
  const card = page.getByTestId('frames-card')
  await card.getByTitle('접기').click()
  await expect(card).toHaveAttribute('data-folded', /.*/)
  await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  await expect(page.getByTestId('frames-card')).toHaveAttribute('data-folded', /.*/)
})
