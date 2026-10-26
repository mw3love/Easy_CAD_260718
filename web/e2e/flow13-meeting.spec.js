// 흐름 13 — 회의록(§8 항목61 ③-3): 녹음 끌어 놓기 → 「만드는 중」 점선 틀 → 프레임 + 요약 메모(할 일 체크) + 접힌 전문 메모 → 「… 줄 더」 = 펼침.
// 그 밖 파일을 떨어뜨려도 칠판을 안 떠남. KAIROS는 가짜(/api/meeting) — 서버 계산은 tests/test_part56, 진짜 받아쓰기는 손 확인.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage, pickShape, dragScene } from './helpers.js'

const TURNS = Array.from({ length: 12 }, (_, i) => ({ speaker: `화자 ${(i % 2) + 1}`, start_ms: i * 15000, text: `${i + 1}번째 발언 — 송신기 교체 이야기` }))
const RESULT = { title: '송신기 교체 회의', summary: '2번 송신기 출력 저하로 교체를 논의했어요.', decisions: ['2번 송신기 교체'], todos: [{ who: '김 차장', what: '견적 받기', due: '금요일' }],
  next: '10월 26일 오후 2시', turns: TURNS, duration: 180, credits: 18, model: 'fake-model' }

async function dropFile(page, name, type, x, y) {
  const p = await toPage(page, x, y)
  await page.evaluate(([name, type, cx, cy]) => {
    const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array([82, 73, 70, 70, 0, 0])], name, { type }))
    document.querySelector('[data-testid=board]').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, clientX: cx, clientY: cy, bubbles: true, cancelable: true }))
  }, [name, type, p.x, p.y])
}

test('녹음 끌어 놓기 → 만드는 중 → 프레임 + 요약 + 접힌 전문 → 펼치기 · 다른 파일은 칠판을 안 떠남', async ({ page }) => {
  const name = boardName('meeting'), posts = []
  let polls = 0
  await page.route('**/api/meeting/**', async r => {
    if (r.request().method() === 'POST') { posts.push({ url: r.request().url(), file: r.request().headers()['x-file-name'] }); return r.fulfill({ json: { job: 'abcdef123456' } }) }
    polls++; await r.fulfill({ json: polls < 2 ? { status: 'run', msg: '받아쓰는 중… 3초' } : { status: 'done', msg: '끝', result: RESULT } })
  })
  await openBoard(page, name); await setCam(page)
  const url0 = page.url()
  await dropFile(page, 'notes.docx', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 100, 100)
  await expect(page.getByText('칠판엔 그림·녹음·PDF·HTML·md·txt 파일을').first()).toBeVisible()
  expect(page.url()).toBe(url0)

  await dropFile(page, '10월 회의.m4a', 'audio/mp4', 0, 0)
  await expect(page.locator('[data-testid="board-skeleton"][data-kind="meeting"]')).toBeVisible()
  expect(decodeURIComponent(posts[0].file)).toBe('10월 회의.m4a')
  await expect(page.locator('[data-testid="board-skeleton"][data-kind="meeting"]')).toBeHidden({ timeout: 10_000 })
  const d = await liveDoc(page)
  const frame = d.items.find(it => it.type === 'frame'), memos = d.items.filter(it => it.type === 'memo')
  expect(frame.name).toContain('송신기 교체 회의')
  const sum = memos.find(m => m.lines[0].t === '송신기 교체 회의'), full = memos.find(m => m.fold === true)
  expect(sum.lines.map(l => l.k)).toEqual(['h2', 'p', 'h3', 'ul', 'h3', 'todo', 'h3', 'p', 'p'])
  expect(sum.lines.find(l => l.k === 'todo').t).toBe('김 차장 — 견적 받기 (금요일)')
  expect(full.lines).toHaveLength(13)                                          // 제목 + 12구간 — 다 들어 있고 보이는 건 앞 6줄
  expect(full.lines[2].t).toBe('[00:15] 화자 2: 2번째 발언 — 송신기 교체 이야기')
  const fb = [frame.pos[0], frame.pos[1], frame.rect[2], frame.rect[3]]
  for (const m of memos) { expect(m.pos[0]).toBeGreaterThanOrEqual(fb[0]); expect(m.pos[1] + m.rect[3]).toBeLessThanOrEqual(fb[1] + fb[3]) }   // 프레임 안
  const h0 = full.rect[3]
  await expect(page.locator('[data-memo-more=open]')).toHaveCount(1)
  const mb = await page.locator('[data-memo-more=open]').boundingBox()
  await page.mouse.click(mb.x + 20, mb.y + mb.height / 2)
  const f2 = (await liveDoc(page)).items.find(it => it.uid === full.uid)
  expect(f2.fold).toBe(false); expect(f2.rect[3]).toBeGreaterThan(h0 * 1.5)  // 펼침
  await expect(page.locator('[data-memo-more=close]')).toHaveCount(1)          // 「▴ 접기」
})

test('녹음을 다른 물건 위에 놓으면 회의록은 가까운 빈자리로(겹치지 않음, 2026-10-26 시연 캡처)', async ({ page }) => {
  await page.route('**/api/meeting/**', async r => r.request().method() === 'POST' ? r.fulfill({ json: { job: 'abcdef123456' } }) : r.fulfill({ json: { status: 'done', msg: '끝', result: RESULT } }))
  await openBoard(page, boardName('meetgap')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 300, y: 200 }); await page.keyboard.press('Escape')
  await dropFile(page, '회의.m4a', 'audio/mp4', 50, 50)
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'frame').length, { timeout: 10_000 }).toBe(1)
  const d = await liveDoc(page), fr = d.items.find(it => it.type === 'frame'), rc = d.items.find(it => it.type === 'rect')
  const ov = !(fr.pos[0] >= rc.pos[0] + rc.rect[2] || fr.pos[0] + fr.rect[2] <= rc.pos[0] || fr.pos[1] >= rc.pos[1] + rc.rect[3] || fr.pos[1] + fr.rect[3] <= rc.pos[1])
  expect(ov).toBe(false)
  for (const m of d.items.filter(it => it.type === 'memo')) { expect(m.pos[0]).toBeGreaterThanOrEqual(fr.pos[0]); expect(m.pos[1]).toBeGreaterThanOrEqual(fr.pos[1]) }   // 요약·전문도 같이 옮겨 프레임 안
})

test('빈자리가 화면 밖이면 화면이 회의록으로 따라감(2026-10-26 점검 — 만들어졌는데 안 보였음)', async ({ page }) => {
  await page.route('**/api/meeting/**', async r => r.request().method() === 'POST' ? r.fulfill({ json: { job: 'abcdef123456' } }) : r.fulfill({ json: { status: 'done', msg: '끝', result: RESULT } }))
  await openBoard(page, boardName('meetfollow')); await setCam(page)
  const box = await page.getByTestId('board').boundingBox()
  await pickShape(page, '사각형'); await dragScene(page, { x: -380, y: -180 }, { x: box.width - 440, y: box.height - 230 }); await page.keyboard.press('Escape')   // 보이는 칠판을 큰 상자로 꽉 채움
  await dropFile(page, '회의.m4a', 'audio/mp4', 50, 50)
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'frame').length, { timeout: 10_000 }).toBe(1)
  const fr = (await liveDoc(page)).items.find(it => it.type === 'frame')
  await expect.poll(async () => { const c = await page.evaluate(() => window.__mb.getCam()), x = fr.pos[0] * c.z + c.x, y = fr.pos[1] * c.z + c.y
    return x >= 0 && x < box.width && y >= 0 && y < box.height }).toBe(true)   // 프레임 왼쪽 위가 화면 안
})
