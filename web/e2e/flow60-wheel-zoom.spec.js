// 흐름 60 — 휠 확대(2026-11-04 사용자: 예시 칠판에서 휠 확대가 매끄럽지 않음)
// 칠판 svg는 CSS로 옮기고 늘림(SVG transform 배율을 바꾸면 크롬이 글자를 전부 다시 배치 — 2026-11-05), 휠 한 칸(15%)은 0.12초에 걸쳐 미끄러지듯(Editor `wheelZoom`)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam } from './helpers.js'

const camOf = page => page.evaluate(() => window.__mb.getCam())

test('휠 세 칸 = 마우스 자리 그대로 1.15³배(미끄러지듯) · 칠판은 CSS로 · 굴리는 중 누르면 그 자리에서 멈춤', async ({ page }) => {
  const board = await openBoard(page, boardName('wheel')); await setCam(page, { x: 100, y: 80, z: 1 })
  const b = await board.boundingBox(), mx = b.x + 500, my = b.y + 300
  await page.mouse.move(mx, my)
  for (let i = 0; i < 3; i++) await page.mouse.wheel(0, -100)
  const seen = await page.evaluate(() => new Promise(res => { const zs = [], t0 = performance.now(); const f = () => { zs.push(window.__mb.getCam().z); if (performance.now() - t0 < 120) requestAnimationFrame(f); else res(zs) }; requestAnimationFrame(f) }))
  expect(seen.some(z => z > 1.001 && z < 1.15 ** 3 - 0.001)).toBe(true)               // 중간 배율을 거쳐 감(한 번에 뛰지 않음)
  await expect.poll(async () => (await camOf(page)).z, { timeout: 3000 }).toBeCloseTo(1.15 ** 3, 4)
  const c = await camOf(page)
  expect((mx - b.x - c.x) / c.z).toBeCloseTo(500 - 100, 4)                            // 마우스 아래 칠판 자리 그대로
  expect((my - b.y - c.y) / c.z).toBeCloseTo(300 - 80, 4)
  const t = (await board.evaluate(el => el.querySelector(':scope > svg').style.transform)).match(/translate\(([-\d.e]+)px, ([-\d.e]+)px\) scale\(([-\d.e]+)\)/)   // 칠판 = CSS
  expect(+t[1]).toBeCloseTo(c.x, 2); expect(+t[2]).toBeCloseTo(c.y, 2); expect(+t[3]).toBeCloseTo(c.z, 4)

  await page.mouse.wheel(0, 100)                                                      // 줄이는 중에 누르기
  await page.waitForTimeout(30)
  await page.mouse.down({ button: 'middle' }); await page.mouse.up({ button: 'middle' })
  await page.waitForTimeout(50); const z = (await camOf(page)).z
  expect(z).toBeLessThan(1.15 ** 3); expect(z).toBeGreaterThan(1.15 ** 2 + 0.001)    // 다 가기 전에 멈춤
  await page.waitForTimeout(300)
  expect((await camOf(page)).z).toBe(z)                                               // 누른 뒤엔 더 안 움직임
})
