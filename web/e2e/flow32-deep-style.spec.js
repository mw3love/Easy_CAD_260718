// 흐름 32 — 딥모드 톤(§8 항목66 3-1, 2026-10-25 — 옛 디자인 묶음): 판(프레임)을 고르면 속성 카드 「톤」 → 신문으로 다시 지음(같은 프레임·번호·같은 자리, 겹침 0) →
// Ctrl+Z 한 번에 차분으로 → 숫자 타일 꼭지를 고르면 「꼭지」 줄 → 위아래로(그 꼭지만, 판에 기억) → 손으로 옮긴 뒤 잡지를 누르면 덮어쓰기 확인 → 덮어쓰기 → 새로고침해도 그대로.
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, liveDoc, dragScene, waitSaved, pickShape } from './helpers.js'
import { overlaps } from '../src/next/deep.js'

const PLAN = JSON.parse(readFileSync(new URL('../test/fixtures/deep_real_news.json', import.meta.url), 'utf-8'))
const box = it => ({ x: it.pos[0], y: it.pos[1], w: it.rect[2] * (it.scale || 1), h: it.rect[3] * (it.scale || 1) })
const root = d => d.items.find(it => it.type === 'frame' && it.deep_plan)
const noOverlap = d => overlaps(d.items.filter(it => !['frame', 'sarrow', 'arrow'].includes(it.type)).map(box)).length

test('톤 바꾸기 · 되돌리기 · 꼭지 모양 · 손으로 고친 뒤 확인', async ({ page }) => {
  const name = boardName('deepstyle')
  await openBoard(page, name)
  await page.evaluate(p => window.__mb.ed.deepBoard(p, { x: 0, y: 0 }), PLAN)
  await setCam(page, { x: 40, y: 40, z: 0.5 })
  let d = await liveDoc(page), f = root(d)
  const uid = f.uid, n0 = d.items.length
  const at = d => d.items.filter(it => it.deep_of === uid && it.deep_sec != null && !['sarrow', 'arrow'].includes(it.type)).map(it => [it.deep_sec, it.type, Math.round(it.pos[0]), Math.round(it.pos[1]), Math.round(it.rect[3])])
  const at0 = at(d)
  expect(f.deep_plan.style).toBe('calm')
  await expect(page.getByTestId('board').locator('rect[fill="#ffffff"][stroke="var(--mb-muted, #8a98a8)"]')).toHaveCount(1)   // 판 프레임 = 흰 종이(어두운 화면에서 투명 메모 제목이 묻혔음 — 2026-10-25 사용자)
  await page.evaluate(id => window.__mb.ed.setSel([id]), uid)
  const styles = page.getByTestId('deep-styles')
  await expect(styles.locator('[data-style]')).toHaveCount(4)
  await expect(styles.locator('[data-style="calm"]')).toHaveAttribute('aria-pressed', 'true')
  await expect(page.getByTestId('deep-variants')).toHaveCount(0)                   // 프레임만 = 꼭지 줄 없음

  await styles.locator('[data-style="news"]').click()
  d = await liveDoc(page); f = root(d)
  expect(f.deep_plan.style).toBe('news')
  expect(f.uid).toBe(uid)                                                           // 같은 프레임(발표 차례 그대로)
  expect(noOverlap(d)).toBe(0)
  expect(at(d)).toEqual(at0)                                                        // 톤 = 색만(자리·높이 그대로)
  expect(d.items.filter(it => it.deep_of === uid).length).toBeGreaterThan(5)
  expect(d.items.filter(it => it.deep_of === uid && it.chart).map(it => it.chart_theme)).toEqual(expect.arrayContaining(['red']))   // 그래프 색 순서 = 디자인 묶음(신문 = 빨강부터)
  await page.getByTestId('board').screenshot({ path: 'test-results/deepstyle-news.png' })

  await page.keyboard.press('Control+z')
  d = await liveDoc(page)
  expect(root(d).deep_plan.style).toBe('calm')                                      // 되돌리기 한 번
  expect(d.items.length).toBe(n0)
  expect(d.items.filter(it => it.deep_of === uid && it.chart).every(it => !it.chart_theme)).toBe(true)   // 차분 = 기본 색 순서

  const tile = d.items.find(it => it.deep_of === uid && PLAN.sections[it.deep_sec]?.shape === '숫자 타일')
  await page.evaluate(id => window.__mb.ed.setSel([id]), tile.uid)
  const vars = page.getByTestId('deep-variants')
  await expect(vars.locator('[data-variant]')).toHaveCount(2)
  const cur = await vars.locator('[aria-pressed="true"]').getAttribute('data-variant'), other = cur === 'row' ? 'col' : 'row'
  await vars.locator(`[data-variant="${other}"]`).click()
  d = await liveDoc(page); f = root(d)
  expect(f.deep_plan.fix[String(tile.deep_sec)]).toBe(other)                        // 판에 기억(다시 지어도 그 모양)
  expect(noOverlap(d)).toBe(0)

  const memo = d.items.find(it => it.deep_of === uid && it.type === 'memo' && it.deep_sec != null && !it.group_id)
  await page.evaluate(() => window.__mb.ed.setSel([]))
  const b = box(memo)
  await dragScene(page, { x: b.x + 40, y: b.y + b.h / 2 }, { x: b.x + 70, y: b.y + b.h / 2 + 30 })   // 손으로 옮김(윗변 가운데는 포트점 = 화살표 뽑기라 피함)
  expect((await liveDoc(page)).items.find(it => it.uid === memo.uid).pos).not.toEqual(memo.pos)
  await page.evaluate(id => window.__mb.ed.setSel([id]), uid)
  await styles.locator('[data-style="magazine"]').click()
  await expect(page.getByTestId('deep-confirm')).toBeVisible()                      // 덮어쓰기 전에 물음
  expect(root(await liveDoc(page)).deep_plan.style).toBe('calm')
  await page.getByTestId('deep-confirm-yes').click()
  d = await liveDoc(page)
  expect(root(d).deep_plan.style).toBe('magazine')
  expect(root(d).deep_plan.fix[String(tile.deep_sec)]).toBe(other)                  // 꼭지 모양은 디자인을 바꿔도 남음
  expect(noOverlap(d)).toBe(0)

  await waitSaved(page); await page.reload()
  await expect(page.getByText(`서버 「${name}」`).first()).toBeVisible()             // 다 받은 뒤에 봄(다른 흐름과 같게)
  d = await liveDoc(page)
  expect(root(d).deep_plan.style).toBe('magazine')
  expect(d.items.filter(it => it.deep_of === root(d).uid).length).toBeGreaterThan(5)
})

// 판 물건에서 판 밖 도형으로 손으로 그린 화살표 — 디자인을 바꿔도 남고, 두 끝이 같은 꼭지의 새 물건·그 도형에 붙어 있음(2026-10-25 — 다시 지으면 물건 id가 새로 바뀜)
test('손으로 그린 화살표는 디자인을 바꿔도 붙어 있음', async ({ page }) => {
  await openBoard(page, boardName('deeparrow'))
  await page.evaluate(p => window.__mb.ed.deepBoard(p, { x: 0, y: 0 }), PLAN)
  await setCam(page, { x: 400, y: 40, z: 0.5 })
  await pickShape(page, '사각형'); await dragScene(page, { x: -500, y: 1000 }, { x: -300, y: 1100 })
  let d = await liveDoc(page)
  const uid = root(d).uid, memo = d.items.find(it => it.deep_of === uid && it.type === 'memo' && it.deep_sec != null && !it.group_id), b = box(memo)
  const rect = d.items.find(it => it.type === 'rect' && !it.deep_of), n0 = d.items.length
  await page.evaluate(() => window.__mb.ed.setSel([]))
  await dragScene(page, { x: b.x + b.w / 2, y: b.y + 12 }, { x: -400, y: 1050 }, 16)          // 메모 윗변 가운데 포트 → 사각형(화살표 뽑기)
  d = await liveDoc(page)
  const hand = d.items.find(it => it.type === 'sarrow' && !it.deep_of)
  expect(hand).toBeTruthy()
  const ends = a => [a.bind1, a.bind2].map(i => d.items[i]?.uid ?? null)   // 저장 꼴 bind = 목록 순번
  expect(ends(hand).sort()).toEqual([memo.uid, rect.uid].sort())

  await page.evaluate(id => window.__mb.ed.setSel([id]), uid)
  await page.getByTestId('deep-styles').locator('[data-style="news"]').click()
  if (await page.getByTestId('deep-confirm').count()) await page.getByTestId('deep-confirm-yes').click()
  d = await liveDoc(page)
  expect(root(d).deep_plan.style).toBe('news')
  const h2 = d.items.find(it => it.uid === hand.uid)
  expect(h2).toBeTruthy()                                                                          // ① 남아 있음
  const e2 = [h2.bind1, h2.bind2].map(i => d.items[i])
  expect(e2.every(Boolean)).toBe(true)                                                             // ② 두 끝 다 붙음
  const nm = e2.find(it => it.uid !== rect.uid)
  expect(nm.deep_of).toBe(uid); expect(nm.deep_sec).toBe(memo.deep_sec); expect(nm.type).toBe('memo')   // 같은 꼭지의 새 메모
  await page.getByTestId('board').screenshot({ path: 'test-results/deeparrow-news.png' })
  await page.keyboard.press('Control+z')
  d = await liveDoc(page)
  expect(root(d).deep_plan.style).toBe('calm'); expect(d.items.length).toBe(n0 + 1)               // ③ 한 번에 되돌아옴
  const h3 = d.items.find(it => it.uid === hand.uid)
  expect([h3.bind1, h3.bind2].map(i => d.items[i]?.uid).sort()).toEqual([memo.uid, rect.uid].sort())
})
