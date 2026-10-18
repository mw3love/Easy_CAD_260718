// 메모(§8 항목61 4-b ⑤ 1차, 2026-10-18 사용자: 노션 같은 메모장 · KAIROS 답도 메모로) — 줄 목록 하나가 칠판 위 네모 하나.
// .ecad 새 종류 `memo` = { rect, fill, lines: [{ k, t, runs?, done?, lv? }] } — k = p·h1·h2·h3·ul·ol·todo·code·quote, lv = 목록 깊이(0부터).
// 그리기(render.jsx `memoLayout`)와 고치기(memoedit.jsx CSS)가 같은 치수(MEMO)를 읽는다 — 고치는 모습 = 결과. 데스크톱은 보존만.
import { answerToEcadText, parseAnswer } from '../chatFormat.js'
import { richTextToRuns, runsToRichText } from '../ecadFormat.js'

export const MEMO = { W: 340, PAD: 14, GAP: 5, INDENT: 18, QUOTE: 14 }
export const MEMO_KIND = {
  p: { pt: 10.5 }, ul: { pt: 10.5 }, ol: { pt: 10.5 }, todo: { pt: 10.5 }, quote: { pt: 10.5 },
  h1: { pt: 16, bold: true, gap: 10 }, h2: { pt: 13.5, bold: true, gap: 8 }, h3: { pt: 11.5, bold: true, gap: 6 }, code: { pt: 10, mono: true },
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
  return (lines || []).map((ln, i) => '  '.repeat(ln.lv || 0) + ({ h1: '# ', h2: '## ', h3: '### ', ul: '• ', ol: `${nums[i]}. `, todo: ln.done ? '☑ ' : '☐ ', quote: '│ ' }[ln.k] || '') + ln.t).join('\n')
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
    else if (/List$/.test(n.type)) walkList(n, 0)
    else out.push(lineOf(n, { k: 'p' }))
  }
  return out.map(ln => { const o = { k: ln.k, t: ln.t }; if (ln.runs) o.runs = ln.runs; if (ln.done) o.done = true; if (ln.lv) o.lv = ln.lv; return o })
}
