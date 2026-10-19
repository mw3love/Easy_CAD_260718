// 흐름 2 — 메모(마크다운 입력·할 일·새로고침)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, waitSaved } from './helpers.js'

test('메모에 제목·목록·할 일을 마크다운으로 쓰고 새로고침해도 그대로', async ({ page }) => {
  const name = boardName('memo')
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '메모', exact: true }).click()
  await expect(page.getByTestId('memo-editor')).toBeVisible()
  await page.keyboard.type('# 회의 정리'); await page.keyboard.press('Enter')
  await page.keyboard.type('- 첫째'); await page.keyboard.press('Enter'); await page.keyboard.press('Enter')
  await page.keyboard.type('[] 할 일')
  await clickScene(page, 900, 600)
  const doc = await liveDoc(page)
  console.log(JSON.stringify(doc.items.map(it => [it.type, it.lines])))
  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  const back = await liveDoc(page)
  expect(back.items[0].lines).toEqual(doc.items[0].lines)
})
