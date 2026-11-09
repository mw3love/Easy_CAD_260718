// 글 입력부 한 부품(2026-11-09 사용자 — ChatGPT·Gemini·Claude 입력창과 비교 검토): 대화창·AI 칩 창·말풍선이 같이 씀.
// 글과 단추가 한 상자 · 글이 늘면 칸도 늘어남(줄바꿈 없는 긴 문단도 — 옛날엔 줄바꿈 수로만 높이를 정해 2줄 그대로였음) · 오른쪽 아래 ↑ 보내기 · 기다리는 동안 ■ 멈춤(onStop을 줄 때만).
// tools = 아래 줄에 놓을 단추들(대화창 — 없으면 글 칸 오른쪽에 ↑만). 폭이 바뀌면 줄 수가 달라지므로 폭 변화도 다시 잼.
import { useEffect, useLayoutEffect, useRef } from 'react'
import { isPhone } from './ui.jsx'

const F = "'Pretendard', sans-serif"
const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)' }
const ICON_UP = <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19 V5 M6 11 L12 5 L18 11" /></svg>
const ICON_STOP = <svg viewBox="0 0 24 24" width="12" height="12" aria-hidden="true"><rect x="4" y="4" width="16" height="16" rx="2.5" fill="currentColor" /></svg>

export function Composer({ value, onChange, onSend, onStop, canSend, busy, inputRef, inputId, sendId, label, placeholder, fs = 13, maxRows = 6, tools, onKeyDown, onPaste, stopTitle }) {
  const own = useRef(null), ta = inputRef || own, touch = isPhone(), hit = touch ? 44 : 30, dot = touch ? 34 : 28, lh = fs * 1.5
  const fit = () => {
    const t = ta.current; if (!t) return
    t.style.height = 'auto'   // 줄어드는 것도 재려면 먼저 풀어야 함
    const most = Math.min(maxRows * lh + 4, window.innerHeight * 0.4), h = Math.min(t.scrollHeight, most)   // 화면의 40%까지만(휴대폰 글쇠판이 떠도 대화가 보이게)
    t.style.height = `${h}px`; t.style.overflowY = t.scrollHeight > most ? 'auto' : 'hidden'
  }
  useLayoutEffect(fit, [value])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {   // 대화창 폭을 끌거나 휴대폰을 돌리면 줄 수가 바뀜 — 높이가 바뀌어 다시 불리는 건 폭으로 걸러냄
    const t = ta.current; if (!t || !window.ResizeObserver) return
    let w = t.offsetWidth; const ob = new ResizeObserver(() => { if (t.offsetWidth !== w) { w = t.offsetWidth; fit() } }); ob.observe(t); return () => ob.disconnect()
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  const key = e => {
    e.stopPropagation(); onKeyDown?.(e)
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing && !e.defaultPrevented) { e.preventDefault(); onSend() }
  }
  const stopping = busy && onStop
  const button = <button type="button" className="mb-send" data-testid={stopping ? 'chat-stop' : sendId} aria-label={stopping ? '답 기다리기 그만두기' : '보내기'} title={stopping ? stopTitle : '보내기 (Enter)'} disabled={!stopping && !canSend}
    onMouseDown={e => e.preventDefault()} onClick={() => (stopping ? onStop() : onSend())}   // 누른 뒤에도 글 칸에 초점이 남게
    style={{ all: 'unset', width: hit, height: hit, flex: 'none', display: 'grid', placeItems: 'center', borderRadius: '50%', cursor: stopping || canSend ? 'pointer' : 'default' }}>
    <span style={{ width: dot, height: dot, borderRadius: '50%', display: 'grid', placeItems: 'center', background: !stopping && canSend ? 'var(--mb-accent)' : C.seg, color: stopping ? C.ink : canSend ? '#fff' : C.muted }}>{stopping ? ICON_STOP : ICON_UP}</span>
  </button>
  const input = <textarea ref={ta} data-testid={inputId} aria-label={label} rows={2} value={value} placeholder={placeholder} onChange={onChange} onKeyDown={key} onPaste={onPaste}
    style={{ flex: tools ? 'none' : 1, display: 'block', width: '100%', minWidth: 0, boxSizing: 'border-box', resize: 'none', border: 0, outline: 'none', padding: '2px 0', background: 'transparent', color: C.ink, font: `400 ${fs}px/${lh}px ${F}` }} />
  return <div className="mb-field" data-testid="composer" onClick={e => { if (e.target === e.currentTarget || e.target.dataset.composerRow != null) ta.current?.focus() }}   // 상자의 빈 곳을 눌러도 글 칸으로
    style={{ display: 'flex', flexDirection: tools ? 'column' : 'row', alignItems: tools ? 'stretch' : 'flex-end', gap: tools ? 2 : 4, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 12, background: C.card, padding: tools ? '8px 6px 4px 12px' : '5px 5px 5px 10px' }}>
    {input}
    {tools ? <div data-composer-row="" style={{ display: 'flex', alignItems: 'center', gap: 2, marginLeft: -6 }}>{tools}{button}</div> : button}
  </div>
}
