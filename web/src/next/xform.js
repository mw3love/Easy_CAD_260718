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
