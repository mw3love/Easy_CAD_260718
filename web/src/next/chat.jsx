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
import { answerTable, contextText, iconName, inlineParts, parseAnswer } from '../chatFormat.js'
import { CHART_KINDS, chartChoices } from './chart.js'
import { CHART_ICONS } from './props.jsx'
import { urlSpans } from './geom.js'
import { MONO_FONT } from './render.jsx'
import { siteOf } from './webcard.js'
import { getKairosKey, KEY_RE, keyHeaders, setKairosKey } from './kairosKey.js'
import { startMic } from './mic.js'
import { svgPreview } from './svgin.js'
import { Confirm, hoverBg, isPhone, useModalDialog } from './ui.jsx'
import { Composer } from './composer.jsx'
import ICONS from './icons.json' with { type: 'json' }
import { DeepAsk, SlidesPlan, askBrief, keptSlides, nextPic, picOf } from './deepchat.jsx'
import { LIVE_CSP, LIVE_H, LIVE_W, bigPage, liveSrc } from './livecard.js'
import { checkCard, problemLines } from './cardcheck.js'
import { measureDoc } from './docfix.js'
import { ChatSkeleton } from './skeleton.jsx'
const LINK_CHAT = 'var(--mb-link)'   // 밝은 화면 #4f8fe8은 흰 바탕 3.27 — 글자라 4.5 이상으로(2026-11-09 점검)
// 정리 문서 크게 보기 — 새 탭에 그 HTML(인쇄·PDF는 그 탭에서 Ctrl+P)
// 크게 보기 = 칠판 「크게 보기」와 같은 페이지(livecard.js `bigPage` — 앱 주소 blob이라 그 페이지엔 스크립트 없음, 움직이는 카드는 그 안 틀에서만)
const openHtml = (html, live = false) => { const u = URL.createObjectURL(new Blob([bigPage({ type: 'doc', live, html })], { type: 'text/html;charset=utf-8' })); window.open(u, '_blank'); setTimeout(() => URL.revokeObjectURL(u), 60_000) }
// 답 종류 — [표시, 표시 꾸밈] — 서버가 고른 길(판단 모델 jev + 규칙, `easycad/ai/route.py`)을 답 위에 보이기만.
// 옛 「다시 ▾」(다른 종류로 다시 묻기)는 2026-10-20 없앰(사용자: 대화창 하나로 다 — 길은 앱이 고르고, 틀리면 말로 다시)
const KINDS = {
  motion: ['▶ 움직이는 장', { color: 'var(--mb-accent)' }],   // 계획 ⑤
  chat: ['💬 대화', null],
  search: ['🔎 웹 검색', { color: 'light-dark(#1d4ed8, #7cb7ff)', background: 'rgba(47,128,237,.12)' }],
  board: ['📌 칠판에서', { color: 'light-dark(#b45309, #fbbf24)', background: 'rgba(245,158,11,.14)' }],
  report: ['📄 문서', { color: 'light-dark(#6d28d9, #c4b5fd)', background: 'rgba(124,58,237,.12)' }],
  tidy: ['🧩 정리정돈', { color: 'light-dark(#0f766e, #5eead4)', background: 'rgba(15,118,110,.12)' }],   // 옛 기록 표시만(정리정돈은 2026-10-25 뺐다)
  image: ['🎨 이미지', { color: 'light-dark(#7e22ce, #d8b4fe)', background: 'rgba(147,51,234,.12)' }],
  icon: ['✏️ 아이콘 (SVG)', { color: 'light-dark(#0e7490, #67e8f9)', background: 'rgba(14,116,144,.12)' }],
  diagram: ['🔷 도형', { color: 'light-dark(#1d4ed8, #93c5fd)', background: 'rgba(37,99,235,.10)' }],   // 상자 + 붙은 화살표(2026-11-03 — flowboard.js)
  live: ['▶ 인터랙티브 HTML', { color: 'light-dark(#9a3f1e, #fdba74)', background: 'rgba(218,119,86,.14)' }],   // 원리를 직접 만져 보는 카드(§8 항목66 4단계)   // 선을 고칠 수 있는 도형(§8 항목63)
  ask: ['❓ 확인', { color: 'var(--mb-accent)', background: 'rgba(218,119,86,.12)' }],   // 되묻기(§8 항목64) — 만들기 전에 버튼으로
  deep: ['📰 취재 한 판', { color: 'light-dark(#9a3f1e, #fdba74)', background: 'rgba(180,83,47,.12)' }],
  slides: ['📽 슬라이드', { color: 'light-dark(#1d4ed8, #93c5fd)', background: 'rgba(29,78,216,.10)' }],   // 프레임 여러 장(§8 항목69) — 질문지·장 계획 카드   // 한 주제 한 판(§8 항목66) — 질문지·지면 계획 카드(deepchat.jsx)
}
// 되묻기 버튼 — [이름, 설명]. 서버가 애매하고 비싼 갈림길에서만 길 둘을 보냄(`easycad/ai/route.py` `decide`)
const ASK_LABEL = { image: ['🎨 이미지로', '사진·일러스트 같은 그림'], icon: ['✏️ 아이콘(SVG)으로', '선으로 된 도형 — 칠판에서 고칠 수 있어요'],
  report: ['📄 문서로', '인쇄할 수 있는 문서 한 장'], chat: ['💬 글로 바로 답하기', '대화창에 글로'],
  search: ['🔎 웹 검색으로', '최신 정보 + 출처'], board: ['📌 칠판에서 찾기', '이 칠판에 적어 둔 것에서'] }
// 고른 답 기억(이 브라우저만 — 편의) — { 갈림길: [최근 고른 길 둘] }, 같은 길을 두 번 연달아 고르면 다음부터 안 물음(서버 `ask_pref`)
const ASK_KEY = 'magic-board-ask'
const askMemo = () => { try { return JSON.parse(localStorage.getItem(ASK_KEY) || '{}') || {} } catch { return {} } }
const askPrefs = () => Object.fromEntries(Object.entries(askMemo()).filter(([, v]) => Array.isArray(v) && v.length >= 2 && v.at(-1) === v.at(-2)).map(([k, v]) => [k, v.at(-1)]))
const rememberAsk = (key, kind) => { try { const m = askMemo(); m[key] = [...(m[key] || []), kind].slice(-2); localStorage.setItem(ASK_KEY, JSON.stringify(m)) } catch { /* 기억 못 해도 그만 */ } }
// 기다리는 동안 보일 말 — 일마다 실제로 일하는 모델(서버 /api/models `jobs`)을 같이(2026-10-20 사용자: 정돈인데 고른 gpt가 보여 헷갈림, 칠판엔 아무 표시가 없어 안 되는 줄 알았음)
const JOB_LABEL = { motion: '▶ 장을 움직이게 만드는 중(3~4분)', 'motion-check': '▶ 만든 장을 확인하는 중', 'motion-fix': '▶ 장의 잘린 곳을 고치는 중(1~4분)', 'live-fix': '▶ 잘린 글자를 고치는 중', 'slides-plan': '📽 장 계획 짜는 중', 'slides-build': '📽 슬라이드 만드는 중', live: '▶ 인터랙티브 HTML 만드는 중', report: '📄 문서 만드는 중', 'doc-fix': '📄 잘린 곳 고치는 중', image: '🎨 이미지 그리는 중', icon: '✏️ 아이콘(SVG) 그리는 중', diagram: '🔷 도형 그리는 중', 'deep-plan': '📰 지면 계획 짜는 중', 'deep-build': '📰 취재 한 판 만드는 중', 'deep-section': '📰 꼭지 다시 쓰는 중', search: '🔎 웹 검색 중', board: '📌 칠판에서 찾는 중' }
// 「+」 도구 창은 2026-11-08에 없앰(대화창 bakeoff 3라운드 사용자 — 「모두 채팅창으로 녹여 버리자」). 길은 말로만: 서버 길 고르기가 KAIROS 기능 표(`easycad/ai/features.py`)에서
// 고르고, 발표 자료·인포그래픽처럼 질문지가 먼저인 길은 서버가 `kind: 'go'`로 알려 대화창이 질문지를 띄움. 파일 올리기는 입력 칸 옆 📎
const CUT_MORE = '끊긴 곳부터 이어서 계속 써 줘. 앞 내용은 되풀이하지 말고 끊긴 문장부터.'   // 끊긴 답 「이어서 쓰기」(2026-10-27)
const EMPTY_ASK = { report: '정리해 줘' }   // 이름표만 두고 빈 칸으로 보내면
const BOARD_JOBS = new Set(['motion', 'report', 'slides-build'])   // 칠판을 바꾸거나 칠판 자료로 만드는 일 — 칠판 위에도 알약(main `aiBusy`)
// 도는 동그라미(칠판 알약·대화창 「생각 중」 공용)
export const Spinner = () => <><style>{'@keyframes mb-spin{to{transform:rotate(360deg)}}'}</style>
  <span style={{ display: 'inline-block', flex: 'none', width: 11, height: 11, borderRadius: '50%', border: '2px solid #da7756', borderTopColor: 'transparent', animation: 'mb-spin .8s linear infinite' }} /></>

// 딥모드 요약 그림(2026-10-25) — 서버가 준 주소(`body.img`)를 받아 칠판 그림 칸(PNG base64 `data`)으로, 크기는 실제 그림에서. 못 받으면 그 꼭지만 안내 메모(`error`)
async function deepImgs(secs) {
  return Promise.all((secs || []).map(async s => {
    const b = s.body || {}; if (!b.img || b.data) return s
    try {
      const im = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = b.img })
      const cv = document.createElement('canvas'); cv.width = im.naturalWidth; cv.height = im.naturalHeight; cv.getContext('2d').drawImage(im, 0, 0)
      return { ...s, body: { ...b, data: cv.toDataURL('image/png').split(',')[1], w: im.naturalWidth, h: im.naturalHeight } }
    } catch { return { ...s, body: { ...b, error: '그림 파일을 못 받았어요' } } }
  }))
}

// 칠판 그림 → 보낼 크기(긴 변 1536px JPEG) — 칠판 그림은 PNG 몇 MB라 그대로면 요청이 무거움(KAIROS 본문 상한 25MB)
export async function shrinkImage(src) {
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
const PICKS_KEY = 'magic-board-models'  // 「모델 설정」 — 일마다 고른 모델 {일: id}(없으면 자동, 2026-10-26)
// 「모델 설정」 칸 — 고를 의미가 있는 일만(2026-10-26 사용자 선택). 길 고르기·검색·받아쓰기·찾기·글 읽기는 늘 자동. [일, 이름, 종류(서버 choices), 서버 jobs 이름]
// 2026-11-04 사용자(「항목이 너무 많음」) — 8칸 → 넷: 칸 하나 = 서버 일 여럿(`PICK_GROUPS`). 자동이면 일마다 지금처럼 따로, 고르면 묶음 전부 그 모델
const PICK_ROWS = [['chat', '대화 · 회의 요약', 'llm'], ['image', '이미지', 'image'], ['make', '만들기 — 정리 문서 · 슬라이드', 'llm'], ['draw', '그리기 — 아이콘 · 도형 · 인터랙티브 HTML', 'llm']]
const PICK_GROUPS = { make: ['report', 'slides'], draw: ['icon', 'diagram', 'live'] }   // 칸 → 서버 일(server `PICK_JOBS`)
const pickOf = job => Object.keys(PICK_GROUPS).find(g => PICK_GROUPS[g].includes(job)) || job   // 서버 일 → 그 일의 칸
const sendPicks = p => Object.fromEntries(Object.entries(p).flatMap(([k, v]) => (PICK_GROUPS[k] || [k]).map(j => [j, v])))   // 칸 → 서버가 아는 일 이름으로 펼침
const JOB_PICK = { 'slides-plan': 'slides', 'slides-build': 'slides' }   // 기다리는 일 → 그 일의 서버 일 이름
const F = "'Pretendard', sans-serif"
const DONE = '#16a34a'   // 칠판에 붙임(끝남) = 초록 — 코랄은 할 수 있는 일 버튼(2026-10-20 사용자)
const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', bar: 'var(--mb-bar)', seg: 'var(--mb-seg)' }
// 입력부 아이콘(2026-11-09 — 이모지 📎·🎤 대신): 마이크 = 앱 손그림, 클립은 세트에 없어 같은 선 굵기 1.6으로
const CLIP = '<svg viewBox="0 0 24 24"><path d="M20 11.5 12.6 19a4.8 4.8 0 0 1-6.8-6.8l7.9-7.9a3.2 3.2 0 0 1 4.5 4.5l-7.9 7.9a1.6 1.6 0 0 1-2.3-2.3l7.2-7.2" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
const Glyph = ({ svg, s = 18 }) => <span aria-hidden="true" style={{ width: s, height: s, display: 'inline-block', flex: 'none' }} dangerouslySetInnerHTML={{ __html: svg.replace('<svg ', `<svg width="${s}" height="${s}" `) }} />
const css = {
  float: { position: 'absolute', right: 12, top: 12, bottom: 12, zIndex: 5, maxWidth: 'calc(100% - 24px)', border: `1px solid ${C.line}`, borderRadius: 10, overflow: 'hidden', boxShadow: '0 4px 16px rgba(0,0,0,.12)' },
  panel: { width: CHAT_W, flex: 'none', position: 'relative', display: 'flex', flexDirection: 'column', background: C.bar, borderLeft: `1px solid ${C.line}`, font: `400 13.5px/1.55 ${F}`, color: C.ink, minHeight: 0 },
  head: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, padding: '10px 12px', borderBottom: `1px solid ${C.line}` },
  msgs: { flex: 1, overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 10 },
  me: { alignSelf: 'flex-end', maxWidth: '92%', background: C.seg, borderRadius: 10, padding: '7px 10px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' },
  ai: { alignSelf: 'stretch', background: C.card, border: `1px solid ${C.line}`, borderRadius: 10, padding: '8px 10px', wordBreak: 'break-word' },
  err: { alignSelf: 'stretch', background: '#fff7ed', border: '1px solid #fdba74', color: '#9a3412', borderRadius: 10, padding: '8px 10px' },
  meta: { font: `400 11px ${F}`, color: C.muted },
  ctx: { display: 'block', font: `500 11px ${F}`, color: LINK_CHAT, marginBottom: 2 },
  bigNav: { font: `600 13px ${F}`, color: '#fff', background: 'rgba(255,255,255,.14)', border: '1px solid rgba(255,255,255,.3)', borderRadius: 7, padding: '6px 12px', cursor: 'pointer' },
  done: { font: `700 12px ${F}`, color: 'light-dark(#166534, #4ade80)', background: 'rgba(22,163,74,.1)', border: `1px solid ${DONE}`, borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  pin: { font: `700 12px ${F}`, color: 'var(--mb-accent)', background: 'transparent', border: '1px solid #da7756', borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  ghost: { font: `500 12px ${F}`, color: C.muted, background: 'transparent', border: `1px solid ${C.line}`, borderRadius: 6, padding: '2px 9px', cursor: 'pointer' },
  foot: { borderTop: `1px solid ${C.line}`, padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: 6 },
  chip: { alignSelf: 'flex-start', font: `500 11.5px ${F}`, color: LINK_CHAT, background: 'rgba(90,169,255,.15)', borderRadius: 99, padding: '2px 9px' },
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
      <iframe srcDoc={liveSrc(m.html)} title={m.title || '인터랙티브 HTML'} sandbox="allow-scripts" csp={LIVE_CSP} scrolling="no"
        style={{ border: 0, width: LIVE_W, height: LIVE_H, transform: `scale(${k})`, transformOrigin: '0 0', display: 'block', background: '#fff' }} />
    </div>
    <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}><button style={css.ghost} onClick={() => openHtml(m.html, true)}>크게 보기</button>
      <span style={{ ...css.meta, alignSelf: 'center' }}>여기서 바로 만져 보세요 · 고칠 점을 이어서 말하면 이 카드를 고쳐요</span></div>
  </div>
}

// 문서 미리보기 — 문서 폭(w)을 칸 폭에 맞춰 줄임, 누르기·Enter = 크게 보기 · 인쇄(2026-11-09 점검 — 폭을 325로 고정해 기본 폭에서 오른쪽이 잘렸음)
function DocThumb({ html, title, w = 794, h, tip, name, open }) {
  const box = useRef(null), [k, setK] = useState(0)
  useEffect(() => { const el = box.current; if (!el) return; const fit = () => setK(el.clientWidth / w); fit(); const ro = new ResizeObserver(fit); ro.observe(el); return () => ro.disconnect() }, [w])
  return <div ref={box} role="button" tabIndex={0} aria-label={name} title={tip} onClick={open} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); open() } }}
    style={{ height: h, overflow: 'hidden', border: `1px solid ${C.line}`, borderRadius: 8, background: '#fff', cursor: 'zoom-in' }}>
    {k > 0 && <iframe srcDoc={html} tabIndex={-1} title={title} sandbox="" scrolling="no" style={{ border: 0, width: w, height: h / k, transform: `scale(${k})`, transformOrigin: '0 0', pointerEvents: 'none' }} />}
  </div>
}

// 그림 크게 보기 = 진짜 창(2026-11-09 점검 — 초점이 뒤에 남아 Tab이 칠판으로 갔음). 처음 초점 = 창 자신(Enter = 추가·←→ = 후보는 창 글쇠가 맡음)
function BigModal({ onClose, children }) {
  const dlg = useRef(null)
  useModalDialog(dlg, undefined, d => d.focus())
  return <dialog ref={dlg} tabIndex={-1} className="mb-dlg" aria-label="그림 크게 보기" data-testid="image-big" onCancel={e => e.preventDefault() /* Esc는 창 글쇠가 닫음 */} onPointerDown={e => e.stopPropagation()} onClick={onClose}
    style={{ position: 'fixed', inset: 0, width: '100%', height: '100%', maxWidth: 'none', maxHeight: 'none', margin: 0, border: 0, outline: 'none', background: 'rgba(0,0,0,.72)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, padding: 24, boxSizing: 'border-box' }}>{children}</dialog>
}

function AddBtn({ done, onClick, big, testid }) {
  const [h, setH] = useState(false), [down, setDown] = useState(false)
  const bg = done ? DONE : big ? (h ? '#c4613f' : 'var(--mb-accent)') : h ? 'var(--mb-accent)' : 'rgba(17,17,17,.62)'   // 크게 보기 창에선 처음부터 코랄(그 창의 할 일)
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
export function ChatPanel({ ed, selKey, floating, full, onClose, request, focus, onBusy, width = CHAT_W, setWidth, fromTop = false }) {   // fromTop = 처음 읽은 대화를 첫 질문부터(예시 칠판 — 2026-11-03 UX 검토: 긴 딥모드 대화 끝 카드 중간부터 보였음)   // width·setWidth = 폭(왼쪽 경계 끌기 — main.jsx가 이 브라우저에 기억)   // onBusy(글) = 칠판 위 알약(정리 문서·딥모드 중에만, 끝나면 '')   // focus = { id, tool } — 빈 칠판 안내가 입력 칸으로(그 길 이름표까지, 2026-10-26)
  const [busyJob, setBusyJob] = useState('')   // 기다리는 일의 종류(모르면 '' = 서버가 짐작)   // request = { id, text, kind } — 칠판에서 시킨 질문(바뀔 때마다 한 번 보냄)   // floating = 좁은 창 — 칠판 위에 뜬 카드(2026-10-19)
  const [msgs, setMsgs] = useState([]), [loaded, setLoaded] = useState(false), [draft, setDraft] = useState(''), [busy, setBusy] = useState(null)
  const [, tick] = useState(0), [models, setModels] = useState(null), [server, setServer] = useState(true), [gone, setGone] = useState({})
  const needKey = !!models?.need_key   // 서버 키를 끈 서버(`--no-server-key`) + 내 키 없음 — 모델 목록부터 「키 필요」로 옴
  const [model, setModel] = useState(() => { try { return localStorage.getItem(MODEL_KEY) || '' } catch { return '' } })
  const [picks, setPicksState] = useState(() => { try { const old = JSON.parse(localStorage.getItem(PICKS_KEY) || '{}') || {}   // 옛 기억(일마다 따로) → 칸으로(묶음 안 첫 값)
    return Object.fromEntries(Object.entries(old).map(([k, v]) => [pickOf(k), v]).reverse()) } catch { return {} } }), [cfgOpen, setCfgOpen] = useState(false)
  const setPick = (job, id) => {
    if (job === 'chat') { setModel(id); try { id ? localStorage.setItem(MODEL_KEY, id) : localStorage.removeItem(MODEL_KEY) } catch { /* 기억 못 해도 그만 */ } return }
    setPicksState(cur => { const next = { ...cur }; if (id) next[job] = id; else delete next[job]; try { localStorage.setItem(PICKS_KEY, JSON.stringify(next)) } catch { /* 기억 못 해도 그만 */ } return next })
  }
  const box = useRef(null)
  const [past, setPastState] = useState([]), pastRef = useRef([]), [pastOpen, setPastOpen] = useState(false)   // 지난 대화(새것부터)
  const setPast = p => { pastRef.current = p; setPastState(p) }
  const [keyDel, setKeyDel] = useState(false), [keyOpen, setKeyOpen] = useState(false), [keyDraft, setKeyDraft] = useState(''), [myKey, setMyKey] = useState(() => !!getKairosKey())   // 내 KAIROS 키 칸
  useEffect(() => { if (!myKey && msgs.at(-1)?.role === 'error' && msgs.at(-1).content.startsWith('🔑')) setKeyOpen(true) }, [msgs])   // eslint-disable-line react-hooks/exhaustive-deps — 서버 키를 끈 서버(`need_key`)에서 물으면 키 칸을 바로 엶
  // 방금 칠판에 붙인 것은 어디 붙었나 보이게 고른 채로 남는데, 그대로 다음 질문에 실려 갔음(2026-10-19 점검) — 고름이 그대로인 동안은 안 실음
  const [skipSel, setSkipSel] = useState('')
  const sel = selKey && selKey === skipSel ? [] : ed.current?.selTexts() || []   // eslint-disable-line react-hooks/exhaustive-deps
  const selImgs = selKey && selKey === skipSel ? [] : ed.current?.selImages?.() || []   // 고른 것 속 그림(data: 주소)
  const selN = selKey && selKey === skipSel ? 0 : ed.current?.getSel?.()?.length || 0   // 같이 실리는 것이 있을 때만 칩
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
      else if (e.key === 'Enter' && e.target.tagName !== 'BUTTON') pinPick(big.i, big.j)   // 단추(‹ ›·닫기)에서 Enter는 그 단추 몫
      else return
      e.preventDefault(); e.stopPropagation()
    }
    window.addEventListener('keydown', key, true); return () => window.removeEventListener('keydown', key, true)
  }, [big, msgs])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetch(LOG_URL, { cache: 'no-store' }).then(r => (r.status === 404 ? { messages: [] } : r.ok ? r.json() : Promise.reject(r)))
      .then(d => { logRev.current = d.rev || 0; setMsgs(d.messages || []); setPast(Array.isArray(d.past) ? d.past : []); curBranch.current = !!d.branch; setLoaded(true) }).catch(() => { setServer(false); setLoaded(true) })
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
  const topOnce = useRef(fromTop)
  useEffect(() => { if (!box.current) return; if (topOnce.current && msgs.length) { topOnce.current = false; box.current.scrollTop = 0; return } box.current.scrollTop = box.current.scrollHeight }, [msgs.length, busy])
  const asked = useRef(null)
  useEffect(() => { if (!request || !loaded || asked.current === request.id) return; asked.current = request.id; send(request.text, request.kind, null, request.extra || {}) }, [request, loaded])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!busy) return; const t = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(t) }, [busy])

  const useModel = model || models?.default || 'gpt-6.1-sol'
  const featCost = k => { const c = models?.features?.find(f => f.kind === k)?.credits; return c ? (c[0] === c[1] ? `약 ${c[0]}크레딧` : `약 ${c[0]}~${c[1]}크레딧`) : '' }   // KAIROS 기능 표 어림(서버 `features.py`)
  const curBranch = useRef(false)   // 지금 대화가 다른 대화에서 갈라져 나왔나(지난 대화 목록 제목 앞 ⑂)
  // 저장 = 읽은 판 번호(base)와 함께, 한 번에 하나씩 — 그사이 다른 창이 저장했으면 서버가 그 대화를 「지난 대화」로 옮겨 두고 알려 줌(2026-10-26 점검: 나중 저장이 통째로 덮었음)
  const logRev = useRef(null), saveQ = useRef(Promise.resolve())
  const save = (next, given) => { const branch = curBranch.current
    saveQ.current = saveQ.current.then(() => { const p = given || pastRef.current   // 지난 대화는 보낼 때 읽음(앞 저장이 옮겨 받은 것까지)
      return fetch(LOG_URL, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ messages: next, ...(p.length ? { past: p } : {}), ...(branch ? { branch: true } : {}), base: logRev.current }) }) })
      .then(async r => { setServer(r.ok); const d = r.ok ? await r.json().catch(() => ({})) : {}; if (typeof d.rev === 'number') logRev.current = d.rev
        if (d.moved > 0) { const g = await fetch(LOG_URL, { cache: 'no-store' }).then(x => x.json()).catch(() => null); if (Array.isArray(g?.past)) setPast(g.past) } })
      .catch(() => setServer(false)) }
  const update = next => { setMsgs(next); save(next) }

  // 묻기 — history = 지금까지(마지막이 질문), kind = 'search'·'chat'(비면 서버가 짐작) → 답 한 차례
  // extra = 대화 기록엔 안 남기고 이번 요청에만 실을 것(칠판에서 고른 그림 data: 주소 — 기록이 그림으로 불지 않게)
  // 기다리는 답 끊기(2026-10-26 점검 — 답이 멈추면 새로고침밖에 없었음). 서버가 이미 시작한 KAIROS 일은 끝까지 가서 크레딧이 들 수 있음
  const stopRef = useRef(null)
  const chatPost = body => { const ac = new AbortController(); stopRef.current = ac
    return fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() }, body: JSON.stringify(body), signal: ac.signal })
      .catch(e => { throw e.name === 'AbortError' ? new Error('취소했어요 — 서버에서 이미 시작한 일은 끝까지 가서 크레딧이 들 수 있어요') : e }) }
  async function ask(history, kind = '', prevHtml = '', extra0 = {}) {   // prevHtml = 바로 앞 답이 정리 문서면 그 HTML(「더 짧게」 = 그 문서 고치기 — 서버가 판단)
    const { flow_into: flowInto = '', ...extra } = extra0   // 이어 고칠 도형 프레임(서버엔 안 보냄 — 설계서만 `base_flow`로)
    const q = history.filter(m => m.role === 'user').at(-1)?.content || ''
    const prefs = kind ? {} : askPrefs()
    const r = await chatPost({ model: useModel, board: DOC_NAME, ...(Object.keys(picks).length ? { models: sendPicks(picks) } : {}), ...(kind ? { kind } : {}), ...(Object.keys(prefs).length ? { ask_pref: prefs } : {}), ...(prevHtml ? { prev_html: prevHtml } : {}), ...(history.at(-1)?.infographic ? { infographic: true } : {}), ...(history.at(-1)?.base_image ? { base_image: history.at(-1).base_image } : {}), ...(history.at(-1)?.base_svg ? { base_svg: history.at(-1).base_svg } : {}), ...extra, messages: history.map(({ role, content, context }) => ({ role, content, ...(context ? { context } : {}) })) })
    const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
    if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
    if (d.kind === 'go') return { kind: 'go', to: d.to }   // 질문지가 먼저인 길(발표 자료·인포그래픽) — 서버는 아무것도 안 만듦, send가 그 질문지로
    const fb = d.kind === 'diagram' && d.place ? ed.current?.flowBoard?.({ spec: d.spec, place: d.place }, d.fixed ? flowInto : '') : null   // 🔷 도형 = 받자마자 칠판에(데스크톱 원칙 — 만들면 바로 넣고 아니면 Del)
    return { role: 'assistant', content: d.content, model: d.model, ...(d.swap ? { swap: d.swap } : {}), ...(d.cut ? { cut: true } : {}),   // cut = 길이 상한에 걸려 끊김(2026-10-27)
      at: Date.now(), elapsed: d.elapsed, kind: d.kind || 'chat', ...(d.sources?.length ? { sources: d.sources } : {}), ...(d.refs?.length ? { refs: d.refs } : {}),
      ...(d.images?.length ? { images: d.images, prompt: d.caption || history.filter(m => m.role === 'user').at(-1)?.content || '' } : {}),
      ...(d.svgs?.length ? { svgs: d.svgs, prompt: history.filter(m => m.role === 'user').at(-1)?.content || '' } : {}), ...(d.credits != null ? { credits: d.credits } : {}),
      ...(d.kind === 'diagram' && d.place ? { flow: d.spec, place: d.place, flowId: fb?.id || '' } : {}),   // caption = 이어 고친 그림이면 처음 요청(서버)
      ...(d.html ? { html: d.html, title: d.title || (d.kind === 'live' ? '인터랙티브 HTML' : '문서') } : {}), ...(d.kind === 'report' && d.page_w && !(d.docs?.length > 1) ? { page_w: d.page_w } : {}), ...(d.kind === 'report' && d.docs?.length ? (d.docs.length > 1 ? { docs: d.docs.map(({ style, label, html, title }) => ({ style, label, html, title })) } : { style: d.docs[0].style }) : {}),   /* 정리 문서 두 장(발표용·읽기용, 2026-11-05) */ ...(d.kind === 'ask' ? { choices: d.choices || [], askKey: d.key || '' } : {}),
      ...(d.remembered ? { askKey: d.remembered.key, alt: (d.remembered.choices || []).filter(k => k !== d.kind) } : {}) }   // 기억으로 고른 답 — 「다른 쪽으로」 버튼
  }
  // 🎤 실시간 받아쓰기(2026-10-20) — 말하는 동안 입력 칸에 글자가 쌓임(누르기 전 글 뒤에), 다시 누르거나 보내면 멈춤. 직접 치면 멈춤
  const [mic, setMic] = useState('off'), [micErr, setMicErr] = useState(''), micStop = useRef(null), micBase = useRef('')
  async function toggleMic() {
    if (mic !== 'off') { micStop.current?.(); return }
    setMicErr(''); setMic('wait'); micBase.current = draft
    const join = t => { const b = micBase.current; return b && t && !/\s$/.test(b) ? `${b} ${t}` : b + t }
    try {
      micStop.current = await startMic({ headers: keyHeaders(), onText: (fin, non) => setDraft(join(fin + non)), onState: setMic, onError: setMicErr, onWarn: setMicErr })
    } catch (e) { setMic('off'); setMicErr(e.message || String(e)) }
  }
  useEffect(() => () => micStop.current?.(), [])

  async function send(text = null, kind = '', from = null, opts = {}) {   // opts = 밖에서 시킨 일의 덧붙임(「이 장 움직이게」 = { frame })   // text·kind = 밖에서 시킨 질문(칠판 우클릭 「정리 문서 만들기」 — 입구는 대화창 하나), from = 「그림으로도」(정리 문서와 같은 자료)
    if (text != null && kind === 'slides') { if (!busy) slidesSend(kind, text); return }   // 칠판 우클릭 「발표 자료 만들기」 = 그 자료로 질문지부터
    if (text != null && kind === 'motion') { if (!busy) motionSend(text, opts.frame); return }   // 칠판 우클릭 「이 장 움직이게」(계획 ⑤)   // 칠판 우클릭 「정리 › 한 판으로」 = 칠판 자료로 딥모드 질문지(2026-11-08)
    if (text == null && !busy && (deepSend(kind) || slidesSend(kind))) return
    const pend = text == null && !from && replyTo == null ? msgs.findLastIndex(m => m.role !== 'error') : -1
    if (pend >= 0 && msgs[pend].kind === 'ask' && draft.trim() && !busy) return choose(pend, kind, draft.trim())   // 되묻기에 글로 답함(§8 항목64)
    const q = (text ?? draft).trim() || (text == null ? EMPTY_ASK[kind] || '' : ''); if (!q || busy) return
    if (text == null && mic !== 'off') micStop.current?.()   // 말하다 보내면 받아쓰기도 멈춤(지금까지 글로 보냄)
    const ctx = from ? from.context || '' : contextText(sel), n = from ? from.ctxCount : sel.length
    // ↩ 이어 묻기(2026-10-20 사용자 — 특정 답을 토대로) = 그 답까지만 앞 대화로 보냄(화면 기록엔 맨 끝에 쌓임, 무엇에 이었는지 표시)
    const ri = replyTo == null ? -1 : msgs.findIndex(m => m.at === replyTo)
    const before = (ri >= 0 ? msgs.slice(0, ri + 1) : msgs).filter(m => m.role !== 'error' && m.kind !== 'ask' && m.kind !== 'deep' && !m.deep && m.kind !== 'slides' && !m.slides)   // 답 안 한 되묻기·딥모드·발표 자료 카드는 앞 대화에 안 실음
    // 바로 앞(또는 이어 묻는) 답이 그림 후보면 고칠 그림 — 「두 번째」라 하면 둘째, 아니면 칠판에 마지막으로 붙인 것, 없으면 첫째(서버가 원본 유지 고치기 — input_images, 2026-10-20 사용자)
    const fresh = text != null && kind === 'report'   // 칠판 우클릭 「정리 › 문서로」 = 고른 재료로 늘 새 문서(대화 마지막 답이 옛 정리 문서여도 그걸 고쳐 쓰지 않음 — 2026-11-08 비교에서 겪음)
    const lastA = before.at(-1), ims = lastA?.role === 'assistant' ? lastA.images || [] : []
    const pick = /두\s*번째|둘째|2\s*번째?|오른쪽/.test(q) ? 1 : /첫\s*번째|첫째|1\s*번째?|왼쪽/.test(q) ? 0 : lastA?.picked?.at(-1) ?? 0
    const base = ims[Math.min(pick, ims.length - 1)]?.url
    const svs = lastA?.role === 'assistant' ? lastA.svgs || [] : [], baseSvg = svs[Math.min(pick, svs.length - 1)]   // 아이콘 뒤 「선을 더 굵게」 = 고른(붙인) 아이콘 고치기 — 고칠 말인지는 서버가 봄
    const boardImgs = from || !selImgs.length ? [] : await Promise.all(selImgs.map(shrinkImage))   // 칠판에서 고른 그림 = 고칠 그림(기록엔 장수만)
    // 🔷 이어 고칠 도형 = 칠판에서 고른 도형 판, 없으면 바로 앞 도형 답의 판(지웠으면 없음) — 고칠 말인지는 서버가 봄(`board_diagram.FOLLOW_WORDS`)
    const fl = from ? null : ed.current?.flowTarget?.() || (lastA?.kind === 'diagram' && lastA.flowId ? ed.current?.flowTarget?.(lastA.flowId) : null)
    const mine = { role: 'user', content: q, at: Date.now(), ...(ctx ? { context: ctx, ctxCount: n } : {}), ...(from ? { infographic: true } : {}), ...(base ? { base_image: base } : {}), ...(baseSvg ? { base_svg: baseSvg } : {}),
      ...(ri >= 0 ? { reply_to: replyTo } : {}), ...(boardImgs.length ? { imgCount: boardImgs.length } : {}) }
    const next = [...msgs.filter(m => m.role !== 'error'), mine]
    update(next); setReplyTo(null); if (text == null) setDraft(''); setBusy(Date.now()); setBusyJob(kind || (/그려|그림|이미지|일러스트/.test(q) && !/흐름도|순서도|계통도|구성도|도면|조직도|아이콘|svg/i.test(q) ? 'image' : ''))   // 길은 서버가 고르지만 「그려 줘」면 기다리는 동안 그림 두 칸 자리(2026-11-08 「+」 이름표가 없어져 — 보이기만)
    try { const ans = await ask([...before, mine], kind, !fresh && (!kind || kind === 'report' || kind === 'live') && lastA?.role === 'assistant' && lastA.html && !lastA.docs && (kind !== 'live' || lastA.kind === 'live') ? lastA.html : '', { ...(lastA?.role === 'assistant' && lastA.style && !lastA.docs ? { prev_style: lastA.style } : {}), ...(!fresh && (!kind || kind === 'report') && lastA?.role === 'assistant' && lastA.docs ? { prev_docs: lastA.docs.map(({ style, html }) => ({ style, html })) } : {}), ...(boardImgs.length ? { board_images: boardImgs } : {}), ...(lastA?.kind === 'live' ? { prev_kind: 'live' } : {}), ...(fl?.spec ? { base_flow: fl.spec, flow_into: fl.id } : {}) })
      if (ans.kind === 'go') { setBusy(null); goTo(ans.to, q); return }   // 내 질문 = 질문지 카드의 주제(그 카드가 질문·카드를 다시 씀 — 이 질문은 대화 기록에서 바뀜)
      const done = await fixDoc(await checkLive(ans, [...before, mine]))
      if (opts.pin && (done.kind === 'report' || done.kind === 'live') && done.html && !done.docs) { const ids = ed.current?.pinCard(done); if (ids) { setSkipSel(ids.join()); done.pinned = true } }   // AI 칩 「문서」·「HTML」 = 칠판에 바로 붙임(2026-11-09)
      update([...next, done]) } catch (e) {
      setMsgs([...next, { role: 'error', content: String(e.message || e) }])   // 오류는 기록에 안 남김
    } finally { setBusy(null) }
  }
  // 딥모드(§8 항목66 3-2) — ① 「+ › 딥모드」 + 주제 = 질문지 카드(서버 안 부름) ② 「지면 계획 짜기」(입력 칸 글 = 「더」) ③ 계획 카드에서 말로 고치기 = 계획 다시 ④ 「이대로 만들기」 = 본문 → 칠판에 판.
  // 서버 길 = /api/chat `kind: 'deep'` + `deep: { step: 'ask' | 'pic', topic, brief, material? }` — 2026-11-09부터 인포그래픽(그림 한 장)만(지면 「한 판」은 뺌). 입력 칸에서 보낼 때 먼저 봄 — 맡았으면 true
  function deepSend(kind, text = null, opt = {}) {   // text = 밖에서 시킨 주제(칠판 우클릭 「한 판으로」·길 고르기 `go`), opt = { pic: 인포그래픽 질문지, brief: 미리 고른 답 }
    const li = msgs.findLastIndex(m => m.role !== 'error'), last = msgs[li], t = (text ?? draft).trim()
    if (text == null && last?.kind === 'deep' && last.step === 'ask' && !last.done) { if (!last.asking) deepGo(li, t); return true }   // 맞춤 질문 정리 중 = Enter 기다림(쓴 글은 칸에 그대로)
    if (kind !== 'deep' || !t) return false
    // 모양은 질문지에서(한 판 ↔ 여러 장) — 여러 장으로 바꿀 때 쓰게 고른 것도 붙잡아 둠(발표 자료와 같게)
    const at = Date.now(), material = contextText(sel), imgIds = selImgs.length ? ed.current?.selImageIds?.() || [] : [], k = opt.pic ? 'deep' : 'slides'
    update([...msgs.filter(m => m.role !== 'error'), { role: 'user', content: t, at, deep: true }, { role: 'assistant', kind: k, step: 'ask', topic: t, brief: opt.brief || {}, ...(opt.pic ? { pic: true } : {}),
      ...(material || imgIds.length ? { material, ctxCount: sel.length + imgIds.length } : {}), ...(imgIds.length ? { imgIds } : {}), at: at + 1 }])
    if (text == null) setDraft(''); if (mic !== 'off') micStop.current?.()
    briefAsk(at + 1, t, material, k)
    return true
  }
  // 맞춤 질문(2026-11-06) — 질문지를 띄우자마자 서버가 주제 글을 읽고 질문을 정리(몇 초 — 그동안 질문지에 「정리하는 중」, 설정은 바로 고를 수 있음).
  // 못 하면 고정 질문(`askFail`). 「생각 중」(busy)·멈춤 단추는 안 씀 — 질문지를 보며 기다리는 짧은 일이라. 화면 시험은 기본 끔(localStorage `mb-brief-ask` = off, helpers `openBoard`)
  async function briefAsk(at, topic, material, kind) {
    const patch = (p, keep = true) => setMsgs(cur => { const next = cur.map(x => (x.at === at && x.step === 'ask' ? { ...x, ...p } : x)); if (keep) save(next); return next })
    let off = false; try { off = localStorage.getItem('mb-brief-ask') === 'off' } catch { /* 못 읽으면 켬 */ }
    if (off) return
    patch({ asking: true }, false)   // 「정리하는 중」은 기록에 안 남김(새로고침하면 고정 질문)
    try {
      const r = await fetch('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json', ...keyHeaders() },
        body: JSON.stringify({ board: DOC_NAME, kind, [kind]: { step: 'ask', topic, material: material || '' }, messages: [{ role: 'user', content: topic }] }) })
      const d = await r.json().catch(() => ({}))
      if (!r.ok || d.error || !d.questions?.length) throw new Error(d.error || `서버 응답 ${r.status}`)
      patch({ asking: false, ai: { known: d.known || [], audience: d.audience || null, questions: d.questions } })
    } catch { patch({ asking: false, askFail: true }) }
  }
  const setMsg = (i, patch) => setMsgs(cur => { const next = cur.map((x, j) => (j === i ? { ...x, ...patch } : x)); save(next); return next })
  async function deepCall(body, job) {
    setBusy(Date.now()); setBusyJob(job)
    try {
      const r = await chatPost({ model: useModel, board: DOC_NAME, ...(Object.keys(picks).length ? { models: sendPicks(picks) } : {}), kind: 'deep', deep: body, messages: [{ role: 'user', content: body.topic }] })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      return d
    } catch (e) { setMsgs(cur => [...cur.filter(x => x.role !== 'error'), { role: 'error', content: String(e.message || e) }]); return null } finally { setBusy(null) }
  }
  // 움직이는 카드 검사(2026-11-08) — 보이지 않는 칸에서 돌려 글자 잘림·겹침을 잼(크레딧 없음). 문제가 있으면 한 번만 고쳐 보고(약 45크레딧) 나아졌을 때만 바꿈
  // 📄 새 문서 재기 → 잘림·넘침이 있는 블록만(최대 3개) 다시 써서 한 번 고침, 문제가 줄었을 때만 바꿈(2026-11-09 문서 통합 2단계 ④)
  async function fixDoc(ans) {
    if (ans.kind !== 'report' || !ans.html || ans.docs?.length > 1) return ans
    const probs = await measureDoc(ans.html, ans.page_w || 794); if (!probs.length) return ans
    setBusy(Date.now()); setBusyJob('doc-fix')
    let html = ans.html, credits = 0
    for (const p of probs.slice(0, 3)) {
      try {
        const r = await chatPost({ kind: 'block', board: DOC_NAME, doc: html, block: p.block, messages: [{ role: 'user', content: `이 블록에서 ${p.why}. 내용은 그대로 두고, 글자·표시가 잘리거나 칸 밖으로 나가지 않게 배치만 고쳐 줘.` }] })
        const d = await r.json().catch(() => ({})); if (r.ok && d.html) { html = d.html; credits += d.credits || 0 }
      } catch { /* 이 블록은 두고 다음 */ }
    }
    if (html === ans.html) return ans
    const after = await measureDoc(html, ans.page_w || 794)
    if (after.length >= probs.length) return ans
    return { ...ans, html, content: `${ans.content || ''}

잘린 곳 ${probs.length - after.length}곳을 고쳤어요(그 블록만 · 약 ${Math.round(credits)}크레딧)`, ...(ans.credits != null ? { credits: ans.credits + credits } : {}) }
  }
  async function checkLive(ans, history) {
    if (ans.kind !== 'live' || !ans.html) return ans
    const c = await checkCard(ans.html); if (!c?.problems.length) return ans
    const lines = problemLines(c.problems)
    setBusy(Date.now()); setBusyJob('live-fix')
    try {
      const fixed = await ask([...history, { role: 'assistant', content: ans.content }, { role: 'user', content: `화면에서 잰 아래 문제만 고쳐 줘. 나머지는 그대로.\n${lines.join('\n')}` }], 'live', ans.html, { prev_kind: 'live' })
      const c2 = fixed.html ? await checkCard(fixed.html) : null
      if (c2 && c2.problems.length < c.problems.length) return { ...fixed, content: ans.content, elapsed: ans.elapsed, autoFixed: c.problems.length - c2.problems.length, ...(c2.problems.length ? { check: problemLines(c2.problems) } : {}) }
    } catch { /* 고치기 실패 = 처음 카드 그대로 + 알림 */ }
    return { ...ans, check: lines }
  }
  // 「이 장 움직이게」(계획 ⑤, 2026-11-08) — 장 글·크기·그 장 그림(참고) → 서버 Opus(3~4분) → 그 프레임을 덮는 카드(`ed.motionPlace`). 대화엔 질문·결과 한 줄만
  async function motionSend(t, frameId) {
    const info = ed.current?.motionInfo?.(frameId); if (!info) return
    const image = info.image ? await shrinkImage(info.image).catch(() => '') : ''
    const mine = { role: 'user', content: t, at: Date.now() }, next = [...msgs.filter(m => m.role !== 'error'), mine]
    update(next); setBusy(Date.now()); setBusyJob('motion')
    try {
      const r = await chatPost({ model: useModel, board: DOC_NAME, ...(Object.keys(picks).length ? { models: sendPicks(picks) } : {}), kind: 'motion', motion: { slide: info.slide, w: info.w, h: info.h, image }, messages: [{ role: 'user', content: t }] })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      const cid = ed.current?.motionPlace?.(frameId, d)
      const done = { role: 'assistant', kind: 'motion', content: d.content, model: d.model, at: Date.now(), elapsed: d.elapsed, ...(d.credits != null ? { credits: d.credits } : {}), ...(cid ? { motionId: cid, motionFrame: frameId } : {}) }
      update([...next, done]); setBusyJob('motion-check')
      const c = await checkCard(d.html, { w: info.w, h: info.h, motion: true })   // 장은 비싸서(수백 크레딧) 고치기는 사용자가 단추로
      if (c?.problems.length) update([...next, { ...done, check: problemLines(c.problems) }])
    } catch (e) { setMsgs([...next, { role: 'error', content: String(e.message || e) }]) } finally { setBusy(null) }
  }
  async function motionFix(i) {
    const m = msgs[i], info = ed.current?.motionInfo?.(m.motionFrame), html = ed.current?.liveModel?.().items.find(it => it.motion_of === m.motionFrame)?.html
    const fail = t => setMsgs([...msgs.filter(x => x.role !== 'error'), { role: 'error', content: t }])
    if (!info || !html) { fail('움직이는 장이 지워져서 고칠 수 없어요'); return }
    setBusy(Date.now()); setBusyJob('motion-fix')
    try {
      const r = await chatPost({ model: useModel, board: DOC_NAME, ...(Object.keys(picks).length ? { models: sendPicks(picks) } : {}), kind: 'motion', motion: { slide: info.slide, w: info.w, h: info.h, image: '', fix_html: html, problems: m.check }, messages: [{ role: 'user', content: '장의 잘린 곳 고치기' }] })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      setBusyJob('motion-check')
      const c = await checkCard(d.html, { w: info.w, h: info.h, motion: true }), better = !c || c.problems.length < m.check.length   // 못 재면 사용자가 시킨 대로 바꿈
      const cid = better ? ed.current?.motionPlace?.(m.motionFrame, d) : ''
      update(msgs.map((x, j) => (j !== i ? x : { ...x, ...(cid ? { motionId: cid } : {}), fixTried: true, fixKept: !better, check: better ? (c?.problems.length ? problemLines(c.problems) : []) : x.check, credits: d.credits != null ? (x.credits || 0) + d.credits : x.credits })))
    } catch (e) { fail(String(e.message || e)) } finally { setBusy(null) }
  }
  // 길 고르기가 「질문지 먼저」라고 한 길(서버 `kind: 'go'`) — 발표 자료 = 작은 책 질문지, 인포그래픽 = 딥모드 질문지(그림 한 장으로 — 대화창에선 「한 판」 대신, 2026-11-08 사용자)
  function goTo(to, q) { if (to === 'slides') slidesSend('slides', q); else if (to === 'infographic') deepSend('deep', q, { pic: true }) }
  async function deepGo(i, more) {
    const m = msgs[i], brief = askBrief(m, more, false)
    if (more) setDraft('')
    if (m.pic) {   // 인포그래픽 = 질문지 답 + 조사 → 그림 후보 둘(서버 `deep.step: 'pic'`) — 답은 보통 그림 답처럼(후보 고르기·이어 고치기)
      const d = await deepCall({ step: 'pic', topic: m.topic, brief, material: m.material || '' }, 'image'); if (!d) return
      setMsgs(cur => { const next = [...cur.map((x, j) => (j === i ? { ...x, done: true, ...(more ? { more } : {}) } : x)), { role: 'assistant', kind: 'image', content: d.content, model: d.model, at: Date.now(), elapsed: d.elapsed,
        ...(d.sources?.length ? { sources: d.sources } : {}), ...(d.images?.length ? { images: d.images, prompt: m.topic } : {}), ...(d.credits != null ? { credits: d.credits } : {}) }]; save(next); return next })
      return
    }
    // 「한 판」 지면 계획은 2026-11-09 뺌(옛 대화 기록의 질문지 카드는 아무것도 안 함)
  }
  // 📽 발표 자료(§8 항목69, 2026-10-28) — 딥모드와 같은 걸음: 「+ › 발표 자료」 + 주제 = 질문지 카드(그때 고른 것의 글을 재료로 붙잡아 둠) → 장 계획 → 「이대로 만들기」 = 칠판에 프레임 N장(`ed.slidesBoard`)
  function slidesSend(kind, text = null) {   // text = 칠판 우클릭 「발표 자료 만들기」가 시킨 주제(3단계)
    const li = msgs.findLastIndex(m => m.role !== 'error'), last = msgs[li], t = (text ?? draft).trim()
    if (text == null && last?.kind === 'slides' && last.step === 'ask' && !last.done) { if (!last.asking) slidesGo(li, t); return true }
    if (text == null && last?.kind === 'slides' && last.step === 'plan' && !last.built && !last.stale && t && (!kind || kind === 'slides')) { slidesReplan(li, t); return true }
    if (kind !== 'slides' || !t) return false
    const at = Date.now(), material = contextText(sel), imgIds = selImgs.length ? ed.current?.selImageIds?.() || [] : []   // 고른 그림 = 이름표만 기억(서버가 칠판 파일에서 꺼내 보임 — 대화 기록이 그림으로 불지 않게, 2026-10-28)
    update([...msgs.filter(m => m.role !== 'error'), { role: 'user', content: t, at, slides: true }, { role: 'assistant', kind: 'slides', step: 'ask', topic: t, brief: {}, ...(material || imgIds.length ? { material, ctxCount: sel.length + imgIds.length } : {}), ...(imgIds.length ? { imgIds } : {}), at: at + 1 }])
    if (text == null) setDraft(''); if (mic !== 'off') micStop.current?.()
    briefAsk(at + 1, t, material, 'slides')
    return true
  }
  async function slidesCall(body, job) {
    setBusy(Date.now()); setBusyJob(job)
    try {
      const r = await chatPost({ model: useModel, board: DOC_NAME, ...(Object.keys(picks).length ? { models: sendPicks(picks) } : {}), kind: 'slides', slides: { ...body, ...(body.imgIds?.length ? { image_uids: body.imgIds } : {}), imgIds: undefined }, messages: [{ role: 'user', content: body.topic }] })
      const d = await r.json().catch(() => ({ error: `서버 응답 ${r.status}` }))
      if (!r.ok || d.error) throw new Error(d.error || `서버 응답 ${r.status}`)
      return d
    } catch (e) { setMsgs(cur => [...cur.filter(x => x.role !== 'error'), { role: 'error', content: String(e.message || e) }]); return null } finally { setBusy(null) }
  }
  const slidesPlanMsg = (m, d) => ({ role: 'assistant', kind: 'slides', step: 'plan', topic: m.topic, brief: m.brief, material: m.material, ...(m.imgIds ? { imgIds: m.imgIds } : {}), plan: d.plan, estimate: d.estimate, drop: [], model: d.model, elapsed: d.elapsed, credits: d.credits, at: Date.now() })
  async function slidesGo(i, more) {
    const m = msgs[i], brief = askBrief(m, more, true)
    if (more) setDraft('')
    const d = await slidesCall({ step: 'plan', topic: m.topic, brief, material: m.material || '', imgIds: m.imgIds }, 'slides-plan'); if (!d) return
    setMsgs(cur => { const next = [...cur.map((x, j) => (j === i ? { ...x, done: true, ...(more ? { more } : {}) } : x)), slidesPlanMsg({ ...m, brief }, d)]; save(next); return next })
  }
  async function slidesReplan(i, fix) {
    const m = msgs[i], mine = { role: 'user', content: fix, at: Date.now(), slides: true }
    setDraft(''); setMsgs(cur => [...cur, mine])
    const d = await slidesCall({ step: 'plan', topic: m.topic, brief: m.brief, material: m.material || '', imgIds: m.imgIds, prev: keptSlides(m), fix }, 'slides-plan')
    if (!d) { setMsgs(cur => cur.filter(x => x !== mine)); setDraft(fix); return }
    setMsgs(cur => { const next = [...cur.map((x, j) => (j === i ? { ...x, stale: true } : x)), slidesPlanMsg(m, d)]; save(next); return next })
  }
  async function slidesBuild(i) {
    const m = msgs[i], plan = keptSlides(m)
    const d = await slidesCall({ step: 'build', topic: m.topic, brief: m.brief, material: m.material || '', imgIds: m.imgIds, plan }, 'slides-build'); if (!d) return
    let deck = d.deck?.cover?.img ? { ...d.deck, cover: (await deepImgs([{ body: d.deck.cover }]))[0].body } : d.deck   // 표지 그림(3단계) = 칠판 그림 칸으로
    for (const f of ['pic', 'alt_pic']) if (deck?.slides?.some(s => s[f]?.img)) { const got = await deepImgs(deck.slides.map(s => ({ body: s[f] || {} })))   // 그림 장·그림 판(2026-11-04) = 칠판 그림 칸으로, 못 받으면 글 장·판 없음(`slidesBoard`)
      deck = { ...deck, slides: deck.slides.map((s, k) => (s[f] ? { ...s, [f]: got[k].body } : s)) } }
    const r = ed.current?.slidesBoard?.(deck); if (!r) return
    setMsg(i, { built: r.ids[0], frames: r.frames, nos: r.nos, model: d.model, elapsed: d.elapsed, credits: d.credits })
    ed.current?.showIds(r.ids); setSkipSel(r.ids.join())
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
    if (add) { setDraft(''); if (mic !== 'off') micStop.current?.() }
    const extra = { ...(add && !k ? { ask_add: add, ask_reply: { choices: m.choices || [], default: m.choices?.[0] || '' } } : {}) }
    const boardImgs = selImgs.length ? await Promise.all(selImgs.map(shrinkImage)) : []
    setBusy(Date.now()); setBusyJob(k)
    try { const a = await ask(sent, k, '', { ...extra, ...(boardImgs.length ? { board_images: boardImgs } : {}) }); update([...shown, a, ...msgs.slice(i + 1)]) } catch (e) {
      setMsgs([...msgs.filter(x => x.role !== 'error'), { role: 'error', content: String(e.message || e) }])
    } finally { setBusy(null) }
  }
  // 🔷 도형 답 → 칠판의 그 판으로(지웠으면 받은 자리로 다시 지음 — AI 안 부름)
  function showFlow(i) {
    const m = msgs[i]; if (m.flowId && ed.current?.showIds([m.flowId])) return
    const r = ed.current?.flowBoard?.({ spec: m.flow, place: m.place }); if (r) setMsg(i, { flowId: r.id })
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
  // 붙인 묶음 이름 = 아이콘 요청(「안테나 아이콘 그려 줘」 → 「안테나」, 2026-10-27). 고친 답(후보 하나)이면 바로 앞 아이콘 답의 요청을 거슬러 — 「선을 더 굵게」는 이름이 아님
  function iconTitle(i) {
    let k = i
    while (msgs[k].svgs?.length === 1) { let j = k - 1; while (j >= 0 && msgs[j].role !== 'assistant') j--; if (j < 0 || !msgs[j].svgs?.length) break; k = j }
    return iconName(msgs[k].prompt)
  }
  function pinSvgPick(i, j) { const ids = ed.current?.pinSvg(msgs[i].svgs[j], iconTitle(i)); if (ids) { setSkipSel(ids.join()); markPicked(i, j) } }
  function svgDown(e, i, j) {
    if (e.button !== 0) return
    dragged.current = false
    const sx = e.clientX, sy = e.clientY
    const move = ev => { if (Math.hypot(ev.clientX - sx, ev.clientY - sy) <= 6) return; done(); dragged.current = true
      ed.current?.dragSvg(msgs[i].svgs[j], ids => { setSkipSel((ids || []).join()); markPicked(i, j) }, iconTitle(i)) }
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
    try { const pv = history.at(-2), a = await ask(history, m.kind || '', m.kind === 'report' && pv?.html && !pv.docs ? pv.html : '', m.kind === 'report' && pv?.docs ? { prev_docs: pv.docs.map(({ style, html }) => ({ style, html })) } : m.kind === 'report' && pv?.style ? { prev_style: pv.style } : {}); update(msgs.map((x, j) => (j === i ? { ...a, prev: { ...m, prev: undefined } } : x))) } catch (e) {
      setMsgs([...msgs.filter(x => x.role !== 'error'), { role: 'error', content: String(e.message || e) }])
    } finally { setBusy(null) }
  }
  // 후보 「2개 더 보기」(2026-10-27 사용자) — 같은 질문(그 앞 대화까지)·같은 종류로 한 번 더 물어 이 답 후보 뒤에 덧붙임(앞 후보·고른 표시는 그대로). 새로 그린 답(후보 2개)에만, 4개까지
  const MORE_MAX = 4
  const canMore = m => (m.kind === 'image' || m.kind === 'icon') && (m.images || m.svgs || []).length >= 2 && (m.images || m.svgs).length < MORE_MAX
  async function more(i) {
    const history = msgs.slice(0, i).filter(m => m.role !== 'error'), m = msgs[i]
    if (busy || history.at(-1)?.role !== 'user' || !canMore(m)) return
    setBusy(Date.now()); setBusyJob(m.kind)
    try {
      const a = await ask(history, m.kind), key = m.kind === 'image' ? 'images' : 'svgs'
      if (!a[key]?.length) throw new Error('후보를 더 못 만들었어요')
      setMsgs(cur => { const next = cur.map(x => (x.at === m.at ? { ...x, [key]: [...x[key], ...a[key]].slice(0, MORE_MAX), ...(a.credits != null ? { credits: (x.credits || 0) + a.credits } : {}) } : x)); save(next); return next })
    } catch (e) {
      setMsgs(cur => [...cur.filter(x => x.role !== 'error'), { role: 'error', content: String(e.message || e) }])
    } finally { setBusy(null) }
  }
  // ⋯ 메뉴 글쇠(2026-11-09 점검): ↑↓ = 옮기기, Esc = 닫고 ⋯로
  const menuKeys = e => { const items = [...e.currentTarget.querySelectorAll('button:not(:disabled)')], at = items.indexOf(document.activeElement)
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); e.stopPropagation(); items[(at + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length]?.focus() }
    if (e.key === 'Escape') { e.stopPropagation(); e.currentTarget.parentElement.querySelector('[data-testid=answer-menu]')?.focus(); setMenuAt(null) } }
  const [menuAt, setMenuAt] = useState(null)   // ⋯ 메뉴를 연 답의 at
  useEffect(() => { if (!cfgOpen) return; const close = e => { if (!e.target.closest?.('[data-model-set]')) setCfgOpen(false) }; window.addEventListener('pointerdown', close, true); return () => window.removeEventListener('pointerdown', close, true) }, [cfgOpen])   // 「모델 설정」 = 바깥 누르면 닫힘
  useEffect(() => { if (menuAt == null) return; const close = e => { if (!e.target.closest?.('[data-answer-menu]')) setMenuAt(null) }; window.addEventListener('pointerdown', close, true); return () => window.removeEventListener('pointerdown', close, true) }, [menuAt])
  function saveKey(v) { setKairosKey(v.trim()); setMyKey(!!v.trim()); setKeyDraft(''); setKeyOpen(false) }
  // 정리 문서 → 같은 자료로 인포그래픽 그림 후보(2026-10-20 사용자 선택 — 그림은 보기 좋지만 숫자를 지어낼 수 있어 기본은 문서, 원하면 한 번 더)
  function drawReport(i) { const src = msgs.slice(0, i).filter(m => m.role === 'user').at(-1) || {}; send(`「${msgs[i].title || '정리 문서'}」 인포그래픽 그림`, 'image', { context: src.context, ctxCount: src.ctxCount }) }
  function retry() {
    const last = [...msgs].reverse().find(m => m.role === 'user'); if (!last) return
    setMsgs(msgs.filter(m => m.role !== 'error').slice(0, -1)); setDraft(last.content)
  }

  const jobModel = picks[pickOf(JOB_PICK[busyJob] || busyJob)] || models?.jobs?.[JOB_PICK[busyJob] || busyJob]   // 고른 모델이 있으면 그것(「모델 설정」)
  const busyLine = !busy ? '' : `${JOB_LABEL[busyJob] || (busyJob === 'chat' ? `${useModel} 생각 중` : 'KAIROS 생각 중')}${JOB_LABEL[busyJob] && (jobModel || (busyJob === 'board' ? useModel : '')) ? ` · ${jobModel || useModel}` : ''}… ${Math.round((Date.now() - busy) / 1000)}초`
  // 일을 아직 모를 때(서버가 짐작 — 「정리 문서로 만들어 줘」를 쳐서 물음)는 모델 이름을 안 씀: 고른 모델이 아닐 수 있음(2026-10-20 실화면)
  useEffect(() => { onBusy?.(busy && BOARD_JOBS.has(busyJob) ? busyLine : '') }, [busyLine])   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => onBusy?.(''), [])   // eslint-disable-line react-hooks/exhaustive-deps
  const lastM = msgs.filter(m => m.role !== 'error').at(-1)
  const canSend = !!draft.trim() || ((lastM?.kind === 'deep' || lastM?.kind === 'slides') && lastM.step === 'ask' && !lastM.done && !lastM.asking)   // 질문지 = 빈 칸 그대로 보내도 시작(Enter와 같게)
  const tool = (s => ({ all: 'unset', width: s, height: s, flex: 'none', display: 'grid', placeItems: 'center', borderRadius: 8, cursor: 'pointer', color: C.muted, boxSizing: 'border-box' }))(isPhone() ? 44 : 30)
  const ta = useRef(null)
  // 첨부(2026-10-28 사용자) — 대화창에 놓기·붙여넣기·입력 칸 옆 📎(2026-11-08 전엔 「+ › 파일 올리기…」) = 칠판 빈자리에 놓고 고른 채(`ed.attachFiles`), 자료는 칠판에 남음
  const fileIn = useRef(null), [dropIn, setDropIn] = useState(false)
  const attach = async fs => { if (fs.length) { await ed.current?.attachFiles?.(fs); ta.current?.focus() } }
  const hasFiles = e => [...(e.dataTransfer?.types || [])].includes('Files')   // 대화창 그림 후보 끌기(주소)는 아님
  const focused = useRef(null)   // 빈 칠판 안내 → 입력 칸(focus.draft = 미리 써 둘 말 — 「발표 자료 만들어 줘」처럼 길 고르기가 알아듣는 말, 2026-11-08 「+」 이름표 대신)
  useEffect(() => { if (!focus || focused.current === focus.id) return; focused.current = focus.id
    if (focus.draft) setDraft(focus.draft); ta.current?.focus() }, [focus])   // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <aside className="mb-chat" style={full ? { ...css.panel, position: 'fixed', inset: 0, zIndex: 50, width: '100%', borderLeft: 0, touchAction: 'pan-y' } : { ...(floating ? { ...css.panel, ...css.float } : css.panel), width }} aria-label="KAIROS 대화" onPointerDown={e => e.stopPropagation()}
      onDragOver={e => { if (!hasFiles(e)) return; e.preventDefault(); if (!dropIn) setDropIn(true) }}   // 막지 않으면 브라우저가 그 파일로 떠남
      onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setDropIn(false) }}
      onDrop={e => { if (!hasFiles(e)) return; e.preventDefault(); setDropIn(false); attach([...e.dataTransfer.files]) }}>
      {dropIn && <div data-testid="chat-drop" style={{ position: 'absolute', inset: 8, zIndex: 20, borderRadius: 12, border: '2px dashed #da7756', background: 'rgba(218,119,86,.08)', display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: 20, font: `600 14px/1.6 ${F}`, color: 'var(--mb-accent)', pointerEvents: 'none' }}>
        <span>여기에 놓으면 칠판 빈자리에 놓고 골라 둬요</span><span style={{ fontWeight: 400, fontSize: 12.5 }}>그림·PDF·녹음(회의록)·md·txt·HTML</span></div>}
      {/* 폭 조절 — 왼쪽 경계 끌기(320~720, 화면 절반까지), 두 번 누르면 기본 폭(왼쪽 판 `dock-resize`와 같은 손맛) */}
      {setWidth && !full && <div data-testid="chat-resize" role="separator" aria-orientation="vertical" aria-label="대화창 폭 조절" aria-valuenow={width} tabIndex={0} title="끌어서 대화창 폭 조절(글쇠 ← →) · 두 번 누르면 기본 폭" onDoubleClick={() => setWidth(CHAT_W)}
        onKeyDown={e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); e.stopPropagation(); setWidth(chatClamp(width + (e.key === 'ArrowLeft' ? 16 : -16))) } }}
        onPointerDown={e => { e.preventDefault(); const x0 = e.clientX, w0 = width, el = e.currentTarget; el.setPointerCapture(e.pointerId)
          const mv = ev => setWidth(chatClamp(w0 - (ev.clientX - x0))), up = () => { el.removeEventListener('pointermove', mv); el.removeEventListener('pointerup', up) }
          el.addEventListener('pointermove', mv); el.addEventListener('pointerup', up) }}
        style={{ position: 'absolute', top: 0, bottom: 0, left: 0, width: 6, cursor: 'col-resize', zIndex: 6 }}
        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(218,119,86,.35)' }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }} />}
      {big && msgs[big.i]?.images?.[big.j] && (() => { const m = msgs[big.i], n = m.images.length, go = d => setBig(b => ({ ...b, j: (b.j + d + n) % n }))
        return createPortal(<BigModal onClose={() => setBig(null)}>
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
          </BigModal>, document.body) })()}
      <div style={css.head}>
        <b style={{ fontSize: 14 }}>KAIROS</b>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {credits && <span data-testid="chat-credits" title={`이번 달 ${Math.round(credits.quota).toLocaleString('ko-KR')} 크레딧 중 남은 것(${myKey ? '내 키' : '서버 키'}) — 답을 받을 때마다 새로`}
            style={{ font: `500 12px ${F}`, color: credits.remaining < credits.quota * 0.1 ? 'var(--mb-accent)' : C.muted }}>남은 {Math.round(credits.remaining).toLocaleString('ko-KR')}</span>}
          <button title="대화창 닫기" aria-label={full ? undefined : '대화창 닫기'} onClick={onClose} style={{ ...css.ghost, padding: full ? '4px 12px' : '0 7px', fontSize: full ? 15 : undefined }}>{full ? '✕ 칠판' : '✕'}</button>
        </div>
      </div>
      <div style={css.bar}>   {/* 대화 관리 줄 — 새 대화 · 지난 대화 · 내 키 */}
        <button style={css.ghost} disabled={!!busy || !msgs.some(m => m.role === 'user')} onClick={newChat} title="지금 대화는 「지난 대화」로 넘기고 빈 대화로 — 앞 대화가 다음 질문에 안 실려요">＋ 새 대화</button>
        {past.length > 0 && <button style={css.ghost} disabled={!!busy} aria-expanded={pastOpen} onClick={() => setPastOpen(o => !o)} title="지난 대화를 골라 다시 열어요(지금 대화는 목록으로)">지난 대화 {past.length} ▾</button>}
        <button data-testid="key-btn" style={{ ...css.ghost, marginLeft: 'auto', ...(myKey ? { color: 'light-dark(#0f766e, #2dd4bf)', borderColor: 'light-dark(#0f766e, #2dd4bf)' } : needKey ? { color: 'var(--mb-accent)', borderColor: 'var(--mb-accent)' } : null) }} aria-expanded={keyOpen} onClick={() => setKeyOpen(o => !o)}
          title={myKey ? '내 KAIROS 키로 부르는 중 — 바꾸거나 지우기' : needKey ? '이 서버는 각자 키로만 물어요 — 내 KAIROS 키 넣기' : '내 KAIROS 키 넣기(안 넣으면 서버 PC 키)'}>🔑 {myKey ? '내 키' : needKey ? '키 넣기' : '서버 키'}</button>
      </div>
      {pastOpen && <div data-testid="past-list" style={css.drop}>
        {past.map((c, j) => <button key={c.at + ':' + j} style={css.row} onClick={() => openPast(j)} title={c.title}>
          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title || '(제목 없음)'}</span>
          <span style={css.meta}>{new Date(c.at).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })} · {c.messages.filter(m => m.role === 'user').length}문</span></button>)}
      </div>}
      {keyOpen && <div data-testid="key-box" style={{ ...css.drop, padding: 10, gap: 6 }}>
        <span style={css.meta}>내 KAIROS API 키 — 이 브라우저에만 저장되고, 물을 때만 서버로 같이 가요(서버는 남기지 않아요). {needKey ? '이 서버는 각자 키로만 물어요(한 번 넣으면 이 브라우저에 남아요).' : '비우면 서버 PC 키를 써요.'}</span>
        <div style={{ display: 'flex', gap: 6 }}>
          <input type="password" className="mb-field" aria-label="내 KAIROS 키" autoComplete="off" placeholder={myKey ? '새 키로 바꾸기' : '키 붙여넣기'} value={keyDraft} onChange={e => setKeyDraft(e.target.value)}
            onKeyDown={e => { e.stopPropagation(); if (e.key === 'Enter' && KEY_RE.test(keyDraft.trim())) saveKey(keyDraft) }} style={{ ...css.input, minHeight: 0, padding: '4px 8px', flex: 1 }} />
          <button style={css.pin} disabled={!KEY_RE.test(keyDraft.trim())} onClick={() => saveKey(keyDraft)}>저장</button>
          {myKey && <button style={css.ghost} onClick={() => setKeyDel(true)}>지우기</button>}
        </div>
      </div>}
      {keyDel && <Confirm testid="key-delete" okTestid="key-delete-ok" title="내 KAIROS 키를 지울까요?" onOk={() => saveKey('')} onClose={() => setKeyDel(false)}>이 브라우저에 저장한 키만 지워요. 다시 쓰려면 키를 다시 넣어야 해요.</Confirm>}
      <div ref={box} role="log" aria-label="대화 내용" aria-busy={!!busy} style={css.msgs}>
        {loaded && !msgs.length && <div style={{ ...css.meta, fontSize: 12.5, lineHeight: 1.6 }}>
          무엇이든 물어보세요. 남길 답은 「칠판에 붙이기」나 끌어다 놓기로 메모가 됩니다.<br />칠판에서 메모나 글을 고른 채 물으면 그 내용을 같이 보냅니다.</div>}
        {msgs.map((m, i) => m.role === 'user'
          ? <div key={i} style={css.me}>{m.addTo ? <span style={css.ctx}>위 질문에 덧붙여</span> : null}{m.reply_to ? <span style={css.ctx}>↩ 「{replyLabel(m.reply_to)}」에 이어서</span> : null}
            {m.ctxCount ? <span style={css.ctx}>칠판에서 고른 것 {m.ctxCount}개와 함께</span> : null}{m.imgCount ? <span style={css.ctx}>칠판에서 고른 그림 {m.imgCount}장과 함께</span> : null}{m.content}</div>
          : m.role === 'error'
            ? <div key={i} style={css.err}>{m.content}<div style={{ marginTop: 6, display: 'flex', gap: 6 }}>{m.content.startsWith('🔑') && !myKey && <button style={css.pin} onClick={() => setKeyOpen(true)}>🔑 키 넣기</button>}<button style={css.ghost} onClick={retry}>질문 다시 고치기</button></div></div>
            : <div key={i} style={css.ai}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4, flexWrap: 'wrap' }}>
                <span data-testid="answer-kind" style={{ ...css.kind, ...(KINDS[m.kind] ? KINDS[m.kind][1] : null) }}>{m.kind === 'deep' && m.pic ? '🖼 인포그래픽' : (KINDS[m.kind] || KINDS.chat)[0]}</span>
              </div>
              {m.alt?.length > 0 && <div data-testid="ask-remembered" style={{ ...css.meta, display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginBottom: 4 }}>
                <span>기억한 대로 {(ASK_LABEL[m.kind] || [m.kind])[0]} 했어요</span>
                {m.alt.map(k => <button key={k} data-testid="ask-other" data-kind={k} style={css.ghost} disabled={!!busy} onClick={() => choose(i, k)} title="같은 질문을 이쪽으로 다시 — 다음엔 다시 물어요">{(ASK_LABEL[k] || [k])[0]} 바꾸기</button>)}
              </div>}
              {m.kind === 'deep' ? (m.step !== 'ask' ? <Answer text={m.content || (m.plan?.title ? `📰 취재 한 판 계획 「${m.plan.title}」(지금은 만들 수 없어요)` : '')} />   /* 옛 기록(한 판 = 2026-11-09 뺌) */
                : m.step === 'ask'
                ? <DeepAsk m={m} busy={busy} css={css} cost={m.pic ? featCost('infographic') : ''} set={(q, v) => setMsg(i, { brief: { ...m.brief, [q]: v } })} go={() => deepGo(i, draft.trim())} />
                : null)
                : m.kind === 'slides' ? (m.step === 'ask'
                  ? <DeepAsk m={m} busy={busy} css={css} slides set={(q, v) => setMsg(i, { brief: { ...m.brief, [q]: v } })} go={() => slidesGo(i, draft.trim())} />
                  : <SlidesPlan m={m} busy={busy} css={css} credits={credits} mine={myKey} setDrop={d => setMsg(i, { drop: d })} setPics={p => setMsg(i, { pics: { ...(m.pics || {}), ...p } })} one={() => goTo('infographic', m.topic)} oneCost={featCost('infographic')} base={(ed.current?.frameIds?.().length || 0) + 1} drop={k => setMsg(i, { drop: (m.drop || []).includes(k) ? m.drop.filter(x => x !== k) : [...(m.drop || []), k] })}
                    flip={k => setMsg(i, { pics: { ...(m.pics || {}), [k]: nextPic(picOf(m, k)) } })}
                    build={() => slidesBuild(i)} show={() => ed.current?.showIds([m.built]) || setGone(g => ({ ...g, [m.at + ':slides']: true }))} />)
                : <Answer text={m.content} chart={m.kind === 'ask' ? null : chartAct(m)} />}
              {/* 길이 상한에 걸려 끊긴 답(2026-10-27 — 긴 연설문 등이 다 된 것처럼 보였음). 이어 쓰기는 맨 끝 답에서만(앞 답이면 「⋯ › 여기서 이어 묻기」) */}
              {m.cut && <div data-testid="answer-cut" style={{ ...css.meta, color: 'light-dark(#b45309, #f59e0b)', display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginTop: 6 }}>
                <span>답이 길어서 중간에 끊겼어요</span>
                {i === msgs.length - 1 && <button data-testid="answer-cut-more" style={css.ghost} disabled={!!busy} onClick={() => send(CUT_MORE, 'chat')} title="끊긴 곳부터 이어서 써 달라고 보내요">이어서 쓰기</button>}
              </div>}
              {m.kind === 'slides' && m.model && <div style={{ ...css.meta, marginTop: 6, textAlign: 'right' }}>{gone[m.at + ':slides'] ? '프레임이 지워졌어요 · ' : ''}{m.model}{m.elapsed != null ? ` · ${m.elapsed}초` : ''}{m.credits != null ? ` · 약 ${Math.round(m.credits)}크레딧` : ''}</div>}
              {m.kind === 'deep' && (m.model || gone[m.at + ':deep']) && <div style={{ ...css.meta, marginTop: 6, textAlign: 'right' }}>{gone[m.at + ':deep'] ? '판이 지워졌어요 · ' : ''}{m.model || ''}{m.elapsed != null ? ` · ${m.elapsed}초` : ''}{m.credits != null ? ` · 약 ${Math.round(m.credits)}크레딧` : ''}</div>}
              {m.kind === 'ask' && <div data-testid="ask-choices" style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
                {(m.choices || []).map(k => <button key={k} data-testid="ask-choice" data-kind={k} disabled={!!busy} onClick={() => choose(i, k)} title={(ASK_LABEL[k] || [])[1]}
                  style={{ ...css.pin, display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 1, padding: '6px 10px', textAlign: 'left' }}>
                  <span>{(ASK_LABEL[k] || [k])[0]}</span><span style={{ ...css.meta, fontWeight: 400 }}>{(ASK_LABEL[k] || [])[1]}</span></button>)}
                <span style={css.meta}>보기에 없으면 아래 칸에 적어 주세요. 같은 걸 두 번 고르면 다음엔 바로 해요</span>
              </div>}
              {m.html && m.kind === 'live' && <LivePreview m={m} />}
              {(m.autoFixed > 0 || m.check?.length > 0 || m.fixTried) && <div data-testid="card-check" style={{ ...css.meta, marginTop: 6 }}>
                {m.autoFixed > 0 && <div>글자 잘림·겹침 {m.autoFixed}곳을 찾아 자동으로 고쳤어요</div>}
                {m.fixKept && <div>고쳐 봤지만 나아지지 않아 그대로 뒀어요</div>}
                {m.fixTried && !m.fixKept && !m.check?.length && <div>잘린 곳을 고쳤어요</div>}
                {m.check?.length > 0 && <div>확인이 필요해요 — {m.check.slice(0, 3).join(' · ')}{m.check.length > 3 ? ` 외 ${m.check.length - 3}곳` : ''}</div>}
                {m.kind === 'motion' && m.check?.length > 0 && !m.fixTried && m.motionFrame && <button data-testid="card-fix" disabled={!!busy} onClick={() => motionFix(i)} style={{ ...css.pin, marginTop: 4 }}>잘린 곳 고치기 (약 270~520크레딧)</button>}
              </div>}
              {m.html && m.kind !== 'live' && <div data-testid="answer-doc" style={{ marginTop: 6 }}>   {/* 정리 문서 미리보기 — A4 폭 794px를 대화창 폭에 맞춰 줄임(스크립트 없는 iframe) */}
                {m.docs?.length > 1 ? <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>   {/* 두 장(발표용·읽기용) = 나란히 반쪽 크기 */}
                  {m.docs.map(d => <div key={d.style} data-testid="answer-doc-style" data-style={d.style}>
                    <div style={{ ...css.meta, marginBottom: 2 }}>{d.label}</div>
                    <DocThumb html={d.html} title={d.title || d.label} h={220} tip={`${d.label} — 누르면 크게 보기 · 인쇄`} name={`${d.label} 크게 보기 · 인쇄`} open={() => openHtml(d.html)} /></div>)}
                </div>
                : <DocThumb html={m.html} title={m.title || '문서'} w={m.page_w || 794} h={300} tip="누르면 크게 보기 · 인쇄" name="문서 크게 보기 · 인쇄" open={() => openHtml(m.html)} />}
                <div style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>   {/* 「크게 보기 · 인쇄」 단추는 뺌 — 미리보기 누르기와 같았음(2026-10-26 실검증) */}
                  <button style={css.ghost} disabled={!!busy} onClick={() => drawReport(i)} title="같은 자료로 인포그래픽 그림 후보 2장 — 보기 좋지만 숫자·날짜를 지어낼 수 있으니 확인하고 쓰세요(약 20크레딧)">🎨 이미지로도</button>
                  <span style={{ ...css.meta, alignSelf: 'center' }}>미리보기를 누르면 크게 보기·인쇄 · 고칠 점을 이어서 말하면 이 문서를 고쳐 써요</span></div>
              </div>}
              {m.images?.length > 0 && <div data-testid="answer-images" style={{ marginTop: 6, display: 'grid', gridTemplateColumns: `repeat(${Math.min(2, m.images.length)}, 1fr)`, gap: 6, alignItems: 'start' }}>   {/* 원래 비율(2026-10-20 사용자: 4:3으로 채우니 잘림) — 세로로 긴 그림은 320px까지 */}
                {/* 사진 누르기 = 크게 보기, 왼쪽 위 「＋ 칠판에 추가」, 추가한 적 있으면 테두리만 초록, 사진·버튼 어디서든 끌면 칠판이 직접 끔(실제 크기 + 정렬선) */}
                {m.images.map((g, j) => { const done = m.picked?.includes(j)
                  return <div key={g.url} data-testid="image-pick" data-picked={done ? "1" : undefined} role="button" tabIndex={0} aria-label={`후보 ${j + 1} 크게 보기`}
                    onClick={() => { if (dragged.current) { dragged.current = false; return } setBig({ i, j }) }}
                    onKeyDown={e => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setBig({ i, j }) } }}   /* 안쪽 「＋ 칠판에 추가」의 Enter는 그 단추 몫(2026-11-09 — 크게 보기가 열렸음) */
                    onPointerDown={e => imgDown(e, i, j)}
                    style={{ cursor: 'zoom-in', position: 'relative', borderRadius: 8, overflow: 'hidden', border: `2px solid ${done ? DONE : C.line}` }}>
                    <img src={g.url} alt={`후보 ${j + 1}`} draggable={false} style={{ display: 'block', width: '100%', height: 'auto', maxHeight: 320, objectFit: 'contain', background: '#fff' }} />
                    <AddBtn testid="image-pin" done={flash === `${i}:${j}`} onClick={async e => { e.stopPropagation(); if (dragged.current) { dragged.current = false; return } await pinPick(i, j) }} />
                  </div> })}</div>}
              {m.svgs?.length > 0 && <div data-testid="answer-svgs" style={{ marginTop: 6, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 6 }}>   {/* 하나여도 반 폭(고치기 답 — 꽉 채우면 너무 큼) */}
                {/* 미리보기 = 칠판에 들어갈 도형 그대로(svgPreview). 누르기 = 칠판에 추가(그림처럼 크게 볼 것 없는 단순한 선), 끌기 = 놓은 자리 */}
                {m.svgs.map((sv, j) => { const done = m.picked?.includes(j)
                  return <div key={j} data-testid="svg-pick" data-picked={done ? '1' : undefined} role="button" tabIndex={0} aria-label={`아이콘 후보 ${j + 1} 칠판에 추가`}
                    title="누르면 칠판 빈자리에 · 끌면 놓은 자리에 — 묶음으로 들어가요(선 하나씩 고치려면 묶음 풀기 Ctrl+Shift+G)"
                    onClick={() => { if (dragged.current) { dragged.current = false; return } pinSvgPick(i, j) }}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pinSvgPick(i, j) } }}
                    onPointerDown={e => svgDown(e, i, j)}
                    style={{ cursor: 'copy', position: 'relative', borderRadius: 8, border: `2px solid ${done ? DONE : C.line}`, background: '#fff', aspectRatio: '1' }}>
                    <img src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgPreview(sv))}`} alt={`아이콘 후보 ${j + 1}`} draggable={false} style={{ display: 'block', width: '100%', height: '100%', padding: 10, boxSizing: 'border-box' }} />
                    {flash === `${i}:${j}` && <span style={{ position: 'absolute', left: 6, top: 6, ...css.meta, color: '#166534', background: '#fff', borderRadius: 4, padding: '0 4px' }}>✓ 추가됨</span>}
                  </div> })}</div>}
              {m.kind === 'diagram' && m.place && <div data-testid="answer-diagram" style={{ display: 'flex', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
                <button data-testid="diagram-show" style={css.pin} onClick={() => showFlow(i)} title="칠판의 그 도형으로 가기(지웠으면 다시 그려 놓아요 — 크레딧 없음)">🔷 칠판에서 보기</button>
                <button data-testid="diagram-image" style={css.ghost} disabled={!!busy} onClick={() => choose(i, 'image')} title="같은 말로 이미지 후보 2장(약 20크레딧) — 보기 좋지만 상자·글을 고칠 수는 없어요. 칠판의 도형은 그대로">🎨 이미지로 다시</button>
              </div>}
              {canMore(m) && <div style={{ marginTop: 6 }}><button data-testid="answer-more" style={css.ghost} disabled={!!busy} onClick={() => more(i)}
                title="같은 요청으로 후보 2개를 더 만들어 아래에 덧붙여요(앞 후보는 그대로)">＋ 2개 더 보기 · 약 {m.kind === 'image' ? 20 : 10}크레딧</button></div>}
              {m.refs?.length > 0 && <div data-testid="answer-refs" style={{ marginTop: 6, display: 'flex', flexDirection: 'column' }}>
                {m.refs.map(r => <button key={r.n} onClick={() => ed.current?.showItem(r.uid) || setGone(g => ({ ...g, [m.at + ':' + r.n]: true }))} title="칠판의 그 도형으로 가기"
                  style={{ all: 'unset', cursor: 'pointer', ...css.meta, padding: '5.5px 0', color: 'light-dark(#b45309, #f59e0b)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  📌 [칠판 {r.n}] {r.kind ? `${r.kind} · ` : ''}{(r.text || '').split('\n')[0]}{gone[m.at + ':' + r.n] ? ' — 지워졌어요' : ''}</button>)}</div>}
              {m.sources?.length > 0 && <div data-testid="answer-sources" style={{ marginTop: 6, display: 'flex', flexDirection: 'column' }}>
                {m.sources.map(s => <a key={s.n} href={s.url} target="_blank" rel="noopener noreferrer" title={s.url} onPointerDown={e => e.stopPropagation()}
                  style={{ ...css.meta, padding: '5.5px 0', color: LINK_CHAT, textDecoration: 'none', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>[{s.n}] {s.title || siteOf(s.url)} · {siteOf(s.url)}</a>)}</div>}
              {m.kind !== 'ask' && m.kind !== 'deep' && m.kind !== 'slides' && <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 8, flexWrap: 'wrap' }}>
                {!m.images?.length && !m.svgs?.length && m.kind !== 'diagram' && <button style={{ ...(m.pinned ? css.done : css.pin), cursor: 'grab' }} onPointerDown={e => dragDown(e, i)} onClick={() => { if (dragged.current) { dragged.current = false; return } pin(i) }}
                  title={m.pinned ? '누르면 붙인 카드로 가기(지웠으면 다시 붙임) · 칠판으로 끌면 그 자리에 하나 더' : m.refs?.length ? '메모 + 근거가 된 칠판 도형으로 가는 점선 화살표(누르면 빈자리, 끌면 놓은 자리)' : m.sources?.length ? '요약 메모 + 출처 카드를 번호 화살표로 이어 한 묶음으로(누르면 빈자리, 끌면 놓은 자리)' : '누르면 빈자리에, 칠판으로 끌면 놓은 자리에 카드로'}>
                  {m.pinned ? '칠판에 붙임 ✓' : '칠판에 붙이기'}</button>}
                {/* ⋯ 하나에 — 이어 묻기·분기·다시 만들기·복사(2026-10-20 사용자: 다른 AI 채팅 참고, 버튼은 늘리지 않게) */}
                {m.prev && <button data-testid="answer-prev" style={css.ghost} disabled={!!busy} title="다시 만들기 전 답으로 돌아가요(지금 답과 맞바꿈 — 크레딧 없음)" onClick={() => update(msgs.map((x, j) => (j === i ? { ...m.prev, prev: { ...m, prev: undefined } } : x)))}>↶ 앞 답으로</button>}
                <span data-answer-menu style={{ position: 'relative' }}>
                  <button data-testid="answer-menu" aria-label="이 답 메뉴" style={{ ...css.ghost, ...(replyTo === m.at ? { color: 'var(--mb-accent)', borderColor: 'var(--mb-accent)' } : null) }} aria-expanded={menuAt === m.at} onClick={() => setMenuAt(a => (a === m.at ? null : m.at))} title="이 답으로 — 이어 묻기·새 대화로 분기·다시 만들기·복사">{replyTo === m.at ? '↩ ⋯' : '⋯'}</button>
                  {menuAt === m.at && <div role="menu" ref={el => el?.querySelector('button:not(:disabled)')?.focus()} onKeyDown={menuKeys} style={css.menu}><style>{'.mb-mi:hover:not(:disabled){background:var(--mb-seg)}.mb-mi:disabled{opacity:.45;cursor:default}'}</style>
                    {[['↩ 여기서 이어 묻기', '다음 질문이 이 답까지를 이어받아요(그림이면 그 그림을 고쳐요)', () => setReplyTo(m.at)],
                      ['⑂ 새 대화로 분기', '이 답까지를 새 대화로 — 지금 대화는 「지난 대화」에', () => branch(i)],
                      ['↻ 다시 만들기', '같은 질문으로 한 번 더 — 크레딧이 다시 들어요. 바꾼 뒤 「↶ 앞 답으로」로 돌아갈 수 있어요', () => regen(i)],
                      ...(!m.images?.length && !m.svgs?.length && !m.html ? [['복사', '답 글을 클립보드로', () => navigator.clipboard?.writeText(m.content).catch(() => {})]] : [])]
                      .map(([label, tip, fn]) => <button key={label} role="menuitem" className="mb-mi" style={css.item} disabled={!!busy && label !== '복사'} title={tip} onClick={() => { setMenuAt(null); fn() }}>{label}</button>)}
                  </div>}
                </span>
                <span data-testid="answer-model" style={{ ...css.meta, marginLeft: 'auto' }} title={m.swap ? `원래 모델 ${m.swap.from}이 KAIROS에서 ${m.swap.why === '은퇴' ? '은퇴해서' : '없어져서'} ${m.swap.to}로 했어요` : undefined}>{m.model}{m.swap ? ' (대신)' : ''}{m.elapsed != null ? ` · ${m.elapsed}초` : ''}{m.credits != null ? ` · ${Math.round(m.credits)}크레딧` : ''}</span>
              </div>}
            </div>)}
        {busy && <div data-testid="chat-busy" style={{ ...css.ai, color: C.muted }}><div style={{ display: 'flex', alignItems: 'center', gap: 8 }}><Spinner />{busyLine}</div><ChatSkeleton kind={busyJob} /></div>}
      </div>
      <div style={css.foot}>
        {replyTo != null && <button data-testid="reply-chip" style={{ ...css.chip, color: 'var(--mb-accent)', background: 'rgba(218,119,86,.14)', cursor: 'pointer', border: 0 }} onClick={() => setReplyTo(null)} title="누르면 이어 묻기 취소">
          ↩ 「{replyLabel(replyTo)}」에 이어서 ✕</button>}
        {selN > 0 && (sel.length > 0 || selImgs.length > 0) && <span data-testid="sel-chip" style={css.chip} >{selN}개 선택됨</span>}{/* 2026-10-21 사용자: 글·그림 칩 둘 + 사용법 문장 → 한 칩(사용법은 설명 페이지로) */}
        <Composer inputRef={ta} label="KAIROS에게 물어보기" sendId="chat-send" fs={13.5} maxRows={12} value={draft} canSend={canSend} busy={!!busy} onStop={() => stopRef.current?.abort()}
          stopTitle="이 답 기다리기를 그만둬요(서버에서 이미 시작한 일은 끝까지 가서 크레딧이 들 수 있어요)"
          placeholder={(lastM?.kind === 'ask' ? '버튼을 누르거나, 원하는 걸 직접 적어 주세요'
            : lastM?.kind === 'deep' && lastM.step === 'ask' && !lastM.done ? '꼭 넣을 것·바라는 점(비워도 돼요) — Enter = 그림 그리기'
            : lastM?.kind === 'slides' && lastM.step === 'ask' && !lastM.done ? '꼭 넣을 것·바라는 점(비워도 돼요) — Enter = 장 계획 짜기'
            : lastM?.kind === 'slides' && lastM.step === 'plan' && !lastM.built && !lastM.stale ? '계획을 고칠 점을 말하면 다시 짜요 — 예: 사례 장을 하나 더'
            : '물어보세요 (Enter 보내기 · Shift+Enter 줄바꿈)')}
          onChange={e => { if (mic === 'listen') micStop.current?.(); setDraft(e.target.value) }}
          onPaste={e => { const fs = [...(e.clipboardData?.files || [])]; if (fs.length && !e.clipboardData.getData('text/plain').trim()) { e.preventDefault(); attach(fs) } }}
          onSend={() => send()}
          tools={<>
            <button data-testid="attach" aria-label="파일 올리기" {...hoverBg} style={tool} onClick={() => fileIn.current?.click()}
              title="파일 올리기 — 칠판 빈자리에 놓고 골라 둬요(그림·PDF·녹음·md·txt·HTML). 대화창에 끌어 놓거나 붙여 넣어도 돼요"><Glyph svg={CLIP} /></button>
            <input ref={fileIn} data-testid="attach-input" type="file" multiple hidden onChange={e => { const fs = [...e.target.files]; e.target.value = ''; attach(fs) }} />
            <button data-testid="mic" aria-label={mic === 'off' ? '말로 입력' : undefined} {...(mic === 'off' ? hoverBg : null)} onClick={toggleMic} disabled={!server || mic === 'wait' || mic === 'stopping'} aria-pressed={mic === 'listen'}
              title={mic === 'listen' ? '듣는 중 — 다시 누르면 멈춰요(보내도 멈춤)' : '말로 입력 — 말하는 동안 글자가 바로 떠요(KAIROS 실시간 받아쓰기, 말한 1분에 약 2크레딧)'}
              style={{ ...tool, ...(mic === 'off' ? null : { width: 'auto', padding: '0 8px', gap: 3, display: 'flex', alignItems: 'center', font: `500 12px ${F}` }), ...(mic === 'listen' ? { color: '#fff', background: '#dc2626' } : null) }}>
              {mic === 'listen' ? '● 듣는 중' : mic === 'wait' ? <><Glyph svg={ICONS.mic} />…</> : mic === 'stopping' ? <><Glyph svg={ICONS.mic} />마무리…</> : <Glyph svg={ICONS.mic} />}</button>
            <span data-testid="chat-foot-note" style={{ ...css.meta, flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', ...(micErr ? { color: 'var(--mb-danger-ink)' } : null) }} title={micErr || (server ? `대화 기록은 이 칠판(「${DOC_NAME}」)에 함께 저장돼요` : '')}>{micErr || (server ? '' : '서버가 꺼져 있어요 — python web/server.py 를 켜야 물을 수 있어요.')}</span>
            <span data-model-set style={{ position: 'relative' }}>
            <button data-testid="model-settings" {...hoverBg} style={{ ...css.ghost, padding: '4px 7px', borderColor: 'transparent', ...(cfgOpen || Object.keys(picks).length ? { color: 'var(--mb-accent)', borderColor: 'var(--mb-accent)' } : null) }} aria-expanded={cfgOpen} onClick={() => setCfgOpen(o => !o)}
              title="모델 설정 — 일마다 쓸 모델(안 고르면 자동: 앱이 재 보고 고른 모델, 은퇴·없어지면 KAIROS 대체로 저절로)">⚙ 모델</button>
            {cfgOpen && <ModelSettings onClose={() => setCfgOpen(false)} models={models} picks={{ ...picks, ...(model ? { chat: model } : {}) }} setPick={setPick} />}
          </span>
          </>} />
      </div>
    </aside>
  )
}

// 「모델 설정」(2026-10-26 사용자 — 회사에 넘긴 뒤에도 고를 수는 있게, 관리는 없이) — 일마다 쓸 모델. 맨 위 = 자동(앱이 재 보고 고른 모델 — 은퇴·없어지면 저절로 대체),
// 그 아래 = 그 종류(KAIROS `type`)의 지금 모델 전부(서버 `choices` — 회사별·비싼 것부터, 판단 모델 jev 같은 것은 종류가 달라 안 섞임). 고른 값은 이 브라우저에만
function ModelSettings({ models, picks, setPick, onClose }) {
  const ch = models?.choices || {}, jobs = models?.jobs || {}
  const can = j => jobs[j]
  const rows = PICK_ROWS.filter(([job]) => job === 'chat' || (PICK_GROUPS[job] || [job]).some(can))   // 서버가 못 하는 일(딥모드 등)은 칸도 없음
  const auto = job => (PICK_GROUPS[job] ? '일마다 알맞게' : (job === 'chat' ? models?.default : jobs[job]) || '앱 기본')   // 묶음 칸은 일마다 기본이 달라 이름 하나로 못 씀
  return (
    <div role="dialog" aria-label="모델 설정" data-testid="model-settings-pop" ref={el => { if (el && !el.contains(document.activeElement)) el.querySelector('select')?.focus() }} onKeyDown={e => { if (e.key === 'Escape') { e.stopPropagation(); e.currentTarget.closest('[data-model-set]').querySelector('[data-testid=model-settings]')?.focus(); onClose() } }} style={{ ...css.menu, left: 'auto', right: 0, width: 300, maxWidth: 'calc(100vw - 32px)', boxSizing: 'border-box', padding: 10, gap: 8 }}>
      <div style={{ font: `700 13px ${F}` }}>모델 설정</div>
      {rows.map(([job, label, type]) => {
        const list = ch[type] || [], cur = picks[job] || ''
        return (
          <label key={job} style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <span style={css.meta}>{label}</span>
            <select data-testid={`pick-${job}`} style={{ ...css.select, maxWidth: 'none', width: '100%' }} value={cur} onChange={e => setPick(job, e.target.value)}>
              <option value="">자동 · {auto(job)}</option>
              {cur && !list.some(m => m.id === cur) && <option value={cur}>{cur}</option>}
              {[...new Set(list.map(m => m.maker))].map(g => (
                <optgroup key={g} label={g}>{list.filter(m => m.maker === g).map(m => <option key={m.id} value={m.id}>{m.id}{m.price ? `  ${m.price}` : ''}</option>)}</optgroup>))}
            </select>
          </label>)
      })}
      <span style={{ ...css.meta, whiteSpace: 'normal' }}>고른 모델이 그 일을 못 하면 자동 모델로 한 번 다시 해요(답에 「대신」). 값 = 100만 토큰당 입력 / 출력 달러, 이미지는 장당 크레딧.</span>
      {Object.keys(picks).length > 0 && <button data-testid="picks-reset" style={{ ...css.ghost, alignSelf: 'flex-start' }} onClick={() => PICK_ROWS.forEach(([j]) => setPick(j, ''))}>모두 자동으로</button>}
    </div>)
}
