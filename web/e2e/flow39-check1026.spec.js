// 흐름 39 — 10-26 실검증 손질: 스타일 복사 Alt+C/V(Ctrl+Alt+C = 윈도 Copilot) · 발표 레이저(끌면 빨간 자취·글 선택 안 잡힘, 도구를 켜면 그 커서) ·
// 대화창 「취소」 한 줄(긴 진행 글에 눌려 세로였음) · 창을 닫으면 접속자 이름이 바로 빠짐(전엔 20초쯤 남음) · 선을 고르고 우클릭 「범례 넣기」(10-27)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, pickShape, dragScene, liveDoc, toPage } from './helpers.js'

const menuBtns = page => page.locator('div[style*="z-index: 30"] > div > button').allInnerTexts()

test('스타일 복사·붙여넣기 = Alt+C / Alt+V', async ({ page }) => {
  await openBoard(page, boardName('stylekey')); await setCam(page)
  for (const x of [0, 300]) { await pickShape(page, '사각형'); await dragScene(page, { x, y: 0 }, { x: x + 160, y: 80 }); await page.keyboard.press('Escape') }
  await clickScene(page, 700, 500)
  await clickScene(page, 80, 40); await page.keyboard.press('Alt+c')
  await expect(page.getByText('스타일 복사됨').first()).toBeVisible()
  await clickScene(page, 380, 40); await page.keyboard.press('Alt+v')
  await expect(page.getByText('스타일 붙여넣기 — 1개').first()).toBeVisible()
})

test('발표 레이저 — 끌면 빨간 자취(글 선택 안 잡힘), 펜을 켜면 십자 커서·끄면 다시 레이저', async ({ page }) => {
  await openBoard(page, boardName('laser')); await setCam(page, { x: 320, y: 300, z: 0.5 })
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 600, y: 300 })
  await page.keyboard.type('레이저로 가리키는 글 한 줄'); await clickScene(page, 300, 700)
  await page.getByRole('button', { name: '프레임', exact: true }).click()
  await dragScene(page, { x: -40, y: -40 }, { x: 640, y: 340 })
  await clickScene(page, 300, 700)
  await page.getByRole('button', { name: '발표', exact: true }).click()
  const pres = page.getByTestId('presenter'); await expect(pres).toBeVisible()
  const vp = page.viewportSize()
  await page.keyboard.press('l'); await page.mouse.move(vp.width * 0.3, vp.height * 0.5)
  await expect(page.getByTestId('laser')).toBeVisible()
  await page.mouse.down(); await page.mouse.move(vp.width * 0.7, vp.height * 0.5, { steps: 10 })
  await expect(page.getByTestId('laser-trail')).toBeVisible()
  await page.mouse.up()
  expect(await page.evaluate(() => getSelection().toString())).toBe('')                     // 전엔 글이 파랗게 골라졌음
  await expect(page.getByTestId('laser-trail')).toBeHidden({ timeout: 2000 })               // 0.6초 뒤 사라짐
  await page.keyboard.press('1'); await page.mouse.move(vp.width * 0.4, vp.height * 0.4)      // 펜
  await expect(page.getByTestId('laser')).toBeHidden()
  await expect(pres).toHaveCSS('cursor', 'crosshair')
  await page.keyboard.press('Escape'); await page.mouse.move(vp.width * 0.5, vp.height * 0.4)  // 펜 끔 = 다시 레이저
  await expect(page.getByTestId('laser')).toBeVisible()
})

test('기다리는 동안 「취소」는 한 줄(진행 글이 길어도 — 정리 문서·인터랙티브 HTML처럼)', async ({ page }) => {
  const LONG = 'fake-model-with-a-long-name'
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { live: LONG } } }))
  await page.route('**/api/chat', () => {})   // 답이 안 옴
  await page.addInitScript(() => { try { localStorage.setItem('mb-chat-w', '320') } catch {} })   // 가장 좁은 대화창
  await openBoard(page, boardName('stopwrap'), { chat: true })
  await page.getByTestId('plus').click(); await page.getByRole('menuitemradio', { name: /인터랙티브 HTML/ }).click()
  await page.getByTestId('tool-chip').waitFor()
  await page.getByPlaceholder('무엇을 움직여 볼까요', { exact: false }).click(); await page.keyboard.type('진자 운동'); await page.keyboard.press('Enter')
  const stop = page.getByTestId('chat-stop'); await expect(stop).toBeVisible()
  await expect(page.getByTestId('chat-busy')).toContainText(LONG)
  const b = await stop.boundingBox()
  expect(b.width).toBeGreaterThan(b.height)                                                  // 세로로 「취/소」가 아님
  expect(b.height).toBeLessThan(30)
})

test('창을 닫으면 접속자 이름이 바로 빠짐', async ({ browser }) => {
  const name = boardName('leave')
  const ca = await browser.newContext(), cb = await browser.newContext()
  const a = await ca.newPage(), b = await cb.newPage()
  await openBoard(a, name, { who: '기자' }); await openBoard(b, name, { who: '작가' })
  const who = a.getByText('👥', { exact: false }).first()
  await expect(who).toContainText('작가', { timeout: 4000 })
  await b.goto('about:blank')                                                                // 탭 닫기와 같음(pagehide)
  await expect(who).not.toContainText('작가', { timeout: 3000 })                             // 전엔 15초 넘게 남았음
  await ca.close(); await cb.close()
})

test('선을 고르고 우클릭 「범례 넣기」(표 창 안에만 있으면 못 찾음)', async ({ page }) => {
  await openBoard(page, boardName('legendmenu')); await setCam(page)
  await page.keyboard.press('2'); await dragScene(page, { x: 0, y: 0 }, { x: 200, y: 0 }); await page.keyboard.press('Escape')
  await clickScene(page, 700, 500); await clickScene(page, 100, 0)
  const p = await toPage(page, 100, 0); await page.mouse.click(p.x, p.y, { button: 'right' })
  const names = await menuBtns(page)
  expect(names.some(n => n.startsWith('범례 넣기'))).toBe(true)
  await page.locator('div[style*="z-index: 30"] > div > button', { hasText: '범례 넣기' }).click()
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'legend').length).toBe(1)
  await clickScene(page, 700, 500); const q = await toPage(page, 700, 500); await page.mouse.click(q.x, q.y, { button: 'right' })
  expect((await menuBtns(page)).some(n => n.startsWith('범례'))).toBe(false)                // 선을 안 고르면 없음
})

test('도구 유지(Q·「유지」) — 켜면 그린 뒤에도 그 도구, 도구를 바꿔도 그대로, Esc = 선택 · 끄면 하나 그리고 선택으로', async ({ page }) => {
  await openBoard(page, boardName('keeptool')); await setCam(page)
  const count = async t => (await liveDoc(page)).items.filter(it => it.type === t).length
  await page.keyboard.press('q'); await expect(page.getByText('도구 유지 켬', { exact: false }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: '유지', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await pickShape(page, '사각형')
  await dragScene(page, { x: 0, y: 0 }, { x: 100, y: 60 }); await dragScene(page, { x: 200, y: 0 }, { x: 300, y: 60 })
  expect(await count('rect')).toBe(2)                                                        // 다시 고르지 않고 둘
  await page.keyboard.press('Escape'); await page.keyboard.press('4')                        // 도구를 바꿔도 유지
  await dragScene(page, { x: 0, y: 200 }, { x: 100, y: 200 }); await dragScene(page, { x: 0, y: 260 }, { x: 100, y: 260 })
  expect(await count('line')).toBe(2)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('button', { name: '선택', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: '유지', exact: true }).click()                      // 끄기
  await pickShape(page, '사각형'); await dragScene(page, { x: 400, y: 0 }, { x: 500, y: 60 }); await dragScene(page, { x: 600, y: 0 }, { x: 700, y: 60 })
  expect(await count('rect')).toBe(3)                                                        // 둘째 끌기는 고르기
})

test('내 심볼 칸 — 제목 줄 누르면 접힘(새로고침해도 그대로) · 심볼에 마우스를 올리면 크게 보기', async ({ page }) => {
  await openBoard(page, boardName('palfold'))
  const sec = page.getByTestId('pal-sec').filter({ hasText: '방송·기술' })
  await expect(sec.getByRole('button', { name: '카메라' })).toBeVisible()
  await sec.getByRole('button', { name: '카메라' }).hover()
  await expect(page.getByTestId('sym-peek')).toContainText('카메라')
  await page.screenshot({ path: 'test-results/sym-peek.png' })
  await page.mouse.move(800, 600); await expect(page.getByTestId('sym-peek')).toBeHidden()
  await sec.getByText('방송·기술').click()
  await expect(sec).toHaveAttribute('data-shut', 'true'); await expect(sec.getByRole('button', { name: '카메라' })).toHaveCount(0)
  await page.reload(); await expect(page.getByTestId('pal-sec').filter({ hasText: '방송·기술' })).toHaveAttribute('data-shut', 'true')
  await page.getByTestId('pal-sec').filter({ hasText: '방송·기술' }).getByText('방송·기술').click()
  await expect(page.getByTestId('pal-sec').filter({ hasText: '방송·기술' }).getByRole('button', { name: '카메라' })).toBeVisible()
})
