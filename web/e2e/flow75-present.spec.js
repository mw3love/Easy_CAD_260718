// 흐름 75 — 화면 검사 8단계(발표·내보내기, 2026-11-11): 움직임 줄이기 = 장 넘김 바로 · 640×360 막대 화면 안 · 🔊 402 = 쉬운 말 + 단추 꺼짐 ·
// 막대 aria-pressed · 발표 = 진짜 창(초점 들어가고 끝나면 돌아옴) · 우클릭 = 공용 메뉴 · 판서 띠 = 다음 편집까지 · ◀ 자리 고정 ·
// 공유 HTML 문서 카드 = 누르면 문서 틀 · 공유 HTML 글꼴 · PDF 끝에 문서 쪽 · SVG 문서 카드 자리 글
import { test, expect } from '@playwright/test'
import { writeFileSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { pathToFileURL } from 'node:url'
import { tmpdir } from 'node:os'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, liveDoc, menuPick, morePick } from './helpers.js'

const slides = page => page.evaluate(d => window.__mb.ed.slidesBoard(d), { title: 't', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'], notes: '오늘은 송신소 이야기입니다.' },
  { title: '아주 긴 이름의 두 번째 장 — 송신소에서 전파가 나가기까지 거치는 길', layout: '글머리', bullets: ['b'] }, { title: '끝', layout: '마무리', bullets: ['c'] }] })
async function present(page, name, { size } = {}) {
  if (size) await page.setViewportSize(size)
  await openBoard(page, boardName(name)); await setCam(page, { x: 0, y: 0, z: 0.25 })
  await slides(page); await page.keyboard.press('Escape')
  await morePick(page, '발표')
  await expect(page.getByTestId('presenter')).toBeVisible()
}
const slideG = page => page.getByTestId('presenter').locator('svg').first().locator('> g > g').first()

test('움직임 줄이기면 장 넘김 기본 = 바로(움직임 없이 그 자리로)', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await present(page, 'pres-rm')
  const bar = page.getByTestId('present-bar')
  await expect(bar.getByRole('button', { name: '바로', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(bar.getByRole('button', { name: '이동', exact: true })).toHaveAttribute('aria-pressed', 'false')
  await page.keyboard.press('ArrowRight')
  const t1 = await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => r(document.querySelector('[data-testid=presenter] svg > g > g').getAttribute('transform'))))))
  await page.waitForTimeout(600)
  expect(await slideG(page).getAttribute('transform')).toBe(t1)                                 // 두 장면 뒤 = 이미 끝 자리
})

test('640×360 — 막대가 화면 안(◀·장 번호·어둡게·끝) · 켜짐 = aria-pressed · 코랄 채움 없음 · 장 목록이 막대에 안 가림', async ({ page }) => {
  await present(page, 'pres-640', { size: { width: 640, height: 360 } })
  const bar = page.getByTestId('present-bar')
  for (const loc of [bar.getByRole('button', { name: '이전 장' }), bar.getByTestId('present-slide'), bar.getByRole('button', { name: '어둡게', exact: true }), bar.getByRole('button', { name: '끝', exact: true })]) {
    const b = await loc.boundingBox(); expect(b).toBeTruthy()
    expect(b.x).toBeGreaterThanOrEqual(0); expect(b.y).toBeGreaterThanOrEqual(0); expect(b.x + b.width).toBeLessThanOrEqual(640); expect(b.y + b.height).toBeLessThanOrEqual(360)
  }
  const pen = bar.getByRole('button', { name: '펜', exact: true })
  await expect(pen).toHaveAttribute('aria-pressed', 'false')
  await pen.click(); await expect(pen).toHaveAttribute('aria-pressed', 'true')
  await expect(bar.getByRole('button', { name: '형광펜', exact: true })).toHaveAttribute('aria-pressed', 'false')
  await expect(bar.getByRole('button', { name: '빨강', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await expect(bar.getByRole('button', { name: '초록', exact: true })).toHaveAttribute('aria-pressed', 'false')
  await expect(bar.getByRole('button', { name: '레이저', exact: true })).toHaveAttribute('aria-pressed', 'false')
  await expect(bar.getByRole('button', { name: '굵기 보통' })).toHaveAttribute('aria-pressed', 'true')
  expect(await bar.evaluate(el => [...el.querySelectorAll('button')].filter(b => getComputedStyle(b).backgroundColor === 'rgb(218, 119, 86)').length)).toBe(0)
  await page.keyboard.press('Escape')                                                          // 펜 끄기
  await page.keyboard.press('Tab'); await expect(page.getByTestId('slide-list')).toBeVisible()
  const last = await page.getByTestId('slide-thumb').last().boundingBox(), bb = await bar.boundingBox()
  const listBox = await page.getByTestId('slide-thumb').first().evaluate(el => el.parentElement.getBoundingClientRect().bottom)
  expect(listBox).toBeLessThanOrEqual(bb.y + 1)                                                // 목록 칸 = 막대 위에서 끝남(넘치면 칸 안에서 굴림)
  expect(last).toBeTruthy()
})

test('🔊 402 = 「크레딧이 모자라요」 + 단추 꺼짐, 알림은 다음 조작까지 · role=status', async ({ page }) => {
  await page.route('**/api/tts', r => r.fulfill({ status: 402, json: { error: 'insufficient credits' } }))
  await present(page, 'pres-tts')
  const btn = page.getByTestId('present-voice'), toast = page.getByTestId('present-toast')
  await expect(toast).toHaveAttribute('role', 'status')
  await page.keyboard.press('n')
  await expect(toast).toContainText('크레딧이 모자라요')
  await expect(btn).toHaveAttribute('aria-pressed', 'false')                                   // 실패하면 끔(사용자 결정)
  await page.waitForTimeout(2600); await expect(toast).toContainText('크레딧이 모자라요')        // 2초 알림과 달리 남음
  await page.keyboard.press('m'); await expect(toast).toHaveText('')                            // 다음 조작에 닫힘
})

test('발표 = 진짜 창 — 열면 초점이 발표로, 끝나면 연 단추로 · 우클릭 = 공용 메뉴(「다음 장」)', async ({ page }) => {
  await openBoard(page, boardName('pres-dlg')); await setCam(page, { x: 0, y: 0, z: 0.25 })
  await slides(page); await page.keyboard.press('Escape')
  const open = page.getByTestId('tools-more')   // 발표 = 도구 줄 ⋯ 안(2026-11-14 B1) — 끝나면 ⋯ 단추로
  await morePick(page, '발표')
  const pr = page.getByTestId('presenter')
  await expect(pr).toHaveAttribute('role', 'dialog'); await expect(pr).toHaveAttribute('aria-modal', 'true'); await expect(pr).toHaveAttribute('aria-label', '발표')
  await expect(pr).toBeFocused()
  const vp = page.viewportSize()
  await page.mouse.move(vp.width / 2, vp.height / 3); await page.mouse.down({ button: 'right' }); await page.mouse.up({ button: 'right' })
  const menu = page.getByTestId('present-menu')
  await expect(menu).toHaveAttribute('role', 'menu')
  await expect(menu.getByRole('menuitem', { name: /지우개/ })).toContainText('6 · E')            // 글쇠 = 둘째 칸
  await expect(menu.getByRole('menuitem', { name: /^펜/ })).toBeFocused()                       // 열면 첫 줄
  await page.keyboard.press('ArrowDown'); await expect(menu.getByRole('menuitem', { name: /형광펜/ })).toBeFocused()   // 글쇠는 메뉴가(장이 안 넘어감)
  await expect(page.getByTestId('present-bar')).toContainText('1 / 3')
  await menu.getByRole('menuitem', { name: /다음 장/ }).click()
  await expect(page.getByTestId('present-bar')).toContainText('2 / 3')
  await expect(menu).toHaveCount(0); await expect(pr).toBeFocused()
  await page.keyboard.press('Escape'); await expect(pr).toBeHidden()
  await expect(open).toBeFocused()                                                              // 끝나면 연 단추로
})

test('◀ ▶ 자리 = 장을 넘겨도 그대로(장 단추 폭 고정 · 전체 이름은 풍선)', async ({ page }) => {
  await present(page, 'pres-fix')
  const bar = page.getByTestId('present-bar'), prev = bar.getByRole('button', { name: '이전 장' }), next = bar.getByRole('button', { name: '다음 장' })
  const settle = async () => { let p = [await prev.boundingBox(), await next.boundingBox()]   // 막대가 자리 잡을 때까지(전체 시험 중 무거우면 들어오는 움직임 도중에 쟀음 — 2026-11-14)
    for (let i = 0; i < 20; i++) { await page.waitForTimeout(100); const q = [await prev.boundingBox(), await next.boundingBox()]; if (Math.abs(q[0].x - p[0].x) < 0.5 && Math.abs(q[1].x - p[1].x) < 0.5) return q; p = q } return p }
  const a = await settle()
  await page.keyboard.press('ArrowRight'); await expect(bar).toContainText('2 / 3')
  const b = await settle()
  expect(b[0].x).toBeCloseTo(a[0].x, 0); expect(b[1].x).toBeCloseTo(a[1].x, 0)
  await expect(bar.getByTestId('present-slide')).toHaveAttribute('title', /아주 긴 이름의 두 번째 장 — 송신소에서 전파가 나가기까지 거치는 길/)
  expect(await bar.getByTestId('present-slide').evaluate(el => getComputedStyle(el).fontVariantNumeric)).toContain('tabular-nums')
})

test('판서 지움 띠 = 8초가 지나도 남음 → 다음 편집에 사라짐 · ✕ 「알림 닫기」 · Ctrl+Z 안내', async ({ page }) => {
  await present(page, 'pres-notes')
  await page.keyboard.press('1')
  const vp = page.viewportSize()
  await page.mouse.move(vp.width * 0.4, vp.height * 0.4); await page.mouse.down(); await page.mouse.move(vp.width * 0.6, vp.height * 0.5, { steps: 6 }); await page.mouse.up()
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape')
  const band = page.getByTestId('notes-gone')
  await expect(band).toContainText('발표 판서 1개 지움'); await expect(band).toContainText('Ctrl+Z로도 되살림'); await expect(band).toHaveAttribute('role', 'status')
  await expect(band.getByRole('button', { name: '알림 닫기' })).toBeVisible()
  await page.waitForTimeout(8500); await expect(band).toBeVisible()                             // 전엔 8초 뒤 사라짐
  const n0 = (await liveDoc(page)).items.length
  await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 120, y: 60 })   // 다음 편집
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(n0 + 1)
  await expect(band).toBeHidden()
  expect((await liveDoc(page)).items.some(it => it.type === 'path')).toBe(false)
})

const DOC = `<!doctype html><html><head><style>body{font-family:'Pretendard',sans-serif;margin:0;padding:40px;color:#222}h1{font-size:40px}p{font-size:18px;line-height:1.7}</style></head>
<body><h1>송신소 안내 문서</h1>${Array.from({ length: 40 }, (_, i) => `<p>${i + 1}번째 단락 — 송신소는 방송 신호를 전파로 바꾸어 멀리 보내는 마지막 관문입니다. 전력·냉각·안테나를 늘 살핍니다.</p>`).join('')}<img src="x" onerror="parent.__evil=1"></body></html>`

async function exportAs(page, fmt) {
  await menuPick(page, '내보내기…')
  const form = page.locator('div', { hasText: /^내보내기/ }).filter({ has: page.getByTestId('export-preview') }).last()
  await form.getByRole('button', { name: fmt, exact: true }).click()
  await expect(page.getByTestId('export-thumb').first()).toBeVisible()
  if (fmt === 'PDF') { await form.getByRole('button', { name: '내보내기', exact: true }).click(); return null }
  const dl = page.waitForEvent('download'); await form.getByRole('button', { name: '내보내기', exact: true }).click(); const d = await dl
  return { name: d.suggestedFilename(), path: await d.path() }
}
async function docBoard(page, tag) {
  await openBoard(page, boardName(tag)); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 220, y: 100 }); await page.keyboard.type('송신 계통'); await clickScene(page, 700, 500)
  await page.evaluate(h => window.__mb.ed.pinCard({ html: h, title: '송신소 안내', page_w: 1000, model: 'claude-opus-5-5', at: 1 }), DOC)
  await page.keyboard.press('Escape')
}

test('공유 HTML — 문서 카드를 누르면 그 자리에 문서 틀(sandbox 빈 값) · 글꼴 Pretendard · ◀ ▶ 이름', async ({ page, browser }) => {
  await docBoard(page, 'share-doc')
  const html = await exportAs(page, 'HTML')
  const src = readFileSync(html.path, 'utf8')
  expect(src).not.toContain('font:600 13px inherit'); expect(src).toContain('aria-label="다음 장"')
  const off = await browser.newContext({ offline: true }), p2 = await off.newPage()
  const file = join(tmpdir(), `mb-share-${Date.now()}.html`); writeFileSync(file, src)   // 내려받은 파일은 이름에 .html이 없어 글로 열림
  await p2.goto(pathToFileURL(file).href)
  await expect(p2.getByText('누르면 문서가 열려요').first()).toBeAttached()
  expect(await p2.evaluate(() => getComputedStyle(document.querySelector('#bar button')).fontFamily)).toContain('Pretendard')
  const card = p2.locator('#ov [data-doc-src]').first(), b = await card.boundingBox()
  await p2.mouse.click(b.x + b.width / 2, b.y + b.height / 2)
  const fr = p2.locator('#ov foreignObject iframe')
  await expect(fr).toHaveCount(1); await expect(fr).toHaveAttribute('sandbox', '')
  await expect(p2.frameLocator('#ov foreignObject iframe').getByText('송신소 안내 문서')).toBeVisible()
  await off.close()
})

test('PDF = 칠판 쪽 뒤에 문서 쪽(자리 글 「N쪽에 이어 붙임」·↗ 없음, 쪽 수 = 칠판 쪽 + 문서 쪽) · SVG 자리 글 = 「따로 인쇄」', async ({ page, browser }) => {
  const logs = []; page.on('console', m => logs.push(m.text()))
  await docBoard(page, 'pdf-doc')
  await exportAs(page, 'PDF')
  const fr = page.locator('iframe[data-testid=pdf-print]')
  await expect(fr).toHaveCount(1)
  await expect.poll(() => fr.evaluate(f => f.contentDocument.querySelectorAll('.mbdoc').length)).toBe(1)
  const got = await fr.evaluate(f => { const d = f.contentDocument, h = d.querySelector('.mbdoc')
    return { sandbox: f.getAttribute('sandbox'), svgPages: d.querySelectorAll('body > div[class^=p]').length, label: d.querySelector('svg').textContent, shadow: h.shadowRoot?.textContent.includes('송신소 안내 문서'),
      html: '<!doctype html>' + d.documentElement.getHTML({ serializableShadowRoots: true }) } })
  expect(got.sandbox).toBe('allow-same-origin allow-modals'); expect(got.shadow).toBe(true); expect(got.svgPages).toBe(1)
  const m = /「송신소 안내」 — (\d+)쪽에 이어 붙임/.exec(got.label); expect(m?.[1]).toBe('2')        // 칠판 1쪽 → 문서는 2쪽부터
  expect(await page.evaluate(() => window.__evil)).toBeUndefined()                               // 문서의 onerror는 앱 쪽에서 안 돎
  expect(logs.some(t => /sandboxed.*print|allow-modals/i.test(t))).toBe(false)                   // 인쇄 창이 막히지 않음
  // 쪽 수 — 인쇄 문서를 그대로 PDF로(같은 크롬 인쇄 엔진)
  const file = join(tmpdir(), `mb-print-${Date.now()}.html`); writeFileSync(file, got.html)
  const p2 = await (await browser.newContext()).newPage(); await p2.goto(pathToFileURL(file).href); await p2.evaluate(() => document.fonts.ready)
  const pdf = (await p2.pdf({ preferCSSPageSize: true })).toString('latin1'), pages = (pdf.match(/\/Type\s*\/Page(?!s)/g) || []).length
  const docPages = await p2.evaluate(() => Math.max(1, Math.ceil((document.querySelector('.mbdoc').getBoundingClientRect().height - 1) / (277 * 96 / 25.4))))
  expect(docPages).toBeGreaterThan(1)
  expect(pages).toBe(1 + docPages)
  await p2.close()

  const svg = await exportAs(page, 'SVG'), s = readFileSync(svg.path, 'utf8')
  expect(s).toContain('「송신소 안내」 — 문서는 칠판에서 따로 인쇄'); expect(s).not.toContain('크게 보기 · 인쇄'); expect(s).not.toContain('@@DOCP')
})
