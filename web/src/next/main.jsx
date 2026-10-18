// 직접 만드는 Magic Board 웹 칠판(§8 항목61 「바뀐 결정」, 2026-10-17).
// 1단계 뼈대(무한 칠판·.ecad 열기/저장·모든 종류 그리기) + 2단계 기본 편집(Editor.jsx).
// 화면 틀(사용자 선택): 위 막대는 데스크톱처럼 아이콘 밑 짧은 이름, 칠판 위 떠 있는 카드(좌상 도형), 오른쪽 KAIROS 대화창(4단계).
import { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Editor } from './Editor.jsx'
import { DOC_NAME, docBounds, emptyDoc, loadServerDoc, parseDoc, saveServerDoc } from './doc.js'
import { fromEcad, toEcad } from './model.js'
import { setInkDark } from './render.jsx'
import { Palette, useLibrary } from './palette.jsx'

const ZMIN = 0.02, ZMAX = 40
// 화면 색은 next.html의 CSS 변수(밝은/어두운 화면 — 어두운 쪽은 데스크톱과 같은 값)
const C = { bar: 'var(--mb-bar)', group: 'var(--mb-group)', ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', accent: '#da7756', board: 'var(--mb-board)', line: 'var(--mb-line)', card: 'var(--mb-card)' }
const SAMPLES = [['모든 종류', '/samples/all_types.ecad'], ['보드 샘플', '/samples/paper_board.ecad'], ['login_flow', '/_local/login_flow.ecad'], ['1TV 계통도', '/_local/1TV_계통도_시험.ecad']]

function useSize(ref) {
  const [s, set] = useState({ w: 1, h: 1 })
  useEffect(() => { const ro = new ResizeObserver(([e]) => set({ w: e.contentRect.width, h: e.contentRect.height })); ro.observe(ref.current); return () => ro.disconnect() }, [ref])
  return s
}

// 위 막대 버튼 — 아이콘 밑 짧은 이름(데스크톱 첫 화면 원칙), 켜짐은 옅은 코랄 바탕
const Btn = ({ icon, label, onClick, title, on, disabled }) => (
  <button onClick={onClick} title={title || label} disabled={disabled} aria-pressed={on || undefined} style={{ all: 'unset', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.35 : 1,
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, padding: '4px 8px', borderRadius: 6, minWidth: 40,
    background: on ? 'rgba(218,119,86,.22)' : 'transparent', font: "500 11px 'Pretendard', sans-serif", color: C.ink }}
    onMouseEnter={e => { if (!disabled && !on) e.currentTarget.style.background = 'rgba(218,119,86,.12)' }} onMouseLeave={e => { e.currentTarget.style.background = on ? 'rgba(218,119,86,.22)' : 'transparent' }}>
    <span style={{ fontSize: 16, lineHeight: '18px' }}>{icon}</span>{label}
  </button>
)
const Group = ({ children }) => <div style={{ display: 'flex', gap: 2, background: C.group, borderRadius: 8, padding: 2 }}>{children}</div>
const TOOLS = [['select', '↖', '선택', '1'], ['arrow', '⤷', '화살표', '2'], ['text', 'T', '글자', '3'], ['line', '╱', '선', '4'], ['polygon', '⬠', '다각형', '5'], ['pen', '✎', '펜', '6'], ['badge', '①', '번호', '7']]

// 표 넣기 — 행·열·첫 행 머리(데스크톱 `_TableSizeDialog`: 기본 3×3, 머리 켬, 행 1~100·열 1~50)
function TableForm({ onInsert, onClose }) {
  const [r, setR] = useState(3), [c, setC] = useState(3), [h, setH] = useState(true)
  const num = (v, set, max) => <input type="number" min={1} max={max} value={v} onChange={e => set(Math.max(1, Math.min(max, +e.target.value || 1)))} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') onInsert(r, c, h); if (e.key === 'Escape') onClose() }}
    style={{ width: 52, height: 24, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 6px' }} />
  return <div style={{ position: 'absolute', top: 48, left: 0, zIndex: 20, width: 170, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: 10, boxShadow: '0 4px 14px rgba(0,0,0,.18)', display: 'flex', flexDirection: 'column', gap: 8, font: "400 12px 'Pretendard', sans-serif" }}>
    <div style={{ font: "700 13px 'Pretendard', sans-serif" }}>표 넣기</div>
    <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>행 {num(r, setR, 100)}</label>
    <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>열 {num(c, setC, 50)}</label>
    <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}><input type="checkbox" checked={h} onChange={e => setH(e.target.checked)} />첫 행을 머리로(굵게)</label>
    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
      <button onClick={onClose} style={{ all: 'unset', cursor: 'pointer', padding: '4px 10px', borderRadius: 6, color: C.muted }}>취소</button>
      <button onClick={() => onInsert(r, c, h)} style={{ all: 'unset', cursor: 'pointer', padding: '4px 12px', borderRadius: 6, background: '#da7756', color: '#fff', fontWeight: 600 }}>넣기</button>
    </div>
  </div>
}

function App() {
  const [tableOpen, setTableOpen] = useState(false)
  const [model, setModel] = useState(() => fromEcad(emptyDoc()))
  const [cam, setCam] = useState({ x: 0, y: 0, z: 1 })   // 화면 = 칠판 × z + (x, y)
  const [tool, setTool] = useState('select')
  const [status, setStatus] = useState('')
  // 어두운 화면(데스크톱 🌙와 같은 뜻) — 고른 값은 이 브라우저에 기억, 없으면 시스템 설정(next.html이 첫 값을 정함)
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === 'dark')
  setInkDark(dark)   // 칠판 기본 잉크(검정 ↔ 흰색) — 그리기 전에
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light' }, [dark])
  const toggleDark = () => setDark(d => { try { localStorage.setItem('mb.theme', d ? 'light' : 'dark') } catch { /* 기억 못 해도 그만 */ } return !d })
  const [server, setServer] = useState(false)
  const box = useRef(null), size = useSize(box), file = useRef(null), ed = useRef(null), saveT = useRef(null)

  const fit = useCallback((items, s = size) => {
    const b = docBounds(items); if (!b) return
    const pad = 40, z = Math.min(ZMAX, Math.max(ZMIN, Math.min((s.w - 2 * pad) / Math.max(b.w, 1), (s.h - 2 * pad) / Math.max(b.h, 1), 1)))
    setCam({ z, x: s.w / 2 - (b.x + b.w / 2) * z, y: s.h / 2 - (b.y + b.h / 2) * z })
  }, [size])
  // 서버 칠판을 다시 열면 이 브라우저에서 마지막에 보던 자리·배율로(없거나 못 읽으면 전체 맞추기). 파일·샘플은 늘 전체 맞추기
  const camKey = `mb.cam.${DOC_NAME}`, camReady = useRef(false)
  const savedCam = () => { try { const c = JSON.parse(localStorage.getItem(camKey)); return c && [c.x, c.y, c.z].every(Number.isFinite) ? c : null } catch { return null } }
  const open = useCallback((doc, how, keepCam = false) => { const m = fromEcad(doc); setModel(m); ed.current?.reset(); const c = keepCam && savedCam(); if (c) setCam(c); else fit(m.items); camReady.current = true; setStatus(`${how} · ${m.items.length}개`) }, [fit])   // eslint-disable-line
  useEffect(() => { if (!camReady.current) return; const t = setTimeout(() => { try { localStorage.setItem(camKey, JSON.stringify(cam)) } catch { /* 저장 못 해도 그만 */ } }, 300); return () => clearTimeout(t) }, [cam])   // eslint-disable-line

  // 고칠 때마다 0.8초 쉬면 서버에 저장(서버 없으면 「내려받기」로)
  const onCommit = useCallback(() => {
    if (!server) { setStatus('고침 — 서버 없음, 「내려받기」로 저장'); return }
    setStatus('고치는 중…'); clearTimeout(saveT.current)
    saveT.current = setTimeout(() => setModel(m => { saveServerDoc(toEcad(m)).then(ok => setStatus(ok ? `서버 「${DOC_NAME}」에 저장됨` : '서버 저장 실패')).catch(() => setStatus('서버 연결 끊김')); return m }), 800)
  }, [server])

  // 시험·자체확인용 손잡이(Playwright)
  useEffect(() => { window.__mb = { setCam, getCam: () => cam, open: async u => open(parseDoc(await (await fetch(u)).text()), u), model, toEcad: () => toEcad(model), get ed() { return ed.current }, setTool } })
  useEffect(() => { loadServerDoc().then(r => { setServer(r.server); if (r.doc) open(r.doc, `서버 「${DOC_NAME}」`, true); else setStatus(r.server ? `서버 「${DOC_NAME}」 · 새 칠판` : '서버 없음 — 파일로 열고 저장') }) }, [])   // eslint-disable-line

  // 카드 버튼: 클릭 = 그리기 도구, 6px 넘게 끌면 도형을 칠판에 바로 놓기(데스크톱 `_PaletteButton._DRAG_THRESH`)
  const lib = useLibrary()   // 「내 심볼」(서버 `/api/symbols`)
  const paletteDown = (e, t) => {
    if (e.button !== 0) return
    const sx = e.clientX, sy = e.clientY
    const move = ev => { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) <= 6) return; done(); ed.current?.startPaletteDrag(t) }
    const done = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', done) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', done)
  }

  const saveFile = () => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(toEcad(model), null, 1)], { type: 'application/json' }))
    a.download = `${DOC_NAME}.ecad`; a.click(); URL.revokeObjectURL(a.href)
  }
  const saveServer = async () => setStatus((await saveServerDoc(toEcad(model)).catch(() => false)) ? `서버 「${DOC_NAME}」에 저장함` : '서버 저장 실패')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: C.board, font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', background: C.bar, borderBottom: `1px solid ${C.line}` }}>
        <Group>
          <Btn icon="📂" label="열기" onClick={() => file.current.click()} />
          <Btn icon="💾" label="저장" onClick={server ? saveServer : saveFile} title={server ? `서버 「${DOC_NAME}」에 저장` : '.ecad로 내려받기'} />
          <Btn icon="⬇" label="내려받기" onClick={saveFile} title=".ecad 파일로 내려받기" />
        </Group>
        <Group>
          <Btn icon="↶" label="되돌리기" onClick={() => ed.current?.undo()} title="되돌리기 (Ctrl+Z)" />
          <Btn icon="↷" label="다시" onClick={() => ed.current?.redo()} title="다시 실행 (Ctrl+Y)" />
        </Group>
        <Group>{TOOLS.map(([k, icon, label, key]) => <Btn key={k} icon={icon} label={label} on={tool === k} onClick={() => setTool(k)} title={`${label} (${key})`} />)}</Group>
        <Group><div style={{ position: 'relative' }}>
          <Btn icon="▦" label="표" on={tableOpen} onClick={() => setTableOpen(o => !o)} title="표 넣기 — 행·열을 고르면 화면 가운데에" />
          {tableOpen && <TableForm onInsert={(r, c, h) => { setTableOpen(false); ed.current?.insertTable(r, c, h) }} onClose={() => setTableOpen(false)} />}
        </div></Group>
        <Group>
          <Btn icon="⤢" label="전체" onClick={() => fit(model.items)} title="전체 보기 (Ctrl+9)" />
          <Btn icon="1:1" label="100%" onClick={() => setCam(c => ({ z: 1, x: size.w / 2 - (size.w / 2 - c.x) / c.z, y: size.h / 2 - (size.h / 2 - c.y) / c.z }))} />
        </Group>
        <select onChange={async e => { const u = e.target.value; e.target.value = ''; if (!u) return; try { open(parseDoc(await (await fetch(u)).text()), u.split('/').pop()) } catch (err) { setStatus('샘플 열기 실패: ' + err.message) } }}
          defaultValue="" style={{ font: "500 12px 'Pretendard', sans-serif", padding: '4px 6px', borderRadius: 6, border: `1px solid ${C.line}`, background: C.card, color: C.ink }}>
          <option value="">샘플 열기…</option>{SAMPLES.map(([n, u]) => <option key={u} value={u}>{n}</option>)}
        </select>
        <span style={{ marginLeft: 'auto', color: C.muted, fontSize: 12 }}>{status} · {Math.round(cam.z * 100)}%</span>
        <Btn icon={dark ? '☀' : '☾'} label={dark ? '밝게' : '어둡게'} onClick={toggleDark} title="밝은 화면 / 어두운 화면" />
        <input ref={file} type="file" accept=".ecad,application/json" hidden onChange={async e => {
          const f = e.target.files?.[0]; e.target.value = ''; if (!f) return
          try { open(parseDoc(await f.text()), f.name) } catch (err) { setStatus('열기 실패: ' + err.message) }
        }} />
      </div>
      <div ref={box} style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        <Editor ref={ed} dark={dark} model={model} setModel={setModel} onCommit={onCommit} size={size} cam={cam} setCam={setCam} tool={tool} setTool={setTool} setStatus={setStatus} library={lib?.symbols} libFolders={lib?.folders} />
        {/* 좌상 도형·심볼 카드(데스크톱 첫 화면: 좌상 도형·심볼) */}
        <Palette lib={lib} tool={tool} dark={dark} onDown={paletteDown} onClick={setTool} />
      </div>
    </div>
  )
}

await document.fonts.load("400 16px 'Pretendard'", '가A').catch(() => {})
createRoot(document.getElementById('root')).render(<App />)
