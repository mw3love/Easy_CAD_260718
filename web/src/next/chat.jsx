// KAIROS 대화창(직접 만드는 칠판판) — 옛 tldraw 칠판 `src/chat.jsx`를 옮김(§8 항목61 ⓒ 4단계). 칠판 오른쪽 칸, 위 막대 「KAIROS」로 열고 닫음.
// - 묻기: 서버 POST /api/chat(키는 서버 PC에만), 앞 대화를 이어 보냄. 칠판에서 고른 것의 글을 같이 보냄(칩).
// - 「칠판에 붙이기」: 답 → 카드(흰 보드 + 보드 글꼴 글, Editor.pinCard). 붙인 카드는 「칠판에 붙임 ✓」로 찾아감(카드의 .ecad `chat_at` = 답 시각).
// - 대화 기록: 칠판마다 서버(/api/chatlog/<이름>) — 옛 칠판과 같은 기록을 이어 씀. 「새 대화」 = 지금 대화를 `past`로 넘기고 빈 대화(앞 대화가 안 실려 주제가 안 섞임),
//   「지난 대화 ▾」 = 골라 다시 열기(2026-10-20 사용자 — 탭은 360px 칸에 2~3개면 꽉 차서 목록으로). 파일 = { messages, past: [{ at, title, messages }] }.
// - 웹 검색(§8 항목61 ② 담는 법, 2026-10-19): 길은 서버가 고름(판단 모델 jev + 규칙 — `easycad/ai/route.py`), 답 위 표시 「🔎 웹 검색 / 💬 대화」만(옛 「다시 ▾」는 2026-10-20 없앰).
//   검색 답은 쓰인 번호의 출처를 아래에 보이고, 붙이면 요약 메모 + 출처 카드 + 번호 화살표 한 묶음(Editor `cardItems`).
// - 칠판에서(§8 항목61 ③-2): 「지난번·저번·정리해 둔」 → 서버가 이 칠판 글을 뜻으로 찾아 근거로 답, [칠판 n] 고리 = 그 도형으로 가기, 붙이면 근거로 가는 점선 화살표.
import { useEffect, useRef, useState } from 'react'
import { DOC_NAME } from './doc.js'
import { contextText, parseAnswer } from '../chatFormat.js'
import { urlSpans } from './geom.js'
import { MONO_FONT } from './render.jsx'
import { siteOf } from './webcard.js'
import { TIDY_RE } from './tidy.js'
import { getKairosKey, KEY_RE, keyHeaders, setKairosKey } from './kairosKey.js'
const LINK_CHAT = '#4f8fe8'
// 정리 문서 크게 보기 — 새 탭에 그 HTML(인쇄·PDF는 그 탭에서 Ctrl+P)
const openHtml = html => { const u = URL.createObjectURL(new Blob([html || ''], { type: 'text/html;charset=utf-8' })); window.open(u, '_blank'); setTimeout(() => URL.revokeObjectURL(u), 60_000) }
// 답 종류 — [표시, 표시 꾸밈] — 서버가 고른 길(판단 모델 jev + 규칙, `easycad/ai/route.py`)을 답 위에 보이기만.
// 옛 「다시 ▾」(다른 종류로 다시 묻기)는 2026-10-20 없앰(사용자: 대화창 하나로 다 — 길은 앱이 고르고, 틀리면 말로 다시)
const KINDS = {
  chat: ['💬 대화', null],
  search: ['🔎 웹 검색', { color: '#2f80ed', background: 'rgba(47,128,237,.12)' }],
  board: ['📌 칠판에서', { color: '#d97706', background: 'rgba(245,158,11,.14)' }],
  report: ['📄 정리 문서', { color: '#7c3aed', background: 'rgba(124,58,237,.12)' }],
  tidy: ['🧩 정리정돈', { color: '#0f766e', background: 'rgba(15,118,110,.12)' }],
  image: ['🎨 그림', { color: '#9333ea', background: 'rgba(147,51,234,.12)' }],
}
// 기다리는 동안 보일 말 — 일마다 실제로 일하는 모델(서버 /api/models `jobs`)을 같이(2026-10-20 사용자: 정돈인데 고른 gpt가 보여 헷갈림, 칠판엔 아무 표시가 없어 안 되는 줄 알았음)
const JOB_LABEL = { tidy: '🧩 정리정돈 중', report: '📄 정리 문서 만드는 중', image: '🎨 그림 그리는 중', search: '🔎 웹 검색 중', board: '📌 칠판에서 찾는 중' }
const BOARD_JOBS = new Set(['tidy', 'report'])   // 칠판을 바꾸거나 칠판 자료로 만드는 일 — 칠판 위에도 알약(main `aiBusy`)
// 도는 동그라미(칠판 알약·대화창 「생각 중」 공용)
export const Spinner = () => <><style>{'@keyframes mb-spin{to{transform:rotate(360deg)}}'}</style>
  <span style={{ display: 'inline-block', flex: 'none', width: 11, height: 11, borderRadius: '50%', border: '2px solid #da7756', borderTopColor: 'transparent', animation: 'mb-spin .8s linear infinite' }} /></>

export const CHAT_W = 360
const LOG_URL = `/api/chatlog/${encodeURIComponent(DOC_NAME)}`
const MODEL_KEY = 'magic-board-model'   // 고른 모델은 이 브라우저에만 기억(편의)
const VENDOR = { gpt: 'GPT', gemini: 'Gemini', claude: 'Claude' }
const F = "'Pretendard', sans-serif"
const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', bar: 'var(--mb-bar)', seg: 'var(--mb-seg)' }
const css = {
  float: { position: 'absolute', right: 12, top: 12, bottom: 12, zIndex: 5, maxWidth: 'calc(100% - 24px)', border: `1px solid ${C.line}`, borderRadius: 10, overflow: 'hidden', boxShadow: '0 4px 16px rgba(0,0,0,.12)' },
  panel: { width: CHAT_W, flex: 'none', display: 'flex', flexDirection: 'column', background: C.bar, borderLeft: `1px solid ${C.line}`, font: `400 13.5px/1.55 ${F}`, color: C.ink, minHeight: 0 },
  head: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '10px 12px', borderBottom: `1px solid ${C.line}` },
  msgs: { flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 10 },
  me: { alignSelf: 'flex-end', maxWidth: '92%', background: C.seg, borderRadius: 10, padding: '7px 10px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
  ai: { alignSelf: 'stretch', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: '8px 10px', wordBreak: 'break-word' },
  err: { alignSelf: 'stretch', background: '#fff7ed', border: '1px solid #fdba74', color: '#9a3412', borderRadius: 10, padding: '8px 10px' },
  meta: { font: `400 11px ${F}`, color: C.muted },
  ctx: { display: 'block', font: `500 11px ${F}`, color: '#5aa9ff', marginBottom: 2 },
  pin: { font: `700 12px ${F}`, color: '#da7756', background: 'transparent', border: '1px solid #da7756', borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  ghost: { font: `500 12px ${F}`, color: C.muted, background: 'transparent', border: `1px solid ${C.line}`, borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  foot: { borderTop: `1px solid ${C.line}`, padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6 },
  chip: { alignSelf: 'flex-start', font: `500 11.5px ${F}`, color: '#5aa9ff', background: 'rgba(90,169,255,.15)', borderRadius: 99, padding: '2px 9px' },
  input: { font: `400 13.5px/1.5 ${F}`, border: `1px solid ${C.line}`, borderRadius: 8, padding: '8px 10px', resize: 'none', minHeight: 40, maxHeight: 200, outline: 'none', background: C.card, color: C.ink },
  kind: { font: `600 11px ${F}`, color: C.muted, background: C.seg, borderRadius: 99, padding: '1px 8px' },
  bar: { display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderBottom: `1px solid ${C.line}` },
  drop: { display: 'flex', flexDirection: 'column', maxHeight: 260, overflowY: 'auto', borderBottom: `1px solid ${C.line}`, background: C.card },
  row: { all: 'unset', cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'center', padding: '6px 12px', font: `400 12.5px ${F}`, color: C.ink, borderBottom: `1px solid ${C.line}` },
  select: { font: `500 12px ${F}`, color: C.ink, border: `1px solid ${C.line}`, borderRadius: 6, padding: '2px 4px', background: C.card, maxWidth: 210 },
}

// 답 글 보이기(굵게·목록·제목만 — 카드에 붙는 모양과 같은 규칙)
function Answer({ text }) {
  return <div>{parseAnswer(text).map((ln, i) => {
    if (ln.kind === 'gap') return <div key={i} style={{ height: 6 }} />
    // 답 속 주소 = 누르면 새 탭(대화창은 읽기만 해서 그냥 클릭 — 2026-10-18 사용자)
    const linked = (t, j) => { if (ln.kind === 'code') return t; const sp = urlSpans(t); if (!sp.length) return t; const out = []; let at = 0
      sp.forEach(([s, n, u], k) => { if (s > at) out.push(t.slice(at, s)); out.push(<a key={`${j}-${k}`} href={u} target="_blank" rel="noopener noreferrer" style={{ color: LINK_CHAT, textDecoration: 'underline', wordBreak: 'break-all' }} onPointerDown={e => e.stopPropagation()}>{u}</a>); at = s + n })
      if (at < t.length) out.push(t.slice(at)); return out }
    const parts = ln.parts.map((p, j) => { const c = p.code ? <code style={{ fontFamily: MONO_FONT, fontSize: '0.92em', background: C.seg, borderRadius: 3, padding: '0 3px' }}>{p.text}</code> : linked(p.text, j)   // 글 속 `코드`
      return p.bold || ln.kind === 'h' ? <b key={j}>{c}</b> : <span key={j}>{c}</span> })
    // 코드 줄 — 글꼴은 메모와 같은 Consolas부터('monospace'만 두면 한글 윈도우 기본 고정폭 글꼴이라 \가 ₩로 보였음 — 2026-10-19 사용자), 빈 줄도 한 줄 높이
    if (ln.kind === 'code') return <div key={i} style={{ fontFamily: MONO_FONT, fontSize: 12, whiteSpace: 'pre-wrap', background: C.seg }}>{ln.parts[0].text || ' '}</div>
    if (ln.kind === 'li') return <div key={i} style={{ paddingLeft: 14, textIndent: -12 }}>{ln.mark} {parts}</div>
    return <div key={i} style={ln.kind === 'h' ? { fontWeight: 700, marginTop: 2 } : null}>{parts}</div>
  })}</div>
}

// ed = Editor 손잡이(selTexts·pinCard·showCard), selKey = 고른 것이 바뀔 때 다시 읽게(main이 넘김)
export function ChatPanel({ ed, selKey, floating, onClose, request, onBusy }) {   // onBusy(글) = 칠판 위 알약(정돈·정리 문서 중에만, 끝나면 '')
  const [busyJob, setBusyJob] = useState('')   // 기다리는 일의 종류(모르면 '' = 서버가 짐작)   // request = { id, text, kind } — 칠판에서 시킨 질문(바뀔 때마다 한 번 보냄)   // floating = 좁은 창 — 칠판 위에 뜬 카드(2026-10-19)
  const [msgs, setMsgs] = useState([]), [loaded, setLoaded] = useState(false), [draft, setDraft] = useState(''), [busy, setBusy] = useState(null)
  const [, tick] = useState(0), [models, setModels] = useState(null), [server, setServer] = useState(true), [gone, setGone] = useState({})
  const [model, setModel] = useState(() => { try { return localStorage.getItem(MODEL_KEY) || '' } catch { return '' } })
  const box = useRef(null)
  const [past, setPastState] = useState([]), pastRef = useRef([]), [pastOpen, setPastOpen] = useState(false)   // 지난 대화(새것부터)
  const setPast = p => { pastRef.current = p; setPastState(p) }
  const [keyOpen, setKeyOpen] = useState(false), [keyDraft, setKeyDraft] = useState(''), [myKey, setMyKey] = useState(() => !!getKairosKey())   // 내 KAIROS 키 칸
  // 방금 칠판에 붙인 것은 어디 붙었나 보이게 고른 채로 남는데, 그대로 다음 질문에 실려 갔음(2026-10-19 점검) — 고름이 그대로인 동안은 안 실음
  const [skipSel, setSkipSel] = useState('')
  const sel = selKey && selKey === skipSel ? [] : ed.current?.selTexts() || []   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetch(LOG_URL, { cache: 'no-store' }).then(r => (r.status === 404 ? { messages: [] } : r.ok ? r.json() : Promise.reject(r)))
      .then(d => { setMsgs(d.messages || []); setPast(Array.isArray(d.past) ? d.past : []); setLoaded(true) }).catch(() => { setServer(false); setLoaded(true) })
  }, [])
  useEffect(() => {   // 모델 목록은 키마다 다를 수 있어 키를 바꾸면 다시
    fetch('/api/models', { headers: keyHeaders() }).then(r => r.json()).then(setModels).catch(() => setModels({ featured: {}, error: '모델 목록 못 받음' }))
  }, [myKey])
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight }, [msgs.length, busy])
  const asked = useRef(null)
  useEffect(() => { if (!request || !loaded || asked.current === request.id) return; asked.current = request.id; send(request.text, request.kind) }, [request, loaded])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!busy) return; const t = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(t) }, [busy])

  const useModel = model || models?.default || 'gpt-6.1-sol'
  const save = (next, p = pastRef.current) => fetch(LOG_URL, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ messages: next, ...(p.length ? { past: p } : {}) }) })
    .then(r => setServer(r.ok)).catch(() => setServer(false))
  const update = next => { setMsgs(next); save(next) }

  // 묻기 — history = 지금까지(마지막이 질문), kind = 'search'·'chat'(비면 서버가 짐작) → 답 한 차례
  async function ask(history, kind = '', prevHtml = '') {   // prevHtml = 바로 앞 답이 정리 문서면 그 HTML(「더 짧게」 = 그 문서 고치기 — 서버가 판단)
    const q = history.filter(m => m.role === 'user').at(-1)?.content || ''
    const items = kind === 'tidy' || (!kind && TIDY_RE.test(q)) ? ed.current?.tidyItems() || [] : null   // 정리정돈(「정리해 줘」 ②) — 옮길 조각 목록(uid·종류·글·크기)
    const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() },
      body: JSON.stringify({ model: useModel, board: DOC_NAME, ...(kind ? { kind } : {}), ...(prevHtml ? { prev_html: prevHtml } : {}), ...(items ? { items } : {}), ...(history.at(-1)?.infographic ? { infographic: true } : {}), messages: history.map(({ role, content, context }) => ({ role, content, ...(context ? { context } : {}) })) }) })
    const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
    if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
    const frames = d.kind === 'tidy' && d.plan ? ed.current?.applyTidy(d.plan, d.model) || [] : null   // 답이 도착한 이때 한 번만 칠판에(기록을 다시 열 땐 안 함)
    if (frames?.length) setSkipSel(frames.join())   // 정돈한 프레임도 고른 채로 남음 — 붙이기처럼 다음 질문엔 안 실음
    return { role: 'assistant', content: d.content, model: d.model, at: Date.now(), elapsed: d.elapsed, kind: d.kind || 'chat', ...(d.sources?.length ? { sources: d.sources } : {}), ...(d.refs?.length ? { refs: d.refs } : {}),
      ...(d.images?.length ? { images: d.images, prompt: history.filter(m => m.role === 'user').at(-1)?.content || '' } : {}), ...(d.credits != null ? { credits: d.credits } : {}),
      ...(d.html ? { html: d.html, title: d.title || '정리 문서' } : {}), ...(frames ? { frames } : {}) }
  }
  async function send(text = null, kind = '', from = null) {   // text·kind = 밖에서 시킨 질문(칠판 우클릭 「정리 문서 만들기」 — 입구는 대화창 하나), from = 「그림으로도」(정리 문서와 같은 자료)
    const q = (text ?? draft).trim(); if (!q || busy) return
    const ctx = from ? from.context || '' : contextText(sel), n = from ? from.ctxCount : sel.length
    const mine = { role: 'user', content: q, at: Date.now(), ...(ctx ? { context: ctx, ctxCount: n } : {}), ...(from ? { infographic: true } : {}) }
    const next = [...msgs.filter(m => m.role !== 'error'), mine]
    update(next); if (text == null) setDraft(''); setBusy(Date.now()); setBusyJob(kind || (TIDY_RE.test(q) ? 'tidy' : ''))
    const prev = msgs.filter(m => m.role !== 'error').at(-1)
    try { update([...next, await ask(next, kind, !kind && prev?.role === 'assistant' && prev.html ? prev.html : '')]) } catch (e) {
      setMsgs([...next, { role: 'error', content: String(e.message || e) }])   // 오류는 기록에 안 남김
    } finally { setBusy(null) }
  }
  function pin(i) {
    const m = msgs[i]
    if (ed.current?.showCard(m.at)) return   // 이미 붙인 카드 → 그리로
    const ids = ed.current?.pinCard(m); if (ids) { setSkipSel(ids.join()); update(msgs.map((x, j) => (j === i ? { ...x, pinned: true } : x))) }
  }
  // 버튼을 6px 넘게 끌면 카드가 손에 붙어 칠판으로(팔레트 버튼과 같은 방식) — 놓은 자리에 붙음
  const dragged = useRef(false)
  function dragDown(e, i) {
    if (e.button !== 0) return
    dragged.current = false   // 끌어 놓고 나면 버튼 위가 아니라 click이 안 올 수 있어 매번 처음부터
    const sx = e.clientX, sy = e.clientY, m = msgs[i]
    const move = ev => { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) <= 6) return; done(); dragged.current = true
      ed.current?.dragCard(m, ids => setSkipSel((ids || []).join()) || setMsgs(cur => { const next = cur.map((x, j) => (j === i ? { ...x, pinned: true } : x)); save(next); return next })) }
    const done = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', done) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', done)
  }
  // 새 대화 — 지금 대화를 지난 대화 맨 위로(빈 대화면 그냥 둠). 질문 하나 = 제목
  const shelve = (cur, p) => { const kept = cur.filter(m => m.role !== 'error'); if (!kept.some(m => m.role === 'user')) return p
    return [{ at: kept[0].at || Date.now(), title: (kept.find(m => m.role === 'user').content || '').split(/\r?\n/)[0].slice(0, 40), messages: kept }, ...p] }
  const reset = () => { setSkipSel(''); setGone({}); setPastOpen(false) }
  function newChat() { if (busy) return; const p = shelve(msgs, pastRef.current); setPast(p); reset(); setMsgs([]); save([], p) }
  function openPast(j) { if (busy) return; const pick = pastRef.current[j], p = shelve(msgs, pastRef.current.filter((_, k) => k !== j)); setPast(p); reset(); setMsgs(pick.messages); save(pick.messages, p) }
  function saveKey(v) { setKairosKey(v.trim()); setMyKey(!!v.trim()); setKeyDraft(''); setKeyOpen(false) }
  // 정리 문서 → 같은 자료로 인포그래픽 그림 후보(2026-10-20 사용자 선택 — 그림은 보기 좋지만 숫자를 지어낼 수 있어 기본은 문서, 원하면 한 번 더)
  function drawReport(i) { const src = msgs.slice(0, i).filter(m => m.role === 'user').at(-1) || {}; send(`「${msgs[i].title || '정리 문서'}」 인포그래픽 그림`, 'image', { context: src.context, ctxCount: src.ctxCount }) }
  function retry() {
    const last = [...msgs].reverse().find(m => m.role === 'user'); if (!last) return
    setMsgs(msgs.filter(m => m.role !== 'error').slice(0, -1)); setDraft(last.content)
  }

  const busyLine = !busy ? '' : `${JOB_LABEL[busyJob] || (busyJob === 'chat' ? `${useModel} 생각 중` : 'KAIROS 생각 중')}${JOB_LABEL[busyJob] && (models?.jobs?.[busyJob] || (busyJob === 'board' ? useModel : '')) ? ` · ${models?.jobs?.[busyJob] || useModel}` : ''}… ${Math.round((Date.now() - busy) / 1000)}초`
  // 일을 아직 모를 때(서버가 짐작 — 「정리 문서로 만들어 줘」를 쳐서 물음)는 모델 이름을 안 씀: 고른 모델이 아닐 수 있음(2026-10-20 실화면)
  useEffect(() => { onBusy?.(busy && BOARD_JOBS.has(busyJob) ? busyLine : '') }, [busyLine])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => onBusy?.(''), [])   // eslint-disable-line react-hooks/exhaustive-deps
  const feat = models?.featured || {}
  return (
    <aside style={floating ? { ...css.panel, ...css.float } : css.panel} aria-label="KAIROS 대화" onPointerDown={e => e.stopPropagation()}>
      <div style={css.head}>
        <b style={{ fontSize: 14 }}>KAIROS</b>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <select style={css.select} value={useModel} title="답할 모델(100만 토큰당 입력 / 출력 달러)" onChange={e => { setModel(e.target.value); try { localStorage.setItem(MODEL_KEY, e.target.value) } catch { /* 기억 못 해도 그만 */ } }}>
            {!Object.values(feat).some(rows => rows.some(m => m.id === useModel)) && <option value={useModel}>기본 · {useModel}</option>}
            {Object.entries(feat).filter(([, rows]) => rows.length).map(([v, rows]) => (
              <optgroup key={v} label={VENDOR[v] || v}>
                {rows.map(m => <option key={m.id} value={m.id}>{m.id === models.default ? '기본 · ' : ''}{m.id}{m.price ? `  ${m.price}` : ''}</option>)}
              </optgroup>))}
          </select>
          <button title="대화창 닫기" onClick={onClose} style={{ ...css.ghost, padding: '0 7px' }}>✕</button>
        </div>
      </div>
      <div style={css.bar}>   {/* 대화 관리 줄 — 새 대화 · 지난 대화 · 내 키 */}
        <button style={css.ghost} disabled={!!busy || !msgs.some(m => m.role === 'user')} onClick={newChat} title="지금 대화는 「지난 대화」로 넘기고 빈 대화로 — 앞 대화가 다음 질문에 안 실려요">＋ 새 대화</button>
        {past.length > 0 && <button style={css.ghost} disabled={!!busy} aria-expanded={pastOpen} onClick={() => setPastOpen(o => !o)} title="지난 대화를 골라 다시 열어요(지금 대화는 목록으로)">지난 대화 {past.length} ▾</button>}
        <button style={{ ...css.ghost, marginLeft: 'auto', ...(myKey ? { color: '#0f766e', borderColor: '#0f766e' } : null) }} aria-expanded={keyOpen} onClick={() => setKeyOpen(o => !o)}
          title={myKey ? '내 KAIROS 키로 부르는 중 — 바꾸거나 지우기' : '내 KAIROS 키 넣기(안 넣으면 서버 PC 키)'}>🔑 {myKey ? '내 키' : '서버 키'}</button>
      </div>
      {pastOpen && <div data-testid="past-list" style={css.drop}>
        {past.map((c, j) => <button key={c.at + ':' + j} style={css.row} onClick={() => openPast(j)} title={c.title}>
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title || '(제목 없음)'}</span>
          <span style={css.meta}>{new Date(c.at).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })} · {c.messages.filter(m => m.role === 'user').length}문</span></button>)}
      </div>}
      {keyOpen && <div data-testid="key-box" style={{ ...css.drop, padding: 10, gap: 6 }}>
        <span style={css.meta}>내 KAIROS API 키 — 이 브라우저에만 저장되고, 물을 때만 서버로 같이 가요(서버는 남기지 않아요). 비우면 서버 PC 키를 써요.</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <input type="password" autoComplete="off" placeholder={myKey ? '새 키로 바꾸기' : '키 붙여넣기'} value={keyDraft} onChange={e => setKeyDraft(e.target.value)}
            onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter' && KEY_RE.test(keyDraft.trim())) saveKey(keyDraft) }} style={{ ...css.input, minHeight: 0, padding: '4px 8px', flex: 1 }} />
          <button style={css.pin} disabled={!KEY_RE.test(keyDraft.trim())} onClick={() => saveKey(keyDraft)}>저장</button>
          {myKey && <button style={css.ghost} onClick={() => saveKey('')}>지우기</button>}
        </div>
      </div>}
      <div ref={box} style={css.msgs}>
        {loaded && !msgs.length && <div style={{ ...css.meta, fontSize: 12.5, lineHeight: 1.6 }}>
          무엇이든 물어보세요. 남길 답은 「칠판에 붙이기」나 끌어다 놓기로 메모가 됩니다.<br />칠판에서 메모나 글을 고른 채 물으면 그 내용을 같이 보냅니다.</div>}
        {msgs.map((m, i) => m.role === 'user'
          ? <div key={i} style={css.me}>{m.ctxCount ? <span style={css.ctx}>칠판에서 고른 것 {m.ctxCount}개와 함께</span> : null}{m.content}</div>
          : m.role === 'error'
            ? <div key={i} style={css.err}>{m.content}<div style={{ marginTop: 6 }}><button style={css.ghost} onClick={retry}>질문 다시 고치기</button></div></div>
            : <div key={i} style={css.ai}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                <span data-testid="answer-kind" style={{ ...css.kind, ...(KINDS[m.kind] ? KINDS[m.kind][1] : null) }}>{(KINDS[m.kind] || KINDS.chat)[0]}</span>
              </div>
              <Answer text={m.content} />
              {m.html && <div data-testid="answer-doc" style={{ marginTop: 6 }}>   {/* 정리 문서 미리보기 — A4 폭 794px를 대화창 폭에 맞춰 줄임(스크립트 없는 iframe) */}
                <div style={{ height: 300, overflow: 'hidden', border: `1px solid ${C.line}`, borderRadius: 8, background: '#fff', cursor: 'zoom-in' }} title="크게 보기·인쇄" onClick={() => openHtml(m.html)}>
                  <iframe srcDoc={m.html} title={m.title || '정리 문서'} sandbox="" scrolling="no" style={{ border: 0, width: 794, height: 300 / 0.41, transform: 'scale(0.41)', transformOrigin: '0 0', pointerEvents: 'none' }} />
                </div>
                <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}><button style={css.ghost} onClick={() => openHtml(m.html)}>크게 보기 · 인쇄</button>
                  <button style={css.ghost} disabled={!!busy} onClick={() => drawReport(i)} title="같은 자료로 인포그래픽 그림 후보 2장 — 보기 좋지만 숫자·날짜를 지어낼 수 있으니 확인하고 쓰세요(약 20크레딧)">🎨 그림으로도</button>
                  <span style={{ ...css.meta, alignSelf: 'center' }}>고칠 점을 이어서 말하면 이 문서를 고쳐 써요</span></div>
              </div>}
              {m.images?.length > 0 && <div data-testid="answer-images" style={{ marginTop: 6, display: 'grid', gridTemplateColumns: `repeat(${Math.min(2, m.images.length)}, 1fr)`, gap: 6 }}>
                {m.images.map((g, j) => <button key={g.url} data-testid="image-pick" title="누르면 칠판에 붙여요(끌어 놓으면 그 자리) — 밑에 요청 글이 같이 붙어요"
                  onClick={async () => { const id = await ed.current?.pinImage(g.url, m.prompt || ''); if (id) update(msgs.map((x, k) => (k === i ? { ...x, picked: [...new Set([...(x.picked || []), j])] } : x))) }}
                  onDragStart={e => { e.dataTransfer.setData('text/uri-list', location.origin + g.url); e.dataTransfer.setData('text/x-mb-caption', m.prompt || '') }} draggable
                  style={{ all: 'unset', cursor: 'pointer', position: 'relative', borderRadius: 8, overflow: 'hidden', border: `2px solid ${m.picked?.includes(j) ? '#da7756' : C.line}` }}>
                  <img src={g.url} alt={`후보 ${j + 1}`} draggable={false} style={{ display: 'block', width: '100%', aspectRatio: '4 / 3', objectFit: 'cover', background: '#fff' }} />
                  {m.picked?.includes(j) && <span style={{ position: 'absolute', right: 4, bottom: 4, ...css.kind, color: '#fff', background: '#da7756' }}>칠판에 붙임 ✓</span>}
                </button>)}</div>}
              {m.refs?.length > 0 && <div data-testid="answer-refs" style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {m.refs.map(r => <button key={r.n} onClick={() => ed.current?.showItem(r.uid) || setGone(g => ({ ...g, [m.at + ':' + r.n]: true }))} title="칠판의 그 도형으로 가기"
                  style={{ all: 'unset', cursor: 'pointer', ...css.meta, color: '#d97706', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  📌 [칠판 {r.n}] {r.kind ? `${r.kind} · ` : ''}{(r.text || '').split('\n')[0]}{gone[m.at + ':' + r.n] ? ' — 지워졌어요' : ''}</button>)}</div>}
              {m.sources?.length > 0 && <div data-testid="answer-sources" style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {m.sources.map(s => <a key={s.n} href={s.url} target="_blank" rel="noopener noreferrer" title={s.url} onPointerDown={e => e.stopPropagation()}
                  style={{ ...css.meta, color: LINK_CHAT, textDecoration: 'none', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>[{s.n}] {s.title || siteOf(s.url)} · {siteOf(s.url)}</a>)}</div>}
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
                {m.kind === 'tidy' && <button style={css.pin} onClick={() => ed.current?.showIds(m.frames) || setGone(g => ({ ...g, [m.at + ':tidy']: true }))} title="정돈해 만든 프레임들이 한눈에 보이게">
                  {gone[m.at + ':tidy'] ? '프레임이 지워졌어요' : '정돈한 곳 보기'}</button>}
                {!m.images?.length && m.kind !== 'tidy' && <button style={{ ...(m.pinned ? css.ghost : css.pin), cursor: 'grab' }} onPointerDown={e => dragDown(e, i)} onClick={() => { if (dragged.current) { dragged.current = false; return } pin(i) }}
                  title={m.pinned ? '누르면 붙인 카드로 가기(지웠으면 다시 붙임) · 칠판으로 끌면 그 자리에 하나 더' : m.refs?.length ? '메모 + 근거가 된 칠판 도형으로 가는 점선 화살표(누르면 빈자리, 끌면 놓은 자리)' : m.sources?.length ? '요약 메모 + 출처 카드를 번호 화살표로 이어 한 묶음으로(누르면 빈자리, 끌면 놓은 자리)' : '누르면 빈자리에, 칠판으로 끌면 놓은 자리에 카드로'}>
                  {m.pinned ? '칠판에 붙임 ✓' : '칠판에 붙이기'}</button>}
                {!m.images?.length && !m.html && m.kind !== 'tidy' && <button style={css.ghost} onClick={() => navigator.clipboard?.writeText(m.content).catch(() => {})}>복사</button>}
                <span style={{ ...css.meta, marginLeft: 'auto' }}>{m.model}{m.elapsed != null ? ` · ${m.elapsed}초` : ''}{m.credits != null ? ` · ${Math.round(m.credits)}크레딧` : ''}</span>
              </div>
            </div>)}
        {busy && <div data-testid="chat-busy" style={{ ...css.ai, color: C.muted, display: 'flex', alignItems: 'center', gap: 8 }}><Spinner />{busyLine}</div>}
      </div>
      <div style={css.foot}>
        {sel.length > 0 && <span style={css.chip}>칠판에서 고른 것 {sel.length}개를 같이 보냄</span>}
        <textarea style={css.input} rows={Math.min(8, Math.max(2, draft.split('\n').length))} value={draft} placeholder="물어보세요 (Enter 보내기 · Shift+Enter 줄바꿈)"
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }} />
        <span style={css.meta}>{server ? `대화 기록은 이 칠판(「${DOC_NAME}」)에 함께 저장돼요.` : '서버가 꺼져 있어요 — python web/server.py 를 켜야 물을 수 있어요.'}</span>
      </div>
    </aside>
  )
}
