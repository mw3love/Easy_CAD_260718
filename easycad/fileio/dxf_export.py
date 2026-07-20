"""DXF 내보내기 (Phase 3 — CAD 상호운용).

.ecad 문서모델의 각 아이템(document.py의 item_to_dict와 동일한 타입 체계)을
개별 DXF 엔티티로 매핑한다. 상용 CAD(AutoCAD 등)에서 「객체 개별 인식」이 목표.

매핑 (2026-07-20 승인):
    rect     → LWPOLYLINE(닫힘, 4점)
    ellipse  → CIRCLE(정원) / ELLIPSE
    line     → LINE
    sarrow   → LWPOLYLINE(열림) + 화살촉
    arrow    → SPLINE(베지어) 또는 LINE + 화살촉         ★ 베지어→SPLINE
    path(펜) → SPLINE(cubic) / LINE 세그먼트
    text/라벨 → MTEXT
    badge    → CIRCLE + MTEXT
    symbol   → LWPOLYLINE(들) — 곡선 kind는 폴리라인 평탄화

공통:
    좌표 — 각 아이템의 로컬 기하를 mapToScene로 월드화(회전·스케일 흡수) 후
           Y축 뒤집기(y→-y): 화면 Y-down → CAD Y-up.
    색   — QColor → DXF true_color(RGB 24bit), 개별 객체 색 보존.
    레이어 — 타입별 레이어(EC_RECT·EC_ARROW…)로 분리.
    단위 — 1 scene unit = 1 DXF drawing unit(mm 월드좌표 매핑은 후속 리팩터까지 보류).
"""
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsTextItem

from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _LineItem, _PathItem, _ArrowItem, _TextItem, _BadgeItem,
    _PolyArrowItem, _SymbolItem,
)

# 타입 → DXF 레이어. AutoCAD에서 켜고/끄기·색 일괄관리가 쉽도록 분리.
_LAYERS = {
    "rect": "EC_RECT", "ellipse": "EC_ELLIPSE", "line": "EC_LINE",
    "arrow": "EC_ARROW", "sarrow": "EC_SARROW", "path": "EC_PATH",
    "text": "EC_TEXT", "badge": "EC_BADGE", "symbol": "EC_SYMBOL",
    "label": "EC_LABEL",
}


# ---- 좌표·색 공통 ----------------------------------------------------------
def _w(it, x: float, y: float):
    """아이템 로컬 (x,y) → 월드좌표 + Y축 뒤집기(CAD Y-up)."""
    sp = it.mapToScene(QPointF(x, y))
    return (sp.x(), -sp.y())


def _true_color(qc) -> int:
    import ezdxf
    return ezdxf.rgb2int((qc.red(), qc.green(), qc.blue()))


def _attrs(layer: str, color) -> dict:
    return {"layer": layer, "true_color": _true_color(color)}


def _unit(dx: float, dy: float):
    n = (dx * dx + dy * dy) ** 0.5
    return (dx / n, dy / n) if n > 1e-9 else (0.0, 0.0)


def _arrowhead(msp, tip, near, width: float, attrs: dict):
    """tip(월드)에 near→tip 방향의 닫힌 삼각형 화살촉 LWPOLYLINE."""
    ux, uy = _unit(tip[0] - near[0], tip[1] - near[1])
    if ux == 0.0 and uy == 0.0:
        return
    s = max(width * 3.0, 6.0)           # 화살촉 길이
    px, py = -uy, ux                     # 좌우 수직
    base = (tip[0] - ux * s, tip[1] - uy * s)
    b1 = (base[0] + px * s * 0.4, base[1] + py * s * 0.4)
    b2 = (base[0] - px * s * 0.4, base[1] - py * s * 0.4)
    msp.add_lwpolyline([tip, b1, b2], close=True, dxfattribs=attrs)


# ---- 아이템별 export -------------------------------------------------------
def _export_symbol(msp, it):
    attrs = _attrs(_LAYERS["symbol"], it.pen().color())
    for poly in it._sym_path().toSubpathPolygons():
        pts = [_w(it, p.x(), p.y()) for p in poly]
        if len(pts) < 2:
            continue
        # QPolygonF는 닫힌 서브패스도 시작점을 끝에 복제하지 않을 수 있어 근접 판정.
        closed = (abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6)
        if closed:
            pts = pts[:-1]
        msp.add_lwpolyline(pts, close=closed, dxfattribs=attrs)


def _export_rect(msp, it):
    r = it.rect()
    pts = [_w(it, r.left(), r.top()), _w(it, r.right(), r.top()),
           _w(it, r.right(), r.bottom()), _w(it, r.left(), r.bottom())]
    msp.add_lwpolyline(pts, close=True, dxfattribs=_attrs(_LAYERS["rect"], it.pen().color()))


def _export_ellipse(msp, it):
    r = it.rect()
    attrs = _attrs(_LAYERS["ellipse"], it.pen().color())
    cx, cy = _w(it, r.center().x(), r.center().y())
    # 로컬 반경축 끝점을 월드화 → 회전·비균일 스케일 흡수.
    ax = _w(it, r.center().x() + r.width() / 2.0, r.center().y())
    ay = _w(it, r.center().x(), r.center().y() + r.height() / 2.0)
    va = (ax[0] - cx, ax[1] - cy)
    vb = (ay[0] - cx, ay[1] - cy)
    la = (va[0] ** 2 + va[1] ** 2) ** 0.5
    lb = (vb[0] ** 2 + vb[1] ** 2) ** 0.5
    if abs(la - lb) < 1e-6:
        msp.add_circle((cx, cy), la, dxfattribs=attrs)
        return
    major, minor = (va, lb / la) if la >= lb else (vb, la / lb)
    msp.add_ellipse((cx, cy), major_axis=(major[0], major[1], 0.0),
                    ratio=minor, dxfattribs=attrs)


def _export_line(msp, it):
    ln = it.line()
    msp.add_line(_w(it, ln.x1(), ln.y1()), _w(it, ln.x2(), ln.y2()),
                 dxfattribs=_attrs(_LAYERS["line"], it.pen().color()))


def _export_arrow(msp, it):
    attrs = _attrs(_LAYERS["arrow"], it._color)
    p1 = (it._p1.x(), it._p1.y())
    p2 = (it._p2.x(), it._p2.y())
    if it._ctrl1 is not None and it._ctrl2 is not None:
        # 3차 베지어 = 4점 클램프 B-스플라인(degree 3, open uniform 노트).
        ctrl = [_w(it, *p1), _w(it, it._ctrl1.x(), it._ctrl1.y()),
                _w(it, it._ctrl2.x(), it._ctrl2.y()), _w(it, *p2)]
        msp.add_open_spline(ctrl, degree=3, dxfattribs=attrs)
    else:
        msp.add_line(_w(it, *p1), _w(it, *p2), dxfattribs=attrs)
    if it._head_at_end:
        near = it._ctrl2 if it._ctrl2 is not None else it._p1
        _arrowhead(msp, _w(it, *p2), _w(it, near.x(), near.y()), it._width, attrs)
    else:
        near = it._ctrl1 if it._ctrl1 is not None else it._p2
        _arrowhead(msp, _w(it, *p1), _w(it, near.x(), near.y()), it._width, attrs)


def _export_sarrow(msp, it):
    attrs = _attrs(_LAYERS["sarrow"], it._color)
    pts = [_w(it, p.x(), p.y()) for p in it._pts]
    if len(pts) >= 2:
        msp.add_lwpolyline(pts, close=False, dxfattribs=attrs)
        if it._head_at_end:
            _arrowhead(msp, pts[-1], pts[-2], it._width, attrs)
        else:
            _arrowhead(msp, pts[0], pts[1], it._width, attrs)


def _export_path(msp, it):
    attrs = _attrs(_LAYERS["path"], it.pen().color())
    path = it.path()
    ET = QPainterPath.ElementType
    i, n = 0, path.elementCount()
    cur = None
    while i < n:
        e = path.elementAt(i)
        if e.type == ET.MoveToElement:
            cur = (e.x, e.y); i += 1
        elif e.type == ET.LineToElement:
            msp.add_line(_w(it, *cur), _w(it, e.x, e.y), dxfattribs=attrs)
            cur = (e.x, e.y); i += 1
        elif e.type == ET.CurveToElement:
            c2 = path.elementAt(i + 1)
            ep = path.elementAt(i + 2)
            ctrl = [_w(it, *cur), _w(it, e.x, e.y), _w(it, c2.x, c2.y), _w(it, ep.x, ep.y)]
            msp.add_open_spline(ctrl, degree=3, dxfattribs=attrs)
            cur = (ep.x, ep.y); i += 3
        else:
            i += 1


def _export_text(msp, it, layer: str):
    txt = it.toPlainText()
    if not txt:
        return
    ins = _w(it, 0.0, 0.0)               # 텍스트 아이템 좌상단
    height = max(float(it.font().pointSize()), 1.0)
    mtext = msp.add_mtext(txt, dxfattribs=_attrs(layer, it.defaultTextColor()))
    mtext.dxf.char_height = height
    mtext.dxf.insert = (ins[0], ins[1], 0.0)
    mtext.dxf.attachment_point = 1       # top-left
    mtext.dxf.rotation = -it.rotation()  # Y-flip → 회전 부호 반전


def _export_badge(msp, it):
    attrs = _attrs(_LAYERS["badge"], it._color)
    c = _w(it, 0.0, 0.0)
    rad = it._R * (it.scale() or 1.0)
    msp.add_circle(c, rad, dxfattribs=attrs)
    mtext = msp.add_mtext(str(it._number), dxfattribs=attrs)
    mtext.dxf.char_height = max(rad, 1.0)
    mtext.dxf.insert = (c[0], c[1], 0.0)
    mtext.dxf.attachment_point = 5       # middle-center


def export_dxf(scene, path: str) -> bool:
    """scene의 모든 아이템을 DXF로 저장. 성공 시 True.

    라벨(_TextItem 자식)은 EC_LABEL 레이어, 독립 텍스트는 EC_TEXT 레이어로 구분한다.
    """
    import ezdxf
    doc = ezdxf.new("R2010")             # true_color·MTEXT·SPLINE 지원 버전
    for name in _LAYERS.values():
        doc.layers.add(name)
    msp = doc.modelspace()

    for it in scene.items():
        try:
            if isinstance(it, _SymbolItem):      # QGraphicsRectItem 하위 → rect보다 먼저
                _export_symbol(msp, it)
            elif isinstance(it, _RectItem):
                _export_rect(msp, it)
            elif isinstance(it, _EllipseItem):
                _export_ellipse(msp, it)
            elif isinstance(it, _ArrowItem):
                _export_arrow(msp, it)
            elif isinstance(it, _PolyArrowItem):
                _export_sarrow(msp, it)
            elif isinstance(it, _LineItem):
                _export_line(msp, it)
            elif isinstance(it, _PathItem):
                _export_path(msp, it)
            elif isinstance(it, _BadgeItem):
                _export_badge(msp, it)
            elif isinstance(it, _TextItem):
                # 부모가 있으면 부착 라벨 → EC_LABEL, 없으면 독립 텍스트.
                layer = _LAYERS["label"] if it.parentItem() is not None else _LAYERS["text"]
                _export_text(msp, it, layer)
            elif isinstance(it, QGraphicsTextItem):
                _export_text(msp, it, _LAYERS["text"])
        except Exception:  # noqa: BLE001 — 한 객체 실패가 전체 export를 막지 않게.
            continue

    doc.saveas(path)
    return True
