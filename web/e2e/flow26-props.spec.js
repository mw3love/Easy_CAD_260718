// 흐름 26 — 속성 카드 다듬기(2026-10-23 사용자 검토): 기본 도형 크기 = 아이콘 비율, 색은 「견본 + 코드」 한 칸 → 누르면 색 창,
// 굵기는 스테퍼 하나, 글자 굵게, KAIROS 대화창 폭 끌어서 조절
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, liveDoc } from './helpers.js'

const last = async page => { const d = await liveDoc(page); return d.items[d.items.length - 1] }

test('클릭만 해 놓으면 기본 크기 = 도형 카드 아이콘 비율 — 사각형 3:2 · 원 정원 · 삼각형 정삼각형', async ({ page }) => {
  await openBoard(page, boardName('shapewh')); await setCam(page)
  const wh = async (name, x) => { await pickShape(page, name); await clickScene(page, x, 100); const it = await last(page); await page.keyboard.press('Escape'); return it.rect.slice(2).map(v => +v.toFixed(2)) }
  expect(await wh('사각형', 0)).toEqual([120, 80])
  expect(await wh('원', 300)).toEqual([100, 100])
  expect(await wh('삼각형', 600)).toEqual([77.94, 90])
})

test('색 = 견본 + 코드 한 칸, 누르면 색 창 — 견본 한 번에 닫힘 · 코드 Enter · 채움 진하기 · Esc는 창만 닫음', async ({ page }) => {
  await openBoard(page, boardName('colorchip')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 120, y: 80 })
  await expect(page.getByTestId('chip-line')).toBeVisible()
  await expect(page.locator('button[title="#007AFF"]')).toHaveCount(0)          // 색표는 접혀 있음(전엔 세 벌이 다 펼쳐짐)
  await expect(page.locator('button[title="2 px"]')).toHaveCount(0)   // 굵기 숫자 버튼(1·2·3·5) 없음 — 스테퍼 하나
  await page.getByTestId('chip-line').click()
  await page.locator('[data-testid=pop-line] button[title="#007AFF"]').click()
  await expect(page.getByTestId('pop-line')).toHaveCount(0)                      // 견본을 누르면 바로 닫힘
  expect((await last(page)).pen.toLowerCase()).toBe('#007aff')
  await expect(page.getByTestId('chip-line')).toContainText('#007AFF')          // 지금 색이 코드로 보임

  await page.getByTestId('chip-line').click()
  await page.getByTestId('color-code').fill('D9703F'); await page.getByTestId('color-code').press('Enter')
  expect((await last(page)).pen).toBe('#d9703f')

  await page.getByTestId('chip-fill').click()
  await page.locator('[data-testid=pop-fill] button[title="#007AFF"]').click()  // 없음이던 채움에 진한 견본 = 불투명
  expect((await last(page)).fill).toBe('#ff007aff')
  await page.getByTestId('chip-fill').click()
  await page.getByTestId('fill-alpha').fill('50')                                // 진하기 50%
  expect((await last(page)).fill).toBe('#80007aff')
  await expect(page.getByTestId('chip-fill')).toContainText('50%')
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('pop-fill')).toHaveCount(0)
  await expect(page.getByTestId('chip-fill')).toBeVisible()                       // Esc는 창만 닫고 고른 것은 그대로
  await page.locator('[aria-label="선 굵기 늘리기"]').click()
  expect((await last(page)).width).toBe(2)
})

test('글자 굵게 — 도형 안 글 전체, 다시 누르면 보통(형광펜과 같이 써도 서로 안 지움)', async ({ page }) => {
  await openBoard(page, boardName('bold')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 160, y: 80 })
  await page.keyboard.type('AB'); await page.keyboard.press('Escape')
  await clickScene(page, 20, 10)
  await page.getByRole('button', { name: '굵게' }).click()
  expect((await last(page)).label.runs).toEqual([[0, 2, null, true]])
  await page.getByRole('button', { name: '형광펜' }).click()
  expect((await last(page)).label.runs[0].slice(0, 4)).toEqual([0, 2, null, true])   // 형광펜이 굵게를 안 지움
  await page.getByRole('button', { name: '굵게' }).click()
  expect((await last(page)).label.runs[0][3]).toBe(false)
})

test('KAIROS 대화창 폭 — 왼쪽 경계를 끌면 넓어지고, 다시 열어도 기억, 두 번 누르면 기본 360', async ({ page }) => {
  const name = boardName('chatw')
  await openBoard(page, name, { chat: true })
  const aside = page.getByRole('complementary', { name: 'KAIROS 대화' })
  await expect(aside).toBeVisible()
  const w0 = Math.round((await aside.boundingBox()).width)   // 360 + 왼쪽 테두리 1
  expect(w0).toBeGreaterThanOrEqual(360); expect(w0).toBeLessThanOrEqual(361)
  const h = await page.getByTestId('chat-resize').boundingBox()
  await page.mouse.move(h.x + 3, h.y + 200); await page.mouse.down(); await page.mouse.move(h.x - 150, h.y + 200, { steps: 6 }); await page.mouse.up()
  expect(Math.round((await aside.boundingBox()).width)).toBe(w0 + 153)
  await page.reload()
  await expect(aside).toBeVisible()
  expect(Math.round((await aside.boundingBox()).width)).toBe(w0 + 153)
  await page.getByTestId('chat-resize').dblclick()
  expect(Math.round((await aside.boundingBox()).width)).toBe(w0)
})
