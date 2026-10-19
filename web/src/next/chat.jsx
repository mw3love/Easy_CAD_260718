// KAIROS 대화창(직접 만드는 칠판판) — 옛 tldraw 칠판 `src/chat.jsx`를 옮김(§8 항목61 ⓒ 4단계). 칠판 오른쪽 칸, 위 막대 「KAIROS」로 열고 닫음.
// - 묻기: 서버 POST /api/chat(키는 서버 PC에만), 앞 대화를 이어 보냄. 칠판에서 고른 것의 글을 같이 보냄(칩).
// - 「칠판에 붙이기」: 답 → 카드(흰 보드 + 보드 글꼴 글, Editor.pinCard). 붙인 카드는 「칠판에 붙임 ✓」로 찾아감(카드의 .ecad `chat_at` = 답 시각).
// - 대화 기록: 칠판마다 서버(/api/chatlog/<이름>) — 옛 칠판과 같은 기록을 이어 씀.
// - 웹 검색(§8 항목61 ② 담는 법, 2026-10-19): 종류는 서버가 짐작(「최신·뉴스·찾아줘」…), 답 위 표시 「🔎 웹 검색 / 💬 대화」 + 반대로 다시 묻기 한 번.
//   검색 답은 쓰인 번호의 출처를 아래에 보이고, 붙이면 요약 메모 + 출처 카드 + 번호 화살표 한 묶음(Editor `cardItems`).
// - 칠판에서(§8 항목61 ③-2): 「지난번·저번·정리해 둔」 → 서버가 이 칠판 글을 뜻으로 찾아 근거로 답, [칠판 n] 고리 = 그 도형으로 가기, 붙이면 근거로 가는 점선 화살표.
import { useEffect, useRef, useState } from 'react'
import { DOC_NAME } from './doc.js'
import { contextText, parseAnswer } from '../chatFormat.js'
import { urlSpans } from './geom.js'
import { MONO_FONT } from './render.jsx'
import { siteOf } from './webcard.js'
const LINK_CHAT = '#4f8fe8'
// 답 종류 — [표시, 표시 꾸밈, 다시 묻기 글, 툴팁] — 서버가 짐작한 것을 답 위에 보이고, 나머지 둘로 한 번에 다시(§8 항목61 ② 원칙 ⓒ)
const KINDS = {
  chat: ['💬 대화', null, '대화로 다시', '웹·칠판을 찾지 않고 대화로 다시 물어 이 답을 바꿔요'],
  search: ['🔎 웹 검색', { color: '#2f80ed', background: 'rgba(47,128,237,.12)' }, '웹 검색으로 다시', '웹을 찾아 출처와 함께 다시 물어 이 답을 바꿔요'],
  board: ['📌 칠판에서', { color: '#d97706', background: 'rgba(245,158,11,.14)' }, '칠판에서 다시', '이 칠판의 메모·글을 뜻으로 찾아 그것을 근거로 다시 물어요'],
  image: ['🎨 그림', { color: '#9333ea', background: 'rgba(147,51,234,.12)' }, '그림으로 다시', '그림 후보 2장을 만들어 이 답을 바꿔요(장당 약 34크레딧)'],
}   // 대화창 주소(어두운·밝은 화면 둘 다 읽히는 파랑)

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
  link: { all: 'unset', cursor: 'pointer', font: `500 11px ${F}`, color: C.muted, textDecoration: 'underline' },
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
export function ChatPanel({ ed, selKey, floating, onClose }) {   // floating = 좁은 창 — 칠판 위에 뜬 카드(2026-10-19)
  const [msgs, setMsgs] = useState([]), [loaded, setLoaded] = useState(false), [draft, setDraft] = useState(''), [busy, setBusy] = useState(null)
  const [, tick] = useState(0), [models, setModels] = useState(null), [server, setServer] = useState(true), [gone, setGone] = useState({})
  const [model, setModel] = useState(() => { try { return localStorage.getItem(MODEL_KEY) || '' } catch { return '' } })
  const box = useRef(null)
  const sel = ed.current?.selTexts() || []   // eslint-disable-line react-hooks/exhaustive-deps
  void selKey

  useEffect(() => {
    fetch(LOG_URL, { cache: 'no-store' }).then(r => (r.status === 404 ? { messages: [] } : r.ok ? r.json() : Promise.reject(r)))
      .then(d => { setMsgs(d.messages || []); setLoaded(true) }).catch(() => { setServer(false); setLoaded(true) })
    fetch('/api/models').then(r => r.json()).then(setModels).catch(() => setModels({ featured: {}, error: '모델 목록 못 받음' }))
  }, [])
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight }, [msgs.length, busy])
  useEffect(() => { if (!busy) return; const t = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(t) }, [busy])

  const useModel = model || models?.default || 'gpt-6.1-sol'
  const save = next => fetch(LOG_URL, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ messages: next }) })
    .then(r => setServer(r.ok)).catch(() => setServer(false))
  const update = next => { setMsgs(next); save(next) }

  // 묻기 — history = 지금까지(마지막이 질문), kind = 'search'·'chat'(비면 서버가 짐작) → 답 한 차례
  async function ask(history, kind = '') {
    const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: useModel, board: DOC_NAME, ...(kind ? { kind } : {}), messages: history.map(({ role, content, context }) => ({ role, content, ...(context ? { context } : {}) })) }) })
    const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
    if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
    return { role: 'assistant', content: d.content, model: d.model, at: Date.now(), elapsed: d.elapsed, kind: d.kind || 'chat', ...(d.sources?.length ? { sources: d.sources } : {}), ...(d.refs?.length ? { refs: d.refs } : {}),
      ...(d.images?.length ? { images: d.images, prompt: history.filter(m => m.role === 'user').at(-1)?.content || '' } : {}), ...(d.credits != null ? { credits: d.credits } : {}) }
  }
  async function send() {
    const q = draft.trim(); if (!q || busy) return
    const ctx = contextText(sel)
    const mine = { role: 'user', content: q, at: Date.now(), ...(ctx ? { context: ctx, ctxCount: sel.length } : {}) }
    const next = [...msgs.filter(m => m.role !== 'error'), mine]
    update(next); setDraft(''); setBusy(Date.now())
    try { update([...next, await ask(next)]) } catch (e) {
      setMsgs([...next, { role: 'error', content: String(e.message || e) }])   // 오류는 기록에 안 남김
    } finally { setBusy(null) }
  }
  // 앱이 짐작한 종류가 틀렸을 때 — 같은 질문을 반대 종류로 다시 물어 그 답을 바꿔 끼움(질문은 그대로, 붙인 표시는 새 답이라 풀림)
  async function redoAs(i, kind) {
    if (busy) return
    const history = msgs.slice(0, i).filter(m => m.role !== 'error'); setBusy(Date.now())
    try { const a = await ask(history, kind); update(msgs.map((x, j) => (j === i ? a : x))) } catch (e) {
      setMsgs([...msgs.filter(m => m.role !== 'error'), { role: 'error', content: String(e.message || e) }])
    } finally { setBusy(null) }
  }
  function pin(i) {
    const m = msgs[i]
    if (ed.current?.showCard(m.at)) return   // 이미 붙인 카드 → 그리로
    if (ed.current?.pinCard(m)) update(msgs.map((x, j) => (j === i ? { ...x, pinned: true } : x)))
  }
  // 버튼을 6px 넘게 끌면 카드가 손에 붙어 칠판으로(팔레트 버튼과 같은 방식) — 놓은 자리에 붙음
  const dragged = useRef(false)
  function dragDown(e, i) {
    if (e.button !== 0) return
    dragged.current = false   // 끌어 놓고 나면 버튼 위가 아니라 click이 안 올 수 있어 매번 처음부터
    const sx = e.clientX, sy = e.clientY, m = msgs[i]
    const move = ev => { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) <= 6) return; done(); dragged.current = true
      ed.current?.dragCard(m, () => setMsgs(cur => { const next = cur.map((x, j) => (j === i ? { ...x, pinned: true } : x)); save(next); return next })) }
    const done = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', done) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', done)
  }
  function retry() {
    const last = [...msgs].reverse().find(m => m.role === 'user'); if (!last) return
    setMsgs(msgs.filter(m => m.role !== 'error').slice(0, -1)); setDraft(last.content)
  }

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
                {Object.entries(KINDS).filter(([k]) => k !== (m.kind || 'chat')).map(([k, [, , again, tip]]) =>
                  <button key={k} style={css.link} disabled={!!busy} onClick={() => redoAs(i, k)} title={tip}>{again}</button>)}
              </div>
              <Answer text={m.content} />
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
                {!m.images?.length && <button style={{ ...(m.pinned ? css.ghost : css.pin), cursor: 'grab' }} onPointerDown={e => dragDown(e, i)} onClick={() => { if (dragged.current) { dragged.current = false; return } pin(i) }}
                  title={m.pinned ? '누르면 붙인 카드로 가기(지웠으면 다시 붙임) · 칠판으로 끌면 그 자리에 하나 더' : m.refs?.length ? '메모 + 근거가 된 칠판 도형으로 가는 점선 화살표(누르면 빈자리, 끌면 놓은 자리)' : m.sources?.length ? '요약 메모 + 출처 카드를 번호 화살표로 이어 한 묶음으로(누르면 빈자리, 끌면 놓은 자리)' : '누르면 빈자리에, 칠판으로 끌면 놓은 자리에 카드로'}>
                  {m.pinned ? '칠판에 붙임 ✓' : '칠판에 붙이기'}</button>}
                {!m.images?.length && <button style={css.ghost} onClick={() => navigator.clipboard?.writeText(m.content).catch(() => {})}>복사</button>}
                <span style={{ ...css.meta, marginLeft: 'auto' }}>{m.model}{m.elapsed != null ? ` · ${m.elapsed}초` : ''}{m.credits != null ? ` · ${Math.round(m.credits)}크레딧` : ''}</span>
              </div>
            </div>)}
        {busy && <div style={{ ...css.ai, color: C.muted }}>{useModel} 생각 중… {Math.round((Date.now() - busy) / 1000)}초</div>}
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
