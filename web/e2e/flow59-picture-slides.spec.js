// 흐름 59 — 📽 발표 자료 「그림 장」(2026-11-04 사용자 「작은 책」 ① — 글 장과 그림 장을 섞음).
// 장 계획 🖼 = 그 장을 그림 한 장으로(어림 크레딧이 따라 바뀜) → 만들기 = 그림 장은 프레임 비율이 그림 비율(3:2), 그림이 프레임을 꽉 채움 · 글 장은 16:9 그대로.
// 내보내기 PDF 용지 「프레임」 = 쪽마다 그 프레임 크기·여백 0. 진짜 KAIROS는 안 부름(그림 = 3×2 PNG).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc } from './helpers.js'

const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAIAAAASFvFNAAAAEElEQVR4nGO4VR4GQQxwFgBmUAnrgvT2ZQAAAABJRU5ErkJggg==', 'base64')   // 3×2 코랄
const PLAN = { title: '전파가 오는 길', slides: [{ title: '표지', point: '', source: 'ai', pic: false }, { title: '송신소', point: '', source: 'ai', pic: true },
  { title: '중계소', point: '', source: 'ai', pic: false }, { title: '정리', point: '', source: 'ai', pic: false }] }
const DECK = { title: '전파가 오는 길', sources: [], slides: [
  { title: '전파가 오는 길', layout: '표지', bullets: ['송신소에서 우리 집까지'], notes: '' },
  { title: '송신소', layout: '그림', bullets: ['전파를 사방으로 쏜다'], notes: '송신기가 영상을 전파에 싣습니다.', pic: { img: '/e2e-pic/1.png', w: 1536, h: 1024, model: 'img-m' } },
  { title: '중계소', layout: '그림', bullets: ['산을 넘겨 준다'], notes: '', pic: { img: '/e2e-pic/2.png', w: 1536, h: 1024, model: 'img-m' } },
  { title: '정리', layout: '마무리', bullets: ['안테나가 받는다'], notes: '' }] }

test('그림 장 — 🖼로 켜고 끄기(어림 크레딧) → 그림 장은 그림 비율 프레임을 꽉 채운 그림 · 글 장은 16:9 · Ctrl+Z 한 번', async ({ page }) => {
  const name = boardName('picslides'), seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'claude-sonnet-5-5' } } }))
  await page.route('**/e2e-pic/**', r => r.fulfill({ body: PNG, contentType: 'image/png' }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return r.fulfill({ json: b.slides?.step === 'plan' ? { kind: 'slides', plan: PLAN, estimate: { credits: [40, 60], seconds: [30, 60] }, model: 'claude-sonnet-5-5', elapsed: 4 }
      : { kind: 'slides', deck: DECK, model: 'claude-sonnet-5-5', elapsed: 30 } }) })
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.getByTestId('plus').click(); await page.getByRole('menuitemradio', { name: /발표 자료/ }).click()
  const box = page.getByPlaceholder('무엇을 발표할까요', { exact: false })
  await box.fill('전파가 집까지 오는 길'); await box.press('Enter')
  await page.locator('[data-q="그림 장"] [data-v="조금"]').click()
  await page.getByTestId('deep-plan-go').click()
  expect(seen[0].slides.brief['그림 장']).toBe('조금')                                           // 질문지 답 = 서버 계획 지시로
  const pics = page.getByTestId('slides-pic')
  await expect(pics).toHaveCount(3)                                                              // 표지는 🖼 없음
  await expect(pics.nth(0)).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('slides-build')).toContainText('약 40~60크레딧')
  await pics.nth(1).click()                                                                       // 중계소도 그림 장으로
  await expect(pics.nth(1)).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('slides-build')).toContainText('약 52~72크레딧')
  await expect(page.getByTestId('slides-plan')).toContainText('그림 장 2')
  await page.getByTestId('slides-build').click()
  await expect(page.getByTestId('slides-show')).toContainText('프레임 4장')
  expect(seen[1].slides.plan.slides.map(s => s.pic)).toEqual([false, true, true, false])          // 🖼 바꾼 것이 만들기로
  const its = (await liveDoc(page)).items, frames = its.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no)
  expect(frames.map(f => [f.rect[2], f.rect[3]])).toEqual([[1600, 900], [1600, 1067], [1600, 1067], [1600, 900]])
  const img = its.find(it => it.type === 'image' && it.slide_of === frames[1].uid)
  expect(img.slide_role).toBe('pic')
  expect([img.pos[0], img.pos[1], img.rect[2], img.rect[3]]).toEqual([frames[1].pos[0], frames[1].pos[1], 1600, 1067])   // 여백 없이 꽉
  expect(img.alt).toContain('전파를 사방으로 쏜다')                                             // 화면 글 = 대체 글
  expect(frames[1].slide.layout).toBe('그림'); expect(frames[1].slide.pic).toBeUndefined()        // 장 기록엔 그림 데이터를 안 둠(칠판 그림 칸에 있음)
  expect(its.filter(it => it.type === 'text' && it.slide_of === frames[1].uid)).toHaveLength(0)   // 그림 장엔 글 상자 없음
  expect(its.some(it => it.type === 'memo' && it.lines[0]?.t === '발표자 메모 · 2장')).toBe(true)
  await page.keyboard.press('Control+z')
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'frame').length).toBe(0)
})

test('그림을 못 받은 그림 장 = 글 장 · 말풍선 다시 짓기는 그 그림 그대로', async ({ page }) => {
  const name = boardName('picslides2')
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'm' } } }))
  await openBoard(page, name); await setCam(page)
  const data = PNG.toString('base64')
  const deck = { title: 't', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'] }, { title: '그림', layout: '그림', bullets: ['b'], pic: { data, w: 3, h: 2 } },
    { title: '깨진 그림', layout: '그림', bullets: ['c'], pic: { error: '못 받음' } }] }
  await page.evaluate(d => window.__mb.ed.slidesBoard(d), deck)
  let its = (await liveDoc(page)).items
  const fr = its.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no)
  expect(fr[2].slide.layout).toBe('마무리'); expect(fr[2].rect[3]).toBe(900)                      // 그림이 없으면 글 장(끝 장 = 마무리)
  expect(its.some(it => it.type === 'text' && it.slide_of === fr[2].uid && it.text.includes('c'))).toBe(true)
  await page.evaluate(([id]) => window.__mb.ed.setFields(id, { slide: { title: '그림', layout: '그림', bullets: ['b 고침'], notes: '새 메모' } }), [fr[1].uid])
  its = (await liveDoc(page)).items
  const pic = its.filter(it => it.slide_of === fr[1].uid && it.type === 'image')
  expect(pic).toHaveLength(1); expect(pic[0].data).toBe(data); expect(pic[0].alt).toContain('b 고침')   // 그림 그대로, 대체 글만 새로
})

test('PDF 용지 「프레임」 — 프레임만 내보낼 때만 보이고, 쪽 크기 = 프레임 비율(여백 0)', async ({ page }) => {
  const name = boardName('picslides3')
  await openBoard(page, name); await setCam(page)
  const deck = { title: 't', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'] }, { title: '그림', layout: '그림', bullets: ['b'], pic: { data: PNG.toString('base64'), w: 3, h: 2 } }] }
  await page.evaluate(d => window.__mb.ed.slidesBoard(d), deck)
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '내보내기' }).click()
  await page.getByRole('button', { name: /^프레임만/ }).click()
  await page.getByRole('button', { name: '프레임', exact: true }).first().click()   // 내보내기 창 용지 칸(위 막대 「프레임」 도구보다 앞)
  await expect(page.getByTestId('export-frame-page')).toBeVisible()
  const pages = await page.evaluate(() => window.__mb.ed.exportPages({ format: 'pdf', scope: 'frames', selection: false, page: 'frame', margin: 10, preview: true }))
  const r = pages.pages.map(p => +(p.pw / p.ph).toFixed(3))
  expect(r).toEqual([+(16 / 9).toFixed(3), +(1600 / 1067).toFixed(3)])                           // 쪽 = 그 프레임 비율
  await page.getByRole('button', { name: 'A4', exact: true }).click()
  await expect(page.getByTestId('export-frame-page')).toHaveCount(0)
  const a4 = await page.evaluate(() => window.__mb.ed.exportPages({ format: 'pdf', scope: 'frames', selection: false, page: 'A4', margin: 10, preview: true }))
  expect(a4.pages.every(p => Math.abs(p.pw / p.ph - 297 / 210) < 0.01)).toBe(true)                // A4 = 그대로(여백 + 용지)
})

test('작은 책 ② — 🖼 세 번째 = 글+그림 → 갈래가 있으면 가로 한 줄 + 그 장 아래 그림 판 · 발표 순서 = 장 → 그 판', async ({ page }) => {
  const name = boardName('picbranch'), seen = []
  const deck = { title: 't', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'], notes: '' }, { title: '송신소', layout: '글머리', bullets: ['쏜다'], notes: '메모', alt_pic: { img: '/e2e-pic/3.png', w: 1536, h: 1024 } },
    { title: '중계소', layout: '글머리', bullets: ['넘긴다'], notes: '' }, { title: '끝', layout: '마무리', bullets: ['b'], notes: '' }] }
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'm' } } }))
  await page.route('**/e2e-pic/**', r => r.fulfill({ body: PNG, contentType: 'image/png' }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return r.fulfill({ json: b.slides?.step === 'plan' ? { kind: 'slides', plan: PLAN, estimate: { credits: [40, 60], seconds: [30, 60] }, model: 'm', elapsed: 4 } : { kind: 'slides', deck, model: 'm', elapsed: 30 } }) })
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.getByTestId('plus').click(); await page.getByRole('menuitemradio', { name: /발표 자료/ }).click()
  const box = page.getByPlaceholder('무엇을 발표할까요', { exact: false }); await box.fill('전파'); await box.press('Enter')
  await page.getByTestId('deep-plan-go').click()
  const pics = page.getByTestId('slides-pic')
  await pics.nth(0).click()                                                                       // 송신소: 그림 → 글+그림
  await expect(pics.nth(0)).toHaveText('글+🖼'); await expect(pics.nth(0)).toHaveAttribute('data-pic', 'both')
  await expect(page.getByTestId('slides-build')).toContainText('약 40~60크레딧')                  // 그림 수는 그대로(하나)
  await pics.nth(0).click(); await expect(pics.nth(0)).toHaveAttribute('data-pic', 'false')       // 한 바퀴 = 글
  await expect(page.getByTestId('slides-build')).toContainText('약 28~48크레딧')
  await pics.nth(0).click(); await pics.nth(0).click()                                            // 다시 글+그림
  await page.getByTestId('slides-build').click()
  await expect(page.getByTestId('slides-show')).toContainText('프레임 5장')
  expect(seen[1].slides.plan.slides[1].pic).toBe('both')
  const its = (await liveDoc(page)).items, fr = its.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no)
  expect(fr.map(f => f.name)).toEqual(['표지', '송신소', '송신소 · 그림', '중계소', '끝'])          // 번호 = 발표 순서: 장 → 그 판
  const [main, br] = [fr[1], fr[2]]
  expect(br.slide_branch).toBe(main.uid); expect(br.pos[0]).toBe(main.pos[0]); expect(br.pos[1]).toBeGreaterThan(main.pos[1] + main.rect[3])   // 바로 아래
  expect(new Set([fr[0], fr[1], fr[3], fr[4]].map(f => f.pos[1])).size).toBe(1)                  // 장들은 가로 한 줄
  expect(br.rect[3]).toBe(1067); expect(its.some(it => it.type === 'image' && it.slide_of === br.uid)).toBe(true)
  expect(its.filter(it => it.type === 'memo' && it.lines[0]?.t?.startsWith('발표자 메모 · 2장'))).toHaveLength(1)   // 판에는 메모를 또 안 붙임
})

test('작은 책 ② — 만든 장 우클릭 「다른 판 더하기」 = 아래에 글 판·그림 판, 뒤 번호가 밀림 · Ctrl+Z 한 번', async ({ page }) => {
  const name = boardName('picbranch2'), seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'm' } } }))
  await page.route('**/e2e-pic/**', r => r.fulfill({ body: PNG, contentType: 'image/png' }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b); return r.fulfill({ json: { kind: 'slides', pic: { img: '/e2e-pic/9.png', w: 1536, h: 1024, model: 'img-m' }, model: 'img-m', elapsed: 9 } }) })
  await openBoard(page, name); await setCam(page)
  await page.evaluate(d => window.__mb.ed.slidesBoard(d), { title: '전파', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'] }, { title: '송신소', layout: '글머리', bullets: ['쏜다'], notes: '메모' }, { title: '끝', layout: '마무리', bullets: ['b'] }] })
  let fr = (await liveDoc(page)).items.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no)
  const [n0, mainId] = [fr[0].no, fr[1].uid]
  await page.evaluate(id => window.__mb.ed.slideBranch(id, 'pic'), mainId)
  expect(seen[0].slides).toMatchObject({ step: 'pic', deck: '전파', slide: { title: '송신소', bullets: ['쏜다'] } })
  await page.evaluate(id => window.__mb.ed.slideBranch(id, 'text'), mainId)
  const doc = await liveDoc(page)
  fr = doc.items.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no)
  expect(fr.map(f => [f.name, f.no - n0])).toEqual([['표지', 0], ['송신소', 1], ['송신소 · 그림', 2], ['송신소 · 글', 3], ['끝', 4]])   // 판들 = 그 장 바로 뒤, 끝 장은 밀림
  const pic = fr[2], txt = fr[3]
  expect(pic.rect[3]).toBe(1067); expect(doc.items.some(it => it.type === 'image' && it.slide_of === pic.uid && it.slide_role === 'pic')).toBe(true)
  expect(txt.pos[1]).toBeGreaterThan(pic.pos[1] + pic.rect[3]); expect(txt.slide.layout).toBe('글머리')   // 판들은 차례로 아래로
  await page.keyboard.press('Control+z')
  fr = (await liveDoc(page)).items.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no)
  expect(fr.map(f => [f.name, f.no - n0])).toEqual([['표지', 0], ['송신소', 1], ['송신소 · 그림', 2], ['끝', 3]])   // 한 번에 되돌림(번호도)
})
