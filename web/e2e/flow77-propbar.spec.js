// 흐름 77 — 속성 막대(2026-11-14 화면 틀 B1 4단계, 시안 6라운드 Q1): 우상 속성 카드 대신 고른 물건 위 한 줄 막대.
// 속성 하나 = 단추 하나(지금 값이 단추에), 누르면 그 단추 밑에 펼침. ⋯ = 우클릭 메뉴 + 맨 위 「속성 자세히…」(옛 카드).
// SHOTS=폴더 를 주면 막대 사진을 그 폴더에 남김(화면 자체 확인용).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, clickScene, toPage, dragScene } from './helpers.js'

const B = { scale: 1, rotation: 0, z: 1, origin: [0, 0], locked: false, group_id: null, layer_id: null }
const DOC = { format: 'easycad-doc', version: 1, items: [
  { ...B, type: 'rect', uid: 'r1', pos: [0, 0], rect: [0, 0, 160, 80], pen: '#ff1e2b45', width: 2, fill: null, style: 1, label: { text: '원인 확인', color: '#ff1e2b45', font: 16, bg: null } },
  { ...B, type: 'sarrow', uid: 'a1', pos: [0, 0], pts: [[300, 40], [420, 40], [420, 140], [560, 140]], color: '#ff1e2b45', width: 2, head: true, head_start: false, head_scale: 1, style: 1, auto_route: false, routing: 'ortho', curve_r: 10, route_hints: [], labels: [] },
  { ...B, type: 'memo', uid: 'm1', pos: [0, 260], rect: [0, 0, 340, 120], lines: [{ k: 'p', t: '첫째 줄' }, { k: 'p', t: '둘째 줄' }] },
] }
const shot = async (page, name) => { if (process.env.SHOTS) await page.screenshot({ path: `${process.env.SHOTS}/${name}.png` }) }
const item = async (page, type) => (await liveDoc(page)).items.find(it => it.type === type)
const labels = bar => bar.locator('button').evaluateAll(bs => bs.map(b => b.getAttribute('aria-label')))

async function open(page, tag) {
  await page.route('**/propbar.ecad', r => r.fulfill({ json: DOC }))
  await openBoard(page, boardName(tag))
  await page.evaluate(() => window.__mb.open('/propbar.ecad'))
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(3)
  await setCam(page)
}

test('도형을 고르면 물건 위 12px에 한 줄 막대 — 단추 차례 = 시안 Q1, 옛 카드는 안 뜸', async ({ page }) => {
  await open(page, 'pbshape')
  await clickScene(page, 20, 20)
  const bar = page.getByTestId('prop-bar')
  await expect(bar).toBeVisible()
  await expect(page.getByTestId('props-card')).toHaveCount(0)
  expect(await labels(bar)).toEqual(['다른 도형으로 바꾸기(크기·연결 유지)', '선 색', '채움', '선 굵기', '선 모양', '글자 크기', '굵게', '글 정렬', '글자 색', '잠그기', '더 보기'])
  const b = await bar.boundingBox(), top = (await toPage(page, 0, 0)).y
  expect(b.height).toBe(40)
  expect(Math.round(top - (b.y + b.height))).toBe(12)                                  // 물건 위 12
  const r = await toPage(page, 80, 0); expect(Math.abs(b.x + b.width / 2 - r.x)).toBeLessThan(1.5)   // 가운데 맞춤
  await expect(page.getByTestId('bar-width')).toContainText('2px')                     // 지금 값이 단추에
  await expect(page.getByTestId('bar-font')).toContainText('16')
  await shot(page, 'shape')

  await page.getByTestId('bar-width').click()                                          // 굵기 = 단추 밑 펼침 속 −/+
  await page.getByTestId('pop-width').locator('[aria-label="선 굵기 늘리기"]').click()
  expect((await item(page, 'rect')).width).toBe(3)
  await page.getByTestId('chip-line').click()                                          // 선 색 = 색 창(속성 카드와 같은 창)
  await expect(page.getByTestId('pop-width')).toHaveCount(0)                           // 펼침은 한 번에 하나
  await page.getByTestId('pop-line').locator('button[title="#007AFF"]').click()
  expect((await item(page, 'rect')).pen).toBe('#007aff')
  await shot(page, 'shape-color')
  await page.keyboard.press('Escape'); await expect(page.getByTestId('pop-line')).toHaveCount(0)
  await page.getByTestId('bar-bold').click()
  expect((await item(page, 'rect')).label.runs).toEqual([[0, 5, null, true]])
  await page.getByTestId('bar-talign').click(); await page.getByRole('button', { name: '왼쪽 맞춤' }).click()
  expect((await item(page, 'rect')).label.ha).toBe('left')
  await page.getByTestId('bar-swap').click(); await page.getByTestId('pop-swap').getByRole('button', { name: '판단' }).click()
  expect((await item(page, 'symbol')).kind).toBe('decision')                           // 모양 바꾸기 — 같은 물건(_id)
})

test('⋯ = 우클릭 메뉴 + 맨 위 「속성 자세히…」(옛 카드, ✕로 닫음) · 잠금 단추', async ({ page }) => {
  await open(page, 'pbmore')
  await clickScene(page, 20, 20)
  await page.getByTestId('bar-more').click()
  const first = page.getByRole('menuitem').first()
  await expect(first).toHaveText(/속성 자세히/)
  await expect(page.getByRole('menuitem', { name: /맨 앞으로/ })).toBeVisible()     // 순서·복제·지우기 = 우클릭과 같은 메뉴
  await shot(page, 'more')
  await first.click()
  await expect(page.getByTestId('props-card')).toBeVisible()
  await expect(page.getByTestId('rot-step')).toBeVisible()                             // 회전 숫자처럼 막대에 없는 것
  await page.getByTestId('props-close').click()
  await expect(page.getByTestId('props-card')).toHaveCount(0)
  await page.getByTestId('bar-lock').click()
  expect((await item(page, 'rect')).locked).toBe(true)
  await expect(page.getByTestId('bar-lock')).toHaveAttribute('aria-pressed', 'true')
  await page.getByTestId('bar-lock').click()
  expect((await item(page, 'rect')).locked).toBe(false)
})

test('화살표 막대 = 종류·촉 | 선 색·굵기·선 모양 | ⋯ — 종류·촉은 펼침에서', async ({ page }) => {
  await open(page, 'pbarrow')
  await clickScene(page, 360, 40)
  const bar = page.getByTestId('prop-bar')
  expect(await labels(bar)).toEqual(['화살표 종류', '화살촉', '선 색', '선 굵기', '선 모양', '더 보기'])
  await shot(page, 'arrow')
  await page.getByTestId('bar-head').click(); await page.getByTestId('pop-head').getByRole('button', { name: '양쪽' }).click()
  const a = await item(page, 'sarrow'); expect([a.head, a.head_start]).toEqual([true, true])
  await page.getByTestId('bar-akind').click(); await page.getByTestId('pop-akind').getByRole('button', { name: '직선' }).click()
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.uid === 'a1' || it.type === 'sarrow' || it.type === 'arrow')?.routing ?? 'straight').not.toBe('ortho')
})

test('메모 막대 = 바탕 | 글 크기·굵게·기울임·목록 | 잠금·⋯ — 메모 글 전체에', async ({ page }) => {
  await open(page, 'pbmemo')
  await clickScene(page, 300, 300)
  const bar = page.getByTestId('prop-bar')
  expect(await labels(bar)).toEqual(['메모 바탕', '메모 글 크기(메모 통째 배율)', '굵게', '기울임', '목록 — 메모의 글 줄 전부(제목·코드·표는 그대로)', '잠그기', '더 보기'])
  await shot(page, 'memo')
  await page.getByTestId('memo-bold').click()
  expect((await item(page, 'memo')).lines.map(l => l.runs)).toEqual([[[0, 4, null, true]], [[0, 4, null, true]]])
  await expect(page.getByTestId('memo-bold')).toHaveAttribute('aria-pressed', 'true')
  await page.getByTestId('memo-italic').click()
  expect((await item(page, 'memo')).lines[0].runs).toEqual([[0, 4, null, true, null, false, 'i']])
  await page.getByTestId('bar-mlist').click(); await page.getByRole('button', { name: '할 일' }).click()
  expect((await item(page, 'memo')).lines.map(l => l.k)).toEqual(['todo', 'todo'])
  await page.keyboard.press('Escape')
  await page.getByTestId('bar-mscale').click(); await page.getByTestId('pop-mscale').locator('[aria-label="메모 글 크기 늘리기"]').click()
  expect((await item(page, 'memo')).scale).toBeCloseTo(1.1, 5)
})

test('위에 자리가 없으면 물건 아래 · 글을 드래그해 고르면 막대는 비키고 꾸미기 막대', async ({ page }) => {
  await open(page, 'pbplace')
  await setCam(page, { x: 400, y: 70, z: 1 })                                           // 도형 위 끝이 섬 바로 밑
  await clickScene(page, 20, 20)
  const b = await page.getByTestId('prop-bar').boundingBox(), bottom = (await toPage(page, 0, 80)).y
  expect(Math.round(b.y - bottom)).toBe(12)                                             // 아래 12
  await shot(page, 'below')
  await page.keyboard.press('Enter')                                                    // 글 고치기
  await expect(page.locator('[data-testid="text-editor"]:not([data-armed])')).toHaveCount(1)
  await expect(page.getByTestId('prop-bar')).toBeVisible()                              // 고치는 중(아무것도 안 고름) = 막대 그대로(글 전체에)
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))))   // 편집기가 자리 잡은 뒤 고르기(flow26 `editing`과 같은 까닭)
  await page.keyboard.press('Shift+ArrowLeft'); await page.keyboard.press('Shift+ArrowLeft')
  await expect(page.getByTestId('format-bar')).toBeVisible()
  await expect(page.getByTestId('prop-bar')).toHaveCount(0)
})

test('여러 개 고르면 맨 앞에 「맞춤 · 분배」 — 펼치면 정렬 여섯·분배 둘', async ({ page }) => {
  await open(page, 'pbmulti')
  await dragScene(page, { x: -30, y: -30 }, { x: 380, y: 420 })
  await page.getByTestId('bar-arrange').click()
  await expect(page.getByTestId('align-row')).toBeVisible()
  await shot(page, 'multi')
})

test('좁은 창(480)에서도 막대는 화면 안(넘치면 막대 안에서 가로로 굴림) · 어두운 화면', async ({ page }) => {
  await page.setViewportSize({ width: 480, height: 800 })
  await page.emulateMedia({ colorScheme: 'dark' })
  await open(page, 'pbnarrow')
  await setCam(page, { x: 120, y: 200, z: 1 })
  await clickScene(page, 20, 20)
  const b = await page.getByTestId('prop-bar').boundingBox()
  expect(b.x).toBeGreaterThanOrEqual(0); expect(b.x + b.width).toBeLessThanOrEqual(480)
  await shot(page, 'narrow-dark')
})

test('글쇠로 — Tab으로 막대 단추에 닿고, Enter = 펼침(초점이 펼침 안으로), Esc = 연 단추로 돌아옴', async ({ page }) => {
  await open(page, 'pbkeys')
  await clickScene(page, 20, 20)
  await expect(page.locator('[data-testid="text-editor"][data-armed]')).toHaveCount(1)   // 고르면 뜨는 글 대기 칸이 초점을 먼저 가져간 뒤(한 박자 늦게 떠 Tab 사이에 초점을 가로챘음)
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))))
  let n = 0
  while (n++ < 60 && !(await page.evaluate(() => !!document.activeElement?.closest('[data-testid="prop-bar"]')))) await page.keyboard.press('Tab')
  expect(n).toBeLessThan(60)                                                            // 막대에 닿음
  while (n++ < 80 && (await page.evaluate(() => document.activeElement?.dataset.testid)) !== 'bar-width') await page.keyboard.press('Tab')
  await page.keyboard.press('Enter')
  await expect(page.getByTestId('pop-width')).toBeVisible()
  await expect.poll(() => page.evaluate(() => !!document.activeElement?.closest('[data-testid="pop-width"]'))).toBe(true)
  await page.keyboard.press('Enter')                                                     // 첫 칸(−)… 굵기 줄이기
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('pop-width')).toHaveCount(0)
  expect(await page.evaluate(() => document.activeElement?.dataset.testid)).toBe('bar-width')
  expect((await liveDoc(page)).items.find(it => it.type === 'rect')).toBeTruthy()       // Esc가 고른 것을 풀지 않음(펼침만 닫힘)
  await expect(page.getByTestId('prop-bar')).toBeVisible()
})

// 2026-11-14 다듬기 — 표 하나 = 「그래프 모양」 · 프레임 하나 = 이름·비율 · 끄는 동안 막대 숨김 · 심볼 이름
const DOC2 = { format: 'easycad-doc', version: 1, items: [
  { ...B, type: 'table', uid: 't1', pos: [0, 0], rect: [0, 0, 240, 150], rows: 4, cols: 2, header: true, col_widths: [0.5, 0.5], cells: [['팀', '점수'], ['가', '10'], ['나', '20'], ['다', '15']] },
  { ...B, type: 'frame', uid: 'f1', pos: [400, 0], rect: [0, 0, 320, 180], name: '표지', no: 1 },
  { ...B, type: 'polygon', uid: 'p1', pos: [0, 300], rect: [0, 0, 80, 60], pts: [[0, 0], [80, 0], [40, 60]], closed: true, pen: '#ff1e2b45', width: 2, fill: null, style: 1, sym_name: '안테나' },
] }
test('표 = 「그래프 모양」 · 프레임 = 이름·비율 · 심볼 이름 · 끄는 동안 막대 숨김', async ({ page }) => {
  await page.route('**/propbar2.ecad', r => r.fulfill({ json: DOC2 }))
  await openBoard(page, boardName('pbpolish'))
  await page.evaluate(() => window.__mb.open('/propbar2.ecad'))
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(3)
  await setCam(page)
  await clickScene(page, 120, 75)                                                        // 표
  await page.getByTestId('bar-chart').click()
  await page.getByTestId('bar-chart-kinds').locator('[data-chart-kind="col"]').click()
  expect((await item(page, 'table')).chart).toBe('col')
  await shot(page, 'chart')
  await page.keyboard.press('Escape')
  await clickScene(page, 400, 90)                                                        // 프레임 테두리
  await expect(page.getByTestId('bar-frame')).toContainText('표지 · 자유')
  await page.getByTestId('bar-frame').click()
  await page.getByTestId('pop-frame').getByRole('button', { name: '16:9' }).click()
  expect((await item(page, 'frame')).ratio).toBe('16:9')
  await page.getByTestId('bar-frame-name').fill('첫 장'); await page.keyboard.press('Enter')
  expect((await item(page, 'frame')).name).toBe('첫 장')
  await page.keyboard.press('Escape')
  await clickScene(page, 40, 300)                                                        // 심볼(이름 있는 다각형) — 윗변
  await expect(page.getByTestId('bar-name')).toHaveText('안테나')
  const p = await toPage(page, 40, 300)                                                  // 끄는 동안 = 막대 없음, 놓으면 다시
  await page.mouse.move(p.x, p.y); await page.mouse.down(); await page.mouse.move(p.x + 40, p.y + 20, { steps: 4 })
  await expect(page.getByTestId('prop-bar')).toHaveCount(0)
  await page.mouse.up()
  await expect(page.getByTestId('prop-bar')).toBeVisible()
})
