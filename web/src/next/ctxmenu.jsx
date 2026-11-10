// 제자리 우클릭 메뉴 — 데스크톱 `host_context._build_context_menu`와 같은 항목·차례(웹에 아직 없는 케이블 번호·심볼 등록·AI로 바꾸기·보드 색은 뺌).
// entries = [이름, 단축키, 할 일, 하위 목록?] | '-'(구분선). 하위 목록 = [이름, 할 일, 끔?] | '-'. 바깥 누르기·Esc로 닫힘.
// 웹의 하나뿐인 메뉴 부품(2026-11-02 디자인 규칙 ⑤). at.anchor = 메뉴를 연 ⋯ 단추 — 그 단추 누르기는 「바깥」으로 안 봄(단추가 다시 눌러 닫음, `ui.jsx` menuBelow)
// 글쇠(2026-11-10 0단계 점검): 열면 첫 줄로 초점 · ↑↓ Home End · → 하위 목록 열기 · ← 닫기 · Esc = 닫고 연 단추로 · Tab = 닫힘. 화면보다 길면 칸 안에서 굴림(200% 확대에서 4줄이 화면 밖이었음)
// — 그래서 하위 목록은 굴림 칸에 잘리지 않게 화면 기준(fixed)으로 띄움
import { useEffect, useRef, useState } from 'react'
import { keyLabel } from './keylabel.js'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)' }
const box = { position: 'absolute', zIndex: 30, pointerEvents: 'auto',minWidth: 190, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, padding: 4, boxShadow: 'var(--mb-shadow)', font: "400 12.5px 'Pretendard', sans-serif", color: C.ink,
  boxSizing: 'border-box', maxHeight: 'calc(100% - 8px)', overflowY: 'auto', overscrollBehavior: 'contain' }
const row = dis => ({ all: 'unset', boxSizing: 'border-box', display: 'flex', alignItems: 'center', gap: 12, width: '100%', padding: '5px 10px', borderRadius: 5, cursor: dis ? 'default' : 'pointer', opacity: dis ? 0.4 : 1 })
const Sep = () => <div role="separator" style={{ height: 1, background: C.line, margin: '4px 6px' }} />
const itemsOf = list => [...(list?.querySelectorAll(':scope > [role=menuitem], :scope > div > [role=menuitem]') || [])].filter(b => !b.disabled)

export function ContextMenu({ at, entries, onClose, testid, touch = false }) {   // touch = 휴대폰(글자 폭·줄 44px·글자 15px — 2026-11-06)
  const ref = useRef(null), subRef = useRef(null), [sub, setSub] = useState(null), [pos, setPos] = useState(at)   // sub = { i, r(그 줄 화면 자리), key(글쇠로 열었으면 첫 줄로) }
  useEffect(() => {   // 화면 밖으로 나가면 안쪽으로
    const el = ref.current, P = el?.parentElement; if (!el || !P) return
    const W = P.clientWidth, H = P.clientHeight, w = el.offsetWidth, h = el.offsetHeight
    setPos({ x: Math.max(4, Math.min(at.x, W - w - 4)), y: Math.max(4, Math.min(at.y, H - h - 4)) })
  }, [at])
  useEffect(() => {
    const down = e => { if (ref.current && !ref.current.contains(e.target) && !at.anchor?.contains(e.target)) onClose() }, key = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('pointerdown', down, true); window.addEventListener('keydown', key)
    return () => { window.removeEventListener('pointerdown', down, true); window.removeEventListener('keydown', key) }
  }, [onClose, at.anchor])
  useEffect(() => { itemsOf(ref.current)[0]?.focus({ preventScroll: true }) }, [])   // 열면 첫 줄로(마우스로 열었으면 초점 테두리는 안 뜸 — :focus-visible)
  useEffect(() => { if (sub?.key) itemsOf(subRef.current)[0]?.focus({ preventScroll: true }) }, [sub])
  // 펼친 하위 목록이 화면 밑·오른쪽을 넘으면 안쪽으로(2026-10-18 사용자: 아래쪽에서 잘림)
  const fitSub = el => {
    subRef.current = el; if (!el || !sub) return
    const r = el.getBoundingClientRect(), W = window.innerWidth, H = window.innerHeight
    if (r.bottom > H - 4) el.style.top = `${Math.max(4, H - 4 - r.height)}px`
    if (r.right > W - 4) el.style.left = `${Math.max(4, sub.r.left - 2 - r.width)}px`
  }
  const none = !entries.length   // 마우스 올림 = 회색(아래 hover — 규칙 ③)
  useEffect(() => { if (none) onClose() }, [none, onClose])   // 띄울 것이 없으면(빈 곳·붙일 것 없음) 바로 닫음 — 남아 있으면 나중에 복사했을 때 옛 자리에 뜸
  if (none) return null
  const hover = e => { e.currentTarget.style.background = 'var(--mb-group)' }, leave = e => { e.currentTarget.style.background = 'transparent' }
  const openSub = (i, el, key = false) => setSub({ i, r: el.getBoundingClientRect(), key })
  const back = () => { if (at.anchor?.isConnected) at.anchor.focus({ preventScroll: true }) }
  const onKey = e => {   // 메뉴 안 글쇠는 칠판으로 안 넘김(칠판이 ↑↓로 도형을 옮기지 않게) — Ctrl+K 같은 잡기 단계 글쇠는 그 전에 받음
    e.stopPropagation()
    const inSub = !!subRef.current?.contains(e.target), list = inSub ? subRef.current : ref.current, its = itemsOf(list), at0 = its.indexOf(e.target)
    const go = n => { e.preventDefault(); its[(n + its.length) % its.length]?.focus() }
    if (e.key === 'ArrowDown') go(at0 + 1)
    else if (e.key === 'ArrowUp') go(at0 < 0 ? its.length - 1 : at0 - 1)
    else if (e.key === 'Home') go(0)
    else if (e.key === 'End') go(its.length - 1)
    else if (e.key === 'ArrowRight' && !inSub && e.target.dataset.sub != null) { e.preventDefault(); openSub(+e.target.dataset.sub, e.target, true) }
    else if ((e.key === 'ArrowLeft' || e.key === 'Escape') && inSub) { e.preventDefault(); const i = sub?.i; setSub(null); ref.current?.querySelector(`[data-sub="${i}"]`)?.focus() }
    else if (e.key === 'Escape') { e.preventDefault(); onClose(); back() }
    else if (e.key === 'Tab') onClose()
  }
  return <div ref={ref} role="menu" data-testid={testid} onContextMenu={e => e.preventDefault()} onPointerDown={e => e.stopPropagation()} onKeyDown={onKey}
    style={{ ...box, ...(touch ? { minWidth: 0, padding: 6, borderRadius: 12, font: "400 15px 'Pretendard', sans-serif" } : {}), left: pos.x, top: pos.y }}>
    {entries.map((en, i) => en === '-' ? <Sep key={i} /> : (
      <div key={i} role="none" style={{ position: 'relative' }} onMouseEnter={e => (en[3] ? openSub(i, e.currentTarget) : setSub(null))}>
        <button role="menuitem" data-sub={en[3] ? i : undefined} aria-haspopup={en[3] ? 'menu' : undefined} aria-expanded={en[3] ? sub?.i === i : undefined}
          onClick={en[3] ? e => openSub(i, e.currentTarget.parentElement) : en[2]} onMouseEnter={hover} onMouseLeave={leave} style={{ ...row(false), ...(touch ? { minHeight: 44, padding: '0 14px 0 10px', borderRadius: 8 } : {}) }}>
          <span style={{ flex: 1, ...(touch ? { display: 'flex', alignItems: 'center', gap: 10, whiteSpace: 'nowrap' } : {}) }}>{en[0]}</span>
          {en[1] && <span style={{ color: C.muted, fontSize: 11 }}>{keyLabel(en[1])}</span>}
          {en[3] && <span aria-hidden="true" style={{ color: C.muted }}>▸</span>}
        </button>
        {en[3] && sub?.i === i && <div ref={fitSub} role="menu" aria-label={typeof en[0] === 'string' ? en[0] : undefined} style={{ ...box, position: 'fixed', zIndex: 71, left: sub.r.right + 2, top: sub.r.top - 4, maxHeight: 'calc(100vh - 8px)' }}>
          {en[3].map((s, j) => s === '-' ? <Sep key={j} /> : <button key={j} role="menuitem" disabled={!!s[2]} onClick={s[1]} onMouseEnter={s[2] ? undefined : hover} onMouseLeave={leave} style={row(s[2])}>{s[0]}</button>)}
        </div>}
      </div>))}
  </div>
}

// 왼쪽 판 줄(칠판·프레임)의 우클릭 메뉴 — 같은 메뉴를 화면 전체 기준으로 띄움(at = 마우스 clientX·Y, 판 밖으로 넘쳐도 안 잘림)
export const FloatMenu = props => <div style={{ position: 'fixed', inset: 0, zIndex: 40, pointerEvents: 'none' }}><ContextMenu {...props} /></div>
