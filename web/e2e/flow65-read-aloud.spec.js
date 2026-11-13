// 흐름 65 — 발표 「읽어 주기」(계획 ⑥, 2026-11-08): 발표자 메모가 있는 장이 있으면 막대에 🔊 · N = 켜고 끄기 ·
// 켜면 지금 장 메모를 서버(`/api/tts`, 가짜)에 → 받은 소리를 틀고, 다음 장 소리는 미리 받음 · 장을 넘기면 그 장 소리. 진짜 KAIROS 음성은 손 확인.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, morePick } from './helpers.js'

// 0.05초 무음 WAV
const WAV = (() => { const n = 1200, b = Buffer.alloc(44 + n * 2); b.write('RIFF', 0); b.writeUInt32LE(36 + n * 2, 4); b.write('WAVEfmt ', 8); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22)
  b.writeUInt32LE(24000, 24); b.writeUInt32LE(48000, 28); b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34); b.write('data', 36); b.writeUInt32LE(n * 2, 40); return b })()

test('읽어 주기 — N으로 켜면 지금 장 메모를 읽고 다음 장은 미리 받음 · 넘기면 그 장 소리', async ({ page }) => {
  const asked = []
  await page.route('**/api/tts', r => { const b = r.request().postDataJSON(); asked.push(b.text); return r.fulfill({ json: { url: `/api/tts/x/${String(asked.length).padStart(16, '0')}.wav`, cached: false } }) })
  await page.route('**/api/tts/x/**', r => r.fulfill({ body: WAV, contentType: 'audio/wav' }))
  await page.addInitScript(() => { const play = HTMLMediaElement.prototype.play; window.__played = []
    HTMLMediaElement.prototype.play = function () { window.__played.push(this.src.split('/').pop()); return play.call(this).catch(() => {}) } })
  await openBoard(page, boardName('voice')); await setCam(page, { x: 0, y: 0, z: 0.25 })
  await page.evaluate(d => window.__mb.ed.slidesBoard(d), { title: 't', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'], notes: '오늘은 송신소 이야기입니다.' },
    { title: '송신소', layout: '글머리', bullets: ['b'], notes: '송신소는 마지막 관문입니다.' }, { title: '끝', layout: '마무리', bullets: ['c'] }] })
  await page.keyboard.press('Escape')
  await morePick(page, '발표')
  const btn = page.getByTestId('present-voice')
  await expect(btn).toHaveAttribute('aria-pressed', 'false')
  expect(asked).toEqual([])                                                                       // 끈 채로는 서버를 안 부름(크레딧)
  await page.keyboard.press('n'); await expect(btn).toHaveAttribute('aria-pressed', 'true')
  await expect.poll(() => asked).toEqual(['오늘은 송신소 이야기입니다.', '송신소는 마지막 관문입니다.'])   // 지금 장 + 다음 장 미리
  await expect.poll(() => page.evaluate(() => window.__played)).toEqual(['0000000000000001.wav'])
  await page.keyboard.press('ArrowRight')
  await expect.poll(() => page.evaluate(() => window.__played)).toEqual(['0000000000000001.wav', '0000000000000002.wav'])   // 미리 받은 소리(다시 안 물음)
  expect(asked).toHaveLength(2)
  await page.keyboard.press('ArrowRight'); await page.waitForTimeout(300)
  expect(await page.evaluate(() => window.__played)).toHaveLength(2)                                // 메모 없는 장 = 조용
  await page.keyboard.press('n'); await expect(btn).toHaveAttribute('aria-pressed', 'false')
})

test('발표자 메모가 하나도 없으면 읽어 주기 단추 없음', async ({ page }) => {
  await openBoard(page, boardName('voice0')); await setCam(page, { x: 0, y: 0, z: 0.25 })
  await page.evaluate(d => window.__mb.ed.slidesBoard(d), { title: 't', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'] }, { title: '끝', layout: '마무리', bullets: ['c'] }] })
  await page.keyboard.press('Escape')
  await morePick(page, '발표')
  await expect(page.getByTestId('presenter')).toBeVisible()
  await expect(page.getByTestId('present-voice')).toHaveCount(0)
})
