import { routeOrthogonal } from './astar.js';

const SVG_NS = 'http://www.w3.org/2000/svg';
const svg = document.getElementById('canvas');
const shapesGroup = svg.querySelector('.shapes');
const arrowsGroup = svg.querySelector('.arrows');
const selectionGroup = svg.querySelector('.selection');
const previewGroup = svg.querySelector('.drag-preview');
const statusEl = document.getElementById('status');
const shapeCountEl = document.getElementById('shape-count');
const arrowCountEl = document.getElementById('arrow-count');

const HOVER_RADIUS = 16;
const DRAG_THRESHOLD = 6;
const DUPLICATE_OFFSET = 190;
const SNAP_RADIUS = 20;

// 포트 8종: key, 사각형 기준 상대 위치(비율), 바깥쪽 방향(정규화), 그리드 라우팅용 축정렬 방향
const PORT_DEFS = [
  { key: 'N', rx: 0.5, ry: 0, nx: 0, ny: -1, gx: 0, gy: -1 },
  { key: 'NE', rx: 1, ry: 0, nx: 0.7071, ny: -0.7071, gx: 1, gy: 0 },
  { key: 'E', rx: 1, ry: 0.5, nx: 1, ny: 0, gx: 1, gy: 0 },
  { key: 'SE', rx: 1, ry: 1, nx: 0.7071, ny: 0.7071, gx: 1, gy: 0 },
  { key: 'S', rx: 0.5, ry: 1, nx: 0, ny: 1, gx: 0, gy: 1 },
  { key: 'SW', rx: 0, ry: 1, nx: -0.7071, ny: 0.7071, gx: -1, gy: 0 },
  { key: 'W', rx: 0, ry: 0.5, nx: -1, ny: 0, gx: -1, gy: 0 },
  { key: 'NW', rx: 0, ry: 0, nx: -0.7071, ny: -0.7071, gx: -1, gy: 0 },
];

let shapeSeq = 0;
const shapes = new Map(); // id -> { x, y, w, h, el, ports: Map(key -> circleEl) }

function nextShapeId() {
  shapeSeq += 1;
  return `shape-${shapeSeq}`;
}

function svgPoint(clientX, clientY) {
  const pt = svg.createSVGPoint();
  pt.x = clientX;
  pt.y = clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}

function portWorldPos(shape, portDef) {
  return { x: shape.x + shape.w * portDef.rx, y: shape.y + shape.h * portDef.ry };
}

function addShape(id, x, y, w, h) {
  const g = document.createElementNS(SVG_NS, 'g');
  g.setAttribute('class', 'shape');
  g.setAttribute('data-id', id);

  const rect = document.createElementNS(SVG_NS, 'rect');
  rect.setAttribute('class', 'body');
  rect.setAttribute('x', x);
  rect.setAttribute('y', y);
  rect.setAttribute('width', w);
  rect.setAttribute('height', h);
  rect.setAttribute('rx', 4);
  g.appendChild(rect);

  const ports = new Map();
  for (const def of PORT_DEFS) {
    const c = document.createElementNS(SVG_NS, 'circle');
    c.setAttribute('class', 'port');
    c.setAttribute('data-port', def.key);
    c.setAttribute('data-shape', id);
    c.setAttribute('r', 5);
    g.appendChild(c);
    ports.set(def.key, c);
  }

  shapesGroup.appendChild(g);
  const shape = { id, x, y, w, h, el: g, rectEl: rect, ports };
  shapes.set(id, shape);
  layoutShapePorts(shape);
  return shape;
}

function layoutShapePorts(shape) {
  shape.rectEl.setAttribute('x', shape.x);
  shape.rectEl.setAttribute('y', shape.y);
  shape.rectEl.setAttribute('width', shape.w);
  shape.rectEl.setAttribute('height', shape.h);
  for (const def of PORT_DEFS) {
    const p = portWorldPos(shape, def);
    const c = shape.ports.get(def.key);
    c.setAttribute('cx', p.x);
    c.setAttribute('cy', p.y);
  }
}

function updateCounts() {
  const shapeCount = shapes.size;
  const arrowCount = arrowsGroup.children.length;
  statusEl.setAttribute('data-shape-count', String(shapeCount));
  statusEl.setAttribute('data-arrow-count', String(arrowCount));
  shapeCountEl.textContent = String(shapeCount);
  arrowCountEl.textContent = String(arrowCount);
}

function findNearestPort(pt, excludeShapeId, radius = HOVER_RADIUS) {
  let best = null;
  let bestDist = radius;
  for (const shape of shapes.values()) {
    if (shape.id === excludeShapeId) continue;
    for (const def of PORT_DEFS) {
      const p = portWorldPos(shape, def);
      const d = Math.hypot(p.x - pt.x, p.y - pt.y);
      if (d < bestDist) {
        bestDist = d;
        best = { shape, def, point: p };
      }
    }
  }
  return best;
}

let hovered = null; // { shape, def }

function setHover(next) {
  if (hovered && (!next || hovered.shape.id !== next.shape.id || hovered.def.key !== next.def.key)) {
    hovered.shape.ports.get(hovered.def.key).classList.remove('hover');
  }
  hovered = next;
  if (hovered) {
    hovered.shape.ports.get(hovered.def.key).classList.add('hover');
    statusEl.setAttribute('data-hovered-port', `${hovered.shape.id}:${hovered.def.key}`);
  } else {
    statusEl.setAttribute('data-hovered-port', 'none');
  }
}

function showAllPortsFaint() {
  for (const shape of shapes.values()) {
    for (const def of PORT_DEFS) {
      shape.ports.get(def.key).classList.add('visible');
    }
  }
}

let selectedIds = new Set();

function normalizedRect(a, b) {
  return {
    x: Math.min(a.x, b.x),
    y: Math.min(a.y, b.y),
    width: Math.abs(b.x - a.x),
    height: Math.abs(b.y - a.y),
  };
}

function rectsIntersect(a, b) {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

function setSelection(ids) {
  const next = new Set(ids);
  for (const id of selectedIds) {
    if (!next.has(id)) shapes.get(id)?.el.classList.remove('selected');
  }
  for (const id of next) {
    shapes.get(id)?.el.classList.add('selected');
  }
  selectedIds = next;
  statusEl.setAttribute('data-selected-count', String(selectedIds.size));
}

function toggleSelection(id) {
  const next = new Set(selectedIds);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  setSelection(next);
}

let bodyDragState = null; // { startSvg, startPositions: Map(id -> {x,y}) }
let selectionDragState = null; // { startSvg, rectEl, additive }

function onPointerDownBody(evt) {
  const shapeId = evt.target.parentElement.getAttribute('data-id');

  if (evt.shiftKey) {
    toggleSelection(shapeId);
    evt.preventDefault();
    return;
  }

  // 이미 다중선택된 도형을 다시 누르면 선택을 유지한 채 그룹 전체를 드래그,
  // 그 외엔 단일 선택으로 교체 — Lucid류 캔버스의 표준 동작.
  if (!selectedIds.has(shapeId)) {
    setSelection([shapeId]);
  }

  const startPositions = new Map();
  for (const id of selectedIds) {
    const s = shapes.get(id);
    startPositions.set(id, { x: s.x, y: s.y });
  }
  bodyDragState = { startSvg: svgPoint(evt.clientX, evt.clientY), startPositions };
  evt.preventDefault();
}

let dragState = null; // { source: {shape, def, point}, startClient, moved, previewEl }

function startDrag(source, clientX, clientY) {
  dragState = {
    source,
    startClient: { x: clientX, y: clientY },
    moved: false,
    previewEl: null,
  };
}

function onPointerDownPort(evt) {
  const shapeId = evt.target.getAttribute('data-shape');
  const portKey = evt.target.getAttribute('data-port');
  const shape = shapes.get(shapeId);
  const def = PORT_DEFS.find((d) => d.key === portKey);
  const point = portWorldPos(shape, def);
  startDrag({ shape, def, point }, evt.clientX, evt.clientY);
  evt.preventDefault();
}

function onPointerMove(evt) {
  const pt = svgPoint(evt.clientX, evt.clientY);

  if (bodyDragState) {
    const dx = pt.x - bodyDragState.startSvg.x;
    const dy = pt.y - bodyDragState.startSvg.y;
    for (const [id, startPos] of bodyDragState.startPositions) {
      const s = shapes.get(id);
      s.x = startPos.x + dx;
      s.y = startPos.y + dy;
      layoutShapePorts(s);
    }
    rerouteAllArrows();
    return;
  }

  if (selectionDragState) {
    const rect = normalizedRect(selectionDragState.startSvg, pt);
    selectionDragState.rectEl.setAttribute('x', rect.x);
    selectionDragState.rectEl.setAttribute('y', rect.y);
    selectionDragState.rectEl.setAttribute('width', rect.width);
    selectionDragState.rectEl.setAttribute('height', rect.height);
    return;
  }

  if (dragState) {
    const dx = evt.clientX - dragState.startClient.x;
    const dy = evt.clientY - dragState.startClient.y;
    const dist = Math.hypot(dx, dy);

    if (!dragState.moved && dist > DRAG_THRESHOLD) {
      dragState.moved = true;
      const line = document.createElementNS(SVG_NS, 'path');
      line.setAttribute('class', 'drag-preview-line');
      previewGroup.appendChild(line);
      dragState.previewEl = line;
    }

    if (dragState.moved) {
      const d = `M ${dragState.source.point.x} ${dragState.source.point.y} L ${pt.x} ${pt.y}`;
      dragState.previewEl.setAttribute('d', d);
      const target = findNearestPort(pt, dragState.source.shape.id, SNAP_RADIUS);
      setHover(target);
    }
    return;
  }

  const near = findNearestPort(pt, null, HOVER_RADIUS);
  setHover(near);
}

function computeRoute(source, target) {
  const obstacles = [...shapes.values()]
    .filter((s) => s.id !== source.shape.id && s.id !== target.shape.id)
    .map((s) => ({ x: s.x, y: s.y, width: s.w, height: s.h }));
  // 자기 자신·상대 도형도 라우팅 장애물로 포함(경로가 도형 내부를 관통하지 않도록)
  obstacles.push({ x: source.shape.x, y: source.shape.y, width: source.shape.w, height: source.shape.h });
  obstacles.push({ x: target.shape.x, y: target.shape.y, width: target.shape.w, height: target.shape.h });

  const bounds = { x: 0, y: 0, width: 800, height: 500 };
  const startDir = { x: source.def.gx, y: source.def.gy };
  const endDir = { x: target.def.gx, y: target.def.gy };
  return routeOrthogonal(source.point, startDir, target.point, endDir, obstacles, bounds);
}

function pathD(points) {
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
}

function finalizeArrow(source, target) {
  const points = computeRoute(source, target);

  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('class', 'arrow');
  path.setAttribute('data-from', `${source.shape.id}:${source.def.key}`);
  path.setAttribute('data-to', `${target.shape.id}:${target.def.key}`);
  path.setAttribute('d', pathD(points));
  arrowsGroup.appendChild(path);
  updateCounts();
}

// 포트 참조 문자열("shape-1:E")을 현재 도형 상태 기준 실좌표로 되돌린다 — 도형이 이동해도
// 화살표가 고정 포트를 계속 따라가게(플로팅 아님) 하기 위한 재계산 기준점.
function resolveEndpoint(ref) {
  const [shapeId, portKey] = ref.split(':');
  const shape = shapes.get(shapeId);
  const def = PORT_DEFS.find((d) => d.key === portKey);
  return { shape, def, point: portWorldPos(shape, def) };
}

// 이동한 도형이 화살표의 연결 당사자가 아니어도 다른 화살표 경로의 장애물이 될 수 있어(예:
// 무관한 도형이 기존 경로 위로 옮겨짐) 매 이동마다 전체 화살표를 재계산한다 — 프로토타입
// 규모(도형 수십 개 이하)에서는 pointermove마다 다시 계산해도 비용이 무시할 만하다.
function rerouteAllArrows() {
  for (const path of arrowsGroup.querySelectorAll('.arrow')) {
    const source = resolveEndpoint(path.getAttribute('data-from'));
    const target = resolveEndpoint(path.getAttribute('data-to'));
    path.setAttribute('d', pathD(computeRoute(source, target)));
  }
}

function removeShape(id) {
  const shape = shapes.get(id);
  if (!shape) return;
  shape.el.remove();
  shapes.delete(id);
  const prefix = `${id}:`;
  for (const path of [...arrowsGroup.querySelectorAll('.arrow')]) {
    if (path.getAttribute('data-from').startsWith(prefix) || path.getAttribute('data-to').startsWith(prefix)) {
      path.remove();
    }
  }
}

function deleteSelection() {
  if (selectedIds.size === 0) return;
  for (const id of selectedIds) removeShape(id);
  setSelection([]);
  updateCounts();
}

function cancelInteractions() {
  if (dragState?.previewEl) dragState.previewEl.remove();
  dragState = null;
  if (selectionDragState) selectionDragState.rectEl.remove();
  selectionDragState = null;
  bodyDragState = null;
  setHover(null);
  setSelection([]);
}

window.addEventListener('keydown', (evt) => {
  if (evt.key === 'Delete' || evt.key === 'Backspace') {
    if (selectedIds.size === 0) return;
    evt.preventDefault();
    deleteSelection();
  } else if (evt.key === 'Escape') {
    cancelInteractions();
  }
});

function duplicateShape(source) {
  const orig = source.shape;
  const nx = orig.x + source.def.nx * DUPLICATE_OFFSET;
  const ny = orig.y + source.def.ny * DUPLICATE_OFFSET;
  const id = nextShapeId();
  addShape(id, nx, ny, orig.w, orig.h);
  updateCounts();
}

function onPointerUp(evt) {
  if (bodyDragState) {
    bodyDragState = null;
    return;
  }

  if (selectionDragState) {
    const pt = svgPoint(evt.clientX, evt.clientY);
    const rect = normalizedRect(selectionDragState.startSvg, pt);
    const hitIds = [...shapes.values()]
      .filter((s) => rectsIntersect(rect, { x: s.x, y: s.y, width: s.w, height: s.h }))
      .map((s) => s.id);
    setSelection(selectionDragState.additive ? [...selectedIds, ...hitIds] : hitIds);
    selectionDragState.rectEl.remove();
    selectionDragState = null;
    return;
  }

  if (!dragState) return;

  if (!dragState.moved) {
    // 클릭 = 복제
    duplicateShape(dragState.source);
  } else {
    // 드래그 = 화살표(유효한 목표 포트에 드롭했을 때만)
    const pt = svgPoint(evt.clientX, evt.clientY);
    const target = findNearestPort(pt, dragState.source.shape.id, SNAP_RADIUS);
    if (target) {
      finalizeArrow(dragState.source, target);
    }
    if (dragState.previewEl) dragState.previewEl.remove();
  }

  setHover(null);
  dragState = null;
}

svg.addEventListener('pointermove', onPointerMove);
window.addEventListener('pointerup', onPointerUp);
svg.addEventListener('pointerdown', (evt) => {
  if (evt.target.classList.contains('port')) {
    onPointerDownPort(evt);
  } else if (evt.target.classList.contains('body')) {
    onPointerDownBody(evt);
  } else if (evt.target === svg) {
    const rectEl = document.createElementNS(SVG_NS, 'rect');
    rectEl.setAttribute('class', 'selection-box');
    selectionGroup.appendChild(rectEl);
    selectionDragState = { startSvg: svgPoint(evt.clientX, evt.clientY), rectEl, additive: evt.shiftKey };
  }
});

svg.addEventListener('dblclick', (evt) => {
  if (evt.target !== svg) return;
  const pt = svgPoint(evt.clientX, evt.clientY);
  const id = nextShapeId();
  addShape(id, pt.x - 70, pt.y - 45, 140, 90);
  showAllPortsFaint();
  updateCounts();
});

// 초기 도형 2개 — 대각선 배치라 직교 라우팅이 실제로 꺾이는지 확인 가능
addShape(nextShapeId(), 80, 80, 140, 90);
addShape(nextShapeId(), 480, 300, 140, 90);
showAllPortsFaint();
setSelection([]);
updateCounts();
