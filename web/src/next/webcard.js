// 웹 카드(§8 항목61 4-b ①', 2026-10-18) — 주소 → 칠판 위 칸. 들어가는 사이트(유튜브 재생 주소·위키백과 등)는 칸 안에 실제 페이지,
// 막는 사이트(네이버·구글·깃허브 등 — 서버가 응답 머리말로 판단, `web/server.py` `link_info`)는 제목·대표 그림·주소 카드 + 「새 탭에서 열기」.
// .ecad 새 종류 `web` = { rect, url, title, desc, icon·thumb(data 주소), embed(칸 안에 넣을 주소), frameable, zoom(칸 안 페이지 배율) }. 데스크톱은 보존만.
// 2026-10-19 사용자: 한 번 누르면 칸 안 조작(유튜브는 바로 재생), 페이지 배율, 막힌 사이트 빈 카드 = 아이콘·설명, 많이 줄이면 페이지 잠재움.

export const WEB_HEAD = 40   // 위 띠(제목 + 주소) 높이 — 내보내기·PDF에도 제목·주소가 남게

// 붙여넣은 글이 주소 하나면 그 주소(www. 로 시작하면 https 붙임), 아니면 null
export function normalizeUrl(text) {
  const t = String(text || '').trim()
  if (!t || /\s/.test(t)) return null
  const u = /^https?:\/\//i.test(t) ? t : /^www\.[^/]+\.[a-z]{2,}/i.test(t) ? 'https://' + t : null
  if (!u) return null
  try { const p = new URL(u); return p.hostname.includes('.') || p.hostname === 'localhost' ? p.href : null } catch { return null }
}

// 재생용(칸 안에 넣는) 주소 — 유튜브(보기·짧은 영상·라이브·youtu.be, 시작 시각 t 유지)·비메오. 해당 없으면 ''
export function embedUrl(url) {
  let p; try { p = new URL(url) } catch { return '' }
  const h = p.hostname.replace(/^(www|m|music)\./, '')
  const secs = v => { if (!v) return 0; if (/^\d+$/.test(v)) return +v; const m = v.match(/^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$/); return m ? (+m[1] || 0) * 3600 + (+m[2] || 0) * 60 + (+m[3] || 0) : 0 }
  let id = ''
  if (h === 'youtu.be') id = p.pathname.slice(1).split('/')[0]
  else if (h === 'youtube.com') id = p.pathname === '/watch' ? p.searchParams.get('v') || '' : (p.pathname.match(/^\/(?:shorts|live|embed)\/([\w-]+)/) || [])[1] || ''
  if (id && /^[\w-]{6,}$/.test(id)) { const s = secs(p.searchParams.get('t') || p.searchParams.get('start')); return `https://www.youtube.com/embed/${id}${s ? `?start=${s}` : ''}` }
  if (h === 'vimeo.com') { const v = (p.pathname.match(/^\/(\d+)/) || [])[1]; if (v) return `https://player.vimeo.com/video/${v}` }
  return ''
}

export const siteOf = url => { try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url } }

// 서버에 물어보기 — 서버가 없으면 재생 주소가 있을 때만 칸 안에(유튜브·비메오는 넣기를 허락함), 나머지는 카드
export async function fetchLinkInfo(url) {
  const embed = embedUrl(url)
  try {
    const r = await fetch(`/api/link?url=${encodeURIComponent(url)}&embed=${encodeURIComponent(embed)}`)
    if (r.ok) { const j = await r.json(); return { url, embed, title: j.title || '', desc: j.desc || '', icon: j.icon || '', thumb: j.thumb || '', frameable: !!j.frameable } }
  } catch { /* 서버 없음 */ }
  return { url, embed, title: '', desc: '', icon: '', thumb: '', frameable: !!embed }
}

// 카드 아이템(칠판 좌표 가운데 cx, cy) — 크기: 영상 16:9, 칸 안 페이지는 넓게, 막힌 사이트는 그림 카드
export function webCardFields(info) {
  const w = info.frameable ? (info.embed ? 480 : 640) : 320
  const body = info.frameable ? (info.embed ? 270 : 420) : info.thumb ? 168 : WEB_INFO_H   // 그림도 없으면 아이콘·설명 칸
  const f = { type: 'web', url: info.url, title: info.title || '', rect: [0, 0, w, WEB_HEAD + body], frameable: !!info.frameable }
  if (info.embed) f.embed = info.embed
  if (info.thumb) f.thumb = info.thumb
  if (info.icon) f.icon = info.icon
  if (info.desc) f.desc = info.desc
  return f
}

export const WEB_INFO_H = 76   // 대표 그림 없는 막힌 사이트의 몸통(아이콘 + 설명 두 줄)
export const WEB_ZOOMS = [0.5, 0.75, 1]   // 칸 안 페이지 배율(속성 카드)
export const WEB_SLEEP_PX = 200   // 화면에서 카드 폭이 이보다 작으면 칸 안 페이지를 끔(그림·이름만) — 페이지 하나가 탭 하나만큼 무거움

export const isYoutube = it => /^https:\/\/www\.youtube\.com\/embed\//.test(it.embed || '')
// 칸 안에 넣을 주소(재생 주소가 있으면 그것). 유튜브는 바깥에서 「재생」을 보낼 수 있게 enablejsapi=1
export const frameSrc = (it, noFs) => (isYoutube(it) ? it.embed + (it.embed.includes('?') ? '&' : '?') + 'enablejsapi=1' + (noFs ? '&fs=0' : '') : it.embed || it.url)   // noFs = 유튜브 전체 화면 단추 숨김(발표 A안)

// 유튜브 카드에 명령 보내기(IFrame API — 카드 한 번 누르기 = 바로 재생). target = 아이템 id 또는 iframe 자체.
// 발표 중엔 뒤 칠판에도 같은 id 칸이 있어 id로 찾으면 숨은 칠판 칸이 재생됨(2026-10-20 사용자: 소리 둘·발표 화면은 멈춤) — 발표는 iframe을 넘김
function ytCommand(target, func) {
  const f = typeof target === 'string' ? document.querySelector(`iframe[data-webid="${CSS.escape(target)}"]`) : target
  const w = f?.contentWindow; if (!w) return
  w.postMessage(JSON.stringify({ event: 'listening', id: f.getAttribute('data-webid'), channel: 'widget' }), 'https://www.youtube.com')   // 먼저 「듣고 있음」(API 연결 인사)
  w.postMessage(JSON.stringify({ event: 'command', func, args: [] }), 'https://www.youtube.com')
}
export const playYoutube = target => ytCommand(target, 'playVideo')
// 재생 중인지 — 「듣고 있음」을 보낸 칸은 유튜브가 상태를 알려 줌(infoDelivery.playerState, 1 = 재생 중)
const ytState = new WeakMap()
if (typeof window !== 'undefined') window.addEventListener('message', e => {
  if (e.origin !== 'https://www.youtube.com') return
  let d; try { d = typeof e.data === 'string' ? JSON.parse(e.data) : e.data } catch { return }
  const st = d?.info?.playerState; if (st != null && e.source) ytState.set(e.source, st)
})
// 재생 ⇄ 일시정지(발표의 Space — 키보드는 발표가 가지므로 유튜브 대신, 2026-10-20)
export function toggleYoutube(f) { ytCommand(f, ytState.get(f?.contentWindow) === 1 ? 'pauseVideo' : 'playVideo') }
// 한 영역(칠판 등) 밖의 유튜브 칸을 모두 멈춤 — 발표를 열면 뒤 칠판 영상은 멈춤
export function pauseYoutubeOutside(root) {
  for (const f of document.querySelectorAll('iframe[data-webid]')) if (!root?.contains(f) && /youtube\.com\/embed\//.test(f.src)) ytCommand(f, 'pauseVideo')
}

// 오른쪽 위 「새 탭에서 열기」 단추 자리(아이템 안 좌표)
export function openBtnRect(it) { const [x, y, w] = it.rect, s = 24; return { x: x + w - s - 8, y: y + (WEB_HEAD - s) / 2, w: s, h: s } }
