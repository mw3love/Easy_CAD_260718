// 흐름 13 — 회의록(§8 항목61 ③-3): 녹음 끌어 놓기 → 「만드는 중」 점선 틀 → 프레임 + 요약 메모(할 일 체크) + 접힌 전문 메모 → 「… 줄 더」 = 펼침.
// 그 밖 파일을 떨어뜨려도 칠판을 안 떠남. KAIROS는 가짜(/api/meeting) — 서버 계산은 tests/test_part56, 진짜 받아쓰기는 손 확인.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage } from './helpers.js'

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
  await dropFile(page, 'notes.txt', 'text/plain', 100, 100)
  await expect(page.getByText('칠판엔 그림·녹음·PDF·HTML 파일을').first()).toBeVisible()
  expect(page.url()).toBe(url0)

  await dropFile(page, '10월 회의.m4a', 'audio/mp4', 0, 0)
  await expect(page.getByTestId('meeting-pending')).toBeVisible()
  expect(decodeURIComponent(posts[0].file)).toBe('10월 회의.m4a')
  await expect(page.getByTestId('meeting-pending')).toBeHidden({ timeout: 10_000 })
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
