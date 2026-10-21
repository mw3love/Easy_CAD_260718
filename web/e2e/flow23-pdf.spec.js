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

test('멀리서 넣어도 쪽 그림(잠들지 않음) · 바깥 눌러도 보던 쪽 · 우클릭 「이 쪽 통째로 칠판에」', async ({ page }) => {   // 2026-10-21 사용자 지적 셋
  await openBoard(page, boardName('pdf2')); await setCam(page, { x: 400, y: 200, z: 0.05 })
  const p = await toPage(page, 6000, 6000); await page.mouse.move(p.x, p.y)
  await pasteFile(page, 'two-pages.pdf', 'application/pdf', PDF_B64)
  await expect.poll(async () => (await items(page)).length, { timeout: 10_000 }).toBe(1)
  const body = page.locator('[data-pdfid]')
  await expect(body).toHaveCount(1)                                       // 화면에 크게 보이면 쪽 그림(옛 버그: 배율을 빼고 재서 첫 쪽 작은 그림만)
  const b = await body.boundingBox()
  expect(b.height).toBeGreaterThan(900 * 0.6)                             // 넣을 때 쪽이 화면 높이 80% 가까이

  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2)
  await page.mouse.wheel(0, 2000)
  await expect.poll(() => body.evaluate(el => el.scrollTop)).toBeGreaterThan(b.height * 0.8)
  const t = await body.evaluate(el => el.scrollTop)
  await page.mouse.click(b.x + b.width + 150, b.y + 300)                            // 바깥 누르기 = 끝
  await expect(body).toHaveCSS('pointer-events', 'none')
  expect(await body.evaluate(el => el.scrollTop)).toBeCloseTo(t, 0)        // 보던 쪽 그대로

  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2)          // 다시 켜고 글쇠로 쪽 넘기기 — 카드가 옮겨지지 않음
  const pos0 = (await items(page))[0].pos
  await page.keyboard.press('Home'); await expect.poll(() => body.evaluate(el => el.scrollTop)).toBe(0)
  await page.keyboard.press('PageDown'); await page.keyboard.press('ArrowDown')
  await expect.poll(() => body.evaluate(el => el.scrollTop)).toBeGreaterThan(b.width * 800 / 600)
  expect((await items(page))[0].pos).toEqual(pos0)
  await page.mouse.click(b.x + b.width + 150, b.y + 300)

  const menuBtns = () => page.locator('div[style*="z-index: 30"] > div > button').allInnerTexts()
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { button: 'right' })   // 객체(켜지 않은 카드) = 틀 메뉴 — 쪽 메뉴·반전 없음
  let names = (await menuBtns()).join('|')
  expect(names).toContain('넘겨 보기'); expect(names).toContain('원본 새 탭에서 열기'); expect(names).toContain('삭제')
  expect(names).not.toContain('통째로'); expect(names).not.toContain('좌우 반전'); expect(names).not.toContain('전체 선택')
  await page.keyboard.press('Escape')
  await page.mouse.click(b.x + b.width + 150, b.y + 300, { button: 'right' })   // 빈 곳 = 칠판 메뉴(고른 것 풂)
  names = (await menuBtns()).join('|'); expect(names).toContain('전체 선택'); expect(names).not.toContain('삭제')
  await page.keyboard.press('Escape')

  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2)          // 켜고 안쪽 우클릭 = 내용 메뉴만, 넘겨 보기는 안 꺼짐
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { button: 'right' })
  names = (await menuBtns()).join('|')
  expect(names).toContain('이 쪽(2쪽) 통째로 칠판에'); expect(names).toContain('이 쪽 글을 메모로'); expect(names).not.toContain('삭제'); expect(names).not.toContain('전체 선택')
  await expect(body).toHaveCSS('pointer-events', 'auto')
  await page.getByRole('button', { name: /이 쪽\(2쪽\) 통째로 칠판에/ }).click()
  await expect.poll(async () => (await items(page)).map(it => it.type), { timeout: 10_000 }).toEqual(['pdf', 'image', 'text', 'sarrow'])
  const [card, img, cap] = await items(page)
  expect(cap.text).toBe('two-pages.pdf · 2쪽'); expect(img.alt).toContain('Charlie')
  expect(img.rect[2]).toBeCloseTo(card.rect[2] * card.scale, 0)           // 쪽 전체 = 카드 폭

  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { button: 'right' })   // 「글을 메모로」 = 바로 메모, 되돌리기 한 번에 사라짐
  await page.getByRole('button', { name: '이 쪽 글을 메모로' }).click()
  await expect.poll(async () => (await items(page)).length, { timeout: 10_000 }).toBe(6)
  const memo = (await items(page)).find(it => it.type === 'memo'); expect(memo.lines.map(l => l.t)).toContain('Charlie')
  await page.keyboard.press('Escape'); await page.keyboard.press('Control+z')
  await expect.poll(async () => (await items(page)).length).toBe(4)

  const [hb] = [await page.locator('[data-pdfid]').boundingBox()]           // ↗ 위 = 손가락 커서
  await page.mouse.move(hb.x + hb.width - 20, hb.y - 20)
  await expect(page.locator('svg[style*="cursor"]').first()).toHaveCSS('cursor', 'pointer')
})
