// 흐름 1 — 열기·그리기·바로 치기·새로고침(매일 쓰는 가장 기본)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, liveDoc, savedDoc, waitSaved } from './helpers.js'

test('사각형 그리고 바로 글 치고 새로고침해도 그대로', async ({ page }) => {
  const name = boardName('basic')
  await openBoard(page, name); await setCam(page)
  await pickShape(page, '사각형')
  await dragScene(page, { x: 0, y: 0 }, { x: 200, y: 100 })
  let doc = await liveDoc(page)
  expect(doc.items.filter(it => it.type === 'rect')).toHaveLength(1)
  await page.keyboard.type('안녕 A1')   // 고른 채로 바로 치기 = 새로 씀
  await clickScene(page, 600, 400)      // 빈 곳 = 고치기 끝
  doc = await liveDoc(page)
  await waitSaved(page)
  await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  const back = await liveDoc(page)
  expect(back.items).toHaveLength(1)
  expect(JSON.stringify(back.items[0])).toContain('안녕 A1')
  expect(JSON.stringify(savedDoc(name).items[0])).toContain('안녕 A1')
})
