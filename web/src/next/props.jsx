// 오른쪽 위 「속성」 카드(고를 때만) — 고른 것 모두의 선 색·굵기·선 모양·채움, 화살표 칸(종류·화살촉·머리 크기·모서리), 글자 크기·색.
// 데스크톱 `host_style._refresh_properties`와 같은 자리·같은 항목·같은 차례(종류 → 선 → 채움 → 화살표 → 글자). 섞어 고르면 해당하는 것에만.
// 첫 화면 규칙(CLAUDE.md): 폭 192, 제목 15px 굵게, 켜짐만 코랄.
import { useEffect, useState } from 'react'
import SYMBOLS from '../symbols.json' with { type: 'json' }
import { symbolPath } from './symbols.js'
import { FRAME_RATIOS, paperWH } from './geom.js'
// 프레임 비율 바꾸기 — 긴 쪽 방향은 그대로(가로로 길면 폭 유지, 세로로 길면 높이 유지)
const frameRatio = (it, ratio) => { const [x, y, w, h] = it.rect; if (!ratio) return { ratio: undefined }; const r = FRAME_RATIOS[ratio]; return { ratio, rect: w >= h ? [x, y, w, w / r] : [x, y, h / r, h] } }
import { cellPt, tableAutoPt } from './render.jsx'
// 글 있는 칸들의 지금 크기(pt)
const tableCellPts = it => { const out = []; for (let r = 0; r < it.rows; r++) for (let c = 0; c < it.cols; c++) if (it.cells?.[r]?.[c]) out.push(cellPt(it, r, c)); return out.length ? out : [tableAutoPt(it)] }
// 표 전체 크기를 안 정한 표의 ± = 칸마다 지금 크기에 각자 더함(값이 섞이면 각자 더하기 — 다른 도형과 같은 규칙, 2026-10-19 사용자: 10에서 시작해 「뻥」 커지던 것)
function stepTableCells(it, d) {
  const styles = { ...(it.cell_styles || {}) }
  for (let r = 0; r < it.rows; r++) for (let c = 0; c < it.cols; c++) if (it.cells?.[r]?.[c]) { const k = `${r},${c}`; styles[k] = { ...(styles[k] || {}), font: d ? stepClamp(cellPt(it, r, c), d, 1, 200, 1) : cellPt(it, r, c, true) } }   // d = 0 = 「자동」 끄기 — 지금 크기 그대로
  return { cell_styles: styles }
}
const hasFixedFont = it => it.type === 'table' && (it.font || Object.values(it.cell_styles || {}).some(s => s.font != null))
const clearTableFont = it => { const st = {}; for (const [k, v] of Object.entries(it.cell_styles || {})) { const { font, ...rest } = v; if (Object.keys(rest).length) st[k] = rest } return { font: undefined, cell_styles: Object.keys(st).length ? st : undefined } }

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)', on: '#da7756', onBg: 'var(--mb-onbg)' }   // 화면 색 = next.html CSS 변수
// 두 줄 꽉 채움(8+8) — 데스크톱 색 창과 같은 짜임: 진한 6색(`_COLOR_GRID_HUES`) + 검정 + 다른 색 / 같은 6색의 연한 색(Qt lighter(150)) + 회색 + 흰색
export const ARROW_COLORS = ['#FF3B30', '#FF9500', '#FFCC00', '#34C759', '#007AFF', '#AF52DE', '#000000', null,
  '#ffb4af', '#ffca7f', '#ffe57f', '#6eff93', '#7fbdff', '#e3acff', '#9e9e9e', '#ffffff']
// 채움 견본 — 데스크톱 `_DEFAULT_FILL_PRESETS`(첫 칸 없음, 나머지는 약 1/3 불투명이라 밝은·어두운 칠판과 흰 종이 모두에서 글이 읽힘)
const FILL_PRESETS = [null, '#555aa9ff', '#555fbf8a', '#55e8c15a', '#55e0646a', '#55b48cf2', '#55da7756', '#558a98a8']
const STYLES = [[1, '실선'], [2, '점선'], [3, '도트'], [4, '일점쇄선'], [5, '이점쇄선']]
const DASH = { 1: undefined, 2: '6 3', 3: '1.5 3', 4: '6 3 1.5 3', 5: '6 3 1.5 3 1.5 3' }
const INK = '#1f1f1f'

// ── 종류마다 무엇을 갖나(데스크톱 `_read_props`·`_text_targets`와 같은 판정, .ecad 칸 이름) ──
export const isArrow = it => it?.type === 'sarrow' || it?.type === 'arrow'
const PEN = new Set(['rect', 'ellipse', 'symbol', 'polygon', 'path', 'line'])
const lineKey = it => (isArrow(it) || it.type === 'badge' ? 'color' : PEN.has(it.type) || it.type === 'table' ? 'pen' : it.type === 'board' ? 'bg' : null)   // 표 선 색 = .ecad 표의 새 칸 pen(웹 먼저)   // 보드는 「바탕」 색
const hasWidth = it => isArrow(it) || PEN.has(it.type)
const fillKey = it => (['rect', 'ellipse', 'symbol'].includes(it.type) || (it.type === 'polygon' && it.closed) ? 'fill' : it.type === 'text' ? 'bg' : null)
const TYPE_NAMES = { rect: '사각형', ellipse: '원', line: '선', arrow: '화살표', sarrow: '화살표', text: '텍스트', badge: '번호', path: '펜', image: '이미지', table: '표', titleblock: '표제란', polygon: '다각형', board: '보드', frame: '프레임' }
const typeName = it => (it.type === 'symbol' ? SYMBOLS[it.kind]?.name || '심볼' : TYPE_NAMES[it.type] || '객체')

// 색 비교용 — '#ffrrggbb'(불투명 ARGB)와 '#rrggbb'를 같게
const norm = c => (c || '').replace(/^#ff(?=[0-9a-f]{6}$)/i, '#').toLowerCase()
// 채움 비교용 ARGB — 글 바탕(.ecad `bg`)은 [r,g,b,a] 배열(데스크톱 document.py), 도형 채움은 '#aarrggbb'
const hex2 = n => Math.round(n).toString(16).padStart(2, '0')
const fillArgb = v => (v == null ? null : Array.isArray(v) ? '#' + hex2(v[3]) + hex2(v[0]) + hex2(v[1]) + hex2(v[2]) : (v.length === 7 ? '#ff' + v.slice(1) : v).toLowerCase())
const argbToBg = c => (c == null ? null : [parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16), parseInt(c.slice(7, 9), 16), parseInt(c.slice(1, 3), 16)])
const argbCss = c => { if (!c) return 'transparent'; const a = parseInt(c.slice(1, 3), 16) / 255; return `rgba(${parseInt(c.slice(3, 5), 16)},${parseInt(c.slice(5, 7), 16)},${parseInt(c.slice(7, 9), 16)},${a.toFixed(3)})` }

// 글자 — 독립 글은 그 자신, 도형·선·화살표는 안에 붙은 글(라벨) 전부. → [{ font, color, text }]
const arrowLabels = it => it.labels || (it.label ? [it.label] : [])   // 옛 파일은 단수 label
function textSlots(it) {
  if (it.type === 'text') return [{ font: it.font || 12, color: it.color || INK, text: it.text || '' }]
  if (it.type === 'table') return [{ font: it.font || tableAutoPt(it), fonts: it.font ? null : tableCellPts(it), color: it.color || '#111111', text: (it.cells || []).flat().find(Boolean) || '' }]   // 표 글자 = 표 전체 하나. 크기를 표 전체로 안 정했으면 칸마다 지금 보이는 크기(자동 칸은 줄어든 실제 크기 — 범위로 보임)
  if (isArrow(it)) return arrowLabels(it).filter(L => L.text?.trim()).map(L => ({ font: L.font || 16, color: L.color || it.color || INK, text: L.text }))
  if (['rect', 'ellipse', 'symbol', 'polygon', 'line'].includes(it.type) && it.label?.text?.trim()) return [{ font: it.label.font || 16, color: it.label.color || it.pen || INK, text: it.label.text }]
  return []
}
// 그 글들에 f(글) → { font?, color? }를 입힌 아이템 고칠 값(없으면 null)
function patchTexts(it, f) {
  const slots = textSlots(it); if (!slots.length) return null
  if (it.type === 'text' || it.type === 'table') return f(slots[0])
  if (isArrow(it)) { let k = 0; return { labels: arrowLabels(it).map(L => (L.text?.trim() ? { ...L, ...f(slots[k++]) } : L)), label: undefined } }
  return { label: { ...it.label, ...f(slots[0]) } }
}

// 스타일 복사·붙여넣기(데스크톱 `_capture_paint_style`·`_apply_paint_style`) — 서식만(글 내용·라벨은 안 옮김), 종류가 달라도 있는 칸만 옮김
export function captureStyle(it) {
  const st = {}, lk = lineKey(it), fk = fillKey(it)
  if (lk) st.color = it[lk]
  if (it.type === 'text') { st.color = st.tcolor = it.color || INK; st.font = it.font || 12; st.bg = it.bg ?? null }   // 데스크톱: 글의 「색」 = 글자 색
  if (hasWidth(it)) { st.width = it.width ?? 1; st.style = it.style || 1 }
  if (fk) st.fill = fillArgb(it[fk])   // 채움 없음(null)도 서식 — 채움 되는 것끼리는 그대로 옮김
  if (isArrow(it)) { st.head = it.head !== false; st.head_start = !!it.head_start; st.head_scale = it.head_scale ?? 1 }
  return st
}
export function styleFor(it, st) {
  const p = {}, lk = lineKey(it)
  if (st.color != null) { if (lk) p[lk] = st.color; else if (it.type === 'text') p.color = st.color }
  if (hasWidth(it)) { if (st.width != null) p.width = st.width; if (st.style != null) p.style = st.style }
  if (fillKey(it) === 'fill' && 'fill' in st) p.fill = st.fill
  if (it.type === 'text') { if (st.font != null) p.font = st.font; if ('tcolor' in st) p.color = st.tcolor; if ('bg' in st) p.bg = st.bg }
  if (isArrow(it) && 'head' in st) Object.assign(p, { head: st.head, head_start: st.head_start, head_scale: st.head_scale })
  return Object.keys(p).length ? p : null
}

// 형광펜(데스크톱 `_text_highlight` — 글 전체, 모두 칠해져 있으면 지움). 독립 글과 도형·선 안 글만(화살표 라벨은 데스크톱도 뺌)
// .ecad runs = [시작, 길이, 색, 굵게, 바탕?] — 글자마다 풀었다가 바탕만 바꿔 다시 묶음
const HL = '#99ffd54f'
const hlHost = it => (it.type === 'text' ? (it.text ? it : null) : ['rect', 'ellipse', 'symbol', 'polygon', 'line'].includes(it.type) && it.label?.text?.trim() ? it.label : null)
const charAttrs = (text, runs) => { const a = Array.from({ length: text.length }, () => [null, false, null])
  for (const [st, len, c, b, g] of runs || []) for (let i = Math.max(0, st); i < Math.min(text.length, st + len); i++) a[i] = [c || null, !!b, g || null]
  return a }
const hasHl = h => { const a = charAttrs(h.text, h.runs); return [...h.text].every((ch, i) => ch === '\n' || !!a[i][2]) }
function runsWithBg(text, runs, bg) {
  const a = charAttrs(text, runs).map(([c, b]) => [c, b, bg]), out = []
  for (let i = 0; i < a.length;) { let j = i + 1; while (j < a.length && a[j].every((v, k) => v === a[i][k])) j++
    const [c, b, g] = a[i]; if (c || b || g) out.push([i, j - i, c, b, ...(g ? [g] : [])]); i = j }
  return out
}
const patchHl = (it, on) => { const h = hlHost(it); if (!h) return null; const runs = runsWithBg(h.text, h.runs, on ? HL : null)
  return it.type === 'text' ? { runs } : { label: { ...it.label, runs } } }

// 도형 바꾸기(데스크톱 `_fill_swap_menu` 기본도형 8종 — 「내 심볼」은 심볼 팔레트를 옮길 때). 같은 _id라 붙은 화살표·라벨·색은 그대로
const SWAP_KINDS = ['rect', 'ellipse', 'triangle', 'decision', 'terminal', 'data', 'prep', 'database']
const kindOf = it => (it.type === 'symbol' ? it.kind : it.type)
const swapPatch = k => (k === 'rect' || k === 'ellipse' ? { type: k, kind: undefined, cuts: undefined } : { type: 'symbol', kind: k, cuts: undefined })
const kindName = k => (k === 'rect' ? '사각형' : k === 'ellipse' ? '원' : SYMBOLS[k]?.name || k)
const shapeIcon = k => <svg width="22" height="14" viewBox="-1 -1 24 16" fill="none" stroke="currentColor" strokeWidth="1.3">
  {k === 'rect' ? <rect x="0" y="0" width="22" height="14" /> : k === 'ellipse' ? <ellipse cx="11" cy="7" rx="11" ry="7" /> : <path d={symbolPath(k, 22, 14).d} />}</svg>
// 회전 대상 — 회전 손잡이가 있는 것(데스크톱 `_is_rotatable`: 끝점으로 모양을 정하는 화살표·선·펜은 뺌)
const ROTATABLE = new Set(['rect', 'ellipse', 'symbol', 'image', 'table', 'board', 'polygon', 'text'])

// 아이콘(16×16, 선 굵기 1.6) — 글자 대신 뜻이 보이게
const Svg = ({ children, w = 18, h = 16 }) => <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
const tip = (x, y, a) => { const s = 4.5, r = d => (d * Math.PI) / 180; return `M${x + s * Math.cos(a + r(150))},${y + s * Math.sin(a + r(150))} L${x},${y} L${x + s * Math.cos(a - r(150))},${y + s * Math.sin(a - r(150))}` }
export const ICONS = {
  straight: <Svg><path d="M3 13 L15 3" /><path d={tip(15, 3, -0.69)} /></Svg>,
  curved: <Svg><path d="M3 13 Q4 4 15 4" /><path d={tip(15, 4, 0)} /></Svg>,
  ortho: <Svg><path d="M3 13 H9 V3 H15" /><path d={tip(15, 3, 0)} /></Svg>,
  none: <Svg><path d="M3 8 H15" /></Svg>,
  end: <Svg><path d="M3 8 H15" /><path d={tip(15, 8, 0)} /></Svg>,
  both: <Svg><path d="M3 8 H15" /><path d={tip(15, 8, 0)} /><path d={tip(3, 8, Math.PI)} /></Svg>,
  start: <Svg><path d="M3 8 H15" /><path d={tip(3, 8, Math.PI)} /></Svg>,
}
const dashIcon = st => <svg width="44" height="10"><line x1="2" y1="5" x2="42" y2="5" stroke="currentColor" strokeWidth="2" strokeDasharray={DASH[st]} strokeLinecap="round" /></svg>

const Row = ({ label, children }) => <div style={{ display: 'flex', alignItems: 'center', gap: 6, minHeight: 28 }}>
  <span style={{ width: 40, flex: 'none', color: C.muted, fontSize: 12 }}>{label}</span>{children}</div>
const btn = (on, extra) => ({ all: 'unset', boxSizing: 'border-box', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3, height: 26, borderRadius: 6,
  color: on ? C.on : C.ink, background: on ? C.onBg : 'transparent', outline: on ? `1px solid ${C.on}` : 'none', ...extra })
// 표 글자 「자동」 켜고 끄기(2026-10-19 사용자: 끄려고 크기를 일부러 바꿔야 했음) — 켜짐 = 칸에 맞춰 줄어듦, 끄면 지금 보이는 크기 그대로 고정
function AutoToggle({ on, onClick }) {
  return <button title={on ? '자동 — 칸에 맞춰 글자 크기가 바뀌어요. 누르면 지금 크기로 고정' : '고정 — 누르면 칸에 맞춰 자동으로'} onClick={onClick}
    style={btn(on, { padding: '0 6px', fontSize: 11, ...(on ? {} : { background: C.seg }) })}>자동</button>
}
// 여러 개 중 하나(켜진 것만 코랄)
function Seg({ items, value, onPick }) {
  return <div style={{ display: 'flex', gap: 2, background: C.seg, borderRadius: 8, padding: 2, flex: 1 }}>
    {items.map(([k, icon, name]) => <button key={k} title={name} aria-pressed={value === k} onClick={() => onPick(k)} style={btn(value === k, { flex: 1 })}>{icon}</button>)}
  </div>
}
// − 값 + (휠로도). 여러 개를 골라 값이 다르면 「1~3px」처럼 범위로 보이고, ±는 각자에 같은 만큼 더함(차이 유지 — 2026-10-18 사용자 선택)
// values = 고른 것들의 값, onStep(d) = 각자 d만큼(부르는 쪽이 범위 안으로 자름)
export const stepClamp = (v, d, min, max, step) => +(Math.round(Math.min(max, Math.max(min, v + d)) / step) * step).toFixed(6)   // 0.1 단위의 떠다니는 소수 자리(1.2000000000000002) 없앰
function Stepper({ values, step = 1, fmt = v => v, onStep, title }) {
  const lo = Math.min(...values), hi = Math.max(...values), mixed = hi - lo > 1e-9
  const text = mixed ? `${String(fmt(lo)).replace(/[^\d.]+$/, '')}~${fmt(hi)}` : fmt(lo)
  return <div title={mixed ? `${title} — 서로 다름(±는 각자에 더함)` : title} onWheel={e => onStep(e.deltaY < 0 ? step : -step)} style={{ display: 'flex', alignItems: 'center', background: C.seg, borderRadius: 8, padding: 2 }}>
    <button onClick={() => onStep(-step)} style={btn(false, { width: 22 })}>−</button>
    <span style={{ minWidth: 34, textAlign: 'center', fontVariantNumeric: 'tabular-nums', fontSize: 12, whiteSpace: 'nowrap', padding: '0 2px' }}>{text}</span>
    <button onClick={() => onStep(step)} style={btn(false, { width: 22 })}>+</button>
  </div>
}
// 색 견본 8+8(마지막 칸 = 다른 색). value = 지금 색(서로 다르면 '' — 아무것도 안 켬)
function ColorGrid({ value, onPick }) {   // onPick(색, 끌기 중이면 true — 되돌리기 한 칸으로 묶음)
  return <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 14px)', gap: 2 }}>
    {ARROW_COLORS.map((c, i) => { if (!c) return <label key={i} title="다른 색" style={{ width: 14, height: 14, borderRadius: 4, cursor: 'pointer', background: 'conic-gradient(#f33,#fc0,#3c6,#39f,#c3f,#f33)', position: 'relative', overflow: 'hidden' }}>
        <input type="color" value={/^#[0-9a-f]{6}$/.test(value) ? value : '#1f1f1f'} onChange={e => onPick(e.target.value, true)} style={{ opacity: 0, position: 'absolute', inset: 0, cursor: 'pointer' }} /></label>
      const on = value === c.toLowerCase()
      return <button key={i} title={c} aria-pressed={on} onClick={() => onPick(c)} style={{ all: 'unset', cursor: 'pointer', width: 14, height: 14, borderRadius: 4, background: c,
        boxShadow: on ? `0 0 0 2px #fff, 0 0 0 3.5px ${C.on}` : 'inset 0 0 0 1px rgba(0,0,0,.15)' }} /> })}
  </div>
}
// 채움 견본(없음 + 7) + 색 코드 칸(데스크톱 「#코드」 — Enter로 적용)
function FillGrid({ value, onPick }) {
  const [code, setCode] = useState('')
  const swatch = (c, on) => ({ all: 'unset', cursor: 'pointer', width: 14, height: 14, borderRadius: 4, position: 'relative', overflow: 'hidden',
    background: c ? `linear-gradient(${argbCss(c)},${argbCss(c)}), #fff` : '#fff',
    boxShadow: on ? `0 0 0 2px #fff, 0 0 0 3.5px ${C.on}` : 'inset 0 0 0 1px rgba(0,0,0,.2)' })
  const apply = () => { const m = /^#?([0-9a-f]{6}|[0-9a-f]{8})$/i.exec(code.trim()); if (!m) return; onPick(m[1].length === 6 ? '#ff' + m[1].toLowerCase() : '#' + m[1].toLowerCase()); setCode('') }
  return <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 14px)', gap: 2 }}>
      {FILL_PRESETS.map((c, i) => <button key={i} title={c ? c : '없음'} aria-pressed={value === c} onClick={() => onPick(c)} style={swatch(c, value === c)}>
        {!c && <svg width="14" height="14" style={{ position: 'absolute', inset: 0 }}><line x1="2" y1="12" x2="12" y2="2" stroke="#e02424" strokeWidth="1.4" /></svg>}</button>)}
    </div>
    <input value={code} placeholder="#코드" title="채움색 코드 — 예: #d9703f (Enter로 적용)" onChange={e => setCode(e.target.value)} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') apply() }}
      style={{ width: 84, height: 22, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: C.seg, color: C.ink, font: '12px monospace', padding: '0 6px' }} />
  </div>
}

// 회전 각도 — 쳐서 Enter(또는 칸을 벗어나면), 휠·↑↓는 1°씩. 서로 다르면 빈칸(쳐 넣으면 전부 그 각도 — 데스크톱과 같음)
function RotInput({ value, onSet }) {
  const [txt, setTxt] = useState(null), shown = txt ?? (value == null ? '' : String(value))
  const commit = v => { setTxt(null); const n = parseFloat(v); if (Number.isFinite(n)) onSet(((n % 360) + 360) % 360) }
  return <div style={{ display: 'flex', alignItems: 'center', gap: 4, background: C.seg, borderRadius: 8, padding: '2px 8px' }}>
    <input value={shown} placeholder="서로 다름" title="회전 각도" onChange={e => setTxt(e.target.value)} onBlur={e => txt != null && commit(e.target.value)}
      onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') commit(e.currentTarget.value); else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') { e.preventDefault(); commit((value ?? 0) + (e.key === 'ArrowUp' ? 1 : -1)) } }}
      onWheel={e => commit((value ?? 0) + (e.deltaY < 0 ? 1 : -1))}
      style={{ all: 'unset', width: 64, height: 22, fontSize: 12, fontVariantNumeric: 'tabular-nums', color: C.ink }} /><span style={{ color: C.muted, fontSize: 12 }}>°</span>
  </div>
}

// 글을 고치는 중 「글자」 카드(2026-10-18 사용자: 고칠 때도 속성이 보여야 — 칸 안 일부만 색 바꾸기) — 드래그한 부분에(없으면 그 자리부터) 굵게·색·형광펜.
// 누를 때 편집기 포커스·선택을 잃지 않게 mousedown 기본 동작을 막고, data-keep-edit로 편집이 안 끝나게 함. 크기는 .ecad 부분 서식에 없어 글 전체 단위(편집을 끝낸 뒤 속성 카드)
export function EditProps({ ed }) {
  const [, tick] = useState(0)
  useEffect(() => { const f = () => tick(n => n + 1); ed.on('selectionUpdate', f); ed.on('transaction', f); return () => { ed.off('selectionUpdate', f); ed.off('transaction', f) } }, [ed])
  const bold = ed.isActive('bold'), ts = ed.getAttributes('textStyle'), color = (ts.color || '').toLowerCase(), hl = !!ts.backgroundColor
  const run = f => f(ed.chain().focus()).run()
  return <div data-keep-edit onMouseDown={e => e.preventDefault()} onPointerDown={e => e.stopPropagation()} style={{ position: 'absolute', right: 12, top: 12, width: 192, boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10,
    padding: '8px 10px 10px', boxShadow: '0 2px 8px rgba(0,0,0,.06)', font: "400 13px 'Pretendard', sans-serif", color: C.ink, display: 'flex', flexDirection: 'column', gap: 4, userSelect: 'none', zIndex: 25 }}>
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}><span style={{ font: "700 15px 'Pretendard', sans-serif" }}>글자</span><span style={{ fontSize: 11, color: C.muted }}>드래그한 부분에</span></div>
    <Row label="굵게"><Seg value={bold} onPick={b => run(c => (b ? c.setBold() : c.unsetBold()))} items={[[true, <b key="b">굵게</b>, '굵게 (Ctrl+B)'], [false, <span key="n">보통</span>, '보통']]} /></Row>
    <Row label="색"><ColorGrid value={/^#[0-9a-f]{6}$/.test(color) ? color : ''} onPick={c => run(ch => ch.setColor(c))} /></Row>
    <Row label=""><button title="형광펜 — 다시 누르면 지워요" aria-pressed={hl} onClick={() => run(c => (hl ? c.unsetBackgroundColor() : c.setBackgroundColor('rgba(255,213,79,0.6)')))}
      style={btn(hl, { padding: '0 10px', background: hl ? C.onBg : C.seg, fontSize: 12, gap: 6 })}><span style={{ width: 14, height: 10, borderRadius: 2, background: 'rgba(255,213,79,.6)' }} />형광펜</button>
      <button title="색 되돌리기(기본 글 색)" onClick={() => run(c => c.unsetColor())} style={btn(false, { padding: '0 8px', background: C.seg, fontSize: 12 })}>기본 색</button></Row>
  </div>
}

// items = 고른 것 전부. set(아이템 → 고칠 값 | null, 이름, 묶음 열쇠) — 해당 없는 아이템은 null.
// kind = 고른 것이 모두 화살표이고 종류가 같으면 그것('straight'|'curved'|'ortho'), onKind(k) = 화살표 종류 바꾸기
// 값이 서로 다르면: 고르는 칸은 아무것도 안 켬(누르면 전부 그 값), 숫자 칸은 범위(데스크톱도 같은 규칙, 2026-10-18)
export function Props({ items, kind, set, onKind, rotate, library, onSwapTo, dark, cells, setCells }) {   // cells = 고른 표 칸 { table, r0, r1, c0, c1 }, setCells(꾸밈 → 고칠 값, 이름, 묶음)   // library = 내 심볼(서버 파일), onSwapTo(아이디들, 'customsym:<id>'|'rect'|'sym:<종류>')   // rotate(아이템, 각도) → 회전한 아이템(가운데 기준, Editor `rotateTo`)
  const [openDash, setOpenDash] = useState(false), [openSwap, setOpenSwap] = useState(false)
  const one = v => (v.length && v.every(x => x === v[0]) ? v[0] : null)
  const arrows = items.filter(isArrow), allArrows = arrows.length === items.length
  const lineItems = items.filter(lineKey), wItems = items.filter(hasWidth), fillItems = items.filter(fillKey)
  const texts = items.flatMap(textSlots)
  const boardsOnly = items.every(it => it.type === 'board'), allText = items.every(it => it.type === 'text')
  const showLine = lineItems.length > 0 && !allText   // 독립 글만 골랐으면 「선」 줄을 숨김(글 색은 「글자」에서)
  const types = new Set(items.map(typeName))
  const title = items.length === 1 ? typeName(items[0]) : types.size === 1 ? `${[...types][0]} ${items.length}개` : `${items.length}개 · 혼합`

  const color = one(lineItems.map(it => norm(it[lineKey(it)]))) ?? ''
  const style = one(wItems.map(it => it.style || 1))
  const fill = fillItems.length ? one(fillItems.map(it => fillArgb(it[fillKey(it)]))) : undefined   // null = 없음, undefined = 서로 다름
  const fillMixed = fillItems.length > 1 && !fillItems.every(it => fillArgb(it[fillKey(it)]) === fillArgb(fillItems[0][fillKey(fillItems[0])]))
  const head = one(arrows.map(a => (a.head !== false ? (a.head_start ? 'both' : 'end') : a.head_start ? 'start' : 'none')))
  const tColor = one(texts.map(t => norm(t.color))) ?? ''
  const swapOne = items.length === 1 && ['rect', 'ellipse', 'symbol'].includes(items[0].type) ? items[0] : null
  // 묶음 하나를 통째로 골랐으면(내 심볼에서 온 것 등) 그것도 바꿀 수 있음 — 기본 도형으로 돌아가기·다른 내 심볼로
  const swapGrp = !swapOne && items.length >= 2 && items[0].group_id && items.every(it => it.group_id === items[0].group_id && !isArrow(it)) ? items.map(it => it._id) : null
  const rotItems = items.filter(it => ROTATABLE.has(it.type)), rot = one(rotItems.map(it => +(it.rotation || 0).toFixed(1)))
  const hlItems = items.filter(hlHost), hlOn = hlItems.length > 0 && hlItems.every(it => hasHl(hlHost(it)))
  const firstText = (texts.find(t => t.text.trim())?.text.trim().split('\n')[0]) || ''
  // 숫자 칸 — 각자에 d만큼(범위 안으로)
  const num = (list, get, d0, min, max, step, name, write) => ({ values: list.map(it => get(it) ?? d0), step,
    onStep: d => { const ids = new Set(list.map(it => it._id)); set(it => (ids.has(it._id) ? write(it, stepClamp(get(it) ?? d0, d, min, max, step)) : null), name, name) } })
  const onArrows = f => it => (isArrow(it) ? f(it) : null)

  return <div onPointerDown={e => e.stopPropagation()} style={{ position: 'absolute', right: 12, top: 12, width: 192, boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10,
    padding: '8px 10px 10px', boxShadow: '0 2px 8px rgba(0,0,0,.06)', font: "400 13px 'Pretendard', sans-serif", color: C.ink, display: 'flex', flexDirection: 'column', gap: 4, userSelect: 'none', maxHeight: 'calc(100% - 180px)', overflowY: 'auto' }}>
    <div style={{ font: "700 15px 'Pretendard', sans-serif", marginBottom: 2 }}>속성</div>
    <Row label="종류">{allArrows
      ? <Seg value={kind} onPick={onKind} items={[['straight', ICONS.straight, '직선'], ['curved', ICONS.curved, '곡선'], ['ortho', ICONS.ortho, '직각']]} />
      : swapOne || swapGrp ? <div style={{ position: 'relative', flex: 1 }}>
        <button title="클릭: 다른 도형으로 바꾸기(크기·연결 유지)" onClick={() => setOpenSwap(o => !o)} style={btn(false, { width: '100%', background: C.seg, justifyContent: 'space-between', padding: '0 8px' })}>
          <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>{swapOne ? shapeIcon(kindOf(swapOne)) : null}<span data-testid="prop-type" style={{ fontSize: 13 }}>{swapOne ? title : `묶음 ${items.length}개`}</span></span><span style={{ color: C.muted }}>▾</span></button>
        {openSwap && <div style={{ position: 'absolute', zIndex: 3, top: 28, left: 0, right: 0, maxHeight: 360, overflowY: 'auto', background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, padding: 3, boxShadow: '0 4px 12px rgba(0,0,0,.1)' }}>
          {SWAP_KINDS.map(k => <button key={k} onClick={() => { if (swapGrp) onSwapTo(swapGrp, k === 'rect' || k === 'ellipse' ? k : 'sym:' + k); else if (k !== kindOf(swapOne)) set(it => (it._id === swapOne._id ? swapPatch(k) : null), '도형 바꾸기'); setOpenSwap(false) }}
            style={btn(!!swapOne && k === kindOf(swapOne), { width: '100%', justifyContent: 'flex-start', gap: 8, padding: '0 8px' })}>{shapeIcon(k)}<span style={{ fontSize: 12 }}>{kindName(k)}</span></button>)}
          {/* 내 심볼 — 폴더마다 구분선(데스크톱 `_fill_swap_menu`). 묶음으로 바뀌고 라벨은 안 옮김(여러 조각 중 어디에 둘지 애매 — 데스크톱과 같음) */}
          {(library?.folders || []).map(f => { const list = (library.symbols || []).filter(s => s.folder === f); if (!list.length) return null
            return <div key={f}><div style={{ borderTop: `1px solid ${C.line}`, margin: '3px 0', padding: '3px 8px 0', fontSize: 11, color: C.muted }}>{f}</div>
              {list.map(s => <button key={s.id} onClick={() => { onSwapTo(swapGrp || [swapOne._id], 'customsym:' + s.id); setOpenSwap(false) }} style={btn(false, { width: '100%', justifyContent: 'flex-start', gap: 8, padding: '0 8px' })}>
                <img alt="" src={'data:image/png;base64,' + s.thumb} width="20" height="20" style={{ filter: dark ? 'invert(1) hue-rotate(180deg)' : undefined }} />
                <span style={{ fontSize: 12, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{s.name}</span></button>)}</div> })}
        </div>}
      </div>
      : <span data-testid="prop-type" style={{ fontSize: 13 }}>{title}</span>}</Row>
    {allArrows && items.length > 1 && <div style={{ fontSize: 12, color: C.muted, margin: '-4px 0 0 46px' }}>화살표 {items.length}개</div>}
    {showLine && <Row label={boardsOnly ? '바탕' : '색'}><ColorGrid value={color} onPick={(c, drag) => set(it => (lineKey(it) ? { [lineKey(it)]: c } : null), boardsOnly ? '바탕 색' : '색', drag ? 'color' : null)} /></Row>}
    {showLine && wItems.length > 0 && <Row label="굵기"><div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Stepper title="선 굵기" {...num(wItems, it => it.width, 1, 1, 40, 1, '굵기', (it, v) => ({ width: v }))} fmt={v => v + 'px'} />
      {/* 자주 쓰는 굵기 — 섞였어도 전부 그 값(데스크톱 `_set_width_all`) */}
      <div style={{ display: 'flex', gap: 2 }}>{[1, 2, 3, 5].map(v => { const on = wItems.every(it => (it.width ?? 1) === v)
        return <button key={v} title={v + ' px'} aria-pressed={on} onClick={() => set(it => (hasWidth(it) ? { width: v } : null), '굵기')} style={btn(on, { width: 24, height: 22, background: on ? C.onBg : C.seg, fontSize: 12 })}>{v}</button> })}</div>
    </div></Row>}
    {showLine && wItems.length > 0 && <Row label="선"><div style={{ position: 'relative', flex: 1 }}>
      <button title="선 모양" onClick={() => setOpenDash(o => !o)} style={btn(false, { width: '100%', background: C.seg, justifyContent: 'space-between', padding: '0 8px' })}>{style ? dashIcon(style) : <span style={{ fontSize: 12, color: C.muted }}>서로 다름</span>}<span style={{ color: C.muted }}>▾</span></button>
      {openDash && <div style={{ position: 'absolute', zIndex: 2, top: 28, left: 0, right: 0, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, padding: 3, boxShadow: '0 4px 12px rgba(0,0,0,.1)' }}>
        {STYLES.map(([st, name]) => <button key={st} title={name} onClick={() => { set(it => (hasWidth(it) ? { style: st } : null), '선 모양'); setOpenDash(false) }} style={btn(style === st, { width: '100%', justifyContent: 'space-between', padding: '0 8px' })}>
          {dashIcon(st)}<span style={{ fontSize: 11, color: C.muted }}>{name}</span></button>)}
      </div>}
    </div></Row>}
    {fillItems.length > 0 && <Row label="채움"><FillGrid value={fillMixed ? undefined : fill} onPick={c => set(it => { const k = fillKey(it); return k ? { [k]: k === 'bg' ? argbToBg(c) : c } : null }, '채움')} /></Row>}
    {arrows.length > 0 && <>
      <Row label="화살촉"><Seg value={head} onPick={h => set(onArrows(() => ({ head: h === 'end' || h === 'both', head_start: h === 'start' || h === 'both' })), '화살촉')}
        items={[['none', ICONS.none, '없음'], ['end', ICONS.end, '끝만'], ['both', ICONS.both, '양쪽'], ['start', ICONS.start, '시작만']]} /></Row>
      <Row label="머리"><Stepper title="화살촉 크기 배율" {...num(arrows, a => a.head_scale, 1, 0.5, 3, 0.1, '머리 크기', (a, v) => ({ head_scale: v }))} fmt={v => v.toFixed(1) + '×'} /></Row>
      {kind === 'ortho' && <Row label="모서리"><Stepper title="꺾인 곳 둥글기(0 = 각짐)" {...num(arrows, a => a.curve_r, 10, 0, 40, 1, '모서리', (a, v) => ({ curve_r: v }))} /></Row>}
    </>}
    {items.some(it => it.type === 'rect') && <Row label="모서리"><Stepper title="네모 모서리 둥글기(0 = 각짐)" {...num(items.filter(it => it.type === 'rect'), it => it.radius, 0, 0, 60, 2, '모서리 둥글기', (it, v) => ({ radius: v || undefined }))} /></Row>}
    {items.length === 1 && items[0].type === 'frame' && (() => { const f = items[0]   // 프레임 — 이름·비율(순서는 좌하 「프레임」 카드, 틀만 옮기기는 이름표 옆 자물쇠·Alt+끌기)
      return <>
        <Row label="이름"><input key={f._id} defaultValue={f.name || ''} placeholder="예: 표지" onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') e.currentTarget.blur() }}
          onChange={e => set(() => ({ name: e.target.value }), '프레임 이름', 'fname')}
          style={{ flex: 1, minWidth: 0, height: 24, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 6px', font: 'inherit' }} /></Row>
        <Row label="비율"><Seg value={f.ratio || ''} onPick={r => set(it => frameRatio(it, r || null), '프레임 비율')}
          items={[['', <span key="f" style={{ fontSize: 11 }}>자유</span>, '자유'], ...['16:9', '4:3', 'A4', '1:1'].map(r => [r, <span key={r} style={{ fontSize: 11 }}>{r}</span>, r])]} /></Row>
      </> })()}
    {items.length > 0 && items.every(it => it.type === 'titleblock') && <>
      <Row label="용지"><Seg value={one(items.map(it => it.size))} onPick={s => set(it => ({ size: s }), '용지')} items={['A4', 'A3', 'A2', 'A1', 'A0'].map(s => [s, <span key={s} style={{ fontSize: 11 }}>{s}</span>, s])} /></Row>
      <Row label="방향"><Seg value={one(items.map(it => it.orient))} onPick={o => set(it => ({ orient: o }), '방향')} items={[['landscape', <span key="l">가로</span>, '가로'], ['portrait', <span key="p">세로</span>, '세로']]} /></Row>
      <Row label="크기"><Stepper title="틀 크기(배율) — 출력하면 이 틀이 종이 한 장에 꽉 차요" {...num(items, it => Math.round((it.scale || 1) * 100), 100, 5, 2000, 5, '틀 크기', (it, v) => ({ scale: v / 100 }))} fmt={x => x + '%'} />
        <button title="틀을 용지 실제 크기(1:1)로 — 가운데 그대로" onClick={() => set(it => { const k = it.scale || 1, [W, H] = paperWH(it.size, it.orient), cx = it.pos[0] + W * k / 2, cy = it.pos[1] + H * k / 2; return { scale: 1, pos: [cx - W / 2, cy - H / 2] } }, '1:1로')}
          style={btn(false, { padding: '0 6px', background: C.seg, fontSize: 11 })}>1:1로</button></Row>
    </>}
    {rotItems.length > 0 && <Row label="회전"><RotInput value={rot} onSet={a => set(it => (ROTATABLE.has(it.type) ? rotate(it, a) : null), '회전', '회전')} /></Row>}
    {cells && (() => {   // 고른 칸(들)의 꾸밈 — 표 전체 값 위에 덮음
      const { table: t, r0, r1, c0, c1 } = cells, list = []
      for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) list.push({ r, c, s: t.cell_styles?.[`${r},${c}`] || {} })
      const v = f => one(list.map(f)), n = list.length
      const fontV = list.map(e => cellPt(t, e.r, e.c)), auto = list.every(e => e.s.font == null && !t.font)
      return <>
        <div style={{ borderTop: `1px solid ${C.line}`, margin: '4px 0 0' }} />
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}><span style={{ fontWeight: 600 }}>칸</span><span style={{ fontSize: 11, color: C.muted }}>{n}개 · Shift+클릭으로 넓히기</span></div>
        <Row label="크기"><Stepper title="칸 글자 크기" values={fontV} onStep={d => setCells((s, r, c) => ({ font: stepClamp(cellPt(t, r, c), d, 1, 200, 1) }), '칸 글자 크기', 'cfont')} fmt={x => x + 'pt'} />
          <AutoToggle on={auto} onClick={() => (auto ? setCells((s, r, c) => ({ font: cellPt(t, r, c, true) }), '칸 글자 크기 고정') : setCells(() => ({ font: undefined }), '칸 글자 크기 자동'))} /></Row>
        <Row label="굵게"><Seg value={v(e => e.s.bold ?? !!(t.header && e.r === 0))} onPick={b => setCells(() => ({ bold: b }), '칸 굵게')} items={[[true, <b key="b">굵게</b>, '굵게'], [false, <span key="n">보통</span>, '보통']]} /></Row>
        <Row label="정렬"><Seg value={v(e => e.s.align || 'center')} onPick={a => setCells(() => ({ align: a === 'center' ? undefined : a }), '칸 정렬')}
          items={[['left', <span key="l">왼쪽</span>, '왼쪽'], ['center', <span key="c">가운데</span>, '가운데'], ['right', <span key="r">오른쪽</span>, '오른쪽']]} /></Row>
        <Row label="색"><ColorGrid value={norm(v(e => e.s.color ?? t.color ?? '#111111') || '')} onPick={(c, drag) => setCells(() => ({ color: c }), '칸 글자 색', drag ? 'ccolor' : null)} /></Row>
        <Row label="채움"><FillGrid value={v(e => fillArgb(e.s.fill) ?? null)} onPick={c => setCells(() => ({ fill: c || undefined }), '칸 채움')} /></Row>
      </>
    })()}
    {texts.length > 0 && !cells && <>
      <div style={{ borderTop: `1px solid ${C.line}`, margin: '4px 0 0' }} />
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}><span style={{ fontWeight: 600 }}>글자</span>
        {firstText && <span style={{ fontSize: 11, color: C.muted, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>「{firstText.slice(0, 10)}{firstText.length > 10 ? '…' : ''}」</span>}</div>
      <Row label="크기"><Stepper title="글자 크기" values={texts.flatMap(t => t.fonts || [t.font])} onStep={d => set(it => (it.type === 'table' && !it.font ? stepTableCells(it, d) : patchTexts(it, t => ({ font: stepClamp(t.font, d, 2, 200, 1) }))), '글자 크기', '글자 크기')} fmt={v => v + 'pt'} />
        {items.some(it => it.type === 'table') && (() => { const on = !items.some(hasFixedFont)
          return <AutoToggle on={on} onClick={() => set(it => (it.type !== 'table' ? null : on ? stepTableCells(it, 0) : clearTableFont(it)), on ? '글자 크기 고정' : '글자 크기 자동')} /> })()}</Row>
      <Row label="색"><ColorGrid value={tColor} onPick={(c, drag) => set(it => patchTexts(it, () => ({ color: c })), '글자 색', drag ? 'tcolor' : null)} /></Row>
      {items.some(it => it.type === 'table') && <Row label="첫 행">
        <Seg value={one(items.filter(it => it.type === 'table').map(it => !!it.header))} onPick={v => set(it => (it.type === 'table' ? { header: v } : null), '머리 행')} items={[[true, <b key="b">굵게</b>, '첫 행을 머리로(굵게)'], [false, <span key="n">보통</span>, '첫 행도 보통']]} />
      </Row>}
      {hlItems.length > 0 && <Row label=""><button title="형광펜 — 고른 글 전체. 다시 누르면 지워요" aria-pressed={hlOn} onClick={() => set(it => patchHl(it, !hlOn), '형광펜')}
        style={btn(hlOn, { padding: '0 10px', background: hlOn ? C.onBg : C.seg, fontSize: 12, gap: 6 })}><span style={{ width: 14, height: 10, borderRadius: 2, background: 'rgba(255,213,79,.6)' }} />형광펜</button></Row>}
    </>}
  </div>
}
