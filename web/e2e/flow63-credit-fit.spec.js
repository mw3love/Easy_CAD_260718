// 흐름 63 — 만들기 전 크레딧 확인(계획 ④, 2026-11-08 사용자 「크레딧을 기반으로 거꾸로 — 여유 있으면 여러 장, 아니면 한 장으로 압축」).
// 계획 카드 = 남은 크레딧(이 키) · 모자라면 경고 + 들게 줄이는 단추(그림 장 → 글 장 · 끝에서 빼기) + 「한 장으로 압축」(인포그래픽 질문지). 진짜 KAIROS는 안 부름.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, routeCall, askChat } from './helpers.js'

const PLAN = { title: '전파', slides: [{ title: '표지', point: '', source: 'ai', pic: false }, ...['송신소', '전파', '안테나', '집'].map(t => ({ title: t, point: '', source: 'ai', pic: true }))] }

async function start(page, name, remaining, to = 'slides') {
  const seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { deep: 'm', slides: 'm' }, features: [{ kind: 'infographic', ask: true, credits: [22, 32] }] } }))
  await page.route('**/api/credits', r => r.fulfill({ json: { remaining, quota: 10000 } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); if (routeCall(b)) return r.fulfill({ json: { kind: 'go', to } }); seen.push(b)
    return r.fulfill({ json: { kind: 'slides', plan: PLAN, estimate: { credits: [55, 60], seconds: [30, 60] }, model: 'm', elapsed: 1 } }) })   // 글 장 5 × 2 + 그림 장 4 × 12 ≈ 60
  await openBoard(page, boardName(name), { chat: true })
  await askChat(page, '전파가 집까지 오는 길 발표 자료 만들어 줘')
  await page.getByTestId('deep-plan-go').click()
  await expect(page.getByTestId('slides-plan')).toBeVisible()
  return seen
}

test('크레딧이 넉넉하면 한 줄 안내만', async ({ page }) => {
  await start(page, 'creditok', 5000)
  await expect(page.getByTestId('credit-ok')).toHaveText('남은 크레딧 5,000(서버 키) — 충분해요')
  await expect(page.getByTestId('credit-short')).toHaveCount(0)
})

test('모자라면 경고 + 그림 장을 글 장으로 → 들어감 · 끝에서 빼기 · 한 장으로 압축 = 인포그래픽 질문지', async ({ page }) => {
  await start(page, 'creditshort', 40)
  const warn = page.getByTestId('credit-short')
  await expect(warn).toContainText('남은 크레딧 40(서버 키)이 이 계획(약 60)보다 적어요')
  const fixes = warn.getByTestId('credit-fix')
  await expect(fixes).toHaveCount(2)
  await expect(fixes.nth(0)).toHaveText(/^그림 장 2개를 글 장으로 · 약 3\d$/)                  // 끝에서부터 둘을 글 장으로 — 남은 크레딧 안
  await expect(fixes.nth(1)).toHaveText(/^끝에서 \d장 빼기 · 약 \d+$/)
  await expect(warn.getByTestId('credit-one')).toHaveText('한 장으로 압축 (인포그래픽 · 약 22~32크레딧)')
  await page.locator('aside[aria-label="KAIROS 대화"]').screenshot({ path: 'test-results/credit-short.png' })
  await fixes.nth(0).click()
  await expect(page.getByTestId('slides-pic').nth(2)).toHaveAttribute('data-pic', 'false')      // 「안테나」·「집」 = 글 장
  await expect(page.getByTestId('slides-pic').nth(3)).toHaveAttribute('data-pic', 'false')
  await expect(page.getByTestId('slides-pic').nth(0)).toHaveAttribute('data-pic', 'true')
  await expect(page.getByTestId('credit-short')).toHaveCount(0)
  await expect(page.getByTestId('credit-ok')).toContainText('남은 크레딧 40')
  await expect(page.getByTestId('slides-build')).toContainText('약 31~36크레딧')               // 어림도 같이 줄어듦(그림 장 둘 × 12)

  await page.getByTestId('slides-pic').nth(2).click(); await page.getByTestId('slides-pic').nth(3).click()   // 다시 그림 장 → 다시 모자람
  await page.getByTestId('credit-short').getByTestId('credit-one').click()
  const ask = page.getByTestId('deep-ask').last()
  await expect(ask).toBeVisible()
  await expect(page.getByTestId('deep-plan-go').last()).toHaveText('그림 만들기')                // 인포그래픽 질문지(같은 주제)
})
