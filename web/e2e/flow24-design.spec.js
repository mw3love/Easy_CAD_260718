// 흐름 24 — 2026-10-22 디자인 점검: 위 막대 팝업은 바깥 누르기·Esc로 닫히고 하나만 · 알림은 칠판 아래 가운데 · 샘플 열기는 칠판 메뉴 안
import { test, expect } from '@playwright/test'
import { boardName, openBoard } from './helpers.js'

const btn = (page, name) => page.getByRole('button', { name, exact: true })

test('팝업 — 다른 팝업을 열면 앞 것은 닫힘 · Esc · 바깥 누르기 · 팝업 안 누르기는 그대로', async ({ page }) => {
  await openBoard(page, boardName('pop'))
  await btn(page, '내보내기').click(); await expect(page.getByTestId('export-preview')).toBeVisible()
  await btn(page, '공유').click()
  await expect(page.getByRole('button', { name: '주소 복사' })).toBeVisible()
  await expect(page.getByTestId('export-preview')).toHaveCount(0)                 // 하나만
  await page.getByRole('button', { name: '주소 복사' }).click()                    // 팝업 안 = 안 닫힘
  await expect(page.getByRole('button', { name: '주소 복사' })).toBeVisible()
  await page.keyboard.press('Escape'); await expect(page.getByRole('button', { name: '주소 복사' })).toHaveCount(0)   // 커서가 팝업 밖이어도 Esc
  await page.getByTestId('dock-board').click(); await expect(page.getByTestId('board-form')).toBeVisible()   // 칠판 목록 = 왼쪽 판 「칠판」 칸(2026-10-23 — 팝업 아님)
  const b = await page.getByTestId('board').boundingBox()
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2)                     // 칠판 빈 곳을 눌러도 판은 그대로
  await expect(page.getByTestId('board-form')).toBeVisible()
  await page.getByTestId('dock-board').click(); await expect(page.getByTestId('board-form')).toHaveCount(0)   // 열린 칸을 다시 누르면 접힘
})

test('알림은 칠판 아래 가운데(잠깐) · 칠판 이름 = 위 막대 맨 왼쪽(누르면 칠판 칸) · 배율·샘플은 없음', async ({ page }) => {
  const name = boardName('toast')
  await openBoard(page, name)
  const toast = page.getByTestId('status-toast')
  await expect(toast).toContainText(`서버 「${name}」`); await expect(toast).toHaveCSS('opacity', '1')
  const tb = await toast.boundingBox(), bb = await page.getByTestId('board').boundingBox()
  expect(tb.y).toBeGreaterThan(bb.y + bb.height - 80)                                // 칠판 아래쪽
  expect(Math.abs(tb.x + tb.width / 2 - (bb.x + bb.width / 2))).toBeLessThan(4)    // 가운데
  await expect(toast).toHaveCSS('opacity', '0', { timeout: 8000 })                  // 잠깐 뒤 사라짐
  const title = page.getByTestId('board-title'); await expect(title).toContainText(name)
  const tbx = await title.boundingBox(), tools = await page.getByRole('button', { name: '저장', exact: true }).boundingBox()
  expect(tbx.x).toBeLessThan(tools.x)                                                // 맨 왼쪽(2026-10-27 사용자)
  await expect(page.getByText('100%', { exact: true })).toHaveCount(1)              // 배율은 미니맵에만(위 막대 것과 겹쳤음)
  await expect(page.getByTestId('sample-select')).toHaveCount(0)                    // 샘플 = 개발 시험용 — 서버 있으면 어디에도 없음
  await title.click(); await expect(page.getByTestId('board-form')).toBeVisible()
  await expect(page.getByTestId('board-form').getByTestId('sample-select')).toHaveCount(0)
  await expect(page.getByTestId('board-form').getByRole('button', { name: '저장' })).toHaveCount(0)   // 위 막대·Ctrl+S와 겹침
  await title.click(); await expect(page.getByTestId('board-form')).toHaveCount(0)
})
