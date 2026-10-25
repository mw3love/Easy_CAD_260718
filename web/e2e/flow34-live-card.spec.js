// 흐름 34 — 움직이는 카드 그릇(§8 항목66 4-1): 「움직임」 표시 문서 카드만 스크립트가 돎(sandbox allow-scripts + CSP),
// 한 번 = 고르기(칸 안은 안 받음) · 두 번 = 조작 · 바깥 누르기 = 끝, 인터넷·저장소·칠판(부모 창)에 못 닿음, 새로고침해도 그대로,
// 크게 보기 = 같은 틀(그 페이지엔 스크립트 없음), 보통 문서 크게 보기 = 스크립트 꺼짐(끌어 놓은 HTML 파일 구멍). 데스크톱 쪽은 tests/test_part74.
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, clickScene, liveDoc } from './helpers.js'

const CARD = `<!doctype html><html><head><title>시험 카드</title><style>body{margin:0;font:16px sans-serif}</style></head><body>
<button id="inc" style="position:absolute;left:300px;top:200px;width:140px;height:70px">더하기</button>
<button id="go" style="position:absolute;left:300px;top:330px;width:140px;height:50px" onclick="location.href='https://example.com/nav'">나가기</button>
<b id="v">0</b><p id="r"></p>
<script>
var r=[];function w(){document.getElementById('r').textContent=r.join(',')}
try{fetch('https://example.com/f').then(function(){r.push('fetch 됨');w()},function(){r.push('fetch 막힘');w()})}catch(e){r.push('fetch 막힘')}
try{localStorage.x=1;r.push('ls 됨')}catch(e){r.push('ls 막힘')}
try{r.push('parent 됨 '+parent.document.title)}catch(e){r.push('parent 막힘')}
new Image().src='https://example.com/i.png';w();
document.getElementById('inc').onclick=function(){var v=document.getElementById('v');v.textContent=+v.textContent+1};
</script></body></html>`

test('움직이는 카드 — 한 번 = 고르기 · 두 번 = 조작 · 바깥 = 끝 · 인터넷·칠판 못 닿음 · 새로고침 · 크게 보기도 같은 틀', async ({ page, context }) => {
  const name = boardName('live'), outside = []
  await context.route('https://example.com/**', r => { outside.push(r.request().url()); r.fulfill({ contentType: 'text/html', body: '<p id="phish">바깥 페이지</p>' }) })
  await openBoard(page, name); await setCam(page)
  await page.evaluate(h => window.__mb.ed.pinCard({ live: true, html: h, title: '시험 카드', model: 'gpt-6.1-sol' }), CARD)
  const card = (await liveDoc(page)).items.find(it => it.type === 'doc')
  expect(card.live).toBe(true)
  const fr = page.locator(`iframe[data-liveid="${card.uid}"]`)
  await expect(fr).toHaveAttribute('sandbox', 'allow-scripts')                  // same-origin 없음
  await expect(fr).toHaveAttribute('csp', /default-src 'none'/)
  const inner = page.frameLocator(`iframe[data-liveid="${card.uid}"]`)
  await expect(inner.locator('#r')).toHaveText(/fetch 막힘/)
  await expect(inner.locator('#r')).toHaveText(/ls 막힘/)
  await expect(inner.locator('#r')).toHaveText(/parent 막힘/)

  // 칸 안 단추의 화면 자리 — 카드는 기준 폭 720을 카드 폭으로 줄여 보여 줌(Playwright boundingBox는 iframe 배율을 빼고 셈)
  const spot = async (loc, el) => { const f = await loc.boundingBox(), k = f.width / 720, r = await inner.locator(el).evaluate(e => { const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2] }); return { x: f.x + r[0] * k, y: f.y + r[1] * k } }
  const at = await spot(fr, '#inc')
  await page.mouse.click(at.x, at.y)                                             // 한 번 = 고르기만(칸 안 단추는 안 눌림)
  await expect(page.getByText('두 번 누르면 움직여 보기').first()).toBeVisible()
  expect(await page.evaluate(() => window.__mb.ed.getSel())).toEqual([card.uid])
  await expect(inner.locator('#v')).toHaveText('0')

  await page.mouse.dblclick(at.x, at.y)                                          // 두 번 = 조작 켜기
  await expect(fr).toHaveCSS('pointer-events', 'auto')
  await page.mouse.click(at.x, at.y)
  await expect(inner.locator('#v')).toHaveText('1')
  await clickScene(page, 300, 560)                                               // 바깥(카드 아래 빈 곳) = 끝
  await expect(fr).toHaveCSS('pointer-events', 'none')
  await page.mouse.click(at.x, at.y)
  await expect(inner.locator('#v')).toHaveText('1')

  await page.mouse.dblclick(at.x, at.y)                                          // 칸 안에서 바깥 주소로 가기 = 막힘(iframe `csp` — 바깥 페이지가 이 틀을 받아들이지 않음)
  const g = await spot(fr, '#go')
  await page.mouse.click(g.x, g.y)
  await page.waitForTimeout(800)
  await expect(inner.locator('#phish')).toHaveCount(0)
  expect(outside.filter(u => !u.endsWith('/nav'))).toEqual([])                   // fetch·그림은 요청조차 안 나감

  await clickScene(page, 300, 560); await expect.poll(() => page.evaluate(() => window.__mb.unsaved())).toBe(false); await page.reload()   // 새로고침해도 움직이는 카드(저장은 넣을 때 끝남 — 상태 글은 「조작 중」이 덮음)
  await expect(page.getByText(`서버 「${name}」`, { exact: false }).first()).toBeVisible()
  await expect(page.locator('iframe[data-liveid]')).toHaveCount(1)

  const c2 = (await liveDoc(page)).items.find(it => it.type === 'doc'), fr2 = page.locator('iframe[data-liveid]')
  const hb = await fr2.boundingBox()
  await page.mouse.click(hb.x + hb.width - 40, hb.y - 20, { button: 'right' })   // 위 띠 우클릭 → 크게 보기
  const pop = context.waitForEvent('page')
  await page.getByText('크게 보기', { exact: true }).click()
  const big = await pop
  await expect(big.locator('iframe[sandbox="allow-scripts"]')).toHaveCount(1)
  await expect(big.frameLocator('iframe').locator('#r')).toHaveText(/parent 막힘/)
  expect(await big.evaluate(() => document.scripts.length)).toBe(0)              // 크게 보기 페이지(앱 주소의 blob) 자체엔 스크립트 없음
  await big.close()
  expect(c2.live).toBe(true)

  await page.evaluate(() => window.__mb.ed.pinCard({ html: '<title>파일</title><script>document.title="RAN"</script><p>글</p>', title: '파일' }))   // 보통 문서(끌어 놓은 HTML 파일과 같음)
  const plain = (await liveDoc(page)).items.find(it => it.type === 'doc' && !it.live)
  const pb = await page.locator(`iframe[data-docid="${plain.uid}"]`).boundingBox()
  await page.mouse.click(pb.x + pb.width / 2, pb.y - 20, { button: 'right' })
  const pop2 = context.waitForEvent('page')
  await page.getByText('크게 보기', { exact: true }).click()
  const big2 = await pop2
  await big2.waitForLoadState()
  expect(await big2.title()).toBe('파일')                                        // 스크립트가 안 돎(돌면 RAN)
  await big2.close()
})

// 4-2·4-3 대화창 — 「+ › ▶ 움직이는 카드」(서버가 할 수 있을 때만) → 답 = 대화창 안에서 바로 만져 보는 카드 → 칠판에 붙이기 = 움직이는 문서 카드
// → 고칠 말 = 앞 카드 HTML을 같이 보냄(prev_kind) · 딥모드 판의 원리 꼭지 = 진짜 카드(고정 계획 셋 — 겹침 0은 flow31). KAIROS·서버는 가짜
test('대화창 「+ › 움직이는 카드」 → 대화창에서 만져 보기 → 칠판에 붙이기 → 말로 고치기', async ({ page }) => {
  const sent = []
  await page.route('**/api/models', r => r.fulfill({ json: { default: 'fake-model', featured: {}, jobs: { live: 'gpt-6.1-sol' } } }))
  await page.route('**/api/chat', r => { const b = r.request().postDataJSON(); sent.push(b)
    r.fulfill({ json: { kind: 'live', content: `${b.prev_html ? '말한 대로 고친 ' : ''}움직이는 카드 「시험 카드」`, title: '시험 카드', html: CARD, model: 'gpt-6.1-sol', elapsed: 50 } }) })
  const name = boardName('livechat')
  await openBoard(page, name, { chat: true }); await setCam(page)
  await page.getByTestId('plus').click()
  await page.getByRole('menuitemradio', { name: /움직이는 카드/ }).click()
  await page.getByPlaceholder('무엇을 움직여 볼까요', { exact: false }).click()
  await page.keyboard.type('가격 × 물량 = 수출액'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-kind').last()).toHaveText('▶ 움직이는 카드')
  expect(sent[0].kind).toBe('live')
  const pv = page.getByTestId('answer-live').locator('iframe')
  await expect(pv).toHaveAttribute('sandbox', 'allow-scripts')
  const inner = page.frameLocator('[data-testid="answer-live"] iframe')
  await expect(inner.locator('#r')).toHaveText(/parent 막힘/)
  const f = await pv.boundingBox(), k = f.width / 720, r = await inner.locator('#inc').evaluate(e => { const b = e.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2] })
  await page.mouse.click(f.x + r[0] * k, f.y + r[1] * k)                         // 대화창 안에선 바로 만져 봄
  await expect(inner.locator('#v')).toHaveText('1')

  await page.getByRole('button', { name: '칠판에 붙이기' }).last().click()
  const card = (await liveDoc(page)).items.find(it => it.type === 'doc')
  expect(card.live).toBe(true); expect(card.html).toBe(CARD)
  expect(card.rect[3] - 40).toBe(Math.round(card.rect[2] * 480 / 720))           // 띠 + 기준 비율
  await expect(page.locator(`iframe[data-liveid="${card.uid}"]`)).toHaveCount(1)

  await page.getByPlaceholder('무엇을 움직여 볼까요', { exact: false }).click()
  await page.keyboard.type('막대를 더 크게'); await page.keyboard.press('Enter')
  await expect(page.getByTestId('answer-kind')).toHaveCount(2)
  expect(sent[1].prev_html).toBe(CARD); expect(sent[1].prev_kind).toBe('live')
})

test('딥모드 판의 원리 꼭지 = 움직이는 카드(카드 HTML 있을 때) · 없으면 설명 메모', async ({ page }) => {
  const load = t => JSON.parse(readFileSync(new URL(`../test/fixtures/deep_${t}.json`, import.meta.url), 'utf-8'))
  await openBoard(page, boardName('livedeep')); await setCam(page, { x: 100, y: 100, z: 0.4 })
  await page.evaluate(p => window.__mb.ed.deepBoard(p, { x: 0, y: 0 }), load('real_tx'))
  let docs = (await liveDoc(page)).items.filter(it => it.type === 'doc')
  expect(docs.length).toBe(1); expect(docs[0].live).toBe(true); expect(docs[0].deep_sec).toBeGreaterThanOrEqual(0)
  expect(docs[0].rect[2]).toBeGreaterThan(560)                                   // 조작 부품이 읽히는 폭(칸 5개 이상)
  await page.evaluate(p => window.__mb.ed.deepBoard(p, { x: 0, y: 3000 }), load('tx'))   // 2단계 고정 계획 = 카드 HTML 없음
  docs = (await liveDoc(page)).items.filter(it => it.type === 'doc')
  expect(docs.length).toBe(1)
  expect(JSON.stringify((await liveDoc(page)).items.filter(it => it.type === 'memo').map(it => it.lines))).toContain('움직이는 카드를 못 만들었어요')
})
