import { routeOrthogonal } from './astar.js';

let failures = 0;
function assert(cond, msg) {
  if (!cond) {
    failures += 1;
    console.error('FAIL:', msg);
  } else {
    console.log('PASS:', msg);
  }
}

const obstacle = { x: 200, y: 100, width: 100, height: 80 };
const bounds = { x: 0, y: 0, width: 800, height: 500 };

const path = routeOrthogonal(
  { x: 150, y: 140 },
  { x: 1, y: 0 },
  { x: 400, y: 140 },
  { x: -1, y: 0 },
  [obstacle],
  bounds
);

assert(Array.isArray(path) && path.length >= 2, '경로를 반환한다');

const hitsObstacle = path.some(
  (p) => p.x > obstacle.x && p.x < obstacle.x + obstacle.width && p.y > obstacle.y && p.y < obstacle.y + obstacle.height
);
assert(!hitsObstacle, '경로가 장애물 bounding box를 관통하지 않는다');

const isOrthogonal = path.every((p, i) => {
  if (i === 0) return true;
  const prev = path[i - 1];
  return p.x === prev.x || p.y === prev.y;
});
assert(isOrthogonal, '모든 세그먼트가 축 정렬(직교)이다');

console.log('path:', JSON.stringify(path));

const noObstaclePath = routeOrthogonal(
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 100, y: 0 },
  { x: -1, y: 0 },
  [],
  { x: -10, y: -10, width: 200, height: 200 }
);
assert(noObstaclePath.length <= 4, '장애물 없으면 경로가 단순하다(우회 불필요)');

// 포트 좌표가 10px 그리드에 맞지 않는 실제 케이스(회귀 방지 — 대각선 잘림 버그)
const offGridPath = routeOrthogonal(
  { x: 220, y: 125 },
  { x: 1, y: 0 },
  { x: 480, y: 345 },
  { x: -1, y: 0 },
  [
    { x: 80, y: 80, width: 140, height: 90 },
    { x: 480, y: 300, width: 140, height: 90 },
  ],
  bounds
);
const offGridOrthogonal = offGridPath.every((p, i) => {
  if (i === 0) return true;
  const prev = offGridPath[i - 1];
  return p.x === prev.x || p.y === prev.y;
});
assert(offGridOrthogonal, '그리드 비정렬 포트 좌표에서도 모든 세그먼트가 축정렬이다');

if (failures > 0) {
  console.error(`${failures}개 실패`);
  process.exitCode = 1;
} else {
  console.log('모두 통과');
}
