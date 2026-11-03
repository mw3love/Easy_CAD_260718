// 🔷 도형 그리기(2026-11-03) — 서버 자리(진짜 KAIROS 설계서 → `board_diagram.place`, 재료 = tools/export_flow_place.py) → 칠판 물건.
// 붙은 화살표·변 고르기·지문. 실제 화면(길 찾기·어두운 화면)은 e2e flow58
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { flowItems, flowSig, linkSides, PAD } from '../src/next/flowboard.js'

const ALL = JSON.parse(readFileSync(new URL('./fixtures/flow_place.json', import.meta.url), 'utf-8'))

test('상자·화살표 수 = 설계서, 화살표 두 끝이 상자에 붙음', () => {
  for (const [name, { place, spec }] of Object.entries(ALL)) {
    const { frame, items } = flowItems(place, 100, 200, { no: 3, spec })
    const boxes = items.filter(it => it.flow_step), arrows = items.filter(it => it.type === 'sarrow'), ids = new Set(boxes.map(b => b._id))
    assert.equal(boxes.length, place.steps.length, name)
    assert.equal(arrows.length, place.links.length, name)
    for (const a of arrows) { assert.ok(ids.has(a._bind1) && ids.has(a._bind2), name); assert.ok(a.auto_route && a.routing === 'ortho') }
    assert.ok(items.every(it => it.flow_of === frame._id))
    assert.equal(frame.type, 'frame'); assert.equal(frame.no, 3); assert.equal(frame.flow_spec, spec)
    assert.deepEqual(frame.rect, [0, 0, place.width + 2 * PAD, place.height + 2 * PAD])
    for (const b of boxes) {   // 프레임 안
      assert.ok(b.pos[0] >= 100 + PAD - 0.5 && b.pos[1] >= 200 + PAD - 0.5 && b.pos[0] + b.rect[2] <= 100 + frame.rect[2] && b.pos[1] + b.rect[3] <= 200 + frame.rect[3], name)
    }
  }
})

test('모양 — 갈림길 = 마름모 심볼, 중요한 단계 하나만 코랄, 담당 띠 = 채운 패스(길 찾기 장애물 아님)', () => {
  const { place } = ALL['점검_sonnet'], { items } = flowItems(place, 0, 0)
  const dec = place.steps.filter(s => s.kind === 'decision').map(s => s.id)
  assert.ok(dec.length > 0)
  for (const it of items.filter(x => dec.includes(x.flow_step))) assert.deepEqual([it.type, it.kind], ['symbol', 'decision'])
  const coral = items.filter(it => it.pen === '#ffda7756')
  assert.equal(coral.length, place.focus ? 1 : 0)
  const s = ALL['송신소_sonnet'], r = flowItems(s.place, 0, 0)
  assert.equal(r.items.filter(it => it.type === 'path').length, s.place.lanes.length)
  assert.equal(r.items.filter(it => it.type === 'text').length, s.place.lanes.length)   // 띠 이름표
})

test('변 고르기 — 가로 흐름 = 오른쪽 → 왼쪽, 꺾은 덩어리 넘기 = 아래 → 위, 되돌아가기 = 아래 → 아래, 갈림길 「예/아니오」는 다른 꼭짓점', () => {
  const { place } = ALL['송신소_sonnet'], sides = linkSides(place), by = new Map(place.steps.map(s => [s.id, s]))
  place.links.forEach((k, i) => {
    const a = by.get(k.from), b = by.get(k.to)
    if (b.seg > a.seg) assert.deepEqual(sides[i], ['b', 't'])
    else if (place.ranks[k.to] <= place.ranks[k.from]) assert.deepEqual(sides[i], ['b', 'b'])
  })
  assert.ok(place.links.some((k, i) => sides[i][0] === 'r' && sides[i][1] === 'l'))
  const chk = ALL['점검_sonnet'].place, cs = linkSides(chk)
  for (const s of chk.steps.filter(x => x.kind === 'decision')) {
    const outs = chk.links.map((k, i) => [k, i]).filter(([k]) => k.from === s.id && chk.ranks[k.to] > chk.ranks[s.id]).map(([, i]) => cs[i][0])
    if (outs.length >= 2) assert.equal(new Set(outs).size, outs.length, `${s.text} 나가는 꼭짓점이 겹침`)
  }
})

test('지문 — 프레임째 옮기면 그대로, 상자 하나를 옮기면 달라짐', () => {
  const { place } = ALL['조직도_sonnet'], { frame, items } = flowItems(place, 0, 0)
  const moved = items.map(it => (it.type === 'sarrow' ? it : { ...it, pos: [it.pos[0] + 50, it.pos[1] + 30] }))
  assert.equal(flowSig(moved, 50, 30), frame.flow_sig)
  const one = items.map((it, i) => (i === items.findIndex(x => x.flow_step) ? { ...it, pos: [it.pos[0] + 9, it.pos[1]] } : it))
  assert.notEqual(flowSig(one, 0, 0), frame.flow_sig)
})
