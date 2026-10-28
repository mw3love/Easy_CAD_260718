// 흐름 53 — 📽 발표 자료 장 말풍선(2026-10-28 사용자): 장(프레임) 우클릭 「AI 말풍선」 → 「숫자 칸으로」 = 그 장만 다시 지음(다른 장은 그대로)
// · 원래대로 ↔ 바꾼 것 · Ctrl+Z 한 번 · 손으로 고친 장은 바로 덮지 않고 「이 장에 적용」. 진짜 KAIROS는 안 부름.
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage } from './helpers.js'

const DECK = { title: '송신소 점검', sources: [], slides: [
  { title: '송신소 점검', layout: '표지', bullets: ['10월 27일'], notes: '' },
  { title: '점검 결과', layout: '글머리', bullets: ['안테나 정상', '2호기 교체 필요'], notes: '결과를 나눕니다.' },
  { title: '다음 할 일', layout: '마무리', bullets: ['2호기 교체'], notes: '' }] }
const NEW = { title: '점검 숫자', layout: '숫자', numbers: [{ value: '70%', label: '연료' }, { value: '8시간', label: '버팀' }], bullets: ['연료 70%'], notes: '숫자로 봅니다.' }

const pieces = (doc, fid) => doc.items.filter(it => it.slide_of === fid)
const texts = (doc, fid) => pieces(doc, fid).map(it => it.text || '').join('|')
async function openSlide(page, fr) {   // 그 장을 화면 왼쪽에 두고 프레임 모서리 우클릭 → 말풍선
  await setCam(page, { x: 120 - fr.pos[0] * 0.3, y: 200 - fr.pos[1] * 0.3, z: 0.3 })
  const c = await toPage(page, fr.pos[0], fr.pos[1]), p = { x: c.x + 2, y: c.y + 2 }   // 왼쪽 위 모서리 안쪽(테두리)
  await page.evaluate(() => window.__mb.ed.setSel([]))   // 만든 직후엔 장 전부가 골라져 있음
  await page.mouse.click(p.x, p.y); await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.getByText('AI 말풍선 (KAIROS)').click()
  return page.getByTestId('bubble')
}

test('장 말풍선 — 그 장만 다시 지음 · 원래대로 ↔ 바꾼 것 · Ctrl+Z 한 번 · 손으로 고친 장은 「이 장에 적용」', async ({ page }) => {
  const seen = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {} } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); seen.push(b)
    return r.fulfill({ json: { kind: 'bubble', content: '숫자 칸으로 바꿨어요.', edit: { ...NEW, title: b.item.slide.title === '점검 결과' ? NEW.title : '할 일 숫자' }, model: 'claude-sonnet-5-5', elapsed: 6 } }) })
  await openBoard(page, boardName('slidebub'), { chat: true }); await setCam(page, { x: 200, y: 100, z: 0.15 })
  await page.evaluate(d => window.__mb.ed.slidesBoard(d), DECK)
  let doc = await liveDoc(page)
  const [f1, f2, f3] = doc.items.filter(it => it.type === 'frame').sort((a, b) => a.no - b.no)
  expect(f2.slide).toMatchObject({ title: '점검 결과', layout: '글머리' })
  const keep1 = JSON.stringify(pieces(doc, f1.uid)), keep3 = JSON.stringify(pieces(doc, f3.uid))

  let bub = await openSlide(page, f2)
  await expect(bub.getByTestId('bubble-scope')).toHaveText('이 장을 보고 고쳐요')
  await bub.getByTestId('bubble-input').fill('숫자 칸으로'); await bub.getByTestId('bubble-input').press('Enter')
  await expect(bub.getByTestId('bubble-a')).toContainText('숫자 칸으로 바꿨어요.')
  expect(seen[0].item).toMatchObject({ type: 'frame', edit: 'slide', deck: '송신소 점검', slide: { title: '점검 결과' } })
  doc = await liveDoc(page)
  expect(texts(doc, f2.uid)).toContain('70%'); expect(texts(doc, f2.uid)).not.toContain('안테나 정상')
  expect(doc.items.find(it => it.uid === f2.uid)).toMatchObject({ name: '2. 점검 숫자', slide: { layout: '숫자' } })
  expect(JSON.stringify(pieces(doc, f1.uid))).toBe(keep1); expect(JSON.stringify(pieces(doc, f3.uid))).toBe(keep3)   // 다른 장은 그대로
  expect(pieces(doc, f2.uid).find(it => it.type === 'memo').lines[1].t).toBe('숫자로 봅니다.')                        // 발표자 메모도

  await bub.getByTestId('bubble-flip').click()                                                  // 원래대로
  await expect.poll(async () => texts(await liveDoc(page), f2.uid)).toContain('안테나 정상')
  await bub.getByTestId('bubble-flip').click()                                                  // 바꾼 것으로
  await expect.poll(async () => texts(await liveDoc(page), f2.uid)).toContain('70%')
  await bub.getByTestId('bubble-close').click()
  await page.keyboard.press('Control+z')                                                        // 한 번 = 원래 장
  await expect.poll(async () => texts(await liveDoc(page), f2.uid)).toContain('안테나 정상')

  // 손으로 고친 장(3장) — 답이 와도 바로 안 덮고 「이 장에 적용」
  const t3 = pieces(await liveDoc(page), f3.uid).find(it => it.text?.startsWith('→'))
  await page.evaluate(uid => window.__mb.ed.setFields(uid, { text: '→  손으로 고침' }, '손'), t3.uid)   // _id = 파일 uid
  await expect.poll(async () => texts(await liveDoc(page), f3.uid)).toContain('손으로 고침')
  bub = await openSlide(page, f3)
  await bub.getByTestId('bubble-input').fill('숫자 칸으로'); await bub.getByTestId('bubble-input').press('Enter')
  await expect(bub.getByTestId('bubble-apply')).toBeVisible()
  expect(texts(await liveDoc(page), f3.uid)).toContain('손으로 고침')                            // 아직 그대로
  await bub.getByTestId('bubble-apply').click()
  await expect.poll(async () => texts(await liveDoc(page), f3.uid)).toContain('70%')
  await expect(bub.getByTestId('bubble-flip')).toBeVisible()
})
