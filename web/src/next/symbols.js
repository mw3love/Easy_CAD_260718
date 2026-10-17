// 데스크톱 순서도·안테나 심볼 모양 — `tools/export_web_symbols.py`가 데스크톱 경로를 100×100 상자로 뽑은 symbols.json을 상자에 맞춰 그린다.
// 비율 따라 모양이 바뀌는 둘(시작/끝 둥근 끝·지연 반원)만 여기서 직접 그린다(데스크톱 `_sym_terminal`·`_sym_delay`와 같은 식).
import SYMBOLS from '../symbols.json'

// → { d, transform? } (transform이 있으면 100×100 경로를 늘림, vector-effect로 선 굵기는 그대로)
export function symbolPath(kind, w, h) {
  if (kind === 'terminal') { const r = Math.min(h, w) / 2; return { d: `M${r},0 H${w - r} A${r},${r} 0 0 1 ${w - r},${h} H${r} A${r},${r} 0 0 1 ${r},0 Z` } }
  if (kind === 'delay') { const r = Math.min(h / 2, w); return { d: `M0,0 H${w - r} A${r},${r} 0 0 1 ${w - r},${h} H0 Z` } }
  const sym = SYMBOLS[kind]
  if (!sym) return { d: `M0,0 H${w} V${h} H0 Z` }   // 모르는 종류는 상자로
  if (sym.fit === 'keep') { const k = Math.min(w / 100, h / 100); return { d: sym.d, transform: `translate(${(w - 100 * k) / 2},${(h - 100 * k) / 2}) scale(${k})` } }
  return { d: sym.d, transform: `scale(${w / 100},${h / 100})` }
}
