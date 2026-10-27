// 흐름 40 — 휴대폰(2026-10-27, 폭 700 미만 = 보기·묻기·회의만): 위는 이름만 · 아래 큰 버튼 셋(다 보기·회의·KAIROS) · 왼쪽 판 없음 ·
// 한 손가락 = 화면 이동 · 두 손가락 = 확대 · 대화창은 화면 전체(「✕ 칠판」으로 닫고 다시 열기) · 끌어도 도형이 안 움직임(고치기 없음)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, liveDoc } from './helpers.js'

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })

const ANSWER = '송신소 점검은 매주 월요일이에요.'
const cam = page => page.evaluate(() => window.__mb.getCam())
// 손가락 끌기(CDP 터치) — pts = 손가락마다 [시작, 끝]
async function fingers(page, pts, steps = 8) {
  const cdp = await page.context().newCDPSession(page)
  const at = t => pts.map(([a, b], id) => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, id }))
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: at(0) })
  for (let i = 1; i <= steps; i++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: at(i / steps) })
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
}

test('휴대폰 — 큰 버튼 셋 · 손가락 이동·확대 · 고치기 없음 · 대화창 화면 전체', async ({ page }) => {
  const name = boardName('phone')
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: { gpt: [{ id: 'fake-model', price: '' }] } } }))
  await page.route('**/api/chat', r => r.fulfill({ json: { content: ANSWER, model: 'fake-model', elapsed: 0.1 } }))
  await openBoard(page, name, { chat: true })                                          // 대화창을 열어 둔 브라우저여도 휴대폰은 칠판부터
  await expect(page.getByLabel('KAIROS 대화')).toBeHidden()
  await expect(page.getByTestId('phone-top')).toContainText(name)
  const bar = page.getByTestId('phone-bar')
  for (const t of ['다 보기', '회의', 'KAIROS']) await expect(bar.getByRole('button', { name: t })).toBeVisible()
  await expect(page.getByTestId('dock-frame')).toHaveCount(0)                           // 왼쪽 판 없음
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)   // 옆으로 넘치지 않음
  await page.screenshot({ path: 'test-results/phone-empty.png' })
  expect(await page.evaluate(() => document.querySelector('meta[name=viewport]').content)).toContain('user-scalable=no')   // 브라우저 확대 막음(뭉개짐 — 10-27 사용자)
  for (const id of ['phone-top', 'phone-bar']) await expect(page.getByTestId(id)).toHaveCSS('touch-action', 'none')

  // 묻고 붙이기 — 대화창은 화면 전체, 「✕ 칠판」으로 닫고 다시 열 수 있음
  await bar.getByRole('button', { name: 'KAIROS' }).click()
  const chat = page.getByLabel('KAIROS 대화'); await expect(chat).toBeVisible()
  const cb = await chat.boundingBox(); expect(cb.width).toBeGreaterThanOrEqual(389); expect(cb.height).toBeGreaterThanOrEqual(843)
  await page.getByPlaceholder('물어보세요', { exact: false }).click(); await page.keyboard.type('송신소 점검 언제?'); await page.keyboard.press('Enter')
  await expect(page.getByText(ANSWER).first()).toBeVisible()
  await page.screenshot({ path: 'test-results/phone-chat.png' })
  await page.getByRole('button', { name: /칠판에/ }).first().click()                     // 답 = 칠판에 메모
  await expect.poll(async () => (await liveDoc(page)).items.length).toBeGreaterThan(0)
  await chat.getByRole('button', { name: '✕ 칠판' }).click(); await expect(chat).toBeHidden()

  // 한 손가락 = 화면 이동(도형은 그대로), 두 손가락 = 확대
  const before = JSON.stringify((await liveDoc(page)).items.map(it => it.pos))
  const b = await page.getByTestId('board').boundingBox(), cx = b.x + b.width / 2, cy = b.y + b.height / 2
  const c0 = await cam(page)
  await fingers(page, [[{ x: cx, y: cy }, { x: cx + 80, y: cy + 120 }]])
  const c1 = await cam(page)
  expect(c1.x - c0.x).toBeCloseTo(80, 0); expect(c1.y - c0.y).toBeCloseTo(120, 0); expect(c1.z).toBeCloseTo(c0.z, 5)
  expect(JSON.stringify((await liveDoc(page)).items.map(it => it.pos))).toBe(before)  // 끌어도 고치지 않음
  await fingers(page, [[{ x: cx - 40, y: cy }, { x: cx - 80, y: cy }], [{ x: cx + 40, y: cy }, { x: cx + 80, y: cy }]])
  expect((await cam(page)).z).toBeCloseTo(c1.z * 2, 1)                                 // 손가락 사이 80 → 160 = 두 배
  await bar.getByRole('button', { name: '다 보기' }).click()
  expect(await page.evaluate(() => window.__mb.ed.getSel())).toEqual([])                 // 고른 표시·속성 카드 없음
  await page.screenshot({ path: 'test-results/phone-board.png' })
})

test('휴대폰 — 정리 문서·웹 카드는 속 페이지를 안 띄움(아이폰에서 확대하면 카드 밖으로 쏟아졌음), 톡 누르면 새 탭', async ({ page }) => {
  await openBoard(page, boardName('phonecard'))
  await page.evaluate(() => window.__mb.ed.dropFiles([new File(['<h1>보고서</h1><p>본문</p>'], '보고서.html', { type: 'text/html' })]))
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'doc').length).toBe(1)
  await page.getByTestId('phone-bar').getByRole('button', { name: '다 보기' }).click()
  await expect(page.getByTestId('board').locator('iframe')).toHaveCount(0)               // 칠판 안 iframe 없음
  const b = await page.getByTestId('board').boundingBox(), cx = b.x + b.width / 2, cy = b.y + b.height / 2
  const pop = page.waitForEvent('popup')
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: cx, y: cy, id: 0 }] })
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  const p2 = await pop; await p2.waitForLoadState(); await expect(p2.locator('body')).toContainText('보고서')
})
