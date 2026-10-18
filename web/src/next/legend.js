// 범례(§8 항목61 4-b ④, 2026-10-18 사용자: 모아서 한 번 만들기 · 선·화살표만) — 도면에 쓴 선 종류(색 + 모양 + 굵기)를 모아
// 견본 선 + 이름 글을 묶음으로 놓는다. 보통 도형(선·글·네모)이라 데스크톱에서도 그대로 보인다.
// 표시 칸: 범례 틀 네모 `legend: 배율`·제목 `legend: true`, 줄마다 견본 선·이름 글 `legend_key`(다시 모을 때 적어 둔 이름을 지키려고 — 데스크톱도 보존).

const LINEY = new Set(['line', 'sarrow', 'arrow', 'polygon', 'path'])
const STYLE_NAMES = { 1: '실선', 2: '파선', 3: '점선', 4: '일점쇄선', 5: '이점쇄선' }
export const isLegendPart = it => !!(it.legend || it.legend_key)

const penOf = it => (it.type === 'sarrow' || it.type === 'arrow' ? it.color : it.pen)
const argb = c => { const m = /^#([0-9a-f]{8})$/i.exec(c || ''); return m ? m[1].toLowerCase() : (/^#([0-9a-f]{6})$/i.exec(c || '') ? 'ff' + c.slice(1).toLowerCase() : null) }

// 모을 선 — 색이 보이는 것만(투명 빼기), 채운 도형의 테두리·판서 레이어·이미 있는 범례는 빼기
export function legendEntries(items, skipLayer = 'pen-notes') {
  const map = new Map()
  for (const it of items) {
    if (!LINEY.has(it.type) || isLegendPart(it) || it.layer_id === skipLayer) continue
    if ((it.type === 'polygon' && it.closed && it.fill) || (it.type === 'path' && it.fill)) continue
    const c = argb(penOf(it)); if (!c || c.startsWith('00') || !(it.width > 0)) continue
    const width = Math.round(it.width * 10) / 10, style = it.style || 1, key = `${c}|${style}|${width}`
    const e = map.get(key) || { key, color: '#' + c, style, width, count: 0, arrow: false }
    e.count += 1; if (it.type === 'sarrow' || it.type === 'arrow') e.arrow = true
    map.set(key, e)
  }
  return [...map.values()].sort((a, b) => b.count - a.count || a.key.localeCompare(b.key))
}

// 색 이름(쉬운 말) — 채도가 낮으면 검정·회색·흰색, 아니면 색상각으로
export function colorName(c) {
  const h = argb(c); if (!h) return '색'
  const r = parseInt(h.slice(2, 4), 16) / 255, g = parseInt(h.slice(4, 6), 16) / 255, b = parseInt(h.slice(6, 8), 16) / 255
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), s = mx ? (mx - mn) / mx : 0
  if (s < 0.18 || mx - mn < 0.08) return mx < 0.25 ? '검정' : mx > 0.85 ? '흰색' : '회색'
  let hue = mx === r ? ((g - b) / (mx - mn)) % 6 : mx === g ? (b - r) / (mx - mn) + 2 : (r - g) / (mx - mn) + 4
  hue = (hue * 60 + 360) % 360
  return hue < 15 ? '빨강' : hue < 42 ? (mx < 0.85 ? '갈색' : '주황') : hue < 68 ? '노랑' : hue < 160 ? '초록' : hue < 200 ? '하늘' : hue < 255 ? '파랑' : hue < 290 ? '보라' : hue < 335 ? '자홍' : '빨강'
}
export const defaultName = e => `${colorName(e.color)} · ${STYLE_NAMES[e.style] || '실선'} · ${e.width}px`

// 범례 아이템들 — at = 왼쪽 위(칠판 좌표), s = 크기 배율(화면에서 보통 글 크기로 보이게 ÷ 확대율), names = 다시 모을 때 지킬 이름 { key: 글 }
// make(extra) = 기본 칸(_id·pos·z…)을 채워 주는 함수(편집기의 base)
export function buildLegend(entries, at, s, names, make, z0 = 0) {
  const gid = 'legend-' + Math.random().toString(36).slice(2, 8), PAD = 12 * s, ROW = 24 * s, SAMPLE = 44 * s, FONT = 10 * s, TITLE = 11 * s
  const textW = t => t.length * FONT * 1.25   // 대강(틀 폭만 정함 — 글 상자 자체는 그릴 때 잰다)
  const dup = new Map(); for (const e of entries) dup.set(defaultName(e), (dup.get(defaultName(e)) || 0) + 1)
  const first = e => (dup.get(defaultName(e)) > 1 ? `${defaultName(e)} ${e.color.length === 9 ? '#' + e.color.slice(3) : e.color}` : defaultName(e))   // 처음 이름이 겹치면 색 코드를 붙여 구별
  const rows = entries.map(e => ({ e, name: names?.[e.key] ?? first(e) }))
  const w = PAD * 3 + SAMPLE + Math.max(textW('범례') * 1.2, ...rows.map(r => textW(r.name)), 80 * s), h = PAD * 2 + TITLE * 1.9 + rows.length * ROW
  const out = [make({ pos: [at.x, at.y], type: 'rect', rect: [0, 0, w, h], pen: '#ffa1a1aa', width: 1, fill: null, style: 1, radius: 8 * s, legend: s, group_id: gid, z: z0 })]   // 틀의 legend = 크기 배율(다시 모을 때 같은 크기로)
  out.push(make({ pos: [at.x + PAD - 4 * s, at.y + PAD - 4 * s], type: 'text', text: '범례', color: '#ff1f1f1f', font: TITLE, bold: true, bg: null, legend: true, group_id: gid, z: z0 + 1 }))
  rows.forEach(({ e, name }, i) => {
    const cy = at.y + PAD + TITLE * 1.9 + i * ROW + ROW / 2
    out.push(make({ pos: [0, 0], type: 'line', line: [at.x + PAD, cy, at.x + PAD + SAMPLE, cy], pen: e.color.length === 9 ? e.color : '#ff' + e.color.slice(1), width: e.width, style: e.style, legend_key: e.key, group_id: gid, z: z0 + 1 }))
    out.push(make({ pos: [at.x + PAD * 2 + SAMPLE - 4 * s, cy - FONT * 0.9], type: 'text', text: name, color: '#ff1f1f1f', font: FONT, bg: null, legend_key: e.key, group_id: gid, z: z0 + 1 }))
  })
  return out
}

// 다시 모으기 — 범례 묶음에서 적어 둔 이름 { key: 글 }과 틀 왼쪽 위
export function legendState(items, gid) {
  const names = {}, frame = items.find(it => it.group_id === gid && it.legend && it.type === 'rect')
  for (const it of items) if (it.group_id === gid && it.type === 'text' && it.legend_key) names[it.legend_key] = it.text
  return { names, at: frame ? { x: frame.pos[0], y: frame.pos[1] } : null, scale: typeof frame?.legend === 'number' ? frame.legend : 1, z: frame?.z ?? 0 }
}
