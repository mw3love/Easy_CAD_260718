import { createRoot } from 'react-dom/client'
import { Tldraw, createShapeId, AssetRecordType } from 'tldraw'
import 'tldraw/tldraw.css'
import { TITLE, CARDS, BOARD, CARD_POS, CARD_SIZE, FIG } from './board.js'

const rich = runs => ({ type: 'doc', content: [{ type: 'paragraph', content:
  runs.map(([t, b]) => (b ? { type: 'text', text: t, marks: [{ type: 'bold' }] } : { type: 'text', text: t })) }] })

function build(editor) {
  if (editor.getCurrentPageShapeIds().size) return     // 저장된 것 있으면 그대로(다시 열기 시험)
  const frame = createShapeId('board')
  editor.createShape({ id: frame, type: 'frame', x: BOARD.x, y: BOARD.y, props: { w: BOARD.w, h: BOARD.h, name: '한 장 보드' } })
  editor.createShape({ type: 'text', parentId: frame, x: 80, y: 70,
    props: { richText: rich([[TITLE, true]]), font: 'sans', size: 'xl', autoSize: true } })
  const ids = CARDS.map((runs, i) => {
    const id = createShapeId('card' + i)
    editor.createShape({ id, type: 'geo', parentId: frame, x: CARD_POS[i][0], y: CARD_POS[i][1],
      props: { geo: 'rectangle', w: CARD_SIZE[0], h: CARD_SIZE[1], richText: rich(runs), font: 'sans', size: 'm',
        fill: 'semi', color: i === 2 ? 'orange' : 'blue', align: 'start', verticalAlign: 'middle' } })
    return id
  })
  const asset = AssetRecordType.createId('fig')
  editor.createAssets([{ id: asset, type: 'image', typeName: 'asset', meta: {},
    props: { name: 'figure.svg', src: '/figure.svg', w: 320, h: 200, mimeType: 'image/svg+xml', isAnimated: false } }])
  editor.createShape({ type: 'image', parentId: frame, x: FIG.x, y: FIG.y, props: { assetId: asset, w: FIG.w, h: FIG.h } })
  for (let i = 0; i < 2; i++) {
    const a = createShapeId('arrow' + i)
    editor.createShape({ id: a, type: 'arrow', parentId: frame, x: 0, y: 0, props: { start: { x: 0, y: 0 }, end: { x: 10, y: 0 } } })
    for (const [term, to] of [['start', ids[i]], ['end', ids[i + 1]]])
      editor.createBinding({ type: 'arrow', fromId: a, toId: to,
        props: { terminal: term, normalizedAnchor: { x: 0.5, y: 0.5 }, isExact: false, isPrecise: false } })
  }
  editor.zoomToFit()
}

createRoot(document.getElementById('root')).render(
  <>
    <style>{`.tl-container{--tl-font-sans:'Pretendard',sans-serif}`}</style>
    <Tldraw persistenceKey="bakeoff-tldraw" onMount={e => { window.editor = e; build(e) }} />
  </>)
