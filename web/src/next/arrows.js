// 직각 화살표 길 다시 찾기 — 데스크톱은 문서를 열면 「자동 길」(auto_route) 화살표를 붙은 자리에서 다시 꺾는다(`_PolyArrowItem.reroute`).
// 저장된 꼭짓점이 옛것일 수 있어(예: Mermaid 가져오기 직후 곧은 두 점) 웹도 열 때 같은 규칙으로 다시 찾는다. 길 찾기 = route.js(데스크톱 `_route_ortho` 이식).
import { routeOrtho } from '../route.js'
import { headSize } from './geom.js'

const ROUTE_BOX = new Set(['rect', 'ellipse', 'symbol', 'image', 'table'])   // 데스크톱 `_ROUTE_BOX_TYPES`
const STUB_MARGIN = 4

// 상자의 칠판 좌표 사각형 {l,t,r,b}(회전 무시 — 데스크톱 bbox와 같음)
function sceneRect(it) {
  const [px, py] = it.pos || [0, 0], s = it.scale || 1, [x, y, w, h] = it.rect
  return { l: px + x * s, t: py + y * s, r: px + (x + w) * s, b: py + (y + h) * s }
}
// 붙은 자리의 바깥 법선 — 가장 가까운 변 방향(데스크톱 `_axis_forced_local_normal`: 축으로 고정)
function sideNormal(r, p) {
  const d = [[p.x - r.l, { x: -1, y: 0 }], [r.r - p.x, { x: 1, y: 0 }], [p.y - r.t, { x: 0, y: -1 }], [r.b - p.y, { x: 0, y: 1 }]]
  return d.reduce((a, b) => (Math.abs(b[0]) < Math.abs(a[0]) ? b : a))[1]
}

// 옛 파일 읽는 규칙(데스크톱 `dict_to_item` sarrow): routing 없으면 auto_route면 ortho·아니면 straight,
// curve_r 없으면 옛 ortho(직각 엘보)는 0(각짐) — 기본 10을 쓰면 옛 도면 커넥터가 전부 둥글어진다
export const sarrowRouting = it => (it.routing ?? (it.auto_route ? 'ortho' : 'straight')) === 'straight' ? 'straight' : 'ortho'
export const sarrowRadius = it => it.curve_r ?? ((it.routing ?? (it.auto_route ? 'ortho' : 'straight')) === 'ortho' ? 0 : 10)

// 문서 → 화살표마다 다시 찾은 꼭짓점(칠판 좌표 [[x,y],…]) 표. 다시 찾을 게 없으면 표에 없음.
export function resolveRoutes(items) {
  const out = new Map()
  const byId = new Map(items.map((it, i) => [it._id, i]))   // 편집 모델(model.js)은 연결을 _id로(_bind1/_bind2), 갓 연 .ecad는 순번으로(bind1/bind2)
  const boxes = items.map((it, i) => (ROUTE_BOX.has(it.type) && it.rect ? { i, r: sceneRect(it) } : null)).filter(Boolean)
  items.forEach((it, i) => {
    if (it.type !== 'sarrow' || !it.auto_route || it.route_hints?.length || sarrowRouting(it) !== 'ortho') return
    const end = k => {
      const j = it['_' + k] !== undefined ? byId.get(it['_' + k]) : it[k], pt = it[k + '_pt'], host = items[j]
      if (j == null || !pt || !host?.rect) return null
      const [px, py] = host.pos || [0, 0], s = host.scale || 1, r = sceneRect(host)
      const p = { x: px + pt[0] * s, y: py + pt[1] * s }
      return { p, n: sideNormal(r, p), r, j }
    }
    const a = end('bind1'), b = end('bind2')
    if (!a || !b) return
    const floor = headSize(it.width || 2, it.head_scale) + sarrowRadius(it) + STUB_MARGIN
    const obstacles = boxes.filter(o => o.i !== a.j && o.i !== b.j).map(o => o.r)
    const pts = routeOrtho(a.p, a.n, b.p, b.n, obstacles, { conn: [a.r, b.r], minStub: [it.head_start ? floor : 0, it.head !== false ? floor : 0] })
    const [px, py] = it.pos || [0, 0]
    out.set(i, pts.map(q => [q.x - px, q.y - py]))
  })
  return out
}
