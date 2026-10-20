// 칠판 찾기(Ctrl+F, §8 항목61 ③-2 뜻으로 찾기, 2026-10-19) — 처음 의도 「쌓여서 다시 찾아진다」의 「다시 찾아진다」.
// 치면 바로 낱말로 찾고(이 브라우저, 서버 없이도), 0.4초 쉬면 서버가 KAIROS 임베딩으로 뜻이 가까운 것을 찾아 순서를 다시 맞춤(`/api/find/<이름>` — easycad/ai/board_find.py).
// 찾은 것은 칠판 위 노란 점선(onMarks), ↑↓로 고르고 Enter·누르기 = 그 도형으로 가기(onGo), Esc 닫기.
import { useEffect, useRef, useState } from 'react'
import { DOC_NAME } from './doc.js'
import { memoText } from './memo.js'
import { keyHeaders } from './kairosKey.js'

// 정리 문서 HTML → 쉬운 글(찾기·대화 근거) — 서버 `board_report.plain_text`와 같은 뜻
export const docText = html => { if (!html) return ''; try { const d = new DOMParser().parseFromString(html, 'text/html'); d.querySelectorAll('style,script').forEach(n => n.remove()); return (d.body?.innerText || d.body?.textContent || '').replace(/[ \t]+/g, ' ').trim().slice(0, 4000) } catch { return '' } }

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', group: 'var(--mb-group)' }
const KIND = { memo: '메모', text: '글', table: '표', web: '웹 카드', frame: '프레임', image: '그림', sarrow: '화살표', arrow: '화살표', rect: '상자', ellipse: '원', symbol: '심볼', line: '선', polygon: '다각형', titleblock: '표제란' }

// 도형 하나의 글 — 서버 `board_find.item_text`와 같은 칸
export function itemText(it) {
  const out = []
  if (it.type === 'memo') out.push(memoText(it.lines || []))
  if (it.type === 'text') out.push(it.text || '')
  if (it.label?.text) out.push(it.label.text)
  for (const L of it.labels || []) if (L?.text) out.push(L.text)
  if (it.type === 'table') for (const row of it.cells || []) out.push(row.filter(Boolean).join(' | '))
  if (it.type === 'web') out.push(it.title || '', it.desc || '', it.url || '')
  if (it.type === 'frame') out.push(it.name || '')
  if (it.type === 'image') out.push(it.alt || '')   // 그림 = 만든 요청(보이지 않는 설명, 2026-10-20)
  if (it.type === 'doc') out.push(it.title || '', docText(it.html))
  if (it.type === 'titleblock' && it.fields) out.push(...Object.values(it.fields).map(String))
  return out.map(s => String(s).trim()).filter(Boolean).join('\n')
}

// 낱말 찾기 — 친 낱말(두 글자 이상, 띄어 쓴 것 각각)이 모두 들어 있는 것
export function wordHits(items, q) {
  const words = q.toLowerCase().split(/\s+/).filter(w => w.length >= 1)
  if (!words.length) return []
  return items.map(it => ({ it, text: itemText(it) })).filter(r => r.text && words.every(w => r.text.toLowerCase().includes(w)))
    .map(r => ({ uid: r.it._id, type: r.it.type, kind: KIND[r.it.type] || r.it.type, text: r.text, word: true }))
}

export function FindBar({ items, server, onMarks, onGo, onClose }) {
  const [q, setQ] = useState(''), [sem, setSem] = useState(null), [busy, setBusy] = useState(false), [err, setErr] = useState(''), [at, setAt] = useState(0)
  const inp = useRef(null), ask = useRef(0)
  useEffect(() => { inp.current?.focus() }, [])
  const words = q.trim() ? wordHits(items, q.trim()) : []
  // 뜻 결과가 오면 그 차례(낱말이 다 든 것은 서버가 점수를 더 줌) + 뜻 결과에 없는 낱말 결과는 뒤에. 지운 도형은 뺌
  const live = new Set(items.map(it => it._id)), wordSet = new Set(words.map(r => r.uid))
  const rows = sem ? [...sem.filter(r => live.has(r.uid)).map(r => ({ ...r, word: wordSet.has(r.uid) })), ...words.filter(r => !sem.some(s => s.uid === r.uid))] : words
  useEffect(() => {
    setSem(null); setErr(''); setAt(0)
    const t = q.trim(); if (!t || !server) { setBusy(false); return }
    const my = ++ask.current; setBusy(true)
    const h = setTimeout(async () => {
      try {
        const r = await fetch(`/api/find/${encodeURIComponent(DOC_NAME)}`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() }, body: JSON.stringify({ q: t, k: 8 }) })
        const d = await r.json().catch(() => ({}))
        if (my !== ask.current) return
        if (!r.ok || d.error) setErr(d.error || `서버 응답 ${r.status}`); else setSem(d.results || [])
      } catch { if (my === ask.current) setErr('서버 연결 안 됨 — 낱말 찾기만') } finally { if (my === ask.current) setBusy(false) }
    }, 400)
    return () => clearTimeout(h)
  }, [q, server])
  const key = rows.map(r => r.uid).join()
  useEffect(() => { onMarks(rows.map(r => r.uid)) }, [key])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => onMarks([]), [])   // eslint-disable-line react-hooks/exhaustive-deps
  const go = i => { const r = rows[i]; if (r) { setAt(i); onGo(r.uid) } }
  return <div data-testid="find-bar" onPointerDown={e => e.stopPropagation()} style={{ position: 'absolute', zIndex: 25, left: '50%', top: 12, transform: 'translateX(-50%)', width: 'min(440px, calc(100% - 32px))',
    background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, boxShadow: '0 6px 18px rgba(0,0,0,.18)', font: "400 12.5px 'Pretendard', sans-serif", color: C.ink, overflow: 'hidden' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 10px', borderBottom: rows.length || q ? `1px solid ${C.line}` : 'none' }}>
      <span style={{ color: C.muted }}>🔍</span>
      <input ref={inp} value={q} onChange={e => setQ(e.target.value)} placeholder="칠판에서 찾기 — 낱말이 달라도 뜻으로 (↑↓ · Enter · Esc)"
        onKeyDown={e => { e.stopPropagation()
          if (e.key === 'Escape') { e.preventDefault(); onClose() }
          else if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); go(at) }
          else if (e.key === 'ArrowDown') { e.preventDefault(); go(Math.min(rows.length - 1, at + 1)) }
          else if (e.key === 'ArrowUp') { e.preventDefault(); go(Math.max(0, at - 1)) } }}
        style={{ flex: 1, border: 'none', outline: 'none', background: 'transparent', color: C.ink, font: "400 13.5px 'Pretendard', sans-serif" }} />
      <span style={{ color: C.muted, fontSize: 11, whiteSpace: 'nowrap' }}>{busy ? '뜻으로 찾는 중…' : q.trim() ? `${rows.length}개` : ''}</span>
    </div>
    {err && <div style={{ padding: '4px 12px', color: '#d97706', fontSize: 11 }}>{err}</div>}
    {rows.length > 0 && <div style={{ maxHeight: 300, overflowY: 'auto', padding: 4 }}>
      {rows.map((r, i) => <button key={r.uid} data-testid="find-row" onClick={() => go(i)} onMouseEnter={() => setAt(i)}
        style={{ all: 'unset', boxSizing: 'border-box', width: '100%', display: 'flex', gap: 8, alignItems: 'baseline', padding: '5px 8px', borderRadius: 6, cursor: 'pointer', background: i === at ? 'rgba(245,158,11,.14)' : 'transparent' }}>
        <span style={{ flex: 'none', fontSize: 11, color: C.muted, width: 46 }}>{r.kind}</span>
        <span style={{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.text.split('\n')[0]}</span>
        <span style={{ flex: 'none', fontSize: 10.5, color: r.word ? '#2f80ed' : '#d97706' }} title={r.word ? '친 낱말이 들어 있음' : '낱말은 달라도 뜻이 가까움'}>{r.word ? '낱말' : '뜻'}</span>
      </button>)}
    </div>}
    {q.trim() && !rows.length && !busy && <div style={{ padding: '8px 12px', color: C.muted }}>{server ? '칠판에서 못 찾았어요' : '못 찾았어요 — 서버가 없으면 낱말 찾기만 돼요'}</div>}
  </div>
}
