// 흐름 29 — 되묻기(§8 항목64, 2026-10-23): 「펭귄 아이콘 그려줘」 → ❓ 버튼 둘(만들기 전) → 「✏️ 선 도형으로」 = 같은 질문을 아이콘 길로 다시, 되묻기 자리에 답
// → 같은 갈림길에서 두 번 연달아 같은 걸 고르면 다음엔 `ask_pref`로 보내 안 물음. KAIROS는 가짜(/api/chat) — 서버 쪽은 tests/test_part71.
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam } from './helpers.js'

const ICON = readFileSync(new URL('../../tests/fixtures/svg_ai/claude-sonnet-5-5__0.svg', import.meta.url), 'utf-8')

test('애매한 아이콘 → 버튼 둘 → 고르면 그 길로 → 두 번 고르면 안 물음', async ({ page }) => {
  const sent = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); sent.push(b)
    const pref = b.ask_pref?.['icon|image']
    return r.fulfill({ json: b.kind === 'icon' || pref === 'icon' ? { kind: 'icon', content: '아이콘 후보 2개', svgs: [ICON, ICON], model: 'icon-m', elapsed: 3,
        ...(pref === 'icon' && !b.kind ? { remembered: { key: 'icon|image', choices: ['image', 'icon'] } } : {}) }
      : b.kind === 'image' ? { kind: 'image', content: '그림 후보 0장', images: [], model: 'img-m', elapsed: 4 }
      : { kind: 'ask', choices: ['image', 'icon'], default: 'image', key: 'icon|image', content: '어느 쪽으로 만들까요?', model: '낱말 규칙', elapsed: 0 } }) })
  await openBoard(page, boardName('ask'), { chat: true }); await setCam(page)
  const input = page.getByPlaceholder('물어보세요', { exact: false })
  const askOnce = async () => { await input.click(); await page.keyboard.type('펭귄 아이콘 그려줘'); await page.keyboard.press('Enter') }

  await askOnce()
  await expect(page.getByTestId('ask-choice')).toHaveCount(2)
  await expect(page.getByTestId('answer-kind').last()).toHaveText('❓ 확인')
  await expect(page.getByRole('button', { name: '칠판에 붙이기' })).toHaveCount(0)   // 되묻기엔 붙이기·⋯ 없음
  await expect(page.getByTestId('answer-menu')).toHaveCount(0)
  await page.locator('[data-testid="ask-choice"][data-kind="icon"]').click()
  await expect(page.getByTestId('svg-pick')).toHaveCount(2)
  expect(sent[1].kind).toBe('icon')
  expect(sent[1].messages).toEqual([{ role: 'user', content: '펭귄 아이콘 그려줘' }])   // 같은 질문 그대로
  await expect(page.getByTestId('ask-choice')).toHaveCount(0)                         // 되묻기 자리에 답이 들어감
  await expect(page.getByTestId('answer-kind')).toHaveCount(1)

  await askOnce()                                                                     // 한 번 골랐을 땐 아직 물음
  expect(sent[2].ask_pref).toBeUndefined()
  await expect(page.getByTestId('ask-choice')).toHaveCount(2)
  await page.locator('[data-testid="ask-choice"][data-kind="icon"]').click()
  await expect(page.getByTestId('svg-pick')).toHaveCount(4)
  expect(sent[3].messages.filter(m => m.content === '어느 쪽으로 만들까요?')).toEqual([])   // 되묻기 글은 앞 대화에 안 실음

  await askOnce()                                                                     // 두 번 연달아 아이콘 = 이제 안 물음
  expect(sent[4].ask_pref).toEqual({ 'icon|image': 'icon' })
  await expect(page.getByTestId('svg-pick')).toHaveCount(6)
  await expect(page.getByTestId('ask-choice')).toHaveCount(0)
  await expect(page.getByTestId('ask-remembered')).toContainText('기억한 대로')      // 기억으로 고른 답 = 다른 쪽 버튼(2026-10-23 사용자: 세 번째에 다른 걸 고르고 싶으면?)

  await page.getByTestId('ask-other').click()                                         // 「🎨 그림으로 바꾸기」 = 같은 질문을 그림으로, 그 자리에 답
  await expect(page.getByTestId('answer-kind').last()).toHaveText('🎨 그림')
  expect(sent[5].kind).toBe('image')
  expect(sent[5].messages.at(-1)).toEqual({ role: 'user', content: '펭귄 아이콘 그려줘' })   // 같은 질문(앞 대화는 그대로)
  await expect(page.getByTestId('svg-pick')).toHaveCount(4)
  await askOnce()                                                                     // 마음이 바뀌었으니 다시 물음
  expect(sent[6].ask_pref).toBeUndefined()
  await expect(page.getByTestId('ask-choice')).toHaveCount(2)
})

test('되묻기에 버튼 대신 입력 칸으로 답함 = 처음 질문에 덧붙여, 다시 안 물음', async ({ page }) => {
  const sent = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); sent.push(b)
    return r.fulfill({ json: b.ask_reply || b.kind ? { kind: 'icon', content: '아이콘 후보 1개', svgs: [ICON], model: 'icon-m', elapsed: 3 }
      : { kind: 'ask', choices: ['image', 'icon'], default: 'image', key: 'icon|image', content: '어느 쪽으로 만들까요?', model: '낱말 규칙', elapsed: 0 } }) })
  await openBoard(page, boardName('ask2'), { chat: true }); await setCam(page)
  await page.getByPlaceholder('물어보세요', { exact: false }).click(); await page.keyboard.type('펭귄 아이콘 그려줘'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('ask-choice')).toHaveCount(2)
  await page.getByPlaceholder('버튼을 누르거나', { exact: false }).click()             // 되묻기가 떠 있으면 안내 글이 바뀜
  await page.keyboard.type('선으로 해 줘'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('svg-pick')).toHaveCount(1)
  expect(sent[1].ask_add).toBe('선으로 해 줘')
  expect(sent[1].ask_reply).toEqual({ choices: ['image', 'icon'], default: 'image' })
  expect(sent[1].kind).toBeUndefined()                                                // 길은 서버가 덧붙인 말로(못 알아들으면 원래 1등)
  expect(sent[1].messages).toEqual([{ role: 'user', content: ['펭귄 아이콘 그려줘', '선으로 해 줘'].join('\n') }])
  await expect(page.getByTestId('ask-choice')).toHaveCount(0)
  await expect(page.getByText('위 질문에 덧붙여')).toBeVisible()

  await page.getByPlaceholder('물어보세요', { exact: false }).click(); await page.keyboard.type('펭귄 아이콘 그려줘'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('ask-choice')).toHaveCount(2)
  await page.getByPlaceholder('버튼을 누르거나', { exact: false }).click(); await page.keyboard.type('수채화 느낌')   // 글을 적고 버튼 = 그 길 + 덧붙임
  await page.locator('[data-testid="ask-choice"][data-kind="icon"]').click()
  await expect(page.getByTestId('svg-pick')).toHaveCount(2)
  expect(sent[3].kind).toBe('icon')
  expect(sent[3].ask_add).toBeUndefined()
  expect(sent[3].messages.at(-1)).toEqual({ role: 'user', content: ['펭귄 아이콘 그려줘', '수채화 느낌'].join('\n') })
})
