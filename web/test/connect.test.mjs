// 붙는 규칙 대조 — 데스크톱 `_nearest_border`·`_shape_ports` 답(`tools/export_connect_cases.py`)과 connect.js가 같은지
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { nearestBorder, shapePorts, snapAt, dropTarget, isConnHost, isBindHost, pathEndPorts, groupHost, groupFrac, bindEnd } from '../src/next/connect.js'
import { resolveRoutes } from '../src/next/arrows.js'
import { followArrows, moveItems } from '../src/next/edit.js'

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
      const cv = CURVED.has(it.kind ?? it.type), pt = cv ? 3 : 1, nt = cv ? 0.2 : 0.05   // 곡선 끝(표시 심볼 왼쪽 등)은 토막 차이로 흔들림 — 외곽선 시험과 같은 허용
      near(ports[i].p.x, px, pt, tag + ' x'); near(ports[i].p.y, py, pt, tag + ' y')
      near(ports[i].n.x, nx, nt, tag + ' nx'); near(ports[i].n.y, ny, nt, tag + ' ny')
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

test('선·화살표에 붙기(좌표만) · 펜 궤적에 붙기(연결) — 데스크톱 `_border_snap_at` Pass 1·2', () => {
  const rectOf = it => it.rect || [0, 0, 0, 0]
  const line = { _id: 'L', type: 'line', pos: [0, 0], line: [0, 0, 100, 0] }
  const pen = { _id: 'P', type: 'path', pos: [0, 200], elements: [['M', 0, 0], ['L', 50, 0], ['L', 100, 50]], freehand: true }
  const box = { _id: 'B', type: 'rect', pos: [0, 0], rect: [100, -20, 60, 40] }   // 왼쪽 변 가운데 = (100,0) = 선 끝점과 같은 자리
  // 선 끝점 근처 → 좌표만(id 없음), 바깥 방향
  let s = snapAt([], { x: 105, y: 3 }, 1, rectOf, [line])
  assert.equal(s.id, null); assert.deepEqual(s.p, { x: 100, y: 0 }); assert.deepEqual(s.n, { x: 1, y: 0 })
  // 같은 거리면 도형 포트가 이김
  s = snapAt([box], { x: 100, y: 5 }, 1, rectOf, [line])
  assert.equal(s.id, 'B')
  // 선 몸통 → 가장 가까운 점, 법선은 커서 쪽
  s = snapAt([], { x: 50, y: -10 }, 1, rectOf, [line])
  assert.equal(s.id, null); assert.deepEqual(s.p, { x: 50, y: 0 }); assert.equal(s.n.y, -1)
  // 펜 궤적: 양 끝이 포트, 몸통에도 붙고 연결됨
  assert.ok(isBindHost(pen) && !isConnHost(pen))
  const ends = pathEndPorts(pen)
  assert.deepEqual(ends.map(e => e.p), [{ x: 0, y: 200 }, { x: 100, y: 250 }])
  assert.deepEqual(ends[0].n, { x: -1, y: 0 })
  s = snapAt([pen], { x: 4, y: 206 }, 1, it => [0, 0, 100, 50]); assert.equal(s.id, 'P'); assert.ok(s.port)
  s = snapAt([pen], { x: 25, y: 192 }, 1, it => [0, 0, 100, 50]); assert.equal(s.id, 'P'); assert.ok(!s.port); assert.deepEqual(s.p, { x: 25, y: 200 })
  // 펜 궤적엔 '안'이 없어 다른 도형 속 포트 고르기에서 빠짐
  assert.equal(dropTarget([pen], { x: 50, y: 230 }, 1, it => [0, 0, 100, 50], null), null)
})

test('묶음 통째 붙기 — 감싼 사각형 = 가상 상자, bindN_group + 0~1 비율, 묶음을 옮기면 따라감(데스크톱 `_GroupBindProxy`)', () => {
  const rectOf = it => it.rect || [0, 0, 0, 0]
  const a = { _id: 'a', type: 'image', pos: [0, 0], rect: [0, 0, 40, 40], group_id: 'G' }   // 그림·표는 선 두께 여유 없음
  const b = { _id: 'b', type: 'table', pos: [60, 20], rect: [0, 0, 40, 40], group_id: 'G' }
  const g = groupHost([a, b], 'G', rectOf)
  assert.deepEqual(g.rect, [0, 0, 100, 60])
  // 묶음 틀의 포트(오른쪽 변 가운데)에 붙음 — 낱개 원이 아니라 틀
  const s = snapAt([g], { x: 103, y: 31 }, 1, rectOf)
  assert.equal(s.id, 'g:G'); assert.deepEqual(s.p, { x: 100, y: 30 })
  assert.deepEqual(groupFrac(g, s.p), [1, 0.5])
  const ar = { _id: 'r', type: 'sarrow', pos: [0, 0], pts: [[300, 30], [100, 30]], auto_route: true, routing: 'ortho', head: true, width: 1,
    _bind1: null, bind1_pt: null, bind1_group: null, _bind2: null, bind2_pt: [1, 0.5], bind2_group: 'G' }
  assert.deepEqual(bindEnd(ar, 'bind2', [a, b, ar], rectOf).p, { x: 100, y: 30 })
  assert.ok(resolveRoutes([a, b, ar], rectOf).has(2), '묶음에 붙은 자동 길 화살표는 다시 찾음')
  // 묶음을 오른쪽 아래로 옮기면 끝이 따라감
  const moved = followArrows(moveItems([a, b, ar], ['a', 'b'], 50, 10), rectOf)
  const end = moved[2].pts.at(-1)
  assert.deepEqual(end, [150, 40])
})

test('묶음 틀 = 데스크톱 `_content_rect` 합(선 두께 절반, 원은 +1)', () => {
  const rectOf = it => it.rect
  const g = groupHost([{ type: 'rect', pos: [0, 0], rect: [0, 0, 40, 40], width: 2, group_id: 'G' }, { type: 'ellipse', pos: [100, 0], rect: [0, 0, 40, 40], width: 2, group_id: 'G' }], 'G', rectOf)
  assert.deepEqual(g.rect, [-1, -2, 143, 44])
})

