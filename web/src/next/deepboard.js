// 딥모드 지면 물건(§8 항목66 2단계, 2026-10-25) — 꼭지 하나를 진짜 칠판 물건으로(새 종류 없음: 메모·표 + 모양·웹 카드, 단계 사이 화살표는 Editor가 길 찾기).
// 자리 계산은 deep.js(순수), 여기는 「이 폭·이 배율로 만들면 무엇이 얼마나 높은가」 — 같은 함수가 재기와 놓기를 맡아 잰 높이 = 놓인 높이.
// 꾸밈은 시안(③ 완성 지면) 그대로: 진한 주인공 면, 코랄 테두리 숫자 타일, 흰 종이 그래프, 옅은 단계 카드. 꾸미려고 넣는 요소 없음(계획서 항목66).
// 출처는 작은 목록 메모(웹 카드 넷은 공간만 먹었음 — 2026-10-25 판정)
import { answerTable, answerToEcadText } from '../chatFormat.js'
import { memoHeight } from './render.jsx'
import { memoFromAnswer, tableLine, tableWidths } from './memo.js'
import { newId } from './model.js'
import { chartData, chartGuess, chartWhy, textW } from './chart.js'
import { siteOf } from './webcard.js'
import { DEEP_STYLES } from './deepstyle.js'

const CLEAR = '#00ffffff', CALM = DEEP_STYLES.calm.look   // 색·카드 모양은 디자인 묶음(deepstyle.js `look`)에서
const STEP_GAP = 30   // 단계 카드 사이(화살표 자리)
const CHART_KIND = { 꺾은선: 'line', '세로 막대': 'col', '가로 막대': 'row', 원: 'pie', 막대: 'col' }

const base = (pos, extra) => ({ pos, scale: 1, rotation: 0, z: 0, origin: [0, 0], locked: false, group_id: null, layer_id: null, _id: newId(), ...extra })
// 메모 — 폭 w(칠판)·배율 s, 높이는 줄에 맞춤(편집기 commit과 같은 규칙)
function memo(x, y, w, s, lines, extra = {}) {
  const it = base([x, y], { type: 'memo', rect: [0, 0, w / s, 40], fill: '#ffffffff', lines, scale: s, ...extra })
  return { ...it, rect: [0, 0, w / s, memoHeight(it)] }
}
const boxOf = it => ({ x: it.pos[0], y: it.pos[1], w: it.rect[2] * (it.scale || 1), h: it.rect[3] * (it.scale || 1) })
const bottomOf = its => Math.max(...its.map(it => { const b = boxOf(it); return b.y + b.h }))
// **굵게** 글 → 줄 하나. color = 줄 전체 색(진한 면 위 글처럼 기본 잉크가 안 맞을 때), hi = 굵은 곳 색
function line(k, md, color, hi) {
  const { text, runs } = answerToEcadText(md)
  if (!color) return { k, t: text, ...(runs.length ? { runs } : {}) }
  const out = []; let at = 0
  for (const [s, n] of runs) { if (s > at) out.push([at, s - at, color, false]); out.push([s, n, hi || color, true]); at = s + n }
  if (at < text.length) out.push([at, text.length - at, color, false])
  return { k, t: text, runs: out }
}
const muted = (t, S = CALM) => ({ k: 'p', t, runs: [[0, t.length, S.muted, false]] })
const srcOf = (plan, n) => (plan.sources || []).find(x => x.n === n)
const siteLine = (plan, n) => { const s = srcOf(plan, n); return s ? `[${n}] ${s.url ? siteOf(s.url) : s.title}` : '' }   // 짧게 — 문서 제목 전체는 좁은 타일을 몇 줄씩 늘렸음(3-0 실제 본문)
const siteLines = (plan, ns, max = 3) => { const ls = ns.map(n => siteLine(plan, n)).filter(Boolean); return ls.slice(0, max).join(' · ') + (ls.length > max ? ` 외 ${ls.length - max}` : '') }
// 판에서 출처 번호가 쓰인 횟수(많이 쓰인 것부터 — 출처 카드 차례)
function usedRefs(plan) {
  const cnt = new Map()
  for (const sec of plan.sections || []) { const b = sec.body || {}
    for (const m of JSON.stringify(b).matchAll(/\[(\d+)\]/g)) cnt.set(+m[1], (cnt.get(+m[1]) || 0) + 1)
    for (const t of b.tiles || []) if (Number.isInteger(t[2])) cnt.set(t[2], (cnt.get(t[2]) || 0) + 1) }
  return [...cnt].sort((a, b) => b[1] - a[1] || a[0] - b[0]).map(([n]) => n)
}
// 제목만 있는 투명 메모(그래프·숫자·단계처럼 물건이 여럿인 꼭지 머리)
const title = (x, y, w, s, t, S = CALM) => memo(x, y, w, s, [{ k: S.title, t }], { fill: CLEAR, pen: CLEAR })
const card = (S, extra = {}) => ({ fill: S.card.fill, ...(S.card.pen ? { pen: S.card.pen } : {}), ...extra })

/** 머리 — 머리말(흐림: 제목 · 꼭지 수) + 헤드라인(크게) — 제목은 프레임 이름표에도 있어 크게 두 번 쓰지 않음(시안 머리와 같게). 반환 아이템 목록 */
export function deepHead(plan, x, y, w, k, page = 0, pages = 1, S = CALM) {
  const eye = `${plan.title || '딥모드'} · 꼭지 ${plan.sections?.length || 0}개${pages > 1 ? ` · ${page + 1}/${pages}장` : ''}`
  return [memo(x, y, w, k * S.head, [muted(eye, S), ...(plan.headline ? [{ k: 'h1', t: plan.headline }] : [])], { fill: CLEAR, pen: CLEAR })]
}

/** 꼭지 하나 → { items, links: [[앞 id, 뒤 id]] } — 왼쪽 위 (x, y), 폭 w, 본문 배율 k, v = 모양 바꿔 보기(deep.js `variantsOf`), S = 디자인 묶음 look */
export function deepSection(plan, sec, x, y, w, k, v = '', S = CALM) {
  const b = sec.body || {}, links = []
  let items = []
  switch (sec.shape) {
    case '주인공 글':
      items = [memo(x, y, w, k * S.hero.scale, [line('h2', sec.title, S.hero.hi), ...(b.text || []).map(t => line('p', t, S.hero.ink, S.hero.hi))], { fill: S.hero.bg, pen: S.hero.pen })]
      break
    case '용어 풀이':
      items = [memo(x, y, w, k, [{ k: S.title, t: sec.title }, ...(b.terms || []).map(([a, d]) => line('p', `**${a}** — ${d}`))], card(S))]
      break
    case '확인 문제':
      items = [memo(x, y, w, k, [{ k: S.title, t: sec.title }, ...(b.items || []).map(t => ({ k: 'todo', t }))], card(S))]
      break
    case '접힌 메모':
      items = [memo(x, y, w, k, [{ k: S.title, t: sec.title }, ...memoFromAnswer(b.md || '')], card(S, { fold: true }))]
      break
    case '움직이는 카드':   // 4단계 전까지 자리만 — 같은 꼭지 머리 + 무엇이 들어올지(흐린 글)
      items = [memo(x, y, w, k, [{ k: S.title, t: sec.title }, muted(b.note || '움직이는 카드 — 4단계에서 만들어요', S), { k: 'p', t: '' }, muted('▶ 움직이는 카드 자리', S)], { fill: S.moving.fill, pen: S.moving.pen })]
      break
    case '단계 카드': {   // 가로로 늘어놓고 사이에 화살표(Editor) — 한 장이 130px보다 좁으면 두 줄
      const head = title(x, y, w, k, sec.title, S), st = b.steps || [], top = bottomOf([head]) + 4
      const per = Math.max(1, Math.min(v === 'grid' ? Math.ceil(st.length / 2) : st.length, Math.floor((w + STEP_GAP) / (130 * k + STEP_GAP)))), rows = Math.ceil(st.length / per)   // grid = 두 줄
      const cw = (w - (per - 1) * STEP_GAP) / per
      items = [head]
      let ry = top
      for (let r = 0; r < rows; r++) {
        const cards = st.slice(r * per, r * per + per).map(([t, d], j) => { const n = r * per + j + 1
          return memo(x + j * (cw + STEP_GAP), ry, cw, k, [{ k: 'h3', t: `${n}. ${t}`, runs: [[0, String(n).length + 1, S.accent, true]] }, { k: 'p', t: d }], { fill: S.step.fill, pen: S.step.pen }) })
        cards.slice(1).forEach((c, j) => links.push([cards[j]._id, c._id]))
        items.push(...cards); ry = bottomOf(cards) + 14
      }
      break
    }
    case '숫자 타일': {   // row = 나란히(한 장 150px 바닥), col = 위아래로 — 큰 숫자 코랄 + 한 줄 + 출처 번호
      const head = title(x, y, w, k, sec.title, S), ts = b.tiles || [], top = bottomOf([head]) + 4, gap = 10, ks = k * S.tile.scale   // 인포그래픽 = 숫자 타일 크게
      const per = v === 'col' ? 1 : Math.max(1, Math.min(ts.length, Math.floor((w + gap) / (150 * ks + gap)))), cw = (w - (per - 1) * gap) / per   // col = 위아래로 쌓은 숫자 줄(시안 옆 칸처럼)
      items = [head]
      let ry = top
      for (let r = 0; r * per < ts.length; r++) {
        const row = ts.slice(r * per, r * per + per).map(([v, d, n], j) => memo(x + j * (cw + gap), ry, cw, ks,
          [{ k: 'h1', t: v, runs: [[0, v.length, S.tile.num, true]] }, { k: 'p', t: d }, ...(n ? [muted(siteLine(plan, n), S)] : [])], { fill: S.tile.fill, pen: S.tile.pen }))
        items.push(...row); ry = bottomOf(row) + gap
      }
      break
    }
    case '그래프': case '표': {   // 표 = 칠판 표, 그래프 = 표 + 모양(대화창 표 답 「그래프로」와 같은 길). 밑에 설명·출처(흐림)
      const head = title(x, y, w, k, sec.title, S), top = bottomOf([head]) + 4
      const { cells, refs } = answerTable(b.rows || [['']]), R = cells.length, C = cells[0].length
      let kind = sec.shape === '그래프' ? (b.kind || CHART_KIND[sec.chart] || 'col') : null
      if (kind && chartWhy(chartData({ cells, header: !!b.header }), kind)) kind = chartGuess({ type: 'table', cells, header: !!b.header }) || null   // 정한 모양이 자료에 안 맞으면(금액인데 원 등 — 3-0 실측) 자료에 맞는 모양, 숫자가 없으면 표
      const long = !kind && cells.some(r => r.some(c => textW(c, 12) > 150))   // 문장이 든 표 = 메모 표 줄(칸 안에서 꺾임 — 칠판 표는 한 줄에 맞춰 글자를 줄여 아주 작아졌음, 3-0 실제 본문)
      const notes = [...(b.caption ? [muted(b.caption, S)] : []), ...(refs.length ? [muted(siteLines(plan, refs), S)] : [])]   // 출처는 사이트 이름만 셋까지(외 N)
      if (long) {
        const mm = memo(x, top, w, k, [tableLine(cells, !!b.header)], card(S))
        items = [head, mm, ...(notes.length ? [memo(x, bottomOf([mm]) + 2, w, k * 0.9, notes, { fill: CLEAR, pen: CLEAR })] : [])]
        break
      }
      const tw = w / k, th = !kind ? R * 26 : v === 'short' ? Math.max(170, Math.min(tw * 0.34, 200)) : Math.max(180, Math.min(tw * 0.5, 260))   // 그래프 = 폭에 비례하되 지면 한 줄을 다 먹지 않게, short = 옆 꼭지가 낮을 때
      // 표 = 머리 행·왼쪽 열(항목 이름)에 옅은 바탕 + 굵게 — 칸 내용과 갈라 보이게(2026-10-25 사용자 판정)
      const cs = {}; if (!kind) for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) if ((b.header && r === 0) || (c === 0 && C > 1)) cs[`${r},${c}`] = { bold: true, fill: r === 0 && b.header ? '#fff1ebe6' : '#fffaf7f4' }
      const tb = base([x, top], { type: 'table', rows: R, cols: C, header: !!b.header, cells, col_widths: kind ? Array(C).fill(1 / C) : tableWidths(cells, C), rect: [0, 0, tw, th], scale: k,
        ...(kind ? { chart: kind, table_wh: [tw, R * 26] } : { cell_styles: cs }) })
      items = [head, tb, ...(notes.length ? [memo(x, bottomOf([tb]) + 2, w, k * 0.9, notes, { fill: CLEAR, pen: CLEAR })] : [])]
      break
    }
    case '출처 카드': {   // 작은 목록 메모 — 번호·제목 + 주소(Ctrl+클릭으로 열림). 웹 카드 넷은 「쓸데없이 공간을 차지」(2026-10-25 사용자 판정)
      // 판에서 많이 쓰인 출처부터, 셋만 펼치고 나머지는 접음(실제 본문은 출처가 20개 넘게 — 주소가 칸을 끝없이 늘렸음)
      const used = usedRefs(plan), pick = [...new Set([...used, ...(b.links || [])])], ss = pick.map(n => srcOf(plan, n)).filter(Boolean)
      items = [memo(x, y, w, k, [{ k: S.title, t: sec.title }, ...ss.flatMap(s => [line('p', `**[${s.n}]** ${s.title}`), ...(s.url ? [{ k: 'p', t: s.url, runs: [[0, s.url.length, S.muted, false]] }] : [])])], card(S, ss.length > 3 ? { fold: true } : {}))]
      break
    }
    default:   // 모르는 모양 = 글 메모(계획이 새 모양을 내도 지면이 깨지지 않게)
      items = [memo(x, y, w, k, [{ k: S.title, t: sec.title }, ...(b.text || [sec.question || '']).map(t => line('p', t))], card(S))]
  }
  if (items.length > 1) { const g = 'g' + newId(); items = items.map(it => ({ ...it, group_id: g })) }   // 꼭지 하나 = 한 묶음(통째로 옮기기 — 「더 자세히」 때 그 꼭지만)
  return { items, links }
}

/** 꼭지(또는 머리, i = -1) 높이 — deep.js `deepLayout`의 measure */
export function deepMeasure(plan, S = CALM) {
  const cache = new Map()
  return (i, w, k, v = '') => {   // v = 머리면 장 번호, 꼭지면 모양
    const key = `${i}|${w.toFixed(2)}|${k}|${v}`
    if (!cache.has(key)) { const its = i < 0 ? deepHead(plan, 0, 0, w, k, v || 0, 2, S) : deepSection(plan, plan.sections[i], 0, 0, w, k, v, S).items; cache.set(key, bottomOf(its)) }
    return cache.get(key)
  }
}
export { boxOf as deepBox }
