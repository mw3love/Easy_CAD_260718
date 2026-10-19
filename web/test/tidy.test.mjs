// node --test web/test — 「정리해 줘」 ② 레고형 정리정돈 자리 계산(§8 항목61, `src/next/tidy.js`)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { TIDY, TIDY_RE, clearSpot, packUnits, tidyLayout } from '../src/next/tidy.js'

const overlap = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h

test('정리정돈 말 — 묶기·정돈은 잡고, 「정리해 줘」(문서)는 서버가 가름', () => {
  for (const q of ['주제별로 정돈해 줘', '비슷한 것끼리 묶어 줘', '이거 그룹으로 모아 줘', '분류해 봐', '종류별로']) assert.ok(TIDY_RE.test(q), q)
  for (const q of ['정리해 줘', '송신기 출력 몇이야', '보고서로 만들어 줘']) assert.ok(!TIDY_RE.test(q), q)
})

test('프레임 안 — 크기 그대로 줄 맞춤, 폭 넘으면 줄바꿈, 겹치지 않음', () => {
  const units = [{ w: 340, h: 120 }, { w: 340, h: 80 }, { w: 200, h: 60 }, { w: 340, h: 200 }]
  const p = packUnits(units)
  const boxes = units.map((u, i) => ({ ...p.at[i], w: u.w, h: u.h }))
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) assert.ok(!overlap(boxes[i], boxes[j]), `${i}-${j}`)
  assert.ok(boxes.every(b => b.x + b.w <= p.w + 1e-9 && b.y + b.h <= p.h + 1e-9))
  assert.equal(p.at[0].x, 0); assert.equal(p.at[0].y, 0)
  assert.ok(new Set(p.at.map(a => a.y)).size >= 2)   // 한 줄에 다 안 들어감 = 줄바꿈
  assert.equal(packUnits([{ w: 50, h: 50 }], 300).w, 300)   // 설명 줄이 넓으면 그 폭
})

test('바둑판 — 원래 자리 왼쪽 위에서, 묶음 수에 따라 1·2·3열, 프레임끼리 안 겹침, 조각은 프레임 안', () => {
  const sec = n => Array.from({ length: n }, (_, i) => ({ units: [{ w: 300, h: 100 + i * 20 }, { w: 120, h: 60 }], noteW: 180, noteH: 20 }))
  for (const [n, cols] of [[1, 1], [3, 2], [4, 2], [5, 3], [7, 3]]) {
    const L = tidyLayout(sec(n), { x: 100, y: 50 })
    assert.equal(L.frames[0].x, 100); assert.equal(L.frames[0].y, 50)
    assert.equal(new Set(L.frames.map(f => f.x)).size, cols, `n=${n}`)
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) assert.ok(!overlap(L.frames[i], L.frames[j]))
    L.frames.forEach((f, i) => sec(n)[i].units.forEach((u, k) => {
      const x = f.inner.x + f.at[k].x, y = f.inner.y + f.at[k].y
      assert.ok(x >= f.x + TIDY.PAD - 1e-9 && y >= f.note.y + 20 && x + u.w <= f.x + f.w + 1e-9 && y + u.h <= f.y + f.h + 1e-9)   // 설명 줄 아래, 틀 안
    }))
    assert.ok(L.frames.every(f => f.x + f.w <= 100 + L.w + 1e-9 && f.y + f.h <= 50 + L.h + 1e-9))
  }
})

test('겹치면 아래로 비킴 — 안 겹치면 제자리', () => {
  assert.deepEqual(clearSpot({ x: 0, y: 0 }, 500, 300, [{ x: 600, y: 0, w: 100, h: 100 }]), { x: 0, y: 0 })
  const at = clearSpot({ x: 0, y: 0 }, 500, 300, [{ x: 100, y: 100, w: 100, h: 100 }, { x: 0, y: 260, w: 50, h: 300 }])
  assert.equal(at.x, 0); assert.ok(at.y >= 560)
})
