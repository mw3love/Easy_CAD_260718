// 흐름 10 — 한글 입력기(IME) 첫 글자: 도형·표 칸을 고른 채 바로 한글을 치면 첫 글자가 빠지거나 겹치지 않음.
// Playwright 글쇠(type)는 조합 없이 완성 글자만 넣어서, 크롬 개발자 기능(CDP)으로 실제 입력기 순서를 흉내 낸다:
// keydown 「Process」(229) → 조합 중(ㅎ → 하 → 한) → 확정. 실제 MS 입력기와 완전히 같지는 않음(마지막 손맛은 사람 몫).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, liveDoc } from './helpers.js'

async function imeType(page, cdp, syllables) {   // syllables = [['ㅎ','하','한'], ['ㄱ','그','글']] — 글자마다 조합 단계
  for (const steps of syllables) {
    for (const t of steps) {
      await cdp.send('Input.dispatchKeyEvent', { type: 'rawKeyDown', key: 'Process', code: '', windowsVirtualKeyCode: 229, nativeVirtualKeyCode: 229 })
      await cdp.send('Input.imeSetComposition', { text: t, selectionStart: t.length, selectionEnd: t.length })
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Process', code: '', windowsVirtualKeyCode: 229, nativeVirtualKeyCode: 229 })
    }
    await cdp.send('Input.insertText', { text: steps.at(-1) })
  }
}
const HAN = [['ㅎ', '하', '한'], ['ㄱ', '그', '글']]

test('상자를 고른 채 바로 한글 — 「한글」 그대로', async ({ page }) => {
  await openBoard(page, boardName('ime')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 160, y: 80 })
  const cdp = await page.context().newCDPSession(page)
  await imeType(page, cdp, HAN)
  await clickScene(page, 700, 500)
  const r = (await liveDoc(page)).items.find(it => it.type === 'rect')
  expect(r.label?.text).toBe('한글')
})

test('이미 고른 상자를 눌러 끌고 난 뒤 바로 한글 — 「한글」 그대로', async ({ page }) => {
  await openBoard(page, boardName('ime2')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 160, y: 80 })
  await dragScene(page, { x: 80, y: 40 }, { x: 120, y: 60 })   // 이미 고른 상자를 눌러 끎 — 누르는 순간 포커스가 칠판으로 빠졌다가 손을 떼면 돌아와야 함(10-19 고친 버그)
  const cdp = await page.context().newCDPSession(page)
  await imeType(page, cdp, HAN)
  await clickScene(page, 700, 500)
  const r = (await liveDoc(page)).items.find(it => it.type === 'rect')
  expect(r.pos).toEqual([40, 20])
  expect(r.label?.text).toBe('한글')
})

test('표 칸을 고른 채 바로 한글 — 「한글」 그대로', async ({ page }) => {
  await openBoard(page, boardName('ime3')); await setCam(page)
  await page.getByRole('button', { name: '표', exact: true }).click()
  await page.getByRole('button', { name: '넣기', exact: true }).click()
  const t = (await liveDoc(page)).items.find(it => it.type === 'table')
  const [x, y] = t.pos, [, , w, h] = t.rect
  await clickScene(page, 700, 500); await clickScene(page, x + w / 6, y + h / 6)   // 표 고르기
  await clickScene(page, x + w / 6, y + h / 6)                                      // 첫 칸 고르기
  const cdp = await page.context().newCDPSession(page)
  await imeType(page, cdp, HAN)
  await clickScene(page, 700, 500)
  const back = (await liveDoc(page)).items.find(it => it.type === 'table')
  expect(back.cells[0][0]).toBe('한글')
})
