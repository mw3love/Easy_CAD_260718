// 흐름 18 — 칠판 고르기(새 칠판·최근 칠판)와 다시 열 때 화면 자리(2026-10-19 점검: 주소창에 ?board=를 쳐야만 옮겨 갔고, 기억한 자리가 빈 곳이면 빈 칠판처럼 열렸음)
import { test, expect } from '@playwright/test'
import { openBoard, setCam, pickShape, dragScene, liveDoc, waitSaved } from './helpers.js'

test('「칠판」으로 새 칠판 만들기(이름 + 칠판 코드) → 내 칠판 목록에 → 눌러서 옮겨 감', async ({ page }) => {
  const stamp = Date.now().toString(36), a = `보드A${stamp}`, b = `보드B${stamp}`
  await openBoard(page, a); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 200, y: 100 }); await waitSaved(page)

  await page.getByTestId('dock-board').click()                                       // 왼쪽 판 「칠판」 칸(2026-10-23)
  const form = page.getByTestId('board-form')
  await expect(form.getByTestId('board-row').filter({ hasText: a })).toBeVisible()    // 지금 칠판 = 내 칠판 — 이 브라우저
  await expect(form.getByTestId('board-row')).toHaveCount(1)                          // 서버의 다른 칠판(다른 시험이 만든 것)은 안 보임 — 비밀번호 없는 서버 = 주소가 열쇠(2026-10-27)
  await expect(form.getByPlaceholder('새 칠판 이름', { exact: false })).toHaveCount(0)   // 처음엔 이름 칸 없음(찾기 칸으로 보였음 — 2026-10-27)
  await form.getByTestId('board-new').click()
  await form.getByPlaceholder('새 칠판 이름', { exact: false }).fill(b)
  await form.getByRole('button', { name: '만들기' }).click()
  await expect(page).toHaveURL(new RegExp(`board=${encodeURIComponent(b)}-[a-z2-9]{8}$`))   // 이름 + 칠판 코드(짐작 못 하는 꼬리)
  await expect(page.getByText(`서버 「${b}-`, { exact: false }).first()).toBeVisible()
  await expect(page.getByTestId('board-title')).toHaveText(new RegExp(`^${b}`))        // 위 막대엔 이름만(코드는 목록에 흐리게)

  await expect(page.getByTestId('dock-board')).toHaveAttribute('aria-pressed', 'true')   // 옮겨 가도 연 칸은 그대로(이 브라우저에 기억)
  await expect(page.getByTestId('board-row')).toHaveCount(2)                          // 새 칠판(지금 — 저장 전) + A
  await page.getByTestId('board-row').filter({ hasText: a }).click()                  // A로 돌아감
  await expect(page.getByText(`서버 「${a}」`).first()).toBeVisible()
  expect((await liveDoc(page)).items.filter(it => it.type === 'rect')).toHaveLength(1)
})

test('기억한 화면 자리에 아무것도 안 보이면 다시 열 때 전체 맞추기', async ({ page }) => {
  const name = `보드C${Date.now().toString(36)}`
  await openBoard(page, name); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 200, y: 100 }); await waitSaved(page)
  await page.evaluate(() => window.__mb.setCam({ x: -90000, y: -90000, z: 3 }))      // 멀리 빈 곳을 보다 닫음
  await page.waitForTimeout(500)                                                      // 화면 자리 기억(0.3초 뒤 저장)
  await page.reload(); await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  const c = await page.evaluate(() => window.__mb.getCam()), box = await page.getByTestId('board').boundingBox()
  const sx = 100 * c.z + c.x, sy = 50 * c.z + c.y                                     // 사각형 가운데의 화면 자리
  expect(sx > 0 && sx < box.width && sy > 0 && sy < box.height).toBe(true)
  expect(0 * c.z + c.x).toBeGreaterThanOrEqual(220)                                  // 사각형 왼쪽 끝이 왼쪽 카드(220px) 밑에 안 들어감

  await page.evaluate(() => window.__mb.setCam({ x: 300, y: 250, z: 1.5 }))          // 도형이 보이는 자리는 그대로 기억
  await page.waitForTimeout(500); await page.reload(); await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  expect(await page.evaluate(() => window.__mb.getCam())).toEqual({ x: 300, y: 250, z: 1.5 })
})
