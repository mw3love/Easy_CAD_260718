// 흐름 14 — 그림(§8 항목61 ③-4): 「그려줘」 → 🎨 후보 2장(대화창에만) → 누르면 그 한 장 + 밑에 요청 글(한 묶음) / 끌어 놓으면 그 자리 / 웹 주소 끌어 놓기 = 웹 카드.
// KAIROS는 가짜(/api/chat·/api/img·/api/link) — 서버 쪽은 tests/test_part57, 진짜 그림은 손 확인.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage } from './helpers.js'

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
  await page.getByTestId('image-pick').first().click()
  await expect(page.getByTestId('image-pick').first()).toContainText('칠판에 붙임 ✓')
  let d = await liveDoc(page)
  const img = d.items.find(it => it.type === 'image'), cap = d.items.find(it => it.type === 'text')
  expect(img.data.length).toBeGreaterThan(20)
  expect(cap.text).toBe('산 위 송신탑 그려줘'); expect(cap.group_id).toBeTruthy(); expect(cap.group_id).toBe(img.group_id)
  expect(cap.pos[1]).toBeGreaterThan(img.pos[1] + img.rect[3] - 1)                // 그림 밑

  await dropUri(page, `http://127.0.0.1:5291/api/img/${name}/2_bbbbbb.png`, '산 위 송신탑 그려줘', 700, 100)
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'image').length).toBe(2)
  d = await liveDoc(page)
  const second = d.items.filter(it => it.type === 'image')[1]
  expect(Math.abs(second.pos[0] + second.rect[2] / 2 - 700)).toBeLessThan(2)    // 놓은 자리 가운데

  const url0 = page.url()
  await dropUri(page, 'https://example.com/', '', -100, 300)
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'web').length).toBe(1)
  expect(page.url()).toBe(url0)                                                   // 칠판을 안 떠남
})
