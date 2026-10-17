// 칠판 저장 — 서버(web/server.py, 감시 PC)가 있으면 거기에, 없으면 이 브라우저에만(IndexedDB).
// 주소 끝 `?board=이름`으로 칠판을 여러 개 둘 수 있다(기본 main). 고친 뒤 0.8초 쉬면 저장, 탭을 숨길 때도 바로 저장.
import { getSnapshot } from 'tldraw'

export const BOARD = (new URLSearchParams(location.search).get('board') || 'main').replace(/[^\w\-가-힣]/g, '').slice(0, 64) || 'main'
const URL_ = `/api/board/${encodeURIComponent(BOARD)}`

// 서버에서 칠판 받기 → { server: true, snapshot } | { server: false }
export async function loadBoard() {
  try {
    const r = await fetch(URL_, { cache: 'no-store' })
    if (r.status === 404) return { server: true, snapshot: null }
    if (!r.ok) return { server: false }
    return { server: true, snapshot: await r.json() }
  } catch { return { server: false } }
}

export function startAutosave(editor, onStatus) {
  let timer = null, dirty = false, saving = null
  const save = async () => {
    clearTimeout(timer); timer = null
    if (!dirty) return
    dirty = false
    const body = JSON.stringify({ document: getSnapshot(editor.store).document })
    onStatus('saving')
    try {
      saving = fetch(URL_, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body, keepalive: body.length < 60000 })
      const r = await saving
      onStatus(r.ok ? 'saved' : 'error')
      if (!r.ok) dirty = true
    } catch { dirty = true; onStatus('offline') }
  }
  const stop = editor.store.listen(() => { dirty = true; onStatus('dirty'); clearTimeout(timer); timer = setTimeout(save, 800) },
    { source: 'user', scope: 'document' })
  const onHide = () => { if (document.visibilityState === 'hidden') save() }
  document.addEventListener('visibilitychange', onHide)
  window.addEventListener('pagehide', save)
  return { save, stop: () => { stop(); document.removeEventListener('visibilitychange', onHide); window.removeEventListener('pagehide', save) } }
}
