// 흐름 16 — 「정리해 줘」 ①(§8 항목61): 고른 메모 → 📄 정리 문서(대화창 미리보기) → 칠판에 붙이기 = 문서 카드(칸 안에 그 문서) → 「더 짧게」 = 앞 문서 고치기
// → 우클릭 「정리 문서 만들기」도 같은 길 → 새로고침해도 그대로 → ↗ 크게 보기 = 새 탭. KAIROS는 가짜(/api/chat) — 서버는 tests/test_part61, 진짜는 손 확인.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, waitSaved, toPage } from './helpers.js'

const html = t => `<!doctype html><html><head><title>${t}</title></head><body style="font-family:sans-serif"><h1>${t}</h1><p>2번 송신기 출력 70%</p></body></html>`

test('정리해 줘 → 📄 미리보기 → 문서 카드 → 더 짧게 = 고쳐 쓰기 → 우클릭으로도 → 새로고침 → 크게 보기', async ({ page }) => {
  const name = boardName('report'), seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b)
    const t = b.prev_html ? '짧은 브리핑' : '회의 브리핑'
    await r.fulfill({ json: { kind: 'report', content: `정리 문서 「${t}」 — 칠판에 붙이면 인쇄용 문서 카드가 돼요`, title: t, html: html(t), model: 'claude-opus-5-5', elapsed: 41 } }) })
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.getByRole('button', { name: '메모', exact: true }).click()
  await page.keyboard.type('송신기 이상 보고'); await clickScene(page, 1500, 900)
  const memo = (await liveDoc(page)).items.find(it => it.type === 'memo')
  await clickScene(page, memo.pos[0] + 60, memo.pos[1] + 15)   // 메모 고르기 = 재료

  await page.getByPlaceholder('물어보세요', { exact: false }).click()
  await page.keyboard.type('이거 정리해 줘'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-kind')).toHaveText('📄 정리 문서')
  await expect(page.getByTestId('answer-doc').locator('iframe')).toHaveAttribute('srcdoc', /회의 브리핑/)
  expect(JSON.stringify(seen[0].messages.at(-1).context || '')).toContain('송신기 이상 보고')
  expect(seen[0].prev_html).toBeUndefined()

  await page.getByRole('button', { name: '칠판에 붙이기' }).click()
  let d = await liveDoc(page)
  const card = d.items.find(it => it.type === 'doc')
  expect(card.title).toBe('회의 브리핑'); expect(card.html).toContain('<h1>회의 브리핑</h1>')
  expect(card.rect[3] / card.rect[2]).toBeGreaterThan(1.4)                         // A4 세로 비율
  await expect(page.locator(`iframe[data-docid="${card.uid}"]`)).toHaveCount(1)   // 칸 안에 그 문서(스크립트 없는 iframe)
  await expect(page.locator(`iframe[data-docid="${card.uid}"]`)).toHaveAttribute('sandbox', '')

  await page.getByPlaceholder('물어보세요', { exact: false }).click()
  await page.keyboard.type('더 짧게'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-kind').last()).toHaveText('📄 정리 문서')
  expect(seen[1].prev_html).toContain('<h1>회의 브리핑</h1>')                       // 바로 앞 문서를 바탕으로

  await clickScene(page, 1500, 900)
  const p = await toPage(page, memo.pos[0] + 60, memo.pos[1] + 15)
  await page.mouse.click(p.x, p.y); await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.getByRole('button', { name: '정리 문서 만들기 (KAIROS)' }).click()
  await expect.poll(() => seen.length).toBe(3)
  expect(seen[2].kind).toBe('report')

  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()
  d = await liveDoc(page)
  expect(d.items.find(it => it.type === 'doc').html).toContain('<h1>회의 브리핑</h1>')
  const c2 = d.items.find(it => it.type === 'doc'), ob = await toPage(page, c2.pos[0] + c2.rect[2] - 20, c2.pos[1] + 20)
  const popup = page.waitForEvent('popup')
  await page.mouse.click(ob.x, ob.y)                                                 // ↗ 크게 보기
  const tab = await popup
  await expect(tab.locator('h1')).toHaveText('회의 브리핑')
})
