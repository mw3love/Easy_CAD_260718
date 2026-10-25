// 흐름 30 — 그래프 = 표 + 모양(§8 항목66 1단계, 2026-10-25): 표 고르기 → 속성 카드 「모양」 세로 막대 → 그래프(흰 카드·막대 넷) →
// 원은 까닭과 함께 막힘 → 두 번 누르면 표로 펼쳐 칸 고치기 → 바깥 누르면 다시 그래프(막대 높이가 고친 숫자로) → 가로 막대·꺾은선 → 새로고침해도 그대로 → 표로 돌아가면 원래 크기.
// 계산은 web/test/chart.test.mjs, 데스크톱은 tests/test_part72.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, waitSaved, toPage } from './helpers.js'

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

// 대화창 표 답 → 바로 그래프로(§8 항목66 1단계 이어서, 2026-10-25): 숫자 표 밑 「그래프로」 단추 = 되는 모양만(시간 흐름 = 꺾은선이 맨 앞, 원은 없음) →
// 누르면 칠판 표 + 모양(출처 번호는 칸에서 빼고 밑에 회색 출처 글, 한 묶음) → 두 번 눌러 표로 → 바깥 = 다시 그래프 → 끌면 놓은 자리에 하나 더. 글만 있는 표엔 단추 없음
const ANSWER = { model: 'fake-model', elapsed: 1.1, kind: 'search',
  content: '연도별 매출이에요.\n\n| 연도 | 매출(억) |\n|---|---|\n| 2023 | 120 [1] |\n| 2024 | 150 [1] |\n| 2025 | **185** [2] |\n\n| 이름 | 설명 |\n|---|---|\n| 가 | 좋음 |',
  sources: [{ n: 1, url: 'https://news.kbs.co.kr/a', title: '연간 실적', date: '' }, { n: 2, url: 'https://www.edaily.co.kr/b', title: '2025 결산', date: '' }] }

test('대화창 표 답 → 그래프로 붙이기 → 두 번 눌러 표로 → 다시 그래프 → 끌어 하나 더', async ({ page }) => {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => r.fulfill({ json: ANSWER }))
  await openBoard(page, boardName('chartans'), { chat: true }); await setCam(page)
  await page.getByPlaceholder('물어보세요', { exact: false }).click()
  await page.keyboard.type('연도별 매출 표로'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-table')).toHaveCount(2)
  const bar = page.getByTestId('answer-chart')
  await expect(bar).toHaveCount(1)                                                   // 글만 있는 표엔 없음
  const kinds = await bar.locator('[data-chart-kind]').evaluateAll(bs => bs.map(b => b.dataset.chartKind))
  expect(kinds).toEqual(['line', 'col', 'row'])                                      // 시간 흐름 = 꺾은선 먼저, 원은 몫이 아니라 없음
  await bar.screenshot({ path: 'test-results/chart-answer-bar.png' })

  await bar.locator('[data-chart-kind="line"]').click()
  let d = await liveDoc(page)
  const t = d.items.find(it => it.type === 'table'), note = d.items.find(it => it.type === 'text')
  expect(t.chart).toBe('line')
  expect(t.cells).toEqual([['연도', '매출(억)'], ['2023', '120'], ['2024', '150'], ['2025', '185']])   // 출처 번호·굵게는 칸에서 뺌
  expect(t.rect.slice(2)).toEqual([360, 240])
  expect(note.text).toBe('[1] 연간 실적 · news.kbs.co.kr\n[2] 2025 결산 · edaily.co.kr')
  expect(note.group_id).toBe(t.group_id); expect(t.group_id).toBeTruthy()
  await expect(page.getByTestId('sel-chip')).toHaveCount(0)                          // 붙인 것은 다음 질문에 안 실림
  await expect(page.locator('[data-chart="line"] circle')).toHaveCount(3)
  await clickScene(page, t.pos[0] + 600, t.pos[1] + 120); await shot(page, 'answer-line')

  const mid = async () => { const b = await page.locator('[data-chart="line"]').boundingBox(); return [b.x + b.width / 2, b.y + b.height / 2] }
  await page.mouse.dblclick(...await mid())
  await expect(page.locator('[data-chart]')).toHaveCount(0)                          // 표로 펼침
  await page.keyboard.press('Escape')
  await clickScene(page, t.pos[0] + 600, t.pos[1] + 120)
  await expect(page.locator('[data-chart="line"]')).toHaveCount(1)                   // 바깥 = 다시 그래프

  const src = await bar.locator('[data-chart-kind="col"]').boundingBox(), drop = await toPage(page, t.pos[0] + 120, t.pos[1] + 400)
  await page.mouse.move(src.x + src.width / 2, src.y + src.height / 2); await page.mouse.down()
  await page.mouse.move(drop.x, drop.y, { steps: 12 }); await page.mouse.up()
  await expect(page.locator('[data-chart="col"]')).toHaveCount(1)
  d = await liveDoc(page)
  const c2 = d.items.find(it => it.type === 'table' && it.chart === 'col')
  expect(c2.pos[1]).toBeGreaterThan(t.pos[1] + 240)                                  // 놓은 자리(첫 그래프 밑)
  expect(d.items.filter(it => it.type === 'table')).toHaveLength(2)
})
