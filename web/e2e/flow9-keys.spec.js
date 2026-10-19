// 흐름 9 — 글쇠 규칙표(src/next/keys.js)의 줄들이 실제로 그렇게 동작하는지. 표를 고치면 여기도.
import { test, expect } from '@playwright/test'
import { KEY_TABLE } from '../src/next/keys.js'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, liveDoc, waitSaved } from './helpers.js'

const tool = (page, label) => page.getByRole('button', { name: label, exact: true })
const rects = d => d.items.filter(it => it.type === 'rect')
async function box(page, x, y, w = 120, h = 60) { await pickShape(page, '사각형'); await dragScene(page, { x, y }, { x: x + w, y: y + h }) }

test('언제나 — Ctrl+9 다 보기 · Ctrl+0 100% · Ctrl+S 저장(브라우저 창 안 뜸) · Ctrl+P 내보내기 · F1 도움말', async ({ page }) => {
  const name = boardName('keysall')
  await openBoard(page, name); await setCam(page)
  await box(page, 0, 0); await clickScene(page, 700, 500)
  await setCam(page, { x: -5000, y: -5000, z: 1 })                     // 상자가 화면 밖으로 가게
  await page.keyboard.press('Control+9')
  let cam = await page.evaluate(() => window.__mb.getCam())
  const b = await page.getByTestId('board').boundingBox(), sx = 60 * cam.z + cam.x
  expect(sx).toBeGreaterThan(0); expect(sx).toBeLessThan(b.width)      // 멀리 있던 상자가 화면 안으로
  await page.keyboard.press('Control+0')
  cam = await page.evaluate(() => window.__mb.getCam()); expect(cam.z).toBe(1)
  let downloaded = false; page.on('download', () => { downloaded = true })
  await page.keyboard.press('Control+s'); await waitSaved(page); expect(downloaded).toBe(false)
  await page.keyboard.press('Control+p'); await expect(page.getByTestId('export-preview')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.keyboard.press('F1')
  const help = page.getByTestId('help-card')
  await expect(help).toBeVisible()
  for (const g of KEY_TABLE) await expect(help).toContainText(g.when)  // 표가 그대로 보임
  await page.keyboard.press('Escape'); await expect(help).toBeHidden()
  const p = await page.getByTestId('board').boundingBox()                // 우클릭(빈 곳) 메뉴에서도
  await page.mouse.click(p.x + 800, p.y + 600, { button: 'right' })
  await page.getByRole('button', { name: /글쇠 도움말/ }).click(); await expect(help).toBeVisible()
})

test('아무것도 안 골랐을 때 — 숫자 = 도구, Esc = 선택으로, Ctrl+A = 전체', async ({ page }) => {
  await openBoard(page, boardName('keysnone')); await setCam(page)
  await box(page, 0, 0); await box(page, 300, 0); await clickScene(page, 700, 500)
  await page.keyboard.press('2'); await expect(tool(page, '화살표')).toHaveAttribute('aria-pressed', 'true')
  await page.keyboard.press('Escape'); await expect(tool(page, '선택')).toHaveAttribute('aria-pressed', 'true')
  await page.keyboard.press('Control+a')
  expect(await page.evaluate(() => window.__mb.ed.getSel().length)).toBe(2)
})

test('글 도형 하나 골랐을 때 — 숫자·대문자도 글로, Enter = 이어 고치기, 방향키 10/1, Del = 지우기', async ({ page }) => {
  await openBoard(page, boardName('keysone')); await setCam(page)
  await box(page, 0, 0)
  await page.keyboard.type('H3')                                       // 도구 3·반전 H가 아니라 글
  await clickScene(page, 700, 500)
  let r = rects(await liveDoc(page))[0]; expect(r.label.text).toBe('H3'); await expect(tool(page, '선택')).toHaveAttribute('aria-pressed', 'true')
  await clickScene(page, 60, 30); await page.keyboard.press('Enter'); await page.keyboard.type('X'); await clickScene(page, 700, 500)
  r = rects(await liveDoc(page))[0]; expect(r.label.text).toBe('H3X')
  await clickScene(page, 60, 30)
  await page.keyboard.press('ArrowRight'); await page.keyboard.press('Shift+ArrowDown')
  r = rects(await liveDoc(page))[0]; expect(r.pos).toEqual([10, 1])
  await page.keyboard.press('Delete'); expect(rects(await liveDoc(page))).toHaveLength(0)
})

test('여럿·글 없는 것 골랐을 때 — 숫자 = 도구, Shift+H = 반전', async ({ page }) => {
  await openBoard(page, boardName('keysmany')); await setCam(page)
  await box(page, 0, 0); await box(page, 300, 0, 60, 60); await clickScene(page, 700, 500)
  await page.keyboard.press('Control+a'); await page.keyboard.press('Shift+H')
  const xs = rects(await liveDoc(page)).map(r => r.pos[0] + (r.rect[0] || 0))
  expect(xs[0]).toBeGreaterThan(xs[1])                                 // 좌우가 뒤바뀜
  await page.keyboard.press('3'); await expect(tool(page, '글자')).toHaveAttribute('aria-pressed', 'true')
})

test('고른 것 공통 — Ctrl+D 복제 · Ctrl+G 묶기 · Ctrl+L 잠그기', async ({ page }) => {
  await openBoard(page, boardName('keyscommon')); await setCam(page)
  await box(page, 0, 0); await page.keyboard.press('Escape')
  await clickScene(page, 60, 30); await page.keyboard.press('Control+d')
  let d = rects(await liveDoc(page)); expect(d).toHaveLength(2); expect(d[1].pos).toEqual([20, 20])
  await page.keyboard.press('Control+a'); await page.keyboard.press('Control+g')
  d = rects(await liveDoc(page)); expect(d[0].group_id).toBeTruthy(); expect(d[0].group_id).toBe(d[1].group_id)
  await page.keyboard.press('Control+l')
  expect(rects(await liveDoc(page)).every(r => r.locked)).toBe(true)
})
