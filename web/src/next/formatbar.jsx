// 드래그 꾸미기 막대(2026-10-19 사용자: 노션처럼 글자를 드래그하면 바로 위에 — 마크다운은 어려움). 메모·글 상자·라벨·표 칸 공용.
// 고른 글자가 있을 때만 그 위(자리가 없으면 아래)에 뜸. 누를 때 편집기 포커스를 잃지 않게 mousedown 기본 동작을 막고, data-keep-edit로 편집이 안 끝나게.
// 옛 오른쪽 위 「글자」 카드(굵게·색·형광펜)를 대신함 — 글 전체 크기 같은 것은 편집을 끝낸 뒤 속성 카드.
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ColorPop } from './colorpop.jsx'
import { FmtButtons, edAct, edRun, edState, useEdTick } from './textfmt.jsx'

const C = { card: 'var(--mb-card)', line: 'var(--mb-line)', ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', seg: 'var(--mb-seg, rgba(127,127,127,.12))' }
// 버튼 줄은 속성 카드 「글자」와 같은 부품(`textfmt.jsx`), 글자색은 속성 카드와 같은 색 창(`colorpop.jsx` — 전엔 노션식 9색, 2026-10-23 통일)

export function FormatBar({ ed, onTurn }) {   // onTurn = 줄 종류 바꾸기 메뉴 열기(메모만 — 제목·목록·할 일…)
  const [pal, setPal] = useState(false), colorBtn = useRef(null)
  useEdTick(ed)
  useEffect(() => { if (!ed) return; const close = () => setPal(false); ed.on('selectionUpdate', close); return () => ed.off('selectionUpdate', close) }, [ed])
  useEffect(() => {   // 색 창 — 바깥 누르기·Esc = 닫기
    if (!pal) return
    const down = e => { if (!e.target.closest?.('[data-ppop="fmtcolor"]')) setPal(false) }, key = e => { if (e.key === 'Escape') { e.stopImmediatePropagation(); setPal(false) } }
    window.addEventListener('pointerdown', down, true); window.addEventListener('keydown', key, true)
    return () => { window.removeEventListener('pointerdown', down, true); window.removeEventListener('keydown', key, true) }
  }, [pal])
  if (!ed || ed.isDestroyed) return null
  const { from, to, empty } = ed.state.selection
  if (empty && !pal) return null
  let a, b; try { a = ed.view.coordsAtPos(from); b = ed.view.coordsAtPos(to) } catch { return null }
  const W = onTurn ? 330 : 290, H = 34
  const above = Math.min(a.top, b.top) - H - 8, top = above > 56 ? above : Math.max(a.bottom, b.bottom) + 8
  const left = Math.max(8, Math.min(window.innerWidth - W - 8, Math.min(a.left, b.left)))
  const st = edState(ed)
  const colorBtnEl = <span ref={colorBtn} data-ppop="fmtcolor" style={{ display: 'flex' }}><button title="글자색" aria-label="글자색" aria-pressed={pal || undefined} data-testid="fmt-글자색" onClick={() => setPal(p => !p)}
    style={{ all: 'unset', cursor: 'pointer', minWidth: 24, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 5, fontSize: 13, color: C.ink, background: pal ? 'rgba(218,119,86,.22)' : 'transparent' }}>
    <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', lineHeight: '13px' }}>A<span style={{ width: 12, height: 3, borderRadius: 1, background: st.color || C.ink }} /></span></button>
    {pal && <ColorPop anchor={colorBtn} id="fmtcolor" align="left" keepEdit value={st.color || undefined} onPick={c => edRun(ed, ch => (c ? ch.setColor(c) : ch.unsetColor()))} onReset={() => edRun(ed, ch => ch.unsetColor())} />}</span>
  return createPortal(<div data-keep-edit data-testid="format-bar" onMouseDown={e => { if (e.target.tagName !== 'INPUT') e.preventDefault() }} onPointerDown={e => e.stopPropagation()}
    style={{ position: 'fixed', left, top, zIndex: 60, display: 'flex', alignItems: 'center', gap: 2, padding: '4px 6px', background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, boxShadow: '0 4px 14px rgba(0,0,0,.18)', font: "400 12px 'Pretendard', sans-serif", userSelect: 'none' }}>
    {onTurn && <><button title="줄 종류 — 제목·목록·할 일·코드…" data-testid="fmt-줄" onClick={onTurn} style={{ all: 'unset', cursor: 'pointer', height: 26, display: 'flex', alignItems: 'center', borderRadius: 5, fontSize: 12, padding: '0 4px', color: C.ink }}>줄 ▾</button>
      <span style={{ width: 1, height: 18, background: C.line, margin: '0 2px' }} /></>}
    <FmtButtons st={st} act={k => edAct(ed, k)} color={colorBtnEl} />
  </div>, document.body)
}
