"""§8 항목61 ④-4(2026-10-19) — 데스크톱 화살표도 웹과 같게: 상자 '안'에서 시작·끝내면 그 상자에 붙고, 반대쪽을 향한 변으로 들어간다.
(웹 `e2e/flow4-arrow`와 같은 그림 — 전엔 시작 쪽이 떠 있었음, 2026-10-19 재현.)
"""
from _shared import *  # noqa: F401,F403
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtTest import QTest


def _drag(v, a, b):
    pt = lambda p: v.mapFromScene(*p)
    QTest.mousePress(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt(a))
    QTest.mouseMove(v.viewport(), pt(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)))
    QTest.mouseMove(v.viewport(), pt(b))
    QTest.mouseRelease(v.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt(b))
    QApplication.processEvents()


def _arrows(w):
    return [it for it in w._scene.items() if type(it).__name__ == "_PolyArrowItem"]


def test_sarrow_from_box_middle_to_box_middle_binds_both_facing_sides():
    w = CanvasWindow(); w.resize(1000, 700); w.show(); QApplication.processEvents()
    v = w._view
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 120, 60)
    b = _mk_rect(w._scene, w.make_pen(), 400, 0, 120, 60)
    v.centerOn(260, 30); QApplication.processEvents()
    w.set_tool("sarrow"); QApplication.processEvents()
    _drag(v, (60, 30), (460, 30))
    (arr,) = _arrows(w)
    assert arr._bound(0) is a and arr._bound(1) is b
    s, e = arr.mapToScene(arr._pts[0]), arr.mapToScene(arr._pts[-1])
    assert (round(s.x()), round(s.y())) == (120, 30)   # A 오른쪽 변 가운데
    assert (round(e.x()), round(e.y())) == (400, 30)   # B 왼쪽 변 가운데(위로 돌아 들어가지 않음)
    b.setPos(QPointF(0, 200)); QApplication.processEvents()   # 옮기면 따라옴
    assert round(arr.mapToScene(arr._pts[-1]).y()) > 150
