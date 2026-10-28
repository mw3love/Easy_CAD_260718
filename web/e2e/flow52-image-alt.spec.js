// 흐름 52 — 그림 설명 자동(2026-10-28): 붙여 넣은 그림 → 서버 `/api/describe`(가짜) → 보이지 않는 설명 `alt` → 대화 재료에 「[그림] …」.
// 늦게 오는 고침이라 되돌리기에 안 남음 — Ctrl+Z 한 번 = 그림째 사라짐. 설명이 이미 있는 그림(대화창 그림 = 요청 글)은 안 부름.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc } from './helpers.js'

const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII='

test('붙여 넣은 그림 = 설명이 alt로 · 고른 채 묻기에 실림 · Ctrl+Z 한 번 = 그림째', async ({ page }) => {
  const asked = []
  await page.route('**/api/describe', async r => { asked.push(r.request().postDataJSON()); await new Promise(ok => setTimeout(ok, 300)); await r.fulfill({ json: { text: '빨간 점 네 개가 찍힌 작은 그림', model: 'fake', elapsed: 0.3 } }) })
  await openBoard(page, boardName('alt')); await setCam(page)
  await page.evaluate(async b64 => { const f = new File([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], 'a.png', { type: 'image/png' }); await window.__mb.ed.attachFiles([f]) }, PNG)
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'image')?.alt).toBe('빨간 점 네 개가 찍힌 작은 그림')
  expect(asked).toHaveLength(1); expect(asked[0].data).toMatch(/^data:image\/png;base64,/)
  expect(await page.evaluate(() => window.__mb.ed.selTexts())).toEqual(['[그림] 빨간 점 네 개가 찍힌 작은 그림'])   // 대화·정리 재료
  await page.keyboard.press('Control+z')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(0)      // 설명은 되돌리기 칸이 아님
})
