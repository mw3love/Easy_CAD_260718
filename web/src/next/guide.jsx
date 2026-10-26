// 빈 칠판 첫 안내(2026-10-26 대회 준비 — 처음 연 사람이 무엇부터 할지). 칠판이 비었을 때만 가운데에, 하나라도 놓이면 사라짐.
// 버튼 = 대화창 입력 칸으로(그 길 이름표까지)·회의 시작, 크레딧은 사용자가 보낼 때만 씀. × = 이 브라우저에선 다시 안 띄움.
import { useEffect, useState } from 'react'
import { keyHeaders } from './kairosKey.js'

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', group: 'var(--mb-group)' }
const KEY = 'mb-guide-off'

export function EmptyGuide({ onAsk, onDeep, onMeet }) {
  const [off, setOff] = useState(() => { try { return localStorage.getItem(KEY) === '1' } catch { return false } })
  const [deep, setDeep] = useState(false)   // 서버가 Deep Mode를 할 수 있을 때만 그 줄(대화창 「+」와 같은 기준 — /api/models `jobs.deep`)
  useEffect(() => { if (off) return; fetch('/api/models', { headers: keyHeaders() }).then(r => r.json()).then(m => setDeep(!!m?.jobs?.deep)).catch(() => {}) }, [off])
  if (off) return null
  const close = () => { setOff(true); try { localStorage.setItem(KEY, '1') } catch { /* 기억 못 해도 그만 */ } }
  const rows = [['💬', 'KAIROS에게 묻기', '물어본 답을 끌어다 놓으면 칠판에 메모로 남아요. 검색 답은 출처 카드와 함께.', onAsk],
    ['🎙', '회의 받아 적기', '말한 사람별로 받아 적고, 끝내면 요약·결정·할 일이 칠판에.', onMeet],
    ...(deep ? [['📰', 'Deep Mode', '주제 하나로 칠판 한 판 — 숫자·그래프·요약 그림까지, 끝까지 고칠 수 있게.', onDeep]] : [])]
  return <div data-testid="empty-guide" style={{ position: 'absolute', zIndex: 5, top: '50%', left: 'calc((100% - var(--mb-right-inset, 0px)) / 2)', transform: 'translate(-50%, -50%)',
    width: 'min(420px, calc(100% - 32px))', boxSizing: 'border-box', background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, padding: '16px 18px 12px',
    boxShadow: '0 8px 24px rgba(0,0,0,.12)', font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 2 }}>
      <span style={{ font: "700 17px 'Pretendard', sans-serif", flex: 1 }}>무엇부터 해 볼까요?</span>
      <button data-testid="empty-guide-close" onClick={close} title="이 안내 다시 보지 않기(이 브라우저)" style={{ border: 'none', background: 'none', color: C.muted, cursor: 'pointer', fontSize: 15, padding: 2 }}>✕</button>
    </div>
    <div style={{ color: C.muted, marginBottom: 10 }}>KAIROS에게 물은 것이 쌓이고 정리되는 칠판이에요.</div>
    {rows.map(([icon, title, tip, go]) => <button key={title} className="mb-mi" data-testid={`empty-guide-${title}`} onClick={go}
      style={{ display: 'flex', alignItems: 'flex-start', gap: 10, width: '100%', textAlign: 'left', padding: '8px 10px', marginBottom: 4, border: `1px solid ${C.line}`, borderRadius: 10,
        background: C.group, color: C.ink, cursor: 'pointer', font: 'inherit' }}>
      <span style={{ fontSize: 18, lineHeight: '20px' }}>{icon}</span>
      <span><span style={{ display: 'block', fontWeight: 700 }}>{title}</span><span style={{ color: C.muted, fontSize: 12 }}>{tip}</span></span>
    </button>)}
    <div style={{ color: C.muted, fontSize: 12, marginTop: 8, lineHeight: 1.6 }}>그림·PDF·녹음 파일은 칠판에 끌어다 놓기 · 빈 곳 두 번 누르기 = 글 · F1 = 도움말</div>
  </div>
}
