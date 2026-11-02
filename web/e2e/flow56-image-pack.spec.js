// 흐름 56 — 칠판에 담는 그림 크기(2026-11-02 실검증: 대화창 그림 1536×1024 PNG가 장당 3~4MB라 4장에 칠판 15MB, 밖에서 열면 10초 넘게 걸림)
// 크고 투명한 곳 없는 그림 = 긴 변 1600 · JPEG, 투명한 그림·작은 그림 = PNG 그대로. 칠판은 JPEG도 그림(이름표 `imgSrc`).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc } from './helpers.js'

const attach = (page, w, h, alpha) => page.evaluate(async ([w, h, alpha]) => {
  const cv = document.createElement('canvas'); cv.width = w; cv.height = h; const g = cv.getContext('2d'), im = g.createImageData(w, h)
  for (let i = 0; i < im.data.length; i += 4) { im.data[i] = Math.random() * 255; im.data[i + 1] = Math.random() * 255; im.data[i + 2] = Math.random() * 255; im.data[i + 3] = alpha && i % 40 === 0 ? 120 : 255 }   // 잡음 = PNG가 큼
  g.putImageData(im, 0, 0)
  const blob = await new Promise(ok => cv.toBlob(ok, 'image/png'))
  await window.__mb.ed.attachFiles([new File([blob], 'big.png', { type: 'image/png' })])
}, [w, h, alpha])

test('큰 그림 = 줄여서 JPEG · 투명 그림 = PNG · 칠판에 보임', async ({ page }) => {
  await openBoard(page, boardName('imgpack')); await setCam(page)
  await attach(page, 2400, 1600, false)
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'image').length).toBe(1)
  const big = (await liveDoc(page)).items.find(it => it.type === 'image')
  expect(big.data.startsWith('/9j/')).toBe(true)                               // JPEG
  const wh = await page.evaluate(d => new Promise(ok => { const i = new Image(); i.onload = () => ok([i.naturalWidth, i.naturalHeight]); i.src = 'data:image/jpeg;base64,' + d }), big.data)
  expect(Math.max(...wh)).toBe(1600)                                           // 긴 변 1600까지
  await expect(page.locator('svg image[href^="data:image/jpeg"]')).toHaveCount(1) // 칠판이 jpeg 이름표로 그림
  await attach(page, 800, 600, true)
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'image').length).toBe(2)
  const kinds = (await liveDoc(page)).items.filter(it => it.type === 'image').map(it => it.data.slice(0, 4)).sort()
  expect(kinds).toEqual(['/9j/', 'iVBO'])                                       // 투명한 곳이 있으면 PNG 그대로
})
