// 칠판 그림 따로 받기(2026-11-05 사용자 — 노트북에서 큰 칠판이 다 뜨기까지 5초). 서버는 웹에 칠판을 보낼 때 큰 그림의 데이터를 빼고
// 주소를 단다(`_ref` = `/api/blob/<지문>.<확장자>`, `_pre` = 원래 앞머리 — `web/docblobs.py`). 화면은 그 주소로 바로 그리고(`render.jsx`),
// 여기서 그림을 받아 원래 데이터(`data`)로 채운다 — 그 뒤로는 내보내기·AI에 보이기·발표 자료 등이 전처럼 `data`를 씀.
// `_`로 시작하는 칸은 저장·보내기에서 빠지므로(`sync.toWire`) 채우기 전에 옮긴 그림은 `data: ''`로 가고, 서버가 원래 데이터를 지킨다.
const got = new Map()      // 주소 → base64(앞머리 없음)
const wait = new Map()     // 받는 중인 주소 → Promise
const failed = new Set()   // 못 받은 주소(다시 조르지 않음 — 화면은 주소로 계속 그림)

const toB64 = blob => new Promise((ok, no) => { const fr = new FileReader(); fr.onload = () => ok(String(fr.result).split(',')[1] || ''); fr.onerror = no; fr.readAsDataURL(blob) })
const pull = u => { if (!wait.has(u)) wait.set(u, fetch(u).then(r => (r.ok ? r.blob() : Promise.reject(new Error(r.status)))).then(toB64).then(b => { got.set(u, b) }, () => { failed.add(u) }).finally(() => wait.delete(u))); return wait.get(u) }

export const needsFill = items => items.some(it => it._ref && !failed.has(it._ref))

// 그 자리에서 채움(모델을 새로 만들지 않음) — 그림은 이미 주소로 그려져 있어 다시 그릴 일이 없는데, 모델을 바꾸면 칠판 전체를 다시 계산·그려
// 노트북에서 0.5초 넘게 더 멈췄음(2026-11-05 실측). 되돌리기 기록이 같은 도형을 들고 있으면 그것도 함께 채워짐.
// 모델과 맞춘 기준(`sync` 기준 — uid → 글)도 함께: 기준의 그 도형이 아직 빈 그림이면 같은 데이터를 넣어 채운 것이 「고친 것」으로 보이지 않게(키 차례가 같아 글이 같음)
export function fillInPlace(items, base) {
  for (const it of items) {
    const b = it._ref && got.get(it._ref); if (b == null) continue
    it.data = (it._pre || '') + b; delete it._ref; delete it._pre
    const w = base?.items.get(it._id); if (w) { try { const o = JSON.parse(w); if (o.type === 'image' && !o.data) { o.data = it.data; base.items.set(it._id, JSON.stringify(o)) } } catch { /* 기준이 깨졌으면 그냥 보냄 */ } }
  }
}

// 아직 안 받은 그림을 받은 뒤 then — 같은 그림(같은 지문)은 한 번만
export function fetchFills(items) {
  const us = [...new Set(items.filter(it => it._ref && !got.has(it._ref) && !failed.has(it._ref)).map(it => it._ref))]
  return Promise.all(us.map(pull))
}
