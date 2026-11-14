// 흐름 71 — 입력부 한 부품(2026-11-09 사용자 — ChatGPT·Gemini·Claude와 비교 검토): 대화창·AI 칩 창·말풍선 모두 글과 단추가 한 상자,
// 줄바꿈 없는 긴 문단에도 칸이 늘어남(옛날엔 2줄 그대로), ↑로 보냄, 대화창은 기다리는 동안 ■ 멈춤. KAIROS는 가짜.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, toPage } from './helpers.js'

const LONG = '줄바꿈 없이 이어지는 긴 문단이에요. '.repeat(40)
const grew = (loc, min) => expect.poll(() => loc.evaluate(e => e.offsetHeight)).toBeGreaterThan(min)

test('대화창 — 긴 문단에 칸이 늘고, 지우면 줄고, ↑로 보내고, 기다리는 동안 ■', async ({ page }) => {
  const seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { seen.push(r.request().postDataJSON()) })   // 답이 안 옴
  await openBoard(page, boardName('composer'), { chat: true })
  const box = page.getByPlaceholder('물어보세요', { exact: false }), send = page.getByTestId('chat-send')
  await expect(send).toBeDisabled()                                                   // 빈 칸 = 못 누름
  const h0 = await box.evaluate(e => e.offsetHeight)
  await box.fill('짧은 글'); expect(await box.evaluate(e => e.offsetHeight)).toBe(h0)   // 짧으면 그대로
  await box.fill(LONG); await grew(box, h0 + 100)                                     // 줄바꿈이 없어도 늘어남
  await box.fill('짧은 글'); await expect.poll(() => box.evaluate(e => e.offsetHeight)).toBe(h0)
  const cb = await page.getByTestId('composer').boundingBox(), sb = await send.boundingBox(), mb = await page.getByTestId('mic').boundingBox(), tb = await box.boundingBox()
  for (const b of [sb, mb, tb]) { expect(b.x).toBeGreaterThanOrEqual(cb.x); expect(b.x + b.width).toBeLessThanOrEqual(cb.x + cb.width + 0.5); expect(b.y + b.height).toBeLessThanOrEqual(cb.y + cb.height + 0.5) }   // 글·단추가 한 상자 안
  await send.click()
  await expect(page.getByTestId('chat-busy')).toBeVisible()
  await expect.poll(() => seen.length).toBe(1)
  await expect(box).toBeFocused()                                                     // 단추를 눌러도 글 칸에 초점
  await page.getByTestId('chat-stop').click()
  await expect(page.getByTestId('chat-busy')).toBeHidden()
  await expect(page.getByText('취소했어요', { exact: false })).toBeVisible()
  await expect(page.getByTestId('chat-send')).toBeDisabled()
})

test('말풍선 — 입력 칸이 6줄까지 늘고 ↑로 보냄', async ({ page }) => {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); r.fulfill({ json: b.kind === 'bubble' ? { kind: 'bubble', content: '작은 답', model: 'fake-model', elapsed: 0.1 } : { content: '답', model: 'fake-model', elapsed: 0.1 } }) })
  await openBoard(page, boardName('composer2'), { chat: false }); await setCam(page)
  await page.getByRole('button', { name: '메모', exact: true }).click(); await page.keyboard.type('송신소 점검'); await clickScene(page, 1500, 900)
  const m = (await liveDoc(page)).items.find(it => it.type === 'memo'), q = await toPage(page, m.pos[0] + 40, m.pos[1] + 15)
  await page.mouse.click(q.x, q.y); await page.mouse.click(q.x, q.y, { button: 'right' }); await page.getByRole('menuitem', { name: /^댓글…/ }).click()   // 옛 AI 칩 창(2026-11-14에 치움) 대신 말풍선만
  const bi = page.getByTestId('bubble-input'), bs = page.getByTestId('bubble-send')
  await expect(bs).toBeDisabled()
  const h0 = await bi.evaluate(e => e.offsetHeight)
  await bi.fill(LONG); await grew(bi, h0 + 40)
  expect(await bi.evaluate(e => e.offsetHeight)).toBeLessThan(130)                    // 6줄에서 멈추고
  expect(await bi.evaluate(e => e.scrollHeight - e.clientHeight)).toBeGreaterThan(0)  // 나머지는 굴려서
  await bi.fill('@KAIROS 이 메모 뜻이 뭐야'); await bs.click()
  await expect(page.getByTestId('bubble-a')).toContainText('작은 답')
  await expect(bs).toBeDisabled()
  await bi.fill(LONG); await grew(bi, h0 + 40); await bi.fill('@KAIROS 하나 더'); await bs.click()
  await expect(page.getByTestId('bubble-a')).toHaveCount(2)
  await expect(bi).toBeFocused()
})
