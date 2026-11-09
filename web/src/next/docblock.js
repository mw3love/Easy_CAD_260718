// 📄 문서 블록 찾기·바꿔 끼우기(2026-11-09 문서 통합 3단계 ①) — 서버 `board_report.find_block`·`splice_block`을 그대로 옮김(순수, DOM 없음).
// 큰 창에서 글자를 손으로 고치면 그 블록 하나만 원래 문서 글에 끼움 — 브라우저가 문서 나머지를 제 방식으로 다시 쓰지 않게.
const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'])
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

export function findBlock(doc, bid) {   // data-block="bid" 요소의 [시작, 끝] — 없으면 null
  doc = String(doc || '')
  const m = new RegExp(`<([a-zA-Z][a-zA-Z0-9-]*)\\b[^>]*\\sdata-block\\s*=\\s*["']${esc(bid)}["'][^>]*>`).exec(doc)
  if (!m) return null
  const rx = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)\b[^>]*?(\/?)>/g, rest = doc.slice(m.index)
  let depth = 0, t
  while ((t = rx.exec(rest))) {
    const [, close, tag, selfc] = t
    if (VOID.has(tag.toLowerCase()) || selfc) { if (depth === 0) return [m.index, m.index + rx.lastIndex]; continue }
    depth += close ? -1 : 1
    if (depth === 0) return [m.index, m.index + rx.lastIndex]
  }
  return null
}

export const blockOf = (doc, bid) => { const at = findBlock(doc, bid); return at ? doc.slice(at[0], at[1]) : '' }

export function spliceBlock(doc, bid, html) {
  const at = findBlock(doc, bid)
  if (!at) throw new Error(`문서에 ${bid} 블록이 없어요`)
  return doc.slice(0, at[0]) + html + doc.slice(at[1])
}

// 손으로 고친 블록(DOM의 outerHTML) → 문서에 끼울 글: 고치는 동안 붙인 표시(contenteditable·mb-* 클래스)를 뗌
export function cleanEdited(outer) {
  return String(outer || '')
    .replace(/\s(?:contenteditable|spellcheck)="[^"]*"/g, '')
    .replace(/\sclass="([^"]*)"/g, (_, c) => { const k = c.split(/\s+/).filter(x => x && !x.startsWith('mb-')).join(' '); return k ? ` class="${k}"` : '' })
}

// 손으로 고칠 수 있는 블록 — 글·상자·표(칸 글자). 그래프·그림은 AI로(말 칸)
export const handEditable = kind => !kind || kind === 'text' || kind === 'box' || kind === 'table'
