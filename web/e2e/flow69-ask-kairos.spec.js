// 흐름 69 — AI 입구 = 오른쪽 KAIROS 대화창 하나(2026-11-14 화면 틀 B1 5단계): 옛 ✨ AI 칩(2026-11-09)·우클릭 「AI로 만들기」를 치움.
// 고른 것 우클릭 「KAIROS에게 묻기…」 = 대화창이 열리고 입력 칸에 초점, 고른 것이 칩으로 붙음 → 말로 묻기(문서·슬라이드도 말로).
// 같은 대화에서 다른 것을 새로 골라 물으면 = 새 재료(앞 정리 문서를 고쳐 쓰지 않음). KAIROS는 가짜(/api/chat).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, toPage } from './helpers.js'

const html = t => `<!doctype html><html><head><title>${t}</title></head><body><h1>${t}</h1></body></html>`

async function twoMemos(page) {
  for (const [t, x] of [['# 송신소 점검\n- 안테나 정상', 1500], ['# 다음 할 일\n- 예비 송신기 시험', 1900]]) {
    await page.getByRole('button', { name: '메모', exact: true }).click(); await page.keyboard.type(t.replace(/\n/g, ' ')); await clickScene(page, x, 900)
  }
  return (await liveDoc(page)).items.filter(it => it.type === 'memo')
}
const rightOn = async (page, m) => { const q = await toPage(page, m.pos[0] + 60, m.pos[1] + 15); await page.mouse.click(q.x, q.y); await page.mouse.click(q.x, q.y, { button: 'right' }) }

test('물건 위 AI 칩 없음 · 우클릭 「KAIROS에게 묻기…」 = 대화창 입력 칸에 초점 + 고른 것 칩 → 말로 문서', async ({ page }) => {
  const seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { report: 'claude-opus-5-5' } } }))
  await page.route('**/api/chat', async r => { const b = r.request().postDataJSON(); seen.push(b)
    await r.fulfill({ json: { kind: 'report', content: '문서', title: '점검', html: html('점검'), model: 'claude-opus-5-5', elapsed: 1 } }) })
  await openBoard(page, boardName('askk'), { chat: false }); await setCam(page)
  const [m1, m2] = await twoMemos(page)
  await clickScene(page, m1.pos[0] + 60, m1.pos[1] + 15)
  await expect(page.getByTestId('prop-bar')).toBeVisible()
  await expect(page.getByTestId('ai-chip')).toHaveCount(0)                                   // 물건 위 AI 칩 없음
  await rightOn(page, m1)
  await expect(page.getByRole('menuitem', { name: /AI로 만들기/ })).toHaveCount(0)
  await page.getByRole('menuitem', { name: 'KAIROS에게 묻기…' }).click()
  const box = page.getByPlaceholder('물어보세요', { exact: false })
  await expect(box).toBeFocused()                                                           // 대화창이 열리고 바로 칠 수 있음
  await expect(page.getByTestId('sel-chip')).toHaveText('1개 선택됨')
  await box.fill('고른 것을 문서 한 장으로 만들어 줘'); await box.press('Enter')
  await expect(page.getByTestId('answer-kind')).toHaveText('📄 문서')
  expect(seen[0].messages.at(-1).context).toContain('안테나 정상')
  // 다른 메모를 새로 골라 물음 = 새 재료(바로 앞 답이 정리 문서여도 고쳐 쓰지 않음)
  await rightOn(page, m2); await page.getByRole('menuitem', { name: 'KAIROS에게 묻기…' }).click()
  await expect(page.getByTestId('chat-busy')).toHaveCount(0)
  await box.fill('이것도 문서 한 장으로 만들어 줘'); await box.press('Enter')
  await expect.poll(() => seen.length).toBe(2)
  expect(seen[1].messages.at(-1).context).toContain('예비 송신기 시험')
  expect(seen[1].prev_html).toBeUndefined()
  // 같은 것을 고른 채 이어 말하면 = 앞 문서 고쳐 쓰기(그대로)
  await expect(page.getByTestId('chat-busy')).toHaveCount(0)
  await box.fill('더 짧게'); await box.press('Enter')
  await expect.poll(() => seen.length).toBe(3)
  expect(seen[2].prev_html).toContain('<h1>점검</h1>')
})
