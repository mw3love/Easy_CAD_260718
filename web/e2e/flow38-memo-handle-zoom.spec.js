// 흐름 38 — 메모 줄 손잡이 ⠿는 화면에서 늘 같은 크기라 많이 줄이면 줄 여럿에 걸침 → 60% 밑에선 숨김(2026-10-26 사용자).
// 81~60%는 메모 바깥 왼쪽에 뜸. 데스크톱은 tests/test_part67 test_handle_hidden_when_zoomed_far_out.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage } from './helpers.js'

const DOC = { format: 'easycad-doc', version: 1, items: [{ type: 'memo', uid: 'm1', pos: [0, 0], scale: 1, rotation: 0, z: 1, origin: [0, 0], locked: false, group_id: null, layer_id: null,
  rect: [0, 0, 340, 120], lines: [{ k: 'p', text: '첫째 줄' }, { k: 'p', text: '둘째 줄' }, { k: 'p', text: '셋째 줄' }] }] }
const handle = page => page.locator('svg rect[fill="rgba(127,127,127,.16)"]')

test('메모 줄 손잡이 — 70%는 바깥에 보임, 50%는 숨김', async ({ page }) => {
  await page.route('**/memo-handle.ecad', r => r.fulfill({ json: DOC }))
  await openBoard(page, boardName('mhandle'))
  await page.evaluate(() => window.__mb.open('/memo-handle.ecad'))
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)

  const hoverLine = async () => { const p = await toPage(page, 120, 40); await page.mouse.move(p.x + 30, p.y); await page.mouse.move(p.x, p.y) }
  await setCam(page, { x: 300, y: 200, z: 0.7 })
  await hoverLine()
  await expect(handle(page)).toHaveCount(1)
  const b = await handle(page).boundingBox(), left = (await toPage(page, 0, 0)).x
  expect(b.x + b.width).toBeLessThan(left)                                            // 70% = 메모 바깥 왼쪽
  expect(Math.round(b.width)).toBe(16)                                                // 화면에서 늘 16px

  await setCam(page, { x: 300, y: 200, z: 0.5 })
  await expect(handle(page)).toHaveCount(0)                                           // 휠로 줄여 마우스가 안 움직여도 사라짐
  await hoverLine()
  await expect(handle(page)).toHaveCount(0)                                           // 50% = 손잡이 없음
})
