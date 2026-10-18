// 메모(§8 항목61 4-b ⑤ 1차, 2026-10-18 사용자: 노션 같은 메모장 · KAIROS 답도 메모로) — 줄 목록 하나가 칠판 위 네모 하나.
// .ecad 새 종류 `memo` = { rect, fill, lines: [{ k, t, runs?, done?, lv? }] } — k = p·h1·h2·h3·ul·ol·todo·code·quote·hr(구분선, 글 없음), lv = 목록 깊이(0부터).
// 그리기(render.jsx `memoLayout`)와 고치기(memoedit.jsx CSS)가 같은 치수(MEMO)를 읽는다 — 고치는 모습 = 결과. 데스크톱은 보존만.
import { answerToEcadText, parseAnswer } from '../chatFormat.js'
import { richTextToRuns, runsToRichText } from '../ecadFormat.js'

// LPAD = 왼쪽 여백 — 줄 손잡이 ⠿가 메모 안쪽에 들어가는 자리(2026-10-18 사용자: 바깥 손잡이는 글과 너무 떨어짐)
export const MEMO = { W: 340, PAD: 14, LPAD: 26, GAP: 5, INDENT: 18, QUOTE: 14, HR: 9 }
export const MEMO_KIND = {
  p: { pt: 10.5 }, ul: { pt: 10.5 }, ol: { pt: 10.5 }, todo: { pt: 10.5 }, quote: { pt: 10.5 },
  h1: { pt: 16, bold: true, gap: 10 }, h2: { pt: 13.5, bold: true, gap: 8 }, h3: { pt: 11.5, bold: true, gap: 6 }, code: { pt: 10, mono: true }, hr: { pt: 10.5 },
}
export const LISTY = new Set(['ul', 'ol', 'todo'])
export const MUTED = '#8a8f98'

// 블록 = 그리기·고치기에서 한 덩어리(위 간격 단위) — 이어진 코드 줄·인용 줄은 한 블록
export function memoBlocks(lines) {
  const out = []
  for (const ln of lines || []) {
    const last = out[out.length - 1]
    if (last && (ln.k === 'code' || ln.k === 'quote') && last.k === ln.k) last.lines.push(ln)
    else out.push({ k: ln.k, lines: [ln] })
  }
  return out
}

// 번호 목록 번호 — 같은 깊이에서 이어진 ol끼리(사이에 더 깊은 줄은 끊지 않음)
export function olNumbers(lines) {
  const nums = [], cnt = []
  ;(lines || []).forEach((ln, i) => {
    const lv = ln.lv || 0
    if (ln.k === 'ol') { cnt.length = lv + 1; cnt[lv] = (cnt[lv] || 0) + 1; nums[i] = cnt[lv] }
    else if (LISTY.has(ln.k)) { cnt.length = lv + 1; cnt[lv] = 0 }
    else cnt.length = 0
  })
  return nums
}

// KAIROS 답 → 메모 줄(제목 # 수 그대로, 목록·번호·할 일·코드·인용, 글 속 **굵게**·`코드`), 맨 끝 회색 출처 줄
export function memoFromAnswer(md, source = '') {
  const lines = []
  for (const ln of parseAnswer(md)) {
    if (ln.kind === 'gap') continue
    if (ln.kind === 'code') { lines.push({ k: 'code', t: ln.parts[0].text.replace(/\t/g, '    ') }); continue }
    if (ln.kind === 'p' && /^\s*([-*_])(\s*\1){2,}\s*$/.test(ln.parts.map(p => p.text).join(''))) { lines.push({ k: 'hr', t: '' }); continue }   // --- · *** · ___ = 구분선
    const src = ln.parts.map(p => (p.code ? '`' + p.text + '`' : p.bold ? `**${p.text}**` : p.text)).join('')
    const { text, runs } = answerToEcadText(src)
    const L = { k: 'p', t: text, ...(runs.length ? { runs } : {}) }
    if (ln.kind === 'h') L.k = ['h1', 'h2', 'h3'][Math.min(2, (ln.level || 2) - 1)]
    else if (ln.kind === 'li') { const m = /^\[( |x|X)\]\s*/.exec(L.t)
      if (m) { L.k = 'todo'; if (m[1] !== ' ') L.done = true; cutFront(L, m[0].length) } else L.k = /\d/.test(ln.mark) ? 'ol' : 'ul'
      if (ln.lv) L.lv = ln.lv }
    else if (ln.kind === 'quote') L.k = 'quote'
    lines.push(L)
  }
  if (source) lines.push({ k: 'p', t: source, runs: [[0, source.length, MUTED, false]] })
  return lines.length ? lines : [{ k: 'p', t: '' }]
}
function cutFront(L, n) { L.t = L.t.slice(n); if (L.runs) { L.runs = L.runs.map(([s, len, ...r]) => [s - n, len, ...r]).filter(r => r[0] + r[1] > 0).map(r => (r[0] < 0 ? [0, r[1] + r[0], ...r.slice(2)] : r)); if (!L.runs.length) delete L.runs } }

// 줄 → 쉬운 글(대화창에 같이 보낼 글·데스크톱 네모 안 글)
export function memoText(lines) {
  const nums = olNumbers(lines)
  return (lines || []).map((ln, i) => (ln.k === 'hr' ? '────────' : '  '.repeat(ln.lv || 0) + ({ h1: '# ', h2: '## ', h3: '### ', ul: '• ', ol: `${nums[i]}. `, todo: ln.done ? '☑ ' : '☐ ', quote: '│ ' }[ln.k] || '') + ln.t)).join('\n')
}

// ── 줄 ↔ TipTap 문서(고치기) ──
const para = ln => ({ ...runsToRichText(ln.t || '', ln.runs).content[0] })
export function linesToDoc(lines) {
  const content = []
  const blocks = memoBlocks(lines)
  let i = 0
  while (i < blocks.length) {
    const b = blocks[i]
    if (b.k === 'code') { const t = b.lines.map(l => l.t).join('\n'); content.push(t ? { type: 'codeBlock', content: [{ type: 'text', text: t }] } : { type: 'codeBlock' }); i++; continue }
    if (b.k === 'quote') { content.push({ type: 'blockquote', content: b.lines.map(para) }); i++; continue }
    if (b.k === 'hr') { content.push({ type: 'horizontalRule' }); i++; continue }
    if (b.k[0] === 'h') { content.push({ type: 'heading', attrs: { level: +b.k[1] }, content: para(b.lines[0]).content }); i++; continue }
    if (!LISTY.has(b.k)) { content.push(para(b.lines[0])); i++; continue }
    let j = i; const run = []
    while (j < blocks.length && LISTY.has(blocks[j].k)) run.push(blocks[j++].lines[0])
    content.push(...buildList(run, 0).nodes); i = j
  }
  return { type: 'doc', content: content.length ? content : [{ type: 'paragraph' }] }
}
// 이어진 목록 줄(깊이 lv) → 중첩 목록 노드. 같은 깊이에서 종류가 바뀌면 새 목록
function buildList(run, lv) {
  const nodes = []; let k = 0
  const listType = { ul: 'bulletList', ol: 'orderedList', todo: 'taskList' }
  while (k < run.length && (run[k].lv || 0) >= lv) {
    const ln = run[k], kind = ln.k, list = { type: listType[kind], content: [] }
    if ((ln.lv || 0) > lv) { const sub = buildList(run.slice(k), lv + 1); nodes.push(...sub.nodes); k += sub.used; continue }
    while (k < run.length && (run[k].lv || 0) === lv && run[k].k === kind) {
      const it = run[k], item = { type: kind === 'todo' ? 'taskItem' : 'listItem', ...(kind === 'todo' ? { attrs: { checked: !!it.done } } : {}), content: [para(it)] }
      k++
      if (k < run.length && (run[k].lv || 0) > lv) { const sub = buildList(run.slice(k), lv + 1); item.content.push(...sub.nodes); k += sub.used }
      list.content.push(item)
    }
    nodes.push(list)
  }
  return { nodes, used: k }
}
const lineOf = (node, extra) => { const { text, runs } = richTextToRuns({ type: 'doc', content: [node || { type: 'paragraph' }] }); return { t: text, ...(runs.length ? { runs } : {}), ...extra } }
export function docToLines(doc) {
  const out = []
  const walkList = (list, lv) => {
    const k = { bulletList: 'ul', orderedList: 'ol', taskList: 'todo' }[list.type]
    for (const item of list.content || []) {
      const [first, ...rest] = item.content || []
      out.push(lineOf(first?.type === 'paragraph' ? first : null, { k, ...(k === 'todo' ? { done: !!item.attrs?.checked } : {}), ...(lv ? { lv } : {}) }))
      for (const sub of first?.type === 'paragraph' ? rest : item.content || []) if (/List$/.test(sub.type)) walkList(sub, lv + 1); else if (sub.type === 'paragraph') out.push(lineOf(sub, { k, ...(lv ? { lv } : {}) }))
    }
  }
  for (const n of doc?.content || []) {
    if (n.type === 'heading') out.push(lineOf({ type: 'paragraph', content: n.content }, { k: 'h' + Math.min(3, n.attrs?.level || 1) }))
    else if (n.type === 'codeBlock') for (const t of (n.content || []).map(c => c.text).join('').split('\n')) out.push({ k: 'code', t })
    else if (n.type === 'blockquote') for (const p of n.content || []) out.push(lineOf(p, { k: 'quote' }))
    else if (n.type === 'horizontalRule') out.push({ k: 'hr', t: '' })
    else if (/List$/.test(n.type)) walkList(n, 0)
    else out.push(lineOf(n, { k: 'p' }))
  }
  return out.map(ln => { const o = { k: ln.k, t: ln.t }; if (ln.runs) o.runs = ln.runs; if (ln.done) o.done = true; if (ln.lv) o.lv = ln.lv; return o })
}

// ── 2차: 줄 손잡이(⠿) — 끌 단위·옮기기·꺼내기·전환·색 ──
// 끌 단위 [시작, 끝) — 코드·인용 = 이어진 덩어리 전체, 목록 줄 = 그 아래 더 깊은 줄까지(노션처럼 하위 항목이 따라옴), 나머지 = 그 줄
export function lineUnit(lines, i) {
  const ln = lines[i]; if (!ln) return [i, i]
  if (ln.k === 'code' || ln.k === 'quote') { let s = i, e = i + 1; while (s > 0 && lines[s - 1].k === ln.k) s--; while (e < lines.length && lines[e].k === ln.k) e++; return [s, e] }
  let e = i + 1
  if (LISTY.has(ln.k)) while (e < lines.length && LISTY.has(lines[e].k) && (lines[e].lv || 0) > (ln.lv || 0)) e++
  return [i, e]
}
// 단위 떼어 내기 — 떼어 낸 줄은 깊이를 맨 앞 줄 기준 0부터로
export function takeUnit(lines, [s, e]) {
  const base = lines[s]?.lv || 0
  const unit = lines.slice(s, e).map(ln => { const o = { ...ln }, lv = (ln.lv || 0) - base; if (lv > 0) o.lv = lv; else delete o.lv; return o })
  return { rest: [...lines.slice(0, s), ...lines.slice(e)], unit }
}
// 같은 메모 안에서 옮기기 — to = 원래 줄 번호 기준으로 끼워 넣을 자리(0…길이). 자기 자리 안이면 그대로
export function moveUnit(lines, [s, e], to) {
  if (to >= s && to <= e) return lines
  const { rest, unit } = takeUnit(lines, [s, e])
  const at = to > e ? to - (e - s) : to
  return [...rest.slice(0, at), ...unit, ...rest.slice(at)]
}
// 줄 종류 바꾸기(전환) — 코드는 부분 서식 없이, 할 일이 아니면 체크 없음, 목록이 아니면 깊이 없음
export function convertLine(ln, k) {
  if (ln.k === 'hr') return ln   // 구분선은 글이 없어 바꾸지 않음
  const o = { ...ln, k }
  if (k === 'code') delete o.runs
  if (k !== 'todo') delete o.done
  if (!LISTY.has(k)) delete o.lv
  return o
}
// 같은 메모 안 여러 단위를 한 번에 옮기기·복사 — [s, e) 범위(고른 줄들), copy = 원래 줄은 둠
export function moveRange(lines, [s, e], to, copy = false) {
  if (!copy) return moveUnit(lines, [s, e], to)
  const unit = structuredClone(lines.slice(s, e))
  return [...lines.slice(0, to), ...unit, ...lines.slice(to)]
}
// TipTap 문서에서 커서가 있는 줄 번호(docToLines 차례와 같음 — 글 블록마다 한 줄, 코드 블록은 \n마다, 구분선 한 줄)
export function caretLine(state) {
  const pos = state.selection.from
  let idx = 0, found = null
  state.doc.descendants((node, at) => {
    if (found != null) return false
    if (node.type.name === 'horizontalRule') { if (pos >= at && pos <= at + node.nodeSize) found = idx; idx++; return false }
    if (!node.isTextblock) return true
    const end = at + node.nodeSize
    if (node.type.name === 'codeBlock') {
      const n = node.textContent.split('\n').length
      if (pos >= at && pos <= end) { found = idx + node.textBetween(0, Math.max(0, Math.min(node.content.size, pos - at - 1)), '\n').split('\n').length - 1; return false }
      idx += n; return false
    }
    if (pos >= at && pos <= end) { found = idx; return false }
    idx++; return false
  })
  return found ?? Math.max(0, idx - 1)
}
// 줄 번호 → 그 줄의 TipTap 글 블록 위치(손잡이 자리 찾기) — caretLine의 거꾸로
export function lineBlocks(doc) {
  const out = []
  doc.descendants((node, at) => {
    if (node.type.name === 'horizontalRule') { out.push({ at, node }); return false }
    if (!node.isTextblock) return true
    if (node.type.name === 'codeBlock') { node.textContent.split('\n').forEach(() => out.push({ at, node })); return false }
    out.push({ at, node }); return false
  })
  return out
}

// 줄 전체 색(글자 color · 배경 bg — 둘 다 null = 기본) — 부분 서식(굵게·코드)은 지키고 색만 줄 전체에
export function recolorLine(ln, { color, bg }) {
  const n = (ln.t || '').length; if (!n || ln.k === 'code' || ln.k === 'hr') return ln
  const at = Array.from({ length: n }, () => ({ color: null, bold: false, bg: null, mono: false }))
  for (const [s, len, c, b, g, m] of ln.runs || []) for (let i = Math.max(0, s); i < Math.min(n, s + len); i++) at[i] = { color: c || null, bold: !!b, bg: g || null, mono: !!m }
  for (const a of at) { if (color !== undefined) a.color = color; if (bg !== undefined) a.bg = bg }
  const runs = []
  for (let i = 0; i < n;) { const a = at[i]; let j = i + 1; while (j < n && JSON.stringify(at[j]) === JSON.stringify(a)) j++
    if (a.mono) runs.push([i, j - i, a.color, a.bold, a.bg, true]); else if (a.color || a.bold || a.bg) runs.push([i, j - i, a.color, a.bold, ...(a.bg ? [a.bg] : [])]); i = j }
  const o = { ...ln }; if (runs.length) o.runs = runs; else delete o.runs; return o
}
// 전환 메뉴 차례(노션 「전환」에서 메모에 맞는 것만 — 2026-10-18 사용자와 정함)
export const LINE_KINDS = [['p', '텍스트'], ['h1', '제목1'], ['h2', '제목2'], ['h3', '제목3'], ['ul', '글머리 기호 목록'], ['ol', '번호 매기기 목록'], ['todo', '할 일 목록'], ['code', '코드'], ['quote', '인용']]
// 색(노션 「색」 — 글자 / 배경). 배경은 옅게(형광펜처럼 글자 뒤)
export const LINE_COLORS = [['기본', null, null], ['회색', '#787774', '#55e3e2e0'], ['갈색', '#9f6b53', '#55eee0da'], ['주황', '#d9730d', '#55fadec9'], ['노랑', '#cb912f', '#66fdecc8'],
  ['초록', '#448361', '#55dbeddb'], ['파랑', '#337ea9', '#55d3e5ef'], ['보라', '#9065b0', '#55e8deee'], ['분홍', '#c14c8a', '#55f5e0e9'], ['빨강', '#d44c47', '#55ffe2dd']]
