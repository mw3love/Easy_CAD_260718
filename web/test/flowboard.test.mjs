// 🔷 도형 그리기(2026-11-03) — 서버 자리(진짜 KAIROS 설계서 → `board_diagram.place`, 재료 = tools/export_flow_place.py) → 칠판 물건.
// 붙은 화살표·변 고르기·지문. 실제 화면(길 찾기·어두운 화면)은 e2e flow58
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { flowItems, flowSig, linkSides, PAD } from '../src/next/flowboard.js'
import { resolveRoutes } from '../src/next/arrows.js'
import { textW } from '../src/next/chart.js'
import { polylineAt } from '../src/next/geom.js'

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

// 2026-11-03 사용자(공개 칠판 18번 「방송 송신소 계통도」): 「예비 전원」 라벨이 짧은 화살표를 다 덮어 화살촉만 보였고,
// 「전원 공급」 라벨 뒤로 같은 높이에 포개진 남의 화살표(신호 분배 → 변조기)가 지나갔음
test('라벨 화살표 — 옆 칸으로 곧게 가면 라벨 + 양옆 선이 들어갈 간격(서버 배치), 통로에서 겹치는 화살표는 높이를 나눔', () => {
  const { place } = ALL['송신소_칠판'], by = new Map(place.steps.map(s => [s.id, s]))
  for (const k of place.links.filter(x => x.text)) {
    const a = by.get(k.from), b = by.get(k.to)
    if (a.lane !== b.lane || place.ranks[k.to] !== place.ranks[k.from] + 1 || a.box[1] !== b.box[1]) continue
    assert.ok(b.box[0] - (a.box[0] + a.box[2]) >= textW(k.text, 16) + 40, `${k.text} 간격이 라벨보다 좁음`)
  }
  // 조직도_sonnet·마인드맵_sol(한 덩어리 안 칸 사이 — 꺾은 덩어리 통로가 아님)은 아직 포개짐: 예) 기술국 → 송신·시설부와 경영국 → 총무·인사부(2026-11-03 남은 일)
  for (const name of ['송신소_칠판', '송신소_sonnet', '점검_sonnet']) {
    const pl = ALL[name].place, { items } = flowItems(pl, 0, 0), routes = resolveRoutes(items)
    const hs = []   // 화살표마다 가로 구간 [y, x0, x1, 화살표, 시작 상자]
    items.forEach((it, i) => {
      if (it.type !== 'sarrow') return
      const p = routes.get(i) || it.pts
      for (let j = 1; j < p.length; j++) if (Math.abs(p[j][1] - p[j - 1][1]) < 0.5) hs.push([p[j][1], Math.min(p[j][0], p[j - 1][0]), Math.max(p[j][0], p[j - 1][0]), i, it._bind1, it._bind2])
    })
    for (const x of hs) for (const y of hs) {
      if (x[3] >= y[3] || x[4] === y[4] || x[5] === y[5]) continue   // 같은 화살표·같은 상자에서 갈라지거나 모이는 건 괜찮음
      const over = Math.min(x[2], y[2]) - Math.max(x[1], y[1])
      assert.ok(!(Math.abs(x[0] - y[0]) < 2 && over > 4), `${name}: 화살표 ${x[3]}·${y[3]}가 y ${Math.round(x[0])}에서 ${Math.round(over)}만큼 포개짐`)
    }
  }
})

// 2026-11-03 실조건(공개 칠판 19번): 곧게 내려가는 「전원 공급」 라벨 밑을 남의 가로선이 지나갔고, 「출력 샘플」·「제어」 라벨이 서로 겹쳤음
// 빈자리가 아예 없는 것(남은 일): 되돌림 선(아래 줄 → 위 줄, 아래 변끼리)이 라벨 달린 두 상자 사이(119)를 세로로 지남(길 찾기) —
// 송신소_칠판2 「제어」가 「출력 샘플」을, 송신소_칠판3 「상태 보고·원격제어」가 「변조된 RF」·「출력 샘플」을. 이것도 다른 라벨·상자와는 안 겹쳐야 함
const KNOWN = new Set(['송신소_칠판2|출력 샘플', '송신소_칠판3|변조된 RF', '송신소_칠판3|출력 샘플'])
test('라벨 자리 — 남의 선·상자·다른 라벨에 안 걸리는 제 선 위(처음 지을 때)', () => {
  const LH = 16 * 1.3 + 10, meet = (a, b) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b
  for (const name of Object.keys(ALL)) {
    const { items } = flowItems(ALL[name].place, 0, 0), routes = resolveRoutes(items)
    const arrows = items.map((it, i) => (it.type === 'sarrow' ? { it, pts: (routes.get(i) || it.pts).map(([x, y]) => ({ x, y })) } : null)).filter(Boolean)
    const boxes = items.filter(it => it.flow_step).map(it => ({ l: it.pos[0], t: it.pos[1], r: it.pos[0] + it.rect[2], b: it.pos[1] + it.rect[3] }))
    const labs = arrows.filter(a => a.it.labels[0]).map(a => {
      const L = a.it.labels[0], { p } = polylineAt(a.pts, L.t), w = textW(L.text, 16) + 8
      return { a, L, r: { l: p.x - w / 2, r: p.x + w / 2, t: p.y - LH / 2, b: p.y + LH / 2 } }
    })
    for (const x of labs) {
      for (const o of KNOWN.has(`${name}|${x.L.text}`) ? [] : arrows.filter(o => o !== x.a)) for (let j = 1; j < o.pts.length; j++) {
        const s = { l: Math.min(o.pts[j].x, o.pts[j - 1].x) - 1, r: Math.max(o.pts[j].x, o.pts[j - 1].x) + 1, t: Math.min(o.pts[j].y, o.pts[j - 1].y) - 1, b: Math.max(o.pts[j].y, o.pts[j - 1].y) + 1 }
        assert.ok(!meet(x.r, s), `${name}: 「${x.L.text}」 밑으로 남의 선`)
      }
      assert.ok(!boxes.some(b => meet(x.r, b)), `${name}: 「${x.L.text}」가 상자에 걸침`)
      assert.ok(!labs.some(y => y !== x && meet(x.r, y.r)), `${name}: 「${x.L.text}」가 다른 라벨과 겹침`)
    }
  }
})
