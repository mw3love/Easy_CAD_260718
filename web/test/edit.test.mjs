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

