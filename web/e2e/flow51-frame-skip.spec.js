// 흐름 51 — 프레임 「발표」 켜고 끄기 + 「프레임으로 감싸고 AI 말풍선」(2026-10-28 사용자).
// 끈 프레임 = 칠판엔 그대로 · 판 번호 「—」 · 발표·「프레임만」 내보내기에서 빠짐. 여럿 우클릭 = 프레임(처음부터 발표 꺼짐)으로 감싸고 그 프레임 말풍선 — 안의 그림까지 보냄. 진짜 KAIROS는 안 부름.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, liveDoc, toPage } from './helpers.js'

const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII='

test('발표 끄기 = 판 「—」·발표에서 빠짐·칠판엔 그대로 · 다시 켜면 돌아옴', async ({ page }) => {
  await openBoard(page, boardName('fskip')); await setCam(page, { x: 320, y: 300, z: 0.5 })
  for (const [i, x] of [0, 600, 1200].entries()) {
    await pickShape(page, '사각형'); await dragScene(page, { x, y: 0 }, { x: x + 300, y: 160 })
    await page.keyboard.type(`${i + 1}장`); await clickScene(page, x + 150, 500)
  }
  for (const x of [0, 600, 1200]) {
    await page.getByRole('button', { name: '프레임', exact: true }).click()
    await dragScene(page, { x: x - 40, y: -40 }, { x: x + 340, y: 200 })
  }
  await page.getByTestId('dock-frame').click()
  const rows = page.getByTestId('frame-row')
  await expect(rows).toHaveCount(3)
  await rows.nth(1).getByTestId('frame-skip').click()                               // 2장 끄기
  await expect(rows.nth(1).getByTestId('frame-skip')).toHaveAttribute('aria-pressed', 'false')
  await expect(rows.nth(1)).toContainText('—'); await expect(rows.nth(2)).toContainText('2')   // 번호 = 발표 순서
  let frames = (await liveDoc(page)).items.filter(it => it.type === 'frame')
  expect(frames.map(f => !!f.skip)).toEqual([false, true, false])
  expect(frames).toHaveLength(3)                                                    // 칠판엔 그대로
  await clickScene(page, 600, 700)
  await page.getByRole('button', { name: '발표', exact: true }).click()
  const bar = page.getByTestId('present-bar')
  await expect(bar).toContainText('1 / 2')
  await page.keyboard.press('ArrowRight'); await expect(bar).toContainText('2 / 2')
  await page.keyboard.press('Escape'); await expect(page.getByTestId('presenter')).toBeHidden()
  // 「프레임만」 내보내기 = 켠 프레임 둘
  expect(await page.evaluate(async () => (await window.__mb.ed.exportPages({ scope: 'frames', format: 'png', preview: true })).pages?.length)).toBe(2)
  await rows.nth(1).click({ button: 'right' }); await page.getByText('발표에 넣기').click()   // 우클릭으로 다시 켜기
  await expect(rows.nth(1)).toContainText('2')
  frames = (await liveDoc(page)).items.filter(it => it.type === 'frame')
  expect(frames.some(f => f.skip)).toBe(false)
  await page.keyboard.press('Control+z')                                            // 되돌리기 한 번 = 다시 꺼짐
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'frame' && it.skip).length).toBe(1)
})

test('여럿 우클릭 「프레임으로 감싸고 AI 말풍선」 = 발표 꺼진 프레임 + 그 말풍선(안 N개 · 그림까지)', async ({ page }) => {
  const seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b); return r.fulfill({ json: { kind: 'bubble', content: '둘 다 봤어요.', model: 'fake-model', elapsed: 0.1 } }) })
  await openBoard(page, boardName('fwrap'), { chat: true }); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 160, y: 100 })
  await page.keyboard.type('송신기'); await clickScene(page, 600, 600)
  await page.evaluate(async b64 => { const f = new File([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], 'a.png', { type: 'image/png' }); await window.__mb.ed.attachFiles([f]) }, PNG)
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(2)
  await page.keyboard.press('Control+a')
  const p = await toPage(page, 80, 50)
  await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.getByText('프레임으로 감싸고 AI 말풍선 (KAIROS)').click()
  const fr = (await liveDoc(page)).items.find(it => it.type === 'frame')
  expect(fr?.skip).toBe(true)                                                       // 토론용 = 발표 꺼짐
  const bub = page.getByTestId('bubble'); await expect(bub).toBeVisible()
  await expect(bub.getByTestId('bubble-scope')).toContainText('프레임 안 2개를 보고 답해요')
  await bub.getByTestId('bubble-input').fill('뭐가 있어?'); await bub.getByTestId('bubble-input').press('Enter')
  await expect(bub.getByTestId('bubble-a')).toContainText('둘 다 봤어요.')
  expect(seen[0].item.type).toBe('frame')
  expect(seen[0].item.text).toContain('송신기')
  expect(seen[0].item.images).toHaveLength(1)                                       // 프레임 안 그림도
  expect(seen[0].item.images[0]).toMatch(/^data:image\/jpeg/)
})
