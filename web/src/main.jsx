// Magic Board 웹 칠판 — 2026-10-17 §8 항목61 ⓑ 칠판 바탕.
// tldraw 5.5.2(버전 고정) 위에 .ecad 도형(shapes.jsx)·CAD 층(cad.jsx: 직각 화살표·큐닷·TRIM)을 얹는다.
import { useRef } from 'react'
import { createRoot } from 'react-dom/client'
import { Tldraw } from 'tldraw'
import 'tldraw/tldraw.css'
import { QcDotOverlayUtil, SArrowBindingUtil, SArrowUtil, TrimTool, reroute } from './cad.jsx'
import { importEcad } from './ecad.js'
import { shapeUtils, textOptions } from './shapes.jsx'

// 지금 화면 가운데에 .ecad를 연다(문서 안 자리 관계는 그대로)
async function openEcad(editor, text) {
  const doc = JSON.parse(text)
  const c = editor.getViewportPageBounds().center
  const res = importEcad(editor, doc, { x: c.x, y: c.y })
  editor.select(...res.ids.filter(id => !editor.getShape(id)?.parentId?.startsWith('shape:')))
  editor.zoomToSelection({ animation: { duration: 200 } })
  editor.selectNone()
  return res
}

function TopBar() {
  const file = useRef(null)
  const ed = () => window.editor
  const btn = { font: "600 13px 'Pretendard', sans-serif", padding: '6px 12px', border: '1px solid #d4d4d8', borderRadius: 8, background: '#fff', cursor: 'pointer' }
  return (
    <div style={{ position: 'fixed', left: 320, top: 8, zIndex: 1000, display: 'flex', gap: 6 }}>
      <button style={btn} onClick={() => file.current.click()}>.ecad 열기</button>
      <button style={btn} onClick={async () => openEcad(ed(), await (await fetch('/samples/paper_board.ecad')).text())}>보드 샘플</button>
      <button style={btn} onClick={() => ed().setCurrentTool('trim')}>TRIM</button>
      <input ref={file} type="file" accept=".ecad,application/json" hidden onChange={async e => {
        const f = e.target.files?.[0]; if (!f) return
        const res = await openEcad(ed(), await f.text()); e.target.value = ''
        window.lastImport = res
      }} />
    </div>
  )
}

const fontsReady = Promise.all(['400', '600', '700', '800'].map(w => document.fonts.load(`${w} 16px Pretendard`, '가A'))).catch(() => {})

await fontsReady
createRoot(document.getElementById('root')).render(
  <>
    <style>{`.tl-container{--tl-font-sans:'Pretendard',sans-serif}`}</style>
    <TopBar />
    <Tldraw
      persistenceKey="magic-board"
      cameraOptions={{ wheelBehavior: 'zoom' }}
      shapeUtils={[...shapeUtils, SArrowUtil]}
      bindingUtils={[SArrowBindingUtil]}
      overlayUtils={[QcDotOverlayUtil]}
      tools={[TrimTool]}
      textOptions={textOptions}
      onMount={e => {
        window.editor = e
        window.openEcad = t => openEcad(e, t)
        // 묶이지 않은 상자(장애물)가 움직여도 화살표 길을 다시 찾는다 — 상자 크기·자리가 바뀐 경우만
        e.sideEffects.registerAfterChangeHandler('shape', (prev, next) => {
          if ((next.type === 'geo' || next.type === 'esym') && (prev.x !== next.x || prev.y !== next.y || prev.props.w !== next.props.w || prev.props.h !== next.props.h))
            for (const a of e.getCurrentPageShapes()) if (a.type === 'sarrow') reroute(e, a.id)
        })
      }}
    />
  </>
)
