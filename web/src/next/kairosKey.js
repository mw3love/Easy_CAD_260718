// 내 KAIROS 키(2026-10-20 사용자 — 사람마다 자기 크레딧으로). 이 브라우저에만 두고, AI를 부르는 요청(대화·모델 목록·뜻으로 찾기·회의록)에만
// 머리말 `X-Kairos-Key`로 실어 보낸다. 서버는 그 키로 부르고 어디에도 남기지 않는다 — 비우면 서버 PC 키(`web/server.py` `_key`).
// ⚠ 키가 네트워크를 지나가므로 다른 PC가 http로 붙는 배포라면 https가 먼저다(같은 PC `localhost`는 괜찮음).
const STORE = 'mb-kairos-key'
export const KEY_RE = /^[!-~]{8,300}$/   // 키 모양(빈칸·한글 없음 — 머리말엔 한글이 못 실림, 서버 `_key`와 같은 규칙)

export const getKairosKey = () => { try { return localStorage.getItem(STORE) || '' } catch { return '' } }
export function setKairosKey(v) { try { if (v) localStorage.setItem(STORE, v); else localStorage.removeItem(STORE) } catch { /* 기억 못 하면 서버 키 */ } }
// fetch 머리말에 펼쳐 넣기 — 키가 없으면 빈 것
export const keyHeaders = () => { const k = getKairosKey(); return KEY_RE.test(k) ? { 'X-Kairos-Key': k } : {} }
