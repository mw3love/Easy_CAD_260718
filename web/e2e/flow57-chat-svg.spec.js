// 흐름 57 — 대화 답에 SVG 코드가 섞이면(2026-11-03 사용자 검토: 「계통도 그려 줘」에 코드 글 + 「저장해 브라우저에서 열면」 — 일반 사용자는 당황)
// 서버가 코드를 그림 칸(`svgs`)으로 뺌(`board_chat.split_svg`, tests/test_part71) → 대화창은 코드 대신 미리보기, 누르면 칠판에 고칠 수 있는 도형. KAIROS는 가짜.
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, liveDoc } from './helpers.js'

const SVG = readFileSync(new URL('../../tests/fixtures/svg_ai/claude-sonnet-5-5__0.svg', import.meta.url), 'utf-8')

test('대화 답의 그림 칸 = 코드 없이 미리보기 → 누르면 칠판에 도형', async ({ page }) => {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => r.fulfill({ json: { kind: 'chat', content: '**연필 느낌 계통도**입니다.\n\n그림은 아래에 보여 드려요 — 누르면 칠판에 고칠 수 있는 도형으로 붙어요.', svgs: [SVG], model: 'm', elapsed: 2 } }))
  await openBoard(page, boardName('chatsvg'), { chat: true }); await setCam(page)
  await page.getByPlaceholder('물어보세요', { exact: false }).click(); await page.keyboard.type('계통도 그려 줘'); await page.keyboard.press('Enter')
  const pick = page.getByTestId('svg-pick'); await expect(pick).toHaveCount(1)
  await expect(page.getByTestId('answer-svgs')).toBeVisible()
  await expect(page.locator('[aria-label="KAIROS 대화"]')).not.toContainText('<svg')
  await pick.click()
  await expect.poll(async () => (await liveDoc(page)).items.length).toBeGreaterThan(1)          // SVG 한 장 = 고칠 수 있는 도형 여럿(묶음)
  expect((await liveDoc(page)).items.every(it => it.type !== 'image')).toBe(true)
})
