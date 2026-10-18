// PNG·PDF·SVG 내보내기 — 데스크톱 `fileio/pdf_export.py`와 같은 규칙: 전체(용지틀이 있으면 그 틀 = 용지·여백 0) 또는 고른 것,
// 용지 A4~A0·방향(자동 = 내용이 가로로 길면 가로)·여백 mm, 내용은 2% 덧대어 용지 안에 비율 유지·가운데. 밝은 칠판 잉크(흰 잉크 → 검정), 투명 배경은 PNG·SVG만.
// PNG는 200dpi(데스크톱 기본), PDF는 브라우저 인쇄 창 「PDF로 저장」(선·글이 벡터 그대로 — 새 라이브러리 없이), SVG는 파일 그대로.
import { renderToStaticMarkup } from 'react-dom/server'
import { Item, setInkDark } from './render.jsx'

export const PAPERS = { A4: [210, 297], A3: [297, 420], A2: [420, 594], A1: [594, 841], A0: [841, 1189] }   // 세로 기준 mm
const FONT_FILES = { 400: 'Regular', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold' }

async function fontFaces(weights) {   // 보드 글꼴(Pretendard)은 그림으로 바꿀 때 글꼴을 못 찾아서 파일째 넣음(윈도우 글꼴은 그대로 찾음)
  const out = []
  for (const w of weights) {
    const blob = await (await fetch(`/fonts/Pretendard-${FONT_FILES[w]}.otf`)).blob()
    const url = await new Promise(r => { const fr = new FileReader(); fr.onload = () => r(fr.result); fr.readAsDataURL(blob) })
    out.push(`@font-face{font-family:'Pretendard';font-weight:${w};src:url(${url}) format('opentype')}`)
  }
  return out.join('')
}
const usesBoardFont = it => it.family || it.label?.family || (it.labels || []).some(L => L.family)
const weightsOf = items => { const s = new Set([400, 700]); for (const it of items) if (it.weight && FONT_FILES[it.weight]) s.add(it.weight); return [...s] }

// entries = [[아이템, 순번]] 그리는 차례, src = 칠판 상자, opts = { page, orient, margin, transparent, frame }
// → { svg 글, pw, ph (mm) }
export async function buildSvg(entries, src, { page = 'A4', orient = null, margin = 10, transparent = false, frame = null, tight = false }, onBoard, routes, embedFonts = true) {
  let pageKey = page, land, m = margin, box = src
  if (frame) { pageKey = frame.size in PAPERS ? frame.size : 'A4'; land = frame.orient === 'landscape'; m = 0; box = frame.box }   // 용지틀 = 정확한 용지 경계
  else { const pad = Math.max(src.w, src.h) * 0.02; box = { x: src.x - pad, y: src.y - pad, w: src.w + 2 * pad, h: src.h + 2 * pad }; land = orient ? orient === 'landscape' : box.w >= box.h }
  let [a, b] = PAPERS[pageKey] || PAPERS.A4, pw = land ? b : a, ph = land ? a : b
  if (tight) { m = 0; pw = box.w * 25.4 / 96; ph = box.h * 25.4 / 96 }   // 그림으로 복사 — 용지 없이 화면 100% 크기(96dpi)
  const aw = pw - 2 * m, ah = ph - 2 * m, k = Math.min(aw / box.w, ah / box.h), tx = m + (aw - box.w * k) / 2, ty = m + (ah - box.h * k) / 2
  const wasDark = document.documentElement.dataset.theme === 'dark'
  setInkDark(false)   // 종이 = 밝은 칠판 잉크(데스크톱 `_swap_white_to_black_for_print`와 같은 뜻)
  let body
  try { body = renderToStaticMarkup(<g transform={`translate(${tx},${ty}) scale(${k}) translate(${-box.x},${-box.y})`} style={{ '--z': 1000 }}>
    {entries.map(([it, i]) => <Item key={it._id} it={it} idx={i} onBoard={onBoard[i]} route={routes.get(i)} />)}</g>) }
  finally { setInkDark(wasDark) }
  const fonts = embedFonts && entries.some(([it]) => usesBoardFont(it)) ? await fontFaces(weightsOf(entries.map(e => e[0]))) : ''
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="${pw}mm" height="${ph}mm" viewBox="0 0 ${pw} ${ph}">`
    + (fonts ? `<style>${fonts}</style>` : '') + (transparent ? '' : `<rect width="${pw}" height="${ph}" fill="#ffffff"/>`) + body + '</svg>'
  return { svg, pw, ph }
}

const download = (blob, name) => { const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000) }

export async function pngBlob({ svg, pw, ph }, dpi = 200) {
  const W = Math.max(1, Math.round(pw / 25.4 * dpi)), H = Math.max(1, Math.round(ph / 25.4 * dpi))
  const img = new Image(), url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }))
  await new Promise((ok, bad) => { img.onload = ok; img.onerror = bad; img.src = url })
  const cv = document.createElement('canvas'); cv.width = W; cv.height = H; cv.getContext('2d').drawImage(img, 0, 0, W, H); URL.revokeObjectURL(url)
  return new Promise(r => cv.toBlob(r, 'image/png'))
}
export async function exportPng(res, name, dpi = 200) { download(await pngBlob(res, dpi), name) }
export const exportSvg = ({ svg }, name) => download(new Blob([svg], { type: 'image/svg+xml' }), name)

// PDF — 숨은 틀에 용지 크기로 놓고 인쇄 창(「PDF로 저장」). 글꼴은 화면이 이미 불러 둔 fonts.css를 그대로 씀
export function exportPdf({ svg, pw, ph }, title) {
  const f = document.createElement('iframe'); f.style.cssText = 'position:fixed;width:0;height:0;border:0;left:-9999px'; document.body.appendChild(f)
  const d = f.contentDocument
  d.open(); d.write(`<!doctype html><html><head><meta charset="utf-8"><title>${title}</title><link rel="stylesheet" href="${location.origin}/fonts.css">
    <style>@page{size:${pw}mm ${ph}mm;margin:0}html,body{margin:0;padding:0}svg{display:block;width:${pw}mm;height:${ph}mm}</style></head><body>${svg}</body></html>`); d.close()
  const go = () => { f.contentWindow.focus(); f.contentWindow.print(); setTimeout(() => f.remove(), 60000) }
  ;(d.fonts?.ready || Promise.resolve()).then(() => setTimeout(go, 100))
}
