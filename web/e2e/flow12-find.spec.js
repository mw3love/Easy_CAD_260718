// 흐름 12 — 뜻으로 찾기(§8 항목61 ③-2): Ctrl+F 찾기 칸(낱말 바로·뜻은 서버)·노란 점선·Enter = 그리로 / 대화 「📌 칠판에서」 근거 고리·붙이면 점선 화살표.
// KAIROS는 가짜(/api/find·/api/chat) — 서버 쪽 계산은 tests/test_part55, 진짜 호출은 손 확인.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, clickScene, liveDoc, waitSaved } from './helpers.js'

async function memo(page, text) {   // 화면 가운데에 새 메모 — 이름표(uid)를 돌려줌
  await page.getByRole('button', { name: '메모', exact: true }).click()
  await page.keyboard.type(text); await clickScene(page, 1500, 900)
  return (await liveDoc(page)).items.filter(it => it.type === 'memo').at(-1).uid
}

test('Ctrl+F — 낱말은 바로, 뜻은 서버에서, 노란 점선, Enter = 그 메모로 가서 고름, Esc = 닫힘', async ({ page }) => {
  const name = boardName('find'), asked = []
  await openBoard(page, name); await setCam(page)
  const a = await memo(page, '송신기 이상 보고'); await memo(page, '점심 메뉴 김치찌개')
  await waitSaved(page)
  await page.route('**/api/find/**', async r => { const q = r.request().postDataJSON().q; asked.push(q)
    await r.fulfill({ json: { results: q === '송신 장비 고장' ? [{ uid: a, type: 'memo', kind: '메모', text: '송신기 이상 보고', score: 0.49 }] : [] } }) })
  await setCam(page, { x: -4000, y: -4000, z: 1 })                      // 메모가 화면 밖에 있게
  await page.keyboard.press('Control+f')
  const bar = page.getByTestId('find-bar'); await expect(bar).toBeVisible()
  await page.keyboard.type('김치')
  await expect(bar.getByTestId('find-row')).toHaveCount(1); await expect(bar.getByTestId('find-row')).toContainText('낱말')
  await expect(page.getByTestId('find-mark')).toHaveCount(1)
  await page.keyboard.press('Control+a'); await page.keyboard.type('송신 장비 고장')
  await expect(bar.getByTestId('find-row')).toHaveCount(1)               // 낱말은 안 겹치지만 뜻으로
  await expect(bar.getByTestId('find-row')).toContainText('뜻')
  expect(asked.at(-1)).toBe('송신 장비 고장')
  await page.keyboard.press('Enter')
  expect(await page.evaluate(() => window.__mb.ed.getSel())).toEqual([a])
  const box = await page.getByTestId('board').boundingBox(), cam = await page.evaluate(() => window.__mb.getCam())
  const m = (await liveDoc(page)).items.find(it => it.uid === a), cx = (m.pos[0] + m.rect[2] / 2) * cam.z + cam.x
  expect(cx).toBeGreaterThan(0); expect(cx).toBeLessThan(box.width)       // 화면 밖에 있던 메모로 날아옴
  await page.keyboard.press('Escape')
  await expect(bar).toBeHidden(); await expect(page.getByTestId('find-mark')).toHaveCount(0)
})

test('「지난번 …」 → 📌 칠판에서 · 근거 고리 = 그 메모로 · 붙이면 근거로 가는 점선 화살표', async ({ page }) => {
  const name = boardName('findchat'), seen = []
  await openBoard(page, name, { chat: true }); await setCam(page)
  const a = await memo(page, '송신기 이상 보고 — 2번 출력 저하')
  await waitSaved(page)
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', async r => { const body = r.request().postDataJSON(); seen.push(body)
    await r.fulfill({ json: { content: '2번 송신기 출력이 떨어졌어요.[칠판 1]', model: 'fake-model', elapsed: 0.3, kind: 'board', refs: [{ n: 1, uid: a, kind: '메모', text: '송신기 이상 보고 — 2번 출력 저하' }] } }) })
  await clickScene(page, 1500, 900)
  await page.getByPlaceholder('물어보세요', { exact: false }).click()
  await page.keyboard.type('지난번 송신기 문제 뭐였지?'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-kind')).toHaveText('📌 칠판에서')
  expect(seen[0].board).toBe(name)
  await expect(page.getByRole('button', { name: '웹 검색으로 다시' })).toBeVisible()
  await expect(page.getByRole('button', { name: '대화로 다시' })).toBeVisible()
  await page.getByTestId('answer-refs').getByRole('button').first().click()
  expect(await page.evaluate(() => window.__mb.ed.getSel())).toEqual([a])
  await page.getByRole('button', { name: '칠판에 붙이기' }).click()
  const d = await liveDoc(page), arrows = d.items.filter(it => it.type === 'sarrow'), memos = d.items.filter(it => it.type === 'memo')
  expect(memos).toHaveLength(2); expect(arrows).toHaveLength(1)
  expect(arrows[0].style).toBe(2)                                         // 점선
  expect(d.items[arrows[0].bind2].uid).toBe(a)                            // 근거 메모로
  expect(memos.find(x => x.uid === a).group_id).toBeFalsy()               // 근거는 묶음에 안 들어감(제자리)
})
