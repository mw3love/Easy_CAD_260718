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
  await page.getByText('AI 말풍선 (KAIROS)').click()
}

test('메모 말풍선 — 고쳐 달라면 그 자리에서 고침 · 원래대로 ↔ 바꾼 것 · Ctrl+Z · 닫으면 💬 · 새로고침해도 대화 남음', async ({ page }) => {
  const name = boardName('bubble'), seen = []
  await fake(page, seen)
  await openBoard(page, name, { chat: true }); await setCam(page)
  await pasteText(page, '# 점검\n- 안테나 정상\n- 송신기 교체')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  await openOn(page, '안테나 정상')
  const bub = page.getByTestId('bubble'); await expect(bub).toBeVisible()
  await bub.getByTestId('bubble-input').fill('할 일만 뽑아 아래에 붙여 줘'); await bub.getByTestId('bubble-input').press('Enter')
  await expect(bub.getByTestId('bubble-a')).toContainText('할 일만 뽑아 아래에 붙였어요.')
  expect(seen).toHaveLength(1)
  expect(seen[0]).toMatchObject({ kind: 'bubble', item: { type: 'memo' }, messages: [{ role: 'user', content: '할 일만 뽑아 아래에 붙여 줘' }] })
  expect(seen[0].item.text).toContain('안테나 정상')                                        // 이 물건의 글만
  expect(hasTodo(await memoOf(page))).toBe(true)                                           // 그 자리에서 고침
  await expect(page.getByRole('complementary', { name: 'KAIROS 대화' }).getByText('할 일만 뽑아')).toHaveCount(0)   // 큰 대화창엔 안 섞임

  await bub.getByTestId('bubble-flip').click(); expect(hasTodo(await memoOf(page))).toBe(false)   // 원래대로
  await bub.getByTestId('bubble-flip').click(); expect(hasTodo(await memoOf(page))).toBe(true)    // 바꾼 것으로
  await page.mouse.click(1000, 700); await page.keyboard.press('Control+z')
  expect(hasTodo(await memoOf(page))).toBe(false)                                          // 칠판 Ctrl+Z 한 번 = 바로 앞

  await bub.getByTestId('bubble-close').click()
  await expect(page.getByTestId('bubble')).toHaveCount(0)
  await expect(page.getByTestId('bubble-badge')).toHaveText('💬 1')
  await waitSaved(page); await page.reload()
  await expect(page.getByTestId('bubble-badge')).toHaveText('💬 1')                         // 대화는 서버에(`.threads.json`)
  await page.getByTestId('bubble-badge').click()
  await expect(page.getByTestId('bubble').getByTestId('bubble-q')).toHaveText('할 일만 뽑아 아래에 붙여 줘')
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
  await memoBub.getByTestId('bubble-input').fill('요약해 줘'); await memoBub.getByTestId('bubble-input').press('Enter')
  await expect(memoBub.getByTestId('bubble-a')).toHaveCount(1)
  const lines = (await memoOf(page)).lines
  const c = await page.evaluate(id => { const b = window.__mb.ed.bubbleInfo(id).box; return { x: b.x + b.w / 2, y: b.y + b.h / 2 } }, img.uid)
  const p = await toPage(page, c.x, c.y)
  await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.getByText('AI 말풍선 (KAIROS)').click()
  await expect(page.getByTestId('bubble')).toHaveCount(2)                                  // 둘이 같이 열림
  const imgBub = page.locator('[data-testid="bubble"][aria-label="AI 말풍선 — 그림"]')
  await imgBub.getByTestId('bubble-input').fill('이 그림 뭐야?'); await imgBub.getByTestId('bubble-input').press('Enter')
  await expect(imgBub.getByTestId('bubble-a')).toContainText('작은 그림이에요.')
  const last = seen.at(-1)
  expect(last.item.type).toBe('image'); expect(last.item.image).toMatch(/^data:image\/jpeg;base64,/)
  expect(last.messages).toEqual([{ role: 'user', content: '이 그림 뭐야?' }])            // 메모 말풍선 대화는 안 실림
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
  await page.mouse.click(p.x, p.y, { button: 'right' }); await page.getByText('AI 말풍선 (KAIROS)').click()
  const bub = page.getByTestId('bubble'), input = bub.getByTestId('bubble-input')
  await input.fill('배경을 밝게 해 줘'); await input.press('Enter')
  await expect(bub.getByTestId('bubble-flip')).toHaveText('원래대로')
  let now = (await liveDoc(page)).items[0]
  expect(now.data).not.toBe(img0.data); expect(now.rect[2]).toBeCloseTo(img0.rect[2]); expect(now.rect[3]).toBeCloseTo(img0.rect[2])   // 폭 그대로, 높이 = 1:1
  await bub.getByTestId('bubble-flip').click()
  now = (await liveDoc(page)).items[0]; expect(now.data).toBe(img0.data); expect(now.rect[3]).toBeCloseTo(img0.rect[3])
  await bub.getByTestId('bubble-flip').click(); expect((await liveDoc(page)).items[0].rect[3]).toBeCloseTo(img0.rect[2])
  await input.fill('이거 뭐야?'); await input.press('Enter')
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
  await input.fill('합계 줄 더해 줘'); await input.press('Enter')
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
  await tb.getByTestId('bubble-input').fill('더 짧게'); await tb.getByTestId('bubble-input').press('Enter')
  await expect(tb.getByTestId('bubble-flip')).toHaveText('원래대로')
  expect(seen.at(-1).item).toMatchObject({ type: 'text', edit: 'text' })
  expect((await liveDoc(page)).items.find(it => it.type === 'text').text).toBe('점검 끝')
})
