// 흐름 15 — 데스크톱 문서를 웹 칠판에서 열고 하나 고쳐 저장해도 나머지 칸이 그대로(§8 항목61 ④-1). 순수 변환만 보는 web/test/roundtrip.test.mjs의 실제 화면판.
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, pickShape, dragScene, waitSaved, savedDoc } from './helpers.js'

const desk = JSON.parse(readFileSync(new URL('../../tests/fixtures/all_types.ecad', import.meta.url), 'utf-8'))

test('데스크톱 모든 종류 → 웹에서 열고 상자 하나 더해 저장 → 원래 도형들의 칸 그대로', async ({ page }) => {
  const name = boardName('roundtrip')
  await openBoard(page, name)
  await page.evaluate(() => window.__mb.open('/samples/all_types.ecad'))
  await expect.poll(async () => (await page.evaluate(() => window.__mb.toEcad())).items.length).toBe(desk.items.length)
  await setCam(page, { x: 400, y: 2400, z: 1 })                                   // 빈 곳(도면 아래)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: -2000 }, { x: 80, y: -1960 })
  await waitSaved(page)
  const saved = savedDoc(name)
  expect(saved.items).toHaveLength(desk.items.length + 1)
  const bad = []
  desk.items.forEach((a, i) => {
    const b = saved.items[i]
    for (const [k, v] of Object.entries(a)) if (JSON.stringify(b[k]) !== JSON.stringify(v)) bad.push([a.type, k, JSON.stringify(v).slice(0, 60), JSON.stringify(b[k]).slice(0, 60)])
    for (const k of Object.keys(b)) if (!(k in a) && k !== 'uid') bad.push([a.type, '+' + k])
  })
  expect(bad).toEqual([])
})
