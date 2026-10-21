// 흐름 2 — 메모(마크다운 입력·할 일·새로고침)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, waitSaved } from './helpers.js'

test('메모에 제목·목록·할 일을 마크다운으로 쓰고 새로고침해도 그대로', async ({ page }) => {
  const name = boardName('memo')
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '메모', exact: true }).click()
  await expect(page.getByText('치면 바로 써져요')).toBeVisible()          // 만들면 고른 채 — 치면 바로 글(2026-10-20)
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

test('메모 안 표 — 두 번 눌러 칸 고치기 · Tab = 다음 칸(마지막 칸이면 줄 더함) · 칸 너비 그대로 · 새로고침해도 그대로', async ({ page }) => {   // 2026-10-21 사용자: md 하나 = 메모 하나
  const name = boardName('memotbl')
  await openBoard(page, name); await setCam(page)
  await page.evaluate(t => { const dt = new DataTransfer(); dt.setData('text/plain', t); window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })) },
    '점검\n\n| 항목 | 상태 |\n|---|---|\n| 안테나 | 정상 |')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  const cw0 = (await liveDoc(page)).items[0].lines[1].cw
  const cell = page.locator('svg text', { hasText: '정상' }).first(), b = await cell.boundingBox()
  await page.mouse.dblclick(b.x + b.width / 2, b.y + b.height / 2)
  const td = page.locator('[data-testid=memo-editor] td', { hasText: '정상' })
  await expect(td).toBeVisible()
  await td.click(); await page.keyboard.press('End'); await page.keyboard.type(' 확인')
  await page.keyboard.press('Tab'); await page.keyboard.type('급전선'); await page.keyboard.press('Tab'); await page.keyboard.type('교체')
  await clickScene(page, 900, 600)
  const T = (await liveDoc(page)).items[0].lines[1]
  expect(T.rows).toEqual([['항목', '상태'], ['안테나', '정상 확인'], ['급전선', '교체']]); expect(T.cw).toEqual(cw0); expect(T.header).toBe(true)
  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  expect((await liveDoc(page)).items[0].lines[1]).toEqual(T)
})
