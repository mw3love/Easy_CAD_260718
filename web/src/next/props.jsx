// 오른쪽 위 「속성」 카드(고를 때만) — 3단계는 화살표 칸만(종류·화살촉·머리 크기·선 색·굵기·점선·모서리). 4단계 속성 칸이 여기서 넓어진다.
// 데스크톱 `host_ui` 속성 카드와 같은 자리·같은 항목. 첫 화면 규칙(CLAUDE.md): 폭 192, 제목 15px 굵게, 켜짐만 코랄, 자주 안 바꾸는 값은 현재 값 버튼 → 펼침.
import { useState } from 'react'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)', on: '#da7756', onBg: 'var(--mb-onbg)' }   // 화면 색 = next.html CSS 변수
// 두 줄 꽉 채움(8+8) — 데스크톱 색 창과 같은 짜임: 진한 6색(`_COLOR_GRID_HUES`) + 검정 + 다른 색 / 같은 6색의 연한 색(Qt lighter(150)) + 회색 + 흰색
export const ARROW_COLORS = ['#FF3B30', '#FF9500', '#FFCC00', '#34C759', '#007AFF', '#AF52DE', '#000000', null,
  '#ffb4af', '#ffca7f', '#ffe57f', '#6eff93', '#7fbdff', '#e3acff', '#9e9e9e', '#ffffff']
const STYLES = [[1, '실선'], [2, '점선'], [3, '도트'], [4, '일점쇄선'], [5, '이점쇄선']]
const DASH = { 1: undefined, 2: '6 3', 3: '1.5 3', 4: '6 3 1.5 3', 5: '6 3 1.5 3 1.5 3' }

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

// arrows = 고른 화살표 전부, kind = 모두 같은 종류면 그것('straight'|'curved'|'ortho'), 다르면 null
// set(patch | (화살표 → patch), 이름, 묶음 열쇠) — 함수면 화살표마다 따로(각자 ±)
// 값이 서로 다르면: 고르는 칸은 아무것도 안 켬(누르면 전부 그 값), 숫자 칸은 범위(데스크톱도 같은 규칙, 2026-10-18)
export function ArrowProps({ arrows, kind, set, onKind }) {
  const [openDash, setOpenDash] = useState(false)
  const one = f => { const v = arrows.map(f); return v.every(x => x === v[0]) ? v[0] : null }
  const head = one(a => (a.head !== false ? (a.head_start ? 'both' : 'end') : a.head_start ? 'start' : 'none'))
  const color = one(a => (a.color || '').replace(/^#ff(?=[0-9a-f]{6}$)/i, '#').toLowerCase()) ?? ''
  const style = one(a => a.style || 1)
  const num = (k, d0, min, max, step, name) => ({ values: arrows.map(a => a[k] ?? d0), step, onStep: d => set(a => ({ [k]: stepClamp(a[k] ?? d0, d, min, max, step) }), name, k) })
  return <div onPointerDown={e => e.stopPropagation()} style={{ position: 'absolute', right: 12, top: 12, width: 192, boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10,
    padding: '8px 10px 10px', boxShadow: '0 2px 8px rgba(0,0,0,.06)', font: "400 13px 'Pretendard', sans-serif", color: C.ink, display: 'flex', flexDirection: 'column', gap: 4, userSelect: 'none' }}>
    <div style={{ font: "700 15px 'Pretendard', sans-serif", marginBottom: 2 }}>속성{arrows.length > 1 && <span style={{ font: "400 12px 'Pretendard', sans-serif", color: C.muted }}> · 화살표 {arrows.length}개</span>}</div>
    <Row label="종류"><Seg value={kind} onPick={onKind} items={[['straight', ICONS.straight, '직선'], ['curved', ICONS.curved, '곡선'], ['ortho', ICONS.ortho, '직각']]} /></Row>
    <Row label="화살촉"><Seg value={head} onPick={h => set({ head: h === 'end' || h === 'both', head_start: h === 'start' || h === 'both' }, '화살촉')}
      items={[['none', ICONS.none, '없음'], ['end', ICONS.end, '끝만'], ['both', ICONS.both, '양쪽'], ['start', ICONS.start, '시작만']]} /></Row>
    <Row label="머리"><Stepper title="화살촉 크기 배율" {...num('head_scale', 1, 0.5, 3, 0.1, '머리 크기')} fmt={v => v.toFixed(1) + '×'} /></Row>
    <Row label="색"><div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 14px)', gap: 3 }}>
      {ARROW_COLORS.map((c, i) => { if (!c) return <label key={i} title="다른 색" style={{ width: 14, height: 14, borderRadius: 4, cursor: 'pointer', background: 'conic-gradient(#f33,#fc0,#3c6,#39f,#c3f,#f33)', position: 'relative', overflow: 'hidden' }}>
          <input type="color" value={/^#[0-9a-f]{6}$/.test(color) ? color : '#1f1f1f'} onChange={e => set({ color: e.target.value }, '색', 'color')} style={{ opacity: 0, position: 'absolute', inset: 0, cursor: 'pointer' }} /></label>
        const on = color === c.toLowerCase()   // 색이 서로 다르면 아무것도 안 켬
        return <button key={i} title={c} aria-pressed={on} onClick={() => set({ color: c }, '색')} style={{ all: 'unset', cursor: 'pointer', width: 14, height: 14, borderRadius: 4, background: c,
          boxShadow: on ? `0 0 0 2px #fff, 0 0 0 3.5px ${C.on}` : 'inset 0 0 0 1px rgba(0,0,0,.15)' }} /> })}
    </div></Row>
    <Row label="굵기"><Stepper title="선 굵기" {...num('width', 1, 1, 40, 1, '굵기')} fmt={v => v + 'px'} /></Row>
    <Row label="선"><div style={{ position: 'relative', flex: 1 }}>
      <button title="선 모양" onClick={() => setOpenDash(o => !o)} style={btn(false, { width: '100%', background: C.seg, justifyContent: 'space-between', padding: '0 8px' })}>{style ? dashIcon(style) : <span style={{ fontSize: 12, color: C.muted }}>서로 다름</span>}<span style={{ color: C.muted }}>▾</span></button>
      {openDash && <div style={{ position: 'absolute', zIndex: 2, top: 28, left: 0, right: 0, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, padding: 3, boxShadow: '0 4px 12px rgba(0,0,0,.1)' }}>
        {STYLES.map(([st, name]) => <button key={st} title={name} onClick={() => { set({ style: st }, '선 모양'); setOpenDash(false) }} style={btn(style === st, { width: '100%', justifyContent: 'space-between', padding: '0 8px' })}>
          {dashIcon(st)}<span style={{ fontSize: 11, color: C.muted }}>{name}</span></button>)}
      </div>}
    </div></Row>
    {kind === 'ortho' && <Row label="모서리"><Stepper title="꺾인 곳 둥글기(0 = 각짐)" {...num('curve_r', 10, 0, 40, 1, '모서리')} /></Row>}
  </div>
}
