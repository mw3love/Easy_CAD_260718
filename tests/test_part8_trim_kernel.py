"""§8 항목17(범용 CAD TRIM/EXTEND) 1~2단계.

1단계 — 기하 커널 순수함수(선분-선분/원/타원 교차점). 좌표계 무관 순수함수라 Qt 아이템 없이
QPointF/QRectF만으로 검증한다 — 렌더(간격이 실제로 화면·PDF에 보이는지)는 이 파일이 아니라
실조건 검증(세션 기록 참조,
`tests/test_part4_ports_fileio.py::test_true_segmented_border_survives_scene_render_and_grab`가
오프스크린 회귀 몫)이 맡는다.

2단계(2026-08-10) — cut 구간 모델(`_add_border_cut`/`build_trimmed_border_path` 일반형) +
실제 프로덕션 paint() 렌더 통합. 1단계 렌더 게이트는 테스트 안 임시 monkeypatch(segmented_paint)
로만 확인했지만, 여기서부터는 진짜 `_RectItem`/`_EllipseItem`/`_SymbolItem.paint()`가
`_cuts`가 있을 때 실제로 갈아타는 코드 경로(`_paint_filled_trimmed_border`)를 검증한다.

3단계(2026-08-10) — 히트·스냅(`_border_pt_in_gap`/`_shape_ports_visible`)이 cut 구간을
호버·스냅에서 인식하는지 검증(연속 폴백 + 이산 4점 둘 다).

4단계(2026-08-10) — TRIM 도구 UI(문지르기). 순수 기하 계산(`_trim_candidate_segment`)과
`_AnnotatorView`를 실제로 띄운 press/move/release 종단 시나리오를 함께 검증한다.

5단계(2026-08-10) — 열린 도형(_LineItem/_PolyArrowItem) 분절 + EXTEND. 순수 기하 계산
(`_trim_candidate_open_segment`/`_extend_candidate`), 커밋 함수(`apply_open_item_trim`/
`apply_extend`)의 아이템 변형(분리·바인딩·라벨), `_AnnotatorView` 종단 시나리오(Shift=EXTEND
전환 포함)를 함께 검증한다.

6단계(2026-08-10) — 직렬화(.ecad)·DXF·undo. `host._cuts`의 `.ecad` JSON 왕복, DXF 내보내기
게이트가 포트뿐 아니라 cut만 있어도 진짜 분절로 나가는지(+ 이전엔 분기 자체가 없던
`_export_ellipse`도 함께), TRIM(닫힌/열린 도형)·EXTEND 전부 Ctrl+Z/Y로 되돌리기/다시실행
되는지(문지르기 드래그 전체가 undo 1스텝으로 뭉치는지 포함)를 검증한다.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part8_trim_kernel.py.
"""
import json

from _shared import *  # noqa: F401,F403
from PyQt6.QtWidgets import QGraphicsScene


def test_seg_seg_intersection_crossing_point():
    p = _seg_seg_intersection(QPointF(0, 0), QPointF(2, 0), QPointF(1, -1), QPointF(1, 1))
    assert p is not None
    assert _close(p, QPointF(1, 0))


def test_seg_seg_intersection_parallel_is_none():
    assert _seg_seg_intersection(QPointF(0, 0), QPointF(2, 0),
                                  QPointF(0, 1), QPointF(2, 1)) is None


def test_seg_seg_intersection_non_overlapping_is_none():
    # 두 선분을 연장하면 만나지만, 선분 구간 자체는 서로 안 닿는다.
    assert _seg_seg_intersection(QPointF(0, 0), QPointF(1, 0),
                                  QPointF(5, -1), QPointF(5, 1)) is None


def test_seg_seg_intersection_endpoint_touch_counts():
    # _seg_cross_seg(불린, 라우팅용)와 달리 이쪽은 끝점 접촉도 유효 교차점으로 인정한다
    # (TRIM 문지르기·EXTEND가 "정확히 끝점에서 만남"을 절단/연장 지점으로 다뤄야 하므로).
    p = _seg_seg_intersection(QPointF(0, 0), QPointF(2, 0), QPointF(2, 0), QPointF(2, 5))
    assert p is not None
    assert _close(p, QPointF(2, 0))


def test_seg_circle_intersections_two_points():
    # 원점 반지름 5 원을 수평선 y=0이 지나감 → x=-5, x=5.
    pts = _seg_circle_intersections(QPointF(-10, 0), QPointF(10, 0), QPointF(0, 0), 5.0)
    assert len(pts) == 2
    xs = sorted(p.x() for p in pts)
    assert abs(xs[0] - (-5.0)) < 1e-6 and abs(xs[1] - 5.0) < 1e-6
    for p in pts:
        assert abs(p.y()) < 1e-6


def test_seg_circle_intersections_segment_stops_short_of_circle():
    # 선분이 원 안까지 도달하지 못하면(끝점이 원 밖 & 원과 안 만남) 0개.
    pts = _seg_circle_intersections(QPointF(-10, 0), QPointF(-6, 0), QPointF(0, 0), 5.0)
    assert pts == []


def test_seg_circle_intersections_tangent_dedupes_to_one():
    # y=5 수평선은 원점 반지름 5 원에 접선(tangent) — 교차점은 (0,5) 하나뿐이어야 한다.
    pts = _seg_circle_intersections(QPointF(-10, 5), QPointF(10, 5), QPointF(0, 0), 5.0)
    assert len(pts) == 1
    assert _close(pts[0], QPointF(0, 5))


def test_seg_circle_intersections_one_endpoint_inside():
    # 한쪽 끝점이 원 내부면 교차점은 1개(선분이 원을 뚫고 나가는 지점).
    pts = _seg_circle_intersections(QPointF(0, 0), QPointF(10, 0), QPointF(0, 0), 5.0)
    assert len(pts) == 1
    assert _close(pts[0], QPointF(5, 0))


def test_seg_ellipse_intersections_matches_axis_extents():
    # rect(-10,-5)-(10,5) → 중심(0,0), rx=10, ry=5. 수평선 y=0은 x=-10,10에서 만나야 한다.
    rect = QRectF(-10, -5, 20, 10)
    pts = _seg_ellipse_intersections(QPointF(-20, 0), QPointF(20, 0), rect)
    assert len(pts) == 2
    xs = sorted(p.x() for p in pts)
    assert abs(xs[0] - (-10.0)) < 1e-6 and abs(xs[1] - 10.0) < 1e-6


def test_seg_ellipse_intersections_vertical_matches_minor_axis():
    rect = QRectF(-10, -5, 20, 10)
    pts = _seg_ellipse_intersections(QPointF(0, -20), QPointF(0, 20), rect)
    assert len(pts) == 2
    ys = sorted(p.y() for p in pts)
    assert abs(ys[0] - (-5.0)) < 1e-6 and abs(ys[1] - 5.0) < 1e-6


def test_seg_ellipse_intersections_offset_center():
    # 중심이 원점이 아닌 타원도 그대로 맞아야 한다(호출부가 host 로컬좌표를 그대로 넘기는
    # 실사용 패턴 — _EllipseItem.rect()는 보통 (0,0) 시작이 아님).
    rect = QRectF(100, 200, 40, 20)   # 중심 (120, 210), rx=20, ry=10
    pts = _seg_ellipse_intersections(QPointF(80, 210), QPointF(160, 210), rect)
    assert len(pts) == 2
    xs = sorted(p.x() for p in pts)
    assert abs(xs[0] - 100.0) < 1e-6 and abs(xs[1] - 140.0) < 1e-6


def test_seg_ellipse_intersections_miss_is_empty():
    rect = QRectF(-10, -5, 20, 10)
    pts = _seg_ellipse_intersections(QPointF(-20, 20), QPointF(20, 20), rect)
    assert pts == []


def test_seg_seg_intersection_rotated_host_local_frame_roundtrip():
    # [2026-08-10 deep-interview 확정] 회전된 도형은 커널 함수를 씬좌표가 아니라 host의
    # 로컬좌표계로 옮겨서 호출한다(host.mapFromScene) — Qt가 회전을 이미 반영해주므로
    # 커널 함수 자체는 회전을 전혀 몰라도 된다는 것을 실제 QGraphicsItem으로 확인한다.
    w = CanvasWindow()
    host = _mk_pen_rect(w, x=0, y=0, ww=100, hh=60)
    host.setRotation(30)
    host.setTransformOriginPoint(host.rect().center())
    # 씬좌표의 수직선 하나가 회전된 사각형의 위쪽 변을 자르도록 배치.
    scene_top = host.mapToScene(QPointF(50, 0))
    cutter_a = QPointF(scene_top.x(), scene_top.y() - 50)
    cutter_b = QPointF(scene_top.x(), scene_top.y() + 50)
    # 커널 호출 전 host 로컬좌표로 변환.
    local_a = host.mapFromScene(cutter_a)
    local_b = host.mapFromScene(cutter_b)
    poly = _host_outline_local_polygon(host)
    hit = None
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        p = _seg_seg_intersection(a, b, local_a, local_b)
        if p is not None:
            hit = p
            break
    assert hit is not None, "회전된 호스트 로컬좌표에서 교차점을 못 찾음"
    # 로컬 교차점을 다시 씬으로 되돌리면 원래 커터 위치(사각형 위쪽 변 중점)와 일치해야 한다.
    assert _close(host.mapToScene(hit), scene_top, eps=1.0)


# ---- 2단계: cut 구간 모델 -----------------------------------------------------------------

def test_host_outline_local_polygon_ellipse_flattens_to_ring_on_boundary():
    # [2026-08-10 선택창 확정] 타원 cut도 폴리곤 근사로 통일 — 이전엔 _EllipseItem이
    # 사각형 네 꼭짓점으로 잘못 취급됐다(원형 포트 trim이 애초에 부정확했던 원인).
    rect = QRectF(0, 0, 200, 120)
    host = _EllipseItem(QRectF(rect))
    poly = _host_outline_local_polygon(host)
    assert len(poly) >= 16, "타원 근사가 사각형 4점 폴백으로 되돌아감"
    cx, cy = rect.center().x(), rect.center().y()
    rx, ry = rect.width() / 2.0, rect.height() / 2.0
    for p in poly:
        val = ((p.x() - cx) / rx) ** 2 + ((p.y() - cy) / ry) ** 2
        assert abs(val - 1.0) < 1e-3, f"정점이 타원 위에 있지 않음: {p}"


def test_build_trimmed_border_path_uses_cuts_without_ports():
    # cut 구간은 포트와 완전히 독립 경로 — 포트가 하나도 없는 호스트도 gap이 생겨야 한다.
    rect = QRectF(0, 0, 200, 120)
    ET = QPainterPath.ElementType

    def move_count(path):
        return sum(1 for i in range(path.elementCount())
                   if path.elementAt(i).type == ET.MoveToElement)

    baseline = build_trimmed_border_path(_RectItem(QRectF(rect)))
    assert move_count(baseline) == 4   # 변 4개 = 끊김 없는 subpath 4개

    host = _RectItem(QRectF(rect))
    _add_border_cut(host, 0, 0.25, 0.75)
    cut_path = build_trimmed_border_path(host)
    assert move_count(cut_path) == 5, "포트 없이 cut만 있어도 끊겨야 함(gap 하나 = subpath +1)"


def test_add_border_cut_appends_multiple_and_updates():
    host = _RectItem(QRectF(0, 0, 100, 60))
    assert getattr(host, "_cuts", None) is None
    _add_border_cut(host, 2, 0.1, 0.4)
    _add_border_cut(host, 0, 0.0, 0.2)
    assert host._cuts == [(2, 0.1, 0.4), (0, 0.0, 0.2)]


def test_cut_follows_resize_by_edge_ratio():
    # [계획서 §8 항목17 2단계 검증 항목] "리사이즈 후 자국 추종" — cut을 (변 인덱스, 비율)로
    # 저장한 이유 자체가 이것: 호스트를 리사이즈해도 잘린 자리가 같은 상대위치를 유지해야 한다.
    ET = QPainterPath.ElementType

    def gap_end_x(path):
        moves = [path.elementAt(i).x for i in range(path.elementCount())
                 if path.elementAt(i).type == ET.MoveToElement]
        # moves[0] = edge0 첫 subpath 시작(TL, x=0, 코너 고정값이라 cut과 무관).
        # moves[1] = edge0 두 번째 subpath 시작 = gap 끝(t1) x — cut 비율이 반영되는 지점.
        return moves[1]

    host = _RectItem(QRectF(0, 0, 200, 100))
    _add_border_cut(host, 0, 0.25, 0.75)
    assert abs(gap_end_x(build_trimmed_border_path(host)) - 150.0) < 1e-6   # 0.75 * 200

    host.prepareGeometryChange()
    host.setRect(QRectF(0, 0, 400, 100))   # 폭 2배 리사이즈
    assert abs(gap_end_x(build_trimmed_border_path(host)) - 300.0) < 1e-6, \
        "리사이즈 후 cut 비율이 안 따라옴"   # 0.75 * 400


def test_real_paint_renders_cut_gap_for_rect_ellipse_symbol():
    """[§8 항목17 2단계 렌더 통합] 1단계는 테스트 안 임시 monkeypatch로 렌더 게이트만 확인
    했다 — 여기서는 진짜 프로덕션 코드(`_cuts`가 있을 때 paint()가 갈아타는
    `_paint_filled_trimmed_border`)가 scene.render()에서 실제로 간격을 남기는지 확인한다.
    gap 좌표는 `_host_outline_local_polygon`으로 직접 구해(하드코딩 안 함) 타원 근사 시작점
    같은 구현 세부에 안 흔들리게 한다."""
    from PyQt6.QtGui import QImage, QPainter, QPen
    from PyQt6.QtWidgets import QGraphicsScene

    def darkest(img, px, py):
        d = 255
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                c = QColor(img.pixel(px + dx, py + dy))
                d = min(d, (c.red() + c.green() + c.blue()) // 3)
        return d

    def check(item, cuts, sample_edge):
        # cuts: [(edge_index, t0, t1), ...] 전부 적용. 샘플 픽셀은 sample_edge 변의 중점 —
        # 타원은 폴리곤 근사라 변 하나가 몇 도(°)짜리 아주 짧은 호라(len(poly) 실측 40+개),
        # 변 하나만 잘라선 픽셀로 안 잡혀 여러 변을 연속으로 잘라 육안·픽셀 모두에 유효한
        # 크기의 호 하나를 만든다(사각·삼각형은 변 자체가 커서 하나로 충분).
        poly = _host_outline_local_polygon(item)
        a, b = poly[sample_edge], poly[(sample_edge + 1) % len(poly)]
        gap_pt = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)

        scene = QGraphicsScene()
        scene.setSceneRect(-20, -20, 240, 160)
        scene.setBackgroundBrush(QColor("white"))
        item.setPen(QPen(QColor("black"), 3))
        scene.addItem(item)
        for edge_i, t0, t1 in cuts:
            _add_border_cut(item, edge_i, t0, t1)

        img = QImage(240, 160, QImage.Format.Format_RGB32)
        img.fill(QColor("white"))
        p = QPainter(img)
        scene.render(p, QRectF(0, 0, 240, 160), QRectF(-20, -20, 240, 160))
        p.end()
        px, py = int(gap_pt.x() + 20), int(gap_pt.y() + 20)
        assert darkest(img, px, py) > 150, f"{type(item).__name__} cut 구간에 테두리가 남음"

    check(_RectItem(QRectF(0, 0, 200, 120)), [(0, 0.25, 0.75)], 0)
    check(_SymbolItem("triangle", QRectF(0, 0, 160, 120)), [(0, 0.25, 0.75)], 0)

    ellipse = _EllipseItem(QRectF(0, 0, 200, 120))
    n = len(_host_outline_local_polygon(ellipse))
    arc = max(4, n // 6)   # 약 60도 폭 호 — 픽셀 검사에 넉넉한 크기
    check(ellipse, [(i, 0.0, 1.0) for i in range(arc)], arc // 2)


def test_real_paint_renders_cut_gap_on_rotated_host():
    """[1단계 회전 결정의 연장, 2026-08-10] 기하 커널은 좌표계 무관 순수함수로 만들었지만,
    실제 화면 렌더는 Qt가 item의 rotation을 painter 변환으로 자동 반영해줘야 paint() 쪽에
    특례 코드 없이도 맞는다 — 그 가정을 위 렌더 테스트들(전부 무회전)이 비워둔 채였다.
    여기서 실제로 회전된 `_RectItem`을 그려 cut gap이 회전 후 올바른 씬 위치에 뜨는지 확인."""
    from PyQt6.QtGui import QImage, QPainter, QPen
    from PyQt6.QtWidgets import QGraphicsScene

    def darkest(img, px, py):
        d = 255
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                c = QColor(img.pixel(px + dx, py + dy))
                d = min(d, (c.red() + c.green() + c.blue()) // 3)
        return d

    item = _RectItem(QRectF(0, 0, 120, 80))
    item.setPen(QPen(QColor("black"), 3))
    item.setPos(-60, -40)
    item.setTransformOriginPoint(60, 40)
    item.setRotation(40)

    poly = _host_outline_local_polygon(item)
    a, b = poly[0], poly[1]   # 위쪽 변(로컬, cut을 걸 자리)
    local_mid = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0)
    scene_mid = item.mapToScene(local_mid)   # 회전 반영된 gap 중점의 씬좌표

    scene = QGraphicsScene()
    scene.setSceneRect(-150, -150, 300, 300)
    scene.setBackgroundBrush(QColor("white"))
    scene.addItem(item)
    _add_border_cut(item, 0, 0.25, 0.75)

    img = QImage(300, 300, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 300, 300), QRectF(-150, -150, 300, 300))
    p.end()
    px, py = int(scene_mid.x() + 150), int(scene_mid.y() + 150)
    assert darkest(img, px, py) > 150, "회전된 호스트에서 cut gap이 제 위치에 안 뜸"


def test_cut_trimmed_host_border_is_not_snappable_or_hoverable():
    # [§8 항목17 3단계, 2026-08-10] 포트 트림(2026-08-09,
    # tests/test_part4_ports_fileio.py::test_port_trimmed_host_border_is_not_snappable_or_hoverable)
    # 과 같은 원칙을 TRIM cut에도 적용 — "스냅되는 곳 == 선이 그려진 곳"을 이산 4점(N/E/S/W)·
    # 연속 폴백 양쪽에서 유지한다. 사각형 위쪽 변 정중앙은 정확히 discrete N 포인트와 같은
    # 자리라, 연속 폴백(_nearest_border_visible)만 고치고 이산 경로(_shape_ports_visible)를
    # 빼먹으면 이 케이스가 그대로 새는 함정이 있다 — 실제로 1차 구현에서 이 사실을 발견해
    # `_border_snap_at`/`_qc_snap_target`의 원래 `_shape_ports(sh)` 호출도 함께 고쳤다.
    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)   # 위쪽 변 정중앙(N) = (300, 0)
    w._scene.clearSelection()
    _add_border_cut(host, 0, 0.25, 0.75)   # 위쪽 변 x=150~450 — N(300,0) 포함
    gap_pt = host.mapToScene(QPointF(300, 0))

    # ⓐ 연속 폴백: cut 구간은 호스트 테두리로 안 잡힌다. 원본 _nearest_border는 그대로여야
    # 한다(포트 부착·드래그가 이걸 쓰기 때문).
    assert _nearest_border_visible(host, gap_pt) is None
    assert _close(_nearest_border(host, gap_pt)[0], gap_pt, eps=0.01)

    # ⓑ 이산 4점: N이 마침 cut 안에 있으므로 스냅 후보 목록에서 빠져야 한다(E/S/W는 그대로).
    visible_pts = [sp for sp, _n in _shape_ports_visible(host)]
    assert not any(_close(p, gap_pt, eps=0.01) for p in visible_pts), \
        "cut에 걸친 discrete N 포인트가 그대로 스냅 후보에 남음"
    assert len(visible_pts) == 3

    # ⓒ cut 안 된 정상 테두리는 계속 잡혀야 한다(과잉 차단 방지).
    normal_pt = QPointF(0, 100)
    hit = _nearest_border_visible(host, normal_pt)
    assert hit is not None and _close(hit[0], normal_pt, eps=0.01)

    # ⓓ 화살표 도구 실제 스냅(_border_snap_at, 이산+연속 둘 다 거침) — cut 구간에서 호스트에
    # 안 붙는다.
    w.set_tool("arrow")
    snap = w._view._border_snap_at(w._view.mapFromScene(gap_pt))
    assert snap is None or snap[2] is not host


def test_cut_border_gap_does_not_punch_through_fill():
    # [데이터모델 확정 사항] 닫힌 도형은 비파괴 — cut은 테두리 선만 끊고 채움은 그대로.
    from PyQt6.QtGui import QImage, QPainter, QPen
    from PyQt6.QtWidgets import QGraphicsScene

    scene = QGraphicsScene()
    scene.setSceneRect(-20, -20, 240, 160)
    scene.setBackgroundBrush(QColor("white"))
    item = _RectItem(QRectF(0, 0, 200, 120))
    item.setPen(QPen(QColor("black"), 3))
    item.setBrush(QBrush(QColor("#cfe8ff")))
    scene.addItem(item)
    _add_border_cut(item, 0, 0.25, 0.75)   # 위쪽 변 절반을 자름(테두리만)

    img = QImage(240, 160, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 240, 160), QRectF(-20, -20, 240, 160))
    p.end()
    c = QColor(img.pixel(120, 80))   # 도형 내부 중앙 부근 — 흰 배경이 아니라 채움색이어야 함
    assert (c.red(), c.green(), c.blue()) == (0xcf, 0xe8, 0xff), \
        "cut이 테두리를 넘어 채움까지 뚫음(비파괴 데이터모델 위반)"


# ---- 4단계: TRIM 도구(문지르기) — 기하 계산 -----------------------------------------------

def test_trim_candidate_segment_finds_gap_between_two_crossings():
    # 계획서 "포트 대체 워크플로": 네모(host) 위에 작은 네모(cutter)를 겹쳐 놓고 그 교차 구간을
    # 자른다. cutter가 host 위쪽 변(y=0, x 0~600)을 x=280~320에서 가로지른다.
    host = _RectItem(QRectF(0, 0, 600, 400))
    cutter = _RectItem(QRectF(280, -20, 40, 40))
    seg = _trim_candidate_segment(host, QPointF(300, 0), [cutter])
    assert seg is not None
    edge_i, t0, t1 = seg
    assert edge_i == 0
    assert abs(t0 - 280.0 / 600.0) < 1e-6
    assert abs(t1 - 320.0 / 600.0) < 1e-6


def test_trim_candidate_segment_none_without_cutter():
    # cutter가 하나도 걸치지 않으면 "자를 게 없음"(빈 구간 통짜 삭제는 스코프 밖).
    host = _RectItem(QRectF(0, 0, 600, 400))
    assert _trim_candidate_segment(host, QPointF(300, 0), []) is None


def test_trim_candidate_segment_clamps_to_edge_end_when_cutter_extends_past_corner():
    # cutter가 host 오른쪽 모서리 밖까지 뻗치면(교차점이 변 하나뿐) 그쪽 경계는 변의 끝(t=1)까지.
    host = _RectItem(QRectF(0, 0, 600, 400))
    cutter = _RectItem(QRectF(580, -20, 70, 40))   # x=580~650, host 밖으로 뻗침
    seg = _trim_candidate_segment(host, QPointF(595, 0), [cutter])
    assert seg is not None
    edge_i, t0, t1 = seg
    assert edge_i == 0
    assert abs(t0 - 580.0 / 600.0) < 1e-6
    assert abs(t1 - 1.0) < 1e-6


def test_trim_candidate_segment_handles_ellipse_cutter_via_polygon_approx():
    # [2단계 결정 재사용 확인] 원/타원 cutter도 특례 없이 폴리곤 근사로 처리된다 — 전용
    # 선분-원 커널(_seg_circle_intersections)을 안 써도 이 경로에서 동작해야 한다.
    host = _RectItem(QRectF(0, 0, 600, 400))
    cutter = _EllipseItem(QRectF(270, -30, 60, 60))   # 중심(300,0), 반지름 30
    seg = _trim_candidate_segment(host, QPointF(300, 0), [cutter])
    assert seg is not None
    edge_i, t0, t1 = seg
    assert edge_i == 0
    assert abs(t0 - 270.0 / 600.0) < 0.01
    assert abs(t1 - 330.0 / 600.0) < 0.01


def test_trim_candidate_segment_pathitem_cutter_ignored():
    # DXF 베지어 폴백(_PathItem)은 계획서 도형 범위 밖 — cutter 후보에서 조용히 제외된다.
    host = _RectItem(QRectF(0, 0, 600, 400))
    path = QPainterPath()
    path.addRect(QRectF(280, -20, 40, 40))
    cutter = _PathItem(path)
    assert _trim_candidate_segment(host, QPointF(300, 0), [cutter]) is None


# ---- 4단계: TRIM 도구(문지르기) — 실제 뷰 종단 시나리오 -----------------------------------

def test_trim_tool_click_commits_cut_and_drag_continues_rubbing():
    """[§8 항목17 4단계] 실제 `_AnnotatorView`에 press/move/release를 흘려 TRIM 도구 전체
    파이프라인(호버 예고 → 클릭 확정 → 드래그로 다음 교차 구간까지 문지르기 → release 종료)을
    검증한다. host 위쪽 변에 겹친 cutter 2개를 두고, 첫 번째는 클릭으로, 두 번째는 드래그로
    커밋되는지 확인 — "클릭=복제/드래그=화살표"류 다른 상호작용과 안 겹치는지도 함께 본다."""
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    _mk_pen_rect(w, x=80, y=-20, ww=40, hh=40)     # cutter1, x=80~120
    _mk_pen_rect(w, x=480, y=-20, ww=40, hh=40)    # cutter2, x=480~520
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)

    # 실사용 흐름대로: hover(move, 버튼 없음) → 예고가 뜬다.
    # [§8 항목17 5단계] _trim_preview 포맷이 ("closed"/"open"/"extend", ...) 태그 튜플로
    # 바뀌었다(열린 도형·EXTEND 지원 추가) — 닫힌 도형은 "closed" 태그 + 기존 4개 필드.
    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(100, 0), NB, NB))
    assert view._trim_preview is not None
    tp_kind, tp_host, tp_edge, tp_t0, tp_t1 = view._trim_preview
    assert tp_kind == "closed"
    assert tp_host is host and tp_edge == 0
    assert abs(tp_t0 - 80.0 / 600.0) < 1e-6 and abs(tp_t1 - 120.0 / 600.0) < 1e-6

    # 클릭 1회 = 확정.
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(100, 0), L, L))
    assert getattr(host, "_cuts", None) == [(0, tp_t0, tp_t1)]
    assert view._trim_dragging is True

    # 드래그로 두 번째 교차 지점까지 이동 — 문지르기로 이어서 커밋.
    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(500, 0), NB, L))
    assert len(host._cuts) == 2
    edge_i2, t0_2, t1_2 = host._cuts[1]
    assert edge_i2 == 0
    assert abs(t0_2 - 480.0 / 600.0) < 1e-6 and abs(t1_2 - 520.0 / 600.0) < 1e-6

    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(500, 0), L, NB))
    assert view._trim_dragging is False
    assert view._trim_seen == set()
    assert len(host._cuts) == 2   # release가 새 cut을 추가하지 않음


def test_trim_tool_does_not_move_or_select_shapes():
    # TRIM 도구가 켜진 동안은 클릭해도 도형 선택/이동이 일어나지 않는다(다른 도구와 혼선 방지).
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)

    # cutter 없이 호스트 몸통 안쪽을 클릭 — 자를 게 없으니 아무 일도 없어야 하고, 선택도 안 된다.
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(300, 200), L, L))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(300, 200), L, NB))
    assert not host.isSelected()
    assert getattr(host, "_cuts", None) in (None, [])


def test_trim_preview_renders_red_dashed_gap_pixel():
    """[§8 항목17 4단계 렌더] 계획서 "조작" 원문: 호버하면 지워질 구간을 빨간 점선으로 예고.
    실제 `drawForeground`(scene.render 경유)에서 그 구간 픽셀이 빨갛게 나오는지 확인."""
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QGraphicsView
    NB = Qt.MouseButton.NoButton

    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    _mk_pen_rect(w, x=280, y=-20, ww=40, hh=40)   # cutter, x=280~320
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view
    # [함정] view는 CanvasWindow 레이아웃의 자식이라 view.resize()가 show() 후 레이아웃에
    # 덮어써진다 — 창을 먼저 리사이즈·표시해 레이아웃을 안정시킨 뒤에야 실제 view 크기가
    # 확정된다(실측: resize(700,500) 요청해도 show() 후 900×644로 되돌아감).
    w.resize(900, 700)
    w.show()
    QApplication.processEvents()
    QApplication.processEvents()
    view.setSceneRect(QRectF(-50, -50, 700, 500))
    view.fitInView(QRectF(-50, -50, 700, 500), Qt.AspectRatioMode.KeepAspectRatio)
    QApplication.processEvents()

    vp = QPointF(view.mapFromScene(QPointF(300, 0)))
    view.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, vp, vp, NB, NB,
                                     Qt.KeyboardModifier.NoModifier))
    assert view._trim_preview is not None

    QApplication.processEvents()
    img = view.grab().toImage()
    dpr = img.width() / view.width()   # 오프스크린 플랫폼 배율 흡수(실측 1.0이지만 안전하게)
    px, py = int(vp.x() * dpr), int(vp.y() * dpr)
    reddest = None
    for dx in range(-4, 5):
        for dy in range(-2, 3):
            c = QColor(img.pixel(px + dx, py + dy))
            if reddest is None or c.red() - c.green() > reddest[0] - reddest[1]:
                reddest = (c.red(), c.green(), c.blue())
    assert reddest is not None and reddest[0] > 180 and reddest[0] - reddest[1] > 60, \
        f"TRIM 예고 구간에서 빨간 점선을 못 찾음: {reddest}"


# ---- 5단계: 열린 도형 분절 + EXTEND — 순수 기하 계산 ----------------------------------------

def test_trim_candidate_open_segment_line_crossed_by_rect_middle():
    line = _LineItem(QLineF(0, 0, 600, 0))
    cutter = _RectItem(QRectF(280, -20, 40, 40))
    seg = _trim_candidate_open_segment(line, QPointF(300, 0), [cutter])
    assert seg is not None
    lo, hi = seg
    assert lo[0] == 0 and hi[0] == 0
    assert abs(lo[1] - 280.0 / 600.0) < 1e-6
    assert abs(hi[1] - 320.0 / 600.0) < 1e-6


def test_trim_candidate_open_segment_none_without_cutter():
    line = _LineItem(QLineF(0, 0, 600, 0))
    assert _trim_candidate_open_segment(line, QPointF(300, 0), []) is None


def test_trim_candidate_open_segment_spans_vertex_across_two_segments():
    # L자 폴리라인: (0,0)->(300,0)->(300,300). 커터 2개가 각각 다른 세그먼트(0·1)에 걸쳐
    # 두 교차점 사이(첫 세그먼트 뒷부분 + 꼭짓점 + 둘째 세그먼트 앞부분)가 한 구간으로
    # 지워져야 한다 — 닫힌 도형의 "변 하나 안에서만" 가정을 못 쓰는 이유가 이것.
    poly = _PolyArrowItem(QColor("#111111"), 2, True)
    poly._pts = [QPointF(0, 0), QPointF(300, 0), QPointF(300, 300)]
    cutter1 = _RectItem(QRectF(80, -20, 40, 40))    # 세그먼트0(y=0) x=80~120 가로지름
    cutter2 = _RectItem(QRectF(280, 80, 40, 40))    # 세그먼트1(x=300) y=80~120 가로지름
    seg = _trim_candidate_open_segment(poly, QPointF(300, 0), [cutter1, cutter2])
    assert seg is not None
    lo, hi = seg
    assert lo[0] == 0 and hi[0] == 1, "자를 구간이 세그먼트 경계(꼭짓점)를 넘어가야 함"
    assert abs(lo[1] - 120.0 / 300.0) < 1e-6
    assert abs(hi[1] - 80.0 / 300.0) < 1e-6


def test_extend_candidate_line_extends_to_rect_edge():
    line = _LineItem(QLineF(0, 0, 100, 0))
    wall = _RectItem(QRectF(300, -50, 40, 100))   # x=300~340
    res = _extend_candidate(line, QPointF(100, 0), [wall])
    assert res is not None
    idx, pt = res
    assert idx == 1   # 끝점(idx 1) 쪽이 커서에 더 가까움
    assert abs(pt.x() - 300.0) < 1e-6 and abs(pt.y() - 0.0) < 1e-6


def test_extend_candidate_none_when_nothing_ahead():
    line = _LineItem(QLineF(0, 0, 100, 0))
    assert _extend_candidate(line, QPointF(100, 0), []) is None


def test_extend_candidate_picks_nearer_endpoint():
    line = _LineItem(QLineF(0, 0, 100, 0))
    wall = _RectItem(QRectF(-300, -50, 40, 100))   # x=-300~-260, 시작점(idx 0)쪽으로 늘어남
    res = _extend_candidate(line, QPointF(0, 0), [wall])
    assert res is not None
    idx, pt = res
    assert idx == 0
    assert abs(pt.x() - (-260.0)) < 1e-6


# ---- 5단계: 열린 도형 TRIM/EXTEND 커밋 — 실제 아이템 변형 ------------------------------------

def test_apply_open_item_trim_interior_bracket_splits_line_into_two_items():
    scene = QGraphicsScene()
    host = _LineItem(QLineF(0, 0, 600, 0))
    scene.addItem(host)
    lo, hi = (0, 280.0 / 600.0), (0, 320.0 / 600.0)
    clone = apply_open_item_trim(host, lo, hi)
    assert clone is not None and clone.scene() is scene
    assert _close(host.line().p1(), QPointF(0, 0)) and _close(host.line().p2(), QPointF(280, 0))
    assert _close(clone.line().p1(), QPointF(320, 0)) and _close(clone.line().p2(), QPointF(600, 0))


def test_apply_open_item_trim_touching_start_boundary_shortens_without_clone():
    scene = QGraphicsScene()
    host = _LineItem(QLineF(0, 0, 600, 0))
    scene.addItem(host)
    clone = apply_open_item_trim(host, (0, 0.0), (0, 320.0 / 600.0))
    assert clone is None
    assert _close(host.line().p1(), QPointF(320, 0)) and _close(host.line().p2(), QPointF(600, 0))


def test_apply_open_item_trim_touching_end_boundary_shortens_without_clone():
    scene = QGraphicsScene()
    host = _LineItem(QLineF(0, 0, 600, 0))
    scene.addItem(host)
    clone = apply_open_item_trim(host, (0, 280.0 / 600.0), (0, 1.0))
    assert clone is None
    assert _close(host.line().p1(), QPointF(0, 0)) and _close(host.line().p2(), QPointF(280, 0))


def test_apply_open_item_trim_preserves_bindings_on_split_polyarrow():
    # [바인딩 정책] 앞쪽 조각(host 자신)은 원래 시작 부착 유지 + 새 끝은 해제.
    # 뒤쪽 조각(복제본)은 원래 끝 부착 유지 + 새 시작은 해제.
    scene = QGraphicsScene()
    a = _RectItem(QRectF(-100, -50, 60, 40))
    b = _RectItem(QRectF(600, -50, 60, 40))
    scene.addItem(a); scene.addItem(b)
    host = _PolyArrowItem(QColor("#111111"), 2, True)
    host._pts = [QPointF(0, 0), QPointF(600, 0)]
    host.set_bound(0, a, QPointF(30, 20))
    host.set_bound(1, b, QPointF(30, 20))
    scene.addItem(host)
    clone = apply_open_item_trim(host, (0, 280.0 / 600.0), (0, 320.0 / 600.0))
    assert clone is not None
    assert host._bind_start is a and host._bind_end is None
    assert clone._bind_start is None and clone._bind_end is b


def test_apply_open_item_trim_before_piece_keeps_label_after_piece_starts_empty():
    # [라벨 정책, 5단계 설계 결정] host(앞쪽 조각)는 원래 라벨을 그대로 들고 가고, 복제된
    # 뒤쪽 조각은 라벨 없이 새로 시작한다(clone()이 라벨을 복사하지 않는 기존 관례 재사용) —
    # 같은 텍스트가 두 조각에 중복 표시되는 것을 피하는 선택.
    scene = QGraphicsScene()
    host = _LineItem(QLineF(0, 0, 600, 0))
    scene.addItem(host)
    host.ensure_label().setPlainText("배선1")
    clone = apply_open_item_trim(host, (0, 280.0 / 600.0), (0, 320.0 / 600.0))
    assert clone is not None
    assert host.has_label() and host._label.toPlainText() == "배선1"
    assert not clone.has_label()


def test_apply_extend_moves_endpoint_and_disables_auto_route():
    scene = QGraphicsScene()
    a = _RectItem(QRectF(0, -20, 60, 40))
    scene.addItem(a)
    host = _PolyArrowItem(QColor("#111111"), 2, True)
    host._pts = [QPointF(60, 0), QPointF(200, 0)]
    host.set_bound(0, a, QPointF(60, 20))
    host._auto_route = True
    scene.addItem(host)
    apply_extend(host, 0, QPointF(10, 0))
    assert _close(host._pts[0], QPointF(10, 0))
    assert host._auto_route is False
    assert host._bind_start is None


# ---- 5단계: 실제 뷰 종단 시나리오(TRIM 열린 도형 분절 + Shift=EXTEND) ------------------------

def test_trim_tool_click_splits_open_line_into_two_items_via_view():
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    w = CanvasWindow(); w.grid_enabled = False
    line = _LineItem(QLineF(0, 0, 600, 0))
    w._scene.addItem(line)
    _mk_pen_rect(w, x=280, y=-20, ww=40, hh=40)   # cutter, x=280~320
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)

    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(300, 0), NB, NB))
    assert view._trim_preview is not None and view._trim_preview[0] == "open"

    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(300, 0), L, NB))

    lines = [it for it in w._scene.items() if isinstance(it, _LineItem)]
    assert len(lines) == 2
    endpoints = sorted((round(it.line().p1().x()), round(it.line().p2().x())) for it in lines)
    assert endpoints == [(0, 280), (320, 600)]


def test_trim_tool_drag_rubbing_splits_open_line_at_multiple_crossings():
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    w = CanvasWindow(); w.grid_enabled = False
    line = _LineItem(QLineF(0, 0, 600, 0))
    w._scene.addItem(line)
    _mk_pen_rect(w, x=80, y=-20, ww=40, hh=40)     # cutter1, x=80~120
    _mk_pen_rect(w, x=480, y=-20, ww=40, hh=40)    # cutter2, x=480~520
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)

    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(100, 0), NB, NB))
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(100, 0), L, L))
    assert view._trim_dragging is True
    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(500, 0), NB, L))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(500, 0), L, NB))

    lines = sorted(
        (round(it.line().p1().x()), round(it.line().p2().x()))
        for it in w._scene.items() if isinstance(it, _LineItem))
    assert lines == [(0, 80), (120, 480), (520, 600)]


def test_trim_tool_open_host_does_not_move_or_select():
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    w = CanvasWindow(); w.grid_enabled = False
    line = _LineItem(QLineF(0, 0, 600, 0))
    line.setFlags(line.GraphicsItemFlag.ItemIsSelectable | line.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(line)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)

    # cutter 없이 몸통 위를 클릭 — 자를 게 없으니 아무 일도 없어야 하고, 선택도 안 된다.
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(300, 0), L, NB))
    assert not line.isSelected()
    assert _close(line.line().p1(), QPointF(0, 0)) and _close(line.line().p2(), QPointF(600, 0))


def test_extend_tool_shift_click_extends_line_endpoint_via_view():
    """[§8 항목17 5단계] EXTEND — Shift+클릭으로 끝점을 벽까지 늘인다. 실사용 시나리오대로
    마지막 hover 이후 마우스를 안 움직이고 Shift만 누른 채 바로 클릭하는 경로까지 확인한다
    (press가 stale hover 미리보기가 아니라 press 시점 modifiers로 다시 계산하는지)."""
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    SHIFT = Qt.KeyboardModifier.ShiftModifier

    w = CanvasWindow(); w.grid_enabled = False
    line = _LineItem(QLineF(0, 0, 100, 0))
    w._scene.addItem(line)
    _mk_pen_rect(w, x=300, y=-50, ww=40, hh=100)   # wall, x=300~340
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns, mods=Qt.KeyboardModifier.NoModifier):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, mods)

    # Shift 없이 hover하면 TRIM(자를 게 없어 None) — EXTEND로 새지 않는다.
    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(100, 0), NB, NB))
    assert view._trim_preview is None

    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(100, 0), NB, NB, SHIFT))
    assert view._trim_preview is not None and view._trim_preview[0] == "extend"

    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(100, 0), L, L, SHIFT))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(100, 0), L, NB, SHIFT))

    assert abs(line.line().p2().x() - 300.0) < 1e-6
    assert view._trim_dragging is False   # EXTEND는 1회성 — 문지르기로 안 넘어감


# ---- 6단계: 직렬화(.ecad) 왕복 -------------------------------------------------------------

def test_ecad_roundtrip_preserves_cuts_on_rect():
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    host = _RectItem(QRectF(0, 0, 200, 100))
    host.setPen(QPen(QColor("black"), 2))
    sc.addItem(host)
    _add_border_cut(host, 0, 0.25, 0.75)
    path = os.path.join(_TMP, "cuts_roundtrip.ecad")
    save_document(sc, path)

    sc2 = QGraphicsScene()
    load_document(sc2, path)
    loaded = [it for it in sc2.items() if isinstance(it, _RectItem)]
    assert len(loaded) == 1
    assert loaded[0]._cuts == [(0, 0.25, 0.75)]


def test_ecad_roundtrip_without_cuts_omits_key_and_stays_none():
    # 하위호환 — cut이 없는 기존 문서는 "cuts" 키 자체가 없고, 로드해도 _cuts는 None(빈 목록
    # 강제 생성 안 함, build_trimmed_border_path 등은 이미 `or []` 폴백으로 처리).
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    host = _RectItem(QRectF(0, 0, 200, 100))
    host.setPen(QPen(QColor("black"), 2))
    sc.addItem(host)
    path = os.path.join(_TMP, "no_cuts_roundtrip.ecad")
    save_document(sc, path)
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    assert "cuts" not in doc["items"][0]

    sc2 = QGraphicsScene()
    load_document(sc2, path)
    loaded = [it for it in sc2.items() if isinstance(it, _RectItem)]
    assert getattr(loaded[0], "_cuts", None) is None


# ---- 6단계: DXF 내보내기가 cut을 반영하는지 -------------------------------------------------

def test_dxf_export_reflects_cut_only_rect_without_ports():
    # [§8 항목17 6단계] 이전엔 _export_rect가 `_ports` 유무만 보고 진짜 분절로 갈아탔다 —
    # 포트 없이 TRIM cut만 있는(항목17이 만든 새 워크플로) 사각형은 안 잘린 채로 나갔었다.
    w = CanvasWindow()
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    _add_border_cut(host, 0, 0.25, 0.75)
    _mk_pen_rect(w, x=400, y=0, ww=100, hh=60)   # cut 없는 회귀 확인용

    out = os.path.join(_TMP, "cut_only.dxf")
    assert export_dxf(w._scene, out) is not False
    import ezdxf
    doc = ezdxf.readfile(out)
    msp = doc.modelspace()
    lines = list(msp.query("LINE"))
    polys = list(msp.query("LWPOLYLINE"))
    # host: 끊긴 위쪽 변 2조각 + 나머지 3변 = 5 LINE. 두 번째 rect: 닫힌 4점 LWPOLYLINE 1개.
    assert len(lines) == 5
    assert len(polys) == 1 and len(polys[0]) == 4


def test_dxf_export_reflects_cut_only_ellipse_as_lines():
    # [§8 항목17 6단계] _export_ellipse는 애초에 포트/cut 분기가 없어 원형 포트조차 DXF에서
    # 안 잘린 CIRCLE/ELLIPSE로 나가던 잠재 버그였다 — rect/symbol과 같은 관례로 통일.
    w = CanvasWindow()
    ell = _EllipseItem(QRectF(0, 0, 200, 100))
    ell.setPen(w.make_pen())
    ell.setFlags(ell.GraphicsItemFlag.ItemIsSelectable | ell.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ell)
    n = len(_host_outline_local_polygon(ell))
    arc = max(4, n // 6)   # 픽셀·엔티티 검사에 넉넉한 호 하나(2단계 테스트와 같은 관례)
    for i in range(arc):
        _add_border_cut(ell, i, 0.0, 1.0)

    out = os.path.join(_TMP, "cut_ellipse.dxf")
    assert export_dxf(w._scene, out) is not False
    import ezdxf
    doc = ezdxf.readfile(out)
    types = [e.dxftype() for e in doc.modelspace()]
    assert "LINE" in types
    assert "CIRCLE" not in types and "ELLIPSE" not in types


# ---- 6단계: undo/redo -----------------------------------------------------------------------

def test_undo_redo_closed_shape_trim_cut():
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    _mk_pen_rect(w, x=280, y=-20, ww=40, hh=40)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)

    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(300, 0), NB, NB))
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(300, 0), L, NB))

    def cuts_close(cuts, want):
        return len(cuts) == len(want) and all(
            c[0] == w0 and abs(c[1] - t0) < 1e-6 and abs(c[2] - t1) < 1e-6
            for c, (w0, t0, t1) in zip(cuts, want))

    want = [(0, 280.0 / 600.0, 320.0 / 600.0)]
    assert cuts_close(host._cuts, want)

    w.undo()
    assert getattr(host, "_cuts", None) in (None, [])
    w.redo()
    assert cuts_close(host._cuts, want)


def test_undo_coalesces_whole_rubbing_drag_into_one_step():
    # [핵심 검증] 드래그 한 번(press+move+move...+release)으로 커밋한 cut 여러 개가
    # Ctrl+Z 한 번에 전부 원복돼야 한다 — push_undo_move의 coalesce_key 패턴을 재사용.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    w = CanvasWindow(); w.grid_enabled = False
    host = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    _mk_pen_rect(w, x=80, y=-20, ww=40, hh=40)
    _mk_pen_rect(w, x=480, y=-20, ww=40, hh=40)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)

    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(100, 0), NB, NB))
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(100, 0), L, L))
    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(500, 0), NB, L))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(500, 0), L, NB))
    assert len(host._cuts) == 2

    w.undo()
    assert getattr(host, "_cuts", None) in (None, [])
    w.redo()
    assert len(host._cuts) == 2


def test_undo_redo_open_line_trim_split_restores_and_removes_clone():
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    w = CanvasWindow(); w.grid_enabled = False
    line = _LineItem(QLineF(0, 0, 600, 0))
    w._scene.addItem(line)
    _mk_pen_rect(w, x=280, y=-20, ww=40, hh=40)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)

    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(300, 0), NB, NB))
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(300, 0), L, NB))
    assert len([it for it in w._scene.items() if isinstance(it, _LineItem)]) == 2

    w.undo()
    remaining = [it for it in w._scene.items() if isinstance(it, _LineItem)]
    assert len(remaining) == 1
    assert _close(remaining[0].line().p1(), QPointF(0, 0))
    assert _close(remaining[0].line().p2(), QPointF(600, 0))

    w.redo()
    lines_after_redo = [it for it in w._scene.items() if isinstance(it, _LineItem)]
    assert len(lines_after_redo) == 2
    endpoints = sorted((round(it.line().p1().x()), round(it.line().p2().x()))
                        for it in lines_after_redo)
    assert endpoints == [(0, 280), (320, 600)]


def test_undo_redo_open_polyarrow_trim_split_preserves_bindings():
    # [핵심 검증] capture_geom()/apply_geom()이 _PolyArrowItem의 pts뿐 아니라 바인딩까지
    # 이미 포괄하므로(4단계 조사) 별도 "바인딩 전용" undo 코드 없이도 분리 전후 바인딩이
    # 정확히 왕복하는지 실제 뷰 시나리오로 확인한다.
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton

    w = CanvasWindow(); w.grid_enabled = False
    a = _mk_pen_rect(w, x=-100, y=-50, ww=60, hh=40)
    b = _mk_pen_rect(w, x=600, y=-50, ww=60, hh=40)
    sa = _PolyArrowItem(QColor("#111111"), 2, True)
    sa._pts = [QPointF(0, 0), QPointF(600, 0)]
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(30, 20))
    sa.set_bound(1, b, QPointF(30, 20))
    _mk_pen_rect(w, x=280, y=-20, ww=40, hh=40)   # cutter
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, Qt.KeyboardModifier.NoModifier)

    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(300, 0), NB, NB))
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(300, 0), L, L))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(300, 0), L, NB))

    polys = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(polys) == 2
    clone = next(p for p in polys if p is not sa)
    assert sa._bind_start is a and sa._bind_end is None
    assert clone._bind_start is None and clone._bind_end is b

    w.undo()
    polys_after_undo = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(polys_after_undo) == 1
    assert sa._bind_start is a and sa._bind_end is b   # 원래 양끝 부착 복원

    w.redo()
    polys_after_redo = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(polys_after_redo) == 2
    clone2 = next(p for p in polys_after_redo if p is not sa)
    assert sa._bind_start is a and sa._bind_end is None
    assert clone2._bind_start is None and clone2._bind_end is b


def test_undo_redo_extend():
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    L, NB = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
    SHIFT = Qt.KeyboardModifier.ShiftModifier

    w = CanvasWindow(); w.grid_enabled = False
    line = _LineItem(QLineF(0, 0, 100, 0))
    w._scene.addItem(line)
    _mk_pen_rect(w, x=300, y=-50, ww=40, hh=100)
    w._scene.clearSelection()
    w.set_tool("trim")
    view = w._view

    def ev(etype, scene_pt, btn, btns, mods=Qt.KeyboardModifier.NoModifier):
        vp = QPointF(view.mapFromScene(scene_pt))
        return QMouseEvent(etype, vp, vp, btn, btns, mods)

    view.mouseMoveEvent(ev(QEvent.Type.MouseMove, QPointF(100, 0), NB, NB, SHIFT))
    view.mousePressEvent(ev(QEvent.Type.MouseButtonPress, QPointF(100, 0), L, L, SHIFT))
    view.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, QPointF(100, 0), L, NB, SHIFT))
    assert abs(line.line().p2().x() - 300.0) < 1e-6

    w.undo()
    assert abs(line.line().p2().x() - 100.0) < 1e-6
    w.redo()
    assert abs(line.line().p2().x() - 300.0) < 1e-6
