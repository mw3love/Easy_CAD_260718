// 흐름 20 — 버튼으로 넣는 자리(가운데 먼저·겹치면 빈자리) · 위 막대 도구 끌어다 놓기 · 메모 = 고른 채 바로 치기(2026-10-20 사용자)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, toPage, clickScene, liveDoc } from './helpers.js'

const btn = (page, name) => page.getByRole('button', { name, exact: true })
const box = it => { const s = it.scale || 1, r = it.rect || [0, 0, 0, 0]; return { x: it.pos[0] + r[0] * s, y: it.pos[1] + r[1] * s, w: r[2] * s, h: r[3] * s } }
const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

/** 위 막대 버튼을 칠판 점(칠판 좌표)으로 끌기 */
async function dragTool(page, name, x, y) {
  const b = await btn(page, name).boundingBox(), q = await toPage(page, x, y)
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await page.mouse.down()
  await page.mouse.move(q.x, q.y, { steps: 10 }); await page.mouse.up()
}

test('메모 버튼 두 번 = 둘째는 겹치지 않는 가까운 빈자리', async ({ page }) => {
  await openBoard(page, boardName('place')); await setCam(page)
  await btn(page, '메모').click(); await page.keyboard.press('Escape')
  await btn(page, '메모').click(); await page.keyboard.press('Escape')
  const ms = (await liveDoc(page)).items.filter(it => it.type === 'memo').map(box)
  expect(ms).toHaveLength(2)
  expect(overlap(ms[0], ms[1])).toBe(false)
})

test('메모 = 만들면 고른 채(바로 끌기), 치면 글, 빈 메모엔 안내', async ({ page }) => {
  await openBoard(page, boardName('memoarm')); await setCam(page)
  await btn(page, '메모').click()
  await expect(page.getByTestId('memo-editor')).toHaveCount(0)              // 입력 상태 아님
  await expect(page.getByText('치면 바로 써져요')).toBeVisible()
  let m = (await liveDoc(page)).items.find(it => it.type === 'memo'), b = box(m)
  const from = { x: b.x + b.w / 2, y: b.y + b.h / 2 }
  const p = await toPage(page, from.x, from.y), q = await toPage(page, from.x + 100, from.y + 50)
  await page.mouse.move(p.x, p.y); await page.mouse.down(); await page.mouse.move(q.x, q.y, { steps: 6 }); await page.mouse.up()
  m = (await liveDoc(page)).items.find(it => it.type === 'memo')
  expect(Math.round(m.pos[0] - (b.x - (m.rect[0] || 0) * (m.scale || 1)))).toBe(100)   // 바로 옮겨짐
  await page.keyboard.type('안녕 메모')                                      // 고른 채 치기 = 글(한글 첫 글자 포함)
  await expect(page.getByTestId('memo-editor')).toBeVisible()
  await clickScene(page, 900, 600)
  m = (await liveDoc(page)).items.find(it => it.type === 'memo')
  expect(m.lines.map(l => l.t).join('')).toBe('안녕 메모')
})

test('위 막대 끌어 놓기 — 선·화살표·글자·번호·메모·표·프레임', async ({ page }) => {
  await openBoard(page, boardName('tooldrag')); await setCam(page)
  await dragTool(page, '선', 0, 0)
  await dragTool(page, '화살표', 0, 100)
  await dragTool(page, '번호', 300, 0); await dragTool(page, '번호', 360, 0)
  await dragTool(page, '메모', 500, 0); await page.keyboard.press('Escape')
  await dragTool(page, '표', 0, 300)
  await dragTool(page, '프레임', 600, 400)
  await dragTool(page, '글자', 300, 200); await page.keyboard.type('놓은 글'); await clickScene(page, 900, 700)
  const d = await liveDoc(page), of = t => d.items.filter(it => it.type === t)
  expect(of('line')).toHaveLength(1)
  expect(Math.round(of('line')[0].line[2] - of('line')[0].line[0])).toBe(120)   // 화면 기준 길이(100% = 120)
  expect(of('sarrow').length + of('arrow').length).toBe(1)
  expect(of('badge').map(b => b.number)).toEqual([1, 2])
  expect(of('memo')).toHaveLength(1)
  expect(of('table')[0].rows).toBe(3)
  expect(of('frame')).toHaveLength(1)
  expect(JSON.stringify(of('text'))).toContain('놓은 글')
  const ln = of('line')[0]; expect(Math.abs(ln.pos[0] + (ln.line[0] + ln.line[2]) / 2)).toBeLessThan(2)   // 놓은 자리가 선의 가운데(pos + 선 좌표)
})

test('위 막대 다각형 끌기 = 첫 선분 놓고 이어 찍기, 웹 끌기 = 주소 칸', async ({ page }) => {
  await openBoard(page, boardName('polydrag')); await setCam(page)
  await dragTool(page, '다각형', 100, 100)
  await expect(btn(page, '다각형')).toHaveAttribute('aria-pressed', 'true')
  await clickScene(page, 160, 200)
  await page.keyboard.press('Enter')
  const pg = (await liveDoc(page)).items.filter(it => it.type === 'polygon')
  expect(pg).toHaveLength(1); expect(pg[0].pts).toHaveLength(3)              // 끌어 놓은 두 점 + 이어 찍은 한 점
  await dragTool(page, '웹', 400, 300)
  await expect(page.getByPlaceholder(/유튜브·웹페이지 주소/)).toBeVisible()
})

test('위 막대 — 「다 보기」 대신 「전체 화면」, 다 보기는 Z', async ({ page }) => {
  await openBoard(page, boardName('fullbtn'))
  await expect(btn(page, '전체 화면')).toBeVisible()
  await expect(btn(page, '다 보기')).toHaveCount(0)
})
