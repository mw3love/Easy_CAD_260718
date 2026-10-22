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
  await btn(page, '칠판').click(); await expect(page.getByTestId('board-form')).toBeVisible()
  const b = await page.getByTestId('board').boundingBox()
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2)                     // 칠판 빈 곳 = 닫힘
  await expect(page.getByTestId('board-form')).toHaveCount(0)
})

test('알림은 칠판 아래 가운데(잠깐) · 위 막대는 칠판 이름·배율만 · 샘플 열기는 칠판 메뉴 안', async ({ page }) => {
  const name = boardName('toast')
  await openBoard(page, name)
  const toast = page.getByTestId('status-toast')
  await expect(toast).toContainText(`서버 「${name}」`); await expect(toast).toHaveCSS('opacity', '1')
  const tb = await toast.boundingBox(), bb = await page.getByTestId('board').boundingBox()
  expect(tb.y).toBeGreaterThan(bb.y + bb.height - 80)                                // 칠판 아래쪽
  expect(Math.abs(tb.x + tb.width / 2 - (bb.x + bb.width / 2))).toBeLessThan(4)    // 가운데
  await expect(toast).toHaveCSS('opacity', '0', { timeout: 8000 })                  // 잠깐 뒤 사라짐
  await expect(page.getByText('100%', { exact: true }).first()).toBeVisible()
  await expect(page.getByTestId('sample-select')).toHaveCount(0)                    // 위 막대엔 없음
  await btn(page, '칠판').click(); await expect(page.getByTestId('board-form').getByTestId('sample-select')).toBeVisible()
})
