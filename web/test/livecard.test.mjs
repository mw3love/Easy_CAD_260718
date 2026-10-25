// 움직이는 카드 틀(§8 항목66 4단계) — 카드 HTML 맨 앞에 우리 머리, 크게 보기 페이지엔 스크립트 없음, 크기 상한
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { LIVE_CSP, LIVE_MAX, STATIC_CSP, bigPage, isLive, liveFits, liveSrc, staticSrc } from '../src/next/livecard.js'

const card = '<!doctype html><html><head><title>카드</title><script>x()</script></head><body><input type="range"></body></html>'

test('틀 = 우리 doctype·CSP가 맨 앞, 카드의 doctype은 뗌', () => {
  const s = liveSrc(card)
  assert.ok(s.startsWith(`<!doctype html><meta http-equiv="Content-Security-Policy" content="${LIVE_CSP}">`))
  assert.equal(s.match(/<!doctype/gi).length, 1)
  assert.ok(s.indexOf('Content-Security-Policy') < s.indexOf('x()'))   // 카드의 첫 스크립트보다 CSP가 먼저
  assert.match(s, /dispatchEvent\(new Event\('resize'\)\)/)             // 처음 innerWidth 0 막기
  assert.equal(liveSrc('<!-- 주석 -->\n<!DOCTYPE html><p>a</p>').match(/<!doctype/gi).length, 1)
})

test('CSP — 인터넷 금지(움직이는 카드), 스크립트 금지(크게 보기)', () => {
  assert.match(LIVE_CSP, /default-src 'none'/)
  assert.doesNotMatch(LIVE_CSP, /https?:|\*/)
  assert.doesNotMatch(STATIC_CSP, /script-src/)          // default-src 'none'이 스크립트도 막음
  assert.ok(staticSrc(card).startsWith(`<!doctype html><meta http-equiv="Content-Security-Policy" content="${STATIC_CSP}">`))
})

test('크게 보기 — 움직이는 카드는 틀 안에서만 스크립트, 바깥 페이지엔 맨 글 스크립트 없음', () => {
  const it = { type: 'doc', live: true, html: card, title: '<b>이름</b> & "따옴"' }
  const p = bigPage(it)
  assert.match(p, /<iframe sandbox="allow-scripts" csp="[^"]+" srcdoc="/)
  assert.doesNotMatch(p.replace(/srcdoc="[^"]*"/, ''), /<script/)   // 틀 밖엔 스크립트가 없음
  assert.match(p, /<title>&lt;b&gt;이름&lt;\/b&gt; &amp; &quot;따옴&quot;<\/title>/)
  assert.doesNotMatch(p, /allow-same-origin/)
  assert.ok(bigPage({ type: 'doc', html: card }).startsWith(`<!doctype html><meta http-equiv="Content-Security-Policy" content="${STATIC_CSP}">`))   // 보통 문서 = 스크립트 끔
})

test('움직임 표시·크기 상한', () => {
  assert.equal(isLive({ type: 'doc', live: true }), true)
  assert.equal(isLive({ type: 'doc' }), false)
  assert.equal(isLive({ type: 'web', live: true }), false)
  assert.equal(liveFits({ type: 'doc', live: true, html: card }), true)
  assert.equal(liveFits({ type: 'doc', live: true, html: 'a'.repeat(LIVE_MAX + 1) }), false)
  assert.ok(bigPage({ type: 'doc', live: true, html: 'a'.repeat(LIVE_MAX + 1) }).includes(STATIC_CSP))   // 넘치면 스크립트 없이
})
