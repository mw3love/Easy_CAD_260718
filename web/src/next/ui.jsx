// 웹 화면 공용 부품(2026-11-02 — 웹 디자인 규칙 `docs/web_ui_rules.md`): 단추 모양·마우스 올림·확인 창을 판마다 따로 짜지 않게 한곳에.
// 메뉴는 `ctxmenu.jsx`(ContextMenu·FloatMenu)가 하나뿐인 메뉴 부품이다.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)' }
export const ACCENT = 'var(--mb-accent)', DANGER = '#d44c47', HOVER = 'var(--mb-group)'
const F = "'Pretendard', sans-serif"

// 휴대폰 = 손가락 기기 + 짧은 변이 700 미만(2026-10-27 저녁 사용자 — 폭만 보면 PC 창을 반으로 나눴을 때도 고치기가 막혔음).
// 짧은 변으로(2026-11-06 휴대폰 점검 — 폭만 보면 휴대폰을 가로로 돌렸을 때(폭 750) PC 화면이 됐음). 태블릿(짧은 변 700 이상)은 PC 화면 + 손가락 이동·확대(Editor)
export const PHONE_W = 700
export const isPhone = () => Math.min(window.innerWidth, window.innerHeight) < PHONE_W && !!window.matchMedia?.('(pointer: coarse)').matches
// 휴대폰 = 브라우저가 화면 전체를 그림처럼 키우지 않게(2026-10-27 사용자: 확대하면 뭉개짐 — 칠판 밖(위·아래 막대·대화창)을 벌리면 브라우저 확대가 됐음, 아이폰 Safari는 칠판의 touch-action도 무시)
// 확대는 칠판 두 손가락(Editor)만 — 글자를 다시 그려 또렷함. 칠판 화면·보기 링크 화면이 같이 씀
export function usePhoneViewport(phone) {
  useEffect(() => { if (!phone) return; const meta = document.querySelector('meta[name=viewport]'), old = meta?.content
    meta?.setAttribute('content', 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no')
    const stop = e => e.preventDefault(); document.addEventListener('gesturestart', stop); document.addEventListener('gesturechange', stop)   // 아이폰 Safari 확대 몸짓
    return () => { if (old) meta.setAttribute('content', old); document.removeEventListener('gesturestart', stop); document.removeEventListener('gesturechange', stop) } }, [phone])
}

// 규칙 ③ 마우스 올림 = 회색 바탕(뜻 있는 「켜짐」만 코랄)
export const hoverBg = { onMouseEnter: e => { e.currentTarget.style.background = HOVER }, onMouseLeave: e => { e.currentTarget.style.background = 'transparent' } }

// 규칙 A1 — 코랄 채움 = 판마다 대표 행동 하나. 그 밖은 회색 테두리
export const btnPrimary = { all: 'unset', cursor: 'pointer', padding: '3px 10px', borderRadius: 6, background: ACCENT, color: '#fff', font: `600 12px ${F}` }
export const btnSecondary = { all: 'unset', cursor: 'pointer', padding: '3px 10px', borderRadius: 6, border: `1px solid ${C.line}`, color: C.ink, font: `500 12px ${F}` }
// 규칙 B1 — 머리줄 오른쪽 작은 단추(「＋ 새 폴더」·「＋ 새 레이어」)
export const btnHead = { all: 'unset', cursor: 'pointer', padding: '1px 6px', borderRadius: 4, border: `1px solid ${C.line}`, color: C.ink, font: `500 11px ${F}`, whiteSpace: 'nowrap' }
// 규칙 ④ — ⋯: 머리줄은 늘 보이고 테두리 없음, 줄은 마우스를 올렸을 때만(`show`)
// 누르는 자리 24×24(WCAG 2.5.8) = 겉모양 18 그대로, 둘레 3px을 `.mb-hit`(index.html)이 넓힘(2026-11-09 점검)
export const moreBtn = show => ({ all: 'unset', position: 'relative', '--hit': '-3px', cursor: 'pointer', flex: 'none', width: 18, textAlign: 'center', borderRadius: 4, color: C.muted, fontWeight: 700, lineHeight: '18px', visibility: show ? 'visible' : 'hidden' })

// ⋯ 단추 아래에 메뉴 띄우기 — 같은 단추를 다시 누르면 닫힘(ContextMenu `anchor`가 그 단추 누르기를 「바깥」으로 안 봄)
export const menuBelow = (e, extra = {}) => { const r = e.currentTarget.getBoundingClientRect(); return { x: r.left, y: r.bottom + 2, anchor: e.currentTarget, ...extra } }

// 규칙 ⑥ — 되돌릴 수 없는 지우기만 묻는 앱 안 확인 창(브라우저 confirm은 칠판 조작을 막음).
// Enter = 확인(초점 테두리로 Enter가 누를 단추를 보여 줌) · Esc·바깥 = 취소. danger = 빨간 단추(지우기), 아니면 코랄(되돌리기 등)
// <dialog> 열고 닫기(2026-11-09 — 확인 창·그림 크게 보기): 열면 showModal + 처음 초점(focus), 닫히면 초점이 연 자리로. 지울 때 정리는 창이 아직 떠 있을 때 돌아서(뒤가 막혀 초점이 안 감) 먼저 close
// 숨은 ⋯(마우스 올림 때만)처럼 초점을 못 받으면 그 줄(tabindex 있는 부모)로
export function useModalDialog(dlg, returnTo, focus) {
  const [back] = useState(() => returnTo || document.activeElement)
  useLayoutEffect(() => { const d = dlg.current; if (!d.open) d.showModal(); focus?.(d)
    return () => { if (d.open) d.close(); if (!back?.isConnected) return
      back.focus?.(); if (document.activeElement !== back) back.parentElement?.closest('[tabindex]')?.focus() } }, [])   // eslint-disable-line react-hooks/exhaustive-deps
}

// 진짜 창(<dialog> + showModal, 2026-11-09 better-interface 점검 — 그냥 div라 화면 읽기 프로그램이 창인 줄 몰랐고 Tab이 창 밖 칠판으로 나갔음):
// 뒤는 못 누르고 Tab은 창 안에서만, 닫으면 초점이 연 자리로 돌아감
export function Confirm({ title, children, okLabel = '지우기', danger = true, onOk, onClose, testid, okTestid, returnTo }) {   // returnTo = 닫으면 초점을 줄 곳(창을 연 메뉴 항목은 이미 사라졌을 때 — 메뉴를 연 ⋯)
  const box = useRef(null), dlg = useRef(null), okRef = useRef(null), col = danger ? DANGER : ACCENT
  useModalDialog(dlg, returnTo, () => okRef.current?.focus())
  useEffect(() => { const key = e => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }; window.addEventListener('keydown', key, true); return () => window.removeEventListener('keydown', key, true) }, [onClose])
  const ring = c => ({ onFocus: e => { e.currentTarget.style.outline = `2px solid ${c}` }, onBlur: e => { e.currentTarget.style.outline = 'none' } })   // all: unset이 초점 테두리를 지움
  return <dialog ref={dlg} className="mb-dlg" aria-labelledby="mb-confirm-title" onCancel={e => e.preventDefault() /* Esc는 위 글쇠 듣기가 닫음 */}
    style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', maxWidth: 'none', maxHeight: 'none', margin: 0, padding: 0, border: 0, zIndex: 60, background: 'rgba(0,0,0,.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onPointerDown={e => { e.stopPropagation(); if (e.target === e.currentTarget) onClose() }}>
    <div ref={box} data-testid={testid} onKeyDown={e => e.stopPropagation()} style={{ width: 320, display: 'flex', flexDirection: 'column', gap: 10, padding: 18, borderRadius: 12, background: C.card, border: `1px solid ${C.line}`, boxShadow: '0 8px 28px rgba(0,0,0,.25)', font: `400 13px ${F}`, color: C.ink }}>
      <div id="mb-confirm-title" style={{ font: `700 15px ${F}` }}>{title}</div>
      {children && <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.55 }}>{children}</div>}
      <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
        <button data-own-ring onClick={onClose} {...ring(col)} style={{ all: 'unset', cursor: 'pointer', padding: '5px 12px', borderRadius: 6, border: `1px solid ${C.line}`, outlineOffset: 2 }}>취소</button>
        <button ref={okRef} data-own-ring data-testid={okTestid} onClick={() => { onClose(); onOk() }} {...ring(col)} style={{ all: 'unset', cursor: 'pointer', padding: '5px 12px', borderRadius: 6, background: col, color: '#fff', fontWeight: 600, outline: `2px solid ${col}`, outlineOffset: 2 }}>{okLabel}</button>
      </div></div></dialog>
}
