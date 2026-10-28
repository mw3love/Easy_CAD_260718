// 흐름 47 — 예시 칠판(2026-10-28 사용자: 들어오자마자 「이렇게 쓰는 거구나」 + 만져 보다 망가지면 한 번에 처음으로).
// 처음 = 원본(`web/examples/intro`) 사본 · 사람마다 따로 · 「↺ 처음 모습으로」 = 이 사본만 원본으로(칠판·대화) · 예시가 아닌 칠판은 서버가 막음
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { liveDoc, waitSaved } from './helpers.js'

const TPL = join(dirname(fileURLToPath(import.meta.url)), '..', 'examples', 'intro')
const N = JSON.parse(readFileSync(join(TPL, 'intro.ecad'), 'utf-8')).items.length
const fresh = async browser => { const c = await browser.newContext(); await c.addInitScript(() => { try { localStorage.setItem('mb-guide-off', '1'); localStorage.setItem('mb-chat-open', '0') } catch {} }); return c }
const count = async p => (await liveDoc(p)).items.length

test('처음 = 예시 사본 · 사람마다 따로 · 「처음 모습으로」 = 칠판·대화가 원본으로', async ({ browser }) => {
  const ca = await fresh(browser), a = await ca.newPage(), cb = await fresh(browser), b = await cb.newPage()
  await a.goto('/'); await b.goto('/')
  await expect(a.getByTestId('example-band')).toBeVisible(); await expect(b.getByTestId('example-band')).toBeVisible()
  await expect.poll(() => count(a)).toBe(N)
  expect(a.url()).not.toBe(b.url())                                                      // 사람마다 자기 사본
  const name = new URL(a.url()).searchParams.get('board')
  expect(((await (await a.request.get(`/api/chatlog/${name}`)).json()).messages || []).length).toBeGreaterThan(0)   // 예시 대화도 같이

  await a.getByTestId('board').click({ position: { x: 20, y: 300 } })
  await a.keyboard.press('Control+a'); await a.keyboard.press('Delete')                  // 망가뜨리기 — 다 지움
  await expect.poll(() => count(a)).toBe(0); await waitSaved(a)
  await b.reload(); await expect.poll(() => count(b)).toBe(N)                            // 남의 사본은 그대로

  await a.getByTestId('example-reset').click()
  await expect(a.getByTestId('example-ask')).toBeVisible()
  await a.keyboard.press('Enter')                                                        // 엔터 = 되돌리기(확인 창)
  await expect.poll(() => count(a), { timeout: 10_000 }).toBe(N)
  expect(new URL(a.url()).searchParams.get('board')).toBe(name)                         // 같은 주소 그대로
  await a.goto('/'); await expect.poll(() => new URL(a.url()).searchParams.get('board')).toBe(name)   // 다시 오면 마지막 칠판(새 예시가 아님)
  await ca.close(); await cb.close()
})

test('예시가 아닌 칠판엔 「처음 모습으로」가 안 먹음(서버 409) · 칠판 판 「예시 칠판 열기」 = 새 사본', async ({ page, request }) => {
  const plain = `e2e_plain_${Date.now().toString(36)}`
  expect((await request.put(`/api/doc/${plain}`, { data: { format: 'easycad-doc', version: 1, items: [] } })).ok()).toBe(true)
  expect((await request.post(`/api/example/${plain}`, { data: {} })).status()).toBe(409)
  await page.addInitScript(() => { try { localStorage.setItem('mb-guide-off', '1'); localStorage.setItem('mb-chat-open', '0'); localStorage.setItem('mb.name', '시험') } catch {} })
  await page.goto(`/?board=${plain}`)
  await expect(page.getByText(`서버 「${plain}」`, { exact: false }).first()).toBeVisible()
  await expect(page.getByTestId('example-band')).toHaveCount(0)                          // 예시가 아니면 띠 없음
  await page.getByTestId('dock-board').click()
  await page.getByTestId('board-new-more').click(); await page.getByTestId('board-example-new').click()
  await expect(page.getByTestId('example-band')).toBeVisible()
  await expect.poll(() => count(page)).toBe(N)
  expect(new URL(page.url()).searchParams.get('board')).not.toBe(plain)
})
