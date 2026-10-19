// 흐름 4 — 화살표로 잇기·도형 옮기면 따라옴·되돌리기
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, liveDoc, waitSaved, savedDoc } from './helpers.js'

const arrowOf = d => d.items.find(it => it.type === 'sarrow')
const ends = a => [a.pts[0], a.pts[a.pts.length - 1]].map(([x, y]) => [x + a.pos[0], y + a.pos[1]])

test('상자 한가운데끼리 화살표 — 양 끝 다 붙고, 옮기면 따라오고, 되돌리면 제자리', async ({ page }) => {
  const name = boardName('arrow')
  await openBoard(page, name); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 120, y: 60 })
  await clickScene(page, 700, 500)
  await pickShape(page, '사각형'); await dragScene(page, { x: 400, y: 0 }, { x: 520, y: 60 })
  await clickScene(page, 700, 500)
  await page.keyboard.press('2')
  await dragScene(page, { x: 60, y: 30 }, { x: 460, y: 30 })   // 상자 '안'에서 시작해 상자 '안'에 놓음
  let a = arrowOf(await liveDoc(page))
  expect(a.bind1).not.toBeNull()   // 2026-10-19 다잡기 전엔 시작 쪽이 안 붙고 상자 속을 지나 위로 돌아 들어갔음
  expect(a.bind2).not.toBeNull()
  expect(ends(a)).toEqual([[120, 30], [400, 30]])   // A 오른쪽 변 가운데 → B 왼쪽 변 가운데, 곧게
  expect(a.pts).toHaveLength(2)

  await clickScene(page, 460, 50)                               // B 고르기
  await dragScene(page, { x: 460, y: 50 }, { x: 460, y: 250 })  // B를 아래로 200
  a = arrowOf(await liveDoc(page))
  const [, end] = ends(a)
  expect(end[1]).toBeGreaterThan(150)                           // 끝이 B를 따라 내려감
  await waitSaved(page)
  expect(ends(arrowOf(savedDoc(name)))[1][1]).toBeGreaterThan(150)

  await page.keyboard.press('Control+z')
  const doc = await liveDoc(page)
  expect(doc.items.filter(it => it.type === 'rect')[1].pos).toEqual([400, 0])
  expect(ends(arrowOf(doc))).toEqual([[120, 30], [400, 30]])
})
