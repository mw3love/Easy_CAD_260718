"""2026-10-17 사용자 지적 "이미지만 안 붙는다는 건 말이 안 됨" — 화살표가 붙는 도형에 이미지·표를 넣고, 종류 목록을
`core_shapes._is_conn_host`/`_ROUTE_BOX_TYPES` 한 곳으로 모음. 전엔 core_view 여러 곳에 목록이 따로 있어 이미지가 조용히 빠졌다.
"""
from _shared import *  # noqa: F401,F403
from PyQt6.QtGui import QPixmap
from easycad.canvas.annotator_core import _is_conn_host


def _mk_image(w, x, y, wd=100, ht=80):
    pm = QPixmap(40, 40); pm.fill(QColor("#ff8899aa"))
    img = _ImageItem(pm, QRectF(0, 0, wd, ht))
    img.setFlags(img.GraphicsItemFlag.ItemIsSelectable | img.GraphicsItemFlag.ItemIsMovable)
    img.setPos(x, y)
    w._scene.addItem(img)
    return img


def test_image_and_table_are_conn_hosts():
    w = CanvasWindow()
    img = _mk_image(w, 0, 0)
    tbl = _TableItem(2, 3, QRectF(0, 0, 120, 40)); w._scene.addItem(tbl); tbl.setPos(300, 0)
    assert _is_conn_host(img) and _is_conn_host(tbl)
    shapes = w._view._conn_shapes()
    assert img in shapes and tbl in shapes


def test_arrow_snaps_to_image_port_and_follows_it():
    w = CanvasWindow(); w.show(); w._zoom_reset()
    img = _mk_image(w, 200, 0)                      # 왼쪽 변 가운데 = (200, 40)
    snap = w._view._border_snap_at(w._view.mapFromScene(QPointF(203, 43)))
    assert snap is not None and snap[2] is img
    assert _close(snap[0], QPointF(200, 40))
    # 미선택 이미지 테두리에서도 포트점 예고 → 화살표 시작 가능
    assert w._view._hover_port_at(w._view.mapFromScene(QPointF(201, 40))) is not None
    arrow = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    arrow.set_points(QPointF(0, 40), QPointF(200, 40))
    w._scene.addItem(arrow)
    arrow.set_bound(1, img, img.mapFromScene(QPointF(200, 40)))
    img.moveBy(50, 30)
    assert arrow.reroute() is True
    assert _close(arrow.mapToScene(arrow._endpoints()[-1]), QPointF(250, 70))


def test_route_avoids_image_obstacle():
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 80, 80)
    b = _mk_rect(w._scene, w.make_pen(), 400, 0, 80, 80)
    img = _mk_image(w, 180, 0, 120, 80)             # 둘 사이를 막는 이미지
    arrow = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    arrow.set_points(QPointF(80, 40), QPointF(400, 40))
    w._scene.addItem(arrow)
    arrow.set_bound(0, a, a.mapFromScene(QPointF(80, 40)))
    arrow.set_bound(1, b, b.mapFromScene(QPointF(400, 40)))
    arrow._auto_route = True
    arrow.reroute()
    pts = [arrow.mapToScene(p) for p in arrow._endpoints()]
    box = img.mapRectToScene(img.rect())
    for p, q in zip(pts, pts[1:]):
        seg = QRectF(p, q).normalized().adjusted(-0.5, -0.5, 0.5, 0.5)
        assert not seg.intersected(box.adjusted(1, 1, -1, -1)).isValid() or seg.intersected(box.adjusted(1, 1, -1, -1)).isEmpty(), (p, q)
