// 발표(슬라이드쇼, 2026-10-18 사용자와 정함 — 계획서 §8 항목61 4-b ②): 프레임 순서대로 한 장씩 화면에 꽉 차게, 밖은 가림(출력한 쪽과 같은 범위).
// 넘길 때 0.4초 카메라 이동(실제 칠판 위를 옮겨 감) — M으로 「바로 넘김」. 레이저 = 따로 켜는 커서(` · L, 도구와 같이). 우클릭·휠 클릭 끌기 = 화면 이동(편집 화면과 같음). 마지막 장에서 멈춤(끝 = Esc). → · 스페이스 · 휠 = 다음(클릭으로는 안 넘김), ← = 이전, Esc = 끝, D = 밝게/어둡게(기본 = 칠판 화면).
// 판서(2차): 마우스를 움직이면 아래 막대(◀ ▶ · 네모 · 펜 · 형광펜 · 화살표 · 글자 · 지우개) — 도구를 고르면 클릭·끌기 = 그리기, 그린 것은 칠판 「판서」 레이어에 진짜 도형으로(Ctrl+Z 되돌리기).
import { useEffect, useRef, useState } from 'react'
import { Item, setInkDark } from './render.jsx'
import { APP_FONT, METRICS, PT, TEXT_MARGIN } from './geom.js'
import { pauseYoutubeOutside, playYoutube, toggleYoutube } from './webcard.js'

const THEMES = {
  light: { '--mb-ink': '#27272a', '--mb-muted': '#71717a', '--mb-board': '#ffffff', '--mb-line': '#e4e4e7', '--mb-card': '#ffffff' },
  dark: { '--mb-ink': '#ffffff', '--mb-muted': '#8a98a8', '--mb-board': '#1e2731', '--mb-line': '#2a3542', '--mb-card': '#171e26' },   // next.html 어두운 값
}
// 판서 색 다섯(2026-10-18 사용자: 「빨 초 파 검 흰, 5개 이내」 — 칠판 잉크 규칙상 검·흰은 화면 따라 서로 바뀌어 한 칸 「검/흰」, 대신 형광펜용 노랑)
const COLORS = [['#ef4444', '빨강', 'KeyR'], ['#22c55e', '초록', 'KeyG'], ['#3b82f6', '파랑', 'KeyB'], ['#facc15', '노랑', 'KeyY'], ['#1f1f1f', '검정(어두운 화면에선 흰색)', 'KeyK']]
const argb = (hex, a = 'ff') => '#' + a + hex.slice(1)
const SIZES = { line: [2, 4, 8], hl: [12, 20, 32] }   // 굵기 세 단계(화면 px) — 펜·네모·화살표 / 형광펜
const I = (d, extra) => <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...extra}>{d}</svg>
// [id, 아이콘, 이름, 단축키 글자, 단축키 code들]
const TOOLS = [
  ['pen', I(<path d="M12.5 3 L15 5.5 L6.5 14 L3.5 14.5 L4 11.5 Z" />), '펜', '1 · P', ['Digit1', 'KeyP']],
  ['hl', I(<><path d="M10.5 3 L15 7.5 L9 13.5 L4.5 9 Z" /><path d="M4.5 9 L3 14.5 L8 13" /></>), '형광펜', '2 · H', ['Digit2', 'KeyH']],
  ['rect', I(<rect x="3" y="4.5" width="12" height="9" rx="1" />), '네모', '3 · S', ['Digit3', 'KeyS']],
  ['arrow', I(<><path d="M4 14 L14 4" /><path d="M8 4 H14 V10" /></>), '화살표', '4 · A', ['Digit4', 'KeyA']],
  ['text', I(<><path d="M4 4.5 H14" /><path d="M9 4.5 V14" /></>, { strokeWidth: 2 }), '글자', '5 · T', ['Digit5', 'KeyT']],
  ['erase', I(<><path d="M7 15 L3.5 11.5 L10.5 4.5 L15 9 L9 15 Z" /><path d="M7 15 H15" /></>), '지우개', '6 · E (두 번 = 이 장 판서 지우기)', ['Digit6', 'KeyE']],
]
const IDLE_MS = 2000
const BIG_BAND = 64   // 영상 크게 보기의 위 검은 띠 — 「⤡ 원래 크기로」가 영상(유튜브 단추)과 겹치지 않게
// 발표 속 유튜브 크게 보기(2026-10-20 사용자) — 발표 전체 화면 안에서 유튜브 전체 화면을 켜면 크롬·유튜브가 서로 다르게 알아 끝내기 단추·F가 안 먹음(실측).
// 그래서 유튜브 전체 화면 단추는 숨기고(fs=0), 카드 제목 띠 「⤢ 크게 보기」 = 그 영상만 검은 바탕에 화면 꽉(사진 크게 보기처럼), 영상 밖·띠·「원래대로」 = 돌아옴.
// 검토한 대안: 영상을 누를 때 발표 전체 화면을 잠깐 풂(B) — 맛본 사용자: 크롬 창·윈도우 막대가 나와 이상함.

// 넘길 때 미끄러짐 — SVG transform 속성을 직접 움직임(requestAnimationFrame). CSS transform 아래에선 크롬이 웹 카드 칸 안 페이지(iframe)를
// 그리지 않아(검은·흰 칸 — 2026-10-18 실험: 같은 자리를 속성으로 바꾸자 바로 보임) CSS 전환을 못 씀. ms = 0이면 바로
function useGlide(target, ms) {
  const [cur, setCur] = useState(target), from = useRef(target), raf = useRef(0), key = target.join(',')
  useEffect(() => {
    cancelAnimationFrame(raf.current)
    if (!ms) { from.current = target; setCur(target); return }
    const a = from.current, t0 = performance.now()
    const step = now => { const u = Math.min(1, (now - t0) / ms), e = u < 0.5 ? 2 * u * u : 1 - (-2 * u + 2) ** 2 / 2   // ease-in-out
      const v = target.map((t, j) => a[j] + (t - a[j]) * e); from.current = v; setCur(v); if (u < 1) raf.current = requestAnimationFrame(step) }
    raf.current = requestAnimationFrame(step); return () => cancelAnimationFrame(raf.current)
  }, [key, ms])   // eslint-disable-line react-hooks/exhaustive-deps
  return cur
}

// frames = [{ id, name, box }] 순서대로, order = 그릴 [아이템, 순번](프레임 자신은 뺀 것), start = 시작 장, dark = 칠판 화면이 어두운가
// onAdd(아이템 설계[]) = 판서 레이어에 넣기, onErase(칠판 점, 허용 거리) = 그 자리 판서 지우기, onUndo = 되돌리기
export function Presenter({ frames, order, onBoard, routes, start = 0, dark: dark0 = false, onAdd, onErase, onUndo, onClearNotes, onFlipArrow, onClose }) {   // onClearNotes(칠판 상자) = 그 안 판서 지우기
  const [list, setList] = useState(null), listRef = useRef(null)   // 장 목록(Tab — 2026-10-18 사용자: 발표 중 특정 장으로 바로) = { typed: 입력 중 번호 }
  const [i, setI] = useState(start), [glide, setGlide] = useState(true), [vw, setVw] = useState(() => ({ w: window.innerWidth, h: window.innerHeight }))
  const [dark, setDark] = useState(dark0), [wasDark] = useState(() => { setInkDark(dark0); return document.documentElement.dataset.theme === 'dark' })   // 첫 그리기 전에 잉크
  const [penColor, setPenColor] = useState('#ef4444'), [hlColor, setHlColor] = useState('#facc15'), [size, setSize] = useState(1)   // 펜·형광펜 색은 따로(펜 = 빨강, 형광펜 = 노랑에서 시작), 굵기 = 0·1·2
  const [tool, setTool] = useState(null), [draft, setDraft] = useState(null), [textAt, setTextAt] = useState(null), [awake, setAwake] = useState(true), idle = useRef(0), barHover = useRef(false)
  useEffect(() => {   // 전체 화면, 끝나면 잉크·화면 되돌림
    try { document.documentElement.requestFullscreen?.()?.catch?.(() => {}) } catch { /* 전체 화면이 안 되면 창 크기로 */ }
    const onFs = () => { if (!document.fullscreenElement) onClose() }
    const onResize = () => setVw({ w: window.innerWidth, h: window.innerHeight })
    document.addEventListener('fullscreenchange', onFs); window.addEventListener('resize', onResize)
    return () => { clearTimeout(idle.current); setInkDark(wasDark); document.removeEventListener('fullscreenchange', onFs); window.removeEventListener('resize', onResize); if (document.fullscreenElement) document.exitFullscreen?.().catch?.(() => {}) }
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps
  const n = frames.length
  const iRef = useRef(i); iRef.current = i
  const go = d => { const k = iRef.current; if (k + d >= n) { flash('마지막 장이에요 — 끝내려면 Esc'); return } if (k + d < 0) { flash('첫 장이에요'); return } setI(k + d) }   // 마지막 장에서 멈춤(2026-10-18 사용자: 휠로 넘기다 꺼지지 않게)
  const toolRef = useRef(tool); toolRef.current = tool
  // 레이저 포인터(2026-10-18 사용자) — ` · L로 켜고 끔(휠 클릭은 편집 화면처럼 화면 이동)
  const [mpos, setMpos] = useState(null), mouse = useRef({ x: -99, y: -99 })
  const [laserOn, setLaserOn] = useState(false)   // 레이저 = 도구와 따로 켜는 커서 — 켠 채로 펜·네모 등도 씀(2026-10-18 사용자)
  const laserShown = laserOn && !tool, laserRef = useRef(false); laserRef.current = laserShown   // 도구를 켜면 그 도구 커서, 끄면 다시 레이저(2026-10-26 실검증 — 판서하는데 커서가 계속 빨간 점이라 불편)
  // 레이저로 누른 채 끌기 = 빨간 자취(0.6초 뒤 사라짐) — 전엔 글 선택(파란 칠)이 잡히거나 깜빡였음(2026-10-26 실검증)
  const [trail, setTrail] = useState([]), trailOn = useRef(false), TRAIL_MS = 600
  useEffect(() => { if (!trail.length) return; const t = setTimeout(() => setTrail(tr => tr.filter(q => Date.now() - q.t < TRAIL_MS)), 40); return () => clearTimeout(t) }, [trail])
  // 막대 = 화면 아래 근처(100px)에서만(2026-10-18 사용자 — 판서할 때 그림을 안 가리게), 시작 때 3초 보여 줌
  const [nearBottom, setNearBottom] = useState(false), [intro, setIntro] = useState(true)   // intro = 시작 3초는 마우스가 어디 있든 보여 줌
  useEffect(() => { const t = setTimeout(() => setIntro(false), 3000); return () => clearTimeout(t) }, [])
  const eraseKey = useRef({ t: 0, prev: null }), [toast, setToast] = useState(null), iNow = useRef(i); iNow.current = i
  const toastT = useRef(0), flash = msg => { setToast(msg); clearTimeout(toastT.current); toastT.current = setTimeout(() => setToast(null), 2000) }
  const clearSlide = () => { const fr = frames[iNow.current]; if (!fr) return; onClearNotes(fr.box); flash('이 장 판서 지움 — Ctrl+Z로 되돌리기') }
  const pickColor = c => { if (toolRef.current === 'hl') setHlColor(c); else setPenColor(c) }   // 형광펜을 들고 있으면 형광펜 색, 아니면 펜 색
  const snap45 = (a, b) => { const ang = Math.round(Math.atan2(b.y - a.y, b.x - a.x) / (Math.PI / 4)) * (Math.PI / 4), L = Math.hypot(b.x - a.x, b.y - a.y); return { x: a.x + L * Math.cos(ang), y: a.y + L * Math.sin(ang) } }
  const wake = () => { setAwake(true); clearTimeout(idle.current); idle.current = setTimeout(() => { if (!barHover.current) setAwake(false) }, IDLE_MS) }   // 커서·막대 — 2초 가만히 있으면 숨김
  useEffect(() => { wake(); pauseYoutubeOutside(root.current) }, [])   // eslint-disable-line react-hooks/exhaustive-deps — 뒤 칠판에서 틀어 둔 영상은 멈춤(소리 둘)
  useEffect(() => {   // 칠판 글쇠보다 먼저(capture) — 발표 중엔 칠판 단축키가 안 돎. 글자 칸에 치는 중이면 그대로 둠
    const onKey = e => {
      if (e.target?.tagName === 'INPUT') return
      const k = e.key, code = /^Numpad\d$/.test(e.code) ? 'Digit' + e.code.slice(6) : e.code; e.stopPropagation()   // 오른쪽 숫자 키(넘패드)도 숫자로(2026-10-18 사용자)
      if (code === 'Tab') { e.preventDefault(); setList(l => (l ? null : { typed: '', pick: iRef.current })); return }   // 장 목록 열기/닫기(고른 칸 = 지금 장)
      if (listRef.current) { e.preventDefault()   // 목록 안: 번호 + Enter = 그 장, Esc = 닫기(숫자 키가 판서 도구로 가지 않음)
        const cols = Math.max(1, Math.floor((window.innerWidth * 0.86 + 14) / 214)), mv = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -cols, ArrowDown: cols }[k]   // 방향키 = 고른 칸 옮기기(2026-10-18 사용자)
        if (/^Digit\d$/.test(code)) setList(l => ({ ...l, typed: (l.typed + code.slice(5)).slice(-3) }))
        else if (mv) setList(l => ({ typed: '', pick: Math.max(0, Math.min(n - 1, l.pick + mv)) }))
        else if (k === 'Backspace') setList(l => ({ ...l, typed: l.typed.slice(0, -1) }))
        else if (k === 'Enter' || k === ' ') { const L = listRef.current, no = L.typed ? +L.typed : L.pick + 1; if (no >= 1 && no <= n) setI(no - 1); setList(null) }   // 번호를 쳤으면 그 번호, 아니면 고른 칸
        else if (k === 'Escape') setList(null)
        return }
      if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === 'z') { e.preventDefault(); onUndo(); return }
      if ((e.ctrlKey || e.metaKey) && code === 'Digit0') { e.preventDefault(); setZoom(null); return }   // 원래 배율(브라우저 확대는 그대로)
      if (code === 'KeyF' && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); yt.current.f(); return }   // 유튜브 크게 보기 ⇄ 원래(2026-10-20 사용자: F 손버릇 — 유튜브 자체 F는 겹친 전체 화면이 돼 발표가 깨졌음)
      if (k === ' ' && yt.current.space()) { e.preventDefault(); return }   // 영상 있는 장의 Space = 재생/일시정지(키보드를 발표가 가지므로 유튜브 대신), 없으면 아래 다음 장
      if (k === 'Escape') { e.preventDefault(); if (menuRef.current) setMenu(null); else if (tool) setTool(null); else onClose(); return }
      if (['ArrowRight', 'ArrowDown', 'PageDown', ' ', 'Enter'].includes(k)) { e.preventDefault(); go(1) }
      else if (['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace'].includes(k)) { e.preventDefault(); go(-1) }
      else if (k === 'Home') setI(0); else if (k === 'End') setI(n - 1)
      else if (code === 'KeyM') setGlide(g => !g)
      else if (code === 'KeyD') setDark(v => !v)
      else if (code === 'Digit0' || code === 'KeyV') setTool(null)   // 도구 끄기
      else if (code === 'Backquote' || code === 'KeyL') setLaserOn(v => !v)   // 레이저 켜기/끄기(도구는 그대로)
      else if (code === 'BracketLeft') setSize(v => Math.max(0, v - 1)); else if (code === 'BracketRight') setSize(v => Math.min(2, v + 1))
      else if (code === 'KeyX') onFlipArrow()   // 방금 그린 화살표 방향 뒤집기
      else if ((code === 'Digit6' || code === 'KeyE') && Date.now() - eraseKey.current.t < 400) {   // 지우개 키 두 번 = 이 장 판서 지우기(2026-10-18 사용자) — 첫 번째로 바뀐 도구는 되돌림
        eraseKey.current.t = 0; setTool(eraseKey.current.prev); clearSlide() }
      else { const t = TOOLS.find(t => t[4].includes(code)); if (t?.[0] === 'erase') eraseKey.current = { t: Date.now(), prev: toolRef.current }
        if (t) setTool(v => (v === t[0] ? null : t[0]))
        const c = COLORS.find(c => c[2] === code); if (c) pickColor(c[0]) }
    }
    window.addEventListener('keydown', onKey, true); return () => window.removeEventListener('keydown', onKey, true)
  }, [n, tool])   // eslint-disable-line react-hooks/exhaustive-deps
  const [zoom, setZoom] = useState(null), [menu, setMenu] = useState(null), root = useRef(null), wheelAt = useRef({ t: 0, acc: 0, flip: 0, qt: 0 }), [quick, setQuick] = useState(false), pan = useRef(null)   // zoom = { s, ox, oy } 지금 장 화면 = o + s·원래 화면(장 넘기면 풀림), pan = 우클릭 끌기
  const menuRef = useRef(null); menuRef.current = menu
  const [bigHover, setBigHover] = useState(false), yt = useRef({})   // yt = F·Space 키가 쓰는 지금 상태(아래 `yt.current`)
  useEffect(() => {   // 키보드는 늘 발표가 — 영상을 누르면 초점이 유튜브 칸으로 가 F가 유튜브 전체 화면(겹침 → 발표 깨짐)이 됐음. 마우스는 그대로 유튜브로 감(실측)
    const back = () => setTimeout(() => { const a = document.activeElement; if (a?.tagName === 'IFRAME' && root.current?.contains(a)) root.current.focus({ preventScroll: true }) }, 0)
    window.addEventListener('blur', back); return () => window.removeEventListener('blur', back)
  }, [])
  const [webOn, setWebOn] = useState(null)   // 조작 중인 웹 카드(장을 넘기면 풀림)
  useEffect(() => { setZoom(null); setWebOn(null); const t = setTimeout(() => yt.current.hint?.(), 600); return () => clearTimeout(t) }, [i])   // 영상 있는 장에 들어오면 Space 알림(넘김 0.4초 뒤)
  useEffect(() => {   // 휠 = 장 넘기기(파워포인트 손버릇), Ctrl+휠 = 커서 자리 확대 — 2026-10-18 사용자
    const el = root.current; if (!el) return
    const onWheel = e => {
      if (listRef.current || e.target.closest?.('[data-testid=present-bar],[data-testid=present-menu]')) return   // 장 목록은 그 안에서 굴림
      e.preventDefault()
      if (e.ctrlKey || e.metaKey) { const f = e.deltaY < 0 ? 1.25 : 1 / 1.25
        setZoom(z => { const s0 = z?.s || 1, s = Math.max(0.25, Math.min(16, s0 * f)), g = s / s0, ox = z?.ox || 0, oy = z?.oy || 0   // 0.25~16배(2026-10-18 사용자), 커서 자리 고정
          return { s, ox: e.clientX - g * (e.clientX - ox), oy: e.clientY - g * (e.clientY - oy) } }); return }
      // 휠 넘기기(2026-10-19 사용자: 빠르게 휘리릭) — 마우스 휠 한 칸(큰 delta) = 바로 한 장, 터치패드(작은 delta가 잇따라 옴)는 모아서 100마다 + 0.3초 간격
      const now = Date.now(), W = wheelAt.current, notch = Math.abs(e.deltaY) >= 50
      if (now - W.t > 200) W.acc = 0
      W.t = now; W.acc += e.deltaY
      if (Math.abs(W.acc) < 100 && !notch) return
      if (now - W.flip < (notch ? 30 : 300)) { W.acc = 0; return }
      W.flip = now; W.acc = 0; setQuick(true); clearTimeout(W.qt); W.qt = setTimeout(() => setQuick(false), 450)
      go(e.deltaY > 0 ? 1 : -1)
    }
    el.addEventListener('wheel', onWheel, { passive: false }); return () => el.removeEventListener('wheel', onWheel)
  }, [n])   // eslint-disable-line react-hooks/exhaustive-deps
  listRef.current = list
  setInkDark(dark)   // 그리기 전에 — effect에서 바꾸면 한 박자 늦어 어둡게 되돌린 뒤 글이 검은 잉크로 남았음(2026-10-18 사용자)
  const f = frames[i]
  const { w: W, h: H } = vw, b = f?.box || { x: 0, y: 0, w: 1, h: 1 }, k = Math.min(W / b.w, H / b.h) * 0.95, hw = b.w * k, hh = b.h * k, hx = (W - hw) / 2, hy = (H - hh) / 2   // 95% — TV 가장자리가 잘려도 내용이 안 붙게(HTML 공유 발표와 같음, 2026-10-19)
  const g = Math.min(W - hw, H - hh) / 2   // 프레임 둘레 여백 띠(칠판 바탕색 — 슬라이드 여백처럼, 그 밖 검정)
  const tx = hx - b.x * k, ty = hy - b.y * k, unz = (x, y) => (zoom ? [(x - zoom.ox) / zoom.s, (y - zoom.oy) / zoom.s] : [x, y])
  const [gx, gy, gk] = useGlide([tx, ty, k], glide && !draft ? (quick ? 120 : 400) : 0), [zx, zy, zs] = useGlide([zoom?.ox || 0, zoom?.oy || 0, zoom?.s || 1], pan.current?.moved ? 0 : 150)   // 휠로 잇따라 넘기는 중 = 0.12초
  if (!f) return null
  const toScene = (x, y) => { const [ux, uy] = unz(x, y); return { x: (ux - tx) / k, y: (uy - ty) / k } }
  // 유튜브 크게 보기 — fr = 그 카드의 iframe(발표 판 안). 영상 몸통을 위 검은 띠 아래에 꽉, 둘레 검은 곳 = 눌러 돌아옴
  const bigOn = fr => {
    const r = fr.closest('foreignObject').getBoundingClientRect(), s0 = zoom?.s || 1, x0 = (r.x - (zoom?.ox || 0)) / s0, y0 = (r.y - (zoom?.oy || 0)) / s0, w0 = r.width / s0, h0 = r.height / s0
    const s = Math.min((W - 32) / w0, (H - BIG_BAND - 16) / h0); setWebOn(fr.getAttribute('data-webid')); setZoom({ s, ox: (W - s * w0) / 2 - s * x0, oy: BIG_BAND + (H - BIG_BAND - 16 - s * h0) / 2 - s * y0, card: fr.getAttribute('data-webid'), right: (W + s * w0) / 2, top: BIG_BAND + (H - BIG_BAND - 16 - s * h0) / 2 })   // right·top = 영상 오른쪽 위 — 「원래 크기로」를 그 바로 위에(세로 화면이면 영상이 가운데라 화면 맨 위는 멀었음)   // 영상 몸통을 위 검은 띠(「원래 크기로」 자리) 아래에 꽉 — 둘레 검은 곳 = 눌러 돌아옴
  }
  // 키보드(F·Space) — 키 처리는 effect 안이라 지금 상태를 ref로 넘김
  // 이 장(화면 안)의 유튜브 칸 — 읽는 순서(위 → 왼쪽)
  const slideVideos = () => [...(root.current?.querySelectorAll('iframe[data-webid]') || [])].map(f => [f, f.getBoundingClientRect()])
    .filter(([f, r]) => { const cx = r.x + r.width / 2, cy = r.y + r.height / 2; return /youtube\.com\/embed\//.test(f.src) && cx > 0 && cy > 0 && cx < W && cy < H })
    .sort((a, b) => a[1].y - b[1].y || a[1].x - b[1].x).map(([f]) => f)
  const target = () => { const frs = slideVideos(); return frs.find(f => f.getAttribute('data-webid') === (zoom?.card || webOn)) || frs[0] || null }   // 크게 보는 영상 > 방금 누른 영상 > 맨 위·왼쪽
  yt.current = {
    f: () => { if (zoom?.card) { setZoom(null); return } const fr = target(); if (fr) bigOn(fr) },
    space: () => { const fr = target(); if (!fr) return false; setWebOn(fr.getAttribute('data-webid')); toggleYoutube(fr); return true },   // 영상 있는 장 = 재생/일시정지(2026-10-20 사용자: 넘기기는 →·PageDown·휠), 없으면 false = 다음 장
    hint: () => { if (slideVideos().length) flash('Space = 영상 재생/정지 · 다음 장은 →') },
  }
  // ── 판서 ──
  const down = e => {
    e.stopPropagation(); wake()
    if (textAt) { document.activeElement?.blur?.(); return }   // 쓰던 글자 칸 밖을 누르면 그 글을 넣고 끝(blur → commitText)
    if (menu) { setMenu(null); return }
    if (e.button === 2 || e.button === 1) { e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); pan.current = { x: e.clientX, y: e.clientY, moved: false, z0: zoom }; return }   // 우클릭: 끌면 화면 이동, 제자리면 메뉴(편집 화면과 같음 — 2026-10-18 사용자)
    if (!tool && e.button === 0) {   // 웹 카드 = 눌러야 칸 안 조작(처음부터 켜 두면 카드 위 휠이 장 넘기기 대신 페이지 스크롤 — 2026-10-19), 유튜브는 바로 재생
      const g = e.target.closest?.('[data-web-url]'), fr = g?.querySelector('iframe[data-webid]'), id = fr?.getAttribute('data-webid'), yt = /youtube\.com\/embed\//.test(g?.getAttribute('data-web-src') || '')
      const lid = e.target.closest?.('[data-doc-box]')?.querySelector('iframe[data-liveid]')?.getAttribute('data-liveid')   // 움직이는 카드 = 누르면 칸 안 조작(§8 항목66 4단계 — 편집 화면은 두 번, 발표는 판서와 안 겹쳐 한 번)
      if (lid && !zoom?.card) { setWebOn(lid); return }
      if (zoom?.card) { setZoom(null); return }   // 크게 보는 중 영상 밖(검은 곳·제목 띠) 누르기 = 원래대로(영상 안 클릭은 유튜브가 받음)
      if (id && yt && e.clientY < fr.closest('foreignObject').getBoundingClientRect().top) {   // 제목 띠 = 크게 보기(오른쪽 ↗ = 새 탭)
        const gr = g.getBoundingClientRect(), cw = +(g.getAttribute('data-web-box') || '0,0,480').split(',')[2] || 480
        if (gr.right - e.clientX < gr.width * 40 / cw) { window.open(g.getAttribute('data-web-url'), '_blank', 'noopener'); return }
        bigOn(fr); return
      }
      if (id) { setWebOn(id); if (yt) playYoutube(fr) } else { if (g) window.open(g.getAttribute('data-web-url'), '_blank', 'noopener'); setWebOn(null) }
    }
    if (!tool && laserRef.current && e.button === 0) { e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); trailOn.current = true; setTrail([{ x: e.clientX, y: e.clientY, t: Date.now() }]); return }   // preventDefault = 글 선택 안 잡힘
    if (!tool) return   // 클릭으로 장을 넘기지 않음(2026-10-18 사용자: 글 선택을 풀거나 판서를 보다가 넘어감) — 끌면 글 선택(기본 동작)
    if (e.button !== 0) return
    const p = { x: e.clientX, y: e.clientY }
    if (tool === 'erase') { e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); const key = 'erase' + Date.now(); setDraft({ tool, key, a: p, b: p, pts: [p] }); onErase(toScene(p.x, p.y), 8 / k, key); return }   // 스치면 지움(TRIM처럼) — 한 번 끌기 = 되돌리기 한 칸
    if (tool === 'text') { e.preventDefault(); setTextAt(p); return }   // 기본 동작(포커스를 판으로 옮김)을 막아야 새 글자 칸이 포커스를 지킴
    e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); setDraft({ tool, a: p, b: p, pts: [p] })   // preventDefault = 끄는 동안 글이 선택(파란 칠)되지 않게
  }
  const move = e => { const pn = pan.current
    if (pn) { const dx = e.clientX - pn.x, dy = e.clientY - pn.y; if (!pn.moved && Math.hypot(dx, dy) < 4) return; pn.moved = true
      setZoom({ s: pn.z0?.s || 1, ox: (pn.z0?.ox || 0) + dx, oy: (pn.z0?.oy || 0) + dy }); return }
    wake(); mouse.current = { x: e.clientX, y: e.clientY }; if (laserRef.current) setMpos({ ...mouse.current }); if (trailOn.current) setTrail(tr => [...tr, { x: e.clientX, y: e.clientY, t: Date.now() }]); const nb = e.clientY >= window.innerHeight - 100; if (nb !== nearBottom) setNearBottom(nb); if (!draft) return; const p = { x: e.clientX, y: e.clientY }
    if (draft.tool === 'erase') { const q = draft.pts.at(-1), dd = Math.hypot(p.x - q.x, p.y - q.y), steps = Math.max(1, Math.ceil(dd / 6))   // 빠르게 그어도 사이를 빠뜨리지 않게
      for (let j = 1; j <= steps; j++) { const s = toScene(q.x + (p.x - q.x) * j / steps, q.y + (p.y - q.y) * j / steps); onErase(s, 8 / k, draft.key) }
      setDraft(d => ({ ...d, pts: [...d.pts, p] })); return }
    setDraft(d => ({ ...d, b: d.tool === 'arrow' && e.shiftKey ? snap45(d.a, p) : p, pts: d.tool === 'pen' || d.tool === 'hl' ? (Math.hypot(p.x - d.pts.at(-1).x, p.y - d.pts.at(-1).y) >= 2 ? [...d.pts, p] : d.pts) : d.pts })) }
  const up = e => {
    trailOn.current = false
    setTimeout(() => { const sl = getSelection(); if (sl?.isCollapsed) sl.removeAllRanges() }, 0)   // 글자 위 클릭이 남긴 빈 선택(깜빡이는 세로 막대)을 지움 — 끌어 고른 글은 그대로(2026-10-18 사용자)
    if ((e.button === 2 || e.button === 1) && pan.current) { const pn = pan.current; pan.current = null; if (!pn.moved && e.button === 2) setMenu({ x: e.clientX, y: e.clientY }); return }   // 휠 클릭은 이동만(메뉴 없음)
    const d = draft; setDraft(null); if (!d || d.tool === 'erase') return
    if (d.tool === 'arrow' && e.shiftKey) d.b = snap45(d.a, d.b)
    const zs = zoom?.s || 1, A = toScene(d.a.x, d.a.y), B = toScene(d.b.x, d.b.y), w = SIZES.line[size] / (k * zs), PEN = argb(penColor), small = Math.hypot(d.b.x - d.a.x, d.b.y - d.a.y) < 4
    if (d.tool === 'rect' && !small) onAdd([{ pos: [Math.min(A.x, B.x), Math.min(A.y, B.y)], type: 'rect', rect: [0, 0, Math.abs(B.x - A.x), Math.abs(B.y - A.y)], pen: PEN, width: w, fill: null, style: 1 }])
    if (d.tool === 'arrow' && !small) onAdd([{ pos: [0, 0], type: 'sarrow', pts: [[A.x, A.y], [B.x, B.y]], color: PEN, width: w, head: true, head_start: false, head_scale: +(((10 + SIZES.line[size] * 2) / (k * zs)) / Math.max(w * 3.2, 11)).toFixed(4), style: 1, auto_route: false, routing: 'straight', curve_r: 0, route_hints: [], bind1: null, bind2: null }])
    if ((d.tool === 'pen' || d.tool === 'hl') && d.pts.length >= 2) onAdd([{ pos: [0, 0], type: 'path', elements: d.pts.map((q, j) => { const s = toScene(q.x, q.y); return [j ? 'L' : 'M', s.x, s.y] }), pen: d.tool === 'hl' ? argb(hlColor, '73') : PEN, width: d.tool === 'hl' ? SIZES.hl[size] / (k * zs) : w, style: 1, freehand: true }])
  }
  // 글자 칸 = 넣을 글과 같은 자리·크기(칠판 글 규칙: 위 왼쪽 + 여백 TEXT_MARGIN + 줄 높이) — 전엔 칸 가운데에 쓰고 넣으면 아래로 내려갔음(2026-10-18 사용자)
  const textBoxAt = p => { const F = [16, 22, 32][size], pad = TEXT_MARGIN * k * (zoom?.s || 1); return { F, pad, x: p.x - pad, y: p.y - F * 0.7 - pad, h: F * METRICS.app.lineSpacing + 2 * pad } }
  const commitText = v => { const p = textAt; setTextAt(null); if (!p || !v.trim()) return; const b = textBoxAt(p), s = toScene(b.x, b.y)
    onAdd([{ pos: [s.x, s.y], type: 'text', text: v, color: argb(penColor), font: +(b.F / (k * (zoom?.s || 1) * PT)).toFixed(3), bg: null }]) }
  const show = awake || !!tool || !!draft, barShow = (intro || nearBottom || barHover.current) && !draft && !zoom?.card   // 영상 크게 보기 중엔 숨김(유튜브 재생바를 가렸음)
  const btn = on => ({ all: 'unset', cursor: 'pointer', minWidth: 30, height: 30, display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: 6, padding: '0 6px', boxSizing: 'border-box',
    color: on ? '#fff' : 'rgba(255,255,255,.85)', background: on ? '#da7756' : 'transparent', font: "600 14px 'Pretendard', sans-serif" })
  const th = THEMES[dark ? 'dark' : 'light']
  const barZoom = Math.min(1.35, Math.max(1, (typeof window !== 'undefined' ? window.innerWidth : 1400) / 1400))   // 큰 화면일수록 막대도 크게(2026-10-22 디자인 점검: TV 앞에 서서 누르기엔 글자가 작았음) — 1400px = 1배, 1920 = 1.35배
  const sep = <span style={{ width: 1, height: 28, background: 'rgba(255,255,255,.2)', margin: '0 4px' }} />
  const tbtn = on => ({ ...btn(on), flexDirection: 'column', gap: 1, height: 40, minWidth: 40, padding: '2px 4px' })
  // 두 칸 고르기 — 지금 상태가 켜진 칸(2026-10-18 사용자: 「이동」 버튼이 지금 상태인지 누르면 바뀐다는 뜻인지 모르겠음)
  const seg = (label, opts, cur, set, key) => <div title={`${label} (${key})`} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, margin: '0 2px' }}>
    <div style={{ display: 'flex', background: 'rgba(255,255,255,.08)', borderRadius: 6, padding: 1 }}>{opts.map(([v, name, tip]) => <button key={name} title={tip || name} onClick={() => set(v)}
      style={{ all: 'unset', cursor: 'pointer', padding: '2px 7px', borderRadius: 5, whiteSpace: 'nowrap', font: "600 12px 'Pretendard', sans-serif", color: cur === v ? '#fff' : 'rgba(255,255,255,.6)', background: cur === v ? '#da7756' : 'transparent' }}>{name}</button>)}</div>
    <span style={{ fontSize: 11, color: 'rgba(255,255,255,.6)', whiteSpace: 'nowrap' }}>{label}</span></div>
  return <div ref={root} tabIndex={-1} data-testid="presenter" onPointerDown={down} onPointerMove={move} onPointerUp={up} onContextMenu={e => e.preventDefault()}
    style={{ position: 'fixed', inset: 0, zIndex: 1000, outline: 'none', background: '#000', cursor: laserShown ? 'none' : show ? (tool && tool !== 'erase' ? 'crosshair' : zoom?.card ? 'zoom-out' : 'default') : 'none', ...th }}>
    <svg width={W} height={H} style={{ display: 'block' }}>
      {!zoom?.card && <rect x={hx - g} y={hy - g} width={hw + 2 * g} height={hh + 2 * g} fill={th['--mb-board']} />}
      <g transform={`translate(${zx},${zy}) scale(${zs})`}><g transform={`translate(${gx},${gy}) scale(${gk})`} style={{ '--z': k * (zoom?.s || 1) }}>
        {order.filter(([it]) => !zoom?.card || it._id === zoom.card).map(([it, idx]) => <Item key={it._id} it={it} idx={idx} onBoard={onBoard[idx]} route={routes.get(idx)} labels="inline" dark={dark} web={it.type === 'web' ? (!tool && webOn === it._id ? 'on' : 'view') : it.type === 'doc' ? (!tool && webOn === it._id ? 'on' : 'view') : undefined} noFs ytBig={zoom?.card === it._id} fsScale={it.type === 'web' ? +(k * (zoom?.s || 1) * (it.scale || 1)).toFixed(2) : undefined} />)}   // fsScale = 목표 배율(넘기는 동안 매 장면이 아니라 한 번만 바뀜)
      </g></g>
      {/* 프레임 밖 가림(구멍 뚫린 검은 판) — 출력한 쪽과 같은 범위만 보임 */}
      {!zoom?.card && <path d={`M${hx - g},${hy - g} H${hx + hw + g} V${hy + hh + g} H${hx - g} Z M${hx},${hy} V${hy + hh} H${hx + hw} V${hy} Z`} fill={th['--mb-board']} fillRule="evenodd" />}
      {!zoom?.card && <path d={`M0,0 H${W} V${H} H0 Z M${hx - g},${hy - g} V${hy + hh + g} H${hx + hw + g} V${hy - g} Z`} fill="#000" fillRule="evenodd" />}
      {draft && (draft.tool === 'rect' ? <rect x={Math.min(draft.a.x, draft.b.x)} y={Math.min(draft.a.y, draft.b.y)} width={Math.abs(draft.b.x - draft.a.x)} height={Math.abs(draft.b.y - draft.a.y)} fill="none" stroke={penColor} strokeWidth={SIZES.line[size]} />
        : draft.tool === 'arrow' ? <line x1={draft.a.x} y1={draft.a.y} x2={draft.b.x} y2={draft.b.y} stroke={penColor} strokeWidth={SIZES.line[size]} />
        : <polyline points={draft.pts.map(q => `${q.x},${q.y}`).join(' ')} fill="none" stroke={draft.tool === 'hl' ? hlColor : draft.tool === 'erase' ? 'rgba(160,160,170,.45)' : penColor} strokeOpacity={draft.tool === 'hl' ? 0.45 : 1} strokeWidth={draft.tool === 'hl' ? SIZES.hl[size] : draft.tool === 'erase' ? 12 : SIZES.line[size]} strokeLinecap="round" strokeLinejoin="round" />)}
    </svg>
    {list && <div data-testid="slide-list" onPointerDown={e => { e.stopPropagation(); if (e.target === e.currentTarget) setList(null) }}
      style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,.72)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, zIndex: 3 }}>
      <div style={{ color: '#fff', font: "600 15px 'Pretendard', sans-serif" }}>장 목록 <span style={{ fontWeight: 400, color: 'rgba(255,255,255,.6)', fontSize: 13 }}>— 누르기 · 방향키 + Enter · 번호 + Enter · Esc 닫기</span>
        {list.typed && <span style={{ marginLeft: 10, padding: '2px 10px', borderRadius: 6, background: '#da7756' }}>{list.typed}번으로</span>}</div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, justifyContent: 'center', maxWidth: '86vw', maxHeight: '72vh', overflowY: 'auto', padding: 8 }}>
        {frames.map((fr, j) => { const bb = fr.box
          return <button key={fr.id} data-testid="slide-thumb" onClick={() => { setI(j); setList(null) }} style={{ all: 'unset', cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'center' }}>
            <svg width={200} height={120} viewBox={`${bb.x} ${bb.y} ${bb.w} ${bb.h}`} style={{ background: th['--mb-board'], borderRadius: 6, outline: j === list.pick ? '3px solid #da7756' : j === i ? '2px solid rgba(255,255,255,.7)' : '1px solid rgba(255,255,255,.25)', outlineOffset: 2 }}>
              <g style={{ '--z': Math.min(200 / bb.w, 120 / bb.h) }}>{order.map(([it, idx]) => <Item key={it._id} it={it} idx={idx} onBoard={onBoard[idx]} route={routes.get(idx)} labels="inline" dark={dark} />)}</g></svg>
            <span style={{ color: j === i ? '#da7756' : '#fff', font: "500 12px 'Pretendard', sans-serif" }}>{j + 1}{fr.name ? ` · ${fr.name}` : ''}</span></button> })}
      </div></div>}
    {zoom?.card && show && <button data-testid="big-close" title="원래 크기로 (영상 밖을 눌러도 됨)" onPointerDown={e => e.stopPropagation()} onClick={() => { setZoom(null); setBigHover(false) }} onPointerEnter={() => { setBigHover(true); barHover.current = true }} onPointerLeave={() => { setBigHover(false); barHover.current = false; wake() }}
      style={{ all: 'unset', cursor: 'pointer', position: 'absolute', right: Math.max(16, W - (zoom.right || W)), top: Math.max((BIG_BAND - 40) / 2, (zoom.top ?? BIG_BAND) - 52), height: 40, padding: '0 18px', display: 'flex', alignItems: 'center', gap: 6, borderRadius: 20,
        color: '#fff', font: "600 15px 'Pretendard', sans-serif", boxShadow: '0 2px 10px rgba(0,0,0,.4)', transition: 'background .12s', background: bigHover ? '#da7756' : 'rgba(63,63,70,.95)', border: '1px solid rgba(255,255,255,.25)' }}>⤡ 원래 크기로 (F)</button>}   {/* 올리면 코랄(2026-10-20 사용자: 알아보게) — 영상 위에선 마우스가 유튜브로 가니 위 띠로 올리면 나타남 */}
    {zoom && !zoom.card && <button data-testid="zoom-reset" title="원래 배율로 (Ctrl+0)" onPointerDown={e => e.stopPropagation()} onClick={() => setZoom(null)}
      style={{ all: 'unset', cursor: 'pointer', position: 'absolute', right: 16, top: 16, padding: '6px 12px', borderRadius: 16, background: 'rgba(24,24,27,.86)', color: '#fff', font: "600 12px 'Pretendard', sans-serif", boxShadow: '0 2px 10px rgba(0,0,0,.4)' }}>
      {Math.round(zoom.s * 100)}% · 원래대로</button>}
    {toast && <div style={{ position: 'absolute', left: '50%', top: 24, transform: 'translateX(-50%)', padding: '8px 14px', borderRadius: 8, background: 'rgba(24,24,27,.9)', color: '#fff', font: "500 13px 'Pretendard', sans-serif", pointerEvents: 'none' }}>{toast}</div>}
    {trail.length > 1 && <svg data-testid="laser-trail" width={W} height={H} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>{trail.slice(1).map((q, j) => { const a = trail[j], f = Math.max(0, 1 - (Date.now() - q.t) / TRAIL_MS)
      return <line key={q.t + ':' + j} x1={a.x} y1={a.y} x2={q.x} y2={q.y} stroke="#ff2a2a" strokeWidth={3 + 5 * f} strokeLinecap="round" opacity={f} style={{ filter: 'drop-shadow(0 0 4px rgba(255,40,40,.8))' }} /> })}</svg>}
    {laserShown && mpos && <div data-testid="laser" style={{ position: 'absolute', left: mpos.x - 7, top: mpos.y - 7, width: 14, height: 14, borderRadius: 7, background: '#ff2a2a', boxShadow: '0 0 10px 4px rgba(255,40,40,.6)', pointerEvents: 'none' }} />}
    {textAt && <input autoFocus placeholder="글 쓰고 Enter" onPointerDown={e => e.stopPropagation()} onKeyDown={e => { if (e.key === 'Enter') commitText(e.currentTarget.value); if (e.key === 'Escape') setTextAt(null) }} onBlur={e => commitText(e.currentTarget.value)}
      style={{ ...(b => ({ left: b.x, top: b.y, height: b.h, padding: b.pad, fontSize: b.F }))(textBoxAt(textAt)), position: 'absolute', minWidth: 160, boxSizing: 'border-box', fontFamily: APP_FONT, fontWeight: 400, lineHeight: METRICS.app.lineSpacing, color: penColor, background: 'rgba(0,0,0,.12)', border: 'none', outline: `1.5px dashed ${penColor}`, borderRadius: 2 }} />}
    {menu && (() => { const pick = f => () => { setMenu(null); f() }, items = [...TOOLS.map(([id, , name, key]) => [`${name}   (${key})${tool === id ? '  — 다시 누르면 끄기' : ''}`, pick(() => setTool(t => (t === id ? null : id))), tool === id]), [`레이저   (\`)${laserOn ? '  — 다시 누르면 끄기' : ''}`, pick(() => setLaserOn(v => !v)), laserOn], '-', ['이 장 판서 지우기   (6 6)', pick(clearSlide)], ['이전 장', pick(() => go(-1))], ['끝', pick(onClose)]]
      return <div data-testid="present-menu" onPointerDown={e => e.stopPropagation()} onContextMenu={e => e.preventDefault()}
        style={{ position: 'absolute', left: Math.min(menu.x, W - 200), top: Math.min(menu.y, H - 330), minWidth: 180, padding: 4, borderRadius: 10, background: 'rgba(24,24,27,.94)', boxShadow: '0 6px 20px rgba(0,0,0,.5)', display: 'flex', flexDirection: 'column' }}>
        {items.map((m, j) => m === '-' ? <div key={j} style={{ height: 1, background: 'rgba(255,255,255,.15)', margin: '4px 6px' }} />
          : <button key={j} onClick={m[1]} style={{ all: 'unset', cursor: 'pointer', padding: '6px 10px', borderRadius: 6, color: m[2] ? '#da7756' : 'rgba(255,255,255,.9)', font: "500 13px 'Pretendard', sans-serif" }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,.1)' }} onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}>{m[0]}</button>)}
      </div> })()}
    {/* 아래 막대 — 마우스를 움직이면 나타남, 2초 가만히 있으면 숨음(도구를 쓰는 중엔 계속) */}
    <div data-testid="present-bar" onPointerDown={e => e.stopPropagation()} onPointerEnter={() => { barHover.current = true; setNearBottom(true) }} onPointerLeave={() => { barHover.current = false; wake() }}
      style={{ position: 'absolute', left: '50%', bottom: 16, transform: 'translateX(-50%)', zoom: barZoom, display: 'flex', alignItems: 'center', gap: 2, padding: 4, borderRadius: 10, background: 'rgba(24,24,27,.86)',
        boxShadow: '0 4px 16px rgba(0,0,0,.4)', opacity: barShow ? 1 : 0, pointerEvents: barShow ? 'auto' : 'none', transition: 'opacity .25s' }}>
      <button title="이전 (←)" onClick={() => go(-1)} style={btn(false)}>◀</button>
      <button title="장 목록 (Tab) — 눌러서 바로 가기 · 방향키 + Enter · 번호 + Enter" onClick={() => setList(l => (l ? null : { typed: '', pick: i }))} style={{ ...btn(!!list), font: "500 12px 'Pretendard', sans-serif", whiteSpace: 'nowrap' }}>{i + 1} / {n}{f.name ? ` · ${f.name}` : ''} ▴</button>
      <button title="다음 (→ · 스페이스 · 클릭)" onClick={() => go(1)} style={btn(false)}>▶</button>
      {sep}
      {TOOLS.map(([id, icon, name, key]) => <button key={id} title={`${name} (${key}) — 다시 누르면 끄기(끄면 클릭 = 다음 장)${id === 'arrow' ? ' · Shift = 45° · X = 방금 그린 화살표 뒤집기' : id === 'erase' ? ' · 판서만, 스치면 지움' : ''} · Ctrl+Z 되돌리기`}
        onClick={() => setTool(t => (t === id ? null : id))} style={tbtn(tool === id)}>{icon}<span style={{ fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap' }}>{name}</span></button>)}
      {sep}
      <button title="레이저 (` · L) — 켜 두면 커서가 빨간 점, 누른 채 끌면 빨간 자취 · 펜·네모 등을 켜면 그 도구 커서, 끄면 다시 레이저" onClick={() => setLaserOn(v => !v)} style={tbtn(laserOn)}>
        {I(<><circle cx="9" cy="9" r="2.6" fill="currentColor" /><circle cx="9" cy="9" r="6" opacity=".5" /></>)}<span style={{ fontSize: 11, fontWeight: 500, whiteSpace: 'nowrap' }}>레이저</span></button>
      {sep}
      {COLORS.map(([c, name, code]) => { const cur = tool === 'hl' ? hlColor : penColor
        return <button key={c} title={`${name} (${code.slice(3)})${tool === 'hl' ? ' — 형광펜' : ' — 펜·네모·화살표·글자'}`} onClick={() => pickColor(c)}
          style={{ all: 'unset', cursor: 'pointer', width: 18, height: 18, borderRadius: 9, background: c === '#1f1f1f' ? 'linear-gradient(135deg,#1f1f1f 50%,#ffffff 50%)' : c, margin: '0 2px', boxSizing: 'border-box',
            border: '1.5px solid rgba(255,255,255,.5)', outline: cur === c ? '2px solid #da7756' : 'none', outlineOffset: 2 }} /> })}
      {sep}
      {[0, 1, 2].map(v => <button key={v} title={`굵기 ${['가늘게', '보통', '굵게'][v]} ([ ])`} onClick={() => setSize(v)} style={{ ...tbtn(size === v), minWidth: 26 }}>
        <span style={{ width: [4, 7, 11][v], height: [4, 7, 11][v], borderRadius: 6, background: 'currentColor' }} /></button>)}
      {sep}
      {seg('넘길 때', [[true, '이동', '칠판 위를 0.4초 미끄러져 감'], [false, '바로', '곧장 바뀜']], glide, setGlide, 'M')}
      {seg('화면', [[false, '밝게', ''], [true, '어둡게', '']], dark, setDark, 'D')}
      <button title="끝 (Esc)" onClick={onClose} style={tbtn(false)}>{I(<><path d="M5 5 L13 13" /><path d="M13 5 L5 13" /></>)}<span style={{ fontSize: 11, fontWeight: 500 }}>끝</span></button>
    </div>
  </div>
}
