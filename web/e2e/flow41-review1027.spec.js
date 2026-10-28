// 흐름 41 — 10-27 사용자 UI 점검: 프레임으로 감싸면 안에 든 것으로 이름 · 레이어 판의 「선택 → 그리는 중」 단추 뺌(우클릭 「레이어로 이동」이 같은 일) ·
// 칠판 칸 = 「＋ 새 칠판」 먼저 · 접속자 = 이름 첫 글자 동그라미(4칸 넘으면 +N)
import { test, expect } from '@playwright/test'
import { boardName, openBoard, setCam, liveDoc, clickScene, pickShape, dragScene, toPage } from './helpers.js'

const frames = async page => (await liveDoc(page)).items.filter(it => it.type === 'frame')

test('프레임으로 감싸기 = 안에 든 것으로 이름(하나 = 종류 · 제목, 여럿 = 가장 많은 것 외 N)', async ({ page }) => {
  await openBoard(page, boardName('fname')); await setCam(page)
  const PNG = 'iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAFElEQVR4nGP4z8DAwMDAwMDAwAAAHwAB/2Y2E7QAAAAASUVORK5CYII='
  await page.evaluate(async png => {
    const d = window.__mb.toEcad()
    d.items.push({ type: 'web', pos: [0, 0], rect: [0, 0, 300, 200], url: 'https://news.kbs.co.kr', title: 'KBS 뉴스' },
      { type: 'image', pos: [400, 0], rect: [0, 0, 100, 80], data: png }, { type: 'image', pos: [550, 0], rect: [0, 0, 100, 80], data: png })
    await window.__mb.open('data:application/json,' + encodeURIComponent(JSON.stringify(d)))
  }, PNG)
  await setCam(page)
  await clickScene(page, 150, 100); await page.keyboard.press('Alt+g')
  await expect.poll(async () => (await frames(page)).map(f => f.name)).toEqual(['웹 · KBS 뉴스'])
  await clickScene(page, 1000, 600); await dragScene(page, { x: 380, y: -30 }, { x: 680, y: 110 }); await page.keyboard.press('Alt+g')
  await expect.poll(async () => (await frames(page)).map(f => f.name).sort()).toEqual(['웹 · KBS 뉴스', '이미지 2개'].sort())
})

test('레이어 판엔 「선택 → 그리는 중」 단추 없음 · 우클릭 「레이어로 이동」은 있음', async ({ page }) => {
  await openBoard(page, boardName('layerbtn')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 150, y: 100 }); await page.keyboard.press('Escape')
  await page.getByTestId('dock-layer').click(); await expect(page.getByRole('button', { name: '＋ 레이어' })).toBeVisible()
  await expect(page.getByRole('button', { name: '선택 → 그리는 중' })).toHaveCount(0)
  const p = await toPage(page, 75, 50); await page.mouse.click(p.x, p.y, { button: 'right' })
  expect((await page.locator('div[style*="z-index: 30"] > div > button').allInnerTexts()).some(n => n.startsWith('레이어로 이동'))).toBe(true)
})

test('칠판 칸 — 이름 칸 없음 · 「＋ 새 칠판」 = 바로 새 칠판(비밀번호 없는 서버, 2026-10-28)', async ({ page }) => {
  const name = boardName('newboard')
  await openBoard(page, name)
  await page.getByTestId('board-title').click()
  const form = page.getByTestId('board-form')
  await expect(form.getByPlaceholder('새 칠판 이름', { exact: false })).toHaveCount(0)
  await expect(form.getByRole('button', { name: '파일 열기' })).toHaveCount(0)               // 파일 = 「▾ › 파일로 새 칠판」·줄 ⋯ 내려받기(2026-10-28)
  await form.getByTestId('board-new-more').click()
  await expect(page.getByTestId('board-new-menu').locator('button')).toHaveText(['＋새 칠판', '#칠판 코드로 열기', '↥파일로 새 칠판'])
  await page.keyboard.press('Escape'); await expect(page.getByTestId('board-new-menu')).toHaveCount(0)
  await form.getByTestId('board-new').click()
  await expect(page).toHaveURL(/board=[a-z2-9]{8}$/)
  await expect(form.getByPlaceholder('새 칠판 이름', { exact: false })).toHaveCount(0)
  await expect(form.getByTestId('board-row').filter({ hasText: name })).toBeVisible()   // 아무것도 안 그린 앞 칠판도 남음
})

test('접속자 = 동그라미 — 5명이면 3명 + 「+2」, 누르면 공유 창(전체 목록)', async ({ page, browser }) => {
  const name = boardName('faces'), ctxs = []
  await openBoard(page, name, { who: '가' })
  for (const w of ['나', '다', '라', '마']) { const c = await browser.newContext(); ctxs.push(c); await openBoard(await c.newPage(), name, { who: w }) }
  const who = page.getByTestId('people')
  await expect(who).toHaveAttribute('title', /5명/, { timeout: 6000 })
  await expect(who).toContainText('+2')
  await who.click(); await expect(page.getByText('지금 이 칠판에 5명')).toBeVisible()
  for (const c of ctxs) await c.close()
})

test('내 심볼(이 브라우저) — 우클릭 추가 → 판에 보임 → 놓기 · 새로 고쳐도 남음 · 이름 바꾸기 · 파일로 저장 → 지우기 → 불러오기', async ({ page }) => {
  await openBoard(page, boardName('mysym')); await setCam(page)
  await pickShape(page, '원'); await dragScene(page, { x: 0, y: 0 }, { x: 120, y: 80 }); await page.keyboard.press('Escape')
  await clickScene(page, 60, 40); const p = await toPage(page, 60, 40); await page.mouse.click(p.x, p.y, { button: 'right' })
  await page.locator('div[style*="z-index: 30"] > div > button', { hasText: '내 심볼에 추가' }).click()
  const dlg = page.getByTestId('symadd'); await expect(dlg).toBeVisible()
  await dlg.getByPlaceholder('예: 송신탑').fill('동그라미'); await dlg.getByRole('button', { name: '추가' }).click()
  const mine = page.getByTestId('mine'); await expect(mine.getByRole('button', { name: '동그라미' })).toBeVisible()   // 폴더 없으면 「내 심볼」
  await expect(mine).toContainText('내 심볼'); await expect(mine.getByRole('button', { name: '카메라' })).toBeVisible()   // 서버 예시도 내 심볼로 복사돼 있음
  const n0 = (await liveDoc(page)).items.length
  await mine.getByRole('button', { name: '동그라미' }).click(); await clickScene(page, 400, 300)
  await expect.poll(async () => (await liveDoc(page)).items.length).toBe(n0 + 1)
  expect((await liveDoc(page)).items.at(-1).sym_name).toBe('동그라미')                       // 속성 카드 제목 = 심볼 이름(2026-10-27)
  await expect(page.getByTestId('prop-type')).toHaveText('동그라미')
  await page.reload(); await expect(page.getByTestId('mine').getByRole('button', { name: '동그라미' })).toBeVisible()   // 이 브라우저에 남음
  await page.getByTestId('mine').getByRole('button', { name: '동그라미' }).click({ button: 'right' })
  await page.getByTestId('mine-pop').getByRole('button', { name: '이름 바꾸기' }).click()
  await page.getByTestId('mine-pop').locator('input').fill('원 심볼'); await page.getByTestId('mine-pop').locator('input').press('Enter')
  await expect(page.getByTestId('mine').getByRole('button', { name: '원 심볼' })).toBeVisible()
  await page.getByTestId('mine-more').click()
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('mine-pop').getByRole('button', { name: '파일로 저장' }).click()])
  const path = await dl.path()
  await page.getByTestId('pal-sec').filter({ has: page.getByRole('button', { name: '원 심볼' }) }).getByTestId('folder-menu').click(); await page.getByTestId('mine-pop').getByRole('button', { name: /지우기/ }).click()
  await expect(page.getByTestId('mine').getByRole('button', { name: '원 심볼' })).toHaveCount(0)
  await page.getByTestId('mine').locator('input[type=file]').setInputFiles(path)
  await expect(page.getByTestId('mine').getByRole('button', { name: '원 심볼' })).toBeVisible()
  await expect(page.getByTestId('mine').getByRole('button', { name: '카메라' })).toHaveCount(1)   // 있던 예시는 두 벌 안 됨
})

test('화살표를 고르고 바로 치면 글 — 라벨 없으면 가운데에 새 라벨, 있으면 첫 라벨을 새로 씀 · 치다 지우면 그대로', async ({ page }) => {
  await openBoard(page, boardName('arrowtype')); await setCam(page)
  await page.keyboard.press('2'); await dragScene(page, { x: 0, y: 0 }, { x: 300, y: 0 }); await page.keyboard.press('Escape')
  const labels = async () => { const a = (await liveDoc(page)).items.find(it => it.type === 'sarrow' || it.type === 'arrow'); return (a.labels || (a.label ? [a.label] : [])).map(L => [L.text, L.t ?? 0.5]) }
  await clickScene(page, 700, 500); await clickScene(page, 150, 0)
  await page.keyboard.type('승인'); await clickScene(page, 700, 500)
  await expect.poll(labels).toEqual([['승인', 0.5]])
  await clickScene(page, 60, 0); await page.keyboard.type('ok'); await clickScene(page, 700, 500)
  await expect.poll(labels).toEqual([['ok', 0.5]])                                          // 첫 라벨을 새로 씀
  await page.keyboard.press('2'); await dragScene(page, { x: 0, y: 200 }, { x: 300, y: 200 }); await page.keyboard.press('Escape')
  await clickScene(page, 700, 500); await clickScene(page, 150, 200)
  const n = (await liveDoc(page)).items.length
  await page.keyboard.type('x'); await page.keyboard.press('Backspace'); await clickScene(page, 700, 500)
  const b = (await liveDoc(page)).items.filter(it => it.type === 'sarrow' || it.type === 'arrow')[1]
  expect(b.labels || b.label || null).toBeFalsy(); expect((await liveDoc(page)).items.length).toBe(n)   // 치다 지움 = 라벨 안 생김
})

test('예시 폴더도 지울 수 있음 — 지우면 새로 고쳐도 안 생김 · ⋯ 「예시 다시 넣기」로 돌아옴', async ({ page }) => {
  await openBoard(page, boardName('seed'))
  const mine = page.getByTestId('mine'), sec = name => page.getByTestId('pal-sec').filter({ hasText: name })
  await expect(mine.getByRole('button', { name: '카메라' })).toBeVisible()
  await sec('방송').getByTestId('folder-menu').click(); await page.getByTestId('mine-pop').getByRole('button', { name: /지우기/ }).click()
  await expect(mine.getByRole('button', { name: '카메라' })).toHaveCount(0)
  await page.reload(); await expect(page.getByTestId('mine').getByRole('button', { name: '사람' })).toBeVisible()
  await expect(page.getByTestId('mine').getByRole('button', { name: '카메라' })).toHaveCount(0)        // 다시 안 생김
  await page.getByTestId('mine-more').click(); await page.getByTestId('mine-pop').getByRole('button', { name: '예시 다시 넣기' }).click()
  await expect(page.getByTestId('mine').getByRole('button', { name: '카메라' })).toHaveCount(1)
  await expect(page.getByTestId('mine').getByRole('button', { name: '사람' })).toHaveCount(1)          // 남아 있던 예시는 두 벌 안 됨
})

test('도형을 끌어 도형 칸(폴더 위)에 놓기 = 그 폴더로 추가 창 · 도형은 제자리 · 칸이 밝아짐', async ({ page }) => {
  await openBoard(page, boardName('symdrag')); await setCam(page)
  await pickShape(page, '사각형'); await dragScene(page, { x: 0, y: 0 }, { x: 150, y: 100 }); await page.keyboard.press('Escape')
  const pos0 = (await liveDoc(page)).items.find(it => it.type === 'rect').pos
  await clickScene(page, 75, 50)
  const a = await toPage(page, 75, 50), sec = page.getByTestId('pal-sec').filter({ hasText: '업무' }), t = await sec.boundingBox()
  await page.mouse.move(a.x, a.y); await page.mouse.down()
  for (let i = 1; i <= 12; i++) await page.mouse.move(a.x + (t.x + 60 - a.x) * i / 12, a.y + (t.y + 40 - a.y) * i / 12)
  await expect(page.getByTestId('symdrop-hint')).toContainText('업무')
  await page.mouse.up()
  await expect(page.getByTestId('symdrop-hint')).toHaveCount(0)
  const dlg = page.getByTestId('symadd'); await expect(dlg).toBeVisible()
  await expect(dlg.locator('select')).toHaveValue('업무')
  expect((await liveDoc(page)).items.find(it => it.type === 'rect').pos).toEqual(pos0)     // 제자리
  await dlg.getByPlaceholder('예: 송신탑').fill('끌어 넣은 상자'); await dlg.getByRole('button', { name: '추가' }).click()
  await expect(sec.getByRole('button', { name: '끌어 넣은 상자' })).toBeVisible()
})
