// 화살표 손질 대조 — 데스크톱 답(`tools/export_arrow_cases.py`)과 arrowedit.js·arrows.js가 같은지
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { beginSegment, beginSubdivide, bendCurve, dragSegment, endSegment, nearestSegment, onPill, projectToCurve, projectToPath, segmentHandles, snapCurve, snapLabelOff } from '../src/next/arrowedit.js'
import { resolveRoutes } from '../src/next/arrows.js'
import { applyCurved, swapArrowKind } from '../src/next/arrowkind.js'

const C = JSON.parse(readFileSync(new URL('./fixtures/arrow_cases.json', import.meta.url)))
const same = (got, exp, tol, msg) => {
  assert.equal(got.length, exp.length, `${msg}: 개수 ${JSON.stringify(got)} vs ${JSON.stringify(exp)}`)
  got.forEach((p, i) => assert.ok(Math.abs(p[0] - exp[i][0]) <= tol && Math.abs(p[1] - exp[i][1]) <= tol, `${msg}: ${i}번 ${p} vs ${exp[i]}`))
}

test('경유지 길이 데스크톱 `build_elbow`와 같다', () => {
  C.hints.forEach((c, n) => {
    const a = { ...c.a, _id: 'a' }, b = { ...c.b, _id: 'b' }
    const ar = { _id: 'r', type: 'sarrow', pos: [0, 0], pts: [c.s, c.e], width: 2, head: true, head_start: false, head_scale: 1, curve_r: 10, routing: 'ortho', auto_route: true,
      route_hints: [c.hint], _bind1: 'a', bind1_pt: [c.s[0] - a.pos[0], c.s[1] - a.pos[1]], _bind2: 'b', bind2_pt: [c.e[0] - b.pos[0], c.e[1] - b.pos[1]] }
    same(resolveRoutes([a, b, ar]).get(2), c.expect, 1e-3, `경유지 ${n}`)
  })
})

test('알약 끌기·나눠 끌기가 데스크톱과 같다', () => {
  C.segments.forEach((c, n) => {
    let seg
    if (c.sub) seg = beginSubdivide(c.pts, c.i, c.near, 1)
    else { assert.ok(onPill(c.pts, c.i, c.near, 1), `알약 위 ${n}`); seg = beginSegment(c.pts, c.i) }
    same(endSegment(dragSegment(seg, { x: c.to[0], y: c.to[1] }, 1)), c.expect, 1e-6, `구간 ${n}${c.sub ? '(나눠)' : ''}`)
  })
})

test('알약은 화면 26px 넘는 구간에만, 고른 화살표 구간 찾기', () => {
  const pts = [[0, 0], [20, 0], [20, 100]]
  assert.deepEqual(segmentHandles(pts, 1).map(h => h.i), [1])
  assert.deepEqual(segmentHandles(pts, 2).map(h => h.i), [0, 1])   // 확대하면 짧은 구간도 화면에선 길어짐
  const s = nearestSegment(pts, { x: 25, y: 50 }); assert.equal(s.i, 1); assert.equal(s.d, 5)
})

test('곡선 휨 손잡이·붙을 때 S자가 데스크톱과 같다', () => {
  C.curves.forEach((c, n) => {
    const it = { p1: c.p1, p2: c.p2, ctrl1: null, ctrl2: null }
    const b = bendCurve(it, c.which, c.target, 2)
    same(b.ctrl1 ? [b.ctrl1, b.ctrl2] : [], c.bend, 1e-3, `휨 ${n}`)
    const s = snapCurve(it, c.n0 && { x: c.n0[0], y: c.n0[1] }, c.n1 && { x: c.n1[0], y: c.n1[1] })
    same(s.ctrl1 ? [s.ctrl1, s.ctrl2] : [], c.snap || [], 1e-3, `S자 ${n}`)
  })
})

test('라벨 길 투영·세 자리 붙기가 데스크톱과 같다', () => {
  const L = C.labels, poly = L.poly.map(([x, y]) => ({ x, y }))
  L.cases.forEach((c, n) => {
    const q = { x: c.q[0], y: c.q[1] }, a = projectToPath(poly, q), b = projectToCurve(L.curve, q)
    assert.ok(Math.abs(a.t - c.poly[0]) < 1e-3 && Math.abs(a.off - c.poly[1]) < 1e-3, `꺾은선 ${n}: ${a.t},${a.off} vs ${c.poly}`)
    assert.ok(Math.abs(b.t - c.curve[0]) < 1e-3 && Math.abs(b.off - c.curve[1]) < 1e-2, `곡선 ${n}: ${b.t},${b.off} vs ${c.curve}`)
    assert.ok(Math.abs(snapLabelOff({ x: c.n[0], y: c.n[1] }, c.poly[1], c.w, c.h) - c.snap) < 1e-3, `세 자리 ${n}`)
  })
})

test('안 붙은 화살표 「곡선」(`apply_curved` 활)이 데스크톱과 같고, 종류 바꾸기가 연결·라벨을 지킨다', () => {
  C.curves.forEach((c, n) => { const r = applyCurved({ _id: 'x', type: 'arrow', p1: c.p1, p2: c.p2, ctrl1: null, ctrl2: null }, [], it => it.rect); same([r.ctrl1, r.ctrl2], c.bow, 1e-3, `활 ${n}`) })
  const a = { _id: 'a', type: 'rect', rect: [0, 0, 100, 60], pos: [0, 0] }, b = { _id: 'b', type: 'rect', rect: [0, 0, 100, 60], pos: [300, 0] }
  const ar = { _id: 'r', type: 'arrow', pos: [0, 0], p1: [100, 30], p2: [300, 30], ctrl1: null, ctrl2: null, width: 2, head: true, color: '#f00', labels: [{ text: '가', t: 0.3, off: 0 }],
    _bind1: 'a', bind1_pt: [100, 30], _bind2: 'b', bind2_pt: [0, 30] }
  const o = swapArrowKind(ar, 'ortho', [a, b, ar], it => it.rect)
  assert.equal(o.type, 'sarrow'); assert.equal(o._id, 'r'); assert.equal(o._bind2, 'b'); assert.deepEqual(o.labels, ar.labels); assert.equal(o.color, '#f00')
  assert.deepEqual(o.pts[0], [100, 30]); assert.deepEqual(o.pts[o.pts.length - 1], [300, 30])
  const back = swapArrowKind(o, 'straight', [a, b, o], it => it.rect)
  assert.equal(back.type, 'arrow'); assert.equal(back.ctrl1, null); assert.deepEqual(back.p2, [300, 30])
})
