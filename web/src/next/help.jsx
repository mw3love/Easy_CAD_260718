// 글쇠 도움말 카드(§8 항목61 다잡기, 2026-10-19) — keys.js 표를 그대로. F1·왼쪽 레일 「?」로 열고 Esc·F1·「?」·바깥 누르기로 닫음.
import { useEffect, useRef } from 'react'
import { KEY_TABLE } from './keys.js'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', group: 'var(--mb-group)' }

export function HelpCard({ onClose }) {
  const ref = useRef(null)
  useEffect(() => {
    const down = e => { if (ref.current && !ref.current.contains(e.target) && !e.target.closest?.('[data-help-btn]')) onClose() }   // 「?」는 제 손으로 닫음(여기서 닫으면 곧바로 다시 열림)
    const key = e => { if (e.key === 'Escape' || e.key === 'F1') { e.preventDefault(); e.stopImmediatePropagation(); onClose() } }
    window.addEventListener('pointerdown', down, true); window.addEventListener('keydown', key, true)
    return () => { window.removeEventListener('pointerdown', down, true); window.removeEventListener('keydown', key, true) }
  }, [onClose])
  return <div ref={ref} data-testid="help-card" role="dialog" aria-label="글쇠 도움말" style={{ position: 'absolute', zIndex: 40, left: '50%', top: 56, transform: 'translateX(-50%)', width: 'min(560px, calc(100% - 32px))',
    maxHeight: 'calc(100% - 80px)', overflowY: 'auto', boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: '14px 16px', boxShadow: '0 8px 24px rgba(0,0,0,.22)',
    font: "400 12.5px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 6 }}>
      <span style={{ font: "700 15px 'Pretendard', sans-serif", flex: 1 }}>글쇠 도움말</span>
      <span style={{ color: C.muted, fontSize: 11 }}>무엇을 골랐느냐에 따라 뜻이 바뀌어요 · Esc 닫기</span>
    </div>
    {KEY_TABLE.map(g => <div key={g.when} style={{ marginTop: 10 }}>
      <div style={{ fontWeight: 700, marginBottom: 4 }}>{g.when}</div>
      {g.rows.map(([k, v]) => <div key={k} style={{ display: 'flex', gap: 12, padding: '3px 0', borderTop: `1px solid ${C.line}` }}>
        <span style={{ width: 190, flex: 'none', color: C.muted, fontFamily: "'Pretendard', sans-serif", fontWeight: 600 }}>{k}</span><span>{v}</span></div>)}
    </div>)}
  </div>
}
