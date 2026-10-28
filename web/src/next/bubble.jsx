// 💬 AI 말풍선(2026-10-28 사용자) — 물건마다 작은 KAIROS 대화창. 큰 대화창에 여러 물건 작업이 섞이지 않게, 옛 주석 말풍선이 AI 대화로.
// 말풍선 하나 = 물건 하나(_id): 그 물건의 글(프레임은 안의 것까지)·그림 + 이 말풍선 앞 대화만 보냄(서버 /api/chat `kind: 'bubble'` → `easycad/ai/board_bubble.py`).
// 메모·표·글 상자(3단계)·그림(2단계)을 고쳐 달라면 그 자리에서 고침(Ctrl+Z 한 번) — 답 글은 「무엇을 바꿨는지」만, 「원래대로 ↔ 바꾼 것」(Claude Docs 댓글 + 딥모드 `deepFlip`에서 가져옴).
// 대화는 서버 `<칠판>.threads.json`(물건 _id마다 — main.jsx가 읽고 씀), 여러 말풍선을 같이 열고 따로 기다림. 칠판 그림(PDF·PNG·발표)엔 안 나옴.
import { useEffect, useRef, useState } from 'react'
import { DOC_NAME } from './doc.js'
import { keyHeaders } from './kairosKey.js'
import { Spinner, shrinkImage } from './chat.jsx'

const F = "'Pretendard', sans-serif"
const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)' }
export const BUBBLE_W = 300
const KIND = { memo: '메모', image: '그림', text: '글', table: '표', pdf: 'PDF', doc: '정리 문서', web: '웹 카드', frame: '프레임', titleblock: '프레임' }
const HINT = { memo: '이 메모를 어떻게 할까요? 예: 할 일만 뽑아 아래에 · 쉬운 말로', table: '이 표를 어떻게 할까요? 예: 합계 줄 더해 줘', text: '이 글을 어떻게 할까요? 예: 더 짧게 · 영어로', label: '이 글을 어떻게 할까요? 예: 더 짧게', image: '묻거나 고쳐 달라고 하세요 — 예: 배경을 밝게', slide: '이 장을 어떻게 할까요? 예: 더 짧게 · 숫자 칸으로', frame: '이 프레임 안의 것에 대해 물어보세요' }
export const bubbleKind = t => KIND[t] || '도형'

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

export function Bubble({ id, info, cam, size, thread = [], onThread, onClose, onEdit, onFields, onImage, onStatus }) {
  const [draft, setDraft] = useState(''), [busy, setBusy] = useState(false), [err, setErr] = useState('')
  const list = useRef(null), ta = useRef(null), swaps = useRef({})   // swaps = 답 번호 → 그림 { before, after }(이 창에만)
  useEffect(() => { ta.current?.focus() }, [])
  useEffect(() => { list.current?.scrollTo(0, list.current.scrollHeight) }, [thread.length, busy])
  if (!info) return null
  const pos = bubblePos(info.box, cam, size)
  async function send() {
    const q = draft.trim(); if (!q || busy) return
    const mine = { role: 'user', content: q, at: Date.now() }, next = [...thread, mine]
    onThread(next); setDraft(''); setBusy(true); setErr('')
    try {
      let model = ''; try { model = localStorage.getItem('magic-board-model') || '' } catch { /* 서버 기본 모델 */ }
      const image = info.image ? await shrinkImage(info.image) : '', images = info.images ? await Promise.all(info.images.map(shrinkImage)) : []   // images = 프레임 안 그림(서버 `see`가 1024로 다시 줄임)
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() },
        body: JSON.stringify({ kind: 'bubble', board: DOC_NAME, ...(model ? { model } : {}), item: { type: info.type, text: info.text, ...(info.edit ? { edit: info.edit === 'label' ? 'text' : info.edit } : {}), ...(image ? { image } : {}), ...(images.length ? { images } : {}), ...(info.slide ? { slide: info.slide, deck: info.deck } : {}) }, messages: next.map(({ role, content }) => ({ role, content })) }) })
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
    } catch (e) { setErr(String(e.message || e)) } finally { setBusy(false) }
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
  const btn = { all: 'unset', cursor: 'pointer', font: `500 11.5px ${F}`, color: C.muted, padding: '2px 7px', borderRadius: 6, border: `1px solid ${C.line}` }
  return <div data-testid="bubble" data-id={id} role="dialog" aria-label={`AI 말풍선 — ${bubbleKind(info.type)}`}
    onPointerDown={e => e.stopPropagation()} onWheel={e => e.stopPropagation()} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') onClose() }}
    style={{ position: 'absolute', left: pos.x, top: pos.y, width: BUBBLE_W, maxHeight: 360, zIndex: 8, display: 'flex', flexDirection: 'column', background: C.card, color: C.ink,
      border: `1px solid ${C.line}`, borderRadius: 12, boxShadow: '0 6px 20px rgba(0,0,0,.18)', font: `400 13px/1.55 ${F}` }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '7px 8px 6px 12px', borderBottom: `1px solid ${C.line}` }}>
      <b style={{ fontSize: 13 }}>💬 {info.slide ? '장' : bubbleKind(info.type)} 말풍선</b>
      <span data-testid="bubble-scope" style={{ font: `400 11px ${F}`, color: C.muted }} title={info.cut ? '글이 길어 앞쪽 2만 자까지만 보내요' : undefined}>{info.slide ? '이 장을 보고 고쳐요' : info.inside ? `프레임 안 ${info.inside}개를 보고 답해요${info.cut ? ' · 글 일부만' : ''}` : '이것만 보고 답해요'}</span>
      <button data-testid="bubble-close" title="닫기(Esc) — 대화는 남아요" onClick={onClose} style={{ ...btn, border: 0, marginLeft: 'auto', fontSize: 14 }}>✕</button>
    </div>
    <div ref={list} style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 6 }}>
      {!thread.length && <div style={{ color: C.muted, fontSize: 12.5 }}>{info.edit ? '고쳐 달라면 그 자리에서 고쳐요(Ctrl+Z로 되돌림). 물으면 답만 해요.' : '이 물건만 보고 답해요 — 큰 대화창과 섞이지 않아요.'}</div>}
      {thread.map((m, i) => m.role === 'user'
        ? <div key={i} data-testid="bubble-q" style={{ alignSelf: 'flex-end', maxWidth: '88%', background: 'rgba(218,119,86,.12)', borderRadius: 10, padding: '4px 9px', whiteSpace: 'pre-wrap' }}>{m.content}</div>
        : <div key={i} data-testid="bubble-a" style={{ alignSelf: 'flex-start', maxWidth: '96%', background: C.seg, borderRadius: 10, padding: '5px 9px', whiteSpace: 'pre-wrap' }}>
          {m.content}
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
      {err && <div data-testid="bubble-err" style={{ color: '#dc2626', fontSize: 12.5 }}>{err}</div>}
    </div>
    <div style={{ padding: 8, borderTop: `1px solid ${C.line}` }}>
      <textarea ref={ta} data-testid="bubble-input" rows={2} value={draft} placeholder={HINT[info.edit] || HINT[info.type] || '이것에 대해 물어보세요'} onChange={e => setDraft(e.target.value)}
        onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') { onClose(); return } if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }}
        style={{ width: '100%', boxSizing: 'border-box', resize: 'none', border: `1px solid ${C.line}`, borderRadius: 8, padding: '5px 8px', font: `400 13px/1.5 ${F}`, background: 'transparent', color: C.ink, outline: 'none' }} />
    </div>
  </div>
}

// 대화가 있는 닫힌 말풍선 — 물건 오른쪽 위 작은 표시(누르면 열림)
export function BubbleBadge({ id, info, cam, count, onOpen }) {
  if (!info) return null
  const x = (info.box.x + info.box.w) * cam.z + cam.x + 8, y = info.box.y * cam.z + cam.y - 22   // 오른쪽 위 바깥 — 고른 물건의 크기 조절 손잡이를 덮지 않게
  return <button data-testid="bubble-badge" data-id={id} title={`AI 말풍선 열기 — 대화 ${count}개`} onPointerDown={e => e.stopPropagation()} onClick={onOpen}
    style={{ all: 'unset', position: 'absolute', left: x, top: y, zIndex: 7, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 2, padding: '1px 6px', borderRadius: 99,
      background: '#da7756', color: '#fff', font: `600 11px ${F}`, boxShadow: '0 1px 4px rgba(0,0,0,.25)' }}>💬 {count}</button>
}
