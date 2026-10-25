// 흐름 28 — 아이콘(§8 항목63 2~3단계, 2026-10-23): 「+ › ✏️ 아이콘」 이름표 → ✏️ 후보 둘(칠판에 들어갈 도형 그대로 미리보기) → 누르면 빈자리에 고칠 수 있는 도형(묶음 하나 — 2026-10-25)
// → 「선을 더 굵게」 = 고른 아이콘을 실어 보냄 → 다른 후보는 끌어 놓은 자리에. KAIROS는 가짜(/api/chat) — 서버 쪽은 tests/test_part70, 진짜 아이콘은 손 확인.
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, liveDoc, toPage } from './helpers.js'

const ICON = readFileSync(new URL('../../tests/fixtures/svg_ai/claude-sonnet-5-5__0.svg', import.meta.url), 'utf-8')
const ICON2 = readFileSync(new URL('../../tests/fixtures/svg_ai/claude-sonnet-5-5__3.svg', import.meta.url), 'utf-8')
const DESK = JSON.parse(readFileSync(new URL('../test/fixtures/svg_cases.json', import.meta.url))).find(c => c.name === 'AI claude-sonnet-5-5__0.svg').items

test('아이콘 → 후보 둘 → 누르면 고칠 수 있는 도형 → 「선을 더 굵게」는 고른 아이콘으로 → 끌어 놓기', async ({ page }) => {
  const sent = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); sent.push(b)
    return r.fulfill({ json: b.base_svg ? { kind: 'icon', content: '고른 아이콘을 바탕으로 고쳤어요 — 누르면 칠판에 붙어요', svgs: [ICON], model: 'icon-m', elapsed: 2.5 }
      : { kind: 'icon', content: '아이콘 후보 2개 — 누르면 칠판에 붙어요(선 하나하나 고칠 수 있어요)', svgs: [ICON, ICON2], model: 'icon-m', elapsed: 7.8 } }) })
  await openBoard(page, boardName('icon'), { chat: true }); await setCam(page)
  await page.getByTestId('plus').click()                                             // 「+ › ✏️ 아이콘」 — 「아이콘」은 뜻이 둘이라 자동으론 그림(2026-10-23 사용자)
  await page.getByRole('menuitemradio', { name: /아이콘/ }).click()
  await expect(page.getByTestId('tool-chip')).toHaveText('✏️ 아이콘 만들기 (SVG) ✕')
  await page.getByPlaceholder('무엇의 아이콘', { exact: false }).click()
  await page.keyboard.type('파라볼라 안테나'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-kind')).toHaveText('✏️ 아이콘 (SVG)')
  expect(sent[0].kind).toBe('icon')
  await expect(page.getByTestId('tool-chip')).toBeVisible()                          // 이름표는 남음 — 이어 고치기도 아이콘으로
  await expect(page.getByTestId('svg-pick')).toHaveCount(2)
  await expect(page.getByRole('button', { name: '칠판에 붙이기' })).toHaveCount(0)   // 고르는 것이 곧 붙이기

  await page.getByTestId('svg-pick').first().click()
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(DESK.length)
  const its = (await liveDoc(page)).items
  expect(its.map(it => it.type)).toEqual(DESK.map(it => it.type))                    // 파일 놓기·데스크톱과 같은 도형
  expect(its[0].group_id).toBeTruthy(); expect(its.every(it => it.group_id === its[0].group_id)).toBe(true)   // 묶음 하나 — 선 하나만 고치려면 묶음 풀기
  await expect(page.getByTestId('svg-pick').first()).toHaveAttribute('data-picked', '1')

  await page.getByPlaceholder('무엇의 아이콘', { exact: false }).click()
  await page.keyboard.type('선을 더 굵게'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-kind')).toHaveCount(2)
  expect(sent[1].base_svg).toBe(ICON)                                                // 붙인(고른) 아이콘을 실어 보냄
  expect(sent[1].kind).toBe('icon')
  expect(sent[1].messages.at(-1)).toEqual({ role: 'user', content: '선을 더 굵게' })
  expect(sent[1].context).toBeUndefined()                                            // 방금 붙인 도형은 다음 질문에 안 실음

  const from = await page.getByTestId('svg-pick').nth(1).boundingBox(), to = await toPage(page, 200, 400)
  await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2); await page.mouse.down()
  await page.mouse.move(from.x + from.width / 2 - 20, from.y + from.height / 2, { steps: 3 })
  await page.mouse.move(to.x, to.y, { steps: 8 }); await page.mouse.up()
  await expect.poll(async () => (await liveDoc(page)).items.length).toBeGreaterThan(DESK.length)
  const added = (await liveDoc(page)).items.slice(DESK.length)
  const xs = added.flatMap(it => (it.line ? [it.line[0], it.line[2]] : it.rect ? [it.rect[0], it.rect[0] + it.rect[2]] : it.pts ? it.pts.map(p => p[0]) : it.elements ? it.elements.map(e => e.at(-2)) : []).map(x => x + it.pos[0]))
  expect(Math.abs((Math.min(...xs) + Math.max(...xs)) / 2 - 200)).toBeLessThan(30)  // 놓은 자리 가운데

  await page.getByTestId('tool-chip').click()                                        // ✕ = 다시 앱이 고름
  await expect(page.getByTestId('tool-chip')).toHaveCount(0)
  await page.getByPlaceholder('물어보세요', { exact: false }).click()
  await page.keyboard.type('고마워'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-kind')).toHaveCount(3)
  expect(sent[2].kind).toBeUndefined()
})
