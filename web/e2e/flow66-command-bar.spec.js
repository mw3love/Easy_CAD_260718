// 흐름 66 — 명령 찾기(Ctrl+K, 2026-11-08): 이름·초성·찾는 말로 찾기 · Enter/누르기 = 실행 · 고른 물건의 우클릭 명령도 · Esc/바깥/Ctrl+K = 닫기 · 닫은 뒤 칠판 글쇠 그대로
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, liveDoc, menuPick, openPane } from './helpers.js'

const tool = (page, label) => page.getByRole('button', { name: label, exact: true })
const bar = page => page.getByTestId('cmd-bar')
const rows = page => page.getByTestId('cmd-row')
const box = async (page, x, y) => { await pickShape(page, '사각형'); await dragScene(page, { x, y }, { x: x + 120, y: y + 60 }) }

test('열고 닫기 — Ctrl+K · 다시 Ctrl+K · Esc · 바깥 누르기, 입력 칸 안에서도 열림, 도움말 표에 있음', async ({ page }) => {
  await openBoard(page, boardName('cmdopen')); await setCam(page); await openPane(page, 'shape')   // 뒤에서 도형·심볼 검색 칸을 씀
  await page.keyboard.press('Control+k'); await expect(bar(page)).toBeVisible()
  await expect(bar(page).locator('input')).toBeFocused()
  await page.keyboard.press('Control+k'); await expect(bar(page)).toHaveCount(0)
  await page.keyboard.press('Control+k'); await page.keyboard.press('Escape'); await expect(bar(page)).toHaveCount(0)
  await page.keyboard.press('Control+k'); await clickScene(page, 700, 500); await expect(bar(page)).toHaveCount(0)
  await page.getByPlaceholder('심볼 찾기 (이름·초성)').click()
  await page.keyboard.press('Control+k'); await expect(bar(page)).toBeVisible(); await page.keyboard.press('Escape')
  await page.keyboard.press('F1'); await expect(page.getByTestId('help-card')).toContainText('Ctrl+K'); await page.keyboard.press('Escape')
})

test('찾기 — 이름·초성·띄어쓰기 없이·찾는 말, 시작하는 이름이 먼저, 없으면 안내', async ({ page }) => {
  await openBoard(page, boardName('cmdfind')); await setCam(page)
  await page.keyboard.press('Control+k')
  const inp = bar(page).locator('input')
  await inp.fill('메모'); await expect(rows(page).first()).toContainText('메모')
  await inp.fill('ㅁㅁ'); await expect(rows(page).first()).toContainText('메모')          // 초성
  await inp.fill('글쇠도움말'); await expect(rows(page).first()).toContainText('글쇠 도움말')   // 띄어쓰기 없이
  await inp.fill('pdf'); await expect(rows(page).first()).toContainText('내보내기')         // 이름에 없는 찾는 말
  await inp.fill('프레'); await expect(rows(page).first()).toContainText('프레임')          // 이름이 그 말로 시작 = 먼저
  await inp.fill('없는명령쀍'); await expect(rows(page)).toHaveCount(0); await expect(bar(page)).toContainText('그런 명령이 없어요')
})

test('실행 — Enter · ↑↓ · 누르기: 도구 바꾸기, 메모 넣기, 내보내기 창', async ({ page }) => {
  await openBoard(page, boardName('cmdrun')); await setCam(page)
  await page.keyboard.press('Control+k'); await bar(page).locator('input').fill('화살표'); await page.keyboard.press('Enter')
  await expect(bar(page)).toHaveCount(0); await expect(tool(page, '화살표')).toHaveAttribute('aria-pressed', 'true')
  await page.keyboard.press('Escape')
  await page.keyboard.press('Control+k'); await bar(page).locator('input').fill('메모'); await rows(page).first().click()
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'memo').length).toBe(1)
  await clickScene(page, 900, 600)
  await page.keyboard.press('Control+k'); await bar(page).locator('input').fill('ㄴㅂㄴㄱ'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('export-preview')).toBeVisible()
  await page.keyboard.press('Escape')
  // ↑↓ = 고르는 줄이 옮겨 감(맨 위에서 ↑ = 맨 아래)
  await page.keyboard.press('Control+k')
  const sel = () => page.locator('[data-testid=cmd-row][aria-selected=true]').innerText()
  const a = await sel(); await page.keyboard.press('ArrowDown'); expect(await sel()).not.toBe(a)
  await page.keyboard.press('ArrowUp'); await page.keyboard.press('ArrowUp')
  await expect(rows(page).last()).toHaveAttribute('aria-selected', 'true')
  await page.keyboard.press('Escape')
})

test('고른 것 — 우클릭 명령이 맨 위에, 안 고르면 없음, 실행하면 그대로', async ({ page }) => {
  await openBoard(page, boardName('cmdsel')); await setCam(page)
  await page.keyboard.press('Control+k'); await bar(page).locator('input').fill('맨 앞으로'); await expect(rows(page)).toHaveCount(0); await page.keyboard.press('Escape')
  await box(page, 0, 0); await box(page, 300, 100)
  await page.keyboard.press('Control+a')
  await page.keyboard.press('Control+k')
  await expect(rows(page).first()).toContainText('고른 것')
  await bar(page).locator('input').fill('왼쪽 맞춤'); await expect(rows(page).first()).toContainText('정렬 / 분배 › 왼쪽 맞춤')
  await page.keyboard.press('Enter'); await expect(bar(page)).toHaveCount(0)
  await expect.poll(async () => { const r = (await liveDoc(page)).items.filter(it => it.type === 'rect'); return Math.abs(r[0].pos[0] - r[1].pos[0]) }).toBeLessThan(1)
  await page.keyboard.press('Control+k'); await bar(page).locator('input').fill('묶기'); await expect(bar(page)).toContainText('묶기'); await page.keyboard.press('Enter')
  await expect.poll(async () => new Set((await liveDoc(page)).items.filter(it => it.type === 'rect').map(it => it.group_id)).size).toBe(1)
})

test('닫은 뒤 칠판 글쇠 그대로 — 찾는 칸에 친 글이 도형으로 안 들어가고, 닫으면 치는 글이 도형으로', async ({ page }) => {
  await openBoard(page, boardName('cmdkeys')); await setCam(page)
  await box(page, 0, 0)
  await page.keyboard.press('Control+k'); await page.keyboard.type('zz'); await page.keyboard.press('Escape')
  let r = (await liveDoc(page)).items.find(it => it.type === 'rect'); expect(r.label?.text || '').toBe('')
  await page.keyboard.type('A'); await clickScene(page, 700, 500)
  r = (await liveDoc(page)).items.find(it => it.type === 'rect'); expect(r.label?.text).toBe('A')
})

test('입구 — ☰ 메뉴 「명령 검색」을 누르면 열리고 Ctrl+K로 닫힘(2026-11-14 B1 — 위 막대 단추였음)', async ({ page }) => {
  await openBoard(page, boardName('cmdbtn')); await setCam(page)
  await menuPick(page, '명령 검색'); await expect(bar(page)).toBeVisible(); await expect(bar(page).locator('input')).toBeFocused()
  await page.keyboard.press('Control+k'); await expect(bar(page)).toHaveCount(0)
})

test('칠판 — 「새 칠판」은 바로 새 주소로, 내 칠판은 이름으로 찾아 옮겨 감', async ({ page }) => {
  const first = boardName('cmdfirst'), second = boardName('cmdsecond')
  await openBoard(page, first); await openBoard(page, second)
  await page.keyboard.press('Control+k'); await bar(page).locator('input').fill(first); await expect(rows(page).first()).toContainText('칠판 열기')
  await page.keyboard.press('Enter'); await expect(page).toHaveURL(new RegExp(`board=${first}$`))
  await expect.poll(() => page.evaluate(() => !!window.__mb)).toBe(true)
  await page.keyboard.press('Control+k'); await bar(page).locator('input').fill('새 칠판'); await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/board=[a-z2-9]{8}$/)
})
