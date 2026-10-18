// 발표(슬라이드쇼, 2026-10-19 사용자와 정함 — 계획서 §8 항목61 4-b ②): 프레임 순서대로 한 장씩 화면에 꽉 차게, 밖은 가림(출력한 쪽과 같은 모습).
// 넘길 때 0.4초 카메라 이동(칠판 위를 옮겨 다니는 느낌) — M으로 「바로 넘김」. → · 스페이스 · 클릭 = 다음, ← = 이전, Esc = 끝. 밝은 종이 잉크로(내보내기와 같음).
import { useEffect, useState } from 'react'
import { Item, setInkDark } from './render.jsx'

const LIGHT = { '--mb-ink': '#27272a', '--mb-muted': '#71717a', '--mb-board': '#ffffff', '--mb-line': '#e4e4e7', '--mb-card': '#ffffff' }

// frames = [{ id, name, box: {x,y,w,h} }] 순서대로, order = 그릴 [아이템, 순번](프레임 자신은 뺀 것), start = 시작 장
export function Presenter({ frames, order, onBoard, routes, start = 0, onClose }) {
  const [i, setI] = useState(start), [glide, setGlide] = useState(true), [vw, setVw] = useState(() => ({ w: window.innerWidth, h: window.innerHeight }))
  const [wasDark] = useState(() => { const d = document.documentElement.dataset.theme === 'dark'; setInkDark(false); return d })   // 첫 그리기 전에 밝은 잉크
  useEffect(() => {   // 전체 화면, 끝나면 잉크·화면 되돌림
    try { document.documentElement.requestFullscreen?.()?.catch?.(() => {}) } catch { /* 전체 화면이 안 되면 창 크기로 */ }
    const onFs = () => { if (!document.fullscreenElement) onClose() }
    const onResize = () => setVw({ w: window.innerWidth, h: window.innerHeight })
    document.addEventListener('fullscreenchange', onFs); window.addEventListener('resize', onResize)
    return () => { setInkDark(wasDark); document.removeEventListener('fullscreenchange', onFs); window.removeEventListener('resize', onResize); if (document.fullscreenElement) document.exitFullscreen?.().catch?.(() => {}) }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  const n = frames.length, go = d => setI(k => Math.max(0, Math.min(n - 1, k + d)))
  useEffect(() => {   // 칠판 글쇠보다 먼저(capture) — 발표 중엔 칠판 단축키가 안 돎
    const onKey = e => {
      const k = e.key; e.stopPropagation()
      if (k === 'Escape') { e.preventDefault(); onClose(); return }
      if (['ArrowRight', 'ArrowDown', 'PageDown', ' ', 'Enter'].includes(k)) { e.preventDefault(); go(1) }
      else if (['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace'].includes(k)) { e.preventDefault(); go(-1) }
      else if (k === 'Home') go(-n); else if (k === 'End') go(n)
      else if (k.toLowerCase() === 'm' || k === 'ㅡ') setGlide(g => !g)
    }
    window.addEventListener('keydown', onKey, true); return () => window.removeEventListener('keydown', onKey, true)
  }, [n])   // eslint-disable-line react-hooks/exhaustive-deps
  const f = frames[i]; if (!f) return null
  const { w: W, h: H } = vw, b = f.box, k = Math.min(W / b.w, H / b.h), hw = b.w * k, hh = b.h * k, hx = (W - hw) / 2, hy = (H - hh) / 2
  const tf = `translate(${hx - b.x * k}px, ${hy - b.y * k}px) scale(${k})`
  return <div data-testid="presenter" onPointerDown={e => { e.stopPropagation(); if (e.button === 0) go(1); else if (e.button === 2) go(-1) }} onContextMenu={e => e.preventDefault()}
    style={{ position: 'fixed', inset: 0, zIndex: 1000, background: '#000', cursor: 'none', ...LIGHT }}>
    <svg width={W} height={H} style={{ display: 'block' }}>
      <rect x={hx} y={hy} width={hw} height={hh} fill="#ffffff" />
      <g style={{ transform: tf, transformOrigin: '0 0', transition: glide ? 'transform .4s ease-in-out' : 'none', '--z': k }}>
        {order.map(([it, idx]) => <Item key={it._id} it={it} idx={idx} onBoard={onBoard[idx]} route={routes.get(idx)} labels="inline" />)}
      </g>
      {/* 프레임 밖 가림(구멍 뚫린 검은 판) — 출력한 쪽과 같은 범위만 보임 */}
      <path d={`M0,0 H${W} V${H} H0 Z M${hx},${hy} V${hy + hh} H${hx + hw} V${hy} Z`} fill="#000" fillRule="evenodd" />
    </svg>
    <div style={{ position: 'absolute', right: 16, bottom: 12, color: 'rgba(255,255,255,.55)', font: "500 12px 'Pretendard', sans-serif", pointerEvents: 'none' }}>
      {i + 1} / {n}{f.name ? ` · ${f.name}` : ''} · {glide ? '이동' : '바로'}(M)</div>
  </div>
}
