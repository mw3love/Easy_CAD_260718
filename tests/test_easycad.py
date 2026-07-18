"""Easy CAD 회귀 스모크 — offscreen에서 핵심 파이프라인을 검증.

실행: python tests/test_easycad.py   (또는 pytest tests/)
GUI 없이 QT_QPA_PLATFORM=offscreen으로 구성·렌더·직렬화·지속연결을 확인한다.
실조건(실제 창 조작)은 python run.py로 별도 확인.
"""
import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QRectF, QLineF, QPointF
from PyQt6.QtGui import QBrush, QColor, QPainterPath

from easycad.canvas.host import CanvasWindow
from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _LineItem, _PathItem, _ArrowItem, _TextItem, _BadgeItem)
from easycad.fileio.pdf_export import export_pdf, _selection_rect
from easycad.fileio.document import save_document, load_document, item_to_dict

_app = QApplication.instance() or QApplication([])
_TMP = tempfile.mkdtemp(prefix="easycad_test_")


def _close(a, b, eps=0.5):
    return abs(a.x() - b.x()) < eps and abs(a.y() - b.y()) < eps


def _mk_rect(scene, pen, x, y, w, h):
    it = _RectItem(QRectF(x, y, w, h)); it.setPen(pen); it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    scene.addItem(it); return it


def test_host_construction():
    w = CanvasWindow()
    assert len(w._tool_buttons) == 8
    r = w._scene.sceneRect()
    assert r.width() > 90000 and r.height() > 90000
    m0 = w._view.transform().m11()
    w._on_wheel_zoom(120)
    assert w._view.transform().m11() > m0


def test_pdf_export():
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 120, 60)
    r2 = _mk_rect(w._scene, w.make_pen(), 300, 0, 120, 60)
    for pg in ("A4", "A1"):
        p = os.path.join(_TMP, f"full_{pg}.pdf")
        assert export_pdf(w._scene, p, page=pg)
        data = open(p, "rb").read()
        assert data[:5] == b"%PDF-" and b"/Page" in data
    w._scene.clearSelection(); r2.setSelected(True)
    assert export_pdf(w._scene, os.path.join(_TMP, "sel.pdf"), selection_only=True)
    assert _selection_rect(w._scene).width() < w._scene.itemsBoundingRect().width()
    w._scene.clearSelection()
    assert export_pdf(w._scene, os.path.join(_TMP, "empty.pdf"), selection_only=True) is False


def test_document_roundtrip():
    from PyQt6.QtWidgets import QGraphicsScene

    def pen(c="#ffff0000", wd=6):
        from PyQt6.QtGui import QPen
        p = QPen(QColor(c)); p.setWidthF(wd); return p

    sc = QGraphicsScene()
    r = _mk_rect(sc, pen(), 0, 0, 120, 60)
    r.setPos(QPointF(10, 20)); r.setRotation(15); r.setTransformOriginPoint(QPointF(60, 30)); r.setScale(1.5)
    e = _EllipseItem(QRectF(0, 0, 80, 80)); e.setPen(pen("#ff0000ff", 4)); e.setBrush(QBrush(Qt.BrushStyle.NoBrush)); e.setPos(QPointF(200, 0)); sc.addItem(e)
    ln = _LineItem(QLineF(0, 0, 100, 50)); ln.setPen(pen("#ff333333", 3)); sc.addItem(ln)
    pp = QPainterPath(QPointF(0, 0)); pp.lineTo(30, 10); pp.cubicTo(40, 40, 60, 40, 80, 10)
    pa = _PathItem(pp); pa.setPen(pen("#ff00aaff", 5)); pa.setPos(QPointF(0, 300)); sc.addItem(pa)
    ar = _ArrowItem(QColor("#ffff9500"), 6, True); ar.set_points(QPointF(120, 30), QPointF(300, 60)); ar._ctrl1 = QPointF(180, -20); ar._ctrl2 = QPointF(260, 120); sc.addItem(ar)
    tx = _TextItem(QColor("#ff000000")); tx.apply_font_size(20); tx.setPlainText("흐름 A\n둘째"); tx.set_bg(QColor(0, 0, 0, 150)); tx.setPos(QPointF(400, 200)); sc.addItem(tx)
    bd = _BadgeItem(7, QColor("#ffff3b30")); bd.setPos(QPointF(500, 500)); bd.setScale(2.0); sc.addItem(bd)

    before = [item_to_dict(it) for it in reversed(sc.items())]
    path = os.path.join(_TMP, "roundtrip.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 7
    after = [item_to_dict(it) for it in reversed(sc2.items())]

    def norm(d):
        out = {}
        for k, v in d.items():
            if isinstance(v, float):
                out[k] = round(v, 4)
            elif isinstance(v, list):
                out[k] = [round(x, 4) if isinstance(x, (int, float)) else x for x in v]
            else:
                out[k] = v
        return out

    for b, a in zip(before, after):
        assert norm(b) == norm(a), (b.get("type"), norm(b), norm(a))


def test_persistent_connection():
    w = CanvasWindow()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    ar = _ArrowItem(QColor("#ffff0000"), 6, True)
    # 고정 부착점: 우측 테두리 (100,30)에 tip 고정, 시작은 자유(500,30)
    ar.set_points(QPointF(500, 30), QPointF(100, 30))
    ar.set_bound(1, r, QPointF(100, 30))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)

    ar.reroute(pin_pred=lambda i: True)
    assert _close(ar.mapToScene(ar._p2), QPointF(100, 30))     # 고정점에 붙음

    r.setPos(QPointF(200, 0)); w._on_scene_changed(None)
    assert _close(ar.mapToScene(ar._p2), QPointF(300, 30))     # 도형 따라 이동(상대점 유지)

    # 반대편(far side) 부착 — 최근접이 아니라 '떨군 자리'를 지킨다(버그 수정 검증)
    r.setPos(QPointF(0, 0))
    ar.set_bound(1, r, QPointF(0, 30))    # 좌측 테두리에 고정
    ar.reroute(pin_pred=lambda i: True)
    assert _close(ar.mapToScene(ar._p2), QPointF(0, 30)), "far-side attach must hold"

    # 곡선 보존: 수동 제어점이 리라우트(도형 무이동)로 사라지지 않음
    ar.set_bound(1, r, QPointF(100, 30)); ar.reroute(pin_pred=lambda i: True)
    ar._ctrl1 = QPointF(200, -50); ar._ctrl2 = QPointF(150, 80)
    ar.reroute(pin_pred=lambda i: True)   # 도형 안 움직였으니 곡선 그대로여야
    assert ar._ctrl1 == QPointF(200, -50) and ar._ctrl2 == QPointF(150, 80), "curve preserved"

    # 강체/늘림 규칙
    r.setSelected(True); ar.setSelected(True)
    assert w._make_pin_pred(ar)(1) is False                    # 둘 다 선택 = 강체
    r.setSelected(False)
    assert w._make_pin_pred(ar)(1) is True                     # 도형만 제자리 = 늘림

    # 왕복: 바인딩 + 고정점 재연결
    path = os.path.join(_TMP, "conn.ecad")
    save_document(w._scene, path)
    from PyQt6.QtWidgets import QGraphicsScene
    sc2 = QGraphicsScene()
    load_document(sc2, path)
    a2 = [it for it in sc2.items() if isinstance(it, _ArrowItem)][0]
    r2 = [it for it in sc2.items() if isinstance(it, _RectItem)][0]
    assert a2._bound(1) is r2 and a2._bound(0) is None
    assert a2._bind_pt(1) == QPointF(100, 30)


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"ALL {len(tests)} TESTS PASSED")


if __name__ == "__main__":
    _run_all()
