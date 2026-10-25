// 직접 만드는 칠판 2단계 — 기본 편집(데스크톱 `core_view` 규칙): 선택(클릭·범위·Shift)·이동(Shift = 축 고정)·크기·회전·스마트 정렬선·
// 되돌리기·복사/붙여넣기/복제·삭제·묶기·잠금·순서·반전·방향키, 그리기 도구(상자·원·글·선·펜·다각형), 글 편집(TipTap).
// 화면 = 칠판 × z + (x, y). 손잡이·선 굵기는 화면 px 고정(÷ z).
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import { flushSync } from 'react-dom'
import { arrowAt, arrowLabelBoxes, cellFontPx, cellStyle, fitTable, legendLayout, tableMins, fitTextHeight, ink, Item, LABEL_PAD, layoutText, measure, memoHeight, memoLayout, memoLinkAt, rr, isDeepPaper, deepPaper } from './render.jsx'
import { DOC_NAME, boardMembership, drawOrder, itemBounds } from './doc.js'
import { docText } from './find.jsx'
import { keyHeaders } from './kairosKey.js'
import { startMic } from './mic.js'
import { APP_FONT, paperWH, PT, TEXT_MARGIN, urlSpans, cutPolyline, headSize, headTriangle, labelAnchor, roundedPath, roundedPts, strokeOutline, trimmedPts } from './geom.js'
import { applyRouting, minStubs, resolveRoutes, sarrowRadius, sceneRect } from './arrows.js'
import { alignSnap } from './align.js'
import { CHART_MIN, isChart } from './chart.js'
import { deepLayout, deepWaste, variantsOf } from './deep.js'
import { deepHead, deepMeasure, deepSection } from './deepboard.js'
import { styleOf } from './deepstyle.js'
import { ROUTE_BOX, bindPt, dropTarget, edgeMid, bindEnd, groupFrac, groupHost, hostPorts, isBindHost, isConnHost, isHollow, isSnapLine, nearestBorder, OPP, qcDelta, qcDots, snapAt } from './connect.js'
import { routeOrtho } from '../route.js'
import { projectToCurve, projectToPath, snapLabelOff } from './arrowedit.js'
import { beginSegment, beginSubdivide, bendCurve, BEND_TS, curvePoint, dragSegment, endSegment, nearestSegment, onPill, SEG_HANDLE_PX, SEG_HIT_PX, segmentHandles, setCurveEnd, snapCurve, subdividePreview } from './arrowedit.js'
import { sarrowRouting } from './arrows.js'
import { fromEcad, newId } from './model.js'
import { bakeSarrow } from './xform.js'
import {
  applyRect, boardContents, keepBinds, duplicate, readingOrder, tableOp, expandGroups, flatten, followArrows, groupItems, localRect, mirror, moveItems, removeItems, resizeRect,
  rotateTo, rubberSelect, sceneBox, toLocal, toScene, toggleLock, topHit, ungroupItems, unionBox, zOrder,
} from './edit.js'
import { TextEditor } from './text.jsx'
import { Props, captureStyle, styleFor } from './props.jsx'
import { FormatBar } from './formatbar.jsx'
import { arrowKindOf, swapArrowKind } from './arrowkind.js'
import { shapeWH, symbolPath } from './symbols.js'
import { cssColor } from '../ecadFormat.js'
import { colEdges, colFracs, frameTag, frameTagFs, rowEdges } from './geom.js'
import { orderedFrames, setFrameOrder } from './edit.js'
import { Presenter } from './present.jsx'
import { layersOf, layerIdOf } from './layers.jsx'
import { buildSvg, download, exportPdf, exportPng, exportSvg, fontFaces, pngBlob, usesBoardFont, weightsOf } from './exporter.jsx'
import { buildHtml } from './htmlshare.js'
import { ContextMenu } from './ctxmenu.jsx'
import { pdfGoPage, pdfLayout, pdfPageAt, pdfScroll, pdfSelectedText } from './pdfcard.jsx'
import { answerTable, freeSpot, nearSpot, sourceLine } from '../chatFormat.js'
import { LIVE_H, LIVE_W, bigPage, liveFits } from './livecard.js'
import { WEB_HEAD, WEB_INFO_H, WEB_SLEEP_PX, fetchLinkInfo, isYoutube, normalizeUrl, openBtnRect, playYoutube, siteOf, webCardFields } from './webcard.js'
import { legendEntries, restyleLegendRow, syncLegends } from './legend.js'
import { LINE_COLORS, LINE_KINDS, MEMO, MUTED, convertLine, lineUnit, memoFromAnswer, memoText, moveLines, pickLines, recolorLine, selIdx, selUnits, toggleTodos } from './memo.js'
import { MemoEditor } from './memoedit.jsx'
import { htmlPlan, looksMarkdown, textKind, tsvRows } from './clipin.js'
import { looksSvg, svgFits, svgItems } from './svgin.js'
import { BoardSkeleton } from './skeleton.jsx'
import { applyDelta, itemDelta, mergeDelta } from './sync.js'

const ZOOM_STEP = 1.15, ZMIN = 0.02, ZMAX = 40
const BLUE = '#89b4fa', PEACH = '#fab387', GUIDE = 'rgb(230,60,160)'   // 데스크톱 theme BLUE·PEACH, 가이드선 마젠타
const HANDLE = 10, HIT_PX = 4, EDGE_PX = 5
const INK = '#ff1f1f1f'   // 새로 그리는 선·글 기본색(밝은 칠판)
// 다른 사람 색 — 접속 id로 늘 같은 색(테두리·이름표)
const PERSON_COLORS = ['#e8590c', '#7048e8', '#0c8599', '#d6336c', '#2f9e44', '#1971c2']
const personColor = id => PERSON_COLORS[[...String(id)].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) >>> 0, 7) % PERSON_COLORS.length]
const BOXY = new Set(['rect', 'ellipse', 'symbol', 'image', 'table', 'board', 'polygon', 'path', 'frame', 'web', 'memo', 'legend', 'doc', 'pdf'])

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
  if (isHollow(it)) return false   // 프레임 속 = 빈 곳(안의 도형 몫)
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
const PEN_LAYER = 'pen-notes'   // 발표 판서 레이어
const IMG_FIXED = 680   // 대화창 그림 후보를 칠판에 붙일 때 긴 변(칠판 단위, 답 메모 340의 두 배) — 배율과 상관없이 같은 크기
const snap45 = (a, p) => { const t = Math.round(Math.atan2(p.y - a.y, p.x - a.x) / (Math.PI / 4)) * (Math.PI / 4), L = Math.hypot(p.x - a.x, p.y - a.y); return { x: a.x + L * Math.cos(t), y: a.y + L * Math.sin(t) } }   // Shift = 45° 단위
const base = (pos, extra) => ({ pos, scale: 1, rotation: 0, z: 0, origin: [0, 0], locked: false, group_id: null, layer_id: null, _id: newId(), ...extra })

// 뜬 대화창 폭(좁은 창 — main.jsx가 칠판 칸에 `--mb-right-inset`으로 적음) — 「다 보기」·프레임으로 가기·AI 답 자리는 그만큼 오른쪽을 뺌(2026-10-19)
export const rightInset = el => (el ? parseFloat(getComputedStyle(el).getPropertyValue('--mb-right-inset')) || 0 : 0)

export const Editor = forwardRef(function Editor({ others = [], dark, model, setModel, onCommit, size, cam, setCam, tool, setTool, setStatus, library, libFolders, activeLayer, onSel, onExportSel, onFit, onDark, onHelp, onAsk, onMeet, marks = [], readOnly = false }, ref) {   // readOnly = 게시 링크로 보기(2026-10-18 공동작업 — 끌기 = 화면 이동, 고치기 없음)
  const [sel, setSel] = useState([])
  const [live, setLive] = useState(null)          // 끄는 동안 보이는 아이템 목록(놓으면 확정)
  const [overlay, setOverlay] = useState({})      // { rubber, guides, draw, poly }
  const [editing, setEditing] = useState(null)    // 글 편집 { id, kind:'text'|'label' }
  const [cursor, setCursor] = useState('default')
  const st = useRef({}), hist = useRef({ past: [], future: [] }), clip = useRef({ items: [], seq: 0 }), svg = useRef(null)
  const items = live || model.items
  const zBack = useRef(null)   // Z 다 보기 전 자리 {before, after} — Z 한 번 더 = 되돌아감
  const R = useRef(); R.current = { vhosts: new Map(), ...R.current, model, sel, cam, tool, items, editing, hp: overlay.hp, activeLayer, live: !!live, poly: !!overlay.poly, lpt: overlay.lpt, others }
  // 누를 수 있는 것 = 숨긴 레이어 밖(데스크톱 setVisible(False)는 눌리지도 않음)
  const layerLocked = it => { const l = layersOf(R.current.model).find(x => x.id === layerIdOf(it)); return !!l?.locked }
  const hitPool = () => { const m = R.current.model, hid = new Set(layersOf(m).filter(l => !l.visible).map(l => l.id)); return hid.size ? m.items.filter(it => !hid.has(layerIdOf(it))) : m.items }   // vhosts = 묶음 가상 상자('g:…', hostsNear가 채움)

  const toSceneP = useCallback(e => { const r = svg.current.getBoundingClientRect(), c = R.current.cam; return { x: (e.clientX - r.left - c.x) / c.z, y: (e.clientY - r.top - c.y) / c.z } }, [])
  const scr = p => ({ x: p.x * cam.z + cam.x, y: p.y * cam.z + cam.y })

  // 확정 — 붙은 화살표 따라가기 + 되돌리기 칸
  // merge = 같은 열쇠로 1.5초 안에 또 고치면 되돌리기 한 칸으로 묶음(−/+ 연타·색 고르기 끌기)
  // 고친 뒤 알릴 말 — 고치면 곧바로 「고치는 중…」·「저장됨」(main `onCommit`)이 알림을 덮으므로 저장 알림 뒤에 다시(크레딧·막힘처럼 꼭 봐야 할 말만)
  const sayLater = msg => setTimeout(() => setStatus(msg), 1200)
  const commit = useCallback((next, nextSel, label = '', merge = null) => {
    const prev = R.current.model.items, h = hist.current, now = Date.now()
    // 잠긴 도형 = 고를 수는 있어도 안 바뀜(2026-10-25 사용자 — 옮기기·지우기·고치기만 막음). 길목 한 곳에서: 잠긴 채 바뀐 것은 옛것으로, 사라진 것은 되살림. 잠금을 푸는 것(locked: false)만 통과
    const lockedPrev = new Map(prev.filter(it => it.locked).map(it => [it._id, it]))
    if (lockedPrev.size) { let kept = 0; const seen = new Set()
      next = next.map(it => { const o = lockedPrev.get(it._id); if (o) seen.add(it._id); if (!o || it === o || !it.locked) return it; if (JSON.stringify(it) !== JSON.stringify(o)) kept++; return o })   // 통째로 새로 만든(값은 같은) 것은 막은 것으로 안 셈
      const gone = [...lockedPrev.values()].filter(o => !seen.has(o._id)); kept += gone.length; next = [...next, ...gone]
      if (kept) sayLater(`잠긴 도형 ${kept}개는 그대로예요 — 바꾸려면 먼저 잠금 해제(Ctrl+L)`) }
    const al = R.current.activeLayer, ly = al && al !== 'default' && layersOf(R.current.model).find(l => l.id === al)
    if (ly && ly.visible && !ly.locked) { const had = new Set(prev.map(it => it._id)); next = next.map(it => (had.has(it._id) || it.layer_id ? it : { ...it, layer_id: al })) }
    next = next.map(it => (it.type === 'table' && !isChart(it) && (it.font || it.cell_styles) ? fitTable(it) : it))   // 직접 정한 표 글자 = 그대로, 칸이 늘어남
    next = next.map(it => (it.type === 'memo' && it.rect && Math.abs(memoHeight(it) - it.rect[3]) > 0.5 ? applyRect(it, [it.rect[0], it.rect[1], it.rect[2], memoHeight(it)]) : it))   // 메모 높이 = 줄에 맞춤
    next = syncLegends(next).map(it => { if (it.type !== 'legend') return it; const lo = legendLayout(it); return it.rect && Math.abs(lo.w - it.rect[2]) < 0.5 && Math.abs(lo.h - it.rect[3]) < 0.5 ? it : { ...it, rect: [it.rect?.[0] || 0, it.rect?.[1] || 0, lo.w, lo.h] } })   // 범례 = 줄은 도면에서 저절로, 크기는 줄에 맞춤(2026-10-19 사용자: 부하 없으면 자동)
    next = next.map(it => (it.fit_text && it.label?.align === 'left' && it.rect && Math.abs(fitTextHeight(it) - it.rect[3]) > 0.5 ? applyRect(it, [it.rect[0], it.rect[1], it.rect[2], fitTextHeight(it)]) : it))   // 글에 맞춘 상자(AI 카드·메모)
    const fixed = followArrows(keepBinds(prev, next), rectOf)
    // 되돌리기 칸 = 바뀐 도형만(2026-10-18 공동작업 — 통째로 되돌리면 그사이 남이 고친 것까지 지워짐, `sync.itemDelta`)
    const delta = itemDelta(prev, fixed)
    if (merge && h.mergeKey === merge && now - h.mergeT < 1500 && h.past.length) mergeDelta(h.past[h.past.length - 1], delta)
    else if (delta.before.size) { h.past.push({ ...delta, sel: R.current.sel }); h.future = [] }
    h.mergeKey = merge; h.mergeT = now
    if (hist.current.past.length > 200) hist.current.past.shift()
    R.current.model = { ...R.current.model, items: fixed }   // 다시 그리기 전에 또 고쳐도(표 칸 Tab 연타) 앞 고침 위에서
    setModel(m => ({ ...m, items: fixed })); setLive(null)
    if (nextSel) setSel(nextSel.filter(id => fixed.some(it => it._id === id)))
    onCommit?.(label)
  }, [setModel, onCommit])
  const undo = () => { const h = hist.current, p = h.past.pop(); h.mergeKey = null; if (!p) return; h.future.push(p); const items = applyDelta(R.current.model.items, p.before); R.current.model = { ...R.current.model, items }; setModel(m => ({ ...m, items })); setSel(p.sel.filter(id => items.some(it => it._id === id))); onCommit?.('되돌림') }
  const redo = () => { const h = hist.current, f = h.future.pop(); h.mergeKey = null; if (!f) return; h.past.push(f); const items = applyDelta(R.current.model.items, f.after); R.current.model = { ...R.current.model, items }; setModel(m => ({ ...m, items })); onCommit?.('다시 실행') }

  // busy = 끄는 중·고치는 중·다각형 찍는 중(공동작업: 그동안 남의 변경 받기를 미룸)
  useImperativeHandle(ref, () => ({ undo, redo, startToolDrag, busy: () => !!(st.current.kind || R.current.editing || R.current.live || R.current.poly), getSel: () => R.current.sel, editingId: () => R.current.editing?.id || '', syncBusy: () => !!(st.current.kind || R.current.poly || (R.current.live && !R.current.editing)), setSel, insertTable, insertLegend, insertWeb, insertMemo, moveSelToLayer, exportDoc, exportPages, startPresent, reorderFrames, renameFrame, goFrame, frameIds: () => orderedFrames(R.current.model.items).map(f => f._id), selFrames: () => { const ids = new Set(R.current.sel); return R.current.model.items.filter(it => ids.has(it._id) && (it.type === 'titleblock' || it.type === 'frame')).length }, selTexts, selImages, meetStart, meetStop, meetDiscard, showIds, pinCard, showCard, showItem, dropFiles, dropUrl, pinImage, dragImage, pinSvg, dragSvg, pinChart, deepBoard, deepPending, deepSectionPending, pendHide, deepRedo, deepTarget, deepRedoSection, deepFlip, deepFlipState, dragChart: (t, onPlaced) => startPaletteDrag('chart', chartItems(t), onPlaced), dragCard: (msg, onPlaced) => startPaletteDrag('card', cardItems(msg, 0, 0, topZ(R.current.model.items) + 1), onPlaced), reset: () => { hist.current = { past: [], future: [] }; setSel([]) }, startPaletteDrag,
    // 시험용(Playwright 자체확인) — 손잡이·상태 들여다보기
    debugHandle: p => ({ single: single?._id, hs: handlesOf(single).map(h => [h.key, h.p]), at: handleAt(p)?.key }), debugState: () => ({ kind: st.current.kind, handle: st.current.handle, live: !!live, editing: R.current.editing, stylePv: R.current.stylePv }) }))

  // 속성 카드에서 색·선을 바꾼 뒤 = 선택선·꼭짓점 사각을 숨김(데스크톱 `_style_preview_active` — 파란 선이 바꾼 선 색을 덮음, 멀리서 볼수록).
  // 칠판을 누르거나 글쇠를 누르거나 고른 것이 바뀌면 다시 보임 — 마우스를 칠판으로 옮기기만 해서는 그대로(바꾼 색을 보러 가는 길, 2026-10-23 사용자). 큐닷·회전 점은 그대로
  const [stylePv, setStylePv] = useState(false); R.current.stylePv = stylePv
  useEffect(() => { if (!stylePv) return; const k = e => { if (!e.target.closest?.('input, textarea, [contenteditable], [data-ppop], [data-keep-edit]')) setStylePv(false) }   // 카드·색 창 안에서 치는 것은 빼고
    window.addEventListener('keydown', k, true); return () => window.removeEventListener('keydown', k, true) }, [stylePv])
  useEffect(() => { setStylePv(false) }, [sel.join()])   // eslint-disable-line react-hooks/exhaustive-deps — 고친 뒤 같은 것을 다시 고른 상태(새 배열)는 그대로
  useEffect(() => { onSel?.(sel) }, [sel])   // eslint-disable-line react-hooks/exhaustive-deps — 대화창 칩(고른 것 N개)
  const keepPoly = useRef(false)   // 위 막대에서 다각형을 끌어 놓은 직후 = 첫 선분을 이어 그리는 중(도구가 바뀌어도 버리지 않음)
  useEffect(() => { if (keepPoly.current) { keepPoly.current = false; return } setOverlay(o => (o.poly || o.lpt ? { ...o, poly: null, lpt: null, pcur: null } : o)) }, [tool])   // 도구를 바꾸면 그리다 만 다각형·선은 버림(다음에 이어 붙지 않게)
  const byId = useMemo(() => new Map(items.map(it => [it._id, it])), [items])
  const selItems = sel.map(id => byId.get(id)).filter(Boolean)
  const single = selItems.length === 1 ? selItems[0] : null

  // ── 손잡이(단일 선택) — [{ key, p(칠판), cursor }] ──
  function handlesOf(it) {
    if (!it || it.locked || it.type === 'legend') return []   // 범례 = 크기는 줄에 맞춤(속성 카드 「크기」), 옮기기만
    const z = R.current.cam.z, out = []
    if (it.type === 'titleblock') {   // 종이틀·도면틀 — 꼭짓점 넷, 끌면 비율 그대로 배율만(2026-10-18 사용자: 하마로 바로 키우고 줄이기)
      const [W, H] = paperWH(it.size, it.orient)
      for (const [k, px, py, c] of [['tl', 0, 0, 'nwse-resize'], ['tr', W, 0, 'nesw-resize'], ['br', W, H, 'nwse-resize'], ['bl', 0, H, 'nesw-resize']]) out.push({ key: k, p: toScene(it, { x: px, y: py }), cursor: c })
      return out
    }
    if (BOXY.has(it.type)) {
      const [x, y, w, h] = localRect(it), s = it.scale || 1
      for (const [k, px, py, c] of [['tl', x, y, 'nwse-resize'], ['tr', x + w, y, 'nesw-resize'], ['br', x + w, y + h, 'nwse-resize'], ['bl', x, y + h, 'nesw-resize']]) out.push({ key: k, p: toScene(it, { x: px, y: py }), cursor: c })
      const g = (HANDLE * 1.6) / z / s
      if (it.type !== 'frame' && it.type !== 'web' && it.type !== 'doc' && it.type !== 'pdf') out.push({ key: 'rot', p: toScene(it, { x: x - g, y: y - g }), cursor: 'grab', round: true })   // 좌상단 대각(데스크톱 `_box_rot_center`) — 프레임은 안 돌림
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
  // 고른 표의 안쪽 경계선(행·열 공통선 — 엑셀처럼 그 선만 끌기, 2026-10-18 사용자). 바깥 테두리는 표 크기(edgeAt)
  function tableLineAt(it, p) {
    if (!it || it.type !== 'table' || it.locked || chartMode(it)) return null
    const q = toLocal(it, p), [x, y, w, h] = it.rect, t = EDGE_PX / R.current.cam.z / (it.scale || 1)
    if (q.x < x || q.x > x + w || q.y < y || q.y > y + h) return null
    const ce = colEdges(x, w, colFracs(it)); for (let i = 1; i < it.cols; i++) if (Math.abs(q.x - ce[i]) <= t) return { axis: 'c', i }
    const re = rowEdges(y, h, it); for (let i = 1; i < it.rows; i++) if (Math.abs(q.y - re[i]) <= t) return { axis: 'r', i }
    return null
  }
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
  const [loose, setLoose] = useState(null); R.current.loose = loose   // 자물쇠를 잠깐 푼 프레임(틀만 옮김 — 고른 게 풀리면 다시 같이, 2026-10-18 사용자: 「자물쇠 개념」)
  // 고른 것 + 틀(프레임·보드) 안의 것 — 복사·내보내기·정리 문서 재료처럼 안 바꾸는 일은 이것(잠긴 것도 포함)
  const withContents = ids => { const its = R.current.model.items, lz = R.current.loose
    return [...new Set([...ids, ...boardContents(lz ? its.map(it => (it._id === lz ? { ...it, magnet: false } : it)) : its, ids, textBox)])] }
  const movingSet = ids => { const lk = new Set(R.current.model.items.filter(it => it.locked).map(it => it._id)); return withContents(ids).filter(id => !lk.has(id)) }   // 옮기기·지우기 = 잠긴 것 빼고(2026-10-25 — 골라도 안 바뀜)
  // 잠긴 도형 찾기 — 안 잠긴 것이 하나도 안 걸렸을 때만(잠긴 바탕 위에 그린 것이 늘 먼저). 잠긴 레이어의 것은 빼고(레이어 카드에서 품)
  const lockedAt = p => topHit(hitPool().filter(it => it.locked && !layerLocked(it)).map(it => ({ ...it, locked: false })), p, HIT_PX / R.current.cam.z, textBox)

  // ── 포인터 ──
  function onPointerDown(e) {
    if (readOnly) { svg.current.setPointerCapture(e.pointerId); st.current = { ...st.current, kind: 'pan', right: false, sx: e.clientX, sy: e.clientY, cam: R.current.cam }; setCursor('grabbing'); return }   // 보기 전용 = 끌면 화면 이동
    if (R.current.editing && e.button === 0) return   // 고치는 중에도 휠·오른쪽 끌기 = 화면 이동(입력은 그대로 — 2026-10-18 사용자)
    if (R.current.webOn && !(e.button === 2 && pdfBodyAt(toSceneP(e))?._id === R.current.webOn)) setWebOn(null)   // 웹 카드 조작 중 바깥을 누름 = 끝(칸 안 누르기는 페이지가 받아 여기 안 옴). 넘겨 보는 PDF 안 우클릭 = 안쪽 메뉴(끝내지 않음)
    const p = toSceneP(e), m = R.current.model, z = R.current.cam.z
    svg.current.setPointerCapture(e.pointerId)
    // 가운데·오른쪽 끌기 = 화면 이동(데스크톱 우클릭 끌기 = 팬, 제자리 우클릭 메뉴는 나중)
    setMenu(null)
    if (e.button === 1 || e.button === 2 || (e.button === 0 && st.current.space)) { st.current = { ...st.current, kind: 'pan', right: e.button === 2, sx: e.clientX, sy: e.clientY, cam: R.current.cam }; setCursor('grabbing'); return }
    if (e.button !== 0) return
    setHp(null)
    const t = R.current.tool
    if (t !== 'select') return startDraw(t, p, e)
    if (!single && R.current.sel.length > 1) {   // 여러 개 고른 바깥 상자 꼭짓점 = 모두 같은 비율로(2026-10-18 사용자: FM 방식 — 종이틀 안 내용 맞추기)
      const mb = multiBoxNow(), cs = mb && [[mb.x, mb.y], [mb.x + mb.w, mb.y], [mb.x + mb.w, mb.y + mb.h], [mb.x, mb.y + mb.h]]
      const i = cs ? cs.findIndex(([cx, cy]) => Math.hypot(cx - p.x, cy - p.y) * z <= HANDLE * 0.75) : -1
      if (i >= 0) { const [ax, ay] = cs[(i + 2) % 4]; st.current = { ...st.current, kind: 'mscale', A: { x: ax, y: ay }, box: mb, start: p, orig: m.items, ids: new Set(movingSet(R.current.sel)) }; return }
    }
    const lk = frameLockAt(p); if (lk) { setLoose(l => (l === lk._id ? null : lk._id)); return }   // 이름표 옆 자물쇠 — 잠깐 틀만
    const wo = webOpenAt(p); if (wo) { if (wo.type === 'doc') openDoc(wo); else window.open(wo.url, '_blank', 'noopener'); return }   // PDF ↗ = 원본(브라우저 PDF 보기)   // 웹 카드 오른쪽 위 ↗ = 새 탭, 정리 문서 ↗ = 크게 보기
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) { const u = memoLinkHit(p); if (u) { window.open(u, '_blank', 'noopener'); return } }   // 메모 속 주소 Ctrl+클릭 = 새 탭(그냥 클릭은 고르기·고치기 — 2026-10-18 사용자 선택)
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) { const h = topHit(hitPool(), p, HIT_PX / z, textBox), src = h && clipSourceOf([h._id]); if (src) { goClipSource(src); return } }   // PDF에서 오려 온 그림·밑 글 Ctrl+클릭 = 그 쪽(2026-10-22)
    // 줄을 고른 채 Shift·Ctrl+클릭은 손잡이가 아니라 줄 글자 위여도 같음(2026-10-18 사용자: 글자 위를 눌러 고른 것이 다 풀렸음 — 노션은 블록 아무 데나)
    const mh = memoHandleHit(p) || ((e.shiftKey || e.ctrlKey || e.metaKey) && lineSel ? (hv => (hv && hv.it._id === lineSel.id ? hv : null))(memoRowAt(p, 0)) : null)
    // ⠿ — 연속 = Shift·Ctrl+Shift 클릭, 개별 = Ctrl·Alt+Shift 클릭(노션 + 흔한 방식 둘 다 — 2026-10-18 사용자), 고른 줄 안을 끌면 고른 줄 전부, Alt 끌기 = 복사
    if (mh) { setSel([mh.it._id]); const ls = lineSel?.id === mh.it._id ? lineSel : null, mod = e.ctrlKey || e.metaKey
      const toggle = (mod && !e.shiftKey) || (e.altKey && e.shiftKey), range = e.shiftKey && !e.altKey
      if (toggle) { if (!ls) { setLineSel({ id: mh.it._id, s: mh.s, e: mh.e }); return }
        const us = selUnits(ls), has = us.findIndex(([s0, e0]) => mh.s >= s0 && mh.e <= e0)
        if (has < 0) { setLineSel({ id: ls.id, s: mh.s, e: mh.e, more: us }); return }
        const left = us.filter((_, j) => j !== has); if (!left.length) { setLineSel(null); return }
        const [a0, ...rest] = left.slice().reverse(); setLineSel({ id: ls.id, s: a0[0], e: a0[1], more: rest }); return }
      if (range) { if (ls) { const s1 = Math.min(ls.s, mh.s), e1 = Math.max(ls.e, mh.e), more = (ls.more || []).filter(([a, b]) => b <= s1 || a >= e1); setLineSel({ id: ls.id, s: s1, e: e1, ...(more.length ? { more } : {}) }) } else setLineSel({ id: mh.it._id, s: mh.s, e: mh.e }); return }
      const inSel = ls && selUnits(ls).some(([s0, e0]) => mh.s >= s0 && mh.e <= e0)
      st.current = { ...st.current, kind: 'mline', id: mh.it._id, units: inSel ? selUnits(ls) : [[mh.s, mh.e]], copy: e.altKey, start: p, moved: false }; return }
    if (lineSel) setLineSel(null)
    const mo = memoMoreAt(p); if (mo) { commit(m.items.map(x => (x._id === mo.it._id ? { ...x, fold: mo.more !== 'open' } : x)), [mo.it._id], mo.more === 'open' ? '메모 펼침' : '메모 접음'); return }
    const mc = memoCheckAt(p); if (mc) { const ln = mc.it.lines[mc.i]; commit(m.items.map(x => (x._id === mc.it._id ? { ...x, lines: x.lines.map((l, j) => (j === mc.i ? (l.done ? (({ done, ...r }) => r)(l) : { ...l, done: true }) : l)) } : x)), R.current.sel, ln.done ? '할 일 풂' : '할 일 끝'); return }
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
    const tln = tableLineAt(single, p)
    if (tln) { st.current = { ...st.current, kind: 'tline', id: single._id, ...tln, orig: m.items }; return }
    const edge = edgeAt(single, p)
    if (edge) { st.current = { ...st.current, kind: 'resize', handle: edge, id: single._id, start: p, orig: m.items }; return }
    const add = e.shiftKey || e.ctrlKey || e.metaKey   // 더해 고르기 — Ctrl(데스크톱 손버릇)·Shift(웹 관례) 둘 다
    // 미선택 도형의 포트점·테두리(14px)를 누르면 화살표 잇기 대기 — 끌면 화살표, 그냥 놓으면 그 도형 선택(데스크톱 `_hover_port_at`→`_hp_*`)
    // 프레임 이름표는 근처 도형의 포트점보다 먼저(이름표 옆 상자에서 화살표가 뽑혀 프레임이 안 끌렸음 — 2026-10-18 시험)
    const tagHit = hitPool().find(it => it.type === 'frame' && !it.locked && (b => p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h)(frameTagBox(it)))
    if (tagHit) { if (add && R.current.sel.includes(tagHit._id)) { setSel(R.current.sel.filter(i => i !== tagHit._id)); return }   // 고른 프레임 이름표를 Shift·Ctrl+클릭 = 빼기(2026-10-18 사용자: 더하기만 됐음)
      const ids = add ? [...new Set([...R.current.sel, tagHit._id])] : R.current.sel.includes(tagHit._id) ? R.current.sel : [tagHit._id]; setSel(ids)
      st.current = { ...st.current, kind: 'move', start: p, orig: m.items, ids: e.altKey ? ids : movingSet(ids), sel: ids, moved: false }; return }
    if (!add && !e.altKey && !inMemoGutter(p)) { const hp = hoverPort(p); if (hp?.target) { st.current = { ...st.current, kind: 'conn', src: hp.target.id, port: { p: hp.target.p, n: hp.target.n }, start: p, cur: p, fromQc: false, moved: false }; return } }
    const hit = topHit(hitPool(), p, HIT_PX / z, textBox) || groupAt(p)
    // 이미 고른 표를 한 번 더 누르면 그 칸을 고름(놓을 때 — 끌면 표 이동), Shift = 범위로 늘림(2026-10-18 사용자: 어느 칸을 눌렀는지 알 수 없음)
    if (hit?.type === 'table' && !chartMode(hit) && R.current.sel.length === 1 && R.current.sel[0] === hit._id) {
      const cell = cellAt(hit, toLocal(hit, p))
      if (cell) { st.current = { ...st.current, kind: 'move', start: p, orig: m.items, ids: movingSet([hit._id]), sel: [hit._id], moved: false, cellPick: { id: hit._id, ...cell, extend: e.shiftKey } }; return }
    }
    if (hit) {
      let ids = R.current.sel
      if (add) ids = ids.includes(hit._id) ? ids.filter(i => i !== hit._id && !(hit.group_id && m.items.find(x => x._id === i)?.group_id === hit.group_id)) : expandGroups(m.items, [...ids, hit._id])
      else if (!ids.includes(hit._id)) ids = expandGroups(m.items, [hit._id])
      setSel(ids)
      const body = (hit.type === 'pdf' || (hit.type === 'web' && hit.frameable) || liveFits(hit)) && !add && !e.altKey && toLocal(hit, p).y > hit.rect[1] + WEB_HEAD ? hit : null
      const webPick = body?.type === 'web' ? body : null, pdfTap = body?.type === 'pdf' || body?.type === 'doc' ? body : null   // 움직이는 카드도 PDF처럼(§8 항목66 4단계)   // 웹 카드 몸통 제자리 클릭 = 칸 안 조작 켜기(놓을 때 — 끌면 이동). PDF는 한 번 = 고르기만, 두 번 = 넘겨 보기(2026-10-21 사용자 — 옮기기·지우기·휠 확대가 잦은 자료)
      if (ids.includes(hit._id)) st.current = { ...st.current, kind: 'move', start: p, orig: m.items, ids: e.altKey && hit.type === 'frame' ? ids : movingSet(ids), sel: ids, moved: false, webPick, pdfTap }   // Alt+끌기 = 프레임 틀만
      return
    }
    const lockTap = lockedAt(p)   // 잠긴 도형(2026-10-25 사용자): 제자리 누르기 = 고르기(놓을 때), 끌기 = 그 위에서도 끌어 고르기(바탕 위 작업 그대로)
    if (lockTap && add) { const m2 = R.current.model, ids = R.current.sel
      setSel(ids.includes(lockTap._id) ? ids.filter(i => i !== lockTap._id && !(lockTap.group_id && m2.items.find(x => x._id === i)?.group_id === lockTap.group_id)) : expandGroups(m2.items, [...ids, lockTap._id])); return }
    if (!add) setSel([])
    // 끌어 고르기 — Ctrl = 더하기, Shift = 빼기(2026-10-18 사용자 선택 — 클릭은 둘 다 뒤집기 그대로). 방향 규칙(왼→오 다 들어간 것, 오→왼 걸친 것)은 빼기에도 같음
    const sub = e.shiftKey && !(e.ctrlKey || e.metaKey)
    st.current = { ...st.current, kind: 'rubber', start: p, add: add && !sub ? R.current.sel : [], sub, base: R.current.sel, lockTap: lockTap?._id }
  }

  function onPointerMove(e) {
    const s = st.current, p = toSceneP(e), z = R.current.cam.z
    R.current.mouse = p   // 주소 붙여넣기 = 커서 자리에
    if (!s.kind) { hoverCursor(p); if ((R.current.poly && R.current.tool === 'polygon') || (R.current.lpt && R.current.tool === 'line')) setOverlay(o => { const last = o.lpt || o.poly?.at(-1); return { ...o, pcur: polyCloseAt(o.poly, p) ? o.poly[0] : e.shiftKey && last ? snap45(last, p) : p } }); return }   // Shift = 45° — 다각형은 마지막 점 기준(2026-10-20 사용자: 다각형만 안 먹었음)   // 클릭 배치 중 = 마지막 점에서 커서까지 따라오는 선(데스크톱 `_draw_pts[-1]`)
    if (s.kind === 'pan') { setCam({ ...s.cam, x: s.cam.x + e.clientX - s.sx, y: s.cam.y + e.clientY - s.sy }); return }
    if (s.kind === 'mline') { if (!s.moved && Math.hypot(p.x - s.start.x, p.y - s.start.y) * z < 4) return; s.moved = true; setCursor('grabbing'); setOverlay(o => ({ ...o, mdrop: { ...memoDropAt(p), from: s.id } })); return }
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
      const sel0 = new Set(R.current.sel), hitIds = Math.hypot(p.x - s.start.x, p.y - s.start.y) * z > 3 ? expandGroups(R.current.model.items, rubberSelect(hitPool(), s.start, p, textBox)).filter(id => (s.sub ? sel0.has(id) : !sel0.has(id))) : []
      setOverlay(o => ({ ...o, rubber: { a: s.start, b: p, hits: hitIds, sub: s.sub } })); return
    }
    if (s.kind === 'conn') {
      if (!s.moved && Math.hypot(p.x - s.start.x, p.y - s.start.y) * z <= CONN_DRAG_PX) return
      s.moved = true
      let cur = p; const n = s.port.n, o = s.port.p   // 출구 축에 10px 안이면 곧게(데스크톱) — 빈 곳에서 시작한 화살표는 출구가 없음
      if (!n) { /* 자유 시작 */ } else if (Math.abs(n.x) >= Math.abs(n.y)) { if (Math.abs(cur.y - o.y) * z <= CONN_STRAIGHT_PX) cur = { x: cur.x, y: o.y } }
      else if (Math.abs(cur.x - o.x) * z <= CONN_STRAIGHT_PX) cur = { x: o.x, y: cur.y }
      s.cur = cur
      const [src, port] = arrowStart(s), tgt = connTarget(src, port, cur)
      setOverlay(o2 => ({ ...o2, conn: connRoute(src, port, tgt, cur), hp: tgt ? { id: tgt.id, target: tgt } : null }))
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
      if (s.kind === 'resize' && it.type === 'titleblock') {   // 맞은편 꼭짓점 고정, 배율만
        const [W, H] = paperWH(it.size, it.orient), A = { tl: [W, H], tr: [0, H], br: [0, 0], bl: [W, 0] }[s.handle], SA = toScene(it, { x: A[0], y: A[1] })
        const k = Math.max(0.05, Math.max(Math.abs(p.x - SA.x) / W, Math.abs(p.y - SA.y) / H))
        next = { ...it, scale: +k.toFixed(4), pos: [SA.x - A[0] * k, SA.y - A[1] * k] }
      } else if (s.kind === 'resize') {
        next = applyRect(it, resizeRect(localRect(it), s.handle, toLocal(it, p), { keepRatio: it.type === 'image' || (it.type === 'frame' && !!it.ratio) || e.shiftKey }))
        if (next.type === 'table' && !isChart(next) && (next.font || next.cell_styles)) {   // 끄는 동안에도 확정과 같게 — 글보다 작아지지 않음(2026-10-18 사용자: 놓기 전엔 글이 넘침). 왼쪽·위 손잡이면 맞은편 변 고정
          const [x0, y0, w0, h0] = next.rect, f = fitTable(next), [, , w1, h1] = f.rect
          next = f === next ? next : { ...f, rect: [/l/.test(s.handle) ? x0 + w0 - w1 : x0, /t/.test(s.handle) ? y0 + h0 - h1 : y0, w1, h1] }
        }
      }
      else if (s.kind === 'rotate') { const [x, y, w, h] = localRect(it), c = toScene(it, { x: x + w / 2, y: y + h / 2 }), a0 = Math.atan2(s.start.y - c.y, s.start.x - c.x), a1 = Math.atan2(p.y - c.y, p.x - c.x)
        next = rotateTo(it, (it.rotation || 0) + ((a1 - a0) * 180) / Math.PI, e.shiftKey) }
      else if (s.kind === 'tscale') { const b = textBox(it), q = toLocal(it, p), k = Math.max(0.2, Math.max(q.x / b.w, q.y / b.h)); next = { ...it, font: Math.max(4, Math.round((it.font || 12) * k)) } }
      else { const q = toLocal(it, p), L = [...it.line]; if (s.handle === 'e0') { L[0] = q.x; L[1] = q.y } else { L[2] = q.x; L[3] = q.y }; next = { ...it, line: L } }
      setLive(followArrows(keepBinds(s.orig, s.orig.map(x => (x._id === s.id ? next : x))), rectOf))
      return
    }
    if (s.kind === 'tline') {   // 공통선 하나만 — 양옆 칸이 나눠 가짐(표 전체 크기 그대로, 데스크톱 열 경계 끌기와 같음)
      const it = s.orig.find(x => x._id === s.id), q = toLocal(it, p), [x, y, w, h] = it.rect, i = s.i
      let next
      const { minW, minH } = tableMins(it), lim = (e, mins, v) => { const lo = e[i - 1] + mins[i - 1], hi = e[i + 1] - mins[i]; return lo > hi ? e[i] : Math.max(lo, Math.min(hi, v)) }   // 옆 칸 글이 들어갈 만큼에서 멈춤(표가 커지지 않게)
      if (s.axis === 'c') { const e = colEdges(x, w, colFracs(it)); e[i] = lim(e, minW, q.x); next = { ...it, col_widths: e.slice(1).map((v, j) => (v - e[j]) / w) } }
      else { const e = rowEdges(y, h, it); e[i] = lim(e, minH, q.y); next = { ...it, row_heights: e.slice(1).map((v, j) => (v - e[j]) / h) } }
      setLive(followArrows(s.orig.map(x => (x._id === s.id ? next : x)), rectOf))
      return
    }
    if (s.kind === 'mscale') {
      const { A, box } = s, f = Math.max(0.05, Math.max(Math.abs(p.x - A.x) / (box.w || 1), Math.abs(p.y - A.y) / (box.h || 1)))
      setLive(followArrows(s.orig.map(it => { if (!s.ids.has(it._id)) return it
        const [px, py] = it.pos || [0, 0], [ox, oy] = it.origin || [0, 0]   // origin을 가운데로 둔 회전 도형도 제자리(origin만큼 보정)
        return bakeSarrow({ ...it, scale: +((it.scale || 1) * f).toFixed(5), pos: [A.x + (px - A.x) * f + ox * (f - 1), A.y + (py - A.y) * f + oy * (f - 1)] }) }), rectOf))   // 직각 화살표는 배율을 점에 녹임
      return
    }
    if (s.kind === 'draw') { s.cur = p; s.shift = e.shiftKey; setOverlay(o => ({ ...o, draw: { tool: s.tool, a: s.start, b: p, shift: e.shiftKey, pts: s.pts } })); if (s.tool === 'pen') { const last = s.pts[s.pts.length - 1]; if (Math.hypot(p.x - last.x, p.y - last.y) * z >= 2) s.pts.push(p) } return }
  }

  function onPointerUp(e) {
    const s = st.current, p = toSceneP(e)
    st.current = { space: s.space }
    setCursor('default')
    if (s.kind === 'pan' && R.current.editing) return   // 고치는 중 이동 = 메뉴·도구 끝 없이
    if (s.kind === 'pan' && s.right && Math.hypot(e.clientX - s.sx, e.clientY - s.sy) < 4 && R.current.tool !== 'select') {   // 그리는 도구 중 = 도구 끝(번호 연달아 찍다가 우클릭 — 2026-10-18 사용자)
      setOverlay(o => ({ ...o, poly: null, draw: null, lpt: null, pcur: null })); setTool('select'); return }
    if (s.kind === 'pan' && s.right && Math.hypot(e.clientX - s.sx, e.clientY - s.sy) < 4) {   // 제자리 우클릭 = 메뉴(고른 것 그대로 — 데스크톱과 같음)
      const r = svg.current.getBoundingClientRect(), one = R.current.sel.length === 1 && R.current.model.items.find(x => x._id === R.current.sel[0])
      const cell = one?.type === 'table' ? (cellAt(one, toLocal(one, p)) || (cellSel?.id === one._id ? { r: cellSel.r1, c: cellSel.c1 } : null)) : null   // 고른 표의 칸 위에서 우클릭 = 그 칸 기준 행·열 메뉴
      // 누른 자리마다 다른 메뉴(2026-10-21 사용자): 넘겨 보는 PDF 안 = 내용 메뉴만 · 도형 = 그 도형(안 고른 것이면 그것을 고름) · 빈 곳 = 칠판 메뉴(고른 것 풂)
      const pc = pdfBodyAt(p)
      if (pc && pc._id === R.current.webOn) { setMenu({ x: e.clientX - r.left, y: e.clientY - r.top, pdfIn: { id: pc._id, page: pdfPageAt(pc, toLocal(pc, p).y - pc.rect[1] - WEB_HEAD) } }); return }
      const hit = !cell && (topHit(hitPool(), p, HIT_PX / R.current.cam.z, textBox) || groupAt(p) || lockedAt(p))   // 잠긴 도형도 그것을 고르고 같은 메뉴(「잠금 해제」가 맨 위)
      if (hit && !R.current.sel.includes(hit._id)) setSel(expandGroups(R.current.model.items, [hit._id]))
      else if (!hit && !cell) setSel([])
      setMenu({ x: e.clientX - r.left, y: e.clientY - r.top, cell }); return }
    if (s.kind === 'mline') { setOverlay(o => ({ ...o, mdrop: null }))
      if (!s.moved) { const r = svg.current.getBoundingClientRect(), [a0, ...rest] = s.units.slice().reverse()   // 제자리 = 그 줄 고르기(고른 줄 안이면 그대로) + 메뉴
        setLineSel({ id: s.id, s: a0[0], e: a0[1], ...(rest.length ? { more: rest } : {}) }); setLineMenu({ x: e.clientX - r.left + 6, y: e.clientY - r.top - 6, id: s.id, units: s.units }); return }
      setLineSel(null); memoLineDrop(s, p); return }
    if (s.kind === 'conn') {
      setOverlay(o => ({ ...o, conn: null, hp: null }))
      if (!s.moved) { if (s.tool === 'arrow') return; if (s.fromQc) qcCreate(s.src, s.side); else setSel(expandGroups(R.current.model.items, [s.src])); return }
      const [src, port] = arrowStart(s)
      newArrow(src, port, connTarget(src, port, s.cur), s.cur)
      if (s.tool === 'arrow') setTool('select')
      return
    }
    if (s.kind === 'aend') { setOverlay(o => ({ ...o, hp: null })); if (live) commit(live, [s.id], '화살표 끝 옮김'); return }
    if (s.kind === 'bend') { if (live) commit(live, [s.id], '곡선 휨'); return }
    if (s.kind === 'label') { if (s.moved && live) commit(live, [s.id], '라벨 옮김'); else setLive(null); return }
    if (s.kind === 'seg') { if (s.moved && live) commit(live.map(x => (x._id === s.id ? { ...x, pts: endSegment(x.pts) } : x)), [s.id], '구간 옮김'); else setLive(null); return }
    if (s.kind === 'mscale') { if (live) commit(live, R.current.sel, '크기'); return }
    if (s.kind === 'tline') { if (live) commit(live, [s.id], s.axis === 'c' ? '열 너비' : '행 높이'); return }
    if (s.kind === 'move') {
      setOverlay(o => ({ ...o, guides: null }))
      if (!s.moved && s.cellPick) { const { id, r, c, extend } = s.cellPick; setCellSel(cs => (extend && cs?.id === id ? { ...cs, r1: r, c1: c } : { id, r0: r, c0: c, r1: r, c1: c })) }
      if (!s.moved && s.webPick) webActivate(s.webPick)
      else if (!s.moved && s.pdfTap && R.current.webOn !== s.pdfTap._id) setStatus(s.pdfTap.type === 'doc' ? '인터랙티브 HTML — 두 번 누르면 움직여 보기' : 'PDF — 두 번 누르면 넘겨 보기(휠로 쪽 넘김)')
      if (s.moved && live) commit(live.filter(it => it), s.sel, '옮김'); else setLive(null); return }
    if (s.kind === 'rubber') {
      setOverlay(o => ({ ...o, rubber: null }))
      if (Math.hypot(p.x - s.start.x, p.y - s.start.y) * R.current.cam.z > 3) {
        const hits = expandGroups(R.current.model.items, rubberSelect(hitPool(), s.start, p, textBox))
        if (s.sub) { const out = new Set(hits); setSel(s.base.filter(id => !out.has(id))) } else setSel(expandGroups(R.current.model.items, [...new Set([...s.add, ...hits])])) }
      else if (s.lockTap) { setSel(expandGroups(R.current.model.items, [s.lockTap])); setStatus('잠긴 도형이에요 — 옮기기·지우기·고치기는 막혀 있어요(풀기 Ctrl+L)') }
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
      if (isHollow(host) && p.x > b.x + m && p.x < b.x + b.w - m && p.y > b.y + m && p.y < b.y + b.h - m) continue   // 프레임은 테두리 근처에서만
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
  // 도형 안에서 시작한 화살표의 시작(arrowStart) — 끝이 그 도형 밖으로 나가면 끝에 가장 가까운 변 가운데(포트)에 붙음, 아직 안이면 떠 있는 시작 그대로
  function arrowStart(s) {
    const host = s.inside && R.current.model.items.find(x => x._id === s.inside)
    if (!host) return [s.src, s.port]
    const [l, t, w, h] = rectOf(host), q = toLocal(host, s.cur)
    if (q.x >= l && q.x <= l + w && q.y >= t && q.y <= t + h) return [s.src, s.port]
    let best = null, bd = Infinity
    for (const pt of hostPorts(host, rectOf)) { const d = Math.hypot(pt.p.x - s.cur.x, pt.p.y - s.cur.y); if (d < bd) { bd = d; best = pt } }
    return best ? [host._id, { p: best.p, n: best.n }] : [s.src, s.port]
  }
  function connTarget(srcId, port, cur) {
    const near = hostsNear(cur), lines = linesNear(cur), z = R.current.cam.z
    let t = dropTarget(near, cur, z, rectOf, srcId, lines)
    // 도형 '안'에 놓음(테두리 스냅 아님) = 화살표가 오는 쪽 변(시작에 가장 가까운 포트) — 가운데에 놓으면 위·아래 변이 더 가까워 엉뚱한 쪽으로 돌아 들어갔음(2026-10-19 다잡기, 데스크톱은 놓은 자리에 가까운 포트)
    if (t?.id && !snapAt(near, cur, z, rectOf, lines)) {
      const host = R.current.model.items.find(x => x._id === t.id)
      let bd = Infinity
      for (const pt of host ? hostPorts(host, rectOf) : []) { const d = Math.hypot(pt.p.x - port.p.x, pt.p.y - port.p.y); if (d < bd) { bd = d; t = { id: host._id, p: pt.p, n: pt.n, port: true } } }
    }
    return t && (t.id !== srcId || Math.hypot(t.p.x - port.p.x, t.p.y - port.p.y) > 1) ? t : null
  }
  // 새 화살표 기본값 — 속성 카드에서 바꾼 값이 다음 화살표에 이어짐(데스크톱 sticky: 색·굵기·선 모양·화살촉·모서리). 굵기 1 = 데스크톱 `_DEFAULT_WIDTH`·웹 그리기 도구와 같게(2026-10-18 — 2였을 땐 같은 화살표인데 선택 띠가 얇아 보였다)
  const sticky = useRef({ color: INK, style: 1, width: 1, head: true, head_start: false, head_scale: 1, curve_r: 10 })
  const [liveEd, setLiveEd] = useState(null)   // 지금 글 편집기(TipTap) — 고치는 중 「글자」 카드가 씀
  const [cellSel, setCellSel] = useState(null)   // 고른 표 칸 범위 { id, r0, c0, r1, c1 }
  useEffect(() => { if (cellSel && (sel.length !== 1 || sel[0] !== cellSel.id || editing)) setCellSel(null) }, [sel, editing])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (loose && !sel.includes(loose)) setLoose(null) }, [sel])   // eslint-disable-line react-hooks/exhaustive-deps
  // 프레임 이름표 자리(칠판) — 이름표·자물쇠 누르기·바로 고치기 칸이 같이 씀
  const frameTagBox = it => { const [x, y] = it.rect, fs = frameTagFs(it), w = measure(frameTag({ ...it, no: pageNo.get(it._id) ?? it.no }), fs, 'app', 600) + fs
    return { x: (it.pos?.[0] || 0) + x, y: (it.pos?.[1] || 0) + y - fs * 1.7, w, h: fs * 1.45, fs } }
  const frameLockAt = p => { const it = single?.type === 'frame' && !single.locked ? single : null; if (!it) return null
    const b = frameTagBox(it), s = b.h; return p.x >= b.x + b.w + b.fs * 0.3 && p.x <= b.x + b.w + b.fs * 0.3 + s && p.y >= b.y && p.y <= b.y + s ? it : null }
  const [memoHov, setMemoHov] = useState(null); R.current.memoHov = memoHov   // 마우스를 올린 메모 줄 { id, s, e } — 왼쪽에 ⠿ 손잡이(2026-10-18 사용자: 노션처럼)
  const [lineMenu, setLineMenu] = useState(null)   // ⠿를 누르면 그 줄 메뉴 { x, y, id, s, e, kinds? }
  const [lineSel, setLineSel] = useState(null); R.current.lineSel = lineSel   // 고른 메모 줄 { id, s, e } — 노션처럼 ⠿ 누르기·Esc로 고르고 Ctrl+D·Del·Ctrl+/·↑↓(2026-10-18 사용자)
  const [webOn, setWebOn] = useState(null); R.current.webOn = webOn   // 칸 안을 조작 중인 웹 카드 _id(두 번 누르기 — 2026-10-18 사용자)
  const [tagEdit, setTagEdit] = useState(null)   // 이름표를 두 번 눌러 고치는 중인 프레임 _id
  const [present, setPresent] = useState(null)   // 발표 중이면 시작 장 번호
  // 판서(발표 중 그린 것) — 칠판 「판서」 레이어에 진짜 도형으로(나중에 레이어 카드에서 숨기기·지우기). 레이어가 없거나 숨겨져 있으면 보이게 만듦
  function addPenNotes(specs) {
    const ly = layersOf(R.current.model).find(l => l.id === PEN_LAYER)
    if (!ly || !ly.visible || ly.locked) setModel(m => ({ ...m, layers: ly ? layersOf(m).map(l => (l.id === PEN_LAYER ? { ...l, visible: true, locked: false } : l)) : [...layersOf(m), { id: PEN_LAYER, name: '판서', visible: true, locked: false, color: '#e0646a' }] }))
    const m = R.current.model, z = topZ(m.items) + 1, its = specs.map((s, j) => base(s.pos, { ...s, layer_id: PEN_LAYER, z: z + j }))
    commit([...m.items, ...its], R.current.sel, '판서')
  }
  function startPresent(fromId) {   // 발표 — 고른 프레임(또는 fromId)부터, 없으면 1번부터
    const fr = orderedFrames(hitPool()); if (!fr.length) { setStatus('프레임이 없어요 — 상단 「프레임」으로 보여 줄 영역을 감싸 보세요'); return }
    const id = fromId || R.current.sel.find(s => fr.some(f => f._id === s)); setEditing(null); setPresent(Math.max(0, fr.findIndex(f => f._id === id)))
  }
  const cellRange = cs => ({ r0: Math.min(cs.r0, cs.r1), r1: Math.max(cs.r0, cs.r1), c0: Math.min(cs.c0, cs.c1), c1: Math.max(cs.c0, cs.c1) })
  // 고른 칸들 꾸밈 고치기 — per(지금 꾸밈, r, c) → 고칠 값(undefined = 그 칸 지움)
  function setCells(per, label, merge) {
    const cs = cellSel; if (!cs) return
    const m = R.current.model, t = m.items.find(x => x._id === cs.id); if (!t) return
    const { r0, r1, c0, c1 } = cellRange(cs), styles = { ...(t.cell_styles || {}) }
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) {
      const k = `${r},${c}`, nv = { ...(styles[k] || {}), ...per(cellStyle(t, r, c), r, c) }
      for (const key of Object.keys(nv)) if (nv[key] === undefined) delete nv[key]
      if (Object.keys(nv).length) styles[k] = nv; else delete styles[k]
    }
    commit(m.items.map(x => (x._id === t._id ? { ...t, cell_styles: styles } : x)), [t._id], label, merge ? merge + t._id : null)
  }
  const [menu, setMenu] = useState(null); R.current.menuOpen = !!menu   // 제자리 우클릭 메뉴 자리(편집 화면 안 px)
  // 번호표 다음 번호 = 칠판에 남은 가장 큰 번호 + 1(2026-10-20 사용자: 3을 지우면 다시 3 — 중간 빈 번호는 안 채움, 데스크톱 `next_badge_number`도 같게)
  const nextBadge = items => Math.max(0, ...items.filter(it => it.type === 'badge').map(it => it.number || 0)) + 1
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
    if (readOnly) { setCursor('grab'); return }
    const t = R.current.tool
    if (t === 'select' && !R.current.editing) { const hv = memoRowAt(p), k = hv ? `${hv.it._id}:${hv.s}:${hv.e}` : null   // 메모 줄 위 = 왼쪽 ⠿
      if (k !== (R.current.memoHov ? `${R.current.memoHov.id}:${R.current.memoHov.s}:${R.current.memoHov.e}` : null)) setMemoHov(hv ? { id: hv.it._id, s: hv.s, e: hv.e } : null)
      if (hv && memoHandleHit(p)) { setHp(null); setCursor('grab'); return }
      if (hv && inMemoGutter(p)) { setHp(null); setCursor('default'); return }
      if (hv && (memoCheckAt(p) || memoMoreAt(p))) { setHp(null); setCursor('pointer'); return }
      if (hv && memoLinkHit(p)) { setHp(null); setCursor('pointer'); return } }   // 주소 위 = 손가락(Ctrl+클릭으로 열림 — 2026-10-18 사용자: 이동 커서였음)   // 할 일 상자 = 누르는 것(2026-10-18 사용자: 이동 커서였음)
    if (t === 'arrow') { const near = hostsNear(p), lines = linesNear(p), tg = snapAt(near, p, R.current.cam.z, rectOf, lines); setHp(near.length || tg ? { id: tg?.id ?? near.at(-1)?._id ?? null, target: tg } : null); setCursor('crosshair'); return }   // 붙을 자리 예고
    if (t !== 'select') { setCursor(t === 'text' ? 'text' : 'crosshair'); return }
    if (!single && R.current.sel.length > 1) { const mb = multiBoxNow(); if (mb) { const cs = [[mb.x, mb.y, 'nwse-resize'], [mb.x + mb.w, mb.y, 'nesw-resize'], [mb.x + mb.w, mb.y + mb.h, 'nwse-resize'], [mb.x, mb.y + mb.h, 'nesw-resize']]
      const c = cs.find(([cx, cy]) => Math.hypot(cx - p.x, cy - p.y) * R.current.cam.z <= HANDLE * 0.75); if (c) { setHp(null); setCursor(c[2]); return } } }
    const h = handleAt(p); setHoverKey(h?.key || null); if (h) { setHp(null); setSegPrev(null); setCursor(h.cursor); return }
    if (webOpenAt(p)) { setHp(null); setSegPrev(null); setCursor('pointer'); return }   // 카드 ↗ = 누르는 단추(2026-10-21 사용자: 이동 커서였음 — 포트점보다 먼저)
    const sg = segAt(p)
    if (sg) {   // 직각 화살표 구간 위 — 알약이 아니면 나눠 끌 자리에 속 빈 알약 미리보기(`_draw_segment_preview_pill`)
      const it = single, a = it.pts[sg.i], b = it.pts[sg.i + 1], horizontal = Math.abs(b[1] - a[1]) <= Math.abs(b[0] - a[0])
      setHp(null); setSegPrev(sg.pill ? null : { p: (q => toScene(it, { x: q[0], y: q[1] }))(subdividePreview(it.pts, sg.i, sg.proj)), horizontal })
      setCursor(horizontal ? 'ns-resize' : 'ew-resize'); return
    }
    setSegPrev(null)
    const tln = tableLineAt(single, p); if (tln) { setHp(null); setCursor(tln.axis === 'c' ? 'col-resize' : 'row-resize'); return }
    const hp = hoverPort(p); setHp(hp)
    if (hp?.target && (!inside(R.current.model.items.find(x => x._id === hp.target.id) || {}, p) || (hp.target.port && Math.hypot(hp.target.p.x - p.x, hp.target.p.y - p.y) * R.current.cam.z <= 5))) { setCursor('crosshair'); return }
    const ed = edgeAt(single, p); if (ed) { setCursor(edgeCursor[ed]); return }
    setCursor(topHit(hitPool(), p, HIT_PX / R.current.cam.z, textBox) ? 'move' : 'default')
  }

  // ── 도형 카드에서 끌어다 놓기(데스크톱 `_PaletteButton` 6px 넘게 끌기) — 진짜 도형이 손에 붙어 따라오고 정렬선도 걸림, 칠판 밖(카드 위 등)에 놓으면 취소 ──
  // 도형·심볼 카드 도구 — 'rect'·'ellipse'·'sym:<종류>'는 상자처럼 끌어 그리기, 'customsym:<id>'(내 심볼)는 원래 모양 그대로 놓기
  const boxDefault = shapeWH   // 기본 크기 = 도형 카드 아이콘과 같은 비율(symbols.js)
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
  // 바꾸기 — 옛것(도형 하나 또는 묶음 전체, oldIds)을 key로: 'customsym:<id>'(내 심볼) 또는 'rect'·'ellipse'·'sym:<종류>'(기본 도형 — 묶음에서 돌아갈 때, 2026-10-18 사용자 지적: 한 번 바꾸면 못 돌아옴)
  // 붙어 있던 화살표(그 도형 또는 묶음 통째에 붙은 끝)는 새것에 다시 붙임
  // 누른 자리가 묶음의 바깥 상자 안이면 그 묶음의 맨 위 조각(빈 상자 안쪽을 눌러도 골라지듯 — 2026-10-18 사용자 지적: 내 심볼은 선을 정확히 눌러야 했음)
  function groupAt(p) {
    const boxes = new Map()
    for (const it of hitPool()) { if (!it.group_id || it.locked) continue; const b = sceneBox(it, textBox), g = boxes.get(it.group_id)
      boxes.set(it.group_id, g ? { box: unionBox([g.box, b]), top: (it.z ?? 0) >= (g.top.z ?? 0) ? it : g.top } : { box: b, top: it }) }
    let best = null
    for (const { box, top } of boxes.values()) if (p.x >= box.x && p.x <= box.x + box.w && p.y >= box.y && p.y <= box.y + box.h && (!best || (top.z ?? 0) > (best.z ?? 0))) best = top
    return best
  }
  function swapShape(oldIds, key) {
    const m = R.current.model, set = new Set(oldIds), olds = m.items.filter(x => set.has(x._id)); if (!olds.length) return
    const ob = unionBox(olds.map(it => sceneBox(it, textBox))), oldGid = olds.every(o => o.group_id && o.group_id === olds[0].group_id) ? olds[0].group_id : null
    let its
    if (key.startsWith('customsym:')) {
      const protos = customItems(key); if (!protos) return
      const b = unionBox(protos.map(it => sceneBox(it, textBox))), lo = Math.max(ob.w, ob.h), lc = Math.max(b.w, b.h); if (lc < 1e-6) return
      const k = lo / lc, bc = { x: b.x + b.w / 2, y: b.y + b.h / 2 }
      its = protos.map(it => ({ ...it, scale: (it.scale || 1) * k, pos: [bc.x + ((it.pos?.[0] || 0) - bc.x) * k, bc.y + ((it.pos?.[1] || 0) - bc.y) * k] }))
      const nb = unionBox(its.map(it => sceneBox(it, textBox)))
      its = moveItems(its, its.map(it => it._id), ob.x + ob.w / 2 - (nb.x + nb.w / 2), ob.y + ob.h / 2 - (nb.y + nb.h / 2))
    } else {
      const s0 = olds.find(o => o.pen !== undefined)   // 선 색·굵기는 옛 조각에서
      its = [{ ...boxItem(key, ob.x, ob.y, ob.w, ob.h), ...(s0 ? { pen: s0.pen, width: s0.width, style: s0.style } : {}), z: Math.max(...olds.map(o => o.z ?? 0)) }]
    }
    const all = [...m.items.filter(x => !set.has(x._id)), ...its]
    const host = its.length === 1 ? its[0] : groupHost(all, its[0].group_id, rectOf)
    const rebound = all.map(a => {
      if (!isArrow(a)) return a
      let o = a
      for (const kk of ['bind1', 'bind2']) {
        if (!set.has(a['_' + kk]) && !(oldGid && a[kk + '_group'] === oldGid)) continue
        const e = bindEnd(a, kk, m.items, rectOf); if (!e) continue
        o = { ...o, ...bindOf(kk, host, nearestBorder(host, e.p, rectOf).p) }
      }
      return o
    })
    commit(rebound, its.map(it => it._id), key.startsWith('customsym:') ? '내 심볼로 바꾸기' : '도형 바꾸기')
  }
  // 고른 도형을 레이어로(데스크톱 `move_selection_to_layer`) — 그 레이어의 잠금을 물려받음, 되돌리기 한 칸
  function moveSelToLayer(id) {
    const m = R.current.model, ly = layersOf(m).find(l => l.id === id), ids = new Set(movingSet(R.current.sel))
    if (!ly) return; if (!ids.size) return setStatus('옮길 도형을 먼저 고르세요')
    commit(m.items.map(it => (ids.has(it._id) ? { ...it, layer_id: id === 'default' ? null : id, locked: ly.locked } : it)), [...ids], '레이어 옮김')
    setStatus(`레이어 옮김: ${ids.size}개 → ${ly.name}`)
  }
  // 내보내기 — o = { format: 'png'|'pdf'|'svg', selection, page, orient, margin, transparent, name }. 숨긴 레이어는 안 냄(데스크톱: 안 보이는 것은 안 그림)
  async function exportDoc(o) {
    if (o.format === 'html') return exportHtml(o)
    const r = await exportPages(o); if (r.error) { setStatus(r.error); return false }
    const pages = r.pages
    if (o.format === 'pdf') exportPdf(pages.length === 1 ? pages[0] : pages, o.name)
    else if (pages.length === 1) { if (o.format === 'png') await exportPng(pages[0], o.name + '.png'); else exportSvg(pages[0], o.name + '.svg') }
    else for (let i = 0; i < pages.length; i++) { const nm = `${o.name}-${i + 1}`; if (o.format === 'png') await exportPng(pages[i], nm + '.png'); else exportSvg(pages[i], nm + '.svg') }
    setStatus(o.format === 'pdf' ? `${pages.length > 1 ? pages.length + '쪽 — ' : ''}인쇄 창에서 「PDF로 저장」을 고르세요` : pages.length > 1 ? `${pages.length}쪽 내려받음` : `${o.name}.${o.format} 내려받음`)
    return true
  }
  // HTML 한 파일(2026-10-18 — 방송본 고정·예비본): 범위의 전체 그림 + 칠판의 프레임 = 발표 장, 글꼴은 맨 위에 한 번만(그림마다 넣지 않음 — preview = 글꼴 빼고 그림)
  async function exportHtml(o) {
    const ov = await exportPages({ ...o, format: 'svg', preview: true, transparent: false, onePage: true, scope: o.scope === 'frames' ? 'all' : o.scope })
    if (ov.error || !ov.pages?.length) { setStatus(ov.error || '내보낼 것이 없어요'); return false }
    const hasFrames = R.current.model.items.some(it => it.type === 'frame')
    const sl = hasFrames ? await exportPages({ ...o, format: 'svg', preview: true, transparent: false, scope: 'frames', onePage: false }) : { pages: [] }
    const its = R.current.model.items, fonts = its.some(usesBoardFont) ? await fontFaces(weightsOf(its)) : ''
    const d = new Date(), p2 = v => String(v).padStart(2, '0'), made = `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`
    const html = buildHtml({ title: o.name, made, overview: ov.pages[0].svg, slides: (sl.pages || []).map(pg => ({ svg: pg.svg, name: pg.name })), fonts })
    download(new Blob([html], { type: 'text/html' }), `${o.name}.html`)
    setStatus(`${o.name}.html 내려받음 — 전체 그림${sl.pages?.length ? ` + 발표 ${sl.pages.length}장` : ''}, 인터넷 없이 열려요`)
    return true
  }
  // 내보낼 쪽들(내려받지 않음 — 내보내기 창 미리보기도 씀). o.scope: 'frames' = 프레임만(순서대로, 2026-10-18 사용자: 「프레임 모두 고르기」를 내보내기 범위로). 쪽마다 frameId(순서 끌기)
  async function exportPages(o) {
    const m = R.current.model, hid = new Set(layersOf(m).filter(l => !l.visible).map(l => l.id))
    // 칠판 규칙(2026-10-18 사용자와 정함 — 데스크톱 「틀이 있으면 전체 = 틀」을 바꿈): 용지틀도 보통 도형
    const all = drawOrder(m.items).filter(([it]) => !hid.has(layerIdOf(it)))
    // 「고른 것」에 종이틀이 있으면 틀마다 한 쪽(틀 안의 것은 고르지 않아도 전부), 어느 틀에도 안 든 고른 것은 마지막 한 쪽에 모음(2026-10-18 사용자와 정함 — 「고른 것」·「종이틀대로」를 하나로)
    const onlyFrames = o.scope === 'frames', selIds = onlyFrames ? null : o.selection ? new Set(withContents(R.current.sel)) : null
    const isFrame = it => it.type === 'frame' || (it.type === 'titleblock' && (it.plain || !onlyFrames))
    const selFrames = onlyFrames ? all.filter(([it]) => it.type === 'frame' || (it.type === 'titleblock' && it.plain)) : selIds ? all.filter(([it]) => selIds.has(it._id) && isFrame(it)) : []   // 프레임은 순서대로, 종이틀은 줄/칸 우선
    if (onlyFrames && !selFrames.length) return { error: '프레임이 없어요 — 상단 「프레임」으로 영역을 감싸 보세요' }
    if (selFrames.length && !o.onePage) {   // onePage = 「고른 것 한 쪽에」 — 틀도 보통 도형처럼 고른 것 전체를 감싼 한 쪽(2026-10-18 사용자: 보이지 않는 종이틀)
      const rank = new Map(orderedFrames(m.items).map((f, i) => [f._id, i]))
      const frames = [...selFrames.filter(([it]) => it.type === 'frame').sort((a, b) => rank.get(a[0]._id) - rank.get(b[0]._id)).map(([it]) => ({ ...sceneBox(it, textBox), it })),
        ...readingOrder(selFrames.filter(([it]) => it.type === 'titleblock').map(([it]) => ({ ...sceneBox(it, textBox), it })), o.order || 'rows')]
      const body = all.filter(([it]) => !(it.type === 'titleblock' && it.plain) && it.type !== 'frame'), ob = boardMembership(m.items), rts = resolveRoutes(m.items, rectOf), pages = []
      const tr = o.format !== 'pdf' && o.transparent
      for (const f of frames) pages.push({ ...await buildSvg(body, f, f.it.type === 'frame' ? { ...o, clip: true, transparent: tr } : { ...o, frame: { size: f.it.size, orient: f.it.orient, box: f }, transparent: tr }, ob, rts, o.format !== 'pdf' && !o.preview), frameId: f.it.type === 'frame' ? f.it._id : null, name: f.it.name || '' })   // 프레임 = 틀 안만(밖은 잘림)
      const inFrame = it => { const b = sceneBox(it, textBox), cx = b.x + b.w / 2, cy = b.y + b.h / 2; return frames.some(f => cx >= f.x && cx <= f.x + f.w && cy >= f.y && cy <= f.y + f.h) }
      const rest = onlyFrames ? [] : all.filter(([it]) => selIds.has(it._id) && it.type !== 'titleblock' && it.type !== 'frame' && !inFrame(it))
      if (rest.length) pages.push(await buildSvg(rest, unionBox(rest.map(([it]) => sceneBox(it, textBox))), { ...o, frame: null, transparent: tr }, ob, rts, o.format !== 'pdf'))   // 틀 밖에 고른 것 — 버리지 않음
      return { pages }
    }
    let ents = all
    if (selIds) ents = all.filter(([it]) => selIds.has(it._id))
    if (!ents.length) return { error: o.selection ? '내보낼 도형을 먼저 고르세요' : '내보낼 도형이 없어요' }
    const frame = null
    const src = unionBox(ents.map(([it]) => sceneBox(it, textBox)))
    // 프레임 테두리·이름표는 그리지 않음(자리만 — 「고른 것 한 쪽에」)
    const res = await buildSvg(ents.filter(([it]) => it.type !== 'frame'), src, { ...o, frame, transparent: o.format !== 'pdf' && o.transparent }, boardMembership(m.items), resolveRoutes(m.items, rectOf), o.format !== 'pdf' && !o.preview)
    return { pages: [res] }
  }
  // ── KAIROS 대화창 길목(chat.jsx) ──
  // 고른 것(보드면 안의 것까지)의 글 — 질문에 같이 보냄
  function selTexts() {
    const m = R.current.model, ids = new Set(withContents(R.current.sel))
    return m.items.filter(it => ids.has(it._id)).flatMap(itemTexts)
  }
  // 고른 것 속 그림(최대 4장) — 대화창이 「이거 고쳐 줘」의 고칠 그림으로 보냄(서버 `input_images`, 2026-10-20 사용자: 칠판에서 고르고 말하기)
  function selImages() {
    const m = R.current.model, ids = new Set(withContents(R.current.sel))
    return m.items.filter(it => ids.has(it._id) && it.type === 'image' && it.data).slice(0, 4).map(it => (it.data.startsWith('data:') ? it.data : 'data:image/png;base64,' + it.data))
  }
  function itemTexts(it) {   // 도형 하나의 글(대화 재료)
    const out = []
    if (it.type === 'text' && it.text?.trim()) out.push(it.text)
    if (it.label?.text?.trim()) out.push(it.label.text)
    for (const L of it.labels || []) if (L.text?.trim()) out.push(L.text)
    if (it.type === 'table') { const t = (it.cells || []).map(r => r.filter(Boolean).join(' | ')).filter(Boolean).join('\n'); if (t) out.push(t) }
    if (it.type === 'memo') { const t = memoText(it.lines); if (t.trim()) out.push(t) }
    if (it.type === 'doc') out.push(`[정리 문서] ${it.title || ''}\n${docText(it.html)}`)   // 정리 문서도 근거·재료로
    if (it.type === 'web') out.push(`[웹] ${it.title || ''} ${it.url || ''}`.trim())
    if (it.type === 'pdf') out.push(`[PDF] ${it.name || ''}\n${it.text || ''}`.trim())   // 올릴 때 서버가 뽑은 글
    if (it.type === 'image' && it.alt) out.push(`[그림] ${it.alt}`)
    return out
  }
  // 여러 도형이 한눈에 들어오게(딥모드 판 보기 등) — 없으면 false
  function showIds(ids) {
    const its = R.current.model.items.filter(it => ids?.includes(it._id)); if (!its.length) return false
    const L = 24, b = unionBox(its.map(it => sceneBox(it, textBox))), W = size.w - rightInset(svg.current) - L, z = Math.min(1.5, Math.max(ZMIN, Math.min(W / (b.w * 1.1), size.h / (b.h * 1.2))))   // 왼쪽 카드(도형·프레임 목록) 자리는 빼고
    setSel(its.map(it => it._id)); setCam({ z, x: L + W / 2 - (b.x + b.w / 2) * z, y: size.h / 2 - (b.y + b.h / 2) * z })
    return true
  }
  // 답 → 카드 = 채운 네모 하나 + 왼쪽 위 라벨(상자 폭에서 줄바꿈) + 글에 맞춘 높이(`fit_text`) — 한 덩어리라 글이 넘칠 수 없음(2026-10-18 사용자 지적: 보드 + 글 두 덩어리는 넘침)
  // 지금 화면에서 다른 것과 안 겹치는 자리(왼쪽 카드·오른쪽 속성 카드 자리는 뺌), 카드에 `chat_at` = 답 시각
  const CARD_W = MEMO.W   // 답 메모 폭(옛 카드와 같은 340)
  // 2026-10-18 사용자: 답도 메모로 — 제목·목록·할 일·코드·인용이 줄 단위(정리하기 쉽게). 옛 카드(네모 + 왼쪽 위 라벨)는 그대로 열림
  function cardItem(msg, x, y, z) {
    const it = base([x, y], { type: 'memo', rect: [0, 0, MEMO.W, 40], fill: '#ffffffff', lines: memoFromAnswer(msg.content, sourceLine(msg.model, msg.at)), chat_at: msg.at, z })
    return { ...it, rect: [0, 0, MEMO.W, memoHeight(it)] }
  }
  // 답 속 표 = 메모 안 표 줄(2026-10-21 사용자: 한 답 = 메모 하나 — 전엔 메모 밑 진짜 표로 따로). 꾸밀 게 많으면 줄 손잡이 ⠿ 「칠판 표로 바꾸기」
  function cardItems(msg, x, y, z) {
    if (msg.html) return [docItem(msg, x, y, z)]   // 정리 문서 = 문서 카드 하나
    return answerItems(msg, x, y, z)
  }
  // 칠판 진짜 표(칸 고치기·칸 꾸밈) — 붙여넣은 표만 있을 때·메모 표 줄 「칠판 표로 바꾸기」
  function boardTable(rows, header, s, z) {
    const cols = Math.max(...rows.map(r => r.length)), cells = rows.map(r => Array.from({ length: cols }, (_, c) => (r[c] || '').replace(/\*\*/g, '')))
    return fitTable(base([0, 0], { type: 'table', rows: rows.length, cols, header, rect: [0, 0, Math.max(MEMO.W, cols * 90), rows.length * 30], cells, col_widths: Array(cols).fill(1 / cols), scale: s, z }))
  }
  // 대화창 표 답 「그래프로」(§8 항목66 1단계 이어서, 2026-10-25) — 칠판 표 + 모양(`chart`), 표 크기는 기억(`table_wh` — 속성 카드에서 표로 돌아가면 그 크기).
  // 칸에 출처 번호가 있었으면 그 출처를 그래프 밑 회색 글로(한 묶음) — 어디서 온 숫자인지 남게. t = { rows, header, kind, sources }
  function chartItems(t) {
    const { cells, refs } = answerTable(t.rows), z = topZ(R.current.model.items) + 1, tb = boardTable(cells, t.header, 1, z), [, , w, h] = tb.rect
    const ch = { ...tb, chart: t.kind, table_wh: [w, h], rect: [0, 0, Math.max(w, CHART_MIN[0]), Math.max(h, CHART_MIN[1])] }
    const used = (t.sources || []).filter(x => refs.includes(x.n)); if (!used.length) return [ch]
    const g = 'g' + newId(), note = base([0, ch.rect[3] + 6], { type: 'text', text: used.map(x => `[${x.n}] ${x.title || siteOf(x.url)} · ${siteOf(x.url)}`).join('\n'), color: '#ff8a8f98', font: 10, bg: null, z, group_id: g })
    return [{ ...ch, group_id: g }, note]
  }
  function pinChart(t) {   // 누르기 = 화면 가운데 먼저·겹치면 빈자리(그림·아이콘 후보와 같게), 넣은 _id들
    const ps = chartItems(t), m = R.current.model, b = unionBox(ps.map(it => sceneBox(it, textBox))), at = spotNear(b.w, b.h), its = placeAt(ps, at.x, at.y)
    commit([...m.items, ...its], its.map(it => it._id), '그래프로 붙이기'); setTool('select')
    setStatus('그래프로 붙였어요 — 두 번 누르면 표로 펼쳐 숫자를 고쳐요 · 모양은 속성 카드에서')
    return its.map(it => it._id)
  }
  // 딥모드 지면(§8 항목66 2단계, 2026-10-25) — 계획(꼭지 + 본문) → 프레임(들) 안에 진짜 칠판 물건. 자리는 deep.js, 물건은 deepboard.js, 단계 사이 화살표만 여기(길 찾기).
  // 프레임 = 폭 1600 · 높이는 내용만큼(16:9 고집 버림 — 같은 날 2차 판정). 프레임 번호 = 발표 차례. 되돌리기 한 번에 통째로.
  // 3-1 톤(옛 디자인 묶음): 첫 프레임에 `deep_plan` { plan, style, fix, vs, sig } — 같은 내용을 다른 톤·꼭지 모양으로 다시 지음(`deepRedo`).
  // 지은 물건마다 `deep_of` = 첫 프레임 _id(다시 지을 때 지울 것), 꼭지 물건은 `deep_sec` = 꼭지 번호(「꼭지 모양」)
  const deepSig = items => { const t = JSON.stringify(items.filter(it => it.type !== 'frame').map(it => [it.type, it.deep_sec ?? -1, Math.round(it.pos[0]), Math.round(it.pos[1]), (it.lines || []).map(l => l.t), it.cells, it.chart || '', it.fill || '', ...(it.html ? [it.html.length, it.html.slice(-80)] : [])]))
    let h = 5381; for (let i = 0; i < t.length; i++) h = ((h << 5) + h + t.charCodeAt(i)) | 0; return String(h >>> 0) }   // 손으로 고쳤나(다시 지을 때 먼저 물음) — 자리·글·칸만(+ 움직이는 카드 HTML — 5단계)
  // meta = { topic, brief } — 꼭지 다시 쓰기(5단계)가 「누구에게」를 알게 계획과 같이 둠
  function deepBuild(plan, o, { style = 'calm', fix = {}, keep = null, meta = {} } = {}) {
    const m = R.current.model, S = styleOf(style), lay = deepLayout(plan, deepMeasure(plan, S.look), { fix }), n = lay.pages.length
    const zb = Math.min(0, ...m.items.map(x => x.z ?? 0)) - 1, zt = topZ(m.items) + 1, no0 = keep ? keep.no - 1 : orderedFrames(m.items).length, out = [], links = []
    const rootId = keep?.id || newId(), vs = {}
    lay.pages.forEach((pg, p) => {
      const X = o.x + pg.x, Y = o.y, name = (plan.title || 'Deep Mode') + (n > 1 ? ` (${p + 1}/${n})` : '')
      out.push(p === 0 ? { ...base([X, Y], { type: 'frame', rect: [0, 0, pg.W, pg.H], name, no: no0 + 1, z: zb }), _id: rootId } : base([X, Y], { type: 'frame', rect: [0, 0, pg.W, pg.H], name, no: no0 + p + 1, z: zb, deep_of: rootId }))
      out.push(...deepHead(plan, X + pg.head.x, Y + pg.head.y, pg.head.w, pg.k, p, n, S.look).map(it => ({ ...it, z: zt, deep_of: rootId })))
      pg.cells.forEach(c => { vs[c.i] = c.v || ''
        const r = deepSection(plan, plan.sections[c.i], X + c.x, Y + c.y, c.w, pg.k, c.v, S.look); out.push(...r.items.map(it => ({ ...it, z: zt, deep_of: rootId, deep_sec: c.i }))); links.push(...r.links) })
    })
    const keepM = R.current.model
    R.current.model = { ...keepM, items: [...keepM.items, ...out] }   // 길 찾기·붙는 끝이 새 카드를 찾게(answerItems와 같게)
    try {
      for (const [a, b] of links) {
        const A = out.find(it => it._id === a), B = out.find(it => it._id === b), ba = sceneBox(A, textBox), bb = sceneBox(B, textBox), cy = Math.min(ba.y + ba.h, bb.y + bb.h) / 2 + Math.max(ba.y, bb.y) / 2
        const pa = { p: { x: ba.x + ba.w, y: cy }, n: { x: 1, y: 0 } }, pb = { id: b, p: { x: bb.x, y: cy }, n: { x: -1, y: 0 } }
        const pts = connRoute(a, pa, pb, null).map(q => [q.x, q.y])
        out.push({ ...arrowItem(a, pa.p, b, pb.p, { auto_route: true, pts, color: S.look.arrow || '#ffc4613f', width: 1.5, style: 1, head: true, head_start: false }), z: zt, group_id: A.group_id, deep_of: rootId, deep_sec: A.deep_sec })
      }
    } finally { R.current.model = keepM }
    out[0] = { ...out[0], deep_plan: { ...meta, plan: deepBare(plan), style, fix, vs, sig: deepSig(out) } }
    return { out, lay, n, o }
  }
  // 요약 그림(2026-10-25) — 그림 바이트(data)는 그림 물건에만 두고 계획엔 주소·크기만(파일이 그림 두 벌로 불지 않게). 다시 지을 땐 판의 그림 물건에서 되살림
  const deepBare = plan => ({ ...plan, sections: (plan.sections || []).map(s => (s.body?.data ? { ...s, body: Object.fromEntries(Object.entries(s.body).filter(([k]) => k !== 'data')) } : s)) })
  const deepWithImgs = (plan, items, rootId) => ({ ...plan, sections: (plan.sections || []).map((s, i) => {
    if (s.shape !== '요약 그림' || !s.body?.img || s.body.data) return s
    const im = items.find(it => it.type === 'image' && it.deep_of === rootId && it.deep_sec === i)
    return im ? { ...s, body: { ...s.body, data: im.data } } : s
  }) })
  const deepInfo = r => ({ ids: r.out.map(it => it._id), pages: r.lay.pages.map(pg => ({ x: r.o.x + pg.x, y: r.o.y, w: pg.W, h: pg.H, waste: deepWaste(pg), rows: r.lay.rows.map(rr => rr.slots.map((sl, k) => `${sl.map(i => i + (rr.v[i] ? rr.v[i][0] : '')).join('+')}:${rr.spans[k]}`).join(' ')) })) })
  // at = 첫 장 왼쪽 위(없으면 지금 칠판의 오른쪽 빈자리)
  const deepSpot = () => { const m = R.current.model, right = m.items.length ? unionBox(m.items.map(it => sceneBox(it, textBox))) : null; return right ? { x: right.x + right.w + 200, y: right.y } : { x: 0, y: 0 } }   // 새 판 자리 = 칠판 오른쪽 끝
  // Deep Mode 스켈레톤(2026-10-25) — 만드는 동안 판이 놓일 자리에 꼭지 칸 n개(폭 1600 = 판 폭, 높이는 어림) + 그리로 화면 이동. 돌려준 번호로 pendHide
  function deepPending(n) {
    const o = deepSpot(), id = newId(), w = 1600, h = 260 + Math.ceil(Math.max(3, n || 6) / 3) * 300
    setPend(ps => [...ps, { id, kind: 'deep', label: 'Deep Mode 판 만드는 중', x: o.x, y: o.y, w, h, n }])
    const L = 24, W = size.w - rightInset(svg.current) - L, z = Math.min(1, Math.max(ZMIN, Math.min(W / (w * 1.1), size.h / (h * 1.2))))
    setCam({ z, x: L + W / 2 - (o.x + w / 2) * z, y: size.h / 2 - (o.y + h / 2) * z })
    return id
  }
  // 꼭지 다시 쓰기 스켈레톤 — 그 꼭지 물건들 자리마다 막대(판은 그대로 보이고 그 칸만 깜빡)
  function deepSectionPending(rootId, idx) {
    const m = R.current.model, ids = []
    for (const i of idx || []) { const its = m.items.filter(it => it.deep_of === rootId && it.deep_sec === i); if (!its.length) continue
      const b = unionBox(its.map(it => sceneBox(it, textBox))), id = newId(); ids.push(id)
      setPend(ps => [...ps, { id, kind: 'section', label: '꼭지 다시 쓰는 중', x: b.x, y: b.y, w: b.w, h: b.h }]) }
    return ids
  }
  const pendHide = ids => { const del = new Set([].concat(ids || [])); setPend(ps => ps.filter(q => !del.has(q.id))) }
  function deepBoard(plan, at, style = 'calm', meta = {}) {
    const m = R.current.model, o = at || deepSpot()
    const r = deepBuild(plan, o, { style, meta })
    commit([...m.items, ...r.out], [], 'Deep Mode 판')
    setStatus(`Deep Mode 판 — ${r.n}장 · 꼭지 ${plan.sections?.length || 0}개 · ${styleOf(style).name}`)
    return deepInfo(r)
  }
  // 딥모드 판의 첫 프레임(그 판 물건 하나 또는 프레임에서) — 없으면 null
  const deepRoot = it => { if (!it) return null; const items = R.current.model.items; return it.deep_plan ? it : it.deep_of ? items.find(x => x._id === it.deep_of && x.deep_plan) || null : null }
  const deepEdited = root => deepSig(R.current.model.items.filter(it => it.deep_of === root._id || it._id === root._id)) !== root.deep_plan.sig
  // 같은 내용을 다른 톤(style)·꼭지 모양(fix = { 꼭지: 모양 })으로 다시 지음 — 첫 프레임 자리·번호·_id는 그대로(발표 차례 유지), 되돌리기 한 번
  // plan·fixAll = 꼭지 다시 쓰기(5단계 `deepRedoSection`) — 새 계획과 모양 기억 통째
  function deepRedo(rootId, { style, fix, plan, fixAll, label } = {}) {
    const m = R.current.model, root = m.items.find(it => it._id === rootId && it.deep_plan); if (!root) return null
    if (m.items.some(it => (it._id === rootId || it.deep_of === rootId) && it.locked)) { setStatus('잠긴 판이라 다시 지을 수 없어요 — 먼저 잠금 해제(Ctrl+L)'); return null }   // 지우고 새로 짓는 길이라 길목 지킴이가 옛것을 되살려 겹침
    const d = root.deep_plan, st = style || d.style, fx = fixAll || (fix ? { ...d.fix, ...fix } : d.fix)
    const meta = Object.fromEntries(['topic', 'brief'].filter(k => d[k] != null).map(k => [k, d[k]]))
    const rest = m.items.filter(it => it._id !== rootId && it.deep_of !== rootId)
    R.current.model = { ...m, items: rest }   // 지을 자리 계산·길 찾기가 옛 물건을 안 보게
    let r
    try { r = deepBuild(deepWithImgs(plan || d.plan, m.items, rootId), { x: root.pos[0], y: root.pos[1] }, { style: st, fix: fx, keep: { id: rootId, no: root.no }, meta }) } finally { R.current.model = m }
    commit([...deepRebind(m.items, rest, r.out, rootId), ...r.out], [rootId], label || (plan ? '꼭지 다시 쓰기' : style ? `톤 — ${styleOf(st).name}` : '꼭지 모양'))
    setStatus(label ? `${label} — 판을 다시 지었어요` : plan ? '꼭지를 다시 써서 판을 다시 지었어요 — Ctrl+Z로 되돌리기' : style ? `톤을 「${styleOf(st).name}」로 바꿔 다시 지었어요 — 마음에 안 들면 Ctrl+Z` : '꼭지 모양을 바꿔 다시 배치했어요 — Ctrl+Z로 되돌리기')
    return deepInfo(r)
  }
  // 꼭지 다시 쓰기(§8 항목66 5단계) — 고른 것이 한 판의 꼭지들뿐이면 { root, idx, titles, edited, plan, brief, topic }.
  // 프레임·머리를 같이 골랐거나 출처 카드뿐이면 null(판 통째는 대화창 계획 카드로 — 이번 범위 밖). rootId·only = 고른 것 대신 그 판 그 꼭지(덮어쓰기 확인 뒤 — 그사이 고른 것이 바뀌어도)
  function deepTarget(rootId, only) {
    const m = R.current.model, ids = new Set(withContents(R.current.sel)), selIt = m.items.filter(it => ids.has(it._id))
    const root = rootId ? m.items.find(it => it._id === rootId && it.deep_plan) : selIt.length ? deepRoot(selIt[0]) : null
    if (!root || (!rootId && selIt.some(it => deepRoot(it) !== root || !Number.isInteger(it.deep_sec)))) return null
    const d = root.deep_plan, secs = d.plan.sections || [], idx = only || [...new Set(selIt.map(it => it.deep_sec))].sort((a, b) => a - b)
    if (idx.every(i => !secs[i] || secs[i].shape === '출처 카드')) return null
    return { root: root._id, idx, titles: idx.map(i => secs[i]?.title || ''), edited: deepEdited(root), plan: d.plan, brief: d.brief || {}, topic: d.topic || d.plan.title || '' }
  }
  // 서버가 다시 쓴 꼭지([{ i, …꼭지 }]) + 판 출처 → 계획에 적고 다시 지음 — 계획에 적으니 「톤」으로 다시 지어도 새 꼭지(4단계에서 남긴 것). 모양이 바뀐 꼭지는 모양 기억(fix)을 지움
  function deepRedoSection(rootId, secs, sources) {
    const m = R.current.model, root = m.items.find(it => it._id === rootId && it.deep_plan); if (!root || !secs?.length) return null
    const d = root.deep_plan, ss = [...d.plan.sections], fix = { ...d.fix }
    for (const { i, ...s } of secs) if (ss[i]) { if (ss[i].shape !== s.shape) delete fix[i]; ss[i] = s }
    const before = { plan: deepWithImgs(d.plan, m.items, rootId), fix: d.fix || {} }, after = { plan: { ...d.plan, sections: ss, ...(sources ? { sources } : {}) }, fix }
    const r = deepRedo(rootId, { plan: after.plan, fixAll: fix })
    if (r) deepAlt.current.set(rootId, { before, after })
    return r
  }
  // 꼭지 다시 쓰기 전·후 비교(2026-10-25 사용자 「바로 교체라 비교가 어려움」) — 대화창 답의 「원래대로 ↔ 바꾼 것」 버튼이 판을 그 자리에서 번갈아 다시 지음.
  // 두 계획은 이 창에만 기억(새로고침하면 버튼이 사라짐 — Ctrl+Z는 그대로). 지금 판이 어느 쪽인지는 계획을 견줘 봄(Ctrl+Z로 돌아가도 맞게).
  // 그사이 손으로 고쳤으면 덮어쓰지 않고 'edited'
  const deepAlt = useRef(new Map())
  const planKey = plan => JSON.stringify(deepBare(plan).sections)
  function deepFlipState(rootId) {
    const a = deepAlt.current.get(rootId), root = R.current.model.items.find(it => it._id === rootId && it.deep_plan); if (!a || !root) return null
    const k = planKey(root.deep_plan.plan)
    return k === planKey(a.after.plan) ? 'after' : k === planKey(a.before.plan) ? 'before' : null
  }
  function deepFlip(rootId) {
    const now = deepFlipState(rootId); if (!now) return null
    const root = R.current.model.items.find(it => it._id === rootId && it.deep_plan)
    if (deepEdited(root)) { setStatus('판을 손으로 고친 뒤라 바꾸면 덮어써요 — 되돌리려면 Ctrl+Z'); return 'edited' }
    const to = now === 'after' ? 'before' : 'after', t = deepAlt.current.get(rootId)[to]
    deepRedo(rootId, { plan: t.plan, fixAll: t.fix, label: to === 'before' ? '꼭지 원래대로 보기' : '꼭지 바꾼 것 보기' })
    return to
  }
  // 다시 지을 때 손으로 그린 화살표(판 밖 물건)의 끝 — 옛 판 물건에 붙어 있었으면 같은 꼭지·같은 종류의 새 물건(그 꼭지 안 차례도 같게)으로 옮겨 붙임.
  // 물건 안 점은 크기 비율로 옮김(테두리 위 점은 새 테두리 위로). 맞는 새 물건이 없으면 끝이 그 자리에 떠 있음
  function deepRebind(all, rest, out, rootId) {
    const old = all.filter(it => it.deep_of === rootId && !isArrow(it)), fresh = out.filter(it => !isArrow(it) && it.type !== 'frame')
    const key = it => `${it.deep_sec ?? -1}|${it.type}`, rank = (list, it) => list.filter(x => key(x) === key(it)).indexOf(it)
    const pair = new Map(old.map(it => { const c = fresh.filter(x => key(x) === key(it)), s = fresh.filter(x => (x.deep_sec ?? -1) === (it.deep_sec ?? -1))
      return [it._id, c[rank(old, it)] || c[0] || s[0] || null] }))
    const grp = new Map(old.filter(it => it.group_id).map(it => [it.group_id, pair.get(it._id)?.group_id || null]))
    const oldById = new Map(old.map(it => [it._id, it]))
    return rest.map(a => {
      if (!isArrow(a)) return a
      let n = a
      for (const k of ['bind1', 'bind2']) {
        const o = oldById.get(a['_' + k]), g = a[k + '_group']
        if (o) {
          const nw = pair.get(o._id), pt = a[k + '_pt']
          if (!nw || !pt) { n = { ...n, ['_' + k]: null, [k + '_pt']: null }; continue }
          const [ox, oy, ow, oh] = rectOf(o), [nx, ny, nW, nH] = rectOf(nw)
          n = { ...n, ['_' + k]: nw._id, [k + '_pt']: [nx + ((pt[0] - ox) / (ow || 1)) * nW, ny + ((pt[1] - oy) / (oh || 1)) * nH] }
        } else if (g && grp.has(g)) n = grp.get(g) ? { ...n, [k + '_group']: grp.get(g) } : { ...n, [k + '_group']: null, [k + '_pt']: null }
      }
      return n
    })
  }
  // 속성 카드 딥모드 줄 — 고른 것이 딥모드 판이면(프레임 또는 그 판 물건). 꼭지 하나(그 묶음)만 골랐고 모양이 둘 이상이면 「꼭지」 줄도
  function deepProps() {
    const selIt = R.current.sel.map(id => R.current.model.items.find(it => it._id === id)).filter(Boolean), root = deepRoot(selIt.find(it => it.deep_plan || it.deep_of)); if (!root) return null
    const d = root.deep_plan, secs = [...new Set(selIt.map(it => it.deep_sec))], si = secs.length === 1 && Number.isInteger(secs[0]) ? secs[0] : null
    const sec = si != null ? d.plan.sections[si] : null, opts = sec ? variantsOf(sec) : []
    const tg = onAsk ? deepTarget() : null   // 꼭지 다시 쓰기(5단계) = 대화창이 맡음(덮어쓰기 확인·크레딧 표시도 거기)
    return { style: d.style || 'calm', edited: () => deepEdited(root), onStyle: k => deepRedo(root._id, { style: k }),
      sec: opts.length > 1 ? { shape: sec.shape, cur: d.fix?.[si] || d.vs?.[si] || opts[0], opts, onPick: v => deepRedo(root._id, { fix: { [si]: v } }) } : null,
      redo: tg ? { n: tg.idx.length, card: tg.idx.some(i => d.plan.sections[i]?.shape === '움직이는 카드'), go: () => onAsk('', 'deep-section') } : null }
  }
  // 웹 검색 답(§8 항목61 ② 담는 법, 2026-10-19) = 요약 메모 + 오른쪽에 출처 웹 카드(본문에 쓰인 번호만, 제목 앞 [n], 가벼운 제목 카드 — 칸 안 페이지 없음) + 메모 → 카드 화살표, 한 묶음.
  // 「어디서 왔는지」가 칠판 위 선으로 보이게(회사 KAIROS 웹은 답과 출처가 따로 놂). 출처가 없으면 메모 하나(cardItem)
  function answerItems(msg, x, y, z) {
    const memo = cardItem(msg, x, y, z), src = msg.sources || []
    if (msg.refs?.length) return boardRefItems(memo, msg.refs, z)
    if (!src.length) return [memo]
    const g = 'g' + newId(), gap = 14, x2 = x + MEMO.W + 90, ch = WEB_HEAD + WEB_INFO_H
    const cards = src.map((s, i) => base([x2, y + i * (ch + gap)], { ...webCardFields({ url: s.url, title: `[${s.n}] ${s.title || siteOf(s.url)}`, desc: [s.date, siteOf(s.url)].filter(Boolean).join(' · '), frameable: false }), z, group_id: g }))
    const keep = R.current.model, ay = y + Math.min(memo.rect[3] / 2, 40)
    R.current.model = { ...keep, items: [...keep.items, memo, ...cards] }   // 길 찾기·붙는 끝이 새 메모·카드를 찾게(아직 칠판엔 안 넣음)
    try {
      const arrows = cards.map((c, i) => {
        const a = { p: { x: x + MEMO.W, y: ay }, n: { x: 1, y: 0 } }, t = { id: c._id, p: { x: x2, y: c.pos[1] + c.rect[3] / 2 }, n: { x: -1, y: 0 } }
        const pts = connRoute(memo._id, a, t, null).map(q => [q.x, q.y])
        return { ...arrowItem(memo._id, a.p, c._id, t.p, { auto_route: true, pts, color: '#ff9aa0a6', width: 1, style: 1, head: true, head_start: false }), z, group_id: g }   // 번호는 카드 제목 앞 [n] — 화살표 라벨은 갈래 줄기에 겹쳐 안 읽혔음(실화면)
      })
      return [{ ...memo, group_id: g }, ...cards, ...arrows]
    } finally { R.current.model = keep }
  }
  // 새 빈 메모(상단 「메모」 — 포스트잇 자리) — 화면 가운데에 놓고 바로 고치기
  // 버튼으로 넣는 것의 자리 — 화면 가운데 먼저, 겹치면 가장 가까운 빈자리(2026-10-20 사용자, chatFormat `nearSpot`). 왼쪽 위 = 돌려줌
  function spotNear(w, h) {
    const c = R.current.cam, view = { x: -c.x / c.z, y: -c.y / c.z, w: size.w / c.z, h: size.h / c.z }, s = 1 / c.z
    const inView = b => b.x < view.x + view.w && b.x + b.w > view.x && b.y < view.y + view.h && b.y + b.h > view.y
    return nearSpot({ x: view.x + view.w / 2, y: view.y + view.h / 2 }, hitPool().map(it => sceneBox(it, textBox)).filter(inView), w, h, { pad: 24 * s, step: 24 * s, view })
  }
  const memoProto = () => { const s = +(1 / R.current.cam.z).toPrecision(2), it = base([0, 0], { type: 'memo', rect: [0, 0, MEMO.W, 40], fill: '#fffff8c5', lines: [{ k: 'p', t: '' }], scale: s, z: topZ(R.current.model.items) + 1 }); return { ...it, rect: [0, 0, MEMO.W, memoHeight(it)] } }
  const tableProto = (rows, cols, header) => base([0, 0], { type: 'table', rows, cols, header, rect: [0, 0, cols * 40, rows * 14], cells: Array.from({ length: rows }, () => Array(cols).fill('')), col_widths: Array(cols).fill(1 / cols), z: topZ(R.current.model.items) + 1 })
  function insertMemo() {
    const m = R.current.model, p0 = memoProto(), s = p0.scale, at = spotNear(p0.rect[2] * s, p0.rect[3] * s), it = { ...p0, pos: [at.x, at.y] }
    commit([...m.items, it], [it._id], '메모'); setTool('select')   // 만들면 고른 채(바로 끌어 옮기기) — 치면 바로 글(2026-10-20 사용자: 도형처럼)
  }
  // 칠판 위 할 일 체크 상자 = 바로 누르기(2026-10-18 사용자: 노션처럼) — 맨 위 메모부터
  function memoLinkHit(p) {   // 맨 위 메모의 그 자리 주소(없으면 null)
    for (let k = R.current.order.length - 1; k >= 0; k--) { const it = R.current.order[k][0]; if (it.type !== 'memo') continue
      const q = toLocal(it, p); if (q.x < it.rect[0] || q.x > it.rect[0] + it.rect[2] || q.y < it.rect[1] || q.y > it.rect[1] + it.rect[3]) continue
      return memoLinkAt(it, q) }
    return null
  }
  const memoCheckAt = p => { const z = R.current.cam.z; for (let k = R.current.order.length - 1; k >= 0; k--) { const it = R.current.order[k][0]; if (it.type !== 'memo' || it.locked) continue
    const q = toLocal(it, p), [x0, y0] = it.rect, pad = 3 / z / (it.scale || 1)
    for (const r of memoLayout(it).rows) if (r.box && q.x >= x0 + r.box.x - pad && q.x <= x0 + r.box.x + r.box.s + pad && q.y >= y0 + r.box.y - pad && q.y <= y0 + r.box.y + r.box.s + pad) return { it, i: r.i } } return null }
  // 메모 「… N줄 더 — 눌러서 펼치기」·「▴ 접기」 줄(render.jsx memoLayout `ln.more`) — 맨 위 메모부터
  const memoMoreAt = p => { for (let k = R.current.order.length - 1; k >= 0; k--) { const it = R.current.order[k][0]; if (it.type !== 'memo' || it.locked) continue
    const q = toLocal(it, p), [x0, y0, w, h] = it.rect; if (q.x < x0 || q.x > x0 + w || q.y < y0 || q.y > y0 + h) continue
    const r = memoLayout(it).rows.find(x => x.ln.more); return r && q.y >= y0 + r.y && q.y <= y0 + r.y + r.lay.h + 2 * TEXT_MARGIN ? { it, more: r.ln.more } : null } return null }
  // ── 메모 2차: 줄 손잡이(⠿) — 끌기 = 줄 순서(다른 메모로도), 메모 밖에 놓기 = 새 메모(칠판으로 꺼내기), 누르기 = 메뉴 ──
  const rowBottom = (rows, k, h) => (rows[k + 1] ? rows[k + 1].y : h - MEMO.PAD)
  function memoRowAt(p, margin = 28, pad = 0) {   // 메모 줄 위(또는 그 왼쪽 손잡이 자리) — 맨 위 메모부터. pad = 위·아래·오른쪽 여유(화면 px)
    const z = R.current.cam.z
    for (let k = R.current.order.length - 1; k >= 0; k--) { const it = R.current.order[k][0]; if (it.type !== 'memo' || it.locked) continue
      const q = toLocal(it, p), [x0, y0, w, h] = it.rect, mg = margin / z / (it.scale || 1), pd = pad / z / (it.scale || 1)
      if (q.x < x0 - mg || q.x > x0 + w + pd || q.y < y0 - pd || q.y > y0 + h + pd) continue
      const rows = memoLayout(it).rows; let r = rows[0]
      for (const row of rows) if (!row.ln.more && q.y >= y0 + row.y) r = row   // 펼치기·접기 줄은 줄이 아님
      const [s, e] = lineUnit(it.lines || [], r.i); return { it, s, e } }
    return null
  }
  function memoHandleRect(it, s) {   // ⠿ 자리(아이템 안 좌표) — 메모 왼쪽 여백 안(글 바로 옆), 화면에서 늘 같은 크기. 많이 줄여 여백보다 커지면 바깥으로
    const k = R.current.cam.z * (it.scale || 1), r = memoLayout(it).rows.find(x => x.i === s) || memoLayout(it).rows[0], w = 16 / k, h = 22 / k
    const x = w + 5 / k <= MEMO.LPAD ? it.rect[0] + MEMO.LPAD - w - 3 / k : it.rect[0] - w - 4 / k
    return { x, y: it.rect[1] + r.cy - h / 2, w, h }
  }
  function memoHandleHit(p) {
    const hv = R.current.memoHov, it = hv && R.current.model.items.find(x => x._id === hv.id); if (!it) return null
    const q = toLocal(it, p), b = memoHandleRect(it, hv.s); return q.x >= b.x && q.x <= b.x + b.w && q.y >= b.y && q.y <= b.y + b.h ? { it, s: hv.s, e: hv.e } : null
  }
  function inMemoGutter(p) {   // ⠿가 뜨는 메모 왼쪽 띠 — 여기선 화살표 뽑기(포트점)를 안 함(손잡이를 조금 빗나가도 화살표가 생기지 않게)
    const hv = R.current.memoHov, it = hv && R.current.model.items.find(x => x._id === hv.id); if (!it) return false
    const q = toLocal(it, p), mg = 28 / R.current.cam.z / (it.scale || 1); return q.x >= it.rect[0] - mg && q.x <= it.rect[0] + MEMO.LPAD && q.y >= it.rect[1] && q.y <= it.rect[1] + it.rect[3]
  }
  // 끌어 놓을 자리 — 메모 위(손잡이 띠·가장자리 여유 포함)면 { id, to(줄 번호), y(안 좌표) }, 확실히 벗어나야 { out: p }(새 메모)
  // 2026-10-18 사용자: 손잡이를 수직으로 내리면 새 메모가 됐음(손잡이가 메모 바깥 띠라 늘 「밖」으로 판정)
  function memoDropAt(p) {
    const hit = memoRowAt(p, 48, 20); if (!hit) return { out: p }
    const it = hit.it, q = toLocal(it, p), rows = memoLayout(it).rows, h = it.rect[3], y0 = it.rect[1]
    for (let k = 0; k < rows.length; k++) { const r = rows[k]; if (r.joinPrev) continue
      if (q.y < y0 + (r.y + rowBottom(rows, k, h)) / 2) return { id: it._id, to: r.i, y: y0 + r.y - MEMO.GAP / 2 } }
    return { id: it._id, to: (it.lines || []).length, y: y0 + h - MEMO.PAD + 2 }
  }
  const withLines = (it, lines) => ({ ...it, lines: lines.length ? lines : [{ k: 'p', t: '' }] })
  function memoLineDrop(s, p) {   // 놓기 — 같은 메모 = 순서, 다른 메모 = 옮겨 넣기, 밖 = 새 메모
    const m = R.current.model, src = m.items.find(x => x._id === s.id); if (!src) return
    const tg = memoDropAt(p)
    const idx = selIdx({ s: s.units[s.units.length - 1][0], e: s.units[s.units.length - 1][1], more: s.units.slice(0, -1) })
    if (tg.id === src._id) { commit(m.items.map(x => (x._id === src._id ? withLines(x, moveLines(x.lines, idx, tg.to, s.copy)) : x)), [src._id], s.copy ? '줄 복사' : '줄 옮김'); return }
    const set = new Set(idx), unit = pickLines(src.lines, idx), rest = s.copy ? src.lines : src.lines.filter((_, i) => !set.has(i))   // Alt = 복사(원래 줄은 둠)
    // 끌어내다 비게 된 메모는 지움(직접 글을 지워 빈 메모는 남김 — 2026-10-18 사용자 선택)
    const gone = !s.copy && rest.every(l => !(l.t || '').trim())
    const srcOut = items => (gone ? items.filter(x => x._id !== src._id) : items.map(x => (x._id === src._id ? withLines(x, rest) : x)))
    if (tg.id) { const dst = m.items.find(x => x._id === tg.id)
      commit(srcOut(m.items.map(x => (x._id === dst._id ? withLines(x, [...x.lines.slice(0, tg.to), ...unit, ...x.lines.slice(tg.to)]) : x))), [dst._id], '줄 옮김'); return }
    const sc = src.scale || 1, it = base([p.x - 24 * sc, p.y - 16 * sc], { type: 'memo', rect: [0, 0, src.rect[2], 40], fill: src.fill, lines: unit, scale: sc, z: topZ(m.items) + 1 })
    const nw = { ...it, rect: [0, 0, src.rect[2], memoHeight(it)] }
    commit([...srcOut(m.items), nw], [nw._id], '칠판으로 꺼냄')
  }
  function lineMenuEntries(lm) {
    const m = R.current.model, it = m.items.find(x => x._id === lm.id); if (!it) return []
    const L = it.lines, us = lm.units, idx = us.flatMap(([a, b]) => Array.from({ length: b - a }, (_, k) => a + k)), on = new Set(idx), cur = L[idx[0]], close = () => setLineMenu(null)
    const kinds = LINE_KINDS.map(([k, name]) => [(cur.k === k ? '✓ ' : '') + name, () => { close(); const mm = R.current.model; commit(mm.items.map(x => (x._id === it._id ? withLines(x, x.lines.map((l, j) => (on.has(j) ? convertLine(l, k) : l))) : x)), [it._id], '줄 전환') }, ''])
    if (lm.kinds) return kinds.map(([n, f]) => [n, '', f])   // Ctrl+/ = 전환 목록만 바로
    const apply = (f, label) => () => { close(); const mm = R.current.model, x0 = mm.items.find(x => x._id === it._id); if (!x0) return; commit(mm.items.map(x => (x._id === it._id ? withLines(x, f(x.lines)) : x)), [it._id], label) }
    const each = f => lines => lines.map((l, j) => (on.has(j) ? f(l) : l)), last = idx[idx.length - 1] + 1
    const sw = (c, txt, bg) => <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}><span style={{ display: 'inline-flex', width: 18, height: 18, alignItems: 'center', justifyContent: 'center', borderRadius: 4, border: '1px solid var(--mb-line)', color: c || 'inherit', background: bg ? cssColor('#ff' + bg.slice(3)) : 'transparent', fontWeight: 600, ...(bg ? { color: '#1f1f1f' } : {}) }}>A</span>{txt}</span>
    return [
      ['전환', 'Ctrl+/', null, kinds],
      ['색', '', null, [...LINE_COLORS.map(([n, c]) => [sw(c, `${n} 텍스트`), apply(each(l => recolorLine(l, { color: c })), '줄 색')]), '-',
        ...LINE_COLORS.map(([n, , b]) => [sw(null, `${n} 배경`, b), apply(each(l => recolorLine(l, { bg: b })), '줄 배경')])]],
      ...(idx.some(i => urlSpans(L[i]?.t).length) ? [(() => { const on2 = idx.some(i => urlSpans(L[i]?.t).length && !L[i].nolink)   // 링크 끄기/켜기(고칠 때 자꾸 열려 불편할 때 — 2026-10-18 사용자)
        return [on2 ? '링크 끄기' : '링크 켜기', '', apply(each(l => (on2 ? { ...l, nolink: true } : (({ nolink, ...r }) => r)(l))), on2 ? '링크 끔' : '링크 켬')] })()] : []),
      ...(idx.length === 1 && cur.k === 'table' ? [['칠판 표로 바꾸기', '', () => {   // 칸 꾸밈·칸 합치기처럼 메모 표 줄이 못 하는 것(2026-10-21) — 메모 오른쪽 옆에, 메모엔 그 줄을 뺌
        close(); const mm = R.current.model, x0 = mm.items.find(x => x._id === it._id); if (!x0) return
        const sc = x0.scale || 1, tb = boardTable(cur.rows, cur.header, sc, topZ(mm.items) + 1), rest = x0.lines.filter((_, j) => j !== idx[0])
        const placed = { ...tb, pos: [x0.pos[0] + (x0.rect[0] + x0.rect[2]) * sc + 24 * sc, x0.pos[1] + x0.rect[1] * sc] }
        commit([...mm.items.map(x => (x._id === it._id ? withLines(x, rest.length ? rest : [{ k: 'p', t: '' }]) : x)), placed], [placed._id], '칠판 표로'); setLineSel(null) }]] : []),
      '-',
      ['복제', 'Ctrl+D', () => { apply(lines => [...lines.slice(0, last), ...idx.map(i => structuredClone(lines[i])), ...lines.slice(last)], '줄 복제')(); setLineSel({ id: it._id, s: last, e: last + idx.length }) }],
      ['삭제', 'Del', () => { apply(lines => lines.filter((_, j) => !on.has(j)), '줄 지움')(); setLineSel(null) }],
    ]   // 「칠판으로 꺼내기」는 뺌(2026-10-18 사용자: 손잡이로 끌어내는 게 더 직관적)
  }
  function finishMemo(lines, extra) {   // extra = { caret }(Esc — 그 줄 고르기) | { grab }(고치는 중 ⠿ — 끝내고 그 줄 끌기·메뉴로)
    const ed = R.current.editing; setEditing(null); if (!ed || !lines) return
    const m = R.current.model, it = m.items.find(x => x._id === ed.id); if (!it) return
    const nol = new Set((it.lines || []).filter(l => l.nolink).map(l => l.t)); lines = lines.map(l => (nol.has(l.t) ? { ...l, nolink: true } : l))   // 고친 뒤에도 「링크 끔」 유지(같은 글의 줄)
    clearTimeout(memoT.current); memoT.current = 0; commit(m.items.map(x => (x._id === it._id ? { ...it, lines } : x)), [it._id], '메모 고침', 'memo' + it._id)
    if (extra?.caret != null && lines[extra.caret]) { const [s, e] = lineUnit(lines, extra.caret); setLineSel({ id: it._id, s, e }) }
    else if (extra?.pick && lines[extra.pick.cur] && lines[extra.pick.clicked]) {   // 고치는 중 단축키 + 다른 줄 클릭 = 줄 고르기
      const [s1, e1] = lineUnit(lines, extra.pick.cur), [s2, e2] = lineUnit(lines, extra.pick.clicked)
      setLineSel(extra.pick.range ? { id: it._id, s: Math.min(s1, s2), e: Math.max(e1, e2) } : s1 === s2 ? { id: it._id, s: s2, e: e2 } : { id: it._id, s: s2, e: e2, more: [[s1, e1]] }) }
    else setLineSel(null)
    if (extra?.grab && lines[extra.grab.i]) { const [s, e] = lineUnit(lines, extra.grab.i), p = toSceneP(extra.grab)
      st.current = { ...st.current, kind: 'mline', id: it._id, units: [[s, e]], copy: false, start: p, moved: false } }
  }
  // 치는 동안 — 높이는 바로(live), 글은 치는 중에도 0.3초마다 칠판에 넣어 저장까지(2026-10-19 사용자: 거의 실시간 — 멈출 때까지 기다리지 않음). 되돌리기는 1.5초 안 이어 친 것끼리 한 칸
  const memoT = useRef(0), memoNext = useRef(null)
  function liveMemo(id, lines) { const m = R.current.model; setLive(m.items.map(x => { if (x._id !== id) return x; const n = { ...x, lines }; return { ...n, rect: [n.rect[0], n.rect[1], n.rect[2], memoHeight(n)] } }))
    memoNext.current = { id, lines }; if (memoT.current) return   // 이미 기다리는 중 = 그때 마지막 글로
    memoT.current = setTimeout(() => { memoT.current = 0; const nx = memoNext.current; if (!nx || R.current.editing?.id !== nx.id) return; const m2 = R.current.model, it = m2.items.find(x => x._id === nx.id); if (!it) return
      const nol = new Set((it.lines || []).filter(l => l.nolink).map(l => l.t)), ls = nx.lines.map(l => (nol.has(l.t) ? { ...l, nolink: true } : l))
      commit(m2.items.map(x => (x._id === nx.id ? { ...it, lines: ls } : x)), R.current.sel, '메모 고침', 'memo' + nx.id) }, 300) }
  function pinCard(msg, drop) {   // drop = 칠판 좌표(끌어 놓은 자리 — 왼쪽 위), 없으면 빈자리
    const m = R.current.model, c = R.current.cam, b0 = unionBox(cardItems(msg, 0, 0, 0).map(it => sceneBox(it, textBox))), h = b0.h, W = b0.w
    const left = 24 / c.z, right = (24 + rightInset(svg.current)) / c.z, top = 48 / c.z   // 위 48px = 감싸도 프레임 이름표가 칠판 밖으로 안 나감(2026-10-19 점검)
    const view = { x: -c.x / c.z + left, y: -c.y / c.z + top, w: Math.max(W, size.w / c.z - left - right), h: size.h / c.z - top }
    const boxes = m.items.map(it => sceneBox(it, textBox))
    const at = drop || freeSpot(view, boxes, W, h)
    const its = cardItems(msg, at.x, at.y, topZ(m.items) + 1)
    commit([...m.items, ...its], its.map(it => it._id), '칠판에 붙이기')
    // 화면 밖으로 나간 만큼만 화면을 옮김(배율 그대로) — 붙였는데 안 보여 아무 일도 없던 것 같았음(2026-10-19 점검). 가운데로 옮기면 옆 메모가 왼쪽 카드 밑으로 갔음
    if (!drop) {
      const nb = unionBox(its.map(it => sceneBox(it, textBox))), vx = -c.x / c.z + left, vy = -c.y / c.z + top, vw = (size.w - rightInset(svg.current)) / c.z - left, vh = size.h / c.z - top, pad = 20 / c.z
      const need = (a, len, v0, vlen) => (len > vlen || a < v0 ? v0 + pad - a : a + len > v0 + vlen ? v0 + vlen - pad - (a + len) : 0)   // 넘치면 앞(왼쪽·위)부터
      const dx = need(nb.x, nb.w, vx, vw), dy = need(nb.y, nb.h, vy, vh)
      if (dx || dy) setCam({ z: c.z, x: c.x + dx * c.z, y: c.y + dy * c.z })   // need = 묶음이 화면에서 옮겨 보여야 할 칠판 거리
    }
    return its.map(it => it._id)   // 고른 채로 둠(어디 붙었나 보이게) — 대화창은 이 고름을 다음 질문에 싣지 않음(chat.jsx `skipSel`)
  }
  // 이미 붙인 카드로 — 고르고 화면 가운데로. 없으면(지웠으면) false
  function showCard(at) {
    const b = R.current.model.items.find(it => it.chat_at === at)
    return b ? showItem(b._id) : false
  }
  // 정리 문서(「정리해 줘」 ①) — 크게 보기 = 새 탭에 그 HTML(인쇄·PDF는 그 탭에서 Ctrl+P), 카드 = A4 비율(폭 397 = 문서 폭 794의 절반)
  function openDoc(it) { const u = URL.createObjectURL(new Blob([bigPage(it)], { type: 'text/html;charset=utf-8' })); window.open(u, '_blank'); setTimeout(() => URL.revokeObjectURL(u), 60_000) }
  const DOC_W = 397
  const LIVE_DOC_W = 480   // 움직이는 카드(§8 항목66 4단계) — 기준 칸 720×480을 2/3로(높이 = 띠 + 같은 비율)
  function docItem(msg, x, y, z) {
    if (msg.live || msg.kind === 'live') return base([x, y], { type: 'doc', live: true, rect: [0, 0, LIVE_DOC_W, WEB_HEAD + Math.round(LIVE_DOC_W * LIVE_H / LIVE_W)], title: msg.title || '인터랙티브 HTML', html: msg.html, model: msg.model || '', chat_at: msg.at, z })
    return base([x, y], { type: 'doc', rect: [0, 0, DOC_W, WEB_HEAD + Math.round(DOC_W * 1.414)], title: msg.title || '정리 문서', html: msg.html, model: msg.model || '', chat_at: msg.at, z })
  }
  // 「칠판에서」 답(§8 항목61 ③-2) = 메모 + 근거가 된 칠판 도형으로 가는 점선 화살표(메모 쪽 변 → 근거 쪽 변, 가까운 포트끼리). 근거 도형은 제자리 그대로 — 메모와 화살표만 한 묶음
  function boardRefItems(memo, refs, z) {
    const items = R.current.model.items, hosts = refs.map(r => items.find(it => it._id === r.uid)).filter(it => it && isConnHost(it))
    if (!hosts.length) return [memo]
    const g = 'g' + newId(), keep = R.current.model, mb = sceneBox(memo, textBox), mc = { x: mb.x + mb.w / 2, y: mb.y + mb.h / 2 }
    const near = (it, q) => hostPorts(it, rectOf).reduce((a, p) => (Math.hypot(p.p.x - q.x, p.p.y - q.y) < Math.hypot(a.p.x - q.x, a.p.y - q.y) ? p : a))
    R.current.model = { ...keep, items: [...keep.items, memo] }
    try {
      const arrows = hosts.map(h => {
        const hb = sceneBox(h, textBox), hc = { x: hb.x + hb.w / 2, y: hb.y + hb.h / 2 }, a = near(memo, hc), t0 = near(h, mc), t = { id: h._id, p: t0.p, n: t0.n }
        const pts = connRoute(memo._id, { p: a.p, n: a.n }, t, null).map(q => [q.x, q.y])
        return { ...arrowItem(memo._id, a.p, h._id, t.p, { auto_route: true, pts, color: '#fff59e0b', width: 1, style: 2, head: true, head_start: false }), z, group_id: g }
      })
      return [{ ...memo, group_id: g }, ...arrows]
    } finally { R.current.model = keep }
  }
  // 도형 하나로 가기 — 고르고 화면 가운데로(뜬 대화창 밑은 빼고), 너무 작게 보이면 읽을 만큼 키움(찾기·「칠판에서」 고리, 2026-10-19). 없으면 false
  function showItem(id) {
    const b = R.current.model.items.find(it => it._id === id); if (!b) return false
    const s = sceneBox(b, textBox), W = size.w - rightInset(svg.current); setSel([id])
    setCam(cc => { const z = s.w * cc.z < 120 ? Math.min(1, (W * 0.4) / Math.max(s.w, 1)) : cc.z; return { z, x: W / 2 - (s.x + s.w / 2) * z, y: size.h / 2 - (s.y + s.h / 2) * z } })
    return true
  }
  // ── 프레임(2026-10-18 사용자와 정함 — 「종이틀」을 바꿈: 종이 비율은 큰 의미 없음) — 번호 = 출력 쪽·슬라이드 순서 ──
  const nextFrameNo = items => orderedFrames(items).length + 1   // 새 프레임 = 맨 끝
  function reorderFrames(ids) { const m = R.current.model; commit(setFrameOrder(m.items, ids), R.current.sel, '프레임 순서') }
  function renameFrame(id, name) { const m = R.current.model; commit(m.items.map(it => (it._id === id ? { ...it, name } : it)), R.current.sel, '프레임 이름', 'fname' + id) }   // 치는 대로 — 되돌리기는 한 칸
  function goFrame(id) {   // 그 프레임이 화면에 꽉 차게(여백 10%)
    const it = R.current.model.items.find(x => x._id === id); if (!it) return
    const W = size.w - rightInset(svg.current), b = sceneBox(it, textBox), z = Math.min(4, Math.max(0.05, Math.min(W / (b.w * 1.2), size.h / (b.h * 1.3))))
    setSel([id]); setCam({ z, x: W / 2 - (b.x + b.w / 2) * z, y: size.h / 2 - (b.y + b.h / 2) * z })
  }
  // 감싸기: 고른 것을 여백 두고 감싸는 프레임(자유 비율)
  function wrapFrame() {
    const m = R.current.model, ids = new Set(withContents(R.current.sel)), its = m.items.filter(it => ids.has(it._id) && it.type !== 'titleblock' && it.type !== 'frame'); if (!its.length) return
    const b = unionBox(its.map(it => sceneBox(it, textBox))), pad = 16   // 작고 일정한 여백(2026-10-18 사용자 선택 — 전엔 내용의 6%라 큰 묶음일수록 여백이 컸음)
    const it = base([b.x - pad, b.y - pad], { type: 'frame', rect: [0, 0, b.w + 2 * pad, b.h + 2 * pad], name: '', no: nextFrameNo(m.items), z: Math.min(0, ...m.items.map(x => x.z ?? 0)) - 1 })
    commit([...m.items, it], [it._id], '프레임으로 감싸기'); setStatus(`프레임 ${it.no} — 내보내기 하면 이 틀이 한 쪽이 돼요`)
  }

  function insertTable(rows, cols, header) {
    const m = R.current.model, p0 = tableProto(rows, cols, header), at = spotNear(p0.rect[2], p0.rect[3]), it = { ...p0, pos: [at.x, at.y] }
    commit([...m.items, it], [it._id], '표'); setTool('select')
    setStatus(`표 넣음: ${rows}×${cols} — 칸을 두 번 눌러 고치기(Enter 아래·Tab 오른쪽)`)
  }
  const chartMode = it => isChart(it) && R.current.editing?.id !== it._id && cellSel?.id !== it._id   // 그래프로 보이는 중(칸 고르기 없음)
  // 표 칸(안 좌표) — 데스크톱 `cell_rect`/`cell_at`
  const cellRect = (it, r, c) => { const [x, y, w, h] = it.rect, re = rowEdges(y, h, it), e = colEdges(x, w, colFracs(it)); return { x: e[c], y: re[r], w: e[c + 1] - e[c], h: re[r + 1] - re[r] } }
  const cellAt = (it, q) => { const [x, y, w, h] = it.rect; if (q.x < x || q.y < y || q.x > x + w || q.y > y + h) return null
    const e = colEdges(x, w, it.col_widths || Array(it.cols).fill(1 / it.cols)); let c = e.findIndex((v, i) => i > 0 && q.x <= v) - 1; if (c < 0) c = it.cols - 1
    const re = rowEdges(y, h, it); let r = re.findIndex((v, i) => i > 0 && q.y <= v) - 1; if (r < 0) r = it.rows - 1
    return { r, c } }
  // 칸 고치기 끝 — text = 새 글(null = 취소), move = [dr, dc] 다음 칸으로(데스크톱 `_CellEditor._move`: Tab 줄넘김)
  function finishCell(text, move, runs) {
    const ed = R.current.editing; if (!ed || ed.kind !== 'cell') return
    const m = R.current.model, it0 = m.items.find(x => x._id === ed.id)
    let it = it0
    // 다음 칸은 같은 순간에 열어야 함 — 한 박자 늦게 열면 Tab 뒤 바로 친 글자가 사라짐(시험에서 겪음)
    let next = null
    if (it && move) { let r = ed.r + move[0], c = ed.c + move[1]; while (c >= it.cols) { c -= it.cols; r++ } while (c < 0) { c += it.cols; r-- }
      if (r === it.rows && move[1] === 1) it = tableOp(it, 'rowBelow', it.rows - 1, 0)   // 마지막 칸에서 Tab = 새 행(엑셀·한글 방식)
      if (r >= 0 && r < it.rows) next = { id: it._id, kind: 'cell', r, c } }
    setEditing(next); R.current.editing = next; if (!it) return null   // 다시 그리기를 기다리지 않음
    if (!next) setCellSel({ id: it._id, r0: ed.r, c0: ed.c, r1: ed.r, c1: ed.c })   // 끝내면 그 칸을 고른 채로(엑셀 — 이어서 치거나 화살표로)
    const key = `${ed.r},${ed.c}`, oldRuns = JSON.stringify(it0.cell_runs?.[key] || [])
    const changed = text != null && (text !== (it0.cells?.[ed.r]?.[ed.c] || '') || JSON.stringify(runs || []) !== oldRuns)
    if (changed || it !== it0) {
      const cells = Array.from({ length: it.rows }, (_, r) => Array.from({ length: it.cols }, (_, c) => it.cells?.[r]?.[c] || ''))
      let cr = it.cell_runs
      if (changed) { cells[ed.r][ed.c] = text; cr = { ...(it.cell_runs || {}) }; if (runs?.length) cr[key] = runs; else delete cr[key] }   // 칸 부분 서식(.ecad 표 `cell_runs` — 웹 먼저)
      commit(m.items.map(x => (x._id === it._id ? { ...it, cells, ...(cr && Object.keys(cr).length ? { cell_runs: cr } : { cell_runs: undefined }) } : x)), [it._id], it !== it0 ? '표 행 넣기' : '표 칸')
    }
    if (!next) return null
    const nt = R.current.model.items.find(x => x._id === it._id) || it   // 다음 칸 내용 — 편집기가 바로 바꿔 끼움
    return { key: `${next.r},${next.c}`, text: nt.cells?.[next.r]?.[next.c] || '', runs: nt.cell_runs?.[`${next.r},${next.c}`] }
  }
  // given = 끌어 놓을 아이템(대화창 카드), onPlaced = 놓았을 때 알림
  // 위 막대 도구를 칠판으로 끌기 = 기본형을 놓은 자리에(2026-10-20 사용자). 선·화살표 = 화면 기준 길이의 가로, 다각형 = 첫 선분 놓고 이어 찍기,
  // 펜은 끌기 없음(놓아도 도구만 바뀌어 누르기와 같았음 — 2026-10-20 사용자), 글자 = 빈 글 상자로 바로 쓰기, 번호 = 다음 번호, 메모·표·프레임 = 기본 크기, 웹 = 놓은 자리로 주소 묻기
  function startToolDrag(kind, { table = [3, 3, true], onWeb } = {}) {
    const m = R.current.model, z = R.current.cam.z, L = 120 / z, top = topZ(m.items) + 1
    const seg = extra => base([0, 0], { type: 'polygon', closed: false, rect: [0, 0, L, 0], pts: [[0, 0], [L, 0]], ...penOf(false), fill: null, z: top, ...extra })
    if (kind === 'polygon') return startPaletteDrag(kind, [seg()], (its, p) => { const a = { x: p.x - L / 2, y: p.y }, b = { x: p.x + L / 2, y: p.y }; keepPoly.current = R.current.tool !== 'polygon'; setTool('polygon'); setOverlay(o => ({ ...o, poly: [a, b], pcur: b })) }, true)
    // 글자 = 끄는 동안만 「글」 미리보기, 놓으면 빈 글 상자에 커서 — 빈 곳 두 번 누르기와 같음(안 쓰면 지워짐, 2026-10-20 사용자: 「글」이 남을 필요 없음)
    if (kind === 'text') return startPaletteDrag(kind, [base([0, 0], { type: 'text', text: '글', color: INK, font: 12, bg: null, z: top })], its => { setTool('select'); newTextAt({ x: its[0].pos[0] + TEXT_MARGIN, y: its[0].pos[1] + TEXT_MARGIN }) }, true)
    if (kind === 'web') return startPaletteDrag(kind, [base([0, 0], { type: 'rect', rect: [0, 0, 320 / z, 180 / z], pen: '#ff9aa0a6', width: 1, style: 2, fill: null, z: top })], (its, p) => onWeb?.(p), true)
    let proto, after = null
    if (kind === 'line') proto = base([0, 0], { type: 'line', line: [0, 0, L, 0], ...penOf(false), z: top })
    else if (kind === 'arrow') { proto = arrowItem(null, { x: 0, y: 0 }, null, { x: L, y: 0 }, { auto_route: false, pts: [[0, 0], [L, 0]] }); if (stickyKind.current !== 'ortho') proto = swapArrowKind(proto, stickyKind.current, m.items, rectOf, sticky.current.curve_r) }
    else if (kind === 'badge') proto = base([0, 0], { type: 'badge', number: nextBadge(m.items), color: sticky.current.color === INK ? '#ffda7756' : sticky.current.color, z: top })
    else if (kind === 'memo') proto = memoProto()
    else if (kind === 'table') proto = tableProto(...table)
    else if (kind === 'frame') { const w = size.w * 0.4 / z; proto = base([0, 0], { type: 'frame', rect: [0, 0, w, w * 9 / 16], name: '', no: nextFrameNo(m.items), ratio: '16:9', z: Math.min(0, ...m.items.map(x => x.z ?? 0)) - 1 }) }
    if (!proto) return
    startPaletteDrag(kind, [proto], ids => { setTool('select'); after?.(ids) })
  }
  function startPaletteDrag(t, given, onPlaced, dry) {   // dry = 놓을 자리만 알림(칠판에 넣지 않음 — 위 막대 다각형·펜·웹: onPlaced(its, 놓은 점))
    const m = R.current.model
    const protos = given || (t.startsWith('customsym:') ? customItems(t) : [{ ...boxItem(t, 0, 0, ...boxDefault(t)), z: topZ(m.items) + 1 }])   // 클릭만 해 놓을 때와 같은 기본 크기
    if (!protos) return
    const b0 = unionBox(protos.map(it => sceneBox(it, textBox))), w = b0.w, h = b0.h
    const others = m.items.filter(it => !it.locked).map(it => sceneBox(it, textBox))
    let last = null
    const place = e => {
      const el = document.elementFromPoint(e.clientX, e.clientY), over = !!el && (el === svg.current || svg.current.contains(el))
      const p = toSceneP(e), a = alignSnap({ x: p.x - w / 2, y: p.y - h / 2, w, h }, others, R.current.cam.z)
      return { over, its: placeAt(protos, p.x - w / 2 + a.dx, p.y - h / 2 + a.dy), guides: a.guides }
    }
    // 답 메모를 다른 메모 위에 놓으면 그 메모 안 그 자리에 줄로(2026-10-18 사용자: 한 번 칠판에 놓고 다시 옮겨야 했음)
    const memoIn = !!given && protos.length === 1 && protos[0].type === 'memo' && !!protos[0].lines?.some(l => l.t)   // 빈 새 메모(위 막대에서 끌기)는 메모 안으로 안 들어감
    const intoMemo = e => { if (!memoIn) return null; const el = document.elementFromPoint(e.clientX, e.clientY); if (!el || !(el === svg.current || svg.current.contains(el))) return null; const tg = memoDropAt(toSceneP(e)); return tg.id ? tg : null }
    const move = e => { const tg = intoMemo(e); if (tg) { setLive(null); setOverlay(o => ({ ...o, guides: null, mdrop: tg })); return }
      last = place(e); setLive(last.over ? [...m.items, ...last.its] : null); setOverlay(o => ({ ...o, mdrop: null, guides: last.over ? last.guides : null })) }
    const up = e => {
      window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); document.body.style.cursor = ''; st.current = { space: st.current.space }
      setOverlay(o => ({ ...o, guides: null, mdrop: null }))
      const tg = intoMemo(e)
      if (tg) { setLive(null); const add = structuredClone(protos[0].lines || [])
        commit(m.items.map(x => (x._id === tg.id ? { ...x, lines: [...x.lines.slice(0, tg.to), ...add, ...x.lines.slice(tg.to)] } : x)), [tg.id], '메모에 붙이기'); onPlaced?.([tg.id]); return }
      last = place(e)
      if (dry) { setLive(null); if (last.over) { const b = unionBox(last.its.map(it => sceneBox(it, textBox))); onPlaced?.(last.its, { x: b.x + b.w / 2, y: b.y + b.h / 2 }) } return }   // 놓은 점 = 정렬선에 맞춘 기본형의 가운데
      if (last.over) { commit([...m.items, ...last.its], last.its.map(it => it._id), given ? '칠판에 붙이기' : '도형'); onPlaced?.(last.its.map(it => it._id)) } else setLive(null)
    }
    document.body.style.cursor = 'copy'; st.current = { ...st.current, kind: 'pdrag' }; setHp(null)   // 끄는 동안 포트점 예고 끔(데스크톱도 드래그 중 억제)
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', up)
  }

  // ── 그리기 ──
  function startDraw(t, p, e) {
    const m = R.current.model
    if (t === 'arrow') {   // 화살표 도구(데스크톱 「화살표」 — 종류는 속성 카드): 시작이 도형 근처면 붙고, 빈 곳이면 떠 있는 끝. 끄는 건 큐닷·포트점 잇기와 같은 길
      const snap = snapAt(hostsNear(p), p, R.current.cam.z, rectOf, linesNear(p))
      // 도형 '안'에서 시작 = 그 도형에 붙음(끝을 도형 안에 놓으면 붙는 것과 같게 — 2026-10-19 다잡기). 어느 변인지는 끄는 쪽으로(arrowStart)
      const inside = snap ? null : dropTarget(hostsNear(p), p, R.current.cam.z, rectOf, null, [])?.id ?? null
      st.current = { ...st.current, kind: 'conn', tool: 'arrow', src: snap?.id ?? null, port: snap ? { p: snap.p, n: snap.n } : { p, n: null }, inside, start: p, cur: p, fromQc: false, moved: false }
      return
    }
    if (t === 'text') { newTextAt(p); setTool('select'); return }
    if (t === 'badge') {   // 번호표 — 누른 자리에 다음 번호(남은 가장 큰 번호 + 1 — `nextBadge`), 색 = 고른 선 색
      const n = nextBadge(m.items)
      const it = base([p.x, p.y], { type: 'badge', number: n, color: sticky.current.color === INK ? '#ffda7756' : sticky.current.color, z: topZ(m.items) + 1 })   // 선 색을 안 골랐으면 코랄(기본 잉크로 칠하면 어두운 화면에서 묻힘)
      commit([...m.items, it], [it._id], '번호표'); return   // 도구는 켜 둔 채 — 누를 때마다 다음 번호, Esc·다른 도구로 끝(2026-10-18 사용자 선택, 데스크톱은 한 번 찍고 돌아감)
    }
    if (t.startsWith('customsym:')) {   // 내 심볼 도구 — 누른 자리에 원래 크기로(데스크톱 `_create_custom_symbol_at`: 왼쪽 위 = 누른 자리)
      const protos = customItems(t); if (!protos) return
      const its = placeAt(protos, p.x, p.y); commit([...m.items, ...its], its.map(it => it._id), '심볼'); setTool('select'); return
    }
    if (t === 'polygon') {
      const poly = overlay.poly || []
      if (polyCloseAt(poly, p)) return finishPoly(poly, true)
      const q = e?.shiftKey && poly.length ? snap45(poly.at(-1), p) : p
      setOverlay(o => ({ ...o, poly: [...poly, q], pcur: q })); return
    }
    if (t === 'line' && overlay.lpt) {   // 클릭 배치 선의 둘째 클릭 = 확정(데스크톱 `_finish_place`)
      const a = overlay.lpt, b = e?.shiftKey ? snap45(a, p) : p
      if (Math.hypot(b.x - a.x, b.y - a.y) * R.current.cam.z < 3) return   // 같은 자리 두 번(더블클릭) = 아직 안 끝냄
      setOverlay(o => ({ ...o, lpt: null, pcur: null }))
      const it = base([0, 0], { type: 'line', line: [a.x, a.y, b.x, b.y], ...penOf(false), z: topZ(m.items) + 1 })
      commit([...m.items, it], [it._id], '그림'); setTool('select'); return
    }
    st.current ={ ...st.current, kind: 'draw', tool: t, start: p, cur: p, pts: [p] }
  }
  function newTextAt(p) { const m = R.current.model, it = base([p.x - TEXT_MARGIN, p.y - TEXT_MARGIN], { type: 'text', text: '', color: INK, font: 12, bg: null, z: topZ(m.items) + 1 }); commit([...m.items, it], [it._id], '글'); setEditing({ id: it._id, kind: 'text', fresh: true }) }
  // 다각형 닫기 자석 — 점 3개 이상이고 커서가 시작점 12px 안(데스크톱 `_POLY_CLOSE_PX`·`_polygon_place_point`: 따라오는 선이 시작점에 붙고 표시가 뜸)
  const polyCloseAt = (poly, p) => R.current.tool === 'polygon' && poly?.length >= 3 && Math.hypot(p.x - poly[0].x, p.y - poly[0].y) * R.current.cam.z <= 12
  function finishPoly(pts, closed) {
    setOverlay(o => ({ ...o, poly: null, pcur: null }))
    if (pts.length < 2) return
    const xs = pts.map(q => q.x), ys = pts.map(q => q.y), x0 = Math.min(...xs), y0 = Math.min(...ys)
    const it = base([x0, y0], { type: 'polygon', closed, rect: [0, 0, Math.max(...xs) - x0, Math.max(...ys) - y0], pts: pts.map(q => [q.x - x0, q.y - y0]), ...penOf(closed), ...(closed ? {} : { fill: null }), z: topZ(R.current.model.items) + 1 })
    commit([...R.current.model.items, it], [it._id], '다각형'); setTool('select')
  }
  function finishDraw(s, p) {
    setOverlay(o => ({ ...o, draw: null }))
    const m = R.current.model, z = R.current.cam.z, click = Math.hypot(p.x - s.start.x, p.y - s.start.y) * z < 3
    let it
    if (s.tool === 'frame') {   // 프레임 — 드래그로 감싼 영역(2026-10-18 사용자: 「클릭하고 원하는 영역을 감싸게 드래그」), 클릭만 = 화면 40% 16:9. 맨 뒤
      let x0 = Math.min(s.start.x, p.x), y0 = Math.min(s.start.y, p.y), w = Math.abs(p.x - s.start.x), h = Math.abs(p.y - s.start.y)
      if (click) { w = size.w * 0.4 / z; h = w * 9 / 16; x0 = p.x - w / 2; y0 = p.y - h / 2 }
      it = base([x0, y0], { type: 'frame', rect: [0, 0, w, h], name: '', no: nextFrameNo(m.items), ...(click ? { ratio: '16:9' } : {}), z: Math.min(0, ...m.items.map(x => x.z ?? 0)) - 1 })
      commit([...m.items, it], [it._id], '프레임'); setTool('select'); return
    }
    if (s.tool === 'rect' || s.tool === 'ellipse' || s.tool.startsWith('sym:')) {
      let x0 = Math.min(s.start.x, p.x), y0 = Math.min(s.start.y, p.y), w = Math.abs(p.x - s.start.x), h = Math.abs(p.y - s.start.y)
      if (s.shift) { const d = Math.max(w, h); w = h = d; x0 = p.x < s.start.x ? s.start.x - d : s.start.x; y0 = p.y < s.start.y ? s.start.y - d : s.start.y }
      if (click) { [w, h] = boxDefault(s.tool); x0 = p.x - w / 2; y0 = p.y - h / 2 }   // 클릭만 = 기본 크기로 그 자리에
      it = boxItem(s.tool, x0, y0, w, h)
    } else if (s.tool === 'line') {
      if (click) { setOverlay(o => ({ ...o, lpt: s.start, pcur: p })); return }   // 클릭만 = 클릭 두 번으로 긋기(데스크톱 클릭 배치 — 선이 커서를 따라옴)
      const { x, y } = s.shift ? snap45(s.start, p) : p
      it = base([0, 0], { type: 'line', line: [s.start.x, s.start.y, x, y], ...penOf(false) })
    } else if (s.tool === 'pen') {
      if (s.pts.length < 2) return
      it = base([0, 0], { type: 'path', elements: s.pts.map((q, i) => [i ? 'L' : 'M', q.x, q.y]), ...penOf(false), freehand: true })
    }
    if (!it) return
    it.z = topZ(m.items) + 1
    commit([...m.items, it], [it._id], '그림'); setTool('select')
  }

  // 남이 고치는 도형 — 바로 열지 않고 한 번 더 묻기(창 없이 알림 줄 · 5초 안에 다시 두 번 누르면 열림, 2026-10-19 사용자: 덮어쓰기 막기)
  const lockAsk = useRef(null)
  function guardEdit(id) {
    const who = R.current.others?.find(o => o.edit === id); if (!who) return true
    const a = lockAsk.current; if (a && a.id === id && Date.now() - a.t < 5000) { lockAsk.current = null; return true }
    lockAsk.current = { id, t: Date.now() }; setStatus(`${who.name}님이 고치는 중 — 한 번 더 두 번 누르면 열려요`); return false   // 짧게(긴 알림은 위 막대를 두 줄로 늘려 칠판을 밀었음)
  }
  // ── 두 번 누르기 = 글 편집(글 상자) / 도형 라벨 ──
  function onDoubleClick(e) {
    if (readOnly) return
    if (R.current.tool === 'polygon') { finishPoly(overlay.poly || [], false); return }
    if (R.current.tool !== 'select') return   // 그리는 도구 중 두 번 누르기 = 그 도구의 클릭 두 번(선 긋기 등)
    const p = toSceneP(e), lb = labelAt(p)
    const at = { x: e.clientX, y: e.clientY }   // 두 번 누른 자리에 커서(2026-10-18 사용자: 한 번 더 눌러야 했음)
    if (lb) { if (!guardEdit(lb.it._id)) return; setSel([lb.it._id]); setEditing({ id: lb.it._id, kind: 'alabel', i: lb.i, at }); return }
    const hit = topHit(hitPool(), p, HIT_PX / R.current.cam.z, textBox)
    if (!hit) { newTextAt(p); return }   // 빈 곳 두 번 누르기 = 그 자리에 글(2026-10-20 사용자 — 아무것도 안 쓰고 나오면 빈 글은 지워짐)
    if (hit.type === 'doc') { setSel([hit._id]); if (liveFits(hit)) webActivate(hit); else openDoc(hit); return }   // 정리 문서 두 번 누르기 = 크게 보기(고치기는 대화창에 말로), 움직이는 카드 = 칸 안 조작
    if (hit.type !== 'web' && hit.type !== 'pdf' && !guardEdit(hit._id)) return
    if (hit.type === 'frame') { const b = frameTagBox(hit); if (p.y <= b.y + b.h + 2 / R.current.cam.z) { setSel([hit._id]); setTagEdit(hit._id) } return }   // 이름표 = 그 자리에서 이름 고치기
    if (hit.type === 'memo') { setSel([hit._id]); setEditing({ id: hit._id, kind: 'memo', at }); return }
    if (hit.type === 'web') { setSel([hit._id]); if (hit.frameable) webActivate(hit); else window.open(hit.url, '_blank', 'noopener'); return }   // 막는 사이트 = 새 탭
    if (hit.type === 'pdf') { webActivate(hit); return }   // PDF 카드 두 번 누르기 = 넘겨 보기
    if (hit.type === 'table' && chartMode(hit)) { const r = Math.min(1, hit.rows - 1), c = Math.min(1, hit.cols - 1); setSel([hit._id]); setCellSel({ id: hit._id, r0: r, c0: c, r1: r, c1: c }); setEditing({ id: hit._id, kind: 'cell', r, c, at }); return }   // 그래프 두 번 누르기 = 표로 펼쳐 첫 숫자 칸부터
    if (hit.type === 'table') { const cell = cellAt(hit, toLocal(hit, p)); if (cell) { setSel([hit._id]); setEditing({ id: hit._id, kind: 'cell', ...cell, at }) } return }
    if (isArrow(hit)) {   // 화살표 빈 자리 더블클릭 = 그 자리에 새 라벨(여러 개 — 데스크톱 `add_label_at_scene_pos`)
      const labels = labelsOf(hit), pr = projectOn(hit, toLocal(hit, p))
      labels.push({ text: '', color: hit.color || INK, font: 16, bg: null, t: pr.t, off: 0 })
      commit(R.current.model.items.map(x => (x._id === hit._id ? withLabels(hit, labels) : x)), [hit._id], '라벨')
      setEditing({ id: hit._id, kind: 'alabel', i: labels.length - 1, fresh: true }); return
    }
    if (hit.type === 'text') { setSel([hit._id]); setEditing({ id: hit._id, kind: 'text', at }) }
    else if (['rect', 'ellipse', 'symbol'].includes(hit.type) || (hit.type === 'polygon' && hit.closed)) { setSel([hit._id]); setEditing({ id: hit._id, kind: 'label', at }) }
  }
  // 고치는 동안 글에 맞춘 상자 높이를 바로(미리보기 — 끝낼 때 commit이 같은 값으로 확정)
  function liveLabel(id, { text, runs }) {
    const m = R.current.model
    setLive(m.items.map(x => { if (x._id !== id) return x; const n = { ...x, label: { ...x.label, text, runs } }; return { ...n, rect: [n.rect[0], n.rect[1], n.rect[2], fitTextHeight(n)] } }))
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
  // 도형 하나를 고른 채 = 보이지 않는 편집기 대기(표 칸과 같은 방식 — 2026-10-19 사용자: 고르고 바로 치면 글, 기존 글은 새로 씀·숫자·대문자도 글로)
  function armTarget() {
    const ids = R.current.sel; if (readOnly || R.current.editing || cellSel || R.current.tool !== 'select' || ids.length !== 1) return null
    const it = R.current.model.items.find(x => x._id === ids[0]); if (!it || it.locked || R.current.others?.some(o => o.edit === it._id)) return null   // 남이 고치는 중이면 두 번 누르기(부드러운 잠금)로만
    const kind = it.type === 'text' ? 'text' : ['rect', 'ellipse', 'symbol'].includes(it.type) || (it.type === 'polygon' && it.closed) ? 'label' : it.type === 'memo' && !R.current.lineSel ? 'memo' : null   // 메모 = 치면 끝에 이어 씀(있는 글을 지우지 않음 — 도형 글은 새로 씀)
    return kind && { id: it._id, kind, armed: true }
  }
  function editSpec(ed = editing) {
    const it = ed && byId.get(ed.id); if (!it) return null
    const ob = onBoard[items.indexOf(it)], col = c => ink(c || '#ff1f1f1f', ob), bg = ob ? 'rgba(255,255,255,.9)' : 'var(--mb-editbg)'   // 글 고치는 칸도 칠판과 같은 잉크·바탕
    if (ed.kind === 'text') {
      const o = scr(toScene(it, { x: 0, y: 0 }))
      return { left: o.x, top: o.y, px: (it.font || 12) * PT * (it.scale || 1), zoom: cam.z, family: it.family ? 'board' : 'app', weight: it.weight ?? (it.bold ? 700 : 400),
        color: col(it.color), bg, rotation: it.rotation || 0, origin: scr(toScene(it, { x: it.origin?.[0] || 0, y: it.origin?.[1] || 0 })), text: it.text, runs: it.runs }
    }
    if (ed.kind === 'alabel') {
      const b = arrowLabelBoxes(it)[ed.i], L = labelsOf(it)[ed.i]; if (!b || !L) return null
      return { center: scr(toScene(it, b.a)), px: (L.font || 16) * PT * (it.scale || 1), zoom: cam.z, family: L.family ? 'board' : 'app', weight: 400, color: col(L.color || it.color), bg, align: 'center', text: L.text || '', runs: L.runs }
    }
    const L = it.label || {}
    if (L.align === 'left') {   // 왼쪽 위·상자 폭에서 줄바꿈 — 그릴 때와 같은 자리·폭
      const [x, y, w] = it.rect, o = scr(toScene(it, { x: x + LABEL_PAD, y: y + LABEL_PAD })), s = it.scale || 1
      return { left: o.x, top: o.y, width: (w - 2 * LABEL_PAD) * s * cam.z, px: (L.font || 16) * PT * s, zoom: cam.z, family: L.family ? 'board' : 'app', weight: 400, color: ink(L.color || it.pen || '#ff1f1f1f', ob || !!it.fill), bg: 'transparent', flat: true, align: 'left',   // 채운 상자 안 글 = 화면 밝기와 상관없이 제 색(그릴 때와 같게)
        onChange: it.fit_text ? (t => liveLabel(it._id, t)) : undefined,   // 고치는 모습 = 결과(2026-10-18 사용자: 끝낼 때 한 번에 늘어나면 예측이 어려움)
        rotation: it.rotation || 0, origin: scr(toScene(it, { x: it.origin?.[0] || 0, y: it.origin?.[1] || 0 })), text: L.text || '', runs: L.runs }
    }
    const a = scr(toScene(it, labelAnchor(it.type, it.kind, it.rect)))
    return { center: a, px: (L.font || 16) * PT * (it.scale || 1), zoom: cam.z, family: L.family ? 'board' : 'app', weight: 400, color: col(L.color || it.pen), bg, align: 'center', text: L.text || '', runs: L.runs }
  }

  // ── 글쇠 ──
  useEffect(() => {
    const onKey = e => {
      if (readOnly || R.current.editing || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '')) return
      const m = R.current.model, ids = R.current.sel, mod = e.ctrlKey || e.metaKey, k = e.key
      if (k === ' ') { st.current.space = true; if (armTarget()) e.preventDefault(); return }   // Space+끌기 = 화면 이동 — 대기 편집기에 빈칸이 들어가 고치기로 바뀌지 않게
      const act = (f, label) => { e.preventDefault(); f(label) }
      const pdfOn = R.current.webOn && m.items.find(it => it._id === R.current.webOn && it.type === 'pdf'), pbox = pdfOn && document.querySelector(`[data-pdfid="${pdfOn._id}"]`)
      if (pbox && k === 'Escape' && !R.current.menuOpen) return act(() => setWebOn(null))   // Esc = 넘겨 보기 끝(보던 쪽 그대로, 카드는 고른 채)
      if (k === 'Escape' && !R.current.menuOpen && R.current.webOn && m.items.some(it => it._id === R.current.webOn && it.type === 'doc')) return act(() => setWebOn(null))   // 움직이는 카드 조작 끝(카드 안에 커서가 있으면 Esc는 카드가 받음 — 바깥 누르기)
      if (pbox && !mod && /^(Arrow(Up|Down|Left|Right)|Page(Up|Down)|Home|End)$/.test(k)) {   // PDF 넘겨 보는 중 = 쪽 넘기기(2026-10-21: 화살표가 카드를 옮기던 것)
        e.preventDefault()
        const lay = pdfLayout(pdfOn, pdfOn.rect[2]), t = pbox.scrollTop, cur = Math.max(0, lay.findIndex(([py, ph]) => t < py + ph - 4))
        const go = i => pdfScroll(pdfOn, pbox, lay[Math.max(0, Math.min(lay.length - 1, i))]?.[0] ?? 0)
        if (k === 'ArrowDown') pdfScroll(pdfOn, pbox, t + 60); else if (k === 'ArrowUp') pdfScroll(pdfOn, pbox, t - 60)
        else if (k === 'Home') go(0); else if (k === 'End') go(lay.length - 1)
        else go(cur + (k === 'PageDown' || k === 'ArrowRight' ? 1 : t > lay[cur][0] + 4 ? 0 : -1))   // 앞으로 = 지금 쪽 첫머리, 이미 첫머리면 앞 쪽
        return
      }
      if (mod && k.toLowerCase() === 'z' && !e.shiftKey) return act(undo)
      if (mod && (k.toLowerCase() === 'y' || (k.toLowerCase() === 'z' && e.shiftKey))) return act(redo)
      if (mod && k.toLowerCase() === 'a') return act(() => setSel(hitPool().filter(it => !layerLocked(it)).map(it => it._id)))   // 잠긴 것도(2026-10-25 — 여럿 한 번에 풀기), 잠긴 레이어의 것만 빼고
      if (lineSel) {   // 고른 메모 줄(노션) — Esc 풀기 · Del 지우기 · Ctrl+D 복제 · Ctrl+/ 전환 · ↑↓ 옮겨 고르기(Shift = 넓히기) · Enter 고치기
        const ls = lineSel, it = m.items.find(x => x._id === ls.id), L = it?.lines || []
        const put = (lines, label) => { setLineMenu(null); commit(m.items.map(x => (x._id === it._id ? { ...x, lines: lines.length ? lines : [{ k: 'p', t: '' }] } : x)), [it._id], label) }
        if (!it) setLineSel(null)
        else if (k === 'Escape' && lineMenu) return act(() => setLineMenu(null))   // 메뉴만 닫음(고른 줄은 그대로 — 노션)
        else if (k === 'Escape') return act(() => setLineSel(null))
        else if (k === 'Delete' || k === 'Backspace') return act(() => { const on = new Set(selIdx(ls)); put(L.filter((_, j) => !on.has(j)), '줄 지움'); setLineSel(null) })
        else if (mod && k.toLowerCase() === 'd') return act(() => { const idx = selIdx(ls), last = idx[idx.length - 1] + 1; put([...L.slice(0, last), ...idx.map(i => structuredClone(L[i])), ...L.slice(last)], '줄 복제'); setLineSel({ id: it._id, s: last, e: last + idx.length }) })
        else if (mod && (k === '/' || e.code === 'Slash')) return act(() => { const us = selUnits(ls), b = memoHandleRect(it, us[0][0]), o = scr(toScene(it, { x: b.x + b.w, y: b.y + b.h })); setLineMenu({ x: o.x + 4, y: o.y, id: it._id, units: us, kinds: true }) })
        else if (k === 'Enter' && mod) return act(() => { const nx = toggleTodos(L, selIdx(ls)); if (nx) put(nx, '할 일') })   // 고른 할 일 한꺼번에 체크/해제
        else if (k === 'Enter' && !mod) return act(() => { setLineSel(null); setEditing({ id: it._id, kind: 'memo', caret: selUnits(ls)[0][0] }) })   // 고른 줄 끝에 커서(2026-10-18 사용자: 맨 아래로 내려갔음)
        else if (k === 'ArrowUp' || k === 'ArrowDown') return act(() => {
          if (k === 'ArrowDown') { if (ls.e >= L.length) return; const [, ne] = lineUnit(L, ls.e); setLineSel(e.shiftKey ? { ...ls, e: ne } : { id: ls.id, s: ls.e, e: ne }) }   // 개별로 고른 것(more)은 화살표에선 풀림(Shift는 유지)
          else { if (ls.s <= 0) return; const s0 = lineUnit(L, ls.s - 1)[0]; setLineSel(e.shiftKey ? { ...ls, s: s0 } : { id: ls.id, s: s0, e: lineUnit(L, s0)[1] }) } })   // 위 줄(코드·인용은 그 덩어리 처음)
      }
      if (k === 'Escape') { setOverlay(o => ({ ...o, poly: null, draw: null, lpt: null, pcur: null })); if (R.current.tool !== 'select') setTool('select'); else if (cellSel) setCellSel(null); else setSel([]); return }
      if (k === 'Enter' && overlay.poly) return act(() => finishPoly(overlay.poly, false))
      // 칸을 고른 채로 — 엑셀처럼: 글자를 치면 바로 그 칸에 새로 씀(두 번 누르지 않아도 — 2026-10-18 사용자), Enter·F2 = 있는 글 이어 고치기, Delete = 칸 글만 지움(표는 그대로)
      if (cellSel && ids.length === 1 && ids[0] === cellSel.id && !mod && !e.altKey) {
        const { r0, r1, c0, c1 } = cellRange(cellSel)
        if (k === 'Delete' || k === 'Backspace') return act(() => { const t = m.items.find(x => x._id === cellSel.id); if (!t) return
          const cells = t.cells.map((row, r) => row.map((v, c) => (r >= r0 && r <= r1 && c >= c0 && c <= c1 ? '' : v))), cr = { ...(t.cell_runs || {}) }
          for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) delete cr[`${r},${c}`]
          commit(m.items.map(x => (x._id === t._id ? { ...t, cells, cell_runs: Object.keys(cr).length ? cr : undefined } : x)), [t._id], '칸 글 지움') })
        if (k === 'Enter' || k === 'F2') return act(() => setEditing({ id: cellSel.id, kind: 'cell', r: r0, c: c0 }))
        if (k.length === 1 || k === 'Process' || e.keyCode === 229) {   // 기본 동작은 막지 않음 — 미리 띄운(보이지 않는) 칸 편집기가 이 글쇠를 받음, 여기선 보이게만
          const ne = { id: cellSel.id, kind: 'cell', r: r0, c: c0, fresh: true }; R.current.editing = ne; flushSync(() => setEditing(ne)); return }
        const dir = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] }[k]
        if (dir) return act(() => { const t = m.items.find(x => x._id === cellSel.id); if (!t) return   // 칸 고르기 옮기기(엑셀) — Shift = 넓히기
          const cl = (v, n) => Math.max(0, Math.min(n - 1, v))
          setCellSel(cs => (e.shiftKey ? { ...cs, r1: cl(cs.r1 + dir[0], t.rows), c1: cl(cs.c1 + dir[1], t.cols) } : { id: cs.id, r0: cl(r0 + dir[0], t.rows), c0: cl(c0 + dir[1], t.cols), r1: cl(r0 + dir[0], t.rows), c1: cl(c0 + dir[1], t.cols) })) })
      }
      const ta = armTarget()   // 도형 하나 고른 채 — 글자를 치면 바로 그 글로 새로 씀(도구 숫자·Shift+H/V보다 먼저), Enter·F2 = 있는 글 이어 고치기
      if (ta && !mod && !e.altKey) {
        if (k === 'Enter' || k === 'F2') return act(() => setEditing({ id: ta.id, kind: ta.kind }))
        if (k.length === 1 || k === 'Process' || e.keyCode === 229) {   // 기본 동작은 막지 않음 — 대기 편집기가 이 글쇠를 받음, 여기선 보이게만
          const ne = { id: ta.id, kind: ta.kind, ...(ta.kind === 'memo' ? {} : { fresh: true }) }; R.current.editing = ne; flushSync(() => setEditing(ne)); return }
      }
      if (!mod && !e.shiftKey && e.code === 'KeyZ') return act(() => {
        const c = R.current.cam, zb = zBack.current; zBack.current = null
        const same = p => p && ['x', 'y', 'z'].every(q => Math.abs(c[q] - p[q]) < 1e-6)
        if (!e.altKey && zb?.after && (same(zb.after) || same(zb.before))) { setCam(zb.before); setStatus('보던 자리로'); return }   // Z 한 번 더(그 사이 화면 안 움직임) = 누르기 전 자리로(2026-10-22 사용자: 전체를 슬쩍 보고 돌아가기). before와 같음 = 맞춘 자리가 아직 안 그려짐(연달아 누름)
        const its = e.altKey ? R.current.model.items.filter(it => ids.includes(it._id)) : null, after = onFit?.(its?.length ? its : null)
        if (!e.altKey && after) zBack.current = { before: { ...c }, after }   // 맞춘 자리는 fit이 바로 돌려줌 — 전엔 다음 화면 그리기에서 읽어, 그 전에 Z를 또 누르면 다 보기를 한 번 더 했음(10-23 화면 시험 흔들림)
      })   // Z = 다 보기 · Alt+Z = 고른 것만(왼손 자리 — 2026-10-20 사용자, 한글 입력이어도 자리로). 옛 Shift+Z는 글 도형 하나를 고르면 글로 들어가 정작 필요할 때 안 먹었음 — Alt는 「치면 글」을 건너뜀
      if (!mod && !e.altKey && !e.shiftKey && e.code === 'KeyD' && !ids.length) return act(() => onDark?.())   // D = 어둡게 ⇄ 밝게(발표와 같은 글쇠, 아무것도 안 골랐을 때)
      const TOOL_KEYS = { 1: 'select', 2: 'arrow', 3: 'text', 4: 'line', 5: 'polygon', 6: 'pen', 7: 'badge' }   // 데스크톱 `SHORTCUT_DEFS` 도구 1~7
      if (!mod && !e.altKey && !e.shiftKey && TOOL_KEYS[k]) return act(() => setTool(TOOL_KEYS[k]))
      if (mod && k.toLowerCase() === 'v') return   // 붙여넣기는 브라우저 붙여넣기 신호에서(주소면 웹 카드, 아니면 칠판 붙여넣기 — 아래 onPaste). 여기서 막으면 그 신호가 안 옴
      if (!ids.length) return
      const LOCK_MSG = '잠긴 도형이에요 — 옮기기·지우기·고치기는 막혀 있어요(풀기 Ctrl+L)'
      if (ids.length && ids.every(id => m.items.find(x => x._id === id)?.locked) && ['Delete', 'Backspace', 'ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(k)) return act(() => setStatus(LOCK_MSG))   // 잠긴 것만 고름 = 말로만 알림
      if (k === 'Delete' || k === 'Backspace') return act(() => commit(removeItems(m.items, movingSet(ids)), [], '지움'))
      // 스타일 복사·붙여넣기(데스크톱 Ctrl+Alt+C/V) — 일반 복사보다 먼저. 글쇠 이름은 한글 입력·Alt에 따라 바뀌어 자리(code)로 봄
      if (mod && e.altKey && e.code === 'KeyC') return act(styleCopy)
      if (mod && e.altKey && e.code === 'KeyV') return act(stylePaste)
      if (mod && k.toLowerCase() === 'c' && pdfSelectedText()) return   // PDF 안 끌어 고른 글 = 브라우저 복사
      if (mod && k.toLowerCase() === 'c') return act(copy)
      if (mod && k.toLowerCase() === 'x') return act(() => { copy(); commit(removeItems(m.items, movingSet(ids)), [], '잘라냄') })
      if (mod && k.toLowerCase() === 'd') return act(dupSel)
      if (mod && e.altKey && e.code === 'KeyG') return act(wrapFrame)   // 프레임으로 감싸기(Figma와 같은 글쇠, 2026-10-25) — Alt+G는 한글 입력·Alt에 따라 이름이 바뀌어 자리로
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
  // 복제(Ctrl+D) — 오른쪽 아래로 20(제자리면 겹쳐 안 보임 — 2026-10-18 사용자 지적). 방금 만든 복제본을 옮기고 또 누르면 그 옮긴 만큼 되풀이(같은 간격으로 늘어놓기)
  const lastDup = useRef(null)   // { ids: 복제본, src: 원본 첫 조각, dup: 복제본 첫 조각 }
  function dupSel() {
    const m = R.current.model, sel = R.current.sel, ld = lastDup.current
    // 방금 만든 복제본을 그대로 고른 채면 그 복제본만 — 다시 「안의 것」을 모으면 20 비켜 겹친 앞 복제본까지 딸려 와 개수가 배로 붙어남(2026-10-18 사용자: 프레임 번호 133·197·229…)
    const live = ld && ld.ids.filter(id => m.items.some(x => x._id === id)), same = !!live?.length && sel.length > 0 && sel.every(id => live.includes(id))
    const ids = same ? live : withContents(sel); if (!ids.length) return
    let dx = 20, dy = 20
    if (same) { const a = m.items.find(x => x._id === ld.src), b = m.items.find(x => x._id === ld.dup)
      if (a && b) { const sa = sceneBox(a, textBox), sb = sceneBox(b, textBox); dx = sb.x - sa.x; dy = sb.y - sa.y } }
    const set = new Set(ids), first = m.items.find(it => set.has(it._id)), r = duplicate(m.items, ids, dx, dy)
    lastDup.current = { ids: r.ids, src: first._id, dup: r.ids[0] }
    commit(r.items, r.ids, '복제')
  }
  function styleCopy() {
    const m = R.current.model, ids = R.current.sel
    if (ids.length !== 1) return setStatus('스타일 복사 — 도형을 하나만 고르세요')
    styleClip.current = captureStyle(m.items.find(it => it._id === ids[0])); setStatus('스타일 복사됨')
  }
  function stylePaste() {
    const m = R.current.model, ids = R.current.sel, sc = styleClip.current
    if (!sc) return setStatus('붙여넣을 스타일이 없어요 — 먼저 Ctrl+Alt+C')
    const set = new Set(ids); commit(m.items.map(it => { const p = set.has(it._id) && styleFor(it, sc); return p ? { ...it, ...p } : it }), ids, '스타일 붙여넣기')
    setStatus(`스타일 붙여넣기 — ${ids.length}개`)
  }
  // ── 정렬·분배(데스크톱 `align_selection`·`distribute_selection`) — 대상 = 고른 것에서 붙은 화살표·용지틀 뺀 것, 기준 = 고른 것 전체 상자 ──
  const alignTargets = () => { const ids = new Set(R.current.sel); return R.current.model.items.filter(it => ids.has(it._id) && !it.locked && it.type !== 'titleblock' && !(isArrow(it) && (it._bind1 || it._bind2 || it.bind1_group || it.bind2_group))) }
  function alignSel(mode) {
    const ts = alignTargets(); if (ts.length < 2) return
    const bs = new Map(ts.map(it => [it._id, sceneBox(it, textBox)])), u = unionBox([...bs.values()])
    let items = R.current.model.items
    for (const it of ts) { const b = bs.get(it._id)
      const dx = mode === 'left' ? u.x - b.x : mode === 'right' ? u.x + u.w - b.x - b.w : mode === 'hcenter' ? u.x + u.w / 2 - b.x - b.w / 2 : 0
      const dy = mode === 'top' ? u.y - b.y : mode === 'bottom' ? u.y + u.h - b.y - b.h : mode === 'vcenter' ? u.y + u.h / 2 - b.y - b.h / 2 : 0
      if (dx || dy) items = moveItems(items, [it._id], dx, dy) }
    commit(items, R.current.sel, '정렬')
  }
  // 균등 분배(양 끝 그대로, 사이 여백을 같게) / 첫 간격 반복(첫 두 개 사이 여백을 뒤로 반복). 붙은 화살표 구간 분배는 아직(데스크톱은 함)
  function distributeSel(axis, firstGap) {
    const ts = alignTargets(); if (ts.length < 3) return
    const H = axis === 'x', st0 = b => (H ? b.x : b.y), sz = b => (H ? b.w : b.h)
    const list = ts.map(it => ({ it, b: sceneBox(it, textBox) })).sort((a, b) => st0(a.b) - st0(b.b))
    const first = list[0].b, last = list[list.length - 1].b
    const gap = firstGap ? st0(list[1].b) - st0(first) - sz(first) : (st0(last) + sz(last) - st0(first) - list.reduce((s, e) => s + sz(e.b), 0)) / (list.length - 1)
    let items = R.current.model.items, cur = st0(first) + sz(first)
    for (const { it, b } of list.slice(1, firstGap ? undefined : -1)) { const d = cur + gap - st0(b); items = moveItems(items, [it._id], H ? d : 0, H ? 0 : d); cur += gap + sz(b) }
    commit(items, R.current.sel, '분배')
  }
  // 복사 = 칠판용(도형 그대로) + 그림(시스템 클립보드 — 한글·PPT에 붙이면 그림, 데스크톱 `_copy_as_image`). 2026-10-18 사용자: 「그림으로 복사」를 따로 두면 불편 → 하나로.
  // 브라우저는 누른 순간에만 클립보드 쓰기를 허락하므로, 그림은 「만들어질 약속」(Promise)으로 바로 넘긴다. 고른 것을 용지 없이 2배 해상도 PNG로
  function imageToClipboard(ids) {
    const m = R.current.model, ents = drawOrder(m.items).filter(([it]) => ids.has(it._id)); if (!ents.length || typeof ClipboardItem === 'undefined') return
    const src = unionBox(ents.map(([it]) => sceneBox(it, textBox))), pad = 8
    const png = buildSvg(ents, { x: src.x - pad, y: src.y - pad, w: src.w + 2 * pad, h: src.h + 2 * pad }, { tight: true, frame: null }, boardMembership(m.items), resolveRoutes(m.items, rectOf)).then(res => pngBlob(res, 192))
    const c = clip.current
    png.then(b => createImageBitmap(b)).then(bm => { c.dims = `${bm.width}x${bm.height}` }).catch(() => {})   // 붙여넣을 때 「이건 칠판이 넣은 그림」 알아보기(브라우저가 PNG를 다시 써도 크기는 같음)
    navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]).catch(() => { c.noClip = true; setStatus('도형은 복사함 — 그림 복사는 브라우저가 막았어요') })
  }
  function copy() {
    const m = R.current.model, ids = new Set(withContents(R.current.sel))
    clip.current = { items: structuredClone(m.items.filter(it => ids.has(it._id))), seq: 0, fresh: true }   // fresh = 복사한 뒤 다른 창에 안 다녀옴(그동안 Ctrl+V = 칠판 도형)
    imageToClipboard(ids)
    setStatus?.(`${ids.size}개 복사 — 칠판에 붙이면 도형, 한글·PPT에 붙이면 그림`)
  }
  // 붙여넣기 신호 — 칠판에서 복사한 것이면 칠판 도형, 아니면 바깥 것: 그림·파일(끌어 놓기와 같게)·주소 = 웹 카드(2026-10-18 사용자)·글(2026-10-21 사용자 — `clipin.js`)
  useEffect(() => {
    const stale = () => { clip.current.fresh = false }   // 다른 창에 다녀오면 바깥에서 새로 복사했을 수 있음
    const onPaste = async e => {
      if (readOnly) return
      const ae = document.activeElement
      if (R.current.editing || /INPUT|TEXTAREA|SELECT/.test(ae?.tagName || '') || (ae?.isContentEditable && !ae.closest('[data-armed]'))) return   // 글 고치는 중이면 그 칸에(고르기만 한 대기 편집기 = 칠판이 받음)
      const cd = e.clipboardData, files = [...(cd?.files || [])], text = cd?.getData('text/plain') || '', html = cd?.getData('text/html') || ''
      e.preventDefault()
      const c = clip.current, img = files.length === 1 && files[0].type.startsWith('image/') && !text && files[0]
      if (c.items.length) {   // 칠판 도형 — 칠판은 그림만 넣으니 글이 있으면 바깥 것. 그림뿐이면 복사하고 안 나갔거나 칠판이 넣은 그 그림(크기)일 때
        let mine = c.noClip ? c.fresh : !text.trim() && (!files.length || img) && c.fresh   // noClip = 그림 넣기가 막힘(클립보드엔 옛것)
        if (!mine && !c.noClip && img && c.dims) mine = await createImageBitmap(img).then(b => `${b.width}x${b.height}` === c.dims, () => false)
        if (mine) { paste(); return }
      }
      const url = normalizeUrl(text)
      if (url) { insertWeb(url); return }
      if (looksSvg(text) && insertSvg(text, pasteAt(), 'SVG 코드')) return   // AI가 준 SVG 코드 = 도형(못 읽는 모양이면 아래 글 규칙으로)
      if (files.length && !text.trim()) { dropFiles(files); return }   // 그림 복사·탐색기에서 복사한 파일(웹 그림 복사는 html에 <img>만 따라옴)
      if (!pasteOutside(text, html) && files.length) dropFiles(files)   // 엑셀·워드는 글 + 그림이 같이 옴 → 글이 먼저
    }
    window.addEventListener('paste', onPaste); window.addEventListener('blur', stale)
    return () => { window.removeEventListener('paste', onPaste); window.removeEventListener('blur', stale) }
  })
  // 웹 카드 넣기 — 서버가 주소를 확인한 뒤(칸 안에 넣어도 되나·제목·대표 그림) 커서 자리(화면 밖이면 가운데)에
  // 그림 파일·클립보드 그림 → 이미지 도형(.ecad image = PNG base64 — 다른 형식도 PNG로 바꿔 넣음, 데스크톱도 그대로 열림). 커서 자리(없으면 화면 가운데), 긴 변 최대 화면의 60%
  // opts.at = 가운데 자리(칠판 좌표, 없으면 커서·화면 가운데), opts.caption = 그림 만들기 요청 → 그림의 보이지 않는 설명 `alt`(§8 항목61 ③-4 — 2026-10-20부터 밑 글 없음)
  async function insertImage(file, opts = {}) {
    const url = URL.createObjectURL(file)
    try {
      const im = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = url })
      const cv = document.createElement('canvas'); cv.width = im.naturalWidth; cv.height = im.naturalHeight; cv.getContext('2d').drawImage(im, 0, 0)
      const data = cv.toDataURL('image/png').split(',')[1]
      const c = R.current.cam, mp = R.current.mouse, vw = { x: -c.x / c.z, y: -c.y / c.z, w: size.w / c.z, h: size.h / c.z }
      // 크기: 보통 = 지금 보이는 곳 짧은 변의 60%(원본보다 크게는 안 함) — 배율 따라 칠판 위 크기가 달라짐.
      // fixed = 대화창 그림 후보 — 배율과 상관없이 긴 변 680(답 메모 두 개 폭, 2026-10-20 사용자: 붙일 때마다 크기가 제각각)
      const k = opts.fixed ? IMG_FIXED / Math.max(im.naturalWidth, im.naturalHeight) : Math.min(1, (Math.min(vw.w, vw.h) * 0.6) / Math.max(im.naturalWidth, im.naturalHeight)), w = im.naturalWidth * k, h = im.naturalHeight * k, m = R.current.model
      // free = 버튼으로 붙이기(대화창 그림 후보 누르기) — 가운데 먼저, 겹치면 가까운 빈자리(메모·표 버튼과 같은 `spotNear`, 2026-10-20 사용자: 둘째 그림이 첫째 위에 겹침)
      const fs = opts.free && spotNear(w, h)
      const at = fs ? { x: fs.x + w / 2, y: fs.y + h / 2 } : opts.at || (mp && mp.x >= vw.x && mp.x <= vw.x + vw.w && mp.y >= vw.y && mp.y <= vw.y + vw.h ? mp : { x: vw.x + vw.w / 2, y: vw.y + vw.h / 2 })
      // caption = 그림을 만든 요청 — 칠판엔 그림만, 요청은 보이지 않는 설명 `alt`(찾기·뜻으로 찾기·대화 재료가 읽음, 2026-10-20 사용자: 밑 글 빼고 깔끔하게)
      const it = base([at.x - w / 2, at.y - h / 2], { type: 'image', rect: [0, 0, w, h], data, z: topZ(m.items) + 1, ...(opts.caption ? { alt: opts.caption } : null) })
      commit([...m.items, it], [it._id], opts.caption ? '그림 붙이기' : '그림 붙여넣기')
      setTool('select'); return it._id
    } catch { setStatus('그림을 읽지 못했어요') } finally { URL.revokeObjectURL(url) }
  }
  // 그림 후보 붙이기(대화창 🎨 — 누르면 빈자리, 끌어 놓으면 그 자리) — 서버 그림(/api/img/…)을 받아 이미지로 + 밑에 요청 글
  async function pinImage(url, caption, at) {
    try { const b = await (await fetch(url)).blob()
      return await insertImage(b, at ? { at, caption, fixed: true } : { free: true, caption, fixed: true }) } catch { setStatus('그림을 못 가져왔어요'); return null }
  }
  // 그림 후보 끌어 붙이기 — 답 메모처럼 칠판이 직접 끔(실제 크기 + 정렬선, 2026-10-20 사용자: 브라우저 끌기는 크기가 다르고 정렬선이 없음). 끄는 동안 손을 떼면 안 붙임
  async function dragImage(url, caption, onPlaced, released) {
    try {
      const b = await (await fetch(url)).blob(), src = URL.createObjectURL(b)
      const im = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src }); URL.revokeObjectURL(src)
      if (released()) return
      const cv = document.createElement('canvas'); cv.width = im.naturalWidth; cv.height = im.naturalHeight; cv.getContext('2d').drawImage(im, 0, 0)
      const k = IMG_FIXED / Math.max(im.naturalWidth, im.naturalHeight), w = im.naturalWidth * k, h = im.naturalHeight * k, z = topZ(R.current.model.items) + 1
      const protos = [base([0, 0], { type: 'image', rect: [0, 0, w, h], data: cv.toDataURL('image/png').split(',')[1], z, ...(caption ? { alt: caption } : null) })]   // 요청 = 보이지 않는 설명
      startPaletteDrag('image', protos, ids => { setTool('select'); onPlaced?.(ids) })
    } catch { setStatus('그림을 못 가져왔어요') }
  }
  // 칠판에 주소 끌어 놓기 — 대화창 그림 후보면 그 그림, 다른 웹 주소면 웹 카드(주소 Ctrl+V와 같게). 전엔 처리가 없어 브라우저가 그 주소로 떠났음
  function dropUrl(url, caption, e) {
    if (readOnly) return
    const p = toSceneP(e); R.current.mouse = p
    if (/\/api\/img\//.test(url)) pinImage(url, caption, p)
    else if (/^https?:\/\//i.test(url)) insertWeb(url)
  }
  // ── 칠판에 파일 끌어 놓기(2026-10-19) — 그림 = 이미지, 녹음 = 회의록(§8 항목61 ③-3). 그 밖 파일은 알림만(전엔 브라우저가 그 파일을 열며 칠판을 떠났음) ──
  const AUDIO_RE = /\.(mp3|m4a|wav|webm|ogg|aac|flac|mp4)$/i
  const TEXT_FILE_RE = /\.(md|markdown|txt)$/i   // 글 파일 = 그 글을 붙여넣은 것과 같게(2026-10-21 사용자 — md는 AI가 많이 쓰는 문서)
  const FILE_FOLD_N = 30   // 글 파일 메모가 이보다 길면 접어서 넣음(칠판을 덮지 않게 — 회의록 전문과 같게)
  async function dropFiles(files, e) {   // e 없음 = 붙여넣기(커서 자리, 화면 밖이면 가운데)
    if (readOnly) return
    const p = e ? toSceneP(e) : pasteAt(); R.current.mouse = p
    for (const f of files) {
      if (/\.svg$/i.test(f.name) || f.type === 'image/svg+xml') { if (!insertSvg(await f.text(), p, f.name)) { await insertImage(f); setStatus(`${f.name} — 도형으로 못 읽는 부분(옮기기·그라디언트 등)이 있어 그림으로 넣었어요`) } }
      else if (/^image\//.test(f.type)) await insertImage(f)
      else if (AUDIO_RE.test(f.name) || /^audio\//.test(f.type)) startMeeting(f, p)
      else if (/\.pdf$/i.test(f.name) || f.type === 'application/pdf') await insertPdf(f, p)
      else if (/\.html?$/i.test(f.name) || f.type === 'text/html') await insertHtmlFile(f, p)
      else if (TEXT_FILE_RE.test(f.name) || /^text\/(plain|markdown)$/.test(f.type)) { if (!pasteOutside(await f.text(), '', { at: p, file: f.name })) setStatus(`${f.name} — 빈 파일이에요`) }
      else setStatus(`${f.name} — 칠판엔 그림·녹음·PDF·HTML·md·txt 파일을 놓을 수 있어요(.ecad는 「열기」)`)
    }
  }
  // SVG → 고칠 수 있는 도형(§8 항목63) — 데스크톱 `_insert_svgs_at`과 같게: 긴 변 160·가운데 = at, 펜 = 지금 그리기색·채움 없음(글자는 제 색),
  // 묶음 하나로(2026-10-25 사용자: 모여 있어야 뜻이 있음 — 끌어 고르기도 하나만 걸리면 통째, 낱개로 고치려면 Ctrl+Shift+G. 옛 2026-08-04 「묶지 않음」을 뒤집음). 못 읽는 모양이면 false
  const SVG_LONG = 160
  const svgProtos = (svg, at) => { const z = topZ(R.current.model.items) + 1, its = svgItems(svg, SVG_LONG, at).items, g = its.length > 1 ? 'g' + newId() : null
    return its.map((s, i) => base(s.pos, s.type === 'text' ? { ...s, bg: null, z: z + i, group_id: g } : { ...penOf(false), ...(s.type === 'path' || s.type === 'line' ? null : { fill: null }), ...s, z: z + i, group_id: g })) }
  function insertSvg(svg, at, what = 'SVG') {
    if (!svgFits(svg)) return false
    const m = R.current.model, its = svgProtos(svg, at)
    commit([...m.items, ...its], its.map(it => it._id), what); setTool('select')
    setStatus(`${what} → 도형 ${its.length}개 묶음 — 선 하나씩 고치려면 묶음 풀기(Ctrl+Shift+G)`)
    return true
  }
  // 대화창 ✏️ 아이콘 후보(2단계) — 넣는 모양은 위와 같게, 자리는 그림 후보처럼: 누르면 가운데 먼저·겹치면 빈자리, 끌면 놓은 자리(정렬선).
  // AI가 만든 것은 `svgFits`로 막지 않음(데스크톱 「심볼」과 같게 — 못 읽는 부분만 건너뜀). 넣은 도형 _id들(없으면 null)
  function pinSvg(svg) {
    const ps = svgProtos(svg, { x: 0, y: 0 }); if (!ps.length) { setStatus('아이콘을 도형으로 못 읽었어요'); return null }
    const m = R.current.model, b = unionBox(ps.map(it => sceneBox(it, textBox))), at = spotNear(b.w, b.h), its = placeAt(ps, at.x, at.y)
    commit([...m.items, ...its], its.map(it => it._id), '아이콘 붙이기'); setTool('select')
    return its.map(it => it._id)
  }
  const dragSvg = (svg, onPlaced) => { const ps = svgProtos(svg, { x: 0, y: 0 }); if (ps.length) startPaletteDrag('svg', ps, onPlaced) }
  // HTML 파일 = 정리 문서 카드(스크립트는 끔 — 칠판이 안전하게, 2026-10-21 사용자)
  async function insertHtmlFile(f, at) {
    const html = await f.text(), m = R.current.model, title = (/<title[^>]*>([^<]*)<\/title>/i.exec(html)?.[1] || '').trim() || f.name.replace(/\.html?$/i, '')
    const it = docItem({ title, html }, 0, 0, topZ(m.items) + 1), w = it.rect[2], h = it.rect[3]
    const placed = { ...it, file: f.name, pos: [at.x - w / 2, at.y - h / 2] }
    commit([...m.items, placed], [placed._id], 'HTML 파일'); setTool('select')
    setStatus(`HTML 파일 → 문서 카드 — ↗ 또는 두 번 누르기 = 크게 보기(파일 속 프로그램은 꺼서 보여요)`)
  }
  // PDF 파일 = PDF 보기 카드(2026-10-21 사용자) — 원본은 서버(`/api/pdf/<칠판>`), 칠판엔 주소·쪽 크기·첫 쪽 작은 그림·글(찾기용)
  const PDF_W = 420, PDF_W_MAX = 760   // 넣을 때 화면 폭 — 쪽 하나가 화면 높이의 80%쯤 들어오게(2026-10-21 사용자: 너무 작아 못 읽음), 이 사이로
  async function insertPdf(f, at) {
    const id = newId(), done = () => setPend(ps => ps.filter(q => q.id !== id)), s0 = 1 / R.current.cam.z, pw0 = PDF_W * s0, ph0 = pw0 * 1.414
    setPend(ps => [...ps, { id, kind: 'pdf', label: 'PDF 올리는 중', x: at.x - pw0 / 2, y: at.y - ph0 / 2, w: pw0, h: ph0, msg: f.name }])
    try {
      const r = await fetch(`/api/pdf/${encodeURIComponent(DOC_NAME)}`, { method: 'POST', body: f, headers: { 'Content-Type': 'application/pdf', 'X-File-Name': encodeURIComponent(f.name) } })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      const s = +(1 / R.current.cam.z).toPrecision(2), [pw, ph] = d.sizes[0] || [595, 842], m = R.current.model
      const W = Math.round(Math.max(PDF_W, Math.min(PDF_W_MAX, (size.h * 0.8 - WEB_HEAD) * pw / ph))), h = WEB_HEAD + Math.round(W * Math.min(1.5, ph / pw))
      const it = base([at.x - W * s / 2, at.y - h * s / 2], { type: 'pdf', rect: [0, 0, W, h], url: d.url, name: d.name, pages: d.pages, sizes: d.sizes, thumb: d.thumb, text: d.text, scale: s, z: topZ(m.items) + 1 })
      done(); commit([...m.items, it], [it._id], 'PDF'); setTool('select')
      setStatus(`PDF ${d.pages}쪽 — 누르면 넘겨 보기`)
    } catch (err) { done(); setStatus(`PDF 실패 — ${err.message || err}`) }
  }
  // PDF 카드에서 Alt+끌기 = 그 부분을 칠판으로(서버가 200dpi로 다시 그림) — 카드 오른쪽 빈자리, 밑에 「파일 · N쪽」, 카드 → 그림 점선 화살표(어디서 왔는지 — 웹 검색 출처 카드와 같은 원칙).
  // 그 부분 글은 그림의 보이지 않는 설명(찾기·대화 재료 — 우클릭 「그림 속 글 읽기」도 이것을 씀)
  async function clipPdf({ id, page, r, top, key }) {
    const tell = (ok, msg) => window.dispatchEvent(new CustomEvent('mb-pdf-clipped', { detail: { key, ok, msg } }))   // 카드의 오린 자리에 결과(2026-10-22 사용자: PDF를 크게 보면 칠판이 안 보임)
    const card = R.current.model.items.find(it => it._id === id); if (!card) { tell(false, '✗ 오려 오기 실패 — 카드를 못 찾음'); return }
    const q = `${card.url}/${'%s'}/${page}?r=${r.map(v => v.toFixed(4)).join(',')}`
    setStatus('오려 오는 중…')
    try {
      const [png, txt] = await Promise.all([fetch(q.replace('%s', 'clip')).then(x => { if (!x.ok) throw new Error(`서버 응답 ${x.status}`); return x.blob() }),
        fetch(q.replace('%s', 'text')).then(x => x.json()).then(d => d.text || '', () => '')])
      const bm = await createImageBitmap(png), cv = document.createElement('canvas'); cv.width = bm.width; cv.height = bm.height; cv.getContext('2d').drawImage(bm, 0, 0)
      const data = cv.toDataURL('image/png').split(',')[1]
      const cb = sceneBox(card, textBox), k = (card.scale || 1), w = card.rect[2] * k * (r[2] - r[0]), h = w * bm.height / bm.width, z = topZ(R.current.model.items) + 1
      const label = `${card.name || 'PDF'} · ${page + 1}쪽`, s = +(1 / R.current.cam.z).toPrecision(2)
      const cap = base([0, 0], { type: 'text', text: label, color: '#ff8a8f98', font: 9, bg: null, scale: s, z }), capH = sceneBox(cap, textBox).h
      const ty = toSceneP({ clientX: 0, clientY: top }).y
      // 놓을 자리 = 쪽마다 한 줄(2026-10-23 사용자 — 전엔 카드 오른쪽 한 단): 같은 쪽을 이어 오리면 앞 그림 오른쪽, 다른 쪽이면 앞서 오린 것들 아래에 새 줄(왼쪽 끝 맞춤).
      // 줄 순서 = 오린 순서. 앞 그림 = 이 카드에서 오려 온 그림(설명 첫 줄 = 「파일 · N쪽」). 첫 그림은 오린 높이, 막히면 오른쪽으로 비켜 줄 시작을 정함. 겹치면 바로 아래로
      const prev = R.current.model.items.filter(x => x.type === 'image' && clipOf(x)?.name === (card.name || 'PDF'))
        .map(x => ({ ...sceneBox(x, textBox), page: clipOf(x).page })).filter(b => b.x > cb.x + cb.w)
      const solid = hitPool().filter(it => !/arrow|line/.test(it.type)).map(it => sceneBox(it, textBox))   // 화살표·선은 비켜 가지 않음
      const gap = 24 * s, free = (x, y) => !solid.some(b => x < b.x + b.w + gap && x + w + gap > b.x && y < b.y + b.h + gap && y + h + capH + gap > b.y)
      const down = (x, y) => {   // 겹친 것 바로 밑으로
        for (let i = 0; i < 200 && !free(x, y); i++) y = Math.max(...solid.filter(b => x < b.x + b.w + gap && x + w + gap > b.x && y < b.y + b.h + gap && y + h + capH + gap > b.y).map(b => b.y + b.h)) + gap
        return y
      }
      const last = prev[prev.length - 1]
      let ax, ay
      if (!last) { ax = cb.x + cb.w + 48 * s; for (let i = 0; i < 80 && !free(ax, ty); i++) ax += gap; ay = down(ax, ty) }
      else if (last.page === page) { ax = last.x + last.w + gap; ay = down(ax, last.y) }   // 같은 쪽 = 같은 줄 오른쪽
      else { ax = Math.min(...prev.map(b => b.x)); ay = down(ax, Math.max(...prev.map(b => b.y + b.h + capH)) + gap) }   // 다른 쪽 = 새 줄
      const at = { x: ax, y: ay }
      const g = 'g' + newId()
      const img = base([at.x, at.y], { type: 'image', rect: [0, 0, w, h], data, alt: `${label}${txt ? '\n' + txt : ''}`, z, group_id: g })
      const capd = { ...cap, pos: [at.x - TEXT_MARGIN * s, at.y + h + 2 * s], group_id: g }
      // 화살표는 없음(2026-10-22 사용자: 그림마다 화살표 = 여럿이면 엉켜 지저분) — 출처는 밑 글 「파일 · N쪽」, Ctrl+클릭·우클릭 = PDF 그 쪽으로
      commit([...R.current.model.items, img, capd], [img._id], 'PDF에서 오려 옴')
      setStatus(`${label} 오려 옴 — Ctrl+클릭 = PDF 그 쪽으로`); tell(true, `✓ 오려 옴 · ${page + 1}쪽`)
    } catch (err) { setStatus(`오려 오기 실패 — ${err.message || err}`); tell(false, `✗ 오려 오기 실패 — ${err.message || err}`) }
  }
  // 오려 온 그림의 출처 — 설명 첫 줄 「파일 · N쪽」(밑 글도 같은 묶음). 같은 이름 PDF 카드가 여럿이면 가장 가까운 것
  function clipOf(it) {
    const m = /^(.*) · (\d+)쪽$/.exec(String(it?.alt || '').split('\n')[0]); return m ? { name: m[1], page: +m[2] - 1 } : null
  }
  function clipSourceOf(ids) {
    const items = R.current.model.items, its = items.filter(it => ids.includes(it._id)), gid = its.find(it => it.group_id)?.group_id
    const img = [...its, ...(gid ? items.filter(it => it.group_id === gid) : [])].find(it => it.type === 'image' && clipOf(it)); if (!img) return null
    const c = clipOf(img), ib = sceneBox(img, textBox), d = it => { const b = sceneBox(it, textBox); return Math.hypot(b.x + b.w / 2 - ib.x, b.y + b.h / 2 - ib.y) }
    const card = items.filter(it => it.type === 'pdf' && (it.name || 'PDF') === c.name && c.page < (it.pages || Infinity)).sort((a, b) => d(a) - d(b))[0]
    return card ? { card, page: c.page } : null
  }
  function goClipSource(src) {   // PDF 카드를 그 쪽에 맞춰 넘겨 보기로 켜고 화면 가운데로
    pdfGoPage(src.card, src.page); showItem(src.card._id); setWebOn(src.card._id)
    setStatus(`${src.card.name || 'PDF'} ${src.page + 1}쪽`)
  }
  // 우클릭 「이 쪽 통째로 칠판에」 — Alt+끌기를 쪽 전체로 한 것과 같음(놓을 자리 = 카드 오른쪽, 높이는 카드 몸통 위)
  function pdfWholePage(id, page) {
    const card = R.current.model.items.find(it => it._id === id); if (!card) return
    const c = R.current.cam, r = svg.current.getBoundingClientRect(), b = sceneBox(card, textBox), k = card.scale || 1
    const sx = X => r.left + X * c.z + c.x, sy = Y => r.top + Y * c.z + c.y, top = sy(b.y + WEB_HEAD * k)
    clipPdf({ id, page, r: [0, 0, 1, 1], top })
  }
  // 「그림 속 글 읽기」(2026-10-21 사용자: 「글로」 단추 대신 그림 → 글 OCR) — 그림 오른쪽 빈자리에 메모, 그림은 그대로.
  // PDF에서 오려 온 그림은 이미 그 부분 글을 품고 있어(alt 둘째 줄부터) KAIROS를 안 부름. 나머지는 서버 `/api/ocr`(easycad/ai/board_ocr.py)
  // 「도면으로 베끼기」(2026-10-25 사용자 — 웹은 단순하게): 그림 → 서버(데스크톱 베끼기 엔진, `easycad/ai/board_trace.py`) → 그림 오른쪽 옆에 같은 크기로, 묶음 하나.
  // 모서리 맞추기·흐린 바탕·부분 다시는 없음(마무리는 그림을 보며 손으로). 기다리는 동안 그 자리에 구역 6칸 스켈레톤이 끝난 구역부터 참
  async function traceImage(id) {
    const img = R.current.model.items.find(it => it._id === id); if (!img?.data) return
    const ib = sceneBox(img, textBox), gap = 40 / R.current.cam.z
    const at = nearSpot({ x: ib.x + ib.w + gap + ib.w / 2, y: ib.y + ib.h / 2 }, hitPool().map(it => sceneBox(it, textBox)), ib.w, ib.h, { pad: gap * 0.6, step: gap })
    const pid = newId(), say = patch => setPend(ps => ps.map(q => (q.id === pid ? { ...q, ...patch } : q)))
    setPend(ps => [...ps, { id: pid, kind: 'trace', label: '도면으로 베끼는 중', x: at.x, y: at.y, w: ib.w, h: ib.h, cols: 3, rows: 2, done: 0, total: 6 }])
    setStatus('도면으로 베끼는 중… (KAIROS — 1분쯤, 구역 6곳 동시)')
    try {
      const r = await fetch(`/api/trace/${encodeURIComponent(DOC_NAME)}`, { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() }, body: JSON.stringify({ data: img.data, width: ib.w }) })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      let res
      for (;;) {
        await new Promise(ok => setTimeout(ok, 1500))
        const g = await fetch(`/api/trace/${encodeURIComponent(DOC_NAME)}/${d.job}`, { cache: 'no-store' }), st = await g.json().catch(() => ({ status: 'error', error: `서버 응답 ${g.status}` }))
        if (st.status === 'run') { say({ done: st.done || 0, total: st.total || 6 }); continue }
        if (st.status !== 'done') throw new Error(st.error || '베끼지 못했어요')
        res = st.result; break
      }
      const m = R.current.model, z0 = topZ(m.items) + 1, g = 'g' + newId(), pen = sticky.current.color
      const its = fromEcad({ items: res.items }).items.map((it, i) => ({ ...base([0, 0], {}), ...it, _id: it._id, z: z0 + i, group_id: g, layer_id: null,
        ...(it.type === 'sarrow' || it.type === 'text' ? { color: pen } : { pen }), ...(it.label ? { label: { ...it.label, color: pen } } : null) }))   // 색 = 지금 펜(SVG 넣기와 같게 — 다크에서도 보이게)
      if (!its.length) throw new Error('그림에서 도면으로 옮길 것을 못 찾았어요')
      const placed = moveItems(its, its.map(it => it._id), at.x, at.y)
      commit([...m.items, ...placed], placed.map(it => it._id), '도면으로 베끼기')
      sayLater(`도면으로 베낌 — 도형 ${placed.length}개 묶음 · ${Math.round(res.elapsed || 0)}초${res.credits != null ? ` · ${res.credits}크레딧` : ''} — 선 하나씩 고치려면 묶음 풀기(Ctrl+Shift+G)`)
    } catch (err) { setStatus(`베끼기 실패 — ${err.message || err}`) } finally { setPend(ps => ps.filter(q => q.id !== pid)) }
  }
  async function ocrImage(id) {
    const img0 = R.current.model.items.find(it => it._id === id); if (!img0?.data) return
    const alt = (img0.alt || '').split('\n'), fromPdf = / · \d+쪽$/.test(alt[0]) && alt.length > 1
    let text = fromPdf ? alt.slice(1).join('\n') : '', foot = fromPdf ? alt[0] : ''
    if (!fromPdf) {
      setStatus('그림 속 글 읽는 중… (KAIROS)')
      const pid = newId(), ib0 = sceneBox(img0, textBox), s0 = 1 / R.current.cam.z
      setPend(ps => [...ps, { id: pid, kind: 'ocr', label: '그림 속 글 읽는 중', x: ib0.x + ib0.w + 40 * s0, y: ib0.y, w: MEMO.W * s0, h: 150 * s0, n: 5 }])
      try {
        const r = await fetch('/api/ocr', { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() }, body: JSON.stringify({ data: img0.data }) })
        const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
        if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
        text = d.text || ''; foot = `그림 속 글 · ${d.model}`
      } catch (err) { setStatus(`글 읽기 실패 — ${err.message || err}`); return } finally { setPend(ps => ps.filter(q => q.id !== pid)) }
    }
    if (!text.trim()) { setStatus('그림에서 읽을 글이 없어요'); return }
    const m = R.current.model, img = m.items.find(it => it._id === id); if (!img) return
    const s = +(1 / R.current.cam.z).toPrecision(2), lines = [...text.split(/\n+/).filter(t => t.trim()).map(t => ({ k: 'p', t: t.trim() })), { k: 'p', t: foot, runs: [[0, foot.length, MUTED, false]] }]
    let memo = base([0, 0], { type: 'memo', rect: [0, 0, MEMO.W, 40], fill: '#ffffffff', lines, scale: s, z: topZ(m.items) + 1 })
    memo = { ...memo, rect: [0, 0, MEMO.W, memoHeight(memo)] }
    const ib = sceneBox(img, textBox), mw = MEMO.W * s, mh = memo.rect[3] * s
    const at = nearSpot({ x: ib.x + ib.w + 40 * s + mw / 2, y: ib.y + mh / 2 }, hitPool().map(it => sceneBox(it, textBox)), mw, mh, { pad: 24 * s, step: 24 * s })
    memo = { ...memo, pos: [at.x, at.y] }
    commit([...m.items, memo], [memo._id], '그림 속 글')
    setStatus(`그림 속 글 → 메모 ${lines.length - 1}줄${fromPdf ? '(PDF 글 그대로)' : ''}`)
  }
  useEffect(() => {
    const on = e => { if (!readOnly) clipPdf(e.detail) }
    window.addEventListener('mb-pdf-clip', on); return () => window.removeEventListener('mb-pdf-clip', on)
  })
  // 회의록 — 녹음을 서버로(받아쓰기·요약은 서버 뒤 일감, easycad/ai/meeting.py), 그동안 놓을 자리에 「만드는 중」 점선 틀(그리는 과정 보이기 — §8 항목61 ③), 2초마다 확인
  const [pend, setPend] = useState([])
  async function startMeeting(file, at) {
    const id = newId(), say = msg => setPend(ps => ps.map(q => (q.id === id ? { ...q, msg } : q)))
    setPend(ps => [...ps, { id, kind: 'meeting', label: '회의록 만드는 중', x: at.x, y: at.y, w: 2 * MEMO.W + 72, h: 240, msg: `「${file.name}」 올리는 중…` }])
    const done = () => setPend(ps => ps.filter(q => q.id !== id))
    let model = ''; try { model = localStorage.getItem('magic-board-model') || '' } catch { /* 없어도 그만 — 서버 기본 모델 */ }
    try {
      const r = await fetch(`/api/meeting/${encodeURIComponent(DOC_NAME)}${model ? `?model=${encodeURIComponent(model)}` : ''}`, { method: 'POST', body: file,
        headers: { 'Content-Type': file.type || 'application/octet-stream', 'X-File-Name': encodeURIComponent(file.name), ...keyHeaders() } })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      for (;;) {
        await new Promise(ok => setTimeout(ok, 2000))
        const g = await fetch(`/api/meeting/${encodeURIComponent(DOC_NAME)}/${d.job}`, { cache: 'no-store' }), st = await g.json().catch(() => ({ status: 'error', error: `서버 응답 ${g.status}` }))
        if (st.status === 'run') { say(st.msg || '만드는 중…'); continue }
        if (st.status !== 'done') throw new Error(st.error || '회의록을 못 만들었어요')
        done(); insertMeeting(st.result, at, file.name); return
      }
    } catch (err) { done(); setStatus(`회의록 실패 — ${err.message || err}`) }
  }
  // 회의록 놓기 = 「회의 날짜 · 제목」 프레임 안에 요약 메모(결정·할 일 체크·다음 회의) + 전문 메모(말한 사람·시간, 접힘 — 펼치기). 배치는 앱(AI는 내용만)
  function insertMeeting(res, at, fname = '') {
    const m = R.current.model, z = topZ(m.items) + 1, pad = 16, gap = 40, d = new Date(), two = n => String(n).padStart(2, '0')
    const clock = ms => { const s = Math.floor((ms || 0) / 1000); return s >= 3600 ? `${Math.floor(s / 3600)}:${two(Math.floor(s / 60) % 60)}:${two(s % 60)}` : `${two(Math.floor(s / 60))}:${two(s % 60)}` }
    const when = `${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`
    const src = `KAIROS 회의록 · ${fname || '녹음'} · ${Math.round(res.duration || 0)}초 · ${res.model || ''} · ${when}`
    const lines = [{ k: 'h2', t: res.title || '회의' }, ...(res.summary ? [{ k: 'p', t: res.summary }] : []),
      ...(res.decisions?.length ? [{ k: 'h3', t: '결정' }, ...res.decisions.map(t => ({ k: 'ul', t }))] : []),
      ...(res.todos?.length ? [{ k: 'h3', t: '할 일' }, ...res.todos.map(t => ({ k: 'todo', t: `${t.who ? t.who + ' — ' : ''}${t.what}${t.due ? ` (${t.due})` : ''}` }))] : []),
      ...(res.next ? [{ k: 'h3', t: '다음 회의' }, { k: 'p', t: res.next }] : []),
      { k: 'p', t: src, runs: [[0, src.length, MUTED, false]] }]
    let sum = base([at.x + pad, at.y + pad], { type: 'memo', rect: [0, 0, MEMO.W, 40], fill: '#ffffffff', lines, z })
    sum = { ...sum, rect: [0, 0, MEMO.W, memoHeight(sum)] }
    const tl = (res.turns || []).map(t => { const head = `[${clock(t.start_ms)}] ${t.speaker}: `; return { k: 'p', t: head + t.text, runs: [[0, head.length, MUTED, false]] } })
    let full = base([at.x + pad + MEMO.W + gap, at.y + pad], { type: 'memo', rect: [0, 0, MEMO.W, 40], fill: '#fffafafa', lines: [{ k: 'h3', t: `전문 · ${tl.length}구간` }, ...tl], fold: true, z })
    full = { ...full, rect: [0, 0, MEMO.W, memoHeight(full)] }
    const H = Math.max(sum.rect[3], full.rect[3]) + 2 * pad, W = 2 * MEMO.W + gap + 2 * pad
    const fr = base([at.x, at.y], { type: 'frame', rect: [0, 0, W, H], name: `회의 ${when} · ${res.title || ''}`.trim(), no: nextFrameNo(m.items), z: Math.min(0, ...m.items.map(x => x.z ?? 0)) - 1 })
    commit([...m.items, fr, sum, full], [sum._id], '회의록')
    setStatus(`회의록 — ${res.title || '회의'} · ${Math.round(res.duration || 0)}초 녹음${res.credits != null ? ` · ${res.credits}크레딧` : ''}. 전문은 「… 줄 더」를 누르면 펼쳐져요`)
  }
  // 「🎙 회의」 실시간 회의록(2026-10-23) — 마이크 → KAIROS 실시간 받아쓰기(말한 사람 나눔, mic.js) → 놓을 자리 점선 틀에 글이 쌓임 → 「끝내기」 = 서버가 요약만(`/api/meeting/<칠판>/live`)
  // → 파일 회의록과 같은 `insertMeeting`. 받아 적는 글은 문서에 안 넣고(되돌리기·공동작업 저장이 글자마다 쌓임) 이 브라우저(5초)·서버(30초)에 임시 저장 — 창이 닫혀도 다시 열면 「정리하기 · 전문만 · 버리기」
  // meet = { at, s(배율), t0, segs: [{speaker, text, start_ms, end_ms}], part(임시 글), state: 'start'|'listen'|'reconnect'|'stopping'|'saved', err }
  const MEET_KEY = `mb-meet:${DOC_NAME}`
  const [meet, setMeetS] = useState(() => { if (readOnly) return null; try { const d = JSON.parse(localStorage.getItem(MEET_KEY) || 'null'); return d?.segs?.length ? { ...d, part: '', state: 'saved' } : null } catch { return null } })
  const meetRef = useRef(meet), meetStopFn = useRef(null)
  const setMeet = f => { const v = typeof f === 'function' ? f(meetRef.current) : f; meetRef.current = v; setMeetS(v) }
  useEffect(() => { onMeet?.(meet ? meet.state : '') }, [meet?.state])   // eslint-disable-line react-hooks/exhaustive-deps
  // 임시 저장 — 말이 쉬지 않아도 5초마다 이 브라우저에, 30초마다 서버에(`<칠판>.meet.json` — 브라우저·PC가 죽어도 남게, 2026-10-23 사용자: 30분 회의가 날아가는 게 최악).
  // 전엔 「새 글 뒤 3초 조용하면」이라 쉬지 않고 말하면 한 번도 저장 안 됐음
  const meetSaved = useRef({ local: null, srv: null, srvAt: 0 })
  function meetPersist(m, srvNow = false) {
    if (!m?.segs?.length) return
    const d = JSON.stringify({ at: m.at, s: m.s, t0: m.t0, dur: m.dur, segs: m.segs }), k = meetSaved.current
    if (k.local !== m.segs) { k.local = m.segs; try { localStorage.setItem(MEET_KEY, d) } catch { /* 저장 못 해도 받아쓰기는 계속 */ } }
    if (k.srv !== m.segs && (srvNow || Date.now() - k.srvAt >= 30000)) {
      k.srv = m.segs; k.srvAt = Date.now()
      fetch(`/api/meetdraft/${encodeURIComponent(DOC_NAME)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: d }).catch(() => { k.srv = null })   // 서버 없음 = 다음에 다시
    }
  }
  function meetForget() {   // 정리 끝·버리기 = 두 사본 다 지움
    try { localStorage.removeItem(MEET_KEY) } catch { /* 그만 */ }
    meetSaved.current = { local: null, srv: null, srvAt: 0 }
    fetch(`/api/meetdraft/${encodeURIComponent(DOC_NAME)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: '{}' }).catch(() => {})
  }
  useEffect(() => {
    if (!meet || meet.state === 'saved') return
    const t = setInterval(() => meetPersist(meetRef.current), 5000)
    return () => clearInterval(t)
  }, [meet?.state])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {   // 이 브라우저에 없으면 서버 사본 — 다른 PC·브라우저가 죽은 뒤에도 「정리하기 · 전문만 · 버리기」
    if (readOnly || meetRef.current) return
    fetch(`/api/meetdraft/${encodeURIComponent(DOC_NAME)}`, { cache: 'no-store' }).then(r => (r.status === 200 ? r.json() : null)).then(d => {
      if (!d?.segs?.length || meetRef.current) return
      setMeet({ ...d, part: '', state: 'saved' }); setStatus(`받아 적던 회의가 서버에 남아 있어요(${d.segs.length}구간) — 「정리하기」 또는 「전문만」`)
    }).catch(() => {})
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  const [, setTick] = useState(0)
  useEffect(() => { if (meet?.state !== 'listen' && meet?.state !== 'reconnect') return; const t = setInterval(() => setTick(n => n + 1), 1000); return () => clearInterval(t) }, [meet?.state])
  const MEET_W = 2 * MEMO.W + 72, MEET_H = 300
  async function meetStart() {
    if (meetRef.current) return
    const s = +(1 / R.current.cam.z).toPrecision(2), at = spotNear(MEET_W * s, MEET_H * s)
    setMeet({ at, s, t0: Date.now(), segs: [], part: '', state: 'start' })
    setStatus('🎙 회의 — 마이크를 켜는 중…')
    const add = fins => setMeet(m => {
      if (!m || !fins.length) return m
      const segs = m.segs.slice()
      for (const t of fins) {
        const last = segs[segs.length - 1]
        if (last && last.speaker === t.speaker) segs[segs.length - 1] = { ...last, text: last.text + t.text, end_ms: t.end_ms }
        else if (t.text.trim()) segs.push({ speaker: t.speaker, text: t.text.trimStart(), start_ms: t.start_ms, end_ms: t.end_ms })
      }
      return { ...m, segs }
    })
    try {
      meetStopFn.current = await startMic({ headers: keyHeaders(), diarize: true, reconnect: true,
        onTokens: (fins, nons) => { add(fins); const part = nons.map(t => t.text).join(''); setMeet(m => (m && m.part !== part ? { ...m, part } : m)) },
        onState: st => {
          const m = meetRef.current; if (!m) return
          if (st === 'off') { meetStopFn.current = null; if (m.state === 'stopping') meetSummarize(); else setMeet({ ...m, part: '', state: 'saved' }); return }
          if (st !== 'stopping') { setMeet({ ...m, state: st }); if (st === 'listen' && m.state === 'start') setStatus('🎙 회의 받아 적는 중 — 끝나면 「끝내기」') }
        },
        onError: msg => { setMeet(m => (m ? { ...m, err: msg } : m)); setStatus(`회의 — ${msg}`) } })
    } catch (err) { setMeet(null); setStatus(`회의를 시작 못 했어요 — ${err.message || err}`) }
  }
  function meetStop() {   // 「끝내기」 = 남은 말 받고 → 요약 / 이미 멈춘(되살린) 것 = 바로 요약
    const m = meetRef.current; if (!m) return
    if (m.state === 'saved') return meetSummarize()
    setMeet({ ...m, state: 'stopping', dur: Math.round((Date.now() - m.t0) / 1000) })
    if (meetStopFn.current) meetStopFn.current(); else meetSummarize()
  }
  function meetDiscard() {
    try { meetStopFn.current?.() } catch { /* 이미 닫힘 */ }
    meetStopFn.current = null; setMeet(null); meetForget()
    setStatus('받아 적은 회의를 버렸어요')
  }
  function meetRaw() {   // 「전문만」 — 요약 없이 받아 적은 글만 회의록 프레임으로(KAIROS 요약이 계속 안 될 때 탈출구, 2026-10-23)
    const m = meetRef.current; if (!m?.segs.length) return
    const tns = []
    for (const g of m.segs) { const sp = `화자 ${g.speaker || '?'}`, t = (g.text || '').trim(); if (!t) continue
      const last = tns[tns.length - 1]; if (last && last.speaker === sp) last.text += ' ' + t; else tns.push({ speaker: sp, start_ms: g.start_ms || 0, text: t }) }   // 서버 `meeting.turns`와 같게
    const dur = m.dur || Math.round((m.segs[m.segs.length - 1].end_ms || 0) / 1000)
    setMeet(null); meetForget()
    insertMeeting({ title: '회의(요약 없음)', turns: tns, duration: dur }, m.at, '실시간 받아쓰기')
  }
  async function meetSummarize() {
    const m = meetRef.current; if (!m) return
    if (!m.segs.length) { setMeet(null); meetForget(); return setStatus('받아 적은 말이 없어 회의록을 안 만들었어요') }
    const dur = m.dur || Math.round((m.segs[m.segs.length - 1].end_ms || 0) / 1000)
    meetPersist({ ...m, dur }, true)
    setMeet(null)
    const id = newId(), say = msg => setPend(ps => ps.map(q => (q.id === id ? { ...q, msg } : q)))
    setPend(ps => [...ps, { id, kind: 'meeting', label: '회의록 만드는 중', x: m.at.x, y: m.at.y, w: 2 * MEMO.W + 72, h: 240, msg: '요약하는 중…' }])
    const done = () => setPend(ps => ps.filter(q => q.id !== id))
    let model = ''; try { model = localStorage.getItem('magic-board-model') || '' } catch { /* 서버 기본 모델 */ }
    const segments = m.segs.map(g => ({ ...g, speaker: g.speaker ? `Speaker ${g.speaker}` : 'Speaker Unknown' }))
    try {
      const r = await fetch(`/api/meeting/${encodeURIComponent(DOC_NAME)}/live${model ? `?model=${encodeURIComponent(model)}` : ''}`, { method: 'POST',
        headers: { 'Content-Type': 'application/json', ...keyHeaders() }, body: JSON.stringify({ segments, duration: dur }) })
      if (r.status === 404) throw new Error('서버가 옛 버전이에요 — python web/server.py를 다시 켜 주세요')   // 화면만 새것이고 서버는 이 주소 전에 켠 것(2026-10-23 실제로 겪음 — 전엔 「실패 — none」)
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      for (;;) {
        await new Promise(ok => setTimeout(ok, 2000))
        const g = await fetch(`/api/meeting/${encodeURIComponent(DOC_NAME)}/${d.job}`, { cache: 'no-store' }), st = await g.json().catch(() => ({ status: 'error', error: `서버 응답 ${g.status}` }))
        if (st.status === 'run') { say(st.msg || '요약하는 중…'); continue }
        if (st.status !== 'done') throw new Error(st.error || '회의록을 못 만들었어요')
        done(); meetForget()
        insertMeeting(st.result, m.at, '실시간 받아쓰기'); return
      }
    } catch (err) { done(); setMeet({ ...m, dur, part: '', state: 'saved', err: '' }); setStatus(`회의록 실패 — ${err.message || err}. 받아 적은 글은 남아 있어요(「정리하기」로 다시 · 「전문만」 = 요약 없이)`) }
  }
  async function insertWeb(url, where) {   // where = 'near'(「웹」 버튼 — 가운데 먼저·빈자리) | {x,y}(위 막대에서 끌어 놓은 자리) | 없음(붙여넣기·끌어 놓기 = 커서 자리)
    const c = R.current.cam, mp = where && where !== 'near' ? where : R.current.mouse, vw = { x: -c.x / c.z, y: -c.y / c.z, w: size.w / c.z, h: size.h / c.z }
    const at = mp && where !== 'near' && mp.x >= vw.x && mp.x <= vw.x + vw.w && mp.y >= vw.y && mp.y <= vw.y + vw.h ? mp : null
    setStatus(`웹 주소 확인 중… ${siteOf(url)}`)
    const f0 = webCardFields({ url }), t0 = at ? { x: at.x - f0.rect[2] / 2, y: at.y - f0.rect[3] / 2 } : spotNear(f0.rect[2], f0.rect[3]), pid = newId()   // 확인하는 동안 카드 자리에 스켈레톤
    setPend(ps => [...ps, { id: pid, kind: 'web', label: '웹 주소 확인 중', x: t0.x, y: t0.y, w: f0.rect[2], h: f0.rect[3], msg: siteOf(url), n: 3 }])
    const info = await fetchLinkInfo(url).finally(() => setPend(ps => ps.filter(q => q.id !== pid))), f = webCardFields(info), m = R.current.model
    const tl = at ? { x: at.x - f.rect[2] / 2, y: at.y - f.rect[3] / 2 } : spotNear(f.rect[2], f.rect[3])
    const it = base([tl.x, tl.y], { ...f, z: topZ(m.items) + 1 })
    commit([...m.items, it], [it._id], '웹 카드'); setTool('select')
    setStatus(info.frameable ? `웹 카드 — 누르면 안을 조작${info.embed ? '(유튜브는 바로 재생)' : ''}, 위 띠를 끌면 이동` : `웹 카드 — ${siteOf(url)}는 칸 안에 넣기를 막아요. 오른쪽 위 ↗나 두 번 누르기 = 새 탭`)
  }
  // 웹 카드 칸 안 조작 켜기 — 한 번 누르기(2026-10-19 사용자: 두 번 누르고 또 눌러야 재생). 유튜브는 그 클릭으로 바로 재생, 다음 클릭부터는 유튜브가 받음(멈춤 등)
  function webActivate(it) {
    setSel([it._id]); setWebOn(it._id)
    if (isYoutube(it)) playYoutube(it._id)
    setStatus(it.type === 'pdf' ? 'PDF 보는 중 · Alt+끌기 = 그림으로 오려 오기' : it.type === 'doc' ? '인터랙티브 HTML 조작 중 — 바깥을 누르거나 Esc = 끝' : isYoutube(it) ? '재생 — 영상을 누르면 멈춤, 바깥을 누르면 끝' : '웹 카드 안을 조작하는 중 — 바깥을 누르면 끝')
  }
  // 점 p가 놓인 PDF 카드 몸통(위 띠 빼고) — 맨 위 것. 우클릭 메뉴가 「안쪽」인지 가르는 데
  const pdfBodyAt = p => { for (let k = R.current.order.length - 1; k >= 0; k--) { const it = R.current.order[k][0]; if (it.type !== 'pdf' || !it.url) continue
    const q = toLocal(it, p); if (q.x >= it.rect[0] && q.x <= it.rect[0] + it.rect[2] && q.y >= it.rect[1] + WEB_HEAD && q.y <= it.rect[1] + it.rect[3]) return it } return null }
  const webOpenAt = p => { const z = R.current.cam.z; for (let k = R.current.order.length - 1; k >= 0; k--) { const it = R.current.order[k][0]; if (it.type !== 'web' && it.type !== 'doc' && it.type !== 'pdf') continue
    const q = toLocal(it, p), b = openBtnRect(it), pad = 2 / z; if (q.x >= b.x - pad && q.x <= b.x + b.w + pad && q.y >= b.y - pad && q.y <= b.y + b.h + pad) return it } return null }
  // 범례(2026-10-19 사용자: 표 모양 · 자동 갱신 · 「표」 버튼 안) — 줄은 commit이 도면에서 다시 모음, 사람이 적는 건 이름뿐
  function insertLegend() {
    const m = R.current.model, c = R.current.cam, s = +(1 / c.z).toPrecision(2)
    const proto = { type: 'legend', rect: [0, 0, 10, 10], rows: legendEntries(m.items), names: {}, scale: s }, lo = legendLayout(proto), w = lo.w * s, h = lo.h * s
    const view = { x: -c.x / c.z, y: -c.y / c.z, w: size.w / c.z, h: size.h / c.z }, inView = b => b.x < view.x + view.w && b.x + b.w > view.x && b.y < view.y + view.h && b.y + b.h > view.y
    const at = spotNear(w, h)
    const it = base([at.x, at.y], { ...proto, rect: [0, 0, lo.w, lo.h], z: topZ(m.items) + 1 })
    commit([...m.items, it], [it._id], '범례'); setTool('select')
    setStatus(proto.rows.length ? `범례 ${proto.rows.length}줄 — 선을 바꾸면 저절로 따라가요. 이름·모양은 오른쪽 속성 카드에서` : '빈 범례 — 색 있는 선·화살표를 그리면 저절로 채워져요')
  }
  // 범례 줄 하나 — { name } = 이름만, { color·style·width } = 도면 속 그 선 전부 바꿈(2026-10-19 사용자: 드롭다운 one of)
  function legendEdit(id, key, patch) {
    const m = R.current.model
    if (patch.name !== undefined) { commit(m.items.map(it => (it._id === id ? { ...it, names: { ...it.names, [key]: patch.name } } : it)), R.current.sel, '범례 이름', 'lgname' + id + key); return }
    commit(restyleLegendRow(m.items, key, patch), R.current.sel, '범례로 선 바꿈')
  }
  function paste() {
    const c = clip.current; if (!c.items.length) return
    c.seq += 1
    const m = R.current.model, tmp = [...m.items, ...c.items.map(it => ({ ...it, _id: '__clip' + it._id }))]
    const remap = tmp.map(it => (it._id.startsWith('__clip') ? { ...it, _bind1: it._bind1 && '__clip' + it._bind1, _bind2: it._bind2 && '__clip' + it._bind2 } : it))
    const r = duplicate(remap, remap.filter(it => it._id.startsWith('__clip')).map(it => it._id), 20 * c.seq, 20 * c.seq)   // 데스크톱: 붙일 때마다 20씩 비켜서
    commit(r.items.filter(it => !it._id.startsWith('__clip')), r.ids, '붙여넣음')
  }
  // 바깥에서 붙일 자리 — 커서가 지금 화면 안이면 커서, 아니면 화면 가운데(center = 빈자리 찾기)
  function pasteAt() {
    const c = R.current.cam, mp = R.current.mouse, vw = { x: -c.x / c.z, y: -c.y / c.z, w: size.w / c.z, h: size.h / c.z }
    return mp && mp.x >= vw.x && mp.x <= vw.x + vw.w && mp.y >= vw.y && mp.y <= vw.y + vw.h ? mp : { x: vw.x + vw.w / 2, y: vw.y + vw.h / 2, center: true }
  }
  // 바깥 글 붙여넣기(2026-10-21 사용자) → 글자·메모·표 — 모양은 `clipin.js`가 고름. 여럿이면 위아래로 한 묶음, 한 번의 commit = Ctrl+Z 한 번. 붙인 게 없으면 false
  function pasteOutside(text, html, opt = {}) {   // opt = 글 파일 끌어 놓기 { at: 놓은 자리, file: 이름 — 메모 맨 위 줄 }
    const s = +(1 / R.current.cam.z).toPrecision(2), z = topZ(R.current.model.items) + 1   // 지금 배율에서 읽히는 크기(「메모」 버튼과 같게)
    const memo = lines => { const it = base([0, 0], { type: 'memo', rect: [0, 0, MEMO.W, 40], fill: '#ffffffff', lines, scale: s, z }); return { ...it, rect: [0, 0, MEMO.W, memoHeight(it)] } }
    const table = (rows, header) => boardTable(rows, header, s, z)
    const filled = lines => lines.some(l => l.t || l.k === 'hr')   // 표 말고 글이 있나 — 표뿐이면 칠판 진짜 표로(글 파일은 늘 메모 하나)
    let its = [], what = ''
    const plan = !looksMarkdown(text) && htmlPlan(html)   // AI 웹 「복사」 버튼 = 마크다운 글이 먼저, 마우스로 긁은 것 = 꾸밈(html)
    if (plan?.code) { its = [memo(text.replace(/\r\n?/g, '\n').replace(/\n+$/, '').split('\n').map(t => ({ k: 'code', t: t.replace(/\t/g, '    ') })))]; what = '코드' }
    else if (plan) { if (filled(plan.lines)) { its = [memo(plan.lines)]; what = '메모' } else { its = plan.tables.map(t => table(t.rows, t.header)); what = '표' } }   // 글이 있으면 표도 메모 안(clipin이 자리 그대로 줄로)
    else {
      const k = textKind(text)
      if (k === 'empty') return false
      if (k === 'tsv') { its = [table(tsvRows(text), false)]; what = '표' }
      else if (k === 'line') { its = [base([0, 0], { type: 'text', text: text.trim(), color: INK, font: 12, bg: null, scale: s, z })]; what = '글자' }
      else {   // 메모 — 마크다운 표는 메모 안 표 줄(대화창 답 붙이기 `cardItems`와 같게). 표뿐인 글은 칠판 진짜 표로
        const lines = memoFromAnswer(text, ''), tabs = lines.filter(l => l.k === 'table')
        if (!opt.file && tabs.length && !filled(lines)) { its = tabs.map(t => table(t.rows, t.header)); what = '표' }
        else {
          const top = opt.file ? [{ k: 'p', t: opt.file, runs: [[0, opt.file.length, MUTED, false]] }, ...lines] : lines, mm = memo(top)
          its = [top.length > FILE_FOLD_N && opt.file ? { ...mm, fold: true, rect: [0, 0, MEMO.W, memoHeight({ ...mm, fold: true })] } : mm]; what = '메모'
        }
      }
    }
    if (!its.length) return false
    let y = 0
    its = its.map(it => { const o = { ...it, pos: [0, y] }; y += sceneBox(o, textBox).h + 12 * s; return o })
    if (its.length > 1) { const g = 'g' + newId(); its = its.map(it => ({ ...it, group_id: g })) }
    const b = unionBox(its.map(it => sceneBox(it, textBox))), at = opt.at || pasteAt(), tl = at.center ? spotNear(b.w, b.h) : { x: at.x - b.w / 2, y: at.y - b.h / 2 }
    its = its.map(it => ({ ...it, pos: [it.pos[0] + tl.x - b.x, it.pos[1] + tl.y - b.y] }))
    commit([...R.current.model.items, ...its], its.map(it => it._id), '붙여넣음'); setTool('select')
    setStatus(opt.file ? `${opt.file} → ${what}${its.some(it => it.fold) ? ' — 길어서 접어 넣음, 「… 줄 더」를 누르면 펼쳐져요' : ''}` : `${what} 붙여넣음 — 마음에 안 들면 Ctrl+Z`)
    return true
  }

  // 휠 = 커서 기준 확대
  // 고치기 칸 위 휠 클릭 = 칠판 화면 이동(칸이 칠판 svg 밖이라 넘겨받음 — 끄는 동안은 svg가 포인터를 잡음)
  const startPan = useCallback(e => { try { svg.current.setPointerCapture(e.pointerId) } catch { /* 이미 끝난 포인터 */ }
    st.current = { ...st.current, kind: 'pan', right: false, sx: e.clientX, sy: e.clientY, cam: R.current.cam }; setCursor('grabbing') }, [])   // eslint-disable-line
  // 메모 입력 칸도 이걸 부름
  const wheelZoom = useCallback(e => { const r = svg.current.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top
    setCam(c => { const z = Math.min(ZMAX, Math.max(ZMIN, c.z * (e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP))), k = z / c.z; return { z, x: mx - (mx - c.x) * k, y: my - (my - c.y) * k } }) }, [setCam])
  useEffect(() => {
    const el = svg.current
    const onWheel = e => { e.preventDefault(); wheelZoom(e) }
    el.addEventListener('wheel', onWheel, { passive: false }); return () => el.removeEventListener('wheel', onWheel)
  }, [wheelZoom])

  // ── 그리기 차례·화면 밖 빼기 ──
  const hiddenL = useMemo(() => new Set(layersOf(model).filter(l => !l.visible).map(l => l.id)), [model])
  const pageNo = useMemo(() => { const fr = items.filter(it => it.type === 'titleblock' && it.plain && !hiddenL.has(layerIdOf(it))); const mp = new Map()
    readingOrder(fr.map(it => ({ ...sceneBox(it, textBox), id: it._id })), 'rows').forEach((b, i) => mp.set(b.id, i + 1)); orderedFrames(items).forEach((f, i) => mp.set(f._id, i + 1)); return mp }, [items, hiddenL])   // 프레임 = 순서(1..n)   // eslint-disable-line react-hooks/exhaustive-deps
  const order = useMemo(() => drawOrder(items).filter(([it]) => !hiddenL.has(layerIdOf(it))), [items, hiddenL]); R.current.order = order
  const onBoard = useMemo(() => boardMembership(items), [items])
  const routes = useMemo(() => resolveRoutes(items, rectOf), [items])
  const bounds = useMemo(() => items.map(itemBounds), [items])
  const view = { x: -cam.x / cam.z, y: -cam.y / cam.z, w: size.w / cam.z, h: size.h / cam.z }, mg = 40 / cam.z
  const visible = order.filter(([it, i]) => { const b = bounds[i]; return it.type === 'board' || (b.x < view.x + view.w + mg && b.x + b.w > view.x - mg && b.y < view.y + view.h + mg && b.y + b.h > view.y - mg) })
  const editingId = editing?.id
  const asTable = it => (isChart(it) && (it._id === editingId || cellSel?.id === it._id) ? { ...it, chart: undefined } : it)   // 그래프 칸 고치는 중 = 그 자리에서 표로 펼침(밖을 누르면 다시 그래프)

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
    setStylePv(true)
  }
  // 여러 개 선택 틀 — 화살촉까지 감쌈(데스크톱 `_GroupTransform.bbox` = 꼭짓점 + 화살촉 끝, 2026-10-18 사용자와 맞춤)
  const selBoxOf = it => {
    const b = sceneBox(it, textBox); if (it.type !== 'sarrow' && it.type !== 'arrow') return b
    const hs = (selShape(it, textBox).heads || []).flat().map(q => toScene(it, q)); if (!hs.length) return b
    const xs = [b.x, b.x + b.w, ...hs.map(q => q.x)], ys = [b.y, b.y + b.h, ...hs.map(q => q.y)]
    return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) }
  }
  const multiBox = selItems.length > 1 ? unionBox(selItems.map(selBoxOf)) : null
  function multiBoxNow() { const ids = new Set(R.current.sel), its = R.current.model.items.filter(it => ids.has(it._id)); return its.length > 1 ? unionBox(its.map(selBoxOf)) : null }
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
        onPointerDown={e => { if (R.current.stylePv) setStylePv(false); onPointerDown(e) }} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onDoubleClick={onDoubleClick} onContextMenu={e => e.preventDefault()}
        onMouseDown={e => { if (R.current.editing && e.button !== 0) e.preventDefault() }}>
        <g transform={`translate(${cam.x},${cam.y}) scale(${z})`} style={{ '--z': z }}>
          {visible.map(([it0, i]) => [asTable(it0), i]).map(([it, i]) => (it._id === editingId && it.label?.align === 'left' && editing?.kind === 'label' ? <Item key={it._id} it={{ ...it, label: { ...it.label, text: '' } }} idx={i} onBoard={onBoard[i]} route={routes.get(i)} dark={dark} labels="skip" />
            : it._id === editingId && it.type === 'memo' ? <Item key={it._id} it={{ ...it, lines: [] }} idx={i} onBoard={onBoard[i]} route={routes.get(i)} dark={dark} labels="skip" />   // 고치는 메모 = 바탕만(흐린 글자가 투명한 채움 사이로 잔상처럼 비쳤음 — 2026-10-18 사용자)
            : it._id === editingId ? <g key={it._id} opacity={0.15}><Item it={it} idx={i} onBoard={onBoard[i]} route={routes.get(i)} dark={dark} labels="skip" /></g>
            : <Item key={it._id} it={it} idx={i} onBoard={onBoard[i]} route={routes.get(i)} dark={dark} labels="skip" page={pageNo.get(it._id)} web={it.type === 'web' ? (webOn === it._id ? 'on' : it.rect[2] * (it.scale || 1) * z < WEB_SLEEP_PX ? 'sleep' : 'view') : it.type === 'pdf' ? (webOn === it._id ? 'on' : it.rect[2] * (it.scale || 1) * z < WEB_SLEEP_PX ? 'sleep' : 'view') : it.type === 'doc' ? (webOn === it._id ? 'on' : it.rect[2] * (it.scale || 1) * z < WEB_SLEEP_PX ? 'sleep' : 'view') : undefined} />))}
          {/* 화살표 라벨은 모든 선·도형 위에(다른 화살표가 지나가도 안 덮임 — 2026-10-18 사용자 지적) */}
          {visible.map(([it, i]) => (isArrow(it) && (it.labels?.length || it.label) && it._id !== editingId ? <Item key={'lb' + it._id} it={it} idx={i} onBoard={onBoard[i]} route={routes.get(i)} dark={dark} labels="only" /> : null))}
          {pend.map(q => <BoardSkeleton key={'pend' + q.id} q={q} z={z} />)}   {/* 오래 걸리는 일 = 놓일 자리에 회색 틀(skeleton.jsx — 회의록·PDF·글 읽기·베끼기·Deep Mode) */}
          {meet && (() => { const s = meet.s, w = MEET_W * s, h = MEET_H * s, sec = Math.max(0, Math.floor((Date.now() - meet.t0) / 1000)), two = n => String(n).padStart(2, '0')   // 「🎙 회의」 받아 적는 중 — 점선 틀 안에 말한 사람별 글(마지막 줄이 보이게)
            const clk = ms => { const t = Math.floor((ms || 0) / 1000); return `${two(Math.floor(t / 60))}:${two(t % 60)}` }, saved = meet.state === 'saved', who = new Set(meet.segs.map(g => g.speaker)).size
            const head = saved ? `🎙 받아 적던 회의 · ${meet.segs.length}구간` : meet.state === 'start' ? '🎙 마이크 켜는 중…' : meet.state === 'reconnect' ? '🎙 다시 붙는 중…(소리는 모아 두는 중)' : meet.state === 'stopping' ? '🎙 마지막 말 받는 중…' : `🎙 받아 적는 중 · ${two(Math.floor(sec / 60))}:${two(sec % 60)}${who ? ` · ${who}명` : ''}`
            const stop = e => e.stopPropagation(), btn = { all: 'unset', cursor: 'pointer', padding: '2px 10px', borderRadius: 99, fontWeight: 600, fontSize: 12 }
            return <g data-testid="meeting-live" data-state={meet.state}><rect x={meet.at.x} y={meet.at.y} width={w} height={h} rx={10 * s} fill="rgba(218,119,86,.06)" stroke="#da7756" strokeWidth={1.5 / z} strokeDasharray={`${8 / z} ${5 / z}`} pointerEvents="none" />
              <foreignObject x={0} y={0} width={MEET_W} height={MEET_H} transform={`translate(${meet.at.x},${meet.at.y}) scale(${s})`}>
                <div style={{ width: MEET_W, height: MEET_H, boxSizing: 'border-box', padding: '10px 14px', display: 'flex', flexDirection: 'column', gap: 6, font: `400 14px ${APP_FONT}`, color: '#3f3f46' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#da7756', fontWeight: 600 }}><span style={{ flex: 1 }}>{head}</span>
                    {(saved || meet.state === 'listen' || meet.state === 'reconnect') && <button data-testid="meeting-live-end" onPointerDown={stop} onClick={meetStop} style={{ ...btn, background: '#da7756', color: '#fff' }}>{saved ? '정리하기' : '끝내기'}</button>}
                    {saved && <button data-testid="meeting-live-raw" onPointerDown={stop} onClick={meetRaw} title="요약 없이 받아 적은 글만 칠판에" style={{ ...btn, color: '#da7756', border: '1px solid #da7756' }}>전문만</button>}
                    {saved && <button data-testid="meeting-live-drop" onPointerDown={stop} onClick={meetDiscard} style={{ ...btn, color: '#71717a' }}>버리기</button>}</div>
                  <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', justifyContent: 'flex-end', gap: 4, lineHeight: 1.5 }}>
                    {meet.segs.slice(-12).map((g, i) => <div key={i}><span style={{ color: '#a1a1aa' }}>[{clk(g.start_ms)}] 화자 {g.speaker || '?'}: </span>{g.text}</div>)}
                    {meet.part && <div style={{ color: '#a1a1aa' }}>{meet.part}</div>}
                    {!meet.segs.length && !meet.part && <div style={{ color: '#a1a1aa' }}>{meet.state === 'listen' ? '말하면 여기에 받아 적어요 — 끝나면 「끝내기」 = 요약·결정·할 일로 정리' : ''}</div>}
                    {meet.err && <div style={{ color: '#dc2626' }}>{meet.err}</div>}</div></div></foreignObject></g> })()}
          {marks.filter(id => byId.has(id)).map(id => { const b = sceneBox(byId.get(id), textBox), pad = 6 / z   // 찾기 결과에 불 켜기(Ctrl+F — 2026-10-19)
            return <rect key={'find' + id} data-testid="find-mark" pointerEvents="none" x={b.x - pad} y={b.y - pad} width={b.w + 2 * pad} height={b.h + 2 * pad} rx={6 / z} fill="rgba(250,204,21,.12)" stroke="#f59e0b" strokeWidth={2.5 / z} strokeDasharray={`${6 / z} ${4 / z}`} /> })}
          {others.map(o => { const c = personColor(o.id), ids = [...new Set([...(o.sel || []), ...(o.edit ? [o.edit] : [])])].filter(id => byId.has(id))   // 다른 사람이 고른·고치는 도형 = 그 사람 색 테두리 + 이름표(2026-10-19)
            return ids.map(id => { const b = sceneBox(byId.get(id), textBox), pad = 4 / z, fs = 11 / z, tag = o.name + (o.edit === id ? ' 고치는 중' : ''), tw = measure(tag, 11, 'app', 600) / z + 10 / z
              return <g key={o.id + id} data-testid="other-mark" pointerEvents="none"><rect x={b.x - pad} y={b.y - pad} width={b.w + 2 * pad} height={b.h + 2 * pad} rx={4 / z} fill="none" stroke={c} strokeWidth={2 / z} strokeDasharray={o.edit === id ? undefined : `${6 / z} ${3 / z}`} />
                <rect x={b.x - pad} y={b.y - pad - fs * 1.7} width={tw} height={fs * 1.6} rx={3 / z} fill={c} />
                <text x={b.x - pad + 5 / z} y={b.y - pad - fs * 0.9} dominantBaseline="central" fontSize={fs} fontWeight={600} fontFamily={APP_FONT} fill="#fff">{tag}</text></g> }) })}
          {!stylePv && (overlay.rubber?.sub ? selItems.filter(it => !overlay.rubber.hits?.includes(it._id)) : selItems).map(outline)}   {/* Shift 끌기 빼기 = 걸린 것의 파란 띠를 바로 지움(2026-10-18 사용자: 빨강 대신) */}
          {cellSel && byId.get(cellSel.id) && (() => { const t = byId.get(cellSel.id), g = cellRange(cellSel), a = cellRect(t, g.r0, g.c0), b = cellRect(t, g.r1, g.c1)
            return <g transform={transformOf(t)}><rect x={a.x} y={a.y} width={b.x + b.w - a.x} height={b.y + b.h - a.y} fill="rgba(137,180,250,.18)" stroke={BLUE} strokeWidth={2 / z} /></g> })()}
          {!overlay.rubber?.sub && overlay.rubber?.hits?.map(id => byId.get(id)).filter(Boolean).map(preview)}
          {single?.type === 'frame' && !single.locked && !tagEdit && (() => { const b = frameTagBox(single), sz = b.h, x = b.x + b.w + b.fs * 0.3, open = loose === single._id   // 이름표 옆 자물쇠 — 잠김 = 안의 것 같이, 풀림 = 잠깐 틀만
            return <g style={{ cursor: 'pointer' }}><title>{open ? '틀만 옮겨요 — 누르면 다시 같이(고른 게 풀리면 저절로)' : '안의 것과 같이 움직여요 — 누르면 잠깐 틀만 · Alt+끌기도 틀만'}</title>
              <rect x={x} y={b.y} width={sz} height={sz} rx={sz * 0.25} fill={open ? '#da7756' : '#3f3f46'} />
              <g transform={`translate(${x + sz * 0.2},${b.y + sz * 0.16}) scale(${sz * 0.6 / 16})`} fill="none" stroke="#fff" strokeWidth={1.6} strokeLinecap="round">
                <rect x="3.5" y="7" width="9" height="6.5" rx="1" /><path d={open ? 'M5.5 7 V5 a2.5 2.5 0 0 1 5 0' : 'M5.5 7 V5 a2.5 2.5 0 0 1 5 0 V7'} /></g></g> })()}
          {multiBox && !stylePv && <rect x={multiBox.x} y={multiBox.y} width={multiBox.w} height={multiBox.h} fill="none" stroke={BLUE} strokeWidth={1 / z} strokeDasharray={`${4 / z} ${3 / z}`} />}
          {multiBox && !editing && !stylePv && [[multiBox.x, multiBox.y], [multiBox.x + multiBox.w, multiBox.y], [multiBox.x + multiBox.w, multiBox.y + multiBox.h], [multiBox.x, multiBox.y + multiBox.h]].map(([cx, cy], i) =>
            <rect key={'mh' + i} x={cx - HANDLE / 2 / z} y={cy - HANDLE / 2 / z} width={HANDLE / z} height={HANDLE / z} fill="#fff" stroke={BLUE} strokeWidth={1.2 / z} />)}
          {selItems.filter(it => it.locked).map(it => { const b = sceneBox(it, textBox); return <text key={'lk' + it._id} x={b.x + b.w} y={b.y} fontSize={12 / z} fill={BLUE}>🔒</text> })}
          {handles.map(h => (h.pill ? pill(h.key, h.p, h.horizontal, true) : h.bend ? <circle key={h.key} cx={h.p.x} cy={h.p.y} r={HANDLE / 2 / z} fill={BEND_GREEN} stroke="#fff" strokeWidth={1 / z} />
            : h.qc ? <circle key={h.key} cx={h.p.x} cy={h.p.y} r={(HANDLE * (hoverKey === h.key ? 0.75 : 0.45)) / z} fill={QC_BLUE} stroke="#fff" strokeWidth={1 / z} style={{ transition: 'r .12s ease-out' }} />
            : h.round ? <circle key={h.key} cx={h.p.x} cy={h.p.y} r={HANDLE / 2 / z} fill={PEACH} stroke="#fff" strokeWidth={1 / z} />
            : stylePv ? null : <rect key={h.key} x={h.p.x - HANDLE / 2 / z} y={h.p.y - HANDLE / 2 / z} width={HANDLE / z} height={HANDLE / z} fill={BLUE} stroke="#fff" strokeWidth={1 / z} />))}
          {memoHov && !editing && !live && (() => { const it = byId.get(memoHov.id); if (!it || it.type !== 'memo') return null; const b = memoHandleRect(it, memoHov.s), k = z * (it.scale || 1)
            return <g transform={transformOf(it)} style={{ pointerEvents: 'none' }}><rect x={b.x} y={b.y} width={b.w} height={b.h} rx={4 / k} fill="rgba(127,127,127,.16)" />
              {[0, 1, 2].flatMap(r => [0, 1].map(c => <circle key={`${r}${c}`} cx={b.x + b.w * (c ? 0.66 : 0.34)} cy={b.y + b.h * (0.28 + r * 0.22)} r={1.5 / k} fill="#8a8f98" />))}</g> })()}
          {lineSel && !editing && (() => { const it = byId.get(lineSel.id); if (!it || it.type !== 'memo') return null; const rows = memoLayout(it).rows
            return <g transform={transformOf(it)} style={{ pointerEvents: 'none' }}>{selUnits(lineSel).map(([s0, e0]) => { const a = rows[s0]; if (!a) return null
              const bot = rows[e0] ? rows[e0].y - MEMO.GAP / 2 : it.rect[3] - MEMO.PAD + TEXT_MARGIN
              return <rect key={s0} x={it.rect[0] + MEMO.LPAD - 4} y={it.rect[1] + a.y} width={it.rect[2] - MEMO.LPAD - MEMO.PAD + 8} height={bot - a.y} rx={4} fill="rgba(137,180,250,.28)" /> })}</g> })()}
          {overlay.mdrop && (overlay.mdrop.out
            ? <rect x={overlay.mdrop.out.x - 24 / z} y={overlay.mdrop.out.y - 16 / z} width={200 / z} height={34 / z} rx={8 / z} fill="rgba(137,180,250,.12)" stroke={BLUE} strokeWidth={1.5 / z} strokeDasharray={`${5 / z} ${3 / z}`} />
            : (() => { const it = byId.get(overlay.mdrop.id); return it && <g transform={transformOf(it)}><line x1={it.rect[0] + MEMO.LPAD} x2={it.rect[0] + it.rect[2] - MEMO.PAD} y1={overlay.mdrop.y} y2={overlay.mdrop.y} stroke={BLUE} strokeWidth={3 / z / (it.scale || 1)} strokeLinecap="round" /></g> })())}
          {overlay.conn && <polyline points={overlay.conn.map(q => `${q.x},${q.y}`).join(' ')} fill="none" stroke={BLUE} strokeWidth={2 / z} strokeDasharray={`${6 / z} ${4 / z}`} />}
          {portDots}
          {overlay.segPrev && !live && pill('segprev', overlay.segPrev.p, overlay.segPrev.horizontal, false)}
          {overlay.guides?.map((g, i) => {
            const [x1, y1, x2, y2] = g.axis === 'v' ? [g.at, g.from, g.at, g.to] : [g.from, g.at, g.to, g.at], dash = g.role === 'center' ? undefined : `${6 / z} ${4 / z}`
            return <g key={i}><line x1={x1} y1={y1} x2={x2} y2={y2} stroke="rgba(0,0,0,.7)" strokeWidth={3 / z} strokeDasharray={dash} /><line x1={x1} y1={y1} x2={x2} y2={y2} stroke={GUIDE} strokeWidth={1.5 / z} strokeDasharray={dash} /></g>
          })}
          {rb && (() => { const x = Math.min(rb.a.x, rb.b.x), y = Math.min(rb.a.y, rb.b.y), w = Math.abs(rb.b.x - rb.a.x), h = Math.abs(rb.b.y - rb.a.y), win = rb.b.x >= rb.a.x
            const col = win ? RB_BLUE : RB_GREEN
            return <rect x={x} y={y} width={w} height={h} fill={col} fillOpacity={45 / 255} stroke={col} strokeWidth={1 / z} strokeDasharray={win ? undefined : `${4 / z} ${3 / z}`} /> })()}
          {dr && (dr.tool === 'rect' || dr.tool === 'frame' || dr.tool.startsWith('sym:') ? <rect x={Math.min(dr.a.x, dr.b.x)} y={Math.min(dr.a.y, dr.b.y)} width={Math.abs(dr.b.x - dr.a.x)} height={Math.abs(dr.b.y - dr.a.y)} fill="none" stroke={BLUE} strokeWidth={1.5 / z} />
            : dr.tool === 'ellipse' ? <ellipse cx={(dr.a.x + dr.b.x) / 2} cy={(dr.a.y + dr.b.y) / 2} rx={Math.abs(dr.b.x - dr.a.x) / 2} ry={Math.abs(dr.b.y - dr.a.y) / 2} fill="none" stroke={BLUE} strokeWidth={1.5 / z} />
            : dr.tool === 'line' ? (b => <Item it={{ ...base([0, 0], { type: 'line', line: [dr.a.x, dr.a.y, b.x, b.y], ...penOf(false) }), _id: 'draft' }} dark={dark} />)(dr.shift ? snap45(dr.a, dr.b) : dr.b)
            : <Item it={{ ...base([0, 0], { type: 'path', elements: dr.pts.map((q, i) => [i ? 'L' : 'M', q.x, q.y]), ...penOf(false), freehand: true }), _id: 'draft' }} dark={dark} />)}
          {items.filter(it => it.type === 'memo' && it._id !== editingId && !(it.lines || []).some(l => l.t?.trim() || (l.k && l.k !== 'p'))).map(it => { const s = it.scale || 1, p = toScene(it, { x: it.rect[0] + MEMO.LPAD, y: it.rect[1] + MEMO.PAD })   // 빈 메모 = 흐린 안내(편집 화면만 — 내보내기엔 안 나감)
            return <text key={'mh' + it._id} x={p.x} y={p.y + 11 * s} fontSize={11 * s} fill="#9aa0a6" style={{ pointerEvents: 'none', fontFamily: 'Pretendard, sans-serif' }}>치면 바로 써져요</text> })}
          {(() => { const pts = tool === 'polygon' && overlay.poly ? [...overlay.poly, ...(overlay.pcur ? [overlay.pcur] : [])] : tool === 'line' && overlay.lpt ? [overlay.lpt, overlay.pcur || overlay.lpt] : null   // 클릭 배치 중 = 실제 색·굵기로(데스크톱처럼 그려질 모습 그대로)
            const shut = tool === 'polygon' && overlay.poly?.length >= 3 && overlay.pcur === overlay.poly[0]   // 시작점에 붙음 = 누르면 닫힘(포트점 붙음 표시와 같은 채운 원)
            return pts && <><Item it={{ ...base([0, 0], { type: 'polygon', closed: false, pts: pts.map(q => [q.x, q.y]), rect: [0, 0, 0, 0], ...penOf(false), fill: null }), _id: 'draft' }} dark={dark} />
              {shut && <circle data-testid="poly-close" cx={overlay.poly[0].x} cy={overlay.poly[0].y} r={5 / z} fill={BLUE} stroke="#fff" strokeWidth={1.5 / z} />}</> })()}
        </g>
      </svg>
      {lineMenu && <ContextMenu at={lineMenu} onClose={() => setLineMenu(null)} entries={lineMenuEntries(lineMenu)} />}
      {menu && <ContextMenu at={menu} onClose={() => setMenu(null)} entries={(() => {
        const m = R.current.model, ids = R.current.sel, has = ids.length > 0, selIt = m.items.filter(it => ids.includes(it._id)), act = f => () => { setMenu(null); f() }
        const out = []
        const lockedSel = selIt.filter(it => it.locked && !layerLocked(it))   // 고른 것 중 잠긴 것 — 한 번에 풀기(2026-10-25 사용자, 잠긴 레이어의 것은 레이어 카드에서)
        if (lockedSel.length) { const uids = new Set(lockedSel.map(it => it._id)); out.push([`잠금 해제 (${lockedSel.length}개)`, '', act(() => commit(m.items.map(it => (uids.has(it._id) ? { ...it, locked: false } : it)), ids, '잠금 해제'))], '-') }
        if (has && lockedSel.length === selIt.length) {   // 잠긴 것만 고름 = 안 바뀌는 일만(복사·내보내기·정리 문서)
          out.push(['복사', 'Ctrl+C', act(copy)], ['잠금 전환', 'Ctrl+L', act(() => commit(toggleLock(m.items, ids), ids, '잠금'))], '-', ['내보내기…', 'Ctrl+P', act(() => onExportSel?.())])
          if (onAsk) out.push(['정리 문서 만들기 (KAIROS)', '', act(() => onAsk('고른 것을 정리한 문서 한 장으로 만들어 줘', 'report'))])
          return out }
        const pin = menu.pdfIn && m.items.find(it => it._id === menu.pdfIn.id)
        if (pin) { const n = menu.pdfIn.page   // PDF 안쪽 = 내용 메뉴만(틀 메뉴·칠판 메뉴 안 섞음)
          const picked = pdfSelectedText()   // 끌어 고른 글이 있으면 복사도
          return [...(picked ? [['고른 글 복사', 'Ctrl+C', act(() => navigator.clipboard?.writeText(picked))]] : []), [`이 쪽(${n + 1}쪽) 통째로 칠판에`, '', act(() => pdfWholePage(pin._id, n))],
            ['새 탭에서 보기', '', act(() => window.open(`${pin.url}#page=${n + 1}`, '_blank', 'noopener'))], '-', ['넘겨 보기 끝', 'Esc', act(() => setWebOn(null))]] }   // 새 탭 = 원본 전체, 보던 쪽에서 시작
        const csrc = selIt.length <= 2 && clipSourceOf(ids); if (csrc) out.push([`PDF에서 이 쪽(${csrc.page + 1}쪽) 보기`, 'Ctrl+클릭', act(() => goClipSource(csrc))])   // 오려 온 그림(밑 글과 묶음) — 출처
        const card = selIt.length === 1 && ['pdf', 'web', 'doc'].includes(selIt[0].type) ? selIt[0] : null   // 카드(PDF·웹·문서) = 뒤집거나 꾸밀 것이 없음
        if (card?.type === 'pdf' && card.url) out.push(['넘겨 보기', '', act(() => webActivate(card))], ['새 탭에서 보기', '', act(() => window.open(`${card.url}#page=${pdfPageAt(card, 0) + 1}`, '_blank', 'noopener'))], '-')
        else if (selIt.length === 1 && selIt[0].type === 'image' && selIt[0].data) out.push(['그림 속 글 읽기', '', act(() => ocrImage(selIt[0]._id))], ['도면으로 베끼기 (KAIROS)', '', act(() => traceImage(selIt[0]._id))], '-')   // OCR → 옆에 메모 · 베끼기 → 옆에 도형 묶음
        else if (card?.type === 'web' && card.url) out.push(['새 탭에서 열기', '', act(() => window.open(card.url, '_blank', 'noopener'))], '-')
        else if (card?.type === 'doc') out.push(['크게 보기', '', act(() => openDoc(card))], '-')
        if (has) out.push(['복사', 'Ctrl+C', act(copy)], ['잘라내기', 'Ctrl+X', act(() => { copy(); commit(removeItems(m.items, movingSet(ids)), [], '잘라냄') })],
          ['복제', 'Ctrl+D', act(dupSel)],
          ['삭제', 'Del', act(() => commit(removeItems(m.items, movingSet(ids)), [], '지움'))])
        if (!card && (ids.length === 1 || styleClip.current)) { out.push('-'); if (ids.length === 1) out.push(['스타일 복사', 'Ctrl+Alt+C', act(styleCopy)]); if (has && styleClip.current) out.push(['스타일 붙여넣기', 'Ctrl+Alt+V', act(stylePaste)]) }
        if (menu.cell && selIt.length === 1 && selIt[0].type === 'table') {   // 표 칸 — 행·열 넣기·지우기
          const t = selIt[0], { r, c } = menu.cell, op = (o, label) => act(() => commit(m.items.map(x => (x._id === t._id ? tableOp(t, o, r, c) : x)), ids, label))
          out.push('-', ['행 · 열', '', null, [['위에 행 넣기', op('rowAbove', '행 넣기')], ['아래에 행 넣기', op('rowBelow', '행 넣기')], ['왼쪽에 열 넣기', op('colLeft', '열 넣기')], ['오른쪽에 열 넣기', op('colRight', '열 넣기')], '-',
            ['이 행 지우기', op('delRow', '행 지우기'), t.rows <= 1], ['이 열 지우기', op('delCol', '열 지우기'), t.cols <= 1]]])
        }
        if (alignTargets().length >= 2) out.push('-', ['정렬 / 분배', '', null, [['왼쪽 맞춤', act(() => alignSel('left'))], ['가로 가운데', act(() => alignSel('hcenter'))], ['오른쪽 맞춤', act(() => alignSel('right'))], '-',
          ['위쪽 맞춤', act(() => alignSel('top'))], ['세로 가운데', act(() => alignSel('vcenter'))], ['아래쪽 맞춤', act(() => alignSel('bottom'))], '-',
          ['가로 균등 분배', act(() => distributeSel('x')), alignTargets().length < 3], ['세로 균등 분배', act(() => distributeSel('y')), alignTargets().length < 3],
          ['가로 첫 간격 반복', act(() => distributeSel('x', true)), alignTargets().length < 3], ['세로 첫 간격 반복', act(() => distributeSel('y', true)), alignTargets().length < 3]]])
        if (has) {
          out.push('-', ['맨 앞으로 보내기', 'Ctrl+]', act(() => commit(zOrder(m.items, ids, true), ids, '맨 앞으로'))], ['맨 뒤로 보내기', 'Ctrl+[', act(() => commit(zOrder(m.items, ids, false), ids, '맨 뒤로'))],
            ['잠금 전환', 'Ctrl+L', act(() => commit(toggleLock(m.items, ids), ids, '잠금'))])
          if (!card) out.push(['좌우 반전', 'Shift+H', act(() => commit(mirror(m.items, ids, true, textBox), ids, '반전'))], ['상하 반전', 'Shift+V', act(() => commit(mirror(m.items, ids, false, textBox), ids, '반전'))])   // 글 도형을 고른 채 Shift+H/V는 글로 들어가므로 메뉴에도(2026-10-19)
          if (ids.length >= 2) out.push(['그룹', 'Ctrl+G', act(() => commit(groupItems(m.items, ids), ids, '묶음'))])
          if (selIt.some(it => it.group_id)) out.push(['그룹 해제', 'Ctrl+Shift+G', act(() => commit(ungroupItems(m.items, ids), ids, '묶음 풂'))])
          out.push(['레이어로 이동', '', null, layersOf(m).map(l => [l.name, act(() => moveSelToLayer(l.id))])])
          if (selIt.some(it => it.type !== 'titleblock' && it.type !== 'frame')) out.push('-', ['프레임으로 감싸기', 'Ctrl+Alt+G', act(wrapFrame)])
          out.push('-', ['내보내기…', 'Ctrl+P', act(() => onExportSel?.())])
          if (onAsk) out.push(['정리 문서 만들기 (KAIROS)', '', act(() => onAsk('고른 것을 정리한 문서 한 장으로 만들어 줘', 'report'))])   // 「정리해 줘」 ① — 고른 것이 재료
        }
        // 빈 곳 = 붙여넣기만(2026-10-25 사용자: 빈 곳 메뉴는 없어도 됨 — 전체 선택은 Ctrl+A, 칠판 전체 정리 문서는 전체 선택 뒤 우클릭, 도움말은 왼쪽 「?」).
        // 우클릭한 그 자리에 붙는 것이 Ctrl+V와 다른 쓸모라 남김. 붙일 것도 없으면 메뉴를 안 띄움(항목 0개 = ContextMenu가 안 그림)
        if (clip.current?.items?.length) { if (has) out.push('-'); out.push(['붙여넣기', 'Ctrl+V', act(paste)]) }
        return out })()} />}
      {present != null && (() => { const fr = orderedFrames(items.filter(it => !hiddenL.has(layerIdOf(it))))
        return <Presenter frames={fr.map(f => ({ id: f._id, name: f.name, box: sceneBox(f, textBox) }))} order={order.filter(([it]) => it.type !== 'frame' || isDeepPaper(it)).map(([it, i]) => (isDeepPaper(it) ? [deepPaper(it), i] : [it, i]))} onBoard={onBoard} routes={routes}
          start={Math.min(present, fr.length - 1)} dark={dark} onClose={() => setPresent(null)} onAdd={addPenNotes} onUndo={undo} onFlipArrow={() => { const m = R.current.model, a = m.items.filter(it => it.layer_id === PEN_LAYER && it.type === 'sarrow').sort((p, q) => (q.z ?? 0) - (p.z ?? 0))[0]   // 방금(맨 위) 그린 판서 화살표 방향 뒤집기
            if (a) commit(m.items.map(it => (it._id === a._id ? { ...it, pts: [...it.pts].reverse() } : it)), R.current.sel, '화살표 뒤집기') }} onClearNotes={box => { const m = R.current.model, inBox = it => { const b = sceneBox(it, textBox), cx = b.x + b.w / 2, cy = b.y + b.h / 2; return cx >= box.x && cx <= box.x + box.w && cy >= box.y && cy <= box.y + box.h }   // 이 장(프레임) 안 판서만
            const ids = m.items.filter(it => it.layer_id === PEN_LAYER && inBox(it)).map(it => it._id); if (ids.length) commit(removeItems(m.items, ids), R.current.sel, '이 장 판서 지움') }}
          onErase={(p, tol, key) => { const m = R.current.model, hit = topHit(m.items.filter(it => it.layer_id === PEN_LAYER), p, tol, textBox); if (hit) commit(removeItems(m.items, [hit._id]), R.current.sel, '판서 지움', key) }} /> })()}
      {tagEdit && (() => { const it = byId.get(tagEdit); if (!it) return null; const b = frameTagBox(it), o = scr({ x: b.x, y: b.y })   // 프레임 이름표 바로 고치기(치는 대로 — 2026-10-18 사용자)
        return <input key={tagEdit} autoFocus defaultValue={it.name || ''} placeholder="이름" onPointerDown={e => e.stopPropagation()} onChange={e => renameFrame(it._id, e.target.value)}
          onBlur={() => setTagEdit(null)} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter' || e.key === 'Escape') setTagEdit(null) }}
          style={{ position: 'absolute', left: o.x, top: o.y, height: Math.max(20, b.h * cam.z), minWidth: 120, width: Math.max(120, b.w * cam.z + 40), boxSizing: 'border-box', zIndex: 20,
            font: `600 ${Math.max(12, b.fs * cam.z)}px 'Pretendard', sans-serif`, color: '#fff', background: '#3f3f46', border: '1.5px solid #89b4fa', borderRadius: 4, padding: '0 6px', outline: 'none' }} /> })()}
      {(editing => { if (!editing) return null; const it = byId.get(editing.id); if (!it) return null   // armed = 칸만 고른 대기(보이지 않음) — 고치기와 같은 자리·같은 편집기

        const r = cellRect(it, editing.r, editing.c), pts = [[r.x, r.y], [r.x + r.w, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y + r.h]].map(([x, y]) => scr(toScene(it, { x, y })))
        const xs = pts.map(q => q.x), ys = pts.map(q => q.y), h = Math.max(...ys) - Math.min(...ys), txt0 = editing.fresh || editing.armed ? '' : it.cells?.[editing.r]?.[editing.c] || ''   // fresh = 고른 칸에 바로 친 글(엑셀처럼 새로 씀)
        const cs = cellStyle(it, editing.r, editing.c), s = it.scale || 1, pxFor = v => cellFontPx(v, r.w, r.h, cs.bold, cs.px) * s
        // 다른 글과 같은 편집기(부분 색·굵게·형광펜) — Enter 아래·Tab 오른쪽·Esc 취소, 치는 동안 글자 크기도 칸에 맞춰(자동 크기)
        return <TextEditor key={`${editing.id}-cell`} onDone={res => (res ? finishCell(res.text, res.move, res.runs) : finishCell(null, null))}   // 돌려준 다음 칸 내용으로 편집기가 바로 바꿈
          spec={{ cell: true, cellKey: `${editing.r},${editing.c}`, left: Math.min(...xs), top: Math.min(...ys), width: Math.max(...xs) - Math.min(...xs), height: h, px: pxFor(txt0), pxFor, zoom: cam.z, family: 'app', weight: cs.bold ? 700 : 400,
            color: ink(cs.color || '#111111', !!cs.fill), bg: 'var(--mb-editbg)', align: cs.align, text: txt0, runs: editing.fresh || editing.armed ? undefined : it.cell_runs?.[`${editing.r},${editing.c}`], onReady: setLiveEd,
            armed: !!editing.armed, fresh: !!editing.fresh, at: editing.at, onPan: startPan, onWheel: wheelZoom, onArm: () => { const e = { id: editing.id, kind: 'cell', r: editing.r, c: editing.c, fresh: true }; R.current.editing = e; setEditing(e) } }} /> })(editing?.kind === 'cell' ? editing : !editing && cellSel && sel.length === 1 && sel[0] === cellSel.id ? { id: cellSel.id, kind: 'cell', r: cellRange(cellSel).r0, c: cellRange(cellSel).c0, armed: true } : null)}
      {(me => { if (!me) return null; const it = byId.get(me.id); if (!it) return null; const s = it.scale || 1, o = scr(toScene(it, { x: it.rect[0], y: it.rect[1] }))   // armed = 메모만 고른 대기(보이지 않음) — 고치기와 같은 key·같은 자리라 편집기가 그대로 이어 받음
        return <MemoEditor key={it._id} spec={{ left: o.x, top: o.y, width: it.rect[2] * s * cam.z, zoom: s * cam.z, fill: it.fill ? cssColor(it.fill) : '#fff', lines: it.lines, caret: me.caret, at: me.at, armed: !!me.armed, onChange: ls => liveMemo(it._id, ls), onWheel: wheelZoom, onPan: startPan,
          onArm: () => { const ne = { id: it._id, kind: 'memo' }; R.current.editing = ne; setEditing(ne) } }} onDone={finishMemo} /> })(editing ? (editing.kind === 'memo' ? editing : null) : armTarget()?.kind === 'memo' ? armTarget() : null)}
      {(ed => { if (!ed) return null; const s = editSpec(ed); if (!s) return null   // armed = 도형만 고른 대기(보이지 않음) — 고치기와 같은 key라 같은 편집기가 그대로 이어 받음
        return <TextEditor key={ed.id} spec={{ ...s, onReady: setLiveEd, at: ed.at, onPan: startPan, onWheel: wheelZoom, armed: !!ed.armed, fresh: !!ed.fresh,
          onArm: () => { const ne = { id: ed.id, kind: ed.kind, fresh: true }; R.current.editing = ne; setEditing(ne) } }} onDone={finishEdit} /> })(editing ? (editing.kind !== 'cell' && editing.kind !== 'memo' ? editing : null) : (t => (t?.kind === 'memo' ? null : t))(armTarget()))}   {/* 메모 대기는 위 MemoEditor가 받음(둘이 같이 뜨면 이 편집기가 첫 글자를 가로챘음) */}
      {editing && liveEd && <FormatBar ed={liveEd} />}   {/* 드래그 꾸미기 막대(2026-10-19 — 옛 오른쪽 위 「글자」 카드 대신) */}
      {selItems.length > 0 && <Props deep={deepProps()} liveEd={editing && !editing.armed && editing.kind !== 'memo' ? liveEd : null} align={selItems.length >= 2 ? { n: alignTargets().length, align: alignSel, dist: a => distributeSel(a) } : null} items={selItems} kind={selArrows.length && selArrows.every(x => arrowKindOf(x) === arrowKindOf(selArrows[0])) ? arrowKindOf(selArrows[0]) : null} set={setProps} rotate={(it, a) => rotateTo(it, a, false)} library={library ? { symbols: library, folders: libFolders } : null} onSwapTo={swapShape} dark={dark} onLegend={legendEdit} cells={cellSel && byId.get(cellSel.id) ? { table: byId.get(cellSel.id), ...cellRange(cellSel) } : null} setCells={setCells}
        onKind={k => { stickyKind.current = k; const m = R.current.model; commit(m.items.map(x => (selArrowIds.has(x._id) ? swapArrowKind(x, k, m.items, rectOf, sticky.current.curve_r) : x)), sel, '화살표 종류') }} />}
    </div>
  )
})

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
    case 'rect': if (it.radius) { const [x, y, w, h] = it.rect; return { d: roundRectD(x, y, w, h, rr(it)), closed: true } } return { d: rectD(...it.rect), closed: true, box: it.rect }
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
