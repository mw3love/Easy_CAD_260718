// 제자리 우클릭 메뉴 — 데스크톱 `host_context._build_context_menu`와 같은 항목·차례(웹에 아직 없는 케이블 번호·심볼 등록·AI로 바꾸기·보드 색은 뺌).
// entries = [이름, 단축키, 할 일, 하위 목록?] | '-'(구분선). 하위 목록 = [이름, 할 일, 끔?] | '-'. 바깥 누르기·Esc로 닫힘.
import { useEffect, useRef, useState } from 'react'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)' }
const box = { position: 'absolute', zIndex: 30, minWidth: 190, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, padding: 4, boxShadow: '0 6px 18px rgba(0,0,0,.22)', font: "400 12.5px 'Pretendard', sans-serif", color: C.ink }
const row = dis => ({ all: 'unset', boxSizing: 'border-box', display: 'flex', alignItems: 'center', gap: 12, width: '100%', padding: '5px 10px', borderRadius: 5, cursor: dis ? 'default' : 'pointer', opacity: dis ? 0.4 : 1 })
const Sep = () => <div style={{ height: 1, background: C.line, margin: '4px 6px' }} />

export function ContextMenu({ at, entries, onClose }) {
  const ref = useRef(null), [sub, setSub] = useState(null), [pos, setPos] = useState(at)
  useEffect(() => {   // 화면 밖으로 나가면 안쪽으로
    const el = ref.current, P = el?.parentElement; if (!el || !P) return
    const W = P.clientWidth, H = P.clientHeight, w = el.offsetWidth, h = el.offsetHeight
    setPos({ x: Math.max(4, Math.min(at.x, W - w - 4)), y: Math.max(4, Math.min(at.y, H - h - 4)) })
  }, [at])
  useEffect(() => {
    const down = e => { if (ref.current && !ref.current.contains(e.target)) onClose() }, key = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('pointerdown', down, true); window.addEventListener('keydown', key)
    return () => { window.removeEventListener('pointerdown', down, true); window.removeEventListener('keydown', key) }
  }, [onClose])
  // 펼친 하위 목록이 화면 밑·오른쪽을 넘으면 안쪽으로(2026-10-18 사용자: 아래쪽에서 잘림)
  const fitSub = el => {
    const P = ref.current?.parentElement; if (!el || !P) return
    const pr = P.getBoundingClientRect(), r = el.getBoundingClientRect(), over = r.bottom - (pr.bottom - 4)
    if (over > 0) el.style.top = `${Math.max(-4 - over, pr.top + 4 - r.top - 4)}px`
    if (r.right > pr.right - 4) { el.style.left = 'auto'; el.style.right = '100%'; el.style.marginLeft = '0'; el.style.marginRight = '2px' }
  }
  if (!entries.length) return null
  const hover = e => { e.currentTarget.style.background = 'rgba(218,119,86,.14)' }, leave = e => { e.currentTarget.style.background = 'transparent' }
  return <div ref={ref} onContextMenu={e => e.preventDefault()} onPointerDown={e => e.stopPropagation()} style={{ ...box, left: pos.x, top: pos.y }}>
    {entries.map((en, i) => en === '-' ? <Sep key={i} /> : (
      <div key={i} style={{ position: 'relative' }} onMouseEnter={() => setSub(en[3] ? i : null)}>
        <button onClick={en[3] ? () => setSub(i) : en[2]} onMouseEnter={hover} onMouseLeave={leave} style={row(false)}>
          <span style={{ flex: 1 }}>{en[0]}</span>
          {en[1] && <span style={{ color: C.muted, fontSize: 11 }}>{en[1]}</span>}
          {en[3] && <span style={{ color: C.muted }}>▸</span>}
        </button>
        {en[3] && sub === i && <div ref={fitSub} style={{ ...box, left: '100%', top: -4, marginLeft: 2 }}>
          {en[3].map((s, j) => s === '-' ? <Sep key={j} /> : <button key={j} disabled={!!s[2]} onClick={s[1]} onMouseEnter={s[2] ? undefined : hover} onMouseLeave={leave} style={row(s[2])}>{s[0]}</button>)}
        </div>}
      </div>))}
  </div>
}
