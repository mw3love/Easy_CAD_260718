// 딥모드 디자인 묶음(§8 항목66 3-1, 2026-10-25 사용자 「디자인은 한 가지 정답이 없다 — 처음에 고르기·일부 개선·다른 형식으로 전면 개선」).
// 디자인 = 색·카드 모양(look) + 배치 무게(layout — deep.js `DEEP`를 덮어씀). 내용(계획·본문)은 그대로, 묶음만 바꿔 다시 짓는다 — AI 크레딧 없음.
// 색은 .ecad 꼴(#AARRGGBB, 글 runs는 #RRGGBB). CLEAR = 투명(테두리 없는 카드).
const CLEAR = '#00ffffff'

export const DEEP_STYLES = {
  // 차분 — 2차 판정 「톤은 차분해서 좋음」 그대로(진한 주인공 면·코랄 테두리 숫자·옅은 단계)
  calm: { name: '차분', tip: '진한 주인공 면 · 코랄 숫자 · 흰 카드',
    layout: {},
    look: { accent: '#b4532f', muted: '#71717a', title: 'h3', head: 1.4,
      hero: { bg: '#ff27272a', pen: '#ff27272a', ink: '#e4e4e7', hi: '#ffffff', scale: 1.2 },
      card: { fill: '#ffffffff', pen: null }, step: { fill: '#fffffaf7', pen: '#fff0c9b8' },
      tile: { fill: '#ffffffff', pen: '#ffda7756', num: '#b4532f', scale: 1 }, moving: { fill: '#fff4f4f5', pen: '#ffd4d4d8' } } },
  // 신문 — 흰 바탕에 검은 선(가는 괘선), 헤드라인 크게, 빽빽하게(간격 좁게 · 본문 조금 작게)
  news: { name: '신문', tip: '헤드라인 크게 · 검은 괘선 · 빽빽하게',
    layout: { G: 12, M: 40, K: 0.95 },
    look: { accent: '#9b1c1c', muted: '#57534e', title: 'h2', head: 1.75,
      hero: { bg: '#ffffffff', pen: '#ff18181b', ink: '#27272a', hi: '#9b1c1c', scale: 1.3 },
      card: { fill: '#ffffffff', pen: '#ff3f3f46' }, step: { fill: '#ffffffff', pen: '#ff3f3f46' },
      tile: { fill: '#ffffffff', pen: '#ff18181b', num: '#9b1c1c', scale: 1.05 }, moving: { fill: '#fff5f5f4', pen: '#ff3f3f46' } } },
  // 잡지 — 주인공 크게, 여백 넉넉, 테두리 없는 옅은 면(남색·모래색)
  magazine: { name: '잡지', tip: '주인공 크게 · 넉넉한 여백 · 테두리 없는 면',
    layout: { G: 24, M: 72, K: 1.05, hero: [7, 9] },
    look: { accent: '#1f5f7a', muted: '#6b7280', title: 'h3', head: 1.6,
      hero: { bg: '#ff1f3a4d', pen: '#ff1f3a4d', ink: '#e6edf2', hi: '#ffd9a7', scale: 1.25 },
      card: { fill: '#fff6f3ee', pen: CLEAR }, step: { fill: '#ffedf3f6', pen: CLEAR },
      tile: { fill: '#fff6f3ee', pen: CLEAR, num: '#1f5f7a', scale: 1.15 }, moving: { fill: '#ffeef0f2', pen: CLEAR } } },
  // 인포그래픽 — 큰 숫자·그래프가 주인공(칸을 더 줌), 파랑 한 색, 옅은 파랑 면
  info: { name: '인포그래픽', tip: '큰 숫자 · 그래프 위주 · 파랑 한 색',
    layout: { boost: { 그래프: 1, '숫자 타일': 1 } },
    look: { accent: '#2a78d6', muted: '#64748b', title: 'h3', head: 1.5,
      hero: { bg: '#ff2a78d6', pen: '#ff2a78d6', ink: '#eaf2fc', hi: '#ffffff', scale: 1.2 },
      card: { fill: '#fff3f7fd', pen: CLEAR }, step: { fill: '#ffe8f1fb', pen: CLEAR },
      tile: { fill: '#ffffffff', pen: '#ff2a78d6', num: '#2a78d6', scale: 1.3 }, moving: { fill: '#ffeef3f9', pen: CLEAR } } },
}
export const STYLE_KEYS = Object.keys(DEEP_STYLES)
export const styleOf = key => DEEP_STYLES[key] || DEEP_STYLES.calm
// 꼭지 모양 바꿔 보기의 이름(속성 카드 「꼭지 모양」)
export const variantName = (shape, v) => ({ row: shape === '단계 카드' ? '한 줄' : '나란히', col: '위아래', grid: '두 줄', tall: '높게', short: '낮게' })[v] || v
