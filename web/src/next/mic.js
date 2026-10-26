// 대화창 🎤 실시간 받아쓰기(2026-10-20 KAIROS 문서 검토) — 마이크 → KAIROS 실시간 받아쓰기(stt-rt-v5) 소켓에 바로, 키는 서버에만.
// 서버 `/api/stt-token`이 60초짜리 일회용 표가 붙은 wss 주소를 준다(`easycad/ai/meeting.live_token`). 형식은 Soniox 실시간 그대로:
// 첫 프레임 JSON 설정 → 0.1초씩 PCM 16비트 모노 → 끝은 빈 글("" — 빈 바이너리를 보내면 408로 끝남). 소리는 구글이 아니라 KAIROS로(회사 보안).
// 답의 tokens 중 is_final = 확정(이어 붙임), 아닌 것 = 지금까지의 임시 글(매번 통째로 옴) — 실측 말 뒤 0.1~0.3초.

const WORKLET = `class MbPcm extends AudioWorkletProcessor {
  process(inputs) { const ch = inputs[0] && inputs[0][0]; if (ch) this.port.postMessage(ch.slice(0)); return true }
}
registerProcessor('mb-pcm', MbPcm)`

// 반환 = 멈추기 함수(남은 소리를 보내고 확정 글을 받은 뒤 닫힘). onText(확정, 임시), onState('listen'|'reconnect'|'stopping'|'off'), onError(쉬운 말)
// 「🎙 회의」(2026-10-23): diarize = 말한 사람 나누기(실측 — 실시간도 토큰마다 speaker "1"·"2"), onTokens(확정 토큰[], 임시 토큰[]) — 토큰 = {text, speaker, start_ms, end_ms}
// (시간은 첫 연결부터 센 것), reconnect = 연결이 닫혀도(KAIROS 한 연결 60분 상한 `session cap` 등) 새 표로 다시 붙음 — 그동안 소리는 모아 뒀다 보냄
// 마이크 지킴이(2026-10-26, 노션 데스크톱 회의 알약 「멈춘 걸 알려 줌」 참고): 장치가 빠지거나 권한이 꺼지면(트랙 ended) 알리고 끝냄(받아 적은 글은 남음),
// 소리가 SILENT_MS 동안 진짜 0에 가까우면 onWarn(쉬운 말) — 다시 들리면 onWarn(''). 기준 SILENT_PEAK = 실측 조용한 방(노이즈 억제 켬)의 최저 0.00055보다 5배 낮게
// 인터넷 끊김(같은 날): KAIROS는 말이 없어도 약 1.1초마다 빈 답을 보냄(실측) → NOREPLY_MS 동안 답이 없으면 경고, DEAD_MS면 죽은 연결로 보고 새 표로(와이파이가 조용히 죽으면
// 브라우저는 닫힘을 모름). reconnect면 표를 못 받아도(인터넷 없음) 3초마다 계속 다시. record = 소리를 PC에도 녹음(인터넷과 상관없이) → 끝날 때 onRecord(Blob, gap) —
// gap = 받아쓰기가 빠진 구간이 있었을 수 있음(30초 넘게 못 보냄·답 끊김). 형식 = audio/mp4(.m4a — KAIROS가 그대로 받음, 실측) 아니면 webm(서버 ffmpeg가 바꿈), 24kbps = 2시간 ≈ 22MB(KAIROS 25MB 아래)
const SILENT_PEAK = 0.0001, SILENT_MS = 10000, NOREPLY_MS = 8000, DEAD_MS = 15000
const SILENT_MSG = `소리가 ${SILENT_MS / 1000}초째 안 들어와요 — 마이크가 음소거됐거나 다른 장치가 골라졌는지 보세요`
const NET_MSG = '받아쓰기 응답이 끊겼어요 — 인터넷 연결을 보세요. 녹음은 계속하는 중이에요'
const REC_TYPES = ['audio/mp4', 'audio/webm;codecs=opus']
export async function startMic({ onText = () => {}, onTokens, onState, onError, onWarn = () => {}, onRecord, headers = {}, diarize = false, reconnect = false, record = false }) {
  const token = async () => {
    const r = await fetch('/api/stt-token', { method: 'POST', headers })
    const tok = await r.json().catch(() => ({}))
    if (!r.ok || !tok.url) throw new Error(tok.error || `서버 응답 ${r.status}`)
    return tok.url
  }
  const url0 = await token()
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
  } catch {
    throw new Error('마이크를 쓸 수 없어요 — 주소창 왼쪽 자물쇠에서 마이크를 허용해 주세요')
  }
  const ctx = new AudioContext({ sampleRate: 24000 })
  const modUrl = URL.createObjectURL(new Blob([WORKLET], { type: 'text/javascript' }))
  await ctx.audioWorklet.addModule(modUrl); URL.revokeObjectURL(modUrl)
  const src = ctx.createMediaStreamSource(stream), node = new AudioWorkletNode(ctx, 'mb-pcm'), mute = ctx.createGain()
  mute.gain.value = 0; src.connect(node); node.connect(mute); mute.connect(ctx.destination)   // 끝까지 이어야 처리가 돎(소리는 0 — 내 목소리가 스피커로 안 나옴)
  const mime = record && window.MediaRecorder ? REC_TYPES.find(t => MediaRecorder.isTypeSupported(t)) : null, chunks = []
  let rec = null
  if (mime) try { rec = new MediaRecorder(stream, { mimeType: mime, audioBitsPerSecond: 24000 }); rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data) }; rec.start(5000) } catch { rec = null }
  const recDone = new Promise(ok => (rec ? rec.addEventListener('stop', ok) : ok()))
  let ws = null, final = '', buf = [], len = 0, open = false, stopping = false, closed = false, timer = 0, sent = 0, offset = 0, fails = 0
  let heard = Date.now(), replied = Date.now(), silent = false, net = false, said = '', gap = false, retrying = false
  const warn = () => { const w = net ? NET_MSG : silent ? SILENT_MSG : ''; if (w !== said) { said = w; onWarn(w) } }   // 경고 칸은 하나 — 인터넷이 먼저
  const micOff = () => { if (rec?.state === 'recording') try { rec.stop() } catch { /* 이미 멈춤 */ } stream.getTracks().forEach(t => t.stop()) }   // 녹음 먼저 멈춰야 마지막 조각까지 남음
  const again = async () => {   // 새 표로 다시 붙기 — 표를 못 받으면(인터넷·서버 없음) 3초마다 계속, 그동안 소리는 30초까지 모으고 나머지는 녹음에만
    if (retrying) return
    retrying = true; open = false; onState('reconnect')
    while (!stopping && !closed) {
      try { const url = await token(); if (!stopping && !closed) connect(url); break } catch { gap = true; net = true; warn(); await new Promise(ok => setTimeout(ok, 3000)) }
    }
    retrying = false
  }
  const watch = setInterval(() => {   // 프레임·답이 아예 안 와도 돌게 따로 잼
    if (stopping || closed) return
    if (!silent && Date.now() - heard > SILENT_MS) { silent = true; warn() }
    if (open && !net && Date.now() - replied > NOREPLY_MS) { net = true; gap = true; warn() }
    if (open && reconnect && Date.now() - replied > DEAD_MS) { ws.onclose = ws.onmessage = ws.onerror = null; try { ws.close() } catch { /* 이미 닫힘 */ } again() }   // 죽은 연결은 버리고 새로
  }, 1000)
  const done = () => {
    if (closed) return
    closed = true; clearTimeout(timer); clearInterval(watch); micOff(); ctx.close().catch(() => {}); try { ws.close() } catch { /* 이미 닫힘 */ }
    Promise.race([recDone, new Promise(ok => setTimeout(ok, 2000))]).then(() => { if (rec && chunks.length) onRecord?.(new Blob(chunks, { type: mime }), gap); onState('off') })   // 녹음을 먼저 넘겨야 「off」 쪽이 녹음 유무를 앎
  }
  const flush = () => {
    if (!len || !ws || ws.readyState !== 1) return
    const pcm = new Int16Array(len); let o = 0
    for (const f of buf) for (let i = 0; i < f.length; i++) { const v = Math.max(-1, Math.min(1, f[i])); pcm[o++] = v < 0 ? v * 0x8000 : v * 0x7fff }
    ws.send(pcm.buffer); sent += len; buf = []; len = 0
  }
  const connect = url => {
    const s = ws = new WebSocket(url)
    open = false; offset = Math.round(sent / ctx.sampleRate * 1000)   // 새 연결의 시간은 0부터 — 앞 연결까지 보낸 소리만큼 밀어 줌
    const shift = t => ({ text: t.text, speaker: t.speaker || '', start_ms: (t.start_ms || 0) + offset, end_ms: (t.end_ms || 0) + offset })
    s.onopen = () => {
      open = true; fails = 0; replied = Date.now()
      s.send(JSON.stringify({ model: 'stt-rt-v5', audio_format: 'pcm_s16le', sample_rate: ctx.sampleRate, num_channels: 1, language_hints: ['ko'], ...(diarize ? { enable_speaker_diarization: true } : {}) }))
      onState('listen'); flush()
    }
    s.onmessage = e => {
      if (s !== ws) return
      replied = Date.now(); if (net) { net = false; warn() }
      let m; try { m = JSON.parse(e.data) } catch { return }
      if (m.error_code || m.error_message) { onError(`받아쓰기 오류: ${m.error_message || m.error_code}`); return done() }
      let fin = '', non = ''; const fins = [], nons = []
      for (const t of m.tokens || []) { if (/^<.+>$/.test(t.text || '')) continue; if (t.is_final) { fin += t.text; fins.push(shift(t)) } else { non += t.text; nons.push(shift(t)) } }
      final += fin; onText(final, non); if (onTokens) onTokens(fins, nons)
      if (m.finished) done()
    }
    s.onerror = () => { if (s === ws && !closed && !reconnect) onError('받아쓰기 연결이 끊겼어요') }
    s.onclose = e => {
      if (s !== ws || closed) return
      if (reconnect && !stopping && e.code !== 4402 && fails < 3) { fails++; again(); return }   // 60분 상한·잠깐 끊김·인터넷 끊김 = 새 표로 다시(크레딧 부족이면 그만)
      if (!stopping && e.code !== 1000) onError(e.code === 4402 ? '크레딧이 모자라요' : `받아쓰기 연결이 끊겼어요(${e.code})`)
      done()
    }
  }
  node.port.onmessage = e => {
    if (stopping || closed) return
    let peak = 0; for (let i = 0; i < e.data.length; i++) { const v = Math.abs(e.data[i]); if (v > peak) peak = v }
    if (peak >= SILENT_PEAK) { heard = Date.now(); if (silent) { silent = false; warn() } }
    if (!open && !(reconnect && ws)) return   // 다시 붙는 동안은 모아 둠(아래 30초까지)
    buf.push(e.data); len += e.data.length
    if (!open) { while (len > ctx.sampleRate * 30) { len -= buf.shift().length; gap = true } return }
    if (len >= ctx.sampleRate / 10) flush()
  }
  connect(url0)
  const stop = () => {
    if (stopping || closed) return
    stopping = true; onState('stopping'); micOff()   // 마이크 표시는 바로 끔
    if (!open) return done()
    flush(); ws.send(''); timer = setTimeout(done, 5000)   // 확정 글이 오면 finished로 닫힘 — 안 오면 5초 뒤 그냥 닫음
  }
  // t.stop()(우리가 끔)은 ended를 안 냄 — 이건 장치 빠짐·권한 끔·브라우저가 끊은 것만
  for (const t of stream.getAudioTracks()) t.addEventListener('ended', () => { if (stopping || closed) return; onError('마이크가 끊겼어요 — 장치가 빠졌거나 마이크 권한이 꺼졌어요. 받아 적은 글은 남아 있어요'); stop() })
  return stop
}
