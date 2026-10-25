// 스켈레톤 로딩(2026-10-25 사용자) — 오래 걸리는 일은 결과가 놓일 자리에 회색 틀을 먼저(무엇이·어디에·얼마나 왔는지).
// 칠판 쪽 = BoardSkeleton(칠판 좌표 SVG, Editor `pend` 목록), 대화창 쪽 = ChatSkeleton(기다리는 답 자리).
// 깜빡임 = 천천히 밝아졌다 흐려지기(Tailwind animate-pulse와 같은 1.6초). 1초 안에 끝나는 일·글이 흘러나오는 보통 대화엔 안 씀.
import { APP_FONT } from './geom.js'

const FILL = 'rgba(128,128,128,.10)', BAR = 'rgba(128,128,128,.22)', DONE = 'rgba(218,119,86,.20)', ACCENT = '#da7756'
const pulse = <animate attributeName="opacity" values="1;.45;1" dur="1.6s" repeatCount="indefinite" />

// 막대 몇 줄(제목 하나 + 글줄) — 칸 안에 맞춰
function Bars({ x, y, w, h, n = 4 }) {
  const gap = Math.min(18, h / (n + 2)), bh = gap * 0.55
  return <g>{Array.from({ length: n }, (_, i) => <rect key={i} x={x} y={y + i * gap * 1.4} width={i === 0 ? w * 0.55 : w * (i % 3 === 2 ? 0.7 : 0.92)} height={i === 0 ? bh * 1.4 : bh} rx={bh / 2} fill={BAR} />)}</g>
}

// q = { id, kind, x, y, w, h, label, msg?, done?, total?, cols?, rows?, n? } — 칠판 좌표. z = 화면 배율(글자·선 굵기를 화면에서 같게)
export function BoardSkeleton({ q, z }) {
  const { x, y, w, h } = q, fs = 13 / z, pad = Math.min(w, h) * 0.06, r = Math.min(10, w / 20)
  let inner = null
  if (q.kind === 'trace') {   // 베끼기 — 구역 cols×rows, 끝난 구역부터 색이 참(서버 진행 그대로)
    const cols = q.cols || 3, rows = q.rows || 2, cw = w / cols, ch = h / rows, done = q.done || 0
    inner = <g>{Array.from({ length: cols * rows }, (_, i) => { const c = i % cols, rr = Math.floor(i / cols), on = i < done
      return <rect key={i} x={x + c * cw + 3 / z} y={y + rr * ch + 3 / z} width={cw - 6 / z} height={ch - 6 / z} rx={4 / z} fill={on ? DONE : BAR} opacity={on ? 1 : 0.6}>{on ? null : pulse}</rect> })}</g>
  } else if (q.kind === 'deep') {   // Deep Mode 판 — 프레임 + 꼭지 칸(12칸 줄을 어림)
    const n = Math.max(3, q.n || 6), head = h * 0.12 + fs * 1.8, cols = 3, rows = Math.ceil(n / cols), cw = (w - 2 * pad) / cols, ch = (h - head - 2 * pad) / rows
    inner = <g><rect x={x + pad} y={y + pad + fs * 1.8} width={w * 0.5} height={head * 0.4} rx={6 / z} fill={BAR}>{pulse}</rect>
      {Array.from({ length: n }, (_, i) => <rect key={i} x={x + pad + (i % cols) * cw + 6 / z} y={y + pad + head + Math.floor(i / cols) * ch + 6 / z} width={cw - 12 / z} height={ch - 12 / z} rx={8 / z} fill={BAR} opacity={0.7}>{pulse}</rect>)}</g>
  } else if (q.kind === 'meeting') {   // 회의록 — 요약 메모 + 접힌 전문 두 칸
    const cw = (w - 3 * pad) / 2
    inner = <g>{[0, 1].map(i => <g key={i}><rect x={x + pad + i * (cw + pad)} y={y + pad + fs * 1.6} width={cw} height={h - 2 * pad - fs * 1.6} rx={8 / z} fill="rgba(255,255,255,.35)" />
      <g>{pulse}<Bars x={x + pad * 2 + i * (cw + pad)} y={y + pad * 2 + fs * 1.6} w={cw - 2 * pad} h={h - 4 * pad - fs * 1.6} n={i ? 6 : 5} /></g></g>)}</g>
  } else {   // 메모·쪽(PDF)·글 — 막대
    inner = <g>{pulse}<Bars x={x + pad} y={y + pad + fs * 1.6} w={w - 2 * pad} h={h - 2 * pad - fs * 1.6} n={q.n || Math.max(3, Math.min(9, Math.round(h / w * 5)))} /></g>
  }
  const tail = q.total ? ` · ${q.done || 0}/${q.total}` : q.msg ? ` · ${q.msg}` : ''
  return <g data-testid="board-skeleton" data-kind={q.kind} pointerEvents="none">
    <rect x={x} y={y} width={w} height={h} rx={r} fill={FILL} stroke={ACCENT} strokeOpacity={0.55} strokeWidth={1.2 / z} strokeDasharray={`${8 / z} ${5 / z}`} />
    {inner}
    <text x={x + pad} y={y + pad} dominantBaseline="hanging" fontSize={fs} fontFamily={APP_FONT} fill={ACCENT}>{q.label}{tail}</text>
  </g>
}

// 대화창 — 기다리는 답 자리. kind = 기다리는 일(image·icon = 후보 두 칸, report·live = 카드, deep-plan = 계획 카드 줄)
const box = { background: 'rgba(128,128,128,.12)', borderRadius: 8 }
const bar = (w, h = 10) => ({ ...box, width: w, height: h, borderRadius: h / 2 })
export const CHAT_SKELETON = new Set(['image', 'icon', 'report', 'live', 'deep-plan'])   // Deep Mode 판·꼭지는 칠판 쪽 스켈레톤이 맡음
export function ChatSkeleton({ kind }) {
  if (!CHAT_SKELETON.has(kind)) return null
  const pairs = kind === 'image' || kind === 'icon'
  return <div data-testid="chat-skeleton" data-kind={kind} className="mb-pulse" style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 6 }}>
    <style>{'@keyframes mb-pulse{50%{opacity:.45}}.mb-pulse{animation:mb-pulse 1.6s ease-in-out infinite}'}</style>
    <div style={bar('60%', 12)} />
    {pairs ? <div style={{ display: 'flex', gap: 8 }}><div style={{ ...box, flex: 1, aspectRatio: '1' }} /><div style={{ ...box, flex: 1, aspectRatio: '1' }} /></div>
      : kind === 'deep-plan' ? [0, 1, 2, 3, 4].map(i => <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}><div style={bar(18, 18)} /><div style={bar(`${70 - i * 7}%`)} /></div>)
      : <div style={{ ...box, width: '100%', aspectRatio: kind === 'live' ? '3 / 2' : '4 / 5', maxHeight: 260 }} />}
  </div>
}
