// 흐름 50 — 📽 발표 자료(§8 항목69, 2026-10-28 사용자: NotebookLM 슬라이드처럼 — 칠판 자료로 프레임 여러 장, 바로 발표).
// 「+ › 발표 자료」 + 주제 = 질문지(고른 메모를 재료로 붙잡음) → 장 계획(× 빼기) → 「이대로 만들기」 = 16:9 프레임 N장 + 발표자 메모 + 출처 장. 진짜 KAIROS는 안 부름.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc } from './helpers.js'

const PLAN = { title: '송신소 점검 공유', slides: [{ title: '표지', point: '', source: 'board' }, { title: '점검 결과', point: '', source: 'board' }, { title: '빼 볼 장', point: '', source: 'ai' }, { title: '연료 기준', point: '', source: 'web', query: '발전기 연료 기준' }, { title: '다음 할 일', point: '', source: 'board' }] }
const DECK = { title: '송신소 점검 공유', sources: [{ n: 1, title: '연료 관리 지침', url: 'https://example.com/a' }],
  slides: [{ title: '송신소 점검 공유', bullets: ['10월 27일 점검'], notes: '어제 점검 내용을 나눕니다.' }, { title: '점검 결과', bullets: ['안테나 정상', '2호기 교체 필요'], notes: '핵심은 2호기입니다.' },
    { title: '연료 기준', bullets: ['8시간분 이상 [1]'], notes: '퍼센트가 아니라 시간으로 봅니다.' }, { title: '다음 할 일', bullets: ['2호기 교체 일정', '연료 보충'], notes: '세 가지를 정리합니다.' }] }

test('발표 자료 — 질문지 → 장 계획(× 빼기) → 프레임 4장 + 출처 장 · 발표자 메모 · 고른 메모가 재료', async ({ page }) => {
  const name = boardName('slides'), seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'claude-sonnet-5-5' } } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return r.fulfill({ json: b.slides?.step === 'plan' ? { kind: 'slides', plan: PLAN, estimate: { credits: [30, 50], seconds: [25, 50] }, model: 'claude-sonnet-5-5', elapsed: 4.6 }
      : { kind: 'slides', deck: DECK, model: 'claude-sonnet-5-5', elapsed: 22.4, missing: [] } }) })
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.evaluate(t => { const dt = new DataTransfer(); dt.setData('text/plain', t); window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })) }, '# 송신소 점검\n- 안테나 정상\n- 2호기 교체 필요')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  await expect(page.getByTestId('sel-chip')).toHaveText('1개 선택됨')
  await page.getByTestId('plus').click(); await page.getByRole('menuitemradio', { name: /발표 자료/ }).click()
  const box = page.getByPlaceholder('무엇을 발표할까요', { exact: false })
  await box.fill('점검 결과 팀 공유'); await box.press('Enter')
  const ask = page.getByTestId('deep-ask'); await expect(ask).toContainText('발표 자료를 짜기 전에')
  await expect(ask).toContainText('칠판에서 고른 것 1개를 재료로')
  await ask.locator('[data-q="장 수"] [data-v="5장"]').click()
  await page.getByTestId('deep-plan-go').click()
  await expect(page.getByTestId('slides-row')).toHaveCount(5)
  expect(seen[0].kind).toBe('slides'); expect(seen[0].slides).toMatchObject({ step: 'plan', topic: '점검 결과 팀 공유', brief: { '장 수': '5장', 재료: '알아서' } })
  expect(seen[0].slides.material).toContain('안테나 정상')                                   // 고른 메모 = 재료
  await page.getByRole('button', { name: '「빼 볼 장」 빼기' }).click()
  await page.getByTestId('slides-build').click()
  await expect(page.getByTestId('slides-show')).toContainText('프레임 5장')
  expect(seen[1].slides.step).toBe('build'); expect(seen[1].slides.plan.slides.map(s => s.title)).not.toContain('빼 볼 장')
  const its = (await liveDoc(page)).items, frames = its.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no)
  expect(frames.map(f => f.name)).toEqual(['1. 송신소 점검 공유', '2. 점검 결과', '3. 연료 기준', '4. 다음 할 일', '5. 출처'])
  expect(frames.every(f => f.rect[2] / f.rect[3] === 16 / 9)).toBe(true)
  expect(its.filter(it => it.type === 'memo' && it.lines[0]?.t?.startsWith('발표자 메모'))).toHaveLength(4)
  expect(its.some(it => it.type === 'text' && it.text.includes('•  2호기 교체 필요'))).toBe(true)
  expect(its.some(it => it.type === 'text' && it.text.includes('[1] 연료 관리 지침'))).toBe(true)
  await page.keyboard.press('Control+z')
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'frame').length).toBe(0)   // 한 번에 되돌림
})

test('발표 자료 2단계 — 장 모양(표지 띠·숫자 칸·단계 줄·한마디)을 칠판 물건으로 · 모양에 쓸 것이 없으면 글머리', async ({ page }) => {
  const name = boardName('slides2')
  const deck = { title: '점검', sources: [], slides: [
    { title: '점검 공유', layout: '표지', bullets: ['10월 27일'], notes: '' },
    { title: '기억할 숫자', layout: '숫자', bullets: ['연료 70%'], numbers: [{ value: '70%', label: '발전기 연료' }, { value: '2대', label: '교체 대상' }], notes: '' },
    { title: '교체 순서', layout: '단계', bullets: ['전환'], steps: ['예비기 전환', '2호기 분리', '설치'], notes: '' },
    { title: '한 문장', layout: '한마디', bullets: ['근거'], message: '2호기는 교체가 필요하다', notes: '' }] }
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'm' } } }))
  await openBoard(page, name); await setCam(page)
  const r = await page.evaluate(d => window.__mb.ed.slidesBoard(d), deck)
  expect(r.frames).toBe(4)
  const its = (await liveDoc(page)).items, texts = its.filter(it => it.type === 'text').map(it => it.text), rects = its.filter(it => it.type === 'rect')
  expect(texts).toEqual(expect.arrayContaining(['70%', '발전기 연료', '2대', '1', '2', '3', '예비기 전환', '2호기는 교체가 필요하다']))
  expect(rects).toHaveLength(2 + 3 + 2 + 3 + 1)                                           // 표지 띠·줄 + 제목 줄 3 + 숫자 칸 2 + 단계 줄 3 + 한마디 줄
  expect(rects.every(x => x.style === 0)).toBe(true)
})

test('발표 자료 3단계 — 고른 자료 우클릭 「발표 자료 만들기」 = 그 자료로 질문지 · 표지 그림이 표지 오른쪽 위에', async ({ page }) => {
  const name = boardName('slides3'), seen = []
  const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII='
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { slides: 'm' } } }))
  await page.route('**/api/img/**', r => r.fulfill({ body: Buffer.from(PNG, 'base64'), contentType: 'image/png' }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return r.fulfill({ json: b.slides?.step === 'plan' ? { kind: 'slides', plan: { title: '점검', slides: [{ title: '표지', source: 'board' }, { title: '결과', source: 'board' }] }, estimate: { credits: [20, 30], seconds: [20, 30] }, model: 'm', elapsed: 1 }
      : { kind: 'slides', deck: { title: '점검', sources: [], cover: { img: `/api/img/${name}/1_cover.png`, w: 4, h: 3 }, slides: [{ title: '점검', layout: '표지', bullets: ['10월'], notes: '' }, { title: '결과', layout: '글머리', bullets: ['정상'], notes: '' }] }, model: 'm', elapsed: 1 } }) })
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.evaluate(t => { const dt = new DataTransfer(); dt.setData('text/plain', t); window.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })) }, '# 송신소 점검\n- 안테나 정상')
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(1)
  const b = await page.locator('svg text', { hasText: '안테나 정상' }).first().boundingBox()
  await page.mouse.click(b.x + 4, b.y + b.height / 2, { button: 'right' })
  await page.getByText('발표 자료 만들기 (KAIROS)').click()
  const ask = page.getByTestId('deep-ask'); await expect(ask).toContainText('「고른 자료로 발표 자료」')
  await expect(ask).toContainText('칠판에서 고른 것 1개를 재료로')
  await page.getByTestId('deep-plan-go').click(); await page.getByTestId('slides-build').click()
  await expect(page.getByTestId('slides-show')).toContainText('프레임 2장')
  expect(seen[0].slides.material).toContain('안테나 정상')
  const its = (await liveDoc(page)).items, cover = its.find(it => it.type === 'image'), f1 = its.find(it => it.type === 'frame' && it.no === Math.min(...its.filter(x => x.type === 'frame').map(x => x.no)))
  expect(cover?.data?.length).toBeGreaterThan(10)
  expect(cover.pos[0]).toBeGreaterThan(f1.pos[0] + f1.rect[2] / 2); expect(cover.pos[1]).toBeLessThan(f1.pos[1] + 100)   // 표지 오른쪽 위
})
