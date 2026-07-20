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
    _PolyArrowItem, _SymbolItem, _ImageItem, _TitleBlockItem,
)

FORMAT = "easycad-doc"
VERSION = 1


def _col(c: QColor) -> str:
    return c.name(QColor.NameFormat.HexArgb)


# ---- 공통 변환 -------------------------------------------------------------
def _common(it) -> dict:
    o = it.transformOriginPoint()
    return {
        "pos": [it.pos().x(), it.pos().y()],
        "scale": it.scale(),
        "rotation": it.rotation(),
        "z": it.zValue(),
        "origin": [o.x(), o.y()],
    }


def _apply_common(it, d: dict):
    it.setPos(QPointF(*d["pos"]))
    it.setTransformOriginPoint(QPointF(*d.get("origin", [0.0, 0.0])))
    sc = d.get("scale", 1.0)
    it.setScale(sc if sc else 1.0)
    it.setRotation(d.get("rotation", 0.0))
    it.setZValue(d.get("z", 0))
    it.setFlags(
        it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable
    )
    return it


def _mkpen(d: dict) -> QPen:
    pen = QPen(QColor(d["pen"]))
    pen.setWidthF(float(d.get("width", 1.0)))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _mkbrush(d: dict) -> QBrush:
    fill = d.get("fill")
    return QBrush(QColor(fill)) if fill else QBrush(Qt.BrushStyle.NoBrush)


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
        )
    elif isinstance(it, _SymbolItem):
        r = it.rect()
        d.update(type="symbol", kind=it._kind, rect=[r.x(), r.y(), r.width(), r.height()],
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
                 auto_route=it._auto_route)   # [Stage1] 직교 자동 라우팅 상태
    elif isinstance(it, _LineItem):
        ln = it.line()
        d.update(type="line", line=[ln.x1(), ln.y1(), ln.x2(), ln.y2()],
                 pen=_col(it.pen().color()), width=it.pen().widthF())
    elif isinstance(it, _PathItem):
        d.update(type="path", elements=_path_elems(it.path()),
                 pen=_col(it.pen().color()), width=it.pen().widthF())
    elif isinstance(it, _TextItem):
        bg = it._bg
        d.update(type="text", text=it.toPlainText(),
                 color=_col(it.defaultTextColor()), font=it.font().pointSize(),
                 bg=None if bg is None else [bg.red(), bg.green(), bg.blue(), bg.alpha()])
    elif isinstance(it, _BadgeItem):
        d.update(type="badge", number=it._number, color=_col(it._color))
    else:
        return None
    # [우리 확장] 선·화살표·닫힌도형(네모·원·심볼)에 붙은 라벨 — 본체 dict 안에 함께 직렬화.
    if isinstance(it, (_ArrowItem, _LineItem, _PolyArrowItem,
                       _SymbolItem, _RectItem, _EllipseItem)) and it.has_label():
        lbl = it._label
        bg = lbl._bg
        d["label"] = {
            "text": lbl.toPlainText(),
            "color": _col(lbl.defaultTextColor()),
            "font": lbl.font().pointSize(),
            "bg": None if bg is None else [bg.red(), bg.green(), bg.blue(), bg.alpha()],
        }
    return d


def dict_to_item(d: dict):
    t = d.get("type")
    if t == "titleblock":
        it = _TitleBlockItem(d.get("size", "A2"), d.get("orient", "landscape"),
                             d.get("fields"))
    elif t == "image":
        it = _ImageItem(_b64_to_pixmap(d["data"]), QRectF(*d["rect"]))
    elif t == "arrow":
        it = _ArrowItem(QColor(d["color"]), d["width"], d.get("head", True))
        it.set_points(QPointF(*d["p1"]), QPointF(*d["p2"]))
        if d.get("ctrl1") is not None:
            it._ctrl1 = QPointF(*d["ctrl1"])
            it._ctrl2 = QPointF(*d["ctrl2"])
    elif t == "symbol":
        it = _SymbolItem(d.get("kind", "decision"), QRectF(*d["rect"]))
        it.setPen(_mkpen(d)); it.setBrush(_mkbrush(d))
    elif t == "rect":
        it = _RectItem(QRectF(*d["rect"])); it.setPen(_mkpen(d)); it.setBrush(_mkbrush(d))
    elif t == "ellipse":
        it = _EllipseItem(QRectF(*d["rect"])); it.setPen(_mkpen(d)); it.setBrush(_mkbrush(d))
    elif t == "sarrow":
        it = _PolyArrowItem(QColor(d["color"]), d["width"], d.get("head", True))
        it._pts = [QPointF(*xy) for xy in d["pts"]]
        it._auto_route = d.get("auto_route", False)   # [Stage1] 직교 자동 라우팅 상태
    elif t == "line":
        it = _LineItem(QLineF(*d["line"])); it.setPen(_mkpen(d))
    elif t == "path":
        it = _PathItem(_elems_to_path(d["elements"])); it.setPen(_mkpen(d))
    elif t == "text":
        it = _TextItem(QColor(d["color"])); it.apply_font_size(d.get("font", 16))
        it.setPlainText(d.get("text", ""))
        if d.get("bg") is not None:
            it.set_bg(QColor(*d["bg"]))
    elif t == "badge":
        it = _BadgeItem(d["number"], QColor(d["color"]))
    else:
        return None
    return _apply_common(it, d)


# ---- 파일 저장/열기 -------------------------------------------------------
def save_document(scene, path: str):
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
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)


def load_document(scene, path: str) -> int:
    """path의 문서를 scene에 로드(기존 내용 지움). 로드한 객체 수 반환."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("format") != FORMAT:
        raise ValueError("Easy CAD 문서가 아닙니다.")
    scene.clear()
    items = doc.get("items", [])
    # 1-pass: 아이템 생성. 2-pass: 인덱스로 바인딩 재연결.
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
    for d, it in zip(items, created):
        if it is not None and d.get("label") and hasattr(it, "restore_label"):
            it.restore_label(d["label"])
    return sum(1 for it in created if it is not None)
