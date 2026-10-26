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
  const k = { tokens: 0, configs: [], audio: [0], sockets: [], posts: [], down: false, mute: -1 }   // down = 인터넷 끊김(표를 못 받음), mute = 답을 멈춘 소켓 번호(조용히 죽은 연결)
  await page.route('**/api/stt-token', r => { if (k.down) return r.abort('internetdisconnected'); k.tokens++; return r.fulfill({ json: { url: `ws://127.0.0.1:5291/fake-stt?token=t${k.tokens}`, model: 'stt-rt-v5' } }) })
  await page.routeWebSocket('**/fake-stt**', ws => {
    const n = k.sockets.length; k.sockets.push(ws); k.audio[n] = 0
    const beat = setInterval(() => { if (k.mute !== n) try { ws.send(JSON.stringify({ tokens: [] })) } catch { clearInterval(beat) } }, 1000)   // 진짜 KAIROS처럼 말이 없어도 약 1초마다 빈 답(2026-10-26 실측)
    ws.onClose(() => clearInterval(beat))
    ws.onMessage(m => {
      if (typeof m === 'string' && m.startsWith('{')) { k.configs.push(JSON.parse(m)); return }
      if (m === '') { ws.send(JSON.stringify({ tokens: [tok(' 마지막 말입니다.', '2', 9000, 9800)], finished: true })); return }
      k.audio[n] += m.length
    })
  })
  await page.route('**/api/meeting/**', async r => {
    const q = r.request()
    if (q.method() === 'POST') {   // 실시간 요약(/live, JSON) · 녹음 파일(그 밖 — 「녹음으로 정리」)
      k.posts.push(q.url().endsWith('/live') ? { url: q.url(), body: q.postDataJSON() } : { url: q.url(), type: q.headers()['content-type'], name: decodeURIComponent(q.headers()['x-file-name'] || ''), size: q.postDataBuffer()?.length || 0 })
      return r.fulfill({ json: { job: 'abcdef123456' } })
    }
    const last = k.posts.at(-1), segs = last.body ? last.body.segments : [{ speaker: 'Speaker 1', start_ms: 0, text: '녹음으로 받아쓴 말' }]
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

  await s0.close({ code: 1000, reason: 'session cap' })                          // KAIROS 한 연결 60분 상한
  await expect.poll(() => k.sockets.length).toBe(2)
  const sent0 = k.audio[0]   // 닫힌 뒤에 잰다 — 닫기 전에 재면 닫는 사이 0.1초 덩이 하나가 더 가서 가끔 어긋났음(10-23)
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
  const ms0 = Math.round(sent0 / 2 / 24000 * 1000)                               // 바이트 → 16비트 샘플 → 밀리초
  expect(segs[2].start_ms).toBeGreaterThanOrEqual(ms0)                           // 앱은 자기가 보낸 만큼 밈 — 닫히는 순간 보낸 덩이는
  expect(segs[2].start_ms).toBeLessThanOrEqual(ms0 + 110)                        // 가짜 서버가 못 받을 수 있어 한 덩이(약 101ms)까지 봐줌
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

test('서버가 옛 버전(요약 주소 없음)이면 다시 켜라고 알림 · 받아 적은 글은 남음', async ({ page }) => {
  const name = boardName('meetold'), k = await fakeKairos(page)
  await page.route('**/api/meeting/**', r => r.fulfill({ status: 404, body: '{"error":"none"}', contentType: 'application/json' }))
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '회의', exact: true }).click()
  await expect.poll(() => k.sockets.length).toBe(1)
  k.sockets[0].send(JSON.stringify({ tokens: [tok('남아야 할 말', '1', 0, 900)] }))
  await expect(page.getByTestId('meeting-live')).toContainText('남아야 할 말')
  await page.getByTestId('meeting-live-end').click()
  await expect(page.getByTestId('status-toast')).toContainText('python web/server.py를 다시 켜 주세요', { timeout: 10_000 })
  await expect(page.getByTestId('meeting-live')).toHaveAttribute('data-state', 'saved')
  await expect(page.getByTestId('meeting-live')).toContainText('남아야 할 말')
})

test('쉬지 않고 말해도 5초 안에 저장 · 요약이 안 되면 서버 사본으로 되살려 「전문만」', async ({ page }) => {
  const name = boardName('meetsafe'), k = await fakeKairos(page)
  await page.route('**/api/meeting/**', r => r.fulfill({ status: 502, json: { error: 'KAIROS 요약 실패(가짜)' } }))
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '회의', exact: true }).click()
  await expect.poll(() => k.sockets.length).toBe(1)
  for (let i = 0; i < 8; i++) { k.sockets[0].send(JSON.stringify({ tokens: [tok(` 쉬지 않는 말 ${i}.`, '1', i * 1000, i * 1000 + 900)] })); await page.waitForTimeout(800) }   // 0.8초마다 새 말 — 전엔 「3초 조용하면」이라 안 저장됐음
  expect(await page.evaluate(n => localStorage.getItem(`mb-meet:${n}`), name)).toContain('쉬지 않는 말 0.')
  await page.getByTestId('meeting-live-end').click()
  await expect(page.getByTestId('status-toast')).toContainText('KAIROS 요약 실패(가짜)', { timeout: 10_000 })
  await expect.poll(async () => (await page.request.get(`/api/meetdraft/${name}`)).status()).toBe(200)   // 끝내는 순간 서버에도
  await page.evaluate(n => localStorage.removeItem(`mb-meet:${n}`), name)                                // 이 브라우저 사본이 없어져도(다른 PC·기록 지움)
  await page.reload()
  const live = page.getByTestId('meeting-live')
  await expect(live).toHaveAttribute('data-state', 'saved')
  await expect(live).toContainText('쉬지 않는 말 7.')
  await page.getByTestId('meeting-live-raw').click()                                                     // 요약 없이 전문만
  await expect.poll(async () => (await liveDoc(page)).items.length, { timeout: 10_000 }).toBe(3)
  const doc = await liveDoc(page), full = doc.items.find(it => it.type === 'memo' && it.fold)
  expect(full.lines.map(l => l.t).join('\n')).toContain('화자 1: 쉬지 않는 말 0.')
  expect(doc.items.find(it => it.type === 'frame').name).toContain('회의(요약 없음)')
  await expect.poll(async () => (await page.request.get(`/api/meetdraft/${name}`)).text()).toBe('{}')     // 다 붙이면 서버 사본도 지움
})

// 마이크 지킴이(2026-10-26, 노션 데스크톱 회의 알약 참고) — 전엔 마이크가 빠지거나 무음이어도 「받아 적는 중」 시계만 흘렀음(실험으로 확인)
const SOUND = () => {   // 마이크 대신 소리 크기를 시험이 정하는 가짜 장치 — window.__mbGain.gain.value = 0(무음) · 0.5(소리)
  navigator.mediaDevices.getUserMedia = async () => {
    const ac = new AudioContext(), osc = ac.createOscillator(), g = ac.createGain(), d = ac.createMediaStreamDestination()
    g.gain.value = 0; osc.connect(g); g.connect(d); osc.start(); window.__mbGain = g; window.__mbStream = d.stream; return d.stream
  }
}

test('소리가 10초째 안 들어오면 경고 → 다시 들리면 사라짐', async ({ page }) => {
  const name = boardName('meetmute'), k = await fakeKairos(page)
  await page.addInitScript(SOUND)
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '회의', exact: true }).click()
  await expect.poll(() => k.sockets.length).toBe(1)
  const warn = page.getByTestId('meeting-live-warn')
  await page.waitForTimeout(7000); await expect(warn).toBeHidden()                 // 10초 전엔 조용
  await expect(warn).toContainText('소리가 10초째 안 들어와요', { timeout: 8000 })
  await expect(page.getByTestId('meeting-live')).toHaveAttribute('data-state', 'listen')   // 경고만 — 받아 적기는 그대로
  await page.evaluate(() => { window.__mbGain.gain.value = 0.5 })
  await expect(warn).toBeHidden()
})

test('마이크가 끊기면(장치 빠짐) 알리고 받아 적던 회의로 남김', async ({ page }) => {
  const name = boardName('meetgone'), k = await fakeKairos(page)
  await page.addInitScript(SOUND)
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '회의', exact: true }).click()
  await expect.poll(() => k.sockets.length).toBe(1)
  k.sockets[0].send(JSON.stringify({ tokens: [tok('끊기기 전 말', '1', 0, 900)] }))
  const live = page.getByTestId('meeting-live')
  await expect(live).toContainText('끊기기 전 말')
  await page.evaluate(() => window.__mbStream.getAudioTracks()[0].dispatchEvent(new Event('ended')))   // 진짜 장치 빠짐은 브라우저가 이 신호를 냄
  await expect(live).toHaveAttribute('data-state', 'saved', { timeout: 10_000 })
  await expect(live).toContainText('마이크가 끊겼어요')
  await expect(live).toContainText('끊기기 전 말')
  await expect(page.getByTestId('meeting-live-end')).toHaveText('정리하기')
})

test('받아쓰기 답이 끊기면(조용히 죽은 연결) 8초 뒤 경고 → 15초면 새 연결로 → 경고 사라짐', async ({ page }) => {
  const name = boardName('meetnet'), k = await fakeKairos(page)
  await page.addInitScript(SOUND)
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '회의', exact: true }).click()
  await expect.poll(() => k.sockets.length).toBe(1)
  await page.evaluate(() => { window.__mbGain.gain.value = 0.5 })                 // 소리는 들어옴 — 무음 경고와 헷갈리지 않게
  k.mute = 0                                                                       // 첫 연결만 조용히 죽음
  const warn = page.getByTestId('meeting-live-warn')
  await expect(warn).toContainText('받아쓰기 응답이 끊겼어요', { timeout: 10_000 })
  await expect.poll(() => k.sockets.length, { timeout: 10_000 }).toBe(2)
  await expect(warn).toBeHidden({ timeout: 5000 })
  await expect(page.getByTestId('meeting-live')).toHaveAttribute('data-state', 'listen')
})

test('인터넷이 끊기면 녹음은 계속 → 끝내기 = 글만으로 요약하지 않음 → 「녹음으로 정리」 = 녹음 파일로 회의록 · 「녹음 받기」', async ({ page }) => {
  const name = boardName('meetoff'), k = await fakeKairos(page)
  await page.addInitScript(SOUND)
  await openBoard(page, name); await setCam(page)
  await page.getByRole('button', { name: '회의', exact: true }).click()
  await expect.poll(() => k.sockets.length).toBe(1)
  await page.evaluate(() => { window.__mbGain.gain.value = 0.5 })
  k.sockets[0].send(JSON.stringify({ tokens: [tok('끊기기 전 말', '1', 0, 900)] }))
  const live = page.getByTestId('meeting-live')
  await expect(live).toContainText('끊기기 전 말')
  k.down = true; await k.sockets[0].close({ code: 1001, reason: 'network' })
  await expect(live).toHaveAttribute('data-state', 'reconnect')
  await expect(live).toContainText('녹음은 계속하는 중')
  await expect(page.getByTestId('meeting-live-warn')).toContainText('받아쓰기 응답이 끊겼어요', { timeout: 6000 })   // 표를 못 받음 = 인터넷 경고
  await page.waitForTimeout(3500)                                                  // 3초마다 다시 시도해도 끝나지 않음
  await expect(live).toHaveAttribute('data-state', 'reconnect')
  await page.getByTestId('meeting-live-end').click()
  await expect(live).toHaveAttribute('data-state', 'saved', { timeout: 10_000 })
  await expect(live).toContainText('인터넷이 끊긴 동안의 말은 녹음에만 있어요')
  expect(k.posts).toHaveLength(0)                                                  // 빠진 구간이 있으니 글만으로 요약하지 않음
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('meeting-live-save-rec').click()])
  expect(dl.suggestedFilename()).toMatch(/^회의 녹음 .+\.(m4a|webm)$/)
  k.down = false
  await page.getByTestId('meeting-live-rec').click()
  await expect.poll(async () => (await liveDoc(page)).items.length, { timeout: 10_000 }).toBe(3)
  expect(k.posts[0].url.split('?')[0]).toMatch(new RegExp(`/api/meeting/${name}$`))   // 실시간 요약(/live)이 아니라 녹음 파일 길
  expect(k.posts[0].type).toMatch(/^audio\/(mp4|webm)/)
  expect(k.posts[0].size).toBeGreaterThan(1000)
  await expect(live).toBeHidden()
  const full = (await liveDoc(page)).items.find(it => it.type === 'memo' && it.fold)
  expect(full.lines.map(l => l.t).join('\n')).toContain('녹음으로 받아쓴 말')
})
