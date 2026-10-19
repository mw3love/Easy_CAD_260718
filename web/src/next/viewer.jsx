// 게시 링크 화면(§8 항목61 ⓕ 공동작업 1단계, 2026-10-18 — 노션 게시처럼 로그인 없이 보기·발표만). 주소 `/?view=<토큰>`.
// 칠판은 같은 그리기(Editor readOnly — 끌기 = 화면 이동, 휠 = 확대), 3초마다 바뀐 것을 받아 옴. 고치기·대화·저장 없음.
// 발표 중 판서는 이 화면에만(서버로 안 감).
import { useCallback, useEffect, useRef, useState } from 'react'
import { Editor } from './Editor.jsx'
import { api, docBounds } from './doc.js'
import { fromEcad } from './model.js'
import { setInkDark } from './render.jsx'

const C = { bar: 'var(--mb-bar)', ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', board: 'var(--mb-board)', line: 'var(--mb-line)' }
const btn = { all: 'unset', cursor: 'pointer', padding: '5px 12px', borderRadius: 6, font: "600 12px 'Pretendard', sans-serif", color: C.ink, background: 'rgba(218,119,86,.14)' }

export function Viewer({ token }) {
  const [model, setModel] = useState(null), [gone, setGone] = useState(false), [cam, setCam] = useState({ x: 0, y: 0, z: 1 }), [size, setSize] = useState({ w: 1, h: 1 })
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === 'dark'), box = useRef(null), ed = useRef(null), rev = useRef(-1), fitted = useRef(false)
  setInkDark(dark)
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light' }, [dark])
  useEffect(() => { const ro = new ResizeObserver(([e]) => setSize({ w: e.contentRect.width, h: e.contentRect.height })); if (box.current) ro.observe(box.current); return () => ro.disconnect() }, [model])
  const fit = useCallback((items, s) => { const b = docBounds(items); if (!b) return; const z = Math.min(1, (s.w - 80) / Math.max(b.w, 1), (s.h - 80) / Math.max(b.h, 1)); setCam({ z, x: s.w / 2 - (b.x + b.w / 2) * z, y: s.h / 2 - (b.y + b.h / 2) * z }) }, [])
  useEffect(() => {
    let live = true
    const pull = async () => {
      if (ed.current?.busy?.()) return
      const r = await api.pub(token, rev.current).catch(() => null); if (!live || !r) return
      if (r.gone) { setGone(true); return }
      if (r.doc) { rev.current = r.doc.rev || 0; setGone(false); setModel(fromEcad(r.doc)) }
    }
    pull(); const t = setInterval(pull, 3000); return () => { live = false; clearInterval(t) }
  }, [token])
  useEffect(() => { if (model && !fitted.current && size.w > 1) { fitted.current = true; fit(model.items, size) } }, [model, size, fit])
  if (gone) return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: C.muted, background: C.board, font: "400 14px 'Pretendard', sans-serif" }}>게시가 꺼졌거나 링크가 바뀌었어요 — 칠판을 고치는 분께 새 링크를 받아 주세요.</div>
  if (!model) return <div style={{ height: '100%', background: C.board }} />
  return <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: C.board, font: "400 13px 'Pretendard', sans-serif", color: C.ink, userSelect: 'none' }}>   {/* 보기 화면 — Ctrl+A가 글자를 칠하지 않게 */}
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', background: C.bar, borderBottom: `1px solid ${C.line}` }}>
      <b>Magic Board</b><span style={{ color: C.muted, fontSize: 12 }}>보기 전용 · 고치는 내용이 몇 초 안에 보여요</span>
      <span style={{ flex: 1 }} />
      <button style={btn} data-testid="view-present" onClick={() => ed.current?.startPresent()} title="발표 — 프레임 순서대로 한 장씩 전체 화면">▶ 발표</button>
      <button style={btn} onClick={() => fit(model.items, size)} title="칠판 전체가 화면에 들어오게 맞춤">⤢ 다 보기</button>
      <button style={btn} onClick={() => setDark(d => !d)}>{dark ? '☀ 밝게' : '☾ 어둡게'}</button>
    </div>
    <div ref={box} style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
      <Editor ref={ed} readOnly dark={dark} model={model} setModel={setModel} onCommit={() => {}} size={size} cam={cam} setCam={setCam} tool="select" setTool={() => {}} setStatus={() => {}} activeLayer="default" />
    </div>
  </div>
}
