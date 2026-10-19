// 좌하 「프레임」 카드(2026-10-18 사용자와 정함) — 프레임 순서의 본거지. 출력 쪽 순서·슬라이드 순서가 모두 이 순서(.ecad 프레임 `no` = 1..n 다시 매김).
// 줄 끌기 = 순서 바꾸기, 누르기 = 그 프레임으로 화면 이동, 두 번 누르기 = 이름 고치기(치는 대로 바로). 프레임이 있을 때만 보임. 레이어 카드와 같은 모양.
import { useState } from 'react'
import { FoldBtn, useFold } from './fold.jsx'
import { orderedFrames } from './edit.js'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', on: '#da7756' }
const GRIP = <svg width="10" height="14" viewBox="0 0 10 14" fill="currentColor" opacity=".55">{[2, 7, 12].flatMap(y => [<circle key={`a${y}`} cx="3" cy={y} r="1.2" />, <circle key={`b${y}`} cx="7" cy={y} r="1.2" />])}</svg>

// items = 문서 아이템, sel = 고른 것 _id, onReorder(ids 새 순서), onRename(id, 이름), onGo(id), dark
export function Frames({ items, sel, onReorder, onRename, onGo, onPresent, dark }) {
  const [folded, toggleFold] = useFold('frames')
  const frames = orderedFrames(items), [hover, setHover] = useState(null), [drag, setDrag] = useState(null), [over, setOver] = useState(null), [renaming, setRenaming] = useState(null)
  if (!frames.length) return null
  const drop = to => {
    if (drag == null || drag === to) return
    const ids = frames.map(f => f._id), [m] = ids.splice(drag, 1); ids.splice(to > drag ? to - 1 : to, 0, m); onReorder(ids)
  }
  const selBg = dark ? '#2d3640' : '#dfe5eb'
  return <div data-folded={folded || undefined} onPointerDown={e => e.stopPropagation()} data-testid="frames-card" style={{ pointerEvents: 'auto', width: 192, boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: 8,
    boxShadow: '0 2px 8px rgba(0,0,0,.06)', color: C.ink, display: 'flex', flexDirection: 'column', gap: 4, userSelect: 'none', flex: 'none' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ font: "700 15px 'Pretendard', sans-serif" }}>프레임</span>
      <span style={{ flex: 1 }} />
      <button onClick={() => onPresent()} title="발표 — 프레임 순서대로 한 장씩(고른 프레임부터) · → 다음 · ← 이전 · Esc 끝" style={{ all: 'unset', cursor: 'pointer', padding: '2px 8px', borderRadius: 6, background: C.on, color: '#fff', font: "600 11px 'Pretendard', sans-serif" }}>▶ 발표</button><FoldBtn folded={folded} onClick={toggleFold} /></div>
    <span style={{ fontSize: 11, color: C.muted }}>끌어서 순서 = 출력·발표 순서</span>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 1, maxHeight: 200, overflowY: 'auto' }}>
      {frames.map((f, i) => <div key={f._id} draggable={renaming !== f._id} data-testid="frame-row"
        onDragStart={e => { setDrag(i); e.dataTransfer.effectAllowed = 'move' }} onDragEnd={() => { setDrag(null); setOver(null) }}
        onDragOver={e => { e.preventDefault(); const r = e.currentTarget.getBoundingClientRect(); setOver(e.clientY < r.top + r.height / 2 ? i : i + 1) }}
        onDrop={e => { e.preventDefault(); drop(over ?? i); setDrag(null); setOver(null) }}
        onMouseEnter={() => setHover(f._id)} onMouseLeave={() => setHover(h => (h === f._id ? null : h))}
        onClick={() => onGo(f._id)} title="누르면 이 프레임으로 · 두 번 누르면 이름 고치기 · 끌어서 순서"
        style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 4px', borderRadius: 4, cursor: 'pointer', font: "400 12px 'Pretendard', sans-serif",
          background: sel.includes(f._id) ? selBg : 'transparent', opacity: drag === i ? 0.4 : 1,
          boxShadow: over === i && drag !== null ? `inset 0 2px 0 ${C.on}` : over === i + 1 && i === frames.length - 1 && drag !== null ? `inset 0 -2px 0 ${C.on}` : 'none' }}>
        <span style={{ display: 'flex', cursor: 'grab', color: C.muted }}>{GRIP}</span>
        <span style={{ minWidth: 16, textAlign: 'right', color: C.muted, fontVariantNumeric: 'tabular-nums' }}>{i + 1}</span>
        {renaming === f._id
          ? <input autoFocus defaultValue={f.name || ''} placeholder="이름" onClick={e => e.stopPropagation()} onChange={e => onRename(f._id, e.target.value)}
            onBlur={() => setRenaming(null)} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter' || e.key === 'Escape') setRenaming(null) }}
            style={{ flex: 1, minWidth: 0, height: 20, border: `1px solid ${C.line}`, borderRadius: 4, background: 'transparent', color: C.ink, font: 'inherit', padding: '0 4px' }} />
          : <span onDoubleClick={e => { e.stopPropagation(); setRenaming(f._id) }} style={{ flex: 1, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis', color: f.name ? C.ink : C.muted }}>{f.name || '이름 없음'}</span>}
        {hover === f._id && renaming !== f._id && <button data-testid="frame-play" title="이 장부터 발표" onClick={e => { e.stopPropagation(); onPresent(f._id) }}
          style={{ all: 'unset', cursor: 'pointer', flex: 'none', width: 20, height: 18, borderRadius: 4, background: C.on, color: '#fff', fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>▶</button>}
      </div>)}
    </div>
  </div>
}
