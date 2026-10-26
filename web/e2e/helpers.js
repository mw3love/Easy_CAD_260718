// 화면 시험 공용 도우미 — 칠판 열기·칠판 좌표 ↔ 화면 좌표·문서 읽기
import { readFileSync, existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect } from '@playwright/test'

export const DATA = join(dirname(fileURLToPath(import.meta.url)), '..', '.e2e-data')

let n = 0
/** 시험마다 새 칠판 이름(같은 서버를 같이 쓰므로) */
export const boardName = tag => `e2e_${tag}_${Date.now().toString(36)}${n++}`

/** 칠판을 열고 서버 답(「서버 「이름」」 상태 글)까지 기다림. 대화창은 기본 닫음(칠판 넓게) */
export async function openBoard(page, name, { chat = false, who = '시험', guide = false } = {}) {   // guide = 빈 칠판 첫 안내(가운데를 덮어 다른 시험의 누르기를 막으니 기본은 끔 — flow37만 켬)
  await page.addInitScript(([c, w, g]) => { try { localStorage.setItem('mb-chat-open', c ? '1' : '0'); localStorage.setItem('mb.name', w); localStorage.setItem('mb-guide-off', g ? '0' : '1') } catch {} }, [chat, who, guide])
  await page.goto(`/?board=${name}`)
  await expect(page.getByText(`서버 「${name}」`, { exact: false }).first()).toBeVisible()
  return page.getByTestId('board')
}

/** 칠판 좌표 → 페이지 좌표(화면 = 칠판 × z + (x, y), 칠판 svg 기준) */
export async function toPage(page, x, y) {
  const box = await page.getByTestId('board').boundingBox()
  const c = await page.evaluate(() => window.__mb.getCam())
  return { x: box.x + x * c.z + c.x, y: box.y + y * c.z + c.y }
}

/** 화면을 정해진 자리·배율로(시험이 좌표를 예측할 수 있게) */
export async function setCam(page, cam = { x: 400, y: 200, z: 1 }) {
  await page.evaluate(c => window.__mb.setCam(c), cam)
  // 화면이 실제로 그 자리로 다시 그려질 때까지(바로 글쇠를 누르면 칠판이 옛 자리를 들고 있음 — 2026-10-22 flow9 Z 되돌아가기가 가끔 실패)
  await page.waitForFunction(c => { const g = window.__mb.getCam(); return Math.abs(g.x - c.x) < 1e-6 && Math.abs(g.y - c.y) < 1e-6 && Math.abs(g.z - c.z) < 1e-6 }, cam, { timeout: 2000 }).catch(() => {})
}

/** 브라우저가 들고 있는 지금 문서(.ecad 모양) */
export const liveDoc = page => page.evaluate(() => window.__mb.toEcad())

/** 서버 데이터 폴더에 저장된 문서 — 없으면 null */
export function savedDoc(name) {
  const f = join(DATA, `${name}.ecad`)
  return existsSync(f) ? JSON.parse(readFileSync(f, 'utf-8')) : null
}

/** 서버에 다 보낼 때까지 기다림 — 상태 글 「저장됨」만 보면 앞 저장 때 글이 남아 있어 너무 일찍 끝남(2026-10-19 flow4가 가끔 실패) */
export async function waitSaved(page) {
  await expect.poll(() => page.evaluate(() => window.__mb.unsaved()), { timeout: 8_000 }).toBe(false)
  await expect(page.getByText('에 저장됨', { exact: false }).first()).toBeVisible({ timeout: 8_000 })
}

/** 칠판 위 두 점 사이를 끌기(칠판 좌표) */
export async function dragScene(page, a, b, steps = 8) {
  const p = await toPage(page, a.x, a.y), q = await toPage(page, b.x, b.y)
  await page.mouse.move(p.x, p.y); await page.mouse.down(); await page.mouse.move(q.x, q.y, { steps }); await page.mouse.up()
}

/** 칠판 좌표 한 점 누르기 */
export async function clickScene(page, x, y, opts) {
  const p = await toPage(page, x, y); await page.mouse.click(p.x, p.y, opts)
}

/** 팔레트(좌상 카드) 기본 도형 고르기 — 이름은 툴팁 앞부분(사각형·원 …) */
export const pickShape = (page, name) => page.locator(`button[title^="${name} —"]`).first().click()
// 대화창 그림 후보를 칠판에 붙이기 — 왼쪽 위 「＋ 칠판에 추가」(2026-10-20 — 사진 누르기는 크게 보기)
export async function pinCandidate(page, n = 0) {
  await page.getByTestId('image-pick').nth(n).getByTestId('image-pin').click()
  await page.getByTestId('image-pick').nth(n).and(page.locator('[data-picked="1"]')).waitFor()
}
