// 딥모드(§8 항목66) 4-0 실측의 화면 검사 — `tools/livecard_probe.py`가 쓴 카드 HTML을 앱과 같은 틀(sandbox="allow-scripts" + CSP)로 띄워
// 조작 전후 그림·스크립트 오류·CSP 위반·넘침·바깥 요청을 잰다. 크롬은 web/의 Playwright(깔린 크롬, e2e와 같게).
// 사용: node tools/livecard_shot.mjs [결과 폴더]   (기본 tools/_livecard_probe)
import { createRequire } from 'node:module'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const require = createRequire(path.join(HERE, '..', 'web', 'package.json'))
const { chromium } = require('@playwright/test')

const DIR = process.argv[2] || path.join(HERE, '_livecard_probe')
const SHOTS = path.join(DIR, 'shots')
fs.mkdirSync(SHOTS, { recursive: true })
const CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:"
// 4-1 그릇 후보와 같은 꼴 — 카드 HTML의 doctype을 떼고 우리 머리(doctype·CSP·charset)를 맨 앞에(그래야 카드의 어떤 스크립트보다 CSP가 먼저)
const wrap = (html) => `<!doctype html><meta http-equiv="Content-Security-Policy" content="${CSP}"><meta charset="utf-8">`
  + `<script>addEventListener('error',e=>console.error('ERR '+e.message));addEventListener('securitypolicyviolation',e=>console.error('CSP '+e.violatedDirective+' '+e.blockedURI))`
  // 다 열린 뒤 resize 한 번 — 스크립트로 만든 iframe(앱·판정 페이지)은 카드 스크립트가 처음 돌 때 innerWidth가 0이라 크기를 0배로 잡는 카드가 있었음(opus 둘, 4-0)
  + `;addEventListener('load',()=>(function k(){innerWidth?dispatchEvent(new Event('resize')):requestAnimationFrame(k)})())</script>`
  + html.replace(/^\s*<!doctype[^>]*>/i, '')
const esc = (s) => s.replace(/&/g, '&amp;').replace(/"/g, '&quot;')
const host = (w, h, html) => `<!doctype html><body style="margin:0;background:#e4e4e7"><iframe id="c" sandbox="allow-scripts" style="border:0;width:${w}px;height:${h}px;background:#fff;display:block" srcdoc="${esc(wrap(html))}"></iframe></body>`

const files = fs.readdirSync(DIR).filter(f => f.endsWith('.html')).sort()
const browser = await chromium.launch({ channel: 'chrome' })
const out = {}
for (const f of files) {
  const tag = f.replace(/\.html$/, '')
  const html = fs.readFileSync(path.join(DIR, f), 'utf8')
  const page = await browser.newPage({ viewport: { width: 760, height: 520 }, deviceScaleFactor: 1.5 })
  const logs = [], reqs = []
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') logs.push(m.text().slice(0, 200)) })
  page.on('pageerror', e => logs.push('PAGEERR ' + String(e.message).slice(0, 200)))
  page.on('request', r => { const u = r.url(); if (!/^(about|data|blob):/.test(u)) reqs.push(u.slice(0, 120)) })
  const r = { tag, logs, reqs }
  try {
    await page.setContent(host(720, 480, html))
    const frame = await (await page.$('#c')).contentFrame()
    await page.waitForTimeout(1200)
    const el = await page.$('#c')
    const info = () => frame.evaluate(() => ({ sw: document.documentElement.scrollWidth, sh: document.documentElement.scrollHeight, w: innerWidth, h: innerHeight, text: document.body.innerText.replace(/\s+/g, ' ').slice(0, 600) }))
    const a = await info()
    r.overflow = { w: a.sw - a.w, h: a.sh - a.h }
    await el.screenshot({ path: path.join(SHOTS, tag + '_1before.png') })
    // 조작: 슬라이더 = 끝까지, 없으면 버튼 하나, 그것도 없으면 가운데를 가로로 끌기
    const ranges = await frame.$$('input[type=range]'), buttons = await frame.$$('button')
    r.parts = { ranges: ranges.length, buttons: buttons.length }
    if (ranges.length) {
      await ranges[0].evaluate(i => { i.value = i.max || 100; i.dispatchEvent(new Event('input', { bubbles: true })); i.dispatchEvent(new Event('change', { bubbles: true })) })
      r.did = 'range→max'
    } else if (buttons.length) { await buttons[buttons.length > 1 ? 1 : 0].click(); r.did = 'button' }
    else { await page.mouse.move(250, 260); await page.mouse.down(); await page.mouse.move(520, 220, { steps: 12 }); await page.mouse.up(); r.did = 'drag' }
    await page.waitForTimeout(900)
    const b = await info()
    await el.screenshot({ path: path.join(SHOTS, tag + '_2after.png') })
    r.changed = a.text !== b.text
    r.text_before = a.text.slice(0, 300); r.text_after = b.text.slice(0, 300)
    // 작은 카드(칠판에서 보통 꼭지 크기)에서도 넘치지 않나
    await page.setViewportSize({ width: 520, height: 360 })
    await el.evaluate(i => { i.style.width = '480px'; i.style.height = '320px' })
    await page.waitForTimeout(600)
    const c = await info()
    r.overflow_small = { w: c.sw - c.w, h: c.sh - c.h }
    await el.screenshot({ path: path.join(SHOTS, tag + '_3small.png') })
  } catch (e) { r.error = String(e.message || e).slice(0, 300) }
  out[tag] = r
  console.log(`[${tag}] 넘침 ${JSON.stringify(r.overflow)} 작게 ${JSON.stringify(r.overflow_small)} · 부품 ${JSON.stringify(r.parts)} ${r.did} → 바뀜 ${r.changed} · 오류 ${logs.length} ${logs.slice(0, 2).join(' | ')} · 바깥 요청 ${reqs.length}${r.error ? ' · ' + r.error : ''}`)
  await page.close()
}
await browser.close()
fs.writeFileSync(path.join(DIR, 'shots.json'), JSON.stringify(out, null, 1))
