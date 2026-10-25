// 흐름 30 — 그래프 = 표 + 모양(§8 항목66 1단계, 2026-10-25): 표 고르기 → 속성 카드 「모양」 세로 막대 → 그래프(흰 카드·막대 넷) →
// 원은 까닭과 함께 막힘 → 두 번 누르면 표로 펼쳐 칸 고치기 → 바깥 누르면 다시 그래프(막대 높이가 고친 숫자로) → 가로 막대·꺾은선 → 새로고침해도 그대로 → 표로 돌아가면 원래 크기.
// 계산은 web/test/chart.test.mjs, 데스크톱은 tests/test_part72.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, waitSaved } from './helpers.js'

const CELLS = [['번역기', 'BLEU'], ['ByteNet', '23.75'], ['GNMT + RL', '24.6'], ['ConvS2S', '25.16'], ['Transformer', '28.4']]
const DOC = { format: 'easycad-doc', version: 1, items: [{ type: 'table', uid: 't1', pos: [0, 0], scale: 1, rotation: 0, z: 1, origin: [0, 0], locked: false, group_id: null, layer_id: null,
  rect: [0, 0, 240, 150], rows: 5, cols: 2, header: true, cells: CELLS, col_widths: [0.5, 0.5] }] }
const table = async page => (await liveDoc(page)).items.find(it => it.type === 'table')
const shot = (page, name) => page.getByTestId('board').screenshot({ path: `test-results/chart-${name}.png` })
const barHeights = page => page.$$eval('[data-chart] path', ps => ps.map(p => p.getBBox().height))

test('표 → 세로 막대 → 원은 막힘 → 두 번 눌러 숫자 고치기 → 다시 그래프 → 새로고침 → 표로', async ({ page }) => {
  const name = boardName('chart')
  await page.route('**/chart-sample.ecad', r => r.fulfill({ json: DOC }))
  await openBoard(page, name)
  await page.evaluate(() => window.__mb.open('/chart-sample.ecad'))
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  await setCam(page, { x: 300, y: 150, z: 1.4 })

  await clickScene(page, 120, 75)                                                    // 표 고르기
  const kinds = page.getByTestId('chart-kinds')
  await expect(kinds).toBeVisible()
  await expect(kinds.locator('[data-chart-kind="pie"]')).toBeDisabled()              // 점수 비교 = 원 안 됨
  expect(await kinds.locator('[data-chart-kind="pie"]').getAttribute('title')).toMatch(/몫/)
  await kinds.locator('[data-chart-kind="col"]').click()
  await page.locator('[data-chart-kind="col"]').locator('xpath=ancestor::div[contains(@style,"width: 192")]').screenshot({ path: 'test-results/chart-props.png' })
  let t = await table(page)
  expect(t.chart).toBe('col')
  expect(t.rect.slice(2)).toEqual([360, 240])                                        // 작으면 그래프 크기로
  expect(t.table_wh).toEqual([240, 150])
  await expect(page.locator('[data-chart="col"] path')).toHaveCount(4)
  await clickScene(page, 420, 300); await shot(page, 'col')
  const before = await barHeights(page)

  await page.mouse.dblclick(...Object.values(await (async () => { const b = await page.locator('[data-chart="col"]').boundingBox(); return { x: b.x + b.width / 2, y: b.y + b.height / 2 } })()))
  await expect(page.locator('[data-chart]')).toHaveCount(0)                          // 표로 펼침
  await page.keyboard.press('Control+a'); await page.keyboard.type('12'); await page.keyboard.press('Enter')   // 첫 숫자 칸(ByteNet) 23.75 → 12
  await page.keyboard.press('Escape')
  await clickScene(page, 420, 300)                                                    // 바깥 = 다시 그래프
  await expect(page.locator('[data-chart="col"]')).toHaveCount(1)
  expect((await table(page)).cells[1][1]).toBe('12')
  const after = await barHeights(page)
  expect(after[0]).toBeLessThan(before[0] * 0.6)                                      // 23.75 → 12 = 막대가 반쯤

  await clickScene(page, 180, 120)
  await kinds.locator('[data-chart-kind="row"]').click(); await expect(page.locator('[data-chart="row"]')).toHaveCount(1)
  await clickScene(page, 420, 300); await shot(page, 'row')
  await clickScene(page, 180, 120)
  await kinds.locator('[data-chart-kind="line"]').click(); await expect(page.locator('[data-chart="line"] circle')).toHaveCount(4)
  await clickScene(page, 420, 300); await shot(page, 'line')

  await waitSaved(page)
  await page.reload()
  await expect(page.locator('[data-chart="line"]')).toHaveCount(1)                    // 새로고침해도 그대로

  await setCam(page, { x: 300, y: 150, z: 1.4 })
  await clickScene(page, 180, 120)
  await kinds.locator('[data-chart-kind="table"]').click()
  t = await table(page)
  expect(t.chart).toBeUndefined()
  expect(t.rect.slice(2)).toEqual([240, 150])                                         // 원래 표 크기
  await expect(page.locator('[data-chart]')).toHaveCount(0)
})

test('비중 열 하나 = 원 그래프 켜짐, 계열 둘 = 색 견본', async ({ page }) => {
  const doc = JSON.parse(JSON.stringify(DOC)), tb = doc.items[0]
  tb.cells = [['나라', '비중'], ['중국', '40%'], ['홍콩', '25%'], ['대만', '20%'], ['베트남', '15%']]
  doc.items.push({ ...tb, uid: 't2', pos: [500, 0], cols: 3, col_widths: [0.4, 0.3, 0.3], cells: [['달', '2025', '2026'], ['1월', '10', '12'], ['2월', '11', '15'], ['3월', '9', '16'], ['4월', '13', '18']], chart: 'col', rect: [0, 0, 360, 240] })
  tb.chart = 'pie'; tb.rect = [0, 0, 360, 240]
  await page.route('**/chart-sample2.ecad', r => r.fulfill({ json: doc }))
  await openBoard(page, boardName('chart2'))
  await page.evaluate(() => window.__mb.open('/chart-sample2.ecad'))
  await setCam(page, { x: 200, y: 200, z: 1.2 })
  await expect(page.locator('[data-chart="pie"] path')).toHaveCount(4)
  await expect(page.locator('[data-chart="pie"] text', { hasText: '40%' })).toHaveCount(1)
  await expect(page.locator('[data-chart="col"] path')).toHaveCount(8)
  await shot(page, 'pie-multi')
})
