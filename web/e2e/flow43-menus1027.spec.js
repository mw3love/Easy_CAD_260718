// 흐름 43 — 10-27 사용자 전수조사(「상식적으로 이상한 것」): 우클릭 메뉴에서 하는 일 없는 항목 숨김(감싼 그대로 다시 감싸기·상자 하나 반전·이미 한 묶음 「그룹」·
// 그림/프레임 스타일 복사·글 없는 정리 문서·메모/표 내 심볼) + 프레임 메뉴(발표·이름·틀만 지우기)·왼쪽 프레임 판/칠판 판 줄 우클릭
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, toPage, openPane } from './helpers.js'

const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII='
const MENU = 'div[style*="z-index: 30"] > div > button'
const names = async page => (await page.locator(MENU).allInnerTexts()).map(s => s.split('\n')[0])
async function menuAt(page, x, y, keep = false) { if (!keep) await page.keyboard.press('Escape'); const p = await toPage(page, x, y); await page.mouse.click(p.x, p.y, { button: 'right' }); await page.waitForTimeout(100); return names(page) }
async function load(page, items) {   // 칠판에 도형을 바로 넣고 화면을 정해진 자리로
  await page.evaluate(async its => { const d = window.__mb.toEcad(); d.items.push(...its); await window.__mb.open('data:application/json,' + encodeURIComponent(JSON.stringify(d))) }, items)
  await setCam(page)
}
const R = (x, y, extra = {}) => ({ type: 'rect', pos: [x, y], rect: [0, 0, 120, 80], pen: '#ff1f1f1f', width: 1, ...extra })

test('감싼 그대로는 다시 감싸기 없음(일부만 고르면 있음) · 프레임 메뉴 = 발표·이름 먼저, 반전·스타일 복사 없음 · 프레임만 지우기', async ({ page }) => {
  await openBoard(page, boardName('wrapdup')); await load(page, [R(0, 0), R(200, 0)])
  await page.keyboard.press('Control+a'); await page.keyboard.press('Alt+g')
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'frame').length).toBe(1)
  await page.keyboard.press('Control+a'); expect(await menuAt(page, 60, 40, true)).not.toContain('프레임으로 감싸기')   // 프레임 + 안의 것 = 이미 감쌈
  expect(await names(page)).not.toContain('묶기')                                                                // 프레임은 원래 안의 것을 같이 옮김
  await page.keyboard.press('Escape'); await page.keyboard.press('Escape')
  expect(await menuAt(page, 60, 40)).toContain('프레임으로 감싸기')                                               // 둘 중 하나만 = 확대 장(그대로)
  const fr = await menuAt(page, -16, 40)                                                                          // 프레임 테두리(여백 16)
  expect(fr.slice(0, 2)).toEqual(['이 장부터 발표', '이름 바꾸기'])
  for (const no of ['좌우 반전', '상하 반전', '스타일 복사', '프레임으로 감싸기']) expect(fr).not.toContain(no)
  await page.locator(MENU, { hasText: '프레임만 지우기' }).click()
  await expect.poll(async () => (await liveDoc(page)).items.map(it => it.type).sort()).toEqual(['rect', 'rect'])
  await menuAt(page, 60, 40); await page.keyboard.press('Escape'); await page.keyboard.press('Alt+g')            // 하나만 감싼 뒤 그것을 우클릭(사용자가 본 그대로)
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'frame').length).toBe(1)
  expect(await menuAt(page, 60, 40)).not.toContain('프레임으로 감싸기')
})

test('상자 하나 = 반전 없음(그림은 진짜로 뒤집힘), 선·둘 이상 = 있음 · 이미 한 묶음 = 「그룹」 없음 · 그림 = 스타일 복사 없음 · 글 없는 것 = 정리 문서 없음 · 메모 = 내 심볼 없음', async ({ page }) => {
  await openBoard(page, boardName('menuhide'))
  await load(page, [R(0, 0), { type: 'line', pos: [0, 0], line: [200, 40, 320, 40], pen: '#ff1f1f1f', width: 2 }, { type: 'image', pos: [400, 0], rect: [0, 0, 100, 80], data: PNG },
    R(0, 200, { group_id: 'g1' }), R(200, 200, { group_id: 'g1' }), R(400, 200, { label: { text: '송신소' } }),
    { type: 'memo', pos: [600, 0], rect: [0, 0, 200, 80], lines: [{ k: 'p', t: '메모 글' }] }])
  const rect = await menuAt(page, 60, 40)
  expect(rect).not.toContain('좌우 반전'); expect(rect).toContain('스타일 복사'); expect(rect).not.toContain('KAIROS에게 묻기…'); expect(rect).toContain('내 심볼에 추가…')
  expect(await menuAt(page, 260, 40)).toContain('좌우 반전')                                                       // 선 = 방향이 뒤집힘
  const img = await menuAt(page, 450, 40); expect(img).not.toContain('스타일 복사'); expect(img).toContain('KAIROS에게 묻기…')
  expect(img).toContain('좌우 반전')                                                                              // 그림은 하나만 골라도 진짜로 뒤집힘(2026-10-27 밤)
  await page.locator(MENU, { hasText: '좌우 반전' }).click()
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'image')?.flip_h).toBe(true)
  const grp = await menuAt(page, 60, 240)
  expect(grp).not.toContain('묶기'); expect(grp).toContain('묶기 풀기'); expect(grp).toContain('좌우 반전')        // 묶음 둘 = 자리 맞바꿈은 뜻이 있음
  expect(await menuAt(page, 460, 240)).toContain('KAIROS에게 묻기…')                                       // 글 있는 도형
  const memo = await menuAt(page, 700, 40); expect(memo).not.toContain('내 심볼에 추가…'); expect(memo).not.toContain('좌우 반전')
})

test('왼쪽 프레임 판 줄 우클릭 = 발표·이름 바꾸기·내보내기·프레임만 지우기 · 칠판 판 줄 우클릭 = 새 탭·주소 복사', async ({ page, context }) => {
  const name = boardName('dockmenu')
  await openBoard(page, name); await load(page, [R(0, 0), R(200, 0)])
  await page.keyboard.press('Control+a'); await page.keyboard.press('Alt+g'); await page.keyboard.press('Escape')
  await openPane(page, 'frame')
  await page.getByTestId('frame-row').first().click({ button: 'right' })
  expect(await names(page)).toEqual(['이 장부터 발표', '발표에서 빼기', '이름 바꾸기', '이 프레임 내보내기…', '프레임만 지우기 (안의 것은 남김)'])   // 발표에서 빼기 = 2026-10-28
  await page.locator(MENU, { hasText: '이름 바꾸기' }).click()
  await page.getByTestId('frame-row').first().locator('input').fill('표지'); await page.keyboard.press('Enter')
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'frame')?.name).toBe('표지')
  await page.getByTestId('frame-row').first().click({ button: 'right' }); await page.locator(MENU, { hasText: '이 프레임 내보내기' }).click()
  await expect(page.getByText('프레임 1개 → 틀마다 한 쪽', { exact: false })).toBeVisible()                         // 그 프레임을 고른 채 내보내기 창
  await page.keyboard.press('Escape')
  await page.getByTestId('frame-row').first().click({ button: 'right' }); await page.locator(MENU, { hasText: '프레임만 지우기' }).click()
  await expect.poll(async () => (await liveDoc(page)).items.map(it => it.type).sort()).toEqual(['rect', 'rect'])
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.getByTestId('board-title').click()   // 지금 칠판 = 「내 칠판 — 이 브라우저」에 있음
  await page.getByTestId('board-row').filter({ hasText: name }).click({ button: 'right' })
  const MOVE = ['위로 옮기기', '아래로 옮기기']   // 옮길 수 있을 때만(2026-11-09 — 끌기의 글쇠·메뉴 길)
  expect((await names(page)).filter(n => !MOVE.includes(n))).toEqual(['이름 바꾸기', '새 탭에서 열기', '주소 복사', '내려받기 (.ecad)', '칠판 지우기…'])   // 이름 바꾸기 = 문서 이름만(2026-10-28 — 주소 그대로)
  await page.mouse.click(700, 500); await expect(page.locator(MENU)).toHaveCount(0)
  await page.getByTestId('board-row').first().click({ button: 'right' })
  expect(await names(page)).not.toContain('위로 옮기기')   // 맨 위 줄
  await page.mouse.click(700, 500); await expect(page.locator(MENU)).toHaveCount(0)
  await page.getByTestId('board-row').filter({ hasText: name }).click({ button: 'right' })
  await page.locator(MENU, { hasText: '주소 복사' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(`?board=${name}`)
})
