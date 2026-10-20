// 흐름 14 — 그림(§8 항목61 ③-4): 「그려줘」 → 🎨 후보 2장(대화창에만) → 누르면 그 한 장 + 밑에 요청 글(따로 — 2026-10-20) / 끌어 놓으면 그 자리 / 웹 주소 끌어 놓기 = 웹 카드.
// KAIROS는 가짜(/api/chat·/api/img·/api/link) — 서버 쪽은 tests/test_part57, 진짜 그림은 손 확인.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage, waitSaved, pickShape, dragScene, clickScene, pinCandidate } from './helpers.js'

const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII=', 'base64')

async function dropUri(page, uri, caption, x, y) {
  const p = await toPage(page, x, y)
  await page.evaluate(([u, c, cx, cy]) => {
    const dt = new DataTransfer(); dt.setData('text/uri-list', u); if (c) dt.setData('text/x-mb-caption', c)
    document.querySelector('[data-testid=board]').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, clientX: cx, clientY: cy, bubbles: true, cancelable: true }))
  }, [uri, caption, p.x, p.y])
}

test('그려줘 → 🎨 후보 둘 → 누르면 그림 + 요청 글 묶음 → 다른 후보는 끌어 놓기 → 웹 주소 끌어 놓기 = 웹 카드', async ({ page }) => {
  const name = boardName('image')
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => r.fulfill({ json: { kind: 'image', content: '그림 후보 2장 — 마음에 드는 것을 눌러 칠판에 붙여요', model: 'img-m', elapsed: 4.1, credits: 68.2,
    images: [{ url: `/api/img/${name}/1_aaaaaa.png` }, { url: `/api/img/${name}/2_bbbbbb.png` }] } }))
  await page.route('**/api/img/**', r => r.fulfill({ body: PNG, contentType: 'image/png' }))
  await page.route('**/api/link**', r => r.fulfill({ json: { url: 'https://example.com/', title: '예시 페이지', frameable: false } }))
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.getByPlaceholder('물어보세요', { exact: false }).click()
  await page.keyboard.type('산 위 송신탑 그려줘'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-kind')).toHaveText('🎨 그림')
  await expect(page.getByTestId('image-pick')).toHaveCount(2)
  await expect(page.getByRole('button', { name: '칠판에 붙이기' })).toHaveCount(0)   // 그림 답은 고르는 것이 곧 붙이기
  await pinCandidate(page, 0)
  let d = await liveDoc(page)
  const img = d.items.find(it => it.type === 'image')
  expect(img.data.length).toBeGreaterThan(20)
  expect(img.alt).toBe('산 위 송신탑 그려줘'); expect(d.items.filter(it => it.type === 'text')).toHaveLength(0)   // 칠판엔 그림만, 요청은 보이지 않는 설명(2026-10-20 사용자)
  await expect(page.getByTestId('image-alt')).toHaveText('산 위 송신탑 그려줘')   // 고르면 속성 카드에 설명
  await page.keyboard.press('Control+f'); await page.keyboard.type('송신탑')   // 찾기가 설명으로 그림을 찾음
  await expect(page.getByTestId('find-bar').getByTestId('find-row').first()).toContainText('송신탑'); await page.keyboard.press('Escape')

  await dropUri(page, `http://127.0.0.1:5291/api/img/${name}/2_bbbbbb.png`, '산 위 송신탑 그려줘', 700, 100)
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'image').length).toBe(2)
  d = await liveDoc(page)
  const second = d.items.filter(it => it.type === 'image')[1]
  expect(Math.abs(second.pos[0] + second.rect[2] / 2 - 700)).toBeLessThan(2)    // 놓은 자리 가운데

  const url0 = page.url()
  await dropUri(page, 'https://example.com/', '', -100, 300)
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'web').length).toBe(1)
  expect(page.url()).toBe(url0)                                                   // 칠판을 안 떠남
  await waitSaved(page)                                                           // 웹이 만든 문서 = 데스크톱 왕복 시험 재료(tools/collect_web_fixture.py)
})

// 2026-10-20 사용자: 후보를 끌어도 안 옮겨짐 → 끄는 그림 크기가 붙는 크기와 다름 → 정렬선이 없음. 그래서 답 메모처럼 칠판이 직접 끔(실제 크기 그림 + 정렬선)
// · 툴팁 위로 지나가면 크게 보기가 깜빡임(title 없앰 — 올려 두면 크게 보기는 그 뒤 없앰, flow21)
test('그림 후보 끌기 = 실제 크기로 따라오고 정렬선 · 놓은 자리에 붙음 · 툴팁 없음', async ({ page }) => {
  const name = boardName('imgdrag')
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => r.fulfill({ json: { kind: 'image', content: '후보', model: 'img-m', images: [{ url: `/api/img/${name}/1_aaaaaa.png` }, { url: `/api/img/${name}/2_bbbbbb.png` }] } }))
  await page.route('**/api/img/**', r => r.fulfill({ body: PNG, contentType: 'image/png' }))
  await openBoard(page, name, { chat: true }); await setCam(page, { x: 400, y: 200, z: 0.3 })
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 400, y: 300 }); await clickScene(page, 1500, 1200)   // 정렬 기준 네모(가운데 x 200)
  await page.getByPlaceholder('물어보세요', { exact: false }).click()
  await page.keyboard.type('송신탑 그려줘'); await page.keyboard.press('Enter')
  const pick = page.getByTestId('image-pick').nth(1)
  await expect(pick).not.toHaveAttribute('title', /.*/)
  await pick.hover()
  const b = await pick.boundingBox(), to = await toPage(page, 200, 700)   // 칠판 x 200 = 네모 가운데 세로선
  await page.mouse.down(); await page.mouse.move(b.x + b.width / 2 - 20, b.y + b.height / 2, { steps: 3 })
  await page.mouse.move(to.x + 3, to.y, { steps: 10 }); await page.mouse.move(to.x + 2, to.y, { steps: 2 })
  await expect(page.locator('[data-testid=board] line[stroke="rgb(230,60,160)"]').first()).toBeAttached()   // 정렬선
  await page.mouse.up()
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'image').length).toBe(1)
  const d = await liveDoc(page), img = d.items.find(it => it.type === 'image')
  expect(Math.max(img.rect[2], img.rect[3])).toBeCloseTo(680, 0)                   // 배율 0.3이어도 긴 변 680
  expect(img.pos[0] + img.rect[2] / 2).toBeCloseTo(200, 0)                          // 정렬선에 맞춰 가운데가 네모 가운데에
  expect(img.alt).toBe('송신탑 그려줘')
  await expect(pick).toHaveAttribute('data-picked', '1')
  await waitSaved(page)
})
