// 아이템 좌표 바꾸기(데스크톱 QGraphicsItem mapToScene/mapFromScene) — edit.js·connect.js·arrows.js가 같이 씀(서로 불러오는 고리 없이)
const rad = d => (d * Math.PI) / 180

// 칠판 좌표 → 아이템 안 좌표(pos 다음 origin 중심 회전·배율의 역)
export function toLocal(it, p) {
  const [x, y] = it.pos || [0, 0], [ox, oy] = it.origin || [0, 0], r = rad(-(it.rotation || 0)), s = it.scale || 1
  let qx = p.x - x - ox, qy = p.y - y - oy
  ;[qx, qy] = [qx * Math.cos(r) - qy * Math.sin(r), qx * Math.sin(r) + qy * Math.cos(r)]
  return { x: qx / s + ox, y: qy / s + oy }
}
export function toScene(it, p) {
  const [x, y] = it.pos || [0, 0], [ox, oy] = it.origin || [0, 0], r = rad(it.rotation || 0), s = it.scale || 1
  let qx = (p.x - ox) * s, qy = (p.y - oy) * s
  ;[qx, qy] = [qx * Math.cos(r) - qy * Math.sin(r), qx * Math.sin(r) + qy * Math.cos(r)]
  return { x: qx + ox + x, y: qy + oy + y }
}
// 직각 화살표의 배율·회전을 점에 녹임 — 화살표 끝 끌기·길 찾기·붙는 끝은 「pts = pos 기준 칠판 좌표」로 계산하므로
// 배율이 남으면 끝점이 커서와 어긋나고 붙은 도형을 못 따라감(2026-10-18 사용자: 여러 개 크기 조절 뒤 화살표만 따로 놂). 선 굵기도 같은 배율로.
export function bakeSarrow(it) {
  const s = it.scale || 1
  if (it.type !== 'sarrow' || (s === 1 && !it.rotation)) return it
  const [x, y] = it.pos || [0, 0], pts = it.pts.map(([px, py]) => { const q = toScene(it, { x: px, y: py }); return [q.x - x, q.y - y] })
  const o = { ...it, pts, scale: 1, rotation: 0, width: +((it.width || 2) * s).toFixed(3) }
  delete o.origin
  return o
}
