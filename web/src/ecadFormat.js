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

