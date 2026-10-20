// KAIROS 대화창의 순수 함수(§8 항목61 ⓒ) — 답 글(가벼운 마크다운) 읽기·카드 글 만들기·빈자리 찾기. `npm test`로 시험.

// **굵게**·`코드` 조각 나누기 → [{ text, bold, code? }] — 글 속 `코드`는 고정폭 조각(2026-10-18 코드 블록)
export function inlineParts(line) {
  const out = []
  const re = /\*\*(.+?)\*\*|`([^`]+)`/g
  let i = 0, m
  while ((m = re.exec(line))) {
    if (m.index > i) out.push({ text: line.slice(i, m.index), bold: false })
    if (m[2] != null) out.push({ text: m[2], bold: false, code: true })
    else m[1].split(/`([^`]+)`/).forEach((t, k) => { if (t) out.push(k % 2 ? { text: t, bold: true, code: true } : { text: t, bold: true }) })   // **굵게 속 `코드`**도 코드 조각(2026-10-19 사용자: 백틱이 그대로 보임)
    i = m.index + m[0].length
  }
  if (i < line.length) out.push({ text: line.slice(i), bold: false })
  return out
}

// 답 글 → 줄 목록 [{ kind: 'p'|'h'|'li'|'code', parts }] — 빈 줄은 문단 사이 한 칸으로 줄인다, 코드펜스 줄은 뺀다
export function parseAnswer(md) {
  const lines = [], src = String(md || '').replace(/\r\n?/g, '\n').split('\n')
  let inCode = false, blank = false
  for (const raw of src) {
    if (/^\s*```/.test(raw)) { inCode = !inCode; continue }
    if (inCode) { lines.push({ kind: 'code', parts: [{ text: raw, bold: false }] }); blank = false; continue }
    const t = raw.trim()
    if (!t) { if (lines.length && !blank) { lines.push({ kind: 'gap', parts: [] }); blank = true } continue }
    blank = false
    // 표(| 가 | 나 |) — 붙은 줄을 한 덩어리로, 둘째 줄이 |---| 이면 첫 줄 = 머리글(2026-10-20 사용자: AI 표 답이 | 글자로 보였음)
    if (/^\|.*\|$/.test(t) && t.length > 2) {
      const cells = t.slice(1, -1).split('|').map(c => c.trim()), prev = lines[lines.length - 1]
      if (cells.every(c => /^:?-{2,}:?$/.test(c))) { if (prev?.kind === 'table' && prev.rows.length === 1) prev.header = true; continue }
      if (prev?.kind === 'table') prev.rows.push(cells); else lines.push({ kind: 'table', rows: [cells], header: false })
      continue
    }
    let m
    if ((m = /^(#{1,6})\s+(.*)$/.exec(t))) lines.push({ kind: 'h', level: m[1].length, parts: inlineParts(m[2].replace(/\*\*/g, '')) })
    else if ((m = /^([-*•]|\d+[.)])\s+(.*)$/.exec(t))) { const lv = Math.min(3, Math.floor((raw.length - raw.trimStart().length) / 2))   // 목록 깊이 = 앞 띄어쓰기 둘마다(메모)
      lines.push({ kind: 'li', mark: /\d/.test(m[1]) ? m[1] : '•', parts: inlineParts(m[2]), ...(lv ? { lv } : {}) }) }
    else if ((m = /^>\s?(.*)$/.exec(t))) lines.push({ kind: 'quote', parts: inlineParts(m[1]) })
    else lines.push({ kind: 'p', parts: inlineParts(t) })
  }
  while (lines.length && lines[lines.length - 1].kind === 'gap') lines.pop()
  return lines
}

const textNode = (text, marks) => (marks.length ? { type: 'text', text, marks } : { type: 'text', text })

// 답 글 → 칠판 카드 글(TipTap 문서). 맨 끝에 회색 출처 줄(「KAIROS · 모델 · 시각」).
export function answerToRichText(md, source = '') {
  const content = []
  for (const ln of parseAnswer(md)) {
    if (ln.kind === 'gap') { content.push({ type: 'paragraph' }); continue }
    const parts = ln.kind === 'li' ? [{ text: ln.mark + ' ', bold: false }, ...ln.parts] : ln.parts
    const nodes = parts.filter(p => p.text).map(p => textNode(p.text, p.bold || ln.kind === 'h' ? [{ type: 'bold' }] : []))
    content.push(nodes.length ? { type: 'paragraph', content: nodes } : { type: 'paragraph' })
  }
  if (source) content.push({ type: 'paragraph', content: [textNode(source, [{ type: 'textStyle', attrs: { color: '#8a8f98' } }])] })
  if (!content.length) content.push({ type: 'paragraph' })
  return { type: 'doc', content }
}

// 출처 줄: 「KAIROS · gpt-6.1-sol · 10-17 14:02」
export function sourceLine(model, at) {
  const d = new Date(at), p = n => String(n).padStart(2, '0')
  return `KAIROS · ${model} · ${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

const hit = (a, b, pad) => a.x < b.x + b.w + pad && b.x < a.x + a.w + pad && a.y < b.y + b.h + pad && b.y < a.y + a.h + pad

// 화면(view) 안에서 w×h 상자가 다른 것(boxes)과 안 겹치는 자리 — 왼쪽 위부터 줄 단위로 훑는다. 화면에 없으면 모든 것의 오른쪽.
export function freeSpot(view, boxes, w, h, { pad = 24, step = 24 } = {}) {
  const x0 = view.x + pad, y0 = view.y + pad
  const yMax = Math.max(y0, view.y + view.h - pad - h), xMax = Math.max(x0, view.x + view.w - pad - w)   // 상자가 화면보다 커도 첫 줄은 본다
  for (let y = y0; y <= yMax; y += step)
    for (let x = x0; x <= xMax; x += step)
      if (!boxes.some(b => hit({ x, y, w, h }, b, pad / 2))) return { x, y }
  if (!boxes.length) return { x: x0, y: y0 }
  const right = Math.max(...boxes.map(b => b.x + b.w)), top = Math.min(...boxes.map(b => b.y))
  return { x: right + pad * 2, y: Math.max(top, y0) }
}

// 가운데 먼저, 겹치면 가장 가까운 빈자리(2026-10-20 사용자 — 표·메모·웹을 버튼으로 넣을 때). c = 놓고 싶은 상자의 가운데,
// 가운데에서 바깥으로 고리처럼 넓혀 가며(가까운 순) 겹치지 않는 첫 자리. 화면 안에서 못 찾으면 가운데 그대로(예측되는 자리가 겹침보다 낫다)
export function nearSpot(c, boxes, w, h, { pad = 24, step = 24, view = null } = {}) {
  const free = (x, y) => !boxes.some(b => hit({ x, y, w, h }, b, pad / 2))
  const x0 = c.x - w / 2, y0 = c.y - h / 2
  if (free(x0, y0)) return { x: x0, y: y0 }
  const inView = (x, y) => !view || (x >= view.x && y >= view.y && x + w <= view.x + view.w && y + h <= view.y + view.h)
  const maxR = view ? Math.ceil(Math.max(view.w, view.h) / step) : 40
  for (let r = 1; r <= maxR; r++) {
    const ring = []
    for (let i = -r; i <= r; i++) ring.push([i, -r], [i, r], [-r, i], [r, i])
    ring.sort((a, b) => Math.hypot(...a) - Math.hypot(...b))
    for (const [i, j] of ring) { const x = x0 + i * step, y = y0 + j * step; if (inView(x, y) && free(x, y)) return { x, y } }
  }
  return { x: x0, y: y0 }
}

// 칠판에서 고른 것들의 글 → 질문에 같이 보낼 글(빈 것은 빼고, 겹친 것은 한 번만)
export function contextText(texts, max = 20000) {
  const seen = new Set(), out = []
  for (const t of texts) {
    const s = String(t || '').trim()
    if (!s || seen.has(s)) continue
    seen.add(s); out.push(s)
  }
  return out.map(s => `- ${s.replace(/\n+/g, ' / ')}`).join('\n').slice(0, max)
}

// ── 직접 만드는 칠판(.ecad) 카드 글 — 답 글 → { text, runs }(.ecad runs = [시작, 길이, 색, 굵게]). 맨 끝 회색 출처 줄.
export function answerToEcadText(md, source = '') {
  let text = ''
  const runs = []
  const add = (s, bold, color = null, mono = false) => { if (!s) return; if (mono) runs.push([text.length, s.length, null, false, null, true]); else if (bold || color) runs.push([text.length, s.length, color, !!bold]); text += s }
  const lines = parseAnswer(md)
  lines.forEach((ln, i) => {
    if (i) text += '\n'
    if (ln.kind === 'gap') return
    if (ln.kind === 'code') { add(ln.parts[0].text.replace(/\t/g, '    ') || ' ', false, null, true); return }   // 코드 = 고정폭 줄(2026-10-18 사용자: 카드 안에)
    if (ln.kind === 'li') add(ln.mark + ' ', false)
    for (const p of ln.parts) add(p.text, p.bold || ln.kind === 'h', null, !!p.code)
  })
  if (source) { if (text) text += '\n'; add(source, false, '#8a8f98') }
  return { text, runs }
}

