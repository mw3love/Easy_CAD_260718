// 직접 만드는 칠판 — .ecad 아이템을 SVG로 그린다(데스크톱 `core_shapes.py` paint 규칙, 밝은 화면 기준).
// 화면 밝기 규칙: 보드 밖의 흰 잉크(선·글)는 밝은 칠판에서 안 보여 검정으로(데스크톱 PDF 출력과 같은 규칙), 보드 안은 보드 바탕을 따르므로 그대로.
import { memo } from 'react'
import { cssColor, bgCss } from '../ecadFormat.js'
import {
  APP_FONT, BOARD_FONT, METRICS, PT, TEXT_MARGIN, TB_ROWS, bezierAt, bezierSub, colEdges, curveAt, dashArray, headSize, headTriangle,
  itemTransform, labelAnchor, labelInset, paperWH, polylineAt, roundedPath, runsToLines, trimmedPts,
} from './geom.js'
import { symbolPath } from './symbols.js'
import { sarrowRadius } from './arrows.js'

// ── 글자 재기(캔버스) ──
let _ctx = null
const ctx = () => (_ctx ||= document.createElement('canvas').getContext('2d'))
const fontCss = (px, family, weight = 400) => `${weight} ${px}px ${family === 'board' ? BOARD_FONT : APP_FONT}`
export function measure(text, px, family, weight) { const c = ctx(); c.font = fontCss(px, family, weight); return c.measureText(text).width }

// 글 배치 — 줄마다 조각(굵게·색·형광펜) 위치까지. 반환 { lines: [{parts:[{text,x,w,…}], w}], w, h, px, family, weight }
export function layoutText(text, runs, px, family, weight = 400) {
  const lines = runsToLines(text || '', runs).map(parts => {
    let x = 0
    const placed = parts.map(p => { const w = measure(p.text, px, family, p.bold ? Math.max(700, weight) : weight); const o = { ...p, x, w }; x += w; return o })
    return { parts: placed, w: x }
  })
  const m = METRICS[family === 'board' ? 'board' : 'app']
  return { lines, w: Math.max(0, ...lines.map(l => l.w)), h: lines.length * m.lineSpacing * px, px, family, weight, m }
}

// 글 그리기 — (left, top) = 문서 상자 왼쪽 위(여백 포함). color = 기본 글 색
function TextLines({ lay, left, top, color }) {
  const { px, m, family, weight } = lay
  const out = []
  lay.lines.forEach((ln, i) => {
    const base = top + TEXT_MARGIN + m.ascent * px + i * m.lineSpacing * px
    for (const p of ln.parts) if (p.bg) out.push(<rect key={`b${i}-${p.x}`} x={left + TEXT_MARGIN + p.x} y={base - m.ascent * px} width={p.w} height={m.lineSpacing * px} fill={bgCss(p.bg)} />)
    out.push(<text key={`t${i}`} y={base} fontSize={px} fontFamily={family === 'board' ? BOARD_FONT : APP_FONT} fontWeight={weight} fill={color} style={{ whiteSpace: 'pre' }}>
      {ln.parts.map((p, j) => <tspan key={j} x={left + TEXT_MARGIN + p.x} fill={p.color ? cssColor(p.color) : undefined} fontWeight={p.bold ? Math.max(700, weight) : undefined}>{p.text}</tspan>)}
    </text>)
  })
  return out
}

// 잉크 가운데 맞춤 — 한글 글리프 잉크는 기준선 위 0.78em ~ 아래 0.09em(데스크톱 `_ink_center_dy`의 실측 보정과 같은 뜻)
const INK_TOP = 0.78, INK_BOT = 0.09
function centeredBox(lay, a) {
  const ls = lay.m.lineSpacing * lay.px, n = Math.max(1, lay.lines.length)
  const b1 = a.y - ((n - 1) * ls) / 2 + ((INK_TOP - INK_BOT) / 2) * lay.px
  const top = b1 - lay.m.ascent * lay.px - TEXT_MARGIN
  const left = a.x - lay.w / 2 - TEXT_MARGIN
  return { left, top, inkTop: b1 - INK_TOP * lay.px, inkBot: b1 + (n - 1) * ls + INK_BOT * lay.px, w: lay.w + 2 * TEXT_MARGIN }
}

// ── 색 ──
const near = (c, white) => { const m = /^#([0-9a-f]{6})$/i.exec(c || ''); if (!m) return false
  const n = parseInt(m[1], 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255; return white ? r >= 250 && g >= 250 && b >= 250 : false }
export const ink = (c, onBoard) => { const css = cssColor(c); return !onBoard && near(css, true) ? '#1f1f1f' : css }
// Qt QColor.darker(118)/lighter(135) — HSV 명도만
function shade(css, f) {
  const m = /^#([0-9a-f]{6})$/i.exec(css || ''); if (!m) return css
  const n = parseInt(m[1], 16); let [r, g, b] = [n >> 16, (n >> 8) & 255, n & 255]
  const mx = Math.max(r, g, b) || 1, v = Math.min(255, (mx * f)), k = v / mx
  return '#' + [r, g, b].map(c => Math.round(Math.min(255, c * k)).toString(16).padStart(2, '0')).join('')
}
const isDark = css => { const m = /^#([0-9a-f]{6})$/i.exec(css || ''); if (!m) return false; const n = parseInt(m[1], 16); return 0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255) < 128 }

const stroke = (it, onBoard) => (it.style === 0 || !it.pen ? 'none' : ink(it.pen, onBoard))
const strokeProps = (it, onBoard) => ({ stroke: stroke(it, onBoard), strokeWidth: it.width || 1, strokeDasharray: dashArray(it.style, it.width), strokeLinecap: 'round', strokeLinejoin: 'round' })

// ── 도형 안 라벨(한 줄씩, 넘치면 글자를 줄임 — `_fit_label_to_shape`) ──
function CenterLabel({ it, onBoard }) {
  const L = it.label; if (!L?.text) return null
  const [x, y, w] = it.rect, family = L.family ? 'board' : 'app'
  const inner = Math.max(1, w * labelInset(it.type, it.kind))
  let pt = Math.max(5, Math.round(L.font || 16)), lay = layoutText(L.text, L.runs, pt * PT, family)
  while (pt > 5 && lay.w + 2 * TEXT_MARGIN > inner) { pt -= 1; lay = layoutText(L.text, L.runs, pt * PT, family) }
  const a = labelAnchor(it.type, it.kind, it.rect), box = centeredBox(lay, a)
  return <TextLines lay={lay} left={box.left} top={box.top} color={ink(L.color, onBoard || !!it.fill)} />   // 채운 도형 안 글은 도형 바탕을 따름(흰 글 그대로)
}

// 화살표 라벨(경로 위 t + 수직 off, 가운데) — 반환 { el, gap }
function arrowLabels(it, at, onBoard) {
  const labels = it.labels || (it.label ? [it.label] : [])   // 옛 파일은 단수 "label"(데스크톱도 하위호환으로 읽음)
  return labels.filter(L => L.text?.trim()).map((L, i) => {
    const lay = layoutText(L.text, L.runs, (L.font || 16) * PT, L.family ? 'board' : 'app')
    const { p, n } = at(L.t ?? 0.5), off = L.off || 0
    const box = centeredBox(lay, { x: p.x + n.x * off, y: p.y + n.y * off })
    const gap = off ? null : { x: box.left - 2, y: box.inkTop - 7, w: box.w + 4, h: box.inkBot - box.inkTop + 14 }   // 옆으로 뺀 라벨은 선을 안 비움
    return { el: <TextLines key={'l' + i} lay={lay} left={box.left} top={box.top} color={ink(L.color, onBoard)} />, gap }
  })
}
function GapMask({ id, gaps }) {
  return <mask id={id} maskUnits="userSpaceOnUse" x={-1e6} y={-1e6} width={2e6} height={2e6}>
    <rect x={-1e6} y={-1e6} width={2e6} height={2e6} fill="#fff" />
    {gaps.map((g, i) => <rect key={i} x={g.x} y={g.y} width={g.w} height={g.h} fill="#000" />)}
  </mask>
}
const Head = ({ tri, color }) => <polygon points={tri.map(p => `${p.x},${p.y}`).join(' ')} fill={color} stroke={color} strokeWidth={1} strokeLinejoin="round" />

// ── TRIM 자국 있는 상자: 네 변(위·오른쪽·아래·왼쪽 — 데스크톱 `_item_local_edges` 차례)에서 자국 구간을 뺀 선 ──
function cutRectPath([x, y, w, h], cuts) {
  const edges = [[x, y, x + w, y], [x + w, y, x + w, y + h], [x + w, y + h, x, y + h], [x, y + h, x, y]]
  let d = ''
  edges.forEach(([x1, y1, x2, y2], i) => {
    const gaps = cuts.filter(c => c[0] === i).map(c => [Math.min(c[1], c[2]), Math.max(c[1], c[2])]).sort((a, b) => a[0] - b[0])
    let t = 0
    for (const [t0, t1] of [...gaps, [1, 1]]) {
      if (t0 > t) d += `M${x1 + (x2 - x1) * t},${y1 + (y2 - y1) * t} L${x1 + (x2 - x1) * t0},${y1 + (y2 - y1) * t0} `
      t = Math.max(t, t1)
    }
  })
  return d
}

// 포트(도형 테두리에 붙은 작은 상자·원) — 가운데 = 테두리 위 비율 자리
function Ports({ it, onBoard }) {
  const [x, y, w, h] = it.rect
  return (it.ports || []).map((p, i) => {
    const [pw, ph] = p.size || [18, 18], cx = x + p.frac[0] * w, cy = y + p.frac[1] * h
    const sp = { stroke: ink(p.pen, onBoard), strokeWidth: p.width || 1, fill: p.fill ? cssColor(p.fill) : '#ffffff' }   // 빈 포트도 밑의 테두리를 가림(데스크톱과 같게)
    return p.shape === 'circle' ? <ellipse key={i} cx={cx} cy={cy} rx={pw / 2} ry={ph / 2} {...sp} /> : <rect key={i} x={cx - pw / 2} y={cy - ph / 2} width={pw} height={ph} {...sp} />
  })
}

// ── 아이템 하나 ── (memo: 확대·이동만 바뀌면 다시 그리지 않음 — 9천 개 도면에서 휠 한 칸이 340ms였다)
export const Item = memo(function Item({ it, idx, onBoard, route }) {
  const T = itemTransform(it), fill = it.fill ? cssColor(it.fill) : 'none'
  switch (it.type) {
    case 'rect': case 'ellipse': case 'symbol': {
      const [x, y, w, h] = it.rect
      let body
      if (it.type === 'rect') body = it.cuts?.length
        ? <><rect x={x} y={y} width={w} height={h} fill={fill} stroke="none" /><path d={cutRectPath(it.rect, it.cuts)} fill="none" {...strokeProps(it, onBoard)} /></>
        : <rect x={x} y={y} width={w} height={h} fill={fill} {...strokeProps(it, onBoard)} />
      else if (it.type === 'ellipse') body = <ellipse cx={x + w / 2} cy={y + h / 2} rx={w / 2} ry={h / 2} fill={fill} {...strokeProps(it, onBoard)} />
      else { const sp = symbolPath(it.kind, w, h); body = <g transform={`translate(${x},${y})`}><path d={sp.d} transform={sp.transform} fill={fill} {...strokeProps(it, onBoard)} vectorEffect={sp.transform ? 'non-scaling-stroke' : undefined} /></g> }
      return <g transform={T}>{body}<Ports it={it} onBoard={onBoard} /><CenterLabel it={it} onBoard={onBoard} /></g>
    }
    case 'polygon': {
      const pts = it.pts.map(p => p.join(',')).join(' ')
      return <g transform={T}>{it.closed ? <polygon points={pts} fill={fill} {...strokeProps(it, onBoard)} /> : <polyline points={pts} fill="none" {...strokeProps(it, onBoard)} />}
        {it.closed && <CenterLabel it={it} onBoard={onBoard} />}</g>
    }
    case 'path': {
      const d = it.elements.map(e => e[0] + e.slice(1).join(' ')).join(' ')
      return <g transform={T}><path d={d} fill={fill} fillRule="evenodd" {...strokeProps(it, onBoard)} stroke={it.width ? stroke(it, onBoard) : 'none'} /></g>
    }
    case 'line': {
      const [x1, y1, x2, y2] = it.line, L = it.label
      let label = null
      if (L?.text) {   // 선 라벨: 가운데 '위쪽'(문서 상자 아래가 중점보다 4 위)
        const lay = layoutText(L.text, L.runs, (L.font || 16) * PT, L.family ? 'board' : 'app')
        const a = { x: (x1 + x2) / 2, y: (y1 + y2) / 2 }
        label = <TextLines lay={lay} left={a.x - lay.w / 2 - TEXT_MARGIN} top={a.y - 4 - (lay.h + 2 * TEXT_MARGIN)} color={ink(L.color, onBoard)} />
      }
      return <g transform={T}><line x1={x1} y1={y1} x2={x2} y2={y2} {...strokeProps(it, onBoard)} />{label}</g>
    }
    case 'text': {
      const family = it.family ? 'board' : 'app', weight = it.weight ?? (it.bold ? 700 : 400)
      const lay = layoutText(it.text, it.runs, (it.font || 12) * PT, family, weight)
      return <g transform={T}>
        {it.bg && <rect x={0} y={0} width={lay.w + 2 * TEXT_MARGIN} height={lay.h + 2 * TEXT_MARGIN} fill={bgCss(it.bg)} />}
        <TextLines lay={lay} left={0} top={0} color={ink(it.color, onBoard)} />
      </g>
    }
    case 'image': {
      const [x, y, w, h] = it.rect
      return <g transform={T}><image href={'data:image/png;base64,' + it.data} x={x} y={y} width={w} height={h} preserveAspectRatio="none" /></g>
    }
    case 'board': {
      const [x, y, w, h] = it.rect, bg = cssColor(it.bg) || '#ffffff'
      return <g transform={T}><rect x={x} y={y} width={w} height={h} rx={14} ry={14} fill={bg} stroke={isDark(bg) ? shade(bg, 1.35) : shade(bg, 1 / 1.18)} strokeWidth={1.2} /></g>
    }
    case 'badge': {
      const c = cssColor(it.color) || '#da7756'
      return <g transform={T}><circle r={15} fill={c} stroke="#fff" strokeWidth={2} />
        <text y={0} textAnchor="middle" dominantBaseline="central" fontSize={12 * PT} fontWeight={700} fontFamily={APP_FONT} fill="#fff">{it.number}</text></g>
    }
    case 'table': {
      const [x, y, w, h] = it.rect, rows = it.rows, ch = h / rows, edges = colEdges(x, w, it.col_widths || Array(it.cols).fill(1 / it.cols))
      const cells = []
      for (let r = 0; r < rows; r++) for (let c = 0; c < it.cols; c++) {
        const txt = it.cells?.[r]?.[c]; if (!txt) continue
        const cw = edges[c + 1] - edges[c], fs = Math.max(2, Math.min(ch * 0.5, cw * 0.3))
        cells.push(<text key={`${r}-${c}`} x={(edges[c] + edges[c + 1]) / 2} y={y + (r + 0.5) * ch} textAnchor="middle" dominantBaseline="central"
          fontSize={fs} fontWeight={it.header && r === 0 ? 700 : 400} fontFamily={APP_FONT} fill="#111111">{txt}</text>)
      }
      const lines = [...edges.slice(1, -1).map(ex => `M${ex},${y} V${y + h}`), ...Array.from({ length: rows - 1 }, (_, j) => `M${x},${y + (j + 1) * ch} H${x + w}`)]
      return <g transform={T}>{cells}<path d={lines.join(' ')} stroke="#333333" strokeWidth={0.5} fill="none" />
        {it.header && rows > 1 && <path d={`M${x},${y + ch} H${x + w}`} stroke="#333333" strokeWidth={1} />}
        <rect x={x} y={y} width={w} height={h} fill="none" stroke="#333333" strokeWidth={1} /></g>
    }
    case 'titleblock': {
      const [W, H] = paperWH(it.size, it.orient), M = 10, line = '#333333', inkC = '#111111'
      if (it.plain) return <g transform={T}><rect width={W} height={H} fill="none" stroke={line} strokeWidth={0.5} /></g>
      const tbw = Math.min(180, W - 2 * M), tb = { x: W - M - tbw, y: H - M - 33, w: tbw, h: 33 }
      const hW = TB_ROWS.reduce((s, r) => s + r[0], 0), out = []
      let yy = tb.y
      TB_ROWS.forEach(([rw, cells], ri) => {
        const rh = tb.h * (rw / hW), cW = cells.reduce((s, c) => s + c[2], 0)
        if (ri > 0) out.push(<line key={'r' + ri} x1={tb.x} y1={yy} x2={tb.x + tb.w} y2={yy} stroke={line} strokeWidth={0.5} />)
        let xx = tb.x
        cells.forEach(([label, key, cw], ci) => {
          const cwid = tb.w * (cw / cW)
          if (ci > 0) out.push(<line key={`c${ri}-${ci}`} x1={xx} y1={yy} x2={xx} y2={yy + rh} stroke={line} strokeWidth={0.5} />)
          out.push(<text key={`l${ri}-${ci}`} x={xx + 1.2} y={yy + 1.2} dominantBaseline="hanging" fontSize={2.6} fontFamily={APP_FONT} fill={inkC}>{label}</text>)
          const v = it.fields?.[key]
          if (v) out.push(<text key={`v${ri}-${ci}`} x={xx + cwid / 2} y={yy + rh / 2} textAnchor="middle" dominantBaseline="central" fontSize={3.8} fontFamily={APP_FONT} fill={inkC}>{v}</text>)
          xx += cwid
        })
        yy += rh
      })
      return <g transform={T}><rect width={W} height={H} fill="none" stroke={line} strokeWidth={0.5} />
        <rect x={M} y={M} width={W - 2 * M} height={H - 2 * M} fill="none" stroke={line} strokeWidth={1.2} />
        <rect x={tb.x} y={tb.y} width={tb.w} height={tb.h} fill="none" stroke={line} strokeWidth={1.2} />{out}</g>
    }
    case 'sarrow': {
      const pts = (route || it.pts).map(([x, y]) => ({ x, y })), color = ink(it.color, onBoard), size = headSize(it.width, it.head_scale)   // route = 열 때 다시 찾은 길(arrows.js)
      const end = it.head !== false, start = !!it.head_start
      const labels = arrowLabels(it, t => polylineAt(pts, t), onBoard), gaps = labels.map(l => l.gap).filter(Boolean)
      const maskId = gaps.length ? `gap-${idx}` : null
      const tri = (a, b) => headTriangle(b, Math.atan2(b.y - a.y, b.x - a.x), size)
      return <g transform={T}>
        {maskId && <defs><GapMask id={maskId} gaps={gaps} /></defs>}
        <path d={roundedPath(trimmedPts(pts, size, end, start), sarrowRadius(it))} fill="none" stroke={color} strokeWidth={it.width}
          strokeDasharray={dashArray(it.style, it.width)} strokeLinecap="round" strokeLinejoin="round" mask={maskId ? `url(#${maskId})` : undefined} />
        {end && <Head tri={tri(pts[pts.length - 2], pts[pts.length - 1])} color={color} />}
        {start && <Head tri={tri(pts[1], pts[0])} color={color} />}
        {labels.map(l => l.el)}
      </g>
    }
    case 'arrow': {
      const p0 = { x: it.p1[0], y: it.p1[1] }, p3 = { x: it.p2[0], y: it.p2[1] }, color = ink(it.color, onBoard), size = headSize(it.width, it.head_scale)
      const end = it.head !== false, start = !!it.head_start, curved = !!it.ctrl1
      const c1 = curved ? { x: it.ctrl1[0], y: it.ctrl1[1] } : null, c2 = curved ? { x: it.ctrl2[0], y: it.ctrl2[1] } : null
      const at = curved ? t => curveAt(p0, c1, c2, p3, t) : t => polylineAt([p0, p3], t)
      const labels = arrowLabels(it, at, onBoard), gaps = labels.map(l => l.gap).filter(Boolean), maskId = gaps.length ? `gap-${idx}` : null
      let body
      if (!curved) {
        const L = Math.hypot(p3.x - p0.x, p3.y - p0.y) || 1
        const t0 = start ? Math.min(0.9, (size * 0.85) / L) : 0, t1 = end ? Math.max(t0 + 0.05, 1 - (size * 0.85) / L) : 1
        body = `M${p0.x + (p3.x - p0.x) * t0},${p0.y + (p3.y - p0.y) * t0} L${p0.x + (p3.x - p0.x) * t1},${p0.y + (p3.y - p0.y) * t1}`
      } else {   // 곡선: 화살촉 길이만큼 떨어진 곡선 매개변수를 찾아 그 구간만 그림
        const cut = size * 0.85, findT = (from, dir) => { let t = from; for (let i = 0; i < 200; i++) { const q = bezierAt(p0, c1, c2, p3, t); const tip = from === 1 ? p3 : p0; if (Math.hypot(q.x - tip.x, q.y - tip.y) >= cut) return t; t += dir * 0.005 } return from }
        const t0 = start ? findT(0, 1) : 0, t1 = end ? findT(1, -1) : 1
        const [a, b, c, d] = bezierSub(p0, c1, c2, p3, t0, t1)
        body = `M${a.x},${a.y} C${b.x},${b.y} ${c.x},${c.y} ${d.x},${d.y}`
      }
      const angEnd = curved ? Math.atan2(p3.y - c2.y, p3.x - c2.x) : Math.atan2(p3.y - p0.y, p3.x - p0.x)
      const angStart = curved ? Math.atan2(p0.y - c1.y, p0.x - c1.x) : Math.atan2(p0.y - p3.y, p0.x - p3.x)
      return <g transform={T}>
        {maskId && <defs><GapMask id={maskId} gaps={gaps} /></defs>}
        <path d={body} fill="none" stroke={color} strokeWidth={it.width} strokeDasharray={dashArray(it.style, it.width)} strokeLinecap="round" mask={maskId ? `url(#${maskId})` : undefined} />
        {end && <Head tri={headTriangle(p3, angEnd, size)} color={color} />}
        {start && <Head tri={headTriangle(p0, angStart, size)} color={color} />}
        {labels.map(l => l.el)}
      </g>
    }
    default: return null
  }
})
