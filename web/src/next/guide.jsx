// 빈 칠판 첫 안내(2026-10-26 대회 준비 — 처음 연 사람이 무엇부터 할지). 칠판이 비었을 때만 가운데에, 하나라도 놓이면 사라짐.
// 버튼 = 대화창 입력 칸으로(발표 자료는 「발표 자료 만들어 줘 — 주제: 」를 미리 써 둠 — 2026-11-08 「+」 이름표 대신)·회의 시작, 크레딧은 사용자가 보낼 때만 씀. × = 이 브라우저에선 다시 안 띄움.
import { useEffect, useRef, useState } from 'react'
import { keyHeaders } from './kairosKey.js'
import ICONS from './icons.json' with { type: 'json' }   // 위 막대와 같은 손그림 아이콘(2026-11-02 실검증 — 이모지는 폭이 달라 줄이 어긋났음)

const C = { ink: 'var(--mb-ink)', muted: 'var(--mb-muted)', line: 'var(--mb-line)', card: 'var(--mb-card)', group: 'var(--mb-group)' }
const KEY = 'mb-guide-off'

export function EmptyGuide({ onAsk, onDeep, onMeet, onExample, phone = false }) {   // phone = 휴대폰 화면(끌어다 놓기·두 번 누르기·F1이 없음 — 2026-11-06 휴대폰 점검)
  const [off, setOff] = useState(() => { try { return localStorage.getItem(KEY) === '1' } catch { return false } })
  // 좁은 창(=200% 확대 포함)에 대화창이 떠 있으면 남은 칠판 자리가 안내보다 좁아 대화창에 가려졌음(2026-11-09 better-interface 점검, 폭 720).
  // 그때만 칠판 가운데 대화창 위에 띄우고, 안내 줄을 누르면 비켜 줌(이 창에서만 — × 와 달리 기억 안 함)
  const box = useRef(null), [tight, setTight] = useState(false), [away, setAway] = useState(false)
  useEffect(() => { const el = box.current?.parentElement; if (!el) return
    const inset = parseFloat(getComputedStyle(el).getPropertyValue('--mb-right-inset')) || 0; setTight(inset > 0 && el.clientWidth - inset < 452) })
  const [, setTick] = useState(0)   // 창 폭이 바뀌면 다시 잼
  useEffect(() => { const fit = () => setTick(t => t + 1); window.addEventListener('resize', fit); return () => window.removeEventListener('resize', fit) }, [])
  const [deep, setDeep] = useState(false)   // 서버가 발표 자료를 할 수 있을 때만 그 줄(/api/models `jobs.slides`)
  useEffect(() => { if (off) return; fetch('/api/models', { headers: keyHeaders() }).then(r => r.json()).then(m => setDeep(!!m?.jobs?.slides)).catch(() => {}) }, [off])
  if (off || away) return null
  const close = () => { setOff(true); try { localStorage.setItem(KEY, '1') } catch { /* 기억 못 해도 그만 */ } }
  const rows = [['generate', 'KAIROS에게 묻기', phone ? '답 밑 「칠판에 붙이기」를 누르면 칠판에 메모로 남아요. 검색 답은 출처 카드와 함께.' : '물어본 답을 끌어다 놓으면 칠판에 메모로 남아요. 검색 답은 출처 카드와 함께.', onAsk],
    ['mic', '회의 받아 적기', '말한 사람별로 받아 적고, 끝내면 요약·결정·할 일이 칠판에.', onMeet],
    ...(deep ? [['board', '슬라이드 만들기', '주제 하나로 여러 장 — 글 장·그림 장, 만들면 바로 발표해요.', onDeep]] : []),   // 2026-11-08 Deep Mode(한 판)는 칠판 자료 우클릭 「정리 › 한 판으로」로 옮김
    ...(onExample ? [['frame', '예시 칠판 보기', '기능마다 KAIROS로 진짜 만든 예시 — 새 칠판으로 열려서 마음껏 고쳐 봐도 돼요.', onExample]] : [])]   // 2026-11-04 — 처음 방문이 예시 사본 대신 빈 칠판이 되며
  return <div ref={box} data-testid="empty-guide" style={{ position: 'absolute', zIndex: tight ? 6 : 5, top: '50%', left: tight ? '50%' : 'calc((100% - var(--mb-right-inset, 0px)) / 2)', transform: 'translate(-50%, -50%)',
    width: 'min(420px, calc(100% - 32px))', maxHeight: 'calc(100% - 24px)', overflowY: 'auto', boxSizing: 'border-box',   /* 200% 확대에서 위아래가 잘렸음(2026-11-10 1단계) */ background: C.card, border: `1px solid ${C.line}`, borderRadius: 14, padding: '16px 18px 12px',
    boxShadow: 'var(--mb-shadow)', font: "400 13px 'Pretendard', sans-serif", color: C.ink }}>
    <div style={{ display: 'flex', alignItems: 'center', marginBottom: 2 }}>
      <h2 style={{ margin: 0, font: "700 17px 'Pretendard', sans-serif", flex: 1 }}>무엇부터 해 볼까요?</h2>
      <button data-testid="empty-guide-close" aria-label="안내 닫기" onClick={close} title="이 안내 다시 보지 않기(이 브라우저)" className="mb-hit" style={{ position: 'relative', '--hit': '0 -4px', border: 'none', background: 'none', color: C.muted, cursor: 'pointer', fontSize: 15, padding: 2 }}>✕</button>
    </div>
    <div style={{ color: C.muted, marginBottom: 10 }}>KAIROS에게 물은 것이 쌓이고 정리되는 칠판이에요.</div>
    {rows.map(([icon, title, tip, go]) => <button key={title} className="mb-mi" data-testid={`empty-guide-${title}`} onClick={() => { if (tight) setAway(true); go() }}
      style={{ display: 'flex', alignItems: 'flex-start', gap: 10, width: '100%', textAlign: 'left', padding: '8px 10px', marginBottom: 4, border: `1px solid ${C.line}`, borderRadius: 10,
        background: C.group, color: C.ink, cursor: 'pointer', font: 'inherit' }}>
      <span aria-hidden className="mb-btn-icon" style={{ width: 20, height: 20, flex: 'none', display: 'block', color: 'var(--mb-icon)' }} dangerouslySetInnerHTML={{ __html: ICONS[icon].replace('<svg ', '<svg width="20" height="20" ') }} />
      <span><span style={{ display: 'block', fontWeight: 700 }}>{title}</span><span style={{ color: C.muted, fontSize: 12 }}>{tip}</span></span>
    </button>)}
    <div data-testid="empty-guide-tip" style={{ color: C.muted, fontSize: 12, marginTop: 8, lineHeight: 1.6 }}>{phone ? '한 손가락 = 칠판 옮기기 · 두 손가락 = 확대 · 위 칠판 이름 = 다른 칠판'
      : '그림·PDF·녹음 파일은 칠판에 끌어다 놓기 · 빈 곳 두 번 누르기 = 글 · F1 = 도움말'}</div>
  </div>
}
