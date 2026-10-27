// 흐름 41 — 10-27 사용자 UI 점검: 프레임으로 감싸면 안에 든 것으로 이름 · 레이어 판의 「선택 → 그리는 중」 단추 뺌(우클릭 「레이어로 이동」이 같은 일) ·
// 칠판 칸 = 「＋ 새 칠판」 먼저 · 접속자 = 이름 첫 글자 동그라미(4칸 넘으면 +N)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, clickScene, pickShape, dragScene, toPage } from './helpers.js'

const frames = async page => (await liveDoc(page)).items.filter(it => it.type === 'frame')

test('프레임으로 감싸기 = 안에 든 것으로 이름(하나 = 종류 · 제목, 여럿 = 가장 많은 것 외 N)', async ({ page }) => {
  await openBoard(page, boardName('fname')); await setCam(page)
  const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII='
  await page.evaluate(async png => {
    const d = window.__mb.toEcad()
    d.items.push({ type: 'web', pos: [0, 0], rect: [0, 0, 300, 200], url: 'https://news.kbs.co.kr', title: 'KBS 뉴스' },
      { type: 'image', pos: [400, 0], rect: [0, 0, 100, 80], data: png }, { type: 'image', pos: [550, 0], rect: [0, 0, 100, 80], data: png })
    await window.__mb.open('data:application/json,' + encodeURIComponent(JSON.stringify(d)))
  }, PNG)
  await setCam(page)
  await clickScene(page, 150, 100); await page.keyboard.press('Alt+g')
  await expect.poll(async () => (await frames(page)).map(f => f.name)).toEqual(['웹 · KBS 뉴스'])
  await clickScene(page, 1000, 600); await dragScene(page, { x: 380, y: -30 }, { x: 680, y: 110 }); await page.keyboard.press('Alt+g')
  await expect.poll(async () => (await frames(page)).map(f => f.name).sort()).toEqual(['웹 · KBS 뉴스', '이미지 2개'].sort())
})

test('레이어 판엔 「선택 → 그리는 중」 단추 없음 · 우클릭 「레이어로 이동」은 있음', async ({ page }) => {
  await openBoard(page, boardName('layerbtn')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 150, y: 100 }); await page.keyboard.press('Escape')
  await page.getByTestId('dock-layer').click(); await expect(page.getByRole('button', { name: '＋ 레이어' })).toBeVisible()
  await expect(page.getByRole('button', { name: '선택 → 그리는 중' })).toHaveCount(0)
  const p = await toPage(page, 75, 50); await page.mouse.click(p.x, p.y, { button: 'right' })
  expect((await page.locator('div[style*="z-index: 30"] > div > button').allInnerTexts()).some(n => n.startsWith('레이어로 이동'))).toBe(true)
})

test('칠판 칸 — 처음엔 이름 칸 없음 · 「＋ 새 칠판」 → 이름 칸 · Esc = 닫힘', async ({ page }) => {
  await openBoard(page, boardName('newboard'))
  await page.getByTestId('board-title').click()
  const form = page.getByTestId('board-form'), inp = form.getByPlaceholder('새 칠판 이름', { exact: false })
  await expect(inp).toHaveCount(0)
  await form.getByTestId('board-new').click(); await expect(inp).toBeFocused()
  await inp.press('Escape'); await expect(inp).toHaveCount(0); await expect(form.getByTestId('board-new')).toBeVisible()
  await expect(form.getByRole('button', { name: '파일 열기' })).toBeVisible()
})

test('접속자 = 동그라미 — 5명이면 3명 + 「+2」, 누르면 공유 창(전체 목록)', async ({ page, browser }) => {
  const name = boardName('faces'), ctxs = []
  await openBoard(page, name, { who: '가' })
  for (const w of ['나', '다', '라', '마']) { const c = await browser.newContext(); ctxs.push(c); await openBoard(await c.newPage(), name, { who: w }) }
  const who = page.getByTestId('people')
  await expect(who).toHaveAttribute('title', /5명/, { timeout: 6000 })
  await expect(who).toContainText('+2')
  await who.click(); await expect(page.getByText('지금 이 칠판에 5명')).toBeVisible()
  for (const c of ctxs) await c.close()
})

test('내 심볼(이 브라우저) — 우클릭 추가 → 판에 보임 → 놓기 · 새로 고쳐도 남음 · 이름 바꾸기 · 파일로 저장 → 지우기 → 불러오기', async ({ page }) => {
  await openBoard(page, boardName('mysym')); await setCam(page)
  await pickShape(page, '원'); await dragScene(page, { x: 0, y: 0 }, { x: 120, y: 80 }); await page.keyboard.press('Escape')
  await clickScene(page, 60, 40); const p = await toPage(page, 60, 40); await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.locator('div[style*="z-index: 30"] > div > button', { hasText: '내 심볼에 추가' }).click()
  const dlg = page.getByTestId('symadd'); await expect(dlg).toBeVisible()
  await dlg.getByPlaceholder('예: 송신탑').fill('동그라미'); await dlg.getByRole('button', { name: '추가' }).click()
  const mine = page.getByTestId('mine'); await expect(mine.getByRole('button', { name: '동그라미' })).toBeVisible()   // 폴더 없으면 「내 심볼」
  await expect(mine).toContainText('내 심볼')
  const n0 = (await liveDoc(page)).items.length
  await mine.getByRole('button', { name: '동그라미' }).click(); await clickScene(page, 400, 300)
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(n0 + 1)
  await page.reload(); await expect(page.getByTestId('mine').getByRole('button', { name: '동그라미' })).toBeVisible()   // 이 브라우저에 남음
  await page.getByTestId('mine').getByRole('button', { name: '동그라미' }).click({ button: 'right' })
  await page.getByTestId('mine-pop').getByRole('button', { name: '이름 바꾸기' }).click()
  await page.getByTestId('mine-pop').locator('input').fill('원 심볼'); await page.getByTestId('mine-pop').locator('input').press('Enter')
  await expect(page.getByTestId('mine').getByRole('button', { name: '원 심볼' })).toBeVisible()
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('mine').getByRole('button', { name: '파일로 저장' }).click()])
  const path = await dl.path()
  await page.getByTestId('folder-menu').click(); await page.getByTestId('mine-pop').getByRole('button', { name: /지우기/ }).click()
  await expect(page.getByTestId('mine').getByRole('button', { name: '원 심볼' })).toHaveCount(0)
  await page.getByTestId('mine').locator('input[type=file]').setInputFiles(path)
  await expect(page.getByTestId('mine').getByRole('button', { name: '원 심볼' })).toBeVisible()
})
