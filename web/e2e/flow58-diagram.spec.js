// 흐름 58 — 🔷 도형 그리기(2026-11-03 사용자 결정: 「계통도 그려 줘」 = 묻지 않고 고칠 수 있는 상자 + 붙은 화살표, 답 밑 「이미지로 다시」·「+」에도).
// 서버 자리는 진짜 KAIROS 설계서를 `board_diagram.place`에 돌린 것(tools/export_flow_place.py → test/fixtures/flow_place.json), KAIROS는 가짜.
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, liveDoc, dragScene } from './helpers.js'

const ALL = JSON.parse(readFileSync(new URL('../test/fixtures/flow_place.json', import.meta.url), 'utf-8'))
const S = ALL['송신소_sonnet'], CHK = ALL['점검_sonnet']
const answer = (x, extra = {}) => ({ kind: 'diagram', content: `🔷 「${x.place.title}」`, spec: x.spec, place: x.place, model: 'claude-sonnet-5-5', elapsed: 9, fixed: false, ...extra })
// 고친 설계서 — 상자 하나 더(서버가 다시 계산한 셈 치고 마지막 상자를 오른쪽 아래에 하나 더)
function plusOne(x) {
  const p = structuredClone(x.place), last = p.steps.at(-1), [bx, by, w, h] = last.box
  p.steps.push({ ...last, id: 'sx', text: '전원 장치', kind: 'step', box: [bx, by + h + 60, w, h] }); p.links.push({ from: 'sx', to: last.id })
  p.ranks.sx = p.ranks[last.id]; p.height = Math.max(p.height, by + 2 * h + 60)
  return { ...x, place: p, spec: x.spec.replace('"steps": [', '"steps": [{"id": "sx", "text": "전원 장치"}, ') }
}
const ask = async (page, t) => { await page.getByPlaceholder('물어보세요', { exact: false }).click(); await page.keyboard.type(t); await page.keyboard.press('Enter') }
// 상자 끌기 — 100%로 그 상자를 화면 가운데에 두고 가운데보다 왼쪽을 잡음(50%면 상자 키가 28px라 가운데가 아래 변 「화살표 뽑는 점」에 걸려 새 화살표가 그려졌음)
async function dragBox(page, b, dx, dy) {
  const g = { x: b.pos[0] + b.rect[2] * 0.3, y: b.pos[1] + b.rect[3] / 2 }
  await setCam(page, { x: 500 - g.x, y: 400 - g.y, z: 1 }); await page.keyboard.press('Escape')
  await dragScene(page, g, { x: g.x + dx, y: g.y + dy })
}
const frames = doc => doc.items.filter(it => it.type === 'frame' && it.flow_spec != null)
const boxesOf = (doc, f) => doc.items.filter(it => it.flow_of === f.uid && (it.type === 'rect' || it.type === 'symbol'))

test('「계통도 그려 줘」 → 묻지 않고 프레임 안 상자 + 붙은 화살표, 상자를 옮기면 화살표가 따라옴', async ({ page }) => {
  const seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { seen.push(r.request().postDataJSON()); return r.fulfill({ json: answer(S) }) })
  await openBoard(page, boardName('diagram'), { chat: true }); await setCam(page, { x: 0, y: 0, z: 0.5 })
  await ask(page, '송신소 계통도 그려 줘')
  await expect(page.getByTestId('answer-diagram')).toBeVisible()
  await expect.poll(async () => frames(await liveDoc(page)).length).toBe(1)
  const doc = await liveDoc(page), f = frames(doc)[0], boxes = boxesOf(doc, f), arrows = doc.items.filter(it => it.flow_of === f.uid && it.type === 'sarrow')
  expect(f.name).toBe(S.place.title); expect(f.flow_spec).toBe(S.spec)
  expect(boxes.length).toBe(S.place.steps.length); expect(arrows.length).toBe(S.place.links.length)
  expect(arrows.every(a => a.bind1 != null && a.bind2 != null)).toBe(true)                       // 저장 파일에서도 두 끝이 상자 순번
  expect(arrows.some(a => a.pts.length > 2)).toBe(true)                                          // 길 찾기가 꺾음(두 점 그대로가 아님)
  expect(doc.items.filter(it => it.flow_of === f.uid && it.type === 'path').length).toBe(S.place.lanes.length)   // 담당 띠
  // 상자 하나를 끌면 붙은 화살표 끝이 따라옴
  const b = boxes[0], i = doc.items.indexOf(b), a = arrows.find(x => x.bind1 === i || x.bind2 === i), end = a.bind1 === i ? 0 : a.pts.length - 1
  const before = [a.pos[0] + a.pts[end][0], a.pos[1] + a.pts[end][1]]
  await dragBox(page, b, 0, 140)
  await expect.poll(async () => { const d = await liveDoc(page), b2 = d.items.find(x => x.uid === b.uid); return b2.pos[1] - b.pos[1] }).toBeGreaterThan(120)   // 정렬선에 몇 px 붙을 수 있음
  const d2 = await liveDoc(page), b2 = d2.items.find(x => x.uid === b.uid), a2 = d2.items.find(x => x.uid === a.uid)
  expect(Math.round(a2.pos[1] + a2.pts[end === 0 ? 0 : a2.pts.length - 1][1] - before[1])).toBe(Math.round(b2.pos[1] - b.pos[1]))   // 붙은 끝이 상자와 같이
})

test('이어 고치기 — 「전원 장치 추가해 줘」 = 같은 프레임 다시(Ctrl+Z 한 번), 손으로 고친 뒤면 옆에 새로', async ({ page }) => {
  const seen = []
  let reply = answer(CHK)
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { seen.push(r.request().postDataJSON()); return r.fulfill({ json: reply }) })
  await openBoard(page, boardName('diagramfix'), { chat: true }); await setCam(page, { x: 0, y: 0, z: 0.5 })
  await ask(page, '점검 순서 흐름도 그려 줘')
  await expect.poll(async () => frames(await liveDoc(page)).length).toBe(1)
  const f0 = frames(await liveDoc(page))[0], n0 = boxesOf(await liveDoc(page), f0).length
  const more = plusOne(CHK); reply = answer(more, { fixed: true })
  await ask(page, '전원 장치 추가해 줘')
  await expect.poll(async () => boxesOf(await liveDoc(page), f0).length).toBe(n0 + 1)
  expect(seen.at(-1).base_flow).toBe(CHK.spec)                                                   // 앞 도형 설계서를 실어 보냄
  expect(frames(await liveDoc(page)).length).toBe(1)                                             // 같은 프레임(uid 그대로)
  await page.locator('[data-testid="board"]').click({ position: { x: 5, y: 5 } }); await page.keyboard.press('Control+z')
  await expect.poll(async () => boxesOf(await liveDoc(page), f0).length).toBe(n0)                // 한 번에 되돌림
  // 손으로 상자 하나를 옮긴 뒤 고치면 — 덮지 않고 옆에 새 프레임
  await dragBox(page, boxesOf(await liveDoc(page), f0)[1], 30, 200)
  await ask(page, '전원 장치 추가해 줘')
  await expect.poll(async () => frames(await liveDoc(page)).length).toBe(2)
  expect(boxesOf(await liveDoc(page), f0).length).toBe(n0)
})

test('「+ › 🔷 도형 그리기」 이름표 = kind diagram · 「이미지로 다시」 = 같은 말로 그림', async ({ page }) => {
  const seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return r.fulfill({ json: b.kind === 'image' ? { kind: 'image', content: '그림 후보', model: 'img-m', elapsed: 1, images: [] } : answer(S) }) })
  await openBoard(page, boardName('diagramplus'), { chat: true }); await setCam(page, { x: 0, y: 0, z: 0.5 })
  await page.getByTestId('plus').click(); await page.getByRole('menuitemradio', { name: /도형 그리기/ }).click()
  await expect(page.getByTestId('tool-chip')).toContainText('도형 그리기')
  await page.locator('textarea').last().click(); await page.keyboard.type('출근 준비 순서'); await page.keyboard.press('Enter')   // 이름표를 고르면 안내 글이 바뀜
  await expect(page.getByTestId('answer-diagram')).toBeVisible()
  expect(seen.at(-1).kind).toBe('diagram')
  await page.getByTestId('diagram-image').click()
  await expect.poll(() => seen.at(-1)?.kind).toBe('image')
  expect(seen.at(-1).messages.at(-1).content).toBe('출근 준비 순서')
  expect(frames(await liveDoc(page)).length).toBe(1)                                            // 칠판의 도형은 그대로
})
