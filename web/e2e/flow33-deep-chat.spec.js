// 흐름 33 — 딥모드 대화창(§8 항목66 3-2, 2026-10-25): 「+ › 📰 딥모드」 + 주제 → 질문지 카드(서버 안 부름) → 버튼 + 입력 칸 글 → 「지면 계획 짜기」 → 계획 카드(× 빼기·예상 크레딧 — 디자인 고르기는 2026-10-25 없앰, 톤은 만든 뒤)
// → 말로 고치기 = 계획 다시(뺀 꼭지는 빼고 보냄) → 「이대로 만들기」 = 칠판에 판(차분 톤) → 새로고침해도 카드 그대로.
// KAIROS·서버는 가짜(/api/chat) — 진짜 서버 길은 3-3. 서버가 딥모드를 못 하면(/api/models `jobs.deep` 없음) 「+」에 안 보임
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, liveDoc } from './helpers.js'
import { overlaps } from '../src/next/deep.js'

const load = t => JSON.parse(readFileSync(new URL(`../test/fixtures/deep_${t}.json`, import.meta.url), 'utf-8'))
const FULL = load('real_paper'), NEWS = load('real_news')
const BODY = new Map([...FULL.sections, ...NEWS.sections].map(s => [s.title, s.body]))
const bare = p => ({ ...p, sections: p.sections.map(({ body, ...s }) => s) })   // 계획 = 본문 없이
const GRAPH = bare(NEWS).sections.find(s => s.shape === '그래프')
const box = it => ({ x: it.pos[0], y: it.pos[1], w: it.rect[2] * (it.scale || 1), h: it.rect[3] * (it.scale || 1) })

test('서버가 딥모드를 못 하면 「+」에 없음', async ({ page }) => {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await openBoard(page, boardName('deepchat0'), { chat: true })
  await page.getByTestId('plus').click()
  await expect(page.getByRole('menuitemradio', { name: /아이콘/ })).toBeVisible()
  await expect(page.getByRole('menuitemradio', { name: /딥모드/ })).toHaveCount(0)
})

test('딥모드 — 질문지 → 지면 계획 → 고치기 → 만들기 → 다시 열어도 그대로', async ({ page }) => {
  const sent = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { deep: 'claude-opus-5-5' } } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); sent.push(b); const d = b.deep || {}
    if (d.step === 'plan' && !d.prev) return r.fulfill({ json: { kind: 'deep', plan: bare(FULL), estimate: { credits: [90, 155], seconds: [45, 90] }, model: 'claude-opus-5-5', elapsed: 21, credits: 44 } })
    if (d.step === 'plan') return r.fulfill({ json: { kind: 'deep', plan: { ...d.prev, sections: [...d.prev.sections, GRAPH] }, estimate: { credits: [100, 160], seconds: [50, 90] }, model: 'claude-opus-5-5', elapsed: 18, credits: 40 } })
    return r.fulfill({ json: { kind: 'deep', plan: { ...d.plan, sources: [...FULL.sources, ...NEWS.sources.map(s => ({ ...s, n: s.n + 100 }))], sections: d.plan.sections.map(s => ({ ...s, body: BODY.get(s.title) })) }, model: 'claude-sonnet-5-5', elapsed: 33, credits: 61 } })
  })
  const name = boardName('deepchat')
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.getByTestId('plus').click()
  await page.getByRole('menuitemradio', { name: /딥모드/ }).click()
  await expect(page.getByTestId('tool-chip')).toHaveText('📰 딥모드 ✕')
  await page.getByPlaceholder('어떤 주제로 한 판', { exact: false }).click()
  await page.keyboard.type('어텐션이 뭐야? 신입 교육용으로'); await page.keyboard.press('Enter')
  const ask = page.getByTestId('deep-ask')
  await expect(ask).toBeVisible()
  expect(sent).toHaveLength(0)                                                       // 질문지는 서버를 안 부름
  await expect(page.getByTestId('tool-chip')).toHaveCount(0)
  await expect(ask.locator('[data-q="깊이"] [data-v="알아서"]')).toHaveAttribute('aria-pressed', 'true')   // 안 고르면 알아서
  await ask.locator('[data-q="누구에게"] [data-v="처음 보는 사람"]').click()
  await ask.locator('[data-q="무엇에"] [data-v="공부·교육"]').click()
  await ask.locator('[data-q="꼭 넣을 것"] [data-v="숫자·그래프"]').click()
  await ask.locator('[data-q="꼭 넣을 것"] [data-v="확인 문제"]').click()
  await ask.locator('[data-q="꼭 넣을 것"] [data-v="확인 문제"]').click()            // 다시 누르면 빠짐
  await page.locator('aside[aria-label="KAIROS 대화"]').screenshot({ path: 'test-results/deepchat-ask.png' })
  await page.getByPlaceholder('꼭 넣을 것', { exact: false }).click()
  await page.keyboard.type('그림은 빼 줘'); await page.keyboard.press('Enter')       // Enter = 지면 계획 짜기(글 = 「더」)

  const plan1 = page.getByTestId('deep-plan').first()
  await expect(plan1).toBeVisible()
  expect(sent[0].kind).toBe('deep')
  expect(sent[0].deep).toEqual({ step: 'plan', topic: '어텐션이 뭐야? 신입 교육용으로',
    brief: { 누구에게: '처음 보는 사람', 무엇에: '공부·교육', 깊이: '알아서', '꼭 넣을 것': ['숫자·그래프'], 재료: '알아서', 더: '그림은 빼 줘' } })
  await expect(ask.locator('[data-v="발표"]')).toBeDisabled()                         // 질문지는 잠김
  const N = FULL.sections.length
  await expect(plan1.getByTestId('deep-sec')).toHaveCount(N)
  await expect(plan1.locator('[data-style]')).toHaveCount(0)                          // 톤은 만든 뒤 속성 카드에서(처음 고르기 없음)
  await expect(plan1.getByTestId('deep-build')).toContainText('90~155크레딧')
  await plan1.getByTestId('deep-sec-x').nth(2).click()                               // 셋째 꼭지 빼기
  await expect(plan1.getByTestId('deep-sec').nth(2)).toHaveAttribute('data-dropped', '1')

  await page.getByPlaceholder('계획을 고칠 점', { exact: false }).click()
  await page.keyboard.type('그래프를 하나 더'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('deep-plan')).toHaveCount(2)
  expect(sent[1].deep.step).toBe('plan'); expect(sent[1].deep.fix).toBe('그래프를 하나 더')
  expect(sent[1].deep.prev.sections.map(s => s.title)).toEqual(FULL.sections.filter((_, i) => i !== 2).map(s => s.title))   // 뺀 꼭지는 빼고
  await expect(plan1.getByTestId('deep-build')).toHaveCount(0)                       // 옛 계획은 「아래에 고친 계획」
  const plan2 = page.getByTestId('deep-plan').nth(1)
  await expect(plan2.getByTestId('deep-sec')).toHaveCount(N)                        // N - 1 + 그래프 하나

  await plan2.getByTestId('deep-build').click()
  await expect(plan2.getByTestId('deep-show')).toBeVisible({ timeout: 10_000 })
  expect(sent[2].deep.step).toBe('build'); expect(sent[2].deep.style).toBeUndefined(); expect(sent[2].deep.plan.sections).toHaveLength(N)
  let d = await liveDoc(page)
  const root = d.items.find(it => it.type === 'frame' && it.deep_plan)
  expect(root.deep_plan.style).toBe('calm')
  expect(d.items.filter(it => it.deep_of === root.uid && it.deep_sec != null).length).toBeGreaterThan(N)
  expect(overlaps(d.items.filter(it => !['frame', 'sarrow', 'arrow'].includes(it.type)).map(box)).length).toBe(0)
  await expect(page.getByTestId('sel-chip')).toHaveCount(0)                          // 보여 주려고 고른 판은 다음 질문에 안 실음
  await page.getByTestId('board').screenshot({ path: 'test-results/deepchat-built.png' })
  await page.locator('aside[aria-label="KAIROS 대화"]').screenshot({ path: 'test-results/deepchat-panel.png' })

  await page.reload(); await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  await expect(page.getByTestId('deep-plan')).toHaveCount(2)
  await expect(page.getByTestId('deep-show')).toBeVisible()
  await expect(page.getByTestId('deep-ask').locator('[data-v="발표"]')).toBeDisabled()
})
