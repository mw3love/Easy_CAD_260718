// 흐름 17 — 「정리해 줘」 ② 레고형 정리정돈(§8 항목61): 흩어진 메모 8개 + 화살표 하나 → 모두 고르고 우클릭 「정리정돈하기」 → 🧩 답이 오면 바로
// 주제별 프레임으로 모임(조각은 틀 안, 화살표 안 끊김, 핵심 의견 노란 메모) → Ctrl+Z 한 번에 원래대로 → 다시 → 새로고침해도 그대로(대화 기록을 다시 열어도 또 하지 않음).
// KAIROS는 가짜(/api/chat) — 서버는 tests/test_part62, 자리 계산은 web/test/tidy.test.mjs, 진짜는 손 확인.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, waitSaved } from './helpers.js'

const TEXTS = ['송신기 2번 출력 70%', '회의: 다음 주 화요일', '송신기 냉각 팬 소음', '점심 메뉴 고민', '회의 안건 — 예산', '송신기 예비품 주문', '회의록 공유하기', '송신기 교체 견적']
const POS = [[0, 0], [700, 40], [260, 380], [1100, 300], [120, 760], [820, 620], [1250, 0], [480, 1000]]
const memo = (t, [x, y], i) => ({ type: 'memo', uid: `m${i}`, pos: [x, y], scale: 1, rotation: 0, z: 1, origin: [0, 0], locked: false, group_id: null, layer_id: null, rect: [0, 0, 340, 53], fill: '#fffff8c5', lines: [{ k: 'p', t }] })
const DOC = { format: 'easycad-doc', version: 1, items: [...TEXTS.map((t, i) => memo(t, POS[i], i)),
  { type: 'sarrow', uid: 'a1', pos: [0, 0], scale: 1, rotation: 0, z: 2, origin: [0, 0], locked: false, group_id: null, layer_id: null, routing: 'ortho', route_hints: [], color: '#ff1f1f1f', style: 1, width: 1,
    head: true, head_start: false, head_scale: 1, curve_r: 10, auto_route: true, pts: [[340, 26], [600, 26], [600, 406], [260, 406]], bind1: 0, bind1_pt: [340, 26], bind1_group: null, bind2: 2, bind2_pt: [0, 26], bind2_group: null }] }

test('흩어진 메모 → 정리정돈 = 주제별 프레임 → Ctrl+Z 한 번 → 다시 → 새로고침해도 그대로', async ({ page }) => {
  const name = boardName('tidy'), seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/tidy-sample.ecad', r => r.fulfill({ json: DOC }))
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b)
    const by = w => (b.items || []).filter(it => it.text.includes(w)).map(it => it.uid), sec = [...by('송신기'), ...by('회의')]
    const plan = { title: '송신소 점검', opinion: '송신기 교체가 가장 급해 보여요', sections: [{ title: '송신기', items: by('송신기'), note: '출력·냉각·예비품' }, { title: '회의', items: by('회의'), note: '' },
      { title: '기타', items: (b.items || []).map(it => it.uid).filter(u => !sec.includes(u)), note: '' }] }
    await r.fulfill({ json: { kind: 'tidy', content: '**송신소 점검** — 조각 8개를 3묶음으로 정돈했어요', plan, model: 'claude-sonnet-5-5', elapsed: 9 } }) })
  await openBoard(page, name)
  await page.evaluate(() => window.__mb.open('/tidy-sample.ecad'))
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(9)
  await setCam(page, { x: 200, y: 150, z: 0.5 })
  const before = await liveDoc(page)

  await clickScene(page, 2400, 1600); await page.keyboard.press('Control+a')        // 모두 고르기
  const m0 = before.items.find(it => it.uid === 'm0')
  await clickScene(page, m0.pos[0] + 200, m0.pos[1] + 26, { button: 'right' })
  await page.getByRole('button', { name: '정리정돈하기 (KAIROS)' }).click()
  await expect(page.getByTestId('answer-kind')).toHaveText('🧩 정리정돈')
  await expect(page.getByText('같이 보냄', { exact: false })).toHaveCount(0)   // 정돈한 프레임은 고른 채로 보이되 다음 질문엔 안 실림(2026-10-19 점검)
  expect(seen[0].kind).toBe('tidy')
  expect(seen[0].items.map(it => it.uid).sort()).toEqual(TEXTS.map((_, i) => `m${i}`))   // 화살표는 조각이 아님
  expect(seen[0].items[0]).toMatchObject({ type: 'memo', w: 340, h: 53 })

  let d = await liveDoc(page)
  const frames = d.items.filter(it => it.type === 'frame')
  expect(frames.map(f => f.name)).toEqual(['송신기', '회의', '기타'])
  const inFrame = (f, it) => it.pos[0] >= f.pos[0] && it.pos[1] >= f.pos[1] && it.pos[0] + it.rect[2] <= f.pos[0] + f.rect[2] && it.pos[1] + it.rect[3] <= f.pos[1] + f.rect[3]
  for (const [fi, w] of [[0, '송신기'], [1, '회의']]) for (const it of d.items.filter(x => x.type === 'memo' && x.lines[0].t.includes(w) && !x.lines[0].t.startsWith('💡'))) expect(inFrame(frames[fi], it), it.lines[0].t).toBe(true)
  expect(inFrame(frames[2], d.items.find(it => it.uid === 'm3'))).toBe(true)
  expect(Math.min(...frames.map(f => f.pos[0]))).toBe(0)                               // 원래 자리(바깥 상자 왼쪽 위)에서
  const ar = d.items.find(it => it.type === 'sarrow')
  expect([ar.bind1, ar.bind2].map(i => d.items[i].uid)).toEqual(['m0', 'm2'])          // 화살표 안 끊김 — 옮긴 메모를 따라감
  const a2 = d.items.find(it => it.uid === 'm2'), end = ar.pts.at(-1)
  expect(end[0] >= a2.pos[0] - 1 && end[0] <= a2.pos[0] + 341 && end[1] >= a2.pos[1] - 1 && end[1] <= a2.pos[1] + 54).toBe(true)
  expect(d.items.find(it => it.type === 'memo' && it.lines.some(l => l.t.includes('송신기 교체가 가장 급해'))).fill).toBe('#fffff8c5')   // 핵심 의견 = 노란 메모

  await clickScene(page, 5000, 4000); await page.keyboard.press('Control+z')         // 한 번에 원래대로
  d = await liveDoc(page)
  expect(d.items.filter(it => it.type === 'frame')).toHaveLength(0)
  expect(d.items.length).toBe(9)
  for (const it of before.items.filter(x => x.type === 'memo')) expect(d.items.find(x => x.uid === it.uid).pos).toEqual(it.pos)

  await page.keyboard.press('Control+y')
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'frame').length).toBe(3)
  await page.getByRole('button', { name: '정돈한 곳 보기' }).click()
  await expect.poll(() => page.evaluate(() => window.__mb.ed.getSel().length)).toBe(3)   // 프레임 셋을 골라 한눈에
  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  await page.getByTitle('KAIROS 대화창 열기/닫기', { exact: false }).click()
  await expect(page.getByTestId('answer-kind')).toHaveText('🧩 정리정돈')            // 기록은 다시 열려도
  d = await liveDoc(page)
  expect(d.items.filter(it => it.type === 'frame')).toHaveLength(3)                     // 또 정돈하지 않음
  expect(seen).toHaveLength(1)
})
