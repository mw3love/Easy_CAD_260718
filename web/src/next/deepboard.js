// 딥모드 지면 물건(§8 항목66 2단계, 2026-10-25) — 꼭지 하나를 진짜 칠판 물건으로(새 종류 없음: 메모·표 + 모양·웹 카드, 단계 사이 화살표는 Editor가 길 찾기).
// 자리 계산은 deep.js(순수), 여기는 「이 폭·이 배율로 만들면 무엇이 얼마나 높은가」 — 같은 함수가 재기와 놓기를 맡아 잰 높이 = 놓인 높이.
// 꾸밈은 시안(③ 완성 지면) 그대로: 진한 주인공 면, 코랄 테두리 숫자 타일, 흰 종이 그래프, 옅은 단계 카드. 꾸미려고 넣는 요소 없음(계획서 항목66).
// 출처는 작은 목록 메모(웹 카드 넷은 공간만 먹었음 — 2026-10-25 판정)
import { answerTable, answerToEcadText } from '../chatFormat.js'
import { memoHeight } from './render.jsx'
import { memoFromAnswer } from './memo.js'
import { newId } from './model.js'
import { siteOf } from './webcard.js'

const ACCENT = '#b4532f', CORAL = '#ffda7756', MUTE = '#71717a', HERO_BG = '#ff27272a', HERO_INK = '#e4e4e7', HERO_HI = '#ffffff', CLEAR = '#00ffffff'
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
const muted = t => ({ k: 'p', t, runs: [[0, t.length, MUTE, false]] })
const srcLine = (plan, n) => { const s = (plan.sources || []).find(x => x.n === n); return s ? `[${n}] ${s.title} · ${siteOf(s.url)}` : '' }
// 제목만 있는 투명 메모(그래프·숫자·단계처럼 물건이 여럿인 꼭지 머리)
const title = (x, y, w, s, t) => memo(x, y, w, s, [{ k: 'h3', t }], { fill: CLEAR, pen: CLEAR })

/** 머리 — 머리말(흐림: 제목 · 꼭지 수) + 헤드라인(크게) — 제목은 프레임 이름표에도 있어 크게 두 번 쓰지 않음(시안 머리와 같게). 반환 아이템 목록 */
export function deepHead(plan, x, y, w, k, page = 0, pages = 1) {
  const eye = `${plan.title || '딥모드'} · 꼭지 ${plan.sections?.length || 0}개${pages > 1 ? ` · ${page + 1}/${pages}장` : ''}`
  return [memo(x, y, w, k * 1.4, [muted(eye), ...(plan.headline ? [{ k: 'h1', t: plan.headline }] : [])], { fill: CLEAR, pen: CLEAR })]
}

/** 꼭지 하나 → { items, links: [[앞 id, 뒤 id]] } — 왼쪽 위 (x, y), 폭 w, 본문 배율 k, v = 모양 바꿔 보기(deep.js `variantsOf`) */
export function deepSection(plan, sec, x, y, w, k, v = '') {
  const b = sec.body || {}, links = []
  let items = []
  switch (sec.shape) {
    case '주인공 글':
      items = [memo(x, y, w, k * 1.2, [line('h2', sec.title, HERO_HI), ...(b.text || []).map(t => line('p', t, HERO_INK, HERO_HI))], { fill: HERO_BG, pen: HERO_BG })]
      break
    case '용어 풀이':
      items = [memo(x, y, w, k, [{ k: 'h3', t: sec.title }, ...(b.terms || []).map(([a, d]) => line('p', `**${a}** — ${d}`))])]
      break
    case '확인 문제':
      items = [memo(x, y, w, k, [{ k: 'h3', t: sec.title }, ...(b.items || []).map(t => ({ k: 'todo', t }))])]
      break
    case '접힌 메모':
      items = [memo(x, y, w, k, [{ k: 'h3', t: sec.title }, ...memoFromAnswer(b.md || '')], { fold: true })]
      break
    case '움직이는 카드':   // 4단계 전까지 자리만 — 같은 꼭지 머리 + 무엇이 들어올지(흐린 글)
      items = [memo(x, y, w, k, [{ k: 'h3', t: sec.title }, muted(b.note || '움직이는 카드 — 4단계에서 만들어요'), { k: 'p', t: '' }, muted('▶ 움직이는 카드 자리')], { fill: '#fff4f4f5', pen: '#ffd4d4d8' })]
      break
    case '단계 카드': {   // 가로로 늘어놓고 사이에 화살표(Editor) — 한 장이 130px보다 좁으면 두 줄
      const head = title(x, y, w, k, sec.title), st = b.steps || [], top = bottomOf([head]) + 4
      const per = Math.max(1, Math.min(v === 'grid' ? Math.ceil(st.length / 2) : st.length, Math.floor((w + STEP_GAP) / (130 * k + STEP_GAP)))), rows = Math.ceil(st.length / per)   // grid = 두 줄
      const cw = (w - (per - 1) * STEP_GAP) / per
      items = [head]
      let ry = top
      for (let r = 0; r < rows; r++) {
        const cards = st.slice(r * per, r * per + per).map(([t, d], j) => { const n = r * per + j + 1
          return memo(x + j * (cw + STEP_GAP), ry, cw, k, [{ k: 'h3', t: `${n}. ${t}`, runs: [[0, String(n).length + 1, ACCENT, true]] }, { k: 'p', t: d }], { fill: '#fffffaf7', pen: '#fff0c9b8' }) })
        cards.slice(1).forEach((c, j) => links.push([cards[j]._id, c._id]))
        items.push(...cards); ry = bottomOf(cards) + 14
      }
      break
    }
    case '숫자 타일': {   // row = 나란히(한 장 150px 바닥), col = 위아래로 — 큰 숫자 코랄 + 한 줄 + 출처 번호
      const head = title(x, y, w, k, sec.title), ts = b.tiles || [], top = bottomOf([head]) + 4, gap = 10
      const per = v === 'col' ? 1 : Math.max(1, Math.min(ts.length, Math.floor((w + gap) / (150 * k + gap)))), cw = (w - (per - 1) * gap) / per   // col = 위아래로 쌓은 숫자 줄(시안 옆 칸처럼)
      items = [head]
      let ry = top
      for (let r = 0; r * per < ts.length; r++) {
        const row = ts.slice(r * per, r * per + per).map(([v, d, n], j) => memo(x + j * (cw + gap), ry, cw, k,
          [{ k: 'h1', t: v, runs: [[0, v.length, ACCENT, true]] }, { k: 'p', t: d }, ...(n ? [muted(srcLine(plan, n))] : [])], { pen: CORAL }))
        items.push(...row); ry = bottomOf(row) + gap
      }
      break
    }
    case '그래프': case '표': {   // 표 = 칠판 표, 그래프 = 표 + 모양(대화창 표 답 「그래프로」와 같은 길). 밑에 설명·출처(흐림)
      const head = title(x, y, w, k, sec.title), top = bottomOf([head]) + 4
      const { cells, refs } = answerTable(b.rows || [['']]), R = cells.length, C = cells[0].length
      const kind = sec.shape === '그래프' ? (b.kind || CHART_KIND[sec.chart] || 'col') : null
      const tw = w / k, th = !kind ? R * 26 : v === 'short' ? Math.max(170, Math.min(tw * 0.34, 200)) : Math.max(180, Math.min(tw * 0.5, 260))   // 그래프 = 폭에 비례하되 지면 한 줄을 다 먹지 않게, short = 옆 꼭지가 낮을 때
      // 표 = 머리 행·왼쪽 열(항목 이름)에 옅은 바탕 + 굵게 — 칸 내용과 갈라 보이게(2026-10-25 사용자 판정)
      const cs = {}; if (!kind) for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) if ((b.header && r === 0) || (c === 0 && C > 1)) cs[`${r},${c}`] = { bold: true, fill: r === 0 && b.header ? '#fff1ebe6' : '#fffaf7f4' }
      const tb = base([x, top], { type: 'table', rows: R, cols: C, header: !!b.header, cells, col_widths: Array(C).fill(1 / C), rect: [0, 0, tw, th], scale: k,
        ...(kind ? { chart: kind, table_wh: [tw, R * 26] } : { cell_styles: cs }) })
      const src = refs.map(n => srcLine(plan, n)).filter(Boolean).join('  '), notes = [...(b.caption ? [muted(b.caption)] : []), ...(src ? [muted(src)] : [])]   // 출처는 한 덩어리(줄마다 쌓으면 꼭지가 길어졌음)
      items = [head, tb, ...(notes.length ? [memo(x, bottomOf([tb]) + 2, w, k * 0.9, notes, { fill: CLEAR, pen: CLEAR })] : [])]
      break
    }
    case '출처 카드': {   // 작은 목록 메모 — 번호·제목 + 주소(Ctrl+클릭으로 열림). 웹 카드 넷은 「쓸데없이 공간을 차지」(2026-10-25 사용자 판정)
      const ss = (b.links || []).map(n => (plan.sources || []).find(s => s.n === n)).filter(Boolean)
      items = [memo(x, y, w, k, [{ k: 'h3', t: sec.title }, ...ss.flatMap(s => [line('p', `**[${s.n}]** ${s.title}`), { k: 'p', t: s.url, runs: [[0, s.url.length, MUTE, false]] }])])]
      break
    }
    default:   // 모르는 모양 = 글 메모(계획이 새 모양을 내도 지면이 깨지지 않게)
      items = [memo(x, y, w, k, [{ k: 'h3', t: sec.title }, ...(b.text || [sec.question || '']).map(t => line('p', t))])]
  }
  if (items.length > 1) { const g = 'g' + newId(); items = items.map(it => ({ ...it, group_id: g })) }   // 꼭지 하나 = 한 묶음(통째로 옮기기 — 「더 자세히」 때 그 꼭지만)
  return { items, links }
}

/** 꼭지(또는 머리, i = -1) 높이 — deep.js `deepLayout`의 measure */
export function deepMeasure(plan) {
  const cache = new Map()
  return (i, w, k, v = '') => {   // v = 머리면 장 번호, 꼭지면 모양
    const key = `${i}|${w.toFixed(2)}|${k}|${v}`
    if (!cache.has(key)) { const its = i < 0 ? deepHead(plan, 0, 0, w, k, v || 0, 2) : deepSection(plan, plan.sections[i], 0, 0, w, k, v).items; cache.set(key, bottomOf(its)) }
    return cache.get(key)
  }
}
export { boxOf as deepBox }
