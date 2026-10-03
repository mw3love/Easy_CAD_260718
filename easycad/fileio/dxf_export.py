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
    polygon  → LWPOLYLINE(닫힘/열림, §8 항목21) — 2026-08-31까지 분기 누락으로 통째로 드롭됨

공통:
    좌표 — 각 아이템의 로컬 기하를 mapToScene로 월드화(회전·스케일 흡수) 후
           Y축 뒤집기(y→-y): 화면 Y-down → CAD Y-up.
    색   — QColor → DXF true_color(RGB 24bit), 개별 객체 색 보존.
    레이어 — 타입별 레이어(EC_RECT·EC_ARROW…)로 분리.
    단위 — 1 scene unit = 1 DXF drawing unit(mm 월드좌표 매핑은 후속 리팩터까지 보류).
    초기 뷰 — `_set_view_extents`가 EXTMIN/EXTMAX·*Active 뷰포트를 실제 콘텐츠 bbox로
             채워, 다른 CAD가 파일을 열 때 콘텐츠가 화면 밖에 있어 빈 화면으로 뜨는 것을
             방지(좌표값 자체는 안 바꿈 — 순수 "열자마자 보여줄 구역" 힌트).
"""
import math
import os
import shutil
import tempfile

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainterPath
from PyQt6.QtWidgets import QGraphicsTextItem

from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _LineItem, _PathItem, _ArrowItem, _TextItem, _BadgeItem,
    _PolyArrowItem, _SymbolItem, _PolygonItem, build_trimmed_border_path,
)
from easycad.fileio.safe_write import write_via_temp

# 타입 → DXF 레이어. AutoCAD에서 켜고/끄기·색 일괄관리가 쉽도록 분리.
_LAYERS = {
    "rect": "EC_RECT", "ellipse": "EC_ELLIPSE", "line": "EC_LINE",
    "arrow": "EC_ARROW", "sarrow": "EC_SARROW", "path": "EC_PATH",
    "text": "EC_TEXT", "badge": "EC_BADGE", "symbol": "EC_SYMBOL",
    "label": "EC_LABEL", "polygon": "EC_POLYGON",
    "fill": "EC_FILL",   # [§8 항목31] 채우기(HATCH) — 사용자 결정: 별도 레이어(CAD에서 한 번에 끄기·색 바꾸기)
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


# 펜 두께는 DXF 표준 lineweight가 enum으로 스냅돼(6→9) 무손실 왕복이 안 되므로,
# 앱 전용 XDATA(AppID EASYCAD, 코드 1040 float)로 실어 import가 정확히 복원하게 한다.
_APPID = "EASYCAD"


def _px_to_lineweight(width: float) -> int:
    """펜 두께(px) → DXF 표준 lineweight(1/100mm) 중 가장 가까운 유효 enum 값.
    외부 CAD(AutoCAD) '표시 전용' — 정밀 왕복은 XDATA(1040)가 담당한다. px×10 스케일
    (3px→0.30mm)이라 AutoCAD에서 굵기가 시각적으로 구분되되 과하지 않게 잡는다."""
    from ezdxf.lldxf.const import VALID_DXF_LINEWEIGHTS as _V
    raw = float(width) * 10.0
    return min(_V, key=lambda v: abs(v - raw))


def _wx(entity, width):
    """생성된 엔티티에 펜 두께를 부착: XDATA(1040, 무손실 왕복) + 표준 lineweight(외부 CAD 표시)."""
    try:
        entity.set_xdata(_APPID, [(1040, float(width))])
    except Exception:  # noqa: BLE001 — 두께 부착 실패가 export를 막지 않게
        pass
    try:
        entity.dxf.lineweight = _px_to_lineweight(width)   # [M2 #3] AutoCAD 두께 표시
    except Exception:  # noqa: BLE001
        pass
    return entity


# [M2 #3] Qt 선스타일 → DXF linetype. Solid는 CONTINUOUS(기본)라 매핑 생략(=미표기).
_QT_TO_LTYPE = {
    Qt.PenStyle.DashLine: "DASHED",
    Qt.PenStyle.DotLine: "DOT",
    Qt.PenStyle.DashDotLine: "DASHDOT",
    Qt.PenStyle.DashDotDotLine: "DIVIDE",
}
# ezdxf 기본 테이블에 없을 수 있어(버전 무관 안전) 직접 등록할 패턴: [total, dash, -gap, ...].
# total = 나머지 요소 절댓값 합. Easy CAD 좌표=픽셀 스케일(화살표 100+ 단위)이라 대시를
# 픽셀급(8/4px)으로 잡아야 외부 CAD(AutoCAD)에서 실선처럼 뭉치지 않는다(기본 LTSCALE=1 기준).
_LTYPE_PATTERNS = {
    "DASHED":  ([12.0, 8.0, -4.0], "Dashed __ __ __ __"),
    "DOT":     ([4.0, 0.0, -4.0], "Dotted . . . ."),
    "DASHDOT": ([16.0, 8.0, -4.0, 0.0, -4.0], "Dash dot __ . __ ."),
    "DIVIDE":  ([20.0, 8.0, -4.0, 0.0, -4.0, 0.0, -4.0], "Divide __ . . __ . ."),
}


def _ensure_linetypes(doc):
    """export에 필요한 linetype이 doc에 없으면 패턴과 함께 등록."""
    for name, (pattern, desc) in _LTYPE_PATTERNS.items():
        if not doc.linetypes.has_entry(name):
            doc.linetypes.add(name, pattern=pattern, description=desc)


def _with_linetype(attrs: dict, style) -> dict:
    """attrs 사본에 선스타일을 linetype으로 실어 반환(solid면 그대로). 화살촉엔 쓰지 않는다."""
    lt = _QT_TO_LTYPE.get(style)
    if lt is None:
        return attrs
    out = dict(attrs)
    out["linetype"] = lt
    return out


def _unit(dx: float, dy: float):
    n = (dx * dx + dy * dy) ** 0.5
    return (dx / n, dy / n) if n > 1e-9 else (0.0, 0.0)


def _arrowhead(msp, tip, near, width: float, attrs: dict, scale: float = 1.0):
    """tip(월드)에 near→tip 방향의 닫힌 삼각형 화살촉 LWPOLYLINE."""
    ux, uy = _unit(tip[0] - near[0], tip[1] - near[1])
    if ux == 0.0 and uy == 0.0:
        return
    s = max(width * 3.0, 6.0) * scale   # 화살촉 길이 — [화살촉 크기 배율, 2026-08-21]
    px, py = -uy, ux                     # 좌우 수직
    base = (tip[0] - ux * s, tip[1] - uy * s)
    b1 = (base[0] + px * s * 0.4, base[1] + py * s * 0.4)
    b2 = (base[0] - px * s * 0.4, base[1] - py * s * 0.4)
    msp.add_lwpolyline([tip, b1, b2], close=True, dxfattribs=attrs)


# ---- 아이템별 export -------------------------------------------------------
# ---- [§8 항목31, 2026-10-03] 채우기 → 단색 HATCH ------------------------------
# 예전엔 도형 채움색이 DXF에서 통째로 사라졌다(§8 항목7 당시 "DXF는 skip"). 사용자 결정:
# 별도 EC_FILL 레이어, 투명도 유지, 도형 4종(사각·원·심볼·닫힌 다각형) + 글자 배경 + 채운 패스.
# 각 도형 내보내기가 **테두리보다 먼저** 부르므로 다른 CAD에서도 채우기가 선 아래에 깔린다.
def _brush_color(it):
    b = it.brush()
    return None if b.style() == Qt.BrushStyle.NoBrush else QColor(b.color())


def _export_fill(msp, it, loops_local, color):
    """아이템 로컬 좌표의 닫힌 고리들(첫 고리=바깥, 나머지=구멍도 가능 — 홀짝 규칙)을 한 HATCH로."""
    if color is None or color.alpha() == 0:
        return
    loops = [[_w(it, p.x(), p.y()) for p in loop] for loop in loops_local if len(loop) >= 3]
    if not loops:
        return
    hatch = msp.add_hatch(dxfattribs={"layer": _LAYERS["fill"]})
    hatch.set_solid_fill(rgb=(color.red(), color.green(), color.blue()))
    for loop in loops:
        hatch.paths.add_polyline_path(loop, is_closed=True)
    if color.alpha() < 255:
        hatch.transparency = 1.0 - color.alpha() / 255.0


def _path_loops(path):
    """QPainterPath의 서브패스들 → 점 목록(채우기는 열린 서브패스도 암묵적으로 닫으므로 3점 이상 전부)."""
    out = []
    for poly in path.toSubpathPolygons():
        pts = [QPointF(p) for p in poly]
        if len(pts) >= 2 and (pts[0] - pts[-1]).manhattanLength() < 1e-6:
            pts = pts[:-1]
        if len(pts) >= 3:
            out.append(pts)
    return out


def _rect_loop(r):
    return [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]


def _ellipse_loop(r, n: int = 72):
    cx, cy, rx, ry = r.center().x(), r.center().y(), r.width() / 2.0, r.height() / 2.0
    return [QPointF(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def _export_trimmed_border(msp, it, attrs):
    """[신규기능 §8-12, §8 항목17 7단계부터 앱 화면도 같은 경로] 부착된 포트/TRIM cut이 걸친
    구간만큼 실제로 끊어서 내보낸다 — 진짜 분절 데이터(`build_trimmed_border_path`)를 그대로
    LINE 엔티티 여러 개로 내보내므로 AutoCAD에서 열어도 실제로 끊겨 있다."""
    path = build_trimmed_border_path(it)
    ET = QPainterPath.ElementType
    cur = None
    for i in range(path.elementCount()):
        e = path.elementAt(i)
        if e.type == ET.MoveToElement:
            cur = (e.x, e.y)
        elif e.type == ET.LineToElement and cur is not None:
            _wx(msp.add_line(_w(it, *cur), _w(it, e.x, e.y), dxfattribs=attrs), it.pen().widthF())
            cur = (e.x, e.y)


def _export_symbol(msp, it):
    _export_fill(msp, it, _path_loops(it._sym_path()), _brush_color(it))   # [§8 항목31]
    attrs = _with_linetype(_attrs(_LAYERS["symbol"], it.pen().color()), it.pen().style())
    # [§8 항목17 6단계] 포트뿐 아니라 TRIM cut(`_cuts`)도 있으면 진짜 분절로 내보낸다 —
    # 둘 다 build_trimmed_border_path가 이미 같은 gaps_by_edge로 합쳐서 처리함(2단계).
    if getattr(it, "_ports", None) or getattr(it, "_cuts", None):
        _export_trimmed_border(msp, it, attrs)
        return
    for poly in it._sym_path().toSubpathPolygons():
        pts = [_w(it, p.x(), p.y()) for p in poly]
        if len(pts) < 2:
            continue
        # QPolygonF는 닫힌 서브패스도 시작점을 끝에 복제하지 않을 수 있어 근접 판정.
        closed = (abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6)
        if closed:
            pts = pts[:-1]
        _wx(msp.add_lwpolyline(pts, close=closed, dxfattribs=attrs), it.pen().widthF())


def _export_rect(msp, it):
    _export_fill(msp, it, [_rect_loop(it.rect())], _brush_color(it))   # [§8 항목31]
    attrs = _with_linetype(_attrs(_LAYERS["rect"], it.pen().color()), it.pen().style())
    if getattr(it, "_ports", None) or getattr(it, "_cuts", None):
        _export_trimmed_border(msp, it, attrs)
        return
    r = it.rect()
    pts = [_w(it, r.left(), r.top()), _w(it, r.right(), r.top()),
           _w(it, r.right(), r.bottom()), _w(it, r.left(), r.bottom())]
    _wx(msp.add_lwpolyline(pts, close=True, dxfattribs=attrs), it.pen().widthF())


def _export_polygon(msp, it):
    """[§8 항목21 다각형/폴리라인 도구 — DXF 내보내기 누락 수정] v1 설계문서가 "후속으로
    미룸"으로 명시한 뒤 한 번도 뒤이어지지 않아, 이 클래스가 `_RectItem`을 상속하지 않는
    별도 클래스라 기존 isinstance 분기 어디에도 걸리지 않고 통째로 드롭되고 있었다(실사용
    재현: 고양이 심볼의 귀·코 삼각형이 EasyCAD엔 있는데 DXF엔 없음). 닫힌 다각형이면
    rect/symbol과 같은 관례로 `_cuts`(TRIM) 여부를 확인."""
    if it._closed:   # [§8 항목31] 열린 폴리라인은 채움 개념 없음
        _export_fill(msp, it, [list(it.local_pts())], _brush_color(it))
    attrs = _with_linetype(_attrs(_LAYERS["polygon"], it.pen().color()), it.pen().style())
    if it._closed and getattr(it, "_cuts", None):
        _export_trimmed_border(msp, it, attrs)
        return
    pts = [_w(it, p.x(), p.y()) for p in it.local_pts()]
    if len(pts) < 2:
        return
    _wx(msp.add_lwpolyline(pts, close=it._closed, dxfattribs=attrs), it.pen().widthF())


def _export_ellipse(msp, it):
    r = it.rect()
    _export_fill(msp, it, [_ellipse_loop(r)], _brush_color(it))   # [§8 항목31]
    attrs = _with_linetype(_attrs(_LAYERS["ellipse"], it.pen().color()), it.pen().style())
    # [§8 항목17 6단계] rect/symbol과 달리 이 함수는 원래 포트/cut 분기가 아예 없었다(선분-원
    # 전용 add_circle/add_ellipse 엔티티라 gap을 뚫을 방법이 없었기 때문) — 있으면
    # _export_trimmed_border의 폴리곤 근사(2단계 결정, 원/타원 cut을 이미 폴리곤으로 다룸)로
    # LINE 다발로 대체 내보낸다. 원형 포트 DXF 내보내기가 이제껏 안 잘려 나가던 잠재 버그였다.
    if getattr(it, "_ports", None) or getattr(it, "_cuts", None):
        _export_trimmed_border(msp, it, attrs)
        return
    cx, cy = _w(it, r.center().x(), r.center().y())
    # 로컬 반경축 끝점을 월드화 → 회전·비균일 스케일 흡수.
    ax = _w(it, r.center().x() + r.width() / 2.0, r.center().y())
    ay = _w(it, r.center().x(), r.center().y() + r.height() / 2.0)
    va = (ax[0] - cx, ax[1] - cy)
    vb = (ay[0] - cx, ay[1] - cy)
    la = (va[0] ** 2 + va[1] ** 2) ** 0.5
    lb = (vb[0] ** 2 + vb[1] ** 2) ** 0.5
    if abs(la - lb) < 1e-6:
        _wx(msp.add_circle((cx, cy), la, dxfattribs=attrs), it.pen().widthF())
        return
    major, minor = (va, lb / la) if la >= lb else (vb, la / lb)
    _wx(msp.add_ellipse((cx, cy), major_axis=(major[0], major[1], 0.0),
                        ratio=minor, dxfattribs=attrs), it.pen().widthF())


def _export_line(msp, it):
    ln = it.line()
    attrs = _with_linetype(_attrs(_LAYERS["line"], it.pen().color()), it.pen().style())
    _wx(msp.add_line(_w(it, ln.x1(), ln.y1()), _w(it, ln.x2(), ln.y2()),
                     dxfattribs=attrs), it.pen().widthF())


def _export_arrow(msp, it):
    attrs = _attrs(_LAYERS["arrow"], it._color)
    body = _with_linetype(attrs, it._style)   # [M2 #3] 몸통만 점선, 화살촉은 solid(attrs)
    p1 = (it._p1.x(), it._p1.y())
    p2 = (it._p2.x(), it._p2.y())
    if it._ctrl1 is not None and it._ctrl2 is not None:
        # 3차 베지어 = 4점 클램프 B-스플라인(degree 3, open uniform 노트).
        ctrl = [_w(it, *p1), _w(it, it._ctrl1.x(), it._ctrl1.y()),
                _w(it, it._ctrl2.x(), it._ctrl2.y()), _w(it, *p2)]
        _wx(msp.add_open_spline(ctrl, degree=3, dxfattribs=body), it._width)
    else:
        _wx(msp.add_line(_w(it, *p1), _w(it, *p2), dxfattribs=body), it._width)
    hscale = getattr(it, "_head_scale", 1.0)   # [화살촉 크기 배율, 2026-08-21]
    if it._head_at_end:
        near = it._ctrl2 if it._ctrl2 is not None else it._p1
        _arrowhead(msp, _w(it, *p2), _w(it, near.x(), near.y()), it._width, attrs, hscale)
    if getattr(it, "_head_at_start", False):   # [양방향 화살표] 끝과 독립 — 둘 다 가능
        near = it._ctrl1 if it._ctrl1 is not None else it._p2
        _arrowhead(msp, _w(it, *p1), _w(it, near.x(), near.y()), it._width, attrs, hscale)


def _export_sarrow(msp, it):
    attrs = _attrs(_LAYERS["sarrow"], it._color)
    body = _with_linetype(attrs, it._style)   # [M2 #3] 몸통만 점선, 화살촉은 solid(attrs)
    pts = [_w(it, p.x(), p.y()) for p in it._pts]
    hscale = getattr(it, "_head_scale", 1.0)   # [화살촉 크기 배율, 2026-08-21]
    if len(pts) >= 2:
        _wx(msp.add_lwpolyline(pts, close=False, dxfattribs=body), it._width)
        if it._head_at_end:
            _arrowhead(msp, pts[-1], pts[-2], it._width, attrs, hscale)
        if getattr(it, "_head_at_start", False):   # [양방향 화살표]
            _arrowhead(msp, pts[0], pts[1], it._width, attrs, hscale)


def _export_path(msp, it):
    path = it.path()
    _export_fill(msp, it, _path_loops(path), _brush_color(it))   # [§8 항목31] 채운 패스(가져온 해치 등)
    attrs = _with_linetype(_attrs(_LAYERS["path"], it.pen().color()), it.pen().style())
    ET = QPainterPath.ElementType
    i, n = 0, path.elementCount()
    cur = None
    while i < n:
        e = path.elementAt(i)
        if e.type == ET.MoveToElement:
            cur = (e.x, e.y); i += 1
        elif e.type == ET.LineToElement:
            _wx(msp.add_line(_w(it, *cur), _w(it, e.x, e.y), dxfattribs=attrs), it.pen().widthF())
            cur = (e.x, e.y); i += 1
        elif e.type == ET.CurveToElement:
            c2 = path.elementAt(i + 1)
            ep = path.elementAt(i + 2)
            ctrl = [_w(it, *cur), _w(it, e.x, e.y), _w(it, c2.x, c2.y), _w(it, ep.x, ep.y)]
            _wx(msp.add_open_spline(ctrl, degree=3, dxfattribs=attrs), it.pen().widthF())
            cur = (ep.x, ep.y); i += 3
        else:
            i += 1


def _export_text(msp, it, layer: str):
    txt = it.toPlainText()
    if not txt:
        return
    bg = getattr(it, "_bg", None)   # [§8 항목31] 글자 배경(화면은 둥근 모서리 — DXF는 직사각형)
    if bg is not None:
        _export_fill(msp, it, [_rect_loop(it._content_rect().adjusted(1, 1, -1, -1))], QColor(bg))
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


def _set_view_extents(doc, scene):
    """[실사용 질문, 2026-08-31] EasyCAD 캔버스는 고정 원점이 없는 무한캔버스라 콘텐츠가
    DXF 월드좌표 (0,0)에서 얼마나·어느 방향으로 떨어져 있는지는 그 문서를 작업하며 사용자가
    화면을 얼마나 팬(pan)했는지에 좌우된다(우연의 산물) — `ezdxf.new()`의 기본 `*Active`
    뷰포트(원점 중심, 세로 1000 범위)를 그대로 두면, 콘텐츠가 그 범위 밖에 있을 때 AutoCAD가
    파일을 열자마자 빈 화면을 보여준다(Zoom Extents를 눌러야 찾음). 좌표값 자체는 절대 안
    건드리고(재수입 시 위치 불변), "열자마자 보여줄 구역"만 실제 콘텐츠 bbox로 채운다."""
    r = scene.itemsBoundingRect()
    if r.isEmpty():
        return
    xmin, xmax = r.left(), r.right()
    ymin, ymax = -r.bottom(), -r.top()   # Y-flip: 화면 Y-down → CAD Y-up (._w()와 동일 규칙)
    # [함정] doc.header["$EXTMIN"]에 직접 써도 ezdxf.save()가 내부적으로 update_extents()/
    # update_limits()를 호출해 modelspace 레이아웃 자신의 dxf.extmin/limmin 값으로 헤더를
    # 덮어써버린다(실측 확인) — 그래서 헤더가 아니라 레이아웃 쪽 속성에 써야 살아남는다.
    msp = doc.modelspace()
    msp.dxf.extmin = (xmin, ymin, 0.0)
    msp.dxf.extmax = (xmax, ymax, 0.0)
    msp.dxf.limmin = (xmin, ymin)
    msp.dxf.limmax = (xmax, ymax)
    width, height = max(xmax - xmin, 1.0), max(ymax - ymin, 1.0)
    try:
        vport = doc.viewports.get_config("*Active")[0]
        vport.dxf.center = ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0)
        vport.dxf.height = height * 1.1   # 10% 여백 — 콘텐츠가 화면 가장자리에 딱 붙지 않게
        vport.dxf.aspect_ratio = width / height
    except Exception:  # noqa: BLE001 — 뷰포트 힌트 실패가 export 자체를 막지 않게
        pass


def _build_dxf_doc(scene, stats: dict | None = None):
    """scene → ezdxf.Drawing(저장 전 상태). export_dxf/export_dwg가 공유한다.
    [§8 DWG 자동변환 후속, 2026-08-14] DWG 내보내기가 필요해지며 저장 직전까지의 변환
    로직을 추출 — 도형→엔티티 매핑 자체는 한 글자도 안 바뀜(순수 리팩터)."""
    import ezdxf
    doc = ezdxf.new("R2010")             # true_color·MTEXT·SPLINE 지원 버전
    doc.header["$LWDISPLAY"] = 1          # [M2 #3] 선가중치 표시 ON — 없으면 AutoCAD가 두께 숨김
    if not doc.appids.has_entry(_APPID):  # 펜 두께 XDATA용 AppID
        doc.appids.add(_APPID)
    _ensure_linetypes(doc)                # [M2 #3] 점선 등 선스타일 linetype 등록
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
            elif isinstance(it, _PolygonItem):
                _export_polygon(msp, it)
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
            # [점검 3단계 2026-10-03] 조용히 빠지던 것 — 개수를 세어 호출부가 알리게 한다.
            if stats is not None:
                stats["failed"] = stats.get("failed", 0) + 1
            continue

    _set_view_extents(doc, scene)
    return doc


def export_dxf(scene, path: str, stats: dict | None = None) -> bool:
    """scene의 모든 아이템을 DXF로 저장. 성공 시 True.

    라벨(_TextItem 자식)은 EC_LABEL 레이어, 독립 텍스트는 EC_TEXT 레이어로 구분한다.
    `stats` dict를 넘기면 변환에 실패해 빠진 객체 수를 `stats["failed"]`에 채운다.
    """
    doc = _build_dxf_doc(scene, stats)
    # [점검 1단계 2026-10-03] 임시 파일에 다 쓴 뒤 바꿔치기(safe_write.py) — 쓰는 도중
    # 실패해도 기존 .dxf가 반쯤 쓰인 채 깨지지 않는다.
    write_via_temp(path, doc.saveas)
    return True


def export_dwg(scene, path: str, stats: dict | None = None) -> bool:
    """[§8 DWG 자동변환 후속, 2026-08-14] scene을 DWG로 저장. 성공 시 True.

    가져오기(`dxf_import._load_ezdxf_doc`)와 대칭 — `ezdxf.addons.odafc`가 이미 내장한
    `export_dwg()`를 재사용한다(내부적으로 임시 DXF를 거쳐 ODA File Converter로 변환, 새
    의존성 없음). 미설치 시 `odafc.ODAFCNotInstalledError` — 호출부(`host_fileio`)가
    가져오기와 같은 안내+경로지정 UI로 처리한다. `replace=True`는 저장 다이얼로그가 이미
    OS 네이티브 "덮어쓸까요?" 확인을 거친 뒤라(기존 `export_dxf`의 `doc.saveas()`도 조용히
    덮어쓰는 것과 동일한 기대) 여기서 또 막을 이유가 없어서다.
    """
    from ezdxf.addons import odafc
    doc = _build_dxf_doc(scene, stats)
    # [점검 1단계 2026-10-03] `odafc.export_dwg(replace=True)`는 변환을 시작하기 **전에**
    # 기존 대상 파일부터 지운다(ezdxf 소스로 확인) — ODA 미설치·변환 실패면 원본 .dwg가
    # 사라진 채 끝났다. 대상과 같은 폴더의 임시 폴더로 먼저 변환하고, 결과 파일이 실제로
    # 생겼을 때만 대상으로 바꿔치기한다(같은 볼륨이라 os.replace가 원자적).
    path = os.path.abspath(path)
    tmp_dir = tempfile.mkdtemp(prefix=".ecad_dwg_", dir=os.path.dirname(path))
    try:
        tmp_out = os.path.join(tmp_dir, os.path.basename(path))
        odafc.export_dwg(doc, tmp_out, replace=True)
        if not os.path.isfile(tmp_out):
            raise RuntimeError("DWG 변환 결과 파일이 만들어지지 않았습니다.")
        os.replace(tmp_out, path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return True
