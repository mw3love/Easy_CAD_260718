// KAIROS 대화창(직접 만드는 칠판판) — 옛 tldraw 칠판 `src/chat.jsx`를 옮김(§8 항목61 ⓒ 4단계). 칠판 오른쪽 칸, 위 막대 「KAIROS」로 열고 닫음.
// - 묻기: 서버 POST /api/chat(키는 서버 PC에만), 앞 대화를 이어 보냄. 칠판에서 고른 것의 글을 같이 보냄(칩).
// - 「칠판에 붙이기」: 답 → 카드(흰 보드 + 보드 글꼴 글, Editor.pinCard). 붙인 카드는 「칠판에 붙임 ✓」로 찾아감(카드의 .ecad `chat_at` = 답 시각).
// - 대화 기록: 칠판마다 서버(/api/chatlog/<이름>) — 옛 칠판과 같은 기록을 이어 씀. 「새 대화」 = 지금 대화를 `past`로 넘기고 빈 대화(앞 대화가 안 실려 주제가 안 섞임),
//   「지난 대화 ▾」 = 골라 다시 열기(2026-10-20 사용자 — 탭은 360px 칸에 2~3개면 꽉 차서 목록으로). 파일 = { messages, past: [{ at, title, messages }] }.
// - 웹 검색(§8 항목61 ② 담는 법, 2026-10-19): 길은 서버가 고름(판단 모델 jev + 규칙 — `easycad/ai/route.py`), 답 위 표시 「🔎 웹 검색 / 💬 대화」만(옛 「다시 ▾」는 2026-10-20 없앰).
//   검색 답은 쓰인 번호의 출처를 아래에 보이고, 붙이면 요약 메모 + 출처 카드 + 번호 화살표 한 묶음(Editor `cardItems`).
// - 칠판에서(§8 항목61 ③-2): 「지난번·저번·정리해 둔」 → 서버가 이 칠판 글을 뜻으로 찾아 근거로 답, [칠판 n] 고리 = 그 도형으로 가기, 붙이면 근거로 가는 점선 화살표.
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { DOC_NAME } from './doc.js'
import { answerTable, contextText, inlineParts, parseAnswer } from '../chatFormat.js'
import { CHART_KINDS, chartChoices } from './chart.js'
import { CHART_ICONS } from './props.jsx'
import { urlSpans } from './geom.js'
import { MONO_FONT } from './render.jsx'
import { siteOf } from './webcard.js'
import { TIDY_RE } from './tidy.js'
import { getKairosKey, KEY_RE, keyHeaders, setKairosKey } from './kairosKey.js'
import { startMic } from './mic.js'
import { svgPreview } from './svgin.js'
import { DeepAsk, DeepConfirm, DeepPlan, REDO_RE, briefOf, keptPlan } from './deepchat.jsx'
import { recommendStyle } from './deepstyle.js'
import { LIVE_CSP, LIVE_H, LIVE_W, bigPage, liveSrc } from './livecard.js'
const LINK_CHAT = '#4f8fe8'
// 정리 문서 크게 보기 — 새 탭에 그 HTML(인쇄·PDF는 그 탭에서 Ctrl+P)
// 크게 보기 = 칠판 「크게 보기」와 같은 페이지(livecard.js `bigPage` — 앱 주소 blob이라 그 페이지엔 스크립트 없음, 움직이는 카드는 그 안 틀에서만)
const openHtml = (html, live = false) => { const u = URL.createObjectURL(new Blob([bigPage({ type: 'doc', live, html })], { type: 'text/html;charset=utf-8' })); window.open(u, '_blank'); setTimeout(() => URL.revokeObjectURL(u), 60_000) }
// 답 종류 — [표시, 표시 꾸밈] — 서버가 고른 길(판단 모델 jev + 규칙, `easycad/ai/route.py`)을 답 위에 보이기만.
// 옛 「다시 ▾」(다른 종류로 다시 묻기)는 2026-10-20 없앰(사용자: 대화창 하나로 다 — 길은 앱이 고르고, 틀리면 말로 다시)
const KINDS = {
  chat: ['💬 대화', null],
  search: ['🔎 웹 검색', { color: '#2f80ed', background: 'rgba(47,128,237,.12)' }],
  board: ['📌 칠판에서', { color: '#d97706', background: 'rgba(245,158,11,.14)' }],
  report: ['📄 정리 문서', { color: '#7c3aed', background: 'rgba(124,58,237,.12)' }],
  tidy: ['🧩 정리정돈', { color: '#0f766e', background: 'rgba(15,118,110,.12)' }],
  image: ['🎨 그림', { color: '#9333ea', background: 'rgba(147,51,234,.12)' }],
  icon: ['✏️ 아이콘', { color: '#0e7490', background: 'rgba(14,116,144,.12)' }],
  live: ['▶ 움직이는 카드', { color: '#b4532f', background: 'rgba(218,119,86,.14)' }],   // 원리를 직접 만져 보는 카드(§8 항목66 4단계)   // 선을 고칠 수 있는 도형(§8 항목63)
  ask: ['❓ 확인', { color: '#da7756', background: 'rgba(218,119,86,.12)' }],   // 되묻기(§8 항목64) — 만들기 전에 버튼으로
  deep: ['📰 딥모드', { color: '#b4532f', background: 'rgba(180,83,47,.12)' }],   // 한 주제 한 판(§8 항목66) — 질문지·지면 계획 카드(deepchat.jsx)
}
// 되묻기 버튼 — [이름, 설명]. 서버가 애매하고 비싼 갈림길에서만 길 둘을 보냄(`easycad/ai/route.py` `decide`)
const ASK_LABEL = { image: ['🎨 그림으로', '사진·일러스트 같은 그림'], icon: ['✏️ 고칠 수 있는 선 도형으로', '선을 하나하나 고칠 수 있는 아이콘(SVG)'],
  report: ['📄 정리 문서로', '인쇄할 수 있는 문서 한 장'], tidy: ['🧩 칠판 정리정돈', '조각을 주제별로 묶어 옮기기'], chat: ['💬 글로 바로 답하기', '대화창에 글로'],
  search: ['🔎 웹 검색으로', '최신 정보 + 출처'], board: ['📌 칠판에서 찾기', '이 칠판에 적어 둔 것에서'] }
// 고른 답 기억(이 브라우저만 — 편의) — { 갈림길: [최근 고른 길 둘] }, 같은 길을 두 번 연달아 고르면 다음부터 안 물음(서버 `ask_pref`)
const ASK_KEY = 'magic-board-ask'
const askMemo = () => { try { return JSON.parse(localStorage.getItem(ASK_KEY) || '{}') || {} } catch { return {} } }
const askPrefs = () => Object.fromEntries(Object.entries(askMemo()).filter(([, v]) => Array.isArray(v) && v.length >= 2 && v.at(-1) === v.at(-2)).map(([k, v]) => [k, v.at(-1)]))
const rememberAsk = (key, kind) => { try { const m = askMemo(); m[key] = [...(m[key] || []), kind].slice(-2); localStorage.setItem(ASK_KEY, JSON.stringify(m)) } catch { /* 기억 못 해도 그만 */ } }
// 기다리는 동안 보일 말 — 일마다 실제로 일하는 모델(서버 /api/models `jobs`)을 같이(2026-10-20 사용자: 정돈인데 고른 gpt가 보여 헷갈림, 칠판엔 아무 표시가 없어 안 되는 줄 알았음)
const JOB_LABEL = { live: '▶ 움직이는 카드 만드는 중', tidy: '🧩 정리정돈 중', report: '📄 정리 문서 만드는 중', image: '🎨 그림 그리는 중', icon: '✏️ 아이콘 그리는 중', 'deep-plan': '📰 지면 계획 짜는 중', 'deep-build': '📰 딥모드 지면 만드는 중', 'deep-section': '📰 꼭지 다시 쓰는 중', search: '🔎 웹 검색 중', board: '📌 칠판에서 찾는 중' }
// 「+」 도구 — [길, 이름, 설명, 입력 칸 안내]. 서버는 길(`kind`)을 그대로 따름
const TOOLS = [['image', '🎨 그림 만들기', '사진·일러스트 같은 그림', '무엇을 그릴까요? 예: 산 위 송신탑 수채화'],
  ['icon', '✏️ 아이콘', '선을 하나하나 고칠 수 있는 도형(SVG)', '무엇의 아이콘? 예: 파라볼라 안테나'],
  ['search', '🔎 웹 검색', '최신 정보 + 출처', '무엇을 찾을까요?'],
  ['report', '📄 정리 문서', '고른 것(없으면 칠판 전체)을 문서 한 장으로', '어떻게 정리할까요? 비워도 돼요'],
  ['tidy', '🧩 정리정돈', '칠판 조각을 주제별로 묶어 옮기기', '어떻게 묶을까요? 비워도 돼요'],
  ['live', '▶ 움직이는 카드', '원리를 직접 만져 보는 카드 하나(고른 것이 재료, 약 45크레딧)', '무엇을 움직여 볼까요? 예: 가격 × 물량 = 수출액'],
  ['deep', '📰 딥모드', '한 주제로 칠판 한 판 — 질문지 → 지면 계획 → 만들기(크레딧 많이)', '어떤 주제로 한 판? 예: 신입에게 어텐션 설명']]   // 딥모드는 서버가 할 수 있을 때만(/api/models `jobs.deep`)
const EMPTY_ASK = { report: '정리해 줘', tidy: '주제별로 묶어 정돈해 줘' }   // 이름표만 두고 빈 칸으로 보내면
const BOARD_JOBS = new Set(['tidy', 'report', 'deep-build', 'deep-section'])   // 칠판을 바꾸거나 칠판 자료로 만드는 일 — 칠판 위에도 알약(main `aiBusy`)
// 도는 동그라미(칠판 알약·대화창 「생각 중」 공용)
export const Spinner = () => <><style>{'@keyframes mb-spin{to{transform:rotate(360deg)}}'}</style>
  <span style={{ display: 'inline-block', flex: 'none', width: 11, height: 11, borderRadius: '50%', border: '2px solid #da7756', borderTopColor: 'transparent', animation: 'mb-spin .8s linear infinite' }} /></>

// 칠판 그림 → 보낼 크기(긴 변 1536px JPEG) — 칠판 그림은 PNG 몇 MB라 그대로면 요청이 무거움(KAIROS 본문 상한 25MB)
async function shrinkImage(src) {
  const im = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src })
  const k = Math.min(1, 1536 / Math.max(im.naturalWidth, im.naturalHeight)), cv = document.createElement('canvas')
  cv.width = Math.round(im.naturalWidth * k); cv.height = Math.round(im.naturalHeight * k)
  const g = cv.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height); g.drawImage(im, 0, 0, cv.width, cv.height)
  return cv.toDataURL('image/jpeg', 0.9)
}

export const CHAT_W = 360, CHAT_MIN = 320, CHAT_MAX = 720   // 기본 폭 · 끌어서 바꾸는 범위(2026-10-23 사용자: 왼쪽 판처럼 폭 조절 — 칠판이 화면 절반 아래로 줄지는 않게)
export const chatClamp = w => Math.max(CHAT_MIN, Math.min(CHAT_MAX, Math.round(window.innerWidth / 2), Math.round(w)))
const LOG_URL = `/api/chatlog/${encodeURIComponent(DOC_NAME)}`
const MODEL_KEY = 'magic-board-model'   // 고른 모델은 이 브라우저에만 기억(편의)
const VENDOR = { gpt: 'GPT', gemini: 'Gemini', claude: 'Claude' }
const F = "'Pretendard', sans-serif"
const DONE = '#16a34a'   // 칠판에 붙임(끝남) = 초록 — 코랄은 할 수 있는 일 버튼(2026-10-20 사용자)
const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', bar: 'var(--mb-bar)', seg: 'var(--mb-seg)' }
const css = {
  float: { position: 'absolute', right: 12, top: 12, bottom: 12, zIndex: 5, maxWidth: 'calc(100% - 24px)', border: `1px solid ${C.line}`, borderRadius: 10, overflow: 'hidden', boxShadow: '0 4px 16px rgba(0,0,0,.12)' },
  panel: { width: CHAT_W, flex: 'none', position: 'relative', display: 'flex', flexDirection: 'column', background: C.bar, borderLeft: `1px solid ${C.line}`, font: `400 13.5px/1.55 ${F}`, color: C.ink, minHeight: 0 },
  head: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '10px 12px', borderBottom: `1px solid ${C.line}` },
  msgs: { flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 10 },
  me: { alignSelf: 'flex-end', maxWidth: '92%', background: C.seg, borderRadius: 10, padding: '7px 10px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
  ai: { alignSelf: 'stretch', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: '8px 10px', wordBreak: 'break-word' },
  err: { alignSelf: 'stretch', background: '#fff7ed', border: '1px solid #fdba74', color: '#9a3412', borderRadius: 10, padding: '8px 10px' },
  meta: { font: `400 11px ${F}`, color: C.muted },
  ctx: { display: 'block', font: `500 11px ${F}`, color: '#5aa9ff', marginBottom: 2 },
  bigNav: { font: `600 13px ${F}`, color: '#fff', background: 'rgba(255,255,255,.14)', border: '1px solid rgba(255,255,255,.3)', borderRadius: 7, padding: '6px 12px', cursor: 'pointer' },
  done: { font: `700 12px ${F}`, color: DONE, background: 'rgba(22,163,74,.1)', border: `1px solid ${DONE}`, borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  pin: { font: `700 12px ${F}`, color: '#da7756', background: 'transparent', border: '1px solid #da7756', borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  ghost: { font: `500 12px ${F}`, color: C.muted, background: 'transparent', border: `1px solid ${C.line}`, borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  foot: { borderTop: `1px solid ${C.line}`, padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6 },
  chip: { alignSelf: 'flex-start', font: `500 11.5px ${F}`, color: '#5aa9ff', background: 'rgba(90,169,255,.15)', borderRadius: 99, padding: '2px 9px' },
  input: { font: `400 13.5px/1.5 ${F}`, border: `1px solid ${C.line}`, borderRadius: 8, padding: '8px 10px', resize: 'none', minHeight: 40, maxHeight: 200, outline: 'none', background: C.card, color: C.ink },
  kind: { font: `600 11px ${F}`, color: C.muted, background: C.seg, borderRadius: 99, padding: '1px 8px' },
  bar: { display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px', borderBottom: `1px solid ${C.line}` },
  menu: { position: 'absolute', left: 0, bottom: 'calc(100% + 4px)', zIndex: 3, display: 'flex', flexDirection: 'column', minWidth: 170, background: C.card, border: `1px solid ${C.line}`, borderRadius: 8, boxShadow: '0 6px 18px rgba(0,0,0,.18)', padding: 4 },
  item: { all: 'unset', cursor: 'pointer', padding: '6px 10px', borderRadius: 6, font: `500 12.5px ${F}`, color: C.ink, whiteSpace: 'nowrap' },
  drop: { display: 'flex', flexDirection: 'column', maxHeight: 260, overflowY: 'auto', borderBottom: `1px solid ${C.line}`, background: C.card },
  row: { all: 'unset', cursor: 'pointer', display: 'flex', gap: 8, alignItems: 'center', padding: '6px 12px', font: `400 12.5px ${F}`, color: C.ink, borderBottom: `1px solid ${C.line}` },
  select: { font: `500 12px ${F}`, color: C.ink, border: `1px solid ${C.line}`, borderRadius: 6, padding: '2px 4px', background: C.card, maxWidth: 210 },
}

// 답 글 보이기(굵게·목록·제목만 — 카드에 붙는 모양과 같은 규칙). chart = { pick(표 줄, 모양), down(e, 표 줄, 모양) } — 있으면 숫자 표 밑에 「그래프로」 단추
const CHART_NAME = Object.fromEntries(CHART_KINDS)
function Answer({ text, chart }) {
  return <div>{parseAnswer(text).map((ln, i) => {
    if (ln.kind === 'gap') return <div key={i} style={{ height: 6 }} />
    if (ln.kind === 'table') { const ks = chart ? chartChoices({ type: 'table', header: ln.header, cells: answerTable(ln.rows).cells }) : []
      return <div key={i} style={{ margin: '4px 0' }}><div style={{ overflowX: 'auto' }}><table data-testid="answer-table" style={{ borderCollapse: 'collapse', fontSize: 12.5, width: '100%' }}><tbody>   {/* 표 답(2026-10-20) — 칠판에 붙이면 진짜 표 */}
        {ln.rows.map((r, j) => <tr key={j} style={ln.header && !j ? { background: C.seg, fontWeight: 700 } : null}>{r.map((c, k) => <td key={k} style={{ border: `1px solid ${C.line}`, padding: '3px 6px', verticalAlign: 'top' }}>
          {inlineParts(c).map((p, q) => (p.bold ? <b key={q}>{p.text}</b> : <span key={q}>{p.text}</span>))}</td>)}</tr>)}</tbody></table></div>
        {/* 숫자 표 = 바로 그래프로(§8 항목66 1단계 이어서, 2026-10-25) — 되는 모양만, 맨 앞(코랄) = 자료에 맞는 모양. 누르면 빈자리·끌면 놓은 자리 */}
        {ks.length > 0 && <div data-testid="answer-chart" style={{ display: 'flex', gap: 4, alignItems: 'center', marginTop: 5, flexWrap: 'wrap' }}><span style={css.meta}>그래프로</span>
          {ks.map((k, j) => <button key={k} data-chart-kind={k} onPointerDown={e => chart.down(e, ln, k)} onClick={() => chart.pick(ln, k)}
            title={`${CHART_NAME[k]} 그래프로 칠판에${j ? '' : '(이 자료에 맞는 모양)'} — 누르면 빈자리, 끌면 놓은 자리. 두 번 누르면 표로 숫자를 고쳐요`}
            style={{ ...(j ? css.ghost : css.pin), display: 'inline-flex', alignItems: 'center', gap: 3, padding: '1px 7px 1px 4px', cursor: 'grab' }}>{CHART_ICONS[k]}{CHART_NAME[k]}</button>)}</div>}</div> }
    // 답 속 주소 = 누르면 새 탭(대화창은 읽기만 해서 그냥 클릭 — 2026-10-18 사용자)
    const linked = (t, j) => { if (ln.kind === 'code') return t; const sp = urlSpans(t); if (!sp.length) return t; const out = []; let at = 0
      sp.forEach(([s, n, u], k) => { if (s > at) out.push(t.slice(at, s)); out.push(<a key={`${j}-${k}`} href={u} target="_blank" rel="noopener noreferrer" style={{ color: LINK_CHAT, textDecoration: 'underline', wordBreak: 'break-all' }} onPointerDown={e => e.stopPropagation()}>{u}</a>); at = s + n })
      if (at < t.length) out.push(t.slice(at)); return out }
    const parts = ln.parts.map((p, j) => { const c = p.code ? <code style={{ fontFamily: MONO_FONT, fontSize: '0.92em', background: C.seg, borderRadius: 3, padding: '0 3px' }}>{p.text}</code> : linked(p.text, j)   // 글 속 `코드`
      return p.bold || ln.kind === 'h' ? <b key={j}>{c}</b> : <span key={j}>{c}</span> })
    // 코드 줄 — 글꼴은 메모와 같은 Consolas부터('monospace'만 두면 한글 윈도우 기본 고정폭 글꼴이라 \가 ₩로 보였음 — 2026-10-19 사용자), 빈 줄도 한 줄 높이
    if (ln.kind === 'code') return <div key={i} style={{ fontFamily: MONO_FONT, fontSize: 12, whiteSpace: 'pre-wrap', background: C.seg }}>{ln.parts[0].text || ' '}</div>
    if (ln.kind === 'li') return <div key={i} style={{ paddingLeft: 14, textIndent: -12 }}>{ln.mark} {parts}</div>
    return <div key={i} style={ln.kind === 'h' ? { fontWeight: 700, marginTop: 2 } : null}>{parts}</div>
  })}</div>
}

// 「＋ 칠판에 추가」(그림 후보 왼쪽 위·크게 보기 창) — 늘 보이고, 올리면 코랄로 채워지며 살짝 뜸, 누르는 동안 눌림, 추가하면 1.5초 초록 「✓ 추가됨」(2026-10-20 사용자)
// 움직이는 카드 답(§8 항목66 4단계) = 대화창 안에서 바로 만져 보기 — 칠판과 같은 틀(livecard.js), 기준 720×480을 대화창 폭에 맞춰 줄임
function LivePreview({ m }) {
  const box = useRef(null), [k, setK] = useState(0.45)
  useEffect(() => { const el = box.current; if (!el) return; const ro = new ResizeObserver(() => setK(el.clientWidth / LIVE_W)); ro.observe(el); return () => ro.disconnect() }, [])
  return <div data-testid="answer-live" style={{ marginTop: 6 }}>
    <div ref={box} style={{ width: '100%', aspectRatio: `${LIVE_W} / ${LIVE_H}`, overflow: 'hidden', border: `1px solid ${C.line}`, borderRadius: 8, background: '#fff' }}>
      <iframe srcDoc={liveSrc(m.html)} title={m.title || '움직이는 카드'} sandbox="allow-scripts" csp={LIVE_CSP} scrolling="no"
        style={{ border: 0, width: LIVE_W, height: LIVE_H, transform: `scale(${k})`, transformOrigin: '0 0', display: 'block', background: '#fff' }} />
    </div>
    <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}><button style={css.ghost} onClick={() => openHtml(m.html, true)}>크게 보기</button>
      <span style={{ ...css.meta, alignSelf: 'center' }}>여기서 바로 만져 보세요 · 고칠 점을 이어서 말하면 이 카드를 고쳐요</span></div>
  </div>
}

function AddBtn({ done, onClick, big, testid }) {
  const [h, setH] = useState(false), [down, setDown] = useState(false)
  const bg = done ? DONE : big ? (h ? '#c4613f' : '#da7756') : h ? '#da7756' : 'rgba(17,17,17,.62)'   // 크게 보기 창에선 처음부터 코랄(그 창의 할 일)
  return <button data-testid={testid} onClick={onClick} onMouseEnter={() => setH(true)} onMouseLeave={() => { setH(false); setDown(false) }}
    onMouseDown={() => setDown(true)} onMouseUp={() => setDown(false)}
    style={{ font: `700 ${big ? 13 : 11}px ${F}`, color: '#fff', background: bg, border: `1px solid ${done || big || h ? bg : 'rgba(255,255,255,.35)'}`, borderRadius: big ? 7 : 6,
      padding: big ? '6px 14px' : '3px 9px', cursor: 'pointer', backdropFilter: 'blur(4px)', boxShadow: h ? '0 4px 12px rgba(0,0,0,.35)' : '0 1px 4px rgba(0,0,0,.2)',
      transform: down ? 'scale(.95)' : h ? 'translateY(-1px)' : 'none', transition: 'background .15s, border-color .15s, box-shadow .15s, transform .1s',
      ...(big ? null : { position: 'absolute', left: 6, top: 6 }) }}>{done ? '✓ 추가됨' : '＋ 칠판에 추가'}</button>
}

// 크게 보기 창 ‹ › — 그림 가장자리 안쪽 둥근 버튼, 올리면 진해짐
function NavBtn({ side, onClick, title, testid, children }) {
  const [h, setH] = useState(false)
  return <button data-testid={testid} onClick={onClick} title={title} aria-label={title} onMouseEnter={() => setH(true)} onMouseLeave={() => setH(false)}
    style={{ position: 'absolute', top: '50%', [side]: 12, transform: `translateY(-50%) scale(${h ? 1.08 : 1})`, width: 44, height: 44, borderRadius: 99, border: '1px solid rgba(255,255,255,.35)',
      background: h ? 'rgba(17,17,17,.82)' : 'rgba(17,17,17,.5)', color: '#fff', font: `400 30px/1 ${F}`, paddingBottom: 4, cursor: 'pointer', backdropFilter: 'blur(4px)',
      boxShadow: '0 2px 10px rgba(0,0,0,.35)', transition: 'background .15s, transform .12s' }}>{children}</button>
}

// ed = Editor 손잡이(selTexts·pinCard·showCard), selKey = 고른 것이 바뀔 때 다시 읽게(main이 넘김)
export function ChatPanel({ ed, selKey, floating, onClose, request, onBusy, width = CHAT_W, setWidth }) {   // width·setWidth = 폭(왼쪽 경계 끌기 — main.jsx가 이 브라우저에 기억)   // onBusy(글) = 칠판 위 알약(정돈·정리 문서 중에만, 끝나면 '')
  const [busyJob, setBusyJob] = useState('')   // 기다리는 일의 종류(모르면 '' = 서버가 짐작)   // request = { id, text, kind } — 칠판에서 시킨 질문(바뀔 때마다 한 번 보냄)   // floating = 좁은 창 — 칠판 위에 뜬 카드(2026-10-19)
  const [msgs, setMsgs] = useState([]), [loaded, setLoaded] = useState(false), [draft, setDraft] = useState(''), [busy, setBusy] = useState(null)
  const [, tick] = useState(0), [models, setModels] = useState(null), [server, setServer] = useState(true), [gone, setGone] = useState({})
  const [model, setModel] = useState(() => { try { return localStorage.getItem(MODEL_KEY) || '' } catch { return '' } })
  const box = useRef(null)
  const [past, setPastState] = useState([]), pastRef = useRef([]), [pastOpen, setPastOpen] = useState(false)   // 지난 대화(새것부터)
  const setPast = p => { pastRef.current = p; setPastState(p) }
  const [keyOpen, setKeyOpen] = useState(false), [keyDraft, setKeyDraft] = useState(''), [myKey, setMyKey] = useState(() => !!getKairosKey())   // 내 KAIROS 키 칸
  // 방금 칠판에 붙인 것은 어디 붙었나 보이게 고른 채로 남는데, 그대로 다음 질문에 실려 갔음(2026-10-19 점검) — 고름이 그대로인 동안은 안 실음
  const [skipSel, setSkipSel] = useState('')
  const sel = selKey && selKey === skipSel ? [] : ed.current?.selTexts() || []   // eslint-disable-line react-hooks/exhaustive-deps
  const selImgs = selKey && selKey === skipSel ? [] : ed.current?.selImages?.() || []   // 고른 것 속 그림(data: 주소)
  const selN = selKey && selKey === skipSel ? 0 : ed.current?.getSel?.()?.length || 0   // 같이 실리는 것이 있을 때만 칩
  const deepTg = selN ? ed.current?.deepTarget?.() : null   // 딥모드 판 꼭지를 골랐나(칩·입력 칸 안내 — 5단계)
  const [replyTo, setReplyTo] = useState(null)   // ↩ 이어 물을 답의 at
  // 그림 후보(2026-10-20 사용자): 사진 누르기 = 크게 보기 창, 왼쪽 위 「＋ 칠판에 추가」 하나(늘 보임 — 올리면 반응, 누르면 1.5초 「✓ 추가됨」 뒤 원래대로), 끌기 = 칠판에 추가(정렬선).
  // 옛 「올려 두면 크게 보기」는 없앰 — 버튼으로 가는 사이 큰 그림이 칠판을 가렸고 툴팁 위에서 깜빡였음, 크게 보기는 누르기가 맡음
  const [big, setBig] = useState(null), [flash, setFlash] = useState(''), flashT = useRef(0)   // big = { i, j }(크게 보기 창), flash = 'i:j'(방금 추가)
  const markPicked = (i, j) => { setMsgs(cur => { const next = cur.map((x, k) => (k === i ? { ...x, picked: [...new Set([...(x.picked || []), j])] } : x)); save(next); return next })
    clearTimeout(flashT.current); setFlash(`${i}:${j}`); flashT.current = setTimeout(() => setFlash(''), 1500) }   // 1.5초 — 1초는 눈이 칠판으로 가는 사이 지나감, 2초는 연달아 누를 때 헷갈림
  useEffect(() => () => clearTimeout(flashT.current), [])
  async function pinPick(i, j) {
    const m = msgs[i], id = await ed.current?.pinImage(m.images[j].url, m.prompt || '')
    if (id) markPicked(i, j)
    return id
  }
  useEffect(() => {   // 크게 보기 창: Esc 닫기 · ←/→ 다른 후보 — 칠판 글쇠(도구 바꾸기 등)로 새지 않게 먼저 받음
    if (!big) return
    const key = e => {
      const n = msgs[big.i]?.images?.length || 0
      if (e.key === 'Escape') setBig(null)
      else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') setBig(b => ({ ...b, j: (b.j + (e.key === 'ArrowRight' ? 1 : n - 1)) % n }))
      else if (e.key === 'Enter') pinPick(big.i, big.j)
      else return
      e.preventDefault(); e.stopPropagation()
    }
    window.addEventListener('keydown', key, true); return () => window.removeEventListener('keydown', key, true)
  }, [big, msgs])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetch(LOG_URL, { cache: 'no-store' }).then(r => (r.status === 404 ? { messages: [] } : r.ok ? r.json() : Promise.reject(r)))
      .then(d => { setMsgs(d.messages || []); setPast(Array.isArray(d.past) ? d.past : []); curBranch.current = !!d.branch; setLoaded(true) }).catch(() => { setServer(false); setLoaded(true) })
  }, [])
  useEffect(() => {   // 모델 목록은 키마다 다를 수 있어 키를 바꾸면 다시
    fetch('/api/models', { headers: keyHeaders() }).then(r => r.json()).then(setModels).catch(() => setModels({ featured: {}, error: '모델 목록 못 받음' }))
  }, [myKey])
  // 남은 크레딧(머리줄) — 열 때·키를 바꿀 때·답을 받을 때마다 새로(2026-10-21 사용자 — 월 할당이라 바닥날 수 있음)
  const [credits, setCredits] = useState(null)
  useEffect(() => {
    if (busy) return
    fetch('/api/credits', { headers: keyHeaders() }).then(r => (r.ok ? r.json() : null)).then(d => setCredits(d && d.quota ? d : null)).catch(() => setCredits(null))
  }, [busy, myKey])
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight }, [msgs.length, busy])
  const asked = useRef(null)
  useEffect(() => { if (!request || !loaded || asked.current === request.id) return; asked.current = request.id; send(request.text, request.kind) }, [request, loaded])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!busy) return; const t = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(t) }, [busy])

  const useModel = model || models?.default || 'gpt-6.1-sol'
  const curBranch = useRef(false)   // 지금 대화가 다른 대화에서 갈라져 나왔나(지난 대화 목록 제목 앞 ⑂)
  const save = (next, p = pastRef.current) => fetch(LOG_URL, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ messages: next, ...(p.length ? { past: p } : {}), ...(curBranch.current ? { branch: true } : {}) }) })
    .then(r => setServer(r.ok)).catch(() => setServer(false))
  const update = next => { setMsgs(next); save(next) }

  // 묻기 — history = 지금까지(마지막이 질문), kind = 'search'·'chat'(비면 서버가 짐작) → 답 한 차례
  // extra = 대화 기록엔 안 남기고 이번 요청에만 실을 것(칠판에서 고른 그림 data: 주소 — 기록이 그림으로 불지 않게)
  async function ask(history, kind = '', prevHtml = '', extra = {}) {   // prevHtml = 바로 앞 답이 정리 문서면 그 HTML(「더 짧게」 = 그 문서 고치기 — 서버가 판단)
    const q = history.filter(m => m.role === 'user').at(-1)?.content || ''
    const items = kind === 'tidy' || (!kind && TIDY_RE.test(q)) ? ed.current?.tidyItems() || [] : null   // 정리정돈(「정리해 줘」 ②) — 옮길 조각 목록(uid·종류·글·크기)
    const prefs = kind ? {} : askPrefs()
    const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() },
      body: JSON.stringify({ model: useModel, board: DOC_NAME, ...(kind ? { kind } : {}), ...(Object.keys(prefs).length ? { ask_pref: prefs } : {}), ...(prevHtml ? { prev_html: prevHtml } : {}), ...(items ? { items } : {}), ...(history.at(-1)?.infographic ? { infographic: true } : {}), ...(history.at(-1)?.base_image ? { base_image: history.at(-1).base_image } : {}), ...(history.at(-1)?.base_svg ? { base_svg: history.at(-1).base_svg } : {}), ...extra, messages: history.map(({ role, content, context }) => ({ role, content, ...(context ? { context } : {}) })) }) })
    const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
    if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
    const frames = d.kind === 'tidy' && d.plan ? ed.current?.applyTidy(d.plan, d.model) || [] : null   // 답이 도착한 이때 한 번만 칠판에(기록을 다시 열 땐 안 함)
    if (frames?.length) setSkipSel(frames.join())   // 정돈한 프레임도 고른 채로 남음 — 붙이기처럼 다음 질문엔 안 실음
    return { role: 'assistant', content: d.content, model: d.model, at: Date.now(), elapsed: d.elapsed, kind: d.kind || 'chat', ...(d.sources?.length ? { sources: d.sources } : {}), ...(d.refs?.length ? { refs: d.refs } : {}),
      ...(d.images?.length ? { images: d.images, prompt: d.caption || history.filter(m => m.role === 'user').at(-1)?.content || '' } : {}),
      ...(d.svgs?.length ? { svgs: d.svgs, prompt: history.filter(m => m.role === 'user').at(-1)?.content || '' } : {}), ...(d.credits != null ? { credits: d.credits } : {}),   // caption = 이어 고친 그림이면 처음 요청(서버)
      ...(d.html ? { html: d.html, title: d.title || (d.kind === 'live' ? '움직이는 카드' : '정리 문서') } : {}), ...(frames ? { frames } : {}), ...(d.kind === 'ask' ? { choices: d.choices || [], askKey: d.key || '' } : {}),
      ...(d.remembered ? { askKey: d.remembered.key, alt: (d.remembered.choices || []).filter(k => k !== d.kind) } : {}) }   // 기억으로 고른 답 — 「다른 쪽으로」 버튼
  }
  // 🎤 실시간 받아쓰기(2026-10-20) — 말하는 동안 입력 칸에 글자가 쌓임(누르기 전 글 뒤에), 다시 누르거나 보내면 멈춤. 직접 치면 멈춤
  const [mic, setMic] = useState('off'), [micErr, setMicErr] = useState(''), micStop = useRef(null), micBase = useRef('')
  async function toggleMic() {
    if (mic !== 'off') { micStop.current?.(); return }
    setMicErr(''); setMic('wait'); micBase.current = draft
    const join = t => { const b = micBase.current; return b && t && !/\s$/.test(b) ? `${b} ${t}` : b + t }
    try {
      micStop.current = await startMic({ headers: keyHeaders(), onText: (fin, non) => setDraft(join(fin + non)), onState: setMic, onError: setMicErr })
    } catch (e) { setMic('off'); setMicErr(e.message || String(e)) }
  }
  useEffect(() => () => micStop.current?.(), [])

  async function send(text = null, kind = '', from = null) {   // text·kind = 밖에서 시킨 질문(칠판 우클릭 「정리 문서 만들기」 — 입구는 대화창 하나), from = 「그림으로도」(정리 문서와 같은 자료)
    if (text == null && !kind) kind = pickTool   // 입력 칸에서 보낼 때만 이름표(칠판 우클릭 등 밖에서 시킨 질문은 제 길)
    const tg = !busy && !from && (kind === 'deep-section' || (text == null && !kind)) ? ed.current?.deepTarget?.() : null   // 판 꼭지를 고른 채 고치는 말 = 그 꼭지만 다시(5단계) — 질문은 보통 대화
    if (kind === 'deep-section' && busy) return
    if (kind === 'deep-section' || (tg && REDO_RE.test(draft.trim()))) { deepSection(tg, kind === 'deep-section' ? '' : draft.trim()); return }
    if (text == null && !busy && deepSend(kind)) return
    const pend = text == null && !from && replyTo == null ? msgs.findLastIndex(m => m.role !== 'error') : -1
    if (pend >= 0 && msgs[pend].kind === 'ask' && draft.trim() && !busy) return choose(pend, kind, draft.trim())   // 되묻기에 글로 답함(§8 항목64)
    const q = (text ?? draft).trim() || (text == null ? EMPTY_ASK[kind] || '' : ''); if (!q || busy) return
    if (text == null && mic !== 'off') micStop.current?.()   // 말하다 보내면 받아쓰기도 멈춤(지금까지 글로 보냄)
    const ctx = from ? from.context || '' : contextText(sel), n = from ? from.ctxCount : sel.length
    // ↩ 이어 묻기(2026-10-20 사용자 — 특정 답을 토대로) = 그 답까지만 앞 대화로 보냄(화면 기록엔 맨 끝에 쌓임, 무엇에 이었는지 표시)
    const ri = replyTo == null ? -1 : msgs.findIndex(m => m.at === replyTo)
    const before = (ri >= 0 ? msgs.slice(0, ri + 1) : msgs).filter(m => m.role !== 'error' && m.kind !== 'ask' && m.kind !== 'deep' && !m.deep)   // 답 안 한 되묻기·딥모드 카드는 앞 대화에 안 실음
    // 바로 앞(또는 이어 묻는) 답이 그림 후보면 고칠 그림 — 「두 번째」라 하면 둘째, 아니면 칠판에 마지막으로 붙인 것, 없으면 첫째(서버가 원본 유지 고치기 — input_images, 2026-10-20 사용자)
    const lastA = before.at(-1), ims = lastA?.role === 'assistant' ? lastA.images || [] : []
    const pick = /두\s*번째|둘째|2\s*번째?|오른쪽/.test(q) ? 1 : /첫\s*번째|첫째|1\s*번째?|왼쪽/.test(q) ? 0 : lastA?.picked?.at(-1) ?? 0
    const base = ims[Math.min(pick, ims.length - 1)]?.url
    const svs = lastA?.role === 'assistant' ? lastA.svgs || [] : [], baseSvg = svs[Math.min(pick, svs.length - 1)]   // 아이콘 뒤 「선을 더 굵게」 = 고른(붙인) 아이콘 고치기 — 고칠 말인지는 서버가 봄
    const boardImgs = from || !selImgs.length ? [] : await Promise.all(selImgs.map(shrinkImage))   // 칠판에서 고른 그림 = 고칠 그림(기록엔 장수만)
    const mine = { role: 'user', content: q, at: Date.now(), ...(ctx ? { context: ctx, ctxCount: n } : {}), ...(from ? { infographic: true } : {}), ...(base ? { base_image: base } : {}), ...(baseSvg ? { base_svg: baseSvg } : {}),
      ...(ri >= 0 ? { reply_to: replyTo } : {}), ...(boardImgs.length ? { imgCount: boardImgs.length } : {}) }
    const next = [...msgs.filter(m => m.role !== 'error'), mine]
    update(next); setReplyTo(null); if (text == null) setDraft(''); setBusy(Date.now()); setBusyJob(kind || (TIDY_RE.test(q) ? 'tidy' : ''))
    try { update([...next, await ask([...before, mine], kind, (!kind || kind === 'report' || kind === 'live') && lastA?.role === 'assistant' && lastA.html && (kind !== 'live' || lastA.kind === 'live') ? lastA.html : '', { ...(boardImgs.length ? { board_images: boardImgs } : {}), ...(lastA?.kind === 'live' ? { prev_kind: 'live' } : {}) })]) } catch (e) {
      setMsgs([...next, { role: 'error', content: String(e.message || e) }])   // 오류는 기록에 안 남김
    } finally { setBusy(null) }
  }
  // 딥모드(§8 항목66 3-2) — ① 「+ › 딥모드」 + 주제 = 질문지 카드(서버 안 부름) ② 「지면 계획 짜기」(입력 칸 글 = 「더」) ③ 계획 카드에서 말로 고치기 = 계획 다시 ④ 「이대로 만들기」 = 본문 → 칠판에 판.
  // 서버 길 = /api/chat `kind: 'deep'` + `deep: { step: 'plan' | 'build', topic, brief, prev?, fix?, plan?, style? }`(3-3에서 서버가 맡음). 입력 칸에서 보낼 때 먼저 봄 — 맡았으면 true
  function deepSend(kind) {
    const li = msgs.findLastIndex(m => m.role !== 'error'), last = msgs[li], t = draft.trim()
    if (last?.kind === 'deep' && last.step === 'ask' && !last.done) { deepGo(li, t); return true }
    if (last?.kind === 'deep' && last.step === 'plan' && !last.built && !last.stale && t && (!kind || kind === 'deep')) { deepReplan(li, t); return true }
    if (kind !== 'deep' || !t) return false
    const at = Date.now()
    update([...msgs.filter(m => m.role !== 'error'), { role: 'user', content: t, at, deep: true }, { role: 'assistant', kind: 'deep', step: 'ask', topic: t, brief: {}, at: at + 1 }])
    setDraft(''); setPickTool(''); if (mic !== 'off') micStop.current?.()
    return true
  }
  const setMsg = (i, patch) => setMsgs(cur => { const next = cur.map((x, j) => (j === i ? { ...x, ...patch } : x)); save(next); return next })
  async function deepCall(body, job) {
    setBusy(Date.now()); setBusyJob(job)
    try {
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() },
        body: JSON.stringify({ model: useModel, board: DOC_NAME, kind: 'deep', deep: body, messages: [{ role: 'user', content: body.topic }] }) })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      return d
    } catch (e) { setMsgs(cur => [...cur.filter(x => x.role !== 'error'), { role: 'error', content: String(e.message || e) }]); return null } finally { setBusy(null) }
  }
  const planMsg = (m, d, style) => { const rec = recommendStyle(m.brief, d.plan)
    return { role: 'assistant', kind: 'deep', step: 'plan', topic: m.topic, brief: m.brief, plan: d.plan, estimate: d.estimate, rec, style: style || rec[0], drop: [], model: d.model, elapsed: d.elapsed, credits: d.credits, at: Date.now() } }
  async function deepGo(i, more) {
    const m = msgs[i], brief = briefOf(m.brief, more)
    if (more) setDraft('')
    const d = await deepCall({ step: 'plan', topic: m.topic, brief }, 'deep-plan'); if (!d) return
    setMsgs(cur => { const next = [...cur.map((x, j) => (j === i ? { ...x, done: true, ...(more ? { more } : {}) } : x)), planMsg({ ...m, brief }, d)]; save(next); return next })
  }
  async function deepReplan(i, fix) {
    const m = msgs[i], mine = { role: 'user', content: fix, at: Date.now(), deep: true }
    setDraft(''); setMsgs(cur => [...cur, mine])
    const d = await deepCall({ step: 'plan', topic: m.topic, brief: m.brief, prev: keptPlan(m), fix }, 'deep-plan')
    if (!d) { setMsgs(cur => cur.filter(x => x !== mine)); setDraft(fix); return }
    setMsgs(cur => { const next = [...cur.map((x, j) => (j === i ? { ...x, stale: true } : x)), planMsg(m, d, m.style !== m.rec?.[0] ? m.style : '')]; save(next); return next })   // 손으로 고른 디자인은 그대로
  }
  async function deepBuild(i) {
    const m = msgs[i], plan = keptPlan(m)
    const d = await deepCall({ step: 'build', topic: m.topic, brief: m.brief, plan, style: m.style }, 'deep-build'); if (!d) return
    const r = ed.current?.deepBoard(d.plan || plan, null, m.style, { topic: m.topic, brief: m.brief }); if (!r) return
    setMsg(i, { built: r.ids[0], pages: r.pages.length, model: d.model, elapsed: d.elapsed, credits: d.credits })
    ed.current?.showIds([r.ids[0]]); setSkipSel(String(r.ids[0]))   // 보여 주려고 고른 판은 다음 질문에 안 실음(붙이기와 같게)
  }
  // 꼭지 다시 쓰기(§8 항목66 5단계) — tg = ed.deepTarget(), ask = 고칠 말(비면 「더 자세히」). 손으로 고친 판이면 크레딧 쓰기 전에 먼저 물음(덮어쓰기 확인 카드)
  function deepSection(tg, ask) {
    if (!tg) { setMsgs(cur => [...cur.filter(x => x.role !== 'error'), { role: 'error', content: '딥모드 판에서 다시 쓸 꼭지를 골라 주세요(프레임째 고르면 안 돼요)' }]); return }
    const at = Date.now(), mine = { role: 'user', content: `${tg.titles.map(t => `「${t}」`).join(' ')} — ${ask || '더 자세히'}`, at, deep: true }
    if (ask) setDraft('')
    if (tg.edited) { update([...msgs.filter(m => m.role !== 'error'), mine, { role: 'assistant', kind: 'deep', step: 'confirm', root: tg.root, idx: tg.idx, titles: tg.titles, ask, at: at + 1 }]); return }
    update([...msgs.filter(m => m.role !== 'error'), mine]); deepSectionRun(tg, ask)
  }
  async function deepSectionRun(tg, ask) {
    const d = await deepCall({ step: 'section', topic: tg.topic, brief: tg.brief, plan: tg.plan, idx: tg.idx, ask }, 'deep-section'); if (!d) return
    const r = d.sections?.length ? ed.current?.deepRedoSection(tg.root, d.sections, d.sources) : null
    if (r) setSkipSel(String(tg.root))   // 다시 지은 판(고른 채)은 다음 질문에 안 실음(붙이기와 같게)
    const miss = d.missing?.length ? `\n\n그대로 둔 꼭지(못 씀): ${d.missing.join(', ')}` : ''
    const content = r ? `${d.sections.map(s => `「${s.title}」`).join(' ')}를 다시 써서 판을 다시 지었어요 — 마음에 안 들면 Ctrl+Z 한 번이면 돌아가요${miss}` : `다시 쓰지 못했어요${miss || ' — 판이 지워졌거나 답이 비었어요'}`
    setMsgs(cur => { const next = [...cur.filter(x => x.role !== 'error'), { role: 'assistant', kind: 'deep', step: 'section', root: tg.root, content, model: d.model, elapsed: d.elapsed, credits: d.credits, at: Date.now() }]; save(next); return next })
  }
  // 덮어쓰기 확인 카드 「덮어쓰고 다시 쓰기」 — 그 판 그 꼭지(그사이 고른 것이 바뀌어도)
  function deepConfirm(i) {
    const m = msgs[i], tg = ed.current?.deepTarget?.(m.root, m.idx)
    setMsg(i, { done: true })
    if (tg) deepSectionRun(tg, m.ask)
    else setMsgs(cur => [...cur.filter(x => x.role !== 'error'), { role: 'error', content: '그 판이 지워졌어요' }])
  }
  // 되묻기 버튼(또는 기억으로 고른 답의 「다른 쪽으로」) — 고른 길을 기억하고, 같은 질문(그 앞 대화까지)을 그 길로 보내 이 자리에 답을 끼움.
  // add = 덧붙일 말(입력 칸 — 버튼과 같이 눌렀거나 버튼 대신 친 글): 처음 질문 뒤에 붙여 보내고, 길이 안 정해졌으면 서버가 그 말로 고름(못 알아들으면 원래 1등 — 다시 안 물음)
  async function choose(i, k, add = '') {
    const history = msgs.slice(0, i).filter(m => m.role !== 'error' && m.kind !== 'ask' && m.kind !== 'deep' && !m.deep), m = msgs[i]
    if (busy || history.at(-1)?.role !== 'user') return
    if (m.askKey && k) rememberAsk(m.askKey, k)
    if (!add && m.kind === 'ask' && draft.trim()) add = draft.trim()
    const q = history.at(-1), sent = add ? [...history.slice(0, -1), { ...q, content: `${q.content}\n${add}` }] : history
    const shown = add ? [...msgs.slice(0, i), { role: 'user', content: add, at: Date.now(), addTo: true }] : msgs.slice(0, i)   // 덧붙인 말도 기록에 보이게
    if (add) { setDraft(''); setPickTool(''); if (mic !== 'off') micStop.current?.() }
    const extra = { ...(add && !k ? { ask_add: add, ask_reply: { choices: m.choices || [], default: m.choices?.[0] || '' } } : {}) }
    const boardImgs = selImgs.length ? await Promise.all(selImgs.map(shrinkImage)) : []
    setBusy(Date.now()); setBusyJob(k)
    try { const a = await ask(sent, k, '', { ...extra, ...(boardImgs.length ? { board_images: boardImgs } : {}) }); update([...shown, a, ...msgs.slice(i + 1)]) } catch (e) {
      setMsgs([...msgs.filter(x => x.role !== 'error'), { role: 'error', content: String(e.message || e) }])
    } finally { setBusy(null) }
  }
  function pin(i) {
    const m = msgs[i]
    if (ed.current?.showCard(m.at)) return   // 이미 붙인 카드 → 그리로
    const ids = ed.current?.pinCard(m); if (ids) { setSkipSel(ids.join()); update(msgs.map((x, j) => (j === i ? { ...x, pinned: true } : x))) }
  }
  // 버튼을 6px 넘게 끌면 카드가 손에 붙어 칠판으로(팔레트 버튼과 같은 방식) — 놓은 자리에 붙음
  const dragged = useRef(false)
  function dragDown(e, i) {
    if (e.button !== 0) return
    dragged.current = false   // 끌어 놓고 나면 버튼 위가 아니라 click이 안 올 수 있어 매번 처음부터
    const sx = e.clientX, sy = e.clientY, m = msgs[i]
    const move = ev => { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) <= 6) return; done(); dragged.current = true
      ed.current?.dragCard(m, ids => setSkipSel((ids || []).join()) || setMsgs(cur => { const next = cur.map((x, j) => (j === i ? { ...x, pinned: true } : x)); save(next); return next })) }
    const done = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', done) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', done)
  }
  // 표 답 「그래프로」 — 누르기 = 빈자리, 6px 넘게 끌면 칠판이 그래프를 끌고 놓은 자리에(위 dragDown과 같은 방식). 붙인 것은 다음 질문에 안 실음
  const chartAct = m => ({
    pick: (ln, kind) => { if (dragged.current) { dragged.current = false; return } const ids = ed.current?.pinChart({ rows: ln.rows, header: ln.header, kind, sources: m.sources }); if (ids) setSkipSel(ids.join()) },
    down: (e, ln, kind) => { if (e.button !== 0) return
      dragged.current = false; const sx = e.clientX, sy = e.clientY
      const move = ev => { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) <= 6) return; done(); dragged.current = true
        ed.current?.dragChart({ rows: ln.rows, header: ln.header, kind, sources: m.sources }, ids => setSkipSel((ids || []).join())) }
      const done = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', done) }
      window.addEventListener('pointermove', move); window.addEventListener('pointerup', done) },
  })
  // 그림 후보 끌기 — 6px 넘게 움직이면 칠판이 실제 크기 그림을 끌고(정렬선), 놓은 자리에 붙음. 대화창 밖에서 떼야 붙음
  function imgDown(e, i, j) {
    if (e.button !== 0) return
    dragged.current = false
    const sx = e.clientX, sy = e.clientY, m = msgs[i]
    let up = false
    const move = ev => { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) <= 6) return; window.removeEventListener('pointermove', move); dragged.current = true
      ed.current?.dragImage(m.images[j].url, m.prompt || '', ids => { setSkipSel((ids || []).join()); markPicked(i, j) }, () => up) }
    const done = () => { up = true; window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', done) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', done)
  }
  // 아이콘 후보 — 누르면 빈자리, 끌면 놓은 자리(칠판이 도형을 끌고 정렬선). 붙인 도형은 다음 질문에 안 실음
  function pinSvgPick(i, j) { const ids = ed.current?.pinSvg(msgs[i].svgs[j]); if (ids) { setSkipSel(ids.join()); markPicked(i, j) } }
  function svgDown(e, i, j) {
    if (e.button !== 0) return
    dragged.current = false
    const sx = e.clientX, sy = e.clientY
    const move = ev => { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) <= 6) return; done(); dragged.current = true
      ed.current?.dragSvg(msgs[i].svgs[j], ids => { setSkipSel((ids || []).join()); markPicked(i, j) }) }
    const done = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', done) }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', done)
  }
  // 새 대화 — 지금 대화를 지난 대화 맨 위로(빈 대화면 그냥 둠). 질문 하나 = 제목
  const shelve = (cur, p) => { const kept = cur.filter(m => m.role !== 'error'); if (!kept.some(m => m.role === 'user')) return p
    return [{ at: kept[0].at || Date.now(), title: (curBranch.current ? '⑂ ' : '') + (kept.find(m => m.role === 'user').content || '').split(/\r?\n/)[0].slice(0, 40), messages: kept, ...(curBranch.current ? { branch: true } : {}) }, ...p] }
  const reset = () => { setSkipSel(''); setGone({}); setPastOpen(false); setReplyTo(null) }
  // 이어 묻는 답을 한 줄로(「↩ … 에 이어서」 표시) — 그림 답은 처음 요청
  const replyLabel = at => { const a = msgs.find(m => m.at === at); if (!a) return '지운 답'; const t = (a.images?.length ? `🎨 ${a.prompt || '그림'}` : a.svgs?.length ? `✏️ ${a.prompt || '아이콘'}` : a.content || '').split('\n')[0].replace(/[*#>`]/g, '').trim(); return t.length > 26 ? t.slice(0, 26) + '…' : t }
  function newChat() { if (busy) return; const p = shelve(msgs, pastRef.current); setPast(p); reset(); curBranch.current = false; setMsgs([]); save([], p) }
  function openPast(j) { if (busy) return; const pick = pastRef.current[j], p = shelve(msgs, pastRef.current.filter((_, k) => k !== j)); setPast(p); reset(); curBranch.current = !!pick.branch; setMsgs(pick.messages); save(pick.messages, p) }
  // 새 대화로 분기(2026-10-20 사용자 — Gemini·ChatGPT 참고) — 이 답까지를 복사해 새 대화로, 지금 대화는 「지난 대화」에 그대로
  function branch(i) { if (busy) return; const keep = msgs.slice(0, i + 1).filter(m => m.role !== 'error'), p = shelve(msgs, pastRef.current); setPast(p); reset(); curBranch.current = true; setMsgs(keep); save(keep, p) }
  // 다시 만들기 — 같은 질문(그 앞 대화까지)·같은 종류로 한 번 더 물어 이 답을 바꿔 끼움
  async function regen(i) {
    const history = msgs.slice(0, i).filter(m => m.role !== 'error'), m = msgs[i]
    if (busy || history.at(-1)?.role !== 'user') return
    setBusy(Date.now()); setBusyJob(m.kind || '')
    try { const a = await ask(history, m.kind || '', m.kind === 'report' && history.at(-2)?.html ? history.at(-2).html : ''); update(msgs.map((x, j) => (j === i ? a : x))) } catch (e) {
      setMsgs([...msgs.filter(x => x.role !== 'error'), { role: 'error', content: String(e.message || e) }])
    } finally { setBusy(null) }
  }
  const [menuAt, setMenuAt] = useState(null)   // ⋯ 메뉴를 연 답의 at
  useEffect(() => { if (menuAt == null) return; const close = e => { if (!e.target.closest?.('[data-answer-menu]')) setMenuAt(null) }; window.addEventListener('pointerdown', close, true); return () => window.removeEventListener('pointerdown', close, true) }, [menuAt])
  // 「+」 도구(2026-10-23 사용자 — Gemini·ChatGPT·Claude처럼): 기본은 앱이 길을 고르고, 고르면 이름표가 남아 그 길로만(× = 다시 자동). 「아이콘」처럼 뜻이 둘인 말을 위해
  const [pickTool, setPickTool] = useState(''), [plusOpen, setPlusOpen] = useState(false)
  useEffect(() => { if (!plusOpen) return; const close = e => { if (!e.target.closest?.('[data-plus-menu]')) setPlusOpen(false) }; window.addEventListener('pointerdown', close, true); return () => window.removeEventListener('pointerdown', close, true) }, [plusOpen])
  function saveKey(v) { setKairosKey(v.trim()); setMyKey(!!v.trim()); setKeyDraft(''); setKeyOpen(false) }
  // 정리 문서 → 같은 자료로 인포그래픽 그림 후보(2026-10-20 사용자 선택 — 그림은 보기 좋지만 숫자를 지어낼 수 있어 기본은 문서, 원하면 한 번 더)
  function drawReport(i) { const src = msgs.slice(0, i).filter(m => m.role === 'user').at(-1) || {}; send(`「${msgs[i].title || '정리 문서'}」 인포그래픽 그림`, 'image', { context: src.context, ctxCount: src.ctxCount }) }
  function retry() {
    const last = [...msgs].reverse().find(m => m.role === 'user'); if (!last) return
    setMsgs(msgs.filter(m => m.role !== 'error').slice(0, -1)); setDraft(last.content)
  }

  const busyLine = !busy ? '' : `${JOB_LABEL[busyJob] || (busyJob === 'chat' ? `${useModel} 생각 중` : 'KAIROS 생각 중')}${JOB_LABEL[busyJob] && (models?.jobs?.[busyJob] || (busyJob === 'board' ? useModel : '')) ? ` · ${models?.jobs?.[busyJob] || useModel}` : ''}… ${Math.round((Date.now() - busy) / 1000)}초`
  // 일을 아직 모를 때(서버가 짐작 — 「정리 문서로 만들어 줘」를 쳐서 물음)는 모델 이름을 안 씀: 고른 모델이 아닐 수 있음(2026-10-20 실화면)
  useEffect(() => { onBusy?.(busy && BOARD_JOBS.has(busyJob) ? busyLine : '') }, [busyLine])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => onBusy?.(''), [])   // eslint-disable-line react-hooks/exhaustive-deps
  const feat = models?.featured || {}
  const lastM = msgs.filter(m => m.role !== 'error').at(-1), tools = TOOLS.filter(t => (t[0] !== 'deep' && t[0] !== 'live') || models?.jobs?.[t[0]])   // 딥모드·움직이는 카드 = 서버가 할 수 있을 때만
  return (
    <aside style={{ ...(floating ? { ...css.panel, ...css.float } : css.panel), width }} aria-label="KAIROS 대화" onPointerDown={e => e.stopPropagation()}>
      {/* 폭 조절 — 왼쪽 경계 끌기(320~720, 화면 절반까지), 두 번 누르면 기본 폭(왼쪽 판 `dock-resize`와 같은 손맛) */}
      {setWidth && <div data-testid="chat-resize" title="끌어서 대화창 폭 조절 · 두 번 누르면 기본 폭" onDoubleClick={() => setWidth(CHAT_W)}
        onPointerDown={e => { e.preventDefault(); const x0 = e.clientX, w0 = width, el = e.currentTarget; el.setPointerCapture(e.pointerId)
          const mv = ev => setWidth(chatClamp(w0 - (ev.clientX - x0))), up = () => { el.removeEventListener('pointermove', mv); el.removeEventListener('pointerup', up) }
          el.addEventListener('pointermove', mv); el.addEventListener('pointerup', up) }}
        style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: 6, cursor: 'col-resize', zIndex: 6 }}
        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(218,119,86,.35)' }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }} />}
      {big && msgs[big.i]?.images?.[big.j] && (() => { const m = msgs[big.i], n = m.images.length, go = d => setBig(b => ({ ...b, j: (b.j + d + n) % n }))
        return createPortal(<div data-testid="image-big" onPointerDown={e => e.stopPropagation()} onClick={() => setBig(null)}
          style={{ position: 'fixed', inset: 0, zIndex: 200, background: 'rgba(0,0,0,.72)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, padding: 24, boxSizing: 'border-box' }}>
          <div onClick={e => e.stopPropagation()} style={{ position: 'relative', display: 'flex', maxWidth: '100%', minHeight: 0 }}>   {/* 2장 이상이면 그림 양옆 ‹ › (사진 보기처럼 — 아래 버튼 줄은 추가 + 닫기만, 2026-10-20 사용자) */}
            <img src={m.images[big.j].url} alt={`후보 ${big.j + 1}`} draggable={false}
              style={{ maxWidth: '100%', maxHeight: 'calc(100vh - 140px)', objectFit: 'contain', borderRadius: 10, boxShadow: '0 16px 50px rgba(0,0,0,.5)', background: '#fff' }} />
            {n > 1 && <NavBtn testid="image-big-prev" side="left" onClick={() => go(-1)} title="이전 후보(←)">‹</NavBtn>}
            {n > 1 && <NavBtn testid="image-big-next" side="right" onClick={() => go(1)} title="다음 후보(→)">›</NavBtn>}
          </div>
          <div onClick={e => e.stopPropagation()} style={{ display: 'flex', gap: 8, alignItems: 'center', font: `500 13px ${F}`, color: '#fff' }}>
            <AddBtn testid="image-big-pin" big done={flash === `${big.i}:${big.j}`} onClick={() => pinPick(big.i, big.j)} />
            <button style={css.bigNav} onClick={() => setBig(null)} title="닫기(Esc)">닫기</button>
          </div>
          {n > 1 && <div data-testid="image-big-count" style={{ font: `500 12px ${F}`, color: 'rgba(255,255,255,.6)', marginTop: -6 }}>{big.j + 1} / {n}</div>}
          </div>, document.body) })()}
      <div style={css.head}>
        <b style={{ fontSize: 14 }}>KAIROS</b>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {credits && <span data-testid="chat-credits" title={`이번 달 ${Math.round(credits.quota).toLocaleString('ko-KR')} 크레딧 중 남은 것(${myKey ? '내 키' : '서버 키'}) — 답을 받을 때마다 새로`}
            style={{ font: `500 12px ${F}`, color: credits.remaining < credits.quota * 0.1 ? '#da7756' : C.muted }}>남은 {Math.round(credits.remaining).toLocaleString('ko-KR')}</span>}
          <button title="대화창 닫기" onClick={onClose} style={{ ...css.ghost, padding: '0 7px' }}>✕</button>
        </div>
      </div>
      <div style={css.bar}>   {/* 대화 관리 줄 — 새 대화 · 지난 대화 · 내 키 */}
        <button style={css.ghost} disabled={!!busy || !msgs.some(m => m.role === 'user')} onClick={newChat} title="지금 대화는 「지난 대화」로 넘기고 빈 대화로 — 앞 대화가 다음 질문에 안 실려요">＋ 새 대화</button>
        {past.length > 0 && <button style={css.ghost} disabled={!!busy} aria-expanded={pastOpen} onClick={() => setPastOpen(o => !o)} title="지난 대화를 골라 다시 열어요(지금 대화는 목록으로)">지난 대화 {past.length} ▾</button>}
        <button style={{ ...css.ghost, marginLeft: 'auto', ...(myKey ? { color: '#0f766e', borderColor: '#0f766e' } : null) }} aria-expanded={keyOpen} onClick={() => setKeyOpen(o => !o)}
          title={myKey ? '내 KAIROS 키로 부르는 중 — 바꾸거나 지우기' : '내 KAIROS 키 넣기(안 넣으면 서버 PC 키)'}>🔑 {myKey ? '내 키' : '서버 키'}</button>
      </div>
      {pastOpen && <div data-testid="past-list" style={css.drop}>
        {past.map((c, j) => <button key={c.at + ':' + j} style={css.row} onClick={() => openPast(j)} title={c.title}>
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title || '(제목 없음)'}</span>
          <span style={css.meta}>{new Date(c.at).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })} · {c.messages.filter(m => m.role === 'user').length}문</span></button>)}
      </div>}
      {keyOpen && <div data-testid="key-box" style={{ ...css.drop, padding: 10, gap: 6 }}>
        <span style={css.meta}>내 KAIROS API 키 — 이 브라우저에만 저장되고, 물을 때만 서버로 같이 가요(서버는 남기지 않아요). 비우면 서버 PC 키를 써요.</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <input type="password" autoComplete="off" placeholder={myKey ? '새 키로 바꾸기' : '키 붙여넣기'} value={keyDraft} onChange={e => setKeyDraft(e.target.value)}
            onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter' && KEY_RE.test(keyDraft.trim())) saveKey(keyDraft) }} style={{ ...css.input, minHeight: 0, padding: '4px 8px', flex: 1 }} />
          <button style={css.pin} disabled={!KEY_RE.test(keyDraft.trim())} onClick={() => saveKey(keyDraft)}>저장</button>
          {myKey && <button style={css.ghost} onClick={() => saveKey('')}>지우기</button>}
        </div>
      </div>}
      <div ref={box} style={css.msgs}>
        {loaded && !msgs.length && <div style={{ ...css.meta, fontSize: 12.5, lineHeight: 1.6 }}>
          무엇이든 물어보세요. 남길 답은 「칠판에 붙이기」나 끌어다 놓기로 메모가 됩니다.<br />칠판에서 메모나 글을 고른 채 물으면 그 내용을 같이 보냅니다.</div>}
        {msgs.map((m, i) => m.role === 'user'
          ? <div key={i} style={css.me}>{m.addTo ? <span style={css.ctx}>위 질문에 덧붙여</span> : null}{m.reply_to ? <span style={css.ctx}>↩ 「{replyLabel(m.reply_to)}」에 이어서</span> : null}
            {m.ctxCount ? <span style={css.ctx}>칠판에서 고른 것 {m.ctxCount}개와 함께</span> : null}{m.imgCount ? <span style={css.ctx}>칠판에서 고른 그림 {m.imgCount}장을 고쳐 달라고</span> : null}{m.content}</div>
          : m.role === 'error'
            ? <div key={i} style={css.err}>{m.content}<div style={{ marginTop: 6 }}><button style={css.ghost} onClick={retry}>질문 다시 고치기</button></div></div>
            : <div key={i} style={css.ai}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                <span data-testid="answer-kind" style={{ ...css.kind, ...(KINDS[m.kind] ? KINDS[m.kind][1] : null) }}>{(KINDS[m.kind] || KINDS.chat)[0]}</span>
              </div>
              {m.alt?.length > 0 && <div data-testid="ask-remembered" style={{ ...css.meta, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginBottom: 4 }}>
                <span>기억한 대로 {(ASK_LABEL[m.kind] || [m.kind])[0]} 했어요</span>
                {m.alt.map(k => <button key={k} data-testid="ask-other" data-kind={k} style={css.ghost} disabled={!!busy} onClick={() => choose(i, k)} title="같은 질문을 이쪽으로 다시 — 다음엔 다시 물어요">{(ASK_LABEL[k] || [k])[0]} 바꾸기</button>)}
              </div>}
              {m.kind === 'deep' ? (m.step === 'section' ? <Answer text={m.content} />
                : m.step === 'confirm' ? <DeepConfirm m={m} busy={busy} css={css} yes={() => deepConfirm(i)} no={() => setMsg(i, { done: 'no' })} />
                : m.step === 'ask'
                ? <DeepAsk m={m} busy={busy} css={css} set={(q, v) => setMsg(i, { brief: { ...m.brief, [q]: v } })} go={() => deepGo(i, draft.trim())} />
                : <DeepPlan m={m} busy={busy} css={css} drop={k => setMsg(i, { drop: (m.drop || []).includes(k) ? m.drop.filter(x => x !== k) : [...(m.drop || []), k] })}
                  pickStyle={k => setMsg(i, { style: k })} build={() => deepBuild(i)} show={() => ed.current?.showIds([m.built]) || setGone(g => ({ ...g, [m.at + ':deep']: true }))} />)
                : <Answer text={m.content} chart={m.kind === 'ask' ? null : chartAct(m)} />}
              {m.kind === 'deep' && (m.model || gone[m.at + ':deep']) && <div style={{ ...css.meta, marginTop: 6, textAlign: 'right' }}>{gone[m.at + ':deep'] ? '판이 지워졌어요 · ' : ''}{m.model || ''}{m.elapsed != null ? ` · ${m.elapsed}초` : ''}{m.credits != null ? ` · ${Math.round(m.credits)}크레딧` : ''}</div>}
              {m.kind === 'ask' && <div data-testid="ask-choices" style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                {(m.choices || []).map(k => <button key={k} data-testid="ask-choice" data-kind={k} disabled={!!busy} onClick={() => choose(i, k)} title={(ASK_LABEL[k] || [])[1]}
                  style={{ ...css.pin, display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 1, padding: '6px 10px', textAlign: 'left' }}>
                  <span>{(ASK_LABEL[k] || [k])[0]}</span><span style={{ ...css.meta, fontWeight: 400 }}>{(ASK_LABEL[k] || [])[1]}</span></button>)}
                <span style={css.meta}>보기에 없으면 아래 칸에 적어 주세요. 같은 걸 두 번 고르면 다음엔 바로 해요</span>
              </div>}
              {m.html && m.kind === 'live' && <LivePreview m={m} />}
              {m.html && m.kind !== 'live' && <div data-testid="answer-doc" style={{ marginTop: 6 }}>   {/* 정리 문서 미리보기 — A4 폭 794px를 대화창 폭에 맞춰 줄임(스크립트 없는 iframe) */}
                <div style={{ height: 300, overflow: 'hidden', border: `1px solid ${C.line}`, borderRadius: 8, background: '#fff', cursor: 'zoom-in' }} title="크게 보기·인쇄" onClick={() => openHtml(m.html)}>
                  <iframe srcDoc={m.html} title={m.title || '정리 문서'} sandbox="" scrolling="no" style={{ border: 0, width: 794, height: 300 / 0.41, transform: 'scale(0.41)', transformOrigin: '0 0', pointerEvents: 'none' }} />
                </div>
                <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}><button style={css.ghost} onClick={() => openHtml(m.html)}>크게 보기 · 인쇄</button>
                  <button style={css.ghost} disabled={!!busy} onClick={() => drawReport(i)} title="같은 자료로 인포그래픽 그림 후보 2장 — 보기 좋지만 숫자·날짜를 지어낼 수 있으니 확인하고 쓰세요(약 20크레딧)">🎨 그림으로도</button>
                  <span style={{ ...css.meta, alignSelf: 'center' }}>고칠 점을 이어서 말하면 이 문서를 고쳐 써요</span></div>
              </div>}
              {m.images?.length > 0 && <div data-testid="answer-images" style={{ marginTop: 6, display: 'grid', gridTemplateColumns: `repeat(${Math.min(2, m.images.length)}, 1fr)`, gap: 6, alignItems: 'start' }}>   {/* 원래 비율(2026-10-20 사용자: 4:3으로 채우니 잘림) — 세로로 긴 그림은 320px까지 */}
                {/* 사진 누르기 = 크게 보기, 왼쪽 위 「＋ 칠판에 추가」, 추가한 적 있으면 테두리만 초록, 사진·버튼 어디서든 끌면 칠판이 직접 끔(실제 크기 + 정렬선) */}
                {m.images.map((g, j) => { const done = m.picked?.includes(j)
                  return <div key={g.url} data-testid="image-pick" data-picked={done ? "1" : undefined} role="button" tabIndex={0} aria-label={`후보 ${j + 1} 크게 보기`}
                    onClick={() => { if (dragged.current) { dragged.current = false; return } setBig({ i, j }) }}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setBig({ i, j }) } }}
                    onPointerDown={e => imgDown(e, i, j)}
                    style={{ cursor: 'zoom-in', position: 'relative', borderRadius: 8, overflow: 'hidden', border: `2px solid ${done ? DONE : C.line}` }}>
                    <img src={g.url} alt={`후보 ${j + 1}`} draggable={false} style={{ display: 'block', width: '100%', height: 'auto', maxHeight: 320, objectFit: 'contain', background: '#fff' }} />
                    <AddBtn testid="image-pin" done={flash === `${i}:${j}`} onClick={async e => { e.stopPropagation(); if (dragged.current) { dragged.current = false; return } await pinPick(i, j) }} />
                  </div> })}</div>}
              {m.svgs?.length > 0 && <div data-testid="answer-svgs" style={{ marginTop: 6, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 6 }}>   {/* 하나여도 반 폭(고치기 답 — 꽉 채우면 너무 큼) */}
                {/* 미리보기 = 칠판에 들어갈 도형 그대로(svgPreview). 누르기 = 칠판에 추가(그림처럼 크게 볼 것 없는 단순한 선), 끌기 = 놓은 자리 */}
                {m.svgs.map((sv, j) => { const done = m.picked?.includes(j)
                  return <div key={j} data-testid="svg-pick" data-picked={done ? '1' : undefined} role="button" tabIndex={0} aria-label={`아이콘 후보 ${j + 1} 칠판에 추가`}
                    title="누르면 칠판 빈자리에 · 끌면 놓은 자리에 — 선 하나하나 고칠 수 있어요"
                    onClick={() => { if (dragged.current) { dragged.current = false; return } pinSvgPick(i, j) }}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pinSvgPick(i, j) } }}
                    onPointerDown={e => svgDown(e, i, j)}
                    style={{ cursor: 'copy', position: 'relative', borderRadius: 8, border: `2px solid ${done ? DONE : C.line}`, background: '#fff', aspectRatio: '1' }}>
                    <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgPreview(sv))}`} alt={`아이콘 후보 ${j + 1}`} draggable={false} style={{ display: 'block', width: '100%', height: '100%', padding: 10, boxSizing: 'border-box' }} />
                    {flash === `${i}:${j}` && <span style={{ position: 'absolute', left: 6, top: 6, ...css.meta, color: DONE, background: '#fff', borderRadius: 4, padding: '0 4px' }}>✓ 추가됨</span>}
                  </div> })}</div>}
              {m.refs?.length > 0 && <div data-testid="answer-refs" style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {m.refs.map(r => <button key={r.n} onClick={() => ed.current?.showItem(r.uid) || setGone(g => ({ ...g, [m.at + ':' + r.n]: true }))} title="칠판의 그 도형으로 가기"
                  style={{ all: 'unset', cursor: 'pointer', ...css.meta, color: '#d97706', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  📌 [칠판 {r.n}] {r.kind ? `${r.kind} · ` : ''}{(r.text || '').split('\n')[0]}{gone[m.at + ':' + r.n] ? ' — 지워졌어요' : ''}</button>)}</div>}
              {m.sources?.length > 0 && <div data-testid="answer-sources" style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
                {m.sources.map(s => <a key={s.n} href={s.url} target="_blank" rel="noopener noreferrer" title={s.url} onPointerDown={e => e.stopPropagation()}
                  style={{ ...css.meta, color: LINK_CHAT, textDecoration: 'none', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>[{s.n}] {s.title || siteOf(s.url)} · {siteOf(s.url)}</a>)}</div>}
              {m.kind !== 'ask' && m.kind !== 'deep' && <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
                {m.kind === 'tidy' && <button style={css.pin} onClick={() => ed.current?.showIds(m.frames) || setGone(g => ({ ...g, [m.at + ':tidy']: true }))} title="정돈해 만든 프레임들이 한눈에 보이게">
                  {gone[m.at + ':tidy'] ? '프레임이 지워졌어요' : '정돈한 곳 보기'}</button>}
                {!m.images?.length && !m.svgs?.length && m.kind !== 'tidy' && <button style={{ ...(m.pinned ? css.done : css.pin), cursor: 'grab' }} onPointerDown={e => dragDown(e, i)} onClick={() => { if (dragged.current) { dragged.current = false; return } pin(i) }}
                  title={m.pinned ? '누르면 붙인 카드로 가기(지웠으면 다시 붙임) · 칠판으로 끌면 그 자리에 하나 더' : m.refs?.length ? '메모 + 근거가 된 칠판 도형으로 가는 점선 화살표(누르면 빈자리, 끌면 놓은 자리)' : m.sources?.length ? '요약 메모 + 출처 카드를 번호 화살표로 이어 한 묶음으로(누르면 빈자리, 끌면 놓은 자리)' : '누르면 빈자리에, 칠판으로 끌면 놓은 자리에 카드로'}>
                  {m.pinned ? '칠판에 붙임 ✓' : '칠판에 붙이기'}</button>}
                {/* ⋯ 하나에 — 이어 묻기·분기·다시 만들기·복사(2026-10-20 사용자: 다른 AI 채팅 참고, 버튼은 늘리지 않게) */}
                <span data-answer-menu style={{ position: 'relative' }}>
                  <button data-testid="answer-menu" style={{ ...css.ghost, ...(replyTo === m.at ? { color: '#da7756', borderColor: '#da7756' } : null) }} aria-expanded={menuAt === m.at} onClick={() => setMenuAt(a => (a === m.at ? null : m.at))} title="이 답으로 — 이어 묻기·새 대화로 분기·다시 만들기·복사">{replyTo === m.at ? '↩ ⋯' : '⋯'}</button>
                  {menuAt === m.at && <div role="menu" style={css.menu}><style>{'.mb-mi:hover:not(:disabled){background:var(--mb-seg)}.mb-mi:disabled{opacity:.45;cursor:default}'}</style>
                    {[['↩ 여기서 이어 묻기', '다음 질문이 이 답까지를 이어받아요(그림이면 그 그림을 고쳐요)', () => setReplyTo(m.at)],
                      ['⑂ 새 대화로 분기', '이 답까지를 새 대화로 — 지금 대화는 「지난 대화」에', () => branch(i)],
                      ...(m.kind !== 'tidy' ? [['↻ 다시 만들기', '같은 질문으로 한 번 더 — 이 답을 바꿔요', () => regen(i)]] : []),
                      ...(!m.images?.length && !m.svgs?.length && !m.html ? [['복사', '답 글을 클립보드로', () => navigator.clipboard?.writeText(m.content).catch(() => {})]] : [])]
                      .map(([label, tip, fn]) => <button key={label} role="menuitem" className="mb-mi" style={css.item} disabled={!!busy && label !== '복사'} title={tip} onClick={() => { setMenuAt(null); fn() }}>{label}</button>)}
                  </div>}
                </span>
                <span style={{ ...css.meta, marginLeft: 'auto' }}>{m.model}{m.elapsed != null ? ` · ${m.elapsed}초` : ''}{m.credits != null ? ` · ${Math.round(m.credits)}크레딧` : ''}</span>
              </div>}
            </div>)}
        {busy && <div data-testid="chat-busy" style={{ ...css.ai, color: C.muted, display: 'flex', alignItems: 'center', gap: 8 }}><Spinner />{busyLine}</div>}
      </div>
      <div style={css.foot}>
        {replyTo != null && <span data-testid="reply-chip" style={{ ...css.chip, color: '#da7756', background: 'rgba(218,119,86,.14)', cursor: 'pointer' }} onClick={() => setReplyTo(null)} title="누르면 이어 묻기 취소">
          ↩ 「{replyLabel(replyTo)}」에 이어서 ✕</span>}
        {selN > 0 && (sel.length > 0 || selImgs.length > 0) && <span data-testid="sel-chip" style={css.chip} title={deepTg ? '고치는 말(더 자세히·바꿔 줘·표로…)이면 이 꼭지만 다시 써요 — 묻는 말이면 보통 대화' : undefined}>{selN}개 선택됨{deepTg ? ` · 꼭지 ${deepTg.titles.map(t => `「${t}」`).join(' ')}` : ''}</span>}{/* 2026-10-21 사용자: 글·그림 칩 둘 + 사용법 문장 → 한 칩(사용법은 설명 페이지로) */}
        {pickTool && <span data-testid="tool-chip" style={{ ...css.chip, color: '#da7756', background: 'rgba(218,119,86,.14)', cursor: 'pointer' }} onClick={() => setPickTool('')} title="누르면 이름표를 떼고 다시 앱이 길을 골라요">
          {TOOLS.find(t => t[0] === pickTool)?.[1]} ✕</span>}
        <textarea style={css.input} rows={Math.min(8, Math.max(2, draft.split('\n').length))} value={draft} placeholder={TOOLS.find(t => t[0] === pickTool)?.[3] || (lastM?.kind === 'ask' ? '버튼을 누르거나, 원하는 걸 직접 적어 주세요'
            : lastM?.kind === 'deep' && lastM.step === 'ask' && !lastM.done ? '꼭 넣을 것·바라는 점(비워도 돼요) — Enter = 지면 계획 짜기'
            : lastM?.kind === 'deep' && lastM.step === 'plan' && !lastM.built && !lastM.stale ? '계획을 고칠 점을 말하면 다시 짜요 — 예: 그래프를 하나 더'
            : deepTg ? '이 꼭지를 고칠 점을 말하면 그 꼭지만 다시 써요 — 예: 더 자세히 · 표로 바꿔 줘' : '물어보세요 (Enter 보내기 · Shift+Enter 줄바꿈)')}
          onChange={e => { if (mic === 'listen') micStop.current?.(); setDraft(e.target.value) }}
          onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send() } }} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>   {/* 모델 고르기 = 입력 칸 옆(2026-10-20 사용자 — Gemini·Claude·ChatGPT처럼 묻는 자리에서) */}
          <span data-plus-menu style={{ position: 'relative' }}>
            <button data-testid="plus" style={{ ...css.ghost, padding: '2px 9px', ...(plusOpen || pickTool ? { color: '#da7756', borderColor: '#da7756' } : null) }} aria-expanded={plusOpen} onClick={() => setPlusOpen(o => !o)}
              title="도구 고르기 — 그림·아이콘·웹 검색·정리 문서·정리정돈(안 고르면 앱이 말을 보고 골라요)">＋</button>
            {plusOpen && <div role="menu" style={{ ...css.menu, minWidth: 250 }}><style>{'.mb-mi:hover:not(:disabled){background:var(--mb-seg)}'}</style>
              {tools.map(([k, label, tip]) => <button key={k} role="menuitemradio" aria-checked={pickTool === k} className="mb-mi" style={{ ...css.item, display: 'flex', flexDirection: 'column', gap: 1, whiteSpace: 'normal' }}
                onClick={() => { setPickTool(t => (t === k ? '' : k)); setPlusOpen(false) }}>
                <span>{label}{pickTool === k ? ' ✓' : ''}</span><span style={{ ...css.meta, fontWeight: 400 }}>{tip}</span></button>)}
            </div>}
          </span>
          <button data-testid="mic" onClick={toggleMic} disabled={!server || mic === 'wait' || mic === 'stopping'} aria-pressed={mic === 'listen'}
            title={mic === 'listen' ? '듣는 중 — 다시 누르면 멈춰요(보내도 멈춤)' : '말로 입력 — 말하는 동안 글자가 바로 떠요(KAIROS 실시간 받아쓰기, 말한 1분에 약 2크레딧)'}
            style={{ ...css.ghost, padding: '2px 8px', ...(mic === 'listen' ? { color: '#fff', background: '#dc2626', borderColor: '#dc2626' } : null) }}>
            {mic === 'listen' ? '● 듣는 중' : mic === 'wait' ? '🎤 …' : mic === 'stopping' ? '🎤 마무리…' : '🎤'}</button>
          <span data-testid="chat-foot-note" style={{ ...css.meta, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', ...(micErr ? { color: '#dc2626' } : null) }} title={micErr || (server ? `대화 기록은 이 칠판(「${DOC_NAME}」)에 함께 저장돼요` : '')}>{micErr || (server ? '기록은 이 칠판에 저장' : '서버가 꺼져 있어요 — python web/server.py 를 켜야 물을 수 있어요.')}</span>
          <select style={css.select} value={useModel} title="대화 답에 쓸 모델(100만 토큰당 입력 / 출력 달러) — 검색·그림·정리정돈은 앱이 일마다 알맞은 모델을 따로 고름" onChange={e => { setModel(e.target.value); try { localStorage.setItem(MODEL_KEY, e.target.value) } catch { /* 기억 못 해도 그만 */ } }}>
            {!Object.values(feat).some(rows => rows.some(m => m.id === useModel)) && <option value={useModel}>기본 · {useModel}</option>}
            {Object.entries(feat).filter(([, rows]) => rows.length).map(([v, rows]) => (
              <optgroup key={v} label={VENDOR[v] || v}>
                {rows.map(m => <option key={m.id} value={m.id}>{m.id === models.default ? '기본 · ' : ''}{m.id}{m.price ? `  ${m.price}` : ''}</option>)}
              </optgroup>))}
          </select>
        </div>
      </div>
    </aside>
  )
}
