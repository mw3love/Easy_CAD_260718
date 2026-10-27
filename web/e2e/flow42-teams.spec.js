// 흐름 42 — 팀별 칠판(§8 항목67, 2026-10-27): 팀 비밀번호로 들어오면 우리 팀 칠판만 보이고, 다른 팀 칠판 주소는 막히고, 새 칠판은 우리 팀 것이 된다.
// 다른 흐름은 비밀번호 없는 시험 서버(5291)를 쓰므로 이 흐름만 팀 서버를 따로 띄운다(5292, 임시 폴더 `.e2e-teams`).
import { test, expect } from '@playwright/test'
import { spawn } from 'node:child_process'
import { mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const WEB = join(dirname(fileURLToPath(import.meta.url)), '..'), DATA = join(WEB, '.e2e-teams'), PORT = 5292, BASE = `http://127.0.0.1:${PORT}`
const TEAMS = [{ name: 'A팀', password: 'aaaa1111', boards: ['A회의'] }, { name: 'B팀', password: 'bbbb2222', boards: ['B회의'] }]
const DOC = { format: 'easycad-doc', version: 1, items: [] }
let srv

test.beforeAll(async () => {
  rmSync(DATA, { recursive: true, force: true }); mkdirSync(DATA, { recursive: true })
  writeFileSync(join(DATA, 'teams.json'), JSON.stringify(TEAMS))
  for (const n of ['A회의', 'B회의', 'main']) writeFileSync(join(DATA, `${n}.ecad`), JSON.stringify(DOC))   // main = 팀 없는 옛 칠판(관리자만)
  srv = spawn('python', ['server.py', '--host', '127.0.0.1', '--port', String(PORT), '--data', DATA], { cwd: WEB, env: { ...process.env, PYTHONIOENCODING: 'utf-8', MB_PASSWORD: 'admin9999', EASYCAD_ROUTE: 'rules' }, stdio: 'ignore' })
  for (let i = 0; i < 100; i++) { try { if ((await fetch(`${BASE}/api/session`)).ok) return } catch { /* 아직 안 켜짐 */ } await new Promise(r => setTimeout(r, 200)) }
  throw new Error('팀 서버가 안 켜짐')
})
test.afterAll(() => { srv?.kill(); rmSync(DATA, { recursive: true, force: true }) })

async function login(page, pw, who = '시험') {
  await page.getByPlaceholder('이름 (예: 김기자)').fill(who)
  await page.getByPlaceholder('팀 비밀번호').fill(pw)
  await page.getByRole('button', { name: '들어가기' }).click()
}
async function boardList(page) {
  await page.getByTestId('board-title').click()
  await expect(page.getByTestId('board-form')).toBeVisible()
  await expect(page.getByTestId('board-row').first()).toBeVisible()
  const rows = await page.getByTestId('board-row').locator('span:first-child').allInnerTexts()
  await page.getByTestId('board-title').click()
  return rows.sort()
}
const initName = ctx => ctx.addInitScript(() => { try { localStorage.setItem('mb-guide-off', '1'); localStorage.setItem('mb-chat-open', '0'); localStorage.setItem('mb-dock', 'shape') } catch {} })

test('팀 비밀번호 = 우리 팀 칠판만 · 다른 팀 칠판은 막힘 · 새 칠판은 우리 팀 것', async ({ browser }) => {
  const ca = await browser.newContext(); await initName(ca); const a = await ca.newPage()
  await a.goto(`${BASE}/`)
  await login(a, 'aaaa1111', '에이')
  await expect(a).toHaveURL(/board=A%ED%9A%8C%EC%9D%98/)                         // 주소에 칠판이 없으면 우리 팀 첫 칠판으로
  await expect(a.getByText('서버 「A회의」', { exact: false }).first()).toBeVisible()
  await expect(a.getByTestId('team-badge')).toHaveText('A팀')
  expect(await boardList(a)).toEqual(['A회의'])                                 // B팀 칠판·옛 칠판(main)은 안 보임

  // 새 칠판 — 다른 팀이 쓰는 이름은 알림, 새 이름은 우리 팀 것
  await a.getByTestId('board-title').click(); await a.getByTestId('board-new').click()
  await a.getByPlaceholder('새 칠판 이름 (예: 송신소점검)').fill('B회의'); await a.keyboard.press('Enter')
  await expect(a.getByTestId('board-new-why')).toContainText('다른 팀이 쓰는 이름')
  await a.getByPlaceholder('새 칠판 이름 (예: 송신소점검)').fill('A새판'); await a.keyboard.press('Enter')
  await expect(a.getByText('서버 「A새판」', { exact: false }).first()).toBeVisible()
  await a.locator('button[title^="사각형 —"]').first().click()
  const box = await a.getByTestId('board').boundingBox()
  await a.mouse.move(box.x + 400, box.y + 300); await a.mouse.down(); await a.mouse.move(box.x + 560, box.y + 380, { steps: 8 }); await a.mouse.up()
  await expect.poll(() => JSON.parse(readFileSync(join(DATA, 'teams.json'), 'utf8'))[0].boards, { timeout: 5000 }).toEqual(['A회의', 'A새판'])

  // 다른 팀 칠판 주소로 직접 → 막힘 → 그 팀 비밀번호로 다시 들어가면 열림
  await a.goto(`${BASE}/?board=${encodeURIComponent('B회의')}`)
  await expect(a.getByTestId('team-blocked')).toBeVisible()
  await expect(a.getByTestId('team-home')).toContainText('A회의')
  await a.getByRole('button', { name: '다른 비밀번호로 들어가기' }).click()
  await login(a, 'bbbb2222', '에이')
  await expect(a.getByText('서버 「B회의」', { exact: false }).first()).toBeVisible()
  await expect(a.getByTestId('team-badge')).toHaveText('B팀')

  // B팀은 A팀이 만든 새 칠판을 못 봄 · 관리자는 다 봄
  const cb = await browser.newContext(); await initName(cb); const b = await cb.newPage()
  await b.goto(`${BASE}/?board=${encodeURIComponent('B회의')}`); await login(b, 'bbbb2222', '비')
  await expect(b.getByText('서버 「B회의」', { exact: false }).first()).toBeVisible()
  expect(await boardList(b)).toEqual(['B회의'])
  const cm = await browser.newContext(); await initName(cm); const m = await cm.newPage()
  await m.goto(`${BASE}/?board=main`); await login(m, 'admin9999', '관리')
  await expect(m.getByTestId('team-badge')).toHaveText('관리자')
  expect(await boardList(m)).toEqual(['A새판', 'A회의', 'B회의', 'main'])
  await ca.close(); await cb.close(); await cm.close()
})
