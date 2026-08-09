"""§8 항목17(범용 CAD TRIM/EXTEND) 1단계 — 기하 커널 순수함수(선분-선분/원/타원 교차점).

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part8_trim_kernel.py. 좌표계 무관 순수함수라 Qt 아이템 없이 QPointF/QRectF만으로
검증한다 — 렌더(간격이 실제로 화면·PDF에 보이는지)는 이 파일이 아니라 실조건 검증(세션 기록
참조, `tests/test_part4_ports_fileio.py::test_true_segmented_border_survives_scene_render_and_grab`
가 오프스크린 회귀 몫)이 맡는다.
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
