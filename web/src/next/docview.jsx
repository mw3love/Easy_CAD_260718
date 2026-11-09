// 📄 문서 큰 창(2026-11-09 문서 통합 2단계 — 시안 B: Artifact `MXRQVg7tBZH6sbNTQagnNx`). 카드 ↗·두 번 누르기 = 칠판 위 큰 창.
// 블록(`data-block`)에 마우스를 올리면 테두리, 누르면 그 블록의 말 칸 → 서버 `/api/chat` `kind: 'block'`이 그 블록만 다시 써서 문서 전체를 돌려줌
// → 칠판 문서에 바로(Ctrl+Z 한 번, 「원래대로 ↔ 바꾼 것」은 이 창에만 기억). 인쇄·한글 파일은 위 막대(옛 「크게 보기」 새 탭 = 인쇄).
// 문서 틀은 스크립트 없이 `allow-same-origin`만 — 앱이 블록을 재고 누르기를 받으려고(문서 글은 서버 `clean_html`이 이미 청소).
import { useEffect, useRef, useState } from 'react'
import { DOC_NAME } from './doc.js'
import { keyHeaders } from './kairosKey.js'
import { Spinner } from './chat.jsx'
import { docPageW } from './render.jsx'

const F = "'Pretendard', sans-serif"
const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)' }
const KIND = { text: '글', table: '표', chart: '그래프', image: '그림', box: '상자' }
const PICK_CSS = '[data-block]{cursor:pointer}[data-block]:hover{outline:2px solid #2563eb;outline-offset:3px}[data-block].mb-sel{outline:2px solid #da7756 !important;outline-offset:3px}[data-block].mb-done{outline:2px solid #16a34a;outline-offset:3px}'
const BUB_W = 320

export function DocView({ it, size, readOnly, threads = {}, onThread, onClose, onHtml, onPrint, onHwpx, onStatus }) {   // threads·onThread = 블록 대화(말풍선 대화 저장소, 키 「문서 _id#bN」 — 창을 닫아도 남음)
  const frame = useRef(null), scroller = useRef(null), swaps = useRef({}), keepTop = useRef(0)
  const [docH, setDocH] = useState(1200), [pick, setPick] = useState(null)   // pick = { bid, kind, top, left, right } (창 안 px)
  const tkey = bid => `${it._id}#${bid}`, talk = bid => threads[tkey(bid)] || []
  const [draft, setDraft] = useState(''), [busy, setBusy] = useState(''), [err, setErr] = useState(''), [done, setDone] = useState('')
  const pageW = docPageW(it), winW = Math.min(pageW + 48, size.w - 32), scale = Math.min(1, (winW - 40) / pageW), winH = size.h - 24
  const esc = useRef(null); esc.current = () => (pick ? setPick(null) : onClose())
  useEffect(() => { const k = e => { if (e.key === 'Escape') esc.current() }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [])   // 초점이 창 밖(말 칸이 닫힌 뒤 등)일 때   // Esc = 말 칸 먼저, 그다음 창(창 밖으로 글쇠를 안 내보내서 여기서 받음 — 문서 틀 안 글쇠도)
  function onLoad() {
    const d = frame.current?.contentDocument; if (!d) return
    setDocH(Math.max(400, d.documentElement.scrollHeight))
    if (scroller.current) scroller.current.scrollTop = keepTop.current
    if (readOnly) return
    d.addEventListener('keydown', e => { if (e.key === 'Escape') esc.current() })
    const s = d.createElement('style'); s.textContent = PICK_CSS; d.head?.appendChild(s)
    if (done) d.querySelector(`[data-block="${done}"]`)?.classList.add('mb-done')
    d.addEventListener('click', e => {
      const el = e.target.closest?.('[data-block]'); if (!el) return
      e.preventDefault()
      d.querySelectorAll('.mb-sel').forEach(x => x.classList.remove('mb-sel')); el.classList.add('mb-sel')
      const r = el.getBoundingClientRect(), sc = scroller.current, off = frame.current.offsetLeft
      setPick({ bid: el.dataset.block, kind: el.dataset.kind || '', top: r.top * scale - (sc?.scrollTop || 0) + 44, left: off + r.left * scale, right: off + r.right * scale })
      setErr(''); setDraft('')
    })
  }
  async function send() {
    const q = draft.trim(); if (!q || busy || !pick) return
    const bid = pick.bid, mine = { role: 'user', content: q, at: Date.now() }, msgs = [...talk(bid), mine]
    onThread?.(tkey(bid), msgs); setDraft(''); setBusy(bid); setErr('')
    try {
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() },
        body: JSON.stringify({ kind: 'block', board: DOC_NAME, doc: it.html, block: bid, messages: msgs.map(({ role, content }) => ({ role, content })) }) })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      const before = it.html
      keepTop.current = scroller.current?.scrollTop || 0
      if (!onHtml(d.html)) throw new Error('칠판 문서를 못 바꿨어요')
      const k = `${bid}:${msgs.length}`; swaps.current[k] = { before, after: d.html, on: true }
      onThread?.(tkey(bid), [...msgs, { role: 'assistant', content: d.content || '고쳤어요', swap: k, model: d.model, credits: d.credits, at: Date.now() }])
      setDone(bid); onStatus?.(`${bid}만 고쳤어요 — Ctrl+Z로 되돌려요`)
    } catch (e) { setErr(String(e.message || e)) } finally { setBusy('') }
  }
  function flip(k) { const s = swaps.current[k]; if (!s) return; keepTop.current = scroller.current?.scrollTop || 0; if (onHtml(s.on ? s.before : s.after)) { s.on = !s.on; setDraft(x => x + '') } }   // 표시만 다시 그림
  const btn = { all: 'unset', cursor: 'pointer', font: `600 12.5px ${F}`, padding: '4px 10px', borderRadius: 7, border: `1px solid ${C.line}`, color: C.ink }
  const bx = pick ? (pick.right + 12 + BUB_W <= winW - 8 ? pick.right + 12 : Math.max(8, Math.min(winW - BUB_W - 8, pick.left - 12 - BUB_W >= 8 ? pick.left - 12 - BUB_W : pick.right - BUB_W))) : 0
  const by = pick ? Math.max(52, Math.min(pick.top, winH - 230)) : 0
  const msgs = pick ? talk(pick.bid) : []
  return <div data-testid="doc-view" onPointerDown={e => e.stopPropagation()} onWheel={e => e.stopPropagation()} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') esc.current() }}
    style={{ position: 'absolute', inset: 0, zIndex: 9, background: 'rgba(24,24,27,.42)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: 12 }}
    onClick={e => { if (e.target === e.currentTarget) onClose() }}>
    <div role="dialog" aria-label={`문서 — ${it.title || ''}`} style={{ position: 'relative', width: winW, height: winH, background: C.card, color: C.ink, borderRadius: 12, boxShadow: '0 8px 28px rgba(0,0,0,.28)', display: 'flex', flexDirection: 'column', overflow: 'hidden', font: `400 13px/1.5 ${F}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 10px 9px 14px', borderBottom: `1px solid ${C.line}`, flex: 'none' }}>
        <b style={{ font: `700 14px ${F}`, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📄 {it.title || '문서'}</b>
        <span style={{ flex: 1 }} />
        <button data-testid="doc-print" style={btn} onClick={onPrint} title="새 탭에서 열어 Ctrl+P — 인쇄·PDF로 저장">인쇄 · PDF</button>
        {onHwpx && <button style={btn} onClick={onHwpx}>한글 파일</button>}
        <button data-testid="doc-close" title="닫기(Esc)" onClick={onClose} style={{ ...btn, border: 0, color: C.muted, fontSize: 15, padding: '2px 8px' }}>✕</button>
      </div>
      <div ref={scroller} onScroll={() => pick && setPick(null)} style={{ flex: 1, overflow: 'auto', background: '#fff', position: 'relative' }}>
        <div style={{ height: docH * scale, position: 'relative' }}>
          <iframe ref={frame} data-testid="doc-frame" title={it.title || '문서'} srcDoc={it.html} sandbox="allow-same-origin" scrolling="no" onLoad={onLoad}
            style={{ position: 'absolute', left: Math.max(0, (winW - pageW * scale) / 2), top: 0, width: pageW, height: docH, border: 0, transform: `scale(${scale})`, transformOrigin: '0 0', background: '#fff' }} />
        </div>
      </div>
      {pick && <div data-testid="block-bubble" data-block={pick.bid} style={{ position: 'absolute', left: bx, top: by, width: BUB_W, zIndex: 2, background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, boxShadow: '0 6px 20px rgba(0,0,0,.2)', display: 'flex', flexDirection: 'column', maxHeight: 360 }}>
        <div style={{ display: 'flex', alignItems: 'center', padding: '8px 8px 7px 12px', borderBottom: `1px solid ${C.line}` }}>
          <b style={{ fontSize: 13 }}>{pick.bid} · {KIND[pick.kind] || '블록'}</b>
          <button title="닫기(Esc)" onClick={() => setPick(null)} style={{ all: 'unset', cursor: 'pointer', marginLeft: 'auto', color: C.muted, padding: '0 6px', fontSize: 14 }}>✕</button>
        </div>
        {(msgs.length > 0 || busy || err) && <div style={{ overflowY: 'auto', padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {msgs.map((m, i) => m.role === 'user'
            ? <div key={i} style={{ alignSelf: 'flex-end', maxWidth: '88%', background: 'rgba(218,119,86,.12)', borderRadius: 10, padding: '4px 9px', whiteSpace: 'pre-wrap' }}>{m.content}</div>
            : <div key={i} data-testid="block-a" style={{ alignSelf: 'flex-start', maxWidth: '96%', background: C.seg, borderRadius: 10, padding: '5px 9px' }}>{m.content}
              {swaps.current[m.swap] && <div style={{ marginTop: 4 }}><button data-testid="block-flip" style={{ ...btn, font: `500 11.5px ${F}`, padding: '2px 7px', color: C.muted }} onClick={() => flip(m.swap)}>{swaps.current[m.swap].on ? '원래대로' : '바꾼 것으로'}</button></div>}
              {m.model && <div style={{ font: `400 10.5px ${F}`, color: C.muted, marginTop: 2 }}>{m.model}{m.credits ? ` · 약 ${Math.round(m.credits * 10) / 10}크레딧` : ''}</div>}</div>)}
          {busy === pick.bid && <div data-testid="block-busy" style={{ display: 'flex', gap: 6, alignItems: 'center', color: C.muted, fontSize: 12.5 }}><Spinner />이 블록만 다시 쓰는 중…</div>}
          {err && <div data-testid="block-err" style={{ color: '#dc2626', fontSize: 12.5 }}>{err}</div>}
        </div>}
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', padding: '8px 10px 10px', borderTop: msgs.length ? `1px solid ${C.line}` : 0 }}>
          <textarea data-testid="block-input" autoFocus rows={2} value={draft} placeholder="이 부분을 어떻게 할까요? 예: 쉬운 말로 · 도표로 · 그림 넣어 줘" onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }}
            style={{ flex: 1, minWidth: 0, resize: 'none', border: `1px solid ${C.line}`, borderRadius: 8, padding: '6px 8px', font: `400 13px/1.5 ${F}`, background: 'transparent', color: C.ink, outline: 'none' }} />
          <button data-testid="block-send" disabled={!!busy} onClick={send} style={{ all: 'unset', cursor: busy ? 'default' : 'pointer', height: 30, padding: '0 12px', display: 'flex', alignItems: 'center', borderRadius: 7, background: 'var(--mb-accent)', color: '#fff', font: `700 12.5px ${F}`, opacity: busy ? 0.6 : 1 }}>보내기</button>
        </div>
      </div>}
    </div>
  </div>
}
