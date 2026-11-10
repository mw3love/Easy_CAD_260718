// 📄 문서 큰 창(2026-11-09 문서 통합 2단계 — 시안 B: Artifact `MXRQVg7tBZH6sbNTQagnNx`). 카드 ↗·두 번 누르기 = 칠판 위 큰 창.
// 블록(`data-block`)에 마우스를 올리면 테두리, 누르면 그 블록의 말 칸 → 서버 `/api/chat` `kind: 'block'`이 그 블록만 다시 써서 문서 전체를 돌려줌
// → 칠판 문서에 바로(Ctrl+Z 한 번, 「원래대로 ↔ 바꾼 것」은 이 창에만 기억). 인쇄·한글 파일은 위 막대(옛 「크게 보기」 새 탭 = 인쇄).
// 문서 틀은 스크립트 없이 `allow-same-origin`만 — 앱이 블록을 재고 누르기를 받으려고(문서 글은 서버 `clean_html`이 이미 청소).
// 2026-11-10 화면 검사 7단계: 진짜 창(<dialog> — 열면 창으로 초점·Tab은 창 안·닫으면 연 자리), 블록 글쇠 길(Tab으로 블록 · Enter = 말 칸 · F2 = 글자 고치기 ·
// Ctrl+Enter = 저장 · Esc = 취소), 블록 이름 = 블록 첫 낱말(속 이름 b2 대신), 블록 색 = 칠판과 같게(고름 = 선택 파랑 · 올림 = 회색 · 고침 = 초록 「✓ 고침」).
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { DOC_NAME } from './doc.js'
import { keyHeaders } from './kairosKey.js'
import { Spinner } from './chat.jsx'
import { docPageW } from './render.jsx'
import { spliceBlock, cleanEdited, handEditable } from './docblock.js'
import { LIVE_CSP, LIVE_W, LIVE_H, liveSrc } from './livecard.js'
import { aiError } from '../chatFormat.js'
import { btnSecondary, useModalDialog } from './ui.jsx'
import { Composer } from './composer.jsx'
import { keyLabel } from './keylabel.js'

const F = "'Pretendard', sans-serif"
const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)' }
const KIND = { text: '글', table: '표', chart: '그래프', image: '그림', box: '상자', live: '움직이는 카드' }
// 틀 안 블록 색 — 문서 틀은 따로 문서라 앱 변수·light-dark()가 안 먹음 → 값을 직접(칠판 Editor `BLUE`·`--mb-ctl`의 밝게 값)
// 문서 종이는 어두운 화면에서도 흰색이라 늘 밝게 값(어둡게 #89b4fa는 흰 종이 위 2.11 — 메모 주소 색과 같은 판단)
const pickCss = () => { const sel = '#3b82f6', hov = '#8b8b94', ring = '#2563eb'
  return `[data-block]{cursor:pointer}[data-block]:hover{outline:2px solid ${hov};outline-offset:3px}[data-block]:focus-visible{outline:2px solid ${ring};outline-offset:3px}`
    + `[data-block].mb-done{outline:2px solid #16a34a;outline-offset:3px}[data-block].mb-sel{outline:2px solid ${sel} !important;outline-offset:3px}[data-block].mb-edit{outline:2px dashed ${sel} !important;outline-offset:3px;cursor:text}` }
const BUB_W = 320
const BAR_H = 32   // 움직이는 카드 단추 묶음 자리(화면 px)
// 블록 이름 = 블록 첫 낱말(열 글자 안쪽 + …) — 글이 없으면 「N번째 덩어리」(2026-11-10 사용자 결정 — 「b2 · 글」은 속 이름이었음)
export function blockName(el, bid) {
  const t = String(el?.textContent || '').replace(/\s+/g, ' ').trim()
  if (!t) { const n = +String(bid || '').replace(/\D/g, ''); return n ? `${n}번째 덩어리` : '이 덩어리' }
  let s = ''; for (const w of t.split(' ')) { const nx = s ? `${s} ${w}` : w; if (nx.length > 10) break; s = nx }
  if (!s) s = t.slice(0, 10)
  return s.length < t.length ? `${s} …` : s
}
// 서버 답 글 속 블록 번호(「b2만 고쳤어요」·「b2를 움직여 볼 수 있게」) → 블록 이름
const named = (txt, bid, name) => String(txt || '').replace(new RegExp(`^${bid}를 `), `「${name}」 부분을 `).replace(new RegExp(`^${bid}(?=만 )`), `「${name}」`)

export function DocView({ it, size, readOnly, threads = {}, onThread, onClose, onHtml, onLives, onPrint, onHwpx, onStatus }) {   // onLives = 움직이는 카드 `lives` { bN: 카드 HTML }(3단계 ②)   // threads·onThread = 블록 대화(말풍선 대화 저장소, 키 「문서 _id#bN」 — 창을 닫아도 남음)
  const frame = useRef(null), scroller = useRef(null), swaps = useRef({}), keepTop = useRef(0), dlg = useRef(null), win = useRef(null), bub = useRef(null), inp = useRef(null), alive = useRef(true)
  const [docH, setDocH] = useState(1200), [pick, setPick] = useState(null)   // pick = { bid, kind, name, top, left, right } (창 안 px)
  const tkey = bid => `${it._id}#${bid}`, talk = bid => threads[tkey(bid)] || []
  const [draft, setDraft] = useState(''), [busy, setBusy] = useState(''), [err, setErr] = useState(''), [done, setDone] = useState(''), [doneR, setDoneR] = useState(null), [bubH, setBubH] = useState(0)
  const vw = window.innerWidth || size.w, vh = window.innerHeight || size.h   // 진짜 창 = 화면 전체 위(칠판 칸만이 아니라)
  const pageW = docPageW(it), winW = Math.min(pageW + 48, vw - 32), scale = Math.min(1, (winW - 40) / pageW), winH = vh - 24, narrow = winW < 720
  const uid = useId()
  // 닫으면 초점 = 연 자리(카드를 연 대화창 미리보기·메뉴를 연 단추). 칠판(대기 편집기)에서 열었으면 칠판에 맡김(4단계 함정 — 그 편집기로 돌아가면 치는 글이 도형에 안 들어갔음)
  const [back] = useState(() => { const a = document.activeElement; return !a || a === document.body || a.closest?.('[data-armed], [data-testid=board]') ? document.body : a })
  useModalDialog(dlg, back, () => win.current?.focus({ preventScroll: true }))
  useEffect(() => () => { alive.current = false; const a = document.activeElement; if (a?.closest?.('[data-armed]')) a.blur() }, [])   // 브라우저가 창 닫을 때 앞 초점(대기 편집기)으로 돌려놓는 것도 칠판에 맡김
  // 글자 손으로 고치기(3단계 ①) — 두 번 누르기·F2 = 그 블록만 contenteditable, 바깥 누르기·Ctrl+Enter = 저장(그 블록 하나만 원래 문서 글에 끼움)·Esc = 취소
  const edit = useRef(null), clickT = useRef(0), [editBid, setEditBid] = useState(''), wantFocus = useRef('')   // wantFocus = 글쇠로 저장한 블록 — 문서가 다시 열리면 그 블록으로
  // 움직이는 카드(3단계 ②) — 문서 글은 늘 멈춘 모습(인쇄·한글 파일·카드), 움직이는 판은 `it.lives[bN]`. ▶ = 그 블록 자리를 스크립트 켠 틀(livecard.js)로 덮음
  const lives = it.lives || {}, [play, setPlay] = useState(''), [rects, setRects] = useState({})
  const blockEl = bid => frame.current?.contentDocument?.querySelector(`[data-block="${bid}"]`)
  const nameOf = bid => blockName(blockEl(bid), bid)
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
    const de = done ? d.querySelector(`[data-block="${done}"]`) : null, dr = de?.getBoundingClientRect()
    setDoneR(dr ? { x: dr.left, y: dr.top } : null)
    setRects(out); setDocH(Math.max(400, d.documentElement.scrollHeight))
  }
  useEffect(measure, [play, it.lives, done])
  const bare = el => {   // 이 창이 붙인 자리 표시(움직이는 카드 여백·글쇠 길)를 뗀 원래 모양의 outerHTML
    const c = el.cloneNode(true)
    if (c.dataset.mbMt != null) { const st = c.dataset.mbStyle; if (st) c.setAttribute('style', st); else c.removeAttribute('style') }
    if (c.dataset.mbTab != null) c.removeAttribute('tabindex')
    delete c.dataset.mbMt; delete c.dataset.mbStyle; delete c.dataset.mbTab
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
      const name = blockName(e.el, e.bid)
      if (!onHtml(spliceBlock(it.html, e.bid, cleanEdited(bare(e.el))), '글자 고침')) throw new Error('칠판 문서를 못 바꿨어요')
      onStatus?.(`「${name}」 글자를 고쳤어요 — ${keyLabel('Ctrl+Z')}로 되돌려요`)
    } catch (x) { setErr(String(x.message || x)) }
    return true
  }
  const refocus = bid => { const el = blockEl(bid); if (el) el.focus({ preventScroll: true }); else win.current?.focus({ preventScroll: true }) }   // 말 칸·글자 고치기를 닫으면 그 블록으로(글쇠로 이어 가게)
  const esc = useRef(null); esc.current = () => {
    if (edit.current) { const bid = edit.current.bid; fin.current(false); refocus(bid); return }
    if (pick) { const bid = pick.bid; setPick(null); refocus(bid); return }
    onClose()
  }
  useEffect(() => { if (!pick) frame.current?.contentDocument?.querySelectorAll('.mb-sel').forEach(x => x.classList.remove('mb-sel')) }, [pick])
  useEffect(() => { if (pick) inp.current?.focus({ preventScroll: true }) }, [pick?.bid])   // eslint-disable-line react-hooks/exhaustive-deps
  useLayoutEffect(() => { const h = bub.current?.offsetHeight || 0; if (h !== bubH) setBubH(h) })   // 말 칸 자리 = 실제 높이로(작은 창에서 아래가 잘렸음)
  function openPick(el) {   // 한 번 누르기·Enter = 그 블록 말 칸
    const d = frame.current?.contentDocument; if (!d) return
    d.querySelectorAll('.mb-sel').forEach(x => x.classList.remove('mb-sel')); el.classList.add('mb-sel')
    const r = el.getBoundingClientRect(), sc = scroller.current, off = frame.current.offsetLeft
    setPick({ bid: el.dataset.block, kind: el.dataset.kind || '', name: blockName(el, el.dataset.block), top: r.top * scale - (sc?.scrollTop || 0) + (sc?.offsetTop || 44), left: off + r.left * scale, right: off + r.right * scale })
    setErr(''); setDraft('')
  }
  function startEdit(el) {   // 두 번 누르기·F2 = 글자 손으로 고치기
    if (!handEditable(el.dataset.kind)) { onStatus?.('그래프·그림은 한 번 눌러(Enter) AI에게 고쳐 달라고 하세요'); return }
    fin.current(true); setPick(null); frame.current?.contentDocument?.querySelectorAll('.mb-sel').forEach(x => x.classList.remove('mb-sel'))
    edit.current = { el, bid: el.dataset.block, before: el.innerHTML }
    el.setAttribute('contenteditable', 'true'); el.setAttribute('spellcheck', 'false'); el.classList.add('mb-edit'); el.focus()
    setEditBid(el.dataset.block); setErr('')
  }
  function onLoad() {
    const d = frame.current?.contentDocument; if (!d) return
    measure()
    if (scroller.current) scroller.current.scrollTop = keepTop.current
    if (readOnly) return
    const s = d.createElement('style'); s.textContent = pickCss(); d.head?.appendChild(s)
    for (const el of d.querySelectorAll('[data-block]')) if (!el.hasAttribute('tabindex')) { el.setAttribute('tabindex', '0'); el.dataset.mbTab = '' }   // 글쇠 길(문서 글엔 안 남김 — bare)
    if (done) d.querySelector(`[data-block="${done}"]`)?.classList.add('mb-done')
    if (wantFocus.current) { d.querySelector(`[data-block="${wantFocus.current}"]`)?.focus({ preventScroll: true }); wantFocus.current = '' }
    d.addEventListener('keydown', e => {
      if (e.key === 'Escape') { e.preventDefault(); esc.current(); return }
      if (edit.current) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); const bid = edit.current.bid; wantFocus.current = bid; fin.current(true); refocus(bid) } return }   // Ctrl+Enter = 저장
      const el = e.target.closest?.('[data-block]'); if (!el || e.target !== el || e.altKey || e.ctrlKey || e.metaKey) return
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); openPick(el) }
      else if (e.key === 'F2') { e.preventDefault(); startEdit(el) }
    })
    let swallow = false
    d.addEventListener('mousedown', e => { if (edit.current && !edit.current.el.contains(e.target)) { fin.current(true); swallow = true } })
    d.addEventListener('click', e => {
      if (swallow) { swallow = false; e.preventDefault(); return }
      if (edit.current?.el.contains(e.target)) return   // 고치는 중인 블록 안 = 글자 자리 옮기기
      const el = e.target.closest?.('[data-block]'); if (!el) return
      e.preventDefault(); clearTimeout(clickT.current)
      if (e.detail > 1) return   // 두 번 누르기의 두 번째 = 아래 dblclick이 맡음
      clickT.current = setTimeout(() => openPick(el), 230)   // 한 번 누르기 = 말 칸(두 번 누르기와 갈리게 잠깐 기다림)
    })
    d.addEventListener('dblclick', e => {
      const el = e.target.closest?.('[data-block]'); if (!el || edit.current?.el === el) return
      clearTimeout(clickT.current); startEdit(el)
    })
    d.addEventListener('paste', e => {   // 붙여넣기는 글자만(바깥 HTML이 문서에 섞이지 않게)
      if (!edit.current) return
      e.preventDefault(); d.execCommand('insertText', false, e.clipboardData?.getData('text/plain') || '')
    })
    d.addEventListener('drop', e => { if (edit.current) e.preventDefault() })
  }
  // base·at = 「다시 보내기」 — 실패한 마지막 질문을 같은 시각으로 다시(말풍선 대화 저장소는 서버가 합칠 때 메시지를 안 지워서 새 시각이면 두 번 쌓임 — 6단계 함정)
  async function send(q, base, at = Date.now()) {
    if (!q || busy || !pick) return
    const bid = pick.bid, name = pick.name, mine = { role: 'user', content: q, at }, msgs = [...base, mine]
    onThread?.(tkey(bid), msgs); setBusy(bid); setErr('')
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
      setDone(bid); onStatus?.(d.kind === 'block_live' ? `「${name}」 부분을 움직여 볼 수 있어요 — 인쇄엔 멈춘 모습` : `「${name}」만 고쳤어요 — ${keyLabel('Ctrl+Z')}로 되돌려요`)
    } catch (e) { setErr(aiError(e)) } finally { setBusy('') }
  }
  const sendDraft = () => { const q = draft.trim(); if (!q || busy || !pick) return; setDraft(''); send(q, talk(pick.bid)) }
  const resend = () => { const t = talk(pick?.bid), last = t.at(-1); if (last?.role === 'user') send(last.content, t.slice(0, -1), last.at) }   // 오류 뒤 「다시 보내기」 = 마지막 말 그대로(말풍선과 같게)
  function flip(k) { const s = swaps.current[k]; if (!s) return; keepTop.current = scroller.current?.scrollTop || 0; if ((s.field === 'lives' ? onLives : onHtml)?.(s.on ? s.before : s.after)) { s.on = !s.on; setDraft(x => x + '') } }
  function dropLive(bid) { const name = nameOf(bid), { [bid]: _, ...rest } = lives; if (play === bid) setPlay(''); if (onLives?.(Object.keys(rest).length ? rest : undefined)) onStatus?.(`「${name}」의 움직임을 뺐어요 — ${keyLabel('Ctrl+Z')}로 되돌려요`) }
  function talkLive(bid) { const r = rects[bid]; if (!r) return; const sc = scroller.current, off = frame.current.offsetLeft
    setPick({ bid, kind: 'live', live: true, name: nameOf(bid), top: r.y * scale - (sc?.scrollTop || 0) + (sc?.offsetTop || 44), left: off + r.x * scale, right: off + (r.x + r.w) * scale }); setErr(''); setDraft('') }   // 표시만 다시 그림
  const fx = Math.max(0, (winW - pageW * scale) / 2)
  // 움직이는 카드 단추 — 문서 종이(늘 흰색) 위라 값으로. 켜짐 = 위 막대 켜짐과 같게(옅은 코랄 + 진한 코랄 테두리 + 검정 글 — 이 창 코랄 채움은 「보내기」 하나)
  const liveBtn = on => ({ all: 'unset', position: 'relative', cursor: 'pointer', font: `600 12px ${F}`, padding: '3px 9px', borderRadius: 7, background: on ? 'var(--mb-on)' : '#fff', color: '#18181b', border: '1px solid', borderColor: on ? 'transparent' : '#8b8b94', boxShadow: on ? 'var(--mb-on-ring), var(--mb-shadow)' : 'var(--mb-shadow)', backgroundClip: 'padding-box' })
  const btn = { ...btnSecondary, flex: 'none', whiteSpace: 'nowrap' }
  const bubW = Math.min(BUB_W, winW - 16), bubMax = Math.min(360, winH - 16)
  const bx = pick ? (pick.right + 12 + bubW <= winW - 8 ? pick.right + 12 : Math.max(8, Math.min(winW - bubW - 8, pick.left - 12 - bubW >= 8 ? pick.left - 12 - bubW : pick.right - bubW))) : 0
  const bh0 = bubH || 230, by = pick ? Math.max(winH - bh0 - 8 >= 52 ? 52 : 8, Math.min(pick.top, winH - bh0 - 8)) : 0
  const msgs = pick ? talk(pick.bid) : []
  const hint = readOnly ? '대화창 문서 — 보기·인쇄만(고칠 점은 대화로 말하면 고쳐 써요)' : editBid ? `글자 고치는 중 — 바깥 누르기·${keyLabel('Ctrl+Enter')} = 저장 · Esc = 취소` : '누르기·Enter = AI로 고치기 · 두 번 누르기·F2 = 글자 고치기'
  return <dialog ref={dlg} className="mb-dlg" data-testid="doc-view" aria-label={`문서 — ${it.title || ''}`}
    onCancel={e => { e.preventDefault(); esc.current() /* 초점이 창 바탕(body)일 때의 Esc */ }} onClose={() => { if (alive.current) onClose() }}
    onPointerDown={e => { e.stopPropagation(); if (edit.current) fin.current(true) }} onWheel={e => e.stopPropagation()} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') { e.preventDefault(); esc.current() } }}
    style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', maxWidth: 'none', maxHeight: 'none', margin: 0, padding: '12px 0 0', boxSizing: 'border-box', border: 0, background: 'rgba(24,24,27,.42)', display: 'flex', justifyContent: 'center', alignItems: 'flex-start' }}
    onClick={e => { if (e.target === e.currentTarget) onClose() }}>
    <div ref={win} tabIndex={-1} style={{ position: 'relative', width: winW, height: winH, background: C.card, color: C.ink, borderRadius: 12, boxShadow: 'var(--mb-shadow-lg)', display: 'flex', flexDirection: 'column', overflow: 'clip', font: `400 13px/1.5 ${F}`, outline: 'none' }}>
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', columnGap: 8, rowGap: 2, padding: '9px 10px 9px 14px', borderBottom: `1px solid ${C.line}`, flex: 'none' }}>
        <b style={{ flex: narrow ? '1 1 0' : '0 1 auto', minWidth: 0, font: `700 14px ${F}`, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>📄 {it.title || '문서'}</b>
        <span data-testid="doc-hint" style={{ ...(narrow ? { order: 3, flex: '1 1 100%', textAlign: 'left' } : { flex: 1, textAlign: 'right', paddingRight: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }), minWidth: 0, color: C.muted, font: `${editBid ? 600 : 400} 12px ${F}`, wordBreak: 'keep-all' }}>{hint}</span>
        <button data-testid="doc-print" style={btn} onClick={onPrint} title={`새 탭에서 열어 ${keyLabel('Ctrl+P')} — 인쇄·PDF로 저장`}>인쇄 · PDF</button>
        {onHwpx && <button style={btn} onClick={onHwpx} aria-label="한글 파일로 내려받기 (.hwpx)" title="한글 파일로 내려받기 (.hwpx)">한글 파일</button>}
        <button data-testid="doc-close" className="mb-hit" aria-label="문서 창 닫기" title="닫기 (Esc)" onClick={onClose} style={{ ...btn, position: 'relative', border: 0, color: C.muted, fontSize: 15, padding: '2px 8px' }}>✕</button>
      </div>
      <div ref={scroller} tabIndex={readOnly ? 0 : undefined} aria-label={readOnly ? '문서 내용' : undefined} onScroll={() => pick && setPick(null)} style={{ flex: 1, overflow: 'auto', background: '#fff', position: 'relative' }}>
        <div style={{ height: docH * scale, position: 'relative' }}>
          <iframe ref={frame} data-testid="doc-frame" title={it.title || '문서'} srcDoc={it.html} sandbox="allow-same-origin" scrolling="no" onLoad={onLoad} tabIndex={readOnly ? -1 : undefined}
            style={{ position: 'absolute', left: fx, top: 0, width: pageW, height: docH, border: 0, transform: `scale(${scale})`, transformOrigin: '0 0', background: '#fff' }} />
          {!readOnly && done && doneR && <span data-testid="block-done" aria-hidden="true" style={{ position: 'absolute', left: fx + doneR.x * scale - 3, top: doneR.y * scale - 5, transform: 'translateY(-100%)', padding: '0 7px', borderRadius: 99, background: '#15803d', color: '#fff', font: `600 11px/18px ${F}`, pointerEvents: 'none', whiteSpace: 'nowrap' }}>✓ 고침</span>}
          {Object.entries(rects).filter(([bid]) => lives[bid]).map(([bid, r]) => <div key={bid}>
            {play === bid && <iframe data-testid="block-live" data-block={bid} title={`${nameOf(bid)} — 움직이는 카드`} srcDoc={liveSrc(lives[bid])} sandbox="allow-scripts" csp={LIVE_CSP} scrolling="no"
              style={{ position: 'absolute', left: fx + r.x * scale, top: r.y * scale, width: r.w, height: r.h, border: 0, transform: `scale(${scale})`, transformOrigin: '0 0', background: '#fff', boxShadow: '0 0 0 2px #da7756' }} />}
            <div data-testid="live-bar" data-block={bid} style={{ position: 'absolute', left: fx + (r.x + r.w) * scale, top: Math.max(0, r.y * scale - BAR_H + 2), transform: 'translateX(-100%)', display: 'flex', gap: 4, zIndex: 1, width: 'max-content', whiteSpace: 'nowrap' }}>
              <button data-testid="live-play" aria-pressed={play === bid} style={liveBtn(play === bid)} onClick={() => setPlay(p => (p === bid ? '' : bid))} title={play === bid ? '멈춘 모습(인쇄에 나가는 모습)으로' : '움직이는 카드로 직접 움직여 보기'}>{play === bid ? '■ 멈춘 모습' : '▶ 움직여 보기'}</button>
              {!readOnly && play === bid && <button data-testid="live-talk" style={liveBtn()} onClick={() => talkLive(bid)} aria-label={`「${nameOf(bid)}」 움직이는 카드 고치기`}>고치기</button>}
              {!readOnly && <button data-testid="live-drop" style={liveBtn()} onClick={() => dropLive(bid)} aria-label={`「${nameOf(bid)}」 움직이는 카드 빼기`} title="움직이는 카드 빼기(문서 글은 그대로)">빼기</button>}
            </div>
          </div>)}
        </div>
      </div>
      {pick && <div ref={bub} data-testid="block-bubble" data-block={pick.bid} role="dialog" aria-labelledby={`${uid}-t`} style={{ position: 'absolute', left: bx, top: by, width: bubW, zIndex: 2, background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, boxShadow: 'var(--mb-shadow)', display: 'flex', flexDirection: 'column', maxHeight: bubMax, boxSizing: 'border-box', overflow: 'hidden', wordBreak: 'keep-all', overflowWrap: 'anywhere' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 8px 7px 12px', borderBottom: `1px solid ${C.line}`, flex: 'none' }}>
          <b id={`${uid}-t`} style={{ fontSize: 13, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{pick.name} · {KIND[pick.kind] || '블록'}</b>
          <button className="mb-hit" aria-label="말 칸 닫기" title="닫기 (Esc)" onClick={() => esc.current()} style={{ all: 'unset', position: 'relative', cursor: 'pointer', marginLeft: 'auto', flex: 'none', color: C.muted, padding: '0 6px', fontSize: 14, borderRadius: 4 }}>✕</button>
        </div>
        {(msgs.length > 0 || busy || err) && <div style={{ flex: '1 1 auto', minHeight: 0, overflowY: 'auto', padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {msgs.map((m, i) => m.role === 'user'
            ? <div key={i} style={{ alignSelf: 'flex-end', maxWidth: '88%', background: C.seg, borderRadius: 10, padding: '4px 9px', whiteSpace: 'pre-wrap' }}>{m.content}</div>
            : <div key={i} data-testid="block-a" style={{ alignSelf: 'flex-start', maxWidth: '96%', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: '5px 9px' }}>{named(m.content, pick.bid, pick.name)}
              {swaps.current[m.swap] && <div style={{ marginTop: 4 }}><button data-testid="block-flip" style={{ ...btnSecondary, font: `400 11.5px ${F}`, padding: '2px 7px' }} onClick={() => flip(m.swap)}>{swaps.current[m.swap].on ? '원래대로' : '바꾼 것으로'}</button></div>}
              {m.model && <div style={{ font: `400 11px ${F}`, fontVariantNumeric: 'tabular-nums', color: C.muted, marginTop: 2 }}>{m.model}{m.credits ? ` · 약 ${Math.round(m.credits * 10) / 10}크레딧` : ''}</div>}</div>)}
          {busy === pick.bid && <div data-testid="block-busy" role="status" style={{ display: 'flex', gap: 6, alignItems: 'center', color: C.muted, fontSize: 12.5 }}><Spinner />이 부분만 다시 쓰는 중…</div>}
          {err && <div data-testid="block-err" role="alert" style={{ color: 'var(--mb-danger-ink)', fontSize: 12.5 }}>{err}
            {msgs.at(-1)?.role === 'user' && !busy && <button data-testid="block-retry" style={{ ...btnSecondary, marginLeft: 6, padding: '1px 8px' }} onClick={resend}>다시 보내기</button>}</div>}
        </div>}
        <div style={{ flex: 'none', padding: '8px 10px 10px', borderTop: msgs.length ? `1px solid ${C.line}` : 0 }}>
          <Composer inputRef={inp} inputId="block-input" sendId="block-send" label={`「${pick.name}」 고칠 말`} value={draft} canSend={!!draft.trim() && !busy} busy={!!busy} maxRows={4}
            placeholder={pick.live ? '움직이는 카드를 어떻게 고칠까요? 예: 느리게 · 값 하나 더' : '이 부분을 어떻게 할까요? 예: 쉬운 말로 · 그림 넣어 줘 · 움직이게'}
            onChange={e => setDraft(e.target.value)} onSend={sendDraft} onKeyDown={e => { if (e.key === 'Escape') { e.preventDefault(); esc.current() } }} />
        </div>
      </div>}
    </div>
  </dialog>
}
