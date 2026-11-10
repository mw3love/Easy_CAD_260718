// 흐름 74 — 화면 검사 7단계(카드, 2026-11-10): 문서 큰 창 = 진짜 창(열면 초점이 창 안 · Tab이 밖으로 안 나감 · 닫으면 연 자리) ·
// 블록 글쇠 길(Tab → Enter = 말 칸 · Esc · F2 · Ctrl+Enter) · 블록 이름 = 첫 낱말 · 640×360 말 칸 화면 안 · 블록 고치기 오류 = 쉬운 말 + 다시 보내기 ·
// 움직이는 카드 = 평소 멈춤 → ▶ 누르면 돎 → ■ · 대화창 문서 미리보기 크게 보기 = 앱 안 창. KAIROS는 가짜(/api/chat).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage, askChat } from './helpers.js'

const DOC = `<!doctype html><html><head><title>점검</title></head><body style="margin:0"><main style="width:1000px;padding:20px;box-sizing:border-box">
<h1 data-block="b1" data-kind="text">결론 한 문장</h1><p data-block="b2" data-kind="text">어려운 말로 쓴 단락</p><p data-block="b3" data-kind="text">끝 단락</p></main></body></html>`
const LIVE = '<!doctype html><html><body style="margin:0"><div id="x">멈춤</div><script>document.getElementById("x").textContent="돈다"</script></body></html>'
const models = page => page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
const where = page => page.evaluate(() => { let a = document.activeElement, inFrame = ''
  if (a?.tagName === 'IFRAME') { inFrame = a.contentDocument?.activeElement?.dataset?.block || 'frame' }
  return { inView: !!a?.closest?.('[data-testid="doc-view"]'), tag: a?.tagName, test: a?.dataset?.testid || '', block: inFrame } })

async function docCard(page) {
  await page.evaluate(h => window.__mb.ed.pinCard({ html: h, title: '점검', page_w: 1000, model: 'claude-opus-5-5', at: 1 }), DOC)
  return (await liveDoc(page)).items.find(it => it.type === 'doc')
}
async function openView(page, card) {
  const at = await toPage(page, card.pos[0] + 100, card.pos[1] + 200)
  await page.mouse.click(at.x, at.y, { button: 'right' }); await page.getByRole('menuitem', { name: '크게 보기…', exact: true }).click()
  await expect(page.getByTestId('doc-view')).toBeVisible()
  await expect(page.frameLocator('[data-testid="doc-frame"]').locator('[data-block="b2"][tabindex="0"]')).toHaveCount(1)
}

test('문서 큰 창 = 진짜 창 · 블록 글쇠 길(Tab → Enter = 말 칸 · Esc · F2 · Ctrl+Enter) · 블록 이름 = 첫 낱말', async ({ page }) => {
  await models(page)
  await openBoard(page, boardName('cardkeys')); await setCam(page)
  const card = await docCard(page); await openView(page, card)
  expect(await page.evaluate(() => document.querySelector('[data-testid="doc-view"]').matches(':modal'))).toBe(true)   // showModal — 뒤는 못 누름
  expect((await where(page)).inView).toBe(true)                                     // 열면 초점 = 창
  const seen = []
  for (let i = 0; i < 12; i++) { await page.keyboard.press('Tab'); const w = await where(page); seen.push(w.block || w.test || w.tag); expect(w.inView || w.tag === 'BODY').toBe(true) }   // Tab이 창 밖(칠판·위 막대)으로 안 나감 — 끝 다음 한 번은 브라우저 칸(헤드리스 = body) 뒤 다시 창 처음
  expect(seen).toContain('b1'); expect(seen).toContain('b2'); expect(seen.filter(x => x === 'doc-close').length).toBe(2)   // 블록에 글쇠로 닿고, 끝나면 창 처음으로 돎
  const ring = await page.evaluate(() => { const d = document.querySelector('[data-testid="doc-frame"]').contentDocument, el = d.querySelector('[data-block="b1"]'); el.focus(); return d.defaultView.getComputedStyle(el).outlineStyle })
  expect(ring).not.toBe('none')                                                      // 초점 테두리(Tab으로 옴 = :focus-visible)
  // b2로 가서 Enter = 말 칸, 이름 = 첫 낱말
  const doc = page.frameLocator('[data-testid="doc-frame"]')
  await doc.locator('[data-block="b2"]').focus(); await page.keyboard.press('Enter')
  const bub = page.getByTestId('block-bubble')
  await expect(bub).toBeVisible(); await expect(bub).toHaveAttribute('role', 'dialog')
  await expect(bub).toContainText('어려운 말로 쓴 … · 글'); await expect(bub).not.toContainText('b2')
  await expect(page.getByTestId('block-input')).toBeFocused()
  await expect(page.getByTestId('block-input')).toHaveAttribute('aria-label', '「어려운 말로 쓴 …」 고칠 말')
  await expect(page.getByRole('button', { name: '말 칸 닫기' })).toBeVisible(); await expect(page.getByRole('button', { name: '문서 창 닫기' })).toBeVisible()
  await page.keyboard.press('Escape'); await expect(bub).toHaveCount(0)              // Esc = 말 칸만 닫고 그 블록으로
  expect((await where(page)).block).toBe('b2')
  await page.keyboard.press('F2'); await expect(page.getByTestId('doc-hint')).toContainText('글자 고치는 중')   // F2 = 글자 고치기
  await page.keyboard.press('End'); await page.keyboard.type(' 덧')
  await page.keyboard.press('Control+Enter')                                         // Ctrl+Enter = 저장
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'doc').html).toContain('어려운 말로 쓴 단락 덧')
  const html = (await liveDoc(page)).items.find(it => it.type === 'doc').html
  expect(html).not.toContain('tabindex'); expect(html).not.toContain('data-mb')       // 글쇠 길 표시는 문서 글에 안 남음
  await expect(page.getByTestId('doc-hint')).not.toContainText('고치는 중')
  await expect.poll(async () => (await where(page)).block).toBe('b2')                // 저장한 뒤(문서가 다시 열려도) 그 블록에 초점
  await page.keyboard.press('Escape'); await expect(page.getByTestId('doc-view')).toHaveCount(0)
})

test('640×360 — 말 칸·✕·머리줄 화면 안 · 블록 고치기 오류 = 쉬운 말 + 다시 보내기(같은 질문 한 번만)', async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 360 })
  await models(page)
  let fail = true
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON()
    if (fail) return r.fulfill({ status: 502, json: { error: '서버 응답 502' } })
    return r.fulfill({ json: { kind: 'block', content: `${b.block}만 고쳤어요. 나머지는 그대로예요.`, html: b.doc.replace('어려운 말로 쓴 단락', '쉬운 단락'), block: b.block, model: 'claude-sonnet-5-5', credits: 2 } }) })
  await openBoard(page, boardName('cardsmall')); await setCam(page, { x: 20, y: 20, z: 0.5 })
  const card = await docCard(page); await openView(page, card)
  const inView = async sel => page.evaluate(s => { const r = document.querySelector(s).getBoundingClientRect(); return r.left >= 0 && r.top >= 0 && r.right <= innerWidth && r.bottom <= innerHeight }, sel)
  expect(await inView('[data-testid="doc-close"]')).toBe(true); expect(await inView('[data-testid="doc-print"]')).toBe(true)
  await page.frameLocator('[data-testid="doc-frame"]').locator('[data-block="b2"]').click()
  await expect(page.getByTestId('block-bubble')).toBeVisible()
  expect(await inView('[data-testid="block-bubble"]')).toBe(true)
  await page.getByTestId('block-input').fill('쉬운 말로'); await page.getByTestId('block-input').press('Enter')
  const err = page.getByTestId('block-err')
  await expect(err).toContainText('서버에 연결이 안 돼요'); await expect(err).toHaveAttribute('role', 'alert')
  await expect(err).not.toContainText('502')
  expect(await inView('[data-testid="block-bubble"]')).toBe(true)
  expect(await inView('[data-testid="block-retry"]')).toBe(true)
  fail = false; await page.getByTestId('block-retry').click()
  await expect(page.getByTestId('block-a')).toContainText('「어려운 말로 쓴 …」만 고쳤어요')
  await expect(page.getByTestId('block-err')).toHaveCount(0)
  await expect(page.getByTestId('block-bubble').getByText('쉬운 말로', { exact: true })).toHaveCount(1)   // 다시 보내도 질문은 한 번(같은 시각으로 덮음)
  await expect(page.getByTestId('block-done')).toBeVisible()                        // 고친 블록 = 초록 「✓ 고침」
})

test('움직이는 카드 = 평소 멈춤(스크립트 안 돎) → ▶ 움직이기 = 돎 → ■ 멈추기', async ({ page }) => {
  await openBoard(page, boardName('cardlive')); await setCam(page)
  await page.evaluate(h => window.__mb.ed.pinCard({ live: true, html: h, title: '시험 카드', model: 'gpt-6.1-sol' }), LIVE)
  const card = (await liveDoc(page)).items.find(it => it.type === 'doc')
  const still = page.locator(`iframe[data-still="${card.uid}"]`), run = page.locator(`iframe[data-liveid="${card.uid}"]`)
  await expect(still).toHaveCount(1); await expect(run).toHaveCount(0)
  await expect(page.frameLocator(`iframe[data-still="${card.uid}"]`).locator('#x')).toHaveText('멈춤')   // 스크립트가 안 돈 첫 모습
  const play = page.getByTestId('live-card-play'); await expect(play).toContainText('▶ 움직이기')
  const pb = await play.boundingBox(); await page.mouse.click(pb.x + pb.width / 2, pb.y + pb.height / 2)
  await expect(run).toHaveCount(1)
  await expect(page.frameLocator(`iframe[data-liveid="${card.uid}"]`).locator('#x')).toHaveText('돈다')   // 누르면 돎
  await expect(play).toContainText('■ 멈추기')
  await page.mouse.click(pb.x + pb.width / 2, pb.y + pb.height / 2)
  await expect(run).toHaveCount(0); await expect(still).toHaveCount(1)
})

test('대화창 문서 미리보기 크게 보기 = 앱 안 큰 창(새 탭 아님) — 닫으면 미리보기로 초점, 칠판에 붙인 뒤엔 블록 고치기까지', async ({ page, context }) => {
  await models(page)
  await page.route('**/api/chat', r => r.fulfill({ json: { kind: 'report', content: '문서를 만들었어요', title: '점검', html: DOC, page_w: 1000, model: 'claude-opus-5-5', elapsed: 3 } }))
  await openBoard(page, boardName('carddoc'), { chat: true }); await setCam(page)
  await askChat(page, '이거 정리해 줘')
  const thumb = page.getByRole('button', { name: '문서 크게 보기 · 인쇄' }); await expect(thumb).toBeVisible()
  let popped = false; context.on('page', () => { popped = true })
  await thumb.focus(); await page.keyboard.press('Enter')
  await expect(page.getByTestId('doc-view')).toBeVisible()
  await expect(page.getByTestId('doc-hint')).toContainText('보기·인쇄만')                // 칠판에 없는 문서 = 보기·인쇄만
  await expect(page.frameLocator('[data-testid="doc-frame"]').locator('h1')).toHaveText('결론 한 문장')
  expect(popped).toBe(false)
  await page.keyboard.press('Escape'); await expect(page.getByTestId('doc-view')).toHaveCount(0)
  await expect(thumb).toBeFocused()                                                 // 닫으면 연 자리
  await page.getByRole('button', { name: '칠판에 붙이기' }).click()
  await thumb.click(); await expect(page.getByTestId('doc-view')).toBeVisible()
  await expect(page.getByTestId('doc-hint')).toContainText('AI로 고치기')              // 붙인 카드 = 그 카드 창(블록 고치기)
  await expect(page.frameLocator('[data-testid="doc-frame"]').locator('[data-block="b2"][tabindex="0"]')).toHaveCount(1)
  expect(popped).toBe(false)
})
