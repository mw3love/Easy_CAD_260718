// .ecad(데스크톱 Magic Board 문서, JSON) → 웹 칠판 도형. 형식 원본: easycad/fileio/document.py `item_to_dict`.
// 아직 안 옮기는 것(세어서 알려 줌): 표·표제란·번호표, 회전·배율, TRIM 자국(cuts), 포트, 화살표 라벨.
import { AssetRecordType, createShapeId, toRichText } from 'tldraw'
import { getIndices } from '@tldraw/utils'
import { reroute } from './cad.jsx'
import { bgCss, cssColor, pathD, runsToRichText } from './ecadFormat.js'

const PT = 96 / 72                         // Qt 글자 pt → 화면 px(96dpi)
const QT_TEXT_MARGIN = 4                   // QGraphicsTextItem 문서 여백

const KEEP = ['pb_part', 'pb_card', 'pb_piece', 'ai', 'set', 'page', 'group_id', 'layer_id', 'locked', 'labels', 'cuts', 'ports', 'head_start', 'head_scale']
const J = o => JSON.parse(JSON.stringify(o))   // tldraw meta는 순수 JSON만(undefined 금지)
const labelMeta = l => l && { color: cssColor(l.color), px: (l.font || 12) * PT, family: !!l.family }
const DASH = st => (st === 2 ? 'dashed' : st === 3 ? 'dotted' : st === 4 || st === 5 ? 'dashed' : 'solid')   // Qt 펜 모양 → tldraw 선
const GEO_OF = { decision: 'diamond', data: 'rhombus', prep: 'hexagon' }   // tldraw 기본 상자로 같은 모양이 나오는 심볼

export function importEcad(editor, doc, at = { x: 0, y: 0 }) {
  const items = doc.items || []
  const order = items.map((it, i) => [it, i]).sort((a, b) => (a[0].z ?? 0) - (b[0].z ?? 0) || a[1] - b[1])
  const idOf = new Map(), skipped = {}, boards = []
  const skip = t => { skipped[t] = (skipped[t] || 0) + 1 }
  // 문서 전체를 at 기준으로 옮겨 놓는다(보드가 여러 개여도 서로 자리는 그대로)
  editor.run(() => {
    for (let [it, idx] of order) {
      const [px, py] = it.pos || [0, 0], X = px + at.x, Y = py + at.y
      const r = it.rect || [0, 0, 0, 0]
      const id = createShapeId()
      const base = { id, x: X + r[0], y: Y + r[1], meta: {} }
      const label = it.label
      if (it.style === 0) it = { ...it, pen: null, width: 0 }   // Qt 펜 모양 0 = 선 없음(보드 형광펜 띠 등)
      switch (it.type) {
        case 'board':
          editor.createShape({ ...base, type: 'eboard', props: { w: r[2], h: r[3], bg: cssColor(it.bg) || '#ffffff' } })
          boards.push(id); break
        case 'text': {
          const color = cssColor(it.color)
          editor.createShape({ id, type: 'text', x: X + QT_TEXT_MARGIN, y: Y + QT_TEXT_MARGIN,
            props: { richText: runsToRichText(it.text || '', it.runs, it.weight ?? (it.bold ? 700 : 400)), autoSize: true, textAlign: 'start', font: 'sans' },
            meta: { ecad: J({ color, px: (it.font || 12) * PT, weight: it.weight ?? (it.bold ? 700 : 400), family: !!it.family, bg: it.bg ? bgCss(it.bg) : null, bgRaw: it.bg ?? null }) } })
          break
        }
        case 'rect': case 'ellipse': {
          editor.createShape({ ...base, type: 'geo', props: { geo: it.type === 'rect' ? 'rectangle' : 'ellipse', w: r[2], h: r[3], dash: DASH(it.style), fill: 'solid', font: 'sans',
            richText: toRichText(label?.text || '') },
            meta: { ecad: J({ stroke: cssColor(it.pen) || 'transparent', fill: cssColor(it.fill), sw: it.width ?? 1, label: labelMeta(label) }) } })
          break
        }
        case 'symbol': {
          const meta = { stroke: cssColor(it.pen) || 'transparent', fill: cssColor(it.fill), sw: it.width ?? 1, label: labelMeta(label) }
          const rt = label ? runsToRichText(label.text || '', label.runs) : toRichText('')
          if (GEO_OF[it.kind]) editor.createShape({ ...base, type: 'geo', props: { geo: GEO_OF[it.kind], w: r[2], h: r[3], dash: DASH(it.style), fill: 'solid', font: 'sans', richText: rt }, meta: { ecad: J(meta) } })
          else editor.createShape({ ...base, type: 'esym', props: { w: r[2], h: r[3], kind: it.kind, stroke: meta.stroke, fill: meta.fill || 'transparent',
            sw: meta.sw, richText: rt, labelColor: meta.label?.color || '#1f1f1f', labelPx: meta.label?.px || 16, labelFamily: !!meta.label?.family } })
          break
        }
        case 'path': case 'polygon': {
          const elems = it.type === 'path' ? it.elements : it.pts.map((p, i) => [i ? 'L' : 'M', p[0], p[1]]).concat(it.closed ? [['L', it.pts[0][0], it.pts[0][1]]] : [])
          if (!elems?.length) { skip(it.type); break }
          const P = pathD(elems), stroke = cssColor(it.pen) || 'transparent', fill = cssColor(it.fill) || 'transparent'
          const pos = { x: X + P.x0, y: Y + P.y0 }   // 다각형 pts도 이미 아이템 좌표(rect 위치 포함 — local_pts())
          if (P.isRect) editor.createShape({ id, ...pos, type: 'geo', props: { geo: 'rectangle', w: P.w, h: P.h, dash: 'solid', fill: 'solid' },
            meta: { ecad: J({ stroke: it.width ? stroke : 'transparent', fill, sw: it.width || 0 }) } })
          else editor.createShape({ id, ...pos, type: 'esym', props: { w: P.w, h: P.h, kind: 'path', d: P.d, vw: P.w, vh: P.h, stroke, fill, sw: it.width ?? 1 } })
          break
        }
        case 'line': {
          const [x1, y1, x2, y2] = it.line, idx2 = getIndices(2)
          editor.createShape({ id, type: 'line', x: X + x1, y: Y + y1, props: { dash: 'solid',
            points: { [idx2[0]]: { id: idx2[0], index: idx2[0], x: 0, y: 0 }, [idx2[1]]: { id: idx2[1], index: idx2[1], x: x2 - x1, y: y2 - y1 } } } })
          break
        }
        case 'image': {
          const asset = AssetRecordType.createId()
          editor.createAssets([{ id: asset, type: 'image', typeName: 'asset', meta: {},
            props: { name: 'image.png', src: 'data:image/png;base64,' + it.data, w: r[2], h: r[3], mimeType: 'image/png', isAnimated: false } }])
          editor.createShape({ ...base, type: 'image', props: { assetId: asset, w: r[2], h: r[3] } })
          break
        }
        case 'sarrow': {
          const pts = it.pts.map(([x, y]) => ({ x: X + x, y: Y + y })), o = pts[0]
          editor.createShape({ id, type: 'sarrow', x: o.x, y: o.y, props: { pts: pts.map(p => ({ x: p.x - o.x, y: p.y - o.y })),
            color: cssColor(it.color) || '#1e2b45', width: Math.max(1.5, it.width ?? 2) } })
          break
        }
        default: skip(it.type); continue
      }
      idOf.set(idx, id)
      // 웹이 쓰지 않는 데스크톱 값(AI 보드 설계서·보드 칸 표시·레이어·그룹·잠금·화살표 라벨·다각형 여부)은 그대로 들고 다니다가 내보낼 때 돌려준다
      const keep = Object.fromEntries(KEEP.filter(k => it[k] != null && it[k] !== false).map(k => [k, it[k]]))
      if (it.type === 'polygon') Object.assign(keep, { _type: 'polygon', closed: !!it.closed })
      if (Object.keys(keep).length) { const sh = editor.getShape(id); editor.updateShape({ id, type: sh.type, meta: { ...sh.meta, keep: J(keep) } }) }
    }
    // 화살표 지속 연결: bind1/bind2 = 저장 목록 순번, bindN_pt = 그 도형 안 부착점 → 가장 가까운 변
    for (const [it, idx] of order) {
      if (it.type !== 'sarrow' || !idOf.has(idx)) continue
      for (const [k, terminal] of [['bind1', 'start'], ['bind2', 'end']]) {
        const to = idOf.get(it[k]); if (to == null || !editor.getShape(to)) continue
        const b = editor.getShapePageBounds(to), [lx, ly] = it[k + '_pt'] || [b.w / 2, b.h / 2]
        const dist = { left: lx, right: b.w - lx, top: ly, bottom: b.h - ly }
        const side = Object.keys(dist).reduce((a, c) => (dist[c] < dist[a] ? c : a))
        editor.createBinding({ type: 'sarrow', fromId: idOf.get(idx), toId: to, props: { terminal, side } })
      }
    }
    // 보드 안에 가운데가 들어간 것은 보드 소속으로(데스크톱 "소속은 위치로"와 같음)
    for (const bid of boards) {
      const bb = editor.getShapePageBounds(bid)
      const inside = [...idOf.values()].filter(id => id !== bid && !boards.includes(id) && (() => {
        const sb = editor.getShapePageBounds(id); return sb && bb.containsPoint(sb.center)
      })())
      if (inside.length) editor.reparentShapes(inside, bid)
    }
  })
  return { count: idOf.size, skipped, ids: [...idOf.values()] }
}

export { reroute, cssColor, runsToRichText }
