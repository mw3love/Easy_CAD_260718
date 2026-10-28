// 내 칠판 — 이 브라우저(2026-10-27 사용자: Excalidraw처럼 처음 접속하면 깨끗한 빈 칠판, 공유하는 순간부터 남이 들어옴).
// 비밀번호 없는 서버에선 칠판 주소가 곧 열쇠 — 새 칠판 이름 끝에 짐작할 수 없는 꼬리(칠판 코드)를 붙이고, 칠판 목록은 서버 전체가 아니라
// 이 브라우저가 만들거나 열어 본 칠판만(서버 `/api/boards`는 비밀번호 없는 서버에서 전체 목록을 숨김). 로그인이 생기면 이 목록이 DB로 감.
const LIST = 'mb.myBoards', LAST = 'mb.lastBoard', MAX = 100
const ABC = 'abcdefghjkmnpqrstuvwxyz23456789'   // 헷갈리는 글자(i·l·o·0·1) 뺌 — 말로 불러 주거나 손으로 칠 때
export const CODE_LEN = 8                         // 31^8 ≈ 8500억 — 짐작으로는 못 찾음

const read = (k, d) => { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v) } catch { return d } }
const write = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch { /* 기억 못 해도 칠판은 서버에 그대로 */ } }

export function boardCode() { const a = new Uint32Array(CODE_LEN); crypto.getRandomValues(a); return [...a].map(v => ABC[v % ABC.length]).join('') }
export const cleanBoardName = s => (s || '').trim().replace(/[^\w\-가-힣]/g, '').slice(0, 48)
export const newBoardName = (title = '') => (cleanBoardName(title) ? `${cleanBoardName(title)}-${boardCode()}` : boardCode())   // 이름 없으면 코드만 = 링크가 짧고 영문뿐(한글 주소는 보낼 때 %EC…로 길어짐 — 2026-10-27 자체 확인)
// 보여 줄 이름 — 「송신소점검-k7p2qx9m」 = 제목 「송신소점검」 + 칠판 코드(흐리게), 코드만인 이름 = 「제목 없음」(2026-10-28 — 바로 만들고 이름은 나중에). 꼬리가 없는 옛 이름(main 등)은 통째로 제목
export const UNTITLED = '제목 없음'
export function boardLabel(name) { if (new RegExp(`^[${ABC}]{${CODE_LEN}}$`).test(name || '')) return { title: UNTITLED, code: name }
  const m = new RegExp(`^(.+)-([${ABC}]{${CODE_LEN}})$`).exec(name || ''); return m ? { title: m[1], code: m[2] } : { title: name || '', code: '' } }
// 칠판 이름 = 문서 `title`(2026-10-28 사용자 — 주소와 따로라 바꿔도 남에게 준 링크 그대로), 없으면 주소에서 읽은 이름
export const boardTitle = (name, title) => (typeof title === 'string' && title.trim()) || boardLabel(name).title

// 「칠판 코드로 열기」(2026-10-28 — QR 밑 코드를 손으로 칠 때) — 데스크톱 `web_board.board_from_text`와 같은 규칙 + 코드·게시 링크.
// 칠판 코드 8자 → { code }(이름에 제목이 붙었을 수 있어 서버에 물음 — `/api/boards?code=`), 주소 …?board=이름 → { board }, 게시 …?view= → { view }, 그 밖 = 이름 그대로
export function boardFromText(text) {
  const t = (text || '').trim(); let q = null
  if (/[?&](board|view)=/.test(t)) try { q = new URL(t, 'http://x').searchParams } catch { q = null }
  if (q?.get('view')) return { view: q.get('view').replace(/[^\w-]/g, '').slice(0, 64) }
  const name = (q?.get('board') ?? t).replace(/\s/g, '').replace(/[^\w\-가-힣]/g, '').slice(0, 64)
  return new RegExp(`^[${ABC}]{${CODE_LEN}}$`, 'i').test(name) ? { code: name.toLowerCase() } : { board: name }
}

export const myBoards =() => (Array.isArray(read(LIST, null)) ? read(LIST, []) : []).filter(b => b && typeof b.name === 'string')   // [{ name, t(마지막으로 연 때) }] 목록 순서 그대로
export const isMyBoard = name => myBoards().some(b => b.name === name)
// 순서 = 사용자가 정함(2026-10-28 사용자: 누를 때마다 맨 위로 올라갈 필요 없음, 끌어서 바꾸기) — 처음 보는 칠판만 맨 위에, 있던 칠판은 그 자리
export function rememberBoard(name) { if (!name) return; const my = myBoards(), i = my.findIndex(b => b.name === name)
  write(LIST, i < 0 ? [{ name, t: Date.now() }, ...my].slice(0, MAX) : my.map((b, j) => (j === i ? { ...b, t: Date.now() } : b))); write(LAST, name) }
export function moveBoard(name, before) { const my = myBoards(), it = my.find(b => b.name === name); if (!it || name === before) return   // before = 이 칠판 앞으로(없으면 맨 끝)
  const rest = my.filter(b => b.name !== name), i = rest.findIndex(b => b.name === before); rest.splice(i < 0 ? rest.length : i, 0, it); write(LIST, rest) }
export function forgetBoard(name) { write(LIST, myBoards().filter(b => b.name !== name)); if (read(LAST, '') === name) write(LAST, myBoards()[0]?.name || '') }

// 주소에 칠판이 없을 때(`/`) 열 칠판 — 마지막으로 쓰던 칠판, 처음이면 새 비밀 주소. auto = '' | 'last' | 'new'(팀 서버는 'new'면 우리 팀 첫 칠판으로 — main.jsx Gate)
// 이 기능 전부터 쓰던 브라우저(다른 기억이 있음)는 처음 한 번 옛 기본 칠판 main을 마지막 칠판으로 — 업데이트하자마자 쓰던 칠판이 사라진 것처럼 보이지 않게
export function pickBoard(search) {
  const q = new URLSearchParams(search)
  if (q.get('board') || q.get('view')) return { name: q.get('board') || '', auto: '' }
  let last = read(LAST, '')
  if (!last && read(LIST, null) == null && (() => { try { return localStorage.getItem('mb.name') != null || localStorage.getItem('mb-dock') != null } catch { return false } })()) { last = 'main'; rememberBoard('main') }
  return last ? { name: last, auto: 'last' } : { name: newBoardName(), auto: 'new' }
}
