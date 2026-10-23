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

test('화살표 붙은 상자를 오른쪽 아래 손잡이로 키워도 — 끝이 같은 변 가운데에 붙어 있음(2026-10-20 사용자: 떨어지고 길이 틀어졌음)', async ({ page }) => {
  const name = boardName('arrowsize')
  await openBoard(page, name); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 120, y: 60 })
  await clickScene(page, 700, 500)
  await pickShape(page, '사각형'); await dragScene(page, { x: 400, y: 0 }, { x: 520, y: 60 })
  await clickScene(page, 700, 500)
  await page.keyboard.press('2')
  await dragScene(page, { x: 60, y: 30 }, { x: 460, y: 30 })
  await page.keyboard.press('Escape')
  await clickScene(page, 60, 30)                                // A 고르기
  await dragScene(page, { x: 120, y: 60 }, { x: 200, y: 100 })  // 오른쪽 아래 손잡이로 키움
  const a = arrowOf(await liveDoc(page))
  expect(ends(a)[0]).toEqual([200, 50])                         // 커진 A의 오른쪽 변 가운데
  expect(ends(a)[1]).toEqual([400, 30])
  await page.keyboard.press('Control+z')
  expect(ends(arrowOf(await liveDoc(page)))).toEqual([[120, 30], [400, 30]])
})

test('프레임 테두리에도 화살표가 붙음 · 프레임 속 빈 곳은 안 붙음(2026-10-23 사용자: 프레임엔 큐닷이 없어 안 붙었음)', async ({ page }) => {
  const name = boardName('arrowframe')
  await openBoard(page, name); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 40, y: 40 }, { x: 160, y: 120 })
  await clickScene(page, 700, 500)
  for (const x of [0, 500]) {
    await page.getByRole('button', { name: '프레임', exact: true }).click()
    await dragScene(page, { x, y: 0 }, { x: x + 300, y: 200 })
  }
  await clickScene(page, 700, 500)
  let doc = await liveDoc(page)
  const [f1, f2] = doc.items.filter(it => it.type === 'frame'), box = doc.items.find(it => it.type === 'rect')
  await page.keyboard.press('2')
  await dragScene(page, { x: 300, y: 100 }, { x: 500, y: 100 })   // 프레임 오른쪽 변 → 다음 프레임 왼쪽 변
  doc = await liveDoc(page)
  let a = arrowOf(doc)
  expect([a.bind1, a.bind2]).toEqual([doc.items.indexOf(doc.items.find(it => it.uid === f1.uid)), doc.items.indexOf(doc.items.find(it => it.uid === f2.uid))])   // 붙은 곳 = 항목 순번
  expect(ends(a)).toEqual([[300, 100], [500, 100]])
  await page.keyboard.press('Escape')
  await page.keyboard.press('2')
  await dragScene(page, { x: 100, y: 80 }, { x: 240, y: 170 })    // 상자 안 → 프레임 속 빈 곳
  doc = await liveDoc(page)
  a = doc.items.filter(it => it.type === 'sarrow')[1]
  expect(a.bind1).toBe(doc.items.findIndex(it => it.uid === box.uid))
  expect(a.bind2 ?? null).toBeNull()                              // 프레임 속은 안의 도형 몫 — 프레임에 붙지 않음
})

test('여러 개 고르면 속성 카드 맨 위에 정렬 아이콘 줄 — 왼쪽 맞춤 · 3개부터 균등 분배(2026-10-23 사용자: 우클릭 메뉴를 못 찾음)', async ({ page }) => {
  await openBoard(page, boardName('alignrow')); await setCam(page)
  for (const [x, y] of [[0, 0], [260, 140], [90, 300]]) { await pickShape(page, '사각형'); await dragScene(page, { x, y }, { x: x + 120, y: y + 60 }); await clickScene(page, 900, 600) }
  await clickScene(page, 60, 30)
  await expect(page.getByTestId('align-row')).toHaveCount(0)                   // 하나만 고르면 없음
  await page.keyboard.press('Control+a')
  await expect(page.getByTestId('align-row')).toBeVisible()
  await page.getByRole('button', { name: '왼쪽 맞춤' }).click()
  let rs = (await liveDoc(page)).items.filter(it => it.type === 'rect')
  expect(rs.map(r => r.pos[0])).toEqual([0, 0, 0])
  await page.getByRole('button', { name: '세로 균등 분배' }).click()
  rs = (await liveDoc(page)).items.filter(it => it.type === 'rect').sort((a, b) => a.pos[1] - b.pos[1])
  expect(rs[1].pos[1] - (rs[0].pos[1] + 60)).toBeCloseTo(rs[2].pos[1] - (rs[1].pos[1] + 60), 3)
  await page.keyboard.press('Control+z'); await page.keyboard.press('Control+z')
  expect((await liveDoc(page)).items.filter(it => it.type === 'rect').map(r => r.pos[0])).toEqual([0, 260, 90])
})
