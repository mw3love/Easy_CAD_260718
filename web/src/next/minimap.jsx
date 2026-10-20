// 우하 「미니맵」 카드 — 데스크톱 `_MinimapView`·`_build_minimap_panel`: 문서 전체를 작게(바뀌면 0.15초 몰아서 한 번 다시 그림), 지금 보는 범위 = 네모(즉시 따라감),
// 누르거나 끌면 그 자리가 화면 가운데로. 제목 줄 = 미니맵 · − · % · ＋(% 누르면 전체 보기 — 2026-10-18 사용자 선택, 「전체」·1:1 버튼은 뺌. 100%는 휠로).
// 보는 범위 네모 = 데스크톱과 같은 고정 시안 #22d3ee 테두리만. 데스크톱은 실제 그림을 축소하지만, 웹은 9천 개 도면에서도 가볍게 도형 윤곽만 캔버스에 그린다(보드는 바탕색 면).
import { useEffect, useRef } from 'react'
import { FoldBtn, useFold } from './fold.jsx'
import { docBounds, itemBounds } from './doc.js'
import { cssColor } from '../ecadFormat.js'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)' }
const W = 172, H = Math.round(W * 9 / 16)
export const ZOOM_STEP = 1.15, ZMIN = 0.02, ZMAX = 40

// 미니맵 배율 — 내용 상자 + 여백(데스크톱 `_padded_bounds`: 긴 변 6% + 12), 비율 유지·가운데
function fitOf(items) {
  const b = docBounds(items); if (!b) return null
  const pad = Math.max(b.w, b.h) * 0.06 + 12, x = b.x - pad, y = b.y - pad, w = b.w + 2 * pad, h = b.h + 2 * pad
  const k = Math.min(W / w, H / h); return { k, ox: (W - w * k) / 2 - x * k, oy: (H - h * k) / 2 - y * k }
}

function draw(ctx, items, f, dark) {
  ctx.clearRect(0, 0, W, H); if (!f) return
  const P = (x, y) => [x * f.k + f.ox, y * f.k + f.oy]
  ctx.lineWidth = 1; ctx.strokeStyle = dark ? 'rgba(220,226,235,.75)' : 'rgba(40,48,60,.7)'
  for (const it of items) {
    const [px, py] = it.pos || [0, 0], s = it.scale || 1, L = (x, y) => P(px + x * s, py + y * s)
    ctx.beginPath()
    if (it.type === 'sarrow' || (it.type === 'polygon' && it.pts)) { it.pts.forEach(([x, y], i) => ctx[i ? 'lineTo' : 'moveTo'](...L(x, y))); if (it.closed) ctx.closePath(); ctx.stroke(); continue }
    if (it.type === 'arrow') { ctx.moveTo(...L(...it.p1)); ctx.lineTo(...L(...it.p2)); ctx.stroke(); continue }
    if (it.type === 'line') { ctx.moveTo(...L(it.line[0], it.line[1])); ctx.lineTo(...L(it.line[2], it.line[3])); ctx.stroke(); continue }
    if (it.type === 'path') { for (const e of it.elements) { if (e.length >= 3) ctx[e[0] === 'M' ? 'moveTo' : 'lineTo'](...L(e[e.length - 2], e[e.length - 1])) } ctx.stroke(); continue }
    const b = itemBounds(it), [x, y] = P(b.x, b.y), w = Math.max(1, b.w * f.k), h = Math.max(1, b.h * f.k)
    if (it.type === 'board') { ctx.fillStyle = cssColor(it.bg) || '#ffffff'; ctx.fillRect(x, y, w, h); continue }
    if (it.type === 'text' || it.type === 'image' || it.type === 'web' || it.type === 'doc' || it.type === 'memo' || it.type === 'legend') { ctx.fillStyle = dark ? 'rgba(220,226,235,.35)' : 'rgba(40,48,60,.28)'; ctx.fillRect(x, y, w, h); continue }
    if (it.type === 'ellipse') { ctx.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2); ctx.stroke(); continue }
    if (it.fill) { ctx.fillStyle = cssColor(it.fill); ctx.fillRect(x, y, w, h) }
    ctx.strokeRect(x, y, w, h)
  }
}

// items = 보이는 도형(숨긴 레이어 뺌), cam·size = 큰 화면, setCam, onFit = 전체 보기
export function Minimap({ items, cam, size, setCam, onFit, dark }) {
  const [folded, toggleFold] = useFold('minimap')
  const cv = useRef(null), fitRef = useRef(null)
  useEffect(() => {   // 내용이 바뀌면 0.15초 몰아서 한 번(데스크톱 `_REBUILD_DEBOUNCE_MS`)
    const t = setTimeout(() => { fitRef.current = fitOf(items); const c = cv.current; if (c) draw(c.getContext('2d'), items, fitRef.current, dark) }, 150)
    return () => clearTimeout(t)
  }, [items, dark])
  const f = fitRef.current || fitOf(items)
  // 지금 보는 범위(칠판 좌표) → 미니맵 네모
  const view = f && { x: (-cam.x / cam.z) * f.k + f.ox, y: (-cam.y / cam.z) * f.k + f.oy, w: (size.w / cam.z) * f.k, h: (size.h / cam.z) * f.k }
  const goTo = e => { const fr = fitRef.current || f; if (!fr) return; const r = cv.current.getBoundingClientRect()
    const sx = ((e.clientX - r.left) - fr.ox) / fr.k, sy = ((e.clientY - r.top) - fr.oy) / fr.k
    setCam(c => ({ ...c, x: size.w / 2 - sx * c.z, y: size.h / 2 - sy * c.z })) }
  const zoomBy = k => setCam(c => { const z = Math.min(ZMAX, Math.max(ZMIN, c.z * k)), q = z / c.z; return { z, x: size.w / 2 - (size.w / 2 - c.x) * q, y: size.h / 2 - (size.h / 2 - c.y) * q } })
  // 버튼처럼 보이게 — 옅은 바탕 + 테두리(2026-10-18 사용자: %·전체가 버튼인지 몰랐음)
  const hb = { all: 'unset', boxSizing: 'border-box', cursor: 'pointer', height: 20, minWidth: 20, padding: '0 4px', marginLeft: 3, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 4, border: `1px solid ${C.line}`, background: 'var(--mb-seg)', color: C.ink, font: "600 11px 'Pretendard', sans-serif" }
  return <div data-folded={folded || undefined} onPointerDown={e => e.stopPropagation()} style={{ position: 'absolute', right: 'calc(12px + var(--mb-right-inset, 0px))', bottom: 12, width: 192, boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10,
    padding: '6px 10px 10px', boxShadow: '0 2px 8px rgba(0,0,0,.06)', color: C.ink, userSelect: 'none' }}>
    <div style={{ display: 'flex', alignItems: 'center', marginBottom: folded ? 0 : 4 }}>
      <span style={{ font: "700 15px 'Pretendard', sans-serif", flex: 1 }}>미니맵</span>
      <button title="축소" onClick={() => zoomBy(1 / ZOOM_STEP)} style={hb}>−</button>
      <button title="다 보기 — 칠판 전체가 보이게(Z)" onClick={onFit} style={{ ...hb, minWidth: 38 }}>{Math.round(cam.z * 100)}%</button>
      <button title="확대" onClick={() => zoomBy(ZOOM_STEP)} style={hb}>＋</button><FoldBtn folded={folded} onClick={toggleFold} />
    </div>
    <div style={{ position: 'relative', width: W, height: H, borderRadius: 4, overflow: 'hidden', background: 'var(--mb-board, transparent)', outline: `1px solid ${C.line}`, cursor: 'pointer' }}
      onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); goTo(e) }} onPointerMove={e => { if (e.buttons & 1) goTo(e) }}>
      <canvas ref={cv} width={W} height={H} style={{ display: 'block' }} />
      {view && <div style={{ position: 'absolute', left: view.x, top: view.y, width: view.w, height: view.h, border: '2px solid #22d3ee', pointerEvents: 'none', boxSizing: 'border-box' }} />}
    </div>
  </div>
}
