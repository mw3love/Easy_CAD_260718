"""[§8 항목21] 다각형/폴리라인 도구 — 그리기(닫기/열린종료/취소)·이동·리사이즈·undo·`.ecad` 왕복.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part11_polygon.py. 설계 확정 문서: docs/polygon_tool_design.md.
"""
import os

from PyQt6.QtGui import QKeyEvent
from PyQt6.QtCore import QEvent

from _shared import *  # noqa: F401,F403


def _polygons(w):
    return [it for it in w._scene.items() if isinstance(it, _PolygonItem)]


def test_polygon_triangle_close_by_reclick_start():
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)

    click(QPointF(0, 0))
    assert view._place is not None and view._place_tool == "polygon"
    click(QPointF(200, 0))
    click(QPointF(100, 150))
    move(QPointF(3, 2))              # 시작점 근처 예고
    click(QPointF(3, 2))             # 시작점 재클릭 = 닫기
    assert view._place is None

    polys = _polygons(w)
    assert len(polys) == 1
    p = polys[0]
    assert p._closed is True
    pts = [(round(pt.x()), round(pt.y())) for pt in p.local_pts()]
    assert pts == [(0, 0), (200, 0), (100, 150)], pts
    assert p.isSelected()


def test_polygon_pentagon_close():
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)

    verts = [(100, 0), (195, 70), (160, 180), (40, 180), (5, 70)]
    for x, y in verts:
        click(QPointF(x, y))
    click(QPointF(102, 3))           # 시작점(100,0) 근처 재클릭 = 닫기

    polys = _polygons(w)
    assert len(polys) == 1
    p = polys[0]
    assert p._closed is True
    pts = [(round(pt.x()), round(pt.y())) for pt in p.local_pts()]
    assert pts == verts, pts


def test_polygon_close_requires_at_least_three_vertices():
    # 확정 정점 2개(시작+1개)뿐일 때 시작점 재클릭은 닫기로 취급하지 않는다(퇴화 다각형 방지).
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)

    click(QPointF(0, 0))
    click(QPointF(200, 0))
    click(QPointF(1, 1))             # 시작점 근처지만 정점 2개뿐 — 닫기 무시, 정점 추가로 처리
    assert view._place is not None, "정점 2개뿐이면 재클릭이 닫기를 트리거하면 안 됨"
    view._cancel_place()


def test_polygon_open_polyline_via_double_click():
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)

    click(QPointF(0, 0))
    click(QPointF(100, 0))
    move(QPointF(80, 100))
    dbl(QPointF(80, 100))            # 더블클릭 = 열린 폴리라인으로 종료
    assert view._place is None

    polys = _polygons(w)
    assert len(polys) == 1
    p = polys[0]
    assert p._closed is False
    pts = [(round(pt.x()), round(pt.y())) for pt in p.local_pts()]
    assert pts == [(0, 0), (100, 0), (80, 100)], pts


def test_polygon_open_polyline_via_enter():
    # [sarrow와 동일 관례] Enter는 '커서가 지금 가리키는 위치'가 아니라 '이미 클릭으로
    # 확정한 점까지' 마무리한다(_finish_polygon이 미리보기 점만 pop) — 그래서 마지막 정점도
    # click으로 확정한 뒤 Enter를 눌러야 그 점이 포함된다.
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    NO = Qt.KeyboardModifier.NoModifier

    click(QPointF(0, 0))
    click(QPointF(100, 0))
    click(QPointF(50, 80))
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, NO))
    assert view._place is None

    polys = _polygons(w)
    assert len(polys) == 1
    assert polys[0]._closed is False
    pts = [(round(pt.x()), round(pt.y())) for pt in polys[0].local_pts()]
    assert pts == [(0, 0), (100, 0), (50, 80)], pts


def test_polygon_escape_cancels_without_creating_item():
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    NO = Qt.KeyboardModifier.NoModifier

    click(QPointF(0, 0))
    click(QPointF(100, 0))
    click(QPointF(50, 80))
    assert view._place is not None
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, NO))
    assert view._place is None
    assert _polygons(w) == [], "Esc는 다각형 도구에서 전체 취소해야 함(sarrow와 다름)"


def _mk_triangle(w):
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    click(QPointF(0, 0))
    click(QPointF(200, 0))
    click(QPointF(100, 150))
    click(QPointF(2, 2))
    return _polygons(w)[0]


def test_polygon_move_is_rigid():
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    p = _mk_triangle(w)
    before = [p.mapToScene(pt) for pt in p.local_pts()]
    p.moveBy(50, 20)
    after = [p.mapToScene(pt) for pt in p.local_pts()]
    for b, a in zip(before, after):
        assert _close(QPointF(b.x() + 50, b.y() + 20), a)


def test_polygon_box_resize_scales_points():
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    p = _mk_triangle(w)
    r0 = QRectF(p.rect())
    # 우하단 모서리(꼭짓점 2)를 오른쪽/아래로 끌어 폭·높이를 2배로.
    _box_drag(p, "corner", 2, QPointF(r0.right() * 2, r0.bottom() * 2), w)
    r1 = p.rect()
    assert abs(r1.width() - r0.width() * 2) < 1.0
    assert abs(r1.height() - r0.height() * 2) < 1.0
    # 정규화좌표는 불변 — 리사이즈 후에도 여전히 삼각형 3정점.
    assert len(p.local_pts()) == 3


def test_polygon_undo_redo_add():
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    p = _mk_triangle(w)
    assert p in w._scene.items()
    w.undo()
    assert p not in w._scene.items()
    w.redo()
    assert _polygons(w) != []


def test_polygon_ecad_roundtrip_closed_with_fill():
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    p = _mk_triangle(w)
    p.apply_fill(QColor("#3366cc"))
    orig_pts = [(round(pt.x()), round(pt.y())) for pt in p.local_pts()]

    path = os.path.join(_TMP, "polygon_closed.ecad")
    save_document(w._scene, path)
    w2 = CanvasWindow()
    n = load_document(w2._scene, path)
    assert n == 1
    loaded = _polygons(w2)
    assert len(loaded) == 1
    lp = loaded[0]
    assert lp._closed is True
    assert [(round(pt.x()), round(pt.y())) for pt in lp.local_pts()] == orig_pts
    assert lp.brush().color().name() == "#3366cc"


def test_polygon_ecad_roundtrip_open_no_fill():
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    click(QPointF(0, 0))
    click(QPointF(120, 10))
    move(QPointF(60, 90))
    dbl(QPointF(60, 90))
    p = _polygons(w)[0]
    orig_pts = [(round(pt.x()), round(pt.y())) for pt in p.local_pts()]

    path = os.path.join(_TMP, "polygon_open.ecad")
    save_document(w._scene, path)
    w2 = CanvasWindow()
    n = load_document(w2._scene, path)
    assert n == 1
    lp = _polygons(w2)[0]
    assert lp._closed is False
    assert [(round(pt.x()), round(pt.y())) for pt in lp.local_pts()] == orig_pts
    assert lp.brush().style() == Qt.BrushStyle.NoBrush


def test_polygon_duplicate_selection_clones_geometry():
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    p = _mk_triangle(w)
    p.apply_fill(QColor("#aa5522"))
    p.setSelected(True)
    w.duplicate_selection()
    polys = _polygons(w)
    assert len(polys) == 2
    dup = [x for x in polys if x is not p][0]
    assert dup._closed is True
    assert dup.brush().color().name() == "#aa5522"
    # moveBy(20,20)은 pos()만 바꾸고 local_pts()(로컬좌표)는 불변 — clone 직후 정점 자체가
    # 원본과 같은지 확인(오프셋은 mapToScene에서만 드러남, test_polygon_move_is_rigid와 동일 근거).
    orig_pts = [(round(pt.x()), round(pt.y())) for pt in p.local_pts()]
    dup_pts = [(round(pt.x()), round(pt.y())) for pt in dup.local_pts()]
    assert dup_pts == orig_pts, (dup_pts, orig_pts)
    orig_scene = [p.mapToScene(pt) for pt in p.local_pts()]
    dup_scene = [dup.mapToScene(pt) for pt in dup.local_pts()]
    for o, d in zip(orig_scene, dup_scene):
        assert _close(QPointF(o.x() + 20, o.y() + 20), d)


def test_polygon_dxf_export_skips_without_crash():
    # [§8 항목21 v1 스코프] DXF 내보내기는 미구현 — 크래시 없이 조용히 건너뛰기만 확인.
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    _mk_triangle(w)
    path = os.path.join(_TMP, "polygon_skip.dxf")
    assert export_dxf(w._scene, path) is True


def test_polygon_vertex_snaps_to_other_shape_border():
    # [실사용 피드백 2026-08-18] "다른 도형에 붙거나" — 정점 배치 중 클릭이 다른 도형 테두리
    # 근처면 line/sarrow와 동일하게 그 테두리 최근접점으로 스냅돼야 한다(그리드 스냅만으론 부족).
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    _mk_rect(w._scene, w.make_pen(), 300, 300, 100, 60)   # 위쪽 변 y=300, x∈[300,400]

    click(QPointF(0, 0))
    # (320,304)는 위쪽 변 최근접점(320,300)에서 4px — 연속 폴백 반경(14px) 안, 변 중점 포트
    # (350,300)에서는 ~30px로 이산 반경(18px) 밖 → Pass2(연속) 스냅만 걸려야 한다.
    move(QPointF(320, 304))
    assert view._arrow_tip_snap is not None, "테두리 근처인데 스냅 마커가 안 뜸"
    click(QPointF(320, 304))
    dbl(QPointF(150, 150))   # 열린 폴리라인으로 종료(닫기 판정과 무관하게 스냅점만 확인)

    p = _polygons(w)[0]
    pts = [(round(pt.x()), round(pt.y())) for pt in p.local_pts()]
    assert pts[1] == (320, 300), pts   # 클릭 좌표(320,304)가 아니라 테두리 스냅점(320,300)


def test_polygon_start_point_snaps_to_other_shape_border():
    # 시작점도 line/sarrow와 동일하게 테두리 스냅이 적용돼야 한다.
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    _mk_rect(w._scene, w.make_pen(), 300, 300, 100, 60)

    # [주의] 시작 클릭은 배치모드 진입 전이라 `_is_empty_area` 게이트를 그대로 탄다 — 도형
    # '내부'는 물론 테두리에서 몇 px 밖까지도 펜 두께의 히트테스트 여유(`_EDGE_HIT_MIN`)에
    # 걸려 "빈 영역"이 아니다(실측: 4px 밖도 non-empty, 8px 밖부터 empty). 다른 도구도 동일한
    # 게이트라 다각형만의 특례가 아니다. 그래서 히트여유 밖(9px) + 테두리 스냅 반경(14px) 안인
    # 지점(320,291)을 찍어야 "빈 영역 클릭 + 테두리 근접 스냅" 조합이 성립한다.
    click(QPointF(320, 291))
    click(QPointF(500, 500))
    dbl(QPointF(150, 150))

    p = _polygons(w)[0]
    pts = [(round(pt.x()), round(pt.y())) for pt in p.local_pts()]
    assert pts[0] == (320, 300), pts


def test_polygon_closing_preview_snaps_exactly_to_start_vertex():
    # "닫히는 도형이 될 때 snap이 되야" — 시작점 근접 시 미리보기 자체가 시작점으로 스냅돼야
    # 사용자가 닫기 직전임을 커서로 보고 확인할 수 있다(클릭 판정만이 아니라 미리보기도).
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)

    click(QPointF(0, 0))
    click(QPointF(200, 0))
    click(QPointF(100, 150))
    move(QPointF(6, 4))   # 시작점(0,0) 근처(닫기 판정 반경 12px 안) — 미리보기가 딱 시작점으로
    it = view._place
    assert it is not None
    last = it._draw_pts[-1]
    assert (round(last.x()), round(last.y())) == (0, 0), last
    # [실사용 피드백 2026-08-18] 좌표만 스냅되는 게 아니라 포트점과 같은 시각 마커도 서야 한다.
    assert view._arrow_tip_snap is not None
    assert (round(view._arrow_tip_snap.x()), round(view._arrow_tip_snap.y())) == (0, 0)
    view._cancel_place()


def test_polygon_vertex_snaps_to_other_polygon_border():
    # [실사용 피드백 2026-08-18] "다각형으로 만들어진 도형에 snap하면 안 붙음" — 닫힌
    # 다각형도 사각형/타원/심볼과 동일하게 다른 도형의 테두리 스냅 대상이 돼야 한다.
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)
    _mk_triangle(w)   # (0,0)-(200,0)-(100,150) 닫힌 삼각형, 아래쪽 변: (200,0)-(100,150)

    click(QPointF(500, 500))
    # 아래쪽 변(200,0)-(100,150) 위 t=0.5 지점은 (150,75). 그 근처(154,79)를 찍으면 변 위
    # 최근접점으로 스냅돼야 한다(연속 폴백, 이산 포트 중점과 충분히 떨어진 지점을 고름).
    click(QPointF(154, 79))
    dbl(QPointF(400, 400))

    polys = _polygons(w)
    assert len(polys) == 2
    new_poly = next(p for p in polys
                     if any(abs(pt.x() - 500) < 1 and abs(pt.y() - 500) < 1 for pt in p.local_pts()))
    pts = [(round(pt.x(), 1), round(pt.y(), 1)) for pt in new_poly.local_pts()]
    assert pts[0] == (500.0, 500.0)
    # 클릭 좌표(154,79)가 그대로 남으면 스냅 실패 — 삼각형 변 위 최근접점으로 바뀌어 있어야 함.
    snapped = pts[1]
    assert snapped != (154.0, 79.0), pts
    # 최근접점은 아래쪽 변(200,0)-(100,150) 근처 범위 안(정확한 값은 부동소수라 근사 확인).
    assert 145 <= snapped[0] <= 158 and 68 <= snapped[1] <= 82, snapped


def test_polygon_open_polyline_is_snap_target_like_a_line():
    # 열린 폴리라인도 선/화살표처럼 몸통에 스냅돼야 한다.
    w = CanvasWindow(); w.show(); w.set_tool("polygon"); w._zoom_reset()
    view = w._view
    press, release, click, move, drag_move, dbl = _draw_helpers(view)

    click(QPointF(0, 0))
    click(QPointF(200, 0))
    dbl(QPointF(200, 0))   # 열린 폴리라인 하나: (0,0)-(200,0)
    polys = _polygons(w)
    assert len(polys) == 1 and polys[0]._closed is False

    click(QPointF(500, 500))
    click(QPointF(100, 4))   # 열린 폴리라인 몸통(y=0) 근처 — 연속 폴백 반경(14px) 안
    dbl(QPointF(400, 400))

    new_poly = next(p for p in _polygons(w)
                     if any(abs(pt.x() - 500) < 1 and abs(pt.y() - 500) < 1 for pt in p.local_pts()))
    pts = [(round(pt.x(), 1), round(pt.y(), 1)) for pt in new_poly.local_pts()]
    assert pts[1] != (100.0, 4.0), pts   # 스냅 안 됐으면 클릭 좌표 그대로 남음
    assert abs(pts[1][0] - 100) < 2 and abs(pts[1][1] - 0) < 2, pts
