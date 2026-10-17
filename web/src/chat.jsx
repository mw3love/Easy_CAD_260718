// KAIROS 대화창(§8 항목61 ⓒ, 2026-10-17) — 칠판 오른쪽 고정 칸. 화면 원칙: 기본 2분할(작업공간 + AI 대화창).
// - 묻기: 서버 POST /api/chat(키는 서버 PC에만). 앞 대화를 이어 보낸다.
// - 칠판에서 고른 것의 글을 질문에 같이 보낸다(칩으로 보임).
// - 「칠판에 붙이기」: 답 → 카드(상자 도형, 글 길이만큼 늘어남)를 지금 화면의 빈자리에. 붙인 카드는 「칠판에 붙임 ✓」로 찾아감.
// - 대화 기록: 칠판마다 서버(/api/chatlog/<이름>)에 — 다시 열어도 그대로.
import { useEffect, useRef, useState } from 'react'
import { createShapeId, useValue } from 'tldraw'
import { BOARD } from './boardStore.js'
import { answerToRichText, contextText, freeSpot, parseAnswer, sourceLine } from './chatFormat.js'

export const CHAT_W = 360
const LOG_URL = `/api/chatlog/${encodeURIComponent(BOARD)}`
const CARD_W = 340
const MODEL_KEY = 'magic-board-model'   // 고른 모델은 이 브라우저에만 기억(편의)
const VENDOR = { gpt: 'GPT', gemini: 'Gemini', claude: 'Claude' }

const F = "'Pretendard', sans-serif"
const css = {
  panel: { position: 'fixed', top: 0, right: 0, bottom: 0, width: CHAT_W, display: 'flex', flexDirection: 'column', background: '#f7f6f3',
    borderLeft: '1px solid #e4e4e7', font: `400 13.5px/1.55 ${F}`, color: '#1f2125', zIndex: 1000 },
  head: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '10px 12px', borderBottom: '1px solid #e4e4e7' },
  msgs: { flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 10 },
  me: { alignSelf: 'flex-end', maxWidth: '92%', background: '#ece9e3', borderRadius: 10, padding: '7px 10px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
  ai: { alignSelf: 'stretch', background: '#fff', border: '1px solid #e4e4e7', borderRadius: 10, padding: '8px 10px', wordBreak: 'break-word' },
  err: { alignSelf: 'stretch', background: '#fff7ed', border: '1px solid #fdba74', color: '#9a3412', borderRadius: 10, padding: '8px 10px' },
  meta: { font: `400 11px ${F}`, color: '#8a8f98' },
  ctx: { display: 'block', font: `500 11px ${F}`, color: '#3b6fd8', marginBottom: 2 },
  pin: { font: `700 12px ${F}`, color: '#c2410c', background: '#fff', border: '1px solid #da7756', borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  pinned: { font: `600 12px ${F}`, color: '#71717a', background: '#fff', border: '1px solid #e4e4e7', borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  ghost: { font: `500 12px ${F}`, color: '#71717a', background: 'transparent', border: '1px solid #e4e4e7', borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  foot: { borderTop: '1px solid #e4e4e7', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6 },
  chip: { alignSelf: 'flex-start', font: `500 11.5px ${F}`, color: '#3b6fd8', background: '#e3ebfb', borderRadius: 99, padding: '2px 9px' },
  input: { font: `400 13.5px/1.5 ${F}`, border: '1px solid #d4d4d8', borderRadius: 8, padding: '8px 10px', resize: 'none', minHeight: 40, maxHeight: 200, outline: 'none' },
  select: { font: `500 12px ${F}`, color: '#52525b', border: '1px solid #d4d4d8', borderRadius: 6, padding: '2px 4px', background: '#fff', maxWidth: 210 },
}

// 답 글 보이기(굵게·목록·제목만 — 카드에 붙는 모양과 같은 규칙)
function Answer({ text }) {
  return <div>{parseAnswer(text).map((ln, i) => {
    if (ln.kind === 'gap') return <div key={i} style={{ height: 6 }} />
    const parts = ln.parts.map((p, j) => (p.bold || ln.kind === 'h' ? <b key={j}>{p.text}</b> : <span key={j}>{p.text}</span>))
    if (ln.kind === 'code') return <div key={i} style={{ fontFamily: 'ui-monospace,monospace', fontSize: 12, whiteSpace: 'pre-wrap', background: '#f4f4f5' }}>{parts}</div>
    if (ln.kind === 'li') return <div key={i} style={{ paddingLeft: 14, textIndent: -12 }}>{ln.mark} {parts}</div>
    return <div key={i} style={ln.kind === 'h' ? { fontWeight: 700, marginTop: 2 } : null}>{parts}</div>
  })}</div>
}

// 칠판에서 고른 것(안에 든 것 포함)의 글
function selectedTexts(editor) {
  const out = []
  for (const id of editor.getSelectedShapeIds())
    for (const sid of editor.getShapeAndDescendantIds([id])) {
      const s = editor.getShape(sid), t = s && editor.getShapeUtil(s).getText?.(s)
      if (t && t.trim()) out.push(t)
    }
  return out
}

// 답 → 카드. 지금 화면에서 다른 것과 안 겹치는 자리에 놓고 고른다.
export function pinAnswer(editor, msg) {
  const view = editor.getViewportPageBounds()
  const boxes = editor.getCurrentPageShapes().filter(s => !s.parentId?.startsWith('shape:')).map(s => editor.getShapePageBounds(s)).filter(Boolean)
  const estH = Math.min(600, 40 + parseAnswer(msg.content).length * 22)
  // 위 메뉴 줄(56px)·오른쪽 스타일 창(카드를 고르면 뜸, 170px)에 가리지 않게 그 자리는 뺀다(화면 px → 칠판 단위)
  const z = editor.getZoomLevel(), top = 56 / z, right = 170 / z
  const at = freeSpot({ x: view.x, y: view.y + top, w: Math.max(CARD_W, view.w - right), h: view.h - top }, boxes, CARD_W, estH)
  const id = createShapeId()
  editor.createShape({ id, type: 'geo', x: at.x, y: at.y,
    props: { geo: 'rectangle', w: CARD_W, h: 40, fill: 'solid', dash: 'solid', font: 'sans', align: 'start', verticalAlign: 'start',
      richText: answerToRichText(msg.content, sourceLine(msg.model, msg.at)) },
    meta: { ecad: { stroke: '#d4d4d8', fill: '#ffffff', sw: 1, label: { color: '#1f1f1f', px: 14, family: true, pad: 12 } },
      chat: { board: BOARD, at: msg.at, model: msg.model } } })
  editor.select(id)
  return id
}

export function ChatPanel({ editor }) {
  const [msgs, setMsgs] = useState([])
  const [loaded, setLoaded] = useState(false)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(null)        // 보낸 시각(생각 중일 때)
  const [, tick] = useState(0)
  const [models, setModels] = useState(null)
  const [model, setModel] = useState(() => { try { return localStorage.getItem(MODEL_KEY) || '' } catch { return '' } })
  const [server, setServer] = useState(true)
  const box = useRef(null)
  const sel = useValue('chat-sel', () => (editor ? selectedTexts(editor) : []), [editor])

  // 대화 기록·모델 목록 받기
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

  async function send() {
    const q = draft.trim(); if (!q || busy) return
    const ctx = contextText(sel)
    const mine = { role: 'user', content: q, at: Date.now(), ...(ctx ? { context: ctx, ctxCount: sel.length } : {}) }
    const next = [...msgs.filter(m => m.role !== 'error'), mine]
    update(next); setDraft(''); setBusy(Date.now())
    try {
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: useModel, messages: next.map(({ role, content, context }) => ({ role, content, ...(context ? { context } : {}) })) }) })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      update([...next, { role: 'assistant', content: d.content, model: d.model, at: Date.now(), elapsed: d.elapsed }])
    } catch (e) {
      setMsgs([...next, { role: 'error', content: String(e.message || e) }])   // 오류는 기록에 안 남김
    } finally { setBusy(null) }
  }

  function pin(i) {
    const m = msgs[i]
    if (m.cardId && editor.getShape(m.cardId)) { editor.select(m.cardId); editor.zoomToSelection({ animation: { duration: 200 } }); return }
    const id = pinAnswer(editor, m)
    update(msgs.map((x, j) => (j === i ? { ...x, cardId: id } : x)))
  }
  function retry() {
    const last = [...msgs].reverse().find(m => m.role === 'user')
    if (!last) return
    setMsgs(msgs.filter(m => m.role !== 'error').slice(0, -1)); setDraft(last.content)
  }

  const feat = models?.featured || {}
  return (
    <aside style={css.panel} aria-label="KAIROS 대화">
      <div style={css.head}>
        <b style={{ fontSize: 14 }}>KAIROS</b>
        <select style={css.select} value={useModel} title="답할 모델(100만 토큰당 입력 / 출력 달러)" onChange={e => {
          setModel(e.target.value); try { localStorage.setItem(MODEL_KEY, e.target.value) } catch {} }}>
          {!Object.values(feat).some(rows => rows.some(m => m.id === useModel)) && <option value={useModel}>기본 · {useModel}</option>}
          {Object.entries(feat).filter(([, rows]) => rows.length).map(([v, rows]) => (
            <optgroup key={v} label={VENDOR[v] || v}>
              {rows.map(m => <option key={m.id} value={m.id}>{m.id === models.default ? '기본 · ' : ''}{m.id}{m.price ? `  ${m.price}` : ''}</option>)}
            </optgroup>))}
        </select>
      </div>
      <div ref={box} style={css.msgs}>
        {loaded && !msgs.length && <div style={{ ...css.meta, fontSize: 12.5, lineHeight: 1.6 }}>
          무엇이든 물어보세요. 남길 답은 「칠판에 붙이기」로 카드가 됩니다.<br />칠판에서 카드나 글을 고른 채 물으면 그 내용을 같이 보냅니다.</div>}
        {msgs.map((m, i) => m.role === 'user'
          ? <div key={i} style={css.me}>{m.ctxCount ? <span style={css.ctx}>칠판에서 고른 것 {m.ctxCount}개와 함께</span> : null}{m.content}</div>
          : m.role === 'error'
            ? <div key={i} style={css.err}>{m.content}<div style={{ marginTop: 6 }}><button style={css.ghost} onClick={retry}>질문 다시 고치기</button></div></div>
            : <div key={i} style={css.ai}>
              <Answer text={m.content} />
              <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
                <button style={m.cardId ? css.pinned : css.pin} onClick={() => pin(i)} title={m.cardId ? '붙인 카드로 가기' : '이 답을 칠판에 카드로'}>
                  {m.cardId ? '칠판에 붙임 ✓' : '칠판에 붙이기'}</button>
                <button style={css.ghost} onClick={() => navigator.clipboard?.writeText(m.content).catch(() => {})}>복사</button>
                <span style={{ ...css.meta, marginLeft: 'auto' }}>{m.model}{m.elapsed != null ? ` · ${m.elapsed}초` : ''}</span>
              </div>
            </div>)}
        {busy && <div style={{ ...css.ai, color: '#71717a' }}>{useModel} 생각 중… {Math.round((Date.now() - busy) / 1000)}초</div>}
      </div>
      <div style={css.foot}>
        {sel.length > 0 && <span style={css.chip}>칠판에서 고른 것 {sel.length}개를 같이 보냄</span>}
        <textarea style={css.input} rows={Math.min(8, Math.max(2, draft.split('\n').length))} value={draft} placeholder="물어보세요 (Enter 보내기 · Shift+Enter 줄바꿈)"
          onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }} />
        <span style={css.meta}>{server ? `대화 기록은 이 칠판(「${BOARD}」)에 함께 저장돼요.` : '서버가 꺼져 있어요 — python web/server.py 를 켜야 물을 수 있어요.'}</span>
      </div>
    </aside>
  )
}
