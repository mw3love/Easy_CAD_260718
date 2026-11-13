// 흐름 64 — 「이 장 움직이게」(계획 ⑤, 2026-11-08): 장 프레임 우클릭 → 서버(가짜)가 모션 HTML → 그 프레임을 꼭 덮는 움직이는 장 카드(Ctrl+Z 한 번)
// → 발표에서 → = 먼저 장 안 단계(카드가 mbNext로 「더 있음」을 답하는 동안 같은 장), 끝나면 다음 프레임 · ← = 장 안 이전 단계부터 · PDF·그림 내보내기엔 카드를 안 그림.
// 진짜 Opus는 안 부름(장 하나 약 370크레딧 — 진짜는 손 확인, docs/history 2026-11).
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage, morePick } from './helpers.js'

// 세 단계 카드 — 지금 단계를 글로 보임(바깥에서 확인용)
const CARD = `<!doctype html><html><body style="margin:0"><h1 id="s">단계 1</h1><script>
window.mbSteps=3;window.mbStep=0;var show=function(){document.getElementById('s').textContent='단계 '+(window.mbStep+1)};
window.mbNext=function(){if(window.mbStep>=window.mbSteps-1)return false;window.mbStep++;show();return true};
window.mbPrev=function(){if(window.mbStep<=0)return false;window.mbStep--;show();return true};</script></body></html>`

test('이 장 움직이게 → 프레임을 덮는 카드 → 발표 → = 장 안 단계 먼저, 끝나면 다음 장 · ← = 이전 단계', async ({ page }) => {
  const name = boardName('motion'), seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'm', motion: 'claude-opus-5-5' } } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return r.fulfill({ json: { kind: 'motion', content: '장 「송신소」을 움직이게 만들어 그 프레임에 덮었어요', title: '송신소', html: CARD, steps: 3, model: 'claude-opus-5-5', elapsed: 180, credits: 366 } }) })
  await openBoard(page, name, { chat: true }); await setCam(page, { x: 0, y: 0, z: 0.25 })
  await page.evaluate(d => window.__mb.ed.slidesBoard(d), { title: '전파', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'] },
    { title: '송신소', layout: '글머리', bullets: ['만든다', '바꾼다', '쏜다'], notes: '마지막 관문' }, { title: '끝', layout: '마무리', bullets: ['b'] }] })
  let doc = await liveDoc(page)
  const frs = doc.items.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no), fr = frs[1], id = frs.map(f => f.uid)
  await page.keyboard.press('Escape')
  const p = await toPage(page, fr.pos[0] + 6, fr.pos[1] + 6)                                   // 프레임 테두리 안쪽 모서리 = 프레임만 고름
  await page.mouse.click(p.x, p.y); await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.getByRole('menuitem', { name: /이 장 움직이게/ }).click()
  await page.getByTestId('cost-ask-ok').click()                                             // 비싼 일 = 확인 창 먼저(2026-11-10 6단계)
  await expect(page.getByTestId('answer-kind').last()).toHaveText('▶ 움직이는 장')
  expect(seen[0].kind).toBe('motion')
  expect(seen[0].motion).toMatchObject({ slide: { title: '송신소', bullets: ['만든다', '바꾼다', '쏜다'], notes: '마지막 관문' }, w: Math.round(fr.rect[2]), h: Math.round(fr.rect[3]), image: '' })   // 글 장 = 참고 그림 없음

  doc = await liveDoc(page)
  const card = doc.items.find(it => it.type === 'doc' && it.motion)
  expect(card.live).toBe(true); expect(card.pos).toEqual(fr.pos); expect(card.rect).toEqual(fr.rect)   // 프레임을 꼭 덮음
  await page.keyboard.press('Control+z')
  await expect.poll(async () => (await liveDoc(page)).items.some(it => it.motion)).toBe(false)        // Ctrl+Z 한 번
  await page.keyboard.press('Control+y')
  await expect.poll(async () => (await liveDoc(page)).items.some(it => it.motion)).toBe(true)

  await page.keyboard.press('Escape')                                                                 // 고른 프레임이 있으면 발표가 그 장부터 — 처음부터 보려고 풂
  await morePick(page, '발표')
  const pr = page.getByTestId('presenter'), step = page.frameLocator('[data-testid="presenter"] iframe[data-motion]').locator('#s')
  await expect(pr).toHaveAttribute('data-cur', id[0])
  await page.keyboard.press('ArrowRight'); await expect(pr).toHaveAttribute('data-cur', id[1])
  await expect(step).toHaveText('단계 1')
  await page.keyboard.press('ArrowRight'); await expect(step).toHaveText('단계 2'); await expect(pr).toHaveAttribute('data-cur', id[1])   // 같은 장
  await page.keyboard.press('ArrowRight'); await expect(step).toHaveText('단계 3'); await expect(pr).toHaveAttribute('data-cur', id[1])
  await page.keyboard.press('ArrowLeft'); await expect(step).toHaveText('단계 2'); await expect(pr).toHaveAttribute('data-cur', id[1])    // ← = 이전 단계
  await page.keyboard.press('ArrowRight'); await expect(step).toHaveText('단계 3')
  await page.keyboard.press('ArrowRight'); await expect(pr).toHaveAttribute('data-cur', id[2])        // 끝 단계 다음 = 다음 장
})

test('움직이는 장 카드는 내보내기에 안 그려짐(원래 장이 찍힘) · 칠판 위엔 움직이는 카드', async ({ page }) => {
  await openBoard(page, boardName('motionexp')); await setCam(page, { x: 0, y: 0, z: 0.25 })
  await page.evaluate(d => window.__mb.ed.slidesBoard(d), { title: 't', sources: [], slides: [{ title: '표지', layout: '표지', bullets: ['a'] }, { title: '장 제목', layout: '글머리', bullets: ['x'] }] })
  await page.evaluate(html => { const ed = window.__mb.ed; ed.motionPlace(ed.frameIds()[1], { html, title: '장 제목' }) }, CARD)
  await expect(page.locator('iframe[data-motion]')).toHaveCount(1)                                 // 칠판 위엔 움직이는 카드
  const pages = await page.evaluate(async () => (await window.__mb.ed.exportPages({ format: 'svg', scope: 'frames', selection: false, page: 'frame', margin: 0, preview: true })).pages.map(p => p.svg))
  expect(pages).toHaveLength(2); expect(pages[1]).not.toContain('<foreignObject')                   // 내보내기 = 카드 없이 원래 장
  expect(pages[1]).not.toContain('움직이는 장'); expect(pages[1]).toContain('장 제목')
})
