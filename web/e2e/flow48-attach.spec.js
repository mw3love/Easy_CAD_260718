// 흐름 48 — 대화창 첨부(2026-10-28 사용자: 대화창에 첨부자료 넣는 방법이 없음). 칠판이 곧 첨부함 —
// 「+ › 📎 파일 올리기…」·대화창에 끌어 놓기·입력 칸 Ctrl+V = 칠판 빈자리에 놓고 고른 채 → 다음 질문에 글·그림이 실림. 진짜 KAIROS는 안 부름.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc } from './helpers.js'

const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII=', 'base64')

async function fakeKairos(page, seen) {
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { seen.push(r.request().postDataJSON()); return r.fulfill({ json: { kind: 'chat', content: `읽었어요 ${seen.length}`, model: 'fake-model', elapsed: 0.1 } }) })
}
async function ask(page, q) {
  const box = page.getByPlaceholder('물어보세요', { exact: false })
  await box.click(); await page.keyboard.type(q); await page.keyboard.press('Enter')
}
const boxOf = it => ({ x: it.pos[0] + it.rect[0], y: it.pos[1] + it.rect[1], w: it.rect[2] * (it.scale || 1), h: it.rect[3] * (it.scale || 1) })
const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

test('「+ › 파일 올리기…」 = 칠판 빈자리에 놓고 고른 채 → 질문에 글·그림이 실림', async ({ page }) => {
  const name = boardName('attach'), seen = []
  await fakeKairos(page, seen)
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.getByTestId('plus').click()
  const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.getByTestId('attach').click()])
  await chooser.setFiles([{ name: '점검.md', mimeType: 'text/markdown', buffer: Buffer.from('# 점검 메모\n- 송신기 2대 교체') }, { name: '현장.png', mimeType: 'image/png', buffer: PNG }])
  await expect(page.getByTestId('sel-chip')).toHaveText('2개 선택됨')
  const its = (await liveDoc(page)).items
  expect(its.map(it => it.type).sort()).toEqual(['image', 'memo'])
  expect(overlap(boxOf(its[0]), boxOf(its[1]))).toBe(false)                // 둘 다 빈자리(겹치지 않게)
  await ask(page, '이거 뭐야?'); await expect(page.getByText('읽었어요 1')).toBeVisible()
  expect(seen[0].board_images).toHaveLength(1)                               // 그림 = 요청에만
  expect(seen[0].messages.at(-1).context).toContain('송신기 2대 교체')       // 글 = 고른 것의 글
  await expect(page.getByText('칠판에서 고른 그림 1장과 함께')).toBeVisible()
})

test('대화창에 끌어 놓기 = 점선 안내 → 칠판에 놓고 고름 · 입력 칸에 그림 붙여넣기도 같게 · 글 붙여넣기는 그대로 글', async ({ page }) => {
  const name = boardName('attach-drop'), seen = []
  await fakeKairos(page, seen)
  await openBoard(page, name, { chat: true }); await setCam(page)
  const panel = page.getByRole('complementary', { name: 'KAIROS 대화' })
  const md = await page.evaluateHandle(() => { const d = new DataTransfer(); d.items.add(new File(['# 회의\n- 결정 A'], '회의.md', { type: 'text/markdown' })); return d })
  await panel.dispatchEvent('dragover', { dataTransfer: md })
  await expect(page.getByTestId('chat-drop')).toBeVisible()
  await panel.dispatchEvent('drop', { dataTransfer: md })
  await expect(page.getByTestId('chat-drop')).toHaveCount(0)
  await expect(page.getByTestId('sel-chip')).toHaveText('1개 선택됨')
  expect(page.url()).toContain(name)                                         // 브라우저가 파일로 떠나지 않음
  expect((await liveDoc(page)).items.map(it => it.type)).toEqual(['memo'])

  const box = page.getByPlaceholder('물어보세요', { exact: false })
  await box.evaluate(el => { const d = new DataTransfer(); d.items.add(new File([Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII='), c => c.charCodeAt(0))], 'shot.png', { type: 'image/png' }))
    el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: d, bubbles: true, cancelable: true })) })
  await expect(page.getByTestId('sel-chip')).toHaveText('1개 선택됨')        // 새로 놓은 그림만 고른 채
  await expect.poll(async () => (await liveDoc(page)).items.map(it => it.type).sort()).toEqual(['image', 'memo'])
  await expect(box).toHaveValue('')

  await box.evaluate(el => { const d = new DataTransfer(); d.setData('text/plain', '그냥 글'); el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: d, bubbles: true, cancelable: true })) })
  expect((await liveDoc(page)).items).toHaveLength(2)                        // 글은 칠판에 안 놓음(입력 칸 몫)
})
