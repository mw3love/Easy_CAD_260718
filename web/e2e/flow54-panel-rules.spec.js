// 흐름 54 — 웹 디자인 규칙 1라운드(2026-11-02, `docs/web_ui_rules.md`) 왼쪽 판: 메뉴 = 공용 부품(판 안을 눌러도 닫힘·같은 ⋯ 다시 누르면 닫힘)·
// 되돌릴 수 없는 지우기만 확인 창(빈 폴더는 바로)·이름 칸 Enter·바깥 = 저장, Esc = 취소·「＋ 새 ○○」 = 머리줄·마우스 올림 = 회색·이 폴더만 내려받기
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, liveDoc, clickScene, pickShape, dragScene } from './helpers.js'

const sec = (page, name) => page.getByTestId('pal-sec').filter({ hasText: name })

test('도형 판 — 메뉴 닫힘 · 이름 칸 저장·취소 · 빈 폴더는 바로 · 심볼 든 폴더는 확인 창 · 이 폴더만 내려받기', async ({ page }) => {
  await openBoard(page, boardName('palrule'))
  const mine = page.getByTestId('mine'), menu = page.getByTestId('mine-menu')
  await expect(mine.getByRole('button', { name: '카메라' })).toBeVisible()
  // ⋯ → 메뉴, 판 안(검색 칸) 누르기 = 닫힘(옛 자체 메뉴는 안 닫혔음)
  await sec(page, '방송').getByTestId('folder-menu').click(); await expect(menu).toBeVisible()
  await page.getByPlaceholder('도형·심볼 검색 (이름·초성)').click(); await expect(menu).toHaveCount(0)
  // 같은 ⋯ 다시 누르기 = 닫기
  await sec(page, '방송').getByTestId('folder-menu').click(); await expect(menu).toBeVisible()
  await sec(page, '방송').getByTestId('folder-menu').click(); await expect(menu).toHaveCount(0)
  // 제목 줄 우클릭 = 같은 메뉴
  await sec(page, '방송').locator('div').first().click({ button: 'right' }); await expect(menu).toContainText('이 폴더만 내려받기')
  // 이 폴더만 내려받기 — 파일 이름 = 폴더 이름, 안엔 그 폴더 심볼만
  const [dl] = await Promise.all([page.waitForEvent('download'), menu.getByRole('menuitem', { name: '이 폴더만 내려받기' }).click()])
  expect(dl.suggestedFilename()).toBe('방송·기술.json')
  const got = JSON.parse(readFileSync(await dl.path(), 'utf-8'))
  expect(got.folders).toEqual(['방송·기술']); expect(got.symbols.length).toBe(6); expect(new Set(got.symbols.map(s => s.folder))).toEqual(new Set(['방송·기술']))
  // ＋ 새 폴더 = 머리줄 단추, Enter = 만들기
  await page.getByTestId('mine-new-folder').click(); await page.getByTestId('mine-pop').locator('input').fill('빈칸'); await page.getByTestId('mine-pop').locator('input').press('Enter')
  await expect(sec(page, '빈칸')).toBeVisible()
  // 이름 바꾸기 — Esc = 취소
  await sec(page, '빈칸').getByTestId('folder-menu').click(); await menu.getByRole('menuitem', { name: '이름 바꾸기' }).click()
  await page.getByTestId('mine-pop').locator('input').fill('바뀐칸'); await page.getByTestId('mine-pop').locator('input').press('Escape')
  await expect(sec(page, '빈칸')).toBeVisible(); await expect(sec(page, '바뀐칸')).toHaveCount(0)
  // 이름 바꾸기 — 바깥 누르기 = 저장(옛 칸은 바깥 = 취소라 고친 글이 사라졌음)
  await sec(page, '빈칸').getByTestId('folder-menu').click(); await menu.getByRole('menuitem', { name: '이름 바꾸기' }).click()
  await page.getByTestId('mine-pop').locator('input').fill('바뀐칸'); await page.getByPlaceholder('도형·심볼 검색 (이름·초성)').click()
  await expect(sec(page, '바뀐칸')).toBeVisible()
  // 빈 폴더 지우기 = 묻지 않음(잃을 것 없음)
  await sec(page, '바뀐칸').getByTestId('folder-menu').click(); await menu.getByRole('menuitem', { name: '지우기', exact: true }).click()
  await expect(page.getByTestId('mine-delete')).toHaveCount(0); await expect(sec(page, '바뀐칸')).toHaveCount(0)
  // 심볼 든 폴더 = 확인 창, Esc = 취소, Enter = 지우기
  await sec(page, '방송').getByTestId('folder-menu').click(); await menu.getByRole('menuitem', { name: '지우기…' }).click()
  await expect(page.getByTestId('mine-delete')).toContainText('「방송·기술」 폴더를 지울까요?'); await expect(page.getByTestId('mine-delete-ok')).toBeFocused()
  await page.keyboard.press('Escape'); await expect(page.getByTestId('mine-delete')).toHaveCount(0); await expect(mine.getByRole('button', { name: '카메라' })).toBeVisible()
  await sec(page, '방송').getByTestId('folder-menu').click(); await menu.getByRole('menuitem', { name: '지우기…' }).click(); await page.keyboard.press('Enter')
  await expect(mine.getByRole('button', { name: '카메라' })).toHaveCount(0)
  // 심볼 하나 지우기도 확인 창
  await mine.getByRole('button', { name: '사람' }).click({ button: 'right' }); await menu.getByRole('menuitem', { name: '지우기…' }).click()
  await expect(page.getByTestId('mine-delete')).toContainText('「사람」 심볼을 지울까요?'); await page.getByTestId('mine-delete-ok').click()
  await expect(mine.getByRole('button', { name: '사람' })).toHaveCount(0)
})

test('레이어 판 — 「＋ 새 레이어」 머리줄 · 줄 ⋯(올렸을 때만)·우클릭 = 공용 메뉴 · 이름 Esc = 취소', async ({ page }) => {
  await openBoard(page, boardName('layrule'))
  await page.getByTestId('dock-layer').click()
  await page.getByTestId('layer-new').click(); await expect(page.getByTestId('layer-row')).toHaveCount(2)
  const row = page.getByTestId('layer-row').nth(1), menu = page.getByTestId('layer-menu')
  await expect(row.getByTestId('layer-more')).toBeHidden(); await row.hover(); await expect(row.getByTestId('layer-more')).toBeVisible()
  await row.getByTestId('layer-more').click(); await expect(menu).toBeVisible()
  await row.getByTestId('layer-more').click(); await expect(menu).toHaveCount(0)                      // 같은 ⋯ = 닫기
  await row.click({ button: 'right' }); await menu.getByRole('menuitem', { name: '이름 바꾸기' }).click()
  await row.locator('input:not([type=color])').fill('글씨'); await row.locator('input:not([type=color])').press('Escape')
  await expect.poll(async () => (await liveDoc(page)).layers.map(l => l.name)).toEqual(['기본', '레이어 2'])
  await row.click({ button: 'right' }); await menu.getByRole('menuitem', { name: '이름 바꾸기' }).click()
  await row.locator('input:not([type=color])').fill('글씨'); await row.locator('input:not([type=color])').press('Enter')
  await expect.poll(async () => (await liveDoc(page)).layers.map(l => l.name)).toEqual(['기본', '글씨'])
  await row.click({ button: 'right' }); await menu.getByRole('menuitem', { name: /^지우기/ }).click()
  await expect(page.getByTestId('layer-row')).toHaveCount(1)
})

test('프레임 판 — 이름 Esc = 처음 이름으로 · 줄 ▶는 회색(코랄 채움은 「▶ 발표」 하나) · 위 막대 마우스 올림 = 회색', async ({ page }) => {
  await openBoard(page, boardName('frmrule')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 200, y: 120 }); await page.keyboard.press('Escape')
  await clickScene(page, 100, 60); await page.keyboard.press('Alt+g')
  await expect.poll(async () => (await liveDoc(page)).items.filter(it => it.type === 'frame').length).toBe(1)
  await page.getByTestId('dock-frame').click()
  const row = page.getByTestId('frame-row').first(), name0 = (await liveDoc(page)).items.find(it => it.type === 'frame').name || ''
  await row.locator('[data-frame-name]').dblclick()
  await row.locator('input:not([type=color])').fill('표지'); await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'frame').name).toBe('표지')   // 치는 대로 바로
  await row.locator('input:not([type=color])').press('Escape')
  await expect.poll(async () => (await liveDoc(page)).items.find(it => it.type === 'frame').name || '').toBe(name0)                       // Esc = 처음 이름
  await row.hover(); const play = row.getByTestId('frame-play'); await expect(play).toBeVisible()
  expect(await play.evaluate(el => getComputedStyle(el).backgroundColor)).toBe('rgba(0, 0, 0, 0)')
  await row.getByTestId('frame-more').click(); await expect(page.getByTestId('frame-menu')).toContainText('이 장부터 발표')
  await page.keyboard.press('Escape'); await expect(page.getByTestId('frame-menu')).toHaveCount(0)
  // 위 막대 마우스 올림 = 회색 — 묶음 안은 묶음 바탕(--mb-group)보다 한 단계 진한 --mb-group-hover(2026-11-10 0단계 B4), 켜짐만 코랄
  const btn = page.getByRole('button', { name: '표', exact: true }); await btn.hover()
  const [bg, group] = await btn.evaluate(el => [getComputedStyle(el).backgroundColor, getComputedStyle(document.documentElement).getPropertyValue('--mb-group-hover').trim()])
  expect(bg).toBe(await page.evaluate(c => { const d = document.createElement('div'); d.style.color = c; document.body.append(d); const v = getComputedStyle(d).color; d.remove(); return v }, group))
})
