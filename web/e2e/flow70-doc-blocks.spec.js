// 흐름 70 — 문서 블록 고치기(2026-11-09 문서 통합 2단계): 문서 카드 「크게 보기」 = 앱 안 큰 창 → 블록 누르기 = 말 칸 → 그 블록만 바뀜 · 원래대로 · Ctrl+Z
// + 새 문서에 넘치는 블록이 있으면 그 블록만 저절로 한 번 고침. KAIROS는 가짜(/api/chat).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, toPage } from './helpers.js'

const page1 = b2 => `<!doctype html><html><head><title>점검</title></head><body style="margin:0"><main style="width:1000px">
<h1 data-block="b1" data-kind="text">결론 한 문장</h1>${b2}<p data-block="b3" data-kind="text">끝 단락</p></main></body></html>`
const HARD = '<p data-block="b2" data-kind="text">어려운 말로 쓴 단락</p>'
const WIDE = '<div data-block="b2" data-kind="box" style="width:1400px">너무 넓은 칸</div>'

async function makeDoc(page, html, seen, fix) {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b)
    if (b.kind === 'block') return r.fulfill({ json: { kind: 'block', content: `${b.block}만 고쳤어요`, html: b.doc.replace(/<(p|div) data-block="b2"[^]*?<\/(p|div)>/, fix), block: b.block, model: 'claude-sonnet-5-5', credits: 2 } })
    return r.fulfill({ json: { kind: 'report', content: '문서', title: '점검', html, docs: [{ style: 'read', html, title: '점검' }], page_w: 1000, model: 'claude-opus-5-5', elapsed: 3 } }) })
  await page.getByRole('button', { name: '메모', exact: true }).click(); await page.keyboard.type('송신소 점검'); await clickScene(page, 1500, 900)
  const m = (await liveDoc(page)).items.find(it => it.type === 'memo')
  await clickScene(page, m.pos[0] + 40, m.pos[1] + 15)
  await page.getByTestId('ai-chip').click(); await page.locator('[data-testid="ai-kind"][data-kind="doc"]').click(); await page.getByTestId('ai-input').press('Enter')
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'doc').length).toBe(1)
  return (await liveDoc(page)).items.find(it => it.type === 'doc')
}

test('큰 창 — 블록 누르기 = 말 칸 → 그 블록만 바뀜 · 원래대로 ↔ 바꾼 것 · 닫고 Ctrl+Z', async ({ page }) => {
  const seen = []
  await openBoard(page, boardName('docblk'), { chat: false }); await setCam(page)
  const card = await makeDoc(page, page1(HARD), seen, '<p data-block="b2" data-kind="text">쉬운 말 단락</p>')
  const at = await toPage(page, card.pos[0] + 100, card.pos[1] + 200)
  await page.mouse.click(at.x, at.y, { button: 'right' }); await page.getByRole('button', { name: '크게 보기' }).click()
  const view = page.getByTestId('doc-view'); await expect(view).toBeVisible()
  const doc = page.frameLocator('[data-testid="doc-frame"]')
  await doc.locator('[data-block="b2"]').click()
  const bub = page.getByTestId('block-bubble'); await expect(bub).toContainText('b2 · 글')
  await page.getByTestId('block-input').fill('쉬운 말로'); await page.getByTestId('block-input').press('Enter')
  await expect(page.getByTestId('block-a')).toContainText('b2만 고쳤어요')
  const blk = seen.find(b => b.kind === 'block')
  expect(blk.block).toBe('b2'); expect(blk.doc).toContain('어려운 말로'); expect(blk.messages.at(-1).content).toBe('쉬운 말로')
  const html = async () => (await liveDoc(page)).items.find(it => it.type === 'doc').html
  await expect.poll(html).toContain('쉬운 말 단락')
  expect(await html()).toContain('결론 한 문장'); expect(await html()).toContain('끝 단락')       // 나머지는 그대로
  await expect(doc.locator('[data-block="b2"]')).toHaveText('쉬운 말 단락')                      // 창 안 문서도 바뀜
  await page.screenshot({ path: 'test-results/doc-blocks.png' })
  await page.getByTestId('block-flip').click(); await expect.poll(html).toContain('어려운 말로')   // 원래대로
  await page.getByTestId('block-flip').click(); await expect.poll(html).toContain('쉬운 말 단락')   // 바꾼 것으로
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape'); await expect(view).toHaveCount(0)
  await page.mouse.click(at.x, at.y, { button: 'right' }); await page.getByRole('button', { name: '크게 보기' }).click()   // 다시 열어도 그 블록 대화는 남음(말풍선 대화 저장소)
  await doc.locator('[data-block="b2"]').click(); await expect(page.getByTestId('block-a')).toContainText('b2만 고쳤어요')
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape'); await expect(view).toHaveCount(0)
  await page.keyboard.press('Control+z'); await expect.poll(html).toContain('어려운 말로')
})

test('큰 창 — 두 번 누르기 = 글자 손으로 고치기 · 바깥 = 저장 · Esc = 취소 · 그래프는 안 됨 · Ctrl+Z', async ({ page }) => {
  const seen = []
  await openBoard(page, boardName('dochand'), { chat: false }); await setCam(page)
  const card = await makeDoc(page, page1(HARD).replace('</main>', '<div data-block="b4" data-kind="chart"><svg width="200" height="80"><text x="10" y="40">그래프</text></svg></div></main>'), seen, HARD)
  const at = await toPage(page, card.pos[0] + 100, card.pos[1] + 200)
  await page.mouse.click(at.x, at.y, { button: 'right' }); await page.getByRole('button', { name: '크게 보기' }).click()
  const doc = page.frameLocator('[data-testid="doc-frame"]'), html = async () => (await liveDoc(page)).items.find(it => it.type === 'doc').html
  await doc.locator('[data-block="b3"]').dblclick()
  await expect(page.getByTestId('doc-hint')).toContainText('글자 고치는 중')
  await expect(page.getByTestId('block-bubble')).toHaveCount(0)                          // 두 번 누르기엔 말 칸이 안 뜸
  await page.keyboard.press('End'); await page.keyboard.type(' 덧붙임')
  await doc.locator('[data-block="b1"]').click()                                          // 바깥 누르기 = 저장
  await expect.poll(html).toContain('끝 단락 덧붙임')
  const h = await html(); expect(h).not.toContain('contenteditable'); expect(h).not.toContain('mb-'); expect(h).toContain('어려운 말로 쓴 단락')
  expect(h.replace('끝 단락 덧붙임', '끝 단락')).toBe(page1(HARD).replace('</main>', '<div data-block="b4" data-kind="chart"><svg width="200" height="80"><text x="10" y="40">그래프</text></svg></div></main>'))   // 나머지 글은 한 글자도 그대로
  await expect(page.getByTestId('block-bubble')).toHaveCount(0)                          // 저장한 누르기는 말 칸을 안 엶
  await doc.locator('[data-block="b1"]').dblclick(); await page.keyboard.type('지움')
  await page.keyboard.press('Escape')                                                     // Esc = 취소
  await expect(page.getByTestId('doc-hint')).not.toContainText('고치는 중')
  expect(await html()).toContain('결론 한 문장'); expect(await html()).not.toContain('지움')
  await doc.locator('[data-block="b4"]').dblclick()                                       // 그래프는 손으로 안 고침
  await expect(page.getByTestId('doc-hint')).not.toContainText('고치는 중')
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape'); await expect(page.getByTestId('doc-view')).toHaveCount(0)
  await page.keyboard.press('Control+z'); await expect.poll(html).not.toContain('덧붙임')
  expect(seen.filter(b => b.kind === 'block')).toHaveLength(0)                            // 크레딧 없음
})

test('큰 창 — 「움직이게」 = 문서 글은 그대로 · ▶ 그 블록 자리에서 움직임 · 고치기 · 빼기 · Ctrl+Z', async ({ page }) => {
  const seen = [], LIVE = n => `<!doctype html><html><body><div id="x">멈춤</div><script>document.getElementById('x').textContent='돈다 ${n}'</script></body></html>`
  await openBoard(page, boardName('doclive'), { chat: false }); await setCam(page)
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b)
    if (b.kind === 'block') return r.fulfill({ json: { kind: 'block_live', content: '움직여 볼 수 있게 만들었어요', live: LIVE(b.live ? 2 : 1), block: b.block, model: 'gpt-6.1-sol', credits: 5 } })
    return r.fulfill({ json: { kind: 'report', content: '문서', title: '점검', html: page1(HARD), docs: [{ style: 'read', html: page1(HARD), title: '점검' }], page_w: 1000, model: 'claude-opus-5-5', elapsed: 3 } }) })
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.getByRole('button', { name: '메모', exact: true }).click(); await page.keyboard.type('송신소 점검'); await clickScene(page, 1500, 900)
  const m = (await liveDoc(page)).items.find(it => it.type === 'memo')
  await clickScene(page, m.pos[0] + 40, m.pos[1] + 15)
  await page.getByTestId('ai-chip').click(); await page.locator('[data-testid="ai-kind"][data-kind="doc"]').click(); await page.getByTestId('ai-input').press('Enter')
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'doc').length).toBe(1)
  const card = (await liveDoc(page)).items.find(it => it.type === 'doc'), docIt = async () => (await liveDoc(page)).items.find(it => it.type === 'doc')
  const at = await toPage(page, card.pos[0] + 100, card.pos[1] + 200)
  await page.mouse.click(at.x, at.y, { button: 'right' }); await page.getByRole('button', { name: '크게 보기' }).click()
  const doc = page.frameLocator('[data-testid="doc-frame"]')
  await doc.locator('[data-block="b2"]').click()
  await page.getByTestId('block-input').fill('이 칸 움직이게 해 줘'); await page.getByTestId('block-input').press('Enter')
  await expect(page.getByTestId('block-live')).toBeVisible()                                   // 바로 움직임
  await expect(page.frameLocator('[data-testid="block-live"]').locator('#x')).toHaveText('돈다 1')   // 스크립트가 돎
  expect((await docIt()).html).toBe(page1(HARD))                                              // 문서 글(인쇄·한글)은 그대로
  expect((await docIt()).lives.b2).toContain("textContent='돈다 1'")
  expect(seen.at(-1).live).toBeFalsy()
  await page.screenshot({ path: 'test-results/doc-live.png' })
  const gap = await page.evaluate(() => { const r = s => document.querySelector(s).getBoundingClientRect(), f = document.querySelector('[data-testid="doc-frame"]'), d = f.contentDocument, k = f.getBoundingClientRect().width / f.offsetWidth
    const bar = r('[data-testid="live-bar"]'), prev = d.querySelector('[data-block="b1"]').getBoundingClientRect()
    return { overlap: bar.top < f.getBoundingClientRect().top + prev.bottom * k, below: bar.bottom <= r('[data-testid="block-live"]').top + 1 } })
  expect(gap).toEqual({ overlap: false, below: true })                                         // ▶ 단추 묶음이 앞 블록 글을 안 가림
  await page.keyboard.press('Escape')
  await page.getByTestId('live-talk').click(); await page.getByTestId('block-input').fill('느리게'); await page.getByTestId('block-input').press('Enter')
  await expect(page.frameLocator('[data-testid="block-live"]').locator('#x')).toHaveText('돈다 2')   // 그 판 고치기
  expect(seen.at(-1).live).toBe(true); expect(seen.at(-1).live_html).toContain("textContent='돈다 1'")
  await page.keyboard.press('Escape')
  await page.getByTestId('live-play').click(); await expect(page.getByTestId('block-live')).toHaveCount(0)   // 멈춘 모습
  await expect(page.getByTestId('live-play')).toHaveText('▶ 움직여 보기')
  await doc.locator('[data-block="b2"]').dblclick(); await page.keyboard.press('End'); await page.keyboard.type('!')   // 움직이는 블록을 손으로 고쳐도
  await doc.locator('[data-block="b1"]').click()
  await expect.poll(async () => (await docIt()).html).toContain('어려운 말로 쓴 단락!')
  expect((await docIt()).html).toContain('<p data-block="b2" data-kind="text">어려운 말로 쓴 단락!</p>')                 // 이 창의 자리 표시(여백)는 문서에 안 들어감
  await page.getByTestId('live-drop').click(); await expect(page.getByTestId('live-bar')).toHaveCount(0)
  expect((await docIt()).lives).toBeFalsy()
  await page.keyboard.press('Escape'); await expect(page.getByTestId('doc-view')).toHaveCount(0)
  await page.keyboard.press('Control+z'); await expect.poll(async () => (await docIt()).lives?.b2 || '').toContain('돈다 2')
})

test('새 문서에 넘치는 블록 = 그 블록만 저절로 한 번 고침(문제가 줄었을 때만)', async ({ page }) => {
  const seen = []
  await openBoard(page, boardName('docfix'), { chat: true }); await setCam(page)
  await makeDoc(page, page1(WIDE), seen, '<div data-block="b2" data-kind="box">알맞은 칸</div>')
  await expect.poll(() => seen.map(b => b.kind).join()).toBe('report,block')
  expect(seen[1].block).toBe('b2'); expect(seen[1].messages[0].content).toContain('넘침')
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'doc')?.html || '').toContain('알맞은 칸')
  await expect(page.locator('aside[aria-label="KAIROS 대화"]')).toContainText('잘린 곳 1곳을 고쳤어요')
})
