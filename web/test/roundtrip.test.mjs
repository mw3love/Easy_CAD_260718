// 데스크톱 문서 → 웹 → 다시 .ecad(§8 항목61 ④-1, 2026-10-19) — 웹이 열었다 저장해도 데스크톱 칸이 그대로(모르는 칸도 들고 다님).
// 반대쪽(웹 문서 → 데스크톱)은 tests/test_part58_roundtrip.py. 기준 문서 = tests/fixtures/all_types.ecad(데스크톱 모든 종류, tools/make_all_types_ecad.py).
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fromEcad, toEcad } from '../src/next/model.js'

const doc = JSON.parse(readFileSync(new URL('../../tests/fixtures/all_types.ecad', import.meta.url), 'utf-8'))

test('데스크톱 모든 종류 → 웹 열기·저장 → 칸 그대로(웹이 붙이는 uid만 더해짐)', () => {
  const back = toEcad(fromEcad(doc))
  assert.equal(back.items.length, doc.items.length)
  const bad = []
  doc.items.forEach((a, i) => {
    const b = back.items[i]
    for (const [k, v] of Object.entries(a)) if (JSON.stringify(b[k]) !== JSON.stringify(v)) bad.push([a.type, k, v, b[k]])
    for (const k of Object.keys(b)) if (!(k in a) && k !== 'uid') bad.push([a.type, '+' + k, b[k]])
  })
  assert.deepEqual(bad, [])
  for (const k of Object.keys(doc).filter(k => k !== 'items')) assert.deepEqual(back[k], doc[k], k)
})
