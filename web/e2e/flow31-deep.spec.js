// 흐름 31 — 딥모드 지면 배치(§8 항목66 2단계, 2026-10-25): 고정 계획 셋(논문·송신 장비·시사 — 계획은 0단계 opus, 본문은 가짜) + 실제 본문 셋(`deep_real_*` — 3-0 실측 sonnet)을 칠판에 놓고
// ① 물건끼리 겹침 0(화살표 빼고) ② 모두 프레임 안 ③ 실제로 그린 글자(<text>)가 모두 제 물건 상자 안 — 시안이 겹쳤던 「글이 아래 줄로 넘침」을 브라우저 치수로 잼
// ④ 갇힌 빈칸 15% 미만(2차 — 사용자 판정 「공간을 효율적으로 못 씀」을 숫자로, 1차 16:9 배치는 이 값이 컸음).
// 디자인 묶음 넷(3-1 — deepstyle.js) 모두. 계산은 web/test/deep.test.mjs. 캡처 test-results/deep-*.png
import { test, expect } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { boardName, openBoard, setCam, liveDoc } from './helpers.js'
import { overlaps, inside } from '../src/next/deep.js'

const plan = t => JSON.parse(readFileSync(new URL(`../test/fixtures/deep_${t}.json`, import.meta.url), 'utf-8'))
test.use({ viewport: { width: 1700, height: 1000 }, deviceScaleFactor: 2 })   // 캡처를 시안과 나란히 볼 때 글자가 읽히게
const box = it => ({ x: it.pos[0], y: it.pos[1], w: it.rect[2] * (it.scale || 1), h: it.rect[3] * (it.scale || 1) })

for (const style of ['calm', 'news', 'magazine', 'info']) for (const t of ['paper', 'tx', 'news', 'real_paper', 'real_tx', 'real_news', 'real_jeonbuk', 'real_live']) test(`딥모드 지면 — ${t} · ${style}: 겹침·넘침 0, 글자는 제 상자 안, 갇힌 빈칸 15% 미만`, async ({ page }) => {
  await openBoard(page, boardName(`deep_${t}_${style}`))
  const P = plan(t)
  const r = await page.evaluate(([p, st]) => window.__mb.ed.deepBoard(p, { x: 0, y: 0 }, st), [P, style])
  const total = r.pages[r.pages.length - 1].x + r.pages[r.pages.length - 1].w, H = Math.max(...r.pages.map(p => p.h))
  const vb = await page.getByTestId('board').boundingBox(), z = Math.min((vb.width - 80) / total, (vb.height - 80) / (H + 60))
  await setCam(page, { x: 40, y: 70, z })
  const d = await liveDoc(page)
  const frames = d.items.filter(it => it.type === 'frame'), things = d.items.filter(it => it.type !== 'frame' && it.type !== 'sarrow' && it.type !== 'arrow')
  expect(frames).toHaveLength(r.pages.length)
  if (P.sections.some(s => s.shape === '단계 카드')) expect(d.items.filter(it => it.type === 'sarrow').length).toBeGreaterThan(0)   // 단계 사이 화살표(단계 꼭지가 있을 때)
  const B = things.map(box)
  expect(overlaps(B).map(([a, b]) => [things[a].type, things[b].type])).toEqual([])              // ① 겹침 0
  const F = frames.map(box)
  expect(B.filter(b => !F.some(f => inside(b, f))).length).toBe(0)                              // ② 프레임 안
  // ③ 그린 글자 — 칠판 좌표로 바꿔 어느 물건 상자 안인지(프레임 이름표는 프레임 위 바깥이라 뺌)
  const stray = await page.evaluate(([B, F]) => {
    const svg = document.querySelector('[data-testid="board"]'), r0 = svg.getBoundingClientRect(), c = window.__mb.getCam(), out = []
    for (const el of svg.querySelectorAll('text')) {
      const q = el.getBoundingClientRect(); if (!q.width || !el.textContent.trim()) continue
      const s = { x: (q.left - r0.left - c.x) / c.z, y: (q.top - r0.top - c.y) / c.z, w: q.width / c.z, h: q.height / c.z }
      if (F.some(f => s.y + s.h <= f.y + 1)) continue                                           // 프레임 이름표
      const ok = B.some(b => s.x >= b.x - 2 && s.y >= b.y - 2 && s.x + s.w <= b.x + b.w + 2 && s.y + s.h <= b.y + b.h + 2)
      if (!ok) out.push(el.textContent.slice(0, 30))
    }
    return out
  }, [B, F])
  expect(stray).toEqual([])
  for (const p of r.pages) expect(p.waste).toBeLessThan(0.15)                                  // ④ 갇힌 빈칸
  if (style === 'calm' || t.startsWith('real_')) await page.getByTestId('board').screenshot({ path: `test-results/deep-${t}${style === 'calm' ? '' : '-' + style}.png` })
  console.log(`[deep ${t} ${style}] ${r.pages.length}장 · ${r.pages.map(p => `${p.w}×${Math.round(p.h)}`).join(' / ')} · 갇힌 빈칸 ${r.pages.map(p => (p.waste * 100).toFixed(1) + '%').join(' / ')} · 줄 ${r.pages[0].rows.join(' | ')}`)
})
