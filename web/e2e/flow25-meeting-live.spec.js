// 흐름 25 — 「🎙 회의」 실시간 회의록(2026-10-23): 위 막대 「회의」 → 점선 틀에 말한 사람별 글이 쌓임 → 60분 상한으로 연결이 닫혀도 새 표로 다시 붙고 시간은 이어짐
// → 「끝내기」 = 남은 말 받고 서버 요약(/api/meeting/<칠판>/live) → 파일 회의록과 같은 프레임. 새로 열면 받아 적던 회의가 「정리하기 · 버리기」로 살아남음.
// 마이크 = 크롬 가짜 장치, KAIROS 소켓 = Playwright routeWebSocket 가짜(Soniox 실시간 형식). 진짜 KAIROS·진짜 목소리는 손 확인.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc } from './helpers.js'

test.use({ launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] }, permissions: ['microphone'] })

const tok = (text, speaker, s, e, fin = true) => ({ text, speaker, start_ms: s, end_ms: e, is_final: fin })
const RESULT = turns => ({ title: '송신소 점검 일정', summary: '점검 날짜를 정했어요.', decisions: ['수요일 10시'], todos: [{ who: '화자 2', what: '예비 부품 목록', due: '금요일' }], next: '',
  turns, duration: 0, credits: null, model: 'fake-model' })

async function fakeKairos(page) {
  const k = { tokens: 0, configs: [], audio: [0], sockets: [], posts: [] }
  await page.route('**/api/stt-token', r => { k.tokens++; return r.fulfill({ json: { url: `ws://127.0.0.1:5291/fake-stt?token=t${k.tokens}`, model: 'stt-rt-v5' } }) })
  await page.routeWebSocket('**/fake-stt**', ws => {
    const n = k.sockets.length; k.sockets.push(ws); k.audio[n] = 0
    ws.onMessage(m => {
      if (typeof m === 'string' && m.startsWith('{')) { k.configs.push(JSON.parse(m)); return }
      if (m === '') { ws.send(JSON.stringify({ tokens: [tok(' 마지막 말입니다.', '2', 9000, 9800)], finished: true })); return }
      k.audio[n] += m.length
    })
  })
  await page.route('**/api/meeting/**', async r => {
    if (r.request().method() === 'POST') { k.posts.push({ url: r.request().url(), body: r.request().postDataJSON() }); return r.fulfill({ json: { job: 'abcdef123456' } }) }
    const segs = k.posts.at(-1).body.segments
    await r.fulfill({ json: { status: 'done', msg: '끝', result: RESULT(segs.map(g => ({ speaker: g.speaker.replace('Speaker ', '화자 '), start_ms: g.start_ms, text: g.text }))) } })
  })
  return k
}

test('회의 → 화자별 글 → 연결 닫혀도 다시 붙음 → 끝내기 = 회의록 프레임', async ({ page }) => {
  const name = boardName('meetlive'), k = await fakeKairos(page)
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '회의', exact: true }).click()
  await expect.poll(() => k.configs.length).toBe(1)
  expect(k.configs[0]).toMatchObject({ model: 'stt-rt-v5', enable_speaker_diarization: true, language_hints: ['ko'] })
  const live = page.getByTestId('meeting-live')
  await expect(live).toHaveAttribute('data-state', 'listen')
  await expect(page.getByRole('button', { name: '끝내기' }).first()).toBeVisible()
  await expect.poll(() => k.audio[0]).toBeGreaterThan(0)                         // 가짜 마이크 소리가 소켓으로 감

  const s0 = k.sockets[0]
  s0.send(JSON.stringify({ tokens: [tok('오늘 회의는', '1', 0, 900), tok(' 점검 일정입니다.', '1', 900, 2000), tok(' 화요일', '2', 2100, 2600, false)] }))
  await expect(live).toContainText('[00:00] 화자 1: 오늘 회의는 점검 일정입니다.')
  await expect(live).toContainText('화요일')                                     // 임시 글도 흐리게 보임
  s0.send(JSON.stringify({ tokens: [tok('수요일 오전이 좋겠습니다.', '2', 2100, 4000)] }))
  await expect(live).toContainText('화자 2: 수요일 오전이 좋겠습니다.')
  expect((await liveDoc(page)).items).toHaveLength(0)                            // 받아 적는 동안은 문서에 안 넣음

  const sent0 = k.audio[0]
  await s0.close({ code: 1000, reason: 'session cap' })                          // KAIROS 한 연결 60분 상한
  await expect.poll(() => k.sockets.length).toBe(2)
  expect(k.tokens).toBe(2)
  await expect(live).toHaveAttribute('data-state', 'listen')
  await expect.poll(() => k.audio[1]).toBeGreaterThan(0)
  k.sockets[1].send(JSON.stringify({ tokens: [tok('제가 준비하겠습니다.', '1', 0, 1500)] }))   // 새 연결은 0부터 — 앞 연결 소리만큼 밀림
  await expect(live).toContainText('제가 준비하겠습니다.')

  await page.getByTestId('meeting-live-end').click()
  await expect(page.getByTestId('meeting-live')).toBeHidden({ timeout: 10_000 })
  await expect.poll(async () => (await liveDoc(page)).items.length, { timeout: 10_000 }).toBe(3)
  const segs = k.posts[0].body.segments
  expect(k.posts[0].url).toContain(`/api/meeting/${name}/live`)
  expect(segs.map(g => g.speaker)).toEqual(['Speaker 1', 'Speaker 2', 'Speaker 1', 'Speaker 2'])
  expect(segs[2].start_ms).toBe(Math.round(sent0 / 2 / 24000 * 1000))           // 바이트 → 16비트 샘플 → 밀리초
  expect(segs[3].text).toBe('마지막 말입니다.')                                    // 「끝내기」 뒤 남은 말까지
  const d = await liveDoc(page), frame = d.items.find(it => it.type === 'frame'), full = d.items.find(it => it.type === 'memo' && it.fold)
  expect(frame.name).toContain('송신소 점검 일정')
  expect(full.lines[1].t).toBe('[00:00] 화자 1: 오늘 회의는 점검 일정입니다.')
  await expect(page.getByRole('button', { name: '회의', exact: true })).toBeVisible()
  expect(await page.evaluate(n => localStorage.getItem(`mb-meet:${n}`), name)).toBeNull()   // 다 만들면 임시 저장도 지움
})

test('받아 적던 회의는 새로 열어도 남음 → 정리하기 / 버리기', async ({ page }) => {
  const name = boardName('meetsave'), k = await fakeKairos(page)
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '회의', exact: true }).click()
  await expect.poll(() => k.sockets.length).toBe(1)
  k.sockets[0].send(JSON.stringify({ tokens: [tok('창이 닫히기 전 말', '1', 0, 900)] }))
  await expect(page.getByTestId('meeting-live')).toContainText('창이 닫히기 전 말')
  await expect.poll(() => page.evaluate(n => localStorage.getItem(`mb-meet:${n}`), name), { timeout: 6000 }).toContain('창이 닫히기 전 말')   // 3초마다 임시 저장
  await page.reload()
  const live = page.getByTestId('meeting-live')
  await expect(live).toHaveAttribute('data-state', 'saved')
  await expect(live).toContainText('받아 적던 회의 · 1구간')
  await expect(page.getByRole('button', { name: '정리하기' }).first()).toBeVisible()
  await page.getByTestId('meeting-live-drop').click()
  await expect(live).toBeHidden()
  expect(await page.evaluate(n => localStorage.getItem(`mb-meet:${n}`), name)).toBeNull()

  await page.evaluate(n => localStorage.setItem(`mb-meet:${n}`, JSON.stringify({ at: { x: 0, y: 0 }, s: 1, t0: Date.now(), dur: 5, segs: [{ speaker: '1', text: '되살린 말', start_ms: 0, end_ms: 900 }] })), name)
  await page.reload()
  await page.getByTestId('meeting-live-end').click()                              // 「정리하기」 = 바로 요약
  await expect.poll(async () => (await liveDoc(page)).items.length, { timeout: 10_000 }).toBe(3)
  expect(k.posts.at(-1).body).toMatchObject({ duration: 5, segments: [{ speaker: 'Speaker 1', text: '되살린 말' }] })
})
