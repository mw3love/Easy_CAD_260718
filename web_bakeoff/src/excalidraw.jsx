import { createRoot } from 'react-dom/client'
import { Excalidraw, convertToExcalidrawElements } from '@excalidraw/excalidraw'
import '@excalidraw/excalidraw/index.css'
import { TITLE, CARDS, plain, BOARD, CARD_POS, CARD_SIZE, FIG } from './board.js'

// Excalidraw 글은 한 덩어리 글꼴·굵기 — 부분 굵게가 없어 **표시**로 대신 남긴다(비교 항목)
const KEY = 'bakeoff-excalidraw'
function initial() {
  try { const s = JSON.parse(localStorage.getItem(KEY)); if (s?.elements?.length) return s } catch {}
  const els = [
    { type: 'frame', id: 'board', x: BOARD.x, y: BOARD.y, width: BOARD.w, height: BOARD.h, name: '한 장 보드', children: [] },
    { type: 'text', x: 80, y: 70, text: TITLE, fontSize: 40, fontFamily: 2, frameId: 'board' },
    ...CARDS.map((runs, i) => ({ type: 'rectangle', id: 'card' + i, x: CARD_POS[i][0], y: CARD_POS[i][1],
      width: CARD_SIZE[0], height: CARD_SIZE[1], roughness: 0, roundness: { type: 3 }, frameId: 'board',
      backgroundColor: i === 2 ? '#ffd8a8' : '#d0ebff', fillStyle: 'solid', strokeColor: '#1e2b45',
      label: { text: plain(runs), fontSize: 22, fontFamily: 2, textAlign: 'left' } })),
    ...[0, 1].map(i => ({ type: 'arrow', x: CARD_POS[i][0] + CARD_SIZE[0], y: CARD_POS[i][1] + 90, width: 60, height: 0,
      roughness: 0, frameId: 'board', start: { id: 'card' + i }, end: { id: 'card' + (i + 1) } })),
  ]
  return { elements: convertToExcalidrawElements(els), files: {} }
}
async function addFigure(api) {
  if (api.getSceneElements().some(e => e.type === 'image')) return
  const svg = await (await fetch('/figure.svg')).text()
  const dataURL = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svg)))
  api.addFiles([{ id: 'fig', dataURL, mimeType: 'image/svg+xml', created: Date.now() }])
  const [img] = convertToExcalidrawElements([{ type: 'image', fileId: 'fig', x: FIG.x, y: FIG.y, width: FIG.w, height: FIG.h, frameId: 'board' }])
  api.updateScene({ elements: [...api.getSceneElements(), { ...img, status: 'saved' }] })
  api.scrollToContent(undefined, { fitToContent: true })
}
const init = initial()
createRoot(document.getElementById('root')).render(
  <div style={{ height: '100%' }}>
    <Excalidraw initialData={{ ...init, scrollToContent: true }}
      excalidrawAPI={api => { window.api = api; setTimeout(() => addFigure(api), 300) }}
      onChange={(elements, _s, files) => { try { localStorage.setItem(KEY, JSON.stringify({ elements, files })) } catch {} }} />
  </div>)
