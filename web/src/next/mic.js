// 대화창 🎤 실시간 받아쓰기(2026-10-20 KAIROS 문서 검토) — 마이크 → KAIROS 실시간 받아쓰기(stt-rt-v5) 소켓에 바로, 키는 서버에만.
// 서버 `/api/stt-token`이 60초짜리 일회용 표가 붙은 wss 주소를 준다(`easycad/ai/meeting.live_token`). 형식은 Soniox 실시간 그대로:
// 첫 프레임 JSON 설정 → 0.1초씩 PCM 16비트 모노 → 끝은 빈 글("" — 빈 바이너리를 보내면 408로 끝남). 소리는 구글이 아니라 KAIROS로(회사 보안).
// 답의 tokens 중 is_final = 확정(이어 붙임), 아닌 것 = 지금까지의 임시 글(매번 통째로 옴) — 실측 말 뒤 0.1~0.3초.

const WORKLET = `class MbPcm extends AudioWorkletProcessor {
  process(inputs) { const ch = inputs[0] && inputs[0][0]; if (ch) this.port.postMessage(ch.slice(0)); return true }
}
registerProcessor('mb-pcm', MbPcm)`

// 반환 = 멈추기 함수(남은 소리를 보내고 확정 글을 받은 뒤 닫힘). onText(확정, 임시), onState('listen'|'stopping'|'off'), onError(쉬운 말)
export async function startMic({ onText, onState, onError, headers = {} }) {
  const r = await fetch('/api/stt-token', { method: 'POST', headers })
  const tok = await r.json().catch(() => ({}))
  if (!r.ok || !tok.url) throw new Error(tok.error || `서버 응답 ${r.status}`)
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
  const ws = new WebSocket(tok.url)
  let final = '', buf = [], len = 0, open = false, stopping = false, closed = false, timer = 0
  const micOff = () => stream.getTracks().forEach(t => t.stop())
  const done = () => { if (closed) return; closed = true; clearTimeout(timer); micOff(); ctx.close().catch(() => {}); try { ws.close() } catch { /* 이미 닫힘 */ } onState('off') }
  const flush = () => {
    if (!len || ws.readyState !== 1) return
    const pcm = new Int16Array(len); let o = 0
    for (const f of buf) for (let i = 0; i < f.length; i++) { const v = Math.max(-1, Math.min(1, f[i])); pcm[o++] = v < 0 ? v * 0x8000 : v * 0x7fff }
    ws.send(pcm.buffer); buf = []; len = 0
  }
  ws.onopen = () => {
    open = true
    ws.send(JSON.stringify({ model: 'stt-rt-v5', audio_format: 'pcm_s16le', sample_rate: ctx.sampleRate, num_channels: 1, language_hints: ['ko'] }))
    onState('listen')
  }
  node.port.onmessage = e => { if (!open || stopping) return; buf.push(e.data); len += e.data.length; if (len >= ctx.sampleRate / 10) flush() }
  ws.onmessage = e => {
    let m; try { m = JSON.parse(e.data) } catch { return }
    if (m.error_code || m.error_message) { onError(`받아쓰기 오류: ${m.error_message || m.error_code}`); return done() }
    let fin = '', non = ''
    for (const t of m.tokens || []) { if (/^<.+>$/.test(t.text || '')) continue; if (t.is_final) fin += t.text; else non += t.text }
    final += fin; onText(final, non)
    if (m.finished) done()
  }
  ws.onerror = () => { if (!closed) onError('받아쓰기 연결이 끊겼어요') }
  ws.onclose = e => { if (!closed && !stopping && e.code !== 1000) onError(e.code === 4402 ? '크레딧이 모자라요' : `받아쓰기 연결이 끊겼어요(${e.code})`); done() }
  return () => {
    if (stopping || closed) return
    stopping = true; onState('stopping'); micOff()   // 마이크 표시는 바로 끔
    if (!open) return done()
    flush(); ws.send(''); timer = setTimeout(done, 5000)   // 확정 글이 오면 finished로 닫힘 — 안 오면 5초 뒤 그냥 닫음
  }
}
