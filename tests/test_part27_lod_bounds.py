"""LOD ①(2026-10-03) — 끝점형 도형(선·경로·곧은 화살표)은 끝점 핸들이 보일 때(선택+단일선택)만
그 자리를 boundingRect에 예약한다. 미선택·다중선택이면 내용 경계만(전체 보기·전체 선택이 가벼워짐)."""
from PyQt6.QtCore import QLineF, QPointF
from PyQt6.QtGui import QPainterPath

from _shared import *  # noqa: F401,F403


def _path(w, x0=0, y0=0):
    p = QPainterPath(QPointF(x0, y0))
    p.lineTo(QPointF(x0 + 200, y0 + 80))
    it = _PathItem(p)
    it.setPen(w.make_pen())
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    return it


def _line(w, y=300):
    it = _LineItem(QLineF(0, y, 200, y))
    it.setPen(w.make_pen())
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    return it


def _covers_shape(it):
    return it.boundingRect().contains(it.shape().boundingRect())


def test_unselected_endpoint_items_skip_handle_reserve():
    w = CanvasWindow()
    for it in (_path(w), _line(w)):
        unsel = it.boundingRect()
        it.setSelected(True)
        sel = it.boundingRect()
        assert sel.contains(unsel) and sel != unsel     # 선택하면 핸들 자리만큼 넓어짐
        assert _covers_shape(it)                         # 끝점 잡기 영역이 잘리지 않음
        w._scene.clearSelection()
        assert it.boundingRect() == unsel                # 해제하면 다시 내용 경계만
        assert _covers_shape(it)


def test_multi_selection_skips_reserve_and_one_left_restores_it():
    w = CanvasWindow()
    a, b = _path(w), _line(w)
    unsel_a = a.boundingRect()
    a.setSelected(True)
    single_a = a.boundingRect()
    b.setSelected(True)
    w._sync_selection_count_cache()
    assert a.boundingRect() == unsel_a               # 다중선택이면 개별 끝점 핸들 없음
    b.setSelected(False)
    w._sync_selection_count_cache()
    assert a.boundingRect() == single_a              # 하나만 남으면 다시 예약
    assert _covers_shape(a)


def test_selected_single_path_endpoint_is_grabbable():
    # 끝점 핸들 잡기 영역이 shape에 있고 boundingRect 안에 있어야 Qt가 클릭을 이 도형에 보낸다.
    w = CanvasWindow()
    it = _path(w)
    it.setSelected(True)
    end = it.mapToScene(it._endpoints()[1])
    probe = it.mapFromScene(QPointF(end.x() + 6, end.y() + 6))   # 끝점 살짝 바깥(핸들 잡기 여유)
    assert it.shape().contains(probe)
    assert it.boundingRect().contains(probe)
