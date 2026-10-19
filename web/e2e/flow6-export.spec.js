// 흐름 6 — 내보내기: HTML 공유 파일이 인터넷 없이 열리고, PNG가 그림 파일로 나옴. (PDF는 브라우저 인쇄 창 — 자동 시험 밖, 손 확인 몫)
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene } from './helpers.js'

async function exportAs(page, fmt) {
  await page.getByRole('button', { name: '내보내기', exact: true }).click()
  const form = page.locator('div', { hasText: /^내보내기/ }).filter({ has: page.getByTestId('export-preview') }).last()
  await form.getByRole('button', { name: fmt, exact: true }).click()
  await expect(page.getByTestId('export-thumb').first()).toBeVisible()
  const dl = page.waitForEvent('download')
  await form.getByRole('button', { name: '내보내기', exact: true }).click()
  const d = await dl
  return { name: d.suggestedFilename(), path: await d.path() }
}

test('HTML 공유 파일 — 인터넷 없이 열려 칠판 글이 보임 / PNG — 그림 파일', async ({ page, context, browser }) => {
  const name = boardName('export')
  await openBoard(page, name); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 220, y: 100 })
  await page.keyboard.type('송신 계통'); await clickScene(page, 700, 500)

  const html = await exportAs(page, 'HTML')
  expect(html.name).toMatch(/\.html$/)
  const off = await browser.newContext({ offline: true }), p2 = await off.newPage()
  const failed = []; p2.on('requestfailed', r => failed.push(r.url()))
  await p2.goto(pathToFileURL(html.path).href)
  await expect(p2.getByText('송신 계통').first()).toBeAttached()
  expect(failed.filter(u => !u.startsWith('file:') && !u.startsWith('data:'))).toEqual([])   // 밖으로 나가는 요청 없음
  await off.close()

  const png = await exportAs(page, 'PNG')
  expect(png.name).toMatch(/\.png$/)
  const buf = readFileSync(png.path)
  expect(buf.subarray(1, 4).toString()).toBe('PNG')
  expect(buf.length).toBeGreaterThan(2000)
})
