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

const DOC_VERSION = 1;

const HOVER_RADIUS = 16;
const DRAG_THRESHOLD = 6;
const DUPLICATE_OFFSET = 190;
const SNAP_RADIUS = 20;
// 드래그 중 "이 화살표를 재계산해야 하나" 판단용 여유폭 — 이동한 도형의 bbox와 화살표
// 경로의 bbox가 이 거리 안으로 근접하면 무관한 화살표라도 재계산 대상에 포함한다.
const REROUTE_MARGIN = 40;

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
    // 드래그 중엔 rerouteAffectedArrows(휴리스틱)로 비용을 줄였으니, 놓는 순간엔 전체
    // 재계산으로 한 번 더 정확성을 보장한다(놓친 원거리 상호작용이 있어도 최종 상태는 항상 맞음).
    rerouteAllArrows();
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

function serializeDocument() {
  return {
    version: DOC_VERSION,
    shapes: [...shapes.values()].map((s) => ({ id: s.id, x: s.x, y: s.y, w: s.w, h: s.h })),
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
    addShape(s.id, s.x, s.y, s.w, s.h);
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

// playwright 자동검증용 디버그 훅 — 파일 다운로드 인터셉트 없이 직렬화/역직렬화 결과를
// 직접 조회하기 위함(실제 저장/열기 버튼 동작과는 무관, 산출물 코드에 영향 없음).
window.__easycadDebug = { serializeDocument, applyDocument };

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
