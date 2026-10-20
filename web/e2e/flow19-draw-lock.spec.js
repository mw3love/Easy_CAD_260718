// 흐름 19 — 다각형·선 따라오는 선 · 빈 곳 두 번 누르기 = 글 · 잠긴 도형 하나만 풀기(2026-10-20 사용자)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, toPage, liveDoc } from './helpers.js'

const lines = page => page.getByTestId('board').locator('polyline').count()

test('다각형은 첫 클릭부터 커서를 따라오는 선이 보인다', async ({ page }) => {
  await openBoard(page, boardName('poly')); await setCam(page)
  await page.keyboard.press('5')
  const before = await lines(page)
  await clickScene(page, 0, 0)
  expect(await lines(page)).toBe(before + 1)   // 점 하나여도 그려질 모습이 보임
  const q = await toPage(page, 150, 80); await page.mouse.move(q.x, q.y, { steps: 4 })
  const pts = await page.getByTestId('board').locator('polyline').last().getAttribute('points')
  expect(pts.trim().split(/\s+/)).toHaveLength(2)
  await clickScene(page, 150, 80); await clickScene(page, 0, 150)
  await page.keyboard.press('Enter')
  expect((await liveDoc(page)).items.filter(it => it.type === 'polygon')).toHaveLength(1)
})

test('다각형 시작점 근처 = 자석(붙고 표시, 누르면 닫힘)', async ({ page }) => {
  await openBoard(page, boardName('polyclose')); await setCam(page)
  await page.keyboard.press('5')
  await clickScene(page, 0, 0); await clickScene(page, 200, 0); await clickScene(page, 200, 150)
  const near = await toPage(page, 9, 6); await page.mouse.move(near.x, near.y, { steps: 4 })   // 시작점에서 화면 약 11px
  await expect(page.getByTestId('poly-close')).toBeVisible()
  const pts = (await page.getByTestId('board').locator('polyline').last().getAttribute('points')).trim().split(/\s+/)
  expect(pts.at(-1)).toBe('0,0')   // 따라오는 선 끝이 시작점에 딱 붙음
  const far = await toPage(page, 30, 30); await page.mouse.move(far.x, far.y, { steps: 2 })
  await expect(page.getByTestId('poly-close')).toHaveCount(0)
  await page.mouse.click(near.x, near.y)
  const pg = (await liveDoc(page)).items.filter(it => it.type === 'polygon')
  expect(pg).toHaveLength(1); expect(pg[0].closed).toBe(true)
})

test('선은 클릭 두 번으로도 긋고, 그 사이 선이 따라온다', async ({ page }) => {
  await openBoard(page, boardName('line')); await setCam(page)
  await page.keyboard.press('4')
  const before = await lines(page)
  await clickScene(page, 0, 0)
  const q = await toPage(page, 200, 50); await page.mouse.move(q.x, q.y, { steps: 4 })
  expect(await lines(page)).toBe(before + 1)
  await clickScene(page, 200, 50)
  const ls = (await liveDoc(page)).items.filter(it => it.type === 'line')
  expect(ls).toHaveLength(1)
  expect(Math.round(ls[0].line[2] - ls[0].line[0])).toBe(200)
  expect(await lines(page)).toBe(before)   // 끝나면 따라오는 선은 사라짐
})

test('빈 곳을 두 번 누르면 글, 아무것도 안 쓰면 지워짐', async ({ page }) => {
  await openBoard(page, boardName('dbltext')); await setCam(page)
  const p = await toPage(page, 100, 100)
  await page.mouse.dblclick(p.x, p.y)
  await page.keyboard.type('메모 A')
  await clickScene(page, 500, 400)
  let doc = await liveDoc(page)
  expect(doc.items.filter(it => it.type === 'text')).toHaveLength(1)
  expect(JSON.stringify(doc.items[0])).toContain('메모 A')
  const r = await toPage(page, 300, 300)
  await page.mouse.dblclick(r.x, r.y)
  await clickScene(page, 500, 400)
  doc = await liveDoc(page)
  expect(doc.items.filter(it => it.type === 'text')).toHaveLength(1)
})

test('잠긴 도형 위 우클릭 = 그것만 잠금 해제', async ({ page }) => {
  await openBoard(page, boardName('lock')); await setCam(page)
  for (const x of [0, 300]) { await pickShape(page, '사각형'); await dragScene(page, { x, y: 0 }, { x: x + 150, y: 100 }); await page.keyboard.press('Escape') }
  await page.keyboard.press('Control+a')   // 다 고르고 한 번에 잠금
  await page.keyboard.press('Control+l')
  expect((await liveDoc(page)).items.every(it => it.locked)).toBe(true)
  const p = await toPage(page, 75, 50); await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.getByText('이 도형 잠금 해제').click()
  const items = (await liveDoc(page)).items.sort((a, b) => (a.pos[0] + a.rect[0]) - (b.pos[0] + b.rect[0]))
  expect(items.map(it => !!it.locked)).toEqual([false, true])
})
