// node --test web/test — 직교 화살표 길 찾기(route.js)가 데스크톱 `_route_ortho`와 같은 답을 내는가(§8 항목61)
// 사례는 `python tools/export_route_cases.py`가 데스크톱 엔진으로 푼 것(fixtures/route_cases.json).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { routeOrtho } from '../src/route.js'

const SIDES = { left: { x: -1, y: 0 }, right: { x: 1, y: 0 }, top: { x: 0, y: -1 }, bottom: { x: 0, y: 1 } }
const R = r => r && { l: r[0], t: r[1], r: r[0] + r[2], b: r[1] + r[3] }
const { cases } = JSON.parse(readFileSync(new URL('./fixtures/route_cases.json', import.meta.url), 'utf8'))

test(`데스크톱과 같은 길 — 임의 배치 ${cases.length}개`, () => {
  const bad = []
  cases.forEach((c, i) => {
    const got = routeOrtho({ x: c.s[0], y: c.s[1] }, SIDES[c.ns] ?? null, { x: c.e[0], y: c.e[1] }, SIDES[c.ne] ?? null,
      c.obstacles.map(R), { conn: c.conn.map(R), minStub: c.minStub })
    const g = got.map(p => [Math.round(p.x * 1e4) / 1e4, Math.round(p.y * 1e4) / 1e4])
    if (JSON.stringify(g) !== JSON.stringify(c.expect)) bad.push(i)
  })
  assert.deepEqual(bad, [], `다른 답: ${bad.length}개 (첫 번째 #${bad[0]})`)
})

test('나란한 두 상자 마주 보는 포트 — 곧은 한 줄', () => {
  const pts = routeOrtho({ x: 100, y: 50 }, SIDES.right, { x: 300, y: 50 }, SIDES.left, [],
    { conn: [{ l: 0, t: 0, r: 100, b: 100 }, { l: 300, t: 0, r: 400, b: 100 }], minStub: [0, 25] })
  assert.deepEqual(pts, [{ x: 100, y: 50 }, { x: 300, y: 50 }])
})
