// 흐름 46 — 칠판 QR(2026-10-28 대회 시연): 공유 창 「QR 크게」 = 이 주소 + 칠판 코드 · 게시 탭 = 보기 링크(코드 없음) · 발표 중 Q = TV에 크게(Esc는 QR만 닫음)
// · 칠판 판 「칠판 코드로 열기」 = 코드 8자(대문자·띄어 써도) → 그 칠판, 없는 코드 = 알림. QR 내용은 같은 계산(`qrpath.js`)으로 되만들어 대조(진짜 풀기는 🖼 캡처 + OpenCV로 따로)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, dragScene, waitSaved } from './helpers.js'
import { qrPath } from '../src/next/qrpath.js'

const ABC = 'abcdefghjkmnpqrstuvwxyz23456789'
const code8 = () => Array.from({ length: 8 }, () => ABC[Math.floor(Math.random() * ABC.length)]).join('')

const qrShows = async (page, link) => {   // 큰 QR이 그 주소를 담았나 — 글(data-qr)과 검은 칸 경로 둘 다
  const svg = page.getByTestId('qr-svg')
  await expect(svg).toHaveAttribute('data-qr', link)
  expect(await svg.locator('path').getAttribute('d')).toBe(qrPath(link).d)
}

test('공유 「QR 크게」 · 게시 QR · 발표 중 Q · 칠판 코드로 열기', async ({ page, browser }) => {
  const code = code8(), name = `${boardName('qr')}-${code}`
  await openBoard(page, name); await setCam(page, { x: 320, y: 300, z: 0.5 })
  await page.getByRole('button', { name: '프레임', exact: true }).click()
  await dragScene(page, { x: 0, y: 0 }, { x: 400, y: 240 })
  await waitSaved(page)
  const origin = new URL(page.url()).origin, board = `${origin}/?board=${name}`

  // 공유 탭 = 이 주소 + 칠판 코드
  await page.getByRole('button', { name: '공유' }).click()
  await page.getByTestId('qr-btn').click()
  await expect(page.getByTestId('qr-big')).toBeVisible()
  await qrShows(page, board)
  await expect(page.getByTestId('qr-code')).toHaveText(`${code.slice(0, 4)} ${code.slice(4)}`)
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('qr-big')).toHaveCount(0)
  await expect(page.getByTestId('share-open')).toBeVisible()                        // Esc = QR만 닫힘(공유 창은 그대로)

  // 발표 중 Q — 게시 전 = 같이 고치는 주소
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: '발표', exact: true }).click()
  await expect(page.getByTestId('presenter')).toBeVisible()
  await page.keyboard.press('q')
  await qrShows(page, board)
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('qr-big')).toHaveCount(0)
  await expect(page.getByTestId('presenter')).toBeVisible()                         // 발표는 그대로
  await page.keyboard.press('Escape'); await expect(page.getByTestId('presenter')).toBeHidden()

  // 게시 탭 = 보기 링크, 코드 없음(코드는 고치는 칠판의 열쇠)
  await page.getByRole('button', { name: '공유' }).click()
  await page.getByTestId('share-tab-publish').click()
  await page.getByRole('button', { name: '게시하기' }).click()
  const view = await page.locator('input[readonly]').first().inputValue()
  expect(view).toContain('/?view=')
  await page.getByTestId('qr-btn').click()
  await qrShows(page, view)
  await expect(page.getByTestId('qr-code')).toHaveCount(0)
  await page.getByTestId('qr-big').click()                                          // 눌러도 닫힘
  await expect(page.getByTestId('qr-big')).toHaveCount(0)
  await page.keyboard.press('Escape')

  // 게시한 뒤 발표 중 Q = 보기 링크
  await page.getByRole('button', { name: '발표', exact: true }).click()
  await page.keyboard.press('q')
  await qrShows(page, view)
  await page.keyboard.press('q'); await expect(page.getByTestId('qr-big')).toHaveCount(0)   // Q 한 번 더 = 닫기
  await page.keyboard.press('Escape')

  // 다른 브라우저에서 칠판 코드로 열기 — 대문자·띄어 쓴 코드도
  const c2 = await browser.newContext(), p2 = await c2.newPage()
  await openBoard(p2, boardName('qr2'))
  await p2.getByTestId('dock-board').click()
  await p2.getByTestId('board-code-open').click()
  await p2.getByTestId('board-code').fill('zzzz zzzz')                              // 없는 코드
  await p2.keyboard.press('Enter')
  await expect(p2.getByTestId('board-code-why')).toBeVisible()
  await p2.getByTestId('board-code').fill(`${code.slice(0, 4).toUpperCase()} ${code.slice(4)}`)
  await p2.keyboard.press('Enter')
  await expect(p2).toHaveURL(`${origin}/?board=${name}`)
  await c2.close()
})
