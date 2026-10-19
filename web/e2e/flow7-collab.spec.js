// 흐름 7 — 공동작업 1.5단계: 둘이 같은 칠판(롱 폴링으로 바로 보임)·서로 다른 도형 동시에 고쳐도 둘 다 남음·「고치는 중」 표시·게시 링크는 보기만
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, pickShape, dragScene, clickScene, liveDoc, waitSaved, savedDoc } from './helpers.js'

const rects = d => d.items.filter(it => it.type === 'rect')

test('둘이 같은 칠판 — 바로 보이고, 동시에 고쳐도 둘 다 남고, 고치는 중이 보임', async ({ browser }) => {
  const name = boardName('collab')
  const ca = await browser.newContext(), cb = await browser.newContext()
  const a = await ca.newPage(), b = await cb.newPage()
  await openBoard(a, name, { who: '기자' }); await setCam(a)
  await openBoard(b, name, { who: '작가' }); await setCam(b)

  await pickShape(a, '사각형'); await dragScene(a, { x: 0, y: 0 }, { x: 160, y: 80 }); await clickScene(a, 700, 500)
  await expect.poll(async () => rects(await liveDoc(b)).length, { timeout: 3000 }).toBe(1)   // 롱 폴링 — 1초 안팎

  // 동시에: A는 새 상자, B는 A의 상자에 글
  await clickScene(b, 80, 40); await b.keyboard.type('작가 메모')
  await pickShape(a, '사각형'); await dragScene(a, { x: 300, y: 0 }, { x: 460, y: 80 })
  await expect(a.getByTestId('other-mark').first()).toBeAttached({ timeout: 3000 })      // A 화면에 「작가 고치는 중」
  await expect(a.getByTestId('other-mark').first()).toContainText('작가')
  await clickScene(b, 700, 500); await clickScene(a, 700, 500)
  for (const p of [a, b]) {
    await expect.poll(async () => { const d = await liveDoc(p); return [rects(d).length, JSON.stringify(d).includes('작가 메모')] }, { timeout: 4000 }).toEqual([2, true])
  }
  await waitSaved(a); await waitSaved(b)
  await expect.poll(() => { const d = savedDoc(name); return d && [rects(d).length, JSON.stringify(d).includes('작가 메모')] }, { timeout: 4000 }).toEqual([2, true])
  await ca.close(); await cb.close()
})

test('게시 링크 — 로그인 없이 보이고, 고치는 도구는 없고, 고친 것이 바로 따라옴', async ({ browser }) => {
  const name = boardName('publish')
  const ca = await browser.newContext(), a = await ca.newPage()
  await openBoard(a, name); await setCam(a)
  await pickShape(a, '사각형'); await dragScene(a, { x: 0, y: 0 }, { x: 160, y: 80 })
  await a.keyboard.type('첫 장'); await clickScene(a, 700, 500); await waitSaved(a)
  await a.getByRole('button', { name: '공유', exact: true }).click()
  await a.getByTestId('share-tab-publish').click()
  await a.getByRole('button', { name: '게시하기' }).click()
  const link = await a.locator('input[readonly]').inputValue()
  expect(link).toContain('/?view=')

  const cv = await browser.newContext(), v = await cv.newPage()
  await v.goto(link)
  await expect(v.getByTestId('view-present')).toBeVisible()
  await expect(v.getByRole('button', { name: '메모', exact: true })).toHaveCount(0)   // 고치는 도구 없음
  await expect(v.locator('text=첫 장').first()).toBeAttached()
  await a.keyboard.press('Escape')
  await clickScene(a, 80, 40); await a.keyboard.type('고친 장'); await clickScene(a, 700, 500)
  await expect(v.locator('text=고친 장').first()).toBeAttached({ timeout: 4000 })
  await ca.close(); await cv.close()
})
