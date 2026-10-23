// SVG → 칠판 도형(§8 항목63 1단계, 2026-10-23) — 데스크톱 `fileio/svg_import.py`를 옮김(데스크톱은 Qt `QPainterPath`라 서버에서 못 씀).
// 좌표만 가져오고 색은 안 읽는다(글자 색 빼고) — 펜은 넣는 쪽이 지금 그리기색으로. 지원: line·rect·circle·ellipse·polyline·polygon·path(M L H V C S Q T A Z)·text.
// <g transform>·<use>·그라디언트는 데스크톱처럼 조용히 건너뜀 — 그런 파일을 끌어 놓으면 Editor가 그림으로 넣는다(`svgFits` — 데스크톱과 다름: 깨진 모양보다 그림이 나음).
// 경로는 데스크톱이 저장하는 모양 그대로(Qt 규칙: 같은 점 선·곡선 빼기, M 연달아 = 덮어쓰기, Z 뒤 이어 그리면 시작점 M, Q = 3차로) — 대조 시험 `tools/export_svg_cases.py` → `test/svgin.test.mjs`.
const NUM_RE = /^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/
const f = (s, d = 0) => { if (s == null) return d; const t = String(s).trim(); return NUM_RE.test(t) ? parseFloat(t) : d }
const TOKEN_RE = /([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)/g
const ENT = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'" }
const unent = s => s.replace(/&(#x[0-9a-f]+|#\d+|\w+);/gi, (m, e) => e[0] === '#' ? String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : +e.slice(1)) : ENT[e] ?? m)
const attrs = s => { const o = {}; for (const m of s.matchAll(/([\w:-]+)\s*=\s*("([^"]*)"|'([^']*)')/g)) o[m[1]] = unent(m[3] ?? m[4]); return o }
// Qt QPointF == (흐린 비교 — 0 근처는 차이, 그 밖은 비율)
const same1 = (a, b) => (a === 0 || b === 0) ? Math.abs(a - b) <= 1e-12 : Math.abs(a - b) * 1e12 <= Math.min(Math.abs(a), Math.abs(b))
const same = (p, q) => same1(p[0], q[0]) && same1(p[1], q[1])

// 태그를 문서 차례대로 — 데스크톱 `root.iter()`처럼 <g>·<defs> 안도 다 훑는다. text는 첫 자식 앞 글만(ElementTree `el.text`)
function tags(svg) {
  const src = svg.replace(/<!--[\s\S]*?-->/g, '').replace(/<!\[CDATA\[[\s\S]*?\]\]>/g, ''), out = []
  for (const m of src.matchAll(/<([A-Za-z][\w:.-]*)((?:\s+[^\s=>/]+\s*=\s*(?:"[^"]*"|'[^']*'))*)\s*(\/?)>/g)) {
    const tag = m[1].replace(/^svg:/, ''), a = attrs(m[2]), el = { tag, a }
    if (tag === 'text' && !m[3]) { const rest = src.slice(m.index + m[0].length), lt = rest.indexOf('<'); el.text = unent(lt < 0 ? rest : rest.slice(0, lt)) }
    out.push(el)
  }
  return out
}

// SVG 끝점 매개변수 타원호 → 3차 베지어 [[c1, c2, end], ...] (데스크톱 `_arc_to_beziers`, SVG 1.1 부록 F.6)
function arcToBeziers(x0, y0, rx, ry, phiDeg, large, sweep, x, y) {
  if (rx === 0 || ry === 0 || (x0 === x && y0 === y)) return [[[x0, y0], [x, y], [x, y]]]
  rx = Math.abs(rx); ry = Math.abs(ry)
  const phi = (((phiDeg % 360) + 360) % 360) * Math.PI / 180, cp = Math.cos(phi), sp = Math.sin(phi)
  const dx2 = (x0 - x) / 2, dy2 = (y0 - y) / 2, x1p = cp * dx2 + sp * dy2, y1p = -sp * dx2 + cp * dy2
  const lam = x1p ** 2 / rx ** 2 + y1p ** 2 / ry ** 2
  if (lam > 1) { const s = Math.sqrt(lam); rx *= s; ry *= s }
  const sign = large === sweep ? -1 : 1, num = rx ** 2 * ry ** 2 - rx ** 2 * y1p ** 2 - ry ** 2 * x1p ** 2, den = rx ** 2 * y1p ** 2 + ry ** 2 * x1p ** 2
  const co = den > 0 ? sign * Math.sqrt(Math.max(num, 0) / den) : 0, cxp = co * (rx * y1p / ry), cyp = co * (-ry * x1p / rx)
  const ccx = cp * cxp - sp * cyp + (x0 + x) / 2, ccy = sp * cxp + cp * cyp + (y0 + y) / 2
  const ang = (ux, uy, vx, vy) => { const l = Math.hypot(ux, uy) * Math.hypot(vx, vy), a = l ? Math.acos(Math.max(-1, Math.min(1, (ux * vx + uy * vy) / l))) : 0; return ux * vy - uy * vx >= 0 ? a : -a }
  const t1 = ang(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
  let dt = ang((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
  if (!sweep && dt > 0) dt -= 2 * Math.PI
  else if (sweep && dt < 0) dt += 2 * Math.PI
  const n = Math.max(1, Math.ceil(Math.abs(dt) / (Math.PI / 2))), st = dt / n, k = 4 / 3 * Math.tan(st / 4)
  const pt = (c, s) => [ccx + rx * c * cp - ry * s * sp, ccy + rx * c * sp + ry * s * cp]
  const dv = (c, s) => [-rx * s * cp - ry * c * sp, -rx * s * sp + ry * c * cp]
  const segs = []
  for (let i = 0, th = t1; i < n; i++, th += st) {
    const c1 = Math.cos(th), s1 = Math.sin(th), c2 = Math.cos(th + st), s2 = Math.sin(th + st), p0 = pt(c1, s1), p1 = pt(c2, s2), d1 = dv(c1, s1), d2 = dv(c2, s2)
    segs.push([[p0[0] + k * d1[0], p0[1] + k * d1[1]], [p1[0] - k * d2[0], p1[1] - k * d2[1]], p1])
  }
  return segs
}

// Qt QPainterPath처럼 쌓는 경로 — .ecad `elements`(M·L·C)
function qtPath() {
  const el = []
  let cStart = 0, needMove = false
  const last = () => el.length ? [el[el.length - 1].at(-2), el[el.length - 1].at(-1)] : [0, 0]
  const maybeMove = () => { if (!el.length) el.push(['M', 0, 0]); if (needMove) { const p = last(); cStart = el.length; el.push(['M', p[0], p[1]]); needMove = false } }
  return {
    el,
    moveTo(p) { needMove = false; if (el.length && el[el.length - 1][0] === 'M') el[el.length - 1] = ['M', p[0], p[1]]; else el.push(['M', p[0], p[1]]); cStart = el.length - 1 },
    lineTo(p) { maybeMove(); if (same(p, last())) return; el.push(['L', p[0], p[1]]) },
    cubicTo(c1, c2, e) { maybeMove(); if (same(last(), c1) && same(c1, c2) && same(c2, e)) return; el.push(['C', c1[0], c1[1], c2[0], c2[1], e[0], e[1]]) },
    quadTo(c, e) { maybeMove(); const p = last(); if (same(p, c) && same(c, e)) return
      this.cubicTo([p[0] + 2 / 3 * (c[0] - p[0]), p[1] + 2 / 3 * (c[1] - p[1])], [e[0] + 2 / 3 * (c[0] - e[0]), e[1] + 2 / 3 * (c[1] - e[1])], e) },
    close() { if (!el.length) return; needMove = true; const a = [el[cStart][1], el[cStart][2]], b = last()
      if (a[0] !== b[0] || a[1] !== b[1]) { if (same(a, b)) { const z = el[el.length - 1]; z[z.length - 2] = a[0]; z[z.length - 1] = a[1] } else el.push(['L', a[0], a[1]]) } },
    done() { return el.length === 1 && el[0][0] === 'M' ? [] : el },
  }
}

// path d → elements, 좌표는 (x*sx+dx, y*sy+dy)로 바로(데스크톱 `_parse_path_d`). S/T 반사는 원본 좌표에서
function pathElements(d, sx, sy, dx, dy) {
  const P = qtPath(), toks = [...d.matchAll(TOKEN_RE)].map(m => m[1] || m[2]), n = toks.length, put = (x, y) => [x * sx + dx, y * sy + dy]
  let i = 0, cx = 0, cy = 0, x0 = 0, y0 = 0, lastC2 = null, lastQ1 = null, cmd = null
  const nf = () => { if (i >= n || /[a-z]/i.test(toks[i])) throw new Error('short'); return parseFloat(toks[i++]) }
  try {
    while (i < n) {
      if (/[a-z]/i.test(toks[i])) cmd = toks[i++]
      if (cmd == null) break
      const c = cmd.toUpperCase(), rel = cmd !== c
      if (c !== 'S') lastC2 = null
      if (c !== 'T') lastQ1 = null
      if (c === 'M') { let x = nf(), y = nf(); if (rel) { x += cx; y += cy } P.moveTo(put(x, y)); cx = x0 = x; cy = y0 = y; cmd = rel ? 'l' : 'L' }
      else if (c === 'L') { let x = nf(), y = nf(); if (rel) { x += cx; y += cy } P.lineTo(put(x, y)); cx = x; cy = y }
      else if (c === 'H') { let x = nf(); if (rel) x += cx; P.lineTo(put(x, cy)); cx = x }
      else if (c === 'V') { let y = nf(); if (rel) y += cy; P.lineTo(put(cx, y)); cy = y }
      else if (c === 'Q') { let x1 = nf(), y1 = nf(), x = nf(), y = nf(); if (rel) { x1 += cx; y1 += cy; x += cx; y += cy } P.quadTo(put(x1, y1), put(x, y)); cx = x; cy = y; lastQ1 = [x1, y1] }
      else if (c === 'T') { let x = nf(), y = nf(); if (rel) { x += cx; y += cy } const q = lastQ1 ? [2 * cx - lastQ1[0], 2 * cy - lastQ1[1]] : [cx, cy]; P.quadTo(put(...q), put(x, y)); cx = x; cy = y; lastQ1 = q }
      else if (c === 'C') { let x1 = nf(), y1 = nf(), x2 = nf(), y2 = nf(), x = nf(), y = nf(); if (rel) { x1 += cx; y1 += cy; x2 += cx; y2 += cy; x += cx; y += cy } P.cubicTo(put(x1, y1), put(x2, y2), put(x, y)); cx = x; cy = y; lastC2 = [x2, y2] }
      else if (c === 'S') { let x2 = nf(), y2 = nf(), x = nf(), y = nf(); if (rel) { x2 += cx; y2 += cy; x += cx; y += cy } const c1 = lastC2 ? [2 * cx - lastC2[0], 2 * cy - lastC2[1]] : [cx, cy]; P.cubicTo(put(...c1), put(x2, y2), put(x, y)); cx = x; cy = y; lastC2 = [x2, y2] }
      else if (c === 'A') { const rx = nf(), ry = nf(), rot = nf(), la = nf(), sw = nf(); let x = nf(), y = nf(); if (rel) { x += cx; y += cy }
        for (const [c1, c2, e] of arcToBeziers(cx, cy, rx, ry, rot, la !== 0, sw !== 0, x, y)) P.cubicTo(put(...c1), put(...c2), put(...e)); cx = x; cy = y }
      else if (c === 'Z') { P.close(); cx = x0; cy = y0 }
    }
  } catch { /* 숫자가 모자람 — 지금까지만(데스크톱은 여기서 오류로 그 파일 전체가 실패 — 웹은 부분 성공) */ }
  return P.done()
}

const NAMED = { black: '000000', white: 'ffffff', red: 'ff0000', green: '008000', blue: '0000ff', gray: '808080', grey: '808080', yellow: 'ffff00', orange: 'ffa500' }
const argb = c => { const s = String(c || 'black').trim().toLowerCase(), h = s[0] === '#' ? s.slice(1) : NAMED[s]
  if (h && /^[0-9a-f]{6}$/.test(h)) return '#ff' + h
  if (h && /^[0-9a-f]{3}$/.test(h)) return '#ff' + [...h].map(x => x + x).join('')
  return '#ff000000' }

// SVG 글 → { items, vb }. items = .ecad 항목 몸통(type·pos·기하, 글자는 color·font) — _id·펜은 넣는 쪽이.
// long·center를 주면 viewBox 긴 변이 long, 가운데가 center(칠판 좌표)가 되게 읽으면서 옮김. 안 주면 원본 좌표 그대로
export function svgItems(svg, long = null, center = null) {
  const all = tags(svg), root = all.find(t => t.tag === 'svg')?.a || {}
  const vp = (root.viewBox || '').trim().split(/[\s,]+/)
  const vb = vp.length === 4 ? vp.map(v => f(v)) : [0, 0, f(root.width, 100), f(root.height, 100)]
  let sx = 1, sy = 1, dx = 0, dy = 0
  if (long != null && center && Math.max(vb[2], vb[3]) > 0) {
    sx = sy = long / Math.max(vb[2], vb[3]); dx = center.x - vb[0] * sx - vb[2] * sx / 2; dy = center.y - vb[1] * sy - vb[3] * sy / 2
  }
  const co = (x, y) => [x * sx + dx, y * sy + dy], items = []
  for (const { tag, a, text } of all) {
    if (tag === 'line') items.push({ type: 'line', pos: [0, 0], line: [...co(f(a.x1), f(a.y1)), ...co(f(a.x2), f(a.y2))] })
    else if (tag === 'rect') items.push({ type: 'rect', pos: [0, 0], rect: [...co(f(a.x), f(a.y)), f(a.width) * sx, f(a.height) * sy] })
    else if (tag === 'circle' || tag === 'ellipse') {
      const rx = f(tag === 'circle' ? a.r : a.rx), ry = f(tag === 'circle' ? a.r : a.ry)
      items.push({ type: 'ellipse', pos: [0, 0], rect: [...co(f(a.cx) - rx, f(a.cy) - ry), rx * 2 * sx, ry * 2 * sy] })
    } else if (tag === 'polyline' || tag === 'polygon') {
      const nums = [...(a.points || '').matchAll(/-?\d*\.?\d+(?:[eE][-+]?\d+)?/g)].map(m => parseFloat(m[0])), pts = []
      for (let i = 0; i + 1 < nums.length; i += 2) pts.push(co(nums[i], nums[i + 1]))
      if (pts.length < 2) continue
      const xs = pts.map(p => p[0]), ys = pts.map(p => p[1]), x0 = Math.min(...xs), y0 = Math.min(...ys)
      items.push({ type: 'polygon', pos: [0, 0], rect: [x0, y0, Math.max(...xs) - x0, Math.max(...ys) - y0], closed: tag === 'polygon', pts })
    } else if (tag === 'path') { if (a.d) items.push({ type: 'path', pos: [0, 0], elements: pathElements(a.d, sx, sy, dx, dy) }) }
    else if (tag === 'text') {
      const t = (text || '').trim(); if (!t) continue
      const fs = f(a['font-size'], 12)
      items.push({ type: 'text', pos: [f(a.x) * sx + dx, f(a.y) * sy + dy - fs * sx], text: t, color: argb(a.fill), font: Math.max(6, Math.trunc(fs * sx)) })   // 기준점 = 글 밑줄 → 한 줄 위로
    }
  }
  return { items, vb }
}

// 끌어 놓은 .svg를 도형으로 넣어도 되나 — 옮기기·되풀이·그라디언트·그림이 들었으면 모양이 깨지니 그림으로(데스크톱은 건너뛰고 도형)
export const svgFits = svg => !/\btransform\s*=|<(use|image|clipPath|mask|pattern|linearGradient|radialGradient|filter)\b|url\(#/i.test(svg) && svgItems(svg).items.length > 0

// 붙여넣은 글이 SVG 코드인가(AI 답에서 복사한 것 — 앞의 <?xml>·주석은 봐줌)
export const looksSvg = t => /^\s*(<\?xml[^>]*\?>\s*)?(<!--[\s\S]*?-->\s*)*(<!DOCTYPE[^>]*>\s*)?<svg[\s>]/i.test(t || '') && /<\/svg>\s*$/i.test(t || '')

// 대화창 아이콘 후보 미리보기 — 칠판에 들어갈 도형 그대로 그린 SVG 글(원본 색·채움이 아니라 우리 선으로 — 붙이면 보이는 모양과 같게)
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
export function svgPreview(svg, ink = '#222') {
  const n = v => +v.toFixed(2), body = svgItems(svg, 100, { x: 50, y: 50 }).items.map(it =>
    it.type === 'line' ? `<line x1="${n(it.line[0])}" y1="${n(it.line[1])}" x2="${n(it.line[2])}" y2="${n(it.line[3])}"/>`
      : it.type === 'rect' ? `<rect x="${n(it.rect[0])}" y="${n(it.rect[1])}" width="${n(it.rect[2])}" height="${n(it.rect[3])}"/>`
        : it.type === 'ellipse' ? `<ellipse cx="${n(it.rect[0] + it.rect[2] / 2)}" cy="${n(it.rect[1] + it.rect[3] / 2)}" rx="${n(it.rect[2] / 2)}" ry="${n(it.rect[3] / 2)}"/>`
          : it.type === 'polygon' ? `<${it.closed ? 'polygon' : 'polyline'} points="${it.pts.map(p => p.map(n).join(',')).join(' ')}"/>`
            : it.type === 'path' ? `<path d="${it.elements.map(e => e[0] + e.slice(1).map(n).join(' ')).join(' ')}"/>`
              : `<text x="${n(it.pos[0])}" y="${n(it.pos[1] + it.font)}" font-size="${it.font}" fill="${ink}" stroke="none">${esc(it.text)}</text>`).join('')
  // 선은 늘 가늘게(크기와 상관없이 1.5px) — 칠판도 굵기는 원본이 아니라 지금 펜(데스크톱과 같게), 미리보기가 굵으면 「굵게 해 줘」가 된 줄 앎(실측)
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 108 108" fill="none" stroke="${ink}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><style>*{vector-effect:non-scaling-stroke}</style>${body}</svg>`
}
