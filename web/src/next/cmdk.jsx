// 명령 찾기(Ctrl+K, 2026-11-08 — RustGIS 「명령 검색」에서 얻은 생각): 위 막대·왼쪽 판·우클릭에 흩어진 기능을 이름·초성으로 찾아 바로 실행.
// 명령 목록은 main.jsx `commandList`가 만들고, 고른 물건에 대한 명령은 우클릭 메뉴(Editor `menuEntries`)를 그대로 펴서 씀 — 이름이 둘로 갈라지지 않게.
// 줄 = { name, group, keys?, words?(이름에 없는 찾는 말), run }. ↑↓ 고르기 · Enter·누르기 = 실행 · Esc·바깥·Ctrl+K = 닫기.
import { useEffect, useRef, useState } from 'react'
import { nameMatch } from './palette.jsx'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', group: 'var(--mb-group)' }
const squeeze = s => s.replace(/\s+/g, '').toLowerCase()   // 「새칠판」으로 쳐도 「새 칠판」이 찾아지게

// 찾는 차례 = 이름이 그 말로 시작 → 이름에 들어 있음 → 초성 → 찾는 말(words). 같은 차례 안에선 목록 순서 그대로
export function rankCommands(list, q) {
  const k = squeeze(q); if (!k) return list
  const score = c => { const n = squeeze(c.name); if (n.startsWith(k)) return 0; if (n.includes(k)) return 1; if (nameMatch(n, k)) return 2; return (c.words || []).some(w => nameMatch(squeeze(w), k)) ? 3 : -1 }
  return list.map((c, i) => ({ c, i, s: score(c) })).filter(r => r.s >= 0).sort((a, b) => a.s - b.s || a.i - b.i).map(r => r.c)
}

// 우클릭 메뉴 항목([이름, 글쇠, 할 일, 하위?] | '-', 하위 = [이름, 할 일, 끔?] | '-') → 명령 줄. 끈 항목은 뺌
export function menuToCommands(entries, group) {
  const out = []
  for (const e of entries) {
    if (e === '-') continue
    const [name, keys, run, sub] = e
    if (sub) { for (const s of sub) if (s !== '-' && !s[2]) out.push({ name: `${name} › ${s[0]}`, group, run: s[1] }) } else if (run) out.push({ name, group, keys, run })
  }
  return out
}

export function CommandBar({ getCommands, onClose }) {
  const [all] = useState(getCommands), [q, setQ] = useState(''), [at, setAt] = useState(0)   // 목록은 열 때 한 번(그때 고른 것 기준)
  const box = useRef(null), inp = useRef(null), on = useRef(null)
  useEffect(() => { inp.current?.focus() }, [])
  useEffect(() => { const down = e => { if (box.current && !box.current.contains(e.target) && !e.target.closest?.('[data-cmd-btn]')) onClose() }; window.addEventListener('pointerdown', down, true); return () => window.removeEventListener('pointerdown', down, true) }, [onClose])
  const rows = rankCommands(all, q)
  const cur = Math.min(at, Math.max(0, rows.length - 1))
  useEffect(() => { on.current?.scrollIntoView({ block: 'nearest' }) }, [cur, q])
  const run = c => { if (!c) return; onClose(); c.run() }
  const key = e => {
    e.stopPropagation()
    if (e.key === 'Escape') { e.preventDefault(); onClose() }
    else if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); run(rows[cur]) }
    else if (e.key === 'ArrowDown' && rows.length) { e.preventDefault(); setAt((cur + 1) % rows.length) }
    else if (e.key === 'ArrowUp' && rows.length) { e.preventDefault(); setAt((cur - 1 + rows.length) % rows.length) }
  }
  return <div ref={box} data-testid="cmd-bar" role="dialog" aria-label="명령 찾기" onPointerDown={e => e.stopPropagation()} style={{ position: 'absolute', zIndex: 45, left: '50%', top: 12, transform: 'translateX(-50%)', width: 'min(480px, calc(100% - 32px))',
    background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, boxShadow: 'var(--mb-shadow)', font: "400 12.5px 'Pretendard', sans-serif", color: C.ink, overflow: 'hidden' }}>
    <div style={{ padding: '8px 12px', borderBottom: `1px solid ${C.line}` }}>
      <input ref={inp} value={q} onChange={e => { setQ(e.target.value); setAt(0) }} onKeyDown={key} placeholder="명령 찾기 — 이름이나 초성으로 (↑↓ · Enter · Esc)"
        style={{ width: '100%', boxSizing: 'border-box', border: 'none', outline: 'none', background: 'transparent', color: C.ink, font: "400 13.5px 'Pretendard', sans-serif" }} />
    </div>
    {rows.length > 0 ? <div style={{ maxHeight: 340, overflowY: 'auto', padding: 4 }}>
      {rows.map((c, i) => <button key={c.id || `${c.group}/${c.name}`} ref={i === cur ? on : null} data-testid="cmd-row" aria-selected={i === cur} onClick={() => run(c)} onMouseMove={() => { if (i !== cur) setAt(i) }}
        style={{ all: 'unset', boxSizing: 'border-box', width: '100%', display: 'flex', gap: 10, alignItems: 'baseline', padding: '5px 8px', borderRadius: 6, cursor: 'pointer', background: i === cur ? C.group : 'transparent' }}>
        <span style={{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</span>
        {c.keys && <span style={{ flex: 'none', fontSize: 11, color: C.muted }}>{c.keys}</span>}
        <span style={{ flex: 'none', width: 44, textAlign: 'right', fontSize: 11, color: C.muted }}>{c.group}</span>
      </button>)}
    </div> : <div style={{ padding: '10px 12px', color: C.muted }}>그런 명령이 없어요</div>}
  </div>
}
