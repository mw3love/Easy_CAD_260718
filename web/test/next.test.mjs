// node --test web/test — 직접 만드는 칠판(src/next)의 순수 계산(§8 항목61 「바뀐 결정」 1단계)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { colEdges, dashArray, headSize, headTriangle, itemTransform, labelAnchor, labelInset, paperWH, polylineAt, roundedPath, roundedPts, runsToLines, strokeOutline, trimmedPts, bezierSub, bezierAt } from '../src/next/geom.js'
import { resolveRoutes, sarrowRadius } from '../src/next/arrows.js'
import { boardMembership, docBounds, drawOrder } from '../src/next/doc.js'

const fixture = JSON.parse(readFileSync(new URL('../../tests/fixtures/all_types.ecad', import.meta.url), 'utf8'))

test('화살촉·몸통 자르기·둥근 꺾임 — 데스크톱 공식', () => {
  assert.equal(headSize(2), 11)          // 바닥 11
  assert.equal(headSize(5, 1.5), 24)     // 굵기×3.2×배율
  const tri = headTriangle({ x: 0, y: 0 }, 0, 10)
  assert.ok(Math.abs(tri[1].x - 10 * Math.cos((150 * Math.PI) / 180)) < 1e-9)
  const t = trimmedPts([{ x: 0, y: 0 }, { x: 100, y: 0 }], 20, true, false)
  assert.equal(t[1].x, 83)              // 끝 쪽만 20×0.85
  assert.equal(roundedPath([{ x: 0, y: 0 }, { x: 10, y: 0 }, { x: 10, y: 10 }], 0), 'M0,0 L10,0 L10,10')
  assert.match(roundedPath([{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }], 10), /Q100,0 100,10/)
})

test('경로 위 t 자리·왼쪽 법선', () => {
  const { p, n } = polylineAt([{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 100 }], 0.75)
  assert.deepEqual(p, { x: 100, y: 50 })
  assert.deepEqual(n, { x: -1, y: 0 })
})

test('베지어 부분 곡선 — 양 끝이 원래 곡선 위', () => {
  const P = [{ x: 0, y: 0 }, { x: 0, y: 100 }, { x: 100, y: 100 }, { x: 100, y: 0 }]
  const [a, , , d] = bezierSub(...P, 0.2, 0.9), A = bezierAt(...P, 0.2), D = bezierAt(...P, 0.9)
  assert.ok(Math.hypot(a.x - A.x, a.y - A.y) < 1e-9 && Math.hypot(d.x - D.x, d.y - D.y) < 1e-9)
})

test('runs → 줄마다 조각(부분 강조·형광펜)', () => {
  const lines = runsToLines('ab\ncde', [[3, 1, '#da7756', true], [4, 2, null, false, '#80ffeb3b']])
  assert.deepEqual(lines[0], [{ text: 'ab', color: null, bold: false, bg: null }])
  assert.deepEqual(lines[1].map(p => [p.text, p.bold, p.bg]), [['c', true, null], ['de', false, '#80ffeb3b']])
})

test('변환·점선·표 열·용지·라벨 비율 — 데스크톱 값', () => {
  assert.equal(itemTransform({ pos: [10, 20] }), 'translate(10,20)')
  assert.equal(itemTransform({ pos: [0, 0], rotation: 20, origin: [60, 30] }), 'translate(0,0) translate(60,30) rotate(20) translate(-60,-30)')
  assert.equal(dashArray(2, 2), '8 4')
  assert.equal(dashArray(1, 2), undefined)
  assert.deepEqual(colEdges(0, 300, [0.4, 0.3, 0.3]), [0, 120, 210, 300])
  assert.deepEqual(paperWH('A4', 'landscape'), [297, 210])
  assert.equal(labelInset('symbol', 'decision'), 0.6)
  assert.equal(labelInset('ellipse'), 0.72)
  assert.deepEqual(labelAnchor('symbol', 'triangle', [0, 0, 90, 60]), { x: 30, y: 30 })
})

test('옛 직각 화살표 모서리 — routing·curve_r 없으면 auto_route면 각짐(0), 새 파일은 저장값', () => {
  assert.equal(sarrowRadius({ auto_route: true }), 0)
  assert.equal(sarrowRadius({ auto_route: false }), 10)
  assert.equal(sarrowRadius({ routing: 'ortho', curve_r: 10 }), 10)
})

test('열 때 다시 찾은 길 = 데스크톱이 열고 저장한 길(모든 종류 시험 문서의 붙은 화살표)', () => {
  const items = fixture.items, i = items.findIndex(it => it.type === 'sarrow' && it.auto_route && it.bind1 != null)
  assert.ok(i >= 0)
  const got = resolveRoutes(items).get(i).map(([x, y]) => [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000])
  assert.deepEqual(got, items[i].pts.map(([x, y]) => [Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000]))
})

test('그리는 차례·보드 소속·전체 범위', () => {
  const items = fixture.items, order = drawOrder(items)
  assert.equal(order[0][0].type, 'board')             // z -1이 먼저
  const on = boardMembership(items), k = items.findIndex(it => it.type === 'text' && it.text === '보드 안 흰 글')
  assert.equal(on[k], true)
  assert.equal(on[items.findIndex(it => it.type === 'badge')], false)
  const b = docBounds(items)
  assert.ok(b.w > 1000 && b.h > 500)
})

test('라벨 자리 비우기 — 계산으로 잘라 꺾인 곳은 이어짐', async () => {
  const { cutPolyline } = await import('../src/next/geom.js')
  const P = (x, y) => ({ x, y })
  assert.deepEqual(cutPolyline([P(0, 0), P(100, 0), P(100, 100)], [{ x: 40, y: -5, w: 20, h: 10 }]), [[P(0, 0), P(40, 0)], [P(60, 0), P(100, 0), P(100, 100)]])
  assert.deepEqual(cutPolyline([P(0, 0), P(100, 0)], []), [[P(0, 0), P(100, 0)]])
  assert.deepEqual(cutPolyline([P(0, 0), P(100, 0)], [{ x: -10, y: -5, w: 200, h: 10 }]), [])
})

test('선 띠 윤곽 — 폭 2·hw, 직각 꺾임은 맞댐, 끝은 반원/잘라냄(범위 미리보기 테두리)', () => {
  const L = [{ x: 0, y: 0 }, { x: 100, y: 0 }, { x: 100, y: 50 }]
  const o = strokeOutline(L, 2, false, false)
  const xs = o.map(p => p.x), ys = o.map(p => p.y)
  assert.equal(Math.min(...xs), 0); assert.equal(Math.max(...xs), 102); assert.equal(Math.min(...ys), -2); assert.equal(Math.max(...ys), 50)
  assert.ok(o.some(p => Math.abs(p.x - 102) < 1e-9 && Math.abs(p.y + 2) < 1e-9), '바깥 모서리 맞댐점')
  assert.ok(o.some(p => Math.abs(p.x - 98) < 1e-9 && Math.abs(p.y - 2) < 1e-9), '안쪽 모서리 맞댐점')
  const c = strokeOutline(L, 2, true, true), cy = c.map(p => p.y), cx = c.map(p => p.x)
  assert.ok(Math.abs(Math.max(...cy) - 52) < 1e-9 && Math.abs(Math.min(...cx) + 2) < 1e-9, '반원 끝은 hw만큼 더 나감')
  const r = roundedPts(L, 10)
  assert.ok(r.length > 3 && r.every(p => p.x <= 100 && p.y <= 50), '둥근 꺾임 점열은 원래 꺾은선 안쪽')
})
