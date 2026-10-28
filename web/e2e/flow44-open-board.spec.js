// 흐름 44 — 비밀번호 없는 서버 = 칠판 주소가 곧 열쇠(2026-10-27 밤 사용자: Excalidraw처럼 처음 접속하면 깨끗한 빈 칠판, 공유한 순간부터 남이 들어옴).
// 처음 = 새 비밀 주소의 예시 칠판 사본(2026-10-28 사용자 — 빈 칠판 대신, flow47) · 로그인 없음 · 다시 오면 마지막 칠판 · 남이 준 링크 = 이름 한 번 + 내 칠판 목록에 · 공유 창 = 이 주소 · 서버 키를 끈 서버 = 「🔑 내 키」 안내
import { test, expect } from '@playwright/test'
import { spawn } from 'node:child_process'
import { mkdirSync, rmSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { liveDoc, waitSaved } from './helpers.js'

const fresh = async browser => { const c = await browser.newContext(); await c.addInitScript(() => { try { localStorage.setItem('mb-guide-off', '1'); localStorage.setItem('mb-chat-open', '0') } catch {} }); return c }   // 처음 온 사람(이름·기억 없음)
const CODE = /board=[a-z2-9]{8}$/   // 이름 없는 새 칠판 = 칠판 코드 8자뿐(링크가 짧고 영문뿐)

test('처음 = 새 비밀 주소의 예시 칠판 · 다시 오면 그 칠판 · 남의 링크 = 이름 한 번 + 내 칠판 · 공유 창 = 이 주소', async ({ browser }) => {
  const ca = await fresh(browser), a = await ca.newPage()
  await a.goto('/')
  await expect(a).toHaveURL(CODE)                                                       // 주소창이 그 칠판으로(그대로 복사해 공유)
  await expect(a.getByTestId('example-band')).toBeVisible()                            // 예시 칠판 사본(2026-10-28)
  await expect(a.getByRole('button', { name: '들어가기' })).toHaveCount(0)               // 비밀번호·이름 안 물음
  await expect(a.getByTestId('board-title')).toHaveText(/^Magic Board 둘러보기/)        // 이름 = 예시 문서 이름(고치면 그 이름)
  const link = a.url(), rects = async p => (await liveDoc(p)).items.filter(it => it.type === 'rect').length, r0 = await rects(a)
  await a.locator('button[title^="사각형 —"]').first().click()
  const box = await a.getByTestId('board').boundingBox()
  await a.mouse.move(box.x + 400, box.y + 300); await a.mouse.down(); await a.mouse.move(box.x + 560, box.y + 380, { steps: 8 }); await a.mouse.up()
  await waitSaved(a)
  await a.goto('/'); await expect(a).toHaveURL(link)                                    // 다시 오면 마지막 칠판(빈 칠판이 아님)
  await expect(a.getByText('서버 「', { exact: false }).first()).toBeVisible()
  await expect.poll(() => rects(a)).toBe(r0 + 1)

  await a.getByRole('button', { name: '공유' }).click()
  await expect(a.getByTestId('share-open')).toBeVisible()
  await expect(a.locator('input[readonly]').first()).toHaveValue(link)                  // 보낼 것 = 이 주소

  const cb = await fresh(browser), b = await cb.newPage()
  await b.goto(link)
  await b.getByPlaceholder('이름 (예: 김기자)').fill('비')                                // 남이 준 링크(있는 칠판) = 이름만 한 번
  await expect(b.getByPlaceholder('팀 비밀번호')).toHaveCount(0)
  await b.getByRole('button', { name: '들어가기' }).click()
  await expect(b.getByText('서버 「', { exact: false }).first()).toBeVisible()
  await expect.poll(() => rects(b)).toBe(r0 + 1)
  await b.getByTestId('dock-board').click()
  await expect(b.getByTestId('board-row')).toHaveCount(1)                               // 내 칠판 = 받은 칠판만(서버의 다른 칠판은 안 보임)
  await b.goto('/'); await expect(b).toHaveURL(link)                                    // 받은 칠판도 「마지막 칠판」
  await expect(b.getByTestId('dock-board')).toHaveAttribute('aria-pressed', 'true')   // 연 칸은 이 브라우저에 기억
  await b.getByTestId('board-new').click()                                              // 누르면 바로 = 코드만(2026-10-28 — 이름 칸 없음)
  await expect(b).toHaveURL(CODE); expect(b.url()).not.toBe(link)
  await expect(b.getByRole('button', { name: '들어가기' })).toHaveCount(0)               // 내가 만든 새 칠판 = 안 물음
  await ca.close(); await cb.close()
})

// 서버 키를 끈 서버는 다른 흐름과 따로(5293, 임시 폴더) — 다른 흐름은 서버 키가 있는 5291 그대로
const WEB = join(dirname(fileURLToPath(import.meta.url)), '..'), DATA = join(WEB, '.e2e-nokey'), PORT = 5293, BASE = `http://127.0.0.1:${PORT}`
test.describe('서버 키 끔', () => {
  let srv
  test.beforeAll(async () => {
    rmSync(DATA, { recursive: true, force: true }); mkdirSync(DATA, { recursive: true })
    srv = spawn('python', ['server.py', '--host', '127.0.0.1', '--port', String(PORT), '--data', DATA, '--no-server-key'], { cwd: WEB, env: { ...process.env, PYTHONIOENCODING: 'utf-8', MB_PASSWORD: '', EASYCAD_ROUTE: 'rules' }, stdio: 'ignore' })
    for (let i = 0; i < 100; i++) { try { if ((await fetch(`${BASE}/api/session`)).ok) return } catch { /* 아직 안 켜짐 */ } await new Promise(r => setTimeout(r, 200)) }
    throw new Error('서버 키 끈 서버가 안 켜짐')
  })
  test.afterAll(() => { srv?.kill(); rmSync(DATA, { recursive: true, force: true }) })

  test('「🔑 내 키」 없이 물으면 키 칸이 열림(크레딧 = 각자)', async ({ browser }) => {
    const c = await browser.newContext(); await c.addInitScript(() => { try { localStorage.setItem('mb-guide-off', '1'); localStorage.setItem('mb-chat-open', '1') } catch {} })
    const p = await c.newPage(); await p.goto(`${BASE}/`)
    await expect(p.getByTestId('key-btn')).toHaveText('🔑 키 넣기')
    const box = p.getByPlaceholder('물어보세요', { exact: false })
    await box.click(); await p.keyboard.type('안녕'); await p.keyboard.press('Enter')
    await expect(p.getByText('내 KAIROS 키가 필요해요', { exact: false }).first()).toBeVisible()
    await expect(p.getByTestId('key-box')).toBeVisible()
    await c.close()
  })
})
