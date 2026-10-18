// 직접 만드는 Magic Board 웹 칠판(§8 항목61 「바뀐 결정」, 2026-10-17).
// 1단계 뼈대(무한 칠판·.ecad 열기/저장·모든 종류 그리기) + 2단계 기본 편집(Editor.jsx).
// 화면 틀(사용자 선택): 위 막대는 데스크톱처럼 아이콘 밑 짧은 이름, 칠판 위 떠 있는 카드(좌상 도형), 오른쪽 KAIROS 대화창(4단계).
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Editor } from './Editor.jsx'
import { DOC_NAME, VIEW_TOKEN, api, docBounds, emptyDoc, loadServerDoc, parseDoc, saveServerDoc } from './doc.js'
import { diffModel, rebase, snapshotModel } from './sync.js'
import { Viewer } from './viewer.jsx'
import { fromEcad, toEcad } from './model.js'
import { setInkDark } from './render.jsx'
import { Palette, useLibrary } from './palette.jsx'
import { Layers, layersOf, layerIdOf } from './layers.jsx'
import { Frames } from './frames.jsx'
import { Minimap } from './minimap.jsx'
import { ChatPanel } from './chat.jsx'

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

// 웹 카드 넣기 — 주소 한 줄(칠판에 주소를 Ctrl+V 해도 같음)
function WebForm({ onInsert, onClose }) {
  const [u, setU] = useState('')
  const go = () => { if (u.trim()) onInsert(u.trim()) }
  return <div style={{ position: 'absolute', top: 48, left: 0, zIndex: 20, width: 300, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: 10, boxShadow: '0 4px 14px rgba(0,0,0,.18)', display: 'flex', flexDirection: 'column', gap: 8, font: "400 12px 'Pretendard', sans-serif" }}>
    <div style={{ font: "700 13px 'Pretendard', sans-serif" }}>웹 카드 넣기</div>
    <input autoFocus value={u} onChange={e => setU(e.target.value)} placeholder="https://… (유튜브·웹페이지 주소)" onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') go(); if (e.key === 'Escape') onClose() }}
      style={{ height: 26, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 8px', font: 'inherit' }} />
    <div style={{ fontSize: 11, color: C.muted }}>들어가는 사이트는 칸 안에 페이지, 막는 사이트는 제목·그림 카드 + 새 탭. 칠판에 주소를 Ctrl+V 해도 돼요</div>
    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
      <button onClick={onClose} style={{ all: 'unset', cursor: 'pointer', padding: '4px 10px', borderRadius: 6, color: C.muted }}>취소</button>
      <button onClick={go} style={{ all: 'unset', cursor: 'pointer', padding: '4px 12px', borderRadius: 6, background: '#da7756', color: '#fff', fontWeight: 600 }}>넣기</button>
    </div>
  </div>
}

// 내보내기 — 형식·범위·용지·방향·여백·투명(데스크톱 `_PdfExportDialog`; 여백은 네 변 한 값으로)
// 쪽 미리보기 그림 하나(svg → img). 프레임 쪽이면 끌어서 순서 바꾸기
const Thumb = ({ pg, i, drag, onDrag, onDrop }) => <div draggable={!!pg.frameId} onDragStart={() => onDrag(i)} onDragOver={e => pg.frameId && e.preventDefault()} onDrop={e => { e.preventDefault(); onDrop(i) }}
  data-testid="export-thumb" title={pg.frameId ? '끌어서 순서 바꾸기(프레임 순서가 바뀌어요)' : ''} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, cursor: pg.frameId ? 'grab' : 'default', opacity: drag === i ? 0.4 : 1 }}>
  <img alt="" src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(pg.svg)}`} style={{ width: 118, height: Math.min(160, 118 * pg.ph / pg.pw), objectFit: 'contain', background: '#fff', border: `1px solid ${C.line}`, borderRadius: 4, boxShadow: '0 1px 3px rgba(0,0,0,.12)' }} />
  <span style={{ fontSize: 11, color: C.muted }}>{i + 1}쪽{pg.name ? ` · ${pg.name}` : ''}</span></div>

function ExportForm({ hasSel, selFrames, frameCount, items, onExport, onPreview, onReorder, onClose }) {   // selFrames = 고른 프레임(옛 종이틀 포함) 수, frameCount = 칠판의 프레임 수
  const [f, setF] = useState('pdf'), [scope, setScope] = useState(hasSel ? 'sel' : 'all'),   // 범위 기본 = 고른 게 있으면 그것, 없으면 전체(2026-10-18 사용자와 정함)
  [page, setPage] = useState('A4'), [orient, setOrient] = useState(''), [margin, setMargin] = useState(10), [tr, setTr] = useState(false), [busy, setBusy] = useState(false)
  const seg = (v, cur, set, label, dis) => <button key={v} disabled={dis} onClick={() => set(v)} style={{ all: 'unset', cursor: dis ? 'default' : 'pointer', opacity: dis ? 0.4 : 1, flex: 1, textAlign: 'center', padding: '3px 0', borderRadius: 6,
    background: cur === v ? 'rgba(218,119,86,.22)' : 'transparent', color: cur === v ? '#da7756' : C.ink, fontWeight: cur === v ? 600 : 400 }}>{label}</button>
  const row = (label, el) => <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ width: 34, color: C.muted }}>{label}</span><div style={{ flex: 1, display: 'flex', gap: 2, background: C.group, borderRadius: 8, padding: 2 }}>{el}</div></div>
  const [split, setSplit] = useState('frames')   // 고른 것에 종이틀이 있을 때 — 틀마다 쪽 / 고른 것 전체를 한 쪽에(2026-10-18 사용자)
  const [order, setOrder] = useState('rows')   // 종이틀 쪽 순서 — 줄 우선(위 줄 왼→오, 지그재그) / 칸 우선(왼 칸 위→아래)
  const opts = { format: f, scope, selection: scope === 'sel', onePage: split === 'one', order, page, orient: orient || null, margin, transparent: tr }
  const go = async () => { setBusy(true); try { await onExport(opts) } finally { setBusy(false) } }
  // 미리보기(2026-10-18 사용자: 인쇄 창 전에 보고 옵션 고르기) — 옵션·칠판이 바뀌면 다시
  const [prev, setPrev] = useState(null), [drag, setDrag] = useState(null), key = JSON.stringify(opts)
  useEffect(() => { let live = true; const t = setTimeout(async () => { const r = await onPreview({ ...opts, preview: true }); if (live) setPrev(r) }, 200); return () => { live = false; clearTimeout(t) } }, [key, items])   // eslint-disable-line react-hooks/exhaustive-deps
  const dropAt = to => { const pg = prev?.pages; if (drag == null || !pg || drag === to) return setDrag(null)
    const ids = pg.filter(q => q.frameId).map(q => q.frameId), [m] = ids.splice(drag, 1); ids.splice(to, 0, m); setDrag(null); onReorder(ids) }
  const sel = scope === 'sel'
  return <div onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') onClose() }} style={{ position: 'absolute', top: 48, left: 0, zIndex: 20, width: 280, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: 10, boxShadow: '0 4px 14px rgba(0,0,0,.18)', display: 'flex', flexDirection: 'column', gap: 8, font: "400 12px 'Pretendard', sans-serif" }}>
    <div style={{ font: "700 13px 'Pretendard', sans-serif" }}>내보내기</div>
    {row('형식', [seg('pdf', f, setF, 'PDF'), seg('png', f, setF, 'PNG'), seg('svg', f, setF, 'SVG'), seg('html', f, setF, 'HTML')])}
    {row('범위', [seg('all', scope, setScope, '전체'), seg('sel', scope, setScope, '고른 것', !hasSel), seg('frames', scope, setScope, `프레임만${frameCount ? ' ' + frameCount : ''}`, !frameCount)])}
    {sel && selFrames > 0 && row('쪽', [seg('frames', split, setSplit, '프레임마다'), seg('one', split, setSplit, '고른 것 한 쪽에')])}
    {sel && selFrames > 0 && <div style={{ fontSize: 11, color: '#da7756' }}>{split === 'one' ? '고른 것 전체를 감싼 영역이 한 쪽(틀도 그림처럼)' : `프레임 ${selFrames}개 → 틀마다 한 쪽, 프레임 순서(틀 밖에 고른 것은 마지막 쪽)`}</div>}
    {sel && selFrames > 1 && split === 'frames' && row('순서', [seg('rows', order, setOrder, '줄 우선 →'), seg('cols', order, setOrder, '칸 우선 ↓')])}
    {row('용지', Object.keys({ A4: 1, A3: 1, A2: 1, A1: 1, A0: 1 }).map(q => seg(q, page, setPage, q)))}
    {row('방향', [seg('', orient, setOrient, '자동'), seg('landscape', orient, setOrient, '가로'), seg('portrait', orient, setOrient, '세로')])}
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><span style={{ width: 34, color: C.muted }}>여백</span>
      <input type="number" min={0} max={50} value={margin} onChange={e => setMargin(Math.max(0, Math.min(50, +e.target.value || 0)))} style={{ width: 56, height: 24, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 6px' }} />mm</div>
    {f !== 'pdf' && <label style={{ display: 'flex', alignItems: 'center', gap: 6 }}><input type="checkbox" checked={tr} onChange={e => setTr(e.target.checked)} />투명 배경(다른 문서에 얹어 쓰기)</label>}
    <div data-testid="export-preview" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ color: C.muted }}>미리보기{prev?.pages ? ` · ${prev.pages.length}쪽` : ''}{prev?.pages?.filter(q => q.frameId).length > 1 ? ' — 끌어서 순서' : ''}</span>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, maxHeight: 280, overflowY: 'auto', padding: 6, background: C.group, borderRadius: 8, minHeight: 40 }}>
        {prev?.error ? <span style={{ color: C.muted }}>{prev.error}</span> : !prev?.pages ? <span style={{ color: C.muted }}>만드는 중…</span>
          : prev.pages.map((pg, i) => <Thumb key={i} pg={pg} i={i} drag={drag} onDrag={setDrag} onDrop={dropAt} />)}
      </div></div>
    <div style={{ fontSize: 11, color: C.muted }}>{f === 'pdf' ? '인쇄 창이 뜨면 「PDF로 저장」을 고르세요' : f === 'png' ? '200dpi 그림으로 내려받아요' : f === 'html' ? '파일 하나 — 앱·서버·인터넷 없이 열림. 전체 그림(확대·이동) + 프레임 = 발표 장(방송 예비본)' : '선·글이 그대로인 그림 파일'}</div>
    <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
      <button onClick={onClose} style={{ all: 'unset', cursor: 'pointer', padding: '4px 10px', borderRadius: 6, color: C.muted }}>닫기</button>
      <button disabled={busy} onClick={go} style={{ all: 'unset', cursor: 'pointer', padding: '4px 12px', borderRadius: 6, background: '#da7756', color: '#fff', fontWeight: 600, opacity: busy ? 0.6 : 1 }}>{busy ? '만드는 중…' : '내보내기'}</button>
    </div>
  </div>
}

// 공동작업 1단계(§8 항목61 ⓕ, 2026-10-18) — 공용 비밀번호 + 이름(사람별 계정 아님, 사용자 결정)
function LoginForm({ onDone }) {
  const [pw, setPw] = useState(''), [name, setName] = useState(() => { try { return localStorage.getItem('mb.name') || '' } catch { return '' } }), [err, setErr] = useState('')
  const go = async () => { if (!name.trim()) { setErr('이름을 적어 주세요(누가 접속했는지 보여요)'); return }
    if (!(await api.login(pw))) { setErr('비밀번호가 맞지 않아요'); return }
    try { localStorage.setItem('mb.name', name.trim()) } catch { /* 기억 못 해도 그만 */ } onDone(name.trim()) }
  const inp = { height: 30, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 10px', font: 'inherit' }
  return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.board, font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ width: 300, display: 'flex', flexDirection: 'column', gap: 10, padding: 20, borderRadius: 12, border: `1px solid ${C.line}`, background: C.card, boxShadow: '0 6px 20px rgba(0,0,0,.12)' }}>
      <div style={{ font: "700 16px 'Pretendard', sans-serif" }}>Magic Board · 「{DOC_NAME}」</div>
      <div style={{ color: C.muted, fontSize: 12 }}>같이 쓰는 칠판이에요. 팀 비밀번호와 내 이름을 적어 주세요.</div>
      <input autoFocus placeholder="이름 (예: 김기자)" value={name} onChange={e => setName(e.target.value)} style={inp} />
      <input type="password" placeholder="팀 비밀번호" value={pw} onChange={e => setPw(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') go() }} style={inp} />
      {err && <div style={{ color: '#d44c47', fontSize: 12 }}>{err}</div>}
      <button onClick={go} style={{ all: 'unset', cursor: 'pointer', textAlign: 'center', padding: '7px 0', borderRadius: 6, background: '#da7756', color: '#fff', fontWeight: 600 }}>들어가기</button>
    </div></div>
}
// 「공유」 — 노션 게시처럼: 로그인 없이 보기·발표만 되는 링크(켜고 끄기, 새 링크로 바꾸면 옛 링크 막힘)
function ShareForm({ onClose }) {
  const [tok, setTok] = useState(undefined), [msg, setMsg] = useState('')
  useEffect(() => { api.getPublish().then(setTok) }, [])
  const link = tok ? `${location.origin}/?view=${tok}` : ''
  const set = async (on, renew) => { const t = await api.setPublish(on, renew); setTok(on ? t : null); setMsg(on ? (renew ? '새 링크 — 옛 링크는 이제 안 열려요' : '게시했어요') : '게시를 껐어요 — 링크가 안 열려요') }
  const b = (bg, fg = '#fff') => ({ all: 'unset', cursor: 'pointer', padding: '5px 10px', borderRadius: 6, background: bg, color: fg, fontWeight: 600, fontSize: 12 })
  return <div onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') onClose() }} style={{ position: 'absolute', top: 48, right: 0, zIndex: 20, width: 320, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: 12, boxShadow: '0 4px 14px rgba(0,0,0,.18)', display: 'flex', flexDirection: 'column', gap: 8, font: "400 12px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ font: "700 13px 'Pretendard', sans-serif" }}>게시 — 보기·발표 전용 링크</div>
    <div style={{ color: C.muted }}>로그인 없이 열려요. 고치기·대화는 안 되고, 여기서 고친 건 몇 초 안에 보여요(큰 TV 발표용).</div>
    {tok === undefined ? <span style={{ color: C.muted }}>확인 중…</span> : tok ? <>
      <input readOnly value={link} onFocus={e => e.target.select()} style={{ height: 26, border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 6px', font: 'inherit' }} />
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        <button style={b('#da7756')} onClick={() => navigator.clipboard?.writeText(link).then(() => setMsg('링크를 복사했어요'), () => setMsg('복사가 막혔어요 — 칸을 눌러 직접 복사'))}>링크 복사</button>
        <button style={b('transparent', C.ink)} onClick={() => window.open(link, '_blank', 'noopener')}>열어 보기</button>
        <button style={b('transparent', C.ink)} onClick={() => set(true, true)}>새 링크로 바꾸기</button>
        <button style={b('transparent', '#d44c47')} onClick={() => set(false)}>게시 끄기</button>
      </div></> : <button style={b('#da7756')} onClick={() => set(true)}>게시하기</button>}
    {msg && <div style={{ color: '#da7756' }}>{msg}</div>}
  </div>
}

function App() {
  const [tableOpen, setTableOpen] = useState(false), [exportOpen, setExportOpen] = useState(false), [webOpen, setWebOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(() => { try { return localStorage.getItem('mb-chat-open') !== '0' } catch { return true } }), [selKey, setSelKey] = useState('')   // 대화창 열림은 이 브라우저에 기억(기본 열림 — 화면 원칙: 작업공간 + AI 대화창)
  useEffect(() => { try { localStorage.setItem('mb-chat-open', chatOpen ? '1' : '0') } catch { /* 기억 못 해도 그만 */ } }, [chatOpen])
  const [activeLayer, setActiveLayer] = useState('default')   // 「그리는 중」 레이어(파일을 열면 기본부터 — 데스크톱 `_apply_loaded_layers`)
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
  const [me, setMe] = useState(() => { try { return localStorage.getItem('mb.name') || '' } catch { return '' } }), [people, setPeople] = useState([]), [shareOpen, setShareOpen] = useState(false)
  const sync = useRef({ base: null, rev: 0, busy: false, again: false, id: Math.random().toString(36).slice(2, 10) }), modelRef = useRef(model); modelRef.current = model
  const box = useRef(null), size = useSize(box), file = useRef(null), ed = useRef(null), saveT = useRef(null)

  const fit = useCallback((items, s = size) => {
    const b = docBounds(items); if (!b) return
    const pad = 40, z = Math.min(ZMAX, Math.max(ZMIN, Math.min((s.w - 2 * pad) / Math.max(b.w, 1), (s.h - 2 * pad) / Math.max(b.h, 1), 1)))
    setCam({ z, x: s.w / 2 - (b.x + b.w / 2) * z, y: s.h / 2 - (b.y + b.h / 2) * z })
  }, [size])
  // 서버 칠판을 다시 열면 이 브라우저에서 마지막에 보던 자리·배율로(없거나 못 읽으면 전체 맞추기). 파일·샘플은 늘 전체 맞추기
  const camKey = `mb.cam.${DOC_NAME}`, camReady = useRef(false)
  const savedCam = () => { try { const c = JSON.parse(localStorage.getItem(camKey)); return c && [c.x, c.y, c.z].every(Number.isFinite) ? c : null } catch { return null } }
  const open = useCallback((doc, how, keepCam = false, fromServer = false) => { const m = { ...fromEcad(doc), rev: doc.rev || 0 }; setModel(m); modelRef.current = m
    if (fromServer) { sync.current.base = snapshotModel(m); sync.current.rev = doc.rev || 0 }   // 서버에서 받은 것 = 맞춘 기준
    else if (sync.current.base) saveServerDoc(toEcad(m)).then(rev => { if (typeof rev === 'number') { sync.current.base = snapshotModel(m); sync.current.rev = rev } })   // 파일·샘플을 이 칠판에 열기 = 통째 바꿈
    setActiveLayer('default'); ed.current?.reset(); const c = keepCam && savedCam(); if (c) setCam(c); else fit(m.items); camReady.current = true; setStatus(`${how} · ${m.items.length}개`) }, [fit])   // eslint-disable-line
  useEffect(() => { if (!camReady.current) return; const t = setTimeout(() => { try { localStorage.setItem(camKey, JSON.stringify(cam)) } catch { /* 저장 못 해도 그만 */ } }, 300); return () => clearTimeout(t) }, [cam])   // eslint-disable-line

  // 공동작업 맞추기(2026-10-18) — 고친 뒤 0.6초 쉬면 바뀐 도형만 보내고(부분 저장), 2초마다 남이 바꾼 것을 받아 내 안 보낸 변경을 그 위에 다시 얹음
  const pull = useCallback(async (since = null) => {
    const S = sync.current; if (!S.base || S.busy || ed.current?.busy?.()) return
    const doc = await api.since(since ?? S.rev).catch(() => null); if (!doc) return
    if (S.busy || ed.current?.busy?.()) return   // 받는 사이 고치기 시작했으면 다음 차례에
    const remote = { ...fromEcad(doc), rev: doc.rev || 0 }, base = S.base
    const merged = rebase(remote, modelRef.current, base)
    S.base = snapshotModel(remote); S.rev = remote.rev; modelRef.current = merged; setModel(merged)
    if (diffModel(S.base, merged)) flush()   // 안 보낸 내 변경이 남아 있으면 이어서 보냄
  }, [])   // eslint-disable-line
  const flush = useCallback(async () => {
    const S = sync.current; if (!S.base) return
    if (S.busy) { S.again = true; return }
    const m = modelRef.current, p = diffModel(S.base, m); if (!p) return
    S.busy = true; const rev0 = S.rev
    try {
      const rev = await api.patch({ base: rev0, ...p })
      if (rev == null) { setStatus('서버 저장 실패 — 다시 들어가야 할 수도(비밀번호)'); return }
      S.base = snapshotModel(m); S.rev = rev; setStatus(`서버 「${DOC_NAME}」에 저장됨`)
      if (rev > rev0 + 1) { S.busy = false; await pull(rev0) }   // 그사이 남도 고쳤음 — 바로 받아 옴
    } catch { setStatus('서버 연결 끊김') } finally { S.busy = false; if (S.again) { S.again = false; flush() } }
  }, [pull])
  const onCommit = useCallback(() => {
    if (!server) { setStatus('고침 — 서버 없음, 「내려받기」로 저장'); return }
    setStatus('고치는 중…'); clearTimeout(saveT.current)
    saveT.current = setTimeout(flush, 600)
  }, [server, flush])
  useEffect(() => { if (!server) return; const t = setInterval(() => pull(), 2000); return () => clearInterval(t) }, [server, pull])
  useEffect(() => { if (!server) return   // 접속자 — 5초마다 이름 신호
    const ping = () => api.presence(sync.current.id, me || '이름 없음').then(p => p && setPeople(p)); ping(); const t = setInterval(ping, 5000); return () => clearInterval(t) }, [server, me])

  // 시험·자체확인용 손잡이(Playwright)
  useEffect(() => { window.__mb = { setCam, getCam: () => cam, open: async u => open(parseDoc(await (await fetch(u)).text()), u), model, toEcad: () => toEcad(model), get ed() { return ed.current }, setTool } })
  useEffect(() => {
    loadServerDoc().then(r => { setServer(r.server); if (r.doc) open(r.doc, `서버 「${DOC_NAME}」`, true, true); else { if (r.server) { const m = modelRef.current; sync.current.base = snapshotModel(m); sync.current.rev = 0 } setStatus(r.server ? `서버 「${DOC_NAME}」 · 새 칠판` : '서버 없음 — 파일로 열고 저장') } }) }, [])   // eslint-disable-line

  // 카드 버튼: 클릭 = 그리기 도구, 6px 넘게 끌면 도형을 칠판에 바로 놓기(데스크톱 `_PaletteButton._DRAG_THRESH`)
  // 미니맵에 그릴 것 — 숨긴 레이어 뺌(화면을 옮길 때마다 다시 그리지 않게 문서가 바뀔 때만)
  const mapItems = useMemo(() => { const hid = new Set(layersOf(model).filter(l => !l.visible).map(l => l.id)); return hid.size ? model.items.filter(it => !hid.has(layerIdOf(it))) : model.items }, [model])
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
  const saveServer = () => { clearTimeout(saveT.current); flush() }   // 지금 바로 보내기(바뀐 도형만)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: C.board, font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 8px', background: C.bar, borderBottom: `1px solid ${C.line}` }}>
        <Group>
          <Btn icon="📂" label="열기" onClick={() => file.current.click()} />
          <Btn icon="💾" label="저장" onClick={server ? saveServer : saveFile} title={server ? `서버 「${DOC_NAME}」에 저장` : '.ecad로 내려받기'} />
          <Btn icon="⬇" label="내려받기" onClick={saveFile} title=".ecad 파일로 내려받기" />
          <div style={{ position: 'relative' }}>
            <Btn icon="🖨" label="내보내기" on={exportOpen} onClick={() => setExportOpen(o => !o)} title="PDF·PNG·SVG로 내보내기 — 전체 또는 고른 것" />
            {exportOpen && <ExportForm hasSel={!!ed.current?.getSel().length} selFrames={ed.current?.selFrames() || 0} frameCount={model.items.filter(it => it.type === 'frame' || (it.type === 'titleblock' && it.plain)).length} items={model.items}
            onPreview={o => ed.current?.exportPages(o) ?? Promise.resolve({ error: '' })} onReorder={ids => ed.current?.reorderFrames(ids)} onClose={() => setExportOpen(false)} onExport={async o => { const ok = await ed.current?.exportDoc({ ...o, name: DOC_NAME || 'magic-board' }); if (ok) setExportOpen(false) }} />}
          </div>
        </Group>
        <Group>
          <Btn icon="↶" label="되돌리기" onClick={() => ed.current?.undo()} title="되돌리기 (Ctrl+Z)" />
          <Btn icon="↷" label="다시" onClick={() => ed.current?.redo()} title="다시 실행 (Ctrl+Y)" />
        </Group>
        <Group>{TOOLS.map(([k, icon, label, key]) => <Btn key={k} icon={icon} label={label} on={tool === k} onClick={() => setTool(k)} title={`${label} (${key})`} />)}</Group>
        <Group><div style={{ position: 'relative' }}>
          <Btn icon="▶" label="발표" onClick={() => ed.current?.startPresent()} title="발표 — 프레임 순서대로 한 장씩 전체 화면(고른 프레임부터) · → 다음 · ← 이전 · M 이동/바로 · Esc 끝" />
          <Btn icon="▭" label="프레임" on={tool === 'frame'} onClick={() => setTool(t => (t === 'frame' ? 'select' : 'frame'))} title="프레임 — 끌어서 영역을 감싸면 그 안이 출력 한 쪽(번호 순서). 클릭만 = 16:9, 우클릭 「프레임으로 감싸기」도" />
        </div><div style={{ position: 'relative' }}>
          <Btn icon="▦" label="표" on={tableOpen} onClick={() => setTableOpen(o => !o)} title="표 넣기 — 행·열을 고르면 화면 가운데에" />
          {tableOpen && <TableForm onInsert={(r, c, h) => { setTableOpen(false); ed.current?.insertTable(r, c, h) }} onClose={() => setTableOpen(false)} />}
        </div><div style={{ position: 'relative' }}>
          <Btn icon="🗒" label="메모" onClick={() => ed.current?.insertMemo()} title="메모 — 줄마다 제목·목록·할 일·코드·인용(`# `·`- `·`[] `·`> ` 입력), 체크 상자는 칠판에서 바로" />
          <Btn icon="🌐" label="웹" on={webOpen} onClick={() => setWebOpen(o => !o)} title="웹 카드 — 유튜브·웹페이지 주소를 칠판에(칠판에 주소를 Ctrl+V 해도 돼요)" />
          {webOpen && <WebForm onInsert={u => { const url = /^https?:\/\//i.test(u) ? u : 'https://' + u; setWebOpen(false); ed.current?.insertWeb(url) }} onClose={() => setWebOpen(false)} />}
        </div></Group>
        <Group>
          <Btn icon="⤢" label="전체" onClick={() => fit(model.items)} title="전체 보기 (Ctrl+9)" />
        </Group>
        <select onChange={async e => { const u = e.target.value; e.target.value = ''; if (!u) return; try { open(parseDoc(await (await fetch(u)).text()), u.split('/').pop()) } catch (err) { setStatus('샘플 열기 실패: ' + err.message) } }}
          defaultValue="" style={{ font: "500 12px 'Pretendard', sans-serif", padding: '4px 6px', borderRadius: 6, border: `1px solid ${C.line}`, background: C.card, color: C.ink }}>
          <option value="">샘플 열기…</option>{SAMPLES.map(([n, u]) => <option key={u} value={u}>{n}</option>)}
        </select>
        <span style={{ marginLeft: 'auto', color: C.muted, fontSize: 12 }}>{status} · {Math.round(cam.z * 100)}%</span>
        {server && <span title={people.length ? `지금 이 칠판에: ${people.join(', ')}` : ''} style={{ fontSize: 12, color: C.muted, whiteSpace: 'nowrap', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }}>👥 {people.length ? people.join(' · ') : (me || '나')}</span>}
        {server && <div style={{ position: 'relative' }}>
          <Btn icon="🔗" label="공유" on={shareOpen} onClick={() => setShareOpen(o => !o)} title="게시 — 로그인 없이 보기·발표만 되는 링크(큰 TV 발표용)" />
          {shareOpen && <ShareForm onClose={() => setShareOpen(false)} />}
        </div>}
        <Btn icon="💬" label="KAIROS" on={chatOpen} onClick={() => setChatOpen(o => !o)} title="KAIROS 대화창 열기/닫기 — 답을 칠판에 카드로 붙여요" />
        <Btn icon={dark ? '☀' : '☾'} label={dark ? '밝게' : '어둡게'} onClick={toggleDark} title="밝은 화면 / 어두운 화면" />
        <input ref={file} type="file" accept=".ecad,application/json" hidden onChange={async e => {
          const f = e.target.files?.[0]; e.target.value = ''; if (!f) return
          try { open(parseDoc(await f.text()), f.name) } catch (err) { setStatus('열기 실패: ' + err.message) }
        }} />
      </div>
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>   {/* 작업공간 + 오른쪽 KAIROS 대화창(2분할) */}
      <div ref={box} style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        <Editor ref={ed} dark={dark} model={model} setModel={setModel} onCommit={onCommit} size={size} cam={cam} setCam={setCam} tool={tool} setTool={setTool} setStatus={setStatus} library={lib?.symbols} libFolders={lib?.folders} activeLayer={activeLayer} onSel={s => setSelKey(s.join())} onExportSel={() => setExportOpen(true)} />
        {/* 좌상 도형·심볼 카드(데스크톱 첫 화면: 좌상 도형·심볼) */}
        {/* 왼쪽 세로 줄 — 위 도형·심볼 카드, 아래 레이어 카드(데스크톱 첫 화면: 좌상·좌하 따로, 통합 금지). 줄 자체는 칠판 누르기를 막지 않음 */}
        <div style={{ position: 'absolute', left: 12, top: 12, bottom: 12, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', gap: 8, pointerEvents: 'none' }}>
          <Palette lib={lib} tool={tool} dark={dark} onDown={paletteDown} onClick={setTool} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <Frames items={model.items} sel={selKey ? selKey.split(',') : []} onReorder={ids => ed.current?.reorderFrames(ids)} onRename={(id, n) => ed.current?.renameFrame(id, n)} onGo={id => ed.current?.goFrame(id)} onPresent={id => ed.current?.startPresent(id)} dark={dark} />
            <Layers model={model} setModel={setModel} active={activeLayer} setActive={setActiveLayer} onChanged={onCommit} onMoveSel={id => ed.current?.moveSelToLayer(id)} dark={dark} />
          </div>
        </div>
        {/* 우하 미니맵(데스크톱 첫 화면: 우하) — 숨긴 레이어는 뺌 */}
        <Minimap items={mapItems}
          cam={cam} size={size} setCam={setCam} onFit={() => fit(model.items)} dark={dark} />
      </div>
      {chatOpen && <ChatPanel ed={ed} selKey={selKey} onClose={() => setChatOpen(false)} />}
      </div>
    </div>
  )
}

await document.fonts.load("400 16px 'Pretendard'", '가A').catch(() => {})
// 들어가기 전 — 비밀번호가 필요한 서버면 먼저 로그인 창(칠판 화면은 그 뒤에 만들어야 크기 재기 등이 바로 돎)
function Gate() {
  const [gate, setGate] = useState('check')
  useEffect(() => { api.session().then(s => setGate(s.auth && !s.ok ? 'login' : 'ok')) }, [])
  if (gate === 'check') return null
  if (gate === 'login') return <LoginForm onDone={() => setGate('ok')} />
  return <App />
}
createRoot(document.getElementById('root')).render(VIEW_TOKEN ? <Viewer token={VIEW_TOKEN} /> : <Gate />)   // ?view= = 게시 링크(보기·발표만)
