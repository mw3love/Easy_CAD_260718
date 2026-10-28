// 흐름 18 — 칠판 고르기(새 칠판·최근 칠판)와 다시 열 때 화면 자리(2026-10-19 점검: 주소창에 ?board=를 쳐야만 옮겨 갔고, 기억한 자리가 빈 곳이면 빈 칠판처럼 열렸음)
import { test, expect } from '@playwright/test'
import { openBoard, setCam, pickShape, dragScene, liveDoc, waitSaved, savedDoc } from './helpers.js'

test('「＋ 새 칠판」 = 바로 새 칠판(칠판 코드만) · 빈 칠판도 남음 · 눌러도 순서 그대로 · 끌어서 순서 · 이름 바꾸기(주소 그대로) · 줄 = 지금 접속자', async ({ page }) => {
  const a = `보드A${Date.now().toString(36)}`
  await openBoard(page, a); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 200, y: 100 }); await waitSaved(page)

  await page.getByTestId('dock-board').click()                                       // 왼쪽 판 「칠판」 칸(2026-10-23)
  const form = page.getByTestId('board-form'), rows = form.getByTestId('board-row')
  await expect(rows.filter({ hasText: a })).toBeVisible()                             // 지금 칠판 = 내 칠판(이 브라우저)
  await expect(rows).toHaveCount(1)                                                   // 서버의 다른 칠판(다른 시험이 만든 것)은 안 보임 — 비밀번호 없는 서버 = 주소가 열쇠(2026-10-27)
  await expect(rows.filter({ hasText: a }).getByTestId('board-people')).toHaveText('시', { timeout: 6000 })   // 개수 대신 지금 접속자(2026-10-28) — 나 = 「시험」
  await form.getByTestId('board-new').click()                                         // 이름 칸 없이 바로(2026-10-28 사용자)
  await expect(page).toHaveURL(/board=[a-z2-9]{8}$/)
  const b = new URL(page.url()).searchParams.get('board')
  await expect(page.getByText(`서버 「${b}」`, { exact: false }).first()).toBeVisible()
  await expect(page.getByTestId('board-title')).toHaveText(/^제목 없음/)
  await expect.poll(() => savedDoc(b)?.items?.length).toBe(0)                         // 아무것도 안 그려도 서버에 빈 칠판(칠판 코드로도 찾힘)
  await expect(page).toHaveTitle('제목 없음 — Magic Board')                            // 탭 제목 = 칠판 이름

  await expect(page.getByTestId('dock-board')).toHaveAttribute('aria-pressed', 'true')   // 옮겨 가도 연 칸은 그대로(이 브라우저에 기억)
  await expect(rows).toHaveCount(2)
  await expect(rows.nth(0)).toContainText(b)                                          // 새 칠판 = 맨 위
  await rows.filter({ hasText: a }).click()                                           // 빈 칠판 그대로 A로
  await expect(page.getByText(`서버 「${a}」`).first()).toBeVisible()
  expect((await liveDoc(page)).items.filter(it => it.type === 'rect')).toHaveLength(1)
  await expect(rows).toHaveCount(2)                                                   // 빈 칠판도 남음(전엔 서버에 없으면 빠졌음)
  await expect(rows.nth(0)).toContainText(b)                                          // 누른 칠판이 맨 위로 안 올라감

  await rows.filter({ hasText: a }).dragTo(rows.nth(0), { targetPosition: { x: 30, y: 3 } })   // 끌어서 순서 바꾸기
  await expect(rows.nth(0)).toContainText(a)
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem('mb.myBoards')).map(x => x.name))).toEqual([a, b])

  await rows.filter({ hasText: b }).dblclick()                                        // 두 번 누르기 = 이름 바꾸기(옮겨 가지 않음)
  await form.getByTestId('board-rename').fill('송신소 점검'); await page.keyboard.press('Enter')
  await expect(rows.nth(1)).toContainText('송신소 점검')
  await expect.poll(() => savedDoc(b)?.title).toBe('송신소 점검')                       // 문서 이름만 — 주소(칠판 코드)는 그대로
  await page.waitForTimeout(400); expect(page.url()).toContain(encodeURIComponent(a))

  await rows.nth(0).hover(); await rows.nth(0).getByTestId('board-more').click()      // ⋯ = 우클릭 메뉴와 같음
  await page.locator('div[style*="z-index: 30"] > div > button', { hasText: '이름 바꾸기' }).click()
  await form.getByTestId('board-rename').fill('본사 회의'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('board-title')).toHaveText(/^본사 회의/)               // 지금 칠판 = 위 막대·탭 제목도(받아 오기로 따라옴)
  await expect(page).toHaveTitle('본사 회의 — Magic Board')
  await page.reload(); await expect(page.getByTestId('board-title')).toHaveText(/^본사 회의/)
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
