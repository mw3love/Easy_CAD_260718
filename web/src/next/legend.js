// 범례(§8 항목61 4-b ④) — 도면에 쓴 선 종류(색 + 모양 + 굵기)를 모은다. 2026-10-18 1판 = 선·글을 묶은 도형(우클릭 「만들기·다시 모으기」),
// 2026-10-19 2판 = 표 모양 새 종류 `legend`(아래). 1판 표시 칸 `legend`·`legend_key`는 남은 옛 범례를 모으기에서 빼려고 그대로 알아봄.

const LINEY = new Set(['line', 'sarrow', 'arrow', 'polygon', 'path'])
export const STYLE_NAMES = { 1: '실선', 2: '파선', 3: '점선', 4: '일점쇄선', 5: '이점쇄선' }
export const isLegendPart = it => !!(it.legend || it.legend_key)

// ── 범례 2판(2026-10-19 사용자: 표 모양 · 자동 갱신 · 종류·굵기는 고르기) ──
// .ecad 새 종류 `legend` = { rect, rows: [{ key, color, style, width, count, arrow }], names: { key: 이름 }, scale }.
// rows는 저장할 때마다(편집기 commit) 도면에서 다시 모은 값 — 사람이 적는 건 names뿐. 데스크톱은 보존만(웹 마무리 뒤 맞추기).
export const LEGEND = { PAD: 10, TITLE: 13, HEAD: 30, ROW: 26, FONT: 12, SAMPLE: 48, GAP: 12 }
export const legendKey = it => {   // 선 하나의 범례 열쇠(색|모양|굵기) — 모을 선이 아니면 null
  const c = argb(penOf(it)); if (!c || c.startsWith('00') || !(it.width > 0)) return null
  return `${c}|${it.style || 1}|${Math.round(it.width * 10) / 10}`
}
export const isLegendLine = (it, skipLayer = 'pen-notes') => LINEY.has(it.type) && !isLegendPart(it) && it.layer_id !== skipLayer &&
  !((it.type === 'polygon' && it.closed && it.fill) || (it.type === 'path' && it.fill))
export const descOf = e => `${STYLE_NAMES[e.style] || '실선'} · ${e.width}px`
export const rowName = (it, e) => it.names?.[e.key] ?? colorName(e.color)
// 저장 길목에서 — 범례마다 줄을 지금 도면에 맞춤(바뀐 게 없으면 그 아이템 그대로 = 저장할 것도 없음)
export function syncLegends(items) {
  if (!items.some(it => it.type === 'legend')) return items
  const rows = legendEntries(items), sig = JSON.stringify(rows)
  return items.map(it => (it.type === 'legend' && JSON.stringify(it.rows || []) !== sig ? { ...it, rows } : it))
}
// 범례 줄 하나 일괄 바꾸기 — 그 열쇠의 선 전부에 patch({ color?, style?, width? }), 범례 이름은 새 열쇠로 옮김
export function restyleLegendRow(items, key, patch) {
  let newKey = null
  const out = items.map(it => {
    if (!isLegendLine(it) || legendKey(it) !== key) return it
    const p = {}
    if (patch.color) p[it.type === 'sarrow' || it.type === 'arrow' ? 'color' : 'pen'] = patch.color
    if (patch.style) p.style = patch.style
    if (patch.width) p.width = patch.width
    const n = { ...it, ...p }; newKey = legendKey(n); return n
  })
  if (!newKey || newKey === key) return out
  return out.map(it => { if (it.type !== 'legend' || it.names?.[key] == null) return it
    const names = { ...it.names, [newKey]: it.names[newKey] ?? it.names[key] }; delete names[key]; return { ...it, names } })
}

const penOf = it => (it.type === 'sarrow' || it.type === 'arrow' ? it.color : it.pen)
const argb = c => { const m = /^#([0-9a-f]{8})$/i.exec(c || ''); return m ? m[1].toLowerCase() : (/^#([0-9a-f]{6})$/i.exec(c || '') ? 'ff' + c.slice(1).toLowerCase() : null) }

// 모을 선 — 색이 보이는 것만(투명 빼기), 채운 도형의 테두리·판서 레이어·이미 있는 범례는 빼기
export function legendEntries(items, skipLayer = 'pen-notes') {
  const map = new Map()
  for (const it of items) {
    if (!isLegendLine(it, skipLayer)) continue
    const key = legendKey(it); if (!key) continue
    const [c, style, width] = key.split('|')
    const e = map.get(key) || { key, color: '#' + c, style: +style, width: +width, count: 0, arrow: false }
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
