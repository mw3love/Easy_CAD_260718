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
// 2026-11-08 「+」 창 없앰 — 발표 자료·인포그래픽처럼 질문지가 먼저인 길은 말로: 진짜 서버는 길 고르기 요청(kind·deep·slides 없음)에 `{ kind: 'go', to }`로 답함.
// 가짜 /api/chat은 `if (routeCall(b)) return r.fulfill({ json: { kind: 'go', to: 'slides' } })`로 흉내(이 요청은 크레딧이 안 들어 `seen`에 안 넣음)
export const routeCall = b => !b.kind && !b.deep && !b.slides
// 「KAIROS에게 묻기」(2026-11-14 B1 5단계 — 옛 AI 칩·「AI로 만들기」를 치움): 우클릭 메뉴가 열린 상태에서 → 대화창 입력 칸(고른 것이 붙음)에 말 → Enter
const AI_SAY = { doc: '고른 것을 문서 한 장으로 만들어 줘', slide: '슬라이드 만들어 줘' }
export async function aiMake(page, kind, text = '') {
  await page.getByRole('menuitem', { name: /KAIROS에게 묻기/ }).click()
  const box = page.getByPlaceholder('물어보세요', { exact: false }); await expect(box).toBeFocused()
  await expect(page.getByTestId('chat-busy')).toHaveCount(0)   // 앞 답을 기다리는 동안 보내면 안 받음(사람도 같음)
  await box.fill([AI_SAY[kind], text].filter(Boolean).join(' — ')); await box.press('Enter')
}
export async function askChat(page, text) { const box = page.getByPlaceholder('물어보세요', { exact: false }); await box.fill(text); await box.press('Enter') }

export async function openBoard(page, name, { chat = false, who = '시험', guide = false, briefAsk = false } = {}) {   // briefAsk = 딥모드 맞춤 질문(서버 한 번 더 — 기본은 끔, flow62만 켬)   // guide = 빈 칠판 첫 안내(가운데를 덮어 다른 시험의 누르기를 막으니 기본은 끔 — flow37만 켬)
  await page.addInitScript(([c, w, g, a]) => { try { localStorage.setItem('mb-chat-open', c ? '1' : '0'); localStorage.setItem('mb.name', w); localStorage.setItem('mb-guide-off', g ? '0' : '1'); localStorage.setItem('mb-brief-ask', a ? 'on' : 'off') } catch {} }, [chat, who, guide, briefAsk])
  await page.goto(`/?board=${name}`)
  await expect.poll(async () => { const t = (await page.getByTestId('status-toast').textContent().catch(() => '')) || ''; return t.includes(`서버 「${name}」`) || t === '새 칠판' || /^「.*」 · \d+개$/.test(t) }).toBe(true)   // 여는 알림 = 이름 없는 칠판은 「서버 「이름」」, 칠판 코드 새 칠판은 「새 칠판」, 제목 있으면 「「제목」 · N개」(2026-11-03)
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
const BASIC_NAMES = new Set(['사각형', '원', '삼각형', '판단', '시작/끝', '입출력', '준비', '저장소'])
export async function pickShape(page, name) {   // 기본 도형 8 = 도구 줄 「도형」 펼침 · 심볼 = 떠 있는 「심볼」 판(닫혀 있으면 엶) — 2026-11-14 B1 3단계
  if (BASIC_NAMES.has(name)) { await page.getByTestId('shape-tool').click(); return page.getByTestId('shape-pop').getByRole('button', { name, exact: true }).click() }
  const b = page.locator(`button[title^="${name} —"]`).first()
  if (!(await b.isVisible())) await page.getByTestId('dock-shape').click()
  await b.click()
}
// 떠 있는 판 열기 — board = 칠판 이름 ▾ · shape = 도구 줄 「도형·심볼」 · frame·layer = ☰ 「프레임 목록」·「레이어」(옛 왼쪽 레일 단추 dock-*)
export async function openPane(page, k) {
  if (k === 'board') return page.getByTestId('board-title').click()
  if (k === 'shape') return page.getByTestId('dock-shape').click()
  return menuPick(page, k === 'frame' ? '프레임 목록' : '레이어')
}
// 대화창 그림 후보를 칠판에 붙이기 — 왼쪽 위 「＋ 칠판에 추가」(2026-10-20 — 사진 누르기는 크게 보기)
export async function pinCandidate(page, n = 0) {
  await page.getByTestId('image-pick').nth(n).getByTestId('image-pin').click()
  await page.getByTestId('image-pick').nth(n).and(page.locator('[data-picked="1"]')).waitFor()
}

// 떠 있는 섬(2026-11-14 B1) — ☰ 메뉴·도구 줄 ⋯ 메뉴의 줄 누르기(위 막대 단추였던 것: 저장·내보내기·밝기 / 다각형·번호·웹·표·회의·발표)
export async function menuPick(page, name) { await page.getByTestId('main-menu').click(); await page.getByTestId('main-menu-list').getByRole('menuitem', { name: itemName(name) }).click() }
export async function morePick(page, name) { await page.getByTestId('tools-more').click(); await page.getByTestId('tools-more-list').getByRole('menuitem', { name: itemName(name) }).click() }
const itemName = n => new RegExp('^' + n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))   // 메뉴 줄 이름 뒤에 글쇠(「내보내기… Ctrl+P」)가 붙음

// 옛 속성 카드(2026-11-14 B1 4단계부터 속성 막대 ⋯ 「속성 자세히…」로만 열림) — 그림 설명·그래프 모양·표 칸·제목처럼 막대에 없는 것
export async function openCard(page) { await page.getByTestId('bar-more').click(); await page.getByRole('menuitem', { name: /속성 자세히/ }).click(); await expect(page.getByTestId('props-card')).toBeVisible() }
