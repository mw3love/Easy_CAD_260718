"""네이티브 문서 저장/열기 (.ecad = JSON).

계획서 §3.B의 '문서모델 씨앗' — 각 QGraphics 아이템을 타입+기하+스타일로 직렬화한다.
이 구조가 Phase 3에서 DXF 엔티티 매핑의 기반이 된다(각 객체가 의미정보를 지님).

지원 타입: rect · ellipse · line · path(펜) · arrow(2점 베지어) · text · badge(번호)
공통: 위치·스케일·회전·z·변환원점.
"""
import base64
import json

from PyQt6.QtCore import Qt, QRectF, QLineF, QPointF, QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QColor, QPen, QBrush, QPainterPath, QFont, QPixmap

from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _LineItem, _PathItem, _ArrowItem, _TextItem, _BadgeItem,
    _PolyArrowItem, _SymbolItem, _ImageItem, _TitleBlockItem, _TableItem, _PolygonItem,
    _ConnectorLabel, _reposition_port_from_frac, _TEXT,
)

FORMAT = "easycad-doc"
VERSION = 1


def _col(c: QColor) -> str:
    return c.name(QColor.NameFormat.HexArgb)


def _label_to_dict(lbl) -> dict:
    """[우리 확장] 라벨 하나(_TextItem/_ConnectorLabel)를 dict로 — 도형 중앙 라벨(단수 "label")과
    화살표 라벨(복수 "labels") 양쪽이 공유한다. 화살표 라벨(`_conn_t`/`_conn_off` 보유)만
    경로 위 위치(t)+수직 오프셋(off)을 추가로 담는다(FigJam/Lucid 드래그)."""
    bg = lbl._bg
    d = {
        "text": lbl.toPlainText(),
        "color": _col(lbl.defaultTextColor()),
        # 중앙 라벨은 도형에 맞춰 렌더 폰트가 축소될 수 있으니 '기준' 크기(_base_pt)를 저장.
        "font": getattr(lbl, "_base_pt", lbl.font().pointSize()),
        "bg": None if bg is None else [bg.red(), bg.green(), bg.blue(), bg.alpha()],
    }
    if isinstance(lbl, _ConnectorLabel):
        d["t"] = getattr(lbl, "_conn_t", 0.5)
        d["off"] = getattr(lbl, "_conn_off", 0.0)
    return d


# ---- 공통 변환 -------------------------------------------------------------
def _common(it) -> dict:
    o = it.transformOriginPoint()
    return {
        "pos": [it.pos().x(), it.pos().y()],
        "scale": it.scale(),
        "rotation": it.rotation(),
        "z": it.zValue(),
        "origin": [o.x(), o.y()],
        # [편의기능] 잠금·그룹 — 기본값(미잠금·무그룹)이면 어차피 로드 시 getattr 기본과 같지만
        # 명시 저장이 더 단순·안전하다(다른 pen/style 필드와 동일 관례).
        "locked": getattr(it, "_locked", False),
        "group_id": getattr(it, "_group_id", None),
        "layer_id": getattr(it, "_layer_id", None),   # [신규기능] 레이어 — None=기본 레이어
    }


def _apply_common(it, d: dict):
    it.setPos(QPointF(*d["pos"]))
    it.setTransformOriginPoint(QPointF(*d.get("origin", [0.0, 0.0])))
    sc = d.get("scale", 1.0)
    it.setScale(sc if sc else 1.0)
    it.setRotation(d.get("rotation", 0.0))
    it.setZValue(d.get("z", 0))
    it._group_id = d.get("group_id")
    it._layer_id = d.get("layer_id")
    locked = d.get("locked", False)
    it._locked = locked
    it.setFlags(
        it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable
    )
    if locked:   # [편의기능] 잠금 상태로 저장된 아이템은 로드 시에도 움직이지 않게
        it.setFlag(it.GraphicsItemFlag.ItemIsMovable, False)
        it.setFlag(it.GraphicsItemFlag.ItemIsSelectable, False)
    return it


# ---- [신규기능 §8-12] 포트(장비 테두리에 부착된 자식 사각/원) 직렬화 -----------
# 최상위 아이템 목록에는 안 실린다(Qt 자식이라 라벨과 동일하게 부모 dict 안에 중첩) —
# save_document()의 "parentItem() is None" 필터가 이미 포트를 최상위에서 자동 제외한다.
def _port_to_dict(port) -> dict:
    r = port.rect()
    return {
        "shape": "circle" if isinstance(port, _EllipseItem) else "rect",
        "size": [r.width(), r.height()],
        "pen": _col(port.pen().color()), "width": port.pen().widthF(),
        "fill": None if port.brush().style() == Qt.BrushStyle.NoBrush
        else _col(port.brush().color()),
        "frac": list(getattr(port, "_port_frac", (0.5, 0.0))),
    }


def _port_from_dict(pd: dict, host):
    w, h = pd.get("size", [18.0, 18.0])
    cls = _EllipseItem if pd.get("shape") == "circle" else _RectItem
    port = cls(QRectF(0.0, 0.0, w, h))
    port.setPen(_mkpen(pd))
    port.setBrush(_mkbrush(pd))
    port.setFlags(port.GraphicsItemFlag.ItemIsMovable | port.GraphicsItemFlag.ItemIsSelectable
                  | port.GraphicsItemFlag.ItemSendsGeometryChanges)
    port.setParentItem(host)
    port._port_host = host
    port._port_frac = tuple(pd.get("frac", [0.5, 0.0]))
    ports = getattr(host, "_ports", None)
    if ports is None:
        ports = host._ports = []
    ports.append(port)
    _reposition_port_from_frac(port)
    return port


def _mkpen(d: dict) -> QPen:
    pen = QPen(QColor(d["pen"]))
    pen.setWidthF(float(d.get("width", 1.0)))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    st = d.get("style")   # [M2 #2] 선스타일(실선/점선…) — 하위호환: 없으면 기본(실선) 유지
    if st is not None:
        pen.setStyle(Qt.PenStyle(int(st)))
    return pen


def _mkbrush(d: dict) -> QBrush:
    fill = d.get("fill")
    return QBrush(QColor(fill)) if fill else QBrush(Qt.BrushStyle.NoBrush)


def _apply_arrow_style(it, d: dict):
    """[M2 #3] 화살표(_ArrowItem/_PolyArrowItem)에 몸통 선스타일 복원.
    화살표는 pen()이 없어 _mkpen 경로를 못 타므로 _style을 직접 세팅한다.
    하위호환: style 키가 없으면 기본(SolidLine) 유지."""
    st = d.get("style")
    if st is not None:
        it._style = Qt.PenStyle(int(st))


# ---- 삽입 이미지 base64 embed (단일 .ecad 이동에도 이미지가 안 깨지게) ----------
def _pixmap_to_b64(pm: QPixmap) -> str:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")   # 원본 해상도 그대로 PNG 인코딩(무손실)
    buf.close()
    return base64.b64encode(bytes(ba)).decode("ascii")


def _b64_to_pixmap(s: str) -> QPixmap:
    pm = QPixmap()
    pm.loadFromData(base64.b64decode(s), "PNG")
    return pm


# ---- 펜(자유곡선) 경로 직렬화 ---------------------------------------------
def _path_elems(path: QPainterPath) -> list:
    out = []
    i, n = 0, path.elementCount()
    ET = QPainterPath.ElementType
    while i < n:
        e = path.elementAt(i)
        if e.type == ET.MoveToElement:
            out.append(["M", e.x, e.y]); i += 1
        elif e.type == ET.LineToElement:
            out.append(["L", e.x, e.y]); i += 1
        elif e.type == ET.CurveToElement:
            c2 = path.elementAt(i + 1)
            ep = path.elementAt(i + 2)
            out.append(["C", e.x, e.y, c2.x, c2.y, ep.x, ep.y]); i += 3
        else:
            i += 1
    return out


def _elems_to_path(elems: list) -> QPainterPath:
    p = QPainterPath()
    for e in elems:
        k = e[0]
        if k == "M":
            p.moveTo(e[1], e[2])
        elif k == "L":
            p.lineTo(e[1], e[2])
        elif k == "C":
            p.cubicTo(e[1], e[2], e[3], e[4], e[5], e[6])
    return p


# ---- 아이템 ↔ dict --------------------------------------------------------
def item_to_dict(it) -> dict | None:
    d = _common(it)
    if isinstance(it, _TitleBlockItem):
        d.update(type="titleblock", size=it._size, orient=it._orient,
                 fields=dict(it._fields))
    elif isinstance(it, _TableItem):
        r = it.rect()
        d.update(type="table", rows=it._rows, cols=it._cols, header=it._header,
                 rect=[r.x(), r.y(), r.width(), r.height()],
                 cells=[row[:] for row in it._cells],
                 col_widths=list(it._col_widths))
    elif isinstance(it, _ImageItem):
        r = it.rect()
        d.update(type="image", rect=[r.x(), r.y(), r.width(), r.height()],
                 data=_pixmap_to_b64(it._pixmap))
    elif isinstance(it, _ArrowItem):
        d.update(
            type="arrow",
            p1=[it._p1.x(), it._p1.y()], p2=[it._p2.x(), it._p2.y()],
            ctrl1=None if it._ctrl1 is None else [it._ctrl1.x(), it._ctrl1.y()],
            ctrl2=None if it._ctrl2 is None else [it._ctrl2.x(), it._ctrl2.y()],
            color=_col(it._color), width=it._width, head=it._head_at_end,
            head_start=it._head_at_start,   # [양방향 화살표, 2026-08-21]
            head_scale=it._head_scale,   # [화살촉 크기 배율, 2026-08-21]
            style=int(it._style.value),   # [M2 #3] 몸통 선스타일(점선 등)
        )
    elif isinstance(it, _SymbolItem):
        r = it.rect()
        d.update(type="symbol", kind=it._kind, rect=[r.x(), r.y(), r.width(), r.height()],
                 pen=_col(it.pen().color()), width=it.pen().widthF(),
                 fill=None if it.brush().style() == Qt.BrushStyle.NoBrush
                 else _col(it.brush().color()))
    elif isinstance(it, _PolygonItem):
        # [§8 항목21] rect는 리사이즈 상태 복원용, pts는 그 rect 기준 로컬 정점 그대로
        # (local_pts()가 정규화좌표×rect를 이미 계산해 줌 — 왕복 시 손실 없음).
        r = it.rect()
        d.update(type="polygon", closed=it._closed,
                 rect=[r.x(), r.y(), r.width(), r.height()],
                 pts=[[p.x(), p.y()] for p in it.local_pts()],
                 pen=_col(it.pen().color()), width=it.pen().widthF(),
                 fill=None if it.brush().style() == Qt.BrushStyle.NoBrush
                 else _col(it.brush().color()))
    elif isinstance(it, _RectItem):
        r = it.rect()
        d.update(type="rect", rect=[r.x(), r.y(), r.width(), r.height()],
                 pen=_col(it.pen().color()), width=it.pen().widthF(),
                 fill=None if it.brush().style() == Qt.BrushStyle.NoBrush
                 else _col(it.brush().color()))
    elif isinstance(it, _EllipseItem):
        r = it.rect()
        d.update(type="ellipse", rect=[r.x(), r.y(), r.width(), r.height()],
                 pen=_col(it.pen().color()), width=it.pen().widthF(),
                 fill=None if it.brush().style() == Qt.BrushStyle.NoBrush
                 else _col(it.brush().color()))
    elif isinstance(it, _PolyArrowItem):
        d.update(type="sarrow", pts=[[p.x(), p.y()] for p in it._pts],
                 color=_col(it._color), width=it._width, head=it._head_at_end,
                 head_start=it._head_at_start,   # [양방향 화살표, 2026-08-21]
                 head_scale=it._head_scale,   # [화살촉 크기 배율, 2026-08-21]
                 style=int(it._style.value),   # [M2 #3] 몸통 선스타일(점선 등)
                 auto_route=it._auto_route,   # [Stage1] 직교 자동 라우팅 상태
                 routing=it._routing,         # [M4-4] 라우팅 스타일(#4)
                 curve_r=it._curve_r,         # [M4-4 ⓑ] 곡선 엘보 반경(0=직각)
                 route_hints=[[h.x(), h.y()] for h in it._route_hints])  # [경유지 힌트(2f)]
    elif isinstance(it, _LineItem):
        ln = it.line()
        d.update(type="line", line=[ln.x1(), ln.y1(), ln.x2(), ln.y2()],
                 pen=_col(it.pen().color()), width=it.pen().widthF())
    elif isinstance(it, _PathItem):
        d.update(type="path", elements=_path_elems(it.path()),
                 pen=_col(it.pen().color()), width=it.pen().widthF())
        # [실사용 요청 2026-08-25] select 유휴호버 억제 표식 — 펜으로 그렸을 때만 True.
        # SVG/DXF 폴백 곡선은 애초에 안 세우므로 키 자체를 생략(하위호환, `cuts`와 같은 관례).
        if getattr(it, "_freehand", False):
            d["freehand"] = True
    elif isinstance(it, _TextItem):
        bg = it._bg
        d.update(type="text", text=it.toPlainText(),
                 color=_col(it.defaultTextColor()), font=it.font().pointSize(),
                 bg=None if bg is None else [bg.red(), bg.green(), bg.blue(), bg.alpha()])
    elif isinstance(it, _BadgeItem):
        d.update(type="badge", number=it._number, color=_col(it._color))
    else:
        return None
    # [M2 #2] pen 기반 도형(심볼·네모·원·선·펜)의 선스타일 직렬화 — 이들만 "pen" 키를 갖는다.
    # 화살표 dash·DXF linetype은 Phase 6 M3(#3)로 별도. 기본(실선)은 저장 생략해도 무방하나
    # 명시 저장이 더 단순·안전하다(로드는 하위호환으로 없으면 실선).
    if "pen" in d:
        d["style"] = int(it.pen().style().value)
    # [우리 확장] 선·화살표·닫힌도형(네모·원·심볼)에 붙은 라벨 — 본체 dict 안에 함께 직렬화.
    if isinstance(it, (_ArrowItem, _PolyArrowItem)) and it.has_label():
        # [다중 라벨 2026-08-21] 화살표는 라벨을 여러 개 가질 수 있어 리스트("labels")로
        # 저장한다 — 옛 단수 "label" 키는 하위호환 로드 전용(아래 dict_to_item)이고, 새로
        # 저장하는 파일은 항상 "labels"만 쓴다(1개짜리도 리스트 원소 1개).
        d["labels"] = [_label_to_dict(lbl) for lbl in it._live_labels() if lbl.toPlainText().strip()]
    elif isinstance(it, (_LineItem, _SymbolItem, _RectItem, _EllipseItem, _PolygonItem)) \
            and it.has_label():
        d["label"] = _label_to_dict(it._label)
    # [신규기능 §8-12] 부착된 포트 — 라벨과 동일하게 부모 dict 안에 중첩 직렬화.
    if getattr(it, "_ports", None):
        d["ports"] = [_port_to_dict(p) for p in it._ports]
    # [§8 항목17 6단계] TRIM cut 구간(닫힌 도형: 사각·원·심볼) — (변 인덱스, t0, t1) 그대로
    # JSON 배열로. 없으면(하위호환) 키 자체를 생략 — 로드 시 getattr 기본(None)과 동일.
    if getattr(it, "_cuts", None):
        d["cuts"] = [[edge_i, t0, t1] for edge_i, t0, t1 in it._cuts]
    return d


def dict_to_item(d: dict):
    t = d.get("type")
    if t == "titleblock":
        it = _TitleBlockItem(d.get("size", "A2"), d.get("orient", "landscape"),
                             d.get("fields"))
    elif t == "table":
        it = _TableItem(d.get("rows", 1), d.get("cols", 1), QRectF(*d["rect"]),
                        d.get("cells"), d.get("header", True), d.get("col_widths"))
    elif t == "image":
        it = _ImageItem(_b64_to_pixmap(d["data"]), QRectF(*d["rect"]))
    elif t == "arrow":
        it = _ArrowItem(QColor(d["color"]), d["width"], d.get("head", True),
                        d.get("head_start", False),   # [양방향 화살표] 하위호환 기본 False
                        d.get("head_scale", 1.0))     # [화살촉 크기 배율] 하위호환 기본 1.0
        it.set_points(QPointF(*d["p1"]), QPointF(*d["p2"]))
        if d.get("ctrl1") is not None:
            it._ctrl1 = QPointF(*d["ctrl1"])
            it._ctrl2 = QPointF(*d["ctrl2"])
        _apply_arrow_style(it, d)   # [M2 #3] 하위호환: 없으면 solid 유지
    elif t == "symbol":
        it = _SymbolItem(d.get("kind", "decision"), QRectF(*d["rect"]))
        it.setPen(_mkpen(d)); it.setBrush(_mkbrush(d))
    elif t == "polygon":
        pts = [QPointF(*xy) for xy in d["pts"]]
        it = _PolygonItem(pts, d.get("closed", True), rect=QRectF(*d["rect"]))
        it.setPen(_mkpen(d))
        if it._closed:
            it.setBrush(_mkbrush(d))
    elif t == "rect":
        it = _RectItem(QRectF(*d["rect"])); it.setPen(_mkpen(d)); it.setBrush(_mkbrush(d))
    elif t == "ellipse":
        it = _EllipseItem(QRectF(*d["rect"])); it.setPen(_mkpen(d)); it.setBrush(_mkbrush(d))
    elif t == "sarrow":
        it = _PolyArrowItem(QColor(d["color"]), d["width"], d.get("head", True),
                            d.get("head_start", False),   # [양방향 화살표] 하위호환 기본 False
                            d.get("head_scale", 1.0))     # [화살촉 크기 배율] 하위호환 기본 1.0
        it._pts = [QPointF(*xy) for xy in d["pts"]]
        it._auto_route = d.get("auto_route", False)   # [Stage1] 직교 자동 라우팅 상태
        # [M4-4] 라우팅 스타일 — 신규 필드. 옛 파일은 auto_route→ortho / 아니면 straight로 유추(무손실).
        raw_routing = d.get("routing", "ortho" if it._auto_route else "straight")
        # [M4-4 · 통합] 옛 3값(straight/ortho/ortho_curved) → 2값. 각짐/둥긂은 반경이 소유하므로
        # ⚠ 옛 "ortho"(=직각 엘보)는 반경 0으로 읽어야 예전 그대로 각지게 렌더된다(기본값 10을 쓰면
        # 옛 도면의 직각 커넥터가 전부 둥글어진다). 옛 "ortho_curved"는 기본 반경.
        it._routing = "straight" if raw_routing == "straight" else "ortho"
        it._route_hints = [QPointF(*xy) for xy in d.get("route_hints", [])]  # [경유지 힌트(2f)]
        it._curve_r = float(d.get("curve_r", 0.0 if raw_routing == "ortho" else it._CORNER_R))
        _apply_arrow_style(it, d)   # [M2 #3] 하위호환: 없으면 solid 유지
    elif t == "line":
        it = _LineItem(QLineF(*d["line"])); it.setPen(_mkpen(d))
    elif t == "path":
        it = _PathItem(_elems_to_path(d["elements"])); it.setPen(_mkpen(d))
        it._freehand = bool(d.get("freehand", False))
    elif t == "text":
        it = _TextItem(QColor(d["color"])); it.apply_font_size(d.get("font", 16))
        it.setPlainText(d.get("text", ""))
        if d.get("bg") is not None:
            it.set_bg(QColor(*d["bg"]))
    elif t == "badge":
        it = _BadgeItem(d["number"], QColor(d["color"]))
    else:
        return None
    it = _apply_common(it, d)
    for pd in d.get("ports", []):
        _port_from_dict(pd, it)
    # [§8 항목17 6단계] TRIM cut 구간 복원 — _add_border_cut을 안 쓰고 직접 대입한다(그
    # 함수는 host.update()까지 호출하는데 이 시점엔 아직 씬에 안 들어가 있을 수 있어 불필요).
    cuts = d.get("cuts")
    if cuts:
        it._cuts = [(c[0], c[1], c[2]) for c in cuts]
    return it


# ---- 파일 저장/열기 -------------------------------------------------------
def save_document(scene, path: str, layers: list | None = None):
    # 아래→위(stacking) 순으로 저장해 열 때 순서·겹침이 보존되게 한다.
    # 자식 아이템(선/화살표에 부착된 라벨)은 부모 dict 안에 직렬화하므로 최상위에서 제외.
    serial = [(it, item_to_dict(it)) for it in reversed(scene.items())
              if it.parentItem() is None]
    serial = [(it, d) for it, d in serial if d is not None]
    idx_of = {id(it): i for i, (it, _d) in enumerate(serial)}
    # 화살표의 지속 연결 바인딩을 '저장 리스트 인덱스' + 고정 부착점(도형 로컬좌표)으로 기록.
    # 곡선(arrow)은 끝점 idx 0·1, 직선(sarrow)은 시작 idx 0·끝 idx last를 bind1·bind2에 매핑.
    for it, d in serial:
        if d["type"] in ("arrow", "sarrow"):
            end_idx = [0, 1] if d["type"] == "arrow" else [0, len(it._pts) - 1]
            for (key, pkey), bi in zip((("bind1", "bind1_pt"), ("bind2", "bind2_pt")), end_idx):
                sh = it._bound(bi)
                pt = it._bind_pt(bi)
                if sh is not None and id(sh) in idx_of and pt is not None:
                    d[key] = idx_of[id(sh)]
                    d[pkey] = [pt.x(), pt.y()]
                else:
                    d[key] = None
                    d[pkey] = None
    items = [d for _it, d in serial]
    doc = {"format": FORMAT, "version": VERSION, "items": items}
    if layers is not None:   # [신규기능] 레이어 목록(이름·표시·잠금) — 문서 레벨 메타
        doc["layers"] = layers
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


def insert_items(scene, items: list[dict]) -> list:
    """`items`(item dict 목록, `bind1`/`bind2`는 **이 목록 안에서의 인덱스**)를 기존
    씬에 그대로 추가한다 — `scene.clear()`를 하지 않는다는 점만 `load_document`와 다르고
    생성→바인딩 재연결→라벨 복원 3-pass 로직은 동일(둘이 공유하도록 여기로 추출,
    2026-08-11 §8 항목18 C단계 — AI 이미지→도면 결과를 기존 문서에 "삽입"하려면
    `load_document`의 `scene.clear()`가 걸림돌이었다).

    반환은 실제로 생성된 아이템 리스트(None 필터링됨) — 호출자가 `push_undo_add_many()`
    등으로 undo에 등록하거나 배치를 옮기는 데 쓴다."""
    created = [dict_to_item(d) for d in items]
    for it in created:
        if it is not None:
            scene.addItem(it)
    for d, it in zip(items, created):
        if it is None or d.get("type") not in ("arrow", "sarrow"):
            continue
        end_idx = [0, 1] if d["type"] == "arrow" else [0, len(it._pts) - 1]
        for (key, pkey), bi in zip((("bind1", "bind1_pt"), ("bind2", "bind2_pt")), end_idx):
            j = d.get(key)
            pt = d.get(pkey)
            if j is not None and 0 <= j < len(created) and created[j] is not None and pt is not None:
                it.set_bound(bi, created[j], QPointF(*pt))
    # [우리 확장] 선·화살표 라벨 복원(본체가 씬에 들어간 뒤라 자식 부착 가능).
    # [다중 라벨 2026-08-21] 화살표/직선화살은 새 "labels"(리스트) 키를 우선 읽고, 없으면
    # 옛 파일의 단수 "label" 키로 하위호환 폴백한다(둘 다 없으면 아무것도 안 함).
    for d, it in zip(items, created):
        if it is None:
            continue
        if isinstance(it, (_ArrowItem, _PolyArrowItem)) and d.get("labels"):
            for ld in d["labels"]:
                lbl = it.add_label_at_t(ld.get("t", 0.5), ld.get("off", 0.0))
                lbl.apply_font_size(ld.get("font", 16))
                lbl.setPlainText(ld.get("text", ""))
                lbl.apply_color(QColor(ld.get("color", _TEXT)))
                if ld.get("bg") is not None:
                    lbl.set_bg(QColor(*ld["bg"]))
            it._sync_label()
        elif d.get("label") and hasattr(it, "restore_label"):
            it.restore_label(d["label"])
            # [우리 확장] 화살표 라벨의 경로/곡선 위 위치(t·off) 복원 후 재배치(없으면 기본 중점).
            if isinstance(it, (_ArrowItem, _PolyArrowItem)):
                it._label_t = d["label"].get("t", 0.5)
                it._label_off = d["label"].get("off", 0.0)
                it._sync_label()
    return [it for it in created if it is not None]


def load_document(scene, path: str) -> int:
    """path의 문서를 scene에 로드(기존 내용 지움). 로드한 객체 수 반환.
    레이어 목록은 반환값에 안 실음(기존 25+ 호출부의 `== n` 계약을 안 깨려고) —
    필요하면 load_document_layers(path)를 별도 호출."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("format") != FORMAT:
        raise ValueError("Easy CAD 문서가 아닙니다.")
    scene.clear()
    return len(insert_items(scene, doc.get("items", [])))


def load_document_layers(path: str):
    """[신규기능] .ecad의 문서 레벨 레이어 목록만 읽는다(이름·표시·잠금).
    레이어 목록이 없는 옛 .ecad는 None(호출측이 기본 레이어로 리셋)."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    return doc.get("layers")
