// 흐름 45 — 글 정렬(왼·가운데·오른, 2026-10-27 밤 — 10-23 시안에 넣고 미뤘던 것): 속성 카드 「정렬」 = 도형 안 글(`label.ha`)은 도형 안 여백 끝에 붙고,
// 독립 글(`ha`)은 줄끼리 맞춤. 가운데 = 전과 같음(칸 없음). 고치는 칸도 같은 쪽에 붙음(고치는 모습 = 결과)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, clickScene, toPage } from './helpers.js'

async function load(page, items) {
  await page.evaluate(async its => { const d = window.__mb.toEcad(); d.items.push(...its); await window.__mb.open('data:application/json,' + encodeURIComponent(JSON.stringify(d))) }, items)
  await setCam(page)
}
const pick = (page, name) => page.getByRole('button', { name, exact: true }).first()
const box = async (page, txt) => page.locator('svg tspan', { hasText: txt }).first().boundingBox()   // 글자 조각(tspan)이 실제 자리 — <text>는 x 없이 감싸기만

test('도형 글 = 왼·오른쪽 끝에 붙음 · 가운데 = 원래대로 · 고치는 칸도 같은 쪽', async ({ page }) => {
  await openBoard(page, boardName('align')); await load(page, [{ type: 'rect', pos: [0, 0], rect: [0, 0, 300, 100], pen: '#ff1f1f1f', width: 1, label: { text: '송신소', font: 16 } }])
  const r = await toPage(page, 0, 0), r2 = await toPage(page, 300, 100), mid = (r.x + r2.x) / 2
  const c0 = await box(page, '송신소'); expect(Math.abs(c0.x + c0.width / 2 - mid)).toBeLessThan(4)          // 처음 = 가운데
  await clickScene(page, 150, 20)
  await pick(page, '오른쪽 맞춤').click()
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'rect').label.ha).toBe('right')
  const cr = await box(page, '송신소'); expect(cr.x + cr.width).toBeGreaterThan(r2.x - 40); expect(cr.x).toBeGreaterThan(mid)   // 오른쪽 끝 가까이
  await pick(page, '왼쪽 맞춤').click()
  const cl = await box(page, '송신소'); expect(cl.x).toBeLessThan(r.x + 40)
  await page.keyboard.press('Enter')                                                                          // 고치기 — 칸이 왼쪽 끝 기준
  await expect(page.getByTestId('text-editor')).toBeVisible()
  expect(await page.getByTestId('text-editor').evaluate(el => [el.style.transform, el.style.textAlign])).toEqual(['translate(0px, -50%)', 'left'])
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape'); await clickScene(page, 150, 20)
  await pick(page, '가운데 맞춤').click()
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'rect').label.ha).toBe(undefined)   // 가운데 = 칸 없음(전과 같은 파일)
})

test('독립 글 = 줄끼리 맞춤(짧은 줄이 가운데·오른쪽으로)', async ({ page }) => {
  await openBoard(page, boardName('align2')); await load(page, [{ type: 'text', pos: [0, 0], text: '아주 긴 첫째 줄입니다\n짧게', font: 16, color: '#ff111111' }])
  const x0 = (await box(page, '짧게')).x, long = await box(page, '아주 긴')
  await clickScene(page, 20, 10)
  await pick(page, '가운데 맞춤').click(); await expect.poll(async () => (await liveDoc(page)).items[0].ha).toBe('center')   // 처음 = 왼쪽이라 가운데를 누르면 칸이 생김
  const xc = (await box(page, '짧게')).x; expect(xc).toBeGreaterThan(x0 + 10)
  await pick(page, '오른쪽 맞춤').click()
  const s = await box(page, '짧게'); expect(Math.abs(s.x + s.width - (long.x + long.width))).toBeLessThan(4)   // 오른쪽 끝이 긴 줄과 같음
})
