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

test('PDF 붙여넣기 = 보기 카드 → 한 번 = 고르기, 두 번 누르면 휠로 쪽 넘기기 → Alt+끌기 = 그림 + 출처(화살표 없음) → 「글로」 = 글 메모, 다시 열어도 카드', async ({ page }) => {
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
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2)           // 한 번 누르기 = 고르기만(2026-10-21 사용자)
  await expect(page.getByText('두 번 누르면 넘겨 보기').first()).toBeVisible()
  await expect(body).toHaveCSS('pointer-events', 'none')
  await page.mouse.click(b.x + b.width + 150, b.y + 300)
  await page.mouse.dblclick(b.x + b.width / 2, b.y + b.height / 2)         // 두 번 누르기 = 넘겨 보기 켜기
  await expect(body).toHaveCSS('pointer-events', 'auto')
  const z0 = (await page.evaluate(() => window.__mb.getCam())).z
  await page.mouse.wheel(0, 400)
  await expect.poll(() => body.evaluate(el => el.scrollTop)).toBeGreaterThan(100)
  expect((await page.evaluate(() => window.__mb.getCam())).z).toBe(z0)    // 휠이 칠판 확대로 안 감
  await body.evaluate(el => { el.scrollTop = 0 })

  const ph = b.width * 800 / 600                                          // 1쪽 높이(카드 폭에 맞춤)
  await expect(body.locator('.mb-pdftext span').first()).toBeAttached()  // 끌기(Alt 없이) = 글 고르기 — 보이지 않는 글 층
  await page.mouse.move(b.x + 3, b.y + 3); await page.mouse.down()
  await page.mouse.move(b.x + b.width - 3, b.y + ph - 3, { steps: 6 }); await page.mouse.up()
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.keyboard.press('Control+c')                                  // 복사 = 줄마다 줄바꿈
  const picked = await page.evaluate(() => navigator.clipboard.readText())
  expect(picked.split(/\r?\n/)).toEqual(['Alpha line', 'Bravo line'])
  expect((await items(page)).length).toBe(1)                              // 고르기는 칠판에 아무것도 안 만듦
  await page.mouse.click(b.x + b.width / 2, b.y + 4)                      // 고른 글 풀기(카드 안 누르기)
  await page.keyboard.down('Alt')
  await page.mouse.move(b.x + 5, b.y + 5); await page.mouse.down()
  await page.mouse.move(b.x + b.width - 5, b.y + ph * 0.4, { steps: 6 }); await page.mouse.up()
  await page.keyboard.up('Alt')
  await expect.poll(async () => (await items(page)).length, { timeout: 10_000 }).toBe(3)
  const [, img, cap] = await items(page)
  expect(img.type).toBe('image'); expect(img.alt).toContain('Alpha line'); expect(img.alt).not.toContain('Bravo')   // 오린 부분 글 = 보이지 않는 설명
  expect(cap.text).toBe('two-pages.pdf · 1쪽'); expect(cap.group_id).toBe(img.group_id)
  expect(img.pos[0]).toBeGreaterThan(card.pos[0] + card.rect[2])         // 카드 오른쪽
  await expect(page.getByTestId('pdf-clip-ok')).toContainText('오려 옴 · 1쪽')   // 오린 자리에 결과(2026-10-22 사용자: PDF를 크게 보면 칠판이 안 보임) → 1.5초 뒤 사라짐
  await expect(page.getByTestId('pdf-clip-ok')).toHaveCount(0, { timeout: 4000 })

  await expect(page.getByTestId('pdf-to-text')).toHaveCount(0)            // 「글로」 단추는 없앰(2026-10-21) — 그림 우클릭 「그림 속 글 읽기」
  let ocrCalls = 0; await page.route('**/api/ocr', r => { ocrCalls++; r.fulfill({ json: { text: '', model: 'x' } }) })
  const ic = await toPage(page, img.pos[0] + img.rect[2] / 2, img.pos[1] + img.rect[3] / 2)
  await page.mouse.click(ic.x, ic.y, { button: 'right' })
  await page.getByRole('button', { name: '그림 속 글 읽기' }).click()
  await expect.poll(async () => (await items(page)).map(it => it.type)).toEqual(['pdf', 'image', 'text', 'memo'])
  expect((await items(page))[3].lines.map(l => l.t)).toEqual(['Alpha line', 'two-pages.pdf · 1쪽'])   // PDF 그림 = 품은 글 그대로(KAIROS 안 부름)
  expect(ocrCalls).toBe(0)
  await page.keyboard.press('Control+z')
  await expect.poll(async () => (await items(page)).map(it => it.type)).toEqual(['pdf', 'image', 'text'])

  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  await expect.poll(() => page.locator('[data-pdfid] img').first().evaluate(im => im.complete && im.naturalWidth > 0)).toBe(true)   // 다시 열어도 쪽 그림
})

test('Alt 누르면 십자 커서 + 「끌어서 오려 오기」 · 여러 번 오리면 쪽마다 한 줄(같은 쪽 = 오른쪽, 다른 쪽 = 아래 새 줄) · 화살표 없음 · Ctrl+클릭·우클릭 = PDF 그 쪽', async ({ page }) => {   // 2026-10-22 사용자
  await openBoard(page, boardName('pdfcol')); await setCam(page)
  const p = await toPage(page, 300, 300); await page.mouse.move(p.x, p.y)
  await pasteFile(page, 'two-pages.pdf', 'application/pdf', PDF_B64)
  await expect.poll(async () => (await items(page)).length, { timeout: 10_000 }).toBe(1)
  const body = page.locator('[data-pdfid]'), b = await body.boundingBox(), ph = b.width * 800 / 600
  await expect(body.locator('img').first()).toHaveJSProperty('complete', true)
  await page.mouse.dblclick(b.x + b.width / 2, b.y + b.height / 2)
  await body.evaluate(el => { el.scrollTop = 0 })
  await expect(body.locator('.mb-pdftext span').first()).toHaveCSS('cursor', 'text')
  await page.mouse.move(b.x + 20, b.y + 20)
  await page.keyboard.down('Alt')
  await expect(body.locator('.mb-pdftext span').first()).toHaveCSS('cursor', 'crosshair')
  await expect(page.getByText('끌어서 오려 오기')).toBeVisible()
  const clip = async (y0, y1) => {
    const n = (await items(page)).length
    await page.mouse.move(b.x + 30, b.y + y0); await page.mouse.down()   // 가장자리 가운데 = 포트점이라 안쪽에서
    await page.mouse.move(b.x + b.width - 30, b.y + y1, { steps: 6 }); await page.mouse.up()
    await expect.poll(async () => (await items(page)).length, { timeout: 10_000 }).toBe(n + 2)
  }
  await body.evaluate(el => { el.scrollTop = el.scrollHeight / 2 + 4 })     // 2쪽부터(줄 순서 = 오린 순서 — 쪽 번호 아님)
  await clip(5, ph * 0.3); await clip(ph * 0.4, ph * 0.6)                   // 2쪽 둘 = 한 줄
  await body.evaluate(el => { el.scrollTop = 0 })
  await clip(ph * 0.5, ph * 0.7); await clip(5, ph * 0.4)                   // 1쪽 둘 = 아래 새 줄(마지막 = 글 있는 윗부분)
  await page.keyboard.up('Alt')
  await expect(page.getByText('끌어서 오려 오기')).toHaveCount(0)
  const all = await items(page), imgs = all.filter(it => it.type === 'image')
  const [c0] = all
  expect(imgs.length).toBe(4)
  expect(imgs.map(im => im.alt.split('\n')[0])).toEqual(['two-pages.pdf · 2쪽', 'two-pages.pdf · 2쪽', 'two-pages.pdf · 1쪽', 'two-pages.pdf · 1쪽'])
  const right = im => im.pos[0] + im.rect[2] * (im.scale || 1), bottom = im => im.pos[1] + im.rect[3] * (im.scale || 1)
  expect(imgs[0].pos[0]).toBeGreaterThan(c0.pos[0] + c0.rect[2])                 // 카드 오른쪽
  expect(imgs[1].pos[1]).toBeCloseTo(imgs[0].pos[1], 3)                           // 같은 쪽 = 같은 줄 위 끝
  expect(imgs[1].pos[0]).toBeGreaterThan(right(imgs[0]))                          //   그 오른쪽
  expect(imgs[2].pos[0]).toBeCloseTo(imgs[0].pos[0], 3)                           // 다른 쪽 = 새 줄, 왼쪽 끝 맞춤
  expect(imgs[2].pos[1]).toBeGreaterThan(Math.max(bottom(imgs[0]), bottom(imgs[1])))   //   앞 줄 아래
  expect(imgs[3].pos[1]).toBeCloseTo(imgs[2].pos[1], 3)
  expect(imgs[3].pos[0]).toBeGreaterThan(right(imgs[2]))
  expect(all.some(it => it.type === 'sarrow')).toBe(false)                     // 화살표 없음(2026-10-22 — 여럿이면 엉킴)
  await page.keyboard.press('Escape')                                       // 넘겨 보기 끝
  const ip0 = await toPage(page, imgs[2].pos[0] + 10, imgs[2].pos[1] + 5)
  // 오려 온 직후 = 그 그림만 고른 채 → 속성 카드 설명 = 첫 줄 + 접힌 글(2026-10-22 사용자: 너무 길어짐)
  await expect(page.getByTestId('image-alt')).toHaveText('two-pages.pdf · 1쪽')
  await expect(page.getByTestId('image-alt-more')).toContainText('들어 있음 ▸')
  await expect(page.getByText('Alpha line', { exact: true })).toHaveCount(0)
  await page.getByTestId('image-alt-more').click()
  await expect(page.getByText('Alpha line', { exact: true })).toBeVisible()

  const body2 = page.locator('[data-pdfid]')                                // 출처 바로가기 — 우클릭 메뉴·Ctrl+클릭
  await page.keyboard.press('Escape')
  const cp = await toPage(page, imgs[0].pos[0] + 10, imgs[0].pos[1] + imgs[0].rect[3] + 8)   // 밑 글 「two-pages.pdf · 2쪽」
  await body2.evaluate(el => { el.scrollTop = 0 })
  await page.mouse.click(cp.x, cp.y, { button: 'right' })
  await expect(page.getByRole('button', { name: /PDF에서 이 쪽\(2쪽\) 보기/ })).toBeVisible()
  await page.keyboard.press('Escape')
  await page.keyboard.down('Control'); await page.mouse.click(ip0.x, ip0.y); await page.keyboard.up('Control')   // Ctrl+클릭 = PDF 카드 넘겨 보기 켜짐
  await expect(body2).toHaveCSS('pointer-events', 'auto')
  await expect(body2).toHaveJSProperty('scrollTop', 0)                       // 1쪽 자리
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

  await page.mouse.dblclick(b.x + b.width / 2, b.y + b.height / 2)
  await page.mouse.wheel(0, 2000)
  await expect.poll(() => body.evaluate(el => el.scrollTop)).toBeGreaterThan(b.height * 0.8)
  const t = await body.evaluate(el => el.scrollTop)
  await page.mouse.click(b.x + b.width + 150, b.y + 300)                            // 바깥 누르기 = 끝
  await expect(body).toHaveCSS('pointer-events', 'none')
  expect(await body.evaluate(el => el.scrollTop)).toBeCloseTo(t, 0)        // 보던 쪽 그대로

  await page.mouse.dblclick(b.x + b.width / 2, b.y + b.height / 2)        // 다시 켜고 글쇠로 쪽 넘기기 — 카드가 옮겨지지 않음
  const pos0 = (await items(page))[0].pos
  await page.keyboard.press('Home'); await expect.poll(() => body.evaluate(el => el.scrollTop)).toBe(0)
  await page.keyboard.press('PageDown'); await page.keyboard.press('ArrowDown')
  await expect.poll(() => body.evaluate(el => el.scrollTop)).toBeGreaterThan(b.width * 800 / 600)
  expect((await items(page))[0].pos).toEqual(pos0)
  await page.mouse.click(b.x + b.width + 150, b.y + 300)

  const menuBtns = () => page.locator('div[style*="z-index: 30"] > div > button').allInnerTexts()
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { button: 'right' })   // 객체(켜지 않은 카드) = 틀 메뉴 — 쪽 메뉴·반전 없음
  let names = (await menuBtns()).join('|')
  expect(names).toContain('넘겨 보기'); expect(names).toContain('새 탭에서 보기'); expect(names).toContain('삭제')
  expect(names).not.toContain('통째로'); expect(names).not.toContain('좌우 반전'); expect(names).not.toContain('전체 선택')
  await page.keyboard.press('Escape')
  await page.mouse.click(b.x + b.width + 150, b.y + 300, { button: 'right' })   // 빈 곳 = 칠판 메뉴(고른 것 풂)
  names = (await menuBtns()).join('|'); expect(names).toContain('전체 선택'); expect(names).not.toContain('삭제')
  await page.keyboard.press('Escape')

  await page.mouse.dblclick(b.x + b.width / 2, b.y + b.height / 2)        // 켜고 안쪽 우클릭 = 내용 메뉴만, 넘겨 보기는 안 꺼짐
  await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2, { button: 'right' })
  names = (await menuBtns()).join('|')
  expect(names).toContain('이 쪽(2쪽) 통째로 칠판에'); expect(names).toContain('새 탭에서 보기'); expect(names).not.toContain('삭제'); expect(names).not.toContain('전체 선택')
  await expect(body).toHaveCSS('pointer-events', 'auto')
  await page.getByRole('button', { name: /이 쪽\(2쪽\) 통째로 칠판에/ }).click()
  await expect.poll(async () => (await items(page)).map(it => it.type), { timeout: 10_000 }).toEqual(['pdf', 'image', 'text'])
  const [card, img, cap] = await items(page)
  expect(cap.text).toBe('two-pages.pdf · 2쪽'); expect(img.alt).toContain('Charlie')
  expect(img.rect[2]).toBeCloseTo(card.rect[2] * card.scale, 0)           // 쪽 전체 = 카드 폭

  const [hb] = [await page.locator('[data-pdfid]').boundingBox()]           // ↗ 위 = 손가락 커서
  await page.mouse.move(hb.x + hb.width - 20, hb.y - 20)
  await expect(page.locator('svg[style*="cursor"]').first()).toHaveCSS('cursor', 'pointer')
})

test('그림 우클릭 「그림 속 글 읽기」 = KAIROS 글 → 그림 옆 메모(그림은 그대로)', async ({ page }) => {
  await openBoard(page, boardName('ocr')); await setCam(page)
  const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
  await pasteFile(page, 'shot.png', 'image/png', PNG)
  await expect.poll(async () => (await items(page)).length).toBe(1)
  let body = null; await page.route('**/api/ocr', r => { body = r.request().postDataJSON(); r.fulfill({ json: { text: '송신소 점검\n출력 4.8kW', model: 'claude-haiku-5-5', elapsed: 1.2 } }) })
  const [im] = await items(page), c = await toPage(page, im.pos[0] + im.rect[2] / 2, im.pos[1] + im.rect[3] / 2)
  await page.mouse.click(c.x, c.y, { button: 'right' })
  await page.getByRole('button', { name: '그림 속 글 읽기' }).click()
  await expect.poll(async () => (await items(page)).length).toBe(2)
  const [img, memo] = await items(page)
  expect(body.data).toBe(img.data)
  expect(memo.type).toBe('memo'); expect(memo.lines.map(l => l.t)).toEqual(['송신소 점검', '출력 4.8kW', '그림 속 글 · claude-haiku-5-5'])
  expect(memo.pos[0]).toBeGreaterThan(img.pos[0] + img.rect[2] * (img.scale || 1))   // 그림 오른쪽
})

test('md·txt 파일 = 붙여넣은 글과 같은 메모(맨 위 파일 이름) · 긴 파일은 접어서 · 끌어 놓은 자리', async ({ page }) => {   // 2026-10-21 사용자: md 끌어 놓아도 반응 없음
  await openBoard(page, boardName('mdfile')); await setCam(page)
  const md = '# 할 일\n- [ ] 철탑 점검\n- 보고서\n\n| 가 | 나 |\n|---|---|\n| 1 | 2 |'
  await pasteFile(page, '메모.md', '', Buffer.from(md).toString('base64'))    // 윈도우 크롬은 .md 종류를 비워 줌
  await expect.poll(async () => (await items(page)).length).toBe(1)
  const [m] = await items(page)
  expect(m.type).toBe('memo'); expect(m.lines.map(l => [l.k, l.t])).toEqual([['p', '메모.md'], ['h1', '할 일'], ['todo', '철탑 점검'], ['ul', '보고서'], ['table', '']])   // md 하나 = 메모 하나(표도 안에)
  expect(m.fold).toBeUndefined()

  const long = Array.from({ length: 40 }, (_, i) => `${i + 1}번째 줄`).join('\n')
  const p = await toPage(page, 900, 600)
  await page.evaluate(([b, x, y]) => {                                     // 진짜 끌어 놓기(칠판 상자에 drop 신호)
    const dt = new DataTransfer(); dt.items.add(new File([Uint8Array.from(atob(b), c => c.charCodeAt(0))], '긴글.txt', { type: 'text/plain' }))
    document.elementFromPoint(x, y).dispatchEvent(new DragEvent('drop', { dataTransfer: dt, clientX: x, clientY: y, bubbles: true, cancelable: true }))
  }, [Buffer.from(long).toString('base64'), p.x, p.y])
  await expect.poll(async () => (await items(page)).length).toBe(2)
  const l = (await items(page))[1]
  expect(l.type).toBe('memo'); expect(l.fold).toBe(true); expect(l.lines.length).toBe(41); expect(l.lines[0].t).toBe('긴글.txt')
  expect(Math.abs(l.pos[0] + l.rect[2] * (l.scale || 1) / 2 - 900)).toBeLessThan(40)   // 놓은 자리가 가운데
  await page.keyboard.press('Control+z')
  await expect.poll(async () => (await items(page)).length).toBe(1)
})
