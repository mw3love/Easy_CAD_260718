// 스마트 정렬(이동 중 근처 도형과 변·가운데가 맞으면 당기고 가이드선) — 데스크톱 `core_view._align_match`·`_build_align_guides`를 옮김.
// 축마다 후보 9개: 같은 역할 3(좌-좌·중-중·우-우) + 마주 보는 변 2 + 가운데-변 4. 임계 = 화면 10px, 같은 거리(1.5px 안)인 역할은 전부 선으로.
// (데스크톱의 꼭짓점×꼭짓점 후보는 삼각형 같은 대각 변용 — 웹은 상자 기준만, 나중에.)
export const ALIGN_PX = 10, TIE_PX = 1.5

const cands = (n, o, ax) => {
  const [lo, c, hi] = ax === 'x' ? [n.x, n.x + n.w / 2, n.x + n.w] : [n.y, n.y + n.h / 2, n.y + n.h]
  const [olo, oc, ohi] = ax === 'x' ? [o.x, o.x + o.w / 2, o.x + o.w] : [o.y, o.y + o.h / 2, o.y + o.h]
  const [a, b] = ax === 'x' ? ['left', 'right'] : ['top', 'bottom']
  return [[lo, olo, a], [c, oc, 'center'], [hi, ohi, b], [hi, olo, 'adj'], [lo, ohi, 'adj'], [c, olo, 'mid-edge'], [c, ohi, 'mid-edge'], [lo, oc, 'mid-edge'], [hi, oc, 'mid-edge']]
}

// n = 옮기는 것(들)의 상자, others = 비교할 상자들, zoom = 화면 배율 → { dx, dy, guides: [{ axis:'v'|'h', at, from, to, role }] }
export function alignSnap(n, others, zoom) {
  const thr = ALIGN_PX / zoom, tie = TIE_PX / zoom
  const best = { x: null, y: null }
  const near = others.filter(o => (o.x <= n.x + n.w + thr && o.x + o.w >= n.x - thr) || (o.y <= n.y + n.h + thr && o.y + o.h >= n.y - thr))   // 가로·세로 띠 안의 것만
  for (const o of near) for (const ax of ['x', 'y']) {
    const scored = cands(n, o, ax).map(([my, ov, role]) => ({ ad: Math.abs(ov - my), d: ov - my, at: ov, role })).filter(c => c.ad <= thr).sort((a, b) => a.ad - b.ad)
    if (!scored.length) continue
    const win = scored.filter(c => c.ad <= scored[0].ad + tie)
    if (!best[ax] || win[0].ad < best[ax].win[0].ad) best[ax] = { win, o }
  }
  const dx = best.x ? best.x.win[0].d : 0, dy = best.y ? best.y.win[0].d : 0
  const m = { x: n.x + dx, y: n.y + dy, w: n.w, h: n.h }, guides = []
  for (const [ax, axis] of [['x', 'v'], ['y', 'h']]) {
    const b = best[ax]; if (!b) continue
    const o = b.o, seen = new Set()
    const [from, to] = axis === 'v' ? [Math.min(m.y, o.y), Math.max(m.y + m.h, o.y + o.h)] : [Math.min(m.x, o.x), Math.max(m.x + m.w, o.x + o.w)]
    for (const c of b.win) if (!seen.has(c.at)) { seen.add(c.at); guides.push({ axis, at: c.at, from, to, role: c.role }) }
  }
  return { dx, dy, guides }
}
