// 직접 만드는 Magic Board 웹 칠판(§8 항목61 「바뀐 결정」, 2026-10-17) — 1단계 뼈대: 무한 칠판(휠 확대·끌어 이동), .ecad 열기·저장(파일·서버), 모든 종류 그리기.
// 화면 틀(사용자 선택): 위 막대는 데스크톱처럼 아이콘 밑 짧은 이름, 칠판 위 떠 있는 카드(2단계~), 오른쪽 KAIROS 대화창(4단계).
// 이동·확대는 데스크톱과 같게 — 휠 = 1.15배씩 커서 기준, 가운데 버튼 끌기 = 이동(1단계는 빈 곳 왼쪽 끌기도 이동, 2단계에서 범위 선택으로).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Item } from './render.jsx'
import { resolveRoutes } from './arrows.js'
import { DOC_NAME, boardMembership, docBounds, drawOrder, emptyDoc, itemBounds, loadServerDoc, parseDoc, saveServerDoc } from './doc.js'

const ZOOM_STEP = 1.15, ZMIN = 0.02, ZMAX = 40
const C = { bar: '#f4f4f5', group: '#e9e9ec', ink: '#27272a', muted: '#71717a', accent: '#da7756', board: '#ffffff', line: '#e4e4e7' }
const SAMPLES = [['모든 종류', '/samples/all_types.ecad'], ['보드 샘플', '/samples/paper_board.ecad'], ['login_flow', '/_local/login_flow.ecad'], ['1TV 계통도', '/_local/1TV_계통도_시험.ecad']]

function useSize(ref) {
  const [s, set] = useState({ w: 1, h: 1 })
  useEffect(() => { const ro = new ResizeObserver(([e]) => set({ w: e.contentRect.width, h: e.contentRect.height })); ro.observe(ref.current); return () => ro.disconnect() }, [ref])
  return s
}

// 위 막대 버튼 — 아이콘 밑 짧은 이름(데스크톱 첫 화면 원칙)
const Btn = ({ icon, label, onClick, title, disabled }) => (
  <button onClick={onClick} title={title || label} disabled={disabled} style={{ all: 'unset', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.35 : 1,
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, padding: '4px 8px', borderRadius: 6, minWidth: 40,
    font: "500 11px 'Pretendard', sans-serif", color: C.ink }}
    onMouseEnter={e => { if (!disabled) e.currentTarget.style.background = 'rgba(218,119,86,.16)' }} onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}>
    <span style={{ fontSize: 16, lineHeight: '18px' }}>{icon}</span>{label}
  </button>
)
const Group = ({ children }) => <div style={{ display: 'flex', gap: 2, background: C.group, borderRadius: 8, padding: 2 }}>{children}</div>

function App() {
  const [doc, setDoc] = useState(emptyDoc())
  const [cam, setCam] = useState({ x: 0, y: 0, z: 1 })   // 화면 = 칠판 × z + (x, y)
  const [status, setStatus] = useState('')
  const [server, setServer] = useState(false)
  const box = useRef(null), size = useSize(box), file = useRef(null), drag = useRef(null)

  const fit = useCallback((items, s = size) => {
    const b = docBounds(items); if (!b) return
    const pad = 40, z = Math.min(ZMAX, Math.max(ZMIN, Math.min((s.w - 2 * pad) / Math.max(b.w, 1), (s.h - 2 * pad) / Math.max(b.h, 1), 1)))
    setCam({ z, x: s.w / 2 - (b.x + b.w / 2) * z, y: s.h / 2 - (b.y + b.h / 2) * z })
  }, [size])

  const open = useCallback((d, how) => { setDoc(d); fit(d.items); setStatus(`${how} · ${d.items.length}개`) }, [fit])

  // 시험·자체확인용 손잡이(Playwright가 카메라를 데스크톱 화면과 같은 자리에 맞출 때)
  useEffect(() => { window.__mb = { setCam, getCam: () => cam, open: async u => open(parseDoc(await (await fetch(u)).text()), u), doc } })

  // 처음: 서버에 이 칠판이 있으면 연다
  useEffect(() => { loadServerDoc().then(r => { setServer(r.server); if (r.doc) open(r.doc, `서버 「${DOC_NAME}」`); else setStatus(r.server ? `서버 「${DOC_NAME}」 · 새 칠판` : '서버 없음 — 파일로 열고 저장') }) }, [])   // eslint-disable-line

  // 휠 = 커서 기준 확대(데스크톱 1.15배)
  useEffect(() => {
    const el = box.current
    const onWheel = e => {
      e.preventDefault()
      const r = el.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top
      setCam(c => { const z = Math.min(ZMAX, Math.max(ZMIN, c.z * (e.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP))), k = z / c.z; return { z, x: mx - (mx - c.x) * k, y: my - (my - c.y) * k } })
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, [])

  const onPointerDown = e => {
    if (e.button !== 1 && e.button !== 0) return
    e.currentTarget.setPointerCapture(e.pointerId)
    drag.current = { x: e.clientX, y: e.clientY, cam }
  }
  const onPointerMove = e => { const d = drag.current; if (!d) return; setCam({ ...d.cam, x: d.cam.x + e.clientX - d.x, y: d.cam.y + e.clientY - d.y }) }
  const onPointerUp = () => { drag.current = null }

  // 그리는 차례·보드 소속·화면 밖 빼기(큰 도면 속도)
  const order = useMemo(() => drawOrder(doc.items), [doc])
  const onBoard = useMemo(() => boardMembership(doc.items), [doc])
  const bounds = useMemo(() => doc.items.map(itemBounds), [doc])
  const routes = useMemo(() => resolveRoutes(doc.items), [doc])   // 「자동 길」 화살표는 열 때 다시 꺾음(데스크톱과 같게)
  const view = { x: -cam.x / cam.z, y: -cam.y / cam.z, w: size.w / cam.z, h: size.h / cam.z }
  const visible = order.filter(([it, i]) => { const b = bounds[i], m = 40 / cam.z; return it.type === 'board' || (b.x < view.x + view.w + m && b.x + b.w > view.x - m && b.y < view.y + view.h + m && b.y + b.h > view.y - m) })

  const saveFile = () => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(doc, null, 1)], { type: 'application/json' }))
    a.download = `${DOC_NAME}.ecad`; a.click(); URL.revokeObjectURL(a.href)
  }
  const saveServer = async () => setStatus((await saveServerDoc(doc).catch(() => false)) ? `서버 「${DOC_NAME}」에 저장함` : '서버 저장 실패')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: C.board, font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', background: C.bar, borderBottom: `1px solid ${C.line}` }}>
        <Group>
          <Btn icon="📂" label="열기" onClick={() => file.current.click()} />
          <Btn icon="💾" label="저장" onClick={server ? saveServer : saveFile} title={server ? `서버 「${DOC_NAME}」에 저장` : '.ecad로 내려받기'} />
          <Btn icon="⬇" label="내려받기" onClick={saveFile} title=".ecad 파일로 내려받기" />
        </Group>
        <Group>
          <Btn icon="⤢" label="전체" onClick={() => fit(doc.items)} title="전체 보기" />
          <Btn icon="1:1" label="100%" onClick={() => setCam(c => ({ z: 1, x: size.w / 2 - (size.w / 2 - c.x) / c.z, y: size.h / 2 - (size.h / 2 - c.y) / c.z }))} />
        </Group>
        <select onChange={async e => { const u = e.target.value; e.target.value = ''; if (!u) return; try { open(parseDoc(await (await fetch(u)).text()), u.split('/').pop()) } catch (err) { setStatus('샘플 열기 실패: ' + err.message) } }}
          defaultValue="" style={{ font: "500 12px 'Pretendard', sans-serif", padding: '4px 6px', borderRadius: 6, border: `1px solid ${C.line}` }}>
          <option value="">샘플 열기…</option>{SAMPLES.map(([n, u]) => <option key={u} value={u}>{n}</option>)}
        </select>
        <span style={{ marginLeft: 'auto', color: C.muted, fontSize: 12 }}>{status} · {Math.round(cam.z * 100)}%</span>
        <input ref={file} type="file" accept=".ecad,application/json" hidden onChange={async e => {
          const f = e.target.files?.[0]; e.target.value = ''; if (!f) return
          try { open(parseDoc(await f.text()), f.name) } catch (err) { setStatus('열기 실패: ' + err.message) }
        }} />
      </div>
      <div ref={box} style={{ flex: 1, position: 'relative', overflow: 'hidden', cursor: drag.current ? 'grabbing' : 'default', touchAction: 'none' }}
        onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onAuxClick={e => e.preventDefault()}>
        <svg width={size.w} height={size.h} style={{ display: 'block' }} data-testid="board">
          <g transform={`translate(${cam.x},${cam.y}) scale(${cam.z})`}>
            {visible.map(([it, i]) => <Item key={i} it={it} idx={i} onBoard={onBoard[i]} route={routes.get(i)} />)}
          </g>
        </svg>
      </div>
    </div>
  )
}

await document.fonts.load("400 16px 'Pretendard'", '가A').catch(() => {})
createRoot(document.getElementById('root')).render(<App />)
