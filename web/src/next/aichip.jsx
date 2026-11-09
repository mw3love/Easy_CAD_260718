// ✨ AI 칩(2026-11-09 사용자 — 클로드 아티팩트 넷을 따라감, 시안 A + E1: Artifact `EFU8UFuHfTtSTDGC4V2vny`)
// 칠판에서 물건을 고르면 고른 것 오른쪽 위에 작은 「AI」 칩 → 누르면 작은 창: 큰 단추 둘(문서·슬라이드 — 2026-11-09 문서 통합 1단계: 디자인·HTML은 문서로 합침) + 입력 칸.
// 단추 한 번 = 고르기만(회색 채움), Enter·보내기 = 실행 — 두 번 누르기로 바로 실행은 안 함(실수로 크레딧이 듦).
// 단추 없이 말만 = 물건 하나면 그 물건의 💬 말풍선, 여럿이면 큰 대화창 질문. 실제 일은 Editor가 `onRun(kind, text)`로 대화창에 넘김.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

const F = "'Pretendard', sans-serif"
const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', seg: 'var(--mb-seg)', pick: 'var(--mb-pick)', acc: 'var(--mb-icon-acc)' }
// 아이콘 = Phosphor regular(MIT) — 시안에서 고른 그대로(앱 손그림 세트엔 넷 중 둘만 있음)
const P = {
  doc: 'M213.66,82.34l-56-56A8,8,0,0,0,152,24H56A16,16,0,0,0,40,40V216a16,16,0,0,0,16,16H200a16,16,0,0,0,16-16V88A8,8,0,0,0,213.66,82.34ZM160,51.31,188.69,80H160ZM200,216H56V40h88V88a8,8,0,0,0,8,8h48V216Zm-32-80a8,8,0,0,1-8,8H96a8,8,0,0,1,0-16h64A8,8,0,0,1,168,136Zm0,32a8,8,0,0,1-8,8H96a8,8,0,0,1,0-16h64A8,8,0,0,1,168,168Z',
  slide: 'M216,40H136V24a8,8,0,0,0-16,0V40H40A16,16,0,0,0,24,56V176a16,16,0,0,0,16,16H79.36L57.75,219a8,8,0,0,0,12.5,10l29.59-37h56.32l29.59,37a8,8,0,1,0,12.5-10l-21.61-27H216a16,16,0,0,0,16-16V56A16,16,0,0,0,216,40Zm0,136H40V56H216V176Z',
  ai: 'M197.58,129.06,146,110l-19-51.62a15.92,15.92,0,0,0-29.88,0L78,110l-51.62,19a15.92,15.92,0,0,0,0,29.88L78,178l19,51.62a15.92,15.92,0,0,0,29.88,0L146,178l51.62-19a15.92,15.92,0,0,0,0-29.88ZM137,164.22a8,8,0,0,0-4.74,4.74L112,223.85,91.78,169A8,8,0,0,0,87,164.22L32.15,144,87,123.78A8,8,0,0,0,91.78,119L112,64.15,132.22,119a8,8,0,0,0,4.74,4.74L191.85,144ZM144,40a8,8,0,0,1,8-8h16V16a8,8,0,0,1,16,0V32h16a8,8,0,0,1,0,16H184V64a8,8,0,0,1-16,0V48H152A8,8,0,0,1,144,40ZM248,88a8,8,0,0,1-8,8h-8v8a8,8,0,0,1-16,0V96h-8a8,8,0,0,1,0-16h8V72a8,8,0,0,1,16,0v8h8A8,8,0,0,1,248,88Z',
}
export const AI_KINDS = [['doc', '문서'], ['slide', '슬라이드']]
const NAME = Object.fromEntries(AI_KINDS)
const Icon = ({ k, s = 16 }) => <svg viewBox="0 0 256 256" width={s} height={s} aria-hidden="true" style={{ flex: 'none', fill: 'currentColor', color: C.acc }}><path d={P[k]} /></svg>
const CHIP_W = 52, WIN_W = 340

// box = 고른 것 전체의 화면 자리(px), size = 칠판 판 크기, n = 고른 개수
export function AiChip({ box, size, n, open, setOpen, onRun }) {
  const [kind, setKind] = useState(null), [draft, setDraft] = useState(''), ta = useRef(null), me = useRef(null), [dodge, setDodge] = useState(null)
  useEffect(() => { if (open) ta.current?.focus(); else { setKind(null); setDraft('') } }, [open])
  const cx0 = Math.max(8, Math.min(box.x + box.w - CHIP_W, size.w - CHIP_W - 8)), cy = Math.max(8, box.y - 32)
  // 오른쪽 위 속성 카드와 겹치면 그 카드 왼쪽으로 비킴(2026-11-09 진짜 확인 — 오른쪽 끝에 닿은 판에서 칩이 카드 위에 올라탐)
  useLayoutEffect(() => {
    const host = me.current?.offsetParent, card = host?.querySelector('[data-testid="props-card"]'); if (!host || !card) { if (dodge != null) setDodge(null); return }
    const h = host.getBoundingClientRect(), c = card.getBoundingClientRect(), l = c.left - h.left, t = c.top - h.top, w = open ? 0 : CHIP_W
    const hit = cx0 + w > l - 6 && cx0 < l + c.width && cy + 24 > t && cy < t + c.height, x = hit ? Math.max(8, l - CHIP_W - 8) : null
    if (x !== dodge) setDodge(x)
  })
  const cx = dodge ?? cx0
  const stop = e => e.stopPropagation()
  if (!open) return <button ref={me} data-testid="ai-chip" title="고른 것으로 만들기 — 문서·슬라이드·디자인·HTML (KAIROS)" onPointerDown={stop} onClick={() => setOpen(true)}
    style={{ all: 'unset', position: 'absolute', left: cx, top: cy, zIndex: 7, height: 24, padding: '0 9px 0 7px', display: 'flex', alignItems: 'center', gap: 4, borderRadius: 99, cursor: 'pointer', boxSizing: 'border-box',
      background: C.card, border: `1px solid ${C.line}`, boxShadow: '0 1px 4px rgba(0,0,0,.18)', font: `600 12px ${F}`, color: C.ink }}><Icon k="ai" s={14} />AI</button>
  const right = box.x + box.w + 12, wx = right + WIN_W <= size.w - 8 ? right : box.x - 12 - WIN_W >= 8 ? box.x - 12 - WIN_W : Math.max(8, size.w - WIN_W - 8)
  const wy = Math.max(8, Math.min(cy, size.h - 200))
  const run = () => { const t = draft.trim(); if (!kind && !t) { ta.current?.focus(); return } onRun(kind, t); setOpen(false) }
  const pick = k => { setKind(kind === k ? null : k); ta.current?.focus() }
  return <div data-testid="ai-panel" role="dialog" aria-label="고른 것으로 만들기" onPointerDown={stop} onWheel={stop} onKeyDown={e => { stop(e); if (e.key === 'Escape') setOpen(false) }}
    style={{ position: 'absolute', left: wx, top: wy, width: WIN_W, zIndex: 8, background: C.card, color: C.ink, border: `1px solid ${C.line}`, borderRadius: 12, boxShadow: '0 6px 20px rgba(0,0,0,.18)', font: `400 13px/1.5 ${F}` }}>
    <div style={{ display: 'flex', alignItems: 'center', padding: '8px 8px 7px 12px', borderBottom: `1px solid ${C.line}` }}>
      <b style={{ fontSize: 13 }}>고른 것 {n}개</b>
      <button data-testid="ai-close" title="닫기(Esc)" onClick={() => setOpen(false)} style={{ all: 'unset', marginLeft: 'auto', cursor: 'pointer', color: C.muted, fontSize: 14, padding: '0 6px', borderRadius: 6 }}>✕</button>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${AI_KINDS.length},1fr)`, gap: 6, padding: '10px 10px 4px' }}>
      {AI_KINDS.map(([k, name]) => <button key={k} data-testid="ai-kind" data-kind={k} aria-pressed={kind === k} onClick={() => pick(k)} className="mb-ai-kind"
        style={{ all: 'unset', cursor: 'pointer', boxSizing: 'border-box', height: 56, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 3, borderRadius: 8,
          border: `1px solid ${kind === k ? 'transparent' : C.line}`, background: kind === k ? C.pick : 'transparent', font: `${kind === k ? 700 : 500} 12.5px ${F}`, color: C.ink }}><Icon k={k} s={20} />{name}</button>)}
    </div>
    <div style={{ display: 'flex', gap: 6, alignItems: 'flex-end', padding: '6px 10px 10px' }}>
      <textarea ref={ta} data-testid="ai-input" rows={2} value={draft} placeholder={kind ? `${NAME[kind]} — 바라는 점 (없으면 Enter)` : '무엇을 할까요? 물어봐도 돼요'} onChange={e => setDraft(e.target.value)}
        onKeyDown={e => { stop(e); if (e.key === 'Escape') { setOpen(false); return } if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); run() } }}
        style={{ flex: 1, minWidth: 0, boxSizing: 'border-box', resize: 'none', border: `1px solid ${C.line}`, borderRadius: 8, padding: '6px 8px', font: `400 13px/1.5 ${F}`, background: 'transparent', color: C.ink, outline: 'none' }} />
      <button data-testid="ai-send" onClick={run} style={{ all: 'unset', cursor: 'pointer', flex: 'none', height: 30, padding: '0 12px', display: 'flex', alignItems: 'center', borderRadius: 7, background: 'var(--mb-accent)', color: '#fff', font: `700 12.5px ${F}` }}>보내기</button>
    </div>
  </div>
}
