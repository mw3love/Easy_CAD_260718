"""DXF 가져오기 (Phase 3 후반 — .dxf → scene 아이템).

dxf_export.py의 역매핑. **우리가 export한 DXF의 왕복(round-trip)이 1차 목표**이며,
export가 레이어 이름(EC_RECT·EC_ARROW…)에 실어 둔 타입 힌트로 아이템 종류를 결정한다.
임의 외부 DXF는 dxftype 기반 폴백(_generic_item)으로 손실 매핑한다.

좌표 — export의 (x, -y) Y-flip을 다시 뒤집어(involution) 화면 Y-down 좌표 복원.
       월드좌표로 바로 복원되므로 아이템은 항등 변환(또는 회전만) + 월드 기하로 재구성된다.
색   — true_color(RGB) → QColor. 없으면 검정.

승인된 결정 (2026-07-20):
  - 화살촉 삼각형 LWPOLYLINE: 독립 도형으로 되살리지 않고 **무시하되, tip 위치로
    화살표 head 방향(_head_at_end)만 복원**(무시+방향복원).
  - 심볼 kind: export가 외곽선 폴리라인으로 평탄화해 소실 → **외곽선(_PathItem)으로만 복원**.
  - 지속연결 바인딩·자식 라벨: DXF에 개념 없음 → 왕복에서 소실(라벨은 독립 텍스트로 복원).
"""
import math

from PyQt6.QtCore import Qt, QRectF, QLineF, QPointF
from PyQt6.QtGui import QColor, QPen, QBrush, QPainterPath

from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _LineItem, _PathItem, _ArrowItem, _TextItem, _BadgeItem,
    _PolyArrowItem,
)

# 레이어 → 타입 (dxf_export._LAYERS의 역)
_LAYER_TYPE = {
    "EC_RECT": "rect", "EC_ELLIPSE": "ellipse", "EC_LINE": "line",
    "EC_ARROW": "arrow", "EC_SARROW": "sarrow", "EC_PATH": "path",
    "EC_TEXT": "text", "EC_BADGE": "badge", "EC_SYMBOL": "symbol",
    "EC_LABEL": "label",
}


# ---- 좌표·색·공통 ----------------------------------------------------------
def _uf(x: float, y: float):
    """DXF (x,y) → 화면좌표: Y-flip 되돌림(export _w의 역, involution)."""
    return (x, -y)


def _color(e) -> QColor:
    rgb = getattr(e, "rgb", None)     # ezdxf: true_color 있으면 (r,g,b), 없으면 None
    if not rgb:
        return QColor("black")
    return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))


_APPID = "EASYCAD"


def _width_of(e, default: float = 1.0) -> float:
    """export가 실은 펜 두께 XDATA(AppID EASYCAD, 코드 1040) 복원. 없으면 기본값."""
    try:
        if e.has_xdata(_APPID):
            for code, val in e.get_xdata(_APPID):
                if code == 1040:
                    return float(val)
    except Exception:  # noqa: BLE001 — XDATA 없음/형식 이상은 기본값으로
        pass
    return default


def _pen(e, width: float = None) -> QPen:
    if width is None:
        width = _width_of(e)
    p = QPen(_color(e))
    p.setWidthF(width)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def _nobrush() -> QBrush:
    return QBrush(Qt.BrushStyle.NoBrush)


def _flag(it):
    it.setFlags(it.GraphicsItemFlag.ItemIsMovable | it.GraphicsItemFlag.ItemIsSelectable)
    return it


def _lw_points(e):
    """LWPOLYLINE 정점 → 화면좌표 리스트."""
    return [_uf(p[0], p[1]) for p in e.get_points()]


def _dist2(a, b) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


# ---- 도형 재구성 -----------------------------------------------------------
def _rect_item(pts, e):
    """4 꼭짓점(TL,TR,BR,BL 순 — export 순서)에서 회전을 흡수해 _RectItem 복원."""
    p0, p1, p3 = pts[0], pts[1], pts[3]
    ex = (p1[0] - p0[0], p1[1] - p0[1])       # 상단 변(로컬 +x)
    ey = (p3[0] - p0[0], p3[1] - p0[1])       # 좌측 변(로컬 +y)
    w = math.hypot(*ex)
    h = math.hypot(*ey)
    ang = math.degrees(math.atan2(ex[1], ex[0]))
    it = _RectItem(QRectF(0, 0, w, h))
    it.setPen(_pen(e))
    it.setBrush(_nobrush())
    it.setTransformOriginPoint(QPointF(0, 0))
    it.setRotation(ang)                        # 월드 = pos + R(ang)*local
    it.setPos(QPointF(p0[0], p0[1]))
    return _flag(it)


def _ellipse_item_circle(e):
    c = _uf(e.dxf.center.x, e.dxf.center.y)
    r = e.dxf.radius
    it = _EllipseItem(QRectF(c[0] - r, c[1] - r, 2 * r, 2 * r))
    it.setPen(_pen(e))
    it.setBrush(_nobrush())
    return _flag(it)


def _ellipse_item_ellipse(e):
    c = _uf(e.dxf.center.x, e.dxf.center.y)
    maj = e.dxf.major_axis
    mx, my = _uf(maj[0], maj[1])               # 방향 벡터도 Y-flip 되돌림
    a = math.hypot(mx, my)                      # 장반경
    b = a * e.dxf.ratio                         # 단반경
    ang = math.degrees(math.atan2(my, mx))
    it = _EllipseItem(QRectF(c[0] - a, c[1] - b, 2 * a, 2 * b))
    it.setPen(_pen(e))
    it.setBrush(_nobrush())
    it.setTransformOriginPoint(QPointF(c[0], c[1]))
    it.setRotation(ang)
    return _flag(it)


def _line_item(e):
    s = _uf(e.dxf.start.x, e.dxf.start.y)
    t = _uf(e.dxf.end.x, e.dxf.end.y)
    it = _LineItem(QLineF(s[0], s[1], t[0], t[1]))
    it.setPen(_pen(e))
    return _flag(it)


def _match_head(p_start, p_end, tips) -> bool:
    """화살촉 tip 목록에서 이 샤프트에 가장 가까운 tip을 소비, head_at_end 반환.

    export는 화살촉 tip을 끝점에 정확히 얹으므로 최근접이 곧 그 화살표의 촉이다.
    tip이 없으면 기본 True(끝쪽 촉).
    """
    if not tips:
        return True
    best_i, best_d, best_end = None, None, True
    for i, tp in enumerate(tips):
        ds = _dist2(tp, p_start)
        de = _dist2(tp, p_end)
        d = min(ds, de)
        if best_d is None or d < best_d:
            best_d, best_i, best_end = d, i, bool(de <= ds)   # np.bool_ → 파이썬 bool
    tips.pop(best_i)
    return best_end


def _arrow_from_spline(e, head_at_end: bool):
    cps = [_uf(p[0], p[1]) for p in e.control_points]
    it = _ArrowItem(_color(e), _width_of(e, 2.0), head_at_end)
    it.set_points(QPointF(*cps[0]), QPointF(*cps[-1]))
    if len(cps) >= 4:
        it._ctrl1 = QPointF(*cps[1])
        it._ctrl2 = QPointF(*cps[2])
    return _flag(it)


def _arrow_from_line(e, head_at_end: bool):
    s = _uf(e.dxf.start.x, e.dxf.start.y)
    t = _uf(e.dxf.end.x, e.dxf.end.y)
    it = _ArrowItem(_color(e), _width_of(e, 2.0), head_at_end)
    it.set_points(QPointF(*s), QPointF(*t))
    return _flag(it)


def _sarrow_item(pts, e, head_at_end: bool):
    it = _PolyArrowItem(_color(e), _width_of(e, 2.0), head_at_end)
    it._pts = [QPointF(x, y) for x, y in pts]
    return _flag(it)


def _text_item(e):
    if e.dxftype() == "MTEXT":
        txt = e.plain_text()
        h = e.dxf.char_height
    else:                                        # TEXT
        txt = e.dxf.text
        h = e.dxf.height
    ins = _uf(e.dxf.insert.x, e.dxf.insert.y)
    rot = e.dxf.rotation if e.dxf.hasattr("rotation") else 0.0
    it = _TextItem(_color(e))
    it.apply_font_size(max(round(h), 1))
    it.setPlainText(txt)
    it.setPos(QPointF(*ins))
    it.setRotation(-rot)                         # export: rotation = -it.rotation()
    return _flag(it)


def _build_badges(circles, texts):
    """EC_BADGE의 CIRCLE + MTEXT를 중심 근접으로 짝지어 _BadgeItem 복원."""
    out = []
    pool = list(texts)
    for circ in circles:
        c = _uf(circ.dxf.center.x, circ.dxf.center.y)
        # 가장 가까운 텍스트를 번호로.
        best_i, best_d = None, None
        for i, mt in enumerate(pool):
            ins = _uf(mt.dxf.insert.x, mt.dxf.insert.y)
            d = _dist2(c, ins)
            if best_d is None or d < best_d:
                best_d, best_i = d, i
        num = 0
        if best_i is not None:
            mt = pool.pop(best_i)
            raw = mt.plain_text() if mt.dxftype() == "MTEXT" else mt.dxf.text
            try:
                num = int(raw.strip())
            except (ValueError, AttributeError):
                num = 0
        it = _BadgeItem(num, _color(circ))
        it.setPos(QPointF(*c))
        r = circ.dxf.radius
        it.setScale(r / _BadgeItem._R if _BadgeItem._R else 1.0)
        out.append(_flag(it))
    return out


def _symbol_path_item(pts, closed, e):
    """심볼 외곽선 폴리라인 → _PathItem(kind 소실, 외곽선만)."""
    path = QPainterPath(QPointF(*pts[0]))
    for p in pts[1:]:
        path.lineTo(p[0], p[1])
    if closed:
        path.closeSubpath()
    it = _PathItem(path)
    it.setPen(_pen(e))
    return _flag(it)


def _build_paths(segments):
    """EC_PATH의 LINE/SPLINE 세그먼트를 끝점 연결로 이어 _PathItem(들) 복원.

    export가 펜 경로를 원소 순서대로 세그먼트 엔티티로 내보내므로, 순차로 잇되
    끝점이 안 맞으면(다른 경로) 새 _PathItem으로 분리한다.
    """
    items = []
    path = None
    last = None
    cur_pen = None

    def flush():
        nonlocal path
        if path is not None:
            it = _PathItem(path)
            it.setPen(cur_pen)
            items.append(_flag(it))
        path = None

    for e in segments:
        if e.dxftype() == "LINE":
            s = _uf(e.dxf.start.x, e.dxf.start.y)
            t = _uf(e.dxf.end.x, e.dxf.end.y)
            if path is None or last is None or _dist2(last, s) > 1e-6:
                flush()
                path = QPainterPath(QPointF(*s))
                cur_pen = _pen(e)
            path.lineTo(t[0], t[1])
            last = t
        elif e.dxftype() == "SPLINE":
            cps = [_uf(p[0], p[1]) for p in e.control_points]
            if len(cps) < 4:
                continue
            s, c1, c2, t = cps[0], cps[1], cps[2], cps[3]
            if path is None or last is None or _dist2(last, s) > 1e-6:
                flush()
                path = QPainterPath(QPointF(*s))
                cur_pen = _pen(e)
            path.cubicTo(c1[0], c1[1], c2[0], c2[1], t[0], t[1])
            last = t
    flush()
    return items


# ---- 외부 DXF 폴백 (손실 허용) ---------------------------------------------
def _generic_item(e):
    dxft = e.dxftype()
    if dxft == "LINE":
        return _line_item(e)
    if dxft == "CIRCLE":
        return _ellipse_item_circle(e)
    if dxft == "ELLIPSE":
        return _ellipse_item_ellipse(e)
    if dxft in ("MTEXT", "TEXT"):
        return _text_item(e)
    if dxft == "LWPOLYLINE":
        pts = _lw_points(e)
        if len(pts) < 2:
            return None
        path = QPainterPath(QPointF(*pts[0]))
        for p in pts[1:]:
            path.lineTo(p[0], p[1])
        if e.closed:
            path.closeSubpath()
        it = _PathItem(path)
        it.setPen(_pen(e))
        return _flag(it)
    if dxft in ("SPLINE", "ARC"):
        try:
            pts = [_uf(v[0], v[1]) for v in e.flattening(0.5)]
        except Exception:      # noqa: BLE001 — flatten 실패 시 이 엔티티만 건너뜀
            return None
        if len(pts) < 2:
            return None
        path = QPainterPath(QPointF(*pts[0]))
        for p in pts[1:]:
            path.lineTo(p[0], p[1])
        it = _PathItem(path)
        it.setPen(_pen(e))
        return _flag(it)
    return None


# ---- 진입점 ---------------------------------------------------------------
def import_dxf(scene, path: str, *, clear: bool = True) -> int:
    """path의 DXF를 scene에 로드. 반환: 생성된 최상위 아이템 수.

    clear=True면 기존 씬을 지우고 대체(파일 '열기' 시맨틱). False면 현재 씬에 추가(병합).
    """
    import ezdxf
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    if clear:
        scene.clear()

    arrow_shafts = []          # SPLINE/LINE on EC_ARROW
    arrow_head_tips = []       # 화살촉 tip
    sarrow_shafts = []         # (pts, entity)
    sarrow_head_tips = []
    badge_circles = []
    badge_texts = []
    path_segments = []
    built = []                 # 즉시 완성된 아이템

    for e in msp:
        layer = e.dxf.layer
        typ = _LAYER_TYPE.get(layer)
        dxft = e.dxftype()

        if typ == "rect" and dxft == "LWPOLYLINE":
            pts = _lw_points(e)
            if len(pts) >= 4:
                built.append(_rect_item(pts, e))
        elif typ == "ellipse" and dxft == "CIRCLE":
            built.append(_ellipse_item_circle(e))
        elif typ == "ellipse" and dxft == "ELLIPSE":
            built.append(_ellipse_item_ellipse(e))
        elif typ == "line" and dxft == "LINE":
            built.append(_line_item(e))
        elif typ == "arrow":
            if dxft == "LWPOLYLINE":                       # 화살촉 → tip만 취함
                pts = _lw_points(e)
                if pts:
                    arrow_head_tips.append(pts[0])
            elif dxft in ("SPLINE", "LINE"):
                arrow_shafts.append(e)
        elif typ == "sarrow" and dxft == "LWPOLYLINE":
            pts = _lw_points(e)
            if e.closed and len(pts) == 3:                 # 화살촉 → tip만 취함
                sarrow_head_tips.append(pts[0])
            elif len(pts) >= 2:
                sarrow_shafts.append((pts, e))
        elif typ == "path" and dxft in ("LINE", "SPLINE"):
            path_segments.append(e)
        elif typ in ("text", "label") and dxft in ("MTEXT", "TEXT"):
            built.append(_text_item(e))
        elif typ == "badge" and dxft == "CIRCLE":
            badge_circles.append(e)
        elif typ == "badge" and dxft in ("MTEXT", "TEXT"):
            badge_texts.append(e)
        elif typ == "symbol" and dxft == "LWPOLYLINE":
            pts = _lw_points(e)
            if len(pts) >= 2:
                built.append(_symbol_path_item(pts, e.closed, e))
        else:                                              # 미지 레이어 → 외부 DXF 폴백
            item = _generic_item(e)
            if item is not None:
                built.append(item)

    # 화살표(곡선/직선) — 화살촉 tip으로 head 방향 복원.
    for e in arrow_shafts:
        if e.dxftype() == "SPLINE":
            cps = [_uf(p[0], p[1]) for p in e.control_points]
            head = _match_head(cps[0], cps[-1], arrow_head_tips)
            built.append(_arrow_from_spline(e, head))
        else:
            s = _uf(e.dxf.start.x, e.dxf.start.y)
            t = _uf(e.dxf.end.x, e.dxf.end.y)
            head = _match_head(s, t, arrow_head_tips)
            built.append(_arrow_from_line(e, head))
    # 직교(꺾은선) 화살표.
    for pts, e in sarrow_shafts:
        head = _match_head(pts[0], pts[-1], sarrow_head_tips)
        built.append(_sarrow_item(pts, e, head))
    # 번호 배지(원+텍스트).
    built.extend(_build_badges(badge_circles, badge_texts))
    # 펜 경로.
    built.extend(_build_paths(path_segments))

    for it in built:
        scene.addItem(it)
    return len(built)
