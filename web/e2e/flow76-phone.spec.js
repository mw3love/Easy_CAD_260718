// 흐름 76 — 화면 검사 9단계(휴대폰, 2026-11-11): 답 카드 「되돌리기」(시간 제한 없음) · 톡 뒤 회색 없음 · 판 초점·Esc · 화면 전체 대화창 = 진짜 창 ·
// 회의 끝내기 색 · 보기 화면 단추 이름·불러오기 글 · 공유 HTML 휴대폰 발표(◀▶ 보임·톡·쓸기) · 가로 폰 첫 빈 틀 = 폰 · 문서 카드 톡 = 앱 안 보기 창 ·
// 가로 폰 발표 장이 막대에 안 덮임 · 장 목록 닫기 · 누르는 자리(휴대폰 44 · 태블릿 손가락 32 이상 · 마우스 PC 그대로 24)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, liveDoc } from './helpers.js'
import { buildHtml } from '../src/next/htmlshare.js'

test.use({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] }, permissions: ['microphone'] })

const ANSWER = '송신소 점검은 매주 월요일이에요.'
const DANGER_RGB = 'rgb(185, 52, 47)'
const frameDoc = (title, n = 2) => ({ format: 'easycad-doc', version: 1, title, items: [
  ...Array.from({ length: n }, (_, k) => ({ type: 'frame', pos: [k * 2000, 0], rect: [0, 0, 1600, 900], name: `${k + 1}장`, no: k + 1, z: -1, scale: 1, rotation: 0, origin: [0, 0], locked: false, group_id: null, layer_id: null, uid: 'f' + k })),
  { type: 'memo', pos: [80, 80], rect: [0, 0, 500, 120], fill: '#ffffffff', lines: [{ k: 'h1', t: '송신소 점검' }], z: 1, scale: 1, rotation: 0, origin: [0, 0], locked: false, group_id: null, layer_id: null, uid: 'm1' }] })
// 누르는 자리 = 단추 상자 + `.mb-hit::after` 둘레(index.html)
const hitBox = loc => loc.evaluate(el => { const r = el.getBoundingClientRect(), a = getComputedStyle(el, '::after'), px = v => (a.content === 'none' || v === 'auto' ? 0 : -parseFloat(v) || 0)
  return { w: r.width + px(a.left) + px(a.right), h: r.height + px(a.top) + px(a.bottom) } })

test('대화창 답 「되돌리기」 = 시간이 지나도 그 답으로 붙인 것만 빠짐 · 화면 전체 대화창 = 진짜 창 · 톡 뒤 회색 없음', async ({ page }) => {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: { gpt: [{ id: 'fake-model', price: '' }] } } }))
  await page.route('**/api/chat', r => r.fulfill({ json: { content: ANSWER, model: 'fake-model', elapsed: 0.1 } }))
  await openBoard(page, boardName('phoneunpin'))
  await expect(page.getByTestId('phone-undo-live')).toHaveAttribute('role', 'status')   // 알림 칸은 미리 있음(글만 바뀜)
  await page.getByTestId('phone-kairos').tap()
  const chat = page.getByLabel('KAIROS 대화'); await expect(chat).toBeVisible()
  await expect(chat).toHaveAttribute('role', 'dialog'); await expect(chat).toHaveAttribute('aria-modal', 'true')
  expect(await page.evaluate(() => document.activeElement?.tagName === 'TEXTAREA' && !!document.activeElement.closest('.mb-chat'))).toBe(true)   // 열면 입력 칸
  expect(await page.evaluate(() => !!document.querySelector('[data-testid=phone-bar]').closest('[inert]'))).toBe(true)   // 뒤는 inert
  await page.keyboard.type('송신소 점검 언제?'); await page.keyboard.press('Enter')
  await expect(page.getByText(ANSWER).first()).toBeVisible()
  // 톡 뒤 회색 바탕이 남지 않음(마우스 올림 = 마우스일 때만)
  const ms = chat.getByTestId('model-settings'); await ms.tap(); await ms.tap()
  expect(await ms.evaluate(el => el.style.background || '')).not.toContain('var(--mb-group)')
  const close = chat.getByRole('button', { name: '대화창 닫기 — 칠판으로' })
  expect((await hitBox(close)).h).toBeGreaterThanOrEqual(44)                             // 화면 전체 대화창 작은 단추 = 누르는 자리 44
  await chat.getByRole('button', { name: '칠판에 붙이기' }).first().tap()
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  await page.waitForTimeout(7500)                                                       // 알림 줄(7초)이 사라진 뒤에도
  await expect(page.getByTestId('phone-undo-snack')).toHaveCount(0)
  const un = chat.getByTestId('answer-unpin'); await expect(un).toBeVisible(); expect((await hitBox(un)).h).toBeGreaterThanOrEqual(44)
  await un.tap()
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(0)
  await expect(chat.getByTestId('answer-pin-note').first()).toContainText('칠판에서 뺐어요')
  await expect(chat.getByRole('button', { name: '칠판에 붙이기' }).first()).toBeVisible()   // 다시 붙이기로 돌아감
  await close.tap(); await expect(chat).toBeHidden()
  await expect.poll(() => page.evaluate(() => document.activeElement?.dataset.testid)).toBe('phone-kairos')   // 닫으면 KAIROS 단추로
  expect(await page.evaluate(() => document.querySelector('[inert]'))).toBeNull()
})

test('손으로 고친 붙인 카드는 되돌리기에서 남김', async ({ page }) => {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => r.fulfill({ json: { content: ANSWER, model: 'fake-model', elapsed: 0.1 } }))
  await openBoard(page, boardName('phoneunpin2'))
  await page.getByTestId('phone-kairos').tap(); await page.keyboard.type('질문'); await page.keyboard.press('Enter')
  const chat = page.getByLabel('KAIROS 대화'); await chat.getByRole('button', { name: '칠판에 붙이기' }).first().tap()
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  await page.evaluate(() => { const it = window.__mb.ed.liveModel().items[0]; window.__mb.ed.setFields(it._id, { fill: '#ffeeaaff' }, '색') })   // 손으로 고침
  await chat.getByTestId('answer-unpin').tap()
  await expect(chat.getByTestId('answer-pin-note').first()).toContainText('손으로 고친 1개는 남겼어요')
  expect((await liveDoc(page)).items).toHaveLength(1)
})

test('휴대폰 판 — 연 단추 aria-expanded · 열면 판 안으로 초점 · Esc = 닫고 연 단추로 · 위 막대·스위치 누르는 자리 44', async ({ page }) => {
  await openBoard(page, boardName('phonepop'))
  const t = page.getByTestId('phone-title')
  await expect(t).toHaveAttribute('aria-expanded', 'false')
  for (const id of ['phone-title', 'phone-share', 'people-count']) { const h = await hitBox(page.getByTestId(id)); expect(h.h).toBeGreaterThanOrEqual(44); expect(h.w).toBeGreaterThanOrEqual(42) }
  await t.tap(); await expect(page.getByTestId('phone-sheet')).toBeVisible(); await expect(t).toHaveAttribute('aria-expanded', 'true')
  expect(await page.evaluate(() => !!document.activeElement?.closest('[data-testid=phone-sheet]'))).toBe(true)
  await page.keyboard.press('Escape'); await expect(page.getByTestId('phone-sheet')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => document.activeElement?.dataset.testid)).toBe('phone-title')
  await page.getByTestId('phone-share').tap(); const sp = page.getByTestId('phone-share-pop'); await expect(sp).toBeVisible()
  const sw = sp.getByTestId('publish-switch'); await expect(sw).toBeEnabled()
  const hs = await hitBox(sw); expect(hs.h).toBeGreaterThanOrEqual(44); expect(hs.w).toBeGreaterThanOrEqual(44)
  expect(await sw.evaluate(el => getComputedStyle(el).backgroundColor)).toBe(await page.evaluate(() => { const d = document.createElement('div'); d.style.background = 'var(--mb-ctl)'; document.body.appendChild(d); const c = getComputedStyle(d).backgroundColor; d.remove(); return c }))   // 꺼짐 = --mb-ctl
  await expect(sp.getByTestId('phone-share-msg')).toHaveAttribute('role', 'status')
  for (const b of await sp.locator('button.mb-hit').all()) expect((await hitBox(b)).h).toBeGreaterThanOrEqual(44)
  await page.keyboard.press('Escape'); await expect(sp).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => document.activeElement?.dataset.testid)).toBe('phone-share')
})

test('회의 「끝내기」 = 지우기 빨강(DANGER)', async ({ page }) => {
  await page.route('**/api/stt-token', r => r.fulfill({ json: { url: 'ws://127.0.0.1:5291/fake-stt?token=t', model: 'stt-rt-v5' } }))
  await page.routeWebSocket('**/fake-stt**', ws => { ws.onMessage(() => {}) })
  await openBoard(page, boardName('phonemeet'))
  await page.getByTestId('phone-bar').getByRole('button', { name: '회의' }).tap()
  const end = page.getByTestId('phone-bar').getByRole('button', { name: '끝내기' }); await expect(end).toBeVisible()
  await expect(end).toHaveCSS('background-color', DANGER_RGB)
})

test('보기 화면 — 불러오는 중 글 · 이어서 못 받으면 연결 안내 · 단추 이름', async ({ browser }) => {
  const name = boardName('phoneviewer')
  const pc = await browser.newContext(), pp = await pc.newPage()
  expect((await pp.request.put(`/api/doc/${name}`, { data: frameDoc('보기 시험') })).ok()).toBeTruthy()
  const tok = (await (await pp.request.post(`/api/publish/${name}`, { data: { on: true } })).json()).token; await pc.close()
  const c = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }), p = await c.newPage()
  await p.route('**/api/pub/**', r => r.abort('internetdisconnected'))
  await p.goto(`/?view=${tok}`)
  const ld = p.getByTestId('view-loading'); await expect(ld).toHaveAttribute('role', 'status')
  await expect(ld).toContainText('연결이 안 돼요 — 인터넷을 확인해 주세요', { timeout: 8000 })
  await p.unroute('**/api/pub/**')
  const bar = p.getByTestId('view-bar'); await expect(bar).toBeVisible({ timeout: 8000 })
  await expect(bar.getByRole('button', { name: '다 보기' })).toBeVisible()
  await expect(bar.getByRole('button', { name: '어둡게' })).toBeVisible()
  await bar.getByRole('button', { name: '어둡게' }).tap(); await expect(bar.getByRole('button', { name: '밝게' })).toBeVisible()
  for (const b of await bar.getByRole('button').all()) expect((await hitBox(b)).h).toBeGreaterThanOrEqual(44)
  await c.close()
})

test('공유 HTML 휴대폰 발표 — ◀▶ 늘 보임 · 톡(왼쪽 1/3 = 이전) · 옆으로 쓸기 · 칠판 두 손가락 확대', async ({ page }) => {
  const svg = c => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 90"><rect width="160" height="90" fill="${c}"/></svg>`
  await page.setContent(buildHtml({ title: '공유 시험', made: '오늘', overview: svg('#eee'), slides: [{ svg: svg('#fcc'), name: '하나' }, { svg: svg('#cfc'), name: '둘' }, { svg: svg('#ccf'), name: '셋' }] }))
  const vb0 = await page.evaluate(() => document.querySelector('#ovin svg').getAttribute('viewBox'))
  const cdp = await page.context().newCDPSession(page)
  const fingers = async (pts, steps = 6) => { const at = t => pts.map(([a, b], id) => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, id }))
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: at(0) })
    for (let i = 1; i <= steps; i++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: at(i / steps) })
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] }) }
  await fingers([[{ x: 160, y: 400 }, { x: 120, y: 400 }], [{ x: 230, y: 400 }, { x: 270, y: 400 }]])   // 두 손가락 벌리기 = 확대
  const w = s => +s.split(' ')[2]
  expect(w(await page.evaluate(() => document.querySelector('#ovin svg').getAttribute('viewBox')))).toBeLessThan(w(vb0) * 0.8)
  await page.locator('#play').tap()
  const no = page.locator('#no'); await expect(no).toContainText('1 / 3')
  await expect(page.locator('#nav')).toHaveCSS('opacity', '1')                          // 마우스 올림이 없는 기기 = 늘 보임
  await page.touchscreen.tap(300, 400); await expect(no).toContainText('2 / 3')          // 오른쪽 톡 = 다음
  await page.touchscreen.tap(40, 400); await expect(no).toContainText('1 / 3')           // 왼쪽 1/3 = 이전
  await fingers([[{ x: 300, y: 400 }, { x: 80, y: 410 }]]); await expect(no).toContainText('2 / 3')   // 왼쪽으로 쓸기 = 다음
  await fingers([[{ x: 80, y: 400 }, { x: 300, y: 395 }]]); await expect(no).toContainText('1 / 3')
  for (const b of await page.locator('#nav button').all()) { const r = await b.boundingBox(); expect(r.height).toBeGreaterThanOrEqual(44) }
})

test('가로 휴대폰 — 첫 빈 틀은 PC 틀을 안 칠함 · 발표 장이 아래 막대에 안 덮임 · 장 목록 닫기', async ({ browser }) => {
  const name = boardName('phoneland2')
  const c = await browser.newContext({ viewport: { width: 844, height: 390 }, hasTouch: true, isMobile: true }), p = await c.newPage()
  expect((await p.request.put(`/api/doc/${name}`, { data: frameDoc('가로 시험') })).ok()).toBeTruthy()
  await p.route(/\/assets\/.*\.js$/, r => r.abort())                                     // 앱을 안 띄우고 index.html 빈 틀만
  await p.goto(`/?board=${name}`)
  expect(await p.evaluate(() => document.getElementById('root').children.length)).toBe(0)   // 폭 844 ≥ 700이어도 짧은 변 390 = 휴대폰
  await p.unroute(/\/assets\/.*\.js$/)
  await openBoard(p, name)
  await p.getByTestId('phone-tour').tap(); const pr = p.getByTestId('presenter'); await expect(pr).toBeVisible()
  const bar = await p.getByTestId('present-bar').boundingBox()
  const slide = await pr.locator('svg > rect').first().boundingBox()                     // 장 + 둘레 여백 띠
  expect(slide.y + slide.height).toBeLessThanOrEqual(bar.y + 1)
  await p.getByTestId('present-slide').tap(); const list = p.getByTestId('slide-list'); await expect(list).toBeVisible()
  await expect(list).toContainText('누르면 그 장 · 빈 곳 = 닫기')
  const cl = p.getByTestId('slide-list-close'); expect((await cl.boundingBox()).height).toBeGreaterThanOrEqual(44)
  await cl.tap(); await expect(list).toHaveCount(0)
  await c.close()
})

test('휴대폰 문서 카드 톡 = 앱 안 문서 창(보기만, 새 탭 아님) · 글이 읽힐 크기 · 닫기 44', async ({ page }) => {
  await openBoard(page, boardName('phonedoc'))
  await page.evaluate(() => window.__mb.ed.dropFiles([new File([`<h1>보고서</h1><p style="font-size:16px">${'본문 글이에요. '.repeat(40)}</p>`], '보고서.html', { type: 'text/html' })]))
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'doc').length).toBe(1)
  await page.getByTestId('phone-bar').getByRole('button', { name: '다 보기' }).tap()
  let popped = false; page.on('popup', () => { popped = true })
  const b = await page.getByTestId('board').boundingBox()
  await page.touchscreen.tap(b.x + b.width / 2, b.y + b.height / 2)
  const dv = page.getByTestId('doc-view'); await expect(dv).toBeVisible()
  await expect(dv.getByTestId('doc-hint')).toContainText('보기만')
  expect(popped).toBe(false)
  const fb = await dv.getByTestId('doc-frame').boundingBox(); expect(fb.x).toBeGreaterThanOrEqual(0); expect(fb.x + fb.width).toBeLessThanOrEqual(391)   // 화면 폭에 맞춤
  const k = await dv.getByTestId('doc-frame').evaluate(f => +(f.style.transform.match(/scale\(([\d.]+)\)/) || [0, 1])[1]); expect(k).toBeGreaterThanOrEqual(0.7)   // 글자 0.7배 이상(16px 글 = 11px 이상)
  const hc = await hitBox(dv.getByTestId('doc-close')); expect(hc.h).toBeGreaterThanOrEqual(44); expect(hc.w).toBeGreaterThanOrEqual(43)
  await dv.getByTestId('doc-frame').contentFrame().locator('p').tap()                 // 고치기 없음 — 블록 말 칸이 안 열림
  await expect(page.getByTestId('block-bubble')).toHaveCount(0)
  await dv.getByTestId('doc-close').tap(); await expect(dv).toHaveCount(0)
})

test('태블릿(손가락 + PC 화면) — 작은 단추 누르는 자리 넓힘 · 넓힌 자리가 이웃 단추를 안 덮음', async ({ browser }) => {
  const name = boardName('tabhit')
  const c = await browser.newContext({ viewport: { width: 820, height: 1180 }, hasTouch: true, isMobile: true }), p = await c.newPage()
  expect((await p.request.put(`/api/doc/${name}`, { data: frameDoc('태블릿', 3) })).ok()).toBeTruthy()
  await p.addInitScript(() => { try { localStorage.setItem('mb-dock', 'frame') } catch {} })
  await openBoard(p, name)
  await expect(p.getByTestId('phone-bar')).toHaveCount(0)
  const more = p.getByTestId('frame-more').first(); await expect(more).toBeAttached()
  const h = await hitBox(more); expect(h.w).toBeGreaterThanOrEqual(32); expect(h.h).toBeGreaterThanOrEqual(24)   // 기준: 손가락 기기 = 폭 32 이상·높이 24 이상(WCAG 2.5.8) — 줄 사이가 9라 위아래로 더 넓히면 윗줄 ⋯를 덮음
  await p.addStyleTag({ content: '.mb-more{visibility:visible!important}' })   // 줄 ⋯를 다 보이게 하고(손가락 기기는 마우스 올림이 없어 연 메뉴 줄만 보임 — 가장 빽빽한 경우)
  // 겹침 검사 — 보이는 단추마다 제 상자의 가운데·네 귀퉁이 안쪽을 누르면 그 단추(다른 단추의 넓힌 자리가 가로채지 않음)
  const bad = await p.evaluate(() => { const out = []
    for (const b of document.querySelectorAll('button')) { const r = b.getBoundingClientRect(); if (r.width < 4 || r.height < 4 || getComputedStyle(b).visibility === 'hidden') continue
      for (const [x, y] of [[r.left + r.width / 2, r.top + r.height / 2], [r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2], [r.right - 2, r.bottom - 2]]) {
        if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue
        const e = document.elementFromPoint(x, y); if (!e) continue
        const hit = e.closest('button'); if (hit && hit !== b && !b.contains(hit) && !hit.contains(b) && hit.classList.contains('mb-hit')) out.push(`${b.getAttribute('aria-label') || b.textContent.trim().slice(0, 12)} ← ${hit.getAttribute('aria-label') || hit.textContent.trim().slice(0, 12)}`) } }
    return [...new Set(out)] })
  expect(bad).toEqual([])
  await c.close()
})

test('마우스 PC — 누르는 자리 그대로(⋯ 24)', async ({ browser }) => {
  const name = boardName('pchit')
  const c = await browser.newContext({ viewport: { width: 1600, height: 900 }, hasTouch: false, isMobile: false }), p = await c.newPage()   // 이 파일 test.use(손가락)를 안 물려받게
  expect((await p.request.put(`/api/doc/${name}`, { data: frameDoc('PC', 2) })).ok()).toBeTruthy()
  await p.addInitScript(() => { try { localStorage.setItem('mb-dock', 'frame') } catch {} })
  await openBoard(p, name)
  const h = await hitBox(p.getByTestId('frame-more').first()); expect(h.w).toBe(24); expect(h.h).toBe(24)
  await c.close()
})
