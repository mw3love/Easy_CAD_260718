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

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part8_trim_kernel.py.
"""
from _shared import *  # noqa: F401,F403


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
