// 글 꾸밈 버튼 한 줄 — 드래그 꾸미기 막대와 속성 카드 「글자」가 같이 씀(2026-10-23 사용자: 두 곳이 같은 항목이어야). 「꾸밈 지우기」는 뺌(같은 날 — 각 버튼을 다시 누르면 풀림)
// st = { bold, italic, underline, strike, code, hl } 지금 켜짐, act(이름) = 누름. color = 글자색 버튼(막대만 — 속성 카드는 색 칸 줄이 따로)
import { useEffect, useState } from 'react'

const C = { ink: 'var(--mb-ink)', line: 'var(--mb-line)' }
export const HL_CSS = 'rgba(255,213,79,0.6)'
export const FMT = [
  ['bold', '굵게 (Ctrl+B)', <b>B</b>],
  ['italic', '기울임 (Ctrl+I)', <i style={{ fontFamily: 'serif' }}>I</i>],
  ['underline', '밑줄 (Ctrl+U)', <u>U</u>],
  ['strike', '취소선 (Ctrl+Shift+X)', <s>S</s>],
  ['code', '코드 — 고정폭 글꼴', <span style={{ fontFamily: 'Consolas, monospace', fontSize: 12 }}>&lt;/&gt;</span>],
]
const fbtn = (on, title, label, onClick, testid, w = 24) => <button key={testid} title={title} aria-label={title.split(' ')[0]} aria-pressed={on || undefined} data-testid={testid} onClick={onClick}
  style={{ all: 'unset', cursor: 'pointer', minWidth: w, height: 26, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 5, fontSize: 13, color: C.ink, background: on ? 'rgba(218,119,86,.22)' : 'transparent' }}>{label}</button>
export function FmtButtons({ st, act, color, prefix = 'fmt', w = 24 }) {   // w = 버튼 폭(속성 카드는 좁아 20 — 한 줄에)
  const sep = <span style={{ width: 1, height: 18, background: C.line, margin: '0 2px', flex: 'none' }} />
  return <>
    {FMT.map(([k, t, l]) => fbtn(st[k], t, l, () => act(k), `${prefix}-${t.split(' ')[0]}`, w))}
    {sep}
    {color}
    {fbtn(st.hl, '형광펜 — 다시 누르면 지워요', <span style={{ width: 16, height: 12, borderRadius: 2, background: HL_CSS }} />, () => act('hl'), `${prefix}-형광펜`, w)}
  </>
}
// TipTap 편집기 — 지금 켜짐 · 누름. whole = 고른 글자가 없으면 글 전체에(속성 카드)
export const edState = ed => { const ts = ed.getAttributes('textStyle'); return { bold: ed.isActive('bold'), italic: ed.isActive('italic'), underline: ed.isActive('underline'), strike: ed.isActive('strike'), code: ed.isActive('code'), hl: !!ts.backgroundColor, color: (ts.color || '').toLowerCase() } }
export function edRun(ed, f, whole) {
  const { from, to, empty } = ed.state.selection
  if (whole && empty) { f(ed.chain().focus().selectAll()).setTextSelection({ from, to }).run(); return }   // 글 전체에 입히고 커서는 제자리
  f(ed.chain().focus()).run()
}
export const edAct = (ed, k, whole) => { const st = edState(ed)
  edRun(ed, c => (k === 'bold' ? c.toggleBold() : k === 'code' ? c.toggleCode() : k === 'hl' ? (st.hl ? c.unsetBackgroundColor() : c.setBackgroundColor(HL_CSS)) : c.toggleMark(k)), whole) }
// 편집기가 바뀔 때마다 다시 그림
export function useEdTick(ed) {
  const [, tick] = useState(0)
  useEffect(() => { if (!ed) return; const f = () => tick(n => n + 1); for (const e of ['selectionUpdate', 'transaction', 'blur', 'focus']) ed.on(e, f); return () => { for (const e of ['selectionUpdate', 'transaction', 'blur', 'focus']) ed.off(e, f) } }, [ed])
}
