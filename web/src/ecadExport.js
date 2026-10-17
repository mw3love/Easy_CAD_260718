// 웹 칠판 → .ecad(데스크톱 Magic Board가 여는 JSON). 읽는 쪽: easycad/fileio/document.py `dict_to_item`·`insert_items`.
// 색·크기는 화면에 실제로 그리는 값(tldraw 표시값 — .ecad에서 온 것은 meta.ecad, 웹에서 새로 그린 것은 tldraw 색표)을 쓴다.
// 아직 안 옮기는 것(세어서 알려 줌): 회전, 메모지·프레임 등 tldraw 전용 도형, 곡선 화살표의 휨.
import { cssToArgb, parseD, richTextToRuns } from './ecadFormat.js'

const PT = 96 / 72, QT_TEXT_MARGIN = 4
const GEO_TO = { rectangle: ['rect'], ellipse: ['ellipse'], diamond: ['symbol', 'decision'], rhombus: ['symbol', 'data'],
  'rhombus-2': ['symbol', 'data'], hexagon: ['symbol', 'prep'], oval: ['symbol', 'terminal'], triangle: ['symbol', 'triangle'] }

function displayValues(editor, shape) {
  const util = editor.getShapeUtil(shape), o = util.options
  if (!o?.getDefaultDisplayValues) return {}
  const theme = editor.getCurrentTheme(), mode = 'light'   // 파일은 늘 밝은 종이 기준(데스크톱이 화면 테마에 맞춰 바꿔 그림)
  return { ...o.getDefaultDisplayValues(editor, shape, theme, mode), ...o.getCustomDisplayValues(editor, shape, theme, mode) }
}
const argb = (c, fallback = '#ff1f1f1f') => cssToArgb(c) ?? fallback
const common = (pos, z) => ({ pos, scale: 1.0, rotation: 0.0, z, origin: [0, 0], locked: false, group_id: null, layer_id: null })

function labelDict(rt, dv) {
  const { text, runs } = richTextToRuns(rt)
  if (!text.trim()) return null
  const d = { text, color: argb(dv.labelColor), font: Math.round((dv.labelFontSize || 22) / PT), bg: null }
  if (runs.length) d.runs = runs
  if (String(dv.labelFontFamily || '').includes('Pretendard')) d.family = 'Pretendard'
  return d
}

async function pngBase64(editor, assetId) {
  const asset = editor.getAsset(assetId), src = asset?.props?.src
  if (!src) return null
  if (src.startsWith('data:image/png;base64,')) return src.slice(22)
  // 데스크톱은 그림을 PNG로만 읽는다 → 브라우저에서 PNG로 다시 굽기
  const img = new Image(); img.crossOrigin = 'anonymous'; img.src = src
  await img.decode()
  const c = document.createElement('canvas'); c.width = img.naturalWidth || asset.props.w; c.height = img.naturalHeight || asset.props.h
  c.getContext('2d').drawImage(img, 0, 0, c.width, c.height)
  return c.toDataURL('image/png').slice(22)
}

export async function exportEcad(editor, ids = null) {
  const shapes = editor.getCurrentPageShapesSorted().filter(s => !ids || ids.includes(s.id))
  const items = [], indexOf = new Map(), skipped = {}, pending = []
  const skip = t => { skipped[t] = (skipped[t] || 0) + 1 }
  for (const s of shapes) {
    const z = items.length * 0.001   // 칠해지는 순서 그대로(데스크톱은 저장 순서 + z)
    const pageT = editor.getShapePageTransform(s.id), P = p => pageT.applyToPoint(p)
    const o = P({ x: 0, y: 0 }), pos = [o.x, o.y]
    if (Math.abs(s.rotation) > 1e-3) skip('회전(0도로 저장)')
    let d = null
    const dv = displayValues(editor, s)
    switch (s.type) {
      case 'eboard':
        d = { ...common(pos, -2.5 + z), type: 'board', rect: [0, 0, s.props.w, s.props.h], bg: argb(s.props.bg, '#ffffffff') }; break
      case 'text': {
        const m = s.meta?.ecad || {}, base = m.weight || 400
        const { text, runs } = richTextToRuns(s.props.richText, base)
        const px = (dv.fontSize || 24) * (s.props.scale || 1)
        d = { ...common([o.x - QT_TEXT_MARGIN, o.y - QT_TEXT_MARGIN], z), type: 'text', text, color: argb(m.color ?? dv.color), font: Math.round(px / PT),
          bg: Array.isArray(m.bgRaw) ? m.bgRaw : null }
        if (base >= 700) d.bold = true
        if (base !== 400 && base !== 700) d.weight = base
        if (m.family || String(dv.fontFamily || '').includes('Pretendard')) d.family = 'Pretendard'
        if (runs.length) d.runs = runs
        break
      }
      case 'geo': {
        const [type, kind] = GEO_TO[s.props.geo] || ['rect']
        const m = s.meta?.ecad, fillCss = m ? m.fill : dv.fillColor
        const fill = fillCss && fillCss !== 'transparent' && s.props.fill !== 'none' ? argb(fillCss, null) : null
        const stroke = m ? m.stroke : dv.strokeColor
        d = { ...common(pos, z), type, ...(kind ? { kind } : {}), rect: [0, 0, s.props.w, s.props.h + (s.props.growY || 0)],
          pen: argb(stroke, '#00000000'), width: m ? m.sw : (dv.strokeWidth ?? 2), fill,
          style: stroke === 'transparent' || (m && !m.sw) ? 0 : ({ dashed: 2, dotted: 3 }[s.props.dash] ?? 1) }
        const lab = labelDict(s.props.richText, m?.label ? { ...dv, labelColor: m.label.color } : dv); if (lab) d.label = lab
        break
      }
      case 'esym': {
        const p = s.props, lab = labelDict(p.richText, { labelColor: p.labelColor, labelFontSize: p.labelPx, labelFontFamily: p.labelFamily ? 'Pretendard' : '' })
        if (p.kind === 'path') {
          d = { ...common(pos, z), type: 'path', elements: parseD(p.d, p.w / p.vw, p.h / p.vh), pen: argb(p.stroke, '#00000000'), width: p.sw, style: p.sw ? 1 : 0 }
          if (p.fill && p.fill !== 'transparent') d.fill = argb(p.fill, null)
        } else {
          d = { ...common(pos, z), type: 'symbol', kind: p.kind, rect: [0, 0, p.w, p.h], pen: argb(p.stroke, '#00000000'), width: p.sw,
            fill: p.fill && p.fill !== 'transparent' ? argb(p.fill, null) : null, style: 1 }
          if (lab) d.label = lab
        }
        break
      }
      case 'sarrow': {
        const pts = s.props.pts.map(q => { const r = P(q); return [r.x, r.y] })
        d = { ...common([0, 0], z), type: 'sarrow', pts, color: argb(s.props.color), width: s.props.width, head: true, head_start: false,
          head_scale: 1.0, style: 1, auto_route: true, routing: 'ortho', curve_r: 0.0, route_hints: [] }
        pending.push([d, s.id]); break
      }
      case 'line': {
        const pts = Object.values(s.props.points).sort((a, b) => (a.index < b.index ? -1 : 1)).map(P)
        const pen = argb(dv.strokeColor ?? '#1d1d1d'), width = dv.strokeWidth ?? 2
        d = pts.length === 2
          ? { ...common([0, 0], z), type: 'line', line: [pts[0].x, pts[0].y, pts[1].x, pts[1].y], pen, width, style: 1 }
          : { ...common([0, 0], z), type: 'path', elements: pts.map((p, i) => [i ? 'L' : 'M', p.x, p.y]), pen, width, style: 1 }
        break
      }
      case 'draw': case 'highlight': {
        const g = editor.getShapeGeometry(s), vs = g.vertices?.map(P) || []
        if (vs.length < 2) { skip(s.type); break }
        d = { ...common([0, 0], z), type: 'path', elements: vs.map((p, i) => [i ? 'L' : 'M', p.x, p.y]), pen: argb(dv.strokeColor ?? '#1d1d1d'),
          width: dv.strokeWidth ?? 2, style: 1, freehand: true }
        break
      }
      case 'arrow': {
        const g = editor.getShapeGeometry(s), vs = g.vertices || []
        if (vs.length < 2) { skip(s.type); break }
        const a = P(vs[0]), b = P(vs[vs.length - 1])
        d = { ...common([0, 0], z), type: 'arrow', p1: [a.x, a.y], p2: [b.x, b.y], ctrl1: null, ctrl2: null, color: argb(dv.strokeColor ?? '#1d1d1d'),
          width: dv.strokeWidth ?? 2, head: s.props.arrowheadEnd !== 'none', head_start: s.props.arrowheadStart !== 'none', head_scale: 1.0, style: 1 }
        if (s.props.bend) skip('곡선 화살표 휨')
        break
      }
      case 'image': {
        const data = await pngBase64(editor, s.props.assetId)
        if (!data) { skip('image'); break }
        d = { ...common(pos, z), type: 'image', rect: [0, 0, s.props.w, s.props.h], data }; break
      }
      default: skip(s.type)
    }
    if (d) {
      const keep = s.meta?.keep
      if (keep) {
        const { _type, closed, ...rest } = keep
        if (_type === 'polygon' && d.type === 'path') {   // 다각형은 다각형으로(데스크톱에서 꼭짓점 편집이 되게)
          const [px, py] = d.pos   // 경로 요소는 pos 기준, 다각형 pts는 아이템 좌표(pos 0) — 원본 .ecad와 같은 꼴로
          const pts = d.elements.filter(e => e[0] !== 'C').map(e => [e[1] + px, e[2] + py])
          if (closed && pts.length > 1 && pts[0][0] === pts.at(-1)[0] && pts[0][1] === pts.at(-1)[1]) pts.pop()
          const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]), x0 = Math.min(...xs), y0 = Math.min(...ys)
          const { elements, ...dd } = d
          d = { ...dd, pos: [0, 0], type: 'polygon', closed, rect: [x0, y0, Math.max(...xs) - x0 || 1, Math.max(...ys) - y0 || 1], pts, fill: d.fill ?? null }
          void elements
        }
        Object.assign(d, rest)
      }
      indexOf.set(s.id, items.length); items.push(d)
    }
  }
  // 직각 화살표 연결: 붙은 도형의 저장 순번 + 그 도형 안 부착점(변 가운데)
  for (const [d, id] of pending) {
    for (const [k, terminal] of [['bind1', 'start'], ['bind2', 'end']]) {
      const b = editor.getBindingsFromShape(id, 'sarrow').find(x => x.props.terminal === terminal)
      const to = b && indexOf.get(b.toId), bb = b && editor.getShapePageBounds(b.toId)
      if (to == null || !bb) { Object.assign(d, { [k]: null, [k + '_group']: null, [k + '_pt']: null }); continue }
      const local = { left: [0, bb.h / 2], right: [bb.w, bb.h / 2], top: [bb.w / 2, 0], bottom: [bb.w / 2, bb.h] }[b.props.side]
      Object.assign(d, { [k]: to, [k + '_group']: null, [k + '_pt']: local })
    }
  }
  return { doc: { format: 'easycad-doc', version: 1, items }, skipped }
}

export async function downloadEcad(editor, name = 'board') {
  const { doc, skipped } = await exportEcad(editor)
  const blob = new Blob([JSON.stringify(doc, null, 1)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = `${name}.ecad`; a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
  return { count: doc.items.length, skipped }
}
