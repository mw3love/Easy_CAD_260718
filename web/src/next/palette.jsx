// 좌상 「도형·심볼」 카드 — 데스크톱 첫 화면 좌상 카드(`host_ui` 팔레트): ★ 즐겨찾기 · 기본 도형 8종 · 내 심볼 폴더들.
// 함께 쓰는 심볼은 데스크톱과 같은 파일(`symbol_library/symbol_library.json`, 서버 `/api/symbols`)을 읽기만 한다(등록·폴더 고치기는 데스크톱에서).
// 「내 심볼 — 이 브라우저」(2026-10-27, `mysym.js`)는 여기서 폴더 만들기·이름 바꾸기·지우기·파일로 저장·불러오기, 넣기는 칠판 우클릭 「내 심볼에 추가」.
// 칸 제목 줄 색 = 데스크톱 규칙(2026-10-12): 사용자가 고른 색만, 안 고른 폴더는 회색·기본 도형은 연한 파랑. 버튼 = 그림 + 짧은 이름.
import { useEffect, useRef, useState } from 'react'
import { DOCKED, FoldBtn, useFold } from './fold.jsx'
import SYMBOLS from '../symbols.json' with { type: 'json' }
import { shapeWH, symbolPath } from './symbols.js'
import { Item } from './render.jsx'
import { drawOrder, itemBounds } from './doc.js'
import { fromEcad } from './model.js'
import { isMine, folderTitle } from './mysym.js'

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
function SymIcon({ e, dark, size = 24 }) {   // size = 크게 보기(마우스 올림)도 같은 그림
  let v = iconCache.get(e.id)
  if (!v) { let items = []; try { items = fromEcad({ items: structuredClone(e.items || []) }).items } catch { /* 못 읽으면 그림으로 */ }
    const bs = items.map(itemBounds).filter(b => Number.isFinite(b.x)), x0 = Math.min(...bs.map(b => b.x)), y0 = Math.min(...bs.map(b => b.y)), x1 = Math.max(...bs.map(b => b.x + b.w)), y1 = Math.max(...bs.map(b => b.y + b.h))
    v = bs.length ? { items, x0, y0, w: Math.max(1, x1 - x0), h: Math.max(1, y1 - y0) } : null; iconCache.set(e.id, v) }
  if (!v) return <img alt="" src={'data:image/png;base64,' + e.thumb} width={size} height={size} />
  const S = Math.max(v.w, v.h), pad = S * 0.06, k = size / (S + 2 * pad)
  return <svg key={dark ? 'd' : 'l'} width={size} height={size} viewBox={`${v.x0 + v.w / 2 - S / 2 - pad} ${v.y0 + v.h / 2 - S / 2 - pad} ${S + 2 * pad} ${S + 2 * pad}`} style={{ '--z': k, overflow: 'visible' }}>
    {drawOrder(v.items).map(([it, i]) => <Item key={i} it={it} idx={i} dark={dark} />)}</svg>
}

// 기본 도형 아이콘 = 칠판에 놓이는 기본 크기 비율 그대로(W×H 칸 가운데). 속성 카드 「도형 바꾸기」도 이걸 씀
export const shapeIcon = (key, W = 30, H = 20, sw = 1.4) => { const k = key.replace(/^sym:/, ''), [bw, bh] = shapeWH(key), s = Math.min(W / bw, H / bh), w = bw * s, h = bh * s
  return <svg width={W} height={H} viewBox={`-1 -1 ${W + 2} ${H + 2}`} fill="none" stroke="currentColor" strokeWidth={sw}><g transform={`translate(${(W - w) / 2} ${(H - h) / 2})`}>
    {k === 'rect' ? <rect x="0" y="0" width={w} height={h} /> : k === 'ellipse' ? <ellipse cx={w / 2} cy={h / 2} rx={w / 2} ry={h / 2} /> : <path d={symbolPath(k, w, h).d} />}</g></svg> }

function Cell({ k, name, icon, on, onDown, onClick, onPeek, onMenu }) {   // onMenu(e) = 우클릭(이 브라우저 심볼 — 이름 바꾸기·지우기)   // onPeek(칸 자리 | null) = 내 심볼 크게 보기(마우스 올림)
  return <button title={onPeek ? undefined : `${name} — 클릭하면 그리기, 칠판으로 끌면 바로 놓기`} aria-label={name} aria-pressed={on} onPointerDown={e => { onPeek?.(null); onDown(e, k) }} onClick={() => onClick(k)}
    onContextMenu={onMenu && (e => { e.preventDefault(); onPeek?.(null); onMenu(e) })} onPointerEnter={onPeek && (e => onPeek(e.currentTarget.getBoundingClientRect()))} onPointerLeave={onPeek && (() => onPeek(null))}
    style={{ all: 'unset', boxSizing: 'border-box', cursor: 'pointer', width: 38, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, padding: '3px 0', borderRadius: 6,
      background: on ? 'rgba(218,119,86,.22)' : 'transparent', color: C.ink }}>
    <span style={{ height: 20, display: 'flex', alignItems: 'center', transform: 'scale(.82)' }}>{icon}</span>   {/* 한 단계 작게(2026-10-23 사용자: 조금 큼) */}
    <span style={{ font: "500 10px 'Pretendard', sans-serif", maxWidth: 38, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{name}</span>
  </button>
}
// 칸 격자 = auto-fill — 왼쪽 판을 넓히면 한 줄에 더(2026-10-23 판 폭 조절)
// 칸 접기(2026-10-27 실검증 — 데스크톱처럼): 제목 줄을 누르면 접힘 ▸ / 펼침 ▾, 이 브라우저에 기억(`mb-pal-fold`, 칸 이름들)
const FOLD_KEY = 'mb-pal-fold'
function useSectionFold() {
  const [shut, setShut] = useState(() => { try { return new Set(JSON.parse(localStorage.getItem(FOLD_KEY) || '[]')) } catch { return new Set() } })
  const toggle = id => setShut(prev => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); try { localStorage.setItem(FOLD_KEY, JSON.stringify([...n])) } catch { /* 기억 못 해도 그만 */ } return n })
  return [shut, toggle]
}
function Section({ title, color, count, children, shut, onToggle, onMenu, folder, lit }) {   // folder = 끌어 놓기 받는 이 브라우저 폴더 이름, lit = 그 위로 끌고 있음   // onMenu(e) = 제목 줄 ⋯(이 브라우저 폴더)
  return <div data-testid="pal-sec" data-shut={shut || undefined} data-symfolder={folder} style={{ display: 'flex', flexDirection: 'column', gap: 2, borderRadius: 6, ...(lit ? { outline: `2px solid ${C.on}`, outlineOffset: 1 } : {}) }}>
    <div onClick={onToggle} title={onToggle ? (shut ? '누르면 펼치기' : '누르면 접기') : undefined} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 6px', borderRadius: 5, cursor: onToggle ? 'pointer' : 'default', background: color ? `color-mix(in srgb, ${color} 35%, transparent)` : 'transparent', font: "600 12px 'Pretendard', sans-serif" }}>
      {onToggle && <span aria-hidden style={{ width: 8, fontSize: 9, color: C.muted }}>{shut ? '▸' : '▾'}</span>}
      <span style={{ flex: 1, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{title}</span>
      {count != null && <span style={{ font: "400 11px 'Pretendard', sans-serif", color: C.muted }}>{count}</span>}
      {onMenu && <button data-testid="folder-menu" title="폴더 이름 바꾸기·지우기" onClick={e => { e.stopPropagation(); onMenu(e) }} style={{ all: 'unset', cursor: 'pointer', padding: '0 3px', borderRadius: 4, color: C.muted, font: "700 12px 'Pretendard', sans-serif" }}>⋯</button>}</div>
    {!shut && <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, 38px)', gap: 2, justifyContent: 'space-between' }}>{children}</div>}
  </div>
}

// lib = 서버 심볼 파일(없으면 기본 도형만), tool = 지금 도구, onDown/onClick = 끌기 시작/클릭(main.jsx paletteDown·setTool)
export function Palette({ lib, tool, onDown, onClick, dark, docked, mine, say }) {   // mine = { mine, api } 이 브라우저 심볼(`useMySymbols`), say = 알림
  const [f0, toggleFold] = useFold('shapes'), folded = !docked && f0
  const [q, setQ] = useState('')
  const [shut, toggle] = useSectionFold()
  const [peek, setPeekS] = useState(null), peekT = useRef(0)   // 내 심볼 크게 보기 = { e, r(칸 자리) } — 0.3초 올려 두면(지나가며 스치는 칸은 안 뜨게)
  const root = useRef(null)
  const peekAt = e => r => { clearTimeout(peekT.current); if (!r) { setPeekS(null); return } peekT.current = setTimeout(() => setPeekS({ e, r, x: root.current?.getBoundingClientRect().right ?? r.right }), 300) }   // x = 판 오른쪽 밖(판 안 칸을 가리지 않게)
  useEffect(() => () => clearTimeout(peekT.current), [])
  const [drop, setDrop] = useState(null)   // 칠판에서 끄는 도형이 이 칸 위 = { folder }(Editor `mb-symdrag`)
  useEffect(() => { const on = e => setDrop(e.detail); window.addEventListener('mb-symdrag', on); return () => window.removeEventListener('mb-symdrag', on) }, [])
  // 이 브라우저 심볼 관리 — pop = { x, y, menu: [[이름, 할 일]] } 또는 { x, y, ask: { label, value, ok(글) } }(이름 묻기 — 브라우저 확인 창은 안 씀)
  const [pop, setPop] = useState(null), file = useRef(null)
  const near = (x, y) => ({ x: Math.min(x, window.innerWidth - 220), y })
  const below = e => { const r = e.currentTarget.getBoundingClientRect(); return near(r.left, r.bottom + 2) }
  const folderMenu = f => e => { const n = folderTitle(f), cnt = syms.filter(s => s.folder === f).length, p = below(e)
    setPop({ ...p, menu: [['이름 바꾸기', () => setPop({ ...p, ask: { label: '폴더 이름', value: n, ok: v => mine.api.renameFolder(n, v) } })],
      [cnt ? `지우기 (심볼 ${cnt}개도)` : '지우기', () => { mine.api.delFolder(n); say?.(`「${n}」 폴더를 지웠어요`) }]] }) }
  const symMenu = s => e => { const p = near(e.clientX, e.clientY)
    setPop({ ...p, menu: [['이름 바꾸기', () => setPop({ ...p, ask: { label: '심볼 이름', value: s.name, ok: v => mine.api.renameSymbol(s.id, v) } })],
      ['지우기', () => { mine.api.delSymbol(s.id); say?.(`「${s.name}」 심볼을 지웠어요`) }]] }) }
  useEffect(() => { if (!pop?.menu) return; const close = () => setPop(null); window.addEventListener('pointerdown', close); return () => window.removeEventListener('pointerdown', close) }, [pop])
  const download = () => { const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([mine.api.exportText()], { type: 'application/json' })); a.download = '내 심볼.json'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000) }
  const syms = lib?.symbols || [], folders = lib?.folders || [], fav = lib?.favorites || []
  const basicName = Object.fromEntries(BASIC)
  const thumb = e => <SymIcon e={e} dark={dark} />
  const cellOf = key => {
    if (key.startsWith('customsym:')) { const e = syms.find(s => 'customsym:' + s.id === key); return e && <Cell key={key} k={key} name={e.name} icon={thumb(e)} on={tool === key} onDown={onDown} onClick={onClick} onPeek={peekAt(e)} onMenu={mine && isMine(e.folder) ? symMenu(e) : undefined} /> }
    const name = basicName[key] || SYMBOLS[key.replace(/^sym:/, '')]?.name; return name && <Cell key={key} k={key} name={name} icon={shapeIcon(key)} on={tool === key} onDown={onDown} onClick={onClick} />
  }
  return <div ref={root} data-folded={folded || undefined} data-symdrop={mine ? '' : undefined} onPointerDown={e => e.stopPropagation()} style={{ pointerEvents: 'auto', width: 192, boxSizing: 'border-box', minHeight: 0, flex: '0 1 auto', overflowY: 'auto',
    background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: '8px 8px 10px', boxShadow: '0 2px 8px rgba(0,0,0,.06)', color: C.ink, display: 'flex', flexDirection: 'column', gap: 8, userSelect: 'none', ...(docked ? { ...DOCKED, flex: '1 1 auto' } : {}), ...(drop ? { boxShadow: `inset 0 0 0 2px ${C.on}` } : {}) }}>   {/* 끄는 도형이 위 = 코랄 테두리 */}
    {drop && (r => <div data-testid="symdrop-hint" style={{ position: 'fixed', left: r.left, top: r.top, width: r.width, boxSizing: 'border-box', zIndex: 45, pointerEvents: 'none', padding: '8px 10px', background: C.on, color: '#fff', font: "600 12px 'Pretendard', sans-serif" }}>
      {drop.folder ? `여기 놓으면 「${drop.folder}」에 추가` : '여기 놓으면 내 심볼에 추가'}</div>)(root.current.getBoundingClientRect())}   {/* 칸 위에 떠 있음 — 흐름에 끼우면 내용이 밀려 놓을 자리가 어긋났음 */}
    <div style={{ display: 'flex', alignItems: 'center' }}><span style={{ font: "700 15px 'Pretendard', sans-serif", flex: 1 }}>도형·심볼</span>{!docked && <FoldBtn folded={folded} onClick={toggleFold} />}</div>
    <input value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') setQ('') }} placeholder="도형·심볼 검색 (이름·초성)"
      title="이름 일부나 초성(예: ㅇㅌ)으로 찾기 — Esc로 지우기" style={{ boxSizing: 'border-box', width: '100%', height: 30, border: `1px solid ${C.line}`, borderRadius: 7, background: 'transparent', color: C.ink, font: "400 12px 'Pretendard', sans-serif", padding: '0 8px' }} />
    {/* 검색 중엔 즐겨찾기·기본 도형·폴더를 숨기고 기본 도형까지 한 목록으로(데스크톱 `_on_palette_search`) */}
    {q.trim() ? (() => { const hits = [...BASIC.filter(([, n]) => nameMatch(n, q)).map(([k]) => k), ...syms.filter(s => nameMatch(s.name, q)).map(s => 'customsym:' + s.id)]
      return hits.length ? <Section title="검색 결과" count={hits.length}>{hits.map(cellOf)}</Section> : <div style={{ fontSize: 12, color: C.muted }}>찾는 도형·심볼이 없어요</div> })() : <>
    {fav.length > 0 && <Section title={<><span style={{ color: C.on }}>★</span> 즐겨찾기</>} count={fav.length} shut={shut.has('★')} onToggle={() => toggle('★')}>{fav.map(cellOf)}</Section>}
    <Section title="기본 도형" color={lib?.section_colors?.basic || BASIC_BLUE} count={BASIC.length} shut={shut.has('□')} onToggle={() => toggle('□')}>{BASIC.map(([k]) => cellOf(k))}</Section>
    {folders.filter(f => !isMine(f)).map(f => { const list = syms.filter(s => s.folder === f); return <Section key={f} title={f} color={lib?.folder_colors?.[f] || FOLDER_GRAY} count={list.length} shut={shut.has('f:' + f)} onToggle={() => toggle('f:' + f)}>{list.map(s => cellOf('customsym:' + s.id))}</Section> })}
    {mine && <div data-testid="mine" style={{ display: 'flex', flexDirection: 'column', gap: 6, ...(folders.some(f => !isMine(f)) ? { borderTop: `1px solid ${C.line}`, paddingTop: 8 } : {}) }}>   {/* 예시를 복사한 뒤엔 서버 폴더가 없어 구분선도 없음 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexWrap: 'wrap' }}>
        <span title="이 브라우저에 저장돼요 — 다른 PC·브라우저로 옮기려면 ⋯ 「파일로 저장」 → 「파일 불러오기」" style={{ flex: 1, whiteSpace: 'nowrap', font: "700 13px 'Pretendard', sans-serif" }}>내 심볼</span>
        {[['＋ 폴더', '새 폴더 만들기', e => setPop({ ...below(e), ask: { label: '새 폴더 이름', value: '', ok: v => mine.api.addFolder(v) } })],
          ['⋯', '파일로 저장 · 파일 불러오기', e => setPop({ ...below(e), menu: [
            ...(mine.mine.symbols.length ? [['파일로 저장', download]] : []), ['파일 불러오기', () => file.current.click()]] })]].map(([l, t, f]) =>
          <button key={l} data-testid={l === '⋯' ? 'mine-more' : undefined} title={t} onClick={f} style={{ all: 'unset', cursor: 'pointer', padding: '1px 6px', borderRadius: 4, border: `1px solid ${C.line}`, font: "500 11px 'Pretendard', sans-serif" }}>{l}</button>)}
      </div>
      {folders.filter(isMine).map(f => { const list = syms.filter(s => s.folder === f); return <Section key={f} title={folderTitle(f)} color={FOLDER_GRAY} count={list.length} shut={shut.has('f:' + f)} onToggle={() => toggle('f:' + f)} onMenu={folderMenu(f)} folder={folderTitle(f)} lit={drop?.folder === folderTitle(f)}>{list.map(s => cellOf('customsym:' + s.id))}</Section> })}
      {!mine.mine.symbols.length && <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.5 }}>칠판에서 도형·아이콘을 고르고 우클릭 「내 심볼에 추가」</div>}
      {(n => n > 0 && <button data-testid="sym-reseed" title="지운 예시 심볼(방송·기술·업무)만 다시 넣어요 — 내가 넣은 심볼은 그대로" onClick={() => { const k = mine.api.reseed(); say?.(k ? `예시 심볼 ${k}개를 되돌렸어요` : '빠진 예시가 없어요') }}
        style={{ all: 'unset', cursor: 'pointer', alignSelf: 'flex-start', padding: '1px 6px', borderRadius: 4, border: `1px solid ${C.line}`, font: "500 11px 'Pretendard', sans-serif", color: C.muted }}>↺ 예시 심볼 되돌리기 ({n}개)</button>)(mine.api.missing())}   {/* 빠진 예시가 있을 때만(2026-10-28 사용자 — 메뉴 안 「예시 다시 넣기」를 따로 보이는 단추로) */}
      <input ref={file} type="file" accept=".json,application/json" hidden onChange={async e => { const f = e.target.files?.[0]; e.target.value = ''; if (!f) return
        const n = mine.api.importText(await f.text()); say?.(n >= 0 ? `내 심볼 ${n}개를 가져왔어요` : n === -2 ? '이 브라우저 저장 공간이 모자라요' : '내 심볼 파일로 읽지 못했어요') }} />
    </div>}
    </>}
    {!lib && !mine && <div style={{ fontSize: 11, color: C.muted }}>내 심볼은 저장 서버를 켜면 보여요</div>}
    {pop && <div data-testid="mine-pop" onPointerDown={e => e.stopPropagation()} onKeyDown={e => e.stopPropagation()} style={{ position: 'fixed', left: pop.x, top: Math.min(pop.y, window.innerHeight - 90), zIndex: 45, minWidth: 150, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, padding: 4, boxShadow: '0 6px 20px rgba(0,0,0,.16)', display: 'flex', flexDirection: 'column', gap: 2 }}>
      {pop.menu ? pop.menu.map(([l, f]) => <button key={l} onClick={() => { setPop(null); f() }} style={{ all: 'unset', cursor: 'pointer', padding: '5px 8px', borderRadius: 5, font: "500 12px 'Pretendard', sans-serif", color: C.ink }}
        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(218,119,86,.12)' }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>{l}</button>)
        : <><span style={{ font: "600 11px 'Pretendard', sans-serif", color: C.muted, padding: '2px 4px' }}>{pop.ask.label}</span>
          <input autoFocus defaultValue={pop.ask.value} onBlur={() => setPop(null)} onKeyDown={e => { if (e.key === 'Enter') { pop.ask.ok(e.currentTarget.value); setPop(null) } if (e.key === 'Escape') setPop(null) }}
            style={{ height: 26, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 8px', font: "400 12px 'Pretendard', sans-serif" }} /></>}
    </div>}
    {peek && <div data-testid="sym-peek" style={{ position: 'fixed', left: peek.x + 8, top: Math.max(8, Math.min(peek.r.top + peek.r.height / 2 - 86, window.innerHeight - 180)), zIndex: 40, pointerEvents: 'none',
      width: 160, boxSizing: 'border-box', padding: '12px 12px 10px', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, boxShadow: '0 6px 20px rgba(0,0,0,.16)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }}>
      <SymIcon e={peek.e} dark={dark} size={120} />
      <span style={{ font: "600 13px 'Pretendard', sans-serif", color: C.ink, textAlign: 'center' }}>{peek.e.name}</span>
      <span style={{ font: "400 11px 'Pretendard', sans-serif", color: C.muted }}>클릭 그리기 · 끌어 놓기</span></div>}   {/* 크게 보기(2026-10-27 실검증 — 데스크톱 「크게 보기」 창 대신 마우스 올림, 툴팁은 끔) */}
  </div>
}

export function useLibrary() {
  const [lib, setLib] = useState(null)
  useEffect(() => { loadLibrary().then(setLib) }, [])
  return lib
}
