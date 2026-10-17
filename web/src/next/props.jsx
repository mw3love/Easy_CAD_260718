// 오른쪽 위 「속성」 카드(고를 때만) — 3단계는 화살표 칸만(종류·화살촉·머리 크기·선 색·굵기·점선·모서리). 4단계 속성 칸이 여기서 넓어진다.
// 데스크톱 `host_ui` 속성 카드와 같은 자리·같은 항목. 첫 화면 규칙(CLAUDE.md): 폭 192, 제목 15px 굵게, 켜짐만 코랄, 자주 안 바꾸는 값은 현재 값 버튼 → 펼침.
import { useState } from 'react'

const C = { ink: '#27272a', muted: '#71717a', line: '#e4e4e7', card: '#ffffff', seg: '#f4f4f5', on: '#da7756', onBg: '#fbeee8' }
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
// − 값 + (휠로도)
function Stepper({ value, min, max, step = 1, fmt = v => v, onChange, title }) {
  const set = v => onChange(Math.round(Math.min(max, Math.max(min, v)) / step) * step)
  return <div title={title} onWheel={e => set(value + (e.deltaY < 0 ? step : -step))} style={{ display: 'flex', alignItems: 'center', background: C.seg, borderRadius: 8, padding: 2 }}>
    <button onClick={() => set(value - step)} style={btn(false, { width: 22 })}>−</button>
    <span style={{ minWidth: 34, textAlign: 'center', fontVariantNumeric: 'tabular-nums', fontSize: 12 }}>{fmt(value)}</span>
    <button onClick={() => set(value + step)} style={btn(false, { width: 22 })}>+</button>
  </div>
}

// a = 첫 화살표(보여 줄 값), kind = 'straight'|'curved'|'ortho', set(patch|kind, 이름, 묶음 열쇠)
export function ArrowProps({ a, kind, set, onKind }) {
  const [openDash, setOpenDash] = useState(false)
  const head = a.head !== false ? (a.head_start ? 'both' : 'end') : a.head_start ? 'start' : 'none'
  const color = (a.color || '').replace(/^#ff(?=[0-9a-f]{6}$)/i, '#')
  return <div onPointerDown={e => e.stopPropagation()} style={{ position: 'absolute', right: 12, top: 12, width: 192, boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10,
    padding: '8px 10px 10px', boxShadow: '0 2px 8px rgba(0,0,0,.06)', font: "400 13px 'Pretendard', sans-serif", color: C.ink, display: 'flex', flexDirection: 'column', gap: 4, userSelect: 'none' }}>
    <div style={{ font: "700 15px 'Pretendard', sans-serif", marginBottom: 2 }}>속성</div>
    <Row label="종류"><Seg value={kind} onPick={onKind} items={[['straight', ICONS.straight, '직선'], ['curved', ICONS.curved, '곡선'], ['ortho', ICONS.ortho, '직각']]} /></Row>
    <Row label="화살촉"><Seg value={head} onPick={h => set({ head: h === 'end' || h === 'both', head_start: h === 'start' || h === 'both' }, '화살촉')}
      items={[['none', ICONS.none, '없음'], ['end', ICONS.end, '끝만'], ['both', ICONS.both, '양쪽'], ['start', ICONS.start, '시작만']]} /></Row>
    <Row label="머리"><Stepper title="화살촉 크기 배율" value={a.head_scale ?? 1} min={0.5} max={3} step={0.1} fmt={v => v.toFixed(1) + '×'} onChange={v => set({ head_scale: v }, '머리 크기', 'head_scale')} /></Row>
    <Row label="색"><div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 14px)', gap: 3 }}>
      {ARROW_COLORS.map((c, i) => { if (!c) return <label key={i} title="다른 색" style={{ width: 14, height: 14, borderRadius: 4, cursor: 'pointer', background: 'conic-gradient(#f33,#fc0,#3c6,#39f,#c3f,#f33)', position: 'relative', overflow: 'hidden' }}>
          <input type="color" value={/^#[0-9a-f]{6}$/i.test(color) ? color : '#1f1f1f'} onChange={e => set({ color: e.target.value }, '색', 'color')} style={{ opacity: 0, position: 'absolute', inset: 0, cursor: 'pointer' }} /></label>
        const on = color.toLowerCase() === c.toLowerCase()
        return <button key={i} title={c} aria-pressed={on} onClick={() => set({ color: c }, '색')} style={{ all: 'unset', cursor: 'pointer', width: 14, height: 14, borderRadius: 4, background: c,
          boxShadow: on ? `0 0 0 2px #fff, 0 0 0 3.5px ${C.on}` : 'inset 0 0 0 1px rgba(0,0,0,.15)' }} /> })}
    </div></Row>
    <Row label="굵기"><Stepper title="선 굵기" value={a.width ?? 2} min={1} max={40} onChange={v => set({ width: v }, '굵기', 'width')} fmt={v => v + 'px'} /></Row>
    <Row label="선"><div style={{ position: 'relative', flex: 1 }}>
      <button title="선 모양" onClick={() => setOpenDash(o => !o)} style={btn(false, { width: '100%', background: C.seg, justifyContent: 'space-between', padding: '0 8px' })}>{dashIcon(a.style || 1)}<span style={{ color: C.muted }}>▾</span></button>
      {openDash && <div style={{ position: 'absolute', zIndex: 2, top: 28, left: 0, right: 0, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, padding: 3, boxShadow: '0 4px 12px rgba(0,0,0,.1)' }}>
        {STYLES.map(([st, name]) => <button key={st} title={name} onClick={() => { set({ style: st }, '선 모양'); setOpenDash(false) }} style={btn((a.style || 1) === st, { width: '100%', justifyContent: 'space-between', padding: '0 8px' })}>
          {dashIcon(st)}<span style={{ fontSize: 11, color: C.muted }}>{name}</span></button>)}
      </div>}
    </div></Row>
    {kind === 'ortho' && <Row label="모서리"><Stepper title="꺾인 곳 둥글기(0 = 각짐)" value={a.curve_r ?? 10} min={0} max={40} onChange={v => set({ curve_r: v }, '모서리', 'curve_r')} /></Row>}
  </div>
}
