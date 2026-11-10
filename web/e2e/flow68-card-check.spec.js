// 흐름 68 — 움직이는 카드 검사(2026-11-08): 보이지 않는 칸에서 돌려 글자 잘림·겹침·오류·빈 화면을 잼(크레딧 없음).
// 움직이는 카드(약 45크레딧) = 문제가 있으면 한 번 자동으로 고치고 나아졌을 때만 바꿈 · 움직이는 장(수백 크레딧) = 알림 + 단추를 눌러야 고침.
import { test, expect } from '@playwright/test'
import { askChat, boardName, liveDoc, openBoard, setCam, toPage } from './helpers.js'
import { checkSource, problemLines, runCheck } from '../src/next/cardcheck.js'
import { LIVE_CSP, LIVE_H, LIVE_W } from '../src/next/livecard.js'

const page0 = body => `<!doctype html><html><body style="margin:0;font:20px sans-serif">${body}</body></html>`
const at = (x, y, t, more = '') => `<div style="position:absolute;left:${x}px;top:${y}px;${more}">${t}</div>`
const OK = page0(at(40, 40, '멀쩡한 글') + at(40, 120, '다른 글'))
const CLIPPED = page0(at(40, 40, '멀쩡한 글') + at(40, 462, '아래로 잘리는 글', 'font-size:40px'))
const stepCard = bad => page0(`<div id="s">첫 단계</div><script>window.mbStep=0;window.mbSteps=3;
  window.mbNext=function(){if(window.mbStep>=2)return false;window.mbStep++;if(window.mbStep===2&&${bad}){var d=document.createElement('div');d.style.cssText='position:absolute;left:40px;top:865px;font-size:50px';d.textContent='마지막에 잘림';document.body.appendChild(d)}return true};window.mbPrev=function(){return false}</script>`)

async function check(page, html, { motion = false, w = LIVE_W, h = LIVE_H } = {}) {
  const token = 77, src = checkSource(html, token, motion)
  const r = await page.evaluate(`(${runCheck})(${JSON.stringify(src)},${w},${h},${token},${JSON.stringify(LIVE_CSP)},45000)`)
  return r.problems
}

test('카드 검사 — 문제는 잡고 멀쩡한 건 그냥 둠', async ({ page }) => {
  test.setTimeout(60_000)
  await page.goto('about:blank')
  const cases = [
    ['멀쩡함', OK, []],
    ['칸 아래로 잘림', CLIPPED, ['clip']],
    ['상자에 잘림', page0(`<div style="position:absolute;left:40px;top:40px;width:100px;height:30px;overflow:hidden;white-space:nowrap">상자보다 훨씬 긴 글자가 잘립니다</div>`), ['clip']],
    ['SVG 글 잘림', page0(`<svg width="300" height="100" style="position:absolute;left:0;top:0"><text x="150" y="50" font-size="30">오른쪽으로 많이 넘치는 글자</text></svg>`), ['clip']],
    ['글자 겹침', page0(at(40, 40, '첫째 글입니다') + at(50, 44, '둘째 글입니다')), ['overlap']],
    ['스크립트 오류', page0(`멀쩡<script>throw new Error('펑')</script>`), ['error']],
    ['빈 화면', page0(''), ['empty']],
    ['칸 밖에 통째로 있는 글(아직 안 나옴)', page0(at(40, 40, '보이는 글') + at(-500, 40, '대기 중인 글')), []],
    ['투명한 글(아직 안 나옴)', page0(at(40, 40, '보이는 글') + at(44, 42, '투명한 글', 'opacity:0')), []],
    ['같은 글 두 번(윤곽 효과)', page0(at(40, 40, '윤곽 글') + at(40, 40, '윤곽 글')), []],
    ['돌린 글은 겹침으로 안 침', page0(at(40, 60, '가로 글입니다') + at(60, 40, '돌린 글입니다', 'transform:rotate(90deg)')), []],
  ]
  for (const [name, html, want] of cases) expect((await check(page, html)).map(p => p.type), name).toEqual(want)
})

test('움직이는 장 — 뒤 단계에서 생긴 문제까지 재고 단계를 알려 줌', async ({ page }) => {
  test.setTimeout(60_000)
  await page.goto('about:blank')
  const box = { motion: true, w: 1600, h: 900 }
  expect(await check(page, stepCard(false), box)).toEqual([])
  const bad = await check(page, stepCard(true), box)
  expect(bad.map(p => [p.type, p.step])).toEqual([['clip', 2]])
  expect(problemLines(bad)[0]).toContain('3번째 단계')
  expect((await check(page, OK, box))[0].text).toContain('mbNext')                       // 단계 함수가 없는 장
})

async function setupLive(page, replies) {
  const sent = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { live: 'gpt-6.1-sol' } } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); sent.push(b); const html = replies[Math.min(sent.length - 1, replies.length - 1)]
    return r.fulfill({ json: { kind: 'live', content: '움직이는 카드 「시험」', title: '시험', html, model: 'gpt-6.1-sol', elapsed: 50 } }) })
  await openBoard(page, boardName('check'), { chat: true }); await setCam(page)
  await askChat(page, '직접 움직여 볼 수 있게 만들어 줘')
  await expect(page.getByTestId('answer-kind').last()).toHaveText('▶ 인터랙티브 HTML', { timeout: 20_000 })
  return sent
}
const shown = page => page.getByTestId('answer-live').locator('iframe').last().getAttribute('srcdoc')

test('움직이는 카드 — 멀쩡하면 다시 요청하지 않음', async ({ page }) => {
  const sent = await setupLive(page, [OK])
  await page.waitForTimeout(300)
  expect(sent.length).toBe(1); await expect(page.getByTestId('card-check')).toHaveCount(0)
})

test('움직이는 카드 — 잘리면 문제를 적어 한 번 고치고, 나아진 카드로 바꿈', async ({ page }) => {
  const fixed = OK.replace('멀쩡한 글', '고친 글')
  const sent = await setupLive(page, [CLIPPED, fixed])
  expect(sent.length).toBe(2)
  expect(sent[1]).toMatchObject({ kind: 'live', prev_html: CLIPPED, prev_kind: 'live' })
  expect(sent[1].messages.at(-1).content).toContain('글자가 잘림: 「아래로 잘리는 글」')
  await expect(page.getByTestId('card-check')).toContainText('1곳을 찾아 자동으로 고쳤어요')
  expect(await shown(page)).toContain('고친 글')
})

test('움직이는 카드 — 고쳐도 나아지지 않으면 처음 카드 + 알림, 또 고치지 않음', async ({ page }) => {
  const sent = await setupLive(page, [CLIPPED, CLIPPED.replace('멀쩡한 글', '더 나쁜 글')])
  expect(sent.length).toBe(2)
  await expect(page.getByTestId('card-check')).toContainText('확인이 필요해요')
  await expect(page.getByTestId('card-fix')).toHaveCount(0)                               // 고치기 단추는 비싼 장에만
  expect(await shown(page)).toContain('멀쩡한 글')
})

test('움직이는 장 — 잘리면 알리기만 하고, 단추를 눌러야 고침', async ({ page }) => {
  test.setTimeout(90_000)
  const seen = [], fixed = stepCard(false).replace('첫 단계', '고친 장')
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'm', motion: 'claude-opus-5-5' } } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return r.fulfill({ json: { kind: 'motion', content: '장 「송신소」을 움직이게 만들어 그 프레임에 덮었어요', title: '송신소', html: b.motion.fix_html ? fixed : stepCard(true), steps: 3, model: 'claude-opus-5-5', elapsed: 180, credits: 366 } }) })
  await openBoard(page, boardName('checkmo'), { chat: true }); await setCam(page, { x: 0, y: 0, z: 0.25 })
  await page.evaluate(d => window.__mb.ed.slidesBoard(d), { title: '전파', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'] }, { title: '송신소', layout: '글머리', bullets: ['만든다', '바꾼다', '쏜다'] }, { title: '끝', layout: '마무리', bullets: ['b'] }] })
  const doc = await liveDoc(page), fr = doc.items.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no)[1]
  await page.keyboard.press('Escape')
  const p = await toPage(page, fr.pos[0] + 6, fr.pos[1] + 6)
  await page.mouse.click(p.x, p.y); await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.getByRole('menuitem', { name: /이 장 움직이게/ }).click()
  const fix = page.getByTestId('card-fix')
  await expect(fix).toBeVisible({ timeout: 30_000 })
  await expect(page.getByTestId('card-check')).toContainText('마지막에 잘림')
  expect(seen.length).toBe(1)                                                             // 저절로 다시 부르지 않음(수백 크레딧)
  await expect(fix).toBeEnabled({ timeout: 30_000 }); await fix.click()
  await expect(page.getByTestId('card-check')).toContainText('잘린 곳을 고쳤어요', { timeout: 30_000 })
  expect(seen.length).toBe(2)
  expect(seen[1].motion.fix_html).toContain('마지막에 잘림')
  expect(seen[1].motion.problems[0]).toContain('글자가 잘림')
  const cards = (await liveDoc(page)).items.filter(it => it.type === 'doc' && it.motion)
  expect(cards.length).toBe(1); expect(cards[0].html).toContain('고친 장')               // 같은 프레임의 카드를 바꿈
  await expect(fix).toHaveCount(0)
})
