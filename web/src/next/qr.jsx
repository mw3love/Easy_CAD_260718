// 칠판 QR(2026-10-28 — 대회 시연: 큰 TV에 띄우면 객석이 휴대폰 카메라로 바로 들어옴). 부품 = qrcode-generator(버전 고정 — 직접 짜면 몇백 줄)
// 공유 창 「QR 크게」·발표 중 `Q`가 씀. 화면 가운데 큰 QR + 칠판 코드(손으로 칠 때 — 칠판 판 「칠판 코드로 열기」), 누르기·Esc·Q = 닫기
import { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { qrPath } from './qrpath.js'

export const QrSvg = ({ text, size }) => { const { n, d } = qrPath(text)
  return <svg data-testid="qr-svg" data-qr={text} viewBox={`0 0 ${n} ${n}`} shapeRendering="crispEdges" style={{ display: 'block', width: size, height: size }}>
    <rect width={n} height={n} fill="#fff" /><path d={d} fill="#000" /></svg> }

// link = QR에 넣을 주소, code = 칠판 코드(보기 링크면 비움 — 코드는 고치는 칠판으로 들어가는 열쇠), title = 칠판 이름, view = 보기 링크인가
export function QrBig({ link, code = '', title = '', view = false, pop, onClose }) {   // pop = 띄운 위 막대 팝업 이름(QR을 눌러 닫아도 그 팝업은 남게 — main.jsx `data-pop`)
  useEffect(() => {   // 칠판·발표 글쇠보다 먼저(capture) — Esc가 발표를 끝내지 않고 QR만 닫게
    const on = e => { if (e.key === 'Escape' || e.code === 'KeyQ') { e.preventDefault(); e.stopPropagation(); onClose() } }
    window.addEventListener('keydown', on, true); return () => window.removeEventListener('keydown', on, true)
  }, [onClose])
  return createPortal(<div data-testid="qr-big" data-qr-big data-pop={pop} onPointerDown={e => { e.stopPropagation(); onClose() }}
    style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(0,0,0,.72)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}>
    <div style={{ background: '#fff', color: '#18181b', borderRadius: 18, padding: '2.2vmin 3vmin', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1.2vmin', boxShadow: '0 10px 40px rgba(0,0,0,.4)', maxWidth: '92vw' }}>
      <div style={{ font: "700 max(18px, 3.2vmin) 'Pretendard', sans-serif", textAlign: 'center' }}>{title ? `「${title}」 ` : ''}{view ? '보기 링크' : '같이 쓰는 칠판'}</div>
      <QrSvg text={link} size="min(64vh, 80vw)" />
      {code && <div data-testid="qr-code" style={{ font: "700 max(22px, 5vmin) ui-monospace, Consolas, monospace", letterSpacing: '.18em' }}>{code.slice(0, 4)} {code.slice(4)}</div>}
      <div style={{ font: "400 max(12px, 1.8vmin) 'Pretendard', sans-serif", color: '#52525b', textAlign: 'center' }}>
        휴대폰 카메라로 비추면 열려요{code ? ' · 또는 칠판 판 「칠판 코드로 열기」에 이 코드' : view ? ' · 보기만 돼요(고치기·대화 없음)' : ''}</div>
      <div style={{ font: "400 max(11px, 1.4vmin) 'Pretendard', sans-serif", color: '#a1a1aa', wordBreak: 'break-all', textAlign: 'center' }}>{link} · 누르거나 Esc = 닫기</div>
    </div></div>, document.body)
}
