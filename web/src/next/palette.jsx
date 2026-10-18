// 좌상 「도형·심볼」 카드 — 데스크톱 첫 화면 좌상 카드(`host_ui` 팔레트): ★ 즐겨찾기 · 기본 도형 8종 · 내 심볼 폴더들.
// 내 심볼은 데스크톱과 같은 파일(`symbol_library/symbol_library.json`, 서버 `/api/symbols`)을 읽기만 한다(등록·폴더 고치기는 데스크톱에서).
// 칸 제목 줄 색 = 데스크톱 규칙(2026-10-12): 사용자가 고른 색만, 안 고른 폴더는 회색·기본 도형은 연한 파랑. 버튼 = 그림 + 짧은 이름.
import { useEffect, useState } from 'react'
import SYMBOLS from '../symbols.json' with { type: 'json' }
import { symbolPath } from './symbols.js'

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

const shapeIcon = key => { const k = key.replace(/^sym:/, '')
  return <svg width="30" height="20" viewBox="-1 -1 32 22" fill="none" stroke="currentColor" strokeWidth="1.4">
    {k === 'rect' ? <rect x="0" y="0" width="30" height="20" /> : k === 'ellipse' ? <ellipse cx="15" cy="10" rx="15" ry="10" /> : <path d={symbolPath(k, 30, 20).d} />}</svg> }

function Cell({ k, name, icon, on, onDown, onClick }) {
  return <button title={`${name} — 클릭하면 그리기, 칠판으로 끌면 바로 놓기`} aria-pressed={on} onPointerDown={e => onDown(e, k)} onClick={() => onClick(k)}
    style={{ all: 'unset', boxSizing: 'border-box', cursor: 'pointer', width: 40, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, padding: '4px 0', borderRadius: 6,
      background: on ? 'rgba(218,119,86,.22)' : 'transparent', color: C.ink }}>
    <span style={{ height: 24, display: 'flex', alignItems: 'center' }}>{icon}</span>
    <span style={{ font: "500 10px 'Pretendard', sans-serif", maxWidth: 40, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{name}</span>
  </button>
}
function Section({ title, color, count, children }) {
  return <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 6px', borderRadius: 5, background: color ? `color-mix(in srgb, ${color} 35%, transparent)` : 'transparent', font: "600 12px 'Pretendard', sans-serif" }}>
      <span style={{ flex: 1, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{title}</span>
      {count != null && <span style={{ font: "400 11px 'Pretendard', sans-serif", color: C.muted }}>{count}</span>}</div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 40px)', gap: 2, justifyContent: 'space-between' }}>{children}</div>
  </div>
}

// lib = 서버 심볼 파일(없으면 기본 도형만), tool = 지금 도구, onDown/onClick = 끌기 시작/클릭(main.jsx paletteDown·setTool)
export function Palette({ lib, tool, onDown, onClick, dark }) {
  const [q, setQ] = useState('')
  const syms = lib?.symbols || [], folders = lib?.folders || [], fav = lib?.favorites || []
  const basicName = Object.fromEntries(BASIC)
  const thumb = e => <img alt="" src={'data:image/png;base64,' + e.thumb} width="24" height="24" style={{ filter: dark ? 'invert(1) hue-rotate(180deg)' : undefined }} />   // 그림은 밝은 칠판 기준으로 찍혀 있음
  const cellOf = key => {
    if (key.startsWith('customsym:')) { const e = syms.find(s => 'customsym:' + s.id === key); return e && <Cell key={key} k={key} name={e.name} icon={thumb(e)} on={tool === key} onDown={onDown} onClick={onClick} /> }
    const name = basicName[key] || SYMBOLS[key.replace(/^sym:/, '')]?.name; return name && <Cell key={key} k={key} name={name} icon={shapeIcon(key)} on={tool === key} onDown={onDown} onClick={onClick} />
  }
  return <div onPointerDown={e => e.stopPropagation()} style={{ pointerEvents: 'auto', width: 192, boxSizing: 'border-box', minHeight: 0, flex: '0 1 auto', overflowY: 'auto',
    background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: '8px 8px 10px', boxShadow: '0 2px 8px rgba(0,0,0,.06)', color: C.ink, display: 'flex', flexDirection: 'column', gap: 8, userSelect: 'none' }}>
    <div style={{ font: "700 15px 'Pretendard', sans-serif" }}>도형·심볼</div>
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
