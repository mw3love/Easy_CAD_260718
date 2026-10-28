// 직접 만드는 Magic Board 웹 칠판(§8 항목61 「바뀐 결정」, 2026-10-17).
// 1단계 뼈대(무한 칠판·.ecad 열기/저장·모든 종류 그리기) + 2단계 기본 편집(Editor.jsx).
// 화면 틀(사용자 선택): 위 막대는 데스크톱처럼 아이콘 밑 짧은 이름, 칠판 위 떠 있는 카드(좌상 도형), 오른쪽 KAIROS 대화창(4단계).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Editor, rightInset, personColor } from './Editor.jsx'
import { AUTO_BOARD, DOC_NAME, VIEW_TOKEN, api, docBounds, emptyDoc, loadServerDoc, parseDoc, saveServerDoc } from './doc.js'
import { diffModel, rebase, snapshotModel } from './sync.js'
import { Viewer } from './viewer.jsx'
import { fromEcad, toEcad } from './model.js'
import { setInkDark } from './render.jsx'
import { Palette, useLibrary } from './palette.jsx'
import { useMySymbols, mergeLib } from './mysym.js'
import { Layers, layersOf, layerIdOf } from './layers.jsx'
import { Frames } from './frames.jsx'
import { UNTITLED, boardFromText, boardLabel, boardTitle, forgetBoard, isMyBoard, knownTitle, moveBoard, myBoards, newBoardName, noteBoards, rememberBoard } from './myboards.js'
import { FloatMenu } from './ctxmenu.jsx'
import { QrBig } from './qr.jsx'
import { Minimap } from './minimap.jsx'
import { ChatPanel, CHAT_W, chatClamp, Spinner } from './chat.jsx'
import { HelpCard } from './help.jsx'
import { EmptyGuide } from './guide.jsx'
import { FindBar } from './find.jsx'

const ZMIN = 0.02, ZMAX = 40, LEFT_CARDS = 24   // LEFT_CARDS = 맞출 때 왼쪽 여백 — 카드가 칠판 위에 떠 있던 때는 220(2026-10-23 왼쪽 판으로 붙이며 칠판 밖으로 나감)
// 화면 색은 next.html의 CSS 변수(밝은/어두운 화면 — 어두운 쪽은 데스크톱과 같은 값)
import { orderedFrames } from './edit.js'
import ICONS from './icons.json' with { type: 'json' }   // 위 막대 아이콘 = 데스크톱 손그림 A2(`tools/export_web_icons.py`, 2026-10-22 사용자 W1)
const C = { bar: 'var(--mb-bar)', group: 'var(--mb-group)', ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', accent: '#da7756', board: 'var(--mb-board)', line: 'var(--mb-line)', card: 'var(--mb-card)' }
const SAMPLES = [['모든 종류', '/samples/all_types.ecad'], ['보드 샘플', '/samples/paper_board.ecad'], ['login_flow', '/_local/login_flow.ecad'], ['1TV 계통도', '/_local/1TV_계통도_시험.ecad']]

function useSize(ref) {
  const [s, set] = useState({ w: 1, h: 1 })
  useEffect(() => { const ro = new ResizeObserver(([e]) => set({ w: e.contentRect.width, h: e.contentRect.height })); ro.observe(ref.current); return () => ro.disconnect() }, [ref])
  return s
}

// 위 막대 버튼 — 아이콘 밑 짧은 이름(데스크톱 첫 화면 원칙), 켜짐은 옅은 코랄 바탕
// 좁은 창(NARROW_W 미만 — 브라우저 옆에 띄워 쓸 때, 2026-10-19 사용자 선택)은 아이콘만(이름은 툴팁) — 지침 「자리가 모자랄 때만 아이콘만」
const NARROW_W = 1440, Narrow = createContext(false)
const PHONE_W = 700   // 휴대폰(2026-10-27) = 보기·묻기·회의만 — 위 막대는 이름만, 아래 큰 버튼 셋, 왼쪽 판 없음, 대화창은 화면 전체, 손가락 = 이동·확대
// 휴대폰 = 손가락 기기 + 좁은 화면(2026-10-27 저녁 사용자 — 폭만 보면 PC 창을 반으로 나눴을 때도 고치기가 막혔음. 「브라우저 옆에 띄워 두고 쓴다」가 목표)
const isPhone = () => window.innerWidth < PHONE_W && !!window.matchMedia?.('(pointer: coarse)').matches
// special = KAIROS(2026-10-23 사용자: 다른 버튼과 다른 특별한 버튼 — 오른쪽 구석, 코랄로 채움. 열림은 한 단계 진하게)
const SPECIAL_BG = on => (on ? '#c4613f' : '#da7756')
// 「도구 유지」 자물쇠 — 데스크톱에 없는 웹 버튼이라 icons.json(데스크톱에서 뽑음) 대신 여기, 같은 선 굵기 1.6(2026-10-27)
const KEEP_ICONS = { keep_on: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><rect x="5" y="10.5" width="14" height="10" rx="1.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/></svg>',
  keep_off: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"><rect x="5" y="10.5" width="14" height="10" rx="1.5"/><path d="M8 10.5V7.5a4 4 0 0 1 7.6-1.7"/></svg>' }
const Btn = ({ icon, label, onClick, onDown, title, on, disabled, special }) => { const narrow = useContext(Narrow); const bg = o => (special ? SPECIAL_BG(o) : o ? 'rgba(218,119,86,.22)' : 'transparent'); return (
  <button onClick={onClick} onPointerDown={onDown} title={title || label} aria-label={label} disabled={disabled} aria-pressed={on || undefined} style={{ all: 'unset', cursor: disabled ? 'default' : 'pointer', opacity: disabled ? 0.35 : 1,
    display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, padding: narrow ? '4px 4px' : '4px 8px', borderRadius: 6, minWidth: narrow ? 24 : 40,   // 좁은 창 옆 여백 6 → 4px: 「칠판」 버튼이 늘며 960px에서 상태 글이 0px로 눌렸음(2026-10-19)
    background: bg(on), font: special ? "700 11px 'Pretendard', sans-serif" : "500 11px 'Pretendard', sans-serif", color: special ? '#fff' : C.ink }}
    onMouseEnter={e => { if (!disabled && (special || !on)) e.currentTarget.style.background = special ? SPECIAL_BG(true) : 'rgba(218,119,86,.12)' }} onMouseLeave={e => { e.currentTarget.style.background = bg(on) }}>
    {(ICONS[icon] || KEEP_ICONS[icon]) ? <span aria-hidden style={{ width: 18, height: 18, display: 'block', color: special ? '#fff' : 'var(--mb-icon)' }} dangerouslySetInnerHTML={{ __html: (ICONS[icon] || KEEP_ICONS[icon]).replace('<svg ', '<svg width="18" height="18" ') }} />
      : <span style={{ fontSize: 16, lineHeight: '18px' }}>{icon}</span>}{!narrow && <span style={{ whiteSpace: 'nowrap' }}>{label}</span>}   {/* 이름은 한 줄(「전체 화면」이 두 줄로 꺾여 위 막대가 높아졌음 — 2026-10-20) */}
  </button>
) }
// 펼침 창(표·웹 등)을 버튼 아래에 붙이는 칸 — 칸 안 버튼도 옆으로(2026-10-19 다잡기: 칸이 버튼을 위아래로 쌓아 위 막대가 95px로 늘고 칠판이 밀렸음)
const ANCHOR = { position: 'relative', display: 'flex', gap: 2 }
const Group = ({ children }) => <div style={{ display: 'flex', gap: 2, background: C.group, borderRadius: 8, padding: 2 }}>{children}</div>
const TOOLS = [['select', 'select', '선택', '1'], ['arrow', 'sarrow', '화살표', '2'], ['text', 'text', '글자', '3'], ['line', 'line', '선', '4'], ['polygon', 'polygon', '다각형', '5'], ['pen', 'pen', '펜', '6'], ['badge', 'badge', '번호', '7']]   // [도구, 아이콘(icons.json), 이름, 글쇠]

// 표 넣기 — 행·열·첫 행 머리(데스크톱 `_TableSizeDialog`: 기본 3×3, 머리 켬, 행 1~100·열 1~50)
function TableForm({ onInsert, onLegend, onClose }) {   // onLegend = 범례 넣기(2026-10-19 사용자: 표 기반, 자주 안 쓰니 우클릭 메뉴 대신 여기 — 10-27부터 선 우클릭에도)
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
    <div style={{ borderTop: `1px solid ${C.line}`, paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
      <button data-testid="insert-legend" onClick={onLegend} style={{ all: 'unset', cursor: 'pointer', textAlign: 'center', padding: '4px 0', borderRadius: 6, background: C.group, fontWeight: 600 }}>범례 넣기</button>
      <span style={{ fontSize: 11, color: C.muted }}>도면의 선 종류를 표로 — 선이 바뀌면 저절로 따라가요</span>
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

// 샘플 열기 — 지금 칠판을 그 내용으로 바꿈(개발 시험용 — 서버 없을 때 위 막대에만, 2026-10-27 칠판 칸에서 뺌)
const SampleSelect = ({ onPick }) => <select data-testid="sample-select" onChange={e => { const u = e.target.value; e.target.value = ''; if (u) onPick(u) }} defaultValue="" title="샘플 칠판으로 바꾸기 — 지금 칠판 내용이 바뀌어요(Ctrl+Z로 되돌리기)"
  style={{ font: "500 12px 'Pretendard', sans-serif", padding: '4px 6px', borderRadius: 6, border: `1px solid ${C.line}`, background: C.card, color: C.ink }}>
  <option value="">샘플 열기…</option>{SAMPLES.map(([n, u]) => <option key={u} value={u}>{n}</option>)}
</select>

// 「내 심볼에 추가」 창(2026-10-27 사용자 — KAIROS 아이콘 등을 심볼 칸에): 이름 + 이 브라우저 폴더(있는 것 고르기 또는 새 이름). 저장은 `mysym.js`
function SymAddForm({ init, folders, onOk, onClose }) {
  const NEW = '\u0000new', [name, setName] = useState(init.name || ''), [pick, setPick] = useState(folders.includes(init.folder) ? init.folder : folders[folders.length - 1] ?? NEW)   // init.folder = 끌어 놓은 폴더, [fresh, setFresh] = useState(folders.length ? '' : '내 심볼')
  const folder = pick === NEW ? fresh.trim() : pick, ok = !!name.trim() && !!folder
  const go = () => { if (ok) onOk(name.trim(), folder) }
  const inp = { height: 30, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 8px', font: "400 13px 'Pretendard', sans-serif" }
  return <div data-testid="symadd" onPointerDown={e => { if (e.target === e.currentTarget) onClose() }} onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') onClose(); if (e.key === 'Enter') go() }}
    style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    <div style={{ width: 300, background: C.card, border: `1px solid ${C.line}`, borderRadius: 12, padding: 16, boxShadow: '0 10px 30px rgba(0,0,0,.2)', display: 'flex', flexDirection: 'column', gap: 10, color: C.ink, font: "400 12px 'Pretendard', sans-serif" }}>
      <div style={{ font: "700 15px 'Pretendard', sans-serif" }}>내 심볼에 추가</div>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><span style={{ color: C.muted }}>이름</span>
        <input autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="예: 송신탑" style={inp} /></label>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}><span style={{ color: C.muted }}>폴더</span>
        {folders.length > 0 && <select value={pick} onChange={e => setPick(e.target.value)} style={inp}>
          {folders.map(f => <option key={f} value={f}>{f}</option>)}<option value={NEW}>＋ 새 폴더…</option></select>}
        {pick === NEW && <input value={fresh} onChange={e => setFresh(e.target.value)} placeholder="새 폴더 이름" style={inp} />}</label>
      <div style={{ fontSize: 11, color: C.muted, lineHeight: 1.5 }}>이 브라우저에 저장돼요. 다른 PC로는 도형 칸 「파일로 저장」 → 「파일 불러오기」.</div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 6 }}>
        <button onClick={onClose} style={{ all: 'unset', cursor: 'pointer', padding: '6px 12px', borderRadius: 6, border: `1px solid ${C.line}` }}>취소</button>
        <button disabled={!ok} onClick={go} style={{ all: 'unset', cursor: ok ? 'pointer' : 'default', opacity: ok ? 1 : 0.5, padding: '6px 14px', borderRadius: 6, background: '#da7756', color: '#fff', fontWeight: 600 }}>추가</button>
      </div>
    </div>
  </div>
}

// 접속자 = 이름 첫 글자 동그라미(2026-10-27 사용자: 이름을 잇대 쓰면 10명이면 잘림) — 4칸까지(넘치면 3명 + 「+N」), 색 = 칠판에서 그 사람이 고른 테두리 색, 누르면 공유 창(전체 목록)
const FACES = 4
const Faces = ({ list, onClick }) => { const shown = list.slice(0, list.length > FACES ? FACES - 1 : FACES), more = list.length - shown.length
  const dot = { width: 24, height: 24, borderRadius: '50%', marginLeft: -6, boxSizing: 'border-box', border: `2px solid ${C.bar}`, display: 'flex', alignItems: 'center', justifyContent: 'center', font: "700 11px 'Pretendard', sans-serif" }
  return <button data-testid="people" onClick={onClick} title={`지금 이 칠판에 ${list.length}명 — ${list.map(p => p.name + (p.me ? ' (나)' : '')).join(', ')}`} aria-label={`접속자 ${list.length}명`}
    style={{ all: 'unset', cursor: 'pointer', display: 'flex', alignItems: 'center', paddingLeft: 6 }}>
    {shown.map(p => <span key={p.id} style={{ ...dot, background: p.color, color: '#fff' }}>{[...(p.name || '?')][0]}</span>)}
    {more > 0 && <span style={{ ...dot, background: C.group, color: C.ink, fontSize: 10 }}>+{more}</span>}
  </button> }

// 칠판 고르기 — 새 칠판·내 칠판(2026-10-19 점검: 주소창에 `?board=`를 직접 쳐야만 옮겨 갈 수 있었음). 옮겨 가기 = 그 주소로 다시 열기(칠판 이름은 주소가 정함)
const TEST_BOARD = /^(claude|e2e)_/   // Claude·화면 시험이 만든 칠판은 서버 목록에서 숨김
const ago = s => { const d = Date.now() / 1000 - s; return d < 60 ? '방금' : d < 3600 ? `${Math.floor(d / 60)}분 전` : d < 86400 ? `${Math.floor(d / 3600)}시간 전` : `${Math.floor(d / 86400)}일 전` }
// 2026-10-27 사용자 점검: 이름 칸이 맨 위에 늘 있어 찾기 칸으로 보였음·보통은 「만들기」 먼저 → 「＋ 새 칠판」을 누르면 그 자리에 이름 칸.
// 샘플 열기는 개발 시험용이라 뺌(서버 없을 때 위 막대에만), 「저장」은 위 막대·Ctrl+S와 겹쳐 뺌(서버는 저절로 저장) — 아래는 파일 열기·내려받기만
// 같은 날 밤(사용자: Excalidraw처럼 — 처음엔 빈 칠판, 공유한 순간부터 남이 들어옴): 목록 = 「내 칠판」(이 브라우저가 만들거나 열어 본 것, `myboards.js`).
// 비밀번호 없는 서버(open)는 「＋ 새 칠판」 = 바로 칠판 코드만인 새 주소(2026-10-28 사용자 — 이름은 나중에 두 번 눌러, 문서 `title`) · 비밀번호·팀 서버는 전처럼 정한 이름 그대로 + 「이 서버의 칠판」(관리자 = 전부, 팀 = 그 팀 것)
// 칠판 코드는 줄에 안 보임(2026-10-28 사용자 「깔끔한 게 좋아」 — 코드가 필요한 건 알려 주는 사람이라 QR 화면·공유 창에, 줄은 툴팁에만). 이름 없는 칠판은 만든 때로 구별
const when = ms => { const d = new Date(ms), p = n => String(n).padStart(2, '0'); return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}` }
const BoardName = ({ name, title, at, bold }) => { const t = boardTitle(name, title)
  return <span data-testid="board-name" style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: bold ? 700 : 500 }}>{t}{t === UNTITLED && at > 0 && <span style={{ marginLeft: 4, fontWeight: 400, fontSize: 10.5, color: C.muted }}>· {when(at)}</span>}</span> }
// 줄마다 지금 접속자(2026-10-28 사용자 — 개수 대신: 남이 들어왔는지·나는 어디서 작업 중인지) — 위 막대 동그라미를 작게, 3칸까지(넘치면 2명 + 「+N」)
const MiniFaces = ({ list, myId, me }) => { if (!list?.length) return null
  const shown = list.slice(0, list.length > 3 ? 2 : 3), more = list.length - shown.length
  const dot = { width: 16, height: 16, flex: 'none', borderRadius: '50%', marginLeft: -4, boxSizing: 'border-box', border: `1.5px solid ${C.bar}`, display: 'flex', alignItems: 'center', justifyContent: 'center', font: "700 9px 'Pretendard', sans-serif" }
  return <span data-testid="board-people" style={{ display: 'flex', alignItems: 'center', paddingLeft: 4, flex: 'none' }}>
    {shown.map(p => { const nm = p.id === myId ? me || '나' : p.name; return <span key={p.id} style={{ ...dot, background: personColor(p.id), color: '#fff' }}>{[...(nm || '?')][0]}</span> })}
    {more > 0 && <span style={{ ...dot, background: C.group, color: C.ink, fontSize: 8 }}>+{more}</span>}</span> }
// 「＋ 새 칠판 ▾」 메뉴(2026-10-28 사용자 — 노션 왼쪽 위 「페이지·채팅·데이터베이스」처럼 새로 시작하는 길을 한곳에, 「새 칠판」은 바로 옆 큰 단추라 메뉴엔 뺌) — 우클릭 메뉴(`ctxmenu.jsx`)와 같은 모양
const MENU_BOX = { position: 'fixed', zIndex: 40, minWidth: 190, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, padding: 4, boxShadow: '0 6px 18px rgba(0,0,0,.22)', font: "400 12.5px 'Pretendard', sans-serif", color: C.ink }
const MENU_ROW = { all: 'unset', boxSizing: 'border-box', display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '5px 10px', borderRadius: 5, cursor: 'pointer' }
const menuHover = { onMouseEnter: e => { e.currentTarget.style.background = 'rgba(218,119,86,.14)' }, onMouseLeave: e => { e.currentTarget.style.background = 'transparent' } }
function BoardForm({ onClose, docked, open, myId, me, onDownload, children }) {   // docked = 왼쪽 판 「칠판」 칸(2026-10-23 — 위 막대 팝업에서 옮김), open = 비밀번호 없는 서버, myId·me = 내 접속 이름표(줄 동그라미의 「나」), onDownload = 지금 칠판 내려받기, children = 서버 없을 때 파일 단추들
  // 처음엔 지난번 서버 답으로 그림(「불러오는 중…」 → 목록으로 바뀌며 아래가 출렁였음 — 2026-10-28 사용자 「새 칠판 누르면 살짝 깜빡」)
  const cached = () => myBoards().filter(b => b.ok !== false || b.name === DOC_NAME).map(b => ({ name: b.name, title: b.title, mtime: b.mtime || 0, c: b.c || b.t }))
  const [list, setList] = useState(null), [mine, setMine] = useState(cached), [name, setName] = useState(''), [all, setAll] = useState(false), [making, setMaking] = useState(false), [why, setWhy] = useState(''), [menu, setMenu] = useState(null)
  const [newMenu, setNewMenu] = useState(null), [codeOn, setCodeOn] = useState(false), [codeText, setCodeText] = useState(''), [codeWhy, setCodeWhy] = useState(''), menuRef = useRef(null), moreRef = useRef(null), fileRef = useRef(null)
  const [del, setDel] = useState(null)   // 지울까요 확인 = { name }
  const [people, setPeople] = useState({}), [renaming, setRenaming] = useState(null), [renameText, setRenameText] = useState(''), [hov, setHov] = useState(null), [drag, setDrag] = useState(null), [over, setOver] = useState(null), clickT = useRef(null)
  // 서버가 아는 칠판만(+ 지금 것) — 빈 칠판도 남음: 열 때 서버에 빈 칠판을 바로 만듦(App, 2026-10-28 사용자: 칠판을 먼저 여러 개 만들고 작업할 수도).
  // 서버에 없는 이름 = 지운 칠판·팀 서버에서 우리 팀 것이 아닌 칠판(옛 기본 main 등)이라 빼야 함
  const loadMine = () => { const my = myBoards(); api.boardInfo(my.map(b => b.name)).then(info => { const at = new Map(info.map(b => [b.name, b]))
    noteBoards(my.map(b => (at.has(b.name) ? { name: b.name, ok: true, title: at.get(b.name).title || '', mtime: at.get(b.name).mtime } : { name: b.name, ok: false })))
    setMine(my.filter(b => at.has(b.name) || b.name === DOC_NAME).map(b => ({ ...(at.get(b.name) || { name: b.name, mtime: 0, fresh: true }), c: b.c || b.t }))) }) }
  useEffect(() => { loadMine(); if (!open) api.boards().then(setList); else setList([]) }, [open])   // eslint-disable-line react-hooks/exhaustive-deps
  const boardUrl = n => `${location.pathname}?board=${encodeURIComponent(n)}`, goTo = n => { location.href = boardUrl(n) }
  const clean = name.trim().replace(/[^\w\-가-힣]/g, '').slice(0, 64), taken = !open && !!list?.some(b => b.name === clean)
  const make = async () => { if (open) { goTo(newBoardName()); return }   // 비밀번호 없는 서버 = 누르면 바로 새 칠판(칠판 코드만 — 이름은 나중에, 2026-10-28 사용자: 만들 때마다 이름 치거나 한 번 더 누르기 불편)
    if (!clean) return
    if (!taken && (await api.session(clean)).board_ok === false) { setWhy('다른 팀이 쓰는 이름이에요 — 다른 이름으로 지어 주세요'); return }   // 팀 서버(§8 항목67) — 목록엔 우리 팀 것만 보여서 겹침을 모름
    goTo(clean) }
  const startNew = () => { setNewMenu(null); if (open) make(); else setMaking(true) }
  const closeMenu = () => { setNewMenu(null); setCodeOn(false); setCodeText(''); setCodeWhy('') }
  useEffect(() => { if (!newMenu) return   // 바깥 누르기 = 닫힘(▾ 다시 누르기는 ▾가 맡음)
    const down = e => { if (!menuRef.current?.contains(e.target) && !moreRef.current?.contains(e.target)) closeMenu() }
    window.addEventListener('pointerdown', down, true); return () => window.removeEventListener('pointerdown', down, true) }, [newMenu])   // eslint-disable-line react-hooks/exhaustive-deps
  const openCode = async () => { const r = boardFromText(codeText); setCodeWhy('')
    if (r.view) { location.href = `${location.pathname}?view=${r.view}`; return }
    if (r.board) { goTo(r.board); return }
    if (!r.code) return
    const hit = await api.boardByCode(r.code); if (hit.length) { goTo(hit[0].name); return }
    setCodeWhy('그 코드의 칠판이 없어요 — 글자를 다시 확인해 주세요') }
  // 파일로 새 칠판(2026-10-28 — 옛 「파일 열기」는 지금 칠판을 그 내용으로 통째로 바꿨음, 실수 한 번에 쓰던 칠판이 덮임) = 새 주소에 올리고 옮겨 감, 이름 = 파일 이름
  const fileNew = async e => { const f = e.target.files?.[0]; e.target.value = ''; closeMenu(); if (!f) return
    let doc; try { doc = parseDoc(await f.text()) } catch (err) { setWhy(`파일을 못 읽었어요 — ${err.message}`); return }
    const n = newBoardName(), body = doc.title ? doc : { ...doc, title: f.name.replace(/\.(ecad|json)$/i, '').slice(0, 60) }
    if (await api.putDoc(n, body)) goTo(n); else setWhy('새 칠판에 못 올렸어요 — 서버 연결을 확인해 주세요') }
  const exampleNew = async () => { closeMenu(); const n = newBoardName(); if (await api.example(n)) goTo(n); else setWhy('예시 칠판을 못 열었어요 — 서버 연결을 확인해 주세요') }   // 예시 칠판 하나 더(2026-10-28 — 처음 방문 때 받은 예시를 지웠을 때도)
  const myNames = new Set((mine || []).map(b => b.name))
  const others = (list || []).filter(b => !myNames.has(b.name)), shown = others.filter(b => all || !TEST_BOARD.test(b.name)), hidden = others.length - shown.length
  // 접속자 = 판이 열린 동안 3초마다(서버는 기억만 읽음 — 신호는 각 칠판 창이 보냄)
  const watch = [...myNames, ...shown.map(b => b.name)].slice(0, 200).join(',')
  useEffect(() => { if (!watch) return; let live = true; const tick = () => api.people(watch.split(',')).then(p => { if (live) setPeople(p) })
    tick(); const t = setInterval(tick, 3000); return () => { live = false; clearInterval(t) } }, [watch])
  // 이름 바꾸기(2026-10-28 사용자 — 두 번 누르기·우클릭·⋯) = 문서 `title`만, 주소(칠판 코드)는 그대로라 남에게 준 링크가 안 끊김
  const findB = n => (mine || []).concat(list || []).find(b => b.name === n)
  const startRename = n => { clearTimeout(clickT.current); setMenu(null); const t = boardTitle(n, findB(n)?.title); setRenameText(t === UNTITLED ? '' : t); setRenaming(n) }
  const commitRename = async () => { const n = renaming; if (!n) return; setRenaming(null)
    const t = renameText.trim().slice(0, 60), b = findB(n); if (t === (b?.title || '') || (!b?.title && t === boardLabel(n).title)) return
    const put = xs => xs?.map(x => (x.name === n ? { ...x, title: t } : x)); setMine(put); setList(put); noteBoards([{ name: n, title: t }])
    if (!(await api.setTitle(n, t))) loadMine() }   // 못 바꿨으면 원래 이름으로
  // 내려받기(2026-10-28 — 판 아래 단추에서 줄 메뉴로): 지금 칠판 = 화면 그대로(아직 안 보낸 것까지), 다른 칠판 = 서버 것
  const download = async n => { setMenu(null); if (n === DOC_NAME) { onDownload?.(); return }
    const text = await api.getDoc(n); if (!text) return
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' })); a.download = `${boardTitle(n, findB(n)?.title)}.ecad`; a.click(); URL.revokeObjectURL(a.href) }
  // 줄 누르기 = 그 칠판으로 — 두 번 누르기(이름 바꾸기)와 가르려고 잠깐 기다림(어차피 페이지를 다시 엶)
  const onRow = n => { if (renaming) return; clearTimeout(clickT.current); if (n === DOC_NAME) { onClose(); return } clickT.current = setTimeout(() => goTo(n), 230) }
  // 끌어서 순서 바꾸기(2026-10-28 사용자 — 누를 때마다 맨 위로 올라가던 것 대신) — 내 칠판만(이 브라우저 목록), 놓은 줄의 위·아래 절반으로 앞·뒤
  const dropRow = () => { const d = drag, o = over; setDrag(null); setOver(null); if (!d || !o || d === o.name) return
    const names = (mine || []).map(b => b.name).filter(x => x !== d), i = names.indexOf(o.name), before = o.after ? names[i + 1] : o.name
    moveBoard(d, before); setMine(m => { const at = new Map((m || []).map(b => [b.name, b])); return myBoards().map(b => at.get(b.name)).filter(Boolean) }) }
  const menuAt = (n, x, y) => setMenu({ name: n, mine: myNames.has(n), x, y })
  const row = b => { const cur = b.name === DOC_NAME, isMine = myNames.has(b.name), ppl = people[b.name] || [], edit = renaming === b.name, lit = cur ? 'rgba(218,119,86,.18)' : hov === b.name ? C.group : 'transparent', code = boardLabel(b.name).code
    const tip = `${boardTitle(b.name, b.title)}${code ? ` · 칠판 코드 ${code}` : ''} — 두 번 누르면 이름 바꾸기${isMine ? ' · 끌어서 순서 바꾸기' : ''}\n${b.fresh ? '아직 빈 칠판' : b.mtime ? `${ago(b.mtime)} 고침` : ''}${ppl.length ? ` · 지금 ${ppl.map(p => (p.id === myId ? `${me || '나'} (나)` : p.name)).join(', ')}` : ''}`
    return <div key={b.name} data-testid="board-row" data-board={b.name} role="button" tabIndex={0} title={edit ? '' : tip} draggable={isMine && !edit}
      onClick={() => onRow(b.name)} onDoubleClick={() => startRename(b.name)} onKeyDown={e => { if (edit) return; if (e.key === 'Enter') onRow(b.name); if (e.key === 'F2') startRename(b.name) }}
      onContextMenu={e => { e.preventDefault(); menuAt(b.name, e.clientX, e.clientY) }} onMouseEnter={() => setHov(b.name)} onMouseLeave={() => setHov(h => (h === b.name ? null : h))}
      onDragStart={e => { setDrag(b.name); e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('application/x-mb-board', b.name) }}   // 칠판 위 놓기(파일·주소)와 안 섞이게 따로 종류
      onDragOver={e => { if (!drag || !isMine) return; e.preventDefault(); const r = e.currentTarget.getBoundingClientRect(), after = e.clientY > r.top + r.height / 2; if (over?.name !== b.name || over.after !== after) setOver({ name: b.name, after }) }}
      onDrop={e => { e.preventDefault(); e.stopPropagation(); dropRow() }} onDragEnd={() => { setDrag(null); setOver(null) }}
      style={{ cursor: edit ? 'default' : 'pointer', display: 'flex', gap: 6, alignItems: 'center', minHeight: 24, padding: '3px 4px', borderRadius: 6, background: lit, opacity: drag === b.name ? 0.45 : 1, outline: 'none',
        boxShadow: over?.name === b.name ? `inset 0 ${over.after ? -2 : 2}px 0 #da7756` : 'none' }}>
      {edit ? <input data-testid="board-rename" autoFocus value={renameText} placeholder={UNTITLED} maxLength={60} onChange={e => setRenameText(e.target.value)} onBlur={commitRename} onFocus={e => e.target.select()}
          onClick={e => e.stopPropagation()} onDoubleClick={e => e.stopPropagation()}
          onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') e.currentTarget.blur(); if (e.key === 'Escape') { setRenameText(boardTitle(b.name, b.title)); setRenaming(null) } }}
          style={{ flex: 1, minWidth: 0, height: 22, boxSizing: 'border-box', border: '1px solid #da7756', borderRadius: 5, background: C.card, color: C.ink, padding: '0 6px', font: "500 12px 'Pretendard', sans-serif" }} />
        : <BoardName name={b.name} title={b.title} at={b.c || (b.mtime || 0) * 1000} bold={cur} />}
      {!edit && <MiniFaces list={ppl} myId={myId} me={me} />}
      {!edit && <button data-testid="board-more" aria-label="칠판 메뉴" title="이름 바꾸기·새 탭·주소 복사·내려받기·목록에서 빼기" onClick={e => { e.stopPropagation(); const r = e.currentTarget.getBoundingClientRect(); menuAt(b.name, r.left, r.bottom + 2) }}
        onDoubleClick={e => e.stopPropagation()}
        style={{ all: 'unset', cursor: 'pointer', flex: 'none', width: 18, textAlign: 'center', borderRadius: 4, color: C.muted, fontWeight: 700, lineHeight: '18px', visibility: hov === b.name || menu?.name === b.name ? 'visible' : 'hidden' }}>⋯</button>}
    </div> }
  const ok = open || !!clean
  const accent = { all: 'unset', cursor: 'pointer', background: '#da7756', color: '#fff', fontWeight: 600 }
  return <div data-testid="board-form" onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') { if (newMenu) closeMenu(); else onClose() } }} style={{ ...(docked ? { padding: '8px 10px' } : { position: 'absolute', top: 48, left: 0, zIndex: 20, width: 280, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: 10, boxShadow: '0 4px 14px rgba(0,0,0,.18)' }), display: 'flex', flexDirection: 'column', gap: 8, font: "400 12px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ flex: 1, font: docked ? "700 15px 'Pretendard', sans-serif" : "700 13px 'Pretendard', sans-serif" }}>칠판</span>
      {!making && <div style={{ display: 'flex' }}>   {/* 갈라진 단추(2026-10-28 사용자 고름) — 왼쪽 = 바로 새 칠판(한 번), ▾ = 칠판 코드로 열기·파일로 새 칠판 */}
        <button data-testid="board-new" onClick={startNew} title={open ? '새 칠판 만들기 — 누르면 바로 새 칠판으로 옮겨 가요(이름은 나중에 목록에서 두 번 눌러서)' : '새 칠판 만들기 — 이름을 정하면 그 칠판으로 옮겨 가요'}
          style={{ ...accent, padding: '3px 8px 3px 10px', borderRadius: '6px 0 0 6px' }}>＋ 새 칠판</button>
        <button ref={moreRef} data-testid="board-new-more" aria-label="새 칠판 메뉴" aria-expanded={!!newMenu} title="칠판 코드로 열기 · 파일로 새 칠판 · 예시 칠판 열기"
          onClick={e => { if (newMenu) { closeMenu(); return } const r = e.currentTarget.getBoundingClientRect(); setNewMenu({ x: Math.max(RAIL_W + 4, r.right - 200), y: r.bottom + 4 }) /* 아이콘 줄은 안 덮게 */ }}
          style={{ ...accent, padding: '3px 6px', borderRadius: '0 6px 6px 0', borderLeft: '1px solid rgba(255,255,255,.45)', fontSize: 10 }}>▾</button>
      </div>}
    </div>
    {newMenu && <div ref={menuRef} data-testid="board-new-menu" style={{ ...MENU_BOX, left: newMenu.x, top: newMenu.y, width: 200 }}>
      {!codeOn ? <>
        <button data-testid="board-code-open" onClick={() => setCodeOn(true)} style={MENU_ROW} {...menuHover} title="받은 칠판 코드(QR 밑 8자)나 칠판 주소를 넣어 그 칠판으로"><span style={{ width: 14, textAlign: 'center' }}>#</span>칠판 코드로 열기</button>
        <button data-testid="board-file-new" onClick={() => fileRef.current?.click()} style={MENU_ROW} {...menuHover} title=".ecad 파일을 새 칠판으로 열어요(지금 칠판은 그대로)"><span style={{ width: 14, textAlign: 'center' }}>↥</span>파일로 새 칠판</button>
        <button data-testid="board-example-new" onClick={exampleNew} style={MENU_ROW} {...menuHover} title="기능 소개로 채운 예시 칠판을 하나 더 열어요(지금 칠판은 그대로 — 예시를 지웠을 때도)"><span style={{ width: 14, textAlign: 'center' }}>★</span>예시 칠판 열기</button>
      </> : <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: 6 }}>
        <span style={{ fontSize: 11, color: C.muted }}>받은 칠판 코드(QR 밑 8자)나 주소</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <input data-testid="board-code" autoFocus value={codeText} onChange={e => { setCodeText(e.target.value); setCodeWhy('') }} placeholder="예: k7p2 qx9m"
            onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter') openCode(); if (e.key === 'Escape') closeMenu() }}
            style={{ flex: 1, minWidth: 0, height: 26, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 8px', font: 'inherit' }} />
          <button disabled={!codeText.trim()} onClick={openCode} style={{ ...accent, cursor: codeText.trim() ? 'pointer' : 'default', opacity: codeText.trim() ? 1 : 0.5, padding: '4px 10px', borderRadius: 6 }}>열기</button>
        </div>
        {codeWhy && <span data-testid="board-code-why" style={{ fontSize: 11, color: '#d44c47' }}>{codeWhy}</span>}
      </div>}
    </div>}
    <input ref={fileRef} data-testid="board-file-input" type="file" accept=".ecad,application/json" hidden onChange={fileNew} />
    {making && <div style={{ display: 'flex', gap: 6 }}>
      <input autoFocus value={name} onChange={e => { setName(e.target.value); setWhy('') }} placeholder="새 칠판 이름 (예: 송신소점검)" onKeyDown={e => { if (e.key === 'Enter') make(); if (e.key === 'Escape') { e.stopPropagation(); setMaking(false); setName('') } }}
        style={{ flex: 1, minWidth: 0, height: 26, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 8px', font: 'inherit' }} />
      <button disabled={!ok} onClick={make} style={{ ...accent, cursor: ok ? 'pointer' : 'default', opacity: ok ? 1 : 0.5, padding: '4px 10px', borderRadius: 6 }}>{taken ? '열기' : '만들기'}</button>
    </div>}
    {making && clean && clean !== name.trim() && <span style={{ fontSize: 11, color: C.muted }}>이름은 「{clean}」(글자·숫자·_·- 만)</span>}
    {why && <span data-testid="board-new-why" style={{ fontSize: 11, color: '#d44c47' }}>{why}</span>}
    {/* 「내 칠판」(2026-10-28 사용자 — 「— 이 브라우저」는 마우스 올리면 설명으로만) */}
    <span style={{ color: C.muted }} title="이 브라우저에서 만들거나 열어 본 칠판이에요 — 다른 PC·다른 브라우저엔 안 보여요(칠판 코드나 주소로 열면 그쪽 목록에도 들어가요)">내 칠판</span>
    <div data-testid="my-boards" onDragOver={e => { if (drag) e.preventDefault() }} onDrop={e => { e.preventDefault(); dropRow() }} style={{ display: 'flex', flexDirection: 'column', maxHeight: 300, overflowY: 'auto', margin: '-4px -4px 0' }}>
      {mine.map(row)}
    </div>
    {!open && (list === null || others.length > 0) && <>
      <span style={{ color: C.muted }}>이 서버의 칠판</span>
      <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 300, overflowY: 'auto', margin: '-4px -4px 0' }}>
        {list === null ? <span style={{ color: C.muted, padding: 4 }}>불러오는 중…</span> : shown.map(row)}
      </div>
      {hidden > 0 && <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: C.muted }}><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} />시험 칠판 {hidden}개도 보기</label>}</>}
    {children}
    {/* 줄 메뉴 = 우클릭·⋯(2026-10-28 — 우클릭을 모르면 못 찾음). 이름 바꾸기 = 문서 이름만(주소 그대로), 지우기는 없음(남과 같이 쓰는 칠판일 수 있음) — 「목록에서 빼기」 = 이 브라우저 목록에서만(칠판은 그대로) */}
    {menu && <FloatMenu at={menu} onClose={() => setMenu(null)} entries={[['이름 바꾸기', 'F2', () => startRename(menu.name)], ['새 탭에서 열기', '', () => { setMenu(null); window.open(boardUrl(menu.name), '_blank', 'noopener') }],
      ['주소 복사', '', () => { setMenu(null); navigator.clipboard?.writeText(location.origin + boardUrl(menu.name)) }], ['내려받기 (.ecad)', '', () => download(menu.name)],
      '-', ...(menu.mine && menu.name !== DOC_NAME ? [['목록에서 빼기', '', () => { setMenu(null); forgetBoard(menu.name); loadMine() }]] : []), ['칠판 지우기…', '', () => { setMenu(null); setDel({ name: menu.name }) }]]} />}
    {/* 칠판 지우기(2026-10-28 사용자) — 앱 안 확인 창(브라우저 confirm은 칠판 조작을 막음), 지금 들어와 있는 사람을 보여 줌. 서버 휴지통으로 옮김 */}
    {del && (() => { const t = boardTitle(del.name, findB(del.name)?.title), here = (people[del.name] || []).filter(p => p.id !== myId)
    const ring = { onFocus: e => { e.currentTarget.style.outline = '2px solid #d44c47' }, onBlur: e => { e.currentTarget.style.outline = 'none' } }   // all: unset이 초점 테두리를 지움
    const go = async () => { setDel(null); if (!(await api.deleteBoard(del.name))) { setWhy('지우지 못했어요 — 서버 연결을 확인해 주세요'); return }
        forgetBoard(del.name); if (del.name === DOC_NAME) location.href = location.pathname; else loadMine() }   // 지금 칠판을 지웠으면 쓰던(마지막) 칠판으로
      return <div style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onPointerDown={e => { if (e.target === e.currentTarget) setDel(null) }}>
        <div data-testid="board-delete" onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') setDel(null) }} style={{ width: 320, display: 'flex', flexDirection: 'column', gap: 10, padding: 18, borderRadius: 12, background: C.card, border: `1px solid ${C.line}`, boxShadow: '0 8px 28px rgba(0,0,0,.25)', font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
          <div style={{ font: "700 15px 'Pretendard', sans-serif" }}>「{t}」 칠판을 지울까요?</div>
          <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.55 }}>같이 쓰는 사람도 이 칠판을 더는 못 열어요(대화·그림·PDF 포함). 서버 휴지통으로 옮겨서, 서버를 맡은 사람은 되살릴 수 있어요.</div>
          {here.length > 0 && <div data-testid="board-delete-here" style={{ fontSize: 12, color: '#d44c47', fontWeight: 600 }}>지금 {here.map(p => p.name).join(', ')} 님이 이 칠판에 있어요</div>}
          <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>
            {/* 엔터 = 지우기(2026-10-28 사용자 — 두 번 일부러 눌러 온 창이고 휴지통으로 감), 초점 테두리로 엔터가 누를 단추를 보여 줌 · Esc·바깥 = 취소 */}
            <button onClick={() => setDel(null)} {...ring} style={{ all: 'unset', cursor: 'pointer', padding: '5px 12px', borderRadius: 6, border: `1px solid ${C.line}`, outlineOffset: 2 }}>취소</button>
            <button data-testid="board-delete-ok" autoFocus onClick={go} {...ring} style={{ all: 'unset', cursor: 'pointer', padding: '5px 12px', borderRadius: 6, background: '#d44c47', color: '#fff', fontWeight: 600, outline: '2px solid #d44c47', outlineOffset: 2 }}>지우기</button>
          </div></div></div> })()}
  </div>
}

// 왼쪽 판(2026-10-23 사용자 — Foxit·PDF-XChange처럼 아이콘 레일 + 판, 오른쪽 KAIROS 창과 대칭으로 위 막대 아래부터 바닥까지). 레일 칸 = 칠판·도형·프레임·레이어,
// 열린 칸을 다시 누르면 판이 접힘(레일만 — VS Code와 같게, 따로 접기 단추는 위 막대와 헷갈려 뺌 — 사용자). 미니맵은 판 맨 아래에 늘(칸을 바꿔도 보이게).
// 카드마다 접기는 없앰(자리가 고정이라 접어도 칠판이 안 넓어짐 — 사용자). ⚠ 10-07 「레일 = 번거로움」·10-11 「도형·레이어 카드 합치지 않기」를 이번에 바꿈(사용자 선택 — 대칭·접으면 칠판이 가장 넓음)
export const RAIL_W = 40, DOCK_W = 192, DOCK_MAX = 400   // 레일 40(이름 유지)·판 192 = 미니맵 기준 최소, 경계를 끌면 400까지(2026-10-23 사용자 — 프레임 이름이 잘려 보임)
const svgI = d => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`
const DOCK_ICONS = { shape: svgI('<rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1"/><circle cx="17" cy="7.3" r="3.8"/><path d="M7.3 13.5l4 7h-8z"/><path d="M17 13.5l3.8 3.5-3.8 3.5-3.8-3.5z"/>'),
  layer: svgI('<path d="M12 3.5l8.5 4.5-8.5 4.5-8.5-4.5z"/><path d="M3.5 12l8.5 4.5 8.5-4.5"/><path d="M3.5 16l8.5 4.5 8.5-4.5"/>') }
const DOCK_TABS = [['board', '칠판', '칠판 — 새 칠판·최근 칠판·열기·내려받기'], ['shape', '도형', '도형·심볼 — 칠판으로 끌거나 눌러서 그리기'], ['frame', '프레임', '프레임 — 순서 = 출력·발표 순서'], ['layer', '레이어', '레이어 — 보이기·잠그기·그리는 중']]
function Dock({ tab, setTab, panes, mini, width, setWidth, help, onHelp }) {   // mini(w) = 그 판 폭의 미니맵, help = 도움말 카드가 열렸나
  return <div data-testid="dock" style={{ display: 'flex', flex: 'none', minHeight: 0, background: C.bar, borderRight: `1px solid ${C.line}` }}>
    <div style={{ width: RAIL_W, flex: 'none', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, paddingTop: 8, borderRight: tab ? `1px solid ${C.line}` : 'none' }}>
      {DOCK_TABS.map(([k, label, tip]) => { const on = tab === k, ic = DOCK_ICONS[k] || ICONS[k]
        return <button key={k} data-testid={`dock-${k}`} aria-label={`${label} 판`} aria-pressed={on} title={on ? `${label} 판 접기` : tip} onClick={() => setTab(on ? '' : k)}
          style={{ all: 'unset', cursor: 'pointer', width: 36, padding: '6px 0 4px', borderRadius: 8, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, font: "500 10px 'Pretendard', sans-serif",
            color: on ? C.accent : C.ink, background: on ? 'rgba(218,119,86,.18)' : 'transparent' }}
          onMouseEnter={e => { if (!on) e.currentTarget.style.background = 'rgba(218,119,86,.10)' }} onMouseLeave={e => { e.currentTarget.style.background = on ? 'rgba(218,119,86,.18)' : 'transparent' }}>
          <span aria-hidden style={{ width: 20, height: 20, display: 'block', color: on ? C.accent : 'var(--mb-icon)' }} dangerouslySetInnerHTML={{ __html: ic.replace('<svg ', '<svg width="20" height="20" ') }} />{label}</button> })}
      {/* 도움말 = 레일 맨 아래 「?」(2026-10-25 사용자 — 옛 빈 곳 우클릭 「글쇠 도움말」 대신. 나중에 사용설명서 페이지가 생기면 카드 안에 길) */}
      <button data-testid="help-btn" data-help-btn aria-label="도움말" aria-pressed={help} title="도움말 — 글쇠 모음(F1)" onClick={onHelp}
        style={{ all: 'unset', cursor: 'pointer', marginTop: 'auto', marginBottom: 8, width: 28, height: 28, borderRadius: 14, display: 'flex', alignItems: 'center', justifyContent: 'center',
          font: "700 14px 'Pretendard', sans-serif", color: help ? C.accent : 'var(--mb-icon)', border: `1.5px solid ${help ? C.accent : 'var(--mb-icon)'}`, boxSizing: 'border-box' }}>?</button>
    </div>
    {tab && <div data-testid="dock-panel" style={{ width, flex: 'none', display: 'flex', flexDirection: 'column', minHeight: 0, position: 'relative' }}>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>{panes[tab]}</div>
      {mini(width - 16)}
      {/* 폭 조절 — 오른쪽 경계 끌기(192~400), 두 번 누르면 192 */}
      <div data-testid="dock-resize" title="끌어서 판 폭 조절 · 두 번 누르면 기본 폭" onDoubleClick={() => setWidth(DOCK_W)}
        onPointerDown={e => { e.preventDefault(); const x0 = e.clientX, w0 = width, el = e.currentTarget; el.setPointerCapture(e.pointerId)
          const mv = ev => setWidth(Math.max(DOCK_W, Math.min(DOCK_MAX, Math.round(w0 + ev.clientX - x0)))), up = () => { el.removeEventListener('pointermove', mv); el.removeEventListener('pointerup', up) }
          el.addEventListener('pointermove', mv); el.addEventListener('pointerup', up) }}
        style={{ position: 'absolute', top: 0, bottom: 0, right: -4, width: 8, cursor: 'col-resize', zIndex: 3 }}
        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(218,119,86,.35)' }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }} />
    </div>}
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
        {prev?.error ? <span style={{ color: C.muted }}>{prev.error}</span> : !prev?.pages ? <div data-testid="export-skeleton" className="mb-pulse" style={{ display: 'flex', gap: 8 }}><style>{'@keyframes mb-pulse{50%{opacity:.45}}.mb-pulse{animation:mb-pulse 1.6s ease-in-out infinite}'}</style>
            {[0, 1, 2].map(i => <div key={i} style={{ width: 118, height: 160, borderRadius: 4, background: 'rgba(128,128,128,.14)' }} />)}</div>
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
function LoginForm({ onDone, nameOnly = false, title = '' }) {   // nameOnly = 편집 초대 링크로 들어옴(비밀번호 칸 없음), title = 칠판 이름(문서 `title` — 서버 /api/session)
  const [pw, setPw] = useState(''), [name, setName] = useState(() => { try { return localStorage.getItem('mb.name') || '' } catch { return '' } }), [err, setErr] = useState('')
  const go = async () => { if (!name.trim()) { setErr('이름을 적어 주세요(누가 접속했는지 보여요)'); return }
    if (!nameOnly && !(await api.login(pw))) { setErr('비밀번호가 맞지 않아요'); return }
    try { localStorage.setItem('mb.name', name.trim()) } catch { /* 기억 못 해도 그만 */ } onDone(name.trim()) }
  const inp = { height: 30, boxSizing: 'border-box', border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 10px', font: 'inherit' }
  return <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.board, font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ width: 300, display: 'flex', flexDirection: 'column', gap: 10, padding: 20, borderRadius: 12, border: `1px solid ${C.line}`, background: C.card, boxShadow: '0 6px 20px rgba(0,0,0,.12)' }}>
      <div style={{ font: "700 16px 'Pretendard', sans-serif" }}>Magic Board · 「{boardTitle(DOC_NAME, title)}」</div>
      <div style={{ color: C.muted, fontSize: 12 }}>{nameOnly ? '초대받은 칠판이에요. 내 이름을 적어 주세요(같이 쓰는 사람에게 보여요).' : '같이 쓰는 칠판이에요. 팀 비밀번호와 내 이름을 적어 주세요.'}</div>
      <input autoFocus placeholder="이름 (예: 김기자)" value={name} onChange={e => setName(e.target.value)} onKeyDown={e => { if (nameOnly && e.key === 'Enter') go() }} style={inp} />
      {!nameOnly && <input type="password" placeholder="팀 비밀번호" value={pw} onChange={e => setPw(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') go() }} style={inp} />}
      {err && <div style={{ color: '#d44c47', fontSize: 12 }}>{err}</div>}
      <button onClick={go} style={{ all: 'unset', cursor: 'pointer', textAlign: 'center', padding: '7px 0', borderRadius: 6, background: '#da7756', color: '#fff', fontWeight: 600 }}>들어가기</button>
    </div></div>
}
// 「공유」 — 노션처럼 두 탭(2026-10-19 사용자): 공유 = 편집 초대 링크(비밀번호 없이 이름만 적고 편집) + 지금 접속한 사람, 게시 = 로그인 없이 보기·발표만
function ShareForm({ onClose, people = [], title = '' }) {   // people = [{ id, name, me }] — 사람(창)마다 하나, 이름이 같아도 따로, title = 칠판 이름(QR 화면)
  const [tab, setTab] = useState('share')
  const [tok, setTok] = useState(undefined), [inv, setInv] = useState(undefined), [msg, setMsg] = useState(''), [qr, setQr] = useState(null)   // qr = 크게 띄운 링크 { link, view }
  useEffect(() => { api.getPublish().then(setTok); api.getInvite().then(r => setInv(r || { token: null, password: true })) }, [])
  const viewLink = tok ? `${location.origin}/?view=${tok}` : ''
  const board = `${location.origin}/?board=${encodeURIComponent(DOC_NAME)}`, editLink = inv?.token ? `${board}&join=${inv.token}` : ''
  const setPub = async (on, renew) => { const t = await api.setPublish(on, renew); setTok(on ? t : null); setMsg(on ? (renew ? '새 링크 — 옛 링크는 이제 안 열려요' : '게시했어요') : '게시를 껐어요 — 링크가 안 열려요') }
  const setInvT = async (on, renew) => { const t = await api.setInvite(on, renew); setInv(v => ({ ...v, token: on ? t : null })); setMsg(on ? (renew ? '새 초대 링크 — 옛 링크로는 이제 못 들어와요' : '초대 링크를 켰어요') : '초대 링크를 껐어요 — 이제 팀 비밀번호로만') }
  const copy = l => navigator.clipboard?.writeText(l).then(() => setMsg('링크를 복사했어요'), () => setMsg('복사가 막혔어요 — 칸을 눌러 직접 복사'))
  const b = (bg, fg = '#fff') => ({ all: 'unset', cursor: 'pointer', padding: '5px 10px', borderRadius: 6, background: bg, color: fg, fontWeight: 600, fontSize: 12 })
  const linkBox = l => <input readOnly value={l} onFocus={e => e.target.select()} style={{ height: 26, border: `1px solid ${C.line}`, borderRadius: 6, background: 'transparent', color: C.ink, padding: '0 6px', font: 'inherit' }} />
  const qrBtn = (link, view = false) => <button data-testid="qr-btn" style={b('transparent', C.ink)} title="큰 화면에 QR — 휴대폰 카메라로 비추면 바로 들어와요" onClick={() => setQr({ link, view })}>QR 크게</button>
  const tabBtn = (k, t) => <button key={k} data-testid={'share-tab-' + k} onClick={() => { setTab(k); setMsg('') }} style={{ all: 'unset', cursor: 'pointer', padding: '4px 2px', borderBottom: `2px solid ${tab === k ? C.ink : 'transparent'}`, fontWeight: tab === k ? 700 : 400, color: tab === k ? C.ink : C.muted }}>{t}</button>
  return <div onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') onClose() }} style={{ position: 'absolute', top: 48, right: 0, zIndex: 20, width: 340, background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: 12, boxShadow: '0 4px 14px rgba(0,0,0,.18)', display: 'flex', flexDirection: 'column', gap: 8, font: "400 12px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ display: 'flex', gap: 14, borderBottom: `1px solid ${C.line}`, fontSize: 13 }}>{tabBtn('share', '공유')}{tabBtn('publish', '게시')}</div>
    {tab === 'share' ? <>
      <div style={{ color: C.muted }}>같이 고칠 사람에게 보내는 링크예요. 들어오면 이름만 적고 바로 편집해요.</div>
      {inv === undefined ? <span style={{ color: C.muted }}>확인 중…</span> : !inv.password ? <>
        <div data-testid="share-open">이 주소가 곧 열쇠예요 — 받은 사람은 처음 한 번 이름만 적고 바로 같이 고쳐요. 주소를 모르는 사람은 이 칠판을 찾을 수 없어요.</div>{linkBox(board)}
        <div style={{ display: 'flex', gap: 6 }}><button style={b('#da7756')} onClick={() => copy(board)}>주소 복사</button>{qrBtn(board)}</div>
        {boardLabel(DOC_NAME).code && <div data-testid="share-code" style={{ fontSize: 11.5, color: C.muted }}>칠판 코드 <b style={{ font: "700 13px ui-monospace, Consolas, monospace", letterSpacing: '.12em', color: C.ink }}>{boardLabel(DOC_NAME).code.slice(0, 4)} {boardLabel(DOC_NAME).code.slice(4)}</b> — 말로 알려 줄 때(받은 사람은 칠판 판 「▾ › 칠판 코드로 열기」)</div>}</>
      : inv.token ? <>{linkBox(editLink)}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button style={b('#da7756')} onClick={() => copy(editLink)}>링크 복사</button>{qrBtn(editLink)}
          <button style={b('transparent', C.ink)} onClick={() => setInvT(true, true)}>새 링크로 바꾸기</button>
          <button style={b('transparent', '#d44c47')} onClick={() => setInvT(false)}>초대 끄기</button></div>
        <div style={{ fontSize: 11, color: C.muted }}>링크가 퍼지면 누구나 고칠 수 있어요 — 일이 끝나면 끄거나 새 링크로</div></>
      : <><div><button data-testid="invite-on" style={b('#da7756')} onClick={() => setInvT(true)}>편집 초대 링크 만들기</button></div>
        <div style={{ fontSize: 11, color: C.muted }}>링크가 없을 때는 팀 비밀번호로만 들어와요</div></>}
      <div style={{ borderTop: `1px solid ${C.line}`, paddingTop: 8, display: 'flex', flexDirection: 'column', gap: 4 }}>
        <span style={{ fontWeight: 600 }}>지금 이 칠판에 {people.length}명</span>
        {people.map(p => <span key={p.id} style={{ color: p.me ? C.ink : C.muted }}>• {p.name}{p.me ? ' (나)' : ''}</span>)}</div>
    </> : <>
      <div style={{ color: C.muted }}>로그인 없이 열려요. 고치기·대화는 안 되고, 여기서 고친 건 바로 보여요(큰 TV 발표용).</div>
      {tok === undefined ? <span style={{ color: C.muted }}>확인 중…</span> : tok ? <>{linkBox(viewLink)}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <button style={b('#da7756')} onClick={() => copy(viewLink)}>링크 복사</button>{qrBtn(viewLink, true)}
          <button style={b('transparent', C.ink)} onClick={() => window.open(viewLink, '_blank', 'noopener')}>열어 보기</button>
          <button style={b('transparent', C.ink)} onClick={() => setPub(true, true)}>새 링크로 바꾸기</button>
          <button style={b('transparent', '#d44c47')} onClick={() => setPub(false)}>게시 끄기</button></div></> : <div><button style={b('#da7756')} onClick={() => setPub(true)}>게시하기</button></div>}
    </>}
    {msg && <div style={{ color: '#da7756' }}>{msg}</div>}
    {qr && <QrBig pop="share" link={qr.link} view={qr.view} code={qr.view ? '' : boardLabel(DOC_NAME).code} title={title} onClose={() => setQr(null)} />}
  </div>
}

function App({ team, openServer }) {   // team = 팀 서버(§8 항목67)에서 내 팀 이름(관리자 = '관리자'), 팀 없는 서버면 없음 · openServer = 비밀번호 없는 서버(칠판 주소 = 열쇠)
  const [tableOpen, setTableOpen] = useState(false), [exportOpen, setExportOpen] = useState(false), [webOpen, setWebOpen] = useState(false)
  const [dockTab, setDockTabS] = useState(() => { try { const v = localStorage.getItem('mb-dock'); return v ?? (window.innerWidth < NARROW_W ? '' : 'shape') } catch { return 'shape' } })   // 왼쪽 판 열린 칸('' = 접힘) — 이 브라우저에 기억, 좁은 창은 처음엔 접힘
  const setDockTab = v => { setDockTabS(v); try { localStorage.setItem('mb-dock', v) } catch { /* 기억 못 해도 그만 */ } }
  const [dockW, setDockWS] = useState(() => { try { return Math.max(DOCK_W, Math.min(DOCK_MAX, +localStorage.getItem('mb-dock-w') || DOCK_W)) } catch { return DOCK_W } })   // 왼쪽 판 폭 — 이 브라우저에 기억
  const setDockW = v => { setDockWS(v); try { localStorage.setItem('mb-dock-w', String(v)) } catch { /* 기억 못 해도 그만 */ } }
  const [chatOpen, setChatOpen] = useState(() => { if (isPhone()) return false; try { return localStorage.getItem('mb-chat-open') !== '0' } catch { return true } }), [selKey, setSelKey] = useState('')   // 대화창 열림은 이 브라우저에 기억(기본 열림 — 화면 원칙: 작업공간 + AI 대화창), 휴대폰은 칠판부터(대화창이 화면 전체라)
  useEffect(() => { try { localStorage.setItem('mb-chat-open', chatOpen ? '1' : '0') } catch { /* 기억 못 해도 그만 */ } }, [chatOpen])
  const [chatW, setChatWS] = useState(() => { try { return chatClamp(+localStorage.getItem('mb-chat-w') || CHAT_W) } catch { return CHAT_W } })   // 대화창 폭 — 이 브라우저에 기억(왼쪽 판 `mb-dock-w`와 같게)
  const setChatW = v => { setChatWS(v); try { localStorage.setItem('mb-chat-w', String(v)) } catch { /* 기억 못 해도 그만 */ } }
  const [narrow, setNarrow] = useState(() => window.innerWidth < NARROW_W)   // 좁은 창 = 위 막대 아이콘만 + 대화창은 칠판 위에 뜸
  const [phone, setPhone] = useState(isPhone), phoneRef = useRef(phone); phoneRef.current = phone
  useEffect(() => { const on = () => { setNarrow(window.innerWidth < NARROW_W); setPhone(isPhone()) }; window.addEventListener('resize', on); return () => window.removeEventListener('resize', on) }, [])
  // 휴대폰 = 브라우저가 화면 전체를 그림처럼 키우지 않게(2026-10-27 사용자: 확대하면 뭉개짐 — 칠판 밖(위·아래 막대·대화창)을 벌리면 브라우저 확대가 됐음, 아이폰 Safari는 칠판의 touch-action도 무시)
  // 확대는 칠판 두 손가락(Editor)만 — 글자를 다시 그려 또렷함
  useEffect(() => { if (!phone) return; const meta = document.querySelector('meta[name=viewport]'), old = meta?.content
    meta?.setAttribute('content', 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no')
    const stop = e => e.preventDefault(); document.addEventListener('gesturestart', stop); document.addEventListener('gesturechange', stop)   // 아이폰 Safari 확대 몸짓
    return () => { if (old) meta.setAttribute('content', old); document.removeEventListener('gesturestart', stop); document.removeEventListener('gesturechange', stop) } }, [phone])
  const [activeLayer, setActiveLayer] = useState('default')   // 「그리는 중」 레이어(파일을 열면 기본부터 — 데스크톱 `_apply_loaded_layers`)
  const [model, setModel] = useState(() => fromEcad(emptyDoc()))
  const [cam, setCam] = useState({ x: 0, y: 0, z: 1 })   // 화면 = 칠판 × z + (x, y)
  const [tool, setTool] = useState('select')
  const [keepTool, setKeepToolS] = useState(() => { try { return localStorage.getItem('mb-keep-tool') === '1' } catch { return false } })   // 「도구 유지」 — 이 브라우저에 기억
  const keepRef = useRef(keepTool); keepRef.current = keepTool
  const toggleKeep = () => { const v = !keepRef.current; keepRef.current = v; setKeepToolS(v); try { localStorage.setItem('mb-keep-tool', v ? '1' : '0') } catch { /* 기억 못 해도 그만 */ }
    setStatus(v ? '도구 유지 켬 — 그린 뒤에도 그 도구 그대로(Esc = 선택으로)' : '도구 유지 끔 — 하나 그리면 선택으로 돌아가요') }
  const [status, setStatus] = useState('')
  const [saveNote, setSaveNote] = useState('')   // 저장 상태 글 — 화면엔 안 보이게(시험 `waitSaved`가 글을 찾음)
  // 어두운 화면(데스크톱 🌙와 같은 뜻) — 고른 값은 이 브라우저에 기억, 없으면 시스템 설정(next.html이 첫 값을 정함)
  const [dark, setDark] = useState(() => document.documentElement.dataset.theme === 'dark')
  setInkDark(dark)   // 칠판 기본 잉크(검정 ↔ 흰색) — 그리기 전에
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light' }, [dark])
  const [full, setFull] = useState(!!document.fullscreenElement)   // 전체 화면(F11로 들어간 브라우저 전체 화면은 브라우저가 알려 주지 않아 여기선 모름)
  useEffect(() => { const on = () => setFull(!!document.fullscreenElement); document.addEventListener('fullscreenchange', on); return () => document.removeEventListener('fullscreenchange', on) }, [])
  const toggleFull = () => { try { if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen() } catch { /* 막힌 환경이면 그대로 */ } }
  const toggleDark = () => setDark(d => { try { localStorage.setItem('mb.theme', d ? 'light' : 'dark') } catch { /* 기억 못 해도 그만 */ } return !d })
  const [server, setServer] = useState(false), [srvKnown, setSrvKnown] = useState(false)   // srvKnown = 서버 답을 받음(대화창도 그 뒤에 — 처음 방문의 예시 대화가 복사된 뒤 읽게, 2026-10-28)
  // 서버 답 전(첫 0.1초)에도 서버 있는 모습으로 그림 — 「Magic Board」·흐린 공유·동그라미 없음 → 바뀌며 위 막대가 좌우로 밀렸음(2026-10-28 사용자 「새 칠판 누르면 살짝 깜빡」)
  const live = server || !srvKnown
  const [me, setMe] = useState(() => { try { return localStorage.getItem('mb.name') || '' } catch { return '' } }), [others, setOthers] = useState([]), [shareOpen, setShareOpen] = useState(false)
  const sync = useRef({ base: null, rev: 0, busy: false, again: false, id: Math.random().toString(36).slice(2, 10) }), modelRef = useRef(model); modelRef.current = model
  const box = useRef(null), size = useSize(box), file = useRef(null), ed = useRef(null), saveT = useRef(null)

  const fit = useCallback((items, s) => {
    const b = docBounds(items); if (!b) return
    // 처음 열 때(서버 답)는 화면 크기를 재기 전 값(1×1)을 붙잡은 함수가 불려 배율 2%가 됐다 — 그 자리에서 직접 잰다
    if (!s) { const r = box.current?.getBoundingClientRect(); s = r && r.width > 1 ? { w: r.width, h: r.height } : size }
    const L = phoneRef.current ? 0 : Math.min(LEFT_CARDS, s.w / 4)   // 왼쪽 카드(도형·심볼·레이어) 밑도 빼고 — 맨 왼쪽 메모가 카드에 가렸음(2026-10-19 점검, Editor `showIds`와 같은 220)
    s = { ...s, w: s.w - rightInset(box.current) - L }   // 좁은 창의 뜬 대화창 밑은 빼고 맞춤(그 자리에서 읽음 — 이 함수는 옛 값을 붙잡고 불릴 수 있음)
    const pad = 40, z = Math.min(ZMAX, Math.max(ZMIN, Math.min((s.w - 2 * pad) / Math.max(b.w, 1), (s.h - 2 * pad) / Math.max(b.h, 1), 1)))
    const c = { z, x: L + s.w / 2 - (b.x + b.w / 2) * z, y: s.h / 2 - (b.y + b.h / 2) * z }
    setCam(c); return c   // 옮긴 자리를 돌려줌 — Z 한 번 더(보던 자리로)가 다음 화면 그리기를 안 기다리게
  }, [size])
  // 서버 칠판을 다시 열면 이 브라우저에서 마지막에 보던 자리·배율로(없거나 못 읽으면 전체 맞추기). 파일·샘플은 늘 전체 맞추기
  const camKey = `mb.cam.${DOC_NAME}`, camReady = useRef(false)
  const savedCam = () => { try { const c = JSON.parse(localStorage.getItem(camKey)); return c && [c.x, c.y, c.z].every(Number.isFinite) && c.z > ZMIN ? c : null } catch { return null } }   // 최저 배율 = 아래 2% 버그로 저장된 값일 수 있음 → 전체 맞추기
  // 기억한 자리에 도형이 하나도 안 보이면(다른 사람이 옮겼거나 빈 곳을 보다 닫음) 전체 맞추기 — 300%로 빈 칠판처럼 열렸음(2026-10-19 점검)
  const camShowsAny = (c, items) => { const r = box.current?.getBoundingClientRect(); if (!r || r.width < 2) return true
    const vx = -c.x / c.z, vy = -c.y / c.z, vw = (r.width - rightInset(box.current)) / c.z, vh = r.height / c.z
    return items.some(it => { const b = docBounds([it]); return b && b.x < vx + vw && b.x + b.w > vx && b.y < vy + vh && b.y + b.h > vy }) }
  const open = useCallback((doc, how, keepCam = false, fromServer = false) => { const m = { ...fromEcad(doc), rev: doc.rev || 0 }; setModel(m); modelRef.current = m
    if (fromServer) { sync.current.base = snapshotModel(m); sync.current.rev = doc.rev || 0 }   // 서버에서 받은 것 = 맞춘 기준
    else if (sync.current.base) saveServerDoc(toEcad(m)).then(rev => { if (typeof rev === 'number') { sync.current.base = snapshotModel(m); sync.current.rev = rev } })   // 파일·샘플을 이 칠판에 열기 = 통째 바꿈
    setActiveLayer('default'); ed.current?.reset(); const c = keepCam && savedCam(); if (c && camShowsAny(c, m.items)) setCam(c); else fit(m.items); camReady.current = true; setStatus(`${how} · ${m.items.length}개`) }, [fit])   // eslint-disable-line
  const openSample = async u => { try { open(parseDoc(await (await fetch(u)).text()), u.split('/').pop()) } catch (err) { setStatus('샘플 열기 실패: ' + err.message) } }
  useEffect(() => { if (!camReady.current) return; const t = setTimeout(() => { try { localStorage.setItem(camKey, JSON.stringify(cam)) } catch { /* 저장 못 해도 그만 */ } }, 300); return () => clearTimeout(t) }, [cam])   // eslint-disable-line

  // 공동작업 맞추기(2026-10-18) — 고친 뒤 0.6초 쉬면 바뀐 도형만 보내고(부분 저장), 2초마다 남이 바꾼 것을 받아 내 안 보낸 변경을 그 위에 다시 얹음
  const pull = useCallback(async (since = null, wait = 0) => {
    const S = sync.current; if (!S.base || S.busy || ed.current?.syncBusy?.()) return   // 글 고치는 중엔 받음(고치는 그 도형은 내 것이 이김 — rebase) — 2026-10-19
    const doc = await api.since(since ?? S.rev, wait).catch(() => null); if (doc === 'gone') { setGone(true); return } if (!doc) return
    if (S.busy || ed.current?.syncBusy?.()) return   // 받는 사이 끌기 등을 시작했으면 다음 차례에
    // 늦게 온 옛 판·내 저장의 메아리(기다리는 사이 내가 그 판까지 저장함) = 받을 것 없음 — 덮으면 방금 되돌린 것이 다시 살아났음(2026-10-28 flow35, 빈 칠판을 열 때 만들면서 자주 걸림).
    // 같은 판 번호는 저장 뒤 남의 변경을 받는 길(`flush` → pull(rev0))만 받음
    if ((doc.rev || 0) < S.rev || (since == null && (doc.rev || 0) === S.rev)) return
    const remote = { ...fromEcad(doc), rev: doc.rev || 0 }, base = S.base
    const merged = rebase(remote, modelRef.current, base)
    S.base = snapshotModel(remote); S.rev = remote.rev; modelRef.current = merged; setModel(merged)
    if (diffModel(S.base, merged)) flush()   // 안 보낸 내 변경이 남아 있으면 이어서 보냄
  }, [])   // eslint-disable-line
  const flush = useCallback(async () => {
    const S = sync.current; if (!S.base) return
    if (S.busy) { S.again = true; return }
    const m = modelRef.current, p = diffModel(S.base, m); if (!p) { setSaveNote(`서버 「${DOC_NAME}」에 저장됨`); return }   // 보낼 게 없음 = 이미 저장됨(「고치는 중…」이 남아 있었음, 2026-10-19 점검)
    S.busy = true; const rev0 = S.rev
    try {
      const rev = await api.patch({ base: rev0, ...p })
      if (rev === 'gone') { setGone(true); return }   // 다른 창에서 지운 칠판 — 저장 안 됨(띠로 알림)
      if (rev == null) { setStatus('서버 저장 실패 — 다시 들어가야 할 수도(비밀번호)'); return }
      S.base = snapshotModel(m); S.rev = rev; setSaveNote(`서버 「${DOC_NAME}」에 저장됨`)
      if (rev > rev0 + 1) { S.busy = false; await pull(rev0) }   // 그사이 남도 고쳤음 — 바로 받아 옴
    } catch { setStatus('서버 연결 끊김') } finally { S.busy = false; if (S.again) { S.again = false; flush() } }
  }, [pull])
  const onCommit = useCallback(() => {
    if (!server) { setStatus('고침 — 서버 없음, 「내려받기」로 저장'); return }
    setSaveNote('고치는 중…'); clearTimeout(saveT.current)   // 평소 저장은 알림 없이(2026-10-27 사용자: 고칠 때마다 뜰 필요 없음) — 실패·끊김만 알림
    saveT.current = setTimeout(flush, 150)   // 0.6 → 0.15초(2026-10-19 사용자: 거의 실시간)
  }, [server, flush])
  // 받아 오기 = 롱 폴링 — 서버가 바뀔 때까지 들고 있다가 바로 돌려줌(2초마다 묻던 것 → 0.x초, 2026-10-19). 끌기 등으로 못 받으면 0.3초 뒤 다시
  useEffect(() => { if (!server) return; let live = true
    ;(async () => { while (live) { const t0 = Date.now(); await pull(null, 20).catch(() => null); if (live && Date.now() - t0 < 250) await new Promise(r => setTimeout(r, 300)) } })()
    return () => { live = false } }, [server, pull])
  useEffect(() => { if (!server) return   // 접속자 — 5초마다 이름 신호
    // 1초마다 — 내가 고른·고치는 도형도 같이(2026-10-19 사용자: 누가 어디를 고치는지). 바뀐 게 없어도 보냄(5초 안 오면 나간 것으로 — 서버 `Presence` ttl)
    const ping = () => api.presence(sync.current.id, me || '이름 없음', ed.current?.getSel?.() || [], ed.current?.editingId?.() || '').then(p => { if (!p) return; setOthers(o => (JSON.stringify(o) === JSON.stringify(p.others || []) ? o : p.others || [])) })
    const bye = () => api.leave(sync.current.id)   // 창을 닫으면 바로 빠짐(2026-10-26 실검증 — 전엔 15초 신호 끊김을 기다려 20초쯤 남았음)
    ping(); const t = setInterval(ping, 1000); window.addEventListener('pagehide', bye); return () => { clearInterval(t); window.removeEventListener('pagehide', bye) } }, [server, me])

  // 시험·자체확인용 손잡이(Playwright)
  useEffect(() => { window.__mb = { setCam, getCam: () => cam, open: async u => open(parseDoc(await (await fetch(u)).text()), u), model, toEcad: () => toEcad(model), get ed() { return ed.current }, setTool,
    unsaved: () => { const S = sync.current; return !!S.base && !!(S.busy || diffModel(S.base, modelRef.current)) } } })   // unsaved = 서버에 아직 안 보낸 변경(시험 — 상태 글 「저장됨」은 앞 저장 것이 남아 있을 수 있음)
  useEffect(() => {
    // 서버에 없는 칠판 = 빈 칠판을 먼저 만들고 그 판 번호로 엶(2026-10-28 사용자: 아무것도 안 쓴 칠판이 목록에서 사라졌음 — 칠판 코드로도 못 찾았음).
    // 받아 오기를 켜기 전에 만들어야 함 — 고치기 시작한 뒤에 도착하면 남의 변경처럼 합쳐져 되돌리기가 어긋났음(flow35)
    // 처음 온 사람(이 브라우저에 칠판이 하나도 없음) = 예시 칠판 사본부터(2026-10-28 사용자 — 들어오자마자 「이렇게 쓰는 거구나」, 원본 없으면 빈 칠판 그대로)
    ;(AUTO_BOARD === 'new' ? api.example() : Promise.resolve()).then(loadServerDoc).then(async r => { const fresh = r.server && !r.doc, rev = fresh ? await api.patch({ upsert: [], delete: [] }) : null
      if (typeof rev === 'number') r = { ...r, doc: { ...emptyDoc(), rev } }
      setExample(r.doc?.example || '')
      setServer(r.server); setSrvKnown(true); if (r.doc) open(r.doc, `서버 「${DOC_NAME}」`, true, true); else if (r.server) { const m = modelRef.current; sync.current.base = snapshotModel(m); sync.current.rev = 0 }
      if (fresh || !r.server) setStatus(r.server ? `서버 「${DOC_NAME}」 · 새 칠판` : '서버 없음 — 파일로 열고 저장') }) }, [])   // eslint-disable-line

  // 카드 버튼: 클릭 = 그리기 도구, 6px 넘게 끌면 도형을 칠판에 바로 놓기(데스크톱 `_PaletteButton._DRAG_THRESH`)
  // 미니맵에 그릴 것 — 숨긴 레이어 뺌(화면을 옮길 때마다 다시 그리지 않게 문서가 바뀔 때만)
  const mapItems = useMemo(() => { const hid = new Set(layersOf(model).filter(l => !l.visible).map(l => l.id)); return hid.size ? model.items.filter(it => !hid.has(layerIdOf(it))) : model.items }, [model])
  const lastTable = useRef([3, 3, true])   // 위 막대에서 표를 끌면 = 마지막에 넣은 행·열(처음은 3×3)
  const [webAt, setWebAt] = useState(null)   // 위 막대에서 「웹」을 끌어 놓은 자리 — 주소 칸이 뜨고 그 자리에 넣음
  const toolDown = (e, k) => paletteDown(e, k, kind => ed.current?.startToolDrag(kind, { table: lastTable.current, onWeb: p => { setWebAt(p); setWebOpen(true) } }))   // 클릭 = 지금처럼, 끌기 = 놓은 자리에 기본형
  const libServer = useLibrary(), [mySyms, myApi] = useMySymbols(libServer), lib = useMemo(() => mergeLib(libServer, mySyms), [libServer, mySyms])   // 내 심볼(이 브라우저, 2026-10-27 — 서버 심볼은 처음 한 번 예시로 복사)
  const [symAdd, setSymAdd] = useState(null)   // 「내 심볼에 추가」 창 = { items, name }   // 「내 심볼」(서버 `/api/symbols`)
  const paletteDown = (e, t, start = k => ed.current?.startPaletteDrag(k)) => {
    if (e.button !== 0) return
    const sx = e.clientX, sy = e.clientY
    const move = ev => { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) <= 6) return; done(); start(t) }
    const done = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', done) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', done)
  }

  const saveFile = () => {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([JSON.stringify(toEcad(model), null, 1)], { type: 'application/json' }))
    a.download = `${DOC_NAME}.ecad`; a.click(); URL.revokeObjectURL(a.href)
  }
  const saveServer = () => { clearTimeout(saveT.current); flush() }   // 지금 바로 보내기(바뀐 도형만)
  // 창 전체 글쇠(2026-10-19 다잡기 — 데스크톱 `SHORTCUT_DEFS`와 같은 뜻, 표는 keys.js): Ctrl+S가 브라우저 「페이지 저장」 창을 띄우던 것·툴팁에만 있던 Ctrl+9.
  // 글쇠 이름은 한글 입력에 따라 바뀌어 자리(code)로 봄. 발표 중엔 발표 화면이 받음
  const [chatAsk, setChatAsk] = useState(null)   // 칠판 우클릭에서 대화창에 시킨 질문(「정리 문서 만들기」)
  const [chatFocus, setChatFocus] = useState(null)   // 빈 칠판 안내 → 대화창 입력 칸(그 길 이름표까지)
  const [meetSt, setMeetSt] = useState('')   // 「🎙 회의」 실시간 회의록 상태(Editor가 알려 줌) — '' | start | listen | reconnect | stopping | saved
  const [gone, setGone] = useState(false)   // 열어 둔 사이 누가 이 칠판을 지움(2026-10-28 — 받아 오기·저장이 410)
  const [example, setExample] = useState(''), [exAsk, setExAsk] = useState(false), [exHide, setExHide] = useState(false)   // 예시 칠판(문서 `example`, 2026-10-28) — 위 띠 · 「처음 모습으로」 확인 창 · 띠 닫기(이 창에서만)
  const resetExample = async () => { setExAsk(false)
    await flush(); for (let i = 0; i < 30 && sync.current.busy; i++) await new Promise(r => setTimeout(r, 100))   // 보내던 것을 먼저 끝냄 — 되돌린 뒤에 도착하면 옛 도형이 되살아남
    if (!(await api.example())) { setStatus('처음 모습으로 못 되돌렸어요 — 서버 연결을 확인해 주세요'); return }
    myApi.reseed(); location.reload() }   // 칠판·대화·예시 심볼 모두 — 대화창은 다시 열어야 새 기록을 읽음
  const [aiBusy, setAiBusy] = useState('')   // 칠판 위 「📄 정리 문서 만드는 중…」 알약(대화창이 알려 줌)
  const [helpOpen, setHelpOpen] = useState(false), [findOpen, setFindOpen] = useState(0), [marks, setMarks] = useState([])   // findOpen = 열 때마다 새 번호(다시 Ctrl+F = 칸에 다시 포커스)
  const keyAct = useRef(null)
  keyAct.current = { fit: () => fit(modelRef.current.items), save: () => (server ? saveServer() : saveFile()),
    zoom100: () => setCam(c => { const cx = (size.w - rightInset(box.current)) / 2, cy = size.h / 2; return { z: 1, x: cx - (cx - c.x) / c.z, y: cy - (cy - c.y) / c.z } }) }
  // 위 막대 팝업(내보내기·표·웹·공유) — 바깥 누르기·Esc = 닫기, 하나만(2026-10-22 디자인 점검: Esc는 팝업 안에 커서가 있을 때만 먹고 둘이 겹쳐 열렸음)
  const anyPop = exportOpen || tableOpen || webOpen || shareOpen
  useEffect(() => {
    if (!anyPop) return
    const close = (keep = '') => { if (keep !== 'export') setExportOpen(false); if (keep !== 'table') setTableOpen(false); if (keep !== 'web') setWebOpen(false); if (keep !== 'share') setShareOpen(false) }
    const down = e => close(e.target.closest?.('[data-pop]')?.dataset.pop || '')   // 그 팝업(버튼 포함) 안이면 그것만 남김 — 다른 팝업 버튼 = 앞 것 닫고 새로 열기
    const key = e => { if (e.key === 'Escape' && !document.querySelector('[data-qr-big]')) { e.stopImmediatePropagation(); close() } }   // 칠판의 Esc(고른 것 풀기)보다 먼저 — 팝업만 닫음. 큰 QR이 떠 있으면 Esc는 QR만(qr.jsx)
    window.addEventListener('pointerdown', down, true); window.addEventListener('keydown', key, true)
    return () => { window.removeEventListener('pointerdown', down, true); window.removeEventListener('keydown', key, true) }
  }, [anyPop])
  // 알림 = 칠판 아래 가운데에 잠깐(글 길이만큼 2~6초). 다 지나도 글은 남기고 투명하게만(시험이 글을 찾음)
  const [toastOn, setToastOn] = useState(false)
  useEffect(() => { if (!status) return; setToastOn(true); const t = setTimeout(() => setToastOn(false), Math.min(6000, 2000 + status.length * 50)); return () => clearTimeout(t) }, [status])
  useEffect(() => {
    const on = e => {
      if (document.querySelector('[data-testid=presenter]')) return
      if (e.key === 'F1') { e.preventDefault(); setHelpOpen(o => !o); return }
      if (!(e.ctrlKey || e.metaKey) || e.altKey) return
      const k = { Digit0: 'zoom100', KeyS: 'save', KeyP: 'export', KeyF: 'find' }[e.code]; if (!k || (k === 'save' && e.shiftKey)) return
      e.preventDefault(); if (k === 'export') setExportOpen(true); else if (k === 'find') setFindOpen(n => n + 1); else keyAct.current[k]()
    }
    window.addEventListener('keydown', on); return () => window.removeEventListener('keydown', on)
  }, [])

  // 접속자 = 나 + 다른 창(id마다 — 이름으로 세면 이름이 같은 사람(로그인 없는 서버는 다 「이름 없음」)이 한 명으로 줄었음, 2026-10-27 사용자: 셋인데 1)
  const crowd = [{ id: sync.current.id, name: me || '나', me: true }, ...others]
  // 칠판 이름 = 문서 `title`(2026-10-28 — 칠판 판에서 바꾸면 받아 오기로 따라옴), 없으면 주소에서 · 브라우저 탭 제목도(칠판 여러 개를 탭으로 열면 다 「Magic Board」였음)
  const title = boardTitle(DOC_NAME, srvKnown ? model.title : knownTitle(DOC_NAME))   // 서버 답 전 = 지난번 이름(깜빡임)
  useEffect(() => { document.title = live ? `${title} — Magic Board` : 'Magic Board' }, [live, title])
  useEffect(() => { if (server) noteBoards([{ name: DOC_NAME, title: model.title || '' }]) }, [server, model.title])   // 다음에 열 때 첫 모습
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: C.board, font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
      {phone && <div data-testid="phone-top" style={{ touchAction: 'none', display: 'flex', alignItems: 'center', gap: 10, padding: '8px 14px', background: C.bar, borderBottom: `1px solid ${C.line}` }}>   {/* 휴대폰 위 = 칠판 이름·사람 수·밝기만 */}
        <span style={{ flex: 1, minWidth: 0, font: "700 15px 'Pretendard', sans-serif", whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{live ? `「${title}」` : 'Magic Board'}{live && team && <span style={{ marginLeft: 6, font: "600 12px 'Pretendard', sans-serif", color: C.muted }}>{team}</span>}</span>
        {live && <span data-testid="people-count" title={crowd.map(p => p.name).join(', ')} style={{ fontSize: 13, color: C.muted, whiteSpace: 'nowrap' }}>👥 {crowd.length}</span>}
        <button onClick={toggleDark} title="밝게 / 어둡게" style={{ all: 'unset', cursor: 'pointer', fontSize: 18, padding: '2px 4px' }}>{dark ? '☀️' : '🌙'}</button></div>}
      <Narrow.Provider value={narrow}>
      <div style={{ display: phone ? 'none' : 'flex', flexWrap: narrow ? 'wrap' : 'nowrap', rowGap: 4, alignItems: 'center', gap: narrow ? 4 : 8, padding: '4px 8px', background: C.bar, borderBottom: `1px solid ${C.line}` }}>   {/* 좁은 PC 창(반 화면)은 두 줄로 — 한 줄이면 칠판 이름·공유·KAIROS가 잘렸음(2026-10-27 저녁) */}
        {/* 칠판 이름 = 맨 왼쪽(2026-10-27 사용자 — Figma·Miro처럼 파일 이름은 왼쪽 위), 누르면 왼쪽 판 「칠판」 칸(새 칠판·최근 칠판·파일) */}
        <button data-testid="board-title" onClick={() => setDockTab(dockTab === 'board' ? '' : 'board')} title={server ? `칠판 「${DOC_NAME}」 — 누르면 새 칠판·최근 칠판·파일` : '새 칠판·최근 칠판·파일'}
          style={{ all: 'unset', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, minWidth: 0, maxWidth: narrow ? 110 : 180, padding: '4px 8px', borderRadius: 6, font: "700 14px 'Pretendard', sans-serif", color: C.ink, background: dockTab === 'board' ? 'rgba(218,119,86,.22)' : 'transparent' }}
          onMouseEnter={e => { if (dockTab !== 'board') e.currentTarget.style.background = 'rgba(218,119,86,.12)' }} onMouseLeave={e => { e.currentTarget.style.background = dockTab === 'board' ? 'rgba(218,119,86,.22)' : 'transparent' }}>
          <span style={{ minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{live ? title : 'Magic Board'}</span><span aria-hidden style={{ fontSize: 10, color: C.muted }}>▾</span></button>
        {live && team && <span data-testid="team-badge" title={team === '관리자' ? '관리자 — 모든 팀의 칠판이 보여요' : `「${team}」 칠판만 보여요 · KAIROS 크레딧도 ${team} 것`}
          style={{ flexShrink: 0, marginLeft: -4, padding: '2px 8px', borderRadius: 10, background: C.group, color: C.muted, font: "600 12px 'Pretendard', sans-serif", whiteSpace: 'nowrap' }}>{team}</span>}
        <Group>
 {/* 칠판·열기·내려받기는 왼쪽 판 「칠판」 칸으로(2026-10-23 사용자) */}
          <Btn icon="save" label="저장" onClick={server ? saveServer : saveFile} title={server ? `서버 「${DOC_NAME}」에 저장` : '.ecad로 내려받기'} />
          <div data-pop="export" style={{ position: 'relative' }}>
            <Btn icon="pdf" label="내보내기" on={exportOpen} onClick={() => setExportOpen(o => !o)} title="PDF·PNG·SVG로 내보내기 — 전체 또는 고른 것" />
            {exportOpen && <ExportForm hasSel={!!ed.current?.getSel().length} selFrames={ed.current?.selFrames() || 0} frameCount={model.items.filter(it => it.type === 'frame' || (it.type === 'titleblock' && it.plain)).length} items={model.items}
            onPreview={o => ed.current?.exportPages(o) ?? Promise.resolve({ error: '' })} onReorder={ids => ed.current?.reorderFrames(ids)} onClose={() => setExportOpen(false)} onExport={async o => { const ok = await ed.current?.exportDoc({ ...o, name: DOC_NAME || 'magic-board' }); if (ok) setExportOpen(false) }} />}
          </div>
        </Group>
        <Group>
          <Btn icon="undo" label="되돌리기" onClick={() => ed.current?.undo()} title="되돌리기 (Ctrl+Z)" />
          <Btn icon="redo" label="다시" onClick={() => ed.current?.redo()} title="다시 실행 (Ctrl+Y)" />
        </Group>
        <Group>{TOOLS.map(([k, icon, label, key]) => <Btn key={k} icon={icon} label={label} on={tool === k} onClick={() => setTool(k)} onDown={k === 'select' || k === 'pen' ? undefined : e => toolDown(e, k)} title={`${label} (${key})${k === 'select' || k === 'pen' ? '' : ' — 칠판으로 끌면 그 자리에'}`} />)}
          <Btn icon={keepTool ? 'keep_on' : 'keep_off'} label="유지" on={keepTool} onClick={toggleKeep} title="도구 유지 (Q) — 켜면 그린 뒤에도 그 도구가 그대로(도구를 바꿔도), Esc·「선택」으로 멈춤" /></Group>
        <Group><div style={ANCHOR}>
          <Btn icon="present" label="발표" onClick={() => ed.current?.startPresent()} title="발표 — 프레임 순서대로 한 장씩 전체 화면(고른 프레임부터) · → 다음 · ← 이전 · M 이동/바로 · Esc 끝" />
          <Btn icon="frame" label="프레임" on={tool === 'frame'} onClick={() => setTool(t => (t === 'frame' ? 'select' : 'frame'))} onDown={e => toolDown(e, 'frame')} title="프레임 — 버튼을 칠판으로 끌면 그 자리에 16:9 · 칠판에서 끌어서 영역을 감싸면 그 안이 출력 한 쪽(번호 순서). 클릭만 = 16:9, 우클릭 「프레임으로 감싸기」도" />
        </div><div data-pop="table" style={ANCHOR}>
          <Btn icon="table" label="표" on={tableOpen} onClick={() => setTableOpen(o => !o)} onDown={e => toolDown(e, 'table')} title="표 넣기 — 행·열을 고르면 화면 가운데(겹치면 가까운 빈자리) · 칠판으로 끌면 그 자리에(마지막 행·열)" />
          {tableOpen && <TableForm onInsert={(r, c, h) => { setTableOpen(false); lastTable.current = [r, c, h]; ed.current?.insertTable(r, c, h) }} onLegend={() => { setTableOpen(false); ed.current?.insertLegend() }} onClose={() => setTableOpen(false)} />}
        </div><div data-pop="web" style={ANCHOR}>
          <Btn icon="memo" label="메모" onClick={() => ed.current?.insertMemo()} onDown={e => toolDown(e, 'memo')} title="메모 — 칠판으로 끌면 그 자리에 · 줄마다 제목·목록·할 일·코드·인용(`# `·`- `·`[] `·`> ` 입력), 체크 상자는 칠판에서 바로" />
          <Btn icon="web" label="웹" on={webOpen} onClick={() => { setWebAt(null); setWebOpen(o => !o) }} onDown={e => toolDown(e, 'web')} title="웹 카드 — 칠판으로 끌면 그 자리에 · 유튜브·웹페이지 주소를 칠판에(칠판에 주소를 Ctrl+V 해도 돼요)" />
          {webOpen && <WebForm onInsert={u => { const url = /^https?:\/\//i.test(u) ? u : 'https://' + u; setWebOpen(false); ed.current?.insertWeb(url, webAt || 'near') }} onClose={() => setWebOpen(false)} />}
        </div>{/* 「회의」 = 칠판에 회의록을 넣는 도구(2026-10-23 사용자 — 전엔 오른쪽 KAIROS 옆) */}
        <Btn icon="🎙" label={meetSt === 'saved' ? '정리하기' : meetSt ? '끝내기' : '회의'} on={!!meetSt} disabled={meetSt === 'start' || meetSt === 'stopping'}
          onClick={() => (!server ? setStatus('서버에 연결 안 됨 — python web/server.py를 켜야 회의를 받아 적을 수 있어요') : meetSt ? ed.current?.meetStop() : ed.current?.meetStart())}
          title={meetSt ? '회의 끝내기 — 받아 적은 글을 요약·결정·할 일로 정리해 칠판에(KAIROS)' : '회의 받아 적기 — 마이크로 말한 사람별로 실시간 받아 적고, 끝내면 회의록으로 정리(KAIROS)'} />
        </Group>
        <Group>
          <Btn icon="zoom_fit" label={full ? '창으로' : '전체 화면'} on={full} onClick={toggleFull} title="전체 화면 ⇄ 창 (F11과 같음) — 다 보기는 Z 또는 미니맵의 %" />
          <Btn icon="theme" label={dark ? '밝게' : '어둡게'} onClick={toggleDark} title="밝은 화면 / 어두운 화면 (D)" />   {/* 보기 묶음으로(2026-10-23 사용자 — 오른쪽 구석은 KAIROS 몫) */}
        </Group>
        {!narrow && !server && <SampleSelect onPick={openSample} />}
        <div style={{ marginLeft: 'auto' }} />   {/* 오른쪽 이름·배율 뺌(2026-10-27 사용자 — 이름은 왼쪽 끝, 배율은 미니맵 %와 겹침) */}
        <div data-pop="share" style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 6, opacity: live ? 1 : 0.4 }}>   {/* 서버가 없으면 숨기지 않고 흐리게 — 안 보이면 왜 없는지 몰랐음(2026-10-20 사용자) */}
          {live && <Faces list={crowd.map(p => ({ ...p, color: personColor(p.id) }))} onClick={() => setShareOpen(o => !o)} />}
          <Btn icon="share" label="공유" on={shareOpen} onClick={() => (server ? setShareOpen(o => !o) : setStatus('서버에 연결 안 됨 — python web/server.py를 켜야 공유·KAIROS를 쓸 수 있어요'))} title={server ? '게시 — 로그인 없이 보기·발표만 되는 링크(큰 TV 발표용)' : '서버에 연결 안 됨 — python web/server.py를 켜면 공유할 수 있어요'} />
          {server && shareOpen && <ShareForm people={crowd} title={title} onClose={() => setShareOpen(false)} />}
        </div>
        <Btn special icon="generate" label="KAIROS" on={chatOpen} onClick={() => setChatOpen(o => !o)} title="KAIROS 대화창 열기/닫기 — 답을 칠판에 카드로 붙여요" />   {/* 오른쪽 구석 = 대화창 바로 위(2026-10-23 사용자) */}
        <input ref={file} type="file" accept=".ecad,application/json" hidden onChange={async e => {
          const f = e.target.files?.[0]; e.target.value = ''; if (!f) return
          try { open(parseDoc(await f.text()), f.name) } catch (err) { setStatus('열기 실패: ' + err.message) }
        }} />
      </div>
      </Narrow.Provider>
      <div style={{ flex: 1, display: 'flex', minHeight: 0, position: 'relative' }}>   {/* 왼쪽 판 + 작업공간 + 오른쪽 KAIROS 대화창(좁은 창은 대화창만 칠판 위에 뜸) */}
      {!phone && <Dock tab={dockTab} setTab={setDockTab} width={dockW} setWidth={setDockW} help={helpOpen} onHelp={() => setHelpOpen(o => !o)} mini={w => <Minimap docked width={w} items={mapItems} cam={cam} size={size} setCam={setCam} dark={dark} />} panes={{
        board: <BoardForm docked open={openServer} myId={sync.current.id} me={me} onDownload={saveFile} onClose={() => {}}>
          {!live && <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', borderTop: `1px solid ${C.line}`, paddingTop: 8 }}>
            {[['open', '파일 열기', () => file.current.click(), '.ecad 파일 열기(지금 칠판을 그 내용으로 바꿈)'], ['download', '내려받기', saveFile, '.ecad 파일로 내려받기']].map(([ic, l, f, t]) =>
              <button key={l} onClick={f} title={t} style={{ all: 'unset', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5, padding: '4px 10px 4px 7px', borderRadius: 6, border: `1px solid ${C.line}`, font: "500 12px 'Pretendard', sans-serif" }}>
                <span aria-hidden style={{ width: 16, height: 16, display: 'block', color: 'var(--mb-icon)' }} dangerouslySetInnerHTML={{ __html: ICONS[ic].replace('<svg ', '<svg width="16" height="16" ') }} />{l}</button>)}
          </div>}</BoardForm>,
        shape: <Palette docked lib={lib} tool={tool} dark={dark} onDown={paletteDown} onClick={setTool} mine={{ mine: mySyms, api: myApi }} say={setStatus} />,
        frame: orderedFrames(model.items).length ? <Frames docked items={model.items} sel={selKey ? selKey.split(',') : []} onReorder={ids => ed.current?.reorderFrames(ids)} onRename={(id, n) => ed.current?.renameFrame(id, n)} onGo={id => ed.current?.goFrame(id)} onPresent={id => ed.current?.startPresent(id)}
          onExport={id => { ed.current?.setSel([id]); setTimeout(() => setExportOpen(true)) /* 내보내기 창은 열 때 고른 것을 읽음 — 고른 것이 바뀐 다음에 열기 */ }} onRemove={id => ed.current?.removeFrame(id)} dark={dark} />
          : <div data-testid="frames-empty" style={{ padding: '10px 12px', color: C.muted, fontSize: 12, lineHeight: 1.6 }}><div style={{ font: "700 15px 'Pretendard', sans-serif", color: C.ink, marginBottom: 6 }}>프레임</div>아직 없어요 — 위 막대 「프레임」을 눌러 칠판에서 영역을 감싸면 여기에 쌓여요(순서 = 출력·발표 순서).</div>,
        layer: <Layers docked model={model} setModel={setModel} active={activeLayer} setActive={setActiveLayer} onChanged={onCommit} dark={dark} /> }} />}
      {/* --mb-right-inset = 뜬 대화창 폭 — 우상 속성·우하 미니맵 카드가 그만큼 왼쪽으로 비킴 */}
      <div ref={box} onDragOver={e => { const ts = [...(e.dataTransfer?.types || [])]; if (ts.includes('Files') || ts.includes('text/uri-list')) e.preventDefault() }}
        onDrop={e => { const fs = [...(e.dataTransfer?.files || [])]; e.preventDefault()   // 끌어 놓기 — 파일(그림·녹음 = 회의록) 또는 주소(대화창 그림 후보·웹 주소 = 웹 카드). 막지 않으면 브라우저가 그 파일·주소로 떠남
          if (fs.length) return ed.current?.dropFiles(fs, e)
          const u = (e.dataTransfer?.getData('text/uri-list') || '').split(/\r?\n/).find(x => x && !x.startsWith('#')); if (u) ed.current?.dropUrl(u, e.dataTransfer.getData('text/x-mb-caption') || '', e) }}
        style={{ flex: 1, position: 'relative', overflow: 'hidden', '--mb-right-inset': narrow && chatOpen ? `${chatW + 12}px` : '0px' }}>
        <Editor ref={ed} others={others} dark={dark} model={model} setModel={setModel} onCommit={onCommit} size={size} cam={cam} setCam={setCam} tool={tool} setTool={setTool} setStatus={setStatus} library={lib?.symbols} libFolders={lib?.folders} activeLayer={activeLayer} phone={phone} keepTool={keepTool} onKeepTool={toggleKeep} onSel={s => setSelKey(s.join())} onExportSel={() => setExportOpen(true)} onAddSymbol={(items, name, folder) => setSymAdd({ items, name, folder })} onFit={its => fit(its || modelRef.current.items)} onDark={toggleDark} onHelp={() => setHelpOpen(true)} marks={marks} onMeet={setMeetSt} onAsk={(text, kind) => { setChatOpen(true); setChatAsk({ id: Date.now(), text, kind }) }} />
        {gone && <div data-testid="gone-banner" style={{ position: 'absolute', top: 10, left: '50%', transform: 'translateX(-50%)', zIndex: 25, display: 'flex', alignItems: 'center', gap: 10, padding: '8px 12px', borderRadius: 10, background: '#d44c47', color: '#fff', font: "600 13px 'Pretendard', sans-serif", boxShadow: '0 4px 14px rgba(0,0,0,.2)' }}>
          이 칠판은 다른 창에서 지워졌어요 — 고친 것은 저장되지 않아요
          <button onClick={saveFile} style={{ all: 'unset', cursor: 'pointer', padding: '3px 8px', borderRadius: 6, background: 'rgba(255,255,255,.22)' }}>내려받기</button>
          <button onClick={() => { forgetBoard(DOC_NAME); location.href = location.pathname }} style={{ all: 'unset', cursor: 'pointer', padding: '3px 8px', borderRadius: 6, background: 'rgba(255,255,255,.22)' }}>쓰던 칠판으로</button></div>}   {/* 2026-10-28 칠판 지우기 — 열어 둔 창 */}
        {/* 예시 칠판 띠(2026-10-28 사용자 — 만져 보다 망가지면 한 번에 처음으로): 이 사람 사본만 되돌림(칠판·대화·예시 심볼), 되돌리면 고친 것이 사라져 한 번 물음 */}
        {example && !gone && !exHide && !phone && <div data-testid="example-band" style={{ position: 'absolute', top: 10, left: '50%', transform: 'translateX(-50%)', zIndex: 25, display: 'flex', alignItems: 'center', gap: 10, padding: '6px 8px 6px 14px', borderRadius: 10,
          background: C.card, border: `1px solid ${C.line}`, color: C.ink, font: "500 13px 'Pretendard', sans-serif", boxShadow: '0 4px 14px rgba(0,0,0,.12)', whiteSpace: 'nowrap' }}>
          <span><b style={{ fontWeight: 700 }}>예시 칠판</b> — 마음껏 만져 보세요. 망가져도 한 번에 되돌려요</span>
          <button data-testid="example-reset" onClick={() => setExAsk(true)} title="이 칠판·KAIROS 대화·예시 심볼을 처음 모습으로" style={{ all: 'unset', cursor: 'pointer', padding: '4px 10px', borderRadius: 6, background: C.accent, color: '#fff', fontWeight: 600 }}>↺ 처음 모습으로</button>
          <button aria-label="띠 닫기" title="띠 닫기 — 칠판을 다시 열면 또 보여요" onClick={() => setExHide(true)} style={{ all: 'unset', cursor: 'pointer', padding: '0 6px', color: C.muted, fontSize: 15 }}>×</button></div>}
        {exAsk && <div style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,.25)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onPointerDown={e => { if (e.target === e.currentTarget) setExAsk(false) }}>
          <div data-testid="example-ask" onKeyDown={e => { e.stopPropagation(); if (e.key === 'Escape') setExAsk(false) }} style={{ width: 320, display: 'flex', flexDirection: 'column', gap: 10, padding: 18, borderRadius: 12, background: C.card, border: `1px solid ${C.line}`, boxShadow: '0 8px 28px rgba(0,0,0,.25)', font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
            <div style={{ font: "700 15px 'Pretendard', sans-serif" }}>예시 칠판을 처음 모습으로 되돌릴까요?</div>
            <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.55 }}>이 칠판에서 고친 것과 KAIROS 대화가 처음 예시로 바뀌고, 지운 예시 심볼도 돌아와요. 다른 사람의 예시 칠판은 그대로예요.</div>
            <div style={{ display: 'flex', gap: 6, justifyContent: 'flex-end' }}>   {/* 엔터 = 되돌리기(칠판 지우기 창과 같게), Esc·바깥 = 취소 */}
              <button onClick={() => setExAsk(false)} style={{ all: 'unset', cursor: 'pointer', padding: '5px 12px', borderRadius: 6, border: `1px solid ${C.line}` }}>취소</button>
              <button data-testid="example-reset-ok" autoFocus onClick={resetExample} style={{ all: 'unset', cursor: 'pointer', padding: '5px 12px', borderRadius: 6, background: C.accent, color: '#fff', fontWeight: 600, outline: `2px solid ${C.accent}`, outlineOffset: 2 }}>되돌리기</button>
            </div></div></div>}
        {helpOpen && <HelpCard onClose={() => setHelpOpen(false)} />}
        {symAdd && <SymAddForm init={symAdd} folders={mySyms.folders} onClose={() => setSymAdd(null)} onOk={(name, folder) => {
          const ok = myApi.addSymbol(name, folder, symAdd.items); setSymAdd(null)
          if (ok) { setDockTab('shape'); setStatus(`「${name}」을 내 심볼 「${folder}」에 넣었어요 — 이 브라우저에 저장`) } else setStatus('이 브라우저 저장 공간이 모자라요 — 그림이 든 것은 클 수 있어요') }} />}
        {!model.items.length && !meetSt && !aiBusy && <EmptyGuide onAsk={() => { setChatOpen(true); setChatFocus({ id: Date.now() }) }} onDeep={() => { setChatOpen(true); setChatFocus({ id: Date.now(), tool: 'deep' }) }}
          onMeet={() => (!server ? setStatus('서버에 연결 안 됨 — python web/server.py를 켜야 회의를 받아 적을 수 있어요') : ed.current?.meetStart())} />}
        <span data-testid="save-note" style={{ position: 'absolute', width: 1, height: 1, overflow: 'hidden', clipPath: 'inset(50%)', whiteSpace: 'nowrap', pointerEvents: 'none' }}>{saveNote}</span>
        {status && <div data-testid="status-toast" role="status" title={status} style={{ position: 'absolute', bottom: 16, left: '50%', transform: 'translateX(-50%)', zIndex: 6, maxWidth: 'min(640px, max(240px, calc(100% - 480px)))', padding: '6px 14px', borderRadius: 99,
          background: 'rgba(24,24,27,.86)', color: '#fff', font: "500 13px 'Pretendard', sans-serif", whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', pointerEvents: 'none', opacity: toastOn ? 1 : 0, transition: 'opacity .3s' }}>{status}</div>}
        {aiBusy && <div data-testid="ai-busy" role="status" style={{ position: 'absolute', top: 12, left: '50%', transform: 'translateX(-50%)', zIndex: 6, display: 'flex', alignItems: 'center', gap: 8, padding: '6px 14px', borderRadius: 99,
          background: 'var(--mb-card)', border: '1px solid var(--mb-line)', boxShadow: '0 2px 8px rgba(0,0,0,.12)', font: "600 13px 'Pretendard', sans-serif", color: 'var(--mb-ink)', pointerEvents: 'none', whiteSpace: 'nowrap' }}><Spinner />{aiBusy}</div>}   {/* 정돈·정리 문서 중 — 칠판만 보고 있어도 도는 게 보이게(2026-10-20 사용자) */}
        {findOpen > 0 && <FindBar key={findOpen} items={model.items} server={server} onMarks={setMarks} onGo={id => ed.current?.showItem(id)} onClose={() => setFindOpen(0)} />}
      </div>
      {chatOpen && srvKnown && <ChatPanel ed={ed} selKey={selKey} floating={narrow} full={phone} onClose={() => setChatOpen(false)} request={chatAsk} focus={chatFocus} onBusy={setAiBusy} width={chatW} setWidth={setChatW} />}
      </div>
      {phone && <div data-testid="phone-bar" style={{ touchAction: 'none', display: 'flex', gap: 8, padding: '8px 10px calc(8px + env(safe-area-inset-bottom))', background: C.bar, borderTop: `1px solid ${C.line}` }}>   {/* 휴대폰 아래 = 엄지로 누르는 큰 버튼 셋 */}
        {[['⤢', '다 보기', () => fit(modelRef.current.items), false, false],
          ['🎙', meetSt === 'saved' ? '정리하기' : meetSt ? '끝내기' : '회의', () => (!server ? setStatus('서버에 연결 안 됨 — python web/server.py를 켜야 회의를 받아 적을 수 있어요') : meetSt ? ed.current?.meetStop() : ed.current?.meetStart()), !!meetSt, meetSt === 'start' || meetSt === 'stopping'],
          ['✦', 'KAIROS', () => setChatOpen(true), false, false]].map(([ic, label, f, on, off]) =>
          <button key={ic} onClick={f} disabled={off} style={{ all: 'unset', flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6, height: 44, borderRadius: 10, cursor: 'pointer', opacity: off ? 0.5 : 1,
            font: "600 15px 'Pretendard', sans-serif", color: ic === '✦' || on ? '#fff' : C.ink, background: ic === '✦' ? '#da7756' : on ? '#d44c47' : 'var(--mb-card)', border: `1px solid ${ic === '✦' || on ? 'transparent' : C.line}` }}><span aria-hidden>{ic}</span>{label}</button>)}
      </div>}
    </div>
  )
}

// 쓰는 굵기를 모두 불러온 뒤 그림 — 400만 기다리면 굵은 글자 폭을 다른 글꼴로 재서(메모 줄 배치는 한 번 재면 그대로) 밑줄·다음 글자 자리가 어긋났음(2026-10-19)
await Promise.all([400, 600, 700, 800].map(w => document.fonts.load(`${w} 16px 'Pretendard'`, '가A'))).catch(() => {})
// 들어가기 전 — 비밀번호가 필요한 서버면 먼저 로그인 창(칠판 화면은 그 뒤에 만들어야 크기 재기 등이 바로 돎)
// 팀 서버(§8 항목67)에서 다른 팀 칠판 주소로 들어옴 — 우리 팀 칠판으로 가거나 다른 팀 비밀번호로 다시
function TeamBlocked({ ss, onLogin }) {
  const go = n => { location.href = `${location.pathname}?board=${encodeURIComponent(n)}` }
  return <div data-testid="team-blocked" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.board, font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ width: 320, display: 'flex', flexDirection: 'column', gap: 10, padding: 20, borderRadius: 12, border: `1px solid ${C.line}`, background: C.card, boxShadow: '0 6px 20px rgba(0,0,0,.12)' }}>
      <div style={{ font: "700 16px 'Pretendard', sans-serif" }}>Magic Board · 「{boardLabel(DOC_NAME).title}」</div>
      <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.5 }}>이 칠판은 다른 팀 칠판이라 「{ss.team}」 비밀번호로는 열 수 없어요. 그 팀에게 초대 링크를 받거나, 그 팀 비밀번호로 들어와 주세요.</div>
      {ss.home && <button data-testid="team-home" onClick={() => go(ss.home)} style={{ all: 'unset', cursor: 'pointer', textAlign: 'center', padding: '7px 0', borderRadius: 6, background: '#da7756', color: '#fff', fontWeight: 600 }}>우리 팀 칠판 「{ss.home}」으로</button>}
      <button onClick={onLogin} style={{ all: 'unset', cursor: 'pointer', textAlign: 'center', padding: '6px 0', borderRadius: 6, color: C.ink, border: `1px solid ${C.line}` }}>다른 비밀번호로 들어가기</button>
    </div></div>
}
// 지운 칠판 링크로 들어옴(2026-10-28) — 열 때 빈 칠판을 만드는 앱이라 그대로 두면 같은 주소에 빈 칠판이 다시 생김
function GoneBoard() {
  const go = q => { location.href = location.pathname + q }
  return <div data-testid="board-gone" style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', background: C.board, font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ width: 320, display: 'flex', flexDirection: 'column', gap: 10, padding: 20, borderRadius: 12, border: `1px solid ${C.line}`, background: C.card, boxShadow: '0 6px 20px rgba(0,0,0,.12)' }}>
      <div style={{ font: "700 16px 'Pretendard', sans-serif" }}>지워진 칠판이에요</div>
      <div style={{ color: C.muted, fontSize: 12, lineHeight: 1.5 }}>누군가 이 칠판을 지웠어요. 서버 휴지통에 남아 있어서, 꼭 필요하면 서버를 맡은 사람이 되살릴 수 있어요.</div>
      <button onClick={() => go(`?board=${newBoardName()}`)} style={{ all: 'unset', cursor: 'pointer', textAlign: 'center', padding: '7px 0', borderRadius: 6, background: '#da7756', color: '#fff', fontWeight: 600 }}>＋ 새 칠판</button>
      <button onClick={() => go('')} style={{ all: 'unset', cursor: 'pointer', textAlign: 'center', padding: '6px 0', borderRadius: 6, color: C.ink, border: `1px solid ${C.line}` }}>쓰던 칠판으로</button>
    </div></div>
}
function Gate() {
  const [gate, setGate] = useState('check'), [ss, setSs] = useState({})
  const check = async () => {   // 로그인이 필요한가 → (팀 서버면) 이 칠판을 써도 되나 — 주소에 칠판이 없으면 우리 팀 첫 칠판으로
    const s = await api.session(); setSs(s)
    if (s.auth && !s.ok) { setGate('login'); return }
    if (s.team && AUTO_BOARD && s.home && (AUTO_BOARD === 'new' || s.board_ok === false)) { location.replace(`${location.pathname}?board=${encodeURIComponent(s.home)}`); return }   // 주소 없이 들어온 팀 = 우리 팀 첫 칠판(새 비밀 주소를 팀이 가져가지 않게)
    if (s.team && s.board_ok === false) { setGate('blocked'); return }
    if (s.gone) { forgetBoard(DOC_NAME); setGate('gone'); return }   // 지운 칠판 링크 = 빈 칠판을 만들지 않고 안내(2026-10-28), 「마지막 칠판」에서도 뺌
    // 남이 준 링크로 처음 연 칠판(이미 있고 내 목록에 없음) = 같이 쓰는 칠판 → 이름을 한 번 물음(혼자 쓰는 새 칠판은 안 물음 — 2026-10-27 Excalidraw처럼)
    if (s.exists && !isMyBoard(DOC_NAME) && !(() => { try { return localStorage.getItem('mb.name') } catch { return '' } })()) { setGate('name'); return }
    rememberBoard(DOC_NAME)   // 내 칠판 — 이 브라우저(만들거나 열어 본 것)
    setGate('ok')
  }
  useEffect(() => { (async () => {
    const u = new URL(location.href), join = u.searchParams.get('join')
    if (join) {   // 편집 초대 링크 — 맞으면 비밀번호 없이 이름만(링크의 열쇠는 주소창에서 지움)
      const ok = await api.join(join); u.searchParams.delete('join'); history.replaceState(null, '', u.pathname + (u.search || ''))
      if (ok) { let nm = ''; try { nm = localStorage.getItem('mb.name') || '' } catch { /* 없어도 그만 */ } if (nm) check(); else setGate('name'); return }
    }
    check() })() }, [])   // eslint-disable-line
  if (gate === 'check') return null
  if (gate === 'login') return <LoginForm onDone={check} />
  if (gate === 'name') return <LoginForm nameOnly title={ss.title} onDone={check} />
  if (gate === 'blocked') return <TeamBlocked ss={ss} onLogin={() => setGate('login')} />
  if (gate === 'gone') return <GoneBoard />
  return <App team={ss.team === null ? '관리자' : ss.team} openServer={!ss.auth} />
}
createRoot(document.getElementById('root')).render(VIEW_TOKEN ? <Viewer token={VIEW_TOKEN} /> : <Gate />)   // ?view= = 게시 링크(보기·발표만)
