// 데스크톱 순서도·안테나 심볼 모양 — `tools/export_web_symbols.py`가 데스크톱 경로를 100×100 상자로 뽑은 symbols.json을 상자에 맞춰 그린다.
// 비율 따라 모양이 바뀌는 둘(시작/끝 둥근 끝·지연 반원)만 여기서 직접 그린다(데스크톱 `_sym_terminal`·`_sym_delay`와 같은 식).
import SYMBOLS from '../symbols.json' with { type: 'json' }

// 도형 카드에서 클릭만 해 놓을 때의 기본 크기 — 카드 아이콘도 이 비율로 그림(2026-10-23 사용자: 원 아이콘은 타원, 삼각형은 납작했음).
// 사각형 3:2(사용자 선택 — 데스크톱 정사각 120×120을 바꿈), 원 = 정원, 삼각형 = 정삼각형(데스크톱 `_PALETTE_TRIANGLE_WH`), 그 밖 심볼 = 데스크톱 `_PALETTE_SYM_WH`
export const shapeWH = key => ({ rect: [120, 80], ellipse: [100, 100], 'sym:triangle': [77.94, 90] })[key] || [120, 72]

// 100×100 경로(M·L·C 좌표 쌍)를 상자에 맞게 늘린 d
const fitD = (d, kx, ky, tx = 0, ty = 0) => { let i = 0; return d.replace(/-?[\d.]+(?:e-?\d+)?/g, v => { const r = i++ % 2 ? ty + +v * ky : tx + +v * kx; return +r.toFixed(3) }) }
// → { d } (상자 안 좌표 — 늘림을 미리 계산해 선 굵기가 다른 도형처럼 확대·축소를 따라감)
export function symbolPath(kind, w, h) {
  // 세로로 긴 시작/끝도 데스크톱처럼(addRoundedRect — 위아래가 반원, 옆은 곧음). 2026-10-17 3단계 대조 시험에서 어긋남 발견
  if (kind === 'terminal') { const r = Math.min(h, w) / 2; return { d: `M${r},0 H${w - r} A${r},${r} 0 0 1 ${w},${r} V${h - r} A${r},${r} 0 0 1 ${w - r},${h} H${r} A${r},${r} 0 0 1 0,${h - r} V${r} A${r},${r} 0 0 1 ${r},0 Z` } }
  // 지연 = 폭 62%까지 곧고 반지름 h/2 반원(`_sym_delay` — 반원이 상자 밖으로 나갈 수 있음도 같게)
  if (kind === 'delay') { const sx = w * 0.62, r = h / 2; return { d: `M0,0 H${sx} A${r},${r} 0 0 1 ${sx},${h} H0 Z` } }
  const sym = SYMBOLS[kind]
  if (!sym) return { d: `M0,0 H${w} V${h} H0 Z` }   // 모르는 종류는 상자로
  if (sym.fit === 'keep') { const k = Math.min(w / 100, h / 100); return { d: fitD(sym.d, k, k, (w - 100 * k) / 2, (h - 100 * k) / 2) } }
  return { d: fitD(sym.d, w / 100, h / 100) }
}
