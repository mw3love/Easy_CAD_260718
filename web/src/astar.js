// 격자 A* 직교 라우팅 — web_prototype/astar.js를 바탕으로 "꺾임 벌점"을 더함(벌점 없으면 계단 모양 경로가 나옴).
// 상태 = (칸, 들어온 방향). 순수 함수.
const DIRS = [[1, 0], [-1, 0], [0, 1], [0, -1]]

export function routeAStar(start, startDir, end, endDir, obstacles, cell = 10, bendCost = 6) {
  const c = p => ({ x: Math.round(p.x / cell), y: Math.round(p.y / cell) })
  const s = c({ x: start.x + startDir[0] * cell * 2, y: start.y + startDir[1] * cell * 2 })
  const e = c({ x: end.x + endDir[0] * cell * 2, y: end.y + endDir[1] * cell * 2 })
  const pad = cell * 1.5
  const blocked = (x, y) => obstacles.some(o => x * cell >= o.minX - pad && x * cell <= o.maxX + pad && y * cell >= o.minY - pad && y * cell <= o.maxY + pad)
  const xs = [s.x, e.x, ...obstacles.flatMap(o => [o.minX / cell, o.maxX / cell])], ys = [s.y, e.y, ...obstacles.flatMap(o => [o.minY / cell, o.maxY / cell])]
  const [minX, maxX, minY, maxY] = [Math.min(...xs) - 6, Math.max(...xs) + 6, Math.min(...ys) - 6, Math.max(...ys) + 6]
  const sd = DIRS.findIndex(d => d[0] === startDir[0] && d[1] === startDir[1])
  const key = (x, y, d) => `${x},${y},${d}`
  const g = new Map([[key(s.x, s.y, sd), 0]]), from = new Map(), open = [[Math.abs(s.x - e.x) + Math.abs(s.y - e.y), s.x, s.y, sd]], done = new Set()
  let goal = null
  while (open.length) {
    open.sort((a, b) => a[0] - b[0])
    const [, x, y, d] = open.shift(), k = key(x, y, d)
    if (done.has(k)) continue
    done.add(k)
    if (x === e.x && y === e.y) { goal = k; break }
    DIRS.forEach(([dx, dy], nd) => {
      if (dx === -DIRS[d][0] && dy === -DIRS[d][1]) return              // 뒤로 꺾기 금지
      const nx = x + dx, ny = y + dy
      if (nx < minX || nx > maxX || ny < minY || ny > maxY) return
      if (blocked(nx, ny) && !(nx === e.x && ny === e.y)) return
      const nk = key(nx, ny, nd), ng = g.get(k) + 1 + (nd !== d ? bendCost : 0)
      if (!g.has(nk) || ng < g.get(nk)) { g.set(nk, ng); from.set(nk, k); open.push([ng + Math.abs(nx - e.x) + Math.abs(ny - e.y), nx, ny, nd]) }
    })
  }
  if (!goal) return null
  const cells = []
  for (let k = goal; k; k = from.get(k)) { const [x, y] = k.split(',').map(Number); cells.unshift({ x: x * cell, y: y * cell }) }
  // 격자 반올림 때문에 포트 옆에 생기는 작은 턱 없애기: 첫 줄·끝 줄을 포트 높이(또는 x)에 맞춘다
  const snapRun = (list, port, dir) => {
    const ax = dir[0] ? 'y' : 'x', v = list[0][ax]
    for (const q of list) { if (q[ax] !== v) break; q[ax] = port[ax] }
  }
  snapRun(cells, start, startDir); snapRun([...cells].reverse(), end, endDir)
  // 포트 → 첫 칸, 끝 칸 → 포트를 축정렬로 잇는다
  const out = [start, { x: startDir[0] ? cells[0].x : start.x, y: startDir[1] ? cells[0].y : start.y }, ...cells,
    { x: endDir[0] ? cells[cells.length - 1].x : end.x, y: endDir[1] ? cells[cells.length - 1].y : end.y }, end]
  return out
}
