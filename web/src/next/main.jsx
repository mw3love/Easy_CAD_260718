// 직접 만드는 Magic Board 웹 칠판(§8 항목61 「바뀐 결정」, 2026-10-17).
// 1단계 뼈대(무한 칠판·.ecad 열기/저장·모든 종류 그리기) + 2단계 기본 편집(Editor.jsx).
// 화면 틀(사용자 선택): 위 막대는 데스크톱처럼 아이콘 밑 짧은 이름, 칠판 위 떠 있는 카드(좌상 도형), 오른쪽 KAIROS 대화창(4단계).
import { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Editor } from './Editor.jsx'
import { DOC_NAME, docBounds, emptyDoc, loadServerDoc, parseDoc, saveServerDoc } from './doc.js'
import { fromEcad, toEcad } from './model.js'

const ZMIN = 0.02, ZMAX = 40
const C = { bar: '#f4f4f5', group: '#e9e9ec', ink: '#27272a', muted: '#71717a', accent: '#da7756', board: '#ffffff', line: '#e4e4e7', card: '#ffffff' }
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
const TOOLS = [['select', '↖', '선택', '1'], ['text', 'T', '글자', '3'], ['line', '╱', '선', '4'], ['polygon', '⬠', '다각형', '5'], ['pen', '✎', '펜', '6']]

function App() {
  const [model, setModel] = useState(() => fromEcad(emptyDoc()))
  const [cam, setCam] = useState({ x: 0, y: 0, z: 1 })   // 화면 = 칠판 × z + (x, y)
  const [tool, setTool] = useState('select')
  const [status, setStatus] = useState('')
  const [server, setServer] = useState(false)
  const box = useRef(null), size = useSize(box), file = useRef(null), ed = useRef(null), saveT = useRef(null)

  const fit = useCallback((items, s = size) => {
    const b = docBounds(items); if (!b) return
    const pad = 40, z = Math.min(ZMAX, Math.max(ZMIN, Math.min((s.w - 2 * pad) / Math.max(b.w, 1), (s.h - 2 * pad) / Math.max(b.h, 1), 1)))
    setCam({ z, x: s.w / 2 - (b.x + b.w / 2) * z, y: s.h / 2 - (b.y + b.h / 2) * z })
  }, [size])
  const open = useCallback((doc, how) => { const m = fromEcad(doc); setModel(m); ed.current?.reset(); fit(m.items); setStatus(`${how} · ${m.items.length}개`) }, [fit])

  // 고칠 때마다 0.8초 쉬면 서버에 저장(서버 없으면 「내려받기」로)
  const onCommit = useCallback(() => {
    if (!server) { setStatus('고침 — 서버 없음, 「내려받기」로 저장'); return }
    setStatus('고치는 중…'); clearTimeout(saveT.current)
    saveT.current = setTimeout(() => setModel(m => { saveServerDoc(toEcad(m)).then(ok => setStatus(ok ? `서버 「${DOC_NAME}」에 저장됨` : '서버 저장 실패')).catch(() => setStatus('서버 연결 끊김')); return m }), 800)
  }, [server])

  // 시험·자체확인용 손잡이(Playwright)
  useEffect(() => { window.__mb = { setCam, getCam: () => cam, open: async u => open(parseDoc(await (await fetch(u)).text()), u), model, toEcad: () => toEcad(model), get ed() { return ed.current }, setTool } })
  useEffect(() => { loadServerDoc().then(r => { setServer(r.server); if (r.doc) open(r.doc, `서버 「${DOC_NAME}」`); else setStatus(r.server ? `서버 「${DOC_NAME}」 · 새 칠판` : '서버 없음 — 파일로 열고 저장') }) }, [])   // eslint-disable-line

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
        <Group>
          <Btn icon="⤢" label="전체" onClick={() => fit(model.items)} title="전체 보기 (Ctrl+9)" />
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
      <div ref={box} style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        <Editor ref={ed} model={model} setModel={setModel} onCommit={onCommit} size={size} cam={cam} setCam={setCam} tool={tool} setTool={setTool} setStatus={setStatus} />
        {/* 좌상 도형 카드(데스크톱 첫 화면: 좌상 도형·심볼) — 심볼·내 심볼은 4단계 */}
        <div style={{ position: 'absolute', left: 12, top: 12, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: 8, boxShadow: '0 2px 8px rgba(0,0,0,.06)', width: 150 }}>
          <div style={{ font: "700 13px 'Pretendard', sans-serif", marginBottom: 6 }}>도형</div>
          <div style={{ display: 'flex', gap: 4 }}>
            <Btn icon="□" label="사각형" on={tool === 'rect'} onClick={() => setTool('rect')} />
            <Btn icon="○" label="원" on={tool === 'ellipse'} onClick={() => setTool('ellipse')} />
          </div>
        </div>
      </div>
    </div>
  )
}

await document.fonts.load("400 16px 'Pretendard'", '가A').catch(() => {})
createRoot(document.getElementById('root')).render(<App />)
