// 흐름 61 — 칠판 그림 따로 받기(2026-11-05 사용자: 노트북에서 큰 칠판이 다 뜨기까지 5초 — 칠판 파일의 75%가 그림).
// 웹은 칠판을 그림 데이터 없이(주소만) 받아 도형부터 그리고, 그림은 따로 받아 원래 데이터로 채운다(`docblobs.py`·`blobs.js`).
// 채운 것이 「고친 것」으로 저장되지 않아야 하고, 채우기 전에 그림을 옮겨도 서버의 그림 데이터가 지켜져야 한다.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, dragScene, liveDoc, waitSaved, savedDoc } from './helpers.js'

// 무늬 PNG(크롬이 만든 base64 = 다시 만들어도 같은 글) — 4KB가 넘어야 따로 보냄
const makePng = page => page.evaluate(() => { const c = document.createElement('canvas'); c.width = c.height = 96; const g = c.getContext('2d'); let r = 7
  for (let i = 0; i < 96 * 96; i++) { r = (r * 1103515245 + 12345) % 2147483648; g.fillStyle = `#${(r % 16777216).toString(16).padStart(6, '0')}`; g.fillRect(i % 96, (i / 96) | 0, 1, 1) }
  return c.toDataURL('image/png').split(',')[1] })
const doc = data => ({ format: 'easycad-doc', version: 1, items: [{ type: 'image', pos: [0, 0], rect: [0, 0, 200, 200], data, uid: 'pic1' }, { type: 'rect', pos: [300, 0], rect: [0, 0, 100, 60], uid: 'box1' }] })

test('그림 든 칠판 — 그림 없이 받아 그리고, 따로 받아 채움(저장할 것 없음)', async ({ page }) => {
  const name = boardName('lite')
  await page.goto('about:blank'); const png = await makePng(page)
  expect((await page.request.put(`/api/doc/${name}`, { data: doc(png) })).ok()).toBe(true)
  const got = page.waitForResponse(r => r.url().includes(`/api/doc/${name}`))
  await openBoard(page, name)
  const sent = await (await got).json()
  expect(sent.items[0].data).toBe('')                                                      // 칠판 파일엔 그림 데이터 없음
  expect(sent.items[0]._ref).toMatch(/^\/api\/blob\/[0-9a-f]{32}\.png$/)
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.uid === 'pic1').data).toBe(png)   // 받아서 원래 데이터로
  expect(await page.evaluate(() => window.__mb.unsaved())).toBe(false)                    // 채운 것 = 고친 것이 아님
  expect([sent.items[0]._ref, `data:image/png;base64,${png}`]).toContain(await page.locator('[data-testid=board] image').first().getAttribute('href'))   // 화면 = 주소(채워도 일부러 다시 안 그림) 또는 다른 일로 다시 그렸으면 데이터
})

test('채우기 전에 그림을 옮겨도 서버의 그림 데이터는 그대로', async ({ page }) => {
  const name = boardName('litemove')
  await page.goto('about:blank'); const png = await makePng(page)
  await page.request.put(`/api/doc/${name}`, { data: doc(png) })
  let release; const gate = new Promise(r => { release = r })
  await page.route('**/api/blob/**', async route => { await gate; await route.continue() })   // 그림 받기를 붙잡아 둠
  await openBoard(page, name); await setCam(page)
  await dragScene(page, { x: 100, y: 100 }, { x: 160, y: 140 })                             // 주소로 그려진 그림을 옮김
  await waitSaved(page)
  const s = savedDoc(name).items.find(it => it.uid === 'pic1'), moved = (await liveDoc(page)).items.find(it => it.uid === 'pic1').pos   // 옮긴 자리(옆 상자 정렬선에 붙을 수 있음)
  expect(moved).not.toEqual([0, 0]); expect(s.pos).toEqual(moved); expect(s.data).toBe(png); expect('_ref' in s).toBe(false)
  release()
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.uid === 'pic1').data).toBe(png)
  await waitSaved(page)
  expect(savedDoc(name).items.find(it => it.uid === 'pic1')).toMatchObject({ pos: moved, data: png })
})
