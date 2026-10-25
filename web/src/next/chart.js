// 그래프(§8 항목66 1단계, 2026-10-25) — 「그래프 = 표 + 모양」(시안 판정). 새 종류가 아니라 표(`table`)에 칸 하나: `chart` = 'col'|'row'|'line'|'pie'(없으면 표).
// 숫자는 표 칸 그대로 — 칸을 고치면 그래프가 따라가고, 그래프를 모르는 프로그램에선 표로 보여 숫자를 잃지 않음.
// 이 파일은 순수 계산(읽기·막기·그릴 조각). 그림 조각(`chartScene`)은 데스크톱 `canvas/core_chart.py`가 똑같이 옮김 — 고치면 `tools/export_chart_cases.mjs`를 다시 돌림.
// 글 폭은 글자 수로 어림(`textW`) — 브라우저·Qt 글꼴 재기가 달라도 두 앱이 같은 자리에 놓게.

export const CHART_KINDS = [['table', '표'], ['col', '세로 막대'], ['row', '가로 막대'], ['line', '꺾은선'], ['pie', '원']]
// 계열 색 — dataviz 기본 팔레트 밝은 화면 칸(검사기로 이웃 색 구별 통과, 순서가 색약 안전 장치라 바꾸지 않음). 그래프는 흰 종이 카드라 어두운 화면에도 이 색
export const CHART_COLORS = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6', '#e34948']
export const MAX_SERIES = CHART_COLORS.length
export const CHART_MIN = [360, 240]   // 표 → 그래프로 바꿀 때 이보다 작으면 키움(돌아가면 표 크기로 — `table_wh`)
export const INK = { title: '#18181b', text: '#3f3f46', muted: '#71717a', grid: '#e4e4e7', base: '#a1a1aa', card: '#ffffff', edge: '#d4d4d8' }
const PAD = 14, HEAD = 24, CAT = 20, FS = 11

const r1 = v => Math.round(v * 10) / 10

/** 칸 글 → 숫자(못 읽으면 null). 「1,234」「45%」「$3」「약 1.2억」「-0.5」 — 앞뒤 단위는 버림, 「1~3」「2017-2022」처럼 숫자가 둘이면 null */
export function numOf(s) {
  const t = String(s ?? '').trim().replace(/(\d),(?=\d{3}(\D|$))/g, '$1').replace(/\s+/g, '')
  const m = t.match(/^[^\d+\-.]*([+-]?(?:\d+\.?\d*|\.\d+))([^\d]*)$/)
  return m ? +m[1] : null
}
const unitOf = s => (String(s ?? '').trim().match(/\d\s*([^\d\s][^\d]*)$/)?.[1] || '').trim()

/** 글 폭 어림 — 한글·한자·전각 = 글자 크기, 그 밖 0.56배 */
export const textW = (s, fs) => [...String(s ?? '')].reduce((a, ch) => a + (/[ᄀ-ᇿ⺀-鿿가-힯＀-￯]/.test(ch) ? fs : fs * 0.56), 0)
/** 폭에 맞게 자름(넘치면 끝에 …) */
export function fitText(s, fs, maxW) {
  s = String(s ?? '')
  if (textW(s, fs) <= maxW) return s
  const chars = [...s]
  while (chars.length && textW(chars.join('') + '…', fs) > maxW) chars.pop()
  return chars.length ? chars.join('') + '…' : ''
}

/** 표 → { cats: [이름], series: [{ name, values: [수|null], texts: [칸 글], unit }] }.
 *  첫 열 = 항목 이름(열이 하나뿐이면 1, 2, 3…), 첫 행 = 계열 이름(머리 행이거나 둘째 칸부터가 숫자가 아니면). 숫자가 하나도 없는 열은 계열이 아님 */
export function chartData(it) {
  const cells = it.cells || [], rows = cells.length, cols = Math.max(0, ...cells.map(r => r.length))
  const at = (r, c) => String(cells[r]?.[c] ?? '').trim()
  const c0 = cols >= 2 ? 1 : 0
  const headCells = []; for (let c = c0; c < cols; c++) headCells.push(at(0, c))
  // 첫 행 = 이름 줄: 머리 행이거나, 채운 칸이 모두 글이거나, 모두 연도(「2025」·「2026년」)인데 밑은 연도가 아닐 때
  const filled = headCells.filter(Boolean), year = t => /^(19|20)\d\d\s*년?$/.test(t)
  const below = []; for (let r = 1; r < rows; r++) for (let c = c0; c < cols; c++) if (at(r, c)) below.push(at(r, c))
  const head = rows >= 2 && (!!it.header || (filled.length > 0 && (filled.every(t => numOf(t) == null) || (filled.every(year) && !below.every(year)))))
  const r0 = head ? 1 : 0
  const dataRows = []
  for (let r = r0; r < rows; r++) {
    const label = c0 ? at(r, 0) : String(r - r0 + 1)
    let any = false; for (let c = c0; c < cols; c++) if (numOf(at(r, c)) != null) any = true
    if ((c0 && label) || any) dataRows.push(r)
  }
  const cats = dataRows.map(r => (c0 ? at(r, 0) : String(r - r0 + 1)))
  const series = []
  for (let c = c0; c < cols; c++) {
    const texts = dataRows.map(r => at(r, c)), values = texts.map(numOf)
    if (!values.some(v => v != null)) continue
    const units = texts.filter((t, i) => values[i] != null).map(unitOf).filter(Boolean)
    const unit = units.length && units.every(u => u === units[0]) ? units[0] : ''
    series.push({ name: head ? at(0, c) : '', values, texts, unit })
  }
  return { cats, series }
}

const SHARE = /비중|비율|점유|구성비|몫|share|percent|%/i
/** 그 모양이 안 되는 까닭(되면 '') — 속성 카드가 버튼을 흐리게 하고 툴팁으로 보임 */
export function chartWhy(data, kind) {
  if (kind === 'table') return ''
  const { cats, series } = data
  if (!series.length || !cats.length) return '숫자 칸이 없어요 — 둘째 열부터 숫자를 넣으면 그래프가 돼요'
  if (series.length > MAX_SERIES) return `숫자 열이 ${MAX_SERIES}개를 넘으면 색으로 구별이 안 돼요 — 열을 줄여 주세요`
  if (kind === 'line' && cats.length < 2) return '꺾은선은 항목이 둘 이상일 때만 — 시간 흐름에 써요'
  if (kind === 'pie') {
    if (series.length !== 1) return '원 그래프는 숫자 열이 하나일 때만 — 전체 중 몫을 보여 줘요'
    const v = series[0].values.filter(x => x != null)
    if (v.some(x => x < 0)) return '원 그래프는 음수가 있으면 못 그려요'
    if (cats.length > MAX_SERIES) return `원 그래프는 조각 ${MAX_SERIES}개까지 — 막대가 더 잘 읽혀요`
    const sum = v.reduce((a, b) => a + b, 0)
    const share = SHARE.test(series[0].name) || (series[0].unit === '%' && Math.abs(sum - 100) <= 2)
    if (!share || sum <= 0) return '원 그래프는 합쳐서 전체가 되는 몫(비중·비율)에만 써요 — 열 이름에 「비중」을 쓰거나 합이 100인 %면 켜져요'
  }
  return ''
}
/** 표 아이템의 모든 모양 → 까닭 */
export const chartWhys = it => { const d = chartData(it); return Object.fromEntries(CHART_KINDS.map(([k]) => [k, chartWhy(d, k)])) }
/** 지금 그래프로 그릴 수 있나(안 되면 표로 그림 — 칸을 고쳐 숫자가 사라진 경우 등) */
export const isChart = it => it?.type === 'table' && !!it.chart && it.chart !== 'table' && !chartWhy(chartData(it), it.chart)

/** 눈금 — 0을 포함한 범위, 1·2·2.5·5 × 10ⁿ 간격으로 3~6칸 */
export function niceTicks(lo, hi) {
  lo = Math.min(0, lo); hi = Math.max(0, hi)
  if (hi - lo < 1e-12) hi = lo + 1
  const raw = (hi - lo) / 4, p = 10 ** Math.floor(Math.log10(raw)), step = [1, 2, 2.5, 5, 10].map(k => k * p).find(s => s >= raw)
  const a = Math.floor(lo / step + 1e-9) * step, b = Math.ceil(hi / step - 1e-9) * step, out = []
  for (let v = a; v <= b + step * 1e-6; v += step) out.push(+v.toFixed(10))
  return out
}
export const tickText = v => { const a = Math.abs(v); return a >= 1e4 ? (+(v / 1e4).toFixed(a >= 1e5 ? 0 : 1)).toLocaleString('en-US') + '만' : (+v.toFixed(4)).toLocaleString('en-US') }

// 막대 끝만 둥글게(데이터 끝 4px, 바닥 쪽은 각짐) — M·L·Q·Z만 씀(데스크톱이 같은 글을 읽음)
function barPath(x, y, w, h, dir) {   // dir = 'up'|'down'|'right'|'left' = 둥근 끝 방향
  const r = Math.max(0, Math.min(4, w / 2, h / 2)), X = x + w, Y = y + h, f = n => r1(n)
  if (dir === 'up') return `M${f(x)},${f(Y)} L${f(x)},${f(y + r)} Q${f(x)},${f(y)} ${f(x + r)},${f(y)} L${f(X - r)},${f(y)} Q${f(X)},${f(y)} ${f(X)},${f(y + r)} L${f(X)},${f(Y)} Z`
  if (dir === 'down') return `M${f(x)},${f(y)} L${f(X)},${f(y)} L${f(X)},${f(Y - r)} Q${f(X)},${f(Y)} ${f(X - r)},${f(Y)} L${f(x + r)},${f(Y)} Q${f(x)},${f(Y)} ${f(x)},${f(Y - r)} Z`
  if (dir === 'right') return `M${f(x)},${f(y)} L${f(X - r)},${f(y)} Q${f(X)},${f(y)} ${f(X)},${f(y + r)} L${f(X)},${f(Y - r)} Q${f(X)},${f(Y)} ${f(X - r)},${f(Y)} L${f(x)},${f(Y)} Z`
  return `M${f(X)},${f(y)} L${f(X)},${f(Y)} L${f(x + r)},${f(Y)} Q${f(x)},${f(Y)} ${f(x)},${f(Y - r)} L${f(x)},${f(y + r)} Q${f(x)},${f(y)} ${f(x + r)},${f(y)} Z`
}
const valText = (s, k) => (s.texts[k] || '').trim() || tickText(s.values[k])

/** 그릴 조각들(아이템 안 좌표) — { t: 'rect'|'line'|'path'|'circle'|'text', … }. 마우스 올림 글 = `tip` */
export function chartScene(it) {
  const [x, y, w, h] = it.rect, kind = it.chart, data = chartData(it), { cats, series } = data, out = []
  out.push({ t: 'rect', x, y, w, h, rx: 8, f: INK.card, s: INK.edge, sw: 1 })
  const why = chartWhy(data, kind)
  if (why) { out.push({ t: 'text', x: x + w / 2, y: y + h / 2, s: fitText('숫자 칸이 없어요', FS, w - 2 * PAD), fs: FS, c: INK.muted, a: 'middle' }); return out }
  const L = x + PAD, R = x + w - PAD, T = y + PAD
  // 머리 — 계열 하나 = 그 이름(제목), 여럿 = 색 견본 + 이름(원은 오른쪽 목록이라 머리 없음)
  if (kind !== 'pie') {
    if (series.length === 1) { if (series[0].name) out.push({ t: 'text', x: L, y: T + 8, s: fitText(series[0].name, 13, R - L), fs: 13, b: 1, c: INK.title, a: 'start' }) }
    else {
      const share = (R - L) / series.length   // 견본은 왼쪽부터 붙여 늘어놓되 한 계열이 폭을 넘지 않게
      let sx = L
      series.forEach((s, j) => { const name = fitText(s.name || `계열 ${j + 1}`, FS, share - 20)
        out.push({ t: 'rect', x: r1(sx), y: T + 3, w: 10, h: 10, rx: 2, f: CHART_COLORS[j] })
        out.push({ t: 'text', x: r1(sx + 14), y: T + 8, s: name, fs: FS, c: INK.text, a: 'start' })
        sx += 14 + textW(name, FS) + 16 })
    }
  }
  const top = T + HEAD, bottom = y + h - PAD
  if (kind === 'pie') return pieScene(out, data, L, top - HEAD + 4, R, bottom)
  const all = series.flatMap(s => s.values).filter(v => v != null), ticks = niceTicks(Math.min(...all), Math.max(...all))
  const lo = ticks[0], hi = ticks[ticks.length - 1]
  if (kind === 'row') {
    const labW = Math.min((R - L) * 0.35, Math.max(...cats.map(c => textW(c, FS))) + 8), pl = L + labW, pb = bottom - CAT, band = (pb - top) / cats.length
    const X = v => pl + ((v - lo) / (hi - lo)) * (R - 6 - pl)
    ticks.forEach(v => { out.push({ t: 'line', x1: r1(X(v)), y1: top, x2: r1(X(v)), y2: pb, s: v === 0 ? INK.base : INK.grid, sw: v === 0 ? 1 : 0.75 })
      out.push({ t: 'text', x: r1(X(v)), y: pb + 10, s: tickText(v), fs: 10, c: INK.muted, a: 'middle' }) })
    const inner = band * 0.7, bh = Math.max(1, (inner - 2 * (series.length - 1)) / series.length), labels = cats.length * series.length <= 12 && bh >= 10
    cats.forEach((c, i) => { const cy = top + band * i + band / 2
      out.push({ t: 'text', x: pl - 6, y: r1(cy), s: fitText(c, FS, labW - 8), fs: FS, c: INK.text, a: 'end' })
      series.forEach((s, j) => { const v = s.values[i]; if (v == null) return
        const by = cy - inner / 2 + j * (bh + 2), x0 = X(0), x1 = X(v)
        out.push({ t: 'path', d: barPath(Math.min(x0, x1), by, Math.abs(x1 - x0), bh, v >= 0 ? 'right' : 'left'), f: CHART_COLORS[j], tip: `${c}${s.name ? ' · ' + s.name : ''}: ${valText(s, i)}` })
        if (labels) out.push({ t: 'text', x: r1(v >= 0 ? x1 + 4 : x1 - 4), y: r1(by + bh / 2), s: valText(s, i), fs: 10, c: INK.text, a: v >= 0 ? 'start' : 'end' }) }) })
    return out
  }
  // 세로 막대·꺾은선 — 왼쪽 눈금, 아래 항목
  const tw = Math.max(...ticks.map(v => textW(tickText(v), 10))) + 6, pl = L + tw, pb = bottom - CAT, band = (R - pl) / cats.length
  const Y = v => pb - ((v - lo) / (hi - lo)) * (pb - top - 6)
  ticks.forEach(v => { out.push({ t: 'line', x1: pl, y1: r1(Y(v)), x2: R, y2: r1(Y(v)), s: v === 0 ? INK.base : INK.grid, sw: v === 0 ? 1 : 0.75 })
    out.push({ t: 'text', x: pl - 6, y: r1(Y(v)), s: tickText(v), fs: 10, c: INK.muted, a: 'end' }) })
  cats.forEach((c, i) => out.push({ t: 'text', x: r1(pl + band * i + band / 2), y: pb + 11, s: fitText(c, FS, band - 4), fs: FS, c: INK.text, a: 'middle' }))
  if (kind === 'col') {
    const inner = band * 0.7, bw = Math.max(1, (inner - 2 * (series.length - 1)) / series.length), labels = cats.length * series.length <= 12 && bw >= 16
    cats.forEach((c, i) => series.forEach((s, j) => { const v = s.values[i]; if (v == null) return
      const bx = pl + band * i + (band - inner) / 2 + j * (bw + 2), y0 = Y(0), y1 = Y(v)
      out.push({ t: 'path', d: barPath(bx, Math.min(y0, y1), bw, Math.abs(y1 - y0), v >= 0 ? 'up' : 'down'), f: CHART_COLORS[j], tip: `${c}${s.name ? ' · ' + s.name : ''}: ${valText(s, i)}` })
      if (labels) out.push({ t: 'text', x: r1(bx + bw / 2), y: r1(v >= 0 ? y1 - 8 : y1 + 8), s: valText(s, i), fs: 10, c: INK.text, a: 'middle' }) }))
    return out
  }
  // 꺾은선 — 2px 선, 점 8px(흰 테두리 2px), 계열 하나이고 항목 8개 이하면 값 글
  series.forEach((s, j) => {
    const pts = s.values.map((v, i) => (v == null ? null : [r1(pl + band * i + band / 2), r1(Y(v))]))
    let d = '', pen = false
    pts.forEach(p => { if (!p) { pen = false; return } d += `${pen ? ' L' : (d ? ' M' : 'M')}${p[0]},${p[1]}`; pen = true })
    if (d) out.push({ t: 'path', d, s: CHART_COLORS[j], sw: 2 })
    pts.forEach((p, i) => { if (!p) return
      out.push({ t: 'circle', cx: p[0], cy: p[1], r: 4, f: CHART_COLORS[j], s: INK.card, sw: 2, tip: `${cats[i]}${s.name ? ' · ' + s.name : ''}: ${valText(s, i)}` })
      if (series.length === 1 && cats.length <= 8) out.push({ t: 'text', x: p[0], y: r1(p[1] - 12), s: valText(s, i), fs: 10, c: INK.text, a: 'middle' }) })
  })
  return out
}

// 원 — 왼쪽 원(조각 사이 흰 틈 2px), 오른쪽 목록(견본 · 이름 · 몫 %). 호는 2° 마다 점(데스크톱이 같은 길을 그림)
function pieScene(out, { cats, series }, L, top, R, bottom) {
  const s = series[0], vals = s.values.map(v => (v == null ? 0 : v)), sum = vals.reduce((a, b) => a + b, 0)
  const listW = Math.min((R - L) * 0.45, Math.max(...cats.map(c => textW(c, FS))) + 64)
  if (s.name) { out.push({ t: 'text', x: L, y: top + 4, s: fitText(s.name, 13, R - L), fs: 13, b: 1, c: INK.title, a: 'start' }); top += HEAD }   // 제목 밑부터 원
  const size = Math.min(R - L - listW - 12, bottom - top), cx = L + size / 2, cy = (top + bottom) / 2, rad = size / 2
  let a = -90
  vals.forEach((v, i) => { if (v <= 0) return
    const sweep = (v / sum) * 360, n = Math.max(2, Math.ceil(sweep / 2)), pts = [[cx, cy]]
    for (let k = 0; k <= n; k++) { const t = ((a + (sweep * k) / n) * Math.PI) / 180; pts.push([cx + rad * Math.cos(t), cy + rad * Math.sin(t)]) }
    out.push({ t: 'path', d: 'M' + pts.map(p => `${r1(p[0])},${r1(p[1])}`).join(' L') + ' Z', f: CHART_COLORS[i], s: INK.card, sw: 2, tip: `${cats[i]}: ${valText(s, i)} (${Math.round((v / sum) * 100)}%)` })
    a += sweep })
  const lx = R - listW + 4, rowH = 20, ly0 = cy - (cats.length * rowH) / 2 + rowH / 2
  cats.forEach((c, i) => { const ly = r1(ly0 + i * rowH)
    out.push({ t: 'rect', x: lx, y: ly - 5, w: 10, h: 10, rx: 2, f: CHART_COLORS[i] })
    out.push({ t: 'text', x: lx + 14, y: ly, s: fitText(c, FS, listW - 56), fs: FS, c: INK.text, a: 'start' })
    out.push({ t: 'text', x: R, y: ly, s: sum > 0 ? Math.round((vals[i] / sum) * 100) + '%' : '', fs: FS, b: 1, c: INK.title, a: 'end' }) })
  return out
}
