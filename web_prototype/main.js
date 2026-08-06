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
const saveBtn = document.getElementById('save-btn');
const loadBtn = document.getElementById('load-btn');
const loadInput = document.getElementById('load-input');
const undoBtn = document.getElementById('undo-btn');
const redoBtn = document.getElementById('redo-btn');

const DOC_VERSION = 1;

// HOVER_RADIUS·SNAP_RADIUS는 "화면 픽셀" 기준(아래 hoverRadiusWorld/snapRadiusWorld로 매 호출
// 시 현재 줌에 맞는 월드좌표 반경으로 환산) — Python core_view.py가 `10.0 / self._view_scale()`
// 식으로 화면 픽셀 히트반경을 줌 무관하게 유지하는 것과 같은 패턴(줌아웃 시 포트가 안 작아
// 보이게, 줌인 시 반경이 과하게 안 커지게).
const HOVER_RADIUS = 16;
const DRAG_THRESHOLD = 6;
const DUPLICATE_OFFSET = 190;
const SNAP_RADIUS = 20;
// 드래그 중 "이 화살표를 재계산해야 하나" 판단용 여유폭 — 이동한 도형의 bbox와 화살표
// 경로의 bbox가 이 거리 안으로 근접하면 무관한 화살표라도 재계산 대상에 포함한다.
const REROUTE_MARGIN = 40;

// ---- 팬/줌 — SVG viewBox를 직접 조작(무한캔버스). Python은 QGraphicsView.scale()+스크롤바를
// 쓰지만 웹은 그 대응물이 viewBox — width/height를 줄이면 확대, x/y를 옮기면 이동이다.
// svgPoint()가 매번 getScreenCTM()으로 화면↔월드 변환을 다시 계산하므로, 기존의 호버·드래그·
// 선택영역 로직은 viewBox가 바뀌어도 손댈 필요 없이 그대로 맞는다.
const BASE_VIEW = { w: 800, h: 500 };
const ZOOM_MIN = 0.15;
const ZOOM_MAX = 6;
const ZOOM_STEP = 1.15; // Python _on_wheel_zoom과 동일 배율
let viewBox = { x: 0, y: 0, w: BASE_VIEW.w, h: BASE_VIEW.h };

function applyViewBox() {
  svg.setAttribute('viewBox', `${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`);
  statusEl.setAttribute('data-zoom', (BASE_VIEW.w / viewBox.w).toFixed(3));
  statusEl.setAttribute('data-view-x', viewBox.x.toFixed(1));
  statusEl.setAttribute('data-view-y', viewBox.y.toFixed(1));
}

// 화면 px당 월드 단위 배율 — 줌 무관 히트반경 계산에 쓴다.
function currentScale() {
  const rect = svg.getBoundingClientRect();
  return rect.width / viewBox.w;
}

function hoverRadiusWorld() {
  return HOVER_RADIUS / currentScale();
}

function snapRadiusWorld() {
  return SNAP_RADIUS / currentScale();
}

function zoomAt(clientX, clientY, factor) {
  const newScale = (BASE_VIEW.w / viewBox.w) * factor;
  if (newScale < ZOOM_MIN || newScale > ZOOM_MAX) return;
  const before = svgPoint(clientX, clientY);
  viewBox.w /= factor;
  viewBox.h /= factor;
  applyViewBox();
  const after = svgPoint(clientX, clientY);
  viewBox.x += before.x - after.x;
  viewBox.y += before.y - after.y;
  applyViewBox();
}

function onWheel(evt) {
  evt.preventDefault();
  zoomAt(evt.clientX, evt.clientY, evt.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP);
}

let panState = null; // { startClient: {x,y}, startViewBox: {x,y}, worldPerPx }

function startPan(clientX, clientY) {
  panState = {
    startClient: { x: clientX, y: clientY },
    startViewBox: { x: viewBox.x, y: viewBox.y },
    worldPerPx: viewBox.w / svg.getBoundingClientRect().width,
  };
}

function movePan(clientX, clientY) {
  const dx = clientX - panState.startClient.x;
  const dy = clientY - panState.startClient.y;
  viewBox.x = panState.startViewBox.x - dx * panState.worldPerPx;
  viewBox.y = panState.startViewBox.y - dy * panState.worldPerPx;
  applyViewBox();
}

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

function addShape(id, x, y, w, h, label = '') {
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

  // 라벨 텍스트 — pointer-events:none(style.css)으로 클릭이 항상 아래 rect.body로 통과하게
  // 해서, 도형 위 어디를 눌러도(텍스트 위여도) 기존 선택/드래그 판정(evt.target.classList
  // .contains('body'))이 그대로 맞는다. 더블클릭만 별도로 텍스트 편집을 시작(아래 dblclick).
  const labelEl = document.createElementNS(SVG_NS, 'text');
  labelEl.setAttribute('class', 'label');
  labelEl.textContent = label;
  g.appendChild(labelEl);

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
  const shape = { id, x, y, w, h, label, el: g, rectEl: rect, labelEl, ports };
  shapes.set(id, shape);
  layoutShapePorts(shape);
  return shape;
}

function layoutShapePorts(shape) {
  shape.rectEl.setAttribute('x', shape.x);
  shape.rectEl.setAttribute('y', shape.y);
  shape.rectEl.setAttribute('width', shape.w);
  shape.rectEl.setAttribute('height', shape.h);
  shape.labelEl.setAttribute('x', shape.x + shape.w / 2);
  shape.labelEl.setAttribute('y', shape.y + shape.h / 2);
  for (const def of PORT_DEFS) {
    const p = portWorldPos(shape, def);
    const c = shape.ports.get(def.key);
    c.setAttribute('cx', p.x);
    c.setAttribute('cy', p.y);
  }
}

function setShapeLabel(shapeId, text) {
  const shape = shapes.get(shapeId);
  shape.label = text;
  shape.labelEl.textContent = text;
}

// 도형의 월드 사각형을 현재 팬/줌 기준 실제 화면(client) 좌표로 — 인라인 편집 <input>을
// 도형 위에 정확히 겹쳐 놓기 위함(getScreenCTM이 viewBox 변화를 항상 반영하므로 팬/줌 중에도 맞음).
function shapeScreenRect(shape) {
  const ctm = svg.getScreenCTM();
  const tl = svg.createSVGPoint();
  tl.x = shape.x; tl.y = shape.y;
  const p1 = tl.matrixTransform(ctm);
  const br = svg.createSVGPoint();
  br.x = shape.x + shape.w; br.y = shape.y + shape.h;
  const p2 = br.matrixTransform(ctm);
  return { left: p1.x, top: p1.y, width: p2.x - p1.x, height: p2.y - p1.y };
}

let labelEditState = null; // { shapeId, inputEl, before }

function beginLabelEdit(shapeId) {
  if (labelEditState) commitLabelEdit();
  const shape = shapes.get(shapeId);
  const rect = shapeScreenRect(shape);
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'label-edit-input';
  input.value = shape.label || '';
  input.style.left = `${rect.left}px`;
  input.style.top = `${rect.top + rect.height / 2 - 12}px`;
  input.style.width = `${Math.max(rect.width, 40)}px`;
  document.body.appendChild(input);
  labelEditState = { shapeId, inputEl: input, before: shape.label || '' };
  input.addEventListener('keydown', (evt) => {
    if (evt.key === 'Enter') {
      evt.preventDefault();
      commitLabelEdit();
    } else if (evt.key === 'Escape') {
      evt.preventDefault();
      cancelLabelEdit();
    }
  });
  input.addEventListener('blur', () => commitLabelEdit());
  input.focus();
  input.select();
}

function commitLabelEdit() {
  if (!labelEditState) return;
  const { shapeId, inputEl, before } = labelEditState;
  const after = inputEl.value;
  labelEditState = null;
  inputEl.remove();
  if (after !== before) {
    setShapeLabel(shapeId, after);
    pushEntry({ type: 'label', id: shapeId, before, after });
  }
}

function cancelLabelEdit() {
  if (!labelEditState) return;
  const { inputEl } = labelEditState;
  labelEditState = null;
  inputEl.remove();
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
  if (panState) {
    movePan(evt.clientX, evt.clientY);
    return;
  }

  const pt = svgPoint(evt.clientX, evt.clientY);

  if (bodyDragState) {
    const dx = pt.x - bodyDragState.startSvg.x;
    const dy = pt.y - bodyDragState.startSvg.y;
    const movedIds = [];
    for (const [id, startPos] of bodyDragState.startPositions) {
      const s = shapes.get(id);
      s.x = startPos.x + dx;
      s.y = startPos.y + dy;
      layoutShapePorts(s);
      movedIds.push(id);
    }
    rerouteAffectedArrows(movedIds);
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
      const target = findNearestPort(pt, dragState.source.shape.id, snapRadiusWorld());
      setHover(target);
    }
    return;
  }

  const near = findNearestPort(pt, null, hoverRadiusWorld());
  setHover(near);
}

// A* 탐색을 제한할 영역 — 현재 도형 전체의 bounding box + 여유(장애물 우회 경로가 밖으로
// 나갈 수 있으므로). 무한캔버스 이전엔 캔버스 크기(800x500) 고정값으로 충분했지만, 팬/줌
// 도입 후 도형이 그 밖 어디에나 있을 수 있어 고정값이면 원점에서 먼 도형끼리는 탐색 실패→
// 대각선 폴백(routeOrthogonal의 !found 분기)이 잦아진다.
const ROUTE_BOUNDS_PADDING = 80;

function worldBounds() {
  if (shapes.size === 0) return { x: 0, y: 0, width: BASE_VIEW.w, height: BASE_VIEW.h };
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const s of shapes.values()) {
    minX = Math.min(minX, s.x);
    minY = Math.min(minY, s.y);
    maxX = Math.max(maxX, s.x + s.w);
    maxY = Math.max(maxY, s.y + s.h);
  }
  return {
    x: minX - ROUTE_BOUNDS_PADDING,
    y: minY - ROUTE_BOUNDS_PADDING,
    width: (maxX - minX) + ROUTE_BOUNDS_PADDING * 2,
    height: (maxY - minY) + ROUTE_BOUNDS_PADDING * 2,
  };
}

function computeRoute(source, target) {
  const obstacles = [...shapes.values()]
    .filter((s) => s.id !== source.shape.id && s.id !== target.shape.id)
    .map((s) => ({ x: s.x, y: s.y, width: s.w, height: s.h }));
  // 자기 자신·상대 도형도 라우팅 장애물로 포함(경로가 도형 내부를 관통하지 않도록)
  obstacles.push({ x: source.shape.x, y: source.shape.y, width: source.shape.w, height: source.shape.h });
  obstacles.push({ x: target.shape.x, y: target.shape.y, width: target.shape.w, height: target.shape.h });

  const startDir = { x: source.def.gx, y: source.def.gy };
  const endDir = { x: target.def.gx, y: target.def.gy };
  return routeOrthogonal(source.point, startDir, target.point, endDir, obstacles, worldBounds());
}

function pathD(points) {
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
}

function appendArrow(fromRef, toRef, points) {
  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('class', 'arrow');
  path.setAttribute('data-from', fromRef);
  path.setAttribute('data-to', toRef);
  path.setAttribute('d', pathD(points));
  arrowsGroup.appendChild(path);
  return path;
}

function finalizeArrow(source, target) {
  const fromRef = `${source.shape.id}:${source.def.key}`;
  const toRef = `${target.shape.id}:${target.def.key}`;
  appendArrow(fromRef, toRef, computeRoute(source, target));
  updateCounts();
  pushEntry({ type: 'createArrow', from: fromRef, to: toRef });
}

// 포트 참조 문자열("shape-1:E")을 현재 도형 상태 기준 실좌표로 되돌린다 — 도형이 이동해도
// 화살표가 고정 포트를 계속 따라가게(플로팅 아님) 하기 위한 재계산 기준점.
function resolveEndpoint(ref) {
  const [shapeId, portKey] = ref.split(':');
  const shape = shapes.get(shapeId);
  const def = PORT_DEFS.find((d) => d.key === portKey);
  return { shape, def, point: portWorldPos(shape, def) };
}

function rerouteAllArrows() {
  for (const path of arrowsGroup.querySelectorAll('.arrow')) {
    const source = resolveEndpoint(path.getAttribute('data-from'));
    const target = resolveEndpoint(path.getAttribute('data-to'));
    path.setAttribute('d', pathD(computeRoute(source, target)));
  }
}

function pathBBox(pathEl) {
  const nums = pathEl.getAttribute('d').replace(/[ML]/g, ' ').trim().split(/\s+/).map(Number);
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (let i = 0; i < nums.length; i += 2) {
    minX = Math.min(minX, nums[i]);
    maxX = Math.max(maxX, nums[i]);
    minY = Math.min(minY, nums[i + 1]);
    maxY = Math.max(maxY, nums[i + 1]);
  }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
}

function bboxesNear(a, b, margin) {
  return (
    a.x - margin < b.x + b.width && a.x + a.width + margin > b.x &&
    a.y - margin < b.y + b.height && a.y + a.height + margin > b.y
  );
}

// 이동한 도형이 화살표의 연결 당사자가 아니어도 다른 화살표 경로의 장애물이 될 수 있어(예:
// 무관한 도형이 기존 경로 위로 옮겨짐) 원칙적으로는 전체 재계산이 정확하다. 하지만 도형·화살표
// 수십 개 규모(스트레스 테스트로 실측: 17도형·22화살표에서 프레임당 평균 21.8ms, 60fps 예산
// 초과)에서는 매 pointermove마다 전체를 다시 계산하면 버벅인다 — 드래그 중엔 "연결된 화살표
// + 이동한 도형 근처를 지나던 화살표"만 재계산해 비용을 줄이고, 드래그가 끝나는 순간(onPointerUp)
// rerouteAllArrows로 한 번 더 전체 재계산해 정확성을 보장한다.
function rerouteAffectedArrows(movedShapeIds) {
  const movedBoxes = movedShapeIds.map((id) => {
    const s = shapes.get(id);
    return { x: s.x, y: s.y, width: s.w, height: s.h };
  });
  for (const path of arrowsGroup.querySelectorAll('.arrow')) {
    const from = path.getAttribute('data-from');
    const to = path.getAttribute('data-to');
    const fromId = from.split(':')[0];
    const toId = to.split(':')[0];
    let affected = movedShapeIds.includes(fromId) || movedShapeIds.includes(toId);
    if (!affected) {
      const pbb = pathBBox(path);
      affected = movedBoxes.some((bb) => bboxesNear(pbb, bb, REROUTE_MARGIN));
    }
    if (!affected) continue;
    const source = resolveEndpoint(from);
    const target = resolveEndpoint(to);
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

// Undo/Redo 저널 — Python 쪽 host_undo.py의 "ops 배열 + before/after 스냅샷" 구조를
// 웹 데이터모델(shapes Map + 화살표 DOM 엘리먼트)에 맞게 새로 설계했다. 연속 드래그는
// Python처럼 매 이동마다 병합(coalesce)하지 않고, 애초에 pointerdown 시점 시작좌표 대
// pointerup 시점 최종좌표 딱 1회 비교해 엔트리 1개만 쌓는다(중간 이동은 저널에 안 남음).
let undoStack = [];
let redoStack = [];

function updateHistoryButtons() {
  undoBtn.disabled = undoStack.length === 0;
  redoBtn.disabled = redoStack.length === 0;
  statusEl.setAttribute('data-undo-count', String(undoStack.length));
  statusEl.setAttribute('data-redo-count', String(redoStack.length));
}

function pushEntry(entry) {
  undoStack.push(entry);
  redoStack.length = 0;
  updateHistoryButtons();
}

function resetHistory() {
  undoStack = [];
  redoStack = [];
  updateHistoryButtons();
}

// entry 하나를 적용한다. isRedo=false면 되돌리기(before로), true면 다시실행(after로).
function applyEntry(entry, isRedo) {
  if (entry.type === 'move') {
    for (const m of entry.moves) {
      const s = shapes.get(m.id);
      const pos = isRedo ? m.after : m.before;
      s.x = pos.x;
      s.y = pos.y;
      layoutShapePorts(s);
    }
    rerouteAllArrows();
  } else if (entry.type === 'createShapes') {
    if (isRedo) {
      for (const sd of entry.shapes) addShape(sd.id, sd.x, sd.y, sd.w, sd.h, sd.label);
    } else {
      for (const sd of entry.shapes) removeShape(sd.id);
    }
    showAllPortsFaint();
  } else if (entry.type === 'deleteShapes') {
    if (isRedo) {
      for (const sd of entry.shapes) removeShape(sd.id);
    } else {
      for (const sd of entry.shapes) addShape(sd.id, sd.x, sd.y, sd.w, sd.h, sd.label);
      for (const a of entry.arrows) {
        const source = resolveEndpoint(a.from);
        const target = resolveEndpoint(a.to);
        appendArrow(a.from, a.to, computeRoute(source, target));
      }
    }
    showAllPortsFaint();
  } else if (entry.type === 'createArrow') {
    if (isRedo) {
      const source = resolveEndpoint(entry.from);
      const target = resolveEndpoint(entry.to);
      appendArrow(entry.from, entry.to, computeRoute(source, target));
    } else {
      removeArrowByRef(entry.from, entry.to);
    }
  } else if (entry.type === 'label') {
    setShapeLabel(entry.id, isRedo ? entry.after : entry.before);
  }
  setSelection([]);
  updateCounts();
}

function undo() {
  if (!undoStack.length) return;
  const entry = undoStack.pop();
  applyEntry(entry, false);
  redoStack.push(entry);
  updateHistoryButtons();
}

function redo() {
  if (!redoStack.length) return;
  const entry = redoStack.pop();
  applyEntry(entry, true);
  undoStack.push(entry);
  updateHistoryButtons();
}

function removeArrowByRef(from, to) {
  for (const path of arrowsGroup.querySelectorAll('.arrow')) {
    if (path.getAttribute('data-from') === from && path.getAttribute('data-to') === to) {
      path.remove();
      return;
    }
  }
}

function shapeSnapshot(id) {
  const s = shapes.get(id);
  return { id: s.id, x: s.x, y: s.y, w: s.w, h: s.h, label: s.label };
}

function deleteSelection() {
  if (selectedIds.size === 0) return;
  const ids = [...selectedIds];
  const shapeSnaps = ids.map(shapeSnapshot);
  const idSet = new Set(ids);
  const arrowSnaps = [...arrowsGroup.querySelectorAll('.arrow')]
    .filter((path) => idSet.has(path.getAttribute('data-from').split(':')[0]) ||
      idSet.has(path.getAttribute('data-to').split(':')[0]))
    .map((path) => ({ from: path.getAttribute('data-from'), to: path.getAttribute('data-to') }));
  for (const id of ids) removeShape(id);
  setSelection([]);
  updateCounts();
  pushEntry({ type: 'deleteShapes', shapes: shapeSnaps, arrows: arrowSnaps });
}

function cancelInteractions() {
  if (dragState?.previewEl) dragState.previewEl.remove();
  dragState = null;
  if (selectionDragState) selectionDragState.rectEl.remove();
  selectionDragState = null;
  bodyDragState = null;
  cancelLabelEdit();
  setHover(null);
  setSelection([]);
}

window.addEventListener('keydown', (evt) => {
  // 라벨 편집 <input>에 포커스가 있는 동안엔 캔버스 단축키(Delete=도형삭제 등)를 죽인다 —
  // 아니면 라벨 텍스트를 백스페이스로 지우다가 선택된 도형이 통째로 삭제되는 사고가 난다.
  // Escape/Enter는 beginLabelEdit이 입력창에 단 자체 핸들러가 이미 처리(evt.preventDefault).
  if (evt.target.tagName === 'INPUT') return;
  if (evt.key === 'Delete' || evt.key === 'Backspace') {
    if (selectedIds.size === 0) return;
    evt.preventDefault();
    deleteSelection();
  } else if (evt.key === 'Escape') {
    cancelInteractions();
  } else if ((evt.ctrlKey || evt.metaKey) && evt.key.toLowerCase() === 'z' && !evt.shiftKey) {
    evt.preventDefault();
    undo();
  } else if ((evt.ctrlKey || evt.metaKey) &&
    (evt.key.toLowerCase() === 'y' || (evt.key.toLowerCase() === 'z' && evt.shiftKey))) {
    evt.preventDefault();
    redo();
  }
});

function duplicateShape(source) {
  const orig = source.shape;
  const nx = orig.x + source.def.nx * DUPLICATE_OFFSET;
  const ny = orig.y + source.def.ny * DUPLICATE_OFFSET;
  const id = nextShapeId();
  addShape(id, nx, ny, orig.w, orig.h, orig.label);
  updateCounts();
  pushEntry({ type: 'createShapes', shapes: [shapeSnapshot(id)] });
}

function onPointerUp(evt) {
  if (panState) {
    panState = null;
    return;
  }

  if (bodyDragState) {
    // 드래그 중엔 rerouteAffectedArrows(휴리스틱)로 비용을 줄였으니, 놓는 순간엔 전체
    // 재계산으로 한 번 더 정확성을 보장한다(놓친 원거리 상호작용이 있어도 최종 상태는 항상 맞음).
    rerouteAllArrows();
    const moves = [];
    for (const [id, before] of bodyDragState.startPositions) {
      const s = shapes.get(id);
      if (s.x !== before.x || s.y !== before.y) {
        moves.push({ id, before, after: { x: s.x, y: s.y } });
      }
    }
    if (moves.length) pushEntry({ type: 'move', moves });
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
    const target = findNearestPort(pt, dragState.source.shape.id, snapRadiusWorld());
    if (target) {
      finalizeArrow(dragState.source, target);
    }
    if (dragState.previewEl) dragState.previewEl.remove();
  }

  setHover(null);
  dragState = null;
}

function serializeDocument() {
  return {
    version: DOC_VERSION,
    shapes: [...shapes.values()].map((s) => ({ id: s.id, x: s.x, y: s.y, w: s.w, h: s.h, label: s.label })),
    arrows: [...arrowsGroup.querySelectorAll('.arrow')].map((path) => ({
      from: path.getAttribute('data-from'),
      to: path.getAttribute('data-to'),
    })),
  };
}

function clearDocument() {
  for (const shape of shapes.values()) shape.el.remove();
  shapes.clear();
  arrowsGroup.replaceChildren();
  cancelInteractions();
}

function applyDocument(data) {
  clearDocument();
  shapeSeq = 0;
  for (const s of data.shapes ?? []) {
    addShape(s.id, s.x, s.y, s.w, s.h, s.label ?? '');
    const n = Number(String(s.id).replace('shape-', ''));
    if (Number.isFinite(n) && n > shapeSeq) shapeSeq = n;
  }
  for (const a of data.arrows ?? []) {
    const source = resolveEndpoint(a.from);
    const target = resolveEndpoint(a.to);
    appendArrow(a.from, a.to, computeRoute(source, target));
  }
  showAllPortsFaint();
  updateCounts();
  resetHistory();
}

function saveDocument() {
  const json = JSON.stringify(serializeDocument(), null, 2);
  const blob = new Blob([json], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'easycad-web.json';
  a.click();
  URL.revokeObjectURL(url);
}

async function loadDocumentFromFile(file) {
  const text = await file.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    statusEl.setAttribute('data-load-error', 'invalid-json');
    return;
  }
  statusEl.removeAttribute('data-load-error');
  applyDocument(data);
}

saveBtn.addEventListener('click', saveDocument);
loadBtn.addEventListener('click', () => loadInput.click());
loadInput.addEventListener('change', () => {
  const file = loadInput.files[0];
  if (file) loadDocumentFromFile(file);
  loadInput.value = '';
});
undoBtn.addEventListener('click', undo);
redoBtn.addEventListener('click', redo);

// playwright 자동검증용 디버그 훅 — 파일 다운로드 인터셉트 없이 직렬화/역직렬화 결과를
// 직접 조회하기 위함(실제 저장/열기 버튼 동작과는 무관, 산출물 코드에 영향 없음).
window.__easycadDebug = { serializeDocument, applyDocument, undo, redo };

svg.addEventListener('pointermove', onPointerMove);
window.addEventListener('pointerup', onPointerUp);
svg.addEventListener('wheel', onWheel, { passive: false });
svg.addEventListener('pointerdown', (evt) => {
  // 휠(가운데) 버튼 드래그 = 캔버스 이동 — Python core_view.py의 미들버튼 팬과 동일 관례.
  if (evt.button === 1) {
    evt.preventDefault();
    startPan(evt.clientX, evt.clientY);
    return;
  }
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
  if (evt.target.classList.contains('body')) {
    beginLabelEdit(evt.target.parentElement.getAttribute('data-id'));
    return;
  }
  if (evt.target !== svg) return;
  const pt = svgPoint(evt.clientX, evt.clientY);
  const id = nextShapeId();
  addShape(id, pt.x - 70, pt.y - 45, 140, 90);
  showAllPortsFaint();
  updateCounts();
  pushEntry({ type: 'createShapes', shapes: [shapeSnapshot(id)] });
});

// 초기 도형 2개 — 대각선 배치라 직교 라우팅이 실제로 꺾이는지 확인 가능
addShape(nextShapeId(), 80, 80, 140, 90);
addShape(nextShapeId(), 480, 300, 140, 90);
showAllPortsFaint();
setSelection([]);
updateCounts();
applyViewBox();
