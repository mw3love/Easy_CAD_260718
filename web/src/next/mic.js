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
export async function startMic({ onText = () => {}, onTokens, onState, onError, headers = {}, diarize = false, reconnect = false }) {
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
  let ws = null, final = '', buf = [], len = 0, open = false, stopping = false, closed = false, timer = 0, sent = 0, offset = 0, fails = 0
  const micOff = () => stream.getTracks().forEach(t => t.stop())
  const done = () => { if (closed) return; closed = true; clearTimeout(timer); micOff(); ctx.close().catch(() => {}); try { ws.close() } catch { /* 이미 닫힘 */ } onState('off') }
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
      open = true; fails = 0
      s.send(JSON.stringify({ model: 'stt-rt-v5', audio_format: 'pcm_s16le', sample_rate: ctx.sampleRate, num_channels: 1, language_hints: ['ko'], ...(diarize ? { enable_speaker_diarization: true } : {}) }))
      onState('listen'); flush()
    }
    s.onmessage = e => {
      if (s !== ws) return
      let m; try { m = JSON.parse(e.data) } catch { return }
      if (m.error_code || m.error_message) { onError(`받아쓰기 오류: ${m.error_message || m.error_code}`); return done() }
      let fin = '', non = ''; const fins = [], nons = []
      for (const t of m.tokens || []) { if (/^<.+>$/.test(t.text || '')) continue; if (t.is_final) { fin += t.text; fins.push(shift(t)) } else { non += t.text; nons.push(shift(t)) } }
      final += fin; onText(final, non); if (onTokens) onTokens(fins, nons)
      if (m.finished) done()
    }
    s.onerror = () => { if (s === ws && !closed && !reconnect) onError('받아쓰기 연결이 끊겼어요') }
    s.onclose = async e => {
      if (s !== ws || closed) return
      if (reconnect && !stopping && e.code !== 4402 && fails < 3) {   // 60분 상한·잠깐 끊김 = 새 표로 다시(크레딧 부족이면 그만)
        open = false; fails++; onState('reconnect')
        try { connect(await token()) } catch (err) { onError(`받아쓰기를 다시 못 붙였어요 — ${err.message || err}`); done() }
        return
      }
      if (!stopping && e.code !== 1000) onError(e.code === 4402 ? '크레딧이 모자라요' : `받아쓰기 연결이 끊겼어요(${e.code})`)
      done()
    }
  }
  node.port.onmessage = e => {
    if (stopping || closed) return
    if (!open && !(reconnect && ws)) return   // 다시 붙는 동안은 모아 둠(아래 30초까지)
    buf.push(e.data); len += e.data.length
    if (!open) { while (len > ctx.sampleRate * 30) len -= buf.shift().length; return }
    if (len >= ctx.sampleRate / 10) flush()
  }
  connect(url0)
  return () => {
    if (stopping || closed) return
    stopping = true; onState('stopping'); micOff()   // 마이크 표시는 바로 끔
    if (!open) return done()
    flush(); ws.send(''); timer = setTimeout(done, 5000)   // 확정 글이 오면 finished로 닫힘 — 안 오면 5초 뒤 그냥 닫음
  }
}
