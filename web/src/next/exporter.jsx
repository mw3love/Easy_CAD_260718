// PNG·PDF·SVG 내보내기 — 데스크톱 `fileio/pdf_export.py`와 같은 규칙: 전체(용지틀이 있으면 그 틀 = 용지·여백 0) 또는 고른 것,
// 용지 A4~A0·방향(자동 = 내용이 가로로 길면 가로)·여백 mm, 내용은 2% 덧대어 용지 안에 비율 유지·가운데. 밝은 칠판 잉크(흰 잉크 → 검정), 투명 배경은 PNG·SVG만.
// PNG는 200dpi(데스크톱 기본), PDF는 브라우저 인쇄 창 「PDF로 저장」(선·글이 벡터 그대로 — 새 라이브러리 없이), SVG는 파일 그대로.
import { renderToStaticMarkup } from 'react-dom/server'
import { Item, setInkDark, setExportCards, docPageW } from './render.jsx'

export const PAPERS = { A4: [210, 297], A3: [297, 420], A2: [420, 594], A1: [594, 841], A0: [841, 1189] }   // 세로 기준 mm
const FONT_FILES = { 400: 'Regular', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold' }

export async function fontFaces(weights) {   // 보드 글꼴(Pretendard)은 그림으로 바꿀 때 글꼴을 못 찾아서 파일째 넣음(윈도우 글꼴은 그대로 찾음)
  const out = []
  for (const w of weights) {
    const blob = await (await fetch(`/fonts/Pretendard-${FONT_FILES[w]}.woff2`)).blob()
    const url = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(blob) })
    out.push(`@font-face{font-family:'Pretendard';font-weight:${w};src:url(${url}) format('woff2')}`)
  }
  return out.join('')
}
export const usesBoardFont = it => it.type === 'memo' || it.family || it.label?.family || (it.labels || []).some(L => L.family)   // 메모 = 보드 글꼴로 그림
export const weightsOf = items => { const s = new Set([400, 700]); for (const it of items) if (it.weight && FONT_FILES[it.weight]) s.add(it.weight); return [...s] }

// entries = [[아이템, 순번]] 그리는 차례, src = 칠판 상자, opts = { page, orient, margin, transparent, frame }
// → { svg 글, pw, ph (mm) }
export async function buildSvg(entries, src, { page = 'A4', orient = null, margin = 10, transparent = false, frame = null, tight = false, clip = false, format = 'pdf', cards = null }, onBoard, routes, embedFonts = true) {   // cards = 문서 카드 모습('pdf'·'img'·'html' — render.jsx setExportCards)   // clip = 프레임(틀 안만 — 여백 없이 그 영역, PDF는 고른 용지에 맞춤)
  let pageKey = page, land, m = margin, box = src
  if (frame) { pageKey = frame.size in PAPERS ? frame.size : 'A4'; land = frame.orient === 'landscape'; m = 0; box = frame.box }   // 용지틀 = 정확한 용지 경계
  else if (clip) { box = src; land = orient ? orient === 'landscape' : box.w >= box.h; if (format !== 'pdf' || page === 'frame') { tight = true } }   // PNG·SVG·PDF 용지 「프레임」(2026-11-04 — 여백 없는 책·그림 장) = 프레임 비율 그대로
  else { const pad = Math.max(src.w, src.h) * 0.02; box = { x: src.x - pad, y: src.y - pad, w: src.w + 2 * pad, h: src.h + 2 * pad }; land = orient ? orient === 'landscape' : box.w >= box.h }
  let [a, b] = PAPERS[pageKey] || PAPERS.A4, pw = land ? b : a, ph = land ? a : b
  if (tight) { m = 0; pw = box.w * 25.4 / 96; ph = box.h * 25.4 / 96; if (clip) { const up = Math.max(1, 297 / Math.max(pw, ph)); pw *= up; ph *= up } }   // 프레임 그림은 긴 변 297mm 이상(작게 그린 틀도 선명하게)   // 그림으로 복사 — 용지 없이 화면 100% 크기(96dpi)
  const aw = pw - 2 * m, ah = ph - 2 * m, k = Math.min(aw / box.w, ah / box.h), tx = m + (aw - box.w * k) / 2, ty = m + (ah - box.h * k) / 2
  const wasDark = document.documentElement.dataset.theme === 'dark'
  setInkDark(false)   // 종이 = 밝은 칠판 잉크(데스크톱 `_swap_white_to_black_for_print`와 같은 뜻)
  setExportCards(cards)
  let body
  try { body = renderToStaticMarkup(<svg x={tx} y={ty} width={box.w * k} height={box.h * k} viewBox={`${box.x} ${box.y} ${box.w} ${box.h}`} overflow={clip ? 'hidden' : 'visible'} style={{ '--z': 1000 }}>
    {entries.map(([it, i]) => <Item key={it._id} it={it} idx={i} onBoard={onBoard[i]} route={routes.get(i)} />)}</svg>) }   // 안쪽 svg = 틀 자리 창(프레임이면 밖은 잘림)
  finally { setInkDark(wasDark); setExportCards(null) }
  const fonts = embedFonts && entries.some(([it]) => usesBoardFont(it)) ? await fontFaces(weightsOf(entries.map(e => e[0]))) : ''
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${pw}mm" height="${ph}mm" viewBox="0 0 ${pw} ${ph}">`
    + (fonts ? `<style>${fonts}</style>` : '') + (transparent ? '' : `<rect width="${pw}" height="${ph}" fill="#ffffff"/>`) + body + '</svg>'
  return { svg, pw, ph }
}

export const download = (blob, name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000) }

export async function pngBlob({ svg, pw, ph }, dpi = 200) {
  const W = Math.max(1, Math.round(pw / 25.4 * dpi)), H = Math.max(1, Math.round(ph / 25.4 * dpi))
  const img = new Image(), url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }))
  await new Promise((ok, bad) => { img.onload = ok; img.onerror = bad; img.src = url })
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H; cv.getContext('2d').drawImage(img, 0, 0, W, H); URL.revokeObjectURL(url)
  return new Promise(r => cv.toBlob(r, 'image/png'))
}
export async function exportPng(res, name, dpi = 200) { download(await pngBlob(res, dpi), name) }
export const exportSvg = ({ svg }, name) => download(new Blob([svg], { type: 'image/svg+xml' }), name)

// ── PDF 끝에 문서 쪽(2026-11-11 화면 검사 8단계 사용자 결정 — 칠판 쪽 뒤에 문서 카드의 문서를 이어 인쇄) ──
// 새 도구 없이 지금 인쇄 길(숨은 틀 + 브라우저 「PDF로 저장」) 그대로: 문서마다 그림자 칸(shadow DOM)에 넣어 문서의 글씨 규칙이 칠판 쪽과 섞이지 않게 하고, 글은 종이에서 저절로 쪽이 나뉨.
// 문서 폭(794·1000px)은 A4 세로 글 칸(190mm)에 맞춰 줄임. 틀은 sandbox(스크립트 없음 — 문서 HTML의 on…= 같은 것이 앱 쪽에서 돌지 않게), 그래도 script·on… 속성은 떼고 넣음
const DOC_PAGE_CSS = '@page mbdoc{size:210mm 297mm;margin:10mm}.mbdoc{page:mbdoc;break-before:page;display:block}'
const DOC_CONTENT = { w: 190 * 96 / 25.4, h: 277 * 96 / 25.4 }   // 글 칸(px, 96dpi)
const docParts = html => {   // 문서 HTML → 글씨 규칙·몸통 노드(DOMParser는 스크립트를 안 돌림)
  const d = new DOMParser().parseFromString(String(html || ''), 'text/html')
  d.querySelectorAll('script,iframe,object,embed,base,meta,noscript,link:not([rel~=stylesheet])').forEach(e => e.remove())
  for (const e of d.querySelectorAll('*')) for (const a of [...e.attributes]) if (/^on/i.test(a.name) || /^\s*javascript:/i.test(a.value)) e.removeAttribute(a.name)
  // html·body·:root 고르는 말 = 그림자 칸의 뿌리(.mbdoc-root) — 고르는 말 자리({ 앞)만 바꿈
  const css = [...d.querySelectorAll('style')].map(st => st.textContent.replace(/\/\*[\s\S]*?\*\//g, '')).join('\n')
    .replace(/(^|[{}])([^{}@]*)(?=\{)/g, (m, a, sel) => a + sel.replace(/(?::root|html)\s+body(?![-\w])/g, 'body').replace(/(^|[\s,>+~(])(?::root|html|body)(?![-\w])/g, '$1.mbdoc-root'))
  d.querySelectorAll('style').forEach(e => e.remove())
  return { css, links: [...d.querySelectorAll('link')].map(l => l.href), body: [...d.body.childNodes], bodyStyle: d.body.getAttribute('style') || '', bodyClass: d.body.getAttribute('class') || '' }
}
const fillDocs = (d, docs) => docs.forEach((it, i) => {   // d = 인쇄 틀 문서 — 문서마다 <div class="mbdoc" id="mbdoc{i}">에 그림자 칸
  const host = d.getElementById('mbdoc' + i); if (!host || host.shadowRoot) return
  const P = docParts(it.html), W = docPageW(it), sh = host.attachShadow({ mode: 'open', serializable: true })   // serializable = 화면 시험이 쪽 수를 셀 때 통째로 꺼냄
  host.style.cssText = `width:${W}px;zoom:${(DOC_CONTENT.w / W).toFixed(4)}`
  const st = d.createElement('style'); st.textContent = `:host{display:block}.mbdoc-root{display:block;background:#fff;color:#18181b;font-family:'Pretendard',sans-serif;margin:0}\n${P.css}`; sh.append(st)
  for (const href of P.links) { const l = d.createElement('link'); l.rel = 'stylesheet'; l.href = href; sh.append(l) }
  const root = d.createElement('div'); root.className = ('mbdoc-root ' + P.bodyClass).trim(); if (P.bodyStyle) root.setAttribute('style', P.bodyStyle)
  for (const n of P.body) root.append(d.importNode(n, true))
  sh.append(root)
})
const printFrame = sandboxed => { const f = document.createElement('iframe'); if (sandboxed) f.setAttribute('sandbox', 'allow-same-origin allow-modals'); f.style.cssText = 'position:fixed;width:0;height:0;border:0;left:-9999px'; document.body.appendChild(f); return f }
const settle = async d => {   // 글꼴·그림이 다 와야 쪽 수가 맞음(그림은 3초까지만 기다림)
  await (d.fonts?.ready || Promise.resolve())
  const imgs = [...d.querySelectorAll('.mbdoc')].flatMap(h => [...(h.shadowRoot?.querySelectorAll('img') || [])]).filter(im => !im.complete)
  await Promise.race([Promise.all(imgs.map(im => new Promise(r => { im.onload = im.onerror = r }))), new Promise(r => setTimeout(r, 3000))])
}
const docCount = new WeakMap()   // 문서 아이템 → 쪽 수(미리보기가 자주 부름 — 같은 문서면 다시 안 잼)
async function measureDocs(docs) {
  const need = docs.filter(it => !docCount.has(it))
  if (need.length) {
    const f = printFrame(true), d = f.contentDocument
    d.open(); d.write(`<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="${location.origin}/fonts.css?v=3"></head><body style="margin:0">${need.map((_, i) => `<div class="mbdoc" id="mbdoc${i}"></div>`).join('')}</body></html>`); d.close()
    try { fillDocs(d, need); await settle(d); need.forEach((it, i) => { const h = d.getElementById('mbdoc' + i).getBoundingClientRect().height; docCount.set(it, Math.max(1, Math.ceil((h - 1) / DOC_CONTENT.h))) }) }
    finally { f.remove() }
  }
  return docs.map(it => docCount.get(it) || 1)
}
// 쪽들의 문서 카드 자리 글(render.jsx DOC_PAGE)에 이어 붙일 쪽 번호를 채움 — byId = _id → 문서 아이템. → { pages, docs(이어 붙일 차례 = 처음 나온 차례) }
export async function withDocPages(pages, byId) {
  const ids = []
  for (const p of pages) for (const m of p.svg.matchAll(/@@DOCP:([^@]+)@@/g)) if (!ids.includes(m[1])) ids.push(m[1])
  const docs = ids.map(id => byId(id)).filter(it => it?.html)
  if (!ids.length) return { pages, docs }
  const counts = docs.length ? await measureDocs(docs) : [], at = new Map(); let no = pages.length + 1
  docs.forEach((it, i) => { at.set(it._id, no); no += counts[i] })
  return { docs, pages: pages.map(p => ({ ...p, svg: p.svg.replace(/@@DOCP:([^@]+)@@/g, (m, id) => String(at.get(id) ?? '끝')) })) }
}

// PDF — 숨은 틀에 용지 크기로 놓고 인쇄 창(「PDF로 저장」). 글꼴은 화면이 이미 불러 둔 fonts.css를 그대로 씀
export function exportPdf(res, title, docs = []) {   // res = 한 쪽 { svg, pw, ph } 또는 여러 쪽 [..] — 쪽마다 용지 크기가 달라도 됨(CSS named page), docs = 끝에 이어 붙일 문서(withDocPages)
  const pages = Array.isArray(res) ? res : [res]
  const f = printFrame(docs.length > 0); f.dataset.testid = 'pdf-print'
  const d = f.contentDocument
  const css = pages.map((p, i) => `@page p${i}{size:${p.pw}mm ${p.ph}mm;margin:0}.p${i}{page:p${i};width:${p.pw}mm;height:${p.ph}mm}`).join('')
  const body = pages.map((p, i) => `<div class="p${i}" style="${i < pages.length - 1 ? 'break-after:page;' : ''}">${p.svg.replace('<svg ', `<svg style="display:block;width:${p.pw}mm;height:${p.ph}mm" `)}</div>`).join('')
    + docs.map((_, i) => `<div class="mbdoc" id="mbdoc${i}"></div>`).join('')
  d.open(); d.write(`<!doctype html><html><head><meta charset="utf-8"><title>${title}</title><link rel="stylesheet" href="${location.origin}/fonts.css?v=3">
    <style>@page{margin:0}${css}${docs.length ? DOC_PAGE_CSS : ''}html,body{margin:0;padding:0}</style></head><body>${body}</body></html>`); d.close()
  fillDocs(d, docs)
  const go = () => { f.contentWindow.focus(); f.contentWindow.print(); setTimeout(() => f.remove(), 60000) }
  ;(docs.length ? settle(d) : (d.fonts?.ready || Promise.resolve())).then(() => setTimeout(go, 100))
}
