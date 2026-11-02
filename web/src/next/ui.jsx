// 웹 화면 공용 부품(2026-11-02 — 웹 디자인 규칙 `docs/web_ui_rules.md`): 단추 모양·마우스 올림·확인 창을 판마다 따로 짜지 않게 한곳에.
// 메뉴는 `ctxmenu.jsx`(ContextMenu·FloatMenu)가 하나뿐인 메뉴 부품이다.
import { useEffect, useRef } from 'react'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)' }
export const ACCENT = 'var(--mb-accent)', DANGER = '#d44c47', HOVER = 'var(--mb-group)'
const F = "'Pretendard', sans-serif"

// 규칙 ③ 마우스 올림 = 회색 바탕(뜻 있는 「켜짐」만 코랄)
export const hoverBg = { onMouseEnter: e => { e.currentTarget.style.background = HOVER }, onMouseLeave: e => { e.currentTarget.style.background = 'transparent' } }

// 규칙 A1 — 코랄 채움 = 판마다 대표 행동 하나. 그 밖은 회색 테두리
export const btnPrimary = { all: 'unset', cursor: 'pointer', padding: '3px 10px', borderRadius: 6, background: ACCENT, color: '#fff', font: `600 12px ${F}` }
export const btnSecondary = { all: 'unset', cursor: 'pointer', padding: '3px 10px', borderRadius: 6, border: `1px solid ${C.line}`, color: C.ink, font: `500 12px ${F}` }
// 규칙 B1 — 머리줄 오른쪽 작은 단추(「＋ 새 폴더」·「＋ 새 레이어」)
export const btnHead = { all: 'unset', cursor: 'pointer', padding: '1px 6px', borderRadius: 4, border: `1px solid ${C.line}`, color: C.ink, font: `500 11px ${F}`, whiteSpace: 'nowrap' }
// 규칙 ④ — ⋯: 머리줄은 늘 보이고 테두리 없음, 줄은 마우스를 올렸을 때만(`show`)
export const moreBtn = show => ({ all: 'unset', cursor: 'pointer', flex: 'none', width: 18, textAlign: 'center', borderRadius: 4, color: C.muted, fontWeight: 700, lineHeight: '18px', visibility: show ? 'visible' : 'hidden' })

// ⋯ 단추 아래에 메뉴 띄우기 — 같은 단추를 다시 누르면 닫힘(ContextMenu `anchor`가 그 단추 누르기를 「바깥」으로 안 봄)
export const menuBelow = (e, extra = {}) => { const r = e.currentTarget.getBoundingClientRect(); return { x: r.left, y: r.bottom + 2, anchor: e.currentTarget, ...extra } }

// 규칙 ⑥ — 되돌릴 수 없는 지우기만 묻는 앱 안 확인 창(브라우저 confirm은 칠판 조작을 막음).
// Enter = 확인(초점 테두리로 Enter가 누를 단추를 보여 줌) · Esc·바깥 = 취소. danger = 빨간 단추(지우기), 아니면 코랄(되돌리기 등)
export function Confirm({ title, children, okLabel = '지우기', danger = true, onOk, onClose, testid, okTestid }) {
  const box = useRef(null), col = danger ? DANGER : ACCENT
  useEffect(() => { const key = e => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }; window.addEventListener('keydown', key, true); return () => window.removeEventListener('keydown', key, true) }, [onClose])
  const ring = c => ({ onFocus: e => { e.currentTarget.style.outline = `2px solid ${c}` }, onBlur: e => { e.currentTarget.style.outline = 'none' } })   // all: unset이 초점 테두리를 지움
  return <div style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onPointerDown={e => { e.stopPropagation(); if (e.target === e.currentTarget) onClose() }}>
    <div ref={box} data-testid={testid} onKeyDown={e => e.stopPropagation()} style={{ width: 320, display: 'flex', flexDirection: 'column', gap: 10, padding: 18, borderRadius: 12, background: C.card, border: `1px solid ${C.line}`, boxShadow: '0 8px 28px rgba(0,0,0,.25)', font: `400 13px ${F}`, color: C.ink }}>
      <div style={{ font: `700 15px ${F}` }}>{title}</div>
      {children && <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.55 }}>{children}</div>}
      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
        <button onClick={onClose} {...ring(col)} style={{ all: 'unset', cursor: 'pointer', padding: '5px 12px', borderRadius: 6, border: `1px solid ${C.line}`, outlineOffset: 2 }}>취소</button>
        <button data-testid={okTestid} autoFocus onClick={() => { onClose(); onOk() }} {...ring(col)} style={{ all: 'unset', cursor: 'pointer', padding: '5px 12px', borderRadius: 6, background: col, color: '#fff', fontWeight: 600, outline: `2px solid ${col}`, outlineOffset: 2 }}>{okLabel}</button>
      </div></div></div>
}
