// 오른쪽 위 「속성」 카드(고를 때만) — 고른 것 모두의 선 색·굵기·선 모양·채움, 화살표 칸(종류·화살촉·머리 크기·모서리), 글자 크기·색.
// 데스크톱 `host_style._refresh_properties`와 같은 자리·같은 항목·같은 차례(종류 → 선 → 채움 → 화살표 → 글자). 섞어 고르면 해당하는 것에만.
// 첫 화면 규칙(CLAUDE.md): 폭 192, 제목 15px 굵게, 켜짐만 코랄.
import { useEffect, useState } from 'react'
import { ColorChip } from './colorpop.jsx'
import { FmtButtons, edAct, edRun, edState, useEdTick } from './textfmt.jsx'
import { FoldBtn, useFold } from './fold.jsx'
import SYMBOLS from '../symbols.json' with { type: 'json' }
import { shapeIcon as paletteIcon } from './palette.jsx'
import { FRAME_RATIOS, paperWH } from './geom.js'
// 프레임 비율 바꾸기 — 긴 쪽 방향은 그대로(가로로 길면 폭 유지, 세로로 길면 높이 유지)
const frameRatio = (it, ratio) => { const [x, y, w, h] = it.rect; if (!ratio) return { ratio: undefined }; const r = FRAME_RATIOS[ratio]; return { ratio, rect: w >= h ? [x, y, w, w / r] : [x, y, h / r, h] } }
import { cellPt, labelNeedW, labelShownPt, tableAutoPt } from './render.jsx'
import { WEB_ZOOMS } from './webcard.js'
import { STYLE_NAMES, rowName } from './legend.js'
const LG_WIDTHS = [0.5, 1, 1.5, 2, 3, 4, 5, 6, 8]
// 글 있는 칸들의 지금 크기(pt)
const tableCellPts = it => { const out = []; for (let r = 0; r < it.rows; r++) for (let c = 0; c < it.cols; c++) if (it.cells?.[r]?.[c]) out.push(cellPt(it, r, c)); return out.length ? out : [tableAutoPt(it)] }
// 표 전체 크기를 안 정한 표의 ± = 칸마다 지금 크기에 각자 더함(값이 섞이면 각자 더하기 — 다른 도형과 같은 규칙, 2026-10-18 사용자: 10에서 시작해 「뻥」 커지던 것)
function stepTableCells(it, d) {
  const styles = { ...(it.cell_styles || {}) }
  for (let r = 0; r < it.rows; r++) for (let c = 0; c < it.cols; c++) if (it.cells?.[r]?.[c]) { const k = `${r},${c}`; styles[k] = { ...(styles[k] || {}), font: d ? stepClamp(cellPt(it, r, c), d, 1, 200, 1) : cellPt(it, r, c, true) } }   // d = 0 = 「자동」 끄기 — 지금 크기 그대로
  return { cell_styles: styles }
}
const hasFixedFont = it => it.type === 'table' && (it.font || Object.values(it.cell_styles || {}).some(s => s.font != null))
const clearTableFont = it => { const st = {}; for (const [k, v] of Object.entries(it.cell_styles || {})) { const { font, ...rest } = v; if (Object.keys(rest).length) st[k] = rest } return { font: undefined, cell_styles: Object.keys(st).length ? st : undefined } }

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)', on: '#da7756', onBg: 'var(--mb-onbg)' }   // 화면 색 = next.html CSS 변수
const STYLES = [[1, '실선'], [2, '점선'], [3, '도트'], [4, '일점쇄선'], [5, '이점쇄선']]
const DASH = { 1: undefined, 2: '6 3', 3: '1.5 3', 4: '6 3 1.5 3', 5: '6 3 1.5 3 1.5 3' }
const INK = '#1f1f1f'

// ── 종류마다 무엇을 갖나(데스크톱 `_read_props`·`_text_targets`와 같은 판정, .ecad 칸 이름) ──
export const isArrow = it => it?.type === 'sarrow' || it?.type === 'arrow'
const PEN = new Set(['rect', 'ellipse', 'symbol', 'polygon', 'path', 'line'])
const lineKey = it => (isArrow(it) || it.type === 'badge' ? 'color' : PEN.has(it.type) || it.type === 'table' ? 'pen' : it.type === 'board' ? 'bg' : null)   // 표 선 색 = .ecad 표의 새 칸 pen(웹 먼저)   // 보드는 「바탕」 색
const hasWidth = it => isArrow(it) || PEN.has(it.type)
const fillKey = it => (['rect', 'ellipse', 'symbol', 'memo'].includes(it.type) || (it.type === 'polygon' && it.closed) ? 'fill' : it.type === 'text' ? 'bg' : null)
const TYPE_NAMES = { doc: '정리 문서', rect: '사각형', ellipse: '원', line: '선', arrow: '화살표', sarrow: '화살표', text: '텍스트', badge: '번호', path: '펜', image: '이미지', table: '표', titleblock: '표제란', polygon: '다각형', board: '보드', frame: '프레임', web: '웹 카드', pdf: 'PDF', memo: '메모', legend: '범례' }
const typeName = it => (it.type === 'symbol' ? SYMBOLS[it.kind]?.name || '심볼' : TYPE_NAMES[it.type] || '객체')

// 색 비교용 — '#ffrrggbb'(불투명 ARGB)와 '#rrggbb'를 같게
const norm = c => (c || '').replace(/^#ff(?=[0-9a-f]{6}$)/i, '#').toLowerCase()
// 채움 비교용 ARGB — 글 바탕(.ecad `bg`)은 [r,g,b,a] 배열(데스크톱 document.py), 도형 채움은 '#aarrggbb'
const hex2 = n => Math.round(n).toString(16).padStart(2, '0')
const fillArgb = v => (v == null ? null : Array.isArray(v) ? '#' + hex2(v[3]) + hex2(v[0]) + hex2(v[1]) + hex2(v[2]) : (v.length === 7 ? '#ff' + v.slice(1) : v).toLowerCase())
const argbToBg = c => (c == null ? null : [parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16), parseInt(c.slice(7, 9), 16), parseInt(c.slice(1, 3), 16)])

// 글자 — 독립 글은 그 자신, 도형·선·화살표는 안에 붙은 글(라벨) 전부. → [{ font, color, text }]
const arrowLabels = it => it.labels || (it.label ? [it.label] : [])   // 옛 파일은 단수 label
function textSlots(it) {
  if (it.type === 'text') return [{ font: it.font || 12, color: it.color || INK, text: it.text || '' }]
  if (it.type === 'table') return [{ font: it.font || tableAutoPt(it), fonts: it.font ? null : tableCellPts(it), color: it.color || '#111111', text: (it.cells || []).flat().find(Boolean) || '' }]   // 표 글자 = 표 전체 하나. 크기를 표 전체로 안 정했으면 칸마다 지금 보이는 크기(자동 칸은 줄어든 실제 크기 — 범위로 보임)
  if (isArrow(it)) return arrowLabels(it).filter(L => L.text?.trim()).map(L => ({ font: L.font || 16, color: L.color || it.color || INK, text: L.text }))
  if (['rect', 'ellipse', 'symbol', 'polygon', 'line'].includes(it.type) && it.label?.text?.trim()) return [{ font: FIT.has(it.type) ? labelShownPt(it) : it.label.font || 16, color: it.label.color || it.pen || INK, text: it.label.text }]   // 상자에 맞춰 줄어든 글은 보이는 크기
  return []
}
// 상자 폭에 맞춰 글을 줄이는 도형(render.jsx `CenterLabel`) — 글을 키웠는데 상자보다 크면 상자 폭을 늘림(가운데 그대로, 2026-10-23 사용자 선택)
const FIT = new Set(['rect', 'ellipse', 'symbol'])
function growToFit(it, p) {
  if (!p?.label || !FIT.has(it.type) || it.label?.align === 'left') return p
  const [x, y, w, h] = it.rect, need = Math.ceil(labelNeedW({ ...it, label: p.label }, p.label.font))
  return need > w ? { ...p, rect: [x - (need - w) / 2, y, need, h] } : p
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
// .ecad runs = [시작, 길이, 색, 굵게, 바탕?, 고정폭?, 꾸밈?] — 글자마다 풀었다가 한 칸만 바꿔 다시 묶음(나머지 칸은 그대로 — 2026-10-23 굵게 추가 때
// 고정폭·꾸밈 칸까지 살림: 전엔 형광펜을 켜면 코드 글꼴·기울임이 지워졌음)
const HL = '#99ffd54f'
const hlHost = it => (it.type === 'text' ? (it.text ? it : null) : ['rect', 'ellipse', 'symbol', 'polygon', 'line'].includes(it.type) && it.label?.text?.trim() ? it.label : null)
const charAttrs = (text, runs) => { const a = Array.from({ length: text.length }, () => [null, false, null, false, ''])
  for (const [st, len, c, b, g, m, d] of runs || []) for (let i = Math.max(0, st); i < Math.min(text.length, st + len); i++) a[i] = [c || null, !!b, g || null, !!m, d || '']
  return a }
const allChars = (h, k, l) => { const a = charAttrs(h.text, h.runs); return [...h.text].every((ch, i) => ch === '\n' || (l ? a[i][4].includes(l) : !!a[i][k])) }   // k = 1 굵게 · 2 바탕 · 3 고정폭 · 4 꾸밈(l = 'i'·'u'·'s')
function runsWith(text, runs, k, v) {   // v = 값, 또는 함수(지금 값 → 새 값)
  const a = charAttrs(text, runs).map(x => { const y = [...x]; y[k] = typeof v === 'function' ? v(y[k]) : v; return y }), out = []
  for (let i = 0; i < a.length;) { let j = i + 1; while (j < a.length && a[j].every((v, k) => v === a[i][k])) j++
    const [c, b, g, m, d] = a[i]
    if (c || b || g || m || d) out.push([i, j - i, c, b, ...(g || m || d ? [g] : []), ...(m || d ? [m] : []), ...(d ? [d] : [])]); i = j }
  return out
}
const patchRuns = (it, k, v) => { const h = hlHost(it); if (!h) return null; const runs = runsWith(h.text, h.runs, k, v)
  return it.type === 'text' ? { runs } : { label: { ...it.label, runs } } }
const patchHl = (it, on) => patchRuns(it, 2, on ? HL : null)
// 속성 카드 꾸밈 버튼(글 전체) — 꾸미기 막대와 같은 항목(`textfmt.jsx`)
const DECO = { italic: 'i', underline: 'u', strike: 's' }
const decoSet = (d, l, on) => 'ius'.split('').filter(x => (x === l ? on : d.includes(x))).join('')
const patchFmt = (it, k, on) => { if (k === 'clear') { const h = hlHost(it); return h && (it.type === 'text' ? { runs: [] } : { label: { ...it.label, runs: [] } }) }
  return k === 'bold' ? patchRuns(it, 1, on) : k === 'hl' ? patchHl(it, on) : k === 'code' ? patchRuns(it, 3, on) : patchRuns(it, 4, d => decoSet(d, DECO[k], on)) }
const fmtOn = (h, k) => (k === 'bold' ? allChars(h, 1) : k === 'hl' ? allChars(h, 2) : k === 'code' ? allChars(h, 3) : allChars(h, 4, DECO[k]))

// 도형 바꾸기(데스크톱 `_fill_swap_menu` 기본도형 8종 — 「내 심볼」은 심볼 팔레트를 옮길 때). 같은 _id라 붙은 화살표·라벨·색은 그대로
const SWAP_KINDS = ['rect', 'ellipse', 'triangle', 'decision', 'terminal', 'data', 'prep', 'database']
const kindOf = it => (it.type === 'symbol' ? it.kind : it.type)
const swapPatch = k => (k === 'rect' || k === 'ellipse' ? { type: k, kind: undefined, cuts: undefined } : { type: 'symbol', kind: k, cuts: undefined })
const kindName = k => (k === 'rect' ? '사각형' : k === 'ellipse' ? '원' : SYMBOLS[k]?.name || k)
const shapeIcon = k => paletteIcon(k === 'rect' || k === 'ellipse' ? k : 'sym:' + k, 22, 14, 1.3)   // 도형 카드와 같은 그림(칠판 기본 비율)
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

// 그림 설명 — 첫 줄만, 둘째 줄부터(PDF에서 오려 온 부분의 글 등)는 「글 N자 들어 있음 ▸」로 접음(2026-10-22 사용자: 속성 카드가 너무 길어짐).
// 글은 그림에 그대로 — 찾기·뜻으로 찾기·KAIROS 질문·「그림 속 글 읽기」가 씀
function ImageAlt({ alt }) {
  const [open, setOpen] = useState(false), [head, ...rest] = alt.split('\n'), more = rest.join('\n')
  return <span style={{ fontSize: 12, lineHeight: 1.4, wordBreak: 'break-all', padding: '4px 0', display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
    <span data-testid="image-alt" title="찾기(Ctrl+F)·뜻으로 찾기가 이 글로 그림을 찾아요">{head}</span>
    {more.trim() && <button data-testid="image-alt-more" onClick={() => setOpen(o => !o)} style={{ all: 'unset', cursor: 'pointer', color: 'var(--mb-muted)', fontSize: 11 }}>글 {more.replace(/\s+/g, '').length.toLocaleString()}자 들어 있음 {open ? '▾' : '▸'}</button>}
    {open && more.trim() && <span style={{ maxHeight: 200, overflowY: 'auto', whiteSpace: 'pre-wrap', opacity: 0.85 }}>{more}</span>}
  </span>
}
const Row = ({ label, children }) => <div style={{ display: 'flex', alignItems: 'center', gap: 6, minHeight: 28 }}>
  <span style={{ width: 40, flex: 'none', color: C.muted, fontSize: 12 }}>{label}</span>{children}</div>
const btn = (on, extra) => ({ all: 'unset', boxSizing: 'border-box', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 3, height: 26, borderRadius: 6,
  color: on ? C.on : C.ink, background: on ? C.onBg : 'transparent', outline: on ? `1px solid ${C.on}` : 'none', ...extra })
// 정렬·분배 아이콘 줄(2026-10-23 사용자: 우클릭 「정렬 / 분배」를 못 찾음 — Figma처럼 여러 개 고르면 속성 카드 맨 위에). align = { n, align(mode), dist(axis) }
const AL = (bar, rects) => <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3">{bar}{rects.map(([x, y, w, h], i) => <rect key={i} x={x} y={y} width={w} height={h} rx="0.8" fill="currentColor" fillOpacity=".25" />)}</svg>
const ALIGNS = [
  ['left', '왼쪽 맞춤', AL(<path d="M2 1.5v13" />, [[2.5, 3.5, 7, 3], [2.5, 9.5, 11, 3]])],
  ['hcenter', '가로 가운데', AL(<path d="M8 1.5v13" />, [[4.5, 3.5, 7, 3], [2.5, 9.5, 11, 3]])],
  ['right', '오른쪽 맞춤', AL(<path d="M14 1.5v13" />, [[6.5, 3.5, 7, 3], [2.5, 9.5, 11, 3]])],
  ['top', '위쪽 맞춤', AL(<path d="M1.5 2h13" />, [[3.5, 2.5, 3, 7], [9.5, 2.5, 3, 11]])],
  ['vcenter', '세로 가운데', AL(<path d="M1.5 8h13" />, [[3.5, 4.5, 3, 7], [9.5, 2.5, 3, 11]])],
  ['bottom', '아래쪽 맞춤', AL(<path d="M1.5 14h13" />, [[3.5, 6.5, 3, 7], [9.5, 2.5, 3, 11]])],
]
const DISTS = [['x', '가로 균등 분배(3개부터)', AL(<path d="M1.5 2v12M14.5 2v12" />, [[6.5, 4, 3, 8]])], ['y', '세로 균등 분배(3개부터)', AL(<path d="M2 1.5h12M2 14.5h12" />, [[4, 6.5, 8, 3]])]]
function AlignRow({ align }) {
  const b = dis => btn(false, { width: 20, height: 24, opacity: dis ? 0.35 : 1, cursor: dis ? 'default' : 'pointer' })
  return <div data-testid="align-row" style={{ display: 'flex', gap: 1, justifyContent: 'space-between', paddingBottom: 4, marginBottom: 2, borderBottom: `1px solid ${C.line}` }}>
    {ALIGNS.map(([m, t, ic]) => <button key={m} title={t} aria-label={t} onClick={() => align.align(m)} style={b(false)}>{ic}</button>)}
    {DISTS.map(([a, t, ic]) => <button key={a} title={t} aria-label={t.replace(/\(.*\)/, '')} disabled={align.n < 3} onClick={() => align.dist(a)} style={b(align.n < 3)}>{ic}</button>)}
  </div>
}
// 표 글자 「자동」 켜고 끄기(2026-10-18 사용자: 끄려고 크기를 일부러 바꿔야 했음) — 켜짐 = 칸에 맞춰 줄어듦, 끄면 지금 보이는 크기 그대로 고정
function AutoToggle({ on, onClick }) {
  return <button title={on ? '자동 — 칸에 맞춰 글자 크기가 바뀌어요. 누르면 지금 크기로 고정' : '고정 — 누르면 칸에 맞춰 자동으로'} onClick={onClick}
    style={btn(on, { padding: '0 6px', fontSize: 11, flex: 'none', whiteSpace: 'nowrap', ...(on ? {} : { background: C.seg }) })}>자동</button>   // 줄바꿈 금지 — 폭이 모자라 「자/동」 두 줄로 꺾였음(2026-10-23)
}
// 여러 개 중 하나(켜진 것만 코랄)
function Seg({ items, value, onPick }) {
  return <div style={{ display: 'flex', gap: 2, background: C.seg, borderRadius: 8, padding: 2, flex: 1 }}>
    {items.map(([k, icon, name]) => <button key={k} title={name} aria-pressed={value === k} onClick={() => onPick(k)} style={btn(value === k, { flex: 1 })}>{icon}</button>)}
  </div>
}
// − 값 + (휠로도). 여러 개를 골라 값이 다르면 「1~3px」처럼 범위로 보이고, ±는 각자에 같은 만큼 더함(차이 유지 — 2026-10-18 사용자 선택)
// values = 고른 것들의 값, onStep(d) = 각자 d만큼(부르는 쪽이 범위 안으로 자름), grow = 줄 남은 폭을 다 씀
export const stepClamp = (v, d, min, max, step) => +(Math.round(Math.min(max, Math.max(min, v + d)) / step) * step).toFixed(6)   // 0.1 단위의 떠다니는 소수 자리(1.2000000000000002) 없앰
function Stepper({ values, step = 1, fmt = v => v, onStep, title, grow, testid }) {
  const lo = Math.min(...values), hi = Math.max(...values), mixed = hi - lo > 1e-9
  const text = mixed ? `${String(fmt(lo)).replace(/[^\d.]+$/, '')}~${fmt(hi)}` : fmt(lo)
  return <div data-testid={testid} title={mixed ? `${title} — 서로 다름(±는 각자에 더함)` : title} onWheel={e => onStep(e.deltaY < 0 ? step : -step)} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: C.seg, borderRadius: 8, padding: 2, ...(grow ? { flex: 1, minWidth: 0 } : {}) }}>
    <button aria-label={title + ' 줄이기'} onClick={() => onStep(-step)} style={btn(false, { width: 22 })}>−</button>
    <span style={{ minWidth: 34, textAlign: 'center', fontVariantNumeric: 'tabular-nums', fontSize: 12, whiteSpace: 'nowrap', padding: '0 2px' }}>{text}</span>
    <button aria-label={title + ' 늘리기'} onClick={() => onStep(step)} style={btn(false, { width: 22 })}>+</button>
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

// items = 고른 것 전부. set(아이템 → 고칠 값 | null, 이름, 묶음 열쇠) — 해당 없는 아이템은 null.
// kind = 고른 것이 모두 화살표이고 종류가 같으면 그것('straight'|'curved'|'ortho'), onKind(k) = 화살표 종류 바꾸기
// 값이 서로 다르면: 고르는 칸은 아무것도 안 켬(누르면 전부 그 값), 숫자 칸은 범위(데스크톱도 같은 규칙, 2026-10-18)
export function Props({ items, kind, set, onKind, rotate, library, onSwapTo, dark, cells, setCells, onLegend, align, liveEd }) {   // liveEd = 글 고치는 중 편집기(TipTap) — 「글자」 꾸밈이 고른 글자(없으면 글 전체)에 먹음, 2026-10-23   // onLegend(범례 id, 줄 열쇠, { name } | { color·style·width }) — 범례 줄 이름·도면 속 그 선 일괄 바꾸기   // cells = 고른 표 칸 { table, r0, r1, c0, c1 }, setCells(꾸밈 → 고칠 값, 이름, 묶음)   // library = 내 심볼(서버 파일), onSwapTo(아이디들, 'customsym:<id>'|'rect'|'sym:<종류>')   // rotate(아이템, 각도) → 회전한 아이템(가운데 기준, Editor `rotateTo`)
  const [pop, setPop] = useState(null)   // 지금 열린 펼침 하나 — 'swap'·'dash'·색 칸 이름(한 번에 하나만)
  useEffect(() => {
    if (!pop) return
    const down = e => { if (e.target.closest?.('[data-ppop]')?.dataset.ppop !== pop) setPop(null) }   // 그 펼침(버튼 포함) 밖을 누르면 닫음
    const key = e => { if (e.key === 'Escape') { e.stopImmediatePropagation(); setPop(null) } }   // 칠판의 Esc(고른 것 풀기)보다 먼저
    window.addEventListener('pointerdown', down, true); window.addEventListener('keydown', key, true)
    return () => { window.removeEventListener('pointerdown', down, true); window.removeEventListener('keydown', key, true) }
  }, [pop])
  const [folded, toggleFold] = useFold('props')
  const one = v => (v.length && v.every(x => x === v[0]) ? v[0] : null)
  const arrows = items.filter(isArrow), allArrows = arrows.length === items.length
  const lineItems = items.filter(lineKey), wItems = items.filter(hasWidth), fillItems = items.filter(fillKey)
  const texts = items.flatMap(textSlots)
  const boardsOnly = items.every(it => it.type === 'board'), allText = items.every(it => it.type === 'text')
  const showLine = lineItems.length > 0 && !allText   // 독립 글만 골랐으면 「선」 줄을 숨김(글 색은 「글자」에서)
  const types = new Set(items.map(typeName))
  const title = items.length === 1 ? typeName(items[0]) : types.size === 1 ? `${[...types][0]} ${items.length}개` : `${items.length}개 · 혼합`

  const color = one(lineItems.map(it => norm(it[lineKey(it)] ?? (it.type === 'table' ? '#333333' : null)))) ?? ''   // 표 선은 안 정했으면 render.jsx 기본(#333333) — 하나만 골라도 「서로 다름」으로 보였음
  const style = one(wItems.map(it => it.style || 1))
  const fill = fillItems.length ? one(fillItems.map(it => fillArgb(it[fillKey(it)]))) : undefined   // null = 없음, undefined = 서로 다름
  const fillMixed = fillItems.length > 1 && !fillItems.every(it => fillArgb(it[fillKey(it)]) === fillArgb(fillItems[0][fillKey(fillItems[0])]))
  const head = one(arrows.map(a => (a.head !== false ? (a.head_start ? 'both' : 'end') : a.head_start ? 'start' : 'none')))
  const tColor = one(texts.map(t => norm(t.color))) ?? ''
  const swapOne = items.length === 1 && ['rect', 'ellipse', 'symbol'].includes(items[0].type) ? items[0] : null
  // 묶음 하나를 통째로 골랐으면(내 심볼에서 온 것 등) 그것도 바꿀 수 있음 — 기본 도형으로 돌아가기·다른 내 심볼로
  const swapGrp = !swapOne && items.length >= 2 && items[0].group_id && items.every(it => it.group_id === items[0].group_id && !isArrow(it)) ? items.map(it => it._id) : null
  const rotItems = items.filter(it => ROTATABLE.has(it.type)), rot = one(rotItems.map(it => +(it.rotation || 0).toFixed(1)))
  const hlItems = items.filter(hlHost)
  useEdTick(liveEd)   // 고치는 중 = 편집기 커서·고른 글자가 바뀔 때마다 켜짐 상태 다시
  const edLive = liveEd && !liveEd.isDestroyed ? liveEd : null
  const fmtSt = edLive ? edState(edLive) : Object.fromEntries(['bold', 'italic', 'underline', 'strike', 'code', 'hl'].map(k => [k, hlItems.length > 0 && hlItems.every(it => fmtOn(hlHost(it), k))]))
  const fmtAct = k => (edLive ? edAct(edLive, k, true) : set(it => patchFmt(it, k, !fmtSt[k]), { bold: '굵게', italic: '기울임', underline: '밑줄', strike: '취소선', code: '코드', hl: '형광펜', clear: '꾸밈 지우기' }[k]))
  const tables = items.filter(it => it.type === 'table'), ptFmt = tables.length ? v => Math.round(v) + 'pt' : v => v + 'pt'   // 표 자동 크기는 11.3처럼 소수 — 반올림해 보임(「자동」 버튼 자리)
  const fillLabel = fillItems.every(it => fillKey(it) === 'bg') ? '바탕' : '채움'   // 글의 채움 = 글 뒤 바탕
  // 숫자 칸 — 각자에 d만큼(범위 안으로)
  const num = (list, get, d0, min, max, step, name, write) => ({ values: list.map(it => get(it) ?? d0), step,
    onStep: d => { const ids = new Set(list.map(it => it._id)); set(it => (ids.has(it._id) ? write(it, stepClamp(get(it) ?? d0, d, min, max, step)) : null), name, name) } })
  const onArrows = f => it => (isArrow(it) ? f(it) : null)
  // 글자 줄들 — 크기 · 색 · (굵게 · 형광펜). 글만 골랐으면 카드 맨 위에(글이 주인공 — 2026-10-23)
  const hasText = (texts.length > 0 || !!edLive) && !cells   // 고치는 중이면 글이 아직 안 들어갔어도(새 상자에 치는 중)
  const textRows = hasText && <>
    <Row label="크기"><Stepper testid="font-step" title="글자 크기" values={texts.length ? texts.flatMap(t => t.fonts || [t.font]) : [items[0]?.label?.font || items[0]?.font || 16]} onStep={d => set(it => { if (it.type === 'table' && !it.font) return stepTableCells(it, d); const p = patchTexts(it, t => ({ font: stepClamp(t.font, d, 2, 200, 1) })) ?? (edLive ? (it.type === 'text' ? { font: stepClamp(it.font || 12, d, 2, 200, 1) } : { label: { ...(it.label || { text: '' }), font: stepClamp(it.label?.font || 16, d, 2, 200, 1) } }) : null)   // 새 상자에 치는 중(글이 아직 안 들어감)이어도
        return d > 0 ? growToFit(it, p) : p }, '글자 크기', '글자 크기')} fmt={ptFmt} />
      {tables.length > 0 && (() => { const on = !items.some(hasFixedFont)
        return <AutoToggle on={on} onClick={() => set(it => (it.type !== 'table' ? null : on ? stepTableCells(it, 0) : clearTableFont(it)), on ? '글자 크기 고정' : '글자 크기 자동')} /> })()}</Row>
    <Row label="색"><ColorChip id="text" pop={pop} setPop={setPop} keepEdit={!!edLive} value={edLive ? edState(edLive).color || tColor : tColor} title="글자 색"
      onPick={(c, drag) => (edLive ? edRun(edLive, ch => ch.setColor(c), true) : set(it => patchTexts(it, () => ({ color: c })), '글자 색', drag ? 'tcolor' : null))} /></Row>
    {(hlItems.length > 0 || edLive) && <div data-testid="props-fmt" style={{ display: 'flex', alignItems: 'center', gap: 1, justifyContent: 'space-between', background: C.seg, borderRadius: 8, padding: 2 }}><FmtButtons prefix="pfmt" w={20} st={fmtSt} act={fmtAct} /></div>}
  </>

  return <div data-folded={folded || undefined} data-keep-edit={edLive ? '' : undefined} onPointerDown={e => e.stopPropagation()} onMouseDown={e => { if (edLive && e.target.tagName !== 'INPUT') e.preventDefault() }} style={{ position: 'absolute', right: 'calc(12px + var(--mb-right-inset, 0px))', top: 12, width: 192, boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10,
    padding: '8px 10px 10px', boxShadow: '0 2px 8px rgba(0,0,0,.06)', font: "400 13px 'Pretendard', sans-serif", color: C.ink, display: 'flex', flexDirection: 'column', gap: 4, userSelect: 'none', maxHeight: 'calc(100% - 24px)', overflowY: 'auto' }}>   {/* 높이 = 칠판 끝까지(미니맵은 왼쪽 판으로 감 — 전엔 아래 180을 비워 일찍 스크롤) */}
    {/* 머리말 = 고른 것의 종류(2026-10-23 사용자 검토: 「속성」 제목과 「종류」 줄이 같은 말 — 한 줄로). 도형이면 눌러서 다른 도형으로 */}
    <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: folded ? 0 : 2 }}>
      {(swapOne || swapGrp) && !folded ? <div data-ppop="swap" style={{ position: 'relative', flex: 1, minWidth: 0 }}>
        <button title="클릭: 다른 도형으로 바꾸기(크기·연결 유지)" aria-expanded={pop === 'swap'} onClick={() => setPop(pop === 'swap' ? null : 'swap')} style={btn(pop === 'swap', { width: '100%', justifyContent: 'flex-start', gap: 6, padding: '0 4px', height: 28 })}>
          {swapOne ? shapeIcon(kindOf(swapOne)) : null}<span data-testid="prop-type" style={{ font: "700 15px 'Pretendard', sans-serif", overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{swapOne ? title : `묶음 ${items.length}개`}</span><span style={{ color: C.muted, marginLeft: 'auto' }}>▾</span></button>
        {pop === 'swap' && <div style={{ position: 'absolute', zIndex: 3, top: 30, left: 0, right: 0, maxHeight: 360, overflowY: 'auto', background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, padding: 3, boxShadow: '0 4px 12px rgba(0,0,0,.1)' }}>
          {SWAP_KINDS.map(k => <button key={k} onClick={() => { if (swapGrp) onSwapTo(swapGrp, k === 'rect' || k === 'ellipse' ? k : 'sym:' + k); else if (k !== kindOf(swapOne)) set(it => (it._id === swapOne._id ? swapPatch(k) : null), '도형 바꾸기'); setPop(null) }}
            style={btn(!!swapOne && k === kindOf(swapOne), { width: '100%', justifyContent: 'flex-start', gap: 8, padding: '0 8px' })}>{shapeIcon(k)}<span style={{ fontSize: 12 }}>{kindName(k)}</span></button>)}
          {/* 내 심볼 — 폴더마다 구분선(데스크톱 `_fill_swap_menu`). 묶음으로 바뀌고 라벨은 안 옮김(여러 조각 중 어디에 둘지 애매 — 데스크톱과 같음) */}
          {(library?.folders || []).map(f => { const list = (library.symbols || []).filter(s => s.folder === f); if (!list.length) return null
            return <div key={f}><div style={{ borderTop: `1px solid ${C.line}`, margin: '3px 0', padding: '3px 8px 0', fontSize: 11, color: C.muted }}>{f}</div>
              {list.map(s => <button key={s.id} onClick={() => { onSwapTo(swapGrp || [swapOne._id], 'customsym:' + s.id); setPop(null) }} style={btn(false, { width: '100%', justifyContent: 'flex-start', gap: 8, padding: '0 8px' })}>
                <img alt="" src={'data:image/png;base64,' + s.thumb} width="20" height="20" style={{ filter: dark ? 'invert(1) hue-rotate(180deg)' : undefined }} />
                <span style={{ fontSize: 12, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{s.name}</span></button>)}</div> })}
        </div>}
      </div>
      : <span data-testid="prop-type" style={{ font: "700 15px 'Pretendard', sans-serif", flex: 1, minWidth: 0, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{title}</span>}
      <FoldBtn minus folded={folded} onClick={toggleFold} /></div>
    {!folded && align?.n >= 2 && <AlignRow align={align} />}
    {allArrows && <Row label="종류"><Seg value={kind} onPick={onKind} items={[['straight', ICONS.straight, '직선'], ['curved', ICONS.curved, '곡선'], ['ortho', ICONS.ortho, '직각']]} /></Row>}
    {allText && textRows}
    {/* 선 = 색 칸 한 줄 + (모양 ▾ · 굵기 −/+) 한 줄. 굵기 숫자 버튼(1·2·3·5)은 뺌 — 스테퍼 하나로(2026-10-23 사용자) */}
    {showLine && <Row label={boardsOnly ? '바탕' : wItems.length || tables.length ? '선' : '색'}><ColorChip id="line" keepEdit={!!edLive} pop={pop} setPop={setPop} value={color} title={boardsOnly ? '바탕 색' : '선 색'}
      onPick={(c, drag) => set(it => (lineKey(it) ? { [lineKey(it)]: c } : null), boardsOnly ? '바탕 색' : '색', drag ? 'color' : null)} /></Row>}
    {showLine && wItems.length > 0 && <Row label=""><div data-ppop="dash" style={{ position: 'relative', flex: 'none' }}>
      <button title="선 모양" aria-expanded={pop === 'dash'} onClick={() => setPop(pop === 'dash' ? null : 'dash')} style={btn(pop === 'dash', { width: 52, background: C.seg, justifyContent: 'space-between', padding: '0 6px' })}>{style ? <svg width="26" height="10"><line x1="1" y1="5" x2="25" y2="5" stroke="currentColor" strokeWidth="2" strokeDasharray={DASH[style]} strokeLinecap="round" /></svg> : <span style={{ fontSize: 11, color: C.muted }}>섞임</span>}<span style={{ color: C.muted }}>▾</span></button>
      {pop === 'dash' && <div style={{ position: 'absolute', zIndex: 2, top: 28, left: 0, width: 126, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, padding: 3, boxShadow: '0 4px 12px rgba(0,0,0,.1)' }}>
        {STYLES.map(([st, name]) => <button key={st} title={name} onClick={() => { set(it => (hasWidth(it) ? { style: st } : null), '선 모양'); setPop(null) }} style={btn(style === st, { width: '100%', justifyContent: 'space-between', padding: '0 8px' })}>
          {dashIcon(st)}<span style={{ fontSize: 11, color: C.muted }}>{name}</span></button>)}
      </div>}
    </div><Stepper grow testid="width-step" title="선 굵기" {...num(wItems, it => it.width, 1, 1, 40, 1, '굵기', (it, v) => ({ width: v }))} fmt={v => v + 'px'} /></Row>}
    {fillItems.length > 0 && <Row label={fillLabel}><ColorChip id="fill" keepEdit={!!edLive} fill pop={pop} setPop={setPop} value={fillMixed ? undefined : fill} title={fillLabel}
      onPick={(c, drag) => set(it => { const k = fillKey(it); return k ? { [k]: k === 'bg' ? argbToBg(c) : c } : null }, fillLabel, drag ? 'fill' : null)} /></Row>}
    {arrows.length > 0 && <>
      <Row label="화살촉"><Seg value={head} onPick={h => set(onArrows(() => ({ head: h === 'end' || h === 'both', head_start: h === 'start' || h === 'both' })), '화살촉')}
        items={[['none', ICONS.none, '없음'], ['end', ICONS.end, '끝만'], ['both', ICONS.both, '양쪽'], ['start', ICONS.start, '시작만']]} /></Row>
      {/* 「머리」 → 화살촉 밑 「촉 1.0×」(무슨 크기인지 바로 보이게), 「모서리」 → 「꺾임」(사각형 둥글기와 이름이 겹쳤음 — 2026-10-23) */}
      <Row label=""><Stepper grow title="화살촉 크기 배율" {...num(arrows, a => a.head_scale, 1, 0.5, 3, 0.1, '촉 크기', (a, v) => ({ head_scale: v }))} fmt={v => '촉 ' + v.toFixed(1) + '×'} /></Row>
      {kind === 'ortho' && <Row label="꺾임"><Stepper title="꺾인 곳 둥글기(0 = 각짐)" {...num(arrows, a => a.curve_r, 10, 0, 40, 1, '꺾임 둥글기', (a, v) => ({ curve_r: v }))} /></Row>}
    </>}
    {items.some(it => it.type === 'rect') && <Row label="둥글기"><Stepper title="네모 모서리 둥글기(0 = 각짐)" {...num(items.filter(it => it.type === 'rect'), it => it.radius, 0, 0, 60, 2, '모서리 둥글기', (it, v) => ({ radius: v || undefined }))} /></Row>}
    {tables.length > 0 && <Row label="첫 행">
      <Seg value={one(tables.map(it => !!it.header))} onPick={v => set(it => (it.type === 'table' ? { header: v } : null), '머리 행')} items={[[true, <b key="b">머리</b>, '첫 행을 머리로(굵게)'], [false, <span key="n">보통</span>, '첫 행도 보통']]} />
    </Row>}
    {items.length === 1 && items[0].type === 'web' && (() => { const w = items[0]   // 웹 카드 — 제목(카드 위 띠·PDF에 나옴)·새 탭
      return <>
        <Row label="제목"><input key={w._id} defaultValue={w.title || ''} placeholder="페이지 제목" onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') e.currentTarget.blur() }}
          onChange={e => set(() => ({ title: e.target.value }), '웹 카드 제목', 'wtitle')}
          style={{ flex: 1, minWidth: 0, height: 24, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 6px', font: 'inherit' }} /></Row>
        <Row label="주소"><button title={w.url} onClick={() => window.open(w.url, '_blank', 'noopener')} style={{ all: 'unset', cursor: 'pointer', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: '#3b82f6', fontSize: 11 }}>↗ 새 탭에서 열기</button></Row>
        {w.frameable && !w.embed && <Row label="배율"><div style={{ flex: 1, display: 'flex', gap: 2, background: C.group, borderRadius: 8, padding: 2 }}>
          {WEB_ZOOMS.map(v => { const on = (w.zoom || 1) === v
            return <button key={v} title={v < 1 ? `페이지를 ${v * 100}%로 — 카드 크기는 그대로, 더 많이 보임` : '원래 크기'} onClick={() => set(() => ({ zoom: v < 1 ? v : undefined }), '웹 카드 배율')}
              style={{ all: 'unset', cursor: 'pointer', flex: 1, textAlign: 'center', padding: '2px 0', borderRadius: 6, fontSize: 11, background: on ? 'rgba(218,119,86,.22)' : 'transparent', color: on ? '#da7756' : C.ink, fontWeight: on ? 600 : 400 }}>{v * 100}%</button> })}</div></Row>}
        <div style={{ fontSize: 11, color: C.muted }}>{w.frameable ? (w.embed ? '누르면 바로 재생 · 위 띠를 끌면 이동' : '누르면 칸 안을 조작(바깥을 누르면 끝) · 위 띠를 끌면 이동') : '이 사이트는 칸 안에 넣기를 막아요 — 두 번 누르면 새 탭'}</div>
      </> })()}
    {items.length === 1 && items[0].type === 'legend' && (() => { const L = items[0], rows = L.rows || []   // 범례(2026-10-19) — 줄은 도면에서 저절로. 이름은 적고, 색·모양·굵기를 고르면 도면 속 그 선이 전부 바뀜
      const sel = { height: 22, border: `1px solid ${C.line}`, borderRadius: 5, background: C.card, color: C.ink, font: 'inherit', fontSize: 11, padding: '0 2px' }
      const hex6 = c => '#' + (c.length === 9 ? c.slice(3) : c.slice(1))
      return <>
        <Row label="제목"><input key={L._id} defaultValue={L.title || '범례'} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') e.currentTarget.blur() }} onChange={e => set(() => ({ title: e.target.value }), '범례 제목', 'lgtitle')}
          style={{ flex: 1, minWidth: 0, height: 24, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 6px', font: 'inherit' }} /></Row>
        <Row label="크기"><div style={{ display: 'flex', gap: 4 }}>{[['작게', 0.8], ['크게', 1.25]].map(([t, f]) => <button key={t} onClick={() => set(it => ({ scale: +((it.scale || 1) * f).toFixed(3) }), '범례 크기')} style={{ all: 'unset', cursor: 'pointer', padding: '2px 10px', borderRadius: 6, background: C.seg, fontSize: 11 }}>{t}</button>)}</div></Row>
        <div style={{ fontSize: 11, color: C.muted }}>{rows.length ? '선을 그리거나 바꾸면 저절로 따라가요. 모양·굵기·색을 고르면 도면 속 그 선이 전부 바뀌어요' : '색 있는 선·화살표를 그리면 저절로 채워져요'}</div>
        {rows.map(e => <div key={e.key} data-testid="legend-row" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 4, paddingBottom: 4, borderBottom: `1px solid ${C.line}` }}>   {/* 한 줄 = 색·이름 / 모양·굵기(카드 폭이 좁아 이름이 잘렸음) */}
          <input type="color" title="색 — 이 선 전부" value={hex6(e.color)} onChange={ev => onLegend(L._id, e.key, { color: '#ff' + ev.target.value.slice(1) })} style={{ width: 22, height: 22, padding: 0, border: 0, background: 'none', cursor: 'pointer' }} />
          <input key={L._id + e.key} defaultValue={rowName(L, e)} title={`이 선 ${e.count}개`} onKeyDown={ev => { ev.stopPropagation(); if (ev.key === 'Enter') ev.currentTarget.blur() }} onChange={ev => onLegend(L._id, e.key, { name: ev.target.value })}
            style={{ flex: '1 0 calc(100% - 30px)', minWidth: 0, height: 22, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 5, background: 'transparent', color: C.ink, padding: '0 5px', font: 'inherit', fontSize: 11 }} />
          <select title="선 모양 — 이 선 전부" value={e.style} onChange={ev => onLegend(L._id, e.key, { style: +ev.target.value })} style={{ ...sel, flex: 1, marginLeft: 26 }}>{Object.entries(STYLE_NAMES).map(([v, n]) => <option key={v} value={v}>{n}</option>)}</select>
          <select title="굵기 — 이 선 전부" value={e.width} onChange={ev => onLegend(L._id, e.key, { width: +ev.target.value })} style={{ ...sel, width: 58 }}>{[...new Set([...LG_WIDTHS, e.width])].sort((a, b) => a - b).map(v => <option key={v} value={v}>{v}px</option>)}</select>
        </div>)}
      </> })()}
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
    {items.length === 1 && items[0].type === 'image' && items[0].alt && <Row label="설명"><ImageAlt key={items[0]._id} alt={items[0].alt} /></Row>}
    {rotItems.length > 0 && <Row label="회전"><RotInput value={rot} onSet={a => set(it => (ROTATABLE.has(it.type) ? rotate(it, a) : null), '회전', '회전')} /></Row>}
    {cells && (() => {   // 고른 칸(들)의 꾸밈 — 표 전체 값 위에 덮음
      const { table: t, r0, r1, c0, c1 } = cells, list = []
      for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) list.push({ r, c, s: t.cell_styles?.[`${r},${c}`] || {} })
      const v = f => one(list.map(f)), n = list.length
      const fontV = list.map(e => cellPt(t, e.r, e.c)), auto = list.every(e => e.s.font == null && !t.font)
      return <>
        <div style={{ borderTop: `1px solid ${C.line}`, margin: '4px 0 0' }} />
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}><span style={{ fontWeight: 600 }}>칸</span><span style={{ fontSize: 11, color: C.muted }}>{n}개 · Shift+클릭으로 넓히기</span></div>
        <Row label="크기"><Stepper title="칸 글자 크기" values={fontV} onStep={d => setCells((s, r, c) => ({ font: stepClamp(cellPt(t, r, c), d, 1, 200, 1) }), '칸 글자 크기', 'cfont')} fmt={x => Math.round(x) + 'pt'} />
          <AutoToggle on={auto} onClick={() => (auto ? setCells((s, r, c) => ({ font: cellPt(t, r, c, true) }), '칸 글자 크기 고정') : setCells(() => ({ font: undefined }), '칸 글자 크기 자동'))} /></Row>
        <Row label="굵게"><Seg value={v(e => e.s.bold ?? !!(t.header && e.r === 0))} onPick={b => setCells(() => ({ bold: b }), '칸 굵게')} items={[[true, <b key="b">굵게</b>, '굵게'], [false, <span key="n">보통</span>, '보통']]} /></Row>
        <Row label="정렬"><Seg value={v(e => e.s.align || 'center')} onPick={a => setCells(() => ({ align: a === 'center' ? undefined : a }), '칸 정렬')}
          items={[['left', <span key="l">왼쪽</span>, '왼쪽'], ['center', <span key="c">가운데</span>, '가운데'], ['right', <span key="r">오른쪽</span>, '오른쪽']]} /></Row>
        <Row label="색"><ColorChip id="ccolor" pop={pop} setPop={setPop} title="칸 글자 색" value={norm(v(e => e.s.color ?? t.color ?? '#111111') || '')} onPick={(c, drag) => setCells(() => ({ color: c }), '칸 글자 색', drag ? 'ccolor' : null)} /></Row>
        <Row label="채움"><ColorChip id="cfill" fill pop={pop} setPop={setPop} title="칸 채움" value={list.every(e => fillArgb(e.s.fill) === fillArgb(list[0].s.fill)) ? fillArgb(list[0].s.fill) ?? null : undefined} onPick={(c, drag) => setCells(() => ({ fill: c || undefined }), '칸 채움', drag ? 'cfill' : null)} /></Row>
      </>
    })()}
    {hasText && !allText && <>
      <div style={{ borderTop: `1px solid ${C.line}`, margin: '4px 0 0' }} />
      <div style={{ fontWeight: 600 }}>글자{edLive && <span style={{ fontWeight: 400, fontSize: 11, color: C.muted }}> · 고른 글자에(없으면 전체)</span>}</div>
      {textRows}
    </>}
  </div>
}
