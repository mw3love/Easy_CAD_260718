// 직접 만드는 칠판 — .ecad 아이템을 SVG로 그린다(데스크톱 `core_shapes.py` paint 규칙, 밝은 화면 기준).
// 화면 밝기 규칙: 보드 밖의 흰 잉크(선·글)는 밝은 칠판에서 안 보여 검정으로(데스크톱 PDF 출력과 같은 규칙), 보드 안은 보드 바탕을 따르므로 그대로.
import { memo } from 'react'
import { cssColor, bgCss } from '../ecadFormat.js'
import {
  APP_FONT, BOARD_FONT, METRICS, PT, TEXT_MARGIN, TB_ROWS, bezierAt, bezierSub, colEdges, curveAt, cutPolyline, dashArray, headSize, headTriangle,
  colFracs, frameTag, frameTagFs, itemTransform, labelAnchor, rowEdges, labelInset, paperWH, polylineAt, roundedPath, runsToLines, trimmedPts, urlSpans,
} from './geom.js'
import { symbolPath } from './symbols.js'
import { sarrowRadius } from './arrows.js'
import { WEB_HEAD, frameSrc, isYoutube, openBtnRect, siteOf } from './webcard.js'
import { LISTY, MEMO, MEMO_KIND, MUTED, olNumbers } from './memo.js'
import { LEGEND, descOf, rowName } from './legend.js'
import { PdfPages, pdfPageAt } from './pdfcard.jsx'
import { chartScene, isChart } from './chart.js'
import { LIVE_CSP, LIVE_W, isLive, liveFits, liveSrc } from './livecard.js'

// ── 글자 재기(캔버스) ──
let _ctx = null
const ctx = () => (_ctx ||= document.createElement('canvas').getContext('2d'))
const fontCss = (px, family, weight = 400) => `${weight} ${px}px ${family === 'mono' ? MONO_FONT : family === 'board' ? BOARD_FONT : APP_FONT}`
// 코드(고정폭 조각, 2026-10-18 코드 블록) — 윈도우 기본 Consolas, 한글은 다음 글꼴로. 코드 줄 바탕은 밝기와 상관없이 보이는 반투명 회색
export const MONO_FONT = "Consolas, 'Cascadia Mono', 'D2Coding', monospace", CODE_BAND = 'rgba(127,127,127,.14)'
// 폭을 넘으면 끝을 「…」로(웹 카드 제목·주소 한 줄)
export function ellipsis(text, px, weight, maxW) {
  const t = String(text || ''); if (maxW <= 0) return ''; if (measure(t, px, 'app', weight) <= maxW) return t
  let lo = 0, hi = t.length; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (measure(t.slice(0, m) + '…', px, 'app', weight) <= maxW) lo = m; else hi = m - 1 }
  return t.slice(0, lo) + '…'
}
// 두 줄로 나누기(넘치면 둘째 줄 끝 …) — 웹 카드 설명
function wrap2(text, px, maxW) {
  const t = String(text || '').replace(/\s+/g, ' ').trim(); if (!t || maxW <= 0) return []
  let i = 1; while (i <= t.length && measure(t.slice(0, i), px, 'app', 400) <= maxW) i++
  if (i > t.length) return [t]
  const sp = t.lastIndexOf(' ', i - 1), cut = sp > (i - 1) * 0.6 ? sp : i - 1   // 낱말 사이에서 끊되 너무 앞이면 글자 단위
  return [t.slice(0, cut).trim(), ellipsis(t.slice(cut).trim(), px, 400, maxW)]
}
export function measure(text, px, family, weight) { const c = ctx(); c.font = fontCss(px, family, weight); return c.measureText(text).width }

// 글 배치 — 줄마다 조각(굵게·색·형광펜) 위치까지. 반환 { lines: [{parts:[{text,x,w,…}], w}], w, h, px, family, weight }
// maxW(px)를 주면 그 폭에서 줄을 바꾼다 — 띄어쓰기에서, 띄어쓰기 없는 긴 덩어리(주소·코드)는 글자 단위로(왼쪽 위 라벨 = AI 카드·메모)
export function layoutText(text, runs, px, family, weight = 400, maxW = 0, links = null) {   // links = 주소 구간(메모만 — 파란 밑줄·Ctrl+클릭)
  const wOf = p => measure(p.text, px, p.mono ? 'mono' : family, p.mono ? 400 : p.bold ? Math.max(700, weight) : weight)
  let src = runsToLines(text || '', runs, links)
  if (maxW > 0) src = src.flatMap(parts => wrapParts(parts, maxW, wOf))
  const lines = src.map(parts => {
    let x = 0
    const placed = parts.map(p => { const w = wOf(p); const o = { ...p, x, w }; x += w; return o })
    return { parts: placed, w: x, code: parts.length > 0 && parts.every(p => p.mono) }   // 코드 줄 = 줄 전체 바탕
  })
  const m = METRICS[family === 'board' ? 'board' : 'app']
  return { lines, w: Math.max(0, ...lines.map(l => l.w)), h: lines.length * m.lineSpacing * px, px, family, weight, m, maxW }
}

// 한 줄(조각들)을 폭 안으로 — 낱말(띄어쓰기 포함 덩어리) 단위로 채우고, 한 낱말이 폭보다 길면 글자 단위로 자름. 줄 첫머리 띄어쓰기는 버림
function wrapParts(parts, maxW, wOf) {
  const toks = []
  for (const p of parts) for (const t of p.text.split(/(\s+)/)) if (t) toks.push({ ...p, text: t })
  const out = [[]]; let cur = 0
  const push = t => { out[out.length - 1].push(t); cur += wOf(t) }
  const brk = () => { out.push([]); cur = 0 }
  for (const t of toks) {
    const sp = /^\s+$/.test(t.text), w = wOf(t)
    if (sp) { if (cur > 0 || t.mono) push(t); continue }   // 코드 줄 앞 띄어쓰기 = 들여쓰기(지키기)
    if (cur > 0 && cur + w > maxW) { const ln = out[out.length - 1]; while (ln.length && /^\s+$/.test(ln[ln.length - 1].text)) ln.pop(); brk() }
    if (w <= maxW) { push(t); continue }
    let acc = ''   // 긴 덩어리 — 글자 단위
    for (const ch of t.text) { const nx = acc + ch; if (cur + wOf({ ...t, text: nx }) > maxW && (acc || cur > 0)) { if (acc) push({ ...t, text: acc }); brk(); acc = ch } else acc = nx }
    if (acc) push({ ...t, text: acc })
  }
  return out
}
// 표 칸 글자 크기(px) — 데스크톱 기본식(칸 높이 50%·칸 폭 30% 중 작은 값)에, 글이 칸 폭을 넘으면 넘지 않을 만큼 줄임(2026-10-18 사용자 지적: 다 쓰면 칸 밖으로 넘침).
// 편집 칸도 이 크기로 띄워 「치는 대로가 결과」
export function cellFontPx(txt, cw, ch, bold, fixedPx = 0) {   // fixedPx = 직접 정한 글자 크기(px) — 그대로 씀(칸이 늘어남, `fitTable`). 없으면 자동 = 칸에 맞춰 줄임
  if (fixedPx > 0) return fixedPx   // 숫자 = 실제 크기(2026-10-18 사용자: 숫자만 늘고 글은 안 커지던 것)
  let fs = Math.max(1, Math.min(ch * 0.5, cw * 0.3))
  const w = txt ? measure(txt, fs, 'app', bold ? 700 : 400) : 0, room = Math.max(1, cw - 4)
  if (w > room) fs = Math.max(1, fs * room / w)
  return fs
}
// 칸 하나의 꾸밈 = 표 전체 값(font·color·머리 행 굵게) 위에 칸 꾸밈(.ecad 표 `cell_styles` "r,c" → { font, bold, color, align, fill } — 2026-10-18 웹 먼저)
export function cellStyle(it, r, c) {
  const s = it.cell_styles?.[`${r},${c}`] || {}, font = s.font ?? it.font
  return { px: font ? font * PT : 0, bold: s.bold ?? !!(it.header && r === 0), color: s.color ?? it.color, align: s.align || 'center', fill: s.fill || null }
}
// 직접 정한 글자가 칸보다 크면 칸을 늘림(워드·한글 표처럼) — 그 행·그 열만 넓힘(2026-10-18: 행도 따로, 엑셀처럼). 줄이지는 않음
export const MIN_COL = 16, MIN_ROW = 8
// 칸 하나의 글을 칸 크기 창 안에 — 아주 좁은 칸에서 글이 옆 칸으로 넘어가지 않게(2026-10-18 사용자). viewBox = 칸 자리라 안 좌표는 그대로
const clipCell = (els, x, y, w, h, k) => <svg key={`c${k}`} x={x} y={y} width={Math.max(0, w)} height={Math.max(0, h)} viewBox={`${x} ${y} ${Math.max(0.001, w)} ${Math.max(0.001, h)}`} overflow="hidden">{els}</svg>
// 열·행마다 가장 좁게 될 수 있는 크기 — 직접 정한 글자가 들어갈 만큼(자동 칸은 최소값). 공통선 끌기가 여기서 멈춤(넘어서 표가 커지지 않게, 2026-10-18 사용자)
export function tableMins(it) {
  const minW = Array(it.cols).fill(MIN_COL), minH = Array(it.rows).fill(MIN_ROW)   // 표를 줄여 끌기를 되풀이해도 글 없는 열이 사라지지 않게
  for (let r = 0; r < it.rows; r++) for (let c = 0; c < it.cols; c++) {
    const s = cellStyle(it, r, c); if (!s.px) continue
    minH[r] = Math.max(minH[r], s.px * 1.35 + 4)
    const txt = it.cells?.[r]?.[c]; minW[c] = Math.max(minW[c], (txt ? measure(txt, s.px, 'app', s.bold ? 700 : 400) : s.px) + 8)   // 빈 칸도 한 글자 폭은 남김
  }
  return { minW, minH }
}
// 칸 글자의 지금 크기(pt) — 자동 칸은 칸에 맞춰 줄어든 실제 크기(속성 카드가 늘 10으로 보여 ±하면 「뻥」 커지던 것, 2026-10-18 사용자)
export function cellPt(it, r, c, exact = false) {   // exact = 반올림 없이(「자동」 끌 때 고정할 값 — 크기가 하나도 안 바뀌게)
  const s = cellStyle(it, r, c), d1 = v => (exact ? v : Math.round(v * 10) / 10)   // 소수 첫째 자리 — 정수로 반올림하면 「자동」을 끌 때 글이 살짝 작아졌음(2026-10-18 사용자)
  if (s.px) return d1(s.px / PT)
  const [x, y, w, h] = it.rect, e = colEdges(x, w, colFracs(it)), re = rowEdges(y, h, it)
  return Math.max(1, d1(cellFontPx(it.cells?.[r]?.[c] || '가', e[c + 1] - e[c], re[r + 1] - re[r], s.bold, 0) / PT))
}
export function tableAutoPt(it) {   // 표 전체 글자 크기 칸 — 글 있는 칸 중 가장 작은 지금 크기
  let m = Infinity
  for (let r = 0; r < it.rows; r++) for (let c = 0; c < it.cols; c++) if (it.cells?.[r]?.[c]) m = Math.min(m, cellPt(it, r, c))
  return m === Infinity ? cellPt(it, 0, 0) : m
}
export function fitTable(it) {
  const [x, y, w, h] = it.rect, rows = it.rows, cols = it.cols, re = rowEdges(y, h, it)
  const fr = colFracs(it), cw = fr.map(f => f * w), rh = Array.from({ length: rows }, (_, r) => re[r + 1] - re[r])
  const { minW, minH } = tableMins(it), needH = rh.map((v, r) => Math.max(v, minH[r])), needW = cw.map((v, c) => Math.max(v, minW[c]))
  const grewW = needW.some((v, i) => v > cw[i] + 0.5), grewH = needH.some((v, i) => v > rh[i] + 0.5)
  if (!grewW && !grewH) return it
  const W = needW.reduce((a, b) => a + b, 0), H = needH.reduce((a, b) => a + b, 0)
  return { ...it, rect: [x, y, grewW ? W : w, grewH ? H : h], col_widths: grewW ? needW.map(v => v / W) : it.col_widths, ...(grewH ? { row_heights: needH.map(v => v / H) } : {}) }
}
// 왼쪽 위 라벨(.ecad label.align = "left") — 상자 안 여백, 상자 폭에서 줄바꿈. fit_text 상자는 높이를 글에 맞춤
export const LABEL_PAD = 12
export function leftLabelLayout(it) {
  const L = it.label || {}, w = it.rect?.[2] || 0, family = L.family ? 'board' : 'app'
  return layoutText(L.text || '', L.runs, (L.font || 16) * PT, family, 400, Math.max(10, w - 2 * LABEL_PAD - 2 * TEXT_MARGIN))
}
export const fitTextHeight = it => Math.ceil(leftLabelLayout(it).h + 2 * TEXT_MARGIN + 2 * LABEL_PAD)

// 메모 배치(아이템 안 좌표) — 줄마다 { ln, x(글 왼쪽), y(글 위), lay, marker, box(할 일 체크 상자) }, h = 메모 전체 높이. 고치기 CSS(memoedit.jsx)와 같은 치수
const _ml = new WeakMap()
// 메모 접기(2026-10-19 회의록 전문 — 긴 메모가 칠판을 넘치지 않게): fold === true면 앞 MEMO_FOLD_N줄 + 「… N줄 더 — 눌러서 펼치기」,
// fold === false(펼친 것)면 끝에 「▴ 접기」, 없으면 보통. 덧붙인 줄은 rows 끝에 `ln.more`('open'·'close'), i = 줄 수(진짜 줄 차례와 안 겹치게). 고칠 때·찾기·대화 근거는 전체
export const MEMO_FOLD_N = 6
export function memoLayout(it) {
  let r = _ml.get(it); if (r) return r
  const all = it.lines?.length ? it.lines : [{ k: 'p', t: '' }], folded = it.fold === true && all.length > MEMO_FOLD_N + 1
  const lines = folded ? all.slice(0, MEMO_FOLD_N) : all, w = it.rect?.[2] || MEMO.W, inner = Math.max(20, w - MEMO.LPAD - MEMO.PAD), nums = olNumbers(all), rows = []
  let y = MEMO.PAD
  lines.forEach((ln, i) => {
    const K = MEMO_KIND[ln.k] || MEMO_KIND.p, px = K.pt * PT, prev = lines[i - 1], next = lines[i + 1]
    const joinPrev = i > 0 && (ln.k === 'code' || ln.k === 'quote') && prev.k === ln.k, joinNext = next && (ln.k === 'code' || ln.k === 'quote') && next.k === ln.k   // 이어진 코드·인용 줄 = 한 덩어리(위아래 여백은 덩어리 끝에만)
    if (i > 0 && !joinPrev) y += K.gap ?? MEMO.GAP
    if (!joinPrev) y += TEXT_MARGIN
    if (ln.k === 'hr') { const x = MEMO.LPAD, h = MEMO.HR * 2   // 구분선 = 가는 줄 하나(위아래 여백 포함 높이 HR*2)
      rows.push({ ln, i, x, y: y - TEXT_MARGIN, lay: { h, lines: [] }, px: 0, marker: null, box: null, cy: y - TEXT_MARGIN + h / 2, lh: h, joinPrev: false, joinNext: false, hr: true })
      y += h - TEXT_MARGIN; return }
    if (ln.k === 'table') {   // 표 줄 — 메모 안 폭 그대로, 칸 너비 = cw 비율, 칸 글은 칸 안에서 꺾음(고치기 CSS memoedit.jsx와 같은 치수)
      const rws = ln.rows?.length ? ln.rows : [['']], n = Math.max(1, ...rws.map(r => r.length)), cw = ln.cw?.length === n ? ln.cw : Array(n).fill(1 / n), cpx = MEMO_KIND.p.pt * PT
      const xs = [0]; cw.forEach(f => xs.push(xs[xs.length - 1] + f * inner))
      let ty = 0; const cells = [], rowY = [0]
      rws.forEach((r, ri) => { const hd = ln.header && ri === 0
        const lays = xs.slice(0, -1).map((cx, c) => layoutText(r[c] || '', null, cpx, 'board', hd ? 700 : 400, Math.max(10, xs[c + 1] - cx - 2 * MEMO.CELL - 2 * TEXT_MARGIN)))
        const rh = Math.max(...lays.map(l => l.h)) + 2 * TEXT_MARGIN + 2 * MEMO.CELL
        lays.forEach((lay, c) => cells.push({ lay, x: xs[c] + MEMO.CELL, y: ty + MEMO.CELL, hd }))
        ty += rh; rowY.push(ty) })
      rows.push({ ln, i, x: MEMO.LPAD, y: y - TEXT_MARGIN, lay: { h: ty, lines: [] }, px: cpx, marker: null, box: null, cy: y - TEXT_MARGIN + ty / 2, lh: ty, joinPrev: false, joinNext: false, table: { xs, rowY, cells, w: inner } })
      y += ty - TEXT_MARGIN; return }
    const ind = LISTY.has(ln.k) ? ((ln.lv || 0) + 1) * MEMO.INDENT : ln.k === 'quote' ? MEMO.QUOTE : 0
    const links = ln.k === 'code' || ln.nolink ? null : urlSpans(ln.t)   // 주소 = 파란 밑줄(줄 메뉴 「링크 끄기」면 보통 글)
    const room = Math.max(10, inner - ind - 2 * TEXT_MARGIN)
    // 코드 줄은 꺾지 않음 — 넘치면 끝을 …로(고치기 칸은 옆으로 스크롤). 꺾는 자리가 칠판·브라우저에서 달랐음(2026-10-19 사용자 선택 A)
    const ct = K.mono ? clipMono(ln.t || '', px, room) : ''
    const lay = K.mono ? layoutText(ct, [[0, ct.length, null, false, null, true]], px, 'board', 400, 0) : layoutText(ln.t || '', ln.runs, px, 'board', K.bold ? 700 : 400, room, links?.length ? links : null)
    const x = MEMO.LPAD + ind, lh = METRICS.board.lineSpacing * px, cy = y + TEXT_MARGIN + lh / 2
    const marker = ln.k === 'ul' ? ['•◦▪'[(ln.lv || 0) % 3]] : ln.k === 'ol' ? [`${nums[i]}.`] : null
    const box = ln.k === 'todo' ? { x: x - MEMO.INDENT + 2, y: cy - TEXT_MARGIN - px * 0.45, s: px * 0.9 } : null   // 글 줄 가운데(cy엔 TEXT_MARGIN이 한 번 더 들어 있어 상자가 처졌음 — 2026-10-18 사용자)
    rows.push({ ln, i, x, y: y - TEXT_MARGIN, lay, px, marker, box, cy: cy - TEXT_MARGIN, lh, joinPrev, joinNext })
    y += lay.h + (joinNext ? 0 : TEXT_MARGIN)
  })
  if (folded || (it.fold === false && all.length > MEMO_FOLD_N + 1)) {   // 펼치기·접기 줄
    const t = folded ? `… ${all.length - MEMO_FOLD_N}줄 더 — 눌러서 펼치기` : '▴ 접기', px = MEMO_KIND.p.pt * PT, lh = METRICS.board.lineSpacing * px
    y += MEMO.GAP + TEXT_MARGIN
    const lay = layoutText(t, null, px, 'board', 400, Math.max(10, inner - 2 * TEXT_MARGIN))
    rows.push({ ln: { k: 'p', t, more: folded ? 'open' : 'close' }, i: all.length, x: MEMO.LPAD, y: y - TEXT_MARGIN, lay, px, marker: null, box: null, cy: y + lh / 2, lh, joinPrev: false, joinNext: false })
    y += lay.h + TEXT_MARGIN
  }
  r = { rows, h: Math.ceil(y + MEMO.PAD) }; _ml.set(it, r); return r
}
function clipMono(t, px, maxW) {
  if (measure(t, px, 'mono', 400) <= maxW) return t
  let lo = 0, hi = t.length; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (measure(t.slice(0, m) + '…', px, 'mono', 400) <= maxW) lo = m; else hi = m - 1 }
  return t.slice(0, lo) + '…'
}
// 범례(표 모양) 칸 너비 — 견본 | 이름 | 모양. 크기 = 줄에 맞춤(편집기 commit이 rect를 이 값으로)
export function legendLayout(it) {
  const L = LEGEND, rows = it.rows || [], px = L.FONT
  const nameW = Math.max(measure('이름', px, 'app', 600), ...rows.map(e => measure(rowName(it, e), px, 'app', 400)))
  const descW = Math.max(measure('모양', px, 'app', 600), ...rows.map(e => measure(descOf(e), px, 'app', 400)))
  const c0 = L.PAD, c1 = c0 + L.SAMPLE + L.GAP, c2 = c1 + nameW + L.GAP * 2, w = c2 + descW + L.PAD
  const empty = rows.length ? 0 : measure('색 있는 선·화살표를 그리면 저절로 채워져요', px, 'app', 400) + 2 * L.PAD
  return { cols: [c0, c1, c2], w: Math.ceil(Math.max(w, empty)), h: L.HEAD + L.ROW * (Math.max(1, rows.length) + 1) + L.PAD / 2, px }
}
export const memoHeight = it => memoLayout(it).h
// 메모 안 좌표(아이템 기준) q에 있는 주소(없으면 null) — Ctrl+클릭으로 열기
export function memoLinkAt(it, q) {
  const [x0, y0] = it.rect
  for (const r of memoLayout(it).rows) { if (!r.lay?.lines || !r.lay.m) continue
    const lh = r.lay.m.lineSpacing * r.px
    for (let i = 0; i < r.lay.lines.length; i++) { const top = y0 + r.y + TEXT_MARGIN + i * lh; if (q.y < top || q.y > top + lh) continue
      for (const p of r.lay.lines[i].parts) if (p.link && q.x >= x0 + r.x + p.x && q.x <= x0 + r.x + p.x + p.w) return p.link } }
  return null
}

// 글 그리기 — (left, top) = 문서 상자 왼쪽 위(여백 포함). color = 기본 글 색
export const LINK = '#2f80ed'   // 메모 속 주소 색(밝은 메모 바탕 위)
function TextLines({ lay, left, top, color, halo, band = true, ha }) {   // ha = 줄 맞춤('center'·'right' — 글 정렬, 2026-10-27 밤 · 없으면 왼쪽), 기준 폭 = 줄바꿈 폭 또는 가장 긴 줄   // band = 코드 줄 바탕(메모 코드 블록은 덩어리째 따로 칠함)   // halo = 글자 둘레를 칠할 바탕색(화살표 라벨 — 다른 선이 지나가도 읽히게)
  const { px, m, family, weight } = lay
  const out = []
  lay.lines.forEach((ln, i) => {
    const base = top + TEXT_MARGIN + m.ascent * px + i * m.lineSpacing * px
    const W = lay.maxW || lay.w, lx = left + TEXT_MARGIN + (ha === 'right' ? W - ln.w : ha === 'center' ? (W - ln.w) / 2 : 0)
    if (ln.code && band) out.push(<rect key={`c${i}`} x={left + TEXT_MARGIN - 4} y={base - m.ascent * px} width={(lay.maxW || lay.w) + 8} height={m.lineSpacing * px} fill={CODE_BAND} />)
    if (!ln.code) for (const p of ln.parts) if (p.mono && !p.bg) out.push(<rect key={`m${i}-${p.x}`} x={lx + p.x} y={base - m.ascent * px} width={p.w} height={m.lineSpacing * px} fill={CODE_BAND} />)   // 글 속 짧은 코드
    for (const p of ln.parts) if (p.link) out.push(<rect key={`u${i}-${p.x}`} x={lx + p.x} y={base + px * 0.12} width={p.w} height={Math.max(0.6, px * 0.06)} fill={LINK} />)   // 주소 밑줄
    const decoLines = []   // 밑줄·취소선(2026-10-19) — 글자 위에 그려야 해서 글 다음에 넣음. 선 = 얇은 네모(PDF·PNG도 같게)
    for (const p of ln.parts) if (p.deco && !p.link) { const c = p.color ? cssColor(p.color) : color, th = Math.max(0.6, px * 0.06)
      if (p.deco.includes('u')) decoLines.push(<rect key={`du${i}-${p.x}`} x={lx + p.x} y={base + px * 0.12} width={p.w} height={th} fill={c} />)
      if (p.deco.includes('s')) decoLines.push(<rect key={`ds${i}-${p.x}`} x={lx + p.x} y={base - px * 0.32} width={p.w} height={th} fill={c} />) }
    for (const p of ln.parts) if (p.bg) out.push(<rect key={`b${i}-${p.x}`} x={lx + p.x} y={base - m.ascent * px} width={p.w} height={m.lineSpacing * px} fill={bgCss(p.bg)} />)
    out.push(<text key={`t${i}`} y={base} fontSize={px} fontFamily={family === 'board' ? BOARD_FONT : APP_FONT} fontWeight={weight} fill={color} style={{ whiteSpace: 'pre' }}
      {...(halo ? { stroke: halo, strokeWidth: px * 0.14, strokeLinejoin: 'round', paintOrder: 'stroke' } : {})}>   {/* 얇게 — 두꺼우면 자기 선 끝도 숫자 모양대로 곡선으로 파였음(2026-10-18) */}
      {ln.parts.map((p, j) => <tspan key={j} x={lx + p.x} fill={p.link ? LINK : p.color ? cssColor(p.color) : undefined} fontWeight={p.mono ? 400 : p.bold ? Math.max(700, weight) : undefined} fontFamily={p.mono ? MONO_FONT : undefined} fontStyle={p.deco?.includes('i') ? 'italic' : undefined}>{p.text}</tspan>)}
    </text>, ...decoLines)
  })
  return out
}

// 잉크 가운데 맞춤 — 한글 글리프 잉크는 기준선 위 0.78em ~ 아래 0.09em(데스크톱 `_ink_center_dy`의 실측 보정과 같은 뜻)
const INK_TOP = 0.78, INK_BOT = 0.09
function centeredBox(lay, a) {
  const ls = lay.m.lineSpacing * lay.px, n = Math.max(1, lay.lines.length)
  const b1 = a.y - ((n - 1) * ls) / 2 + ((INK_TOP - INK_BOT) / 2) * lay.px
  const top = b1 - lay.m.ascent * lay.px - TEXT_MARGIN
  const left = a.x - lay.w / 2 - TEXT_MARGIN
  return { left, top, inkTop: b1 - INK_TOP * lay.px, inkBot: b1 + (n - 1) * ls + INK_BOT * lay.px, w: lay.w + 2 * TEXT_MARGIN }
}

// ── 색 ──
const near = (c, white) => { const m = /^#([0-9a-f]{6})$/i.exec(c || ''); if (!m) return false
  const n = parseInt(m[1], 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255; return white ? r >= 250 && g >= 250 && b >= 250 : false }
// 칠판 바탕 기본 잉크 — 밝은 화면은 흰 잉크를 검정으로, 어두운 화면은 검정 잉크를 흰색으로(데스크톱 `_DEFAULT_INK_DARK` #FFFFFF). 보드 안은 보드 색 기준이라 그대로
let DARK = false
export const setInkDark = v => { DARK = !!v }
// 검정 잉크 = 어둡고(밝기 < 64) 색이 옅은(최대−최소 ≤ 64) 색 — 검정·숯색·보드 남색 #1e2b45가 다 들어감. 옛 규칙(세 값 모두 ≤ 0x40)은 남색(파랑 0x45~0x4d)을 놓쳐
// 어두운 화면에서 판단·화살표·글이 바탕에 묻혔음(2026-10-19 점검). 짙은 빨강·초록처럼 색이 뚜렷한 것은 뜻이 있어 그대로
const nearBlack = c => { const m = /^#([0-9a-f]{6})$/i.exec(c || ''); if (!m) return false; const n = parseInt(m[1], 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255
  return 0.299 * r + 0.587 * g + 0.114 * b < 64 && Math.max(r, g, b) - Math.min(r, g, b) <= 64 }
export const ink = (c, onBoard) => { const css = cssColor(c); if (onBoard) return css; return DARK ? (nearBlack(css) ? '#ffffff' : css) : (near(css, true) ? '#1f1f1f' : css) }
// 딥모드 판 프레임 = 흰 종이(2026-10-25 사용자 「어두운 화면에서도 잘 보여야」) — 판의 제목·밑 글은 투명 메모(메모 글은 늘 검은 잉크)·흰 종이 기준 톤이라 어두운 칠판에 묻혔음.
// 판 = 인쇄하는 한 장이라 바탕째 종이로(메모 = 흰 종이 그대로와 같은 생각). 발표 화면은 프레임을 안 그려 종이만 네모로(`deepPaper`). 데스크톱 core_web `_FrameItem`도 같게
export const isDeepPaper = it => it.type === 'frame' && !!(it.deep_plan || it.deep_of)
export const deepPaper = it => ({ ...it, type: 'rect', fill: '#ffffff', style: 0, label: undefined, cuts: undefined })
// Qt QColor.darker(118)/lighter(135) — HSV 명도만
function shade(css, f) {
  const m = /^#([0-9a-f]{6})$/i.exec(css || ''); if (!m) return css
  const n = parseInt(m[1], 16); let [r, g, b] = [n >> 16, (n >> 8) & 255, n & 255]
  const mx = Math.max(r, g, b) || 1, v = Math.min(255, (mx * f)), k = v / mx
  return '#' + [r, g, b].map(c => Math.round(Math.min(255, c * k)).toString(16).padStart(2, '0')).join('')
}
const isDark = css => { const m = /^#([0-9a-f]{6})$/i.exec(css || ''); if (!m) return false; const n = parseInt(m[1], 16); return 0.299 * (n >> 16) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255) < 128 }

const stroke = (it, onBoard) => (it.style === 0 || !it.pen ? 'none' : ink(it.pen, onBoard))
// 선 굵기 — 아무리 줄여도 화면에서 1px 아래로는 안 가늘어짐(CAD식). 저장 굵기는 그대로, --z = 화면 배율(Editor가 칠판 묶음에 줌)
export const minStroke = w => ({ strokeWidth: `max(${w}px, calc(1px / var(--z, 1)))` })
const strokeProps = (it, onBoard) => ({ stroke: stroke(it, onBoard), style: minStroke(it.width || 1), strokeDasharray: dashArray(it.style, it.width), strokeLinecap: 'round', strokeLinejoin: 'round' })

// ── 도형 안 라벨(한 줄씩, 넘치면 글자를 줄임 — `_fit_label_to_shape`) ──
// 라벨이 그 크기(pt)로 줄지 않고 들어가려면 필요한 상자 폭 · 지금 실제로 보이는 크기 — 속성 카드 글자 크기가 씀(2026-10-23 사용자: 키워도 안 커짐 — 상자에 맞춰 줄었음)
export const labelNeedW = (it, pt) => { const L = it.label, lay = layoutText(L.text, L.runs, pt * PT, L.family ? 'board' : 'app'); return (lay.w + 2 * TEXT_MARGIN) / labelInset(it.type, it.kind) }
export function labelShownPt(it) {
  const L = it.label; let pt = Math.max(5, Math.round(L.font || 16)); if (L.align === 'left') return pt
  while (pt > 5 && labelNeedW(it, pt) > Math.max(1, it.rect[2])) pt -= 1
  return pt
}
function CenterLabel({ it, onBoard }) {
  const L = it.label; if (!L?.text) return null
  const [x, y, w] = it.rect, family = L.family ? 'board' : 'app'
  if (L.align === 'left') return <TextLines lay={leftLabelLayout(it)} left={x + LABEL_PAD} top={y + LABEL_PAD} color={ink(L.color, onBoard || !!it.fill)} ha={L.ha} />   // 왼쪽 위·줄바꿈(줄이지 않음)
  const inner = Math.max(1, w * labelInset(it.type, it.kind))
  let pt = Math.max(5, Math.round(L.font || 16)), lay = layoutText(L.text, L.runs, pt * PT, family)
  while (pt > 5 && lay.w + 2 * TEXT_MARGIN > inner) { pt -= 1; lay = layoutText(L.text, L.runs, pt * PT, family) }
  const a = labelAnchor(it.type, it.kind, it.rect, it), box = centeredBox(lay, a)
  const left = L.ha === 'left' ? a.x - inner / 2 : L.ha === 'right' ? a.x + inner / 2 - box.w : box.left   // 글 정렬(`label.ha`, 2026-10-27 밤) — 왼·오른쪽 = 도형 안 여백 끝에 붙음, 없으면 가운데(전과 같음)
  return <TextLines lay={lay} left={left} top={box.top} color={ink(L.color, onBoard || !!it.fill)} ha={L.ha || 'center'} />   // 가운데 = 줄마다 가운데(고치는 칸과 같게 — 전엔 덩어리만 가운데·줄은 왼쪽)   // 채운 도형 안 글은 도형 바탕을 따름(흰 글 그대로)
}

// 화살표 라벨(경로 위 t + 수직 off, 가운데) — 반환 { el, gap }
function arrowLabels(it, at, onBoard) {
  const labels = it.labels || (it.label ? [it.label] : [])   // 옛 파일은 단수 "label"(데스크톱도 하위호환으로 읽음)
  return labels.filter(L => L.text?.trim()).map((L, i) => {
    const lay = layoutText(L.text, L.runs, (L.font || 16) * PT, L.family ? 'board' : 'app')
    const { p, n } = at(L.t ?? 0.5), off = L.off || 0
    const box = centeredBox(lay, { x: p.x + n.x * off, y: p.y + n.y * off })
    const gap = off ? null : { x: box.left - 2, y: box.inkTop - 7, w: box.w + 4, h: box.inkBot - box.inkTop + 14 }   // 옆으로 뺀 라벨은 선을 안 비움
    return { el: <TextLines key={'l' + i} lay={lay} left={box.left} top={box.top} color={ink(L.color, onBoard)} halo={onBoard ? null : 'var(--mb-board, #ffffff)'} ha="center" />, gap }
  })
}
// 화살표 라벨 자리(화살표 안 좌표) — 편집 화면이 누르기·끌기·글 편집에 씀. → [{ i, left, top, w, h, a(앵커), n(왼쪽 법선) }]
export const arrowPath = (it, route) => it.type === 'sarrow' ? (route || it.pts).map(([x, y]) => ({ x, y })) : null
export function arrowAt(it, route) {
  if (it.type === 'sarrow') { const pts = arrowPath(it, route); return t => polylineAt(pts, t) }
  const p0 = { x: it.p1[0], y: it.p1[1] }, p3 = { x: it.p2[0], y: it.p2[1] }
  return it.ctrl1 ? t => curveAt(p0, { x: it.ctrl1[0], y: it.ctrl1[1] }, { x: it.ctrl2[0], y: it.ctrl2[1] }, p3, t) : t => polylineAt([p0, p3], t)
}
export function arrowLabelBoxes(it, route) {
  const at = arrowAt(it, route), labels = it.labels || (it.label ? [it.label] : [])
  return labels.map((L, i) => {
    const lay = layoutText(L.text || ' ', L.runs, (L.font || 16) * PT, L.family ? 'board' : 'app'), { p, n } = at(L.t ?? 0.5), off = L.off || 0
    const a = { x: p.x + n.x * off, y: p.y + n.y * off }, box = centeredBox(lay, a)
    return { i, left: box.left, top: box.top, w: box.w, h: lay.h + 2 * TEXT_MARGIN, a, n, empty: !L.text?.trim(),
      gap: off || !L.text?.trim() ? null : { x: box.left - 2, y: box.inkTop - 7, w: box.w + 4, h: box.inkBot - box.inkTop + 14 } }   // 그릴 때 비우는 자리와 같게
  })
}
const Head = ({ tri, color }) => <polygon points={tri.map(p => `${p.x},${p.y}`).join(' ')} fill={color} stroke={color} strokeWidth={1} strokeLinejoin="round" />

// ── TRIM 자국 있는 상자: 네 변(위·오른쪽·아래·왼쪽 — 데스크톱 `_item_local_edges` 차례)에서 자국 구간을 뺀 선 ──
function cutRectPath([x, y, w, h], cuts) {
  const edges = [[x, y, x + w, y], [x + w, y, x + w, y + h], [x + w, y + h, x, y + h], [x, y + h, x, y]]
  let d = ''
  edges.forEach(([x1, y1, x2, y2], i) => {
    const gaps = cuts.filter(c => c[0] === i).map(c => [Math.min(c[1], c[2]), Math.max(c[1], c[2])]).sort((a, b) => a[0] - b[0])
    let t = 0
    for (const [t0, t1] of [...gaps, [1, 1]]) {
      if (t0 > t) d += `M${x1 + (x2 - x1) * t},${y1 + (y2 - y1) * t} L${x1 + (x2 - x1) * t0},${y1 + (y2 - y1) * t0} `
      t = Math.max(t, t1)
    }
  })
  return d
}

// 네모 모서리 둥글기 — .ecad rect `radius`(2026-10-18, 반 변 넘지 않게)
export const rr = it => (it.radius ? Math.min(it.radius, Math.abs(it.rect[2]) / 2, Math.abs(it.rect[3]) / 2) : undefined)

// 포트(도형 테두리에 붙은 작은 상자·원) — 가운데 = 테두리 위 비율 자리
function Ports({ it, onBoard }) {
  const [x, y, w, h] = it.rect
  return (it.ports || []).map((p, i) => {
    const [pw, ph] = p.size || [18, 18], cx = x + p.frac[0] * w, cy = y + p.frac[1] * h
    const sp = { stroke: ink(p.pen, onBoard), strokeWidth: p.width || 1, fill: p.fill ? cssColor(p.fill) : '#ffffff' }   // 빈 포트도 밑의 테두리를 가림(데스크톱과 같게)
    return p.shape === 'circle' ? <ellipse key={i} cx={cx} cy={cy} rx={pw / 2} ry={ph / 2} {...sp} /> : <rect key={i} x={cx - pw / 2} y={cy - ph / 2} width={pw} height={ph} {...sp} />
  })
}

// ── 아이템 하나 ── (memo: 확대·이동만 바뀌면 다시 그리지 않음 — 9천 개 도면에서 휠 한 칸이 340ms였다)
// labels = 'inline'(기본 — 내보내기) | 'skip'(화살표 라벨은 빼고) | 'only'(화살표 라벨만 — 편집 화면이 모든 선 위에 한 번 더 그림)
// 종이틀 축척 — 틀이 용지의 k배 크기면 종이엔 1/k로 찍힘(「1:2.9」), 작으면 「2:1」. 1배 근처면 안 씀
export const scaleText = k => { k = k || 1; if (Math.abs(k - 1) < 0.01) return ''; return k > 1 ? ` · 1:${+k.toFixed(1)}` : ` · ${+(1 / k).toFixed(1)}:1` }
// 그래프 조각 → SVG(chart.js `chartScene`) — 마우스 올림 = 그 값(`tip`)
function chartPrim(p, k) {
  const tip = p.tip ? <title>{p.tip}</title> : null
  if (p.t === 'rect') return <rect key={k} x={p.x} y={p.y} width={p.w} height={p.h} rx={p.rx || 0} fill={p.f || 'none'} stroke={p.s || 'none'} strokeWidth={p.sw || 0}>{tip}</rect>
  if (p.t === 'line') return <line key={k} x1={p.x1} y1={p.y1} x2={p.x2} y2={p.y2} stroke={p.s} strokeWidth={p.sw} />
  if (p.t === 'path') return <path key={k} d={p.d} fill={p.f || 'none'} stroke={p.s || 'none'} strokeWidth={p.sw || 0} strokeLinejoin="round" strokeLinecap="round">{tip}</path>
  if (p.t === 'circle') return <circle key={k} cx={p.cx} cy={p.cy} r={p.r} fill={p.f} stroke={p.s} strokeWidth={p.sw}>{tip}</circle>
  return <text key={k} x={p.x} y={p.y} textAnchor={p.a} dominantBaseline="central" fontSize={p.fs} fontWeight={p.b ? 700 : 400} fontFamily={APP_FONT} fill={p.c} style={{ whiteSpace: 'pre' }}>{p.s}</text>
}
// 카드 속 페이지(iframe) — 칠판 안(foreignObject)과 휴대폰 위층(Editor `phoneCards`, 아이폰 Safari는 SVG 안 iframe에 칠판 배율을 안 먹임 — 2026-10-27)이 같이 씀
export function docFrame(it, bh, web) { const lv = isLive(it), k = it.rect[2] / (lv ? LIVE_W : 794)
  return lv
    ? <iframe data-docid={it._id} data-liveid={it._id} srcDoc={liveSrc(it.html)} title={it.title || '인터랙티브 HTML'} sandbox="allow-scripts" csp={LIVE_CSP} scrolling="no"
        style={{ border: 0, width: LIVE_W, height: bh / k, transform: `scale(${k})`, transformOrigin: '0 0', display: 'block', background: '#fff', pointerEvents: web === 'on' ? 'auto' : 'none' }} />
    : <iframe data-docid={it._id} srcDoc={it.html} title={it.title || '정리 문서'} sandbox="" scrolling="no"
        style={{ border: 0, width: 794, height: bh / k, transform: `scale(${k})`, transformOrigin: '0 0', display: 'block', background: '#fff', pointerEvents: 'none' }} /> }
export const webZoom = (it, fsScale) => (!isYoutube(it) && it.zoom > 0 && it.zoom < 1 ? it.zoom : isYoutube(it) && fsScale > 1 ? 1 / fsScale : 1)
export function webFrame(it, web, noFs, fsScale) { const zm = webZoom(it, fsScale)
  return <iframe data-webid={it._id} src={frameSrc(it, noFs)} title={it.title || it.url} allow="autoplay; encrypted-media; picture-in-picture; fullscreen; clipboard-write" allowFullScreen referrerPolicy="strict-origin-when-cross-origin"
    sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-forms allow-presentation" style={{ border: 0, width: `${100 / zm}%`, height: `${100 / zm}%`, transform: zm < 1 ? `scale(${zm})` : undefined, transformOrigin: '0 0', display: 'block', background: '#fff', pointerEvents: web === 'on' ? 'auto' : 'none' }} /> }

// 그림·심볼 진짜 뒤집기(`flip_h`·`flip_v`, edit.js `mirror` — 2026-10-27 밤) — 몸통만 상자 가운데 기준으로, 글은 그대로(읽게)
export const flipT = it => { if (!it.flip_h && !it.flip_v) return undefined; const [x, y, w, h] = it.rect, cx = x + w / 2, cy = y + h / 2
  return `translate(${cx},${cy}) scale(${it.flip_h ? -1 : 1},${it.flip_v ? -1 : 1}) translate(${-cx},${-cy})` }
export const Item = memo(function Item({ it, idx, onBoard, route, labels: lmode = 'inline', page, web, noFs, ytBig, fsScale }) {   // noFs·ytBig·fsScale = 발표 화면(유튜브 전체 화면 단추 숨김 · 크게 보는 중 · 화면 배율)   // web = 웹 카드 칸 안 페이지: 없음 = 그림 카드(내보내기·장 목록), 'view' = 보이기만(누르면 칠판이 받음), 'on' = 조작 중   // page = 종이틀 쪽 번호(편집 화면만)   // props의 dark: 화면이 바뀌면 다시 그리게(memo가 props를 비교)
  const T = itemTransform(it), fill = it.fill ? cssColor(it.fill) : 'none'
  if (lmode === 'only' && it.type !== 'sarrow' && it.type !== 'arrow') return null
  switch (it.type) {
    case 'rect': case 'ellipse': case 'symbol': {
      const [x, y, w, h] = it.rect
      let body
      if (it.type === 'rect') body = it.cuts?.length
        ? <><rect x={x} y={y} width={w} height={h} fill={fill} stroke="none" /><path d={cutRectPath(it.rect, it.cuts)} fill="none" {...strokeProps(it, onBoard)} /></>
        : <rect x={x} y={y} width={w} height={h} rx={rr(it)} ry={rr(it)} fill={fill} {...strokeProps(it, onBoard)} />
      else if (it.type === 'ellipse') body = <ellipse cx={x + w / 2} cy={y + h / 2} rx={w / 2} ry={h / 2} fill={fill} {...strokeProps(it, onBoard)} />
      else body = <g transform={`${flipT(it) || ''} translate(${x},${y})`}><path d={symbolPath(it.kind, w, h).d} fill={fill} {...strokeProps(it, onBoard)} /></g>
      return <g transform={T}>{body}<Ports it={it} onBoard={onBoard} /><CenterLabel it={it} onBoard={onBoard} /></g>
    }
    case 'polygon': {
      const pts = it.pts.map(p => p.join(',')).join(' ')
      return <g transform={T}>{it.closed ? <polygon points={pts} fill={fill} {...strokeProps(it, onBoard)} /> : <polyline points={pts} fill="none" {...strokeProps(it, onBoard)} />}
        {it.closed && <CenterLabel it={it} onBoard={onBoard} />}</g>
    }
    case 'path': {
      const d = it.elements.map(e => e[0] + e.slice(1).join(' ')).join(' ')
      return <g transform={T}><path d={d} fill={fill} fillRule="evenodd" {...strokeProps(it, onBoard)} stroke={it.width ? stroke(it, onBoard) : 'none'} /></g>
    }
    case 'line': {
      const [x1, y1, x2, y2] = it.line, L = it.label
      let label = null
      if (L?.text) {   // 선 라벨: 가운데 '위쪽'(문서 상자 아래가 중점보다 4 위)
        const lay = layoutText(L.text, L.runs, (L.font || 16) * PT, L.family ? 'board' : 'app')
        const a = { x: (x1 + x2) / 2, y: (y1 + y2) / 2 }
        label = <TextLines lay={lay} left={a.x - lay.w / 2 - TEXT_MARGIN} top={a.y - 4 - (lay.h + 2 * TEXT_MARGIN)} color={ink(L.color, onBoard)} ha="center" />
      }
      return <g transform={T}><line x1={x1} y1={y1} x2={x2} y2={y2} {...strokeProps(it, onBoard)} />{label}</g>
    }
    case 'text': {
      const family = it.family ? 'board' : 'app', weight = it.weight ?? (it.bold ? 700 : 400)
      const lay = layoutText(it.text, it.runs, (it.font || 12) * PT, family, weight)
      return <g transform={T}>
        {it.bg && <rect x={0} y={0} width={lay.w + 2 * TEXT_MARGIN} height={lay.h + 2 * TEXT_MARGIN} fill={bgCss(it.bg)} />}
        <TextLines lay={lay} left={0} top={0} color={ink(it.color, onBoard)} ha={it.ha} />
      </g>
    }
    case 'image': {
      const [x, y, w, h] = it.rect
      return <g transform={T}><image href={'data:image/png;base64,' + it.data} x={x} y={y} width={w} height={h} preserveAspectRatio="none" transform={flipT(it)} /></g>
    }
    case 'board': {
      const [x, y, w, h] = it.rect, bg = cssColor(it.bg) || '#ffffff'
      return <g transform={T}><rect x={x} y={y} width={w} height={h} rx={14} ry={14} fill={bg} stroke={isDark(bg) ? shade(bg, 1.35) : shade(bg, 1 / 1.18)} strokeWidth={1.2} /></g>
    }
    case 'badge': {
      const c = cssColor(it.color) || '#da7756'
      return <g transform={T}><circle r={15} fill={c} stroke="#fff" strokeWidth={2} />
        <text y={0} textAnchor="middle" dominantBaseline="central" fontSize={12 * PT} fontWeight={700} fontFamily={APP_FONT} fill="#fff">{it.number}</text></g>
    }
    case 'table': {
      if (isChart(it)) return <g transform={T} data-chart={it.chart}>{chartScene(it).map(chartPrim)}</g>   // 그래프 = 표 + 모양(chart.js) — 숫자를 못 읽게 되면 표로
      const [x, y, w, h] = it.rect, rows = it.rows, edges = colEdges(x, w, colFracs(it)), re = rowEdges(y, h, it)
      const cells = []
      for (let r = 0; r < rows; r++) for (let c = 0; c < it.cols; c++) {
        const txt = it.cells?.[r]?.[c], cs = cellStyle(it, r, c), cw = edges[c + 1] - edges[c], ch = re[r + 1] - re[r]
        if (cs.fill) cells.push(<rect key={`f${r}-${c}`} x={edges[c]} y={re[r]} width={cw} height={ch} fill={cssColor(cs.fill)} />)   // 칸 채움(글 밑)
        if (!txt) continue
        const out = cells, cellsAt = cells.length
        const fs = cellFontPx(txt, cw, ch, cs.bold, cs.px), al = cs.align, base = ink(cs.color || '#111111', onBoard || !!cs.fill), runs = it.cell_runs?.[`${r},${c}`]
        if (runs?.length) {   // 부분 서식 — 조각마다 자리를 재서 그림(형광펜 바탕 포함)
          const parts = runsToLines(txt, runs)[0] || [], ws = parts.map(p => measure(p.text, fs, 'app', p.bold || cs.bold ? 700 : 400)), tw = ws.reduce((a, b) => a + b, 0)
          let px = al === 'left' ? edges[c] + 3 : al === 'right' ? edges[c + 1] - 3 - tw : (edges[c] + edges[c + 1]) / 2 - tw / 2
          const cy = (re[r] + re[r + 1]) / 2
          parts.forEach((p, j) => { if (p.bg) cells.push(<rect key={`h${r}-${c}-${j}`} x={px} y={cy - fs * 0.6} width={ws[j]} height={fs * 1.2} fill={bgCss(p.bg)} />)
            const fc = p.color ? cssColor(p.color) : base, th = Math.max(0.6, fs * 0.06)
            cells.push(<text key={`${r}-${c}-${j}`} x={px} y={cy} dominantBaseline="central" fontSize={fs} fontWeight={p.bold || cs.bold ? 700 : 400} fontStyle={p.deco?.includes('i') ? 'italic' : undefined} fontFamily={APP_FONT} fill={fc} style={{ whiteSpace: 'pre' }}>{p.text}</text>)
            if (p.deco?.includes('u')) cells.push(<rect key={`du${r}-${c}-${j}`} x={px} y={cy + fs * 0.42} width={ws[j]} height={th} fill={fc} />)   // 밑줄·취소선(2026-10-19 — 칸도 칠판 글과 같게)
            if (p.deco?.includes('s')) cells.push(<rect key={`ds${r}-${c}-${j}`} x={px} y={cy - th / 2} width={ws[j]} height={th} fill={fc} />)
            px += ws[j] })
          out.push(clipCell(out.splice(cellsAt), edges[c], re[r], cw, ch, `${r}-${c}`))
          continue
        }
        cells.push(<text key={`${r}-${c}`} x={al === 'left' ? edges[c] + 3 : al === 'right' ? edges[c + 1] - 3 : (edges[c] + edges[c + 1]) / 2} y={(re[r] + re[r + 1]) / 2} textAnchor={al === 'left' ? 'start' : al === 'right' ? 'end' : 'middle'} dominantBaseline="central"
          fontSize={fs} fontWeight={cs.bold ? 700 : 400} fontFamily={APP_FONT} fill={base}>{txt}</text>)   // 채운 칸 안 글 = 제 색(채운 도형 라벨과 같은 규칙)
        out.push(clipCell(out.splice(cellsAt), edges[c], re[r], cw, ch, `${r}-${c}`))
      }
      const lines = [...edges.slice(1, -1).map(ex => `M${ex},${y} V${y + h}`), ...re.slice(1, -1).map(ey => `M${x},${ey} H${x + w}`)]
      const tl = ink(it.pen || '#333333', onBoard)
      return <g transform={T}>{cells}<path d={lines.join(' ')} stroke={tl} strokeWidth={0.5} fill="none" />
        {it.header && rows > 1 && <path d={`M${x},${re[1]} H${x + w}`} stroke={tl} strokeWidth={1} />}
        <rect x={x} y={y} width={w} height={h} fill="none" stroke={tl} strokeWidth={1} /></g>
    }
    case 'web': {   // 웹 카드 — 위 띠(제목·주소·새 탭 단추) + 칸 안 페이지(들어가는 사이트, 편집·발표 화면만) 또는 대표 그림
      const [x, y, w, h] = it.rect, H = Math.min(WEB_HEAD, h), bh = h - H, cid = 'wc-' + (it._id || idx), ob = openBtnRect(it), ic = it.icon ? 16 : 0, tx = x + 10 + (ic && ic + 6), yl = noFs && isYoutube(it) ? 104 : 0, tw = w - ob.w - 26 - (ic && ic + 6) - yl   // yl = 발표의 「⤢ 크게 보기」 자리
      const live = (web === 'on' || web === 'view') && it.frameable && bh > 4   // 'sleep' = 많이 줄여 봄 → 페이지 끔(그림·이름만)
      const zm = webZoom(it, fsScale)   // 칸 안 페이지 배율 — 큰 판에 띄우고 통째로 줄임.
      // 발표의 유튜브 = 화면에 보이는 크기의 판에 띄우고 줄임(작은 판을 확대하면 유튜브 단추가 몇 배로 커 보였음 — 2026-10-20 사용자)
      const info = () => { const s = Math.min(36, bh - 16), lw = w - s - 34, lines = wrap2(it.desc || siteOf(it.url), 12, lw)   // 막힌 사이트·그림 없음 = 아이콘 + 설명 두 줄
        return <>{it.icon ? <image href={it.icon} x={x + 12} y={y + H + (bh - s) / 2} width={s} height={s} />
          : <><rect x={x + 12} y={y + H + (bh - s) / 2} width={s} height={s} rx={s / 4} fill="#e4e4e7" /><text x={x + 12 + s / 2} y={y + H + bh / 2} textAnchor="middle" dominantBaseline="central" fontSize={s / 2} fontWeight={700} fontFamily={APP_FONT} fill="#71717a">{siteOf(it.url).slice(0, 1).toUpperCase()}</text></>}
          {lines.map((t, k) => <text key={k} x={x + s + 22} y={y + H + bh / 2 + (k - (lines.length - 1) / 2) * 17} dominantBaseline="central" fontSize={12} fontFamily={APP_FONT} fill="#52525b">{t}</text>)}</> }
      // data-web-* = HTML 공유 파일이 카드를 누르면 그 자리에 실제 페이지를 끼울 때 씀(htmlshare.js — 2026-10-19 사용자)
      return <g transform={T} data-web-url={it.url} data-web-src={it.frameable && bh > 4 ? frameSrc(it) : undefined} data-web-box={`${x},${y + H},${w},${bh}`} data-web-head={h > 0 ? (H / h).toFixed(3) : 1} data-web-zoom={zm < 1 ? zm : undefined}>
        <clipPath id={cid}>{ytBig ? <rect x={x} y={y + H} width={w} height={bh} /> : <rect x={x} y={y} width={w} height={h} rx={8} ry={8} />}</clipPath>
        <g clipPath={`url(#${cid})`}>
          {!ytBig && <><rect x={x} y={y} width={w} height={h} fill="#ffffff" />
          <rect x={x} y={y} width={w} height={H} fill="#f4f4f5" /></>}
          {bh > 0 && (live
            ? <foreignObject x={x} y={y + H} width={w} height={bh}>{webFrame(it, web, noFs, fsScale)}</foreignObject>   // sandbox = 칠판 화면을 통째로 다른 주소로 넘기지 못하게(일부 사이트의 「틀 벗어나기」)
            : web === 'shell' ? <rect x={x} y={y + H} width={w} height={bh} fill="#ffffff" />   // 몸통은 휴대폰 위층이 그림
            : it.thumb ? <image href={it.thumb} x={x} y={y + H} width={w} height={bh} preserveAspectRatio="xMidYMid slice" />
            : !it.embed && bh >= 30 ? <><rect x={x} y={y + H} width={w} height={bh} fill="#ffffff" />{info()}</>
            : <><rect x={x} y={y + H} width={w} height={bh} fill="#e4e4e7" />
              <text x={x + w / 2} y={y + H + bh / 2} textAnchor="middle" dominantBaseline="central" fontSize={Math.min(28, bh / 3)} fontFamily={APP_FONT} fill="#71717a">{it.embed ? '▶' : siteOf(it.url)}</text></>)}
        </g>
        {!ytBig && <>   {/* 크게 보는 중(발표) = 몸통만 — 위 띠·테두리는 숨김 */}
        {bh > 0 && <path d={`M${x},${y + H} H${x + w}`} stroke="#d4d4d8" strokeWidth={1} />}
        <rect x={x} y={y} width={w} height={h} rx={8} ry={8} fill="none" stroke="#a1a1aa" strokeWidth={1} />
        {ic > 0 && <image href={it.icon} x={x + 10} y={y + (Math.min(WEB_HEAD, h) - ic) / 2} width={ic} height={ic} />}
        <text x={tx} y={y + 15} dominantBaseline="central" fontSize={13} fontWeight={700} fontFamily={APP_FONT} fill="#18181b">{ellipsis(it.title || siteOf(it.url), 13, 700, tw)}</text>
        <text x={tx} y={y + 31} dominantBaseline="central" fontSize={10} fontFamily={APP_FONT} fill="#71717a">{ellipsis(it.url, 10, 400, tw)}</text>
        {yl > 0 && <g style={{ cursor: 'pointer' }}><rect x={ob.x - yl} y={ob.y} width={yl - 6} height={ob.h} rx={5} fill={ytBig ? '#da7756' : '#ffffff'} stroke={ytBig ? '#da7756' : '#d4d4d8'} />
          <text x={ob.x - yl + (yl - 6) / 2} y={ob.y + ob.h / 2} textAnchor="middle" dominantBaseline="central" fontSize={11} fontWeight={600} fontFamily={APP_FONT} fill={ytBig ? '#ffffff' : '#3f3f46'}>{ytBig ? '⤡ 원래대로' : '⤢ 크게 보기 (F)'}</text></g>}
        <g><title>새 탭에서 열기</title><rect x={ob.x} y={ob.y} width={ob.w} height={ob.h} rx={5} fill="#ffffff" stroke="#d4d4d8" />
          <path d={`M${ob.x + 10},${ob.y + 7} H${ob.x + 17} V${ob.y + 14} M${ob.x + 17},${ob.y + 7} L${ob.x + 8},${ob.y + 16}`} fill="none" stroke="#52525b" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" /></g>
        </>}
      </g>
    }
    case 'doc': {   // 정리 문서 카드(「정리해 줘」 ①, 2026-10-19) — 위 띠(📄 제목·↗ 크게 보기) + 칸 안에 AI가 쓴 HTML(A4 폭 794px를 카드 폭에 맞춰 줄임, 스크립트 없는 iframe).
      // 'sleep'(많이 줄여 봄)·내보내기·HTML 공유는 문서 대신 제목 자리만(iframe은 그림으로 안 찍힘)
      // 움직이는 카드(`live`, §8 항목66 4단계) = 같은 카드에 스크립트만 켠 틀(livecard.js) — 기준 폭 720, 'on'(두 번 누름)일 때만 칸 안을 누를 수 있음. 내보내기엔 틀 글(data-live-src)을 남겨 HTML 공유가 띄움
      const [x, y, w, h] = it.rect, H = Math.min(WEB_HEAD, h), bh = h - H, cid = 'dc-' + (it._id || idx), ob = openBtnRect(it), tw = w - ob.w - 26
      const lv = isLive(it), fits = liveFits(it), k = w / (lv ? LIVE_W : 794)
      const live = (web === 'on' || web === 'view') && bh > 4 && it.html && (!lv || fits)
      return <g transform={T} data-doc-box={`${x},${y + H},${w},${bh}`} data-live-src={lv && fits && !web ? liveSrc(it.html) : undefined}>
        <clipPath id={cid}><rect x={x} y={y} width={w} height={h} rx={6} ry={6} /></clipPath>
        <g clipPath={`url(#${cid})`}>
          <rect x={x} y={y} width={w} height={h} fill="#ffffff" />
          <rect x={x} y={y} width={w} height={H} fill="#f5f3ff" />
          {bh > 0 && (live
            ? <foreignObject x={x} y={y + H} width={w} height={bh}>{docFrame(it, bh, web)}</foreignObject>
            : web === 'shell' ? <rect x={x} y={y + H} width={w} height={bh} fill="#ffffff" />   // 몸통은 휴대폰 위층이 그림
            : <><rect x={x} y={y + H} width={w} height={bh} fill="#fafafa" />
              <text x={x + w / 2} y={y + H + bh / 2} textAnchor="middle" dominantBaseline="central" fontSize={Math.min(16, bh / 6)} fontFamily={APP_FONT} fill="#8a8f98">{lv ? (fits ? '▶ 인터랙티브 HTML — 칠판에서 두 번 눌러 움직여 보세요' : '▶ 인터랙티브 HTML — 너무 커서 못 띄워요') : '📄 정리 문서 — ↗로 크게 보기·인쇄'}</text></>)}
        </g>
        {bh > 0 && <path d={`M${x},${y + H} H${x + w}`} stroke="#ddd6fe" strokeWidth={1} />}
        <rect x={x} y={y} width={w} height={h} rx={6} ry={6} fill="none" stroke={web === 'on' ? '#da7756' : '#a78bfa'} strokeWidth={web === 'on' ? 2 : 1} />
        <text x={x + 10} y={y + 15} dominantBaseline="central" fontSize={13} fontWeight={700} fontFamily={APP_FONT} fill="#18181b">{ellipsis((lv ? '▶ ' : '📄 ') + (it.title || (lv ? '인터랙티브 HTML' : '정리 문서')), 13, 700, tw)}</text>
        <text x={x + 10} y={y + 31} dominantBaseline="central" fontSize={10} fontFamily={APP_FONT} fill="#71717a">{ellipsis(it.file ? `HTML 파일 · ${it.file}` : `${lv ? '인터랙티브 HTML' : '정리 문서'} · KAIROS ${it.model || ''}`, 10, 400, tw)}</text>
        <g><title>크게 보기 · 인쇄</title><rect x={ob.x} y={ob.y} width={ob.w} height={ob.h} rx={5} fill="#ffffff" stroke="#d4d4d8" />
          <path d={`M${ob.x + 10},${ob.y + 7} H${ob.x + 17} V${ob.y + 14} M${ob.x + 17},${ob.y + 7} L${ob.x + 8},${ob.y + 16}`} fill="none" stroke="#52525b" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" /></g>
      </g>
    }
    case 'pdf': {   // PDF 보기 카드(2026-10-21) — 위 띠(📕 파일 이름·쪽 수·↗ 원본) + 칸 안 쪽 그림(편집·발표 화면, `pdfcard.jsx`). 서버 없이(내보내기·HTML 공유) = 첫 쪽 작은 그림
      const [x, y, w, h] = it.rect, H = Math.min(WEB_HEAD, h), bh = h - H, cid = 'pc-' + (it._id || idx), ob = openBtnRect(it), tw = w - ob.w - 26
      const live = (web === 'on' || web === 'view') && bh > 4 && it.url
      return <g transform={T}>
        <clipPath id={cid}><rect x={x} y={y} width={w} height={h} rx={6} ry={6} /></clipPath>
        <g clipPath={`url(#${cid})`}>
          <rect x={x} y={y} width={w} height={h} fill="#ffffff" />
          <rect x={x} y={y} width={w} height={H} fill="#fef2f2" />
          {bh > 0 && (live
            ? <foreignObject x={x} y={y + H} width={w} height={bh}><PdfPages it={it} w={w} h={bh} on={web === 'on'} /></foreignObject>
            : web === 'sleep' && it.url && pdfPageAt(it, 0) > 0 ? <><rect x={x} y={y + H} width={w} height={bh} fill="#e4e4e7" /><image href={`${it.url}/page/${pdfPageAt(it, 0)}?w=320`} x={x} y={y + H} width={w} height={bh} preserveAspectRatio="xMidYMin meet" /></>   // 멀리서 잠든 카드 = 보던 쪽(첫 쪽으로 돌아가 보이지 않게)
            : it.thumb ? <><rect x={x} y={y + H} width={w} height={bh} fill="#e4e4e7" /><image href={it.thumb} x={x} y={y + H} width={w} height={it.sizes?.[0] ? w * it.sizes[0][1] / it.sizes[0][0] : bh} preserveAspectRatio="xMidYMin meet" /></>
            : <rect x={x} y={y + H} width={w} height={bh} fill="#e4e4e7" />)}
        </g>
        {bh > 0 && <path d={`M${x},${y + H} H${x + w}`} stroke="#fecaca" strokeWidth={1} />}
        <rect x={x} y={y} width={w} height={h} rx={6} ry={6} fill="none" stroke={web === 'on' ? '#da7756' : '#f87171'} strokeWidth={web === 'on' ? 2 : 1} />
        <text x={x + 10} y={y + 15} dominantBaseline="central" fontSize={13} fontWeight={700} fontFamily={APP_FONT} fill="#18181b">{ellipsis('📕 ' + (it.name || 'PDF'), 13, 700, tw)}</text>
        <text x={x + 10} y={y + 31} dominantBaseline="central" fontSize={10} fontFamily={APP_FONT} fill="#71717a">{ellipsis(`PDF · ${it.pages || 0}쪽`, 10, 400, tw)}</text>
        <g><title>원본 PDF 새 탭에서 열기</title><rect x={ob.x} y={ob.y} width={ob.w} height={ob.h} rx={5} fill="#ffffff" stroke="#d4d4d8" />
          <path d={`M${ob.x + 10},${ob.y + 7} H${ob.x + 17} V${ob.y + 14} M${ob.x + 17},${ob.y + 7} L${ob.x + 8},${ob.y + 16}`} fill="none" stroke="#52525b" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" /></g>
      </g>
    }
    case 'memo': {   // 메모 — 채운 둥근 네모 + 줄마다 글(제목·목록 표·할 일 상자·인용 막대·코드)
      const [x, y, w, h] = it.rect, ml = memoLayout(it), ink0 = ink('#ff1f1f1f', true), fillC = it.fill ? cssColor(it.fill) : '#ffffff'
      return <g transform={T}>
        <rect x={x} y={y} width={w} height={h} rx={10} ry={10} fill={fillC} stroke={it.pen ? cssColor(it.pen) : '#d4d4d8'} strokeWidth={1} />
        {ml.rows.map(({ ln, i, x: lx, y: ly, lay, px, marker, box, cy, lh, hr, table: tb }) => {
          if (hr) return <line key={i} x1={x + lx} x2={x + w - MEMO.PAD} y1={y + cy} y2={y + cy} stroke="#d4d4d8" strokeWidth={1} />
          if (tb) { const X = x + lx, Y = y + ly, H = tb.rowY[tb.rowY.length - 1]
            return <g key={i}>
              {ln.header && <rect x={X} y={Y} width={tb.w} height={tb.rowY[1]} fill="#f4f4f5" />}
              {tb.cells.map((c, j) => <TextLines key={j} lay={c.lay} left={X + c.x} top={Y + c.y} color={ink0} />)}
              <path d={[...tb.rowY.map(ry => `M${X},${Y + ry} H${X + tb.w}`), ...tb.xs.map(cx => `M${X + cx},${Y} V${Y + H}`)].join(' ')} stroke="#d4d4d8" strokeWidth={1} fill="none" />
            </g> }
          const done = ln.k === 'todo' && ln.done, col = done || ln.more ? MUTED : ln.k === 'quote' ? '#52525b' : ink0
          return <g key={ln.more ? 'more' : i} data-memo-more={ln.more || undefined}>
            {ln.k === 'quote' && <rect x={x + MEMO.LPAD} y={y + ly + (ml.rows[i].joinPrev ? TEXT_MARGIN : 0)} width={3} height={lay.h + (ml.rows[i].joinPrev ? 0 : TEXT_MARGIN) + (ml.rows[i].joinNext ? 0 : TEXT_MARGIN)} fill="#d4d4d8" />}
            {ln.k === 'code' && <rect x={x + lx - 4} y={y + ly + (ml.rows[i].joinPrev ? TEXT_MARGIN : 0)} width={w - MEMO.PAD - lx + 8} height={lay.h + (ml.rows[i].joinPrev ? 0 : TEXT_MARGIN) + (ml.rows[i].joinNext ? 0 : TEXT_MARGIN)} fill={CODE_BAND} />}   {/* 코드 블록 = 한 덩어리 바탕(빈 줄·여백까지 — 줄마다 칠하면 빈 줄에서 끊겨 여러 칸으로 보였음, 2026-10-19 사용자) */}
            {marker && <text x={x + lx - 6} y={y + cy} textAnchor="end" dominantBaseline="central" fontSize={px} fontFamily={BOARD_FONT} fill={ink0} style={{ fontVariantNumeric: 'tabular-nums' }}>{marker[0]}</text>}
            {box && <g><rect x={x + box.x} y={y + box.y} width={box.s} height={box.s} rx={box.s * 0.18} fill={ln.done ? '#2f80ed' : '#ffffff'} stroke={ln.done ? '#2f80ed' : '#a1a1aa'} strokeWidth={1.2} />
              {ln.done && <path d={`M${x + box.x + box.s * 0.22},${y + box.y + box.s * 0.52} L${x + box.x + box.s * 0.43},${y + box.y + box.s * 0.72} L${x + box.x + box.s * 0.8},${y + box.y + box.s * 0.3}`} fill="none" stroke="#fff" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" />}</g>}
            <TextLines lay={lay} left={x + lx - TEXT_MARGIN} top={y + ly} color={col} band={ln.k !== 'code'} />
            {done && lay.lines.map((l, j) => <path key={'s' + j} d={`M${x + lx},${y + ly + TEXT_MARGIN + (j + 0.55) * lh} H${x + lx + l.w}`} stroke={MUTED} strokeWidth={1} />)}
          </g> })}
      </g>
    }
    case 'legend': {   // 범례(2026-10-19) — 제목 + 표(견본 선 | 이름 | 모양). 줄은 도면에서 저절로(legend.js syncLegends)
      const [x, y, w, h] = it.rect, L = LEGEND, lo = legendLayout(it), rows = it.rows || [], [c0, c1, c2] = lo.cols, ty = y + L.HEAD, line = '#e4e4e7', mut = '#71717a'
      const rowY = j => ty + L.ROW * (j + 1)
      return <g transform={T}>
        <rect x={x} y={y} width={w} height={h} rx={8} ry={8} fill="#ffffff" stroke="#d4d4d8" strokeWidth={1} />
        <text x={x + L.PAD} y={y + L.HEAD / 2 + 1} dominantBaseline="central" fontSize={L.TITLE} fontWeight={700} fontFamily={APP_FONT} fill="#18181b">{it.title || '범례'}</text>
        <rect x={x + 1} y={ty} width={w - 2} height={L.ROW} fill="#f4f4f5" />
        {[['견본', c0], ['이름', c1], ['모양', c2]].map(([t, cx]) => <text key={t} x={x + cx} y={ty + L.ROW / 2} dominantBaseline="central" fontSize={lo.px - 1} fontWeight={600} fontFamily={APP_FONT} fill={mut}>{t}</text>)}
        <path d={[0, ...rows.map((_, j) => j + 1)].map(j => `M${x},${rowY(j)} H${x + w}`).join(' ') + ` M${x},${ty} H${x + w} M${x + c1 - L.GAP / 2},${ty} V${rowY(rows.length)} M${x + c2 - L.GAP},${ty} V${rowY(rows.length)}`} stroke={line} strokeWidth={1} fill="none" />
        {rows.map((e, j) => { const cy = rowY(j) + L.ROW / 2, col = e.color, x1 = x + c0, x2 = x + c0 + L.SAMPLE, hw = Math.min(e.width, 4)
          return <g key={e.key}>
            <path d={`M${x1},${cy} H${x2 - (e.arrow ? 6 + hw : 0)}`} stroke={cssColor(col)} strokeWidth={Math.min(e.width, 6)} strokeDasharray={dashArray(e.style, Math.min(e.width, 6))} strokeLinecap="round" fill="none" />
            {e.arrow && <path d={`M${x2},${cy} L${x2 - 8 - hw},${cy - 4 - hw / 2} L${x2 - 8 - hw},${cy + 4 + hw / 2} Z`} fill={cssColor(col)} />}
            <text x={x + c1} y={cy} dominantBaseline="central" fontSize={lo.px} fontFamily={APP_FONT} fill="#27272a">{rowName(it, e)}</text>
            <text x={x + c2} y={cy} dominantBaseline="central" fontSize={lo.px} fontFamily={APP_FONT} fill={mut}>{descOf(e)}</text></g> })}
        {!rows.length && <text x={x + L.PAD} y={rowY(0) + L.ROW / 2} dominantBaseline="central" fontSize={lo.px} fontFamily={APP_FONT} fill={mut}>색 있는 선·화살표를 그리면 저절로 채워져요</text>}
      </g>
    }
    case 'frame': {   // 프레임 — 얇은 테두리 + 위 왼쪽 이름표(Lucid Frame·Figma Section). 안은 비움(위에 그림)
      const [x, y, w, h] = it.rect, fs = frameTagFs(it), tag = frameTag({ ...it, no: page ?? it.no }), tw = measure(tag, fs, 'app', 600) + fs
      return <g transform={T}><rect x={x} y={y} width={w} height={h} fill={isDeepPaper(it) ? '#ffffff' : 'none'} stroke="var(--mb-muted, #8a98a8)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" />
        <rect x={x} y={y - fs * 1.7} width={tw} height={fs * 1.45} rx={fs * 0.3} fill="#3f3f46" />
        <text x={x + fs / 2} y={y - fs * 0.97} dominantBaseline="central" fontSize={fs} fontWeight={600} fontFamily={APP_FONT} fill="#ffffff">{tag}</text></g>
    }
    case 'titleblock': {
      const [W, H] = paperWH(it.size, it.orient), M = 10, line = ink('#333333', onBoard), inkC = ink('#111111', onBoard)
      if (it.plain) return <g transform={T}>   {/* 종이틀(2026-10-18) — 화면에선 옅은 종이 면 + 쪽 이름, 내보내기 그림엔 테두리만 */}
        {page != null && <rect width={W} height={H} fill="var(--mb-paper, rgba(127,127,127,.06))" stroke="none" />}
        <rect width={W} height={H} fill="none" stroke={page != null ? 'var(--mb-muted, #8a98a8)' : line} style={page != null ? minStroke(0.4) : undefined} strokeWidth={0.5} strokeDasharray={page != null ? '4 3' : undefined} />
        {page != null && <text x={0} y={-3} fontSize={Math.min(W, H) * 0.035} fontFamily={APP_FONT} fill="var(--mb-muted, #8a98a8)">{page}쪽 · {it.size} {it.orient === 'landscape' ? '가로' : '세로'}{scaleText(it.scale)}</text>}
      </g>
      const tbw = Math.min(180, W - 2 * M), tb = { x: W - M - tbw, y: H - M - 33, w: tbw, h: 33 }
      const hW = TB_ROWS.reduce((s, r) => s + r[0], 0), out = []
      let yy = tb.y
      TB_ROWS.forEach(([rw, cells], ri) => {
        const rh = tb.h * (rw / hW), cW = cells.reduce((s, c) => s + c[2], 0)
        if (ri > 0) out.push(<line key={'r' + ri} x1={tb.x} y1={yy} x2={tb.x + tb.w} y2={yy} stroke={line} strokeWidth={0.5} />)
        let xx = tb.x
        cells.forEach(([label, key, cw], ci) => {
          const cwid = tb.w * (cw / cW)
          if (ci > 0) out.push(<line key={`c${ri}-${ci}`} x1={xx} y1={yy} x2={xx} y2={yy + rh} stroke={line} strokeWidth={0.5} />)
          out.push(<text key={`l${ri}-${ci}`} x={xx + 1.2} y={yy + 1.2} dominantBaseline="hanging" fontSize={2.6} fontFamily={APP_FONT} fill={inkC}>{label}</text>)
          const v = it.fields?.[key]
          if (v) out.push(<text key={`v${ri}-${ci}`} x={xx + cwid / 2} y={yy + rh / 2} textAnchor="middle" dominantBaseline="central" fontSize={3.8} fontFamily={APP_FONT} fill={inkC}>{v}</text>)
          xx += cwid
        })
        yy += rh
      })
      return <g transform={T}><rect width={W} height={H} fill="none" stroke={line} strokeWidth={0.5} />
        <rect x={M} y={M} width={W - 2 * M} height={H - 2 * M} fill="none" stroke={line} strokeWidth={1.2} />
        <rect x={tb.x} y={tb.y} width={tb.w} height={tb.h} fill="none" stroke={line} strokeWidth={1.2} />{out}</g>
    }
    case 'sarrow': {
      const pts = (route || it.pts).map(([x, y]) => ({ x, y })), color = ink(it.color, onBoard), size = headSize(it.width, it.head_scale)   // route = 열 때 다시 찾은 길(arrows.js)
      const end = it.head !== false, start = !!it.head_start
      const labels = arrowLabels(it, t => polylineAt(pts, t), onBoard), gaps = labels.map(l => l.gap).filter(Boolean)
      const tri = (a, b) => headTriangle(b, Math.atan2(b.y - a.y, b.x - a.x), size)
      const body = cutPolyline(trimmedPts(pts, size, end, start), gaps).map(q => roundedPath(q, sarrowRadius(it))).join(' ')   // 라벨 자리는 계산으로 잘라 비움
      if (lmode === 'only') return <g transform={T}>{labels.map(l => l.el)}</g>
      return <g transform={T}>
        <path d={body} fill="none" stroke={color} style={minStroke(it.width)}
          strokeDasharray={dashArray(it.style, it.width)} strokeLinecap="round" strokeLinejoin="round" />
        {end && <Head tri={tri(pts[pts.length - 2], pts[pts.length - 1])} color={color} />}
        {start && <Head tri={tri(pts[1], pts[0])} color={color} />}
        {lmode === 'inline' && labels.map(l => l.el)}
      </g>
    }
    case 'arrow': {
      const p0 = { x: it.p1[0], y: it.p1[1] }, p3 = { x: it.p2[0], y: it.p2[1] }, color = ink(it.color, onBoard), size = headSize(it.width, it.head_scale)
      const end = it.head !== false, start = !!it.head_start, curved = !!it.ctrl1
      const c1 = curved ? { x: it.ctrl1[0], y: it.ctrl1[1] } : null, c2 = curved ? { x: it.ctrl2[0], y: it.ctrl2[1] } : null
      const at = curved ? t => curveAt(p0, c1, c2, p3, t) : t => polylineAt([p0, p3], t)
      const labels = arrowLabels(it, at, onBoard), gaps = labels.map(l => l.gap).filter(Boolean)
      const line = q => q.map((v, k) => `${k ? 'L' : 'M'}${v.x},${v.y}`).join(' ')
      let body
      if (!curved) {
        const L = Math.hypot(p3.x - p0.x, p3.y - p0.y) || 1
        const t0 = start ? Math.min(0.9, (size * 0.85) / L) : 0, t1 = end ? Math.max(t0 + 0.05, 1 - (size * 0.85) / L) : 1
        const q = [{ x: p0.x + (p3.x - p0.x) * t0, y: p0.y + (p3.y - p0.y) * t0 }, { x: p0.x + (p3.x - p0.x) * t1, y: p0.y + (p3.y - p0.y) * t1 }]
        body = gaps.length ? cutPolyline(q, gaps).map(line).join(' ') : line(q)
      } else {   // 곡선: 화살촉 길이만큼 떨어진 곡선 매개변수를 찾아 그 구간만 그림
        const cut = size * 0.85, findT = (from, dir) => { let t = from; for (let i = 0; i < 200; i++) { const q = bezierAt(p0, c1, c2, p3, t); const tip = from === 1 ? p3 : p0; if (Math.hypot(q.x - tip.x, q.y - tip.y) >= cut) return t; t += dir * 0.005 } return from }
        const t0 = start ? findT(0, 1) : 0, t1 = end ? findT(1, -1) : 1
        const [a, b, c, d] = bezierSub(p0, c1, c2, p3, t0, t1)
        body = gaps.length ? cutPolyline(Array.from({ length: 65 }, (_, k) => bezierAt(a, b, c, d, k / 64)), gaps).map(line).join(' ')   // 라벨 있으면 잘게 나눠 자름
          : `M${a.x},${a.y} C${b.x},${b.y} ${c.x},${c.y} ${d.x},${d.y}`
      }
      const angEnd = curved ? Math.atan2(p3.y - c2.y, p3.x - c2.x) : Math.atan2(p3.y - p0.y, p3.x - p0.x)
      const angStart = curved ? Math.atan2(p0.y - c1.y, p0.x - c1.x) : Math.atan2(p0.y - p3.y, p0.x - p3.x)
      if (lmode === 'only') return <g transform={T}>{labels.map(l => l.el)}</g>
      return <g transform={T}>
        <path d={body} fill="none" stroke={color} style={minStroke(it.width)} strokeDasharray={dashArray(it.style, it.width)} strokeLinecap="round" strokeLinejoin="round" />
        {end && <Head tri={headTriangle(p3, angEnd, size)} color={color} />}
        {start && <Head tri={headTriangle(p0, angStart, size)} color={color} />}
        {lmode === 'inline' && labels.map(l => l.el)}
      </g>
    }
    default: return null
  }
})
