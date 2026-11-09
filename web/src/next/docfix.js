// 📄 문서 재기(2026-11-09 문서 통합 2단계 ④) — 새 문서를 보이지 않는 틀(스크립트 없이 allow-same-origin)에 그 폭으로 펼쳐 블록마다 잘림·넘침을 잼.
// 움직이는 카드 검사(cardcheck.js)와 같은 생각이지만 문서엔 스크립트가 없어 앱이 바깥에서 직접 잼. 고치기는 chat.jsx `fixDoc`이 문제 블록만 `kind: 'block'`으로.
const PAD = 3

export async function measureDoc(html, pageW = 1000, ms = 5000) {
  if (typeof document === 'undefined' || !html) return []
  const f = document.createElement('iframe')
  f.setAttribute('sandbox', 'allow-same-origin'); f.setAttribute('aria-hidden', 'true'); f.tabIndex = -1
  Object.assign(f.style, { position: 'fixed', left: '-20000px', top: '0', width: pageW + 'px', height: '900px', border: '0', visibility: 'hidden' })
  const loaded = new Promise(ok => { f.onload = ok; setTimeout(ok, ms) })
  f.srcdoc = html; document.body.appendChild(f)
  try {
    await loaded; await new Promise(r => setTimeout(r, 150))
    const d = f.contentDocument; if (!d) return []
    const W = d.documentElement.clientWidth, out = []
    for (const el of d.querySelectorAll('[data-block]')) {
      const why = new Set(), r = el.getBoundingClientRect()
      if (r.right > W + PAD) why.add('문서 폭 밖으로 넘침')
      if (el.scrollWidth > el.clientWidth + PAD && el.clientWidth > 0) why.add('내용이 칸 오른쪽으로 넘침')
      for (const n of el.querySelectorAll('*')) {
        const cs = d.defaultView.getComputedStyle(n)
        if (/hidden|clip/.test(cs.overflowX + cs.overflow) && n.clientWidth > 0 && n.scrollWidth > n.clientWidth + PAD) why.add('글자가 칸에 잘림')
        if (n.getBoundingClientRect().right > W + PAD) why.add('문서 폭 밖으로 넘침')
      }
      for (const svg of el.querySelectorAll('svg')) {
        const sr = svg.getBoundingClientRect(); if (!sr.width) continue
        for (const t of svg.querySelectorAll('text')) {
          const tr = t.getBoundingClientRect()
          if (tr.width && (tr.left < sr.left - PAD || tr.right > sr.right + PAD || tr.top < sr.top - PAD || tr.bottom > sr.bottom + PAD)) { why.add('그래프 글자가 그림 밖으로 나감'); break }
        }
      }
      if (why.size) out.push({ block: el.dataset.block, why: [...why].join(', ') })
    }
    return out
  } catch { return [] } finally { f.remove() }
}
