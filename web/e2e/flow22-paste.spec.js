// 흐름 22 — 바깥에서 복사한 것 붙여넣기(2026-10-21 사용자: 클립보드 글을 바로 칠판에). 클립보드는 붙여넣기 신호를 직접 만들어 흉내
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage } from './helpers.js'

/** 칠판에 붙여넣기 신호 — data = { 'text/plain': …, 'text/html': … }, files = [{ name, type, b64 }] */
const pasteIn = (page, data, files = []) => page.evaluate(([d, fs]) => {
  const dt = new DataTransfer()
  for (const [k, v] of Object.entries(d)) dt.setData(k, v)
  for (const f of fs) dt.items.add(new File([Uint8Array.from(atob(f.b64), c => c.charCodeAt(0))], f.name, { type: f.type }))
  window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }))
}, [data, files])
const PNG_1PX = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
const added = async (page, n0) => (await liveDoc(page)).items.slice(n0)

test('글 붙여넣기 — 짧은 한 줄 = 글자(커서 자리), 여러 줄 마크다운 = 메모 + 진짜 표, 탭 표 = 표', async ({ page }) => {
  await openBoard(page, boardName('paste')); await setCam(page)
  const p = await toPage(page, 300, 200); await page.mouse.move(p.x, p.y)

  await pasteIn(page, { 'text/plain': '회의 10시' })
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  const [t] = (await liveDoc(page)).items
  expect(t.type).toBe('text'); expect(t.text).toBe('회의 10시')
  expect(Math.abs(t.pos[1] - 200)).toBeLessThan(30)                    // 커서 자리

  await pasteIn(page, { 'text/plain': '# 정리\n- 첫째\n- **둘째**\n\n| 가 | 나 |\n|---|---|\n| 1 | 2 |' })
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(3)
  const [memo, tab] = await added(page, 1)
  expect(memo.type).toBe('memo'); expect(memo.lines.map(l => [l.k, l.t])).toEqual([['h1', '정리'], ['ul', '첫째'], ['ul', '둘째']])
  expect(tab.type).toBe('table'); expect(tab.cells).toEqual([['가', '나'], ['1', '2']]); expect(tab.header).toBe(true)
  expect(memo.group_id).toBeTruthy(); expect(tab.group_id).toBe(memo.group_id)   // 한 묶음

  await pasteIn(page, { 'text/plain': '이름\t값\r\n가\t1\r\n' })
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(4)
  const [tsv] = await added(page, 3)
  expect(tsv.type).toBe('table'); expect(tsv.cells).toEqual([['이름', '값'], ['가', '1']])
  await page.keyboard.press('Control+z')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(3)    // Ctrl+Z 한 번에 사라짐
})

test('긁어 복사한 웹 글(html) = 꾸밈 살린 메모·색은 버림, 엑셀 표(html) = 표, VS Code = 코드 칸', async ({ page }) => {
  await openBoard(page, boardName('pastehtml')); await setCam(page)
  await pasteIn(page, { 'text/plain': '요약\n첫째\n둘째', 'text/html': '<h2>요약</h2><ul><li><p><strong style="color:#fff">첫째</strong></p></li><li>둘째</li></ul>' })
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  const [m] = (await liveDoc(page)).items
  expect(m.type).toBe('memo'); expect(m.lines.map(l => [l.k, l.t])).toEqual([['h2', '요약'], ['ul', '첫째'], ['ul', '둘째']])
  expect(m.lines[1].runs?.[0]?.[2] ?? null).toBe(null); expect(m.lines[1].runs?.[0]?.[3]).toBe(true)   // 굵게는 살리고 흰 글자색은 버림

  await pasteIn(page, { 'text/plain': '이름\t값\r\n가\t1\r\n', 'text/html': '<html><body><table><tr><td>이름</td><td>값</td></tr><tr><td>가</td><td>1</td></tr></table></body></html>' },
    [{ name: 'image.png', type: 'image/png', b64: PNG_1PX }])                // 엑셀은 표 그림도 같이 옴 → 글(표)이 먼저
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(2)
  const [xl] = await added(page, 1)
  expect(xl.type).toBe('table'); expect(xl.cells).toEqual([['이름', '값'], ['가', '1']])

  await pasteIn(page, { 'text/plain': 'def f():\n\treturn 1', 'text/html': '<div style="font-family: Consolas, monospace"><div><span>def f():</span></div><div><span>    return 1</span></div></div>' })
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(3)
  const [code] = await added(page, 2)
  expect(code.lines).toEqual([{ k: 'code', t: 'def f():' }, { k: 'code', t: '    return 1' }])
})

test('그림·파일 붙여넣기 = 이미지, 칠판에서 복사한 도형은 그림이 아니라 도형으로', async ({ page }) => {
  await openBoard(page, boardName('pastefile')); await setCam(page)
  await pasteIn(page, {}, [{ name: 'a.png', type: 'image/png', b64: PNG_1PX }])
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  expect((await liveDoc(page)).items[0].type).toBe('image')

  await pasteIn(page, { 'text/plain': '상자' }); await expect.poll(async () => (await liveDoc(page)).items.length).toBe(2)
  await page.keyboard.press('Control+c')                                    // 방금 붙인 글자(고른 채) 복사 — 클립보드엔 칠판이 그 그림을 넣음
  await pasteIn(page, {}, [{ name: 'image.png', type: 'image/png', b64: PNG_1PX }])
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(3)
  const last = (await liveDoc(page)).items[2]
  expect(last.type).toBe('text'); expect(last.text).toBe('상자')            // 다른 창에 안 다녀옴 = 칠판 도형

  await page.evaluate(() => window.dispatchEvent(new Event('blur')))       // 다른 창에 다녀옴 → 바깥에서 새로 복사한 것
  await pasteIn(page, { 'text/plain': '바깥 글' })
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(4)
  expect((await liveDoc(page)).items[3].text).toBe('바깥 글')

  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])   // 칠판이 클립보드에 그림을 넣을 수 있게(실제 크롬과 같게)
  await page.keyboard.press('Control+c')                                    // 다시 복사(창을 안 떠남) — 그래도 클립보드에 글이 있으면 바깥 것(칠판은 그림만 넣음)
  await expect.poll(() => page.evaluate(() => navigator.clipboard.read().then(c => c[0]?.types.join(',') || ''))).toContain('image/png')
  await pasteIn(page, { 'text/plain': '다른 앱 글' })
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(5)
  expect((await liveDoc(page)).items[4].text).toBe('다른 앱 글')
})
