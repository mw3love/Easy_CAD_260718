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
const gridBtn = document.getElementById('grid-btn');
const gridBg = document.getElementById('grid-bg');
const kindBtns = [...document.querySelectorAll('#toolbar button[data-kind]')];
const fillSwatches = [...document.querySelectorAll('#fill-swatches .swatch[data-color]')];
const fillResetBtn = document.getElementById('fill-reset-btn');

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

// ---- 그리드/스냅 — 표시(점)와 스냅이 토글 하나로 묶여 있음(Python core_constants.py 주석과
// 동일 설계). `<pattern>`이 SVG 표준 타일링이라 팬/줌 중 별도 갱신 로직 없이 항상 맞는다.
const GRID_SPACING = 20;
let gridEnabled = true;

function gridSnap(pt) {
  if (!gridEnabled) return pt;
  const sp = GRID_SPACING;
  return { x: Math.round(pt.x / sp) * sp, y: Math.round(pt.y / sp) * sp };
}

function setGridEnabled(next) {
  gridEnabled = next;
  gridBg.classList.toggle('visible', gridEnabled);
  gridBtn.classList.toggle('toggled', gridEnabled);
  statusEl.setAttribute('data-grid-enabled', String(gridEnabled));
}

function toggleGrid() {
  setGridEnabled(!gridEnabled);
}

// ---- 도형 종류 — 다음 더블클릭 생성에 쓸 종류를 툴바 버튼으로 고른다(라디오형, 하나만 활성).
let currentShapeKind = 'rect';

function setCurrentShapeKind(kind) {
  currentShapeKind = kind;
  for (const btn of kindBtns) {
    btn.classList.toggle('toggled', btn.getAttribute('data-kind') === kind);
  }
  statusEl.setAttribute('data-next-kind', kind);
}

// 포트 4종(N/E/S/W) — Python이 2026-07-30 실사용 피드백으로 대각(NE/SE/SW/NW)을 상시표시
// 목록에서 뺀 것과 동일하게 맞춤(`_shape_ports` 주석 참조). key, 사각형 기준 상대 위치(비율),
// 바깥쪽 방향(정규화), 그리드 라우팅용 축정렬 방향.
const PORT_DEFS = [
  { key: 'N', rx: 0.5, ry: 0, nx: 0, ny: -1, gx: 0, gy: -1 },
  { key: 'E', rx: 1, ry: 0.5, nx: 1, ny: 0, gx: 1, gy: 0 },
  { key: 'S', rx: 0.5, ry: 1, nx: 0, ny: 1, gx: 0, gy: 1 },
  { key: 'W', rx: 0, ry: 0.5, nx: -1, ny: 0, gx: -1, gy: 0 },
];

// 포트 원(점)은 테두리에서 살짝 띄워 바깥쪽에 그린다(Python의 gap — `_draw_port_dots`가
// `best_sh._handle_px() * HANDLE_GAP_FACTOR`로 같은 간격을 리사이즈 핸들과 공유). 화면px
// 고정이라 줌 무관하게 같은 간격으로 보인다. 연결 앵커(라우팅 시작/끝점)는 이 뜬 점이 아니라
// 실제 테두리 위 점(portWorldPos)을 그대로 쓴다 — 뜬 점은 순수 표시·히트테스트 편의용.
const PORT_GAP_PX = 8;

function portGapWorld() {
  return PORT_GAP_PX / currentScale();
}

function portDisplayPos(shape, portDef) {
  const anchor = portWorldPos(shape, portDef);
  const gap = portGapWorld();
  return { x: anchor.x + portDef.nx * gap, y: anchor.y + portDef.ny * gap };
}

let shapeSeq = 0;
const shapes = new Map(); // id -> { x, y, w, h, el, ports: Map(key -> circleEl) }

function nextShapeId() {
  shapeSeq += 1;
  return `shape-${shapeSeq}`;
}

// 화살표 id — 선택·삭제 대상을 from/to 문자열이 아니라 이걸로 특정한다(동일 포트 쌍을 잇는
// 화살표가 둘 이상 있어도 정확히 하나만 지목 가능).
let arrowSeq = 0;

function nextArrowId() {
  arrowSeq += 1;
  return `arrow-${arrowSeq}`;
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

function addShape(id, x, y, w, h, label = '', kind = 'rect', fill = null) {
  const g = document.createElementNS(SVG_NS, 'g');
  g.setAttribute('class', 'shape');
  g.setAttribute('data-id', id);

  // 히트/이동/리사이즈 앵커는 도형 종류와 무관하게 항상 이 사각형(bounding box) 하나다 —
  // 사각형이 아닌 종류는 이 사각형을 투명화(`.body-hidden`, CSS `pointer-events:all`로
  // 클릭은 여전히 받음)하고 실제 모양은 별도 `visualEl`(타원/마름모)로 그 위에 그린다.
  // 포트 위치(N/E/S/W = bbox 변 중점)는 타원·마름모 둘 다 실제 외곽선과 정확히 일치한다
  // (타원은 bbox 변 중점이 곧 타원 접점, 마름모는 bbox 변 중점이 곧 꼭짓점).
  const rect = document.createElementNS(SVG_NS, 'rect');
  rect.setAttribute('class', kind === 'rect' ? 'body' : 'body body-hidden');
  rect.setAttribute('x', x);
  rect.setAttribute('y', y);
  rect.setAttribute('width', w);
  rect.setAttribute('height', h);
  rect.setAttribute('rx', 4);
  g.appendChild(rect);

  let visualEl = null;
  if (kind === 'ellipse') {
    visualEl = document.createElementNS(SVG_NS, 'ellipse');
    visualEl.setAttribute('class', 'visual-ellipse');
    g.appendChild(visualEl);
  } else if (kind === 'diamond') {
    visualEl = document.createElementNS(SVG_NS, 'polygon');
    visualEl.setAttribute('class', 'visual-diamond');
    g.appendChild(visualEl);
  }

  // 리사이즈 핸들 — 선택된 도형 하나뿐일 때만 CSS(.resizable)로 보이고 히트테스트된다
  // (setSelection이 토글). 변(edge) 4개=그 변만 단축 리사이즈, 모서리(corner) 4개=자유
  // 리사이즈. body보다 뒤(위)에 둬서 테두리 근처 클릭이 이동 대신 리사이즈로 먼저 잡히게 한다.
  const edges = {};
  for (const key of ['N', 'E', 'S', 'W']) {
    const r = document.createElementNS(SVG_NS, 'rect');
    r.setAttribute('class', `edge-resize edge-${key.toLowerCase()}`);
    r.setAttribute('data-resize-edge', key);
    r.setAttribute('data-shape', id);
    g.appendChild(r);
    edges[key] = r;
  }
  const corners = {};
  for (const key of ['NW', 'NE', 'SE', 'SW']) {
    const r = document.createElementNS(SVG_NS, 'rect');
    r.setAttribute('class', `corner-resize corner-${key.toLowerCase()}`);
    r.setAttribute('data-resize-corner', key);
    r.setAttribute('data-shape', id);
    g.appendChild(r);
    corners[key] = r;
  }

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
  const shape = { id, x, y, w, h, label, kind, fill: null, el: g, rectEl: rect, visualEl, labelEl, ports, edges, corners };
  shapes.set(id, shape);
  layoutShapePorts(shape);
  if (fill) applyShapeFill(shape, fill);
  return shape;
}

// 채움색 대상 엘리먼트 — 사각형은 rect.body 자신, 타원·마름모는 그 위에 얹힌 visualEl
// (rect.body는 그 경우 투명 히트박스라 색을 칠해도 안 보인다).
function fillTarget(shape) {
  return shape.kind === 'rect' ? shape.rectEl : shape.visualEl;
}

// 인라인 style로 세팅 — CSS 클래스 규칙(.shape rect.body { fill: ... })보다 우선순위가 높아야
// 커스텀 색이 기본색을 실제로 덮어쓴다(속성 fill="..."만으론 클래스 규칙에 밀림).
function applyShapeFill(shape, color) {
  shape.fill = color;
  fillTarget(shape).style.fill = color || '';
}

// 선택된 도형들에 채움색을 적용 — Python `_edit_color`처럼 선택 대상에 작용(리사이즈와 달리
// 다중선택도 허용: 여러 도형을 한 번에 같은 색으로 칠하는 건 자연스러운 조작이라 제약 없음).
function applyFillToSelection(color) {
  if (selectedIds.size === 0) return;
  const fills = [];
  for (const id of selectedIds) {
    const shape = shapes.get(id);
    const before = shape.fill;
    if (before === color) continue;
    fills.push({ id, before, after: color });
    applyShapeFill(shape, color);
  }
  if (fills.length) pushEntry({ type: 'fill', fills });
}

function layoutShapePorts(shape) {
  shape.rectEl.setAttribute('x', shape.x);
  shape.rectEl.setAttribute('y', shape.y);
  shape.rectEl.setAttribute('width', shape.w);
  shape.rectEl.setAttribute('height', shape.h);
  shape.labelEl.setAttribute('x', shape.x + shape.w / 2);
  shape.labelEl.setAttribute('y', shape.y + shape.h / 2);
  if (shape.kind === 'ellipse') {
    shape.visualEl.setAttribute('cx', shape.x + shape.w / 2);
    shape.visualEl.setAttribute('cy', shape.y + shape.h / 2);
    shape.visualEl.setAttribute('rx', shape.w / 2);
    shape.visualEl.setAttribute('ry', shape.h / 2);
  } else if (shape.kind === 'diamond') {
    const cx = shape.x + shape.w / 2, cy = shape.y + shape.h / 2;
    const pts = [
      `${cx},${shape.y}`, `${shape.x + shape.w},${cy}`,
      `${cx},${shape.y + shape.h}`, `${shape.x},${cy}`,
    ].join(' ');
    shape.visualEl.setAttribute('points', pts);
  }
  for (const def of PORT_DEFS) {
    const p = portDisplayPos(shape, def);
    const c = shape.ports.get(def.key);
    c.setAttribute('cx', p.x);
    c.setAttribute('cy', p.y);
  }
  layoutResizeHandles(shape);
}

const CORNER_SIZE = 10; // 월드 단위 고정(줌 무관 스케일링은 이번 범위 밖 — Not-tested 기록)
const EDGE_BAND = 8;

function layoutResizeHandles(shape) {
  const { x, y, w, h } = shape;
  const half = CORNER_SIZE / 2;
  const bandHalf = EDGE_BAND / 2;
  const cornerPts = {
    NW: { x, y }, NE: { x: x + w, y }, SE: { x: x + w, y: y + h }, SW: { x, y: y + h },
  };
  for (const key of ['NW', 'NE', 'SE', 'SW']) {
    const p = cornerPts[key];
    const r = shape.corners[key];
    r.setAttribute('x', p.x - half);
    r.setAttribute('y', p.y - half);
    r.setAttribute('width', CORNER_SIZE);
    r.setAttribute('height', CORNER_SIZE);
  }
  const innerW = Math.max(0, w - CORNER_SIZE);
  const innerH = Math.max(0, h - CORNER_SIZE);
  const en = shape.edges.N, es = shape.edges.S, ee = shape.edges.E, ew = shape.edges.W;
  en.setAttribute('x', x + half); en.setAttribute('y', y - bandHalf);
  en.setAttribute('width', innerW); en.setAttribute('height', EDGE_BAND);
  es.setAttribute('x', x + half); es.setAttribute('y', y + h - bandHalf);
  es.setAttribute('width', innerW); es.setAttribute('height', EDGE_BAND);
  ee.setAttribute('x', x + w - bandHalf); ee.setAttribute('y', y + half);
  ee.setAttribute('width', EDGE_BAND); ee.setAttribute('height', innerH);
  ew.setAttribute('x', x - bandHalf); ew.setAttribute('y', y + half);
  ew.setAttribute('width', EDGE_BAND); ew.setAttribute('height', innerH);
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
      // 거리 판정은 눈에 보이는 위치(뜬 점)로 — 연결 앵커(point)는 테두리 그대로 유지.
      const disp = portDisplayPos(shape, def);
      const d = Math.hypot(disp.x - pt.x, disp.y - pt.y);
      if (d < bestDist) {
        bestDist = d;
        best = { shape, def, point: portWorldPos(shape, def), displayPoint: disp };
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
let selectedArrowId = null; // 화살표는 그룹드래그·리사이즈 대상이 아니라 도형 선택과 별개로 단일 선택만 취급.

function setArrowSelection(id) {
  if (selectedArrowId && selectedArrowId !== id) {
    arrowsGroup.querySelector(`.arrow[data-id="${selectedArrowId}"]`)?.classList.remove('selected');
  }
  selectedArrowId = id;
  if (selectedArrowId) {
    arrowsGroup.querySelector(`.arrow[data-id="${selectedArrowId}"]`)?.classList.add('selected');
  }
  statusEl.setAttribute('data-selected-arrow', selectedArrowId ?? 'none');
}

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
  setArrowSelection(null); // 도형 선택과 화살표 선택은 상호배타(둘 다 활성인 상태를 만들지 않음).
  const next = new Set(ids);
  for (const id of selectedIds) {
    if (!next.has(id)) {
      const el = shapes.get(id)?.el;
      el?.classList.remove('selected');
      el?.classList.remove('resizable');
    }
  }
  // 리사이즈 핸들은 단일 선택일 때만 보임(Python도 다중선택 그룹은 리사이즈 대상이 아님).
  for (const id of next) {
    const el = shapes.get(id)?.el;
    el?.classList.add('selected');
    el?.classList.toggle('resizable', next.size === 1);
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
let resizeDragState = null; // { shapeId, kind: 'N'|'E'|'S'|'W'|'NW'|'NE'|'SE'|'SW', startRect }

// Python core_shapes.py의 _grid_snap_local과 같은 역할 — 코너/변 리사이즈 중 이동하는 축의
// 절대좌표를 격자에 스냅한다(gridSnap은 {x,y} 점 전용이라 스칼라 하나만 필요한 여기엔 안 맞음).
function gridSnapScalar(v) {
  return gridEnabled ? Math.round(v / GRID_SPACING) * GRID_SPACING : v;
}

const MIN_SHAPE_W = 40;
const MIN_SHAPE_H = 30;

// kind의 각 방향 문자(N/E/S/W)가 뜻하는 변만 움직이고 반대쪽 변은 고정한다 — 변(edge) 리사이즈는
// 문자 하나(예: 'N'), 모서리(corner) 자유 리사이즈는 두 문자(예: 'NW')라 자연히 축 2개가 함께 움직인다.
function computeResize(startRect, kind, cursorPt) {
  const { x, y, w, h } = startRect;
  const right = x + w;
  const bottom = y + h;
  let newX = x, newY = y, newRight = right, newBottom = bottom;
  if (kind.includes('N')) newY = Math.min(gridSnapScalar(cursorPt.y), bottom - MIN_SHAPE_H);
  if (kind.includes('S')) newBottom = Math.max(gridSnapScalar(cursorPt.y), y + MIN_SHAPE_H);
  if (kind.includes('W')) newX = Math.min(gridSnapScalar(cursorPt.x), right - MIN_SHAPE_W);
  if (kind.includes('E')) newRight = Math.max(gridSnapScalar(cursorPt.x), x + MIN_SHAPE_W);
  return { x: newX, y: newY, w: newRight - newX, h: newBottom - newY };
}

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
  const displayPoint = portDisplayPos(shape, def);
  startDrag({ shape, def, point, displayPoint }, evt.clientX, evt.clientY);
  evt.preventDefault();
}

function onPointerDownResize(evt) {
  const shapeId = evt.target.getAttribute('data-shape');
  const shape = shapes.get(shapeId);
  const kind = evt.target.getAttribute('data-resize-edge') || evt.target.getAttribute('data-resize-corner');
  resizeDragState = { shapeId, kind, startRect: { x: shape.x, y: shape.y, w: shape.w, h: shape.h } };
  evt.preventDefault();
}

function onPointerMove(evt) {
  if (panState) {
    movePan(evt.clientX, evt.clientY);
    return;
  }

  const pt = svgPoint(evt.clientX, evt.clientY);

  if (resizeDragState) {
    const shape = shapes.get(resizeDragState.shapeId);
    const next = computeResize(resizeDragState.startRect, resizeDragState.kind, pt);
    shape.x = next.x;
    shape.y = next.y;
    shape.w = next.w;
    shape.h = next.h;
    layoutShapePorts(shape);
    rerouteAffectedArrows([resizeDragState.shapeId]);
    return;
  }

  if (bodyDragState) {
    const dx = pt.x - bodyDragState.startSvg.x;
    const dy = pt.y - bodyDragState.startSvg.y;
    // 그리드 스냅은 Python core_view.py의 _apply_grid_snap_move와 동일하게 단일 도형
    // 이동에만 적용한다(다중선택 그룹드래그는 상대 배치가 흐트러지므로 스냅 제외).
    const snapSingle = gridEnabled && bodyDragState.startPositions.size === 1;
    const movedIds = [];
    for (const [id, startPos] of bodyDragState.startPositions) {
      const s = shapes.get(id);
      let nx = startPos.x + dx;
      let ny = startPos.y + dy;
      if (snapSingle) {
        const snapped = gridSnap({ x: nx, y: ny });
        nx = snapped.x;
        ny = snapped.y;
      }
      s.x = nx;
      s.y = ny;
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
      const d = `M ${dragState.source.displayPoint.x} ${dragState.source.displayPoint.y} L ${pt.x} ${pt.y}`;
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

// 화살표는 <g class="arrow"> 안에 보이는 얇은 선(arrow-line)과 그 위에 겹치는 넓은 투명
// 히트영역(arrow-hit)을 함께 둔다 — 실제 선폭(1.6)만으로는 클릭 판정이 너무 좁아 선택이
// 안 되기 때문(포트처럼 화면px 고정 반경을 쓰지 않고 월드단위 고정폭으로 단순화, 줌 배율별
// 정확도는 Not-tested).
function appendArrow(fromRef, toRef, points) {
  const id = nextArrowId();
  const g = document.createElementNS(SVG_NS, 'g');
  g.setAttribute('class', 'arrow');
  g.setAttribute('data-id', id);
  g.setAttribute('data-from', fromRef);
  g.setAttribute('data-to', toRef);
  const hit = document.createElementNS(SVG_NS, 'path');
  hit.setAttribute('class', 'arrow-hit');
  const line = document.createElementNS(SVG_NS, 'path');
  line.setAttribute('class', 'arrow-line');
  g.appendChild(hit);
  g.appendChild(line);
  setArrowPoints(g, points);
  arrowsGroup.appendChild(g);
  return g;
}

function setArrowPoints(arrowEl, points) {
  const d = pathD(points);
  arrowEl.querySelector('.arrow-hit').setAttribute('d', d);
  arrowEl.querySelector('.arrow-line').setAttribute('d', d);
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
function isResolvableEndpoint(ref) {
  const [shapeId, portKey] = ref.split(':');
  return shapes.has(shapeId) && PORT_DEFS.some((d) => d.key === portKey);
}

function resolveEndpoint(ref) {
  const [shapeId, portKey] = ref.split(':');
  const shape = shapes.get(shapeId);
  const def = PORT_DEFS.find((d) => d.key === portKey);
  return { shape, def, point: portWorldPos(shape, def) };
}

function rerouteAllArrows() {
  for (const g of arrowsGroup.querySelectorAll('.arrow')) {
    const source = resolveEndpoint(g.getAttribute('data-from'));
    const target = resolveEndpoint(g.getAttribute('data-to'));
    setArrowPoints(g, computeRoute(source, target));
  }
}

function pathBBox(arrowEl) {
  const d = arrowEl.querySelector('.arrow-line').getAttribute('d');
  const nums = d.replace(/[ML]/g, ' ').trim().split(/\s+/).map(Number);
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
  for (const g of arrowsGroup.querySelectorAll('.arrow')) {
    const from = g.getAttribute('data-from');
    const to = g.getAttribute('data-to');
    const fromId = from.split(':')[0];
    const toId = to.split(':')[0];
    let affected = movedShapeIds.includes(fromId) || movedShapeIds.includes(toId);
    if (!affected) {
      const pbb = pathBBox(g);
      affected = movedBoxes.some((bb) => bboxesNear(pbb, bb, REROUTE_MARGIN));
    }
    if (!affected) continue;
    const source = resolveEndpoint(from);
    const target = resolveEndpoint(to);
    setArrowPoints(g, computeRoute(source, target));
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
      for (const sd of entry.shapes) addShape(sd.id, sd.x, sd.y, sd.w, sd.h, sd.label, sd.kind, sd.fill);
    } else {
      for (const sd of entry.shapes) removeShape(sd.id);
    }
    showAllPortsFaint();
  } else if (entry.type === 'deleteShapes') {
    if (isRedo) {
      for (const sd of entry.shapes) removeShape(sd.id);
    } else {
      for (const sd of entry.shapes) addShape(sd.id, sd.x, sd.y, sd.w, sd.h, sd.label, sd.kind, sd.fill);
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
  } else if (entry.type === 'resize') {
    const shape = shapes.get(entry.shapeId);
    const r = isRedo ? entry.after : entry.before;
    shape.x = r.x; shape.y = r.y; shape.w = r.w; shape.h = r.h;
    layoutShapePorts(shape);
    rerouteAllArrows();
  } else if (entry.type === 'fill') {
    for (const f of entry.fills) {
      applyShapeFill(shapes.get(f.id), isRedo ? f.after : f.before);
    }
  } else if (entry.type === 'deleteArrow') {
    if (isRedo) {
      removeArrowByRef(entry.from, entry.to);
    } else {
      const source = resolveEndpoint(entry.from);
      const target = resolveEndpoint(entry.to);
      appendArrow(entry.from, entry.to, computeRoute(source, target));
    }
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
  return { id: s.id, x: s.x, y: s.y, w: s.w, h: s.h, label: s.label, kind: s.kind, fill: s.fill };
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

// 개별 화살표 삭제 — removeShape의 도형 cascade 삭제와는 별개 경로(포트/도형은 그대로 두고
// 화살표 하나만 없앤다). undo는 같은 from/to로 새로 appendArrow해 되살린다(id는 재생성돼도
// 무방 — 화살표를 참조하는 다른 데이터가 없음).
function deleteSelectedArrow() {
  const id = selectedArrowId;
  if (!id) return;
  const g = arrowsGroup.querySelector(`.arrow[data-id="${id}"]`);
  if (!g) return;
  const from = g.getAttribute('data-from');
  const to = g.getAttribute('data-to');
  g.remove();
  setArrowSelection(null);
  updateCounts();
  pushEntry({ type: 'deleteArrow', from, to });
}

function cancelInteractions() {
  if (dragState?.previewEl) dragState.previewEl.remove();
  dragState = null;
  if (selectionDragState) selectionDragState.rectEl.remove();
  selectionDragState = null;
  bodyDragState = null;
  resizeDragState = null;
  cancelLabelEdit();
  setHover(null);
  setArrowSelection(null);
  setSelection([]);
}

window.addEventListener('keydown', (evt) => {
  // 라벨 편집 <input>에 포커스가 있는 동안엔 캔버스 단축키(Delete=도형삭제 등)를 죽인다 —
  // 아니면 라벨 텍스트를 백스페이스로 지우다가 선택된 도형이 통째로 삭제되는 사고가 난다.
  // Escape/Enter는 beginLabelEdit이 입력창에 단 자체 핸들러가 이미 처리(evt.preventDefault).
  if (evt.target.tagName === 'INPUT') return;
  if (evt.key === 'Delete' || evt.key === 'Backspace') {
    if (selectedArrowId) {
      evt.preventDefault();
      deleteSelectedArrow();
    } else if (selectedIds.size > 0) {
      evt.preventDefault();
      deleteSelection();
    }
  } else if (evt.key === 'Escape') {
    cancelInteractions();
  } else if ((evt.ctrlKey || evt.metaKey) && evt.key.toLowerCase() === 'z' && !evt.shiftKey) {
    evt.preventDefault();
    undo();
  } else if ((evt.ctrlKey || evt.metaKey) &&
    (evt.key.toLowerCase() === 'y' || (evt.key.toLowerCase() === 'z' && evt.shiftKey))) {
    evt.preventDefault();
    redo();
  } else if (evt.key.toLowerCase() === 'g' && !evt.ctrlKey && !evt.metaKey && !evt.altKey) {
    evt.preventDefault();
    toggleGrid();
  }
});

function duplicateShape(source) {
  const orig = source.shape;
  const nx = orig.x + source.def.nx * DUPLICATE_OFFSET;
  const ny = orig.y + source.def.ny * DUPLICATE_OFFSET;
  const id = nextShapeId();
  addShape(id, nx, ny, orig.w, orig.h, orig.label, orig.kind, orig.fill);
  updateCounts();
  pushEntry({ type: 'createShapes', shapes: [shapeSnapshot(id)] });
}

function onPointerUp(evt) {
  if (panState) {
    panState = null;
    return;
  }

  if (resizeDragState) {
    rerouteAllArrows();
    const shape = shapes.get(resizeDragState.shapeId);
    const before = resizeDragState.startRect;
    const after = { x: shape.x, y: shape.y, w: shape.w, h: shape.h };
    if (before.x !== after.x || before.y !== after.y || before.w !== after.w || before.h !== after.h) {
      pushEntry({ type: 'resize', shapeId: resizeDragState.shapeId, before, after });
    }
    resizeDragState = null;
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
    shapes: [...shapes.values()].map((s) => ({ id: s.id, x: s.x, y: s.y, w: s.w, h: s.h, label: s.label, kind: s.kind, fill: s.fill })),
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
  arrowSeq = 0;
  for (const s of data.shapes ?? []) {
    addShape(s.id, s.x, s.y, s.w, s.h, s.label ?? '', s.kind ?? 'rect', s.fill ?? null);
    const n = Number(String(s.id).replace('shape-', ''));
    if (Number.isFinite(n) && n > shapeSeq) shapeSeq = n;
  }
  for (const a of data.arrows ?? []) {
    // 포트를 4종(N/E/S/W)으로 줄이기 전(NE/SE/SW/NW 포함 8포트) 저장된 옛 문서를 열면 그
    // 대각 포트 참조가 더 이상 PORT_DEFS에 없다 — 조용히 건너뛰고 나머지 도형·화살표는
    // 그대로 로드한다(문서 전체가 깨지는 것보다 일부 화살표만 빠지는 쪽이 낫다).
    if (!isResolvableEndpoint(a.from) || !isResolvableEndpoint(a.to)) continue;
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
gridBtn.addEventListener('click', toggleGrid);
for (const btn of kindBtns) {
  btn.addEventListener('click', () => setCurrentShapeKind(btn.getAttribute('data-kind')));
}
for (const btn of fillSwatches) {
  btn.addEventListener('click', () => applyFillToSelection(btn.getAttribute('data-color')));
}
fillResetBtn.addEventListener('click', () => applyFillToSelection(null));

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
  if (evt.target.classList.contains('arrow-hit')) {
    const id = evt.target.parentElement.getAttribute('data-id');
    setSelection([]);
    setArrowSelection(id);
    evt.preventDefault();
  } else if (evt.target.classList.contains('port')) {
    onPointerDownPort(evt);
  } else if (evt.target.classList.contains('edge-resize') || evt.target.classList.contains('corner-resize')) {
    onPointerDownResize(evt);
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
  const topLeft = gridSnap({ x: pt.x - 70, y: pt.y - 45 });
  const id = nextShapeId();
  addShape(id, topLeft.x, topLeft.y, 140, 90, '', currentShapeKind);
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
setGridEnabled(gridEnabled);
