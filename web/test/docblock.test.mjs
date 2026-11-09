import { test } from 'node:test'
import assert from 'node:assert/strict'
import { findBlock, blockOf, spliceBlock, cleanEdited, handEditable } from '../src/next/docblock.js'

const DOC = '<html><body><main><h1 data-block="b1" data-kind="text">제목</h1><div data-block="b2" data-kind="box"><p>안 <b>굵게</b></p><img src="x.png"><div>속</div></div><p data-block="b3">끝</p></main></body></html>'

test('블록 찾기 — 안쪽 같은 태그·빈 태그를 건너 짝을 맞춤', () => {
  assert.equal(blockOf(DOC, 'b2'), '<div data-block="b2" data-kind="box"><p>안 <b>굵게</b></p><img src="x.png"><div>속</div></div>')
  assert.equal(blockOf(DOC, 'b3'), '<p data-block="b3">끝</p>')
  assert.equal(findBlock(DOC, 'b9'), null)
  assert.equal(findBlock(DOC, 'b1')[0], DOC.indexOf('<h1'))
})

test('바꿔 끼우기 — 그 블록만, 나머지 글은 한 글자도 그대로', () => {
  const out = spliceBlock(DOC, 'b3', '<p data-block="b3">고친 끝</p>')
  assert.equal(out, DOC.replace('<p data-block="b3">끝</p>', '<p data-block="b3">고친 끝</p>'))
  assert.throws(() => spliceBlock(DOC, 'b7', 'x'))
})

test('손으로 고친 표시 떼기 · 고칠 수 있는 종류', () => {
  assert.equal(cleanEdited('<p data-block="b3" class="mb-sel mb-edit" contenteditable="true" spellcheck="false">새 글</p>'), '<p data-block="b3">새 글</p>')
  assert.equal(cleanEdited('<div data-block="b2" class="note mb-edit" contenteditable="true">x</div>'), '<div data-block="b2" class="note">x</div>')
  assert.ok(handEditable('text') && handEditable('table') && handEditable('box') && handEditable(''))
  assert.ok(!handEditable('chart') && !handEditable('image'))
})
