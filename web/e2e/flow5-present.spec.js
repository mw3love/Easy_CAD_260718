// 흐름 5 — 프레임으로 감싸기 → 순서 → 발표(넘기기·마지막 장 멈춤·판서·끝) → 새로고침
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, liveDoc, waitSaved } from './helpers.js'

test('프레임 셋 → 발표 넘기기·마지막에서 멈춤·판서는 「판서」 레이어 → 새로고침해도 프레임 순서 그대로', async ({ page }) => {
  const name = boardName('present')
  await openBoard(page, name); await setCam(page, { x: 320, y: 300, z: 0.5 })   // 왼쪽 도형 카드(폭 192) 밖에서 그리게
  for (const [i, x] of [0, 600, 1200].entries()) {
    await pickShape(page, '사각형'); await dragScene(page, { x, y: 0 }, { x: x + 300, y: 160 })
    await page.keyboard.type(`${i + 1}장`); await clickScene(page, x + 150, 500)
  }
  for (const x of [0, 600, 1200]) {
    await page.getByRole('button', { name: '프레임', exact: true }).click()
    await dragScene(page, { x: x - 40, y: -40 }, { x: x + 340, y: 200 })
  }
  let doc = await liveDoc(page)
  const frames = doc.items.filter(it => it.type === 'frame')
  expect(frames).toHaveLength(3)
  await expect(page.getByTestId('frame-row')).toHaveCount(3)

  await clickScene(page, 600, 700)   // 빈 곳 — 고른 프레임이 있으면 그 장부터 시작(의도된 동작)
  await page.getByRole('button', { name: '발표', exact: true }).click()
  const bar = page.getByTestId('present-bar')
  await expect(page.getByTestId('presenter')).toBeVisible()
  await expect(bar).toContainText('1 / 3')
  await page.keyboard.press('ArrowRight'); await expect(bar).toContainText('2 / 3')
  await page.keyboard.press('ArrowRight'); await page.keyboard.press('ArrowRight')
  await expect(bar).toContainText('3 / 3')                       // 마지막 장에서 멈춤
  await page.keyboard.press('ArrowLeft'); await expect(bar).toContainText('2 / 3')
  await page.keyboard.press('1')                                 // 펜
  const vp = page.viewportSize()
  await page.mouse.move(vp.width * 0.4, vp.height * 0.4); await page.mouse.down()
  await page.mouse.move(vp.width * 0.6, vp.height * 0.5, { steps: 6 }); await page.mouse.up()
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape')   // 도구 끄기 → 발표 끝
  await expect(page.getByTestId('presenter')).toBeHidden()
  doc = await liveDoc(page)
  const note = doc.items.find(it => it.type === 'path')
  expect(note).toBeTruthy()
  const layer = (doc.layers || []).find(l => l.id === note.layer_id)
  expect(layer?.name).toBe('판서')

  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  const back = (await liveDoc(page)).items.filter(it => it.type === 'frame')
  expect(back.map(f => f.uid)).toEqual(frames.map(f => f.uid))
})
