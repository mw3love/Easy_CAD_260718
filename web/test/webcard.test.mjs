// 웹 카드(§8 항목61 4-b ①', 2026-10-18) — 주소 알아보기·유튜브 재생 주소·카드 크기(순수 계산)
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { embedUrl, normalizeUrl, webCardFields, WEB_HEAD } from '../src/next/webcard.js'

test('붙여넣은 글이 주소 하나일 때만 웹 카드', () => {
  assert.equal(normalizeUrl(' https://ko.wikipedia.org/wiki/KBS \n'), 'https://ko.wikipedia.org/wiki/KBS')
  assert.equal(normalizeUrl('www.kbs.co.kr'), 'https://www.kbs.co.kr/')
  assert.equal(normalizeUrl('회의록 https://a.com'), null)        // 글 속 주소는 그냥 글
  assert.equal(normalizeUrl('hello'), null)
  assert.equal(normalizeUrl('https://nodot'), null)
  assert.equal(normalizeUrl(''), null)
})

test('유튜브·비메오 → 칸 안에 넣는 재생 주소(시작 시각 유지)', () => {
  const E = 'https://www.youtube.com/embed/dQw4w9WgXcQ'
  assert.equal(embedUrl('https://www.youtube.com/watch?v=dQw4w9WgXcQ'), E)
  assert.equal(embedUrl('https://youtu.be/dQw4w9WgXcQ?t=43'), E + '?start=43')
  assert.equal(embedUrl('https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=1m5s'), E + '?start=65')
  assert.equal(embedUrl('https://www.youtube.com/shorts/dQw4w9WgXcQ'), E)
  assert.equal(embedUrl('https://vimeo.com/76979871'), 'https://player.vimeo.com/video/76979871')
  assert.equal(embedUrl('https://www.youtube.com/'), '')
  assert.equal(embedUrl('https://news.naver.com'), '')
})

test('카드 크기 — 영상 16:9, 페이지 넓게, 막힌 사이트는 그림 카드', () => {
  const v = webCardFields({ url: 'u', embed: 'e', frameable: true, title: 't', thumb: '' })
  assert.deepEqual(v.rect, [0, 0, 480, WEB_HEAD + 270]); assert.equal(v.embed, 'e'); assert.equal(v.thumb, undefined)
  assert.deepEqual(webCardFields({ url: 'u', frameable: true }).rect, [0, 0, 640, WEB_HEAD + 420])
  const b = webCardFields({ url: 'u', frameable: false, thumb: 'data:x' })
  assert.deepEqual(b.rect, [0, 0, 320, WEB_HEAD + 168]); assert.equal(b.frameable, false)
  assert.deepEqual(webCardFields({ url: 'u', frameable: false }).rect, [0, 0, 320, WEB_HEAD])   // 그림도 없으면 띠만
})
