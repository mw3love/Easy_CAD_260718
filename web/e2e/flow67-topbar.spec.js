// 흐름 67 — 위 막대 2단 쌓기(2026-11-08 시안 D): 넓은 창 = 높이 54 그대로 · 작은 버튼 2단 · 겹침 없음, 좁은 창 = 예전처럼 아이콘 한 줄
import { test, expect } from '@playwright/test'
import { boardName, openBoard } from './helpers.js'

const btn = (page, name) => page.getByRole('button', { name, exact: true })
const rect = async (page, name) => btn(page, name).boundingBox()

test('넓은 창 — 칠판 높이 그대로, 저장·내보내기는 위아래로, 큰 버튼은 두 칸 높이, 겹침 없음', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 })
  await openBoard(page, boardName('topbar'))
  expect((await page.getByTestId('board').boundingBox()).y).toBeLessThanOrEqual(55)
  const save = await rect(page, '저장'), exp = await rect(page, '내보내기'), sel = await rect(page, '선택')
  expect(Math.abs(save.x - exp.x)).toBeLessThan(1); expect(exp.y).toBeGreaterThan(save.y)
  expect(save.height).toBeLessThanOrEqual(21); expect(sel.height).toBeGreaterThanOrEqual(40)
  const names = ['저장', '내보내기', '되돌리기', '다시', '선택', '화살표', '글자', '선', '다각형', '펜', '번호', '유지', '프레임', '메모', '회의', '웹', '표', '발표', '전체 화면', '어둡게']
  const rs = await Promise.all(names.map(n => rect(page, n)))
  rs.forEach((r, i) => expect(r, names[i]).toBeTruthy())
  for (let i = 0; i < rs.length; i++) for (let j = i + 1; j < rs.length; j++) {
    const a = rs[i], b = rs[j]
    expect(a.x < b.x + b.width - 1 && b.x < a.x + a.width - 1 && a.y < b.y + b.height - 1 && b.y < a.y + a.height - 1, `${names[i]}/${names[j]}`).toBe(false)
  }
  await btn(page, '선').click(); await expect(btn(page, '선')).toHaveAttribute('aria-pressed', 'true')
  // 아이콘 2색(시안 I1): 채운 부분만 파랑, KAIROS 흰색은 그대로
  const fill = (name, sel) => btn(page, name).locator(sel).first().evaluate(el => getComputedStyle(el).fill)
  expect(await fill('프레임', 'svg [fill="currentColor"]')).toBe('rgb(37, 99, 235)')
  expect(await fill('프레임', 'svg > :first-child')).toBe('none')
  expect(await btn(page, 'KAIROS').locator('span[aria-hidden]').evaluate(el => el.className)).toBe('')
})

test('좁은 창 — 2단 없이 아이콘 한 줄', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await openBoard(page, boardName('topnarrow'))
  const save = await rect(page, '저장'), exp = await rect(page, '내보내기')
  expect(Math.abs(save.y - exp.y)).toBeLessThan(1); expect(exp.x).toBeGreaterThan(save.x)
})
