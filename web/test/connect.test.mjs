// 붙는 규칙 대조 — 데스크톱 `_nearest_border`·`_shape_ports` 답(`tools/export_connect_cases.py`)과 connect.js가 같은지
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { nearestBorder, shapePorts, snapAt, dropTarget, isConnHost } from '../src/next/connect.js'

const cases = JSON.parse(readFileSync(new URL('./fixtures/connect_cases.json', import.meta.url)))
const rectOf = it => it.rect
const CURVED = new Set(['ellipse', 'terminal', 'delay', 'database', 'document', 'display', 'manual_input'])
const near = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg}: ${a} vs ${b}`)

test('외곽선 최근접점·법선이 데스크톱과 같다(곡선 평탄화 차이만 허용)', () => {
  // 거리는 늘 0.3 안. 곧은 도형은 자리 0.3·법선 0.02로 전부 같아야 한다.
  // 곡선 도형은 데스크톱이 Qt로 굵게 나눈 토막 위에서 재므로(토막 하나 10° 안팎) 평평한 곳·이음매에서 자리가 미끄러지고 법선이 갈린다 —
  // 거리는 전부, 자리(3)·법선(0.2)은 95% 이상 같으면 통과.
  let n = 0, curved = 0, off = []
  for (const c of cases) {
    const it = { ...c.item, _id: 'x' }, tag = `${it.type}${it.kind ? ':' + it.kind : ''} rot${it.rotation} s${it.scale}`, cv = CURVED.has(it.kind ?? it.type)
    for (const [qx, qy, px, py, nx, ny] of c.probes) {
      const r = nearestBorder(it, { x: qx, y: qy }, rectOf), at = `${tag} @(${qx},${qy})`
      near(Math.hypot(r.p.x - qx, r.p.y - qy), Math.hypot(px - qx, py - qy), 0.3, `${at} 거리`)
      n++
      if (!cv) { near(r.p.x, px, 0.3, at + ' p.x'); near(r.p.y, py, 0.3, at + ' p.y'); near(r.n.x, nx, 0.02, at + ' n.x'); near(r.n.y, ny, 0.02, at + ' n.y'); continue }
      curved++
      if (Math.hypot(r.p.x - px, r.p.y - py) > 3 || Math.hypot(r.n.x - nx, r.n.y - ny) > 0.2) off.push(at)
    }
  }
  assert.ok(n > 400)
  assert.ok(off.length <= curved * 0.05, `곡선 도형 어긋남 ${off.length}/${curved}: ${off.slice(0, 5).join(' | ')}`)
})

test('포트 넷(상·우·하·좌)이 데스크톱과 같다', () => {
  for (const c of cases) {
    const it = { ...c.item, _id: 'x' }, ports = shapePorts(it, rectOf)
    c.ports.forEach(([px, py, nx, ny], i) => {
      const tag = `${it.type}${it.kind ? ':' + it.kind : ''} port${i}`
      near(ports[i].p.x, px, 1, tag + ' x'); near(ports[i].p.y, py, 1, tag + ' y')
      near(ports[i].n.x, nx, 0.05, tag + ' nx'); near(ports[i].n.y, ny, 0.05, tag + ' ny')
    })
  }
})

test('붙는 순서: 포트 18px 먼저, 없으면 외곽선 14px, 그 밖은 안 붙음', () => {
  const box = { _id: 'a', type: 'rect', rect: [0, 0, 100, 60], pos: [0, 0] }
  assert.equal(snapAt([box], { x: 100 + 10, y: 30 + 10 }, 1, rectOf).port, true)                    // 오른쪽 포트에서 14px → 포트
  const b = snapAt([box], { x: 108, y: 10 }, 1, rectOf); assert.equal(b.port, false); assert.equal(b.p.x, 100)   // 포트에서 멀고 테두리 8px
  assert.equal(snapAt([box], { x: 50, y: 30 }, 1, rectOf), null)                                       // 한가운데 = 안 붙음
  assert.equal(snapAt([box], { x: 130, y: 2 }, 1, rectOf), null)
  assert.equal(snapAt([box], { x: 130, y: 2 }, 0.45, rectOf)?.port, false)                            // 줌아웃하면 화면 px가 줄어 테두리에 붙음(포트는 18.5px라 아직 밖)
  const d = dropTarget([box], { x: 50, y: 30 }, 1, rectOf, 'src')                                     // 놓을 때는 안에 놓아도 가장 가까운 포트로
  assert.equal(d.port, true); assert.equal(d.id, 'a')
})

test('붙는 도형 종류(데스크톱 `_is_conn_host`)', () => {
  for (const t of ['rect', 'ellipse', 'symbol', 'image', 'table', 'text']) assert.ok(isConnHost({ type: t }), t)
  assert.ok(isConnHost({ type: 'polygon', closed: true })); assert.ok(!isConnHost({ type: 'polygon', closed: false }))
  for (const t of ['line', 'sarrow', 'arrow', 'board', 'path']) assert.ok(!isConnHost({ type: t }), t)
})
