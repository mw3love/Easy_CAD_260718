// 색 칸 · 색 창 — 속성 카드(선·채움·글자)와 드래그 꾸미기 막대(글자색)가 같이 씀(2026-10-23 사용자: 두 곳이 같은 모양이어야).
// 칸 = [견본][코드][진하기%] 한 덩이 — 어디를 눌러도 색 창(누를 자리가 넓게). 채움 칸은 휠 = 진하기 5%씩.
// 색 창 = 맨 위 코드(열리면 선택돼 있어 바로 치면 바뀜) + 16색 두 줄 + 최근 쓴 색, 채움만 아래 「없음」·진하기(휠로도).
// 견본을 눌러도 창은 열린 채(눌러 가며 비교) — 닫기는 바깥 누르기·Esc(여는 쪽이 맡음). 화면 위에 떠서(포털) 카드에 잘리지 않고, 아래가 모자라면 위로.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)', on: '#da7756', onBg: 'var(--mb-onbg)' }
// 두 줄 꽉 채움(8+8) — 데스크톱 색 창과 같은 짜임: 진한 6색(`_COLOR_GRID_HUES`) + 검정 + 다른 색 / 같은 6색의 연한 색(Qt lighter(150)) + 회색 + 흰색
export const ARROW_COLORS = ['#FF3B30', '#FF9500', '#FFCC00', '#34C759', '#007AFF', '#AF52DE', '#000000', null,
  '#ffb4af', '#ffca7f', '#ffe57f', '#6eff93', '#7fbdff', '#e3acff', '#9e9e9e', '#ffffff']
const hex2 = n => Math.round(n).toString(16).padStart(2, '0')
export const argbCss = c => { if (!c) return 'transparent'; const a = parseInt(c.slice(1, 3), 16) / 255; return `rgba(${parseInt(c.slice(3, 5), 16)},${parseInt(c.slice(5, 7), 16)},${parseInt(c.slice(7, 9), 16)},${a.toFixed(3)})` }
// 최근 쓴 색 = 이 브라우저만(편의용 — 못 읽으면 줄이 안 보일 뿐)
const RECENT_KEY = 'mb-recent-colors'
export const rgbOf = c => (c && c.length === 9 ? '#' + c.slice(3) : c || '').toLowerCase()
const loadRecent = () => { try { return (JSON.parse(localStorage.getItem(RECENT_KEY) || '[]') || []).filter(c => /^#[0-9a-f]{6}$/.test(c)).slice(0, 8) } catch { return [] } }
const pushRecent = c => { const v = rgbOf(c); if (!/^#[0-9a-f]{6}$/.test(v)) return; try { localStorage.setItem(RECENT_KEY, JSON.stringify([v, ...loadRecent().filter(x => x !== v)].slice(0, 8))) } catch { /* 저장 못 해도 그만 */ } }
const alphaOf = c => (c && c.length === 9 ? parseInt(c.slice(1, 3), 16) : 255)
const withAlpha = (rgb, a) => '#' + hex2(Math.max(0, Math.min(255, a))) + rgbOf(rgb).slice(1)
const FILL_NEW_ALPHA = 0x55   // 채움 없던 것에 처음 칠하면 약 1/3 진하기 — 옛 채움 견본(데스크톱 `_DEFAULT_FILL_PRESETS`)과 같아 칠해도 글이 읽힘
const pct = a => Math.round(a / 2.55), fromPct = p => Math.round(Math.max(0, Math.min(100, p)) * 255 / 100)
const MONO = '12px ui-monospace, Consolas, monospace'
const NoneMark = ({ s }) => <svg width={s} height={s} style={{ position: 'absolute', inset: 0 }}><line x1="2" y1={s - 2} x2={s - 2} y2="2" stroke="#e02424" strokeWidth="1.4" /></svg>
// 휠 = 진하기 5%씩(브라우저 기본 스크롤 막기 — React onWheel은 막을 수 없어 직접 붙임)
function useWheel(ref, f) { const fr = useRef(f); fr.current = f
  useEffect(() => { const el = ref.current; if (!el) return; const h = e => { if (!fr.current) return; e.preventDefault(); e.stopPropagation(); fr.current(e.deltaY < 0 ? 1 : -1) }; el.addEventListener('wheel', h, { passive: false }); return () => el.removeEventListener('wheel', h) }) }

// 색 견본 8+8(마지막 칸 = 다른 색). value = 지금 색(서로 다르면 '' — 아무것도 안 켬)
function ColorGrid({ value, onPick, s = 18 }) {   // onPick(색, 끌기 중이면 true — 되돌리기 한 칸으로 묶음)
  return <div data-testid="color-grid" style={{ display: 'grid', gridTemplateColumns: `repeat(8, ${s}px)`, gap: 2, justifyContent: 'space-between' }}>
    {ARROW_COLORS.map((c, i) => { if (!c) return <label key={i} title="다른 색" style={{ width: s, height: s, borderRadius: 4, cursor: 'pointer', background: 'conic-gradient(#f33,#fc0,#3c6,#39f,#c3f,#f33)', position: 'relative', overflow: 'hidden' }}>
        <input type="color" value={/^#[0-9a-f]{6}$/.test(value) ? value : '#1f1f1f'} onChange={e => onPick(e.target.value, true)} style={{ opacity: 0, position: 'absolute', inset: 0, cursor: 'pointer' }} /></label>
      const on = value === c.toLowerCase()
      return <button key={i} title={c} aria-pressed={on} onClick={() => onPick(c)} style={{ all: 'unset', cursor: 'pointer', width: s, height: s, borderRadius: 4, background: c,
        boxShadow: on ? `0 0 0 2px #fff, 0 0 0 3.5px ${C.on}` : 'inset 0 0 0 1px rgba(0,0,0,.15)' }} /> })}
  </div>
}
// 색 창 자리 — 기준(칸·버튼) 바로 아래(오른쪽 끝 맞춤), 아래가 모자라면 위로. 화면 밖으로는 안 나감
function popPlace(el, h, align) {
  const r = el.getBoundingClientRect(), W = 172, vw = window.innerWidth, vh = window.innerHeight
  const left = Math.max(8, Math.min(vw - W - 8, align === 'left' ? r.left : r.right - W)), below = r.bottom + 4
  return { left, top: below + h <= vh - 8 ? below : Math.max(8, r.top - 4 - h) }
}

// 펼침 목록(선 모양·도형 바꾸기 등) — 색 창처럼 화면 위에 떠서(포털) 카드에 잘리지 않음, 아래가 모자라면 위로(2026-10-23 전수조사: 카드 안에 펼쳐 스크롤이 생겼음)
// anchor = 기준 요소 ref, id = data-ppop 이름(여는 쪽의 바깥 누르기 판정), width = 폭(없으면 기준 폭), maxHeight = 넘치면 목록 안에서 스크롤
export function FloatPanel({ anchor, id, width, maxHeight = 360, children, testid }) {
  const el = useRef(null), [at, setAt] = useState(null)
  const place = () => { if (!anchor.current || !el.current) return; const r = anchor.current.getBoundingClientRect(), W = width || r.width, h = el.current.offsetHeight, vw = window.innerWidth, vh = window.innerHeight
    const p = { left: Math.max(8, Math.min(vw - W - 8, r.left)), top: r.bottom + 4 + h <= vh - 8 ? r.bottom + 4 : Math.max(8, r.top - 4 - h), w: W }
    if (!at || p.left !== at.left || p.top !== at.top || p.w !== at.w) setAt(p) }
  useLayoutEffect(place)
  useEffect(() => { window.addEventListener('resize', place); return () => window.removeEventListener('resize', place) })
  return createPortal(<div ref={el} data-ppop={id} data-keep-edit data-testid={testid} onPointerDown={e => e.stopPropagation()}
    style={{ position: 'fixed', zIndex: 70, left: at?.left ?? -9999, top: at?.top ?? -9999, width: at?.w ?? width ?? 160, boxSizing: 'border-box', maxHeight, overflowY: 'auto', background: C.card, color: C.ink, border: `1px solid ${C.line}`, borderRadius: 8, padding: 3, boxShadow: '0 8px 24px rgba(0,0,0,.18)', font: "400 12px 'Pretendard', sans-serif" }}>{children}</div>, document.body)
}

// 색 창. anchor = 기준 요소 ref, id = data-ppop 이름(여는 쪽의 바깥 누르기 판정), value·fill은 ColorChip과 같음, onPick(색, 끌기 중)
export function ColorPop({ anchor, id, value, fill, onPick, align, keepEdit, onReset }) {   // onReset = 「기본」(꾸미기 막대 글자색 — 색 지우기)
  const mixed = value === '' || value === undefined, none = fill ? value === null : !mixed && alphaOf(value) === 0
  const a = fill && value ? alphaOf(value) : 255
  const pick = (c, drag) => { onPick(c, drag); if (!drag && c) pushRecent(c) }
  const rgbPick = (c, drag) => pick(fill ? withAlpha(c, value ? a : FILL_NEW_ALPHA) : rgbOf(c), drag)   // 채움 = 지금 진하기 그대로(없음이었으면 1/3)
  const popEl = useRef(null), [at, setAt] = useState(null), codeEl = useRef(null), [txt, setTxt] = useState(null), slider = useRef(null)
  useLayoutEffect(() => { const place = () => anchor.current && popEl.current && setAt(popPlace(anchor.current, popEl.current.offsetHeight, align)); place()
    window.addEventListener('resize', place); return () => window.removeEventListener('resize', place) }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  useLayoutEffect(() => { if (at && popEl.current && anchor.current) { const p = popPlace(anchor.current, popEl.current.offsetHeight, align); if (p.top !== at.top || p.left !== at.left) setAt(p) } })   // 최근 줄이 생기는 등 높이가 바뀌면
  useEffect(() => { if (!keepEdit) { codeEl.current?.focus(); codeEl.current?.select() } }, [])   // eslint-disable-line react-hooks/exhaustive-deps — 열리면 코드가 골라진 채(바로 치면 바뀜). 글 고치는 중이면 편집기 포커스를 안 뺏음
  useWheel(slider, fill && value ? d => onPick(withAlpha(value, fromPct(pct(a) + d * 5)), true) : null)
  const shown = txt ?? (mixed || none ? '' : rgbOf(value).slice(1).toUpperCase())
  const applyCode = () => { const m = /^#?([0-9a-f]{6}|[0-9a-f]{8})$/i.exec((txt ?? '').trim()); setTxt(null); if (!m) return
    const c = m[1].length === 8 && fill ? '#' + m[1].toLowerCase() : '#' + m[1].slice(-6).toLowerCase(); pick(fill ? (c.length === 9 ? c : withAlpha(c, value ? a : 255)) : c) }
  return createPortal(<div ref={popEl} data-ppop={id} data-keep-edit data-testid={'pop-' + id} onPointerDown={e => e.stopPropagation()}
    onMouseDown={e => { if (keepEdit && e.target.tagName !== 'INPUT') e.preventDefault() }}   // 글 고치는 중 = 편집기 포커스(고른 글자)를 지킴
    style={{ position: 'fixed', zIndex: 70, left: at?.left ?? -9999, top: at?.top ?? -9999, width: 172, boxSizing: 'border-box', background: C.card, color: C.ink, border: `1px solid ${C.line}`, borderRadius: 10, padding: 8, boxShadow: '0 8px 24px rgba(0,0,0,.18)', display: 'flex', flexDirection: 'column', gap: 6, font: "400 12px 'Pretendard', sans-serif" }}>
    <label style={{ display: 'flex', alignItems: 'center', gap: 2, height: 26, padding: '0 6px', boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, font: MONO, color: C.muted }}>#
      <input ref={codeEl} data-testid="color-code" value={shown} placeholder={onReset ? '기본' : mixed ? '서로 다름' : '코드'} spellCheck={false} title={fill ? '색 코드 — 치고 Enter(8자리면 진하기까지)' : '색 코드 — 치고 Enter'}
        onChange={e => setTxt(e.target.value)} onFocus={e => e.currentTarget.select()} onBlur={() => txt != null && applyCode()}
        onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') applyCode(); if (e.key === 'Escape') { if (txt != null) setTxt(null); else e.currentTarget.blur() } }}
        style={{ all: 'unset', flex: 1, minWidth: 0, font: MONO, color: C.ink }} />
      {onReset && <button data-testid="color-reset" title="기본 색으로(색 지우기)" onClick={onReset} style={{ all: 'unset', cursor: 'pointer', padding: '1px 6px', borderRadius: 5, background: C.seg, color: C.ink, font: "400 11px 'Pretendard', sans-serif" }}>기본</button>}</label>
    <ColorGrid value={mixed || none ? '' : rgbOf(value)} onPick={rgbPick} />
    {(() => { const recent = loadRecent(); return recent.length > 0 && <><span style={{ fontSize: 11, color: C.muted }}>최근 쓴 색</span>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(8, 18px)', gap: 2, justifyContent: 'space-between' }}>{recent.map(c => <button key={c} title={c} onClick={() => rgbPick(c)} style={{ all: 'unset', cursor: 'pointer', width: 18, height: 18, borderRadius: 4, background: c, boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.15)' }} />)}</div></> })()}
    {fill && <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: C.muted }}>
      <button data-testid="fill-none" title="채움 없음" aria-pressed={none} onClick={() => pick(null)} style={{ all: 'unset', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, padding: '0 6px', height: 22, borderRadius: 6, fontSize: 11, color: none ? C.on : C.ink, background: none ? C.onBg : C.seg, outline: none ? `1px solid ${C.on}` : 'none' }}>
        <span style={{ position: 'relative', overflow: 'hidden', width: 12, height: 12, borderRadius: 3, background: '#fff', boxShadow: 'inset 0 0 0 1px rgba(0,0,0,.2)' }}><NoneMark s={12} /></span>없음</button>
      {value ? <><input ref={slider} data-testid="fill-alpha" type="range" min="0" max="100" title="진하기 — 낮을수록 비쳐요(휠로도)" value={pct(a)} onChange={e => onPick(withAlpha(value, fromPct(+e.target.value)), true)} style={{ flex: 1, minWidth: 0, accentColor: C.on }} />
        <span style={{ width: 30, textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>{pct(a)}%</span></> : <span style={{ flex: 1, whiteSpace: 'nowrap' }}>칠하면 진하기 33%</span>}
    </div>}
  </div>, document.body)
}

// 색 칸 — 한 덩이 버튼(어디를 눌러도 색 창). id = 이 칸 이름(한 번에 하나만 열림 — 여는 쪽 `pop`), value = 지금 색('#rrggbb'·'#aarrggbb', 없음 = null, 서로 다름 = ''/undefined)
// fill = 채움 칸(「없음」·진하기, 휠 = 진하기), onPick(색, 끌기 중) — 색 = 선·글은 '#rrggbb', 채움은 '#aarrggbb'|null
export function ColorChip({ id, pop, setPop, value, fill, onPick, title, keepEdit }) {
  const open = pop === id, mixed = value === '' || value === undefined, none = fill ? value === null : !mixed && alphaOf(value) === 0   // 선이 완전히 투명(채운 면의 선 등)이면 「없음」
  const a = fill && value ? alphaOf(value) : 255
  const chipBg = mixed ? 'conic-gradient(#9e9e9e 0 50%, #fff 0)' : none ? '#fff' : fill || value.length === 9 ? `linear-gradient(${argbCss(value)},${argbCss(value)}), #fff` : value
  const anchor = useRef(null)
  useWheel(anchor, fill && value ? d => onPick(withAlpha(value, fromPct(pct(a) + d * 5)), true) : null)
  return <div ref={anchor} data-ppop={id} style={{ flex: 1, minWidth: 0 }}>
    <button data-testid={'chip-' + id} title={fill && value ? title + ' — 눌러서 색 고르기 · 휠 = 진하기' : title + ' — 눌러서 색 고르기'} aria-label={title} aria-expanded={open} onClick={() => setPop(open ? null : id)}
      onMouseDown={e => { if (keepEdit) e.preventDefault() }}
      style={{ all: 'unset', cursor: 'pointer', boxSizing: 'border-box', width: '100%', display: 'flex', alignItems: 'center', gap: 6, height: 26, padding: '0 8px', borderRadius: 6, background: C.seg, outline: open ? `1px solid ${C.on}` : 'none' }}>
      <span style={{ position: 'relative', overflow: 'hidden', flex: 'none', width: 16, height: 16, borderRadius: 4, boxShadow: `inset 0 0 0 1px ${C.line}`, background: chipBg }}>{none && <NoneMark s={16} />}</span>
      <span style={{ flex: 1, minWidth: 0, font: mixed || none ? "12px 'Pretendard', sans-serif" : MONO, color: mixed || none ? C.muted : C.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{mixed ? '서로 다름' : none ? '없음' : rgbOf(value).slice(1).toUpperCase()}</span>
      {fill && value && a < 255 && <span style={{ flex: 'none', fontSize: 11, color: C.muted, fontVariantNumeric: 'tabular-nums' }}>{pct(a)}%</span>}
    </button>
    {open && <ColorPop anchor={anchor} id={id} value={value} fill={fill} onPick={onPick} keepEdit={keepEdit} />}
  </div>
}
