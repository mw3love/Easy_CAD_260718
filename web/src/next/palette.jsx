// 좌상 「도형·심볼」 카드 — 데스크톱 첫 화면 좌상 카드(`host_ui` 팔레트): ★ 즐겨찾기 · 기본 도형 8종 · 내 심볼 폴더들.
// 내 심볼은 데스크톱과 같은 파일(`symbol_library/symbol_library.json`, 서버 `/api/symbols`)을 읽기만 한다(등록·폴더 고치기는 데스크톱에서).
// 칸 제목 줄 색 = 데스크톱 규칙(2026-10-12): 사용자가 고른 색만, 안 고른 폴더는 회색·기본 도형은 연한 파랑. 버튼 = 그림 + 짧은 이름.
import { useEffect, useState } from 'react'
import { DOCKED, FoldBtn, useFold } from './fold.jsx'
import SYMBOLS from '../symbols.json' with { type: 'json' }
import { shapeWH, symbolPath } from './symbols.js'
import { Item } from './render.jsx'
import { drawOrder, itemBounds } from './doc.js'
import { fromEcad } from './model.js'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', on: '#da7756' }
export const BASIC = [['rect', '사각형'], ['ellipse', '원'], ['sym:triangle', '삼각형'], ['sym:decision', '판단'], ['sym:terminal', '시작/끝'], ['sym:data', '입출력'], ['sym:prep', '준비'], ['sym:database', '저장소']]
const FOLDER_GRAY = '#9e9e9e', BASIC_BLUE = '#7fbdff'
// 초성(데스크톱 검색 「이름·초성」, 예: ㅇㅌ) — 한글 음절은 첫소리로, 나머지는 그대로
const CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
const chosung = s => [...s].map(ch => { const c = ch.charCodeAt(0) - 0xac00; return c >= 0 && c < 11172 ? CHO[Math.floor(c / 588)] : ch }).join('')
export const nameMatch = (name, q) => { const n = name.toLowerCase(), k = q.trim().toLowerCase(); return !k || n.includes(k) || chosung(n).includes(k) }

export async function loadLibrary() {
  try { const r = await fetch('/api/symbols'); if (!r.ok) return null; return await r.json() } catch { return null }
}

// 내 심볼 아이콘 = 저장된 실제 도형으로 그림(2026-10-18 사용자: 야옹이 등이 두 화면 모두 안 보임 — 저장된 그림은 데스크톱 어두운 화면에서 찍은 28px 흰 선이라
// 밝은 화면에선 흰 바탕에, 어두운 화면에선 색 뒤집기로 검게 묻혔음). 잉크 색은 칠판 규칙(ink)대로 화면 밝기에 맞춤, 선은 1px 아래로 안 가늘어짐(--z)
const iconCache = new Map()
function SymIcon({ e, dark }) {
  let v = iconCache.get(e.id)
  if (!v) { let items = []; try { items = fromEcad({ items: structuredClone(e.items || []) }).items } catch { /* 못 읽으면 그림으로 */ }
    const bs = items.map(itemBounds).filter(b => Number.isFinite(b.x)), x0 = Math.min(...bs.map(b => b.x)), y0 = Math.min(...bs.map(b => b.y)), x1 = Math.max(...bs.map(b => b.x + b.w)), y1 = Math.max(...bs.map(b => b.y + b.h))
    v = bs.length ? { items, x0, y0, w: Math.max(1, x1 - x0), h: Math.max(1, y1 - y0) } : null; iconCache.set(e.id, v) }
  if (!v) return <img alt="" src={'data:image/png;base64,' + e.thumb} width="24" height="24" />
  const S = Math.max(v.w, v.h), pad = S * 0.06, k = 24 / (S + 2 * pad)
  return <svg key={dark ? 'd' : 'l'} width="24" height="24" viewBox={`${v.x0 + v.w / 2 - S / 2 - pad} ${v.y0 + v.h / 2 - S / 2 - pad} ${S + 2 * pad} ${S + 2 * pad}`} style={{ '--z': k, overflow: 'visible' }}>
    {drawOrder(v.items).map(([it, i]) => <Item key={i} it={it} idx={i} dark={dark} />)}</svg>
}

// 기본 도형 아이콘 = 칠판에 놓이는 기본 크기 비율 그대로(W×H 칸 가운데). 속성 카드 「도형 바꾸기」도 이걸 씀
export const shapeIcon = (key, W = 30, H = 20, sw = 1.4) => { const k = key.replace(/^sym:/, ''), [bw, bh] = shapeWH(key), s = Math.min(W / bw, H / bh), w = bw * s, h = bh * s
  return <svg width={W} height={H} viewBox={`-1 -1 ${W + 2} ${H + 2}`} fill="none" stroke="currentColor" strokeWidth={sw}><g transform={`translate(${(W - w) / 2} ${(H - h) / 2})`}>
    {k === 'rect' ? <rect x="0" y="0" width={w} height={h} /> : k === 'ellipse' ? <ellipse cx={w / 2} cy={h / 2} rx={w / 2} ry={h / 2} /> : <path d={symbolPath(k, w, h).d} />}</g></svg> }

function Cell({ k, name, icon, on, onDown, onClick }) {
  return <button title={`${name} — 클릭하면 그리기, 칠판으로 끌면 바로 놓기`} aria-pressed={on} onPointerDown={e => onDown(e, k)} onClick={() => onClick(k)}
    style={{ all: 'unset', boxSizing: 'border-box', cursor: 'pointer', width: 38, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, padding: '3px 0', borderRadius: 6,
      background: on ? 'rgba(218,119,86,.22)' : 'transparent', color: C.ink }}>
    <span style={{ height: 20, display: 'flex', alignItems: 'center', transform: 'scale(.82)' }}>{icon}</span>   {/* 한 단계 작게(2026-10-23 사용자: 조금 큼) */}
    <span style={{ font: "500 10px 'Pretendard', sans-serif", maxWidth: 38, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{name}</span>
  </button>
}
// 칸 격자 = auto-fill — 왼쪽 판을 넓히면 한 줄에 더(2026-10-23 판 폭 조절)
function Section({ title, color, count, children }) {
  return <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 6px', borderRadius: 5, background: color ? `color-mix(in srgb, ${color} 35%, transparent)` : 'transparent', font: "600 12px 'Pretendard', sans-serif" }}>
      <span style={{ flex: 1, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{title}</span>
      {count != null && <span style={{ font: "400 11px 'Pretendard', sans-serif", color: C.muted }}>{count}</span>}</div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, 38px)', gap: 2, justifyContent: 'space-between' }}>{children}</div>
  </div>
}

// lib = 서버 심볼 파일(없으면 기본 도형만), tool = 지금 도구, onDown/onClick = 끌기 시작/클릭(main.jsx paletteDown·setTool)
export function Palette({ lib, tool, onDown, onClick, dark, docked }) {
  const [f0, toggleFold] = useFold('shapes'), folded = !docked && f0
  const [q, setQ] = useState('')
  const syms = lib?.symbols || [], folders = lib?.folders || [], fav = lib?.favorites || []
  const basicName = Object.fromEntries(BASIC)
  const thumb = e => <SymIcon e={e} dark={dark} />
  const cellOf = key => {
    if (key.startsWith('customsym:')) { const e = syms.find(s => 'customsym:' + s.id === key); return e && <Cell key={key} k={key} name={e.name} icon={thumb(e)} on={tool === key} onDown={onDown} onClick={onClick} /> }
    const name = basicName[key] || SYMBOLS[key.replace(/^sym:/, '')]?.name; return name && <Cell key={key} k={key} name={name} icon={shapeIcon(key)} on={tool === key} onDown={onDown} onClick={onClick} />
  }
  return <div data-folded={folded || undefined} onPointerDown={e => e.stopPropagation()} style={{ pointerEvents: 'auto', width: 192, boxSizing: 'border-box', minHeight: 0, flex: '0 1 auto', overflowY: 'auto',
    background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: '8px 8px 10px', boxShadow: '0 2px 8px rgba(0,0,0,.06)', color: C.ink, display: 'flex', flexDirection: 'column', gap: 8, userSelect: 'none', ...(docked ? { ...DOCKED, flex: '1 1 auto' } : {}) }}>
    <div style={{ display: 'flex', alignItems: 'center' }}><span style={{ font: "700 15px 'Pretendard', sans-serif", flex: 1 }}>도형·심볼</span>{!docked && <FoldBtn folded={folded} onClick={toggleFold} />}</div>
    <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') setQ('') }} placeholder="도형·심볼 검색 (이름·초성)"
      title="이름 일부나 초성(예: ㅇㅌ)으로 찾기 — Esc로 지우기" style={{ boxSizing: 'border-box', width: '100%', height: 30, border: `1px solid ${C.line}`, borderRadius: 7, background: 'transparent', color: C.ink, font: "400 12px 'Pretendard', sans-serif", padding: '0 8px' }} />
    {/* 검색 중엔 즐겨찾기·기본 도형·폴더를 숨기고 기본 도형까지 한 목록으로(데스크톱 `_on_palette_search`) */}
    {q.trim() ? (() => { const hits = [...BASIC.filter(([, n]) => nameMatch(n, q)).map(([k]) => k), ...syms.filter(s => nameMatch(s.name, q)).map(s => 'customsym:' + s.id)]
      return hits.length ? <Section title="검색 결과" count={hits.length}>{hits.map(cellOf)}</Section> : <div style={{ fontSize: 12, color: C.muted }}>찾는 도형·심볼이 없어요</div> })() : <>
    {fav.length > 0 && <Section title={<><span style={{ color: C.on }}>★</span> 즐겨찾기</>} count={fav.length}>{fav.map(cellOf)}</Section>}
    <Section title="□○△ 기본 도형" color={lib?.section_colors?.basic || BASIC_BLUE} count={BASIC.length}>{BASIC.map(([k]) => cellOf(k))}</Section>
    {folders.map(f => { const list = syms.filter(s => s.folder === f); return <Section key={f} title={f} color={lib?.folder_colors?.[f] || FOLDER_GRAY} count={list.length}>{list.map(s => cellOf('customsym:' + s.id))}</Section> })}
    </>}
    {!lib && <div style={{ fontSize: 11, color: C.muted }}>내 심볼은 저장 서버를 켜면 보여요</div>}
  </div>
}

export function useLibrary() {
  const [lib, setLib] = useState(null)
  useEffect(() => { loadLibrary().then(setLib) }, [])
  return lib
}
