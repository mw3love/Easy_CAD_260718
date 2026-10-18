// node --test web/test — 직접 만드는 칠판 2단계 편집 계산(model·edit·align)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fromEcad, toEcad } from '../src/next/model.js'
import { duplicate, expandGroups, followArrows, groupItems, hits, mirror, moveItems, removeItems, resizeRect, rotateTo, rubberSelect, toLocal, toScene, toggleLock, topHit, zOrder, boardContents } from '../src/next/edit.js'
import { alignSnap } from '../src/next/align.js'

const raw = JSON.parse(readFileSync(new URL('../../tests/fixtures/all_types.ecad', import.meta.url), 'utf8'))
const tb = () => ({ w: 100, h: 20 })   // 글 상자(시험용 고정)
const rect = (id, x, y, w = 100, h = 60, extra = {}) => ({ _id: id, type: 'rect', pos: [x, y], rect: [0, 0, w, h], pen: '#ff000000', width: 2, ...extra })

test('모델 왕복 — .ecad 그대로(연결 순번은 _id로 들었다 되돌림, _ 키는 안 나감)', () => {
  const m = fromEcad(raw), back = toEcad(m)
  assert.deepEqual(back, raw)
  const a = m.items.find(it => it.type === 'sarrow' && it._bind1)
  assert.equal(m.items.find(it => it._id === a._bind1).type, 'rect')
})

test('지운 도형에 붙은 화살표 끝은 끊김(화살표는 남음 — 데스크톱과 같음)', () => {
  const m = fromEcad(raw), a = m.items.find(it => it.type === 'sarrow' && it._bind1)
  const after = toEcad({ ...m, items: removeItems(m.items, [a._bind1]) })
  const arrow = after.items.find(it => it.type === 'sarrow' && it.auto_route)
  assert.equal(arrow.bind1, null)
  assert.notEqual(arrow.bind2, null)
})

test('좌표 바꾸기 — 회전·origin 왕복', () => {
  const it = { pos: [10, 20], rotation: 30, origin: [50, 25], scale: 1.5 }
  const p = toScene(it, { x: 7, y: 3 }), q = toLocal(it, p)
  assert.ok(Math.abs(q.x - 7) < 1e-9 && Math.abs(q.y - 3) < 1e-9)
})

test('누르기 — 속 빈 상자 안쪽도 상자, 잠긴 것은 못 잡음, 위에 그린 것이 먼저', () => {
  const a = rect('a', 0, 0), b = rect('b', 50, 30, 100, 60, { z: 1 })
  assert.equal(topHit([a, b], { x: 60, y: 40 }, 1, tb)._id, 'b')
  assert.equal(topHit([a, b], { x: 20, y: 20 }, 1, tb)._id, 'a')
  assert.equal(topHit([a, { ...b, locked: true }], { x: 120, y: 80 }, 1, tb), null)
  assert.ok(hits({ type: 'line', pos: [0, 0], line: [0, 0, 100, 0], width: 2 }, { x: 50, y: 3 }, 2, tb))
  assert.ok(!hits({ type: 'line', pos: [0, 0], line: [0, 0, 100, 0], width: 2 }, { x: 50, y: 9 }, 2, tb))
})

test('범위 선택 — 왼→오는 완전 포함, 오→왼은 걸침', () => {
  const items = [rect('a', 0, 0), rect('b', 200, 0)]
  assert.deepEqual(rubberSelect(items, { x: -10, y: -10 }, { x: 150, y: 100 }, tb), ['a'])
  assert.deepEqual(rubberSelect(items, { x: 250, y: 100 }, { x: 50, y: -10 }, tb).sort(), ['a', 'b'])
})

test('걸침 선택 — 감싼 사각형이 아니라 실제 선과 겹칠 때(데스크톱 `_base_shape().intersects`)', () => {
  const diag = { _id: 'd', type: 'sarrow', pos: [0, 0], pts: [[0, 0], [200, 0], [200, 200]], width: 2 }   // ┐ 모양 — 왼쪽 아래는 빈 자리
  const ring = { _id: 'e', type: 'ellipse', pos: [400, 0], rect: [0, 0, 200, 200], width: 2 }
  const big = rect('r', 700, 0, 300, 300)
  const items = [diag, ring, big]
  assert.deepEqual(rubberSelect(items, { x: 60, y: 190 }, { x: 10, y: 140 }, tb), [], '빈 모서리만 스치면 안 걸림')
  assert.deepEqual(rubberSelect(items, { x: 210, y: 190 }, { x: 190, y: 140 }, tb), ['d'], '꺾인 선에 닿으면 걸림')
  assert.deepEqual(rubberSelect(items, { x: 415, y: 15 }, { x: 405, y: 5 }, tb), [], '원의 바깥 모서리 자리는 안 걸림')
  assert.deepEqual(rubberSelect(items, { x: 860, y: 160 }, { x: 840, y: 140 }, tb), ['r'], '닫힌 도형 안쪽에 통째로 들어도 걸림')
})

test('크기 — 모서리·변·이미지 비율 고정', () => {
  assert.deepEqual(resizeRect([0, 0, 100, 50], 'br', { x: 150, y: 80 }), [0, 0, 150, 80])
  assert.deepEqual(resizeRect([0, 0, 100, 50], 'l', { x: 20, y: 999 }), [20, 0, 80, 50])
  assert.deepEqual(resizeRect([0, 0, 100, 50], 'br', { x: 200, y: 60 }, { keepRatio: true }), [0, 0, 200, 100])
})

test('회전 — 가운데 기준, 같은 가운데가 같은 자리에 남음, Shift 15°', () => {
  const it = rect('a', 10, 10), r = rotateTo(it, 37, true)
  assert.equal(r.rotation, 30)
  const c0 = toScene(it, { x: 50, y: 30 }), c1 = toScene(r, { x: 50, y: 30 })
  assert.ok(Math.hypot(c0.x - c1.x, c0.y - c1.y) < 1e-9)
})

test('복제·묶음·잠금·순서', () => {
  const items = [rect('a', 0, 0, 100, 60, { group_id: 'g' }), rect('b', 200, 0, 100, 60, { group_id: 'g', z: 3 })]
  assert.deepEqual(expandGroups(items, ['a']).sort(), ['a', 'b'])
  const d = duplicate(items, ['a', 'b'], 20, 20)
  assert.equal(d.items.length, 4)
  const copies = d.items.filter(it => d.ids.includes(it._id))
  assert.equal(new Set(copies.map(c => c.group_id)).size, 1)
  assert.notEqual(copies[0].group_id, 'g')               // 복제본은 새 묶음
  assert.deepEqual(copies[0].pos, [20, 20])
  assert.ok(toggleLock(items, ['a']).find(it => it._id === 'a').locked)
  const g = groupItems(items.map(it => ({ ...it, group_id: null })), ['a', 'b'])
  assert.equal(new Set(g.map(it => it.group_id)).size, 1)
  const z = zOrder(items, ['a'], true)
  assert.ok(z.find(it => it._id === 'a').z > 3)
})

test('반전 — 상자 둘의 좌우 자리가 바뀜', () => {
  const m = mirror([rect('a', 0, 0), rect('b', 300, 0)], ['a', 'b'], true, tb)
  assert.deepEqual(m.map(it => it.pos[0]), [300, 0])
})

test('보드를 옮기면 안의 것도(가운데가 보드 안)', () => {
  const items = [{ _id: 'B', type: 'board', pos: [0, 0], rect: [0, 0, 400, 300] }, rect('in', 50, 50), rect('out', 500, 50)]
  assert.deepEqual(boardContents(items, ['B'], tb), ['in'])
})

test('붙은 화살표 따라가기 — 「자동 길」은 다시 꺾고, 아니면 양 끝만', () => {
  const m = fromEcad(raw), a = m.items.find(it => it.type === 'sarrow' && it._bind1)
  const moved = followArrows(moveItems(m.items, [a._bind1], 0, 200))
  const na = moved.find(it => it._id === a._id)
  assert.notDeepEqual(na.pts, a.pts)
  const manual = [rect('h', 0, 0), { _id: 'ar', type: 'sarrow', pos: [0, 0], pts: [[100, 30], [150, 30], [150, 100]], _bind1: 'h', bind1_pt: [100, 30], width: 2 }]
  const f = followArrows(moveItems(manual, ['h'], 10, 5)).find(it => it._id === 'ar')
  assert.deepEqual(f.pts, [[110, 35], [150, 30], [150, 100]])
})

test('스마트 정렬 — 임계 안이면 당김 + 같은 거리 역할은 선 여러 개, 가운데-가운데만 실선 역할', () => {
  const r = alignSnap({ x: 0, y: 103, w: 100, h: 50 }, [{ x: 300, y: 100, w: 100, h: 50 }], 1)
  assert.equal(r.dy, -3)
  assert.deepEqual(r.guides.map(g => g.role).sort(), ['bottom', 'center', 'top'])
  assert.equal(alignSnap({ x: 0, y: 130, w: 100, h: 50 }, [{ x: 300, y: 100, w: 100, h: 50 }], 1).dy, -5)   // 가운데-변(내 가운데 155 = 상대 아래 150)
  assert.equal(alignSnap({ x: 0, y: 170, w: 100, h: 50 }, [{ x: 300, y: 100, w: 100, h: 50 }], 1).dy, 0)    // 가장 가까운 후보도 20 — 안 당김
  assert.equal(alignSnap({ x: 0, y: 170, w: 100, h: 50 }, [{ x: 300, y: 100, w: 100, h: 50 }], 0.3).dy, -20) // 멀리서 보면(30%) 임계가 칠판 33 — 마주 보는 변
})

test('손으로 그린 직각 길은 붙은 도형이 움직여도 직각 유지(데스크톱 reroute manual_ortho와 같은 꼭짓점)', () => {
  const a = { _id: 'a', type: 'rect', rect: [0, 0, 160, 80], pos: [40, 40] }, e = { _id: 'e', type: 'ellipse', rect: [0, 0, 140, 80], pos: [260, 40] }
  const ar = { _id: 'r', type: 'sarrow', pos: [0, 0], routing: 'ortho', auto_route: false, pts: [[120, 120], [120, 133], [330, 133], [330, 120]],
    _bind1: 'a', bind1_pt: [80, 80], _bind2: 'e', bind2_pt: [70, 80] }
  const out = followArrows([a, { ...e, pos: [320, 160] }, ar]).find(x => x._id === 'r')
  assert.deepEqual(out.pts, [[120, 120], [120, 133], [390, 133], [390, 240]])   // 데스크톱 엔진 실측 답(2026-10-17)
})

test('묶음에 붙은 끝은 저장해도 남음(bindN = null, bindN_group + 비율) — 데스크톱이 같은 연결로 읽음', () => {
  const doc = { format: 'easycad-doc', version: 1, items: [
    { type: 'rect', pos: [0, 0], rect: [0, 0, 40, 40], group_id: 'G' },
    { type: 'sarrow', pos: [0, 0], pts: [[100, 20], [40, 20]], bind1: null, bind1_pt: null, bind1_group: null, bind2: null, bind2_pt: [1, 0.5], bind2_group: 'G' }] }
  const back = toEcad(fromEcad(doc)).items[1]
  assert.equal(back.bind2, null); assert.equal(back.bind2_group, 'G'); assert.deepEqual(back.bind2_pt, [1, 0.5])
})

test('손으로 놓은 직각 길이 끝을 따라가도 사선이 안 생김 — 양끝 같이 움직이면 평행이동, 한 줄 점은 같이(2026-10-18 사용자 화면)', () => {
  const rectOf = it => it.rect || [0, 0, 0, 0]
  const A = rect('A', 0, 0, 100, 60), B = rect('B', 400, 0, 100, 60)
  // 끝 구간이 세로, 그 위 점도 같은 세로줄(한 줄 점 셋) — 옛 규칙은 옆 점만 밀어 그다음 구간이 사선이 됐다
  const ar = { _id: 'r', type: 'sarrow', pos: [0, 0], routing: 'ortho', auto_route: false, width: 1, head: true,
    pts: [[50, 60], [50, 100], [50, 140], [450, 140], [450, 60]], _bind1: 'A', bind1_pt: [50, 60], bind1_group: null, _bind2: 'B', bind2_pt: [50, 60], bind2_group: null }
  const ortho = pts => pts.every((p, i) => !i || Math.abs(p[0] - pts[i - 1][0]) < 1e-6 || Math.abs(p[1] - pts[i - 1][1]) < 1e-6)
  // 한쪽(A)만 오른쪽으로 20 → 한 줄 점이 다 같이 x 70
  let out = followArrows(moveItems([A, B, ar], ['A'], 20, 0), rectOf)[2]
  assert.ok(ortho(out.pts), JSON.stringify(out.pts)); assert.deepEqual(out.pts.slice(0, 3), [[70, 60], [70, 100], [70, 140]])
  // 둘 다 같이 (15, 25) → 길 전체 평행이동
  out = followArrows(moveItems([A, B, ar], ['A', 'B'], 15, 25), rectOf)[2]
  assert.deepEqual(out.pts, ar.pts.map(([x, y]) => [x + 15, y + 25]))
})


import { tableOp } from '../src/next/edit.js'
test('tableOp — 행·열 넣기·지우기(크기는 행 높이·열 폭만큼)', () => {
  const t = { type: 'table', rows: 2, cols: 2, rect: [0, 0, 80, 28], col_widths: [0.25, 0.75], cells: [['a', 'b'], ['c', 'd']] }
  const r1 = tableOp(t, 'rowBelow', 0, 0)
  assert.equal(r1.rows, 3); assert.deepEqual(r1.cells, [['a', 'b'], ['', ''], ['c', 'd']]); assert.equal(r1.rect[3], 42)
  const c1 = tableOp(t, 'colLeft', 0, 1)
  assert.equal(c1.cols, 3); assert.deepEqual(c1.cells[0], ['a', '', 'b']); assert.equal(c1.rect[2], 140)
  assert.deepEqual(c1.col_widths.map(v => Math.round(v * 140)), [20, 60, 60])
  const d = tableOp(c1, 'delCol', 0, 0)
  assert.deepEqual(d.cells[0], ['', 'b']); assert.equal(Math.round(d.rect[2]), 120)
  assert.equal(tableOp({ ...t, rows: 1, cells: [['a', 'b']] }, 'delRow', 0, 0).rows, 1)   // 마지막 한 줄은 못 지움
})

test('tableOp — 칸 꾸밈(cell_styles)도 행·열을 따라 밀리고, 지운 줄 것은 사라짐', () => {
  const t = { type: 'table', rows: 2, cols: 2, rect: [0, 0, 80, 28], cells: [['a', 'b'], ['c', 'd']], cell_styles: { '0,1': { bold: true }, '1,0': { fill: '#ff00ff00' } } }
  assert.deepEqual(tableOp(t, 'rowAbove', 0, 0).cell_styles, { '1,1': { bold: true }, '2,0': { fill: '#ff00ff00' } })
  assert.deepEqual(tableOp(t, 'colLeft', 0, 1).cell_styles, { '0,2': { bold: true }, '1,0': { fill: '#ff00ff00' } })
  assert.deepEqual(tableOp(t, 'delRow', 1, 0).cell_styles, { '0,1': { bold: true } })
})

import { readingOrder } from '../src/next/edit.js'
test('readingOrder — 줄 우선(지그재그)·칸 우선, 조금 어긋나도 같은 줄', () => {
  const b = (id, x, y) => ({ id, x, y, w: 100, h: 70 })
  const pages = [b('C', 0, 100), b('B', 120, 5), b('A', 0, 0), b('D', 120, 110)]   // B는 A보다 5 낮아도 같은 줄
  assert.deepEqual(readingOrder(pages, 'rows').map(p => p.id), ['A', 'B', 'C', 'D'])
  assert.deepEqual(readingOrder(pages, 'cols').map(p => p.id), ['A', 'C', 'B', 'D'])
})

// 프레임(2026-10-18): 옮기면 가운데가 안에 있는 것이 같이(Lucid Magnetize), 「틀만」(magnet:false)이면 따로. 안의 보드·프레임도 같이
test('프레임 안의 것 같이 움직임', async () => {
  const { boardContents } = await import('../src/next/edit.js')
  const tb = it => ({ w: 10, h: 10 }), R = (id, x, y, w = 20, h = 20, extra = {}) => ({ _id: id, type: 'rect', pos: [x, y], rect: [0, 0, w, h], ...extra })
  const items = [{ _id: 'f', type: 'frame', pos: [0, 0], rect: [0, 0, 200, 100] }, R('a', 10, 10), R('b', 300, 10), { _id: 'g', type: 'board', pos: [100, 20], rect: [0, 0, 50, 50] },
    R('c', 190, 90, 40, 40)]   // c는 가운데(210,110)가 밖
  assert.deepEqual(boardContents(items, ['f'], tb).sort(), ['a', 'g'])
  assert.deepEqual(boardContents(items.map(it => (it._id === 'f' ? { ...it, magnet: false } : it)), ['f'], tb), [])
})

// 프레임 순서(2026-10-18): no 오름차순·같으면 문서 순서, 번호 없는 건 끝 — 다시 매기면 1..n(겹침 없음)
test('프레임 순서', async () => {
  const { orderedFrames, setFrameOrder } = await import('../src/next/edit.js')
  const F = (id, no) => ({ _id: id, type: 'frame', rect: [0, 0, 10, 10], ...(no != null ? { no } : {}) })
  const items = [F('a', 2), { _id: 'r', type: 'rect' }, F('b', 2), F('c'), F('d', 1)]
  assert.deepEqual(orderedFrames(items).map(f => f._id), ['d', 'a', 'b', 'c'])
  const re = setFrameOrder(items, ['c', 'd', 'a', 'b'])
  assert.deepEqual(orderedFrames(re).map(f => [f._id, f.no]), [['c', 1], ['d', 2], ['a', 3], ['b', 4]])
})
