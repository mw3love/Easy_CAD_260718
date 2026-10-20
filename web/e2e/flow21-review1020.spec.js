// 흐름 21 — 10-20 사용자 검토: 번호 = 남은 가장 큰 수 + 1 · 미니맵 % = 100% · Alt+Z 고른 것만 · 펜은 끌기 없음 ·
// 대화창 「다시 ▾」 셋 · 새 대화·지난 대화 · 🔑 내 키(머리말로만). 진짜 KAIROS는 안 부름(flow3처럼 가짜 답).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, toPage, clickScene, liveDoc } from './helpers.js'

const btn = (page, name) => page.getByRole('button', { name, exact: true })

async function fakeKairos(page, seen) {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: { gpt: [{ id: 'fake-model', price: '' }] } } }))
  await page.route('**/api/chat', async r => { seen.push({ body: r.request().postDataJSON(), headers: r.request().headers() })
    await r.fulfill({ json: { content: `답 ${seen.length}`, model: 'fake-model', elapsed: 0.1 } }) })
}
async function ask(page, q) {
  const box = page.getByPlaceholder('물어보세요', { exact: false })
  await box.click(); await page.keyboard.type(q); await page.keyboard.press('Enter')
}

test('번호 — 3을 지우면 다음은 다시 3, 중간 2를 지우면 4', async ({ page }) => {
  await openBoard(page, boardName('badge')); await setCam(page)
  await page.keyboard.press('7')
  for (const x of [0, 80, 160]) await clickScene(page, x, 0)
  const nums = async () => (await liveDoc(page)).items.filter(it => it.type === 'badge').map(it => it.number).sort((a, b) => a - b)
  expect(await nums()).toEqual([1, 2, 3])
  await page.keyboard.press('Escape')
  await clickScene(page, 160, 0); await page.keyboard.press('Delete')          // 3 지움
  await page.keyboard.press('7'); await clickScene(page, 240, 0)
  expect(await nums()).toEqual([1, 2, 3])
  await page.keyboard.press('Escape')
  await clickScene(page, 80, 0); await page.keyboard.press('Delete')           // 가운데 2 지움
  await page.keyboard.press('7'); await clickScene(page, 320, 0)
  expect(await nums()).toEqual([1, 3, 4])
})

test('미니맵 % = 100%(화면 가운데 기준) · Alt+Z = 메모 하나 골라도 고른 것만 맞춤', async ({ page }) => {
  await openBoard(page, boardName('mmzoom')); await setCam(page, { x: 400, y: 200, z: 0.5 })
  await page.getByRole('button', { name: '50%' }).click()
  expect((await page.evaluate(() => window.__mb.getCam())).z).toBe(1)
  await setCam(page)
  await btn(page, '메모').click()                                           // 만들면 고른 채
  await setCam(page, { x: -6000, y: -6000, z: 1 })
  await page.keyboard.press('Alt+z')
  await expect(page.getByTestId('memo-editor')).toHaveCount(0)              // 글로 안 들어감
  const m = (await liveDoc(page)).items.find(it => it.type === 'memo'), p = await toPage(page, m.pos[0], m.pos[1])
  const b = await page.getByTestId('board').boundingBox()
  expect(p.x).toBeGreaterThan(b.x); expect(p.x).toBeLessThan(b.x + b.width) // 화면 안으로
})

test('펜 버튼은 끌어도 아무것도 안 놓임', async ({ page }) => {
  await openBoard(page, boardName('pendrag')); await setCam(page)
  const b = await btn(page, '펜').boundingBox(), q = await toPage(page, 200, 200)
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await page.mouse.down()
  await page.mouse.move(q.x, q.y, { steps: 10 }); await page.mouse.up()
  expect((await liveDoc(page)).items).toHaveLength(0)
  await expect(btn(page, '펜')).not.toHaveAttribute('aria-pressed', 'true')   // 도구도 안 바뀜
})

test('대화창 — 「다시 ▾」 없음 · 새 대화 = 앞 대화 안 실림 · 지난 대화 다시 열기', async ({ page }) => {
  const seen = []
  await fakeKairos(page, seen)
  await openBoard(page, boardName('threads'), { chat: true })
  await ask(page, '첫 대화 질문'); await expect(page.getByText('답 1')).toBeVisible()
  await expect(page.getByTestId('answer-kind')).toBeVisible()             // 어느 길로 갔는지는 보임
  await expect(page.getByTestId('redo-menu')).toHaveCount(0)              // 다시 묻는 메뉴는 없음(2026-10-20 사용자)
  await page.getByRole('button', { name: /새 대화/ }).click()
  await expect(page.getByText('첫 대화 질문')).toHaveCount(0)
  await ask(page, '둘째 대화 질문'); await expect(page.getByText('답 2')).toBeVisible()
  expect(seen[1].body.messages.map(m => m.content)).toEqual(['둘째 대화 질문'])   // 앞 대화가 안 실림
  await page.getByRole('button', { name: /지난 대화 1/ }).click()
  await page.getByTestId('past-list').getByRole('button', { name: /첫 대화 질문/ }).click()
  await expect(page.getByText('첫 대화 질문')).toBeVisible()
  await expect(page.getByRole('button', { name: /지난 대화 1/ })).toBeVisible()  // 둘째 대화는 목록으로
  await page.reload()                                                         // 서버에 남음
  await expect(page.getByText('첫 대화 질문')).toBeVisible()
  await page.getByRole('button', { name: /지난 대화 1/ }).click()
  await expect(page.getByTestId('past-list')).toContainText('둘째 대화 질문')
})

test('🔑 내 키 — 넣으면 물을 때 머리말로만, 지우면 서버 키', async ({ page }) => {
  const seen = []
  await fakeKairos(page, seen)
  await openBoard(page, boardName('mykey'), { chat: true })
  await page.getByRole('button', { name: /서버 키/ }).click()
  const box = page.getByTestId('key-box')
  await box.locator('input').fill('한글키')
  await expect(box.getByRole('button', { name: '저장' })).toBeDisabled()     // 키 모양이 아니면 못 넣음
  await box.locator('input').fill('my-own-key-1234'); await box.getByRole('button', { name: '저장' }).click()
  await expect(page.getByRole('button', { name: /내 키/ })).toBeVisible()
  await ask(page, '키 시험'); await expect(page.getByText('답 1')).toBeVisible()
  expect(seen[0].headers['x-kairos-key']).toBe('my-own-key-1234')
  expect(JSON.stringify(seen[0].body)).not.toContain('my-own-key-1234')
  await page.getByRole('button', { name: /내 키/ }).click(); await page.getByTestId('key-box').getByRole('button', { name: '지우기' }).click()
  await ask(page, '다시'); await expect(page.getByText('답 2')).toBeVisible()
  expect(seen[1].headers['x-kairos-key']).toBeUndefined()
})

test('보이는 것 정리정돈 = 칠판 위 「🧩 정리정돈 중 · 실제 모델」 알약, 끝나면 사라짐', async ({ page }) => {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: { gpt: [{ id: 'fake-model', price: '' }] }, jobs: { tidy: 'claude-sonnet-5-5' } } }))
  await page.route('**/api/chat', async r => { await new Promise(s => setTimeout(s, 1500)); await r.fulfill({ status: 502, json: { error: '시험 — 일부러 실패' } }) })
  await openBoard(page, boardName('tidybusy')); await setCam(page)
  for (const t of ['하나', '둘']) { await btn(page, '메모').click(); await page.keyboard.type(t); await clickScene(page, 900, 600) }
  const b = await page.getByTestId('board').boundingBox()
  await page.mouse.click(b.x + 1000, b.y + 700, { button: 'right' })
  await page.getByRole('button', { name: /보이는 것 정리정돈하기/ }).click()
  await expect(page.getByTestId('ai-busy')).toContainText('정리정돈 중 · claude-sonnet-5-5')
  await expect(page.getByTestId('chat-busy')).toContainText('정리정돈 중 · claude-sonnet-5-5')   // 고른 대화 모델(fake-model)이 아니라
  await expect(page.getByTestId('ai-busy')).toHaveCount(0)
  await expect(page.getByText('시험 — 일부러 실패')).toBeVisible()
})

test('다각형 Shift = 마지막 점에서 45° 단위', async ({ page }) => {
  await openBoard(page, boardName('polyshift')); await setCam(page)
  await page.keyboard.press('5')
  await clickScene(page, 0, 0)
  await page.keyboard.down('Shift'); await clickScene(page, 100, 12); await page.keyboard.up('Shift')
  await clickScene(page, 60, 100); await page.keyboard.press('Enter')
  const pg = (await liveDoc(page)).items.find(it => it.type === 'polygon')
  expect(Math.abs(pg.pts[1][1] - pg.pts[0][1])).toBeLessThan(0.5)            // 수평으로 붙음
})

test('글자 끌어 놓기 = 빈 글 상자(「글」 안 남음), 안 쓰고 나가면 지워짐', async ({ page }) => {
  await openBoard(page, boardName('textdrag')); await setCam(page)
  const b = await btn(page, '글자').boundingBox(), q = await toPage(page, 200, 200)
  await page.mouse.move(b.x + b.width / 2, b.y + b.height / 2); await page.mouse.down()
  await page.mouse.move(q.x, q.y, { steps: 10 }); await page.mouse.up()
  await clickScene(page, 900, 600)
  expect((await liveDoc(page)).items.filter(it => it.type === 'text')).toHaveLength(0)
})

test('정리 문서 답의 「🎨 그림으로도」 = 같은 자료로 그림 후보(kind image + infographic)', async ({ page }) => {
  const seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: {} } }))
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b)
    await r.fulfill({ json: b.kind === 'image' ? { kind: 'image', content: '그림 후보 1장', images: [], model: 'gpt-image-2.5-flare', elapsed: 0.1 }
      : { kind: 'report', content: '정리 문서 「점검」', title: '점검', html: '<h1>점검</h1>', model: 'claude-opus-5-5', elapsed: 0.1 } }) })
  await openBoard(page, boardName('infog'), { chat: true })
  await ask(page, '정리 문서로 만들어 줘'); await expect(page.getByTestId('answer-doc')).toBeVisible()
  await page.getByRole('button', { name: '🎨 그림으로도' }).click()
  await expect(page.getByText('그림 후보 1장')).toBeVisible()
  expect(seen[1]).toMatchObject({ kind: 'image', infographic: true })
  expect(seen[1].messages.at(-1).content).toBe('「점검」 인포그래픽 그림')
})

test('그림 후보 둘을 차례로 누르면 둘째는 첫째와 안 겹치는 빈자리에(2026-10-20 사용자)', async ({ page }) => {
  const name = boardName('imgspot')
  const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII=', 'base64')
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => r.fulfill({ json: { kind: 'image', content: '그림 후보 2장', model: 'img-m', elapsed: 1,
    images: [{ url: `/api/img/${name}/1_aaaaaa.png` }, { url: `/api/img/${name}/2_bbbbbb.png` }] } }))
  await page.route('**/api/img/**', r => r.fulfill({ body: PNG, contentType: 'image/png' }))
  await openBoard(page, name, { chat: true }); await setCam(page, { x: 400, y: 200, z: 0.02 })   // 4×3 그림이 화면에서 크게 보이게 멀리서
  await ask(page, '송신탑 그려줘')
  await page.getByTestId('image-pick').nth(0).click(); await expect(page.getByTestId('image-pick').nth(0)).toContainText('칠판에 붙임 ✓')
  await page.getByTestId('image-pick').nth(1).click(); await expect(page.getByTestId('image-pick').nth(1)).toContainText('칠판에 붙임 ✓')
  const ims = (await liveDoc(page)).items.filter(it => it.type === 'image').map(it => ({ x: it.pos[0], y: it.pos[1], w: it.rect[2], h: it.rect[3] }))
  expect(ims).toHaveLength(2)
  const [a, b] = ims
  expect(a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h).toBe(false)
})

test('그림 뒤 고칠 말 = 고칠 그림 주소를 같이(붙인 것 → 둘째, 「첫 번째」라 하면 첫째)', async ({ page }) => {
  const name = boardName('imgedit'), seen = []
  const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII=', 'base64')
  const imgs = [{ url: `/api/img/${name}/1_aaaaaa.png` }, { url: `/api/img/${name}/2_bbbbbb.png` }]
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { seen.push(r.request().postDataJSON()); return r.fulfill({ json: { kind: 'image', content: '그림 후보', model: 'img-m', elapsed: 1, images: imgs } }) })
  await page.route('**/api/img/**', r => r.fulfill({ body: PNG, contentType: 'image/png' }))
  await openBoard(page, name, { chat: true })
  await ask(page, '송신탑 그려줘'); await expect(page.getByTestId('image-pick')).toHaveCount(2)
  expect(seen[0].base_image).toBeUndefined()
  await page.getByTestId('image-pick').nth(1).click(); await expect(page.getByTestId('image-pick').nth(1)).toContainText('칠판에 붙임 ✓')
  await ask(page, '날짜도 넣어 줘'); await expect(page.getByTestId('image-pick')).toHaveCount(4)
  expect(seen[1].base_image).toBe(imgs[1].url)                               // 붙인 그림
  await ask(page, '첫 번째 그림에 제목 넣어 줘'); await expect(page.getByTestId('image-pick')).toHaveCount(6)
  expect(seen[2].base_image).toBe(imgs[0].url)                               // 말로 고름
})
