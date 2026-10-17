// 직접 만드는 칠판 2단계 — 기본 편집(데스크톱 `core_view` 규칙): 선택(클릭·범위·Shift)·이동(Shift = 축 고정)·크기·회전·스마트 정렬선·
// 되돌리기·복사/붙여넣기/복제·삭제·묶기·잠금·순서·반전·방향키, 그리기 도구(상자·원·글·선·펜·다각형), 글 편집(TipTap).
// 화면 = 칠판 × z + (x, y). 손잡이·선 굵기는 화면 px 고정(÷ z).
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { Item, layoutText } from './render.jsx'
import { boardMembership, drawOrder, itemBounds } from './doc.js'
import { PT, TEXT_MARGIN, labelAnchor } from './geom.js'
import { resolveRoutes } from './arrows.js'
import { alignSnap } from './align.js'
import { newId } from './model.js'
import {
  applyRect, boardContents, duplicate, expandGroups, followArrows, groupItems, localRect, mirror, moveItems, removeItems, resizeRect,
  rotateTo, rubberSelect, sceneBox, toLocal, toScene, toggleLock, topHit, ungroupItems, unionBox, zOrder,
} from './edit.js'
import { TextEditor } from './text.jsx'
import { cssColor } from '../ecadFormat.js'

const ZOOM_STEP = 1.15, ZMIN = 0.02, ZMAX = 40
const BLUE = '#89b4fa', PEACH = '#fab387', GUIDE = 'rgb(230,60,160)'   // 데스크톱 theme BLUE·PEACH, 가이드선 마젠타
const HANDLE = 10, HIT_PX = 4, EDGE_PX = 5
const INK = '#ff1f1f1f'   // 새로 그리는 선·글 기본색(밝은 칠판)
const BOXY = new Set(['rect', 'ellipse', 'symbol', 'image', 'table', 'board', 'polygon', 'path'])

// 글 상자 크기(아이템 안 단위) — 그릴 때와 같은 재기, 아이템 객체마다 한 번
const _tb = new WeakMap()
export function textBox(it) {
  let b = _tb.get(it)
  if (!b) { const lay = layoutText(it.text, it.runs, (it.font || 12) * PT, it.family ? 'board' : 'app', it.weight ?? (it.bold ? 700 : 400)); b = { w: lay.w + 2 * TEXT_MARGIN, h: lay.h + 2 * TEXT_MARGIN }; _tb.set(it, b) }
  return b
}

const topZ = items => Math.max(0, ...items.map(it => it.z ?? 0))
const base = (pos, extra) => ({ pos, scale: 1, rotation: 0, z: 0, origin: [0, 0], locked: false, group_id: null, layer_id: null, _id: newId(), ...extra })

export const Editor = forwardRef(function Editor({ model, setModel, onCommit, size, cam, setCam, tool, setTool, setStatus }, ref) {
  const [sel, setSel] = useState([])
  const [live, setLive] = useState(null)          // 끄는 동안 보이는 아이템 목록(놓으면 확정)
  const [overlay, setOverlay] = useState({})      // { rubber, guides, draw, poly }
  const [editing, setEditing] = useState(null)    // 글 편집 { id, kind:'text'|'label' }
  const [cursor, setCursor] = useState('default')
  const st = useRef({}), hist = useRef({ past: [], future: [] }), clip = useRef({ items: [], seq: 0 }), svg = useRef(null)
  const items = live || model.items
  const R = useRef(); R.current = { model, sel, cam, tool, items, editing }

  const toSceneP = useCallback(e => { const r = svg.current.getBoundingClientRect(), c = R.current.cam; return { x: (e.clientX - r.left - c.x) / c.z, y: (e.clientY - r.top - c.y) / c.z } }, [])
  const scr = p => ({ x: p.x * cam.z + cam.x, y: p.y * cam.z + cam.y })

  // 확정 — 붙은 화살표 따라가기 + 되돌리기 칸
  const commit = useCallback((next, nextSel, label = '') => {
    const prev = R.current.model.items, fixed = followArrows(next)
    hist.current.past.push({ items: prev, sel: R.current.sel }); hist.current.future = []
    if (hist.current.past.length > 200) hist.current.past.shift()
    setModel(m => ({ ...m, items: fixed })); setLive(null)
    if (nextSel) setSel(nextSel.filter(id => fixed.some(it => it._id === id)))
    onCommit?.(label)
  }, [setModel, onCommit])
  const undo = () => { const h = hist.current, p = h.past.pop(); if (!p) return; h.future.push({ items: R.current.model.items, sel: R.current.sel }); setModel(m => ({ ...m, items: p.items })); setSel(p.sel); onCommit?.('되돌림') }
  const redo = () => { const h = hist.current, f = h.future.pop(); if (!f) return; h.past.push({ items: R.current.model.items, sel: R.current.sel }); setModel(m => ({ ...m, items: f.items })); setSel(f.sel); onCommit?.('다시 실행') }

  useImperativeHandle(ref, () => ({ undo, redo, getSel: () => R.current.sel, setSel, reset: () => { hist.current = { past: [], future: [] }; setSel([]) },
    // 시험용(Playwright 자체확인) — 손잡이·상태 들여다보기
    debugHandle: p => ({ single: single?._id, hs: handlesOf(single).map(h => [h.key, h.p]), at: handleAt(p)?.key }), debugState: () => ({ kind: st.current.kind, handle: st.current.handle, live: !!live }) }))

  const byId = useMemo(() => new Map(items.map(it => [it._id, it])), [items])
  const selItems = sel.map(id => byId.get(id)).filter(Boolean)
  const single = selItems.length === 1 ? selItems[0] : null

  // ── 손잡이(단일 선택) — [{ key, p(칠판), cursor }] ──
  function handlesOf(it) {
    if (!it || it.locked) return []
    const z = R.current.cam.z, out = []
    if (BOXY.has(it.type)) {
      const [x, y, w, h] = localRect(it), s = it.scale || 1
      for (const [k, px, py, c] of [['tl', x, y, 'nwse-resize'], ['tr', x + w, y, 'nesw-resize'], ['br', x + w, y + h, 'nwse-resize'], ['bl', x, y + h, 'nesw-resize']]) out.push({ key: k, p: toScene(it, { x: px, y: py }), cursor: c })
      const g = (HANDLE * 1.6) / z / s
      out.push({ key: 'rot', p: toScene(it, { x: x - g, y: y - g }), cursor: 'grab', round: true })   // 좌상단 대각(데스크톱 `_box_rot_center`)
    } else if (it.type === 'text') {
      const b = textBox(it), r = HANDLE / 2 / z
      out.push({ key: 'scale', p: toScene(it, { x: b.w, y: b.h }), cursor: 'nwse-resize' })
      out.push({ key: 'rot', p: toScene(it, { x: b.w - r, y: r }), cursor: 'grab', round: true })   // 우상단 안쪽(데스크톱 `_rot_handle_center`)
    } else if (it.type === 'line') {
      out.push({ key: 'e0', p: toScene(it, { x: it.line[0], y: it.line[1] }), cursor: 'crosshair' }, { key: 'e1', p: toScene(it, { x: it.line[2], y: it.line[3] }), cursor: 'crosshair' })
    }
    return out
  }
  const handleAt = p => { const z = R.current.cam.z; return handlesOf(single).find(h => Math.hypot(h.p.x - p.x, h.p.y - p.y) * z <= HANDLE * 0.75) || null }
  // 변 가까이(선택한 상자류) — 한 축 크기 바꾸기
  function edgeAt(it, p) {
    if (!it || it.locked || !BOXY.has(it.type)) return null
    const q = toLocal(it, p), [x, y, w, h] = localRect(it), t = EDGE_PX / R.current.cam.z / (it.scale || 1)
    const inY = q.y > y + t && q.y < y + h - t, inX = q.x > x + t && q.x < x + w - t
    if (inY && Math.abs(q.x - x) <= t) return 'l'
    if (inY && Math.abs(q.x - x - w) <= t) return 'r'
    if (inX && Math.abs(q.y - y) <= t) return 't'
    if (inX && Math.abs(q.y - y - h) <= t) return 'b'
    return null
  }
  const edgeCursor = { l: 'ew-resize', r: 'ew-resize', t: 'ns-resize', b: 'ns-resize' }

  // 끄는 것 + 함께 움직일 것(보드 안 것·같은 묶음)
  const movingSet = ids => [...new Set([...ids, ...boardContents(R.current.model.items, ids, textBox)])]

  // ── 포인터 ──
  function onPointerDown(e) {
    if (R.current.editing) return
    const p = toSceneP(e), m = R.current.model, z = R.current.cam.z
    svg.current.setPointerCapture(e.pointerId)
    if (e.button === 1 || (e.button === 0 && st.current.space)) { st.current = { ...st.current, kind: 'pan', sx: e.clientX, sy: e.clientY, cam: R.current.cam }; setCursor('grabbing'); return }
    if (e.button !== 0) return
    const t = R.current.tool
    if (t !== 'select') return startDraw(t, p, e)
    const h = handleAt(p)
    if (h) {
      const it = single
      st.current = { ...st.current, kind: h.key === 'rot' ? 'rotate' : h.key === 'scale' ? 'tscale' : h.key.startsWith('e') ? 'lineend' : 'resize', handle: h.key, id: it._id, start: p, orig: m.items }
      return
    }
    const edge = edgeAt(single, p)
    if (edge) { st.current = { ...st.current, kind: 'resize', handle: edge, id: single._id, start: p, orig: m.items }; return }
    const hit = topHit(m.items, p, HIT_PX / z, textBox)
    if (hit) {
      let ids = R.current.sel
      if (e.shiftKey) ids = ids.includes(hit._id) ? ids.filter(i => i !== hit._id && !(hit.group_id && m.items.find(x => x._id === i)?.group_id === hit.group_id)) : expandGroups(m.items, [...ids, hit._id])
      else if (!ids.includes(hit._id)) ids = expandGroups(m.items, [hit._id])
      setSel(ids)
      if (ids.includes(hit._id)) st.current = { ...st.current, kind: 'move', start: p, orig: m.items, ids: movingSet(ids), sel: ids, moved: false }
      return
    }
    if (!e.shiftKey) setSel([])
    st.current = { ...st.current, kind: 'rubber', start: p, add: e.shiftKey ? R.current.sel : [] }
  }

  function onPointerMove(e) {
    const s = st.current, p = toSceneP(e), z = R.current.cam.z
    if (!s.kind) { hoverCursor(p); return }
    if (s.kind === 'pan') { setCam({ ...s.cam, x: s.cam.x + e.clientX - s.sx, y: s.cam.y + e.clientY - s.sy }); return }
    if (s.kind === 'move') {
      let dx = p.x - s.start.x, dy = p.y - s.start.y
      if (!s.moved && Math.hypot(dx, dy) * z < 3) return
      s.moved = true
      if (e.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0 }   // 축 고정(데스크톱 Shift+끌기)
      const movedIds = new Set(s.ids)
      const box = unionBox(s.orig.filter(it => s.sel.includes(it._id)).map(it => sceneBox(it, textBox)))
      const others = s.orig.filter(it => !movedIds.has(it._id) && !it.locked && !(it.type === 'sarrow' && (movedIds.has(it._bind1) || movedIds.has(it._bind2)))).map(it => sceneBox(it, textBox))
      const a = alignSnap({ x: box.x + dx, y: box.y + dy, w: box.w, h: box.h }, others, z)
      if (!e.shiftKey || dx) dx += a.dx; if (!e.shiftKey || dy) dy += a.dy
      setLive(followArrows(moveItems(s.orig, s.ids, dx, dy))); setOverlay(o => ({ ...o, guides: a.guides }))
      return
    }
    if (s.kind === 'rubber') { setOverlay(o => ({ ...o, rubber: { a: s.start, b: p } })); return }
    if (s.kind === 'resize' || s.kind === 'rotate' || s.kind === 'tscale' || s.kind === 'lineend') {
      const it = s.orig.find(x => x._id === s.id); let next
      if (s.kind === 'resize') next = applyRect(it, resizeRect(localRect(it), s.handle, toLocal(it, p), { keepRatio: it.type === 'image' || e.shiftKey }))
      else if (s.kind === 'rotate') { const [x, y, w, h] = localRect(it), c = toScene(it, { x: x + w / 2, y: y + h / 2 }), a0 = Math.atan2(s.start.y - c.y, s.start.x - c.x), a1 = Math.atan2(p.y - c.y, p.x - c.x)
        next = rotateTo(it, (it.rotation || 0) + ((a1 - a0) * 180) / Math.PI, e.shiftKey) }
      else if (s.kind === 'tscale') { const b = textBox(it), q = toLocal(it, p), k = Math.max(0.2, Math.max(q.x / b.w, q.y / b.h)); next = { ...it, font: Math.max(4, Math.round((it.font || 12) * k)) } }
      else { const q = toLocal(it, p), L = [...it.line]; if (s.handle === 'e0') { L[0] = q.x; L[1] = q.y } else { L[2] = q.x; L[3] = q.y }; next = { ...it, line: L } }
      setLive(followArrows(s.orig.map(x => (x._id === s.id ? next : x))))
      return
    }
    if (s.kind === 'draw') { s.cur = p; s.shift = e.shiftKey; setOverlay(o => ({ ...o, draw: { tool: s.tool, a: s.start, b: p, shift: e.shiftKey, pts: s.pts } })); if (s.tool === 'pen') { const last = s.pts[s.pts.length - 1]; if (Math.hypot(p.x - last.x, p.y - last.y) * z >= 2) s.pts.push(p) } return }
  }

  function onPointerUp(e) {
    const s = st.current, p = toSceneP(e)
    st.current = { space: s.space }
    setCursor('default')
    if (s.kind === 'move') { setOverlay(o => ({ ...o, guides: null })); if (s.moved && live) commit(live.filter(it => it), s.sel, '옮김'); else setLive(null); return }
    if (s.kind === 'rubber') {
      setOverlay(o => ({ ...o, rubber: null }))
      if (Math.hypot(p.x - s.start.x, p.y - s.start.y) * R.current.cam.z > 3) setSel(expandGroups(R.current.model.items, [...new Set([...s.add, ...rubberSelect(R.current.model.items, s.start, p, textBox)])]))
      return
    }
    if (['resize', 'rotate', 'tscale', 'lineend'].includes(s.kind)) { if (live) commit(live, R.current.sel, '바꿈'); return }
    if (s.kind === 'draw') return finishDraw(s, p)
  }

  function hoverCursor(p) {
    const t = R.current.tool
    if (t !== 'select') { setCursor(t === 'text' ? 'text' : 'crosshair'); return }
    const h = handleAt(p); if (h) { setCursor(h.cursor); return }
    const ed = edgeAt(single, p); if (ed) { setCursor(edgeCursor[ed]); return }
    setCursor(topHit(R.current.model.items, p, HIT_PX / R.current.cam.z, textBox) ? 'move' : 'default')
  }

  // ── 그리기 ──
  function startDraw(t, p) {
    const m = R.current.model
    if (t === 'text') { const it = base([p.x - TEXT_MARGIN, p.y - TEXT_MARGIN], { type: 'text', text: '', color: INK, font: 12, bg: null, z: topZ(m.items) + 1 }); commit([...m.items, it], [it._id], '글'); setEditing({ id: it._id, kind: 'text', fresh: true }); setTool('select'); return }
    if (t === 'polygon') {
      const poly = overlay.poly || []
      if (poly.length >= 3 && Math.hypot(p.x - poly[0].x, p.y - poly[0].y) * R.current.cam.z <= 8) return finishPoly(poly, true)
      setOverlay(o => ({ ...o, poly: [...poly, p] })); return
    }
    st.current = { ...st.current, kind: 'draw', tool: t, start: p, cur: p, pts: [p] }
  }
  function finishPoly(pts, closed) {
    setOverlay(o => ({ ...o, poly: null }))
    if (pts.length < 2) return
    const xs = pts.map(q => q.x), ys = pts.map(q => q.y), x0 = Math.min(...xs), y0 = Math.min(...ys)
    const it = base([x0, y0], { type: 'polygon', closed, rect: [0, 0, Math.max(...xs) - x0, Math.max(...ys) - y0], pts: pts.map(q => [q.x - x0, q.y - y0]), pen: INK, width: 2, fill: null, style: 1, z: topZ(R.current.model.items) + 1 })
    commit([...R.current.model.items, it], [it._id], '다각형'); setTool('select')
  }
  function finishDraw(s, p) {
    setOverlay(o => ({ ...o, draw: null }))
    const m = R.current.model, z = R.current.cam.z, click = Math.hypot(p.x - s.start.x, p.y - s.start.y) * z < 3
    let it
    if (s.tool === 'rect' || s.tool === 'ellipse') {
      let x0 = Math.min(s.start.x, p.x), y0 = Math.min(s.start.y, p.y), w = Math.abs(p.x - s.start.x), h = Math.abs(p.y - s.start.y)
      if (s.shift) { const d = Math.max(w, h); w = h = d; x0 = p.x < s.start.x ? s.start.x - d : s.start.x; y0 = p.y < s.start.y ? s.start.y - d : s.start.y }
      if (click) { w = s.tool === 'ellipse' ? 100 : 120; h = s.tool === 'ellipse' ? 100 : 60; x0 = p.x - w / 2; y0 = p.y - h / 2 }   // 클릭만 = 기본 크기로 그 자리에
      it = base([x0, y0], { type: s.tool, rect: [0, 0, w, h], pen: INK, width: 2, fill: null, style: 1 })
    } else if (s.tool === 'line') {
      if (click) return
      let { x, y } = p
      if (s.shift) { const a = Math.round(Math.atan2(y - s.start.y, x - s.start.x) / (Math.PI / 4)) * (Math.PI / 4), L = Math.hypot(x - s.start.x, y - s.start.y); x = s.start.x + L * Math.cos(a); y = s.start.y + L * Math.sin(a) }
      it = base([0, 0], { type: 'line', line: [s.start.x, s.start.y, x, y], pen: INK, width: 2, style: 1 })
    } else if (s.tool === 'pen') {
      if (s.pts.length < 2) return
      it = base([0, 0], { type: 'path', elements: s.pts.map((q, i) => [i ? 'L' : 'M', q.x, q.y]), pen: INK, width: 2, style: 1, freehand: true })
    }
    if (!it) return
    it.z = topZ(m.items) + 1
    commit([...m.items, it], [it._id], '그림'); setTool('select')
  }

  // ── 두 번 누르기 = 글 편집(글 상자) / 도형 라벨 ──
  function onDoubleClick(e) {
    if (R.current.tool === 'polygon') { finishPoly(overlay.poly || [], false); return }
    const p = toSceneP(e), hit = topHit(R.current.model.items, p, HIT_PX / R.current.cam.z, textBox)
    if (!hit || hit.locked) return
    if (hit.type === 'text') { setSel([hit._id]); setEditing({ id: hit._id, kind: 'text' }) }
    else if (['rect', 'ellipse', 'symbol'].includes(hit.type) || (hit.type === 'polygon' && hit.closed)) { setSel([hit._id]); setEditing({ id: hit._id, kind: 'label' }) }
  }
  function finishEdit({ text, runs }) {
    const ed = R.current.editing; setEditing(null); if (!ed) return
    const m = R.current.model, it = m.items.find(x => x._id === ed.id); if (!it) return
    let next
    if (ed.kind === 'text') {
      if (!text.trim()) { commit(removeItems(m.items, [it._id]), [], '빈 글 지움'); return }
      next = { ...it, text, runs: runs.length ? runs : undefined }
    } else {
      const L = it.label || { text: '', color: it.pen && it.pen !== '#00000000' ? it.pen : INK, font: 16, bg: null }
      next = { ...it, label: text.trim() ? { ...L, text, runs: runs.length ? runs : undefined } : undefined }
    }
    if (!next.runs) delete next.runs
    if (next.label && !next.label.runs) { const { runs: _r, ...l } = next.label; next.label = l }
    if (next.label === undefined) delete next.label
    commit(m.items.map(x => (x._id === it._id ? next : x)), [it._id], '글 고침')
  }
  function editSpec() {
    const it = editing && byId.get(editing.id); if (!it) return null
    if (editing.kind === 'text') {
      const o = scr(toScene(it, { x: 0, y: 0 }))
      return { left: o.x, top: o.y, px: (it.font || 12) * PT * (it.scale || 1), zoom: cam.z, family: it.family ? 'board' : 'app', weight: it.weight ?? (it.bold ? 700 : 400),
        color: cssColor(it.color) || '#1f1f1f', rotation: it.rotation || 0, origin: scr(toScene(it, { x: it.origin?.[0] || 0, y: it.origin?.[1] || 0 })), text: it.text, runs: it.runs }
    }
    const a = scr(toScene(it, labelAnchor(it.type, it.kind, it.rect))), L = it.label || {}
    return { center: a, px: (L.font || 16) * PT * (it.scale || 1), zoom: cam.z, family: L.family ? 'board' : 'app', weight: 400, color: cssColor(L.color || it.pen) || '#1f1f1f', align: 'center', text: L.text || '', runs: L.runs }
  }

  // ── 글쇠 ──
  useEffect(() => {
    const onKey = e => {
      if (R.current.editing || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '')) return
      const m = R.current.model, ids = R.current.sel, mod = e.ctrlKey || e.metaKey, k = e.key
      if (k === ' ') { st.current.space = true; return }
      const act = (f, label) => { e.preventDefault(); f(label) }
      if (mod && k.toLowerCase() === 'z' && !e.shiftKey) return act(undo)
      if (mod && (k.toLowerCase() === 'y' || (k.toLowerCase() === 'z' && e.shiftKey))) return act(redo)
      if (mod && k.toLowerCase() === 'a') return act(() => setSel(m.items.filter(it => !it.locked).map(it => it._id)))
      if (k === 'Escape') { setOverlay(o => ({ ...o, poly: null, draw: null })); if (R.current.tool !== 'select') setTool('select'); else setSel([]); return }
      if (k === 'Enter' && overlay.poly) return act(() => finishPoly(overlay.poly, false))
      if (!mod && !e.altKey && !e.shiftKey && { 1: 'select', 3: 'text', 4: 'line', 5: 'polygon', 6: 'pen' }[k]) return act(() => setTool({ 1: 'select', 3: 'text', 4: 'line', 5: 'polygon', 6: 'pen' }[k]))
      if (!ids.length) { if (mod && k.toLowerCase() === 'v') return act(paste); return }
      if (k === 'Delete' || k === 'Backspace') return act(() => commit(removeItems(m.items, movingSet(ids)), [], '지움'))
      if (mod && k.toLowerCase() === 'c') return act(copy)
      if (mod && k.toLowerCase() === 'x') return act(() => { copy(); commit(removeItems(m.items, movingSet(ids)), [], '잘라냄') })
      if (mod && k.toLowerCase() === 'v') return act(paste)
      if (mod && k.toLowerCase() === 'd') return act(() => { const r = duplicate(m.items, movingSet(ids), 0, 0); commit(r.items, r.ids, '제자리 복제') })
      if (mod && k.toLowerCase() === 'g') return act(() => commit(e.shiftKey ? ungroupItems(m.items, ids) : groupItems(m.items, ids), ids, e.shiftKey ? '묶음 풂' : '묶음'))
      if (mod && k.toLowerCase() === 'l') return act(() => commit(toggleLock(m.items, ids), ids, '잠금'))
      if (mod && (k === ']' || k === '[')) return act(() => commit(zOrder(m.items, ids, k === ']'), ids, k === ']' ? '맨 앞으로' : '맨 뒤로'))
      if (e.shiftKey && !mod && (k === 'H' || k === 'V')) return act(() => commit(mirror(m.items, ids, k === 'H', textBox), ids, '반전'))
      const dir = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[k]
      if (dir) { const d = e.shiftKey || mod ? 1 : 10; return act(() => commit(moveItems(m.items, movingSet(ids), dir[0] * d, dir[1] * d), ids, '조금 옮김')) }   // 기본 10, Shift/Ctrl 1(데스크톱)
    }
    const onUp = e => { if (e.key === ' ') st.current.space = false }
    window.addEventListener('keydown', onKey); window.addEventListener('keyup', onUp)
    return () => { window.removeEventListener('keydown', onKey); window.removeEventListener('keyup', onUp) }
  })
  function copy() {
    const m = R.current.model, ids = new Set(movingSet(R.current.sel))
    clip.current = { items: structuredClone(m.items.filter(it => ids.has(it._id))), seq: 0 }
    setStatus?.(`${ids.size}개 복사`)
  }
  function paste() {
    const c = clip.current; if (!c.items.length) return
    c.seq += 1
    const m = R.current.model, tmp = [...m.items, ...c.items.map(it => ({ ...it, _id: '__clip' + it._id }))]
    const remap = tmp.map(it => (it._id.startsWith('__clip') ? { ...it, _bind1: it._bind1 && '__clip' + it._bind1, _bind2: it._bind2 && '__clip' + it._bind2 } : it))
    const r = duplicate(remap, remap.filter(it => it._id.startsWith('__clip')).map(it => it._id), 20 * c.seq, 20 * c.seq)   // 데스크톱: 붙일 때마다 20씩 비켜서
    commit(r.items.filter(it => !it._id.startsWith('__clip')), r.ids, '붙여넣음')
  }

  // 휠 = 커서 기준 확대
  useEffect(() => {
    const el = svg.current
    const onWheel = e => { e.preventDefault(); const r = el.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top
      setCam(c => { const z = Math.min(ZMAX, Math.max(ZMIN, c.z * (e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP))), k = z / c.z; return { z, x: mx - (mx - c.x) * k, y: my - (my - c.y) * k } }) }
    el.addEventListener('wheel', onWheel, { passive: false }); return () => el.removeEventListener('wheel', onWheel)
  }, [setCam])

  // ── 그리기 차례·화면 밖 빼기 ──
  const order = useMemo(() => drawOrder(items), [items])
  const onBoard = useMemo(() => boardMembership(items), [items])
  const routes = useMemo(() => resolveRoutes(items), [items])
  const bounds = useMemo(() => items.map(itemBounds), [items])
  const view = { x: -cam.x / cam.z, y: -cam.y / cam.z, w: size.w / cam.z, h: size.h / cam.z }, mg = 40 / cam.z
  const visible = order.filter(([it, i]) => { const b = bounds[i]; return it.type === 'board' || (b.x < view.x + view.w + mg && b.x + b.w > view.x - mg && b.y < view.y + view.h + mg && b.y + b.h > view.y - mg) })
  const editingId = editing?.id

  // ── 덧그림(칠판 좌표, 굵기는 ÷z) ──
  const z = cam.z, sw = 1.6 / z
  const outline = it => {
    const [x, y, w, h] = it.type === 'text' ? [0, 0, textBox(it).w, textBox(it).h] : localRect(it)
    if (it.type === 'line') { const a = toScene(it, { x: it.line[0], y: it.line[1] }), b = toScene(it, { x: it.line[2], y: it.line[3] }); return <line key={it._id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={BLUE} strokeWidth={sw} /> }
    if (it.type === 'sarrow') return <polyline key={it._id} points={it.pts.map(([px, py]) => { const q = toScene(it, { x: px, y: py }); return `${q.x},${q.y}` }).join(' ')} fill="none" stroke={BLUE} strokeWidth={sw} />
    if (it.type === 'ellipse') return <ellipse key={it._id} cx={x + w / 2} cy={y + h / 2} rx={w / 2} ry={h / 2} transform={transformOf(it)} fill="none" stroke={BLUE} strokeWidth={sw / (it.scale || 1)} />
    if (it.type === 'badge') { const c = toScene(it, { x: 0, y: 0 }); return <circle key={it._id} cx={c.x} cy={c.y} r={17} fill="none" stroke={BLUE} strokeWidth={sw} /> }
    const cs = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]].map(([a, b]) => toScene(it, { x: a, y: b }))
    return <polygon key={it._id} points={cs.map(c => `${c.x},${c.y}`).join(' ')} fill="none" stroke={BLUE} strokeWidth={sw} />
  }
  const handles = single && !editing && !live ? handlesOf(single) : []
  const multiBox = selItems.length > 1 ? unionBox(selItems.map(it => sceneBox(it, textBox))) : null
  const rb = overlay.rubber, dr = overlay.draw

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <svg ref={svg} width={size.w} height={size.h} style={{ display: 'block', cursor, touchAction: 'none', userSelect: 'none', WebkitUserSelect: 'none' }} data-testid="board"
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onDoubleClick={onDoubleClick} onContextMenu={e => e.preventDefault()}>
        <g transform={`translate(${cam.x},${cam.y}) scale(${z})`}>
          {visible.map(([it, i]) => (it._id === editingId ? <g key={it._id} opacity={0.15}><Item it={it} idx={i} onBoard={onBoard[i]} route={routes.get(i)} /></g>
            : <Item key={it._id} it={it} idx={i} onBoard={onBoard[i]} route={routes.get(i)} />))}
          {selItems.map(outline)}
          {multiBox && <rect x={multiBox.x} y={multiBox.y} width={multiBox.w} height={multiBox.h} fill="none" stroke={BLUE} strokeWidth={1 / z} strokeDasharray={`${4 / z} ${3 / z}`} />}
          {selItems.filter(it => it.locked).map(it => { const b = sceneBox(it, textBox); return <text key={'lk' + it._id} x={b.x + b.w} y={b.y} fontSize={12 / z} fill={BLUE}>🔒</text> })}
          {handles.map(h => (h.round ? <circle key={h.key} cx={h.p.x} cy={h.p.y} r={HANDLE / 2 / z} fill={PEACH} stroke="#fff" strokeWidth={1 / z} />
            : <rect key={h.key} x={h.p.x - HANDLE / 2 / z} y={h.p.y - HANDLE / 2 / z} width={HANDLE / z} height={HANDLE / z} fill={BLUE} stroke="#fff" strokeWidth={1 / z} />))}
          {overlay.guides?.map((g, i) => {
            const [x1, y1, x2, y2] = g.axis === 'v' ? [g.at, g.from, g.at, g.to] : [g.from, g.at, g.to, g.at], dash = g.role === 'center' ? undefined : `${6 / z} ${4 / z}`
            return <g key={i}><line x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(0,0,0,.7)" strokeWidth={3 / z} strokeDasharray={dash} /><line x1={x1} y1={y1} x2={x2} y2={y2} stroke={GUIDE} strokeWidth={1.5 / z} strokeDasharray={dash} /></g>
          })}
          {rb && (() => { const x = Math.min(rb.a.x, rb.b.x), y = Math.min(rb.a.y, rb.b.y), w = Math.abs(rb.b.x - rb.a.x), h = Math.abs(rb.b.y - rb.a.y), win = rb.b.x >= rb.a.x
            return <rect x={x} y={y} width={w} height={h} fill={win ? 'rgba(137,180,250,.15)' : 'rgba(166,227,161,.15)'} stroke={win ? BLUE : '#40a02b'} strokeWidth={1 / z} strokeDasharray={win ? undefined : `${4 / z} ${3 / z}`} /> })()}
          {dr && (dr.tool === 'rect' ? <rect x={Math.min(dr.a.x, dr.b.x)} y={Math.min(dr.a.y, dr.b.y)} width={Math.abs(dr.b.x - dr.a.x)} height={Math.abs(dr.b.y - dr.a.y)} fill="none" stroke={BLUE} strokeWidth={1.5 / z} />
            : dr.tool === 'ellipse' ? <ellipse cx={(dr.a.x + dr.b.x) / 2} cy={(dr.a.y + dr.b.y) / 2} rx={Math.abs(dr.b.x - dr.a.x) / 2} ry={Math.abs(dr.b.y - dr.a.y) / 2} fill="none" stroke={BLUE} strokeWidth={1.5 / z} />
            : dr.tool === 'line' ? <line x1={dr.a.x} y1={dr.a.y} x2={dr.b.x} y2={dr.b.y} stroke={BLUE} strokeWidth={1.5 / z} />
            : <polyline points={dr.pts.map(q => `${q.x},${q.y}`).join(' ')} fill="none" stroke={BLUE} strokeWidth={1.5 / z} />)}
          {overlay.poly && <polyline points={overlay.poly.map(q => `${q.x},${q.y}`).join(' ')} fill="none" stroke={BLUE} strokeWidth={1.5 / z} />}
        </g>
      </svg>
      {editing && (() => { const s = editSpec(); if (!s) return null
        return <TextEditor key={editing.id} spec={s} onDone={finishEdit} /> })()}
    </div>
  )
})

const transformOf = it => {
  const [x, y] = it.pos || [0, 0], r = it.rotation || 0, s = it.scale || 1, [ox, oy] = it.origin || [0, 0]
  return `translate(${x},${y}) translate(${ox},${oy}) rotate(${r}) scale(${s}) translate(${-ox},${-oy})`
}
