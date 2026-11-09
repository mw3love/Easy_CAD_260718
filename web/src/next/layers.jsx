// 좌하 「레이어」 카드 — 데스크톱 `host_layers`(첫 화면 시안 L2): 색 점 · 이름 · 「그리는 중」(코랄 연필) · 개수 · 눈 · 자물쇠.
// 줄을 누르면 그 레이어가 「그리는 중」(새 도형이 들어갈 곳). 레이어 목록은 .ecad 문서 `layers`(데스크톱 save_document와 같은 모양), 도형은 `layer_id`(없으면 기본).
// 표시·잠금은 되돌리기 밖(데스크톱과 같음 — 문서 설정). 잠금은 그 레이어 도형의 `locked`를 같이 바꾼다(데스크톱 `_set_item_lock_flags`).
import { useRef, useState } from 'react'
import { DOCKED, FoldBtn, useFold } from './fold.jsx'
import { FloatMenu } from './ctxmenu.jsx'
import { btnHead, menuBelow, moreBtn } from './ui.jsx'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', on: 'var(--mb-accent)' }
export const LAYER_COLORS = ['#8a98a8', '#5aa9ff', '#e8c15a', '#5fbf8a', '#e0646a', '#b48cf2', '#da7756', '#4fd1e0']   // 데스크톱 `_LAYER_COLORS`
export const DEFAULT_LAYER = { id: 'default', name: '기본', visible: true, locked: false, color: LAYER_COLORS[0] }
export const layersOf = m => (m.layers?.length ? m.layers.map((l, i) => ({ ...l, color: l.color || LAYER_COLORS[i % LAYER_COLORS.length] })) : [DEFAULT_LAYER])
export const layerIdOf = it => it.layer_id || 'default'
const newLayerId = () => Math.random().toString(16).slice(2, 10)

const Svg = ({ children }) => <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">{children}</svg>
const EYE = <Svg><path d="M1.5 8 C3.5 4 12.5 4 14.5 8 C12.5 12 3.5 12 1.5 8 Z" /><circle cx="8" cy="8" r="2" /></Svg>
const EYE_OFF = <Svg><path d="M1.5 8 C3.5 4 12.5 4 14.5 8 C12.5 12 3.5 12 1.5 8 Z" opacity=".45" /><path d="M2.5 13.5 L13.5 2.5" /></Svg>
const LOCK = <Svg><rect x="3.5" y="7" width="9" height="6.5" rx="1" /><path d="M5.5 7 V5 a2.5 2.5 0 0 1 5 0 V7" /></Svg>
const UNLOCK = <Svg><rect x="3.5" y="7" width="9" height="6.5" rx="1" opacity=".45" /><path d="M5.5 7 V5 a2.5 2.5 0 0 1 5 0" opacity=".45" /></Svg>
const PEN = <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="#da7756" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M11 2.5 L13.5 5 L5.5 13 L2.5 13.5 L3 10.5 Z" /></svg>
const iconBtn = { all: 'unset', cursor: 'pointer', width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 4, color: C.ink }

// model·setModel = 문서, active/setActive = 「그리는 중」, onChanged = 저장 알림. 고른 도형 옮기기는 칠판 우클릭 「레이어로 이동 ▸」(2026-10-27 사용자 — 판의 「선택 → 그리는 중」 단추는 「그 레이어 고르기」로 읽혀 뺌)
export function Layers({ model, setModel, active, setActive, onChanged, dark, docked }) {
  const [f0, toggleFold] = useFold('layers'), folded = !docked && f0
  const layers = layersOf(model), [menu, setMenu] = useState(null), [renaming, setRenaming] = useState(null), [hov, setHov] = useState(null), cancel = useRef(false)
  // 줄 메뉴(2026-11-02 디자인 규칙) = 공용 메뉴 — ⋯(마우스 올렸을 때만, 같은 ⋯ 다시 누르면 닫힘)·우클릭. 옛 자체 메뉴는 마우스가 벗어나면 닫혔음
  const openMenu = (id, at) => setMenu(m => (m?.id === id && at.anchor ? null : { id, ...at }))
  const startRename = id => { cancel.current = false; setRenaming(id) }
  const count = id => model.items.filter(it => layerIdOf(it) === id).length
  const cur = layers.some(l => l.id === active) ? active : 'default'
  const save = (fn, items) => { setModel(m => ({ ...m, layers: fn(layersOf(m)), ...(items ? { items: items(m.items) } : {}) })); onChanged?.() }
  const setVisible = (id, v) => { save(ls => ls.map(l => (l.id === id ? { ...l, visible: v } : l))); if (!v && cur === id) setActive('default') }   // 숨긴 레이어엔 못 그림
  const setLocked = (id, v) => { save(ls => ls.map(l => (l.id === id ? { ...l, locked: v } : l)), its => its.map(it => (layerIdOf(it) === id ? { ...it, locked: v } : it))); if (v && cur === id) setActive('default') }
  const add = () => save(ls => { const used = new Set(ls.map(l => l.color)); return [...ls, { id: newLayerId(), name: `레이어 ${ls.length + 1}`, visible: true, locked: false, color: LAYER_COLORS.find(c => !used.has(c)) || LAYER_COLORS[ls.length % LAYER_COLORS.length] }] })
  const rename = (id, name) => { setRenaming(null); if (cancel.current) return; if (name.trim()) save(ls => ls.map(l => (l.id === id ? { ...l, name: name.trim() } : l))) }
  const del = id => { if (id === 'default') return; const def = layers.find(l => l.id === 'default') || DEFAULT_LAYER
    save(ls => ls.filter(l => l.id !== id), its => its.map(it => (layerIdOf(it) === id ? { ...it, layer_id: null, locked: def.locked } : it)))   // 소속은 기본으로 — 기본의 잠금을 물려받음
    if (cur === id) setActive('default') }
  const rowBg = dark ? '#2d3640' : '#dfe5eb'   // 「그리는 중」 줄만 옅은 면(데스크톱 `_style_layer_row`)
  return <div data-folded={folded || undefined} onPointerDown={e => e.stopPropagation()} style={{ pointerEvents: 'auto', width: 192, boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: '8px 8px 8px',
    boxShadow: '0 2px 8px rgba(0,0,0,.06)', color: C.ink, display: 'flex', flexDirection: 'column', gap: 4, userSelect: 'none', position: 'relative', flex: 'none', ...(docked ? DOCKED : {}) }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}><span style={{ font: "700 15px 'Pretendard', sans-serif", flex: 1 }}>레이어</span>
      <button data-testid="layer-new" onClick={add} title="레이어를 하나 더 만들어요" style={btnHead}>＋ 새 레이어</button>{!docked && <FoldBtn folded={folded} onClick={toggleFold} />}</div>   {/* 머리줄 오른쪽(규칙 B1 — 옛 자리는 목록 아래) */}
    <div style={{ display: 'flex', flexDirection: 'column', gap: 1, maxHeight: 240, overflowY: 'auto' }}>
      {layers.map(l => <div key={l.id} onClick={() => l.visible && !l.locked && setActive(l.id)} onContextMenu={e => { e.preventDefault(); openMenu(l.id, { x: e.clientX, y: e.clientY }) }} data-testid="layer-row"
        onMouseEnter={() => setHov(l.id)} onMouseLeave={() => setHov(h => (h === l.id ? null : h))}
        title={l.visible && !l.locked ? '누르면 「그리는 중」 — 새 도형이 이 레이어로 들어가요' : '숨기거나 잠근 레이어엔 그릴 수 없어요'}
        style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '3px 4px 3px 6px', borderRadius: 4, background: l.id === cur ? rowBg : 'transparent', cursor: 'pointer', font: "400 12px 'Pretendard', sans-serif" }}>
        <label title="레이어 색 바꾸기(구분용 — 도형 색은 그대로)" onClick={e => e.stopPropagation()} style={{ position: 'relative', width: 12, height: 12, borderRadius: 6, background: l.color, flex: 'none', cursor: 'pointer' }}>
          <input type="color" value={l.color} onChange={e => save(ls => ls.map(x => (x.id === l.id ? { ...x, color: e.target.value } : x)))} style={{ opacity: 0, position: 'absolute', inset: 0, width: 12, height: 12, cursor: 'pointer' }} /></label>
        {renaming === l.id
          ? <input autoFocus defaultValue={l.name} onClick={e => e.stopPropagation()} onFocus={e => e.target.select()} onBlur={e => rename(l.id, e.target.value)} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') { cancel.current = true; setRenaming(null) } }}
            style={{ flex: 1, minWidth: 0, height: 20, border: `1px solid ${C.line}`, borderRadius: 4, background: 'transparent', color: C.ink, font: 'inherit', padding: '0 4px' }} />
          : <span onDoubleClick={e => { e.stopPropagation(); startRename(l.id) }} style={{ overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis', opacity: l.visible ? 1 : 0.5 }}>{l.name}</span>}
        {l.id === cur && <span title="그리는 중 — 새 도형이 이 레이어로 들어가요" aria-label="그리는 중" style={{ display: 'flex' }}>{PEN}</span>}
        <span style={{ flex: 1 }} />
        <span style={{ color: C.muted, fontSize: 11 }}>{count(l.id)}</span>
        <button title="레이어 표시/숨김" aria-pressed={l.visible} onClick={e => { e.stopPropagation(); setVisible(l.id, !l.visible) }} style={iconBtn}>{l.visible ? EYE : EYE_OFF}</button>
        <button title="레이어 잠금" aria-pressed={l.locked} onClick={e => { e.stopPropagation(); setLocked(l.id, !l.locked) }} style={iconBtn}>{l.locked ? LOCK : UNLOCK}</button>
        {renaming !== l.id && <button data-testid="layer-more" className="mb-hit" aria-label="레이어 메뉴" title="이름 바꾸기·지우기" onClick={e => { e.stopPropagation(); openMenu(l.id, menuBelow(e)) }} style={moreBtn(hov === l.id || menu?.id === l.id)}>⋯</button>}
      </div>)}
    </div>
    {/* 지우기 = 확인 없음(규칙 ⑥ — 안의 도형은 「기본」으로 옮겨 남음) */}
    {menu && <FloatMenu testid="layer-menu" at={menu} onClose={() => setMenu(null)} entries={[['이름 바꾸기', '', () => { setMenu(null); startRename(menu.id) }],
      ...(menu.id !== 'default' ? ['-', ['지우기 (도형은 「기본」으로)', '', () => { setMenu(null); del(menu.id) }]] : [])]} />}
  </div>
}
