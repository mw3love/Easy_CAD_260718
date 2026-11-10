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

test('휴대폰 — 정리 문서 속 페이지는 칠판 위층에(아이폰에서 SVG 안이면 확대할 때 카드 밖으로 쏟아졌음), 톡 누르면 새 탭', async ({ page }) => {
  await openBoard(page, boardName('phonecard'))
  await page.evaluate(() => window.__mb.ed.dropFiles([new File(['<h1>보고서</h1><p>본문</p>'], '보고서.html', { type: 'text/html' })]))
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'doc').length).toBe(1)
  await page.getByTestId('phone-bar').getByRole('button', { name: '다 보기' }).click()
  await expect(page.getByTestId('board').locator('iframe')).toHaveCount(0)               // 칠판(SVG) 안 iframe 없음 — 아이폰에서 확대하면 밖으로 쏟아졌음
  await expect(page.getByTestId('phone-cards').locator('iframe')).toHaveCount(1)        // 속 페이지는 위층에서 보임(10-27 사용자: 제목만이면 10개일 때 못 찾음)
  const fb = await page.getByTestId('phone-cards').locator('iframe').boundingBox(), db = await page.evaluate(() => { const r = document.querySelector('[data-doc-box]').getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height } })
  expect(fb.x).toBeGreaterThanOrEqual(db.x - 1); expect(fb.y).toBeGreaterThanOrEqual(db.y - 1); expect(fb.x).toBeLessThan(db.x + db.w)   // 카드 자리 안에서 시작
  const b = await page.getByTestId('board').boundingBox(), cx = b.x + b.width / 2, cy = b.y + b.height / 2
  const pop = page.waitForEvent('popup')
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: cx, y: cy, id: 0 }] })
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
  const p2 = await pop; await p2.waitForLoadState(); await expect(p2.locator('body')).toContainText('보고서')
})

// 2026-11-06 휴대폰 점검 — 칠판 고르기가 없었음(위 이름 = 글자뿐), 가로로 돌리면 PC 화면, 보기 링크는 휴대폰을 몰랐음, 태블릿은 손가락 확대가 없었음
const zoomOf = async page => +(await page.getByTestId('board').locator(':scope > svg').evaluate(s => s.style.transform)).match(/scale\(([\d.e-]+)\)/)[1]
const frameDoc = title => ({ format: 'easycad-doc', version: 1, title, items: [
  { type: 'frame', pos: [0, 0], rect: [0, 0, 1600, 900], name: '첫 장', no: 1, z: -1, scale: 1, rotation: 0, origin: [0, 0], locked: false, group_id: null, layer_id: null, uid: 'f1' },
  { type: 'memo', pos: [80, 80], rect: [0, 0, 500, 120], fill: '#ffffffff', lines: [{ k: 'h1', t: '송신소 점검' }], z: 1, scale: 1, rotation: 0, origin: [0, 0], locked: false, group_id: null, layer_id: null, uid: 'm1' }] })

test('휴대폰 — 위 이름 톡 = 칠판 판(새 칠판·다른 칠판으로·공유 QR) · 되돌리기 · 첫 안내는 손가락 말', async ({ page }) => {
  const a = boardName('phonesheet')
  await openBoard(page, a, { guide: true })
  await expect(page.getByTestId('empty-guide-tip')).toContainText('두 손가락')                // PC 말(끌어다 놓기·F1) 대신
  await expect(page.getByTestId('phone-undo')).toHaveCount(0)                           // 되돌리기 = 붙인 직후 알림 줄에만(위 막대 ↶ 없앰 — 2026-11-06 사용자)
  await page.evaluate(() => window.__mb.ed.dropFiles([new File(['<h1>보고서</h1>'], '보고서.html', { type: 'text/html' })]))
  await expect(page.getByTestId('phone-undo-snack')).toContainText('칠판에 붙였어요')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  await page.getByTestId('phone-undo').tap()                                            // 잘못 붙인 것 빼기
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(0)

  await expect(page.getByTestId('phone-undo-snack')).toHaveCount(0)
  await page.getByTestId('people-count').tap(); await expect(page.getByTestId('people-pop')).toBeVisible()   // 👥 = 누가 있나만(작은 메뉴)
  await expect(page.getByTestId('phone-sheet')).toHaveCount(0)
  await page.touchscreen.tap(60, 500); await expect(page.getByTestId('people-pop')).toHaveCount(0)              // 바깥 톡 = 닫힘
  // 2026-11-06 bakeoff 2라운드 — 입구 셋(이름 ▾ = 칠판 · 👥 · 공유 아이콘), 누른 자리 밑 작은 메뉴, 설명 글·코랄 채움 없음
  await page.getByTestId('phone-title').tap()
  const sheet = page.getByTestId('phone-sheet'); await expect(sheet).toBeVisible()
  const row = sheet.locator(`[data-testid=board-row][data-board="${a}"]`); await expect(row).toBeVisible()
  expect((await row.boundingBox()).height).toBeGreaterThanOrEqual(44)                     // 손가락 크기
  expect((await sheet.boundingBox()).y).toBeLessThan(80)                                  // 위 막대 바로 밑(아래에서 올라오는 큰 판 아님)
  await expect(sheet.getByTestId('share-form')).toHaveCount(0)                             // 공유는 따로
  expect(await sheet.evaluate(el => { const t = document.createElement('div'); t.style.background = 'var(--mb-accent)'; document.body.appendChild(t)
    const c = getComputedStyle(t).backgroundColor; t.remove(); return [...el.querySelectorAll('button')].filter(b => getComputedStyle(b).backgroundColor === c).length })).toBe(0)
  expect((await sheet.getByTestId('board-new').boundingBox()).y).toBeLessThan((await sheet.getByTestId('my-boards').boundingBox()).y)   // 새로 시작 = 맨 위(칠판이 많아도 안 밀림)
  await row.locator('[data-testid=board-more]').tap()
  await expect(page.getByText('이름 바꾸기')).toBeVisible()
  const item = await page.getByRole('menuitem', { name: '이름 바꾸기' }).boundingBox()
  expect(item.height).toBeGreaterThanOrEqual(44); expect(item.width).toBeLessThan(220)                       // 폰 ⋯ 메뉴 = 손가락 크기·글자 폭(PC 메뉴 최소 폭 190 아님)
  await expect(page.getByText('새 탭에서 열기')).toHaveCount(0); await expect(page.getByText('내려받기 (.ecad)')).toHaveCount(0)
  await page.screenshot({ path: 'test-results/phone-sheet.png' })
  await page.touchscreen.tap(200, 780); await expect(page.getByText('이름 바꾸기')).toHaveCount(0)   // 바깥 톡 = 줄 메뉴 닫힘
  if (await sheet.count()) await page.touchscreen.tap(200, 780)
  await expect(sheet).toHaveCount(0)
  await page.getByTestId('phone-share').tap(); const sp = page.getByTestId('phone-share-pop'); await expect(sp).toBeVisible()
  await expect(sp.getByTestId('share-url')).toContainText(`board=${a}`)                     // 주소는 정해져 있음 — 그대로 보임
  await sp.getByTestId('qr-btn').tap(); await expect(page.getByTestId('qr-big')).toBeVisible()
  await page.getByTestId('qr-big').tap(); await expect(page.getByTestId('qr-big')).toHaveCount(0)
  await expect(sp).toBeVisible()                                                           // QR을 닫아도 메뉴는 그대로
  await sp.getByTestId('publish-switch').tap(); await expect(sp.getByTestId('share-view')).toContainText('view=')   // 보기 전용 링크 = 스위치
  await sp.getByTestId('publish-switch').tap(); await expect(sp.getByTestId('share-view')).toHaveCount(0)
  await page.touchscreen.tap(200, 780); await expect(sp).toHaveCount(0)

  await page.getByTestId('phone-title').tap(); await sheet.getByTestId('board-new').tap()  // 새 칠판 = 새 주소로
  await expect.poll(() => new URL(page.url()).searchParams.get('board')).not.toBe(a)
  await expect(page.getByTestId('phone-bar')).toBeVisible()
  await page.getByTestId('phone-title').tap()
  await page.getByTestId('phone-sheet').locator(`[data-testid=board-row][data-board="${a}"]`).tap()   // 다른 칠판으로 옮겨 가기
  await expect.poll(() => new URL(page.url()).searchParams.get('board')).toBe(a)
})

test('휴대폰 — 가로로 돌려도 휴대폰 화면 · 내 칠판도 프레임이 있으면 「▶ 차례로」', async ({ browser }) => {
  const name = boardName('phoneland')
  const c = await browser.newContext({ viewport: { width: 844, height: 390 }, hasTouch: true, isMobile: true }), p = await c.newPage()
  expect((await p.request.put(`/api/doc/${name}`, { data: frameDoc('가로 시험') })).ok()).toBeTruthy()
  await openBoard(p, name)
  await expect(p.getByTestId('phone-bar')).toBeVisible()                                // 전엔 폭 750 ≥ 700이라 PC 위 막대·도구가 떴음
  await expect(p.getByTestId('dock')).toHaveCount(0)
  await expect(p.getByTestId('phone-tour')).toBeVisible()                               // 예시 칠판이 아니어도
  await p.getByTestId('phone-tour').tap(); await expect(p.getByTestId('presenter')).toBeVisible()
  await p.screenshot({ path: 'test-results/phone-landscape.png' })
  await c.close()
})

test('휴대폰 발표 — 옆으로 쓸기 = 넘기기 · 아래 막대는 가장자리에서 띄우고 손가락 크기', async ({ page }) => {   // 2026-11-06 아이폰 사용자 「넘기기 단추 안 됨·스와이프도」
  const name = boardName('phoneswipe'), d = frameDoc('쓸기 시험')
  d.items.push({ ...d.items[0], pos: [2000, 0], name: 'Deep Mode — 점심 30분 걷기, 몸에 무엇이 달라지나', no: 2, uid: 'f2' })   // 긴 장 이름 = 막대가 화면 밖으로 밀렸음(예시 칠판 5번 장)
  expect((await page.request.put(`/api/doc/${name}`, { data: d })).ok()).toBeTruthy()
  await openBoard(page, name)
  await page.getByTestId('phone-tour').tap(); const pr = page.getByTestId('presenter'); await expect(pr).toBeVisible()
  const first = await pr.getAttribute('data-cur')
  await fingers(page, [[{ x: 300, y: 400 }, { x: 80, y: 410 }]])                        // 왼쪽으로 쓸기 = 다음 장
  await expect(pr).not.toHaveAttribute('data-cur', first)
  await fingers(page, [[{ x: 80, y: 400 }, { x: 300, y: 390 }]])                        // 오른쪽으로 = 이전 장
  await expect(pr).toHaveAttribute('data-cur', first)
  const bar = await page.getByTestId('present-bar').boundingBox(), btn = await page.getByTestId('present-bar').locator('button').first().boundingBox()
  expect(844 - (bar.y + bar.height)).toBeGreaterThanOrEqual(36)                          // 아이폰 사파리 가장자리 톡 자리 피함
  expect(btn.height).toBeGreaterThanOrEqual(44)
  await fingers(page, [[{ x: 300, y: 400 }, { x: 80, y: 410 }]])                        // 긴 이름 장에서도
  for (const b of await page.getByTestId('present-bar').locator('button').all()) { const r = await b.boundingBox(); expect(r.x).toBeGreaterThanOrEqual(0); expect(r.x + r.width).toBeLessThanOrEqual(390) }
})

test('보기 링크(발표 QR 관객) — 휴대폰이면 짧은 막대·두 손가락 확대·브라우저 확대 막기', async ({ browser }) => {
  const name = boardName('phoneview')
  const pc = await browser.newContext(), pp = await pc.newPage()
  expect((await pp.request.put(`/api/doc/${name}`, { data: frameDoc('보기 시험') })).ok()).toBeTruthy()
  const tok = (await (await pp.request.post(`/api/publish/${name}`, { data: { on: true } })).json()).token; expect(tok).toBeTruthy()
  await pc.close()
  const c = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }), p = await c.newPage()
  await p.goto(`/?view=${tok}`)
  const bar = p.getByTestId('view-bar'); await expect(bar).toBeVisible()
  expect((await bar.boundingBox()).height).toBeLessThan(60)                             // 단추 글자가 두 줄로 꺾여 막대가 높았음
  await expect(bar).toContainText('보기 시험')
  expect(await p.evaluate(() => document.querySelector('meta[name=viewport]').content)).toContain('user-scalable=no')
  await expect.poll(() => zoomOf(p)).toBeGreaterThan(0)
  const z0 = await zoomOf(p), b = await p.getByTestId('board').boundingBox(), cx = b.x + b.width / 2, cy = b.y + b.height / 2
  await fingers(p, [[{ x: cx - 40, y: cy }, { x: cx - 80, y: cy }], [{ x: cx + 40, y: cy }, { x: cx + 80, y: cy }]])
  expect(await zoomOf(p) / z0).toBeCloseTo(2, 1)                                         // 손가락 사이 80 → 160
  await p.screenshot({ path: 'test-results/phone-view.png' })
  await c.close()
})

test('태블릿 — PC 화면 그대로 + 두 손가락 확대 · 빈 곳 한 손가락 = 화면 이동(도형은 그대로)', async ({ browser }) => {
  const name = boardName('tablet')
  const c = await browser.newContext({ viewport: { width: 810, height: 1080 }, hasTouch: true, isMobile: true }), p = await c.newPage()
  expect((await p.request.put(`/api/doc/${name}`, { data: frameDoc('태블릿 시험') })).ok()).toBeTruthy()
  await openBoard(p, name)
  await expect(p.getByTestId('phone-bar')).toHaveCount(0)                                // 짧은 변 810 = 태블릿
  await expect(p.getByTestId('dock')).toBeVisible()
  await p.evaluate(() => window.__mb.setCam({ x: 300, y: 600, z: 0.3 }))
  const before = JSON.stringify((await liveDoc(p)).items.map(it => it.pos))
  const b = await p.getByTestId('board').boundingBox(), x = b.x + 40, y = b.y + b.height - 80   // 칠판 왼쪽 아래 빈 곳
  const c0 = await cam(p)
  await fingers(p, [[{ x, y }, { x: x + 60, y: y - 90 }]])
  const c1 = await cam(p)
  expect(c1.x - c0.x).toBeCloseTo(60, 0); expect(c1.y - c0.y).toBeCloseTo(-90, 0)
  expect(JSON.stringify((await liveDoc(p)).items.map(it => it.pos))).toBe(before)
  await fingers(p, [[{ x: x + 40, y }, { x: x + 20, y }], [{ x: x + 120, y }, { x: x + 140, y }]])   // 80 → 120
  expect((await cam(p)).z / c1.z).toBeCloseTo(1.5, 1)
  expect(JSON.stringify((await liveDoc(p)).items.map(it => it.pos))).toBe(before)
  await c.close()
})
