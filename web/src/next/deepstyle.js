// 딥모드 톤(§8 항목66 3-1, 2026-10-25) — 같은 판을 다른 색으로 다시 짓기(내용·배치는 그대로, AI 크레딧 없음). 판을 고르면 속성 카드 「톤」.
// 처음엔 「디자인 묶음」(색 + 배치 무게 — 차분·신문·잡지·인포그래픽)이었다(사용자 「디자인은 한 가지 정답이 없다」).
// 색은 .ecad 꼴(#AARRGGBB, 글 runs는 #RRGGBB). look.chart = 그래프 색 순서(chart.js `CHART_THEMES` — 없으면 기본 파랑·주황).
// 2026-10-25 최종 판정 → **톤**(사용자 「차분·신문만 괜찮고 둘은 구성이 거의 같음 — 구성 하나에 색만 다르게, 일단 만들고 톤은 나중에」):
// 배치는 넷 다 차분과 같고(빈칸 없이 빽빽한 2차 판정 배치) 색만 다름 — 글 크기·카드 모양도 같게. 처음 고르기·추천은 없앰(만든 뒤 속성 카드 「톤」).
// 키는 옛 판 그대로 읽히게 둠(magazine = 남색, info = 파랑 — 옛 잡지·인포그래픽 배치는 버림).
const tone = (name, tip, c) => ({ name, tip,
  look: { accent: c.accent, muted: c.muted, title: 'h3', head: 1.4, ...(c.chart ? { chart: c.chart } : {}),
    hero: { bg: c.hero, pen: c.heroPen || c.hero, ink: c.heroInk, hi: c.heroHi, scale: 1.2 },
    card: { fill: '#ffffffff', pen: c.cardPen || null }, step: { fill: c.step, pen: c.stepPen },
    tile: { fill: '#ffffffff', pen: c.tilePen, num: c.accent, scale: 1 }, moving: { fill: c.moving, pen: c.movingPen } } })

export const DEEP_STYLES = {
  // 차분 — 2차 판정 「톤은 차분해서 좋음」 그대로(진한 주인공 면·코랄 테두리 숫자·옅은 단계)
  calm: tone('차분', '진한 회색 · 코랄', { accent: '#b4532f', muted: '#71717a', hero: '#ff27272a', heroInk: '#e4e4e7', heroHi: '#ffffff',
    step: '#fffffaf7', stepPen: '#fff0c9b8', tilePen: '#ffda7756', moving: '#fff4f4f5', movingPen: '#ffd4d4d8' }),
  // 신문 — 흰 바탕에 검은 괘선 · 빨강(배치는 차분과 같음)
  news: tone('신문', '흰 바탕 · 검은 괘선 · 빨강', { accent: '#9b1c1c', muted: '#57534e', chart: 'red', hero: '#ffffffff', heroPen: '#ff18181b', heroInk: '#27272a', heroHi: '#9b1c1c',
    cardPen: '#ff3f3f46', step: '#ffffffff', stepPen: '#ff3f3f46', tilePen: '#ff18181b', moving: '#fff5f5f4', movingPen: '#ff3f3f46' }),
  // 남색 — 옛 잡지의 색만(남색 면·모래색 강조)
  magazine: tone('남색', '남색 면 · 모래색 강조', { accent: '#1f5f7a', muted: '#6b7280', chart: 'cool', hero: '#ff1f3a4d', heroInk: '#e6edf2', heroHi: '#ffd9a7',
    step: '#ffedf3f6', stepPen: '#ffc6d9e2', tilePen: '#ff1f5f7a', moving: '#ffeef0f2', movingPen: '#ffcfd6dc' }),
  // 파랑 — 옛 인포그래픽의 색만(파랑 한 색)
  info: tone('파랑', '파랑 한 색', { accent: '#2a78d6', muted: '#64748b', hero: '#ff2a78d6', heroInk: '#eaf2fc', heroHi: '#ffffff',
    step: '#ffe8f1fb', stepPen: '#ffbcd6f3', tilePen: '#ff2a78d6', moving: '#ffeef3f9', movingPen: '#ffcbd9ea' }),
}
export const STYLE_KEYS = Object.keys(DEEP_STYLES)
export const styleOf = key => DEEP_STYLES[key] || DEEP_STYLES.calm
// 꼭지 모양 바꿔 보기의 이름(속성 카드 「꼭지 모양」)
export const variantName = (shape, v) => ({ row: shape === '단계 카드' ? '한 줄' : '나란히', col: '위아래', grid: '두 줄', tall: '높게', short: '낮게' })[v] || v
