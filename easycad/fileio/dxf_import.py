"""DXF 가져오기 (Phase 3 후반 — .dxf → scene 아이템).

dxf_export.py의 역매핑. **우리가 export한 DXF의 왕복(round-trip)이 1차 목표**이며,
export가 레이어 이름(EC_RECT·EC_ARROW…)에 실어 둔 타입 힌트로 아이템 종류를 결정한다.
임의 외부 DXF는 dxftype 기반 폴백(_generic_item)으로 손실 매핑한다.

좌표 — export의 (x, -y) Y-flip을 다시 뒤집어(involution) 화면 Y-down 좌표 복원.
       월드좌표로 바로 복원되므로 아이템은 항등 변환(또는 회전만) + 월드 기하로 재구성된다.
색   — true_color(RGB) 최우선, 없으면 ACI(AutoCAD Color Index, ByLayer/ByBlock은 레이어색으로
       해석) → QColor. ACI 7(흰색)은 화면에서도 흰색 그대로(우리 앱은 다크 캔버스라 AutoCAD의
       "화면=흰색" 관례와 자연스럽게 맞는다) — 인쇄 시 흰→검정 전환은 `pdf_export.py`가 렌더
       직전에 담당(2026-07-29, 실사용 피드백: "화면 흰색·종이 검정"이 사용자 확정 방향).

승인된 결정 (2026-07-20):
  - 화살촉 삼각형 LWPOLYLINE: 독립 도형으로 되살리지 않고 **무시하되, tip 위치로
    화살표 head 방향(_head_at_end)만 복원**(무시+방향복원).
  - 심볼 kind: export가 외곽선 폴리라인으로 평탄화해 소실 → **외곽선(_PathItem)으로만 복원**.
  - 지속연결 바인딩·자식 라벨: DXF에 개념 없음 → 왕복에서 소실(라벨은 독립 텍스트로 복원).

INSERT/BLOCK 흡수 (2026-07-29 — 외부 무료 DXF 심볼/블록 라이브러리 활용용):
  - 우리 export는 INSERT를 만들지 않으므로(모든 아이템을 개별 엔티티로 평탄화 export) 이건
    순수히 **외부 DXF 폴백** 경로다. ezdxf의 `Insert.virtual_entities()`가 이미 배치 변환
    (위치·스케일·회전, 중첩 INSERT 포함)을 다 해 주므로(규칙 2 손안의 카드 — 우리가 행렬을
    직접 굴릴 필요 없음), 그 결과를 일반 엔티티처럼 기존 폴백 경로에 그대로 흘려보낸다.
  - 한 INSERT에서 나온 아이템 2개 이상이면 `_group_id`로 묶어 하나처럼 선택·이동되게 한다
    (`Ctrl+G` 그룹과 동일 메커니즘 재사용). 단, EC_* 레이어로 분류돼 지연 처리되는 화살표/배지/
    펜 경로 버킷(arrow_shafts 등)까지는 그룹 태깅이 안 미친다 — 외부 블록이 그 레이어명을 쓸
    가능성은 사실상 0이라 실사용 영향 없음(알려진 한계).
  - MINSERT(배열형 다중삽입)·XCLIP 클리핑은 `virtual_entities()` 자체가 처리 안 함(ezdxf 문서화된
    한계) → 첫 인스턴스만 반영. 변환 불가 엔티티는 조용히 skip(기존 손실 허용 정책과 일관).

외부 도면 자동 재스케일 (2026-07-29 — 실제 AutoCAD 도면 가져오기 실사용 피드백):
  - 실사용 파일(전주국 결선도, INSUNITS=mm)로 실측하니 도면 전체가 88×36단위밖에 안 됐다.
    우리 앱의 도형 기본 크기(네모 150×90 등)·핸들/선택박스 여백(8~12단위 고정값)·기본 펜 두께
    (1.0)는 전부 "도면 전체가 수백~수천 단위"라는 암묵적 전제로 캘리브레이션돼 있어, 그보다 훨씬
    작은 외부 도면을 그대로 가져오면 100% 줌에서 우표만큼 작게 보이고(어쩔 수 없이 크게 확대하면)
    이번엔 원래 고정폭이던 선 두께·핸들·선택박스가 도면 크기 대비 상대적으로 거대해 보인다.
  - 손안의 카드: PDF 출력(`pdf_export.py`)이 애초에 절대단위 가정 없이 항상 "용지에 비율 맞춤"
    방식이라(itemsBoundingRect → 용지 fit), 가져오기 시점에 좌표를 재스케일해도 인쇄 결과에
    영향이 없다 — 확인함. 그래서 **순수 외부 DXF(우리 EC_* 레이어가 하나도 없는 파일)에 한해**
    전체 도면 bbox를 재서 우리 앱 기준 크기(`_TARGET_EXTENT`)로 균일 확대/축소한다. 우리 자신이
    export한 파일(EC_* 레이어 존재)은 왕복 정밀도가 XDATA 두께 등에 의존하므로 **절대 건드리지
    않는다**(스케일 1.0 유지) — 기존 라운드트립 스모크 무영향.
  - 구현: 모듈 레벨 `_IMPORT_SCALE`(기본 1.0)을 `import_dxf()` 시작에서 계산해 세팅하고 끝에서
    되돌린다(단일 스레드 GUI 흐름 전제, 재진입 없음). `_uf()`가 이 값을 곱해 모든 좌표·벡터에
    일괄 적용되고, 원의 반지름·텍스트 높이처럼 `_uf()`를 안 타는 스칼라값만 별도로 곱한다.
    펜 두께는 그대로 둔다 — 외부 폴백 기본 두께(1.0/2.0)가 이미 우리 앱 스케일 기준값이라,
    지오메트리만 커지면 자동으로 비율이 맞아진다(별도 스케일 불필요).
"""
import math
import uuid

from PyQt6.QtCore import Qt, QRectF, QLineF, QPointF
from PyQt6.QtGui import QColor, QPen, QBrush, QPainterPath, QFontMetricsF

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

# [2026-07-29] 순수 외부 DXF 재스케일 목표 크기(씬 단위) — 우리 앱 네이티브 도형 스케일(기본
# 네모 150×90 등)과 같은 자릿수를 노려 handle/선택박스/기본펜폭 고정값들이 자동으로 비율이 맞게.
_TARGET_EXTENT = 1000.0
_IMPORT_SCALE = 1.0   # import_dxf() 실행 중에만 세팅되는 모듈 상태(단일 진입점, 재진입 없음)


# ---- 좌표·색·공통 ----------------------------------------------------------
def _uf(x: float, y: float):
    """DXF (x,y) → 화면좌표: Y-flip 되돌림(export _w의 역, involution) + 외부 도면 재스케일."""
    return (x * _IMPORT_SCALE, -y * _IMPORT_SCALE)


def _resolve_aci(e):
    """[2026-07-29] 실사용 DXF에서 발견 — 대부분의 외부 도면은 true_color가 아니라
    ACI(AutoCAD Color Index)나 ByLayer로 색을 지정한다(이 프로젝트 테스트 파일도 전부
    ByLayer). 그동안 true_color 없으면 무조건 검정 처리해, 레이어별로 다른 ACI 색(예:
    청록색 DATA 레이어)이 전부 검정으로 뭉개졌다. ByLayer(256)면 엔티티가 속한 레이어의
    색을, ByBlock(0)이면 근사로 레이어색을 따른다(부모 INSERT 색 추적은 안 함)."""
    try:
        c = e.dxf.color
    except Exception:  # noqa: BLE001
        return 7
    if c in (0, 256):                             # ByBlock/ByLayer → 레이어 색으로 해석
        try:
            return e.doc.layers.get(e.dxf.layer).dxf.color if e.doc else 7
        except Exception:  # noqa: BLE001 — 레이어 미존재 등
            return 7
    return c


def _color(e) -> QColor:
    """[2026-07-29 개정] ACI 7(흰색)을 화면에서도 흰색 그대로 반환 — 우리 앱은 다크 캔버스라
    AutoCAD 관례(화면=희게)와 자연스럽게 맞는다. 인쇄(PDF는 항상 흰 종이) 시에만 흰→검정
    전환이 필요한데, 그건 렌더링 시점의 관심사라 여기서 미리 결정하지 않고 `pdf_export.py`가
    렌더 직전 흰색 계열 잉크색만 일괄 치환한다(사용자 확인: '화면 흰색·종이 검정'이 맞다)."""
    rgb = getattr(e, "rgb", None)     # ezdxf: true_color(24비트) 있으면 최우선
    if rgb:
        return QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
    aci = _resolve_aci(e)
    if aci is None:
        return QColor("black")
    from ezdxf.colors import aci2rgb
    r, g, b = aci2rgb(aci)
    return QColor(r, g, b)


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


# [M2 #3] DXF linetype → Qt 선스타일 역매핑(export _QT_TO_LTYPE의 역). 나머지는 solid.
_LTYPE_TO_QT = {
    "DASHED": Qt.PenStyle.DashLine,
    "DOT": Qt.PenStyle.DotLine,
    "DASHDOT": Qt.PenStyle.DashDotLine,
    "DIVIDE": Qt.PenStyle.DashDotDotLine,
}


def _style_of(e):
    """엔티티의 linetype → Qt 선스타일. 표준/미지정이면 None(=기본 solid 유지)."""
    try:
        lt = e.dxf.linetype
    except Exception:  # noqa: BLE001
        return None
    return _LTYPE_TO_QT.get(str(lt).upper()) if lt else None


def _pen(e, width: float = None) -> QPen:
    if width is None:
        width = _width_of(e)
    p = QPen(_color(e))
    p.setWidthF(width)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    st = _style_of(e)               # [M2 #3] linetype → 선스타일(네모·선·원·심볼·펜 공통)
    if st is not None:
        p.setStyle(st)
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
    r = e.dxf.radius * _IMPORT_SCALE     # 스칼라라 _uf()를 안 타므로 별도로 재스케일
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
    st = _style_of(e)               # [M2 #3] 몸통 선스타일 복원
    if st is not None:
        it._style = st
    return _flag(it)


def _arrow_from_line(e, head_at_end: bool):
    s = _uf(e.dxf.start.x, e.dxf.start.y)
    t = _uf(e.dxf.end.x, e.dxf.end.y)
    it = _ArrowItem(_color(e), _width_of(e, 2.0), head_at_end)
    it.set_points(QPointF(*s), QPointF(*t))
    st = _style_of(e)               # [M2 #3] 몸통 선스타일 복원
    if st is not None:
        it._style = st
    return _flag(it)


def _sarrow_item(pts, e, head_at_end: bool):
    it = _PolyArrowItem(_color(e), _width_of(e, 2.0), head_at_end)
    it._pts = [QPointF(x, y) for x, y in pts]
    st = _style_of(e)               # [M2 #3] 몸통 선스타일 복원
    if st is not None:
        it._style = st
    return _flag(it)


# MTEXT attachment_point(1~9) → (수평비율, 수직비율). 1=TL 2=TC 3=TR 4=ML 5=MC 6=MR 7=BL 8=BC 9=BR.
_MTEXT_ATTACH_FRAC = {
    1: (0.0, 0.0), 2: (0.5, 0.0), 3: (1.0, 0.0),
    4: (0.0, 0.5), 5: (0.5, 0.5), 6: (1.0, 0.5),
    7: (0.0, 1.0), 8: (0.5, 1.0), 9: (1.0, 1.0),
}
# TEXT halign(0~5) → 수평비율. 3(aligned)·5(fit)는 두 점 사이 맞춤이라 중앙으로 근사.
_TEXT_HALIGN_FRAC = {0: 0.0, 1: 0.5, 2: 1.0, 3: 0.5, 4: 0.5, 5: 0.5}
# TEXT valign(0~3) → 수직비율. 0(baseline)은 별도 처리(폰트 ascent 필요)라 여기 없음.
_TEXT_VALIGN_FRAC = {1: 1.0, 2: 0.5, 3: 0.0}


def _text_item(e):
    """[2026-07-29] 실사용 DXF에서 발견 — halign/valign이 기본(0,0)이 아니면 DXF 스펙상
    앵커가 insert가 아니라 align_point이고(둘이 다른 값이었음, 실측 확인), 우리 _TextItem은
    pos()가 항상 '문서 좌상단'이라 원본 정렬(가운데·중앙 등)을 무시하고 좌상단으로 꽂아
    전체적으로 아래로 치우쳐 보였다. halign/valign(MTEXT는 attachment_point)에 따라 실제
    렌더된 bounding rect 비율만큼 오프셋을 계산해 정확한 앵커점에 맞춘다. 회전 대비:
    setTransformOriginPoint를 같은 오프셋으로 잡아 회전축도 원래 앵커점에 고정한다
    (world 앵커 위치 = pos() + originPoint, 회전각과 무관 — Qt 변환 성질)."""
    rot = e.dxf.rotation if e.dxf.hasattr("rotation") else 0.0
    if e.dxftype() == "MTEXT":
        txt = e.plain_text()
        h = e.dxf.char_height
        ins = e.dxf.insert
        hf, vf = _MTEXT_ATTACH_FRAC.get(e.dxf.get("attachment_point", 1), (0.0, 0.0))
        baseline = False
    else:                                        # TEXT
        txt = e.dxf.text
        h = e.dxf.height
        halign, valign = e.dxf.halign, e.dxf.valign
        # halign/valign이 (0,0)이 아니면 DXF 스펙상 정렬점은 align_point.
        ins = e.dxf.align_point if (halign != 0 or valign != 0) else e.dxf.insert
        hf = _TEXT_HALIGN_FRAC.get(halign, 0.0)
        baseline = valign == 0
        vf = _TEXT_VALIGN_FRAC.get(valign, 0.0)   # baseline이면 아래서 별도 계산해 안 쓰임

    anchor = _uf(ins.x, ins.y)
    it = _TextItem(_color(e))
    it.apply_font_size(max(round(h * _IMPORT_SCALE), 1))   # 스칼라라 별도 재스케일
    it.setPlainText(txt)
    br = it.boundingRect()
    dx = br.width() * hf
    dy = QFontMetricsF(it.font()).ascent() if baseline else br.height() * vf
    it.setPos(QPointF(anchor[0] - dx, anchor[1] - dy))
    it.setTransformOriginPoint(QPointF(dx, dy))
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


def _solid_item(e):
    """[2026-07-29] SOLID(채워진 삼각/사각형) — 화살촉 등에 흔히 쓰이는데 그동안 지원이
    없어 조용히 누락되고 있었다(실사용 DXF에서 발견). DXF 정점 순서는 1-2-4-3(vtx0,vtx1,
    vtx3,vtx2)이 실제 그리기 순서 — 순차(0,1,2,3)로 그리면 사각형이 나비형으로 꼬인다.
    삼각형은 vtx2==vtx3로 중복 지정되므로 순서 무관, 중복점은 제거한다."""
    order = (e.dxf.vtx0, e.dxf.vtx1, e.dxf.vtx3, e.dxf.vtx2)
    pts = [_uf(v.x, v.y) for v in order]
    dedup = []
    for p in pts:
        if not dedup or _dist2(dedup[-1], p) > 1e-9:
            dedup.append(p)
    if len(dedup) >= 2 and _dist2(dedup[0], dedup[-1]) < 1e-9:
        dedup.pop()
    if len(dedup) < 3:
        return None
    path = QPainterPath(QPointF(*dedup[0]))
    for p in dedup[1:]:
        path.lineTo(p[0], p[1])
    path.closeSubpath()
    it = _PathItem(path)
    color = _color(e)
    it.setPen(QPen(color, 0))
    it.setBrush(QBrush(color))
    return _flag(it)


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
    if dxft == "SOLID":
        return _solid_item(e)
    return None


def _extend_bbox_raw(e, xs: list, ys: list):
    """엔티티의 (아직 재스케일 전) 원본 DXF 좌표로 bbox 후보점을 xs/ys에 추가.
    정밀할 필요 없음 — 재스케일 비율을 정하기 위한 근사치 목적."""
    dxft = e.dxftype()
    try:
        if dxft == "LINE":
            xs += [e.dxf.start.x, e.dxf.end.x]; ys += [e.dxf.start.y, e.dxf.end.y]
        elif dxft == "LWPOLYLINE":
            for p in e.get_points():
                xs.append(p[0]); ys.append(p[1])
        elif dxft == "CIRCLE":
            c, r = e.dxf.center, e.dxf.radius
            xs += [c.x - r, c.x + r]; ys += [c.y - r, c.y + r]
        elif dxft == "ELLIPSE":
            c = e.dxf.center
            a = math.hypot(e.dxf.major_axis.x, e.dxf.major_axis.y)
            xs += [c.x - a, c.x + a]; ys += [c.y - a, c.y + a]
        elif dxft in ("SPLINE",):
            for p in e.control_points:
                xs.append(p[0]); ys.append(p[1])
        elif dxft == "ARC":
            c, r = e.dxf.center, e.dxf.radius
            xs += [c.x - r, c.x + r]; ys += [c.y - r, c.y + r]
        elif dxft in ("TEXT", "MTEXT"):
            # [실사용 파일에서 발견] 삽입점만 쓰고 텍스트 실제 렌더 폭은 bbox에 안 넣는다 —
            # 의도적. 긴 주석 텍스트(예: 60자 URL)의 폭은 폰트 렌더링에 의존해 미리 정확히
            # 추정하기 어렵고, 도면 자체보다 우발적으로 훨씬 넓은 텍스트가 스케일 기준을
            # 왜곡하면(실측: 도형만의 bbox 916×385인데 텍스트까지 넣으면 2172×690으로 폭증)
            # 정작 핵심 도형이 다시 작아진다 — 스케일은 지오메트리 위주로 정하고, 그보다
            # 넓은 텍스트는 자연스러운 폰트 크기로 그리게 둔다(부작용 감수).
            ins = e.dxf.insert
            xs.append(ins.x); ys.append(ins.y)
        elif dxft == "SOLID":
            for i in range(4):
                v = getattr(e.dxf, f"vtx{i}")
                xs.append(v.x); ys.append(v.y)
    except Exception:  # noqa: BLE001 — bbox 추정 실패는 이 엔티티만 건너뜀(근사치 목적)
        pass


def _compute_import_scale(msp) -> float:
    """[2026-07-29] 순수 외부 DXF(우리 EC_* 레이어가 하나도 없는 파일)만 전체 bbox를 재서
    우리 앱 기준 크기(_TARGET_EXTENT)로 재스케일할 배율을 계산. 우리 자신이 export한 파일은
    왕복 정밀도 보존을 위해 항상 1.0(원문 그대로)을 반환한다."""
    xs, ys = [], []
    for e in msp:
        if e.dxf.layer in _LAYER_TYPE:
            return 1.0                          # 우리 export 흔적 발견 — 재스케일 skip
        if e.dxftype() == "INSERT":
            for child in _expand_insert(e):
                if child.dxf.layer in _LAYER_TYPE:
                    return 1.0
                _extend_bbox_raw(child, xs, ys)
        else:
            _extend_bbox_raw(e, xs, ys)
    if not xs or not ys:
        return 1.0
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    extent = max(w, h)
    if extent < 1e-9:
        return 1.0
    scale = _TARGET_EXTENT / extent
    return min(max(scale, 1e-3), 1e3)           # 극단값 방지 세이프가드


def _expand_insert(e, depth: int = 0, max_depth: int = 6):
    """INSERT를 재귀적으로 평탄화 — virtual_entities()가 이미 배치 변환(위치·스케일·회전)을
    적용한 자식 엔티티를 내주므로, 우리는 그걸 일반 엔티티처럼 취급하면 된다. 자식이 또
    INSERT(중첩 블록)면 depth 제한까지 재귀 전개. 순환·과도한 중첩 방어용 max_depth."""
    if depth >= max_depth:
        return
    try:
        children = list(e.virtual_entities())
    except Exception:  # noqa: BLE001 — 변환 실패한 블록은 조용히 skip(손실 허용)
        return
    for child in children:
        if child.dxftype() == "INSERT":
            yield from _expand_insert(child, depth + 1, max_depth)
        else:
            yield child


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

    global _IMPORT_SCALE
    _IMPORT_SCALE = _compute_import_scale(msp)
    try:
        return _ingest_modelspace(scene, msp)
    finally:
        _IMPORT_SCALE = 1.0    # 다음 호출에 새지 않도록 항상 원복(재진입 없는 단일 흐름 전제)


def _ingest_modelspace(scene, msp) -> int:
    """import_dxf 본체 — _IMPORT_SCALE이 이미 세팅된 뒤 호출된다(분리 이유: try/finally로
    감싸되 본문 들여쓰기를 그대로 유지하기 위해)."""
    arrow_shafts = []          # SPLINE/LINE on EC_ARROW
    arrow_head_tips = []       # 화살촉 tip
    sarrow_shafts = []         # (pts, entity)
    sarrow_head_tips = []
    badge_circles = []
    badge_texts = []
    path_segments = []
    built = []                 # 즉시 완성된 아이템

    def _ingest(e):
        """단일 엔티티(top-level 또는 INSERT에서 평탄화된 자식) 분류·변환. built 등
        바깥 스코프 누산 리스트에 closure로 append(INSERT 확장 시에도 재사용하기 위해 분리)."""
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

    for e in msp:
        if e.dxftype() == "INSERT":
            # [2026-07-29] 블록 참조 — virtual_entities()가 배치 변환을 이미 적용한
            # 자식들을 일반 엔티티처럼 흘려보내고, 2개 이상 나오면 한 블록으로 그룹 태깅.
            before = len(built)
            for child in _expand_insert(e):
                _ingest(child)
            new_items = built[before:]
            if len(new_items) >= 2:
                gid = uuid.uuid4().hex[:8]
                for it in new_items:
                    it._group_id = gid
        else:
            _ingest(e)

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
