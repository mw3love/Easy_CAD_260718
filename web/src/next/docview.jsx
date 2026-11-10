// 📄 문서 큰 창(2026-11-09 문서 통합 2단계 — 시안 B: Artifact `MXRQVg7tBZH6sbNTQagnNx`). 카드 ↗·두 번 누르기 = 칠판 위 큰 창.
// 블록(`data-block`)에 마우스를 올리면 테두리, 누르면 그 블록의 말 칸 → 서버 `/api/chat` `kind: 'block'`이 그 블록만 다시 써서 문서 전체를 돌려줌
// → 칠판 문서에 바로(Ctrl+Z 한 번, 「원래대로 ↔ 바꾼 것」은 이 창에만 기억). 인쇄·한글 파일은 위 막대(옛 「크게 보기」 새 탭 = 인쇄).
// 문서 틀은 스크립트 없이 `allow-same-origin`만 — 앱이 블록을 재고 누르기를 받으려고(문서 글은 서버 `clean_html`이 이미 청소).
import { useEffect, useRef, useState } from 'react'
import { DOC_NAME } from './doc.js'
import { keyHeaders } from './kairosKey.js'
import { Spinner } from './chat.jsx'
import { docPageW } from './render.jsx'
import { spliceBlock, cleanEdited, handEditable } from './docblock.js'
import { LIVE_CSP, LIVE_W, LIVE_H, liveSrc } from './livecard.js'

const F = "'Pretendard', sans-serif"
const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)' }
const KIND = { text: '글', table: '표', chart: '그래프', image: '그림', box: '상자', live: '움직이는 칸' }
const PICK_CSS = '[data-block]{cursor:pointer}[data-block]:hover{outline:2px solid #2563eb;outline-offset:3px}[data-block].mb-sel{outline:2px solid #da7756 !important;outline-offset:3px}[data-block].mb-done{outline:2px solid #16a34a;outline-offset:3px}[data-block].mb-edit{outline:2px dashed #da7756 !important;outline-offset:3px;cursor:text}'
const BUB_W = 320
const BAR_H = 32   // 움직이는 칸 단추 묶음 자리(화면 px)

export function DocView({ it, size, readOnly, threads = {}, onThread, onClose, onHtml, onLives, onPrint, onHwpx, onStatus }) {   // onLives = 움직이는 칸 `lives` { bN: 카드 HTML }(3단계 ②)   // threads·onThread = 블록 대화(말풍선 대화 저장소, 키 「문서 _id#bN」 — 창을 닫아도 남음)
  const frame = useRef(null), scroller = useRef(null), swaps = useRef({}), keepTop = useRef(0)
  const [docH, setDocH] = useState(1200), [pick, setPick] = useState(null)   // pick = { bid, kind, top, left, right } (창 안 px)
  const tkey = bid => `${it._id}#${bid}`, talk = bid => threads[tkey(bid)] || []
  const [draft, setDraft] = useState(''), [busy, setBusy] = useState(''), [err, setErr] = useState(''), [done, setDone] = useState('')
  const pageW = docPageW(it), winW = Math.min(pageW + 48, size.w - 32), scale = Math.min(1, (winW - 40) / pageW), winH = size.h - 24
  // 글자 손으로 고치기(3단계 ①) — 두 번 누르기 = 그 블록만 contenteditable, 바깥 누르기 = 저장(그 블록 하나만 원래 문서 글에 끼움)·Esc = 취소
  const edit = useRef(null), clickT = useRef(0), [editBid, setEditBid] = useState('')
  // 움직이는 칸(3단계 ②) — 문서 글은 늘 멈춘 모습(인쇄·한글 파일·카드), 움직이는 판은 `it.lives[bN]`. ▶ = 그 블록 자리를 스크립트 켠 틀(livecard.js)로 덮음
  const lives = it.lives || {}, [play, setPlay] = useState(''), [rects, setRects] = useState({})
  function measure() {
    const d = frame.current?.contentDocument; if (!d) return
    const out = {}
    for (const bid of Object.keys(it.lives || {})) {
      const el = d.querySelector(`[data-block="${bid}"]`); if (!el) continue
      if (el.dataset.mbMt == null) { el.dataset.mbStyle = el.getAttribute('style') || ''; el.dataset.mbMt = d.defaultView.getComputedStyle(el).marginTop }   // ▶ 단추 자리 = 블록 위 여백을 단추 높이만큼(이 창에서만 — 문서 글은 그대로)
      el.style.marginTop = `calc(${el.dataset.mbMt} + ${Math.ceil(BAR_H / scale)}px)`
      el.style.minHeight = bid === play ? Math.ceil(el.getBoundingClientRect().width * LIVE_H / LIVE_W) + 'px' : ''   // 움직이는 동안만 칸을 카드 비율만큼(문서 글은 안 바뀜)
      const r = el.getBoundingClientRect(); out[bid] = { x: r.left, y: r.top, w: r.width, h: r.height }
    }
    setRects(out); setDocH(Math.max(400, d.documentElement.scrollHeight))
  }
  useEffect(measure, [play, it.lives])
  const bare = el => {   // 이 창이 붙인 자리 표시(움직이는 칸 여백)를 뗀 원래 모양의 outerHTML
    const c = el.cloneNode(true)
    if (c.dataset.mbMt != null) { const st = c.dataset.mbStyle; if (st) c.setAttribute('style', st); else c.removeAttribute('style') }
    delete c.dataset.mbMt; delete c.dataset.mbStyle
    return c.outerHTML
  }
  const fin = useRef(null); fin.current = save => {
    const e = edit.current; if (!e) return false
    edit.current = null; setEditBid('')
    const changed = e.el.innerHTML !== e.before
    if (!save) e.el.innerHTML = e.before
    e.el.removeAttribute('contenteditable'); e.el.classList.remove('mb-edit')
    if (!save || !changed) return true
    try {
      keepTop.current = scroller.current?.scrollTop || 0
      if (!onHtml(spliceBlock(it.html, e.bid, cleanEdited(bare(e.el))), '글자 고침')) throw new Error('칠판 문서를 못 바꿨어요')
      onStatus?.(`${e.bid} 글자를 고쳤어요 — Ctrl+Z로 되돌려요`)
    } catch (x) { setErr(String(x.message || x)) }
    return true
  }
  const esc = useRef(null); esc.current = () => (edit.current ? fin.current(false) : pick ? setPick(null) : onClose())
  useEffect(() => { const k = e => { if (e.key === 'Escape') esc.current() }; window.addEventListener('keydown', k); return () => window.removeEventListener('keydown', k) }, [])   // 초점이 창 밖(말 칸이 닫힌 뒤 등)일 때   // Esc = 말 칸 먼저, 그다음 창(창 밖으로 글쇠를 안 내보내서 여기서 받음 — 문서 틀 안 글쇠도)
  function onLoad() {
    const d = frame.current?.contentDocument; if (!d) return
    measure()
    if (scroller.current) scroller.current.scrollTop = keepTop.current
    if (readOnly) return
    d.addEventListener('keydown', e => { if (e.key === 'Escape') esc.current() })
    const s = d.createElement('style'); s.textContent = PICK_CSS; d.head?.appendChild(s)
    if (done) d.querySelector(`[data-block="${done}"]`)?.classList.add('mb-done')
    let swallow = false
    d.addEventListener('mousedown', e => { if (edit.current && !edit.current.el.contains(e.target)) { fin.current(true); swallow = true } })
    d.addEventListener('click', e => {
      if (swallow) { swallow = false; e.preventDefault(); return }
      if (edit.current?.el.contains(e.target)) return   // 고치는 중인 블록 안 = 글자 자리 옮기기
      const el = e.target.closest?.('[data-block]'); if (!el) return
      e.preventDefault(); clearTimeout(clickT.current)
      if (e.detail > 1) return   // 두 번 누르기의 두 번째 = 아래 dblclick이 맡음
      clickT.current = setTimeout(() => {   // 한 번 누르기 = 말 칸(두 번 누르기와 갈리게 잠깐 기다림)
        d.querySelectorAll('.mb-sel').forEach(x => x.classList.remove('mb-sel')); el.classList.add('mb-sel')
        const r = el.getBoundingClientRect(), sc = scroller.current, off = frame.current.offsetLeft
        setPick({ bid: el.dataset.block, kind: el.dataset.kind || '', top: r.top * scale - (sc?.scrollTop || 0) + 44, left: off + r.left * scale, right: off + r.right * scale })
        setErr(''); setDraft('')
      }, 230)
    })
    d.addEventListener('dblclick', e => {
      const el = e.target.closest?.('[data-block]'); if (!el || edit.current?.el === el) return
      clearTimeout(clickT.current)
      if (!handEditable(el.dataset.kind)) { onStatus?.('그래프·그림은 한 번 눌러 AI에게 고쳐 달라고 하세요'); return }
      fin.current(true); setPick(null); d.querySelectorAll('.mb-sel').forEach(x => x.classList.remove('mb-sel'))
      edit.current = { el, bid: el.dataset.block, before: el.innerHTML }
      el.setAttribute('contenteditable', 'true'); el.setAttribute('spellcheck', 'false'); el.classList.add('mb-edit'); el.focus()
      setEditBid(el.dataset.block); setErr('')
    })
    d.addEventListener('paste', e => {   // 붙여넣기는 글자만(바깥 HTML이 문서에 섞이지 않게)
      if (!edit.current) return
      e.preventDefault(); d.execCommand('insertText', false, e.clipboardData?.getData('text/plain') || '')
    })
    d.addEventListener('drop', e => { if (edit.current) e.preventDefault() })
  }
  async function send() {
    const q = draft.trim(); if (!q || busy || !pick) return
    const bid = pick.bid, mine = { role: 'user', content: q, at: Date.now() }, msgs = [...talk(bid), mine]
    onThread?.(tkey(bid), msgs); setDraft(''); setBusy(bid); setErr('')
    try {
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() },
        body: JSON.stringify({ kind: 'block', board: DOC_NAME, doc: it.html, block: bid, messages: msgs.map(({ role, content }) => ({ role, content })), ...(pick.live && lives[bid] ? { live: true, live_html: lives[bid] } : {}) }) })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      keepTop.current = scroller.current?.scrollTop || 0
      const k = `${bid}:${msgs.length}`
      if (d.kind === 'block_live') {   // 움직이는 판 = 문서 글은 그대로, lives만
        const after = { ...lives, [bid]: d.live }
        if (!onLives?.(after)) throw new Error('칠판 문서를 못 바꿨어요')
        swaps.current[k] = { before: it.lives, after, on: true, field: 'lives' }; setPlay(bid); setPick(p => p && { ...p, live: true, kind: 'live' })
      } else {
        if (!onHtml(d.html)) throw new Error('칠판 문서를 못 바꿨어요')
        swaps.current[k] = { before: it.html, after: d.html, on: true }
      }
      onThread?.(tkey(bid), [...msgs, { role: 'assistant', content: d.content || '고쳤어요', swap: k, model: d.model, credits: d.credits, at: Date.now() }])
      setDone(bid); onStatus?.(d.kind === 'block_live' ? `${bid}를 움직여 볼 수 있어요 — 인쇄엔 멈춘 모습` : `${bid}만 고쳤어요 — Ctrl+Z로 되돌려요`)
    } catch (e) { setErr(String(e.message || e)) } finally { setBusy('') }
  }
  function flip(k) { const s = swaps.current[k]; if (!s) return; keepTop.current = scroller.current?.scrollTop || 0; if ((s.field === 'lives' ? onLives : onHtml)?.(s.on ? s.before : s.after)) { s.on = !s.on; setDraft(x => x + '') } }
  function dropLive(bid) { const { [bid]: _, ...rest } = lives; if (play === bid) setPlay(''); if (onLives?.(Object.keys(rest).length ? rest : undefined)) onStatus?.(`${bid}의 움직임을 뺐어요 — Ctrl+Z로 되돌려요`) }
  function talkLive(bid) { const r = rects[bid]; if (!r) return; const sc = scroller.current, off = frame.current.offsetLeft
    setPick({ bid, kind: 'live', live: true, top: r.y * scale - (sc?.scrollTop || 0) + 44, left: off + r.x * scale, right: off + (r.x + r.w) * scale }); setErr(''); setDraft('') }   // 표시만 다시 그림
  const fx = Math.max(0, (winW - pageW * scale) / 2)
  const liveBtn = on => ({ all: 'unset', cursor: 'pointer', font: `600 12px ${F}`, padding: '3px 9px', borderRadius: 7, background: on ? 'var(--mb-accent)' : '#fff', color: on ? '#fff' : '#18181b', border: on ? 0 : '1px solid #d4d4d8', boxShadow: '0 1px 4px rgba(0,0,0,.12)' })
  const btn = { all: 'unset', cursor: 'pointer', font: `600 12.5px ${F}`, padding: '4px 10px', borderRadius: 7, border: `1px solid ${C.line}`, color: C.ink }
  const bx = pick ? (pick.right + 12 + BUB_W <= winW - 8 ? pick.right + 12 : Math.max(8, Math.min(winW - BUB_W - 8, pick.left - 12 - BUB_W >= 8 ? pick.left - 12 - BUB_W : pick.right - BUB_W))) : 0
  const by = pick ? Math.max(52, Math.min(pick.top, winH - 230)) : 0
  const msgs = pick ? talk(pick.bid) : []
  return <div data-testid="doc-view" onPointerDown={e => { e.stopPropagation(); if (edit.current) fin.current(true) }} onWheel={e => e.stopPropagation()} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') esc.current() }}
    style={{ position: 'absolute', inset: 0, zIndex: 9, background: 'rgba(24,24,27,.42)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start', paddingTop: 12 }}
    onClick={e => { if (e.target === e.currentTarget) onClose() }}>
    <div role="dialog" aria-label={`문서 — ${it.title || ''}`} style={{ position: 'relative', width: winW, height: winH, background: C.card, color: C.ink, borderRadius: 12, boxShadow: '0 8px 28px rgba(0,0,0,.28)', display: 'flex', flexDirection: 'column', overflow: 'hidden', font: `400 13px/1.5 ${F}` }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 10px 9px 14px', borderBottom: `1px solid ${C.line}`, flex: 'none' }}>
        <b style={{ font: `700 14px ${F}`, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📄 {it.title || '문서'}</b>
        <span data-testid="doc-hint" style={{ flex: 1, minWidth: 0, color: editBid ? 'var(--mb-accent)' : C.muted, font: `400 12px ${F}`, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textAlign: 'right', paddingRight: 4 }}>
          {readOnly ? '' : editBid ? '글자 고치는 중 — 바깥 누르기 = 저장 · Esc = 취소' : '누르기 = AI로 고치기 · 두 번 누르기 = 글자 고치기'}</span>
        <button data-testid="doc-print" style={btn} onClick={onPrint} title="새 탭에서 열어 Ctrl+P — 인쇄·PDF로 저장">인쇄 · PDF</button>
        {onHwpx && <button style={btn} onClick={onHwpx}>한글 파일</button>}
        <button data-testid="doc-close" title="닫기(Esc)" onClick={onClose} style={{ ...btn, border: 0, color: C.muted, fontSize: 15, padding: '2px 8px' }}>✕</button>
      </div>
      <div ref={scroller} onScroll={() => pick && setPick(null)} style={{ flex: 1, overflow: 'auto', background: '#fff', position: 'relative' }}>
        <div style={{ height: docH * scale, position: 'relative' }}>
          <iframe ref={frame} data-testid="doc-frame" title={it.title || '문서'} srcDoc={it.html} sandbox="allow-same-origin" scrolling="no" onLoad={onLoad}
            style={{ position: 'absolute', left: fx, top: 0, width: pageW, height: docH, border: 0, transform: `scale(${scale})`, transformOrigin: '0 0', background: '#fff' }} />
          {Object.entries(rects).filter(([bid]) => lives[bid]).map(([bid, r]) => <div key={bid}>
            {play === bid && <iframe data-testid="block-live" data-block={bid} title={`${bid} 움직이는 칸`} srcDoc={liveSrc(lives[bid])} sandbox="allow-scripts" csp={LIVE_CSP} scrolling="no"
              style={{ position: 'absolute', left: fx + r.x * scale, top: r.y * scale, width: r.w, height: r.h, border: 0, transform: `scale(${scale})`, transformOrigin: '0 0', background: '#fff', boxShadow: '0 0 0 2px #da7756' }} />}
            <div data-testid="live-bar" data-block={bid} style={{ position: 'absolute', left: fx + (r.x + r.w) * scale, top: Math.max(0, r.y * scale - BAR_H + 2), transform: 'translateX(-100%)', display: 'flex', gap: 4, zIndex: 1, width: 'max-content', whiteSpace: 'nowrap' }}>
              <button data-testid="live-play" style={liveBtn(play === bid)} onClick={() => setPlay(p => (p === bid ? '' : bid))} title={play === bid ? '멈춘 모습(인쇄에 나가는 모습)으로' : '이 칸을 직접 움직여 보기'}>{play === bid ? '■ 멈춘 모습' : '▶ 움직여 보기'}</button>
              {!readOnly && play === bid && <button data-testid="live-talk" style={liveBtn()} onClick={() => talkLive(bid)}>고치기</button>}
              {!readOnly && <button data-testid="live-drop" style={liveBtn()} onClick={() => dropLive(bid)} title="움직이는 판 빼기(문서 글은 그대로)">빼기</button>}
            </div>
          </div>)}
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
              {swaps.current[m.swap] && <div style={{ marginTop: 4 }}><button data-testid="block-flip" style={{ ...btn, font: `400 11.5px ${F}`, padding: '2px 7px', color: C.muted }} onClick={() => flip(m.swap)}>{swaps.current[m.swap].on ? '원래대로' : '바꾼 것으로'}</button></div>}
              {m.model && <div style={{ font: `400 10.5px ${F}`, color: C.muted, marginTop: 2 }}>{m.model}{m.credits ? ` · 약 ${Math.round(m.credits * 10) / 10}크레딧` : ''}</div>}</div>)}
          {busy === pick.bid && <div data-testid="block-busy" style={{ display: 'flex', gap: 6, alignItems: 'center', color: C.muted, fontSize: 12.5 }}><Spinner />이 블록만 다시 쓰는 중…</div>}
          {err && <div data-testid="block-err" style={{ color: '#dc2626', fontSize: 12.5 }}>{err}</div>}
        </div>}
        <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', padding: '8px 10px 10px', borderTop: msgs.length ? `1px solid ${C.line}` : 0 }}>
          <textarea data-testid="block-input" className="mb-field" autoFocus rows={2} value={draft} placeholder={pick.live ? '움직이는 칸을 어떻게 고칠까요? 예: 느리게 · 값 하나 더' : '이 부분을 어떻게 할까요? 예: 쉬운 말로 · 그림 넣어 줘 · 움직이게'} onChange={e => setDraft(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }}
            style={{ flex: 1, minWidth: 0, resize: 'none', border: `1px solid ${C.line}`, borderRadius: 8, padding: '6px 8px', font: `400 13px/1.5 ${F}`, background: 'transparent', color: C.ink, outline: 'none' }} />
          <button data-testid="block-send" disabled={!!busy} onClick={send} style={{ all: 'unset', cursor: busy ? 'default' : 'pointer', height: 30, padding: '0 12px', display: 'flex', alignItems: 'center', borderRadius: 7, background: 'var(--mb-accent)', color: '#fff', font: `700 12.5px ${F}`, opacity: busy ? 0.6 : 1 }}>보내기</button>
        </div>
      </div>}
    </div>
  </div>
}
