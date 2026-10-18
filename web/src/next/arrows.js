// 직각 화살표 길 다시 찾기 — 데스크톱은 문서를 열면 「자동 길」(auto_route) 화살표를 붙은 자리에서 다시 꺾는다(`_PolyArrowItem.reroute`).
// 저장된 꼭짓점이 옛것일 수 있어(예: Mermaid 가져오기 직후 곧은 두 점) 웹도 열 때 같은 규칙으로 다시 찾는다. 길 찾기 = route.js(데스크톱 `_route_ortho` 이식).
import { dedup, elbow, routeOrtho } from '../route.js'
import { headSize } from './geom.js'
import { toScene } from './xform.js'
import { ROUTE_BOX, isBindHost, nearestBorder } from './connect.js'
import { dedupHint } from './arrowedit.js'

const STUB_MARGIN = 4
const defaultRect = it => it.rect || [0, 0, 0, 0]

// 상자의 칠판 좌표 감싼 사각형 {l,t,r,b}(회전하면 네 모서리를 감쌈 — 데스크톱 mapRectToScene)
export function sceneRect(it) {
  const [x, y, w, h] = it.rect, cs = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]].map(([a, b]) => toScene(it, { x: a, y: b }))
  const xs = cs.map(c => c.x), ys = cs.map(c => c.y)
  return { l: Math.min(...xs), t: Math.min(...ys), r: Math.max(...xs), b: Math.max(...ys) }
}

// 옛 파일 읽는 규칙(데스크톱 `dict_to_item` sarrow): routing 없으면 auto_route면 ortho·아니면 straight,
// curve_r 없으면 옛 ortho(직각 엘보)는 0(각짐) — 기본 10을 쓰면 옛 도면 커넥터가 전부 둥글어진다
export const sarrowRouting = it => (it.routing ?? (it.auto_route ? 'ortho' : 'straight')) === 'straight' ? 'straight' : 'ortho'
export const sarrowRadius = it => it.curve_r ?? ((it.routing ?? (it.auto_route ? 'ortho' : 'straight')) === 'ortho' ? 0 : 10)
// 화살촉 쪽 첫 꺾임까지 최소 직선(`_route_min_stubs` = 화살촉 + 모서리 + 4, 화살촉 없는 끝은 0)
export const minStubs = it => { const f = headSize(it.width || 2, it.head_scale) + sarrowRadius(it) + STUB_MARGIN; return [it.head_start ? f : 0, it.head !== false ? f : 0] }

// 길 찾기 준비물(문서 한 번에) — _id → 순번, 장애물 상자들
function routeCtx(items, rectOf) {
  return { items, rectOf, byId: new Map(items.map((it, i) => [it._id, i])),   // 편집 모델(model.js)은 연결을 _id로(_bind1/_bind2), 갓 연 .ecad는 순번으로(bind1/bind2)
    boxes: items.map((it, i) => (ROUTE_BOX.has(it.type) && it.rect ? { i, r: sceneRect(it) } : null)).filter(Boolean) }
}
// 화살표 하나의 꼭짓점(화살표 안 좌표) — 데스크톱 `_apply_routing`: 곧은 길 = 두 점, 직각 = 한쪽이라도 붙었으면 A*(붙은 끝은 도형 고정점·외곽선 법선,
// 떠 있는 끝은 제자리·법선 없음), 둘 다 떠 있으면 단순 꺾음(`_ortho_elbow`)
function routeWith(it, ctx) {
  const { items, rectOf, byId, boxes } = ctx, [px, py] = it.pos || [0, 0], last = it.pts.length - 1
  const at = idx => ({ x: it.pts[idx][0] + px, y: it.pts[idx][1] + py })
  const end = k => {
    const j = it['_' + k] !== undefined ? byId.get(it['_' + k]) : it[k], pt = it[k + '_pt'], host = j == null ? null : items[j]
    if (!host || !pt || !isBindHost(host)) return null
    const p = toScene(host, { x: pt[0], y: pt[1] })
    return { p, n: nearestBorder(host, p, rectOf).n, r: ROUTE_BOX.has(host.type) && host.rect ? sceneRect(host) : null, j }
  }
  const a = end('bind1'), b = end('bind2'), A = a || { p: at(0), n: null, r: null, j: -1 }, B = b || { p: at(last), n: null, r: null, j: -1 }
  const obstacles = () => boxes.filter(o => o.i !== A.j && o.i !== B.j).map(o => o.r)
  let pts
  if (sarrowRouting(it) === 'straight') pts = [A.p, B.p]
  else if (a && b && it.route_hints?.length) {   // 경유지(`build_elbow`→`_route_with_hints`): 두 끝 가운데 + 상대 좌표를 지나게 구간마다 길 찾기
    const m = { x: (A.p.x + B.p.x) / 2, y: (A.p.y + B.p.y) / 2 }, hints = it.route_hints.map(([hx, hy]) => ({ x: m.x + hx, y: m.y + hy }))
    const way = [A.p, ...hints, B.p], norms = [A.n, ...hints.map(() => null), B.n], [ss, se] = minStubs(it), obst = obstacles(), last = way.length - 2
    const all = [A.p], flags = [false]
    for (let i = 0; i < way.length - 1; i++) {
      const seg = routeOrtho(way[i], norms[i], way[i + 1], norms[i + 1], obst, { conn: [A.r, B.r], minStub: [i === 0 ? ss : 0, i === last ? se : 0] })
      seg.slice(1, -1).forEach(q => { all.push(q); flags.push(false) })
      all.push(way[i + 1]); flags.push(i + 1 <= hints.length)
    }
    pts = dedupHint(all, flags)
  }
  else if (!a && !b) pts = dedup([A.p, ...elbow(A.p, B.p, null, null), B.p])
  else pts = routeOrtho(A.p, A.n, B.p, B.n, obstacles(), { conn: [A.r, B.r], minStub: minStubs(it) })
  return pts.map(q => [q.x - px, q.y - py])
}
export const applyRouting = (it, items, rectOf = defaultRect) => routeWith(it, routeCtx(items, rectOf))

// 문서 → 화살표마다 다시 찾은 꼭짓점(화살표 안 좌표 [[x,y],…]) 표. 다시 찾을 게 없으면 표에 없음.
// 데스크톱 `reroute`: 「자동 길」 직각이고 한쪽이라도 붙었으면 다시 찾는다(경유지는 두 끝 다 붙었을 때만 지킴).
// rectOf(it) = 도형 안 바탕 사각형(글 상자는 화면에서 잰 크기 — 편집 화면이 줌, 없으면 rect)
export function resolveRoutes(items, rectOf = defaultRect) {
  const out = new Map(), ctx = routeCtx(items, rectOf)
  items.forEach((it, i) => {
    if (it.type !== 'sarrow' || !it.auto_route || sarrowRouting(it) !== 'ortho' || !(it.pts?.length >= 2)) return
    const bound = k => (it['_' + k] !== undefined ? it['_' + k] != null : it[k] != null) && it[k + '_pt']
    if (!bound('bind1') && !bound('bind2')) return
    out.set(i, routeWith(it, ctx))
  })
  return out
}
