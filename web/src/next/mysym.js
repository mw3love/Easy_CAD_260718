// 「내 심볼 — 이 브라우저」(2026-10-27 사용자: KAIROS로 만든 아이콘을 심볼 칸에 넣고 싶음·웹엔 폴더 만들기·이름 바꾸기가 없음).
// 세 층(10-27 결정): 기본 도형(앱) · 함께 쓰는 심볼(서버 `symbol_library.json`, 읽기만 — 데스크톱이 고침) · 내 심볼 = 이 브라우저 저장 + 파일 내보내기·가져오기
// (Excalidraw 라이브러리처럼 로그인 없이 — 로그인이 생기면 그때 계정으로 옮김). 파일 모양 = 데스크톱 `symbol_library.json`과 같아 데스크톱 파일도 가져올 수 있음.
// 칠판·속성 카드·도형 바꾸기는 서버 심볼과 합친 한 목록(`mergeLib`)을 그대로 씀 — 이 브라우저 폴더는 이름 앞에 `MINE`을 붙여 서버 폴더와 안 섞임.
import { useState } from 'react'

const KEY = 'mb-mysym'
export const MINE = 'browser:'
export const isMine = f => typeof f === 'string' && f.startsWith(MINE)
export const folderTitle = f => (isMine(f) ? f.slice(MINE.length) : f)
const EMPTY = { folders: [], symbols: [] }

function load() {
  try { const d = JSON.parse(localStorage.getItem(KEY) || 'null'); return d && Array.isArray(d.symbols) && Array.isArray(d.folders) ? d : EMPTY } catch { return EMPTY }
}
const newSymId = () => 'b' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6)

// [mine, api] — api의 함수들은 성공하면 true(저장 공간이 모자라면 false — 그림이 든 심볼은 클 수 있음)
export function useMySymbols() {
  const [mine, setMine] = useState(load)
  const put = d => { try { localStorage.setItem(KEY, JSON.stringify(d)) } catch { return false } setMine(d); return true }
  const uniq = (name, taken) => { let n = name, i = 2; while (taken.includes(n)) n = `${name} ${i++}`; return n }
  const api = {
    addFolder: name => { const n = name.trim(); if (!n) return false; return mine.folders.includes(n) ? true : put({ ...mine, folders: [...mine.folders, n] }) },
    renameFolder: (old, name) => { const n = name.trim(); if (!n || n === old) return !!n; const to = uniq(n, mine.folders)
      return put({ folders: mine.folders.map(f => (f === old ? to : f)), symbols: mine.symbols.map(s => (s.folder === old ? { ...s, folder: to } : s)) }) },
    delFolder: f => put({ folders: mine.folders.filter(x => x !== f), symbols: mine.symbols.filter(s => s.folder !== f) }),
    // items = .ecad 아이템들(`toEcad` 모양), folder = 이 브라우저 폴더 이름(없으면 만듦)
    addSymbol: (name, folder, items) => { const f = folder.trim() || '내 심볼'
      return put({ folders: mine.folders.includes(f) ? mine.folders : [...mine.folders, f], symbols: [...mine.symbols, { id: newSymId(), name: name.trim() || '심볼', folder: f, thumb: '', items }] }) },
    renameSymbol: (id, name) => { const n = name.trim(); return !!n && put({ ...mine, symbols: mine.symbols.map(s => (s.id === id ? { ...s, name: n } : s)) }) },
    delSymbol: id => put({ ...mine, symbols: mine.symbols.filter(s => s.id !== id) }),
    // 파일로 — 데스크톱 `symbol_library.json`과 같은 모양
    exportText: () => JSON.stringify({ folders: mine.folders, symbols: mine.symbols, folder_colors: {}, section_colors: {}, favorites: [], last_folder: mine.folders[0] || '' }, null, 1),
    // 가져오기 = 더하기(같은 이름 폴더는 합침, 심볼은 새 id) → 더한 심볼 수, 못 읽으면 -1, 저장 공간이 모자라면 -2
    importText: text => {
      let d; try { d = JSON.parse(text) } catch { return -1 }
      if (!d || !Array.isArray(d.symbols)) return -1
      const syms = d.symbols.filter(s => s && Array.isArray(s.items) && s.items.length).map(s => ({ id: newSymId(), name: String(s.name || '심볼'), folder: String(s.folder || '가져온 심볼'), thumb: '', items: s.items }))
      const folders = [...mine.folders]; for (const f of [...(Array.isArray(d.folders) ? d.folders : []), ...syms.map(s => s.folder)]) if (typeof f === 'string' && f && !folders.includes(f) && syms.some(s => s.folder === f)) folders.push(f)
      return put({ folders, symbols: [...mine.symbols, ...syms] }) ? syms.length : -2
    },
  }
  return [mine, api]
}

// 서버 심볼 + 이 브라우저 심볼 = 칠판·속성 카드가 쓰는 한 목록(이 브라우저 폴더는 맨 뒤)
export function mergeLib(server, mine) {
  if (!mine.folders.length && !mine.symbols.length) return server
  const s = server || { folders: [], symbols: [], favorites: [] }
  return { ...s, folders: [...(s.folders || []), ...mine.folders.map(f => MINE + f)], symbols: [...(s.symbols || []), ...mine.symbols.map(x => ({ ...x, folder: MINE + x.folder }))] }
}
