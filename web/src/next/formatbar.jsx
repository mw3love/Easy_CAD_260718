// 드래그 꾸미기 막대(2026-10-19 사용자: 노션처럼 글자를 드래그하면 바로 위에 — 마크다운은 어려움). 메모·글 상자·라벨·표 칸 공용.
// 고른 글자가 있을 때만 그 위(자리가 없으면 아래)에 뜸. 누를 때 편집기 포커스를 잃지 않게 mousedown 기본 동작을 막고, data-keep-edit로 편집이 안 끝나게.
// 옛 오른쪽 위 「글자」 카드(굵게·색·형광펜)를 대신함 — 글 전체 크기 같은 것은 편집을 끝낸 뒤 속성 카드.
import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

const C = { card: 'var(--mb-card)', line: 'var(--mb-line)', ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', seg: 'var(--mb-seg, rgba(127,127,127,.12))' }
// 글자색 — 노션 글자색과 같은 결(진한 쪽), 맨 앞 = 기본(색 지우기)
const COLORS = [[null, '기본'], ['#d44c47', '빨강'], ['#d9730d', '주황'], ['#cb912f', '노랑'], ['#448361', '초록'], ['#337ea9', '파랑'], ['#9065b0', '보라'], ['#c14c8a', '분홍'], ['#787774', '회색']]
const HL = 'rgba(255,213,79,0.6)'

export function FormatBar({ ed, onTurn }) {   // onTurn = 줄 종류 바꾸기 메뉴 열기(메모만 — 제목·목록·할 일…)
  const [, tick] = useState(0), [pal, setPal] = useState(false)
  useEffect(() => {
    if (!ed) return
    const f = () => tick(n => n + 1), close = () => setPal(false)
    ed.on('selectionUpdate', f); ed.on('transaction', f); ed.on('blur', f); ed.on('focus', f); ed.on('selectionUpdate', close)
    return () => { ed.off('selectionUpdate', f); ed.off('transaction', f); ed.off('blur', f); ed.off('focus', f); ed.off('selectionUpdate', close) }
  }, [ed])
  if (!ed || ed.isDestroyed) return null
  const { from, to, empty } = ed.state.selection
  if (empty) return null
  let a, b; try { a = ed.view.coordsAtPos(from); b = ed.view.coordsAtPos(to) } catch { return null }
  const W = onTurn ? 330 : 290, H = 34
  const above = Math.min(a.top, b.top) - H - 8, top = above > 56 ? above : Math.max(a.bottom, b.bottom) + 8
  const left = Math.max(8, Math.min(window.innerWidth - W - 8, Math.min(a.left, b.left)))
  const run = f => f(ed.chain().focus()).run(), on = n => ed.isActive(n)
  const ts = ed.getAttributes('textStyle'), color = (ts.color || '').toLowerCase(), hl = !!ts.backgroundColor
  const btn = (act, title, label, extra = {}) => <button title={title} aria-pressed={act || undefined} data-testid={'fmt-' + title.split(' ')[0]}
    style={{ all: 'unset', cursor: 'pointer', minWidth: 26, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 5, fontSize: 13, color: C.ink, background: act ? 'rgba(218,119,86,.22)' : 'transparent', ...extra.style }}
    onClick={extra.onClick}>{label}</button>
  const sep = <span style={{ width: 1, height: 18, background: C.line, margin: '0 2px' }} />
  return createPortal(<div data-keep-edit data-testid="format-bar" onMouseDown={e => e.preventDefault()} onPointerDown={e => e.stopPropagation()}
    style={{ position: 'fixed', left, top, zIndex: 60, display: 'flex', alignItems: 'center', gap: 2, padding: '4px 6px', background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, boxShadow: '0 4px 14px rgba(0,0,0,.18)', font: "400 12px 'Pretendard', sans-serif", userSelect: 'none' }}>
    {onTurn && <>{btn(false, '줄 종류 — 제목·목록·할 일·코드…', <span style={{ fontSize: 12, padding: '0 4px' }}>줄 ▾</span>, { onClick: onTurn })}{sep}</>}
    {btn(on('bold'), '굵게 (Ctrl+B)', <b>B</b>, { onClick: () => run(c => c.toggleBold()) })}
    {btn(on('italic'), '기울임 (Ctrl+I)', <i style={{ fontFamily: 'serif' }}>I</i>, { onClick: () => run(c => c.toggleMark('italic')) })}
    {btn(on('underline'), '밑줄 (Ctrl+U)', <u>U</u>, { onClick: () => run(c => c.toggleMark('underline')) })}
    {btn(on('strike'), '취소선 (Ctrl+Shift+X)', <s>S</s>, { onClick: () => run(c => c.toggleMark('strike')) })}
    {btn(on('code'), '코드 — 고정폭 글꼴', <span style={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}>&lt;/&gt;</span>, { onClick: () => run(c => c.toggleCode()) })}
    {sep}
    <div style={{ position: 'relative' }}>
      {btn(pal, '글자색', <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', lineHeight: '13px' }}>A<span style={{ width: 12, height: 3, borderRadius: 1, background: color || C.ink }} /></span>, { onClick: () => setPal(p => !p) })}
      {pal && <div data-testid="fmt-palette" style={{ position: 'absolute', top: 30, left: -4, display: 'grid', gridTemplateColumns: 'repeat(3, 72px)', gap: 2, padding: 6, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, boxShadow: '0 4px 14px rgba(0,0,0,.18)' }}>
        {COLORS.map(([c, n]) => <button key={n} title={n} onClick={() => { run(ch => (c ? ch.setColor(c) : ch.unsetColor())); setPal(false) }}
          style={{ all: 'unset', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, padding: '3px 6px', borderRadius: 5, fontSize: 12, color: C.ink, background: (c || '') === color ? 'rgba(218,119,86,.18)' : 'transparent' }}>
          <span style={{ width: 16, height: 16, borderRadius: 4, border: `1px solid ${C.line}`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: c || C.ink, fontWeight: 700, fontSize: 12 }}>A</span>{n}</button>)}
      </div>}
    </div>
    {btn(hl, '형광펜 — 다시 누르면 지워요', <span style={{ width: 16, height: 12, borderRadius: 2, background: HL }} />, { onClick: () => run(c => (hl ? c.unsetBackgroundColor() : c.setBackgroundColor(HL))) })}
    {btn(false, '꾸밈 지우기', <span style={{ fontSize: 12 }}>T<sub style={{ fontSize: 9 }}>x</sub></span>, { onClick: () => run(c => c.unsetAllMarks()) })}
  </div>, document.body)
}
