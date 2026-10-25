// 움직이는 카드(§8 항목66 4단계, 2026-10-25) — 정리 문서 카드(`doc`)에 「움직임」 표시(`live: true`)가 붙으면 그 카드만 스크립트가 돈다.
// 틀: iframe `sandbox="allow-scripts"`(same-origin 없이 = 칠판·로그인·저장소에 못 닿음) + 카드 HTML 맨 앞에 우리 머리(CSP = 인터넷 금지).
// 맨 앞이어야 카드의 어떤 스크립트보다 CSP가 먼저 선다(4-0 실측 — <head> 안에 끼우면 그 앞 스크립트는 CSP 없이 돎). 순수(DOM 없음), 데스크톱 `core_web.py`와 같은 글.
export const LIVE_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:"
// 스크립트 없는 문서(정리 문서·끌어 놓은 HTML 파일)를 크게 볼 때 — 그림·글꼴은 지금 카드 칸(`sandbox=""`)처럼 바깥 것도 됨, 스크립트만 끔
export const STATIC_CSP = "default-src 'none'; style-src 'unsafe-inline' https:; img-src data: blob: https: http:; font-src data: https:"
export const LIVE_MAX = 200_000   // 카드 HTML 상한(자) — 4-0 실측 카드는 3~12KB, 넘으면 띄우지 않고 자리 글
export const LIVE_W = 720, LIVE_H = 480   // 카드가 그려지는 기준 칸(지시문과 같은 값) — 칠판 카드는 이 폭에 맞춰 줄이고 늘림

// 다 열린 뒤 resize 한 번 — 스크립트로 만든 iframe은 카드 스크립트가 처음 돌 때 innerWidth가 0이라 크기를 0배로 잡는 카드가 있었음(4-0 opus 둘)
const KICK = "<script>addEventListener('load',()=>(function k(){innerWidth?dispatchEvent(new Event('resize')):requestAnimationFrame(k)})())</script>"
const head = csp => `<!doctype html><meta http-equiv="Content-Security-Policy" content="${csp}"><meta charset="utf-8">`
const body = html => String(html || '').replace(/^\s*(?:<!--[\s\S]*?-->\s*)*<!doctype[^>]*>/i, '')   // 카드의 doctype은 뗌(우리 것이 먼저)
const attr = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))

export const isLive = it => it?.type === 'doc' && !!it.live
export const liveFits = it => isLive(it) && !!it.html && it.html.length <= LIVE_MAX
export const liveSrc = html => head(LIVE_CSP) + KICK + body(html)
export const staticSrc = html => head(STATIC_CSP) + body(html)
// 「크게 보기」 새 탭에 둘 페이지 — 앱 주소의 blob이라 그 페이지 자체엔 스크립트가 없어야 함. 움직이는 카드는 그 안의 틀(iframe)에서만 돎
export function bigPage(it) {
  if (!liveFits(it)) return staticSrc(it?.html)
  return head(LIVE_CSP) + `<title>${attr(it.title || '움직이는 카드')}</title><style>html,body{margin:0;height:100%;background:#fff}iframe{border:0;width:100%;height:100%;display:block}</style>`
    + `<iframe sandbox="allow-scripts" csp="${LIVE_CSP}" srcdoc="${attr(liveSrc(it.html))}"></iframe>`
}
