// 흐름 47 — 예시 칠판(2026-10-28 사용자: 들어오자마자 「이렇게 쓰는 거구나」 + 만져 보다 망가지면 한 번에 처음으로).
// 2026-11-04 사용자: 새 칠판은 깨끗해야 — 처음 = 빈 칠판 + 첫 안내 「예시 칠판 보기」, 칠판 판 「★ 예시 칠판」 = 누를 때마다 원본(`web/examples/intro`)의 새 사본(이름이 겹치면 「… 2」).
// 사람마다 따로 · 「↺ 처음 모습으로」 = 이 사본만 원본으로(칠판·대화) · 예시가 아닌 칠판은 서버가 막음
import { test, expect, devices } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { liveDoc, waitSaved } from './helpers.js'

const TPL = join(dirname(fileURLToPath(import.meta.url)), '..', 'examples', 'intro')
const N = JSON.parse(readFileSync(join(TPL, 'intro.ecad'), 'utf-8')).items.length
const fresh = async browser => { const c = await browser.newContext(); await c.addInitScript(() => { try { localStorage.setItem('mb-guide-off', '1'); localStorage.setItem('mb-chat-open', '0') } catch {} }); return c }
const count = async p => (await liveDoc(p)).items.length
const withGuide = async browser => { const c = await browser.newContext(); await c.addInitScript(() => { try { localStorage.setItem('mb-chat-open', '0') } catch {} }); return c }
const moved = async (p, u0) => { await p.waitForURL(u => u.href !== u0); await p.waitForFunction(() => !!window.__mb?.toEcad); await expect(p.getByTestId('example-band')).toBeVisible() }   // 새 주소로 옮겨 간 뒤에 읽기(옮기는 중엔 __mb가 없음)
const viaGuide = async p => { await p.goto('/'); const u0 = p.url(); await p.getByTestId('empty-guide-예시 칠판 보기').click(); await moved(p, u0) }
const viaPanel = async p => { await p.getByTestId('dock-board').waitFor(); if (!(await p.getByTestId('board-example-new').isVisible())) await p.getByTestId('dock-board').click(); const u0 = p.url(); await p.getByTestId('board-example-new').click()   // 칠판 판은 열린 채 기억됨 — 또 누르면 닫힘
  await moved(p, u0) }

test('처음 = 빈 칠판 + 안내 「예시 칠판 보기」 → 예시 사본 · 사람마다 따로 · 「처음 모습으로」 = 칠판·대화가 원본으로', async ({ browser }) => {
  const ca = await withGuide(browser), a = await ca.newPage(), cb = await withGuide(browser), b = await cb.newPage()
  await a.goto('/'); await expect(a.getByTestId('empty-guide')).toBeVisible()
  await expect.poll(() => count(a)).toBe(0); await expect(a.getByTestId('example-band')).toHaveCount(0)   // 처음 칠판 = 깨끗(예시 아님)
  const first = new URL(a.url()).searchParams.get('board')
  await a.getByTestId('empty-guide-예시 칠판 보기').click(); await expect(a.getByTestId('example-band')).toBeVisible()
  expect(new URL(a.url()).searchParams.get('board')).not.toBe(first)                    // 예시는 새 칠판으로(빈 칠판은 그대로)
  await viaGuide(b)
  await expect.poll(() => count(a)).toBe(N)
  expect(a.url()).not.toBe(b.url())                                                      // 사람마다 자기 사본
  const name = new URL(a.url()).searchParams.get('board')
  expect(((await (await a.request.get(`/api/chatlog/${name}`)).json()).messages || []).length).toBeGreaterThan(0)   // 예시 대화도 같이

  await a.getByTestId('board').click({ position: { x: 20, y: 300 } })
  await a.keyboard.press('Control+a'); await a.keyboard.press('Delete')                  // 망가뜨리기 — 다 지움
  await expect.poll(() => count(a)).toBe(0); await waitSaved(a)
  await b.reload(); await b.waitForFunction(() => !!window.__mb?.toEcad); await expect.poll(() => count(b)).toBe(N)                            // 남의 사본은 그대로

  await a.getByTestId('example-reset').click()
  await expect(a.getByTestId('example-ask')).toBeVisible()
  await a.keyboard.press('Enter')                                                        // 엔터 = 되돌리기(확인 창)
  await expect.poll(() => count(a), { timeout: 10_000 }).toBe(N)
  expect(new URL(a.url()).searchParams.get('board')).toBe(name)                         // 같은 주소 그대로
  await a.goto('/'); await expect.poll(() => new URL(a.url()).searchParams.get('board')).toBe(name)   // 다시 오면 마지막 칠판(새 예시가 아님)
  await ca.close(); await cb.close()
})

test('「▶ 차례로 보기」 = 1번 프레임부터 발표 · → 다음 · Esc 끝 (노트북 크기)', async ({ browser }) => {
  const c = await withGuide(browser), p = await c.newPage(); await p.setViewportSize({ width: 1366, height: 768 })
  await viaGuide(p); await expect.poll(() => count(p)).toBe(N)
  await expect(p.getByTestId('example-tour')).toBeVisible()
  await p.getByTestId('board').click({ position: { x: 20, y: 300 } })
  await p.keyboard.press('Control+a')                                                   // 아무 프레임이나 골라 둬도 1번부터
  await p.getByTestId('example-tour').click()
  await expect(p.getByTestId('presenter')).toBeVisible()
  await expect(p.getByTestId('presenter')).toContainText('1 /')
  await p.keyboard.press('ArrowRight'); await expect(p.getByTestId('presenter')).toContainText('2 /')
  await p.keyboard.press('Escape'); await expect(p.getByTestId('presenter')).toHaveCount(0)
  await c.close()
})

test('휴대폰 「▶ 차례로」 = 막대는 ◀ 장 ▶ 끝만 · 톡 = 다음 · 왼쪽 톡 = 이전 · 여는 알림 = 칠판 이름 · 대화창은 첫 질문부터(PC)', async ({ browser }) => {
  const { defaultBrowserType, ...iphone } = devices['iPhone 13']   // eslint-disable-line no-unused-vars
  const c = await browser.newContext({ ...iphone })
  const p = await c.newPage(); await p.goto('/'); await p.getByTestId('empty-guide-예시 칠판 보기').tap()   // 휴대폰도 첫 안내로
  await expect(p.getByTestId('status-toast')).toContainText('「Magic Board 둘러보기」')        // 코드(「x9fxv3tn」) 대신 이름
  await p.getByTestId('phone-tour').tap()
  const pr = p.getByTestId('presenter'); await expect(pr).toContainText('1 /')
  await expect(p.getByTestId('present-bar').getByText('형광펜')).toHaveCount(0)              // 판서 도구 없음(화면 밖으로 넘쳤음)
  const vp = p.viewportSize()
  await p.touchscreen.tap(vp.width * 0.8, vp.height / 2); await expect(pr).toContainText('2 /')
  await p.touchscreen.tap(vp.width * 0.1, vp.height / 2); await expect(pr).toContainText('1 /')
  await c.close()
  const d = await fresh(browser), q = await d.newPage(); await q.addInitScript(() => { try { localStorage.setItem('mb-chat-open', '1') } catch {} })
  await q.goto('/'); await viaPanel(q)
  await expect(q.getByText('2026년 연말정산에서 직장인이 챙겨야 할', { exact: false }).first()).toBeInViewport()   // 예시 대화 첫 질문이 보임
  await d.close()
})

test('예시가 아닌 칠판엔 「처음 모습으로」가 안 먹음(서버 409) · 칠판 판 「★ 예시 칠판」 = 새 사본(또 누르면 「… 2」)', async ({ page, request }) => {
  const plain = `e2e_plain_${Date.now().toString(36)}`
  expect((await request.put(`/api/doc/${plain}`, { data: { format: 'easycad-doc', version: 1, items: [] } })).ok()).toBe(true)
  expect((await request.post(`/api/example/${plain}`, { data: {} })).status()).toBe(409)
  await page.addInitScript(() => { try { localStorage.setItem('mb-guide-off', '1'); localStorage.setItem('mb-chat-open', '0'); localStorage.setItem('mb.name', '시험') } catch {} })
  await page.goto(`/?board=${plain}`)
  await expect(page.getByText(`서버 「${plain}」`, { exact: false }).first()).toBeVisible()
  await expect(page.getByTestId('example-band')).toHaveCount(0)                          // 예시가 아니면 띠 없음
  await viaPanel(page)
  await expect.poll(() => count(page)).toBe(N)
  const one = new URL(page.url()).searchParams.get('board'); expect(one).not.toBe(plain)
  expect((await liveDoc(page)).title).toBe('Magic Board 둘러보기')
  await viaPanel(page); await expect.poll(() => new URL(page.url()).searchParams.get('board')).not.toBe(one)
  await expect.poll(async () => (await liveDoc(page)).title).toBe('Magic Board 둘러보기 2')   // 이름이 겹치면 번호(서버가 사본 만들 때 — 안 고친 사본 그대로)
  const d2 = await (await request.get(`/api/doc/${new URL(page.url()).searchParams.get('board')}`)).json()
  expect(d2.example_rev).toBe(d2.rev)
})
