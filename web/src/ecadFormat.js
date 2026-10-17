// .ecad 값 변환 — tldraw 없이 도는 순수 함수(node 테스트 대상: test/ecadFormat.test.mjs).

// '#AARRGGBB'(Qt HexArgb) → CSS
export function cssColor(c) {
  if (!c) return null
  if (c.length === 9) {
    const a = parseInt(c.slice(1, 3), 16) / 255, rgb = c.slice(3)
    return a >= 0.999 ? '#' + rgb : `rgba(${parseInt(rgb.slice(0, 2), 16)},${parseInt(rgb.slice(2, 4), 16)},${parseInt(rgb.slice(4, 6), 16)},${a.toFixed(3)})`
  }
  return c
}
export const bgCss = bg => Array.isArray(bg) ? `rgba(${bg[0]},${bg[1]},${bg[2]},${(bg[3] / 255).toFixed(3)})` : cssColor(bg)

// 글 + runs([시작, 길이, 색, 굵게, 배경?]) → tldraw 서식 글(줄마다 문단, 부분 굵게·색·형광펜)
export function runsToRichText(text, runs = [], weight = null) {
  const n = text.length, attr = new Array(n).fill(null)
  for (const [s, len, color, bold, bg] of runs || [])
    for (let i = Math.max(0, s); i < Math.min(n, s + len); i++) attr[i] = { color, bold, bg }
  const same = (a, b) => (a?.color ?? null) === (b?.color ?? null) && !!a?.bold === !!b?.bold && (a?.bg ?? null) === (b?.bg ?? null)
  const paras = []
  let pos = 0
  for (const line of text.split('\n')) {
    const content = []
    for (let i = 0; i < line.length;) {
      const a = attr[pos + i]
      let j = i + 1
      while (j < line.length && same(attr[pos + j], a)) j++
      const node = { type: 'text', text: line.slice(i, j) }, marks = []
      // 굵은 조각은 바탕 굵기보다 가늘어지지 않게(800 제목 안 굵은 조각이 700으로 내려가지 않도록)
      const w = a?.bold ? Math.max(700, weight || 0) : weight
      if (a?.bold) marks.push({ type: 'bold' })   // 굵게 표시는 늘 남긴다(내보낼 때 되살림) — 안쪽 textStyle 굵기가 실제 굵기를 정함
      if (w && w !== 400) marks.push({ type: 'textStyle', attrs: { color: a?.color ?? null, backgroundColor: a?.bg ? cssColor(a.bg) : null, fontWeight: String(w) } })
      else if (a?.color || a?.bg) marks.push({ type: 'textStyle', attrs: { color: a.color ?? null, backgroundColor: a.bg ? cssColor(a.bg) : null, fontWeight: null } })
      if (marks.length) node.marks = marks
      content.push(node); i = j
    }
    paras.push(content.length ? { type: 'paragraph', content } : { type: 'paragraph' })
    pos += line.length + 1
  }
  return { type: 'doc', content: paras }
}

// 경로 요소 [["M",x,y],["L",..],["C",..]] → SVG d + 상자
export function pathD(elems) {
  const xs = [], ys = []
  for (const e of elems) for (let i = 1; i < e.length; i += 2) { xs.push(e[i]); ys.push(e[i + 1]) }
  const x0 = Math.min(...xs), y0 = Math.min(...ys), w = Math.max(...xs) - x0 || 1, h = Math.max(...ys) - y0 || 1
  const pair = e => { const out = []; for (let i = 1; i < e.length; i += 2) out.push(`${(e[i] - x0).toFixed(2)},${(e[i + 1] - y0).toFixed(2)}`); return out.join(' ') }
  const d = elems.map(e => e[0] + pair(e)).join(' ')
  // 사각형으로 볼 것: 꼭짓점 5개로 닫힘·곡선 없음·x값 둘·y값 둘 — 점 2~3개짜리 열린 선(빗금·꺾인 선)은 사각형이 아니다
  const closed = elems.length === 5 && elems[0][1] === elems[4][1] && elems[0][2] === elems[4][2]   // ㄷ자처럼 열린 4점은 제외
  const isRect = closed && elems.every(e => e[0] !== 'C') && new Set(elems.map(e => e[1])).size === 2 && new Set(elems.map(e => e[2])).size === 2
  return { x0, y0, w, h, d, isRect }
}


// ── 웹 → .ecad(내보내기) ──

// CSS 색(#rgb·#rrggbb·#rrggbbaa·rgb()·rgba()·transparent) → Qt '#AARRGGBB'. 못 읽으면 null
export function cssToArgb(c) {
  if (!c || c === 'transparent' || c === 'none') return c === 'transparent' ? '#00000000' : null
  const h2 = n => Math.round(n).toString(16).padStart(2, '0')
  let m = /^#([0-9a-f]{3})$/i.exec(c)
  if (m) return '#ff' + m[1].split('').map(x => x + x).join('').toLowerCase()
  if ((m = /^#([0-9a-f]{6})$/i.exec(c))) return '#ff' + m[1].toLowerCase()
  if ((m = /^#([0-9a-f]{6})([0-9a-f]{2})$/i.exec(c))) return '#' + m[2].toLowerCase() + m[1].toLowerCase()
  if ((m = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+%?))?\s*\)$/i.exec(c))) {
    let a = m[4] == null ? 1 : m[4].endsWith('%') ? parseFloat(m[4]) / 100 : parseFloat(m[4])
    return '#' + h2(a * 255) + h2(+m[1]) + h2(+m[2]) + h2(+m[3])
  }
  return null
}
const argbToRgbHex = c => (c && c.length === 9 ? '#' + c.slice(3) : c)

// tldraw 서식 글 → { text(줄은 \n), runs: [시작, 길이, 색, 굵게, 배경?] } — runsToRichText의 반대.
// baseWeight보다 굵은 조각만 "굵게"로 센다(바탕이 800인 제목 전체를 굵게 조각으로 만들지 않게).
export function richTextToRuns(doc, baseWeight = 400) {
  const lines = [], runs = []
  let pos = 0
  const walk = (node, out) => {
    if (node.type === 'text') { out.push(node); return }
    if (node.type === 'hardBreak') { out.push({ type: 'text', text: '\n' }); return }
    for (const c of node.content || []) walk(c, out)
  }
  for (const block of doc?.content || []) {
    const nodes = []; walk(block, nodes)
    let line = ''
    for (const n of nodes) {
      const ts = n.marks?.find(m => m.type === 'textStyle')?.attrs || {}
      const w = ts.fontWeight ? parseInt(ts.fontWeight, 10) : null
      const bold = !!n.marks?.some(m => m.type === 'bold') || (w != null && w > baseWeight && w >= 600)   // 웹에서 Ctrl+B로 굵게 한 것도
      const color = ts.color ? argbToRgbHex(cssToArgb(ts.color)) : null
      const bg = ts.backgroundColor ? cssToArgb(ts.backgroundColor) : (n.marks?.find(m => m.type === 'highlight') ? '#80ffeb3b' : null)
      if (color || bold || bg) runs.push([pos + line.length, n.text.length, color, bold, ...(bg ? [bg] : [])])
      line += n.text
    }
    lines.push(line); pos += line.length + 1
  }
  return { text: lines.join('\n'), runs }
}

// 우리 esym 경로 d("M0.00,0.00 L.. C..") → .ecad 경로 요소, 상자(w,h)에 맞춰 늘림
export function parseD(d, sx = 1, sy = 1, ox = 0, oy = 0) {
  const out = []
  for (const m of d.matchAll(/([MLC])([^MLCZ]*)/g)) {
    const nums = m[2].trim().split(/[\s,]+/).filter(Boolean).map(Number)
    const e = [m[1]]
    for (let i = 0; i < nums.length; i += 2) e.push(ox + nums[i] * sx, oy + nums[i + 1] * sy)
    out.push(e)
  }
  return out
}
