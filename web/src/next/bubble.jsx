// 💬 댓글(2026-11-14 화면 틀 B1 5단계 — 사용자 「댓글 + @KAIROS」: 사람끼리 댓글, `@KAIROS`를 붙인 댓글에만 AI가 답함. Figma·Miro 댓글처럼
// 이름·시각, 「✓ 해결」 = 칠판 💬 표시만 숨김(지우지 않음 — 대화 저장소는 메시지를 지우지 않아 해결·다시 열기도 메시지 `role: 'note'`)).
// 옛 💬 AI 말풍선(2026-10-28 사용자) — 물건마다 작은 KAIROS 대화창. 큰 대화창에 여러 물건 작업이 섞이지 않게, 옛 주석 말풍선이 AI 대화로.
// 말풍선 하나 = 물건 하나(_id): 그 물건의 글(프레임은 안의 것까지)·그림 + 이 말풍선 앞 대화만 보냄(서버 /api/chat `kind: 'bubble'` → `easycad/ai/board_bubble.py`).
// 메모·표·글 상자(3단계)·그림(2단계)을 고쳐 달라면 그 자리에서 고침(Ctrl+Z 한 번) — 답 글은 「무엇을 바꿨는지」만, 「원래대로 ↔ 바꾼 것」(Claude Docs 댓글 + 딥모드 `deepFlip`에서 가져옴).
// 대화는 서버 `<칠판>.threads.json`(물건 _id마다 — main.jsx가 읽고 씀), 여러 말풍선을 같이 열고 따로 기다림. 칠판 그림(PDF·PNG·발표)엔 안 나옴.
import { useEffect, useRef, useState } from 'react'
import { DOC_NAME } from './doc.js'
import { keyHeaders } from './kairosKey.js'
import { Spinner, shrinkImage } from './chat.jsx'
import { Composer } from './composer.jsx'
import { aiError } from '../chatFormat.js'

const F = "'Pretendard', sans-serif"
const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)' }
export const BUBBLE_W = 300
const KIND = { memo: '메모', image: '그림', text: '글', table: '표', pdf: 'PDF', doc: '문서', web: '웹 카드', frame: '프레임', titleblock: '프레임' }
const HINT = { memo: '이 메모를 어떻게 할까요? 예: 할 일만 뽑아 아래에 · 쉬운 말로', table: '이 표를 어떻게 할까요? 예: 합계 줄 더해 줘', text: '이 글을 어떻게 할까요? 예: 더 짧게 · 영어로', label: '이 글을 어떻게 할까요? 예: 더 짧게', image: '묻거나 고쳐 달라고 하세요 — 예: 배경을 밝게', slide: '이 장을 어떻게 할까요? 예: 더 짧게 · 숫자 칸으로', frame: '이 프레임 안의 것에 대해 물어보세요' }
export const bubbleKind = t => KIND[t] || '도형'
const AT_AI = /@(kairos|카이로스)/i   // 이 말이 든 댓글만 AI가 답함
// 해결됐나 = 마지막 해결·다시 열기 표시가 「해결」
export const isResolved = t => (t || []).filter(m => m.role === 'note').at(-1)?.act === 'resolve'
export const commentCount = t => (t || []).filter(m => (m.role === 'user' || m.role === 'assistant') && !m.deleted).length
// AI에게 보낼 대화 — 표시(note)는 빼고, 사람 댓글은 「이름: 글」, 같은 쪽이 이어지면 한 덩이(서버는 사람·AI가 번갈아 오길 기대)
const toAI = msgs => { const out = []
  for (const m of msgs) { if ((m.role !== 'user' && m.role !== 'assistant') || m.deleted) continue
    const c = m.role === 'user' && m.who ? `${m.who}: ${m.content}` : m.content, last = out.at(-1)
    if (last && last.role === m.role) last.content += '\n' + c; else out.push({ role: m.role, content: c }) }
  return out }
const when = at => { const d = new Date(at), n = new Date(), hm = `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  return d.toDateString() === n.toDateString() ? hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}` }

// 화면 자리 — 물건 오른쪽(모자라면 왼쪽), 칠판 영역 안으로
export function bubblePos(box, cam, size, h = 320) {
  const r = (box.x + box.w) * cam.z + cam.x, l = box.x * cam.z + cam.x, t = box.y * cam.z + cam.y
  const x = r + 10 + BUBBLE_W <= size.w ? r + 10 : l - 10 - BUBBLE_W >= 0 ? l - 10 - BUBBLE_W : Math.max(8, size.w - BUBBLE_W - 8)
  return { x, y: Math.max(8, Math.min(t, size.h - h - 8)) }
}

// 서버 그림 주소 → 칠판 그림 칸(PNG base64 — 붙여넣은 그림과 같게) + 비율(높이/폭)
async function pngOf(url) {
  const im = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = url })
  const cv = document.createElement('canvas'); cv.width = im.naturalWidth; cv.height = im.naturalHeight; cv.getContext('2d').drawImage(im, 0, 0)
  return { data: cv.toDataURL('image/png').split(',')[1], aspect: im.naturalHeight / im.naturalWidth }
}

export function Bubble({ id, info, cam, size, thread = [], me = '', onThread, onClose, onEdit, onFields, onImage, onStatus }) {   // me = 내 이름(접속자 이름 — 댓글 쓴 사람)
  const [draft, setDraft] = useState(''), [busy, setBusy] = useState(false), [err, setErr] = useState('')
  const list = useRef(null), ta = useRef(null), swaps = useRef({})   // swaps = 답 번호 → 그림 { before, after }(이 창에만)
  const [editAt, setEditAt] = useState(null), [editText, setEditText] = useState('')   // 내 댓글 고치기(2026-11-14 — 같은 시각 = 같은 메시지라 서버 합치기가 고친 것으로 바꿈)
  useEffect(() => { ta.current?.focus() }, [])
  useEffect(() => { list.current?.scrollTo(0, list.current.scrollHeight) }, [thread.length, busy])
  if (!info) return null
  const pos = bubblePos(info.box, cam, size)
  async function send(said, base = thread, at = Date.now()) {   // base·at = 「다시 보내기」 — 실패한 마지막 질문을 같은 시각으로 다시(서버 합치기는 메시지를 안 지워서 새 시각이면 두 번 쌓임)
    const q = (said ?? draft).trim(); if (!q || busy) return
    const mine = { role: 'user', content: q, at, ...(me ? { who: me } : {}) }
    const next = [...base, ...(isResolved(base) ? [{ role: 'note', act: 'reopen', at: at - 1, ...(me ? { who: me } : {}) }] : []), mine]   // 해결된 댓글에 새로 쓰면 다시 열림
    onThread(next); setDraft(''); setErr('')
    if (!AT_AI.test(q)) return   // 사람끼리 댓글 — AI를 안 부름(크레딧 0)
    setBusy(true)
    try {
      let model = ''; try { model = localStorage.getItem('magic-board-model') || '' } catch { /* 서버 기본 모델 */ }
      const image = info.image ? await shrinkImage(info.image) : '', images = info.images ? await Promise.all(info.images.map(shrinkImage)) : []   // images = 프레임 안 그림(서버 `see`가 1024로 다시 줄임)
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() },
        body: JSON.stringify({ kind: 'bubble', board: DOC_NAME, ...(model ? { model } : {}), item: { type: info.type, text: info.text, ...(info.edit ? { edit: info.edit === 'label' ? 'text' : info.edit } : {}), ...(image ? { image } : {}), ...(images.length ? { images } : {}), ...(info.slide ? { slide: info.slide, deck: info.deck } : {}) }, messages: toAI(next) }) })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      const a = { role: 'assistant', content: d.content || '', at: Date.now(), model: d.model, ...(d.credits ? { credits: d.credits } : {}) }
      if (d.edit && info.edit === 'slide' && info.edited) a.pend = d.edit   // 손으로 고친 장 = 바로 덮지 않고 「이 장에 적용」 단추(2026-10-28)
      else if (d.edit && info.edit) { const r = onEdit(d.edit); if (r?.before) a.fix = { ...r, on: true } }   // 메모·표·글·장 = 그 자리에서(3단계)
      if (d.image_url && info.type === 'image') {   // 2단계 — 고친 그림을 그 자리에(원래 그림은 이 창에만 기억 — 대화 파일이 커지지 않게, 새로 열면 Ctrl+Z로)
        const after = await pngOf(d.image_url), before = onImage(after.data, after.aspect)
        if (before) { swaps.current[next.length] = { before, after }; a.img = { url: d.image_url, on: true } }
      }
      onThread([...next, a])
    } catch (e) { setErr(aiError(e)) } finally { setBusy(false) }
  }
  function apply(i) {   // 손으로 고친 장에 AI가 고친 장을 덮어씀(Ctrl+Z 한 번)
    const m = thread[i], r = m?.pend && onEdit(m.pend); if (!r?.before) return
    onThread(thread.map((x, k) => (k === i ? { ...x, pend: undefined, fix: { ...r, on: true } } : x))); onStatus?.('이 장을 다시 지었어요')
  }
  function flip(i) {   // 원래대로 ↔ 바꾼 것 — 그 답의 고친 메모·그림을 칠판에서 바꿔 끼움(Ctrl+Z 한 칸)
    const m = thread[i]
    if (m?.img) { const s = swaps.current[i]; if (!s) return; const on = !m.img.on, v = on ? s.after : s.before
      if (!onImage(v.data, v.aspect)) return
      onThread(thread.map((x, k) => (k === i ? { ...x, img: { ...x.img, on } } : x))); onStatus?.(on ? '바꾼 그림으로' : '원래 그림으로'); return }
    if (!m?.fix) return
    const on = !m.fix.on; if (!onFields(on ? m.fix.after : m.fix.before)) return
    onThread(thread.map((x, k) => (k === i ? { ...x, fix: { ...x.fix, on } } : x))); onStatus?.(on ? '바꾼 것으로' : '원래대로')
  }
  const btn = { all: 'unset', cursor: 'pointer', font: `400 11.5px ${F}`, color: C.muted, padding: '2px 7px', borderRadius: 6, border: '1px solid var(--mb-ctl)' }
  const resend = () => { const last = thread.at(-1); if (last?.role === 'user') send(last.content, thread.slice(0, -1), last.at) }   // 오류 뒤 「다시 보내기」 = 마지막 질문 그대로
  const resolved = isResolved(thread), note = act => onThread([...thread, { role: 'note', act, at: Date.now(), ...(me ? { who: me } : {}) }])
  const meta = (who, at, extra) => <div style={{ display: 'flex', gap: 6, alignItems: 'baseline', font: `400 11px ${F}`, color: C.muted }}><b style={{ color: C.ink, fontSize: 12 }}>{who}</b>{at ? when(at) : ''}{extra}</div>
  const mine = m => !!me && m.who === me   // 내가 쓴 댓글만 고치기·지우기(Figma처럼 남의 것은 안 됨)
  const saveEdit = m => { const t = editText.trim(); setEditAt(null); if (!t || t === m.content) return; onThread(thread.map(x => (x === m ? { ...x, content: t, edited: Date.now() } : x))) }
  const remove = m => onThread(thread.map(x => (x === m ? { ...x, content: '', deleted: true } : x)))   // 저장소가 메시지를 안 지워 「지움」 표시로
  const link = { all: 'unset', cursor: 'pointer', color: C.muted, textDecoration: 'underline', fontSize: 11 }
  return <div data-testid="bubble" data-id={id} role="dialog" aria-label={`댓글 — ${info.slide ? '장' : bubbleKind(info.type)}`}
    onPointerDown={e => e.stopPropagation()} onWheel={e => e.stopPropagation()} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') onClose() }}
    style={{ position: 'absolute', left: pos.x, top: pos.y, width: BUBBLE_W, maxHeight: 360, zIndex: 8, display: 'flex', flexDirection: 'column', background: C.card, color: C.ink,
      border: `1px solid ${C.line}`, borderRadius: 12, boxShadow: 'var(--mb-shadow)', font: `400 13px/1.55 ${F}` }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 8px 6px 12px', borderBottom: `1px solid ${C.line}` }}>
      <b style={{ fontSize: 13, whiteSpace: 'nowrap', flex: 'none' }}>💬 {info.slide ? '장' : bubbleKind(info.type)} 댓글</b>
      <span data-testid="bubble-scope" style={{ font: `400 11px ${F}`, color: C.muted, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={info.cut ? '글이 길어 앞쪽 2만 자까지만 보내요' : '@KAIROS를 붙인 댓글에만 AI가 답해요'}>{info.slide ? '@KAIROS = 이 장을 보고 고쳐요' : info.inside ? `@KAIROS = 프레임 안 ${info.inside}개를 보고 답해요${info.cut ? ' · 글 일부만' : ''}` : '@KAIROS = 이것을 보고 답해요'}</span>
      {commentCount(thread) > 0 && !resolved && <button data-testid="bubble-resolve" style={{ ...btn, whiteSpace: 'nowrap', flex: 'none' }} title="해결 — 칠판의 💬 표시를 숨겨요(댓글은 남아요)" onClick={() => { note('resolve'); onClose() }}>✓ 해결</button>}
      <button data-testid="bubble-close" aria-label="댓글 닫기" className="mb-hit" title="닫기(Esc) — 댓글은 남아요" onClick={onClose} style={{ ...btn, position: 'relative', border: 0, flex: 'none', fontSize: 14 }}>✕</button>
    </div>
    <div ref={list} role="log" aria-label="댓글" aria-busy={busy} style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      {!commentCount(thread) && <div style={{ color: C.muted, fontSize: 12.5 }}>이 물건에 댓글을 남겨요 — 같이 보는 사람에게 보여요. {info.edit ? '@KAIROS를 붙여 고쳐 달라면 AI가 그 자리에서 고쳐요(Ctrl+Z로 되돌림).' : '@KAIROS를 붙이면 AI가 이것만 보고 답해요.'}</div>}
      {resolved && <div data-testid="bubble-resolved" style={{ display: 'flex', alignItems: 'center', gap: 6, color: C.muted, fontSize: 12 }}>✓ 해결된 댓글이에요<button data-testid="bubble-reopen" style={btn} onClick={() => note('reopen')}>다시 열기</button></div>}
      {thread.map((m, i) => m.role === 'note' || m.deleted ? null : m.role === 'user'
        ? <div key={i} data-testid="bubble-q" style={{ whiteSpace: 'pre-wrap', wordBreak: 'keep-all', overflowWrap: 'anywhere' }}>
          {meta(m.who || '이름 없음', m.at, <>{m.edited ? <span>· 고침</span> : null}{mine(m) && editAt !== m.at && <span style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <button data-testid="comment-edit" style={link} onClick={() => { setEditAt(m.at); setEditText(m.content) }}>고치기</button>
            <button data-testid="comment-delete" style={link} onClick={() => remove(m)}>지우기</button></span>}</>)}
          {editAt === m.at ? <textarea data-testid="comment-edit-input" className="mb-field" autoFocus aria-label="댓글 고치기" value={editText} rows={2} onChange={e => setEditText(e.target.value)}
              onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); saveEdit(m) } if (e.key === 'Escape') { e.preventDefault(); setEditAt(null) } }} onBlur={() => saveEdit(m)}
              style={{ width: '100%', boxSizing: 'border-box', resize: 'none', border: '1px solid var(--mb-ctl)', borderRadius: 6, padding: '4px 6px', background: 'transparent', color: C.ink, font: `400 13px/1.5 ${F}` }} />
            : m.content}</div>
        : <div key={i} data-testid="bubble-a" style={{ background: C.seg, borderRadius: 10, padding: '5px 9px', whiteSpace: 'pre-wrap', wordBreak: 'keep-all', overflowWrap: 'anywhere' }}>
          {meta('KAIROS', m.at)}{m.content}
          {m.fix && <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4 }}>
            <button data-testid="bubble-flip" style={btn} onClick={() => flip(i)} title="칠판의 것을 바꿔 끼워요">{m.fix.on ? '원래대로' : '바꾼 것으로'}</button>
            <span style={{ font: `400 11px ${F}`, color: C.muted }}>{m.fix.on ? '칠판에서 고쳤어요' : '원래 모습이에요'}</span></div>}
          {m.pend && <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4, flexWrap: 'wrap' }}>
            <button data-testid="bubble-apply" style={btn} onClick={() => apply(i)} title="Ctrl+Z로 되돌릴 수 있어요">이 장에 적용</button>
            <span style={{ font: `400 11px ${F}`, color: C.muted }}>손으로 고친 장이라 기다려요 — 적용하면 손으로 고친 것은 덮여요</span></div>}
          {m.img && <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 4 }}>
            <img src={m.img.url} alt="" style={{ width: 44, height: 44, objectFit: 'cover', borderRadius: 6, border: `1px solid ${C.line}` }} />
            {swaps.current[i] ? <button data-testid="bubble-flip" style={btn} onClick={() => flip(i)} title="칠판의 그림을 바꿔 끼워요">{m.img.on ? '원래대로' : '바꾼 것으로'}</button>
              : <span style={{ font: `400 11px ${F}`, color: C.muted }}>되돌리기는 칠판 Ctrl+Z</span>}</div>}
          {m.model && <div style={{ font: `400 10.5px ${F}`, color: C.muted, marginTop: 2 }}>{m.model}{m.credits ? ` · 약 ${Math.round(m.credits * 10) / 10}크레딧` : ''}</div>}
        </div>)}
      {busy && <div data-testid="bubble-busy" style={{ display: 'flex', alignItems: 'center', gap: 6, color: C.muted, fontSize: 12.5 }}><Spinner />생각 중…</div>}
      {err && <div data-testid="bubble-err" role="alert" style={{ color: 'var(--mb-danger-ink)', fontSize: 12.5, wordBreak: 'keep-all', overflowWrap: 'anywhere' }}>{err}
        {thread.at(-1)?.role === 'user' && <button data-testid="bubble-retry" style={{ ...btn, marginLeft: 6 }} onClick={resend}>다시 보내기</button>}</div>}
    </div>
    <div style={{ padding: 8, borderTop: `1px solid ${C.line}` }}>
      <Composer inputRef={ta} inputId="bubble-input" sendId="bubble-send" label="댓글" value={draft} placeholder={AT_AI.test(draft) ? HINT[info.edit] || HINT[info.type] || '이것에 대해 물어보세요' : '댓글 남기기 — @KAIROS를 붙이면 AI가 답해요'} onChange={e => setDraft(e.target.value)}
        canSend={!!draft.trim() && !busy} onSend={() => send()} onKeyDown={e => { if (e.key === 'Escape') { e.preventDefault(); onClose() } }}
        tools={<><button data-testid="bubble-at" type="button" style={{ ...btn, border: 0 }} title="AI에게 — 댓글 앞에 @KAIROS를 붙여요" onClick={() => { setDraft(d => (AT_AI.test(d) ? d : '@KAIROS ' + d)); ta.current?.focus() }}>@KAIROS</button><span style={{ flex: 1 }} /></>} />
    </div>
  </div>
}

// 댓글이 있는 닫힌 댓글 창 — 물건 오른쪽 위 작은 표시(누르면 열림). 해결된 것은 안 보임(부르는 쪽이 거름)
export function BubbleBadge({ id, info, cam, count, onOpen }) {
  if (!info) return null
  const x = (info.box.x + info.box.w) * cam.z + cam.x + 8, y = info.box.y * cam.z + cam.y - 22   // 오른쪽 위 바깥 — 고른 물건의 크기 조절 손잡이를 덮지 않게
  return <button data-testid="bubble-badge" data-id={id} aria-label={`댓글 열기 — ${count}개`} title={`댓글 열기 — ${count}개`} onPointerDown={e => e.stopPropagation()} onClick={onOpen}
    style={{ all: 'unset', position: 'absolute', left: x, top: y, zIndex: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 2, padding: '1px 6px', borderRadius: 99,
      background: 'var(--mb-accent)', color: '#fff', font: `600 11px ${F}`, boxShadow: '0 1px 4px rgba(0,0,0,.25)' }}>💬 {count}</button>
}

// 댓글 모아 보기(2026-11-14 — 떠 있는 판 「댓글」: ☰ 메뉴 「댓글 모아 보기」) — 칠판의 댓글 전부, 해결된 것은 「해결된 것도」를 켜야 보임.
// 줄 누르기 = 그 물건으로 가서 댓글 창을 엶. info(id) = 물건 정보(지운 물건의 댓글은 안 보임)
export function CommentList({ threads, info, onOpen }) {
  const [all, setAll] = useState(false)
  const rows = Object.entries(threads || {}).map(([id, t]) => ({ id, t, i: info(id), n: commentCount(t), done: isResolved(t) })).filter(r => r.i && r.n && (all || !r.done))
    .sort((a, b) => (b.t.at(-1)?.at || 0) - (a.t.at(-1)?.at || 0))   // 최근 것 먼저
  const first = t => t.find(m => (m.role === 'user' || m.role === 'assistant') && !m.deleted)
  return <div data-testid="comment-list" style={{ padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6, font: `400 12.5px ${F}`, color: C.ink }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><b style={{ font: `700 15px ${F}` }}>댓글</b>
      <label style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4, fontSize: 11.5, color: C.muted, cursor: 'pointer' }}><input type="checkbox" data-testid="comment-all" checked={all} onChange={e => setAll(e.target.checked)} />해결된 것도</label></div>
    {!rows.length && <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.6 }}>{all ? '아직 댓글이 없어요 — 물건을 우클릭 「댓글…」로 남겨요.' : '열린 댓글이 없어요. 해결된 것은 「해결된 것도」를 켜면 보여요.'}</div>}
    {rows.map(r => { const f = first(r.t)
      return <button key={r.id} data-testid="comment-row" data-done={r.done || undefined} onClick={() => onOpen(r.id)} className="mb-row"
        style={{ all: 'unset', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 2, padding: '6px 8px', borderRadius: 8, border: `1px solid ${C.line}`, opacity: r.done ? 0.7 : 1 }}>
        <span style={{ display: 'flex', gap: 6, fontSize: 11, color: C.muted }}>💬 {r.n} · {r.i.slide ? '장' : bubbleKind(r.i.type)}{r.done ? ' · ✓ 해결' : ''}<span style={{ marginLeft: 'auto' }}>{when(r.t.at(-1)?.at || 0)}</span></span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f ? `${f.role === 'assistant' ? 'KAIROS' : f.who || '이름 없음'}: ${f.content}` : ''}</span></button> })}
  </div>
}
