// 카드 접기 — 제목 줄 오른쪽 ▾/▸(데스크톱 플로팅 패널 `_collapse_btn`과 같게, 2026-10-19 사용자: 칠판이 좁으면 접어서 씀).
// 접으면 제목 줄만 남음(카드에 data-folded → index.html CSS가 첫 줄 말고 숨김). 접은 상태는 이 브라우저에 기억.
import { useState } from 'react'

export function useFold(key) {
  const k = 'mb-fold-' + key
  const [folded, setFolded] = useState(() => { try { return localStorage.getItem(k) === '1' } catch { return false } })
  const toggle = () => setFolded(f => { try { localStorage.setItem(k, f ? '0' : '1') } catch { /* 기억 못 해도 그만 */ } return !f })
  return [folded, toggle]
}

export const FoldBtn = ({ folded, onClick }) => <button onClick={onClick} title={folded ? '펴기' : '접기'}
  style={{ all: 'unset', cursor: 'pointer', width: 21, height: 21, flex: 'none', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 4, color: 'var(--mb-muted)', font: "400 12px 'Pretendard', sans-serif" }}>{folded ? '▸' : '▾'}</button>
