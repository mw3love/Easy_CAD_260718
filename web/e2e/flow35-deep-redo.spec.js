// 흐름 35 — 딥모드 꼭지 다시 쓰기(§8 항목66 5단계, 2026-10-25): 판 꼭지를 고른 채 대화창에 고치는 말 = 그 꼭지만 다시(서버 step section) → 계획에 적고 판 다시 지음.
// 묻는 말은 보통 대화(꼭지 안 바뀜) · 나머지 꼭지 글 그대로 · 겹침 0 · Ctrl+Z 한 번 · 「디자인」으로 다시 지어도 새 꼭지 · 손으로 고친 판은 크레딧 쓰기 전에 물음 ·
// 속성 카드 「이 꼭지 더 자세히」 · 움직이는 카드 꼭지 = 카드 고치기(계획 속 HTML도 새것). KAIROS·서버는 가짜(/api/chat) — 진짜 서버 길은 `tests/test_part73`
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, liveDoc, dragScene, waitSaved } from './helpers.js'
import { overlaps } from '../src/next/deep.js'

const PLAN = JSON.parse(readFileSync(new URL('../test/fixtures/deep_real_live.json', import.meta.url), 'utf-8'))
const HERO = PLAN.sections.findIndex(s => s.shape === '주인공 글'), CARD = PLAN.sections.findIndex(s => s.shape === '움직이는 카드')
const META = { topic: 'ATSC 3.0 변조·부호율', brief: { 누구에게: '송신소 신입' } }
const box = it => ({ x: it.pos[0], y: it.pos[1], w: it.rect[2] * (it.scale || 1), h: it.rect[3] * (it.scale || 1) })
const root = d => d.items.find(it => it.type === 'frame' && it.deep_plan)
const noOverlap = d => overlaps(d.items.filter(it => !['frame', 'sarrow', 'arrow'].includes(it.type)).map(box)).length
// 꼭지마다 글·칸·카드(자리 말고 내용) — 「나머지 그대로」 견주기
const contents = d => { const out = {}
  for (const it of d.items.filter(x => x.deep_of === root(d).uid && Number.isInteger(x.deep_sec) && !['sarrow', 'arrow'].includes(x.type)))
    (out[it.deep_sec] ||= []).push(JSON.stringify([it.type, (it.lines || []).map(l => l.t), it.cells || null, it.html ? it.html.length : 0]))
  return Object.fromEntries(Object.entries(out).map(([k, v]) => [k, v.sort().join('|')])) }
const NEW_P = '**새 문단** — 더 자세히 쓴 줄이에요 [24]'
const NEW_HTML = PLAN.sections[CARD].body.html.replace('<title>', '<title>고친 ')

function fake(page, sent) {
  return Promise.all([
    page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { deep: 'claude-opus-5-5', live: 'gpt-6.1-sol' } } })),
    page.route('**/api/chat', r => { const b = r.request().postDataJSON(); sent.push(b); const d = b.deep || {}
      if (d.step === 'section') return r.fulfill({ json: { kind: 'deep', step: 'section', model: 'claude-sonnet-5-5', elapsed: 12, credits: 18, missing: [],
        sources: [...d.plan.sources, { n: d.plan.sources.length + 1, title: '새 출처', url: 'https://new.example/a' }],
        sections: d.idx.map(i => { const s = d.plan.sections[i]
          return { i, ...s, body: s.shape === '움직이는 카드' ? { ...s.body, html: NEW_HTML } : { ...s.body, text: [...(s.body.text || []), NEW_P] } } }) } })
      return r.fulfill({ json: { kind: 'chat', content: '변조 차수는 한 번에 싣는 비트 수예요.', model: 'fake-model', elapsed: 1 } })
    })])
}

test('고른 꼭지만 다시 — 질문은 그대로 · 나머지 그대로 · 겹침 0 · Ctrl+Z 한 번 · 디자인을 바꿔도 남음', async ({ page }) => {
  const sent = []
  await fake(page, sent)
  const name = boardName('deepredo')
  await openBoard(page, name, { chat: true })
  await page.evaluate(([p, m]) => window.__mb.ed.deepBoard(p, { x: 0, y: 0 }, 'calm', m), [PLAN, META])
  await setCam(page, { x: 40, y: 40, z: 0.45 })
  let d = await liveDoc(page)
  const uid = root(d).uid, before = contents(d), hero = d.items.find(it => it.deep_of === uid && it.deep_sec === HERO)
  expect(root(d).deep_plan.brief).toEqual(META.brief)                                       // 주제·질문지 답도 판에(누구에게 쓰는지)

  await page.evaluate(id => window.__mb.ed.setSel([id]), hero.uid)
  await expect(page.getByTestId('sel-chip')).toContainText(`꼭지 「${PLAN.sections[HERO].title}」`)
  await page.getByPlaceholder('이 꼭지를 고칠 점', { exact: false }).click()
  await page.keyboard.type('이게 무슨 뜻이야?'); await page.keyboard.press('Enter')        // 묻는 말 = 보통 대화
  await expect(page.getByText('변조 차수는 한 번에 싣는 비트 수예요.')).toBeVisible()
  expect(sent.at(-1).kind).toBeUndefined(); expect(sent.at(-1).deep).toBeUndefined()
  expect(contents(await liveDoc(page))).toEqual(before)

  await page.evaluate(id => window.__mb.ed.setSel([id]), hero.uid)
  await page.getByPlaceholder('이 꼭지를 고칠 점', { exact: false }).click()
  await page.keyboard.type('더 자세히 써 줘'); await page.keyboard.press('Enter')
  await expect(page.locator('aside[aria-label="KAIROS 대화"]').getByText('를 다시 써서 판을 다시 지었어요', { exact: false })).toBeVisible({ timeout: 10_000 })
  const q = sent.at(-1)
  expect(q.kind).toBe('deep'); expect(q.deep.step).toBe('section'); expect(q.deep.idx).toEqual([HERO]); expect(q.deep.ask).toBe('더 자세히 써 줘')
  expect(q.deep.brief).toEqual(META.brief); expect(q.deep.plan.sections[CARD].body.html).toBeTruthy()   // 판 계획(본문 포함)을 그대로 보냄
  d = await liveDoc(page)
  const after = contents(d)
  expect(root(d).uid).toBe(uid)                                                               // 같은 프레임(발표 차례)
  expect(after[HERO]).toContain('새 문단'); expect(after[HERO]).not.toEqual(before[HERO])
  const SRC = PLAN.sections.findIndex(s => s.shape === '출처 카드')
  for (const k of Object.keys(before)) if (+k !== HERO && +k !== SRC) expect(after[k], `꼭지 ${k}`).toEqual(before[k])   // 나머지 꼭지 글 그대로
  expect(after[SRC]).toContain('[24] 새 출처')                                                  // 출처 카드 = 판에서 쓴 출처(새 출처도)
  expect(noOverlap(d)).toBe(0)
  expect(root(d).deep_plan.plan.sections[HERO].body.text.at(-1)).toBe(NEW_P)                  // 계획에 적힘
  expect(root(d).deep_plan.plan.sources).toHaveLength(PLAN.sources.length + 1)
  await page.getByTestId('board').screenshot({ path: 'test-results/deepredo-hero.png' })

  await page.keyboard.press('Escape')
  await page.evaluate(() => window.__mb.ed.undo())                                            // 되돌리기 한 번 = 다시 쓰기 전
  expect(contents(await liveDoc(page))).toEqual(before)
  await page.evaluate(() => window.__mb.ed.redo())
  expect(contents(await liveDoc(page))[HERO]).toContain('새 문단')

  await page.evaluate(id => window.__mb.ed.setSel([id]), uid)
  await page.getByTestId('deep-styles').locator('[data-style="news"]').click()                // 다시 지어도 옛 꼭지로 안 돌아감
  d = await liveDoc(page)
  expect(root(d).deep_plan.style).toBe('news'); expect(contents(d)[HERO]).toContain('새 문단'); expect(noOverlap(d)).toBe(0)

  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  d = await liveDoc(page)
  expect(contents(d)[HERO]).toContain('새 문단'); expect(root(d).deep_plan.brief).toEqual(META.brief)
})

test('속성 카드 「이 꼭지 더 자세히」 · 손으로 고친 판은 먼저 물음 · 움직이는 카드 고치기', async ({ page }) => {
  const sent = []
  await fake(page, sent)
  await openBoard(page, boardName('deepredo2'), { chat: true })
  await page.evaluate(([p, m]) => window.__mb.ed.deepBoard(p, { x: 0, y: 0 }, 'calm', m), [PLAN, META])
  await setCam(page, { x: 40, y: 40, z: 0.45 })
  let d = await liveDoc(page)
  const uid = root(d).uid
  const memo = d.items.find(it => it.deep_of === uid && it.type === 'memo' && Number.isInteger(it.deep_sec) && !it.group_id && it.deep_sec !== CARD), b = box(memo)
  await dragScene(page, { x: b.x + 40, y: b.y + b.h / 2 }, { x: b.x + 70, y: b.y + b.h / 2 + 30 })   // 손으로 옮김
  const card = (await liveDoc(page)).items.find(it => it.deep_of === uid && it.deep_sec === CARD && it.type === 'doc')
  await page.evaluate(id => window.__mb.ed.setSel([id]), card.uid)
  const n0 = sent.length
  await expect(page.getByTestId('deep-redo')).toHaveText('이 꼭지 더 자세히')
  await page.getByTestId('deep-rows').screenshot({ path: 'test-results/deepredo-props.png' })
  await page.getByTestId('deep-redo').click()
  await expect(page.getByTestId('deep-confirm-chat')).toBeVisible()                         // 크레딧 쓰기 전에 물음
  expect(sent.length).toBe(n0)
  expect(root(await liveDoc(page)).deep_plan.plan.sections[CARD].body.html).toBe(PLAN.sections[CARD].body.html)
  await page.getByTestId('deep-confirm-chat-yes').click()
  await expect(page.locator('aside[aria-label="KAIROS 대화"]').getByText('를 다시 써서 판을 다시 지었어요', { exact: false })).toBeVisible({ timeout: 10_000 })
  expect(sent.at(-1).deep.idx).toEqual([CARD]); expect(sent.at(-1).deep.ask).toBe('')        // 고칠 말 없음 = 서버가 「더 자세히」
  d = await liveDoc(page)
  expect(d.items.find(it => it.deep_of === uid && it.deep_sec === CARD && it.type === 'doc').html).toBe(NEW_HTML)
  expect(root(d).deep_plan.plan.sections[CARD].body.html).toBe(NEW_HTML)                     // 계획 속 카드도 새것(4단계에서 남긴 것)
  expect(noOverlap(d)).toBe(0)
  await page.locator('aside[aria-label="KAIROS 대화"]').screenshot({ path: 'test-results/deepredo-panel.png' })
})
