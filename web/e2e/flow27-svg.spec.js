// 흐름 27 — SVG → 고칠 수 있는 도형(§8 항목63 1단계, 2026-10-23): 파일 끌어 놓기·SVG 코드 붙여넣기, 못 읽는 모양은 그림
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, liveDoc, toPage, waitSaved } from './helpers.js'

const ICON = readFileSync(new URL('../../tests/fixtures/svg_ai/claude-sonnet-5-5__0.svg', import.meta.url), 'utf-8')   // KAIROS가 만든 파라볼라 안테나(0단계 실측)
const DESK = JSON.parse(readFileSync(new URL('../test/fixtures/svg_cases.json', import.meta.url))).find(c => c.name === 'AI claude-sonnet-5-5__0.svg').items

const dropSvg = (page, name, text, p) => page.evaluate(([n, t, x, y]) => {
  const dt = new DataTransfer(); dt.items.add(new File([t], n, { type: 'image/svg+xml' }))
  document.elementFromPoint(x, y).dispatchEvent(new DragEvent('drop', { dataTransfer: dt, clientX: x, clientY: y, bubbles: true, cancelable: true }))
}, [name, text, p.x, p.y])
const pasteText = (page, text) => page.evaluate(t => {
  const dt = new DataTransfer(); dt.setData('text/plain', t)
  window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }))
}, text)
const box = its => { const xs = [], ys = []
  for (const it of its) { const pts = it.line ? [[it.line[0], it.line[1]], [it.line[2], it.line[3]]] : it.rect ? [[it.rect[0], it.rect[1]], [it.rect[0] + it.rect[2], it.rect[1] + it.rect[3]]] : it.pts || it.elements?.map(e => e.slice(-2)) || []
    for (const [x, y] of pts) { xs.push(x + it.pos[0]); ys.push(y + it.pos[1]) } }
  return { cx: (Math.min(...xs) + Math.max(...xs)) / 2, cy: (Math.min(...ys) + Math.max(...ys)) / 2, w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) } }

test('SVG 파일 놓기 = 데스크톱과 같은 도형(묶음 하나로 다 고른 채), 코드 붙여넣기도, 못 읽는 모양은 그림, 다시 열어도 그대로', async ({ page }) => {
  const name = boardName('svg')
  await openBoard(page, name); await setCam(page)
  await dropSvg(page, '안테나.svg', ICON, await toPage(page, 300, 200))
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(DESK.length)
  const its = (await liveDoc(page)).items
  expect(its.map(it => it.type)).toEqual(DESK.map(it => it.type))                       // 데스크톱과 같은 종류·차례
  expect(its[0].group_id).toBeTruthy(); expect(its.every(it => it.group_id === its[0].group_id)).toBe(true)   // 묶음 하나(2026-10-25 사용자 — 옛 「묶지 않음」을 뒤집음)
  expect(its.filter(it => it.type !== 'text').every(it => it.fill == null && it.width > 0)).toBe(true)   // 채움 없음·지금 펜
  expect(await page.evaluate(() => window.__mb.ed.getSel().length)).toBe(DESK.length)   // 다 고른 채
  const b = box(its)
  expect(Math.abs(b.cx - 300)).toBeLessThan(25); expect(Math.abs(b.cy - 200)).toBeLessThan(25)   // 놓은 자리가 가운데(viewBox 가운데 = 그림 가운데는 아님 — 넉넉히)
  expect(Math.max(b.w, b.h)).toBeLessThanOrEqual(160.5)                                  // 긴 변 160(데스크톱 `_SVG_LONG`)

  await page.keyboard.press('Control+z')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(0)              // Ctrl+Z 한 번

  await page.mouse.move(...Object.values(await toPage(page, 500, 300)))
  await pasteText(page, '<svg viewBox="0 0 10 10"><rect x="1" y="1" width="8" height="8"/><line x1="0" y1="0" x2="10" y2="10"/></svg>')   // AI 답에서 복사한 SVG 코드
  await expect.poll(async () => (await liveDoc(page)).items.map(it => it.type)).toEqual(['rect', 'line'])

  await dropSvg(page, '로고.svg', '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20" viewBox="0 0 40 20"><g transform="translate(10 0)"><rect width="10" height="10"/></g></svg>', await toPage(page, 700, 200))
  await expect.poll(async () => (await liveDoc(page)).items.map(it => it.type)).toEqual(['rect', 'line', 'image'])   // 옮기기가 든 SVG = 그림

  await waitSaved(page)
  await openBoard(page, name)
  await expect.poll(async () => (await liveDoc(page)).items.map(it => it.type)).toEqual(['rect', 'line', 'image'])
})
