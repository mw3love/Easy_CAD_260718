// 흐름 8 — 창 크기 셋: 위 막대가 한 줄·화면 밖으로 안 나감·버튼이 다 보임, 좁은 창은 대화창이 칠판 위에 뜸(왼쪽 판은 처음엔 접혀 레일만), 왼쪽 판 칸·접기는 새로고침 뒤에도 기억
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, waitSaved, openPane } from './helpers.js'

for (const [w, h] of [[960, 800], [1040, 800], [1366, 768], [1600, 900]]) {
  test(`${w}px — 섬 단추가 다 화면 안·대화창 자리`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await openBoard(page, boardName('size' + w), { chat: true })
    const out = await page.evaluate(vw => [...document.querySelectorAll('[data-testid^="isl-"] button')]   // 옛 위 막대 → 떠 있는 섬(2026-11-14 B1)
      .map(b => [b.getAttribute('aria-label'), b.getBoundingClientRect()]).filter(([, q]) => q.right > vw + 0.5 || q.left < -0.5).map(([n]) => n), w)
    expect(out).toEqual([])                                              // 화면 밖으로 밀린 버튼 없음
    const board = await page.getByTestId('board').boundingBox()
    if (w < 1440) expect(board.width).toBeGreaterThan(w - 60)            // 좁은 창: 대화창은 칠판 위에 뜸(칠판 = 창 폭 − 왼쪽 레일 52, 판은 처음엔 접힘)
    else expect(board.width).toBeLessThan(w - 200)                       // 넓은 창: 오른쪽에 나란히
  })
}

test('떠 있는 판 — 처음엔 닫힘 · 여는 길(☰ 프레임 목록·레이어) · 다시 고르면 닫힘 · 새로고침 뒤에도 그대로 · 폭 조절 · 미니맵은 오른쪽 아래(2026-11-14 B1)', async ({ page }) => {
  const name = boardName('dock')
  await openBoard(page, name); await setCam(page)
  await expect(page.getByTestId('dock-panel')).toHaveCount(0)                       // 처음 = 닫힘(칠판 넓게)
  await openPane(page, 'frame')
  await expect(page.getByTestId('frames-empty')).toBeVisible()                      // 프레임이 없으면 안내
  await page.getByTestId('isl-tools').getByRole('button', { name: '프레임', exact: true }).click(); await clickScene(page, 100, 100)   // 「프레임」 클릭만 = 16:9 프레임
  await waitSaved(page)
  const card = page.getByTestId('frames-card')
  await expect(card.getByRole('button', { name: '▶ 발표' })).toBeVisible()
  await expect(card.getByTitle('접기')).toHaveCount(0)                              // 카드마다 접기는 없음
  await expect(page.getByText('미니맵', { exact: true })).toBeVisible()             // 미니맵 = 판 밖 오른쪽 아래
  await openPane(page, 'frame')                                                     // 다시 고르면 닫힘
  await expect(page.getByTestId('dock-panel')).toHaveCount(0)
  await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  await expect(page.getByTestId('dock-panel')).toHaveCount(0)                       // 닫은 것 기억
  await openPane(page, 'layer'); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '＋ 새 레이어' })).toBeVisible()   // 연 판도 기억
  const panel = page.getByTestId('dock-panel'), r = await page.getByTestId('dock-resize').boundingBox()   // 폭 조절 — 192~400
  expect(Math.round((await panel.boundingBox()).width)).toBe(192)
  await page.mouse.move(r.x + 3, r.y + 20); await page.mouse.down(); await page.mouse.move(r.x + 103, r.y + 20, { steps: 5 }); await page.mouse.up()
  expect(Math.round((await panel.boundingBox()).width)).toBe(292)
  await page.mouse.move(r.x + 103, r.y + 20); await page.mouse.down(); await page.mouse.move(r.x - 300, r.y + 20, { steps: 5 }); await page.mouse.up()
  expect(Math.round((await panel.boundingBox()).width)).toBe(192)                   // 최소 아래로는 안 줄어듦
  await page.mouse.move(r.x + 3, r.y + 20); await page.mouse.down(); await page.mouse.move(r.x + 53, r.y + 20, { steps: 3 }); await page.mouse.up()
  await page.getByTestId('dock-resize').dblclick()
  expect(Math.round((await panel.boundingBox()).width)).toBe(192)                   // 두 번 누르면 기본 폭
})
