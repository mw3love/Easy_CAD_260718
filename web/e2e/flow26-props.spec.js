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

test('색 칸 = 한 덩이(어디 눌러도 색 창, 열리면 바로 코드 입력) · 견본을 눌러도 창은 열린 채 · 채움 휠 = 진하기 · 바꾸면 선택선 숨김(칠판을 눌러야 다시)', async ({ page }) => {
  await openBoard(page, boardName('colorchip')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 120, y: 80 })
  await expect(page.locator('button[title="#007AFF"]')).toHaveCount(0)          // 색표는 접혀 있음(전엔 세 벌이 다 펼쳐짐)
  await expect(page.locator('button[title="2 px"]')).toHaveCount(0)             // 굵기 숫자 버튼(1·2·3·5) 없음 — 스테퍼 하나
  await page.getByTestId('chip-line').click({ position: { x: 90, y: 12 } })     // 코드 글자 자리를 눌러도 창이 열림(누를 자리가 넓게)
  const pop = page.getByTestId('pop-line')
  await expect(pop.getByTestId('color-code')).toBeFocused()                     // 열리면 코드가 골라진 채 — 바로 치면 바뀜
  await page.keyboard.type('D9703F'); await page.keyboard.press('Enter')
  expect((await last(page)).pen).toBe('#d9703f')
  await pop.locator('button[title="#007AFF"]').click()
  await expect(pop).toBeVisible()                                                // 견본을 눌러도 열린 채(눌러 가며 비교)
  expect((await last(page)).pen).toBe('#007aff')
  await pop.locator('button[title="#FF3B30"]').click()
  expect((await last(page)).pen).toBe('#ff3b30')
  await page.keyboard.press('Escape'); await expect(pop).toHaveCount(0)
  await expect(page.getByTestId('chip-line')).toContainText('FF3B30')

  expect((await page.evaluate(() => window.__mb.ed.debugState())).stylePv).toBe(true)   // 바꾼 뒤 = 선택선 숨김(바꾼 색이 보이게)
  await page.mouse.move(700, 600); await page.mouse.move(650, 560)               // 칠판으로 옮기기만 해서는 그대로(바꾼 색을 보러 가는 길)
  expect((await page.evaluate(() => window.__mb.ed.debugState())).stylePv).toBe(true)
  await clickScene(page, 60, 40)                                                 // 칠판을 누르면 다시
  await expect.poll(() => page.evaluate(() => window.__mb.ed.debugState().stylePv)).toBe(false)

  // 세 색 창 모양이 같음 — 맨 위 코드 + 색 두 줄 16칸 + 최근, 채움만 아래 「없음」·진하기
  await page.getByTestId('chip-fill').click()
  const fp = page.getByTestId('pop-fill')
  await expect(fp.getByTestId('color-grid').locator(':scope > *')).toHaveCount(16)
  await fp.getByTestId('color-grid').locator('button[title="#007AFF"]').click()  // 없음이던 채움 = 진하기 1/3
  expect((await last(page)).fill).toBe('#55007aff')
  await page.getByTestId('fill-alpha').fill('50')
  expect((await last(page)).fill).toBe('#80007aff')
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('chip-fill')).toContainText('50%')
  await page.getByTestId('chip-fill').hover(); await page.mouse.wheel(0, -100)    // 휠 = 진하기 5%씩
  await expect.poll(async () => (await last(page)).fill).toBe('#8c007aff')
  await expect(page.getByTestId('chip-fill')).toBeVisible()
  await page.getByTestId('chip-fill').click(); await page.getByTestId('fill-none').click()
  expect((await last(page)).fill ?? null).toBeNull()
  await page.keyboard.press('Escape')
  await page.locator('[aria-label="선 굵기 늘리기"]').click()
  expect((await last(page)).width).toBe(2)
})

test('글 고치는 중에도 속성 카드 — 「글자」 꾸밈 버튼 = 꾸미기 막대와 같은 줄, 드래그한 부분에만 먹음', async ({ page }) => {
  await openBoard(page, boardName('editprops')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 200, y: 80 })
  await page.keyboard.type('ABCD')                                               // 고치는 중(아직 안 끝냄)
  await expect(page.getByTestId('props-fmt')).toBeVisible()                       // 전엔 고치는 중엔 속성 카드가 숨었음
  await page.keyboard.press('Shift+ArrowLeft'); await page.keyboard.press('Shift+ArrowLeft')   // 「CD」만 고름
  const bar = await page.getByTestId('format-bar').locator('button').evaluateAll(bs => bs.map(b => b.getAttribute('aria-label')))
  const card = await page.getByTestId('props-fmt').locator('button').evaluateAll(bs => bs.map(b => b.getAttribute('aria-label')))
  expect(card).toEqual(bar.filter(n => n !== '글자색'))                          // 같은 항목(글자색은 카드에선 「색」 줄)
  await page.getByTestId('pfmt-굵게').click()
  await page.keyboard.press('Escape')
  expect((await last(page)).label.runs).toEqual([[2, 2, null, true]])            // 고른 「CD」에만
})

test('색 창은 카드 밖에 떠서 안 잘림 — 카드 아래쪽 글자 색도 화면 안, 카드에 스크롤 안 생김', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 640 })
  await openBoard(page, boardName('popclip')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 160, y: 80 })
  await page.keyboard.type('글'); await page.keyboard.press('Escape'); await clickScene(page, 10, 10)
  await page.getByTestId('chip-text').click()
  const b = await page.getByTestId('pop-text').boundingBox()
  expect(b.y + b.height).toBeLessThanOrEqual(640)                                  // 화면 아래로 안 잘림(모자라면 위로 펼침)
  expect(b.y).toBeGreaterThanOrEqual(0)
  const scroll = await page.getByTestId('chip-text').evaluate(el => { let p = el; while (p && !(p.dataset && 'folded' in p.dataset) && !(p.style && p.style.overflowY === 'auto')) p = p.parentElement; return p ? p.scrollHeight - p.clientHeight : -1 })
  expect(scroll).toBeLessThanOrEqual(1)
})

test('글이 상자에 꽉 찼을 때 크기를 키우면 상자 폭이 같이 늘어남(가운데 그대로) — 카드 숫자 = 보이는 크기', async ({ page }) => {
  await openBoard(page, boardName('labelgrow')); await setCam(page)
  await pickShape(page, '사각형'); await clickScene(page, 200, 100)
  await page.keyboard.type('가나다라마바사'); await page.keyboard.press('Escape'); await clickScene(page, 160, 70)
  const r0 = (await last(page)).rect, cx0 = r0[0] + r0[2] / 2
  for (let i = 0; i < 8; i++) await page.locator('[aria-label="글자 크기 늘리기"]').click()
  const it = await last(page)
  expect(it.rect[2]).toBeGreaterThan(r0[2])                                        // 상자가 넓어짐
  expect(it.rect[0] + it.rect[2] / 2).toBeCloseTo(cx0, 3)                           // 가운데 그대로
  await expect(page.getByTestId('font-step')).toContainText(it.label.font + 'pt')  // 저장값 = 보이는 크기(전엔 42pt인데 17pt로 보였음)
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

test('−/+ 누르고 있으면 계속(되돌리기 한 번) · 숫자 두 번 누르면 직접 입력 · 선 모양은 골라도 목록이 열린 채 · 꾸밈 지우기 없음', async ({ page }) => {
  await openBoard(page, boardName('stepper')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 160, y: 80 })
  const plus = page.locator('[aria-label="선 굵기 늘리기"]')
  await plus.hover(); await page.mouse.down(); await page.waitForTimeout(900); await page.mouse.up()
  const w = (await last(page)).width
  expect(w).toBeGreaterThan(4)                                                   // 0.4초 뒤부터 계속 늘어남
  await page.waitForTimeout(300); expect((await last(page)).width).toBe(w)       // 떼면 멈춤
  await page.mouse.move(700, 600); await page.keyboard.press('Control+z')
  expect((await last(page)).width ?? 1).toBe(1)                                   // 되돌리기 한 번에 통째로
  await page.getByTestId('width-step-value').dblclick()
  const inp = page.getByTestId('width-step-input'); await expect(inp).toBeFocused()
  await page.keyboard.type('7'); await page.keyboard.press('Enter')
  expect((await last(page)).width).toBe(7)

  await page.getByRole('button', { name: '선 모양' }).click()
  await page.getByRole('button', { name: '점선' }).click()
  await expect(page.getByRole('button', { name: '도트' })).toBeVisible()           // 골라도 열린 채(눌러 가며 비교)
  await page.getByRole('button', { name: '도트' }).click()
  expect((await last(page)).style).toBe(3)
  await page.keyboard.press('Escape'); await expect(page.getByRole('button', { name: '도트' })).toHaveCount(0)

  await page.keyboard.type('글'); await page.keyboard.press('Escape'); await clickScene(page, 10, 10)
  await expect(page.getByTestId('props-fmt')).toBeVisible()
  await expect(page.getByTestId('pfmt-꾸밈')).toHaveCount(0)                    // 꾸밈 지우기 뺌(각 버튼을 다시 누르면 풀림)
  const f0 = (await last(page)).label.font
  await page.getByTestId('font-step-value').dblclick(); await page.keyboard.type('30'); await page.keyboard.press('Escape')   // Esc = 취소
  await expect(page.getByTestId('font-step-input')).toHaveCount(0)
  expect((await last(page)).label.font).toBe(f0)
  await page.getByTestId('font-step-value').dblclick(); await page.keyboard.type('20'); await page.keyboard.press('Enter')
  expect((await last(page)).label.font).toBe(20)
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
