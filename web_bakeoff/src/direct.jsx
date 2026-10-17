// 직접 만들기 표본 — DOM 상자(글은 브라우저 기본 서식 편집 contenteditable) + SVG 화살표 + 이동·확대·저장.
import { TITLE, CARDS, BOARD, CARD_POS, CARD_SIZE, FIG } from './board.js'
const KEY = 'bakeoff-direct'
const root = document.getElementById('root')
root.innerHTML = `<style>
  #vp{position:absolute;inset:0;overflow:hidden;background:#f3f4f6;font-family:Pretendard,sans-serif;cursor:default}
  #world{position:absolute;left:0;top:0;transform-origin:0 0}
  .board{position:absolute;background:#fff;box-shadow:0 2px 12px #0002}
  .it{position:absolute;box-sizing:border-box}
  .it.sel{outline:2px solid #3b82f6}
  .card{border-left:6px solid #2f6fb3;background:#f2f6fb;padding:18px 22px;font-size:22px;line-height:1.5;color:#1e2b45;display:flex;align-items:center}
  .card.hot{border-color:#e8613c;background:#fdf1ec}
  .title{font-size:44px;font-weight:800;color:#1e2b45;white-space:nowrap}
  [contenteditable]:focus{outline:none}
  svg{position:absolute;left:0;top:0;overflow:visible;pointer-events:none}
</style><div id="vp"><div id="world"></div></div>`
const vp = document.getElementById('vp'), world = document.getElementById('world')
let view = { x: 40, y: 40, s: 0.7 }
const apply = () => world.style.transform = `translate(${view.x}px,${view.y}px) scale(${view.s})`

const html = runs => '<span>' + runs.map(([t, b]) => b ? `<b>${t}</b>` : t).join('') + '</span>'   // flex 안 글 덩어리가 공백을 먹지 않게 한 겹
function defaults() {
  return [
    { id: 'board', kind: 'board', x: BOARD.x, y: BOARD.y, w: BOARD.w, h: BOARD.h },
    { id: 'title', kind: 'title', x: 80, y: 70, html: TITLE },
    ...CARDS.map((r, i) => ({ id: 'card' + i, kind: 'card', hot: i === 2, x: CARD_POS[i][0], y: CARD_POS[i][1], w: CARD_SIZE[0], h: CARD_SIZE[1], html: html(r) })),
    { id: 'fig', kind: 'img', src: '/figure.svg', x: FIG.x, y: FIG.y, w: FIG.w, h: FIG.h },
    { id: 'a0', kind: 'arrow', from: 'card0', to: 'card1' }, { id: 'a1', kind: 'arrow', from: 'card1', to: 'card2' },
  ]
}
let items; try { items = JSON.parse(localStorage.getItem(KEY)) } catch {} ; items ||= defaults()
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(items)) } catch {} }
const byId = id => items.find(i => i.id === id)
const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')

function render() {
  world.innerHTML = ''
  for (const it of items) {
    if (it.kind === 'arrow') continue
    const el = document.createElement(it.kind === 'img' ? 'img' : 'div')
    el.className = 'it ' + (it.kind === 'board' ? 'board' : it.kind) + (it.hot ? ' hot' : '')
    Object.assign(el.style, { left: it.x + 'px', top: it.y + 'px' })
    if (it.w) Object.assign(el.style, { width: it.w + 'px', height: it.h + 'px' })
    if (it.kind === 'img') { el.src = it.src; el.draggable = false }
    if (it.html != null) { el.innerHTML = it.html; el.ondblclick = () => { el.contentEditable = true; el.focus() }
      el.onblur = () => { el.contentEditable = false; it.html = el.innerHTML; save() } }
    el.dataset.id = it.id; world.appendChild(el)
  }
  world.appendChild(svg); drawArrows()
}
function drawArrows() {
  svg.innerHTML = '<defs><marker id="h" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0L10,5L0,10z" fill="#1e2b45"/></marker></defs>'
  for (const a of items.filter(i => i.kind === 'arrow')) {
    const f = byId(a.from), t = byId(a.to)
    const p = document.createElementNS(svg.namespaceURI, 'line')
    Object.entries({ x1: f.x + f.w, y1: f.y + f.h / 2, x2: t.x - 4, y2: t.y + t.h / 2, stroke: '#1e2b45', 'stroke-width': 3, 'marker-end': 'url(#h)' })
      .forEach(([k, v]) => p.setAttribute(k, v))
    svg.appendChild(p)
  }
}
let drag = null
vp.addEventListener('pointerdown', e => {
  const el = e.target.closest('.it'); if (el?.isContentEditable) return
  document.querySelectorAll('.sel').forEach(n => n.classList.remove('sel'))
  if (el && el.dataset.id !== 'board') { el.classList.add('sel'); drag = { it: byId(el.dataset.id), el, x: e.clientX, y: e.clientY } }
  else drag = { pan: true, x: e.clientX, y: e.clientY }
})
addEventListener('pointermove', e => { if (!drag) return
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY
  if (drag.pan) { view.x += dx; view.y += dy; apply(); return }
  drag.it.x += dx / view.s; drag.it.y += dy / view.s
  drag.el.style.left = drag.it.x + 'px'; drag.el.style.top = drag.it.y + 'px'; drawArrows() })
addEventListener('pointerup', () => { if (drag && !drag.pan) save(); drag = null })
vp.addEventListener('wheel', e => { e.preventDefault(); const k = Math.exp(-e.deltaY / 500)
  view.x = e.clientX - (e.clientX - view.x) * k; view.y = e.clientY - (e.clientY - view.y) * k; view.s *= k; apply() }, { passive: false })
apply(); document.fonts.ready.then(render)
