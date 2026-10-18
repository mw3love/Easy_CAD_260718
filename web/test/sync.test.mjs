// 공동작업 1단계(§8 항목61 ⓕ, 2026-10-18) — 부분 저장 만들기·남의 변경 받기(서로 다른 도형이면 둘 다 남음)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { applyToItems, diffModel, fromWire, rebase, snapshotModel, toWire } from '../src/next/sync.js'

const R = (id, w, extra = {}) => ({ _id: id, type: 'rect', rect: [0, 0, w, 10], ...extra })
const M = (items, extra = {}) => ({ format: 'easycad-doc', version: 1, layers: [{ id: 'default' }], items, ...extra })

test('보낼 꼴 — uid·연결은 상대 uid, _ 칸은 안 나감', () => {
  const a = { _id: 'a', type: 'sarrow', pts: [], _bind1: 'x', _bind2: null }
  assert.deepEqual(toWire(a), { type: 'sarrow', pts: [], uid: 'a', bind1: 'x', bind2: null })
  assert.deepEqual(fromWire(toWire(a)), a)
})

test('기준과 다른 것만 — 고침·새것·지움·레이어', () => {
  const base = snapshotModel(M([R('a', 1), R('b', 2)]))
  assert.equal(diffModel(base, M([R('a', 1), R('b', 2)])), null)
  const p = diffModel(base, M([R('a', 5), R('c', 3)], { layers: [{ id: 'default' }, { id: 'x' }] }))
  assert.deepEqual(p.upsert.map(w => [w.uid, w.rect[2]]), [['a', 5], ['c', 3]])
  assert.deepEqual(p.delete, ['b']); assert.equal(p.meta.layers.length, 2)
})

test('남의 변경 받기 — 갑은 a를, 을은 b를 고치면 둘 다 남음(안 보낸 내 것을 남의 것 위에 다시 얹음)', () => {
  const start = M([R('a', 1), R('b', 2)], { rev: 3 })
  const base = snapshotModel(start)
  const mine = M([R('a', 99), R('b', 2)])                        // 갑: a를 고쳤고 아직 안 보냄
  const remote = M([R('a', 1), R('b', 77), R('n', 4)], { rev: 4 })   // 을: b 고침 + n 넣음
  const out = rebase(remote, mine, base)
  assert.deepEqual(out.items.map(it => [it._id, it.rect[2]]), [['a', 99], ['b', 77], ['n', 4]])
  assert.equal(out.rev, 4)
  // 내가 지운 것은 남의 화면에서 와도 다시 안 생김, 남이 지운 것(내가 안 고친 것)은 사라짐
  const out2 = rebase(M([R('b', 2)], { rev: 5 }), M([R('b', 2), R('mine', 1)]), snapshotModel(M([R('a', 1), R('b', 2)])))
  assert.deepEqual(out2.items.map(it => it._id), ['b', 'mine'])
  assert.deepEqual(applyToItems([R('a', 1)], { upsert: [toWire(R('a', 2))], delete: [] })[0].rect[2], 2)
})

test('되돌리기 = 도형 단위 — 그사이 남이 고친 도형은 그대로', async () => {
  const { applyDelta, itemDelta, mergeDelta } = await import('../src/next/sync.js')
  const a = R('a', 1), b = R('b', 2)
  const d = itemDelta([a, b], [R('a', 5), b, R('c', 3)])              // 내가 a 고치고 c 넣음
  assert.deepEqual([...d.before.keys()].sort(), ['a', 'c'])
  const now = [R('a', 5), R('b', 77), R('c', 3), R('z', 9)]            // 그사이 남이 b 고치고 z 넣음
  const undone = applyDelta(now, d.before)
  assert.deepEqual(undone.map(it => [it._id, it.rect[2]]), [['a', 1], ['b', 77], ['z', 9]])
  assert.deepEqual(applyDelta(undone, d.after).map(it => it._id), ['a', 'b', 'c', 'z'])
  const del = itemDelta([a, b], [b]); assert.deepEqual(applyDelta([b], del.before).map(it => it._id), ['a', 'b'])   // 지운 것 되살리면 제자리
  const m = mergeDelta(itemDelta([a], [R('a', 2)]), itemDelta([R('a', 2)], [R('a', 3)]))
  assert.equal(m.before.get('a').it.rect[2], 1); assert.equal(m.after.get('a').it.rect[2], 3)
})
