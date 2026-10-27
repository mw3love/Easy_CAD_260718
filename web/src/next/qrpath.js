// 칠판 QR 계산(순수 — 화면 시험 `e2e/flow46`도 이걸로 되만들어 대조). 부품 = qrcode-generator(버전 고정 — 직접 짜면 몇백 줄), 그리기는 `qr.jsx`
import qrcode from 'qrcode-generator'

const QUIET = 4   // QR 둘레 흰 여백(표준 4칸 — 모자라면 카메라가 못 읽음)
// 글 → { n: 한 변 칸 수(여백 포함), d: 검은 칸 경로 }
export function qrPath(text) {
  const q = qrcode(0, 'M'); q.addData(text, 'Byte'); q.make()   // 0 = 글 길이에 맞는 가장 작은 판, M = 15% 가려져도 읽힘
  const m = q.getModuleCount(); let d = ''
  for (let r = 0; r < m; r++) for (let c = 0; c < m; c++) if (q.isDark(r, c)) d += `M${c + QUIET} ${r + QUIET}h1v1h-1z`
  return { n: m + 2 * QUIET, d }
}
