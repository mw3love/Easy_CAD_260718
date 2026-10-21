// 흐름 23 — PDF 보기 카드(2026-10-21 사용자: 휠로 쭉 보다가 Alt+드래그로 칠판에 오려 오기) + HTML 파일 = 문서 카드
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { boardName, openBoard, setCam, liveDoc, toPage, waitSaved } from './helpers.js'

const PDF_B64 = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'fixtures', 'two-pages.pdf')).toString('base64')   // 1쪽 위 「Alpha line」·아래 「Bravo line」, 2쪽 「Charlie」
const pasteFile = (page, name, type, b64) => page.evaluate(([n, t, b]) => {
  const dt = new DataTransfer(); dt.items.add(new File([Uint8Array.from(atob(b), c => c.charCodeAt(0))], n, { type: t }))
  window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }))
}, [name, type, b64])
const items = async page => (await liveDoc(page)).items

test('PDF 붙여넣기 = 보기 카드 → 누르면 휠로 쪽 넘기기 → Alt+끌기 = 그림 + 출처 + 점선 화살표 → 「글로」 = 글 메모, 다시 열어도 카드', async ({ page }) => {
  const name = boardName('pdf')
  await openBoard(page, name); await setCam(page)
  const p = await toPage(page, 300, 300); await page.mouse.move(p.x, p.y)
  await pasteFile(page, 'two-pages.pdf', 'application/pdf', PDF_B64)
  await expect.poll(async () => (await items(page)).length, { timeout: 10_000 }).toBe(1)
  const [card] = await items(page)
  expect(card.type).toBe('pdf'); expect(card.pages).toBe(2); expect(card.name).toBe('two-pages.pdf')
  expect(card.url).toMatch(/^\/api\/pdf\//); expect(card.thumb).toMatch(/^data:image\/jpeg/); expect(card.text).toContain('Charlie')
  expect(card.data).toBeUndefined()                                       // 원본은 서버 — 칠판엔 주소만

  const body = page.locator('[data-pdfid]'), b = await body.boundingBox()
  await expect(body.locator('img').first()).toHaveJSProperty('complete', true)
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2)           // 한 번 누르기 = 넘겨 보기 켜기
  await expect(body).toHaveCSS('pointer-events', 'auto')
  const z0 = (await page.evaluate(() => window.__mb.getCam())).z
  await page.mouse.wheel(0, 400)
  await expect.poll(() => body.evaluate(el => el.scrollTop)).toBeGreaterThan(100)
  expect((await page.evaluate(() => window.__mb.getCam())).z).toBe(z0)    // 휠이 칠판 확대로 안 감
  await body.evaluate(el => { el.scrollTop = 0 })

  const ph = b.width * 800 / 600                                          // 1쪽 높이(카드 폭에 맞춤)
  await page.keyboard.down('Alt')
  await page.mouse.move(b.x + 5, b.y + 5); await page.mouse.down()
  await page.mouse.move(b.x + b.width - 5, b.y + ph * 0.4, { steps: 6 }); await page.mouse.up()
  await page.keyboard.up('Alt')
  await expect.poll(async () => (await items(page)).length, { timeout: 10_000 }).toBe(4)
  const [, img, cap, arrow] = await items(page)
  expect(img.type).toBe('image'); expect(img.alt).toContain('Alpha line'); expect(img.alt).not.toContain('Bravo')   // 오린 부분 글 = 보이지 않는 설명
  expect(cap.text).toBe('two-pages.pdf · 1쪽'); expect(cap.group_id).toBe(img.group_id)
  expect(arrow.type).toBe('sarrow'); expect(arrow.style).toBe(2)
  expect(img.pos[0]).toBeGreaterThan(card.pos[0] + card.rect[2])         // 카드 오른쪽

  await page.getByTestId('pdf-to-text').click()
  await expect.poll(async () => (await items(page)).map(it => it.type)).toEqual(['pdf', 'sarrow', 'memo'])
  const memo = (await items(page))[2]
  expect(memo.lines.map(l => l.t)).toEqual(['Alpha line', 'two-pages.pdf · 1쪽'])
  await page.keyboard.press('Control+z')                                  // 되돌리면 다시 그림
  await expect.poll(async () => (await items(page)).map(it => it.type)).toEqual(['pdf', 'image', 'text', 'sarrow'])

  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  await expect.poll(() => page.locator('[data-pdfid] img').first().evaluate(im => im.complete && im.naturalWidth > 0)).toBe(true)   // 다시 열어도 쪽 그림
})

test('HTML 파일 붙여넣기 = 문서 카드(파일 이름·제목)', async ({ page }) => {
  await openBoard(page, boardName('html')); await setCam(page)
  const html = '<!doctype html><html><head><title>송신소 안내</title></head><body><h1>안내</h1><script>document.body.textContent="돌았음"</script></body></html>'
  await pasteFile(page, '안내.html', 'text/html', Buffer.from(html).toString('base64'))
  await expect.poll(async () => (await items(page)).length).toBe(1)
  const [d] = await items(page)
  expect(d.type).toBe('doc'); expect(d.title).toBe('송신소 안내'); expect(d.file).toBe('안내.html'); expect(d.html).toBe(html)
  await expect(page.locator('iframe[data-docid]')).toHaveAttribute('sandbox', '')   // 파일 속 프로그램은 끔
})
