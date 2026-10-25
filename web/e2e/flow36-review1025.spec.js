// 흐름 36 — 10-25 사용자 검토: 우클릭 메뉴 단축키(Ctrl+X·Ctrl+Alt+G·Ctrl+P) · 빈 곳 우클릭 = 붙일 것 없으면 메뉴 없음 ·
// 「+」 메뉴 이름(이미지·아이콘(SVG)·인터랙티브 HTML·Deep Mode, 정리 문서 뺌) · 대화창 스켈레톤 · 그림 「도면으로 베끼기」(구역 스켈레톤 → 그림 옆 묶음).
// KAIROS·서버 일감은 가짜(/api/chat·/api/trace) — 진짜 베끼기 엔진은 tests/test_part75.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage, clickScene, pickShape, dragScene } from './helpers.js'

const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII='
const menuBtns = page => page.locator('div[style*="z-index: 30"] > div > button').allInnerTexts()
const dropPng = (page, p) => page.evaluate(([b64, x, y]) => {
  const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0)), dt = new DataTransfer(); dt.items.add(new File([bin], '도면.png', { type: 'image/png' }))
  document.elementFromPoint(x, y).dispatchEvent(new DragEvent('drop', { dataTransfer: dt, clientX: x, clientY: y, bubbles: true, cancelable: true }))
}, [PNG, p.x, p.y])

test('우클릭 메뉴 단축키 · Ctrl+Alt+G = 프레임으로 감싸기 · 빈 곳 우클릭(붙일 것 없음) = 메뉴 없음', async ({ page }) => {
  await openBoard(page, boardName('menu1025')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 100, y: 100 }, { x: 250, y: 200 }); await page.keyboard.press('Escape')
  const p = await toPage(page, 175, 150); await page.mouse.click(p.x, p.y, { button: 'right' })
  const names = await menuBtns(page)
  expect(names.find(n => n.startsWith('잘라내기'))).toContain('Ctrl+X')
  expect(names.find(n => n.startsWith('프레임으로 감싸기'))).toContain('Ctrl+Alt+G')
  expect(names.find(n => n.startsWith('내보내기'))).toContain('Ctrl+P')
  await page.keyboard.press('Escape')
  await page.keyboard.press('Control+Alt+g')
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'frame').length).toBe(1)
  await page.keyboard.press('Escape')
  const q = await toPage(page, 700, 500); await page.mouse.click(q.x, q.y, { button: 'right' })
  expect(await menuBtns(page)).toEqual([])                                                  // 빈 곳 + 붙일 것 없음 = 메뉴 없음(2026-10-25 사용자)
  await clickScene(page, 175, 150); await page.keyboard.press('Control+c')
  await page.mouse.click(q.x, q.y, { button: 'right' })
  expect(await menuBtns(page)).toEqual([expect.stringContaining('붙여넣기')])                 // 붙일 것이 있으면 그것만
})

test('「+」 메뉴 이름 = 이미지·아이콘(SVG)·인터랙티브 HTML·Deep Mode(정리 문서 없음) · 기다리는 동안 대화창 스켈레톤', async ({ page }) => {
  const name = boardName('plus1025')
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { image: 'img-m', live: 'sol', deep: 'opus' } } }))
  await page.route('**/api/chat', async r => { await new Promise(s => setTimeout(s, 1500))
    await r.fulfill({ json: { kind: 'image', content: '그림 후보 2장', model: 'img-m', elapsed: 1.5, images: [{ url: `/api/img/${name}/1_aaaaaa.png` }, { url: `/api/img/${name}/2_bbbbbb.png` }] } }) })
  await page.route('**/api/img/**', r => r.fulfill({ body: Buffer.from(PNG, 'base64'), contentType: 'image/png' }))
  await openBoard(page, name, { chat: true })
  await page.getByTestId('plus').click()
  const items = await page.getByRole('menuitemradio').allInnerTexts()
  expect(items.map(t => t.split('\n')[0])).toEqual(['🎨 이미지 만들기', '✏️ 아이콘 만들기 (SVG)', '▶ 인터랙티브 HTML', '📰 Deep Mode'])
  await page.getByRole('menuitemradio', { name: /이미지 만들기/ }).click()
  await expect(page.getByTestId('tool-chip')).toHaveText('🎨 이미지 만들기 ✕')
  await page.getByPlaceholder('무엇을 그릴까요', { exact: false }).click()
  await page.keyboard.type('송신탑'); await page.keyboard.press('Enter')
  await expect(page.locator('[data-testid="chat-skeleton"][data-kind="image"]')).toBeVisible()   // 후보 두 칸 자리
  await expect(page.getByTestId('image-pick')).toHaveCount(2)
  await expect(page.getByTestId('chat-skeleton')).toHaveCount(0)
})

test('그림 우클릭 「도면으로 베끼기」 → 그림 옆 구역 스켈레톤(끝난 구역부터) → 같은 자리에 도형 묶음', async ({ page }) => {
  const name = boardName('trace')
  let polls = 0, sent = null
  await page.route('**/api/trace/**', async r => {
    if (r.request().method() === 'POST') { sent = r.request().postDataJSON(); return r.fulfill({ json: { job: 'abcdef123456' } }) }
    polls++
    if (polls < 3) return r.fulfill({ json: { status: 'run', msg: `구역 ${polls * 2}/6곳 끝`, done: polls * 2, total: 6 } })
    return r.fulfill({ json: { status: 'done', result: { elapsed: 48, credits: 150.9, w: 400, h: 300, items: [
      { type: 'rect', pos: [0, 0], scale: 1, rotation: 0, z: 0, origin: [0, 0], rect: [20, 20, 120, 60], pen: '#ff000000', width: 2, fill: null, label: { text: 'TX-A', color: '#ff000000', font: 13, bg: null } },
      { type: 'text', pos: [200, 40], scale: 1, rotation: 0, z: 1, origin: [0, 0], text: '연주소', color: '#ff000000', font: 13, bg: null },
      { type: 'sarrow', pos: [0, 0], scale: 1, rotation: 0, z: 2, origin: [0, 0], pts: [[140, 50], [260, 50]], color: '#ff000000', width: 2, head: true, auto_route: false, routing: 'straight', curve_r: 0, bind1: 0, bind1_pt: [140, 50] }] } } })
  })
  await openBoard(page, name); await setCam(page)
  await dropPng(page, await toPage(page, 200, 200))
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'image').length).toBe(1)
  const img = (await liveDoc(page)).items.find(it => it.type === 'image')
  const c = await toPage(page, img.pos[0] + img.rect[2] / 2, img.pos[1] + img.rect[3] / 2)
  await page.keyboard.press('Escape'); await page.mouse.click(c.x, c.y, { button: 'right' })
  await page.getByRole('button', { name: /도면으로 베끼기/ }).click()
  const sk = page.locator('[data-testid="board-skeleton"][data-kind="trace"]')
  await expect(sk).toBeVisible()
  await expect(sk).toContainText('2/6')                                                      // 서버 진행이 그대로(끝난 구역 수)
  await expect(sk).toBeHidden({ timeout: 10_000 })
  expect(sent.data).toBe(img.data); expect(sent.width).toBeGreaterThan(0)                    // 칠판 그림 그대로 + 놓일 폭
  const d = await liveDoc(page), its = d.items.filter(it => it.type !== 'image')
  expect(its.map(it => it.type).sort()).toEqual(['rect', 'sarrow', 'text'])
  expect(its[0].group_id).toBeTruthy(); expect(its.every(it => it.group_id === its[0].group_id)).toBe(true)   // 묶음 하나
  const rect = its.find(it => it.type === 'rect'), arrow = its.find(it => it.type === 'sarrow')
  expect(arrow.bind1).toBe(d.items.indexOf(rect))                                            // 연결 그대로
  expect(rect.pos[0] + rect.rect[0]).toBeGreaterThan(img.pos[0] + img.rect[2])               // 그림 오른쪽 옆
  await expect(page.getByTestId('status-toast')).toContainText('도면으로 베낌 — 도형 3개 묶음 · 48초 · 150.9크레딧')   // 저장 알림 뒤에도 보임(sayLater)
})
