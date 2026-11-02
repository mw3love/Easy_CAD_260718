// 흐름 55 — 다른 물건으로 바꾸기(2026-11-02 사용자: 「네모에 적은 글을 제대로 된 메모로 키우고 싶을 때」).
// 같은 이름표(_id)라 붙은 화살표가 그대로, Ctrl+Z 한 번. 입구 = 속성 카드 머리말 목록 맨 위 · 우클릭.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, clickScene, pickShape, dragScene, toPage } from './helpers.js'

const byText = (doc, t) => doc.items.find(it => it.label?.text === t || it.lines?.[0]?.t === t || it.text === t)

test('네모 글 → 메모(화살표 그대로·자리 가운데·Ctrl+Z 한 번) · 메모 → 사각형·글 상자 · 우클릭에도', async ({ page }) => {
  await openBoard(page, boardName('convert')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 100, y: 100 }, { x: 220, y: 180 })
  await page.keyboard.type('- 송신기\n- 예비기'); await page.keyboard.press('Escape'); await page.keyboard.press('Escape')
  await pickShape(page, '사각형'); await dragScene(page, { x: 500, y: 100 }, { x: 620, y: 180 })
  await page.keyboard.type('안테나'); await page.keyboard.press('Escape'); await page.keyboard.press('Escape')
  // 화살표: 화살표 도구로 앞 상자 안 → 뒤 상자 안(붙음)
  const box = byText(await liveDoc(page), '- 송신기\n- 예비기'); expect(box?.type).toBe('rect')
  await clickScene(page, 800, 500); await page.keyboard.press('2')
  await dragScene(page, { x: 160, y: 140 }, { x: 560, y: 140 }); await page.keyboard.press('Escape')
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'sarrow').length).toBe(1)
  const center = box.pos[0] + box.rect[2] / 2

  // 속성 카드 머리말 → 목록 맨 위 「메모로 바꾸기」
  await clickScene(page, 160, 140)
  await page.getByTitle('클릭: 다른 도형으로 바꾸기', { exact: false }).click()
  const list = page.getByTestId('pop-swap'), first = list.locator('button').first()
  await expect(first).toHaveAttribute('data-testid', 'convert-memo')
  await first.click()
  let d = await liveDoc(page), m = d.items.find(it => it.uid === box.uid)
  expect(m.type).toBe('memo')
  expect(m.lines.map(l => [l.k, l.t])).toEqual([['ul', '송신기'], ['ul', '예비기']])   // 꾸밈 없는 글 = 마크다운으로 읽어 목록
  expect(Math.abs(m.pos[0] + m.rect[2] / 2 - center)).toBeLessThan(1)                    // 가운데 그대로(옆 도형을 덮지 않게)
  expect(m.rect[2]).toBeLessThan(340)
  const arrow = d.items.find(it => it.type === 'sarrow'); expect(d.items[arrow.bind1]?.uid).toBe(box.uid)  // 화살표는 붙은 채(bind = 파일 속 순서)
  await page.keyboard.press('Control+z')
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.uid === box.uid).type).toBe('rect')
  await page.keyboard.press('Control+y')
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.uid === box.uid).type).toBe('memo')

  // 메모 = 머리말이 「다른 물건으로」 목록(사각형·글 상자)
  await page.getByTitle('클릭: 다른 물건으로 바꾸기', { exact: false }).click()
  await expect(page.getByTestId('pop-swap').locator('button')).toHaveCount(2)
  await page.getByTestId('convert-rect').click()
  d = await liveDoc(page); m = d.items.find(it => it.uid === box.uid)
  expect(m.type).toBe('rect'); expect(m.label.text).toBe('• 송신기\n• 예비기'); expect(m.label.align).toBe('left')

  // 우클릭에도 — 「안테나」 → 메모
  const ant = byText(d, '안테나'), p = await toPage(page, ant.pos[0] + 60, ant.pos[1] + 40)
  await page.mouse.click(p.x, p.y); await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.getByRole('button', { name: '메모로 바꾸기' }).click()
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.uid === ant.uid).type).toBe('memo')
  // 메모 → 글 상자
  await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.getByRole('button', { name: '글 상자로 바꾸기' }).click()
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.uid === ant.uid)?.type).toBe('text')
  expect((await liveDoc(page)).items.find(it => it.uid === ant.uid).text).toBe('안테나')
})
