// 흐름 62 — 딥모드·발표 자료 맞춤 질문(2026-11-06 사용자 「프롬프트를 읽고 맞춤으로 — 대상을 썼는데 또 물음」).
// 질문지를 띄우자마자 서버 `step: 'ask'`(주제 글 → 알아들은 것 + 질문) → 알아들은 것 칩 + 맞춤 질문 + 아래 「설정」(장 수·그림 장·재료…).
// 계획을 짤 때 보내는 답 = 맞춤 답 + 알아들은 것 + 누구에게(= 알아들은 대상). 못 만들면 고정 질문. 진짜 KAIROS는 안 부름.
import { test, expect } from '@playwright/test'
import { boardName, openBoard } from './helpers.js'

const TOPIC = '모악산 송신소 소개. 대상은 신입사원'
const ASK = { kind: 'slides', step: 'ask', known: [{ label: '대상', value: '신입사원' }], audience: '신입사원',
  questions: [{ q: '언제 쓰는 자료인가요', options: ['견학 전', '다녀온 뒤'], multi: false }, { q: '어떤 내용을 중심으로', options: ['역사', '설비', '운영'], multi: true }], model: 'm', elapsed: 4 }
const PLAN = { title: 't', slides: [{ title: '표지', point: '', source: 'ai', pic: false }, { title: '설비', point: '', source: 'ai', pic: true }] }

async function start(page, name, onAsk) {
  const seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { deep: 'm', slides: 'm' } } }))
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b); const d = b.slides || b.deep
    if (d?.step === 'ask') return onAsk(r, b)
    return r.fulfill({ json: b.slides ? { kind: 'slides', plan: PLAN, estimate: { credits: [10, 20], seconds: [10, 20] }, model: 'm', elapsed: 1 } : { kind: 'deep', plan: { title: 't', sections: [{ title: 'a', shape: '주인공 글', source: 'ai' }, { title: 'b', shape: '표', source: 'ai' }, { title: 'c', shape: '용어 풀이', source: 'ai' }] }, estimate: { credits: [10, 20], seconds: [10, 20] }, model: 'm', elapsed: 1 } }) })
  await openBoard(page, boardName(name), { chat: true, briefAsk: true })
  await page.getByTestId('plus').click(); await page.getByRole('menuitemradio', { name: /Deep Mode/ }).click()
  const box = page.getByPlaceholder('어떤 주제로', { exact: false }); await box.fill(TOPIC); await box.press('Enter')
  return seen
}

test('맞춤 질문 — 알아들은 것은 칩으로(다시 안 물음) · 맞춤 질문 + 「설정」 · 보낸 답에 알아들은 것·누구에게가 실림', async ({ page }) => {
  const seen = await start(page, 'briefask', r => r.fulfill({ json: ASK }))
  const ask = page.getByTestId('deep-ask')
  await expect(page.getByTestId('deep-known')).toContainText('대상 · 신입사원')
  await expect(ask.locator('[data-q="언제 쓰는 자료인가요"]')).toBeVisible()
  await expect(ask.locator('[data-q="누구에게"]')).toHaveCount(0)                                   // 대상을 말했으니 안 물음
  expect(seen[0].deep || seen[0].slides).toMatchObject({ step: 'ask', topic: TOPIC })
  await ask.getByTestId('deep-shape').locator('button[data-v="slides"]').click()                      // 여러 장으로 바꿔도 맞춤 질문은 그대로, 설정만 바뀜
  await expect(ask.locator('[data-q="언제 쓰는 자료인가요"]')).toBeVisible()
  await expect(ask.locator('[data-q="장 수"]')).toBeVisible(); await expect(ask.locator('[data-q="듣는 사람"]')).toHaveCount(0)
  await ask.locator('[data-q="언제 쓰는 자료인가요"] button[data-v="견학 전"]').click()
  await ask.locator('[data-q="어떤 내용을 중심으로"] button[data-v="설비"]').click()
  await ask.locator('[data-q="장 수"] button[data-v="5장"]').click()
  await page.getByTestId('deep-plan-go').click()
  await expect(page.getByTestId('slides-plan')).toBeVisible()
  const brief = seen.at(-1).slides.brief
  expect(brief).toMatchObject({ '언제 쓰는 자료인가요': '견학 전', '어떤 내용을 중심으로': ['설비'], '장 수': '5장', '그림 장': '알아서', 누구에게: '신입사원', '주제에서 알아들은 것': '대상: 신입사원' })
})

test('맞춤 질문 — 못 만들면 고정 질문 · 정리하는 동안은 설정만 보이고 Enter·계획 단추는 기다림', async ({ page }) => {
  let release; const gate = new Promise(res => { release = res })
  await start(page, 'briefask2', async r => { await gate; return r.fulfill({ status: 502, json: { error: '안 됨' } }) })
  const ask = page.getByTestId('deep-ask')
  await expect(page.getByTestId('deep-asking')).toBeVisible()
  await expect(ask.locator('[data-q="깊이"]')).toBeVisible(); await expect(ask.locator('[data-q="누구에게"]')).toHaveCount(0)   // 정리 중 = 설정만
  await expect(page.getByTestId('deep-plan-go')).toBeDisabled()
  const box = page.getByPlaceholder('꼭 넣을 것', { exact: false }); await box.fill('숫자 많이'); await box.press('Enter')
  await expect(box).toHaveValue('숫자 많이')                                                          // Enter = 기다림(글은 그대로)
  release()
  await expect(page.getByTestId('deep-ask-fallback')).toBeVisible()
  await expect(ask.locator('[data-q="누구에게"]')).toBeVisible()                                      // 고정 질문으로
  await expect(page.getByTestId('deep-plan-go')).toBeEnabled()
})
