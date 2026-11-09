// 흐름 37 — 빈 칠판 첫 안내(2026-10-26 대회 준비): 비었을 때만 가운데 · 「발표 자료 만들기」 = 입력 칸에 「발표 자료 만들어 줘 — 주제: 」(2026-11-08 — 전엔 Deep Mode 이름표) · 「KAIROS에게 묻기」 = 입력 칸 ·
// 하나라도 놓이면 사라짐 · × = 이 브라우저에선 다시 안 뜸. KAIROS는 부르지 않음(크레딧은 사용자가 보낼 때만).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, pickShape, dragScene } from './helpers.js'

test('빈 칠판 안내 — 버튼은 대화창 입력 칸으로 · 도형을 놓으면 사라짐', async ({ page }) => {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'claude-sonnet-5-5' } } }))   // 발표 자료 되는 서버
  await openBoard(page, boardName('guide'), { guide: true }); await setCam(page)
  const g = page.getByTestId('empty-guide')
  await expect(g).toBeVisible()
  await g.getByTestId('empty-guide-슬라이드 만들기').click()
  await expect(page.locator('aside[aria-label="KAIROS 대화"] textarea')).toHaveValue('슬라이드 만들어 줘 — 주제: ')   // 길 고르기가 알아듣는 말을 미리
  await expect.poll(() => page.evaluate(() => document.activeElement?.tagName)).toBe('TEXTAREA')
  await g.getByTestId('empty-guide-KAIROS에게 묻기').click()
  await expect.poll(() => page.evaluate(() => document.activeElement?.tagName)).toBe('TEXTAREA')
  await pickShape(page, '사각형'); await dragScene(page, { x: 600, y: 600 }, { x: 700, y: 680 })
  await expect(g).toHaveCount(0)                                                                // 하나라도 놓이면 사라짐
})

test('빈 칠판 안내 × = 이 브라우저에선 다시 안 뜸', async ({ page }) => {
  await openBoard(page, boardName('guide2'), { guide: true })
  await page.getByTestId('empty-guide-close').click()
  await expect(page.getByTestId('empty-guide')).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('mb-guide-off'))).toBe('1')            // 다시 열어도 안 뜸(시험 도우미는 열 때마다 값을 새로 넣어 새로고침으로는 못 봄)
})
