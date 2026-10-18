// 직접 만드는 칠판 2단계 — 기본 편집(데스크톱 `core_view` 규칙): 선택(클릭·범위·Shift)·이동(Shift = 축 고정)·크기·회전·스마트 정렬선·
// 되돌리기·복사/붙여넣기/복제·삭제·묶기·잠금·순서·반전·방향키, 그리기 도구(상자·원·글·선·펜·다각형), 글 편집(TipTap).
// 화면 = 칠판 × z + (x, y). 손잡이·선 굵기는 화면 px 고정(÷ z).
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { arrowAt, arrowLabelBoxes, ink, Item, layoutText } from './render.jsx'
import { boardMembership, drawOrder, itemBounds } from './doc.js'
import { PT, TEXT_MARGIN, cutPolyline, headSize, headTriangle, labelAnchor, roundedPath, roundedPts, strokeOutline, trimmedPts } from './geom.js'
import { applyRouting, minStubs, resolveRoutes, sarrowRadius, sceneRect } from './arrows.js'
import { alignSnap } from './align.js'
import { ROUTE_BOX, bindPt, dropTarget, edgeMid, bindEnd, groupFrac, groupHost, hostPorts, isBindHost, isConnHost, isSnapLine, nearestBorder, OPP, qcDelta, qcDots, snapAt } from './connect.js'
import { routeOrtho } from '../route.js'
import { projectToCurve, projectToPath, snapLabelOff } from './arrowedit.js'
import { beginSegment, beginSubdivide, bendCurve, BEND_TS, curvePoint, dragSegment, endSegment, nearestSegment, onPill, SEG_HANDLE_PX, SEG_HIT_PX, segmentHandles, setCurveEnd, snapCurve, subdividePreview } from './arrowedit.js'
import { sarrowRouting } from './arrows.js'
import { fromEcad, newId } from './model.js'
import {
  applyRect, boardContents, duplicate, expandGroups, flatten, followArrows, groupItems, localRect, mirror, moveItems, removeItems, resizeRect,
  rotateTo, rubberSelect, sceneBox, toLocal, toScene, toggleLock, topHit, ungroupItems, unionBox, zOrder,
} from './edit.js'
import { TextEditor } from './text.jsx'
import { Props, captureStyle, styleFor } from './props.jsx'
import { arrowKindOf, swapArrowKind } from './arrowkind.js'
import { symbolPath } from './symbols.js'
import { cssColor } from '../ecadFormat.js'
import { colEdges } from './geom.js'
import { layersOf, layerIdOf } from './layers.jsx'

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

// 붙는 계산이 쓰는 도형 안 바탕 사각형(글 상자는 화면에서 잰 크기)
const rectOf = it => { if (it.type === 'text') { const b = textBox(it); return [0, 0, b.w, b.h] } return localRect(it) }
const QC_BLUE = 'rgb(90,150,235)', BEND_GREEN = '#a6e3a1'   // 데스크톱 큐닷·포트점 색, 곡선 휨 손잡이(theme GREEN)
const HP_MARGIN = 30, CONN_DRAG_PX = 8, CONN_STRAIGHT_PX = 10   // 포트점 후보 범위·끌기 시작·출구 축 맞추기(데스크톱 `_hover_port_at`·`_hp_*`)
// 도형 '속'에 있나(데스크톱 `_shape_interior_contains` — 원은 타원 안, 나머지는 바탕 사각형 안)
function inside(it, p) {
  const q = toLocal(it, p), [x, y, w, h] = rectOf(it)
  if (it.type === 'ellipse') { const dx = (q.x - x - w / 2) / (w / 2 || 1), dy = (q.y - y - h / 2) / (h / 2 || 1); return dx * dx + dy * dy <= 1 }
  return q.x >= x && q.x <= x + w && q.y >= y && q.y <= y + h
}
const sceneRectOf = it => { const b = sceneBox(it, textBox); return { l: b.x, t: b.y, r: b.x + b.w, b: b.y + b.h } }

const topZ = items => Math.max(0, ...items.map(it => it.z ?? 0))
// 화살표 라벨 — 옛 파일의 단수 label은 고칠 때 labels 하나로(데스크톱도 저장할 땐 labels만)
const isArrow = it => it?.type === 'sarrow' || it?.type === 'arrow'
const labelsOf = it => (it.labels ? it.labels.map(L => ({ ...L })) : it.label ? [{ t: 0.5, off: 0, ...it.label }] : [])
const withLabels = (it, labels) => { const o = { ...it, labels }; delete o.label; return o }
// 화살표 안 점 → 길 위 t·옆 거리(직각 = 꺾은선 길이 비율, 곡선 = 매개변수 — 데스크톱 `_project_to_path`·`_project_to_curve`)
const projectOn = (it, q) => (it.type === 'sarrow' ? projectToPath(it.pts.map(([x, y]) => ({ x, y })), q) : projectToCurve(it, q))
const base = (pos, extra) => ({ pos, scale: 1, rotation: 0, z: 0, origin: [0, 0], locked: false, group_id: null, layer_id: null, _id: newId(), ...extra })

export const Editor = forwardRef(function Editor({ dark, model, setModel, onCommit, size, cam, setCam, tool, setTool, setStatus, library, libFolders, activeLayer }, ref) {
  const [sel, setSel] = useState([])
  const [live, setLive] = useState(null)          // 끄는 동안 보이는 아이템 목록(놓으면 확정)
  const [overlay, setOverlay] = useState({})      // { rubber, guides, draw, poly }
  const [editing, setEditing] = useState(null)    // 글 편집 { id, kind:'text'|'label' }
  const [cursor, setCursor] = useState('default')
  const st = useRef({}), hist = useRef({ past: [], future: [] }), clip = useRef({ items: [], seq: 0 }), svg = useRef(null)
  const items = live || model.items
  const R = useRef(); R.current = { vhosts: new Map(), ...R.current, model, sel, cam, tool, items, editing, hp: overlay.hp, activeLayer }
  // 누를 수 있는 것 = 숨긴 레이어 밖(데스크톱 setVisible(False)는 눌리지도 않음)
  const hitPool = () => { const m = R.current.model, hid = new Set(layersOf(m).filter(l => !l.visible).map(l => l.id)); return hid.size ? m.items.filter(it => !hid.has(layerIdOf(it))) : m.items }   // vhosts = 묶음 가상 상자('g:…', hostsNear가 채움)

  const toSceneP = useCallback(e => { const r = svg.current.getBoundingClientRect(), c = R.current.cam; return { x: (e.clientX - r.left - c.x) / c.z, y: (e.clientY - r.top - c.y) / c.z } }, [])
  const scr = p => ({ x: p.x * cam.z + cam.x, y: p.y * cam.z + cam.y })

  // 확정 — 붙은 화살표 따라가기 + 되돌리기 칸
  // merge = 같은 열쇠로 1.5초 안에 또 고치면 되돌리기 한 칸으로 묶음(−/+ 연타·색 고르기 끌기)
  const commit = useCallback((next, nextSel, label = '', merge = null) => {
    const prev = R.current.model.items, h = hist.current, now = Date.now()
    const al = R.current.activeLayer, ly = al && al !== 'default' && layersOf(R.current.model).find(l => l.id === al)
    if (ly && ly.visible && !ly.locked) { const had = new Set(prev.map(it => it._id)); next = next.map(it => (had.has(it._id) || it.layer_id ? it : { ...it, layer_id: al })) }
    const fixed = followArrows(next, rectOf)
    if (!(merge && h.mergeKey === merge && now - h.mergeT < 1500)) { h.past.push({ items: prev, sel: R.current.sel }); h.future = [] }
    h.mergeKey = merge; h.mergeT = now
    if (hist.current.past.length > 200) hist.current.past.shift()
    setModel(m => ({ ...m, items: fixed })); setLive(null)
    if (nextSel) setSel(nextSel.filter(id => fixed.some(it => it._id === id)))
    onCommit?.(label)
  }, [setModel, onCommit])
  const undo = () => { const h = hist.current, p = h.past.pop(); h.mergeKey = null; if (!p) return; h.future.push({ items: R.current.model.items, sel: R.current.sel }); setModel(m => ({ ...m, items: p.items })); setSel(p.sel); onCommit?.('되돌림') }
  const redo = () => { const h = hist.current, f = h.future.pop(); h.mergeKey = null; if (!f) return; h.past.push({ items: R.current.model.items, sel: R.current.sel }); setModel(m => ({ ...m, items: f.items })); setSel(f.sel); onCommit?.('다시 실행') }

  useImperativeHandle(ref, () => ({ undo, redo, getSel: () => R.current.sel, setSel, insertTable, moveSelToLayer, reset: () => { hist.current = { past: [], future: [] }; setSel([]) }, startPaletteDrag,
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
      const b = textBox(it), g = (HANDLE * 1.6) / z / (it.scale || 1)
      out.push({ key: 'scale', p: toScene(it, { x: b.w, y: b.h }), cursor: 'nwse-resize' })
      out.push({ key: 'rot', p: toScene(it, { x: -g, y: -g }), cursor: 'grab', round: true })   // 좌상단 대각 — 상자와 같은 자리(데스크톱 `_rot_handle_center`, 2026-10-17 통일)
    } else if (it.type === 'line') {
      out.push({ key: 'e0', p: toScene(it, { x: it.line[0], y: it.line[1] }), cursor: 'crosshair' }, { key: 'e1', p: toScene(it, { x: it.line[2], y: it.line[3] }), cursor: 'crosshair' })
    } else if (it.type === 'sarrow' && it.pts?.length >= 2) {   // 끝점 손잡이 — 끌어 다시 붙이기·떼기(데스크톱 endpoint handle) + 알약(직각 구간 가운데)
      const a = it.pts[0], b = it.pts[it.pts.length - 1]
      out.push({ key: 'a0', p: toScene(it, { x: a[0], y: a[1] }), cursor: 'pointer' }, { key: 'a1', p: toScene(it, { x: b[0], y: b[1] }), cursor: 'pointer' })
      if (sarrowRouting(it) === 'ortho') for (const h of segmentHandles(it.pts, z, it.scale || 1)) out.push({ key: 'seg:' + h.i, p: toScene(it, { x: h.mid[0], y: h.mid[1] }), pill: true, horizontal: h.horizontal })
    } else if (it.type === 'arrow') {   // 곡선: 끝점 둘 + 휨 손잡이 둘(t 1/3·2/3, 초록)
      out.push({ key: 'a0', p: toScene(it, { x: it.p1[0], y: it.p1[1] }), cursor: 'pointer' }, { key: 'a1', p: toScene(it, { x: it.p2[0], y: it.p2[1] }), cursor: 'pointer' })
      BEND_TS.forEach((t, k) => { const q = curvePoint(it, t); out.push({ key: 'b' + (k + 1), p: toScene(it, { x: q[0], y: q[1] }), cursor: 'pointer', bend: true }) })
    }
    // 큐닷 — 포트에서 바깥 24px(클릭 = 복제+연결, 끌기 = 화살표). 다른 도형을 가리키는 중이면 숨김(`_qc_dots_hover_suppressed`)
    if (isConnHost(it) && !R.current.hp) for (const q of qcDots(it, rectOf, z)) out.push({ key: 'qc:' + q.side, p: q.p, cursor: 'crosshair', qc: true, port: { p: q.port, n: q.n } })
    return out
  }
  const handleAt = p => { const z = R.current.cam.z; return handlesOf(single).find(h => !h.pill && Math.hypot(h.p.x - p.x, h.p.y - p.y) * z <= HANDLE * 0.75) || null }
  // 누른 곳의 화살표 라벨(맨 위부터) → { it, i, box }
  function labelAt(p) {
    const ord = R.current.order || []
    for (let k = ord.length - 1; k >= 0; k--) {
      const it = ord[k][0]; if (!isArrow(it) || it.locked) continue
      const q = toLocal(it, p), b = arrowLabelBoxes(it).find(b => !b.empty && q.x >= b.left && q.x <= b.left + b.w && q.y >= b.top && q.y <= b.top + b.h)
      if (b) return { it, i: b.i, box: b }
    }
    return null
  }
  // 고른 직각 화살표의 구간 위(화면 10px) → { i, proj(화살표 안), pill(알약 위인가) } — 알약 = 구간 통째 평행 이동, 아니면 나눠 끌기(데스크톱 `_segment_add_at`)
  function segAt(p) {
    const it = single
    if (!it || it.locked || it.type !== 'sarrow' || sarrowRouting(it) !== 'ortho') return null
    const z = R.current.cam.z, sc = it.scale || 1, q = toLocal(it, p), n = nearestSegment(it.pts, q)
    if (!n || n.d * z * sc > SEG_HIT_PX) return null
    return { ...n, pill: onPill(it.pts, n.i, n.proj, z, sc) }
  }
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
  // 커서 아래 손잡이(큐닷은 살짝 커짐 — Lucid)
  const [hoverKey, setHoverKeyS] = useState(null)
  const setHoverKey = k => { if (R.current.hoverKey !== k) { R.current.hoverKey = k; setHoverKeyS(k) } }
  const setSegPrev = v => { const a = R.current.segPrev; if ((!a && !v) || (a && v && a.p.x === v.p.x && a.p.y === v.p.y)) return; R.current.segPrev = v; setOverlay(o => ({ ...o, segPrev: v })) }
  // 포트점 예고 바꾸기(같으면 다시 그리지 않음)
  const setHp = hp => { const a = R.current.hp, same = (!a && !hp) || (a && hp && a.id === hp.id && a.target?.p.x === hp.target?.p.x && a.target?.p.y === hp.target?.p.y); if (!same) { R.current.hp = hp; setOverlay(o => ({ ...o, hp })) } }

  // 끄는 것 + 함께 움직일 것(보드 안 것·같은 묶음)
  const movingSet = ids => [...new Set([...ids, ...boardContents(R.current.model.items, ids, textBox)])]

  // ── 포인터 ──
  function onPointerDown(e) {
    if (R.current.editing) return
    const p = toSceneP(e), m = R.current.model, z = R.current.cam.z
    svg.current.setPointerCapture(e.pointerId)
    // 가운데·오른쪽 끌기 = 화면 이동(데스크톱 우클릭 끌기 = 팬, 제자리 우클릭 메뉴는 나중)
    if (e.button === 1 || e.button === 2 || (e.button === 0 && st.current.space)) { st.current = { ...st.current, kind: 'pan', sx: e.clientX, sy: e.clientY, cam: R.current.cam }; setCursor('grabbing'); return }
    if (e.button !== 0) return
    setHp(null)
    const t = R.current.tool
    if (t !== 'select') return startDraw(t, p, e)
    const h = handleAt(p)
    if (h?.qc) { st.current = { ...st.current, kind: 'conn', src: single._id, side: h.key.slice(3), port: h.port, start: p, cur: p, fromQc: true, moved: false }; return }
    if (h?.bend) { st.current = { ...st.current, kind: 'bend', id: single._id, which: +h.key.slice(1), orig: m.items }; return }
    if (h && (h.key === 'a0' || h.key === 'a1')) { st.current = { ...st.current, kind: 'aend', id: single._id, idx: h.key === 'a0' ? 0 : 1, orig: m.items }; setOverlay(o => ({ ...o, hp: null })); return }
    if (h) {
      const it = single
      st.current = { ...st.current, kind: h.key === 'rot' ? 'rotate' : h.key === 'scale' ? 'tscale' : h.key.startsWith('e') ? 'lineend' : 'resize', handle: h.key, id: it._id, start: p, orig: m.items }
      return
    }
    const lb = !h && labelAt(p)
    if (lb) {   // 라벨 끌기 = 길 따라 미끄러짐 + 옆으로 당기면 선 위/양옆 세 자리(데스크톱 `_reproject_label`)
      const q = toLocal(lb.it, p)
      setSel([lb.it._id]); st.current = { ...st.current, kind: 'label', id: lb.it._id, i: lb.i, box: lb.box, grab: { x: lb.box.a.x - q.x, y: lb.box.a.y - q.y }, orig: m.items, start: p, moved: false }
      return
    }
    const sg = !h && segAt(p)
    if (sg) {
      const it = single, sc = it.scale || 1, seg = sg.pill ? beginSegment(it.pts, sg.i) : beginSubdivide(it.pts, sg.i, sg.proj, z, sc)
      if (seg) { st.current = { ...st.current, kind: 'seg', id: it._id, seg, orig: m.items, start: p, moved: false }; setSegPrev(null); return }
    }
    const edge = edgeAt(single, p)
    if (edge) { st.current = { ...st.current, kind: 'resize', handle: edge, id: single._id, start: p, orig: m.items }; return }
    const add = e.shiftKey || e.ctrlKey || e.metaKey   // 더해 고르기 — Ctrl(데스크톱 손버릇)·Shift(웹 관례) 둘 다
    // 미선택 도형의 포트점·테두리(14px)를 누르면 화살표 잇기 대기 — 끌면 화살표, 그냥 놓으면 그 도형 선택(데스크톱 `_hover_port_at`→`_hp_*`)
    if (!add && !e.altKey) { const hp = hoverPort(p); if (hp?.target) { st.current = { ...st.current, kind: 'conn', src: hp.target.id, port: { p: hp.target.p, n: hp.target.n }, start: p, cur: p, fromQc: false, moved: false }; return } }
    const hit = topHit(hitPool(), p, HIT_PX / z, textBox)
    if (hit) {
      let ids = R.current.sel
      if (add) ids = ids.includes(hit._id) ? ids.filter(i => i !== hit._id && !(hit.group_id && m.items.find(x => x._id === i)?.group_id === hit.group_id)) : expandGroups(m.items, [...ids, hit._id])
      else if (!ids.includes(hit._id)) ids = expandGroups(m.items, [hit._id])
      setSel(ids)
      if (ids.includes(hit._id)) st.current = { ...st.current, kind: 'move', start: p, orig: m.items, ids: movingSet(ids), sel: ids, moved: false }
      return
    }
    if (!add) setSel([])
    st.current = { ...st.current, kind: 'rubber', start: p, add: add ? R.current.sel : [] }
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
      setLive(followArrows(moveItems(s.orig, s.ids, dx, dy), rectOf)); setOverlay(o => ({ ...o, guides: a.guides }))
      return
    }
    if (s.kind === 'rubber') {   // 끄는 동안 걸릴 것을 바로 보여 줌(데스크톱 `_rb_preview_hits` — 실제 선택은 놓을 때)
      const sel0 = new Set(R.current.sel), hitIds = Math.hypot(p.x - s.start.x, p.y - s.start.y) * z > 3 ? expandGroups(R.current.model.items, rubberSelect(hitPool(), s.start, p, textBox)).filter(id => !sel0.has(id)) : []
      setOverlay(o => ({ ...o, rubber: { a: s.start, b: p, hits: hitIds } })); return
    }
    if (s.kind === 'conn') {
      if (!s.moved && Math.hypot(p.x - s.start.x, p.y - s.start.y) * z <= CONN_DRAG_PX) return
      s.moved = true
      let cur = p; const n = s.port.n, o = s.port.p   // 출구 축에 10px 안이면 곧게(데스크톱) — 빈 곳에서 시작한 화살표는 출구가 없음
      if (!n) { /* 자유 시작 */ } else if (Math.abs(n.x) >= Math.abs(n.y)) { if (Math.abs(cur.y - o.y) * z <= CONN_STRAIGHT_PX) cur = { x: cur.x, y: o.y } }
      else if (Math.abs(cur.x - o.x) * z <= CONN_STRAIGHT_PX) cur = { x: o.x, y: cur.y }
      s.cur = cur
      const tgt = connTarget(s.src, s.port, cur)
      setOverlay(o2 => ({ ...o2, conn: connRoute(s.src, s.port, tgt, cur), hp: tgt ? { id: tgt.id, target: tgt } : null }))
      return
    }
    if (s.kind === 'label') {
      if (!s.moved && Math.hypot(p.x - s.start.x, p.y - s.start.y) * z < 3) return
      s.moved = true
      const it = s.orig.find(x => x._id === s.id), q = toLocal(it, p), c = { x: q.x + s.grab.x, y: q.y + s.grab.y }, pr = projectOn(it, c)
      const n = arrowAt(it)(pr.t).n, labels = labelsOf(it)
      labels[s.i] = { ...labels[s.i], t: pr.t, off: snapLabelOff(n, pr.off, s.box.w, s.box.h) }
      setLive(s.orig.map(x => (x._id === s.id ? withLabels(it, labels) : x)))
      return
    }
    if (s.kind === 'seg') {
      if (!s.moved && Math.hypot(p.x - s.start.x, p.y - s.start.y) * z < 3) return
      s.moved = true
      const it = s.orig.find(x => x._id === s.id), next = { ...it, pts: dragSegment(s.seg, toLocal(it, p), z, it.scale || 1), auto_route: false, route_hints: [] }   // 구간을 만지면 손으로 그린 길(자동 길 끔)
      setLive(s.orig.map(x => (x._id === s.id ? next : x)))
      return
    }
    if (s.kind === 'bend') {
      const it = s.orig.find(x => x._id === s.id), q = toLocal(it, p), next = bendCurve(it, s.which, [q.x, q.y], it.width || 2, (it.scale || 1) * z)
      setLive(s.orig.map(x => (x._id === s.id ? next : x)))
      return
    }
    if (s.kind === 'aend' && s.orig.find(x => x._id === s.id)?.type === 'arrow') {   // 곡선 끝점: 붙으면 S자로 다시 휨, 떼면 그 쪽 제어점만 같이(데스크톱 `_ArrowItem._move_endpoint_with_snap`)
      const it = s.orig.find(x => x._id === s.id), tgt = snapAt(hostsNear(p), p, z, rectOf, linesNear(p, s.id)), end = tgt ? tgt.p : p, k = s.idx ? 'bind2' : 'bind1'
      const host = hostOf(tgt?.id, s.orig), q = toLocal(it, end)   // 선·화살표에 붙으면 host 없음 = 좌표만
      let next = { ...setCurveEnd(it, s.idx, [q.x, q.y]), ...bindOf(k, host, tgt?.p) }
      if (tgt) {
        const ok = s.idx ? 'bind1' : 'bind2', oe = bindEnd(next, ok, s.orig, rectOf)
        const on = oe ? nearestBorder(oe.host, oe.p, rectOf).n : null
        next = s.idx ? snapCurve(next, on, tgt.n) : snapCurve(next, tgt.n, on)
      }
      setLive(s.orig.map(x => (x._id === s.id ? next : x))); setOverlay(o => ({ ...o, hp: tgt ? { id: tgt.id, target: tgt } : null }))
      return
    }
    if (s.kind === 'aend') {
      const it = s.orig.find(x => x._id === s.id), tgt = snapAt(hostsNear(p), p, z, rectOf, linesNear(p, s.id)), end = tgt ? tgt.p : p
      const k = s.idx ? 'bind2' : 'bind1', last = it.pts.length - 1, [px, py] = it.pos || [0, 0], lp = [end.x - px, end.y - py]
      const host = hostOf(tgt?.id, s.orig)   // 선·화살표에 붙으면 host 없음 = 좌표만
      let next = { ...it, ...bindOf(k, host, tgt?.p), route_hints: [], auto_route: host ? true : it.auto_route }   // 다시 붙이면 자동 길(데스크톱은 안 켬 — 옮길 후보)
      next.pts = s.idx ? [it.pts[0], lp] : [lp, it.pts[last]]   // 끝점 끌기 = 새로 그리기처럼 길 전체 다시(데스크톱 `_move_endpoint_with_snap`)
      next = { ...next, pts: applyRouting(next, s.orig.map(x => (x._id === s.id ? next : x)), rectOf) }
      setLive(s.orig.map(x => (x._id === s.id ? next : x))); setOverlay(o => ({ ...o, hp: tgt ? { id: tgt.id, target: tgt } : null }))
      return
    }
    if (s.kind === 'resize' || s.kind === 'rotate' || s.kind === 'tscale' || s.kind === 'lineend') {
      const it = s.orig.find(x => x._id === s.id); let next
      if (s.kind === 'resize') next = applyRect(it, resizeRect(localRect(it), s.handle, toLocal(it, p), { keepRatio: it.type === 'image' || e.shiftKey }))
      else if (s.kind === 'rotate') { const [x, y, w, h] = localRect(it), c = toScene(it, { x: x + w / 2, y: y + h / 2 }), a0 = Math.atan2(s.start.y - c.y, s.start.x - c.x), a1 = Math.atan2(p.y - c.y, p.x - c.x)
        next = rotateTo(it, (it.rotation || 0) + ((a1 - a0) * 180) / Math.PI, e.shiftKey) }
      else if (s.kind === 'tscale') { const b = textBox(it), q = toLocal(it, p), k = Math.max(0.2, Math.max(q.x / b.w, q.y / b.h)); next = { ...it, font: Math.max(4, Math.round((it.font || 12) * k)) } }
      else { const q = toLocal(it, p), L = [...it.line]; if (s.handle === 'e0') { L[0] = q.x; L[1] = q.y } else { L[2] = q.x; L[3] = q.y }; next = { ...it, line: L } }
      setLive(followArrows(s.orig.map(x => (x._id === s.id ? next : x)), rectOf))
      return
    }
    if (s.kind === 'draw') { s.cur = p; s.shift = e.shiftKey; setOverlay(o => ({ ...o, draw: { tool: s.tool, a: s.start, b: p, shift: e.shiftKey, pts: s.pts } })); if (s.tool === 'pen') { const last = s.pts[s.pts.length - 1]; if (Math.hypot(p.x - last.x, p.y - last.y) * z >= 2) s.pts.push(p) } return }
  }

  function onPointerUp(e) {
    const s = st.current, p = toSceneP(e)
    st.current = { space: s.space }
    setCursor('default')
    if (s.kind === 'conn') {
      setOverlay(o => ({ ...o, conn: null, hp: null }))
      if (!s.moved) { if (s.tool === 'arrow') return; if (s.fromQc) qcCreate(s.src, s.side); else setSel(expandGroups(R.current.model.items, [s.src])); return }
      newArrow(s.src, s.port, connTarget(s.src, s.port, s.cur), s.cur)
      if (s.tool === 'arrow') setTool('select')
      return
    }
    if (s.kind === 'aend') { setOverlay(o => ({ ...o, hp: null })); if (live) commit(live, [s.id], '화살표 끝 옮김'); return }
    if (s.kind === 'bend') { if (live) commit(live, [s.id], '곡선 휨'); return }
    if (s.kind === 'label') { if (s.moved && live) commit(live, [s.id], '라벨 옮김'); else setLive(null); return }
    if (s.kind === 'seg') { if (s.moved && live) commit(live.map(x => (x._id === s.id ? { ...x, pts: endSegment(x.pts) } : x)), [s.id], '구간 옮김'); else setLive(null); return }
    if (s.kind === 'move') { setOverlay(o => ({ ...o, guides: null })); if (s.moved && live) commit(live.filter(it => it), s.sel, '옮김'); else setLive(null); return }
    if (s.kind === 'rubber') {
      setOverlay(o => ({ ...o, rubber: null }))
      if (Math.hypot(p.x - s.start.x, p.y - s.start.y) * R.current.cam.z > 3) setSel(expandGroups(R.current.model.items, [...new Set([...s.add, ...rubberSelect(hitPool(), s.start, p, textBox)])]))
      return
    }
    if (['resize', 'rotate', 'tscale', 'lineend'].includes(s.kind)) { if (live) commit(live, R.current.sel, '바꿈'); return }
    if (s.kind === 'draw') return finishDraw(s, p)
  }

  // ── 화살표 잇기(3단계, 데스크톱 `core_view` `_hover_port_at`·`_qc_snap_target`·`_hp_create_arrow`·`_qc_create`) ──
  // 칠판 점 근처(화면 30px)의 붙는 도형 — 그리는 차례(위에 그린 것이 뒤)
  function hostsNear(p, skip, test = isBindHost) {
    const m = HP_MARGIN / R.current.cam.z, out = [], seen = new Set(), items = R.current.model.items
    for (const [it] of R.current.order || []) {
      if (!test(it) || it.locked || skip?.has(it._id)) continue
      let host = it
      if (it.group_id && isConnHost(it)) {   // 묶음 멤버 = 묶음 전체 틀 하나로(데스크톱 `_group_proxy` — 그룹당 한 번)
        if (seen.has(it.group_id)) continue
        seen.add(it.group_id); host = groupHost(items, it.group_id, rectOf); R.current.vhosts.set(host._id, host)
      }
      const b = boxOf(host)
      if (p.x >= b.x - m && p.x <= b.x + b.w + m && p.y >= b.y - m && p.y <= b.y + b.h + m) out.push(host)
    }
    return out
  }
  const boxOf = it => (it.type === 'group' ? { x: it.rect[0], y: it.rect[1], w: it.rect[2], h: it.rect[3] } : sceneBox(it, textBox))
  // _id → 아이템(묶음 가상 상자 'g:…' 포함)
  const hostOf = (id, items = R.current.model.items) => (id == null ? null : items.find(x => x._id === id) || R.current.vhosts.get(id) || null)
  // 화살표 끝 붙이기 필드 — 도형 = 안 고정점, 묶음 = bindN_group + 비율(데스크톱 .ecad), 없음 = 떠 있는 끝
  const bindOf = (k, host, p) => (!host ? { ['_' + k]: null, [k + '_pt']: null, [k + '_group']: null }
    : host.type === 'group' ? { ['_' + k]: null, [k + '_pt']: groupFrac(host, p), [k + '_group']: host.group }
    : { ['_' + k]: host._id, [k + '_pt']: bindPt(host, p), [k + '_group']: null })
  // 끝이 좌표로만 붙는 선·화살표(자기 자신은 빼고)
  const linesNear = (p, skipId) => hostsNear(p, skipId ? new Set([skipId]) : null, isSnapLine)
  // 미선택 도형 포트점 예고 → { id(점 보일 도형), target(누르면 화살표가 시작될 자리 | null) } | null
  function hoverPort(p) {
    const sel = new Set(R.current.sel), items = R.current.model.items
    if (items.some(it => sel.has(it._id) && isConnHost(it) && inside(it, p))) return null   // 고른 도형 속 = 그 도형 몫(이동)
    let near = hostsNear(p, sel, it => isConnHost(it) || (it.type === 'path' && !it.freehand))   // 펜으로 그린 궤적은 선택 도구 호버에서 뺌(데스크톱 `_freehand` — 아니면 궤적을 끌 때마다 화살표가 나옴)
    const occ = near.filter(it => it.type !== 'path' && inside(it, p))
    if (occ.length) near = [occ[occ.length - 1]]   // 도형 속이면 맨 위 그것만(밑에 가려진 도형 점은 안 뜸)
    if (!near.length) return null
    const d = it => { const b = boxOf(it); return Math.hypot(b.x + b.w / 2 - p.x, b.y + b.h / 2 - p.y) }
    const host = near.reduce((a, b) => (d(b) < d(a) ? b : a))
    return { id: host._id, target: snapAt(near, p, R.current.cam.z, rectOf) }
  }
  // 끌어 놓을 자리 — 붙을 곳(포트·테두리, 다른 도형 속이면 그 도형 가장 가까운 포트). 같은 도형은 다른 자리일 때만(자기 연결)
  function connTarget(srcId, port, cur) {
    const t = dropTarget(hostsNear(cur), cur, R.current.cam.z, rectOf, srcId, linesNear(cur))
    return t && (t.id !== srcId || Math.hypot(t.p.x - port.p.x, t.p.y - port.p.y) > 1) ? t : null
  }
  // 새 화살표 기본값 — 속성 카드에서 바꾼 값이 다음 화살표에 이어짐(데스크톱 sticky: 색·굵기·선 모양·화살촉·모서리). 굵기 1 = 데스크톱 `_DEFAULT_WIDTH`·웹 그리기 도구와 같게(2026-10-18 — 2였을 땐 같은 화살표인데 선택 띠가 얇아 보였다)
  const sticky = useRef({ color: INK, style: 1, width: 1, head: true, head_start: false, head_scale: 1, curve_r: 10 })
  const badgeN = useRef(0)   // 마지막으로 놓은 번호표 번호
  const styleClip = useRef(null)   // 스타일 복사한 서식(데스크톱 `_style_clip`)
  const stickyFill = useRef(null)   // 새 닫힌 도형 채움 — 속성 카드 「채움」(데스크톱 `current_fill`)
  // 새 도형 선 = 화살표와 같은 색·굵기·선 모양(데스크톱 `current_color`·`current_width`·`current_style`은 도형·화살표 공용)
  const penOf = closed => ({ pen: sticky.current.color, width: sticky.current.width, style: sticky.current.style, ...(closed ? { fill: stickyFill.current } : {}) })
  const stickyKind = useRef('ortho')   // 새 화살표 종류(직각·직선·곡선) — 속성 카드 「종류」로 바꾼 것이 이어짐
  function connRoute(srcId, port, tgt, cur) {
    const items = R.current.model.items, src = hostOf(srcId), dst = tgt && hostOf(tgt.id)
    const box = it => (it && (ROUTE_BOX.has(it.type) || it.type === 'group') && it.rect ? sceneRect(it) : null)
    const gids = new Set([src?.group, dst?.group].filter(Boolean))
    const obstacles = items.filter(it => ROUTE_BOX.has(it.type) && it.rect && it._id !== srcId && it._id !== tgt?.id && !gids.has(it.group_id)).map(sceneRect)
    return routeOrtho(port.p, port.n, tgt ? tgt.p : cur, tgt ? tgt.n : null, obstacles, { conn: [box(src), box(dst)], minStub: minStubs(sticky.current) })
  }
  const arrowItem = (srcId, a, dstId, b, extra) => {
    const items = R.current.model.items, src = hostOf(srcId), dst = hostOf(dstId)
    return base([0, 0], { type: 'sarrow', routing: 'ortho', route_hints: [], ...sticky.current, ...extra, ...bindOf('bind1', src, a), ...bindOf('bind2', dst, b), z: topZ(items) + 1 })
  }
  // 끌어 놓음 = 화살표만(빈 곳이면 끝이 떠 있는 화살표). 「자동 길」로 — 도형을 옮겨도 다시 꺾임
  function newArrow(srcId, port, tgt, cur) {
    const items = R.current.model.items, pts = connRoute(srcId, port, tgt, cur)
    let it = arrowItem(srcId, port.p, tgt?.id, tgt?.p, { auto_route: !!(srcId || tgt?.id), pts: pts.map(q => [q.x, q.y]) })   // 양끝이 다 떠 있으면 손으로 놓은 길(데스크톱도 붙은 끝이 있을 때만 자동 길)
    if (stickyKind.current !== 'ortho') it = swapArrowKind(it, stickyKind.current, items, rectOf, sticky.current.curve_r)   // 화살표 종류 = 마지막에 고른 것(데스크톱 `current_arrow_kind`)
    commit([...items, it], [it._id], '화살표')
  }
  // 큐닷 클릭 = 그 방향으로 (크기 + 40) 옆에 같은 도형 복제(라벨·묶음 없이) + 변 가운데끼리 잇는 화살표
  function qcCreate(srcId, side) {
    const items = R.current.model.items, src = items.find(x => x._id === srcId), box = sceneBox(src, textBox), [dx, dy] = qcDelta(box, side)
    const r = duplicate(items, [srcId], dx, dy), dup = { ...r.items.find(x => x._id === r.ids[0]), group_id: null, z: src.z ?? 0 }
    delete dup.label
    const all = r.items.map(x => (x._id === dup._id ? dup : x)), a = edgeMid(box, side), b = edgeMid(sceneBox(dup, textBox), OPP[side])
    R.current.model = { ...R.current.model, items: all }   // arrowItem이 복제본을 찾게
    const ar = arrowItem(srcId, a, dup._id, b, { auto_route: false, pts: [[a.x, a.y], [b.x, b.y]] })
    commit([...all, ar], [dup._id], '복제 + 화살표')
  }

  function hoverCursor(p) {
    const t = R.current.tool
    if (t === 'arrow') { const near = hostsNear(p), lines = linesNear(p), tg = snapAt(near, p, R.current.cam.z, rectOf, lines); setHp(near.length || tg ? { id: tg?.id ?? near.at(-1)?._id ?? null, target: tg } : null); setCursor('crosshair'); return }   // 붙을 자리 예고
    if (t !== 'select') { setCursor(t === 'text' ? 'text' : 'crosshair'); return }
    const h = handleAt(p); setHoverKey(h?.key || null); if (h) { setHp(null); setSegPrev(null); setCursor(h.cursor); return }
    const sg = segAt(p)
    if (sg) {   // 직각 화살표 구간 위 — 알약이 아니면 나눠 끌 자리에 속 빈 알약 미리보기(`_draw_segment_preview_pill`)
      const it = single, a = it.pts[sg.i], b = it.pts[sg.i + 1], horizontal = Math.abs(b[1] - a[1]) <= Math.abs(b[0] - a[0])
      setHp(null); setSegPrev(sg.pill ? null : { p: (q => toScene(it, { x: q[0], y: q[1] }))(subdividePreview(it.pts, sg.i, sg.proj)), horizontal })
      setCursor(horizontal ? 'ns-resize' : 'ew-resize'); return
    }
    setSegPrev(null)
    const hp = hoverPort(p); setHp(hp)
    if (hp?.target && (!inside(R.current.model.items.find(x => x._id === hp.target.id) || {}, p) || (hp.target.port && Math.hypot(hp.target.p.x - p.x, hp.target.p.y - p.y) * R.current.cam.z <= 5))) { setCursor('crosshair'); return }
    const ed = edgeAt(single, p); if (ed) { setCursor(edgeCursor[ed]); return }
    setCursor(topHit(hitPool(), p, HIT_PX / R.current.cam.z, textBox) ? 'move' : 'default')
  }

  // ── 도형 카드에서 끌어다 놓기(데스크톱 `_PaletteButton` 6px 넘게 끌기) — 진짜 도형이 손에 붙어 따라오고 정렬선도 걸림, 칠판 밖(카드 위 등)에 놓으면 취소 ──
  // 도형·심볼 카드 도구 — 'rect'·'ellipse'·'sym:<종류>'는 상자처럼 끌어 그리기, 'customsym:<id>'(내 심볼)는 원래 모양 그대로 놓기
  const boxDefault = t => (t === 'ellipse' ? [100, 100] : t === 'rect' ? [120, 60] : [120, 72])   // 심볼 기본 크기 = 데스크톱 `_PALETTE_SYM_WH`
  const boxItem = (t, x0, y0, w, h) => base([x0, y0], { ...(t.startsWith('sym:') ? { type: 'symbol', kind: t.slice(4) } : { type: t }), rect: [0, 0, w, h], ...penOf(true) })
  // 내 심볼 아이템들(새 _id, 안의 화살표 연결은 그대로, 둘 이상이면 새 묶음 — 데스크톱 `_finish_custom_symbol_placement`). 칠판 위 맨 앞, 안의 앞뒤 차례는 유지
  function customItems(key) {
    const e = (library || []).find(s => 'customsym:' + s.id === key); if (!e) return null
    const items = fromEcad({ items: structuredClone(e.items) }).items, gid = items.length >= 2 ? newId() : null, top = topZ(R.current.model.items) + 1
    return items.map(it => ({ ...it, group_id: gid, z: top + (it.z || 0) }))
  }
  // protos를 왼쪽 위가 (x, y)인 자리로
  const placeAt = (protos, x, y) => { const b = unionBox(protos.map(it => sceneBox(it, textBox))); return moveItems(protos, protos.map(it => it._id), x - b.x, y - b.y) }
  // 도형 → 내 심볼(데스크톱 `_swap_to_custom_symbol`): 긴 변을 옛 도형 긴 변에 맞춰 늘이고(비율 유지) 가운데 맞춤, 옛 도형은 지움.
  // 붙어 있던 화살표 끝은 다시 붙임 — 조각 하나면 그 외곽선 가장 가까운 곳, 여럿이면 묶음 통째(데스크톱은 가장 가까운 조각 — 웹은 묶음을 옮겨도 덜 꼬이게)
  function swapToCustom(old, key) {
    const m = R.current.model, protos = customItems(key); if (!protos) return
    const ob = sceneBox(old, textBox), b = unionBox(protos.map(it => sceneBox(it, textBox)))
    const lo = Math.max(ob.w, ob.h), lc = Math.max(b.w, b.h); if (lc < 1e-6) return
    const k = lo / lc, bc = { x: b.x + b.w / 2, y: b.y + b.h / 2 }
    let its = protos.map(it => ({ ...it, scale: (it.scale || 1) * k, pos: [bc.x + ((it.pos?.[0] || 0) - bc.x) * k, bc.y + ((it.pos?.[1] || 0) - bc.y) * k] }))
    const nb = unionBox(its.map(it => sceneBox(it, textBox)))
    its = moveItems(its, its.map(it => it._id), ob.x + ob.w / 2 - (nb.x + nb.w / 2), ob.y + ob.h / 2 - (nb.y + nb.h / 2))
    const rest = m.items.filter(x => x._id !== old._id), all = [...rest, ...its]
    const host = its.length === 1 ? its[0] : groupHost(all, its[0].group_id, rectOf)
    const rebound = all.map(a => {
      if (!isArrow(a)) return a
      let o = a
      for (const kk of ['bind1', 'bind2']) {
        if (a['_' + kk] !== old._id) continue
        const e = bindEnd(a, kk, m.items, rectOf); if (!e) continue
        o = { ...o, ...bindOf(kk, host, nearestBorder(host, e.p, rectOf).p) }
      }
      return o
    })
    commit(rebound, its.map(it => it._id), '내 심볼로 바꾸기')
  }
  // 고른 도형을 레이어로(데스크톱 `move_selection_to_layer`) — 그 레이어의 잠금을 물려받음, 되돌리기 한 칸
  function moveSelToLayer(id) {
    const m = R.current.model, ly = layersOf(m).find(l => l.id === id), ids = new Set(movingSet(R.current.sel))
    if (!ly) return; if (!ids.size) return setStatus('옮길 도형을 먼저 고르세요')
    commit(m.items.map(it => (ids.has(it._id) ? { ...it, layer_id: id === 'default' ? null : id, locked: ly.locked } : it)), [...ids], '레이어 옮김')
    setStatus(`레이어 옮김: ${ids.size}개 → ${ly.name}`)
  }
  function insertTable(rows, cols, header) {
    const m = R.current.model, c = R.current.cam, W = cols * 40, H = rows * 14
    const cx = (size.w / 2 - c.x) / c.z, cy = (size.h / 2 - c.y) / c.z
    const it = base([cx - W / 2, cy - H / 2], { type: 'table', rows, cols, header, rect: [0, 0, W, H], cells: Array.from({ length: rows }, () => Array(cols).fill('')), col_widths: Array(cols).fill(1 / cols), z: topZ(m.items) + 1 })
    commit([...m.items, it], [it._id], '표'); setTool('select')
    setStatus(`표 넣음: ${rows}×${cols} — 칸을 두 번 눌러 고치기(Enter 아래·Tab 오른쪽)`)
  }
  // 표 칸(안 좌표) — 데스크톱 `cell_rect`/`cell_at`
  const cellRect = (it, r, c) => { const [x, y, w, h] = it.rect, ch = h / it.rows, e = colEdges(x, w, it.col_widths || Array(it.cols).fill(1 / it.cols)); return { x: e[c], y: y + r * ch, w: e[c + 1] - e[c], h: ch } }
  const cellAt = (it, q) => { const [x, y, w, h] = it.rect; if (q.x < x || q.y < y || q.x > x + w || q.y > y + h) return null
    const e = colEdges(x, w, it.col_widths || Array(it.cols).fill(1 / it.cols)); let c = e.findIndex((v, i) => i > 0 && q.x <= v) - 1; if (c < 0) c = it.cols - 1
    return { r: Math.min(it.rows - 1, Math.floor((q.y - y) / (h / it.rows))), c } }
  // 칸 고치기 끝 — text = 새 글(null = 취소), move = [dr, dc] 다음 칸으로(데스크톱 `_CellEditor._move`: Tab 줄넘김)
  function finishCell(text, move) {
    const ed = R.current.editing; if (!ed || ed.kind !== 'cell') return
    const m = R.current.model, it = m.items.find(x => x._id === ed.id)
    // 다음 칸은 같은 순간에 열어야 함 — 한 박자 늦게 열면 Tab 뒤 바로 친 글자가 사라짐(시험에서 겪음)
    let next = null
    if (it && move) { let r = ed.r + move[0], c = ed.c + move[1]; while (c >= it.cols) { c -= it.cols; r++ } while (c < 0) { c += it.cols; r-- }
      if (r >= 0 && r < it.rows) next = { id: it._id, kind: 'cell', r, c } }
    setEditing(next); if (!it) return
    if (text != null && text !== (it.cells?.[ed.r]?.[ed.c] || '')) {
      const cells = Array.from({ length: it.rows }, (_, r) => Array.from({ length: it.cols }, (_, c) => it.cells?.[r]?.[c] || ''))
      cells[ed.r][ed.c] = text; commit(m.items.map(x => (x._id === it._id ? { ...x, cells } : x)), [it._id], '표 칸')
    }
  }
  function startPaletteDrag(t) {
    const m = R.current.model
    const protos = t.startsWith('customsym:') ? customItems(t) : [{ ...boxItem(t, 0, 0, ...boxDefault(t)), z: topZ(m.items) + 1 }]   // 클릭만 해 놓을 때와 같은 기본 크기
    if (!protos) return
    const b0 = unionBox(protos.map(it => sceneBox(it, textBox))), w = b0.w, h = b0.h
    const others = m.items.filter(it => !it.locked).map(it => sceneBox(it, textBox))
    let last = null
    const place = e => {
      const el = document.elementFromPoint(e.clientX, e.clientY), over = !!el && (el === svg.current || svg.current.contains(el))
      const p = toSceneP(e), a = alignSnap({ x: p.x - w / 2, y: p.y - h / 2, w, h }, others, R.current.cam.z)
      return { over, its: placeAt(protos, p.x - w / 2 + a.dx, p.y - h / 2 + a.dy), guides: a.guides }
    }
    const move = e => { last = place(e); setLive(last.over ? [...m.items, ...last.its] : null); setOverlay(o => ({ ...o, guides: last.over ? last.guides : null })) }
    const up = e => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); document.body.style.cursor = ''; st.current = { space: st.current.space }
      setOverlay(o => ({ ...o, guides: null }))
      last = place(e)
      if (last.over) commit([...m.items, ...last.its], last.its.map(it => it._id), '도형'); else setLive(null)
    }
    document.body.style.cursor = 'copy'; st.current = { ...st.current, kind: 'pdrag' }; setHp(null)   // 끄는 동안 포트점 예고 끔(데스크톱도 드래그 중 억제)
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up)
  }

  // ── 그리기 ──
  function startDraw(t, p) {
    const m = R.current.model
    if (t === 'arrow') {   // 화살표 도구(데스크톱 「화살표」 — 종류는 속성 카드): 시작이 도형 근처면 붙고, 빈 곳이면 떠 있는 끝. 끄는 건 큐닷·포트점 잇기와 같은 길
      const snap = snapAt(hostsNear(p), p, R.current.cam.z, rectOf, linesNear(p))
      st.current = { ...st.current, kind: 'conn', tool: 'arrow', src: snap?.id ?? null, port: snap ? { p: snap.p, n: snap.n } : { p, n: null }, start: p, cur: p, fromQc: false, moved: false }
      return
    }
    if (t === 'text') { const it = base([p.x - TEXT_MARGIN, p.y - TEXT_MARGIN], { type: 'text', text: '', color: INK, font: 12, bg: null, z: topZ(m.items) + 1 }); commit([...m.items, it], [it._id], '글'); setEditing({ id: it._id, kind: 'text', fresh: true }); setTool('select'); return }
    if (t === 'badge') {   // 번호표 — 누른 자리에 다음 번호(데스크톱 `next_badge_number`: 연 문서의 가장 큰 번호부터 하나씩, 지워도 되돌리지 않음), 색 = 고른 선 색
      const n = Math.max(badgeN.current, ...m.items.filter(it => it.type === 'badge').map(it => it.number || 0)) + 1; badgeN.current = n
      const it = base([p.x, p.y], { type: 'badge', number: n, color: sticky.current.color === INK ? '#ffda7756' : sticky.current.color, z: topZ(m.items) + 1 })   // 선 색을 안 골랐으면 코랄(기본 잉크로 칠하면 어두운 화면에서 묻힘)
      commit([...m.items, it], [it._id], '번호표'); setTool('select'); return
    }
    if (t.startsWith('customsym:')) {   // 내 심볼 도구 — 누른 자리에 원래 크기로(데스크톱 `_create_custom_symbol_at`: 왼쪽 위 = 누른 자리)
      const protos = customItems(t); if (!protos) return
      const its = placeAt(protos, p.x, p.y); commit([...m.items, ...its], its.map(it => it._id), '심볼'); setTool('select'); return
    }
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
    const it = base([x0, y0], { type: 'polygon', closed, rect: [0, 0, Math.max(...xs) - x0, Math.max(...ys) - y0], pts: pts.map(q => [q.x - x0, q.y - y0]), ...penOf(closed), ...(closed ? {} : { fill: null }), z: topZ(R.current.model.items) + 1 })
    commit([...R.current.model.items, it], [it._id], '다각형'); setTool('select')
  }
  function finishDraw(s, p) {
    setOverlay(o => ({ ...o, draw: null }))
    const m = R.current.model, z = R.current.cam.z, click = Math.hypot(p.x - s.start.x, p.y - s.start.y) * z < 3
    let it
    if (s.tool === 'rect' || s.tool === 'ellipse' || s.tool.startsWith('sym:')) {
      let x0 = Math.min(s.start.x, p.x), y0 = Math.min(s.start.y, p.y), w = Math.abs(p.x - s.start.x), h = Math.abs(p.y - s.start.y)
      if (s.shift) { const d = Math.max(w, h); w = h = d; x0 = p.x < s.start.x ? s.start.x - d : s.start.x; y0 = p.y < s.start.y ? s.start.y - d : s.start.y }
      if (click) { [w, h] = boxDefault(s.tool); x0 = p.x - w / 2; y0 = p.y - h / 2 }   // 클릭만 = 기본 크기로 그 자리에
      it = boxItem(s.tool, x0, y0, w, h)
    } else if (s.tool === 'line') {
      if (click) return
      let { x, y } = p
      if (s.shift) { const a = Math.round(Math.atan2(y - s.start.y, x - s.start.x) / (Math.PI / 4)) * (Math.PI / 4), L = Math.hypot(x - s.start.x, y - s.start.y); x = s.start.x + L * Math.cos(a); y = s.start.y + L * Math.sin(a) }
      it = base([0, 0], { type: 'line', line: [s.start.x, s.start.y, x, y], ...penOf(false) })
    } else if (s.tool === 'pen') {
      if (s.pts.length < 2) return
      it = base([0, 0], { type: 'path', elements: s.pts.map((q, i) => [i ? 'L' : 'M', q.x, q.y]), ...penOf(false), freehand: true })
    }
    if (!it) return
    it.z = topZ(m.items) + 1
    commit([...m.items, it], [it._id], '그림'); setTool('select')
  }

  // ── 두 번 누르기 = 글 편집(글 상자) / 도형 라벨 ──
  function onDoubleClick(e) {
    if (R.current.tool === 'polygon') { finishPoly(overlay.poly || [], false); return }
    const p = toSceneP(e), lb = labelAt(p)
    if (lb) { setSel([lb.it._id]); setEditing({ id: lb.it._id, kind: 'alabel', i: lb.i }); return }
    const hit = topHit(hitPool(), p, HIT_PX / R.current.cam.z, textBox)
    if (!hit || hit.locked) return
    if (hit.type === 'table') { const cell = cellAt(hit, toLocal(hit, p)); if (cell) { setSel([hit._id]); setEditing({ id: hit._id, kind: 'cell', ...cell }) } return }
    if (isArrow(hit)) {   // 화살표 빈 자리 더블클릭 = 그 자리에 새 라벨(여러 개 — 데스크톱 `add_label_at_scene_pos`)
      const labels = labelsOf(hit), pr = projectOn(hit, toLocal(hit, p))
      labels.push({ text: '', color: hit.color || INK, font: 16, bg: null, t: pr.t, off: 0 })
      commit(R.current.model.items.map(x => (x._id === hit._id ? withLabels(hit, labels) : x)), [hit._id], '라벨')
      setEditing({ id: hit._id, kind: 'alabel', i: labels.length - 1, fresh: true }); return
    }
    if (hit.type === 'text') { setSel([hit._id]); setEditing({ id: hit._id, kind: 'text' }) }
    else if (['rect', 'ellipse', 'symbol'].includes(hit.type) || (hit.type === 'polygon' && hit.closed)) { setSel([hit._id]); setEditing({ id: hit._id, kind: 'label' }) }
  }
  function finishEdit({ text, runs }) {
    const ed = R.current.editing; setEditing(null); if (!ed) return
    const m = R.current.model, it = m.items.find(x => x._id === ed.id); if (!it) return
    let next
    if (ed.kind === 'alabel') {
      const labels = labelsOf(it)
      if (!text.trim()) labels.splice(ed.i, 1)
      else { labels[ed.i] = { ...labels[ed.i], text, runs: runs.length ? runs : undefined }; if (!labels[ed.i].runs) delete labels[ed.i].runs }
      commit(m.items.map(x => (x._id === it._id ? withLabels(it, labels) : x)), [it._id], text.trim() ? '라벨 고침' : '빈 라벨 지움'); return
    }
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
    const ob = onBoard[items.indexOf(it)], col = c => ink(c || '#ff1f1f1f', ob), bg = ob ? 'rgba(255,255,255,.9)' : 'var(--mb-editbg)'   // 글 고치는 칸도 칠판과 같은 잉크·바탕
    if (editing.kind === 'text') {
      const o = scr(toScene(it, { x: 0, y: 0 }))
      return { left: o.x, top: o.y, px: (it.font || 12) * PT * (it.scale || 1), zoom: cam.z, family: it.family ? 'board' : 'app', weight: it.weight ?? (it.bold ? 700 : 400),
        color: col(it.color), bg, rotation: it.rotation || 0, origin: scr(toScene(it, { x: it.origin?.[0] || 0, y: it.origin?.[1] || 0 })), text: it.text, runs: it.runs }
    }
    if (editing.kind === 'alabel') {
      const b = arrowLabelBoxes(it)[editing.i], L = labelsOf(it)[editing.i]; if (!b || !L) return null
      return { center: scr(toScene(it, b.a)), px: (L.font || 16) * PT * (it.scale || 1), zoom: cam.z, family: L.family ? 'board' : 'app', weight: 400, color: col(L.color || it.color), bg, align: 'center', text: L.text || '', runs: L.runs }
    }
    const a = scr(toScene(it, labelAnchor(it.type, it.kind, it.rect))), L = it.label || {}
    return { center: a, px: (L.font || 16) * PT * (it.scale || 1), zoom: cam.z, family: L.family ? 'board' : 'app', weight: 400, color: col(L.color || it.pen), bg, align: 'center', text: L.text || '', runs: L.runs }
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
      if (mod && k.toLowerCase() === 'a') return act(() => setSel(hitPool().filter(it => !it.locked).map(it => it._id)))
      if (k === 'Escape') { setOverlay(o => ({ ...o, poly: null, draw: null })); if (R.current.tool !== 'select') setTool('select'); else setSel([]); return }
      if (k === 'Enter' && overlay.poly) return act(() => finishPoly(overlay.poly, false))
      const TOOL_KEYS = { 1: 'select', 2: 'arrow', 3: 'text', 4: 'line', 5: 'polygon', 6: 'pen', 7: 'badge' }   // 데스크톱 `SHORTCUT_DEFS` 도구 1~7
      if (!mod && !e.altKey && !e.shiftKey && TOOL_KEYS[k]) return act(() => setTool(TOOL_KEYS[k]))
      if (!ids.length) { if (mod && k.toLowerCase() === 'v') return act(paste); return }
      if (k === 'Delete' || k === 'Backspace') return act(() => commit(removeItems(m.items, movingSet(ids)), [], '지움'))
      // 스타일 복사·붙여넣기(데스크톱 Ctrl+Alt+C/V) — 일반 복사보다 먼저. 글쇠 이름은 한글 입력·Alt에 따라 바뀌어 자리(code)로 봄
      if (mod && e.altKey && e.code === 'KeyC') return act(() => {
        if (ids.length !== 1) return setStatus('스타일 복사 — 도형을 하나만 고르세요')
        styleClip.current = captureStyle(m.items.find(it => it._id === ids[0])); setStatus('스타일 복사됨') })
      if (mod && e.altKey && e.code === 'KeyV') return act(() => {
        const sc = styleClip.current; if (!sc) return setStatus('붙여넣을 스타일이 없어요 — 먼저 Ctrl+Alt+C'), undefined
        const set = new Set(ids); commit(m.items.map(it => { const p = set.has(it._id) && styleFor(it, sc); return p ? { ...it, ...p } : it }), ids, '스타일 붙여넣기')
        setStatus(`스타일 붙여넣기 — ${ids.length}개`) })
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
  const hiddenL = useMemo(() => new Set(layersOf(model).filter(l => !l.visible).map(l => l.id)), [model])
  const order = useMemo(() => drawOrder(items).filter(([it]) => !hiddenL.has(layerIdOf(it))), [items, hiddenL]); R.current.order = order
  const onBoard = useMemo(() => boardMembership(items), [items])
  const routes = useMemo(() => resolveRoutes(items, rectOf), [items])
  const bounds = useMemo(() => items.map(itemBounds), [items])
  const view = { x: -cam.x / cam.z, y: -cam.y / cam.z, w: size.w / cam.z, h: size.h / cam.z }, mg = 40 / cam.z
  const visible = order.filter(([it, i]) => { const b = bounds[i]; return it.type === 'board' || (b.x < view.x + view.w + mg && b.x + b.w > view.x - mg && b.y < view.y + view.h + mg && b.y + b.h > view.y - mg) })
  const editingId = editing?.id

  // ── 덧그림(칠판 좌표, 굵기는 ÷z) ──
  const z = cam.z, sw = 1.6 / z
  const multi = selItems.length > 1
  const outline = it => {
    // 중심선 = 화면 1.6px, 선 가운데를 지나감(데스크톱과 통일 — 선 원래 색이 가장자리로 보임, 2026-10-18 사용자 선택)
    const s = it.scale || 1, cw = sw / s
    if (it.type === 'line') { const a = toScene(it, { x: it.line[0], y: it.line[1] }), b = toScene(it, { x: it.line[2], y: it.line[3] }); return <line key={it._id} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={BLUE} strokeWidth={cw * s} strokeLinecap="round" /> }
    if (it.type === 'sarrow') {   // 선택 선도 라벨 자리는 비움(글자 위로 지나가지 않게), 모서리는 화살표처럼 둥글게
      const gaps = arrowLabelBoxes(it).map(b => b.gap).filter(Boolean), pieces = cutPolyline(it.pts.map(([x, y]) => ({ x, y })), gaps)
      return <g key={it._id} transform={transformOf(it)}>{pieces.map((pc, k) => <path key={k} d={roundedPath(pc, sarrowRadius(it))} fill="none" stroke={BLUE} strokeWidth={cw} strokeLinecap="round" strokeLinejoin="round" />)}</g>
    }
    const g = selShape(it, textBox)
    return <g key={it._id} transform={transformOf(it)}><g transform={g.off ? `translate(${g.off[0]},${g.off[1]})` : undefined}>
      {multi && g.closed ? selBand(it._id, g, it, z, BAND_ALPHA, BLUE)
        : <path d={g.d} fill="none" stroke={BLUE} strokeWidth={cw} strokeLinejoin="round" strokeLinecap="round" />}</g></g>
  }
  // 범위 선택 미리보기 — 걸릴 것마다 띠(데스크톱 drawForeground: 닫힌 도형은 바깥, 선은 양옆, 채움 알파 90)
  const pvColor = overlay.rubber && overlay.rubber.b.x < overlay.rubber.a.x ? RB_GREEN : RB_BLUE
  const preview = it => { const g = selShape(it, textBox)
    return <g key={'pv' + it._id} transform={transformOf(it)}><g transform={g.off ? `translate(${g.off[0]},${g.off[1]})` : undefined}>{selBand('pv' + it._id, g, it, z, PREVIEW_ALPHA, pvColor)}</g></g> }
  const handles = single && !editing && !live ? handlesOf(single) : []
  // 속성 카드 — 고른 것 모두에(해당하는 것만, 데스크톱 `_edit_items`). 모서리는 직각만
  const selArrows = selItems.filter(isArrow), selArrowIds = new Set(selArrows.map(x => x._id)), selIds = new Set(selItems.map(x => x._id))
  function setProps(per, label, merge) {   // per(아이템) → 고칠 값 | null(해당 없음)
    const m = R.current.model, cur = m.items.filter(x => selIds.has(x._id))
    // 다음에 그릴 것의 기본값 = 처음 고친 것에 들어간 값(데스크톱 sticky — 보드 바탕·글 색은 아님)
    const a0 = cur.find(isArrow), pa = a0 && per(a0)
    if (pa) for (const k of ['color', 'width', 'style', 'head', 'head_start', 'head_scale', 'curve_r']) if (pa[k] !== undefined) sticky.current[k] = pa[k]
    const s0 = cur.find(x => x.pen !== undefined), ps = s0 && per(s0)
    if (ps) { if (ps.pen !== undefined) sticky.current.color = ps.pen; if (ps.width !== undefined) sticky.current.width = ps.width; if (ps.style !== undefined) sticky.current.style = ps.style; if (ps.fill !== undefined) stickyFill.current = ps.fill }
    commit(m.items.map(x => { if (!selIds.has(x._id)) return x; const p = per(x); if (!p) return x; const pt = { ...p }; if (x.type !== 'sarrow') delete pt.curve_r; return { ...x, ...pt } }), sel, label, merge ? merge + [...selIds].join() : null)
  }
  // 여러 개 선택 틀 — 화살촉까지 감쌈(데스크톱 `_GroupTransform.bbox` = 꼭짓점 + 화살촉 끝, 2026-10-18 사용자와 맞춤)
  const selBoxOf = it => {
    const b = sceneBox(it, textBox); if (it.type !== 'sarrow' && it.type !== 'arrow') return b
    const hs = (selShape(it, textBox).heads || []).flat().map(q => toScene(it, q)); if (!hs.length) return b
    const xs = [b.x, b.x + b.w, ...hs.map(q => q.x)], ys = [b.y, b.y + b.h, ...hs.map(q => q.y)]
    return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) }
  }
  const multiBox = selItems.length > 1 ? unionBox(selItems.map(selBoxOf)) : null
  const rb = overlay.rubber, dr = overlay.draw
  // 알약(구간 가운데, 변 방향으로 길쭉) — 채움 = 실제 알약, 속 빈 = 나눠 끌 자리 미리보기(데스크톱 `_paint_segment_handles`)
  const pill = (key, p, horizontal, filled) => { const half = SEG_HANDLE_PX / z, th = 3.5 / z
    return <rect key={key} x={p.x - (horizontal ? half : th)} y={p.y - (horizontal ? th : half)} width={2 * (horizontal ? half : th)} height={2 * (horizontal ? th : half)} rx={th} ry={th}
      fill={filled ? BLUE : '#fff'} stroke={filled ? '#fff' : BLUE} strokeWidth={(filled ? 1 : 1.4) / z} /> }
  // 포트점 예고 — 가장 가까운 도형 하나의 포트 넷(속 빈 점), 누르면 시작될 자리는 채운 점(데스크톱 `_draw_port_dots`)
  const portDots = (() => {
    const hp = overlay.hp, host = hp && (byId.get(hp.id) || R.current.vhosts.get(hp.id)); if (!host || editing) return null
    const r = 5 / z, tp = hp.target?.id === hp.id ? hp.target.p : null, dots = hostPorts(host, rectOf).map(q => q.p)
    const hit = q => tp && Math.abs(q.x - tp.x) < 0.5 && Math.abs(q.y - tp.y) < 0.5
    return <g>{dots.map((q, i) => <circle key={i} cx={q.x} cy={q.y} r={r} fill={hit(q) ? BLUE : '#fff'} stroke={hit(q) ? '#fff' : BLUE} strokeWidth={(hit(q) ? 1.5 : 1.4) / z} />)}
      {tp && !dots.some(hit) && <circle cx={tp.x} cy={tp.y} r={r} fill={BLUE} stroke="#fff" strokeWidth={1.5 / z} />}</g>
  })()

  return (
    <div style={{ position: 'absolute', inset: 0 }}>
      <svg ref={svg} width={size.w} height={size.h} style={{ display: 'block', cursor, touchAction: 'none', userSelect: 'none', WebkitUserSelect: 'none' }} data-testid="board"
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onDoubleClick={onDoubleClick} onContextMenu={e => e.preventDefault()}>
        <g transform={`translate(${cam.x},${cam.y}) scale(${z})`} style={{ '--z': z }}>
          {visible.map(([it, i]) => (it._id === editingId ? <g key={it._id} opacity={0.15}><Item it={it} idx={i} onBoard={onBoard[i]} route={routes.get(i)} dark={dark} /></g>
            : <Item key={it._id} it={it} idx={i} onBoard={onBoard[i]} route={routes.get(i)} dark={dark} />))}
          {selItems.map(outline)}
          {overlay.rubber?.hits?.map(id => byId.get(id)).filter(Boolean).map(preview)}
          {multiBox && <rect x={multiBox.x} y={multiBox.y} width={multiBox.w} height={multiBox.h} fill="none" stroke={BLUE} strokeWidth={1 / z} strokeDasharray={`${4 / z} ${3 / z}`} />}
          {selItems.filter(it => it.locked).map(it => { const b = sceneBox(it, textBox); return <text key={'lk' + it._id} x={b.x + b.w} y={b.y} fontSize={12 / z} fill={BLUE}>🔒</text> })}
          {handles.map(h => (h.pill ? pill(h.key, h.p, h.horizontal, true) : h.bend ? <circle key={h.key} cx={h.p.x} cy={h.p.y} r={HANDLE / 2 / z} fill={BEND_GREEN} stroke="#fff" strokeWidth={1 / z} />
            : h.qc ? <circle key={h.key} cx={h.p.x} cy={h.p.y} r={(HANDLE * (hoverKey === h.key ? 0.75 : 0.45)) / z} fill={QC_BLUE} stroke="#fff" strokeWidth={1 / z} style={{ transition: 'r .12s ease-out' }} />
            : h.round ? <circle key={h.key} cx={h.p.x} cy={h.p.y} r={HANDLE / 2 / z} fill={PEACH} stroke="#fff" strokeWidth={1 / z} />
            : <rect key={h.key} x={h.p.x - HANDLE / 2 / z} y={h.p.y - HANDLE / 2 / z} width={HANDLE / z} height={HANDLE / z} fill={BLUE} stroke="#fff" strokeWidth={1 / z} />))}
          {overlay.conn && <polyline points={overlay.conn.map(q => `${q.x},${q.y}`).join(' ')} fill="none" stroke={BLUE} strokeWidth={2 / z} strokeDasharray={`${6 / z} ${4 / z}`} />}
          {portDots}
          {overlay.segPrev && !live && pill('segprev', overlay.segPrev.p, overlay.segPrev.horizontal, false)}
          {overlay.guides?.map((g, i) => {
            const [x1, y1, x2, y2] = g.axis === 'v' ? [g.at, g.from, g.at, g.to] : [g.from, g.at, g.to, g.at], dash = g.role === 'center' ? undefined : `${6 / z} ${4 / z}`
            return <g key={i}><line x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(0,0,0,.7)" strokeWidth={3 / z} strokeDasharray={dash} /><line x1={x1} y1={y1} x2={x2} y2={y2} stroke={GUIDE} strokeWidth={1.5 / z} strokeDasharray={dash} /></g>
          })}
          {rb && (() => { const x = Math.min(rb.a.x, rb.b.x), y = Math.min(rb.a.y, rb.b.y), w = Math.abs(rb.b.x - rb.a.x), h = Math.abs(rb.b.y - rb.a.y), win = rb.b.x >= rb.a.x
            return <rect x={x} y={y} width={w} height={h} fill={win ? RB_BLUE : RB_GREEN} fillOpacity={45 / 255} stroke={win ? RB_BLUE : RB_GREEN} strokeWidth={1 / z} strokeDasharray={win ? undefined : `${4 / z} ${3 / z}`} /> })()}
          {dr && (dr.tool === 'rect' || dr.tool.startsWith('sym:') ? <rect x={Math.min(dr.a.x, dr.b.x)} y={Math.min(dr.a.y, dr.b.y)} width={Math.abs(dr.b.x - dr.a.x)} height={Math.abs(dr.b.y - dr.a.y)} fill="none" stroke={BLUE} strokeWidth={1.5 / z} />
            : dr.tool === 'ellipse' ? <ellipse cx={(dr.a.x + dr.b.x) / 2} cy={(dr.a.y + dr.b.y) / 2} rx={Math.abs(dr.b.x - dr.a.x) / 2} ry={Math.abs(dr.b.y - dr.a.y) / 2} fill="none" stroke={BLUE} strokeWidth={1.5 / z} />
            : dr.tool === 'line' ? <line x1={dr.a.x} y1={dr.a.y} x2={dr.b.x} y2={dr.b.y} stroke={BLUE} strokeWidth={1.5 / z} />
            : <polyline points={dr.pts.map(q => `${q.x},${q.y}`).join(' ')} fill="none" stroke={BLUE} strokeWidth={1.5 / z} />)}
          {overlay.poly && <polyline points={overlay.poly.map(q => `${q.x},${q.y}`).join(' ')} fill="none" stroke={BLUE} strokeWidth={1.5 / z} />}
        </g>
      </svg>
      {editing?.kind === 'cell' && (() => { const it = byId.get(editing.id); if (!it) return null
        const r = cellRect(it, editing.r, editing.c), pts = [[r.x, r.y], [r.x + r.w, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y + r.h]].map(([x, y]) => scr(toScene(it, { x, y })))
        const xs = pts.map(q => q.x), ys = pts.map(q => q.y), h = Math.max(...ys) - Math.min(...ys)
        return <CellInput key={`${editing.id}-${editing.r}-${editing.c}`} init={it.cells?.[editing.r]?.[editing.c] || ''} onDone={finishCell}
          style={{ left: Math.min(...xs), top: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: h, fontSize: Math.max(10, Math.min(h * 0.6, 18)), fontWeight: it.header && editing.r === 0 ? 700 : 400 }} /> })()}
      {editing && editing.kind !== 'cell' && (() => { const s = editSpec(); if (!s) return null
        return <TextEditor key={editing.id} spec={s} onDone={finishEdit} /> })()}
      {selItems.length > 0 && !editing && <Props items={selItems} kind={selArrows.length && selArrows.every(x => arrowKindOf(x) === arrowKindOf(selArrows[0])) ? arrowKindOf(selArrows[0]) : null} set={setProps} rotate={(it, a) => rotateTo(it, a, false)} library={library ? { symbols: library, folders: libFolders } : null} onSwapCustom={swapToCustom} dark={dark}
        onKind={k => { stickyKind.current = k; const m = R.current.model; commit(m.items.map(x => (selArrowIds.has(x._id) ? swapArrowKind(x, k, m.items, rectOf, sticky.current.curve_r) : x)), sel, '화살표 종류') }} />}
    </div>
  )
})

// 표 칸 한 줄 편집기(데스크톱 `_CellEditor`) — Enter 아래 칸, Tab 오른쪽(줄 끝이면 다음 줄), Shift+Tab 왼쪽, Esc 취소, 밖을 누르면 확정
function CellInput({ init, onDone, style }) {
  const done = useRef(false), fin = (v, mv) => { if (done.current) return; done.current = true; onDone(v, mv) }
  return <input autoFocus defaultValue={init} onFocus={e => e.target.select()} onBlur={e => fin(e.target.value, null)} onPointerDown={e => e.stopPropagation()}
    onKeyDown={e => { e.stopPropagation(); if (e.nativeEvent.isComposing) return
      if (e.key === 'Enter') { e.preventDefault(); fin(e.target.value, [1, 0]) } else if (e.key === 'Tab') { e.preventDefault(); fin(e.target.value, [0, e.shiftKey ? -1 : 1]) } else if (e.key === 'Escape') fin(null, null) }}
    style={{ position: 'absolute', boxSizing: 'border-box', textAlign: 'center', border: '2px solid #89b4fa', borderRadius: 2, background: 'var(--mb-editbg, #fff)', color: 'var(--mb-ink)', padding: 0, outline: 'none', fontFamily: "'Pretendard', sans-serif", ...style }} />
}

// ── 선택 표시 모양 — 데스크톱 `_paint_selection_highlight`: 하나 선택·화살표 = 1.6px 중심선, 여러 개 중 닫힌 도형 = 바깥 띠 ──
const BAND_ALPHA = 110 / 255, PREVIEW_ALPHA = 90 / 255
const RB_BLUE = 'rgb(70,130,220)', RB_GREEN = 'rgb(90,190,90)'   // 범위 상자·미리보기 색(데스크톱 drawForeground: 왼→오 파랑, 오→왼 초록, 상자 채움 알파 45)
const rectD = (x, y, w, h) => `M${x},${y} H${x + w} V${y + h} H${x} Z`
const ellipseD = (x, y, w, h) => { const rx = w / 2, ry = h / 2; return `M${x},${y + ry} A${rx},${ry} 0 1 0 ${x + w},${y + ry} A${rx},${ry} 0 1 0 ${x},${y + ry} Z` }
const roundRectD = (x, y, w, h, r) => `M${x + r},${y} H${x + w - r} A${r},${r} 0 0 1 ${x + w},${y + r} V${y + h - r} A${r},${r} 0 0 1 ${x + w - r},${y + h} H${x + r} A${r},${r} 0 0 1 ${x},${y + h - r} V${y + r} A${r},${r} 0 0 1 ${x + r},${y} Z`
// 아이템 안 좌표의 외곽선 d + 닫힘 여부 + (상자·원이면) 바탕 상자 — 상자·원은 띠를 계산으로, 나머지는 잘라 내기로
function selShape(it, textBox) {
  const line = pts => pts.map(([x, y], k) => `${k ? 'L' : 'M'}${x},${y}`).join(' ')
  switch (it.type) {
    case 'line': { const [x1, y1, x2, y2] = it.line; return { d: line([[x1, y1], [x2, y2]]), closed: false, lines: [{ pts: [{ x: x1, y: y1 }, { x: x2, y: y2 }], capS: true, capE: true }] } }
    case 'sarrow': {   // 둥근 모서리·라벨 자리 비움(화살표 그림과 같게)
      const pts = it.pts.map(([x, y]) => ({ x, y })), gaps = arrowLabelBoxes(it).map(l => l.gap).filter(Boolean), size = headSize(it.width, it.head_scale), end = it.head !== false, start = !!it.head_start
      const r = sarrowRadius(it), n = pts.length, pieces = cutPolyline(trimmedPts(pts, size, end, start), gaps)
      const lines = pieces.map((pc, k) => ({ pts: roundedPts(pc, r), capS: k > 0 || !start, capE: k < pieces.length - 1 || !end }))   // 화살촉 쪽 끝은 반원 없이(촉이 덮음)
      return { d: cutPolyline(pts, gaps).map(pc => roundedPath(pc, r)).join(' '), lines, closed: false, heads: arrowHeads(pts[n - 2], pts[n - 1], pts[1], pts[0], size, end, start), labels: labelRects(it) }
    }
    case 'arrow': {
      const P = ([x, y]) => ({ x, y }), p0 = P(it.p1), p3 = P(it.p2), c1 = it.ctrl1 ? P(it.ctrl1) : p3, c2 = it.ctrl2 ? P(it.ctrl2) : p0, size = headSize(it.width, it.head_scale), end = it.head !== false, start = !!it.head_start
      const pts = it.ctrl1 ? Array.from({ length: 33 }, (_, k) => { const t = k / 32, u = 1 - t; return { x: u * u * u * p0.x + 3 * u * u * t * c1.x + 3 * u * t * t * c2.x + t * t * t * p3.x, y: u * u * u * p0.y + 3 * u * u * t * c1.y + 3 * u * t * t * c2.y + t * t * t * p3.y } }) : [p0, p3]
      const cut = q => { let a = 0, b = q.length; const L = size * 0.85, far = (i, tip) => Math.hypot(q[i].x - tip.x, q[i].y - tip.y) >= L
        if (end) while (b > a + 2 && !far(b - 2, p3)) b--; if (start) while (a < b - 2 && !far(a + 1, p0)) a++
        return trimmedPts(q.slice(a, b), 0, false, false) }
      const body = pts.length > 2 ? cut(pts) : trimmedPts(pts, size, end, start)
      return { d: it.ctrl1 ? `M${it.p1} C${it.ctrl1} ${it.ctrl2} ${it.p2}` : line([it.p1, it.p2]), lines: [{ pts: body, capS: !start, capE: !end }], closed: false, heads: arrowHeads(c2, p3, c1, p0, size, end, start), labels: labelRects(it) }
    }
    case 'path': return { d: it.elements.map(e => e[0] + e.slice(1).join(' ')).join(' '), closed: !!it.fill, lines: flatten(it.elements).map(pc => ({ pts: pc, capS: true, capE: true })) }
    case 'polygon': return { d: line(it.pts) + (it.closed ? ' Z' : ''), closed: !!it.closed, lines: [{ pts: it.pts.map(([x, y]) => ({ x, y })), capS: true, capE: true }] }
    case 'badge': return { d: ellipseD(-17, -17, 34, 34), closed: true, box: [-17, -17, 34, 34], round: true }   // 데스크톱 `_BadgeItem._content_rect`(반지름 15 + 2)
    case 'ellipse': return { d: ellipseD(...it.rect), closed: true, box: it.rect, round: true }
    case 'symbol': { const [x, y, w, h] = it.rect; return { d: symbolPath(it.kind, w, h).d, closed: true, off: [x, y] } }
    default: { const b = it.type === 'text' ? [0, 0, textBox(it).w, textBox(it).h] : localRect(it); return { d: rectD(...b), closed: true, box: b } }
  }
}
// 화살표 라벨 상자(글 있는 것만) — 데스크톱은 라벨이 따로 고를 수 있는 아이템이라 범위 미리보기에 라벨 상자 띠도 뜬다
const labelRects = it => arrowLabelBoxes(it).filter(l => !l.empty).map(l => [l.left, l.top, l.w, l.h])
// 화살촉 삼각형(있는 끝만) — 끝 = (바로 앞 점, 끝점), 시작 = (두 번째 점, 첫 점)
function arrowHeads(a1, tip1, a0, tip0, size, end, start) {
  const tri = (a, b) => headTriangle(b, Math.atan2(b.y - a.y, b.x - a.x), size)
  return [...(end ? [tri(a1, tip1)] : []), ...(start ? [tri(a0, tip0)] : [])]
}
// 띠 — 폭 = 도형 선 굵기 + 3(칠판 단위, 줌 따라 커짐), 닫힌 도형은 바깥 절반만, 1px 테두리(데스크톱 `_highlight_band`)
function selBand(key, g, it, z, alpha, color) {
  const s = it.scale || 1, hw = (Math.max(it.width || 1, 1) + 3) / 2
  if (g.closed && g.box) {
    const [x, y, w, h] = g.box, outer = g.round ? ellipseD(x - hw, y - hw, w + 2 * hw, h + 2 * hw) : roundRectD(x - hw, y - hw, w + 2 * hw, h + 2 * hw, hw)
    return <path d={`${outer} ${g.round ? ellipseD(x, y, w, h) : rectD(x, y, w, h)}`} fillRule="evenodd" fill={color} fillOpacity={alpha} stroke={color} strokeWidth={1 / z / s} />
  }
  if (!g.closed) {   // 선 띠 = 윤곽 다각형(계산) + 키운 화살촉, 채움은 한 겹(무리 투명도 — 겹친 자리가 두 번 진해지지 않게), 테두리는 서로의 안쪽을 잘라 하나로 보이게
    const ew = 1 / z / s, P = q => q.map(v => `${v.x},${v.y}`).join(' '), polyD = q => 'M' + q.map(v => `${v.x},${v.y}`).join(' L') + ' Z', BIG = 'M-1e7,-1e7 H1e7 V1e7 H-1e7 Z'
    const grow = tri => { const cx = (tri[0].x + tri[1].x + tri[2].x) / 3, cy = (tri[0].y + tri[1].y + tri[2].y) / 3
      return tri.map(v => { const d = Math.hypot(v.x - cx, v.y - cy) || 1; return { x: v.x + ((v.x - cx) / d) * 3, y: v.y + ((v.y - cy) / d) * 3 } }) }   // 데스크톱 `_expand_polygon(tri, 3)`
    const outs = (g.lines || []).filter(l => l.pts.length).map(l => strokeOutline(l.pts, hw, l.capS, l.capE)), heads = (g.heads || []).map(grow)
    const idH = 'selh-' + key, idB = 'selb-' + key
    return <>
      <g opacity={alpha}>{outs.map((o, i) => <polygon key={i} points={P(o)} fill={color} />)}{heads.map((h, i) => <polygon key={'h' + i} points={P(h)} fill={color} />)}</g>
      {heads.length > 0 && <clipPath id={idH}><path d={`${BIG} ${heads.map(polyD).join(' ')}`} clipRule="evenodd" /></clipPath>}
      {heads.length > 0 && <clipPath id={idB}><path d={`${BIG} ${outs.map(polyD).join(' ')}`} clipRule="evenodd" /></clipPath>}
      <g clipPath={heads.length ? `url(#${idH})` : undefined}>{outs.map((o, i) => <polygon key={i} points={P(o)} fill="none" stroke={color} strokeWidth={ew} strokeLinejoin="round" />)}</g>
      <g clipPath={`url(#${idB})`}>{heads.map((h, i) => <polygon key={i} points={P(h)} fill="none" stroke={color} strokeWidth={ew} />)}</g>
      {g.labels?.map(([x, y, w, h], i) => <path key={'l' + i} d={`${roundRectD(x - 2, y - 2, w + 4, h + 4, 2)} ${rectD(x, y, w, h)}`} fillRule="evenodd" fill={color} fillOpacity={alpha} stroke={color} strokeWidth={ew} />)}
    </>
  }
  // 심볼·다각형: 굵게 그은 외곽선 중 도형 밖만 남김(clipPath = 모양으로 자름, 색은 안 씀 — 마스크는 다크 확장이 색을 바꿔 깨졌다)
  const id = 'selclip-' + key
  return <><clipPath id={id}><path d={`M-1e7,-1e7 H1e7 V1e7 H-1e7 Z ${g.d}`} clipRule="evenodd" /></clipPath>
    <path d={g.d} fill="none" stroke={color} strokeOpacity={alpha} strokeWidth={2 * hw} strokeLinejoin="round" clipPath={`url(#${id})`} />
    <path d={g.d} fill="none" stroke={color} strokeWidth={1 / z / s} /></>
}

const transformOf = it => {
  const [x, y] = it.pos || [0, 0], r = it.rotation || 0, s = it.scale || 1, [ox, oy] = it.origin || [0, 0]
  return `translate(${x},${y}) translate(${ox},${oy}) rotate(${r}) scale(${s}) translate(${-ox},${-oy})`
}
