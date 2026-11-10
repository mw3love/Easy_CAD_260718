// 흐름 72 — 화면 검사 5단계(글 편집, 2026-11-10): 메모 줄 메뉴·옮기기를 글쇠로(Shift+F10 · Alt+↑↓ · 「새 메모로 꺼내기」),
// 줄 종류 메뉴가 작은 창에서도 화면 안(위로 띄움·굴림·지금 종류 ✓), 표 칸을 고른 채 Shift+F10·Ctrl+K에 「행 · 열」, 메모 우클릭 = 접기·주소 열기
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc } from './helpers.js'

async function load(page, items, cam) {   // 칠판에 바로 넣고 화면을 정해진 자리로
  await page.evaluate(async its => { const d = window.__mb.toEcad(); d.items.push(...its); await window.__mb.open('data:application/json,' + encodeURIComponent(JSON.stringify(d))) }, items)
  await setCam(page, cam)
}
const MEMO = (x, y, lines, extra = {}) => ({ type: 'memo', pos: [x, y], rect: [0, 0, 220, 40], lines, ...extra })
const texts = async page => (await liveDoc(page)).items.filter(it => it.type === 'memo').map(it => it.lines.map(l => l.t))

test('메모 줄 — Esc로 고르면 알림, Alt+↑↓ = 옮기기, Shift+F10 = 줄 메뉴(옮기기·새 메모로 꺼내기)', async ({ page }) => {
  await openBoard(page, boardName('linekeys'))
  await load(page, [MEMO(0, 0, [{ k: 'p', t: '가' }, { k: 'p', t: '나' }, { k: 'p', t: '다' }])])
  await clickScene(page, 100, 15); await page.keyboard.press('Enter')                 // 고치기(커서 = 맨 끝 줄)
  await expect(page.getByTestId('memo-editor')).toBeVisible()
  await page.keyboard.press('Escape')                                                 // 그 줄 고르기
  await expect(page.getByTestId('status-toast')).toContainText('줄 1개 고름')
  await expect(page.getByTestId('status-toast')).toContainText('Shift+F10')
  await page.keyboard.press('Alt+ArrowUp')
  await expect.poll(() => texts(page)).toEqual([['가', '다', '나']])
  await page.keyboard.press('Alt+ArrowUp'); await page.keyboard.press('Alt+ArrowUp')  // 맨 위에서 더 = 그대로
  await expect.poll(() => texts(page)).toEqual([['다', '가', '나']])
  await page.keyboard.press('Alt+ArrowDown')
  await expect.poll(() => texts(page)).toEqual([['가', '다', '나']])
  await page.keyboard.press('Shift+F10')
  const menu = page.getByRole('menu')
  await expect(menu).toBeVisible()
  await expect(page.getByRole('menuitem').first()).toBeFocused()                      // 열면 첫 줄로(글쇠로 이어서)
  for (const n of ['줄 종류', '위로 옮기기', '아래로 옮기기', '새 메모로 꺼내기']) await expect(menu.getByRole('menuitem', { name: n })).toHaveCount(1)
  await menu.getByRole('menuitem', { name: '새 메모로 꺼내기' }).click()
  await expect.poll(() => texts(page)).toEqual([['가', '나'], ['다']])
})

test('줄 종류 메뉴 — 640×360에서 화면 안(위로 띄움 · 굴림), 지금 종류 ✓·그 줄부터, listbox', async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 360 })
  await openBoard(page, boardName('turnfit'))
  await load(page, [MEMO(0, 0, [{ k: 'p', t: '첫 줄' }, { k: 'h2', t: '제목 줄' }])], { x: 120, y: 220, z: 1 })   // 메모가 화면 아래쪽 = 밑이 모자람
  await clickScene(page, 100, 15); await page.keyboard.press('Enter')
  await page.keyboard.press('Control+/')
  const turn = page.getByTestId('memo-turn')
  await expect(turn).toBeVisible()
  const b = await turn.boundingBox()
  expect(b.y).toBeGreaterThanOrEqual(0); expect(b.y + b.height).toBeLessThanOrEqual(360)
  const lb = page.getByRole('listbox', { name: '줄 종류' })
  await expect(lb.getByRole('option')).toHaveCount(9)
  await expect(lb.getByRole('option', { selected: true })).toContainText('제목2')     // 커서 줄(제목2)부터
  await expect(lb.getByRole('option', { name: /제목2/ })).toContainText('✓')
  const ad = await page.getByTestId('memo-editor').locator('.ProseMirror').getAttribute('aria-activedescendant')
  expect(ad).toBeTruthy()
  for (let i = 0; i < 6; i++) await page.keyboard.press('ArrowDown')                  // 굴림 칸 안에서 고른 줄이 보이게
  const sel = lb.getByRole('option', { selected: true }), sb = await sel.boundingBox(), lbb = await lb.boundingBox()
  expect(sb.y).toBeGreaterThanOrEqual(lbb.y - 1); expect(sb.y + sb.height).toBeLessThanOrEqual(lbb.y + lbb.height + 1)
  await page.keyboard.press('Escape'); await expect(turn).toHaveCount(0)
})

test('표 칸 고른 채 — Shift+F10·Ctrl+K에 「행 · 열」', async ({ page }) => {
  await openBoard(page, boardName('cellkeys'))
  await load(page, [{ type: 'table', pos: [0, 0], scale: 1, rotation: 0, z: 1, origin: [0, 0], rect: [0, 0, 240, 90], rows: 3, cols: 2, header: false, col_widths: [0.5, 0.5], cells: [['a', 'b'], ['c', 'd'], ['e', 'f']] }])
  await clickScene(page, 700, 500); await clickScene(page, 60, 15); await clickScene(page, 60, 15)   // 표 → 첫 칸
  await page.keyboard.press('Shift+F10')
  const menu = page.getByRole('menu')
  await expect(menu.getByRole('menuitem', { name: '행 · 열' })).toHaveCount(1)
  await page.keyboard.press('Escape'); await expect(menu).toHaveCount(0)
  await page.keyboard.press('Control+k')
  await page.getByTestId('cmd-bar').locator('input').fill('아래에 행')
  await expect(page.getByTestId('cmd-row').first()).toContainText('행 · 열 › 아래에 행 넣기')
  await page.keyboard.press('Enter')
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'table').rows).toBe(4)
})

test('메모 우클릭 — 접기/펼치기 · 주소 새 탭에서 열기', async ({ page }) => {
  await openBoard(page, boardName('memomenu'))
  const lines = Array.from({ length: 9 }, (_, i) => ({ k: 'p', t: i === 0 ? '참고 https://example.com/a' : `줄 ${i}` }))
  await load(page, [MEMO(0, 0, lines, { rect: [0, 0, 260, 300] })])
  await clickScene(page, 120, 15); await page.keyboard.press('Shift+F10')
  const menu = page.getByRole('menu')
  await expect(menu.getByRole('menuitem', { name: '접기' })).toHaveCount(1)
  await expect(menu.getByRole('menuitem', { name: /주소 새 탭에서 열기/ })).toHaveCount(1)
  await menu.getByRole('menuitem', { name: '접기' }).click()
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'memo').fold).toBe(true)
  await page.keyboard.press('Shift+F10')
  await expect(page.getByRole('menu').getByRole('menuitem', { name: '펼치기' })).toHaveCount(1)
})
