// 편집용 문서 모델(2단계) — .ecad 아이템마다 변하지 않는 _id를 달고, 화살표 연결(bind1/bind2 = 저장 목록 순번)을 _id로 바꿔 든다.
// 편집하면 목록 순서가 바뀌므로(삭제·앞으로·복제) 순번은 저장할 때 다시 매긴다. 저장 파일은 데스크톱 .ecad 그대로(_로 시작하는 키는 빼고).
let _seq = 0
export const newId = () => 'i' + (++_seq).toString(36) + Math.random().toString(36).slice(2, 6)

export function fromEcad(doc) {
  const ids = doc.items.map(() => newId())
  const items = doc.items.map((it, i) => {
    const o = { ...it, _id: ids[i] }
    for (const k of ['bind1', 'bind2']) if (it[k] != null) { o['_' + k] = ids[it[k]] ?? null; delete o[k] }
    return o
  })
  return { ...doc, items }
}

export function toEcad(model) {
  const index = new Map(model.items.map((it, i) => [it._id, i]))
  const items = model.items.map(it => {
    const o = {}
    for (const [k, v] of Object.entries(it)) if (!k.startsWith('_')) o[k] = v
    for (const k of ['bind1', 'bind2']) {
      const ref = it['_' + k]
      if (ref === undefined) continue
      const j = ref == null ? undefined : index.get(ref)
      if (j == null && it[k + '_group'] && it[k + '_pt']) o[k] = null   // 묶음에 붙은 끝 — 순번 없이 group_id + 비율(데스크톱 `_GroupBindProxy` 저장)
      else if (j == null) { o[k] = null; o[k + '_pt'] = null; o[k + '_group'] = null }   // 붙은 도형이 지워짐 — 데스크톱처럼 끊긴 끝
      else o[k] = j
    }
    return o
  })
  const { items: _drop, ...rest } = model
  return { ...rest, format: 'easycad-doc', version: model.version ?? 1, items }
}

// 화살표 쪽에서 본 연결 상대 _id
export const boundIds = it => [it._bind1, it._bind2].filter(Boolean)
