// 글쇠 도움말 카드(§8 항목61 다잡기, 2026-10-19) — keys.js 표를 그대로. F1·왼쪽 아래 되돌리기 섬 「?」로 열고 Esc·F1·「?」·바깥 누르기로 닫음.
import { useEffect, useRef, useState } from 'react'
import { KEY_TABLE } from './keys.js'
import { keyLabel } from './keylabel.js'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', group: 'var(--mb-group)' }

export function HelpCard({ onClose }) {
  const ref = useRef(null), [back] = useState(() => document.activeElement)
  useEffect(() => { ref.current?.focus({ preventScroll: true }); return () => { if (back?.isConnected) back.focus({ preventScroll: true }) } }, [])   // 열면 카드로, 닫으면 연 자리로(2026-11-10 2단계 — Tab 46번 만에 닿았음)
  useEffect(() => {
    const down = e => { if (ref.current && !ref.current.contains(e.target) && !e.target.closest?.('[data-help-btn]')) onClose() }   // 「?」는 제 손으로 닫음(여기서 닫으면 곧바로 다시 열림)
    const key = e => { if (e.key === 'Escape' || e.key === 'F1') { e.preventDefault(); e.stopImmediatePropagation(); onClose() } }
    window.addEventListener('pointerdown', down, true); window.addEventListener('keydown', key, true)
    return () => { window.removeEventListener('pointerdown', down, true); window.removeEventListener('keydown', key, true) }
  }, [onClose])
  return <div ref={ref} tabIndex={-1} data-testid="help-card" role="dialog" aria-label="글쇠 도움말" style={{ outline: 'none', position: 'absolute', zIndex: 40, left: '50%', top: 'var(--mb-top, 60px)', transform: 'translateX(-50%)', width: 'min(560px, calc(100% - 32px))',
    maxHeight: 'calc(100% - 80px)', overflowY: 'auto', boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: '14px 16px', boxShadow: 'var(--mb-shadow)',
    font: "400 12.5px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', columnGap: 8, marginBottom: 6 }}>
      <span style={{ font: "700 15px 'Pretendard', sans-serif", flex: '1 0 auto' }}>글쇠 도움말</span>
      <span style={{ color: C.muted, fontSize: 11 }}>무엇을 골랐느냐에 따라 뜻이 바뀌어요 · Esc 닫기</span>
    </div>
    {KEY_TABLE.map(g => <div key={g.when} style={{ marginTop: 10 }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{g.when}</div>
      {g.rows.map(([k, v]) => <div key={k} style={{ display: 'flex', flexWrap: 'wrap', columnGap: 12, padding: '3px 0', borderTop: `1px solid ${C.line}` }}>   {/* 좁으면 설명이 글쇠 밑으로(2026-11-10 2단계 — 320에서 한 글자씩 꺾였음) */}
        <span style={{ flex: '0 0 190px', maxWidth: '100%', color: C.muted, fontFamily: "'Pretendard', sans-serif", fontWeight: 600 }}>{keyLabel(k)}</span><span style={{ flex: '1 1 160px', minWidth: 0 }}>{keyLabel(v)}</span></div>)}
    </div>)}
  </div>
}
