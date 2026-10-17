// 직교 화살표 길 찾기 — 데스크톱 `easycad/canvas/core_routing.py` `_route_ortho`를 그대로 옮김(§8 항목61, 2026-10-17 사용자 요청:
// "기본 도형 기능은 magic board를 많이 참고"). 순수 함수(npm test). 점 {x,y}, 사각형 {l,t,r,b}, 법선 {x,y}|null.
// 규칙(데스크톱과 같음):
//  1) 기본 길 = 양 끝에서 법선 방향으로 스텁(연결 도형은 여유 36, 화살촉 쪽은 최소 25) 뒤 ㄱ·ㄹ 엘보.
//     도형 관통·연결 도형 재진입·변 타기가 없으면 그대로.
//  2) 있으면 Hanan 격자 A*(꺾임 벌점)로 우회 → 연결 도형 여유 사다리(36→12→1→0)를 돌며 점수가 엄격히 나은 것만 바꿈.
//     점수(작을수록 좋음, 사전식) = (관통, 재진입, 변 타기 길이, 화살표 교차, 꼭짓점 수, 짧은 스텁, 사다리 칸, 총길이)
//  3) 그래도 관통이면 장애물을 부풀리지 않고 한 번 더.
// 다른 화살표는 길 찾기에 넣지 않는다(데스크톱 Stage3 철회 — 같은 포트면 늘 같은 길, 남의 화살표가 지워져도 안 바뀜).

export const CLEARANCE = 12       // 제3 도형과의 여유(데스크톱 _ROUTE_CLEARANCE)
export const CONN_CLEAR_MULT = 3  // 연결 도형 여유 배수(_CONN_CLEAR_MULT) → 36
const RIDE_TOL = 4, RIDE_MIN_OVERLAP = 4
const CORRIDOR_PAD_MIN = 400, CORRIDOR_PAD_MULT = 15
const EPS = 1e-6

const P = (x, y) => ({ x, y })
const same = (a, b) => Math.abs(a.x - b.x) <= EPS && Math.abs(a.y - b.y) <= EPS
export const inflate = (r, d) => ({ l: r.l - d, t: r.t - d, r: r.r + d, b: r.b + d })
const intersects = (a, b) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b

// 연속 중복점 + 구간 '안'에 있는 공선점만 접는다(되돌아오기 꺾임은 보존 — 데스크톱 _dedup_pts 2026-08-31)
export function dedup(pts) {
  const out = [pts[0]]
  for (const p of pts.slice(1)) if (!same(p, out[out.length - 1])) out.push(p)
  let i = 1
  while (i < out.length - 1) {
    const [a, b, c] = [out[i - 1], out[i], out[i + 1]]
    const cross = (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
    const between = Math.min(a.x, c.x) - EPS <= b.x && b.x <= Math.max(a.x, c.x) + EPS && Math.min(a.y, c.y) - EPS <= b.y && b.y <= Math.max(a.y, c.y) + EPS
    if (Math.abs(cross) <= EPS && between) out.splice(i, 1); else i++
  }
  return out
}

const isHoriz = (n, dflt) => (n ? Math.abs(n.x) >= Math.abs(n.y) : dflt)
export function elbow(s, e, ns, ne) {
  const dh = Math.abs(e.x - s.x) >= Math.abs(e.y - s.y), sh = isHoriz(ns, dh), eh = isHoriz(ne, dh)
  if (sh && eh) { const mx = (s.x + e.x) / 2; return [P(mx, s.y), P(mx, e.y)] }
  if (!sh && !eh) { const my = (s.y + e.y) / 2; return [P(s.x, my), P(e.x, my)] }
  return sh ? [P(e.x, s.y)] : [P(s.x, e.y)]
}

// 축정렬 선분이 사각형 '속'을 지나나(테두리 접촉은 통과)
export function segHitsRect(a, b, r) {
  if (Math.abs(a.y - b.y) <= EPS) {
    if (a.y <= r.t + EPS || a.y >= r.b - EPS) return false
    return Math.max(a.x, b.x) > r.l + EPS && Math.min(a.x, b.x) < r.r - EPS
  }
  if (Math.abs(a.x - b.x) <= EPS) {
    if (a.x <= r.l + EPS || a.x >= r.r - EPS) return false
    return Math.max(a.y, b.y) > r.t + EPS && Math.min(a.y, b.y) < r.b - EPS
  }
  return Math.max(a.x, b.x) > r.l && Math.min(a.x, b.x) < r.r && Math.max(a.y, b.y) > r.t && Math.min(a.y, b.y) < r.b
}
export const pathHits = (pts, rects) => pts.some((p, i) => i && rects.some(r => segHitsRect(pts[i - 1], p, r)))

function normalStub(p, n, d, clear) {
  if (!n) return p
  const h = Math.abs(n.x) >= Math.abs(n.y), sign = (h ? n.x : n.y) >= 0 ? 1 : -1
  if (clear) {
    const need = h ? (sign > 0 ? clear.r - p.x : p.x - clear.l) : (sign > 0 ? clear.b - p.y : p.y - clear.t)
    d = Math.max(d, need + 1)
  }
  return h ? P(p.x + sign * d, p.y) : P(p.x, p.y + sign * d)
}

function corridor(a, b, clearance) {
  const pad = Math.max(CORRIDOR_PAD_MIN, clearance * CORRIDOR_PAD_MULT)
  return { l: Math.min(a.x, b.x) - pad, t: Math.min(a.y, b.y) - pad, r: Math.max(a.x, b.x) + pad, b: Math.max(a.y, b.y) + pad }
}

// Hanan 격자 직교 A* — 중간 꼭짓점만 돌려줌(없으면 null). 꺾임 벌점 = clearance/2
export function astar(start, goal, infl, clearance) {
  const cor = corridor(start, goal, clearance)
  infl = infl.filter(r => intersects(r, cor))
  const xs = [...new Set([start.x, goal.x, ...infl.flatMap(r => [r.l, r.r])])].sort((a, b) => a - b)
  const ys = [...new Set([start.y, goal.y, ...infl.flatMap(r => [r.t, r.b])])].sort((a, b) => a - b)
  const nx = xs.length, ny = ys.length
  const sx = xs.indexOf(start.x), sy = ys.indexOf(start.y), gx = xs.indexOf(goal.x), gy = ys.indexOf(goal.y)
  const rowO = ys.map(y => infl.filter(r => r.t + EPS < y && y < r.b - EPS))
  const colO = xs.map(x => infl.filter(r => r.l + EPS < x && x < r.r - EPS))
  const edgeOk = (ax, ay, bx, by) => ay === by
    ? !rowO[ay].some(r => segHitsRect(P(xs[ax], ys[ay]), P(xs[bx], ys[ay]), r))
    : !colO[ax].some(r => segHitsRect(P(xs[ax], ys[ay]), P(xs[ax], ys[by]), r))
  const turn = clearance * 0.5, h = (ix, iy) => Math.abs(xs[ix] - xs[gx]) + Math.abs(ys[iy] - ys[gy])
  const key = (ix, iy, ax) => (ix * ny + iy) * 3 + ax
  const dist = new Map(), prev = new Map(), heap = []
  // 데스크톱 heapq와 같은 순서 — (f, g, ix, iy, 축) 사전식(같은 비용 길이 여럿일 때 같은 것을 고르게)
  const lt = (a, b) => { for (let i = 0; i < 2; i++) if (a[i] !== b[i]) return a[i] < b[i]; for (let i = 0; i < 3; i++) if (a[2][i] !== b[2][i]) return a[2][i] < b[2][i]; return false }
  const push = (f, g, st) => { heap.push([f, g, st]); let i = heap.length - 1; while (i) { const p = (i - 1) >> 1; if (!lt(heap[i], heap[p])) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p } }
  const pop = () => { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i; if (l < heap.length && lt(heap[l], heap[m])) m = l; if (r < heap.length && lt(heap[r], heap[m])) m = r; if (m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m } } return top }
  const s0 = [sx, sy, 0]; dist.set(key(...s0), 0); push(h(sx, sy), 0, s0)
  let goalSt = null
  while (heap.length) {
    const [, g, st] = pop(), [ix, iy, ax] = st
    if (g > (dist.get(key(...st)) ?? Infinity)) continue
    if (ix === gx && iy === gy) { goalSt = st; break }
    for (const [dx, dy, nax] of [[1, 0, 1], [-1, 0, 1], [0, 1, 2], [0, -1, 2]]) {
      const jx = ix + dx, jy = iy + dy
      if (jx < 0 || jy < 0 || jx >= nx || jy >= ny || !edgeOk(ix, iy, jx, jy)) continue
      const ng = g + Math.abs(xs[jx] - xs[ix]) + Math.abs(ys[jy] - ys[iy]) + (ax && ax !== nax ? turn : 0)
      const nst = [jx, jy, nax], k = key(...nst)
      if (ng < (dist.get(k) ?? Infinity)) { dist.set(k, ng); prev.set(k, st); push(ng + h(jx, jy), ng, nst) }
    }
  }
  if (!goalSt) return null
  const path = []
  for (let st = goalSt; st; st = prev.get(key(...st))) path.push(P(xs[st[0]], ys[st[1]]))
  path.reverse()
  return path.slice(1, -1)
}

function rideLen(a, b, r, n) {
  if (n) {
    const dx = b.x - a.x, dy = b.y - a.y
    if (Math.abs(n.x) >= Math.abs(n.y)) { if (Math.abs(dy) <= EPS && Math.abs(dx) > EPS) return 0 }
    else if (Math.abs(dx) <= EPS && Math.abs(dy) > EPS) return 0
  }
  if (Math.abs(a.y - b.y) <= EPS && Math.abs(a.x - b.x) > EPS) {
    const ov = Math.min(Math.max(a.x, b.x), r.r) - Math.max(Math.min(a.x, b.x), r.l)
    if (ov > RIDE_MIN_OVERLAP && Math.min(Math.abs(a.y - r.t), Math.abs(a.y - r.b)) <= RIDE_TOL) return ov
  } else if (Math.abs(a.x - b.x) <= EPS && Math.abs(a.y - b.y) > EPS) {
    const ov = Math.min(Math.max(a.y, b.y), r.b) - Math.max(Math.min(a.y, b.y), r.t)
    if (ov > RIDE_MIN_OVERLAP && Math.min(Math.abs(a.x - r.l), Math.abs(a.x - r.r)) <= RIDE_TOL) return ov
  }
  return 0
}
function pathRide(pts, pairs, ns, ne) {
  pts = dedup(pts)
  let tot = 0
  const last = pts.length - 2
  for (let i = 0; i < pts.length - 1; i++)
    for (const [r, owner] of pairs) tot += rideLen(pts[i], pts[i + 1], r, i === 0 && owner === 'start' ? ns : i === last && owner === 'end' ? ne : null)
  return tot
}
const manhattan = pts => pts.reduce((s, p, i) => (i ? s + Math.abs(p.x - pts[i - 1].x) + Math.abs(p.y - pts[i - 1].y) : 0), 0)
function shortStubs(full, ns, ne, min) {
  let n = 0
  ;[[ns, min[0], 0], [ne, min[1], 1]].forEach(([nrm, floor, i]) => {
    if (!nrm || floor <= 0 || full.length < 3) return
    const [a, b] = i === 0 ? [full[0], full[1]] : [full[full.length - 1], full[full.length - 2]]
    if (Math.abs(a.x - b.x) + Math.abs(a.y - b.y) < floor - 0.5) n++
  })
  return n
}
function score(mids, s, e, ns, ne, infl, connOrig, pairs, rung, min) {
  const full = dedup([s, ...mids, e])
  return [infl.length && pathHits(full, infl) ? 1 : 0, connOrig.length && pathHits(full, connOrig) ? 1 : 0,
    pairs.length ? Math.round(pathRide(full, pairs, ns, ne) * 10) / 10 : 0, 0, full.length, shortStubs(full, ns, ne, min), rung,
    Math.round(manhattan(full) * 10) / 10]
}
const less = (a, b) => { for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return a[i] < b[i]; return false }

// s·ns: 시작 부착점·바깥 법선, e·ne: 끝(떠 있는 끝은 법선 null), obstacles: 양끝 연결 도형을 뺀 상자들, conn: [시작 도형|null, 끝 도형|null]
// minStub: [시작, 끝] 화살촉 쪽 최소 직선 길이. 돌려주는 것 = 양 끝을 포함한 전체 꼭짓점.
export function routeOrtho(s, ns, e, ne, obstacles = [], { clearance = CLEARANCE, conn = [null, null], minStub = [0, 0] } = {}) {
  const cor = corridor(s, e, clearance)
  const infl = obstacles.map(r => inflate(r, clearance)).filter(r => intersects(r, cor))
  const connClear = clearance * CONN_CLEAR_MULT
  const connOrig = conn.filter(Boolean)
  const pairs = conn.map((r, i) => r && [r, i ? 'end' : 'start']).filter(Boolean)
  const connInfl = connOrig.map(r => inflate(r, connClear))
  const [ownS, ownE] = conn
  let ownPush = connClear
  if (ownS && ownE && ns && ne) {
    const nsH = Math.abs(ns.x) >= Math.abs(ns.y), neH = Math.abs(ne.x) >= Math.abs(ne.y)
    if (nsH === neH) ownPush = Math.min(connClear, (nsH ? Math.abs(e.x - s.x) : Math.abs(e.y - s.y)) / 2)   // 마주 보는 좁은 간격: 하이핀 방지
  }
  const cap = ownPush < connClear ? ownPush : Infinity
  const floorS = Math.min(Math.max(minStub[0], ownS ? connClear : 0), cap)
  const floorE = Math.min(Math.max(minStub[1], ownE ? connClear : 0), cap)
  const ownStub = (p, n, rect, floor) => (rect ? normalStub(p, n, Math.max(ownPush, floor), inflate(rect, ownPush)) : normalStub(p, n, Math.max(clearance, floor)))
  const sS = ownStub(s, ns, ownS, floorS), eS = ownStub(e, ne, ownE, floorE)
  const preferred = [...(same(sS, s) ? [] : [sS]), ...elbow(sS, eS, ns, ne), ...(same(eS, e) ? [] : [eS])]
  const prefFull = [s, ...preferred, e]
  const prefHits = infl.length && pathHits(prefFull, infl)
  const prefRe = connOrig.length && pathHits(prefFull, connOrig)
  const prefRide = pairs.length && pathRide(prefFull, pairs, ns, ne) > 0
  if (!prefHits && !prefRe && !prefRide) return dedup(prefFull)

  function* candidates(obst, push, cc = null) {
    const own = i => (conn[i] && cc != null ? inflate(conn[i], cc) : null)
    const tries = []
    for (const [fs, fe] of [[floorS, floorE], [0, 0]]) {
      const s2 = normalStub(s, ns, Math.max(push, fs), own(0)), e2 = normalStub(e, ne, Math.max(push, fe), own(1))
      if (!tries.some(t => same(t[0], s2) && same(t[1], e2))) tries.push([s2, e2, same(s2, s) ? [] : [s2], same(e2, e) ? [] : [e2]])
    }
    for (const [a, b, pre, post] of [...tries, [s, e, [], []]]) {
      const mid = astar(a, b, obst, clearance)
      if (mid) yield [...pre, ...mid, ...post]
    }
  }
  let base = preferred
  if (prefHits || prefRe) {
    const obst = prefRe ? [...infl, ...connInfl] : infl, check = prefRe ? [...infl, ...connOrig] : infl
    for (const mids of candidates(obst, prefRe ? connClear : clearance))
      if (!pathHits([s, ...mids, e], check)) { base = mids; break }
  }
  const min = [floorS, floorE]
  let best = base, bestScore = score(base, s, e, ns, ne, infl, connOrig, pairs, 0, min)
  ;[connClear, clearance, 1, 0].forEach((cc, rung) => {
    const cinfl = connOrig.map(r => inflate(r, cc))
    for (const mids of candidates([...infl, ...cinfl], cc, cc)) {
      const sc = score(mids, s, e, ns, ne, infl, connOrig, pairs, rung, min)
      if (less(sc, bestScore)) { best = mids; bestScore = sc }
    }
  })
  if (bestScore[0] !== 0 && obstacles.length)
    for (const mids of candidates(obstacles, 0, 0))
      if (!pathHits(dedup([s, ...mids, e]), obstacles)) { best = mids; break }
  return dedup([s, ...best, e])
}
