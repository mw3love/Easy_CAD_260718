// PDF 보기 카드 몸통(2026-10-21 사용자: 휠로 쭉쭉 보다가 Alt+드래그로 칠판에 오려 오기) — 카드 칸 안(foreignObject) HTML.
// 쪽 그림은 서버가 그때그때(`web/pdfview.py`, 보이는 쪽 ±1만 받음). 켜짐(on) = 웹 카드처럼 한 번 눌러 조작 — 휠 = 쪽 넘기기, Alt+끌기 = 오려 오기.
// 오려 오기·위치는 칠판(Editor)이 받는다: 창 신호 `mb-pdf-clip` {id, page, r: [x0, y0, x1, y1](쪽 안 비율), top: 화면 y}.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

export const PDF_GAP = 8          // 쪽 사이(카드 좌표)
const KEEP = new Map()            // 카드 _id → 스크롤 위치(이 창에서만 — 공동작업 상대 카드가 따라 움직이지 않게)
// 보던 자리는 이 브라우저에도 남김(2026-10-21 사용자: 바깥 누르면 첫 쪽 — 다시 열어도 보던 데까지). 칠판 문서엔 안 넣음(남의 화면이 따라 넘어가지 않게)
const keyOf = it => 'mb-pdf-top:' + (it.url || it._id)
export function pdfTop(it) {
  if (KEEP.has(it._id)) return KEEP.get(it._id)
  let v = 0; try { v = +(localStorage.getItem(keyOf(it)) || 0) || 0 } catch { /* 저장소 막힘 — 처음부터 */ }
  KEEP.set(it._id, v); return v
}
function saveTop(it, t) { KEEP.set(it._id, t); try { localStorage.setItem(keyOf(it), String(Math.round(t))) } catch { /* 저장소 막힘 — 이 창에서만 */ } }

// 쪽마다 [위, 높이](카드 폭 w 기준)
export function pdfLayout(it, w) {
  let y = 0
  return (it.sizes || []).map(([pw, ph]) => { const h = w * ph / pw, o = [y, h]; y += h + PDF_GAP; return o })
}
// 카드 몸통 안 y(카드 좌표, 몸통 위 = 0)에 있는 쪽 번호(0부터) — 보던 스크롤 자리 기준. 우클릭 「이 쪽 통째로」·잠든 카드 그림
export function pdfPageAt(it, y) {
  const lay = pdfLayout(it, it.rect[2]), t = pdfTop(it) + y, i = lay.findIndex(([py, ph]) => t < py + ph + PDF_GAP)
  return i < 0 ? Math.max(0, lay.length - 1) : i
}

// 쪽마다 보이지 않는 글 층(2026-10-21 사용자: 「글로」 단추 대신 PDF 안에서 끌어 글 고르기) — 서버가 준 줄 상자에 투명 글자를 겹쳐
// 브라우저가 원래 하는 끌어 고르기·Ctrl+C를 그대로 씀(PDF.js 없이). 글꼴이 달라 폭은 줄마다 scaleX로 맞춤
const LINES = new Map()   // `${주소}/${쪽}` → 줄 목록 | Promise
const SEL_CSS = '.mb-pdftext ::selection { background: rgba(37, 99, 235, .32); color: transparent }'
function PageText({ it, i, w, top, ph }) {
  const k = `${it.url}/${i}`, [lines, setLines] = useState(() => (Array.isArray(LINES.get(k)) ? LINES.get(k) : null)), ref = useRef(null)
  useEffect(() => {
    if (lines) return
    let live = true
    if (!LINES.has(k)) LINES.set(k, fetch(`${it.url}/lines/${i}`).then(r => r.json()).then(d => { LINES.set(k, d.lines || []); return d.lines || [] }, () => { LINES.delete(k); return [] }))
    Promise.resolve(LINES.get(k)).then(v => { if (live) setLines(v) })
    return () => { live = false }
  }, [k])   // eslint-disable-line
  useLayoutEffect(() => {   // 줄 폭 맞추기 — 화면 글꼴로 잰 폭 → 상자 폭
    for (const el of ref.current?.querySelectorAll('span') || []) { const want = +el.dataset.w, got = el.offsetWidth; if (want && got) el.style.transform = `scaleX(${want / got})` }
  }, [lines, w, ph])
  if (!lines?.length) return null
  return <div ref={ref} className="mb-pdftext" style={{ position: 'absolute', left: 0, top, width: w, height: ph, userSelect: 'text', cursor: 'text' }}>
    {lines.map(([x0, y0, x1, y1, t], j) => { const lh = (y1 - y0) * ph
      return <span key={j} data-w={(x1 - x0) * w} style={{ position: 'absolute', left: x0 * w, top: y0 * ph, height: lh, fontSize: lh * 0.86, lineHeight: `${lh}px`, whiteSpace: 'pre', color: 'transparent', transformOrigin: '0 0', fontFamily: 'sans-serif' }}>{t}</span> })}
  </div>
}

// 끌어 고른 PDF 글 — 줄 사이를 줄바꿈으로(브라우저 기본 복사는 떠 있는 줄을 그냥 붙여 「convolutionsentirely」가 됨. <br>을 끼우면
// 여백에서 끌기 시작할 때 첫 줄을 놓침 — 2026-10-21 시험). 고른 것이 PDF 글 층 밖이면 ""
export function pdfSelectedText() {
  const sel = window.getSelection?.(); if (!sel?.rangeCount || sel.isCollapsed) return ''
  const rg = sel.getRangeAt(0), parts = []
  for (const sp of document.querySelectorAll('.mb-pdftext span')) {
    if (!rg.intersectsNode(sp)) continue
    const tn = sp.firstChild, t = sp.textContent, a = rg.startContainer === tn ? rg.startOffset : 0, b = rg.endContainer === tn ? rg.endOffset : t.length
    if (b > a) parts.push(t.slice(a, b))
  }
  return parts.join('\n')
}
if (typeof document !== 'undefined') document.addEventListener('copy', e => { const t = pdfSelectedText(); if (t) { e.clipboardData.setData('text/plain', t); e.preventDefault() } })

export function PdfPages({ it, w, h, on }) {
  const box = useRef(null), [top, setTop] = useState(() => pdfTop(it)), [px, setPx] = useState(1200), [sel, setSel] = useState(null)
  const lay = pdfLayout(it, w), total = lay.length ? lay[lay.length - 1][0] + lay[lay.length - 1][1] : 0
  useLayoutEffect(() => { if (box.current) box.current.scrollTop = pdfTop(it) }, [on])   // eslint-disable-line
  // 휠 = 카드 안 스크롤(칠판 확대로 안 가게 — 칠판 휠은 svg가 직접 듣는 신호라 여기서 막음). Ctrl+휠은 그대로 칠판 확대
  useEffect(() => {
    const el = box.current; if (!el) return
    const onWheel = e => { if (on && !e.ctrlKey) e.stopPropagation() }
    el.addEventListener('wheel', onWheel); return () => el.removeEventListener('wheel', onWheel)
  }, [on])
  // 받을 그림 폭 — 화면에 보이는 크기 × 화면 배율 × 1.5(작은 글자가 또렷하게 — 2026-10-21 사용자: 화질), 너무 잦게 다시 받지 않게 네 단계
  useEffect(() => {
    const el = box.current; if (!el) return
    const k = el.getBoundingClientRect().width / Math.max(1, el.offsetWidth), need = w * k * (window.devicePixelRatio || 1) * 1.5
    setPx(need <= 800 ? 800 : need <= 1200 ? 1200 : need <= 1700 ? 1700 : 2400)
  })
  const onScroll = e => { const t = e.currentTarget.scrollTop; saveTop(it, t); setTop(t) }
  const pageAt = y => { const i = lay.findIndex(([py, ph]) => y < py + ph + PDF_GAP); return i < 0 ? lay.length - 1 : i }
  const cur = lay.length ? pageAt(top + h * 0.3) : 0
  const local = e => { const r = box.current.getBoundingClientRect(), k = r.width / Math.max(1, box.current.offsetWidth); return { x: (e.clientX - r.left) / k, y: (e.clientY - r.top) / k + box.current.scrollTop } }
  const down = e => {
    if (!on || e.button === 2) return   // 우클릭 = 칠판 메뉴(「이 쪽 통째로 칠판에」)
    e.stopPropagation()   // 칠판이 「바깥 누름 = 조작 끝」으로 받지 않게
    if (!e.altKey || e.button !== 0) return
    e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId)
    const p = local(e), i = pageAt(p.y); setSel({ i, a: p, b: p })
  }
  const move = e => { if (sel) setSel(s => ({ ...s, b: local(e) })) }
  const up = e => {
    if (!sel) return
    const s = sel; setSel(null)
    const [py, ph] = lay[s.i], cl = (v, lo, hi) => Math.max(lo, Math.min(hi, v))
    const x0 = cl(Math.min(s.a.x, s.b.x), 0, w), x1 = cl(Math.max(s.a.x, s.b.x), 0, w), y0 = cl(Math.min(s.a.y, s.b.y), py, py + ph), y1 = cl(Math.max(s.a.y, s.b.y), py, py + ph)
    if (x1 - x0 < 4 || y1 - y0 < 4) return   // 그냥 누름
    const r = box.current.getBoundingClientRect(), k = r.width / Math.max(1, box.current.offsetWidth)
    window.dispatchEvent(new CustomEvent('mb-pdf-clip', { detail: { id: it._id, page: s.i, r: [x0 / w, (y0 - py) / ph, x1 / w, (y1 - py) / ph],
      top: r.top + (y0 - box.current.scrollTop) * k } }))
    e.stopPropagation()
  }
  const rect = sel && { left: Math.min(sel.a.x, sel.b.x), top: Math.min(sel.a.y, sel.b.y), width: Math.abs(sel.a.x - sel.b.x), height: Math.abs(sel.a.y - sel.b.y) }
  return <div style={{ position: 'relative', width: w, height: h }}>
    {on && <style>{SEL_CSS}</style>}
    <div ref={box} data-pdfid={it._id} onScroll={onScroll} onPointerDown={down} onPointerMove={move} onPointerUp={up}
      style={{ position: 'absolute', inset: 0, overflowY: on ? 'auto' : 'hidden', overflowX: 'hidden', background: '#e4e4e7', pointerEvents: on ? 'auto' : 'none', cursor: on ? 'crosshair' : 'default', overscrollBehavior: 'contain' }}>
      <div style={{ position: 'relative', height: total }}>
        {lay.map(([py, ph], i) => (py + ph < top - h || py > top + 2 * h ? null   // 보이는 쪽 ±1 화면만
          : <img key={i} alt={`${i + 1}쪽`} draggable={false} src={`${it.url}/page/${i}?w=${px}`} style={{ position: 'absolute', left: 0, top: py, width: w, height: ph, background: '#fff', display: 'block', userSelect: 'none' }} />))}
        {on && lay.map(([py, ph], i) => (py + ph < top - h || py > top + 2 * h ? null : <PageText key={'t' + i} it={it} i={i} w={w} top={py} ph={ph} />))}
        {rect && <div style={{ position: 'absolute', ...rect, border: '1.5px solid #da7756', background: 'rgba(218,119,86,.12)', pointerEvents: 'none' }} />}
      </div>
    </div>
    {lay.length > 0 && <div style={{ position: 'absolute', right: 8, bottom: 8, padding: '2px 8px', borderRadius: 99, background: 'rgba(24,24,27,.72)', color: '#fff', font: "600 11px 'Pretendard', sans-serif", pointerEvents: 'none' }}>{cur + 1} / {lay.length}</div>}
  </div>
}
