// 흐름 49 — 💬 AI 말풍선(2026-10-28 사용자: 큰 대화창에 여러 물건 작업이 섞임 → 물건마다 작은 대화창).
// 우클릭 「AI 말풍선 (KAIROS)」 → 그 물건만 보고 답 · 메모를 고쳐 달라면 그 자리에서 고침(원래대로 ↔ 바꾼 것 · Ctrl+Z) · 닫으면 💬 표시 · 새로고침해도 대화 남음 · 여럿 같이. 진짜 KAIROS는 안 부름.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, waitSaved, toPage } from './helpers.js'

const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII='
const FIXED = '# 점검\n- 안테나 정상\n- 송신기 교체\n\n## 할 일\n- [ ] 송신기 교체'

async function fake(page, seen) {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return r.fulfill({ json: b.kind === 'bubble'
      ? { kind: 'bubble', content: b.item.type === 'memo' ? '할 일만 뽑아 아래에 붙였어요.' : '작은 그림이에요.', edit: FIXED, model: 'fake-model', elapsed: 0.1, credits: 1.2 }
      : { content: '큰 대화 답', model: 'fake-model', elapsed: 0.1 } }) })
}
const pasteText = (page, t) => page.evaluate(t => { const dt = new DataTransfer(); dt.setData('text/plain', t); window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })) }, t)
const memoOf = async page => (await liveDoc(page)).items.find(it => it.type === 'memo')
const hasTodo = m => m.lines.some(l => l.k === 'todo' && l.t === '송신기 교체')
async function openOn(page, text) {
  const b = await page.locator('svg text', { hasText: text }).first().boundingBox()
  await page.mouse.click(b.x + 4, b.y + b.height / 2, { button: 'right' })
  await page.getByText('댓글…', { exact: true }).click()
}

test('메모 말풍선 — 고쳐 달라면 그 자리에서 고침 · 원래대로 ↔ 바꾼 것 · Ctrl+Z · 닫으면 💬 · 새로고침해도 대화 남음', async ({ page }) => {
  const name = boardName('bubble'), seen = []
  await fake(page, seen)
  await openBoard(page, name, { chat: true }); await setCam(page)
  await pasteText(page, '# 점검\n- 안테나 정상\n- 송신기 교체')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  await openOn(page, '안테나 정상')
  const bub = page.getByTestId('bubble'); await expect(bub).toBeVisible()
  await bub.getByTestId('bubble-input').fill('@KAIROS 할 일만 뽑아 아래에 붙여 줘'); await bub.getByTestId('bubble-input').press('Enter')
  await expect(bub.getByTestId('bubble-a')).toContainText('할 일만 뽑아 아래에 붙였어요.')
  expect(seen).toHaveLength(1)
  expect(seen[0]).toMatchObject({ kind: 'bubble', item: { type: 'memo' }, messages: [{ role: 'user', content: '시험: @KAIROS 할 일만 뽑아 아래에 붙여 줘' }] })   // 댓글 = 「이름: 글」(2026-11-14)
  expect(seen[0].item.text).toContain('안테나 정상')                                        // 이 물건의 글만
  expect(hasTodo(await memoOf(page))).toBe(true)                                           // 그 자리에서 고침
  await expect(page.getByRole('complementary', { name: 'KAIROS 대화' }).getByText('할 일만 뽑아')).toHaveCount(0)   // 큰 대화창엔 안 섞임

  await bub.getByTestId('bubble-flip').click(); expect(hasTodo(await memoOf(page))).toBe(false)   // 원래대로
  await bub.getByTestId('bubble-flip').click(); expect(hasTodo(await memoOf(page))).toBe(true)    // 바꾼 것으로
  await page.mouse.click(1000, 700); await page.keyboard.press('Control+z')
  expect(hasTodo(await memoOf(page))).toBe(false)                                          // 칠판 Ctrl+Z 한 번 = 바로 앞

  await bub.getByTestId('bubble-close').click()
  await expect(page.getByTestId('bubble')).toHaveCount(0)
  await expect(page.getByTestId('bubble-badge')).toHaveText('💬 2')   // 댓글 수 = 사람 + KAIROS(2026-11-14 — 옛 말풍선은 질문 수)
  await waitSaved(page); await page.reload()
  await expect(page.getByTestId('bubble-badge')).toHaveText('💬 2')                         // 대화는 서버에(`.threads.json`)
  await page.getByTestId('bubble-badge').click()
  await expect(page.getByTestId('bubble').getByTestId('bubble-q')).toContainText('할 일만 뽑아 아래에 붙여 줘')
})

test('말풍선 여럿을 같이 — 그림 말풍선은 그 그림을 보내고 메모를 고치지 않음 · 서로 대화가 안 섞임', async ({ page }) => {
  const name = boardName('bubble2'), seen = []
  await fake(page, seen)
  await openBoard(page, name); await setCam(page)
  await pasteText(page, '# 회의\n- 결정 A')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  await page.evaluate(async b64 => { const f = new File([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], 'a.png', { type: 'image/png' }); await window.__mb.ed.attachFiles([f]) }, PNG)
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(2)
  const img = (await liveDoc(page)).items.find(it => it.type === 'image')
  await openOn(page, '결정 A')
  const memoBub = page.getByTestId('bubble').first()
  await memoBub.getByTestId('bubble-input').fill('@KAIROS 요약해 줘'); await memoBub.getByTestId('bubble-input').press('Enter')
  await expect(memoBub.getByTestId('bubble-a')).toHaveCount(1)
  const lines = (await memoOf(page)).lines
  const c = await page.evaluate(id => { const b = window.__mb.ed.bubbleInfo(id).box; return { x: b.x + b.w / 2, y: b.y + b.h / 2 } }, img.uid)
  const p = await toPage(page, c.x, c.y)
  await page.evaluate(() => window.__mb.ed.setSel([]))                                    // 고른 메모 풀기 — 그 위 속성 막대가 그림을 덮지 않게(2026-11-14)
  await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.getByText('댓글…', { exact: true }).click()
  await expect(page.getByTestId('bubble')).toHaveCount(2)                                  // 둘이 같이 열림
  const imgBub = page.locator('[data-testid="bubble"][aria-label="댓글 — 그림"]')
  await imgBub.getByTestId('bubble-input').fill('@KAIROS 이 그림 뭐야?'); await imgBub.getByTestId('bubble-input').press('Enter')
  await expect(imgBub.getByTestId('bubble-a')).toContainText('작은 그림이에요.')
  const last = seen.at(-1)
  expect(last.item.type).toBe('image'); expect(last.item.image).toMatch(/^data:image\/jpeg;base64,/)
  expect(last.messages).toEqual([{ role: 'user', content: '시험: @KAIROS 이 그림 뭐야?' }])   // 메모 댓글은 안 실림
  await expect(imgBub.getByTestId('bubble-flip')).toHaveCount(0)                           // 그림 = 메모를 안 고침
  expect((await memoOf(page)).lines).toEqual(lines)
})

test('그림 말풍선 2단계 — 「배경 밝게」 = 그 자리 그림을 바꿈(폭 그대로·새 비율) · 원래대로 ↔ 바꾼 것 · 묻는 말은 답만', async ({ page }) => {
  const name = boardName('bubble3'), seen = []
  const RED = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=='   // 1×1(원본 4×3과 비율이 다름)
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b); const fix = /밝게/.test(b.messages.at(-1).content)
    return r.fulfill({ json: fix ? { kind: 'bubble', content: '말한 점만 고쳐서 이 그림을 바꿨어요.', image_url: `/api/img/${name}/9_abcdef.png`, model: 'img-m', elapsed: 1 } : { kind: 'bubble', content: '빨간 점이에요.', model: 'fake-model', elapsed: 0.1 } }) })
  await page.route('**/api/img/**', r => r.fulfill({ body: Buffer.from(RED, 'base64'), contentType: 'image/png' }))
  await openBoard(page, name); await setCam(page)
  await page.evaluate(async b64 => { const f = new File([Uint8Array.from(atob(b64), c => c.charCodeAt(0))], 'a.png', { type: 'image/png' }); await window.__mb.ed.attachFiles([f]) }, PNG)
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  const img0 = (await liveDoc(page)).items[0]
  const c = await page.evaluate(id => { const b = window.__mb.ed.bubbleInfo(id).box; return { x: b.x + b.w / 2, y: b.y + b.h / 2 } }, img0.uid)
  const p = await toPage(page, c.x, c.y)
  await page.mouse.click(p.x, p.y, { button: 'right' }); await page.getByText('댓글…', { exact: true }).click()
  const bub = page.getByTestId('bubble'), input = bub.getByTestId('bubble-input')
  await input.fill('@KAIROS 배경을 밝게 해 줘'); await input.press('Enter')
  await expect(bub.getByTestId('bubble-flip')).toHaveText('원래대로')
  let now = (await liveDoc(page)).items[0]
  expect(now.data).not.toBe(img0.data); expect(now.rect[2]).toBeCloseTo(img0.rect[2]); expect(now.rect[3]).toBeCloseTo(img0.rect[2])   // 폭 그대로, 높이 = 1:1
  await bub.getByTestId('bubble-flip').click()
  now = (await liveDoc(page)).items[0]; expect(now.data).toBe(img0.data); expect(now.rect[3]).toBeCloseTo(img0.rect[3])
  await bub.getByTestId('bubble-flip').click(); expect((await liveDoc(page)).items[0].rect[3]).toBeCloseTo(img0.rect[2])
  await input.fill('@KAIROS 이거 뭐야?'); await input.press('Enter')
  await expect(bub.getByTestId('bubble-a')).toHaveCount(2); await expect(bub.getByTestId('bubble-a').last()).toHaveText(/빨간 점이에요/)
  expect(seen[0].item.image).toMatch(/^data:image\/jpeg;base64,/)
})

test('말풍선 3단계 — 표는 그 자리에서 칸이 바뀌고(줄 더하면 높이도) · 글 상자는 글이 바뀜 · 원래대로', async ({ page }) => {
  const name = boardName('bubble4'), seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return r.fulfill({ json: b.item.edit === 'table' ? { kind: 'bubble', content: '합계 줄을 더했어요.', edit: '| 항목 | 수량 |\n|---|---|\n| 안테나 | 2 |\n| 송신기 | 1 |\n| 합계 | 3 |', model: 'm', elapsed: 0.1 }
      : { kind: 'bubble', content: '짧게 줄였어요.', edit: '점검 끝', model: 'm', elapsed: 0.1 } }) })
  await openBoard(page, name); await setCam(page)
  await pasteText(page, '| 항목 | 수량 |\n|---|---|\n| 안테나 | 2 |\n| 송신기 | 1 |')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  const t0 = (await liveDoc(page)).items[0]; expect(t0.type).toBe('table')
  await openOn(page, '안테나')
  const bub = page.getByTestId('bubble'), input = bub.getByTestId('bubble-input')
  await input.fill('@KAIROS 합계 줄 더해 줘'); await input.press('Enter')
  await expect(bub.getByTestId('bubble-flip')).toHaveText('원래대로')
  expect(seen[0].item).toMatchObject({ type: 'table', edit: 'table' }); expect(seen[0].item.text).toContain('| 안테나 | 2 |')
  let t = (await liveDoc(page)).items[0]
  expect(t.cells.at(-1)).toEqual(['합계', '3']); expect(t.rows).toBe(4); expect(t.rect[3]).toBeGreaterThan(t0.rect[3])
  await bub.getByTestId('bubble-flip').click()
  t = (await liveDoc(page)).items[0]; expect(t.rows).toBe(3); expect(t.cells).toEqual(t0.cells)
  await bub.getByTestId('bubble-close').click()

  await page.mouse.click(800, 760)
  await pasteText(page, '송신소 점검 결과를 정리했습니다')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(2)
  await openOn(page, '점검 결과를')
  const tb = page.getByTestId('bubble')
  await tb.getByTestId('bubble-input').fill('@KAIROS 더 짧게'); await tb.getByTestId('bubble-input').press('Enter')
  await expect(tb.getByTestId('bubble-flip')).toHaveText('원래대로')
  expect(seen.at(-1).item).toMatchObject({ type: 'text', edit: 'text' })
  expect((await liveDoc(page)).items.find(it => it.type === 'text').text).toBe('점검 끝')
})

test('말풍선 두 창 — 다른 메모에 쓴 대화가 서로 안 지워짐 · 말풍선을 열면 다른 창이 쓴 대화도 보임(2026-11-02)', async ({ browser }) => {
  const name = boardName('bubble2'), ca = await browser.newContext(), cb = await browser.newContext(), a = await ca.newPage(), b = await cb.newPage(), seen = []
  await fake(a, seen); await fake(b, seen)
  await openBoard(a, name); await setCam(a)
  await pasteText(a, '# 첫 메모\n- 안테나 정상'); await expect.poll(async () => (await liveDoc(a)).items.length).toBe(1)
  await a.mouse.click(1200, 700); await pasteText(a, '# 둘째 메모\n- 송신기 점검'); await expect.poll(async () => (await liveDoc(a)).items.length).toBe(2)
  await waitSaved(a)
  await openBoard(b, name); await expect.poll(async () => (await liveDoc(b)).items.length).toBe(2)
  await openOn(a, '안테나 정상'); await openOn(b, '송신기 점검')                       // 두 창이 먼저 열어 둠(각자 빈 대화를 들고 있음)
  const ba = a.getByTestId('bubble'), bb = b.getByTestId('bubble')
  await ba.getByTestId('bubble-input').fill('@KAIROS A 창 질문'); await ba.getByTestId('bubble-input').press('Enter')
  await expect(ba.getByTestId('bubble-a')).toHaveCount(1)
  await bb.getByTestId('bubble-input').fill('@KAIROS B 창 질문'); await bb.getByTestId('bubble-input').press('Enter')
  await expect(bb.getByTestId('bubble-a')).toHaveCount(1)
  const file = async () => (await (await a.request.get(`/api/threads/${encodeURIComponent(name)}`)).json())
  await expect.poll(async () => Object.values(await file()).map(t => t.length).sort()).toEqual([2, 2])   // 전엔 B 저장이 A 대화를 지웠음
  await bb.getByTestId('bubble-close').click(); await openOn(b, '안테나 정상')          // B가 A의 메모 말풍선을 열면 A 대화가 보임
  await expect(b.getByTestId('bubble').getByTestId('bubble-q')).toContainText('A 창 질문')
  await ca.close(); await cb.close()
})

// 2026-11-14 화면 틀 B1 5단계 — 말풍선 = 댓글(사용자 「댓글 + @KAIROS」, Figma·Miro 댓글처럼): 사람끼리 = AI 안 부름, 이름·시각 · @KAIROS 단추 = 붙임 → AI 답
// · 「✓ 해결」 = 칠판 💬 표시 숨김(댓글은 남음) · 다시 열기 · 해결된 댓글에 새로 쓰면 다시 열림
test('댓글 — 사람 댓글은 AI 안 부름 · 이름 보임 · @KAIROS면 AI 답 · ✓ 해결 = 💬 숨김 · 다시 열기', async ({ page }) => {
  const seen = []
  await fake(page, seen)
  await openBoard(page, boardName('comment'), { who: '민우' }); await setCam(page)
  await pasteText(page, '# 회의\n- 결정 A')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  await openOn(page, '결정 A')
  const bub = page.getByTestId('bubble'), input = bub.getByTestId('bubble-input')
  await input.fill('이거 내일까지 확인 부탁해요'); await input.press('Enter')
  await expect(bub.getByTestId('bubble-q')).toContainText('민우')                       // 쓴 사람 이름
  await expect(bub.getByTestId('bubble-q')).toContainText('내일까지 확인')
  await page.waitForTimeout(300); expect(seen.filter(b => b.kind === 'bubble')).toHaveLength(0)   // AI 안 부름(크레딧 0)
  await bub.getByTestId('bubble-at').click(); await expect(input).toHaveValue('@KAIROS ')   // @KAIROS 단추 = 붙여 줌
  await input.pressSequentially('요약해 줘'); await input.press('Enter')
  await expect(bub.getByTestId('bubble-a')).toContainText('KAIROS')
  if (process.env.SHOTS) await page.screenshot({ path: process.env.SHOTS + '/comment.png' })   // 화면 자체 확인용
  const b0 = seen.find(b => b.kind === 'bubble'); expect(b0.messages.at(-1).content).toContain('민우: 이거 내일까지 확인 부탁해요\n민우: @KAIROS 요약해 줘')   // 앞 댓글도 AI에게(이름 붙여)
  await bub.getByTestId('bubble-close').click()
  await expect(page.getByTestId('bubble-badge')).toHaveText('💬 3')
  await openOn(page, '안테나 정상'); await bub.getByTestId('bubble-resolve').click()   // AI가 메모를 고쳐 씀(가짜 답 FIXED)
  await expect(page.getByTestId('bubble')).toHaveCount(0)
  await expect(page.getByTestId('bubble-badge')).toHaveCount(0)                           // 해결 = 표시 숨김
  await openOn(page, '안테나 정상')
  await expect(bub.getByTestId('bubble-resolved')).toBeVisible()
  await expect(bub.getByTestId('bubble-q')).toHaveCount(2); await expect(bub.getByTestId('bubble-a')).toHaveCount(1)   // 댓글은 남음
  await input.fill('다시 볼게요'); await input.press('Enter')                              // 새로 쓰면 다시 열림
  await expect(bub.getByTestId('bubble-resolved')).toHaveCount(0)
  await bub.getByTestId('bubble-close').click()
  await expect(page.getByTestId('bubble-badge')).toHaveText('💬 4')
})
