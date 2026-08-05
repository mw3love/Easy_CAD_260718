// 순수 함수 — 그리드 기반 A* 직교(4방향) 라우팅. DOM/브라우저 의존 없음(node로 유닛테스트 가능).

function heuristic(a, b) {
  return Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
}

// 그리드 반올림 때문에 포트 실좌표(비정수 그리드)와 첫/끝 그리드점 사이가 대각선이 될 수 있다.
// 그 구간에 직각 코너를 하나 끼워 넣어 모든 세그먼트를 축정렬로 강제한다.
function fixOrthogonal(points) {
  const out = [points[0]];
  for (let i = 1; i < points.length; i++) {
    const prev = out[out.length - 1];
    const cur = points[i];
    if (prev.x !== cur.x && prev.y !== cur.y) {
      out.push({ x: cur.x, y: prev.y });
    }
    out.push(cur);
  }
  return out;
}

function simplifyCollinear(points) {
  if (points.length < 3) return points;
  const out = [points[0]];
  for (let i = 1; i < points.length - 1; i++) {
    const a = out[out.length - 1];
    const b = points[i];
    const c = points[i + 1];
    const collinear = (b.x - a.x) * (c.y - a.y) === (b.y - a.y) * (c.x - a.x);
    if (!collinear) out.push(b);
  }
  out.push(points[points.length - 1]);
  return out;
}

// start/end: {x,y} 포트 좌표. startDir/endDir: 포트 바깥쪽 방향(단위 근사, 예: {x:1,y:0}).
// obstacles: [{x,y,width,height}, ...] 장애물(도형) bounding box.
// bounds: 라우팅 탐색을 제한할 캔버스 영역 {x,y,width,height}.
export function routeOrthogonal(start, startDir, end, endDir, obstacles, bounds, cellSize = 10) {
  const toCell = (p) => ({ x: Math.round(p.x / cellSize), y: Math.round(p.y / cellSize) });
  const toPoint = (c) => ({ x: c.x * cellSize, y: c.y * cellSize });

  const startExit = { x: start.x + startDir.x * cellSize, y: start.y + startDir.y * cellSize };
  const endExit = { x: end.x + endDir.x * cellSize, y: end.y + endDir.y * cellSize };

  const startCell = toCell(startExit);
  const endCell = toCell(endExit);

  const minX = Math.floor(bounds.x / cellSize) - 2;
  const maxX = Math.ceil((bounds.x + bounds.width) / cellSize) + 2;
  const minY = Math.floor(bounds.y / cellSize) - 2;
  const maxY = Math.ceil((bounds.y + bounds.height) / cellSize) + 2;

  const isBlocked = (cell) => {
    const p = toPoint(cell);
    for (const ob of obstacles) {
      if (
        p.x >= ob.x - cellSize * 0.5 &&
        p.x <= ob.x + ob.width + cellSize * 0.5 &&
        p.y >= ob.y - cellSize * 0.5 &&
        p.y <= ob.y + ob.height + cellSize * 0.5
      ) {
        return true;
      }
    }
    return false;
  };

  const key = (c) => `${c.x},${c.y}`;
  const cameFrom = new Map();
  const gScore = new Map([[key(startCell), 0]]);
  const pending = [{ cell: startCell, f: heuristic(startCell, endCell) }];
  const visited = new Set();
  const neighbors4 = [
    { x: 1, y: 0 },
    { x: -1, y: 0 },
    { x: 0, y: 1 },
    { x: 0, y: -1 },
  ];

  let found = false;
  while (pending.length) {
    pending.sort((a, b) => a.f - b.f);
    const current = pending.shift();
    const ck = key(current.cell);
    if (visited.has(ck)) continue;
    visited.add(ck);
    if (current.cell.x === endCell.x && current.cell.y === endCell.y) {
      found = true;
      break;
    }
    for (const d of neighbors4) {
      const next = { x: current.cell.x + d.x, y: current.cell.y + d.y };
      if (next.x < minX || next.x > maxX || next.y < minY || next.y > maxY) continue;
      const nk = key(next);
      if (visited.has(nk)) continue;
      const isEnd = next.x === endCell.x && next.y === endCell.y;
      if (isBlocked(next) && !isEnd) continue;
      const tentativeG = gScore.get(ck) + 1;
      if (!gScore.has(nk) || tentativeG < gScore.get(nk)) {
        gScore.set(nk, tentativeG);
        cameFrom.set(nk, ck);
        pending.push({ cell: next, f: tentativeG + heuristic(next, endCell) });
      }
    }
  }

  // 경로를 못 찾아도(예: start/end가 bounds 밖) 다른 반환 경로와 동일하게 축정렬을 보장한다 —
  // 그대로 반환하면 startExit-endExit 구간이 대각선이 되어 장애물을 그대로 관통할 수 있다.
  if (!found) {
    return simplifyCollinear(fixOrthogonal([start, startExit, endExit, end]));
  }

  const cellsPath = [];
  let curKey = key(endCell);
  while (curKey) {
    const [x, y] = curKey.split(',').map(Number);
    cellsPath.unshift({ x, y });
    curKey = cameFrom.get(curKey);
  }
  const pts = cellsPath.map(toPoint);
  const full = [start, ...pts, end];
  return simplifyCollinear(fixOrthogonal(full));
}
