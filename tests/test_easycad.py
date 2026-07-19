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
    _RectItem, _EllipseItem, _LineItem, _PathItem, _ArrowItem, _TextItem, _BadgeItem,
    _PolyArrowItem)
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
    assert len(w._tool_buttons) == 9
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


def test_view_controls():
    w = CanvasWindow(); w.show()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    vpos = w._view.mapFromScene(QPointF(100, 30))   # 우측 테두리 근처

    # o-snap 토글: 켜짐이면 스냅, 꺼짐이면 None
    w.snap_enabled = True
    assert w._view._border_snap_at(vpos) is not None
    w.snap_enabled = False
    assert w._view._border_snap_at(vpos) is None
    w.snap_enabled = True

    # 기준 zoom(100%) 복귀
    w._view.scale(2.5, 2.5)
    assert abs(w._view.transform().m11() - 2.5) < 1e-6
    w._zoom_reset()
    assert abs(w._view.transform().m11() - 1.0) < 1e-6

    # 전체 맞춤 — 크래시 없이 변환 적용
    w._zoom_fit()
    assert w._view.transform().m11() > 0


def test_direction_rubber_band():
    # 방향 감지 러버밴드: 왼→오=window(완전포함), 오→왼=crossing(걸침), Shift=추가선택.
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    view = w._view
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)     # 상자에 완전 포함될 도형
    b = _mk_rect(w._scene, w.make_pen(), 450, 0, 100, 60)   # 상자 우측 경계를 걸치는 도형
    tl = view.mapFromScene(QPointF(-10, -10))               # 상자 좌상단(view 좌표)
    br = view.mapFromScene(QPointF(500, 300))               # 상자 우하단(view 좌표)

    # window(왼→오): 완전 포함만 → a만
    view._rb_origin, view._rb_current = tl, br
    assert view._rb_is_window() is True
    view._apply_rubber_selection()
    assert set(w._scene.selectedItems()) == {a}, set(w._scene.selectedItems())

    # crossing(오→왼): 걸치기만 해도 → a, b 둘 다
    view._rb_origin, view._rb_current = br, tl
    assert view._rb_is_window() is False
    view._apply_rubber_selection()
    assert set(w._scene.selectedItems()) == {a, b}, set(w._scene.selectedItems())

    # Shift 추가선택: 기존 선택(b)을 유지한 채 window(a) 결과를 더함
    view._rb_base = [b]
    view._rb_origin, view._rb_current = tl, br
    view._apply_rubber_selection()
    assert set(w._scene.selectedItems()) == {a, b}
    view._rb_base = []

    # 보이는 외형에 딱 맞는(핸들 여유 제외) window 박스도 잡혀야 함(사용자 리포트 회귀).
    # 예전엔 sceneBoundingRect의 핸들 패딩 때문에 보이는 것보다 넓게 그려야만 잡혔다.
    snug_tl = view.mapFromScene(QPointF(-4, -4))
    snug_br = view.mapFromScene(QPointF(104, 64))     # a(0,0,100,60) + 4px 여유
    view._rb_origin, view._rb_current = snug_tl, snug_br
    view._apply_rubber_selection()
    assert a in set(w._scene.selectedItems()), "snug window box must select fully-visible item"
    view._rb_origin = view._rb_current = None


def test_line_arrow_label():
    # 선/화살표 라벨: 자식으로 부착 → 본체 이동·끝점 이동 시 중점 추종, .ecad 왕복 보존.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    ln = _LineItem(QLineF(0, 0, 100, 0)); ln.setPen(w.make_pen())
    ln.setFlags(ln.GraphicsItemFlag.ItemIsSelectable | ln.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ln)

    lbl = ln.ensure_label(); lbl.setPlainText("L1"); ln._sync_label()
    assert lbl.parentItem() is ln                       # 자식으로 부착
    lc = lbl.mapToScene(lbl._content_rect().center())
    assert abs(lc.x() - 50) < 2 and lc.y() < 0          # 중점 x≈50, 선 위쪽

    ln.setPos(QPointF(200, 0))                          # 본체 이동 → 자식 자동 추종
    assert abs(lbl.mapToScene(lbl._content_rect().center()).x() - 250) < 2

    ln.setPos(QPointF(0, 0))
    ln._set_endpoint(1, QPointF(0, 100))                # (0,0)-(0,100), 중점 (0,50)
    lc3 = lbl.mapToScene(lbl._content_rect().center())
    assert abs(lc3.x()) < 2 and abs(lc3.y() - 50) < 30  # 끝점 이동 추종

    ar = _ArrowItem(QColor("#ffff0000"), 6, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 0))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    albl = ar.ensure_label(); albl.setPlainText("A1"); ar._sync_label()
    assert abs(albl.mapToScene(albl._content_rect().center()).x() - 50) < 2
    ar._set_endpoint(1, QPointF(100, 100))              # 중점 (50,50)
    ac2 = albl.mapToScene(albl._content_rect().center())
    assert abs(ac2.x() - 50) < 2 and abs(ac2.y() - 50) < 40

    # .ecad 왕복 — 라벨은 자식이라 최상위 카운트 제외, 텍스트 보존
    path = os.path.join(_TMP, "label.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 2                # 선 + 화살표(라벨 제외)
    tops = [it for it in sc2.items() if it.parentItem() is None]
    lines = [it for it in tops if isinstance(it, _LineItem)]
    arrows = [it for it in tops if isinstance(it, _ArrowItem)]
    assert len(lines) == 1 and lines[0].has_label() and lines[0]._label.toPlainText() == "L1"
    assert len(arrows) == 1 and arrows[0].has_label() and arrows[0]._label.toPlainText() == "A1"


def test_click_outside_finishes_text_edit():
    # 편집 중 텍스트 바깥을 좌클릭하면 편집을 마무리(clearFocus)해야 한다. 실제 포커스 해제는
    # 활성창이 필요해 offscreen에선 관측 불가 → '바깥 클릭이면 clearFocus 호출, 텍스트 위면
    # 미호출'이라는 우리 분기 판정만 검증(실제 종료는 GUI에서 확인).
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select")
    tx = _TextItem(QColor("#ff000000")); tx.setPlainText("hi")
    tx.setFlags(tx.GraphicsItemFlag.ItemIsSelectable | tx.GraphicsItemFlag.ItemIsMovable)
    tx.setPos(QPointF(50, 50)); w._scene.addItem(tx)
    tx.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
    tx.setFocus()
    calls = []
    tx.clearFocus = lambda: calls.append(1)   # 호출 여부 감지(offscreen 무해)

    def press_at(scene_pt):
        vp = w._view.mapFromScene(scene_pt)
        w._view.mousePressEvent(QMouseEvent(
            QEvent.Type.MouseButtonPress, QPointF(vp), QPointF(vp),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
        w._view.mouseReleaseEvent(QMouseEvent(
            QEvent.Type.MouseButtonRelease, QPointF(vp), QPointF(vp),
            Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier))

    press_at(QPointF(55, 55))          # 텍스트 '위' 클릭 = 캐럿 이동, 종료 안 함
    assert not calls, "click inside editing text must not finish edit"
    press_at(QPointF(5000, 5000))      # 텍스트 '바깥' 빈 영역 = 편집 종료 호출
    assert calls, "click outside editing text must finish edit"


def test_straight_arrow():
    # 직선(꺾은선) 화살표: 정점 드래그(끝점 재사용)·waypoint 삽입·라벨·.ecad 왕복.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(0, 0), QPointF(100, 0))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    assert len(sa._endpoints()) == 2                       # 정점 = 끝점 핸들

    sa.insert_vertex(0, QPointF(50, 40))                   # 세그먼트0에 waypoint 삽입
    assert len(sa._pts) == 3 and sa._pts[1] == QPointF(50, 40)
    sa._set_endpoint(2, QPointF(100, 80))                  # 정점 드래그(끝점 machinery 경로)
    assert sa._pts[2] == QPointF(100, 80)

    tip, _ang = sa._tip_and_angle()                        # 화살촉 = 마지막 정점
    assert tip == QPointF(100, 80)

    lbl = sa.ensure_label(); lbl.setPlainText("S1"); sa._sync_label()
    assert lbl.parentItem() is sa

    path = os.path.join(_TMP, "sarrow.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 1                   # 라벨은 자식이라 카운트 제외
    tops = [it for it in sc2.items() if it.parentItem() is None]
    sas = [it for it in tops if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    assert [(p.x(), p.y()) for p in sas[0]._pts] == [(0, 0), (50, 40), (100, 80)]
    assert sas[0].has_label() and sas[0]._label.toPlainText() == "S1"


def test_straight_arrow_waypoint():
    # 세그먼트 위 hover 감지 → 클릭 시 그 자리에 정점(waypoint) 삽입(A2).
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    w = CanvasWindow(); w.show(); w.set_tool("select"); w._zoom_reset()
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(0, 0), QPointF(100, 0))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa); sa.setSelected(True)
    view = w._view

    vp = view.mapFromScene(QPointF(50, 0))          # 세그먼트0 중앙 hover
    hit = view._segment_add_at(vp)
    assert hit is not None and hit[0] is sa and hit[1] == 0

    view._seg_add = hit                              # 클릭 → 정점 삽입 + 드래그
    view.mousePressEvent(QMouseEvent(
        QEvent.Type.MouseButtonPress, QPointF(vp), QPointF(vp),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    view.mouseReleaseEvent(QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(vp), QPointF(vp),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    assert len(sa._pts) == 3
    assert abs(sa._pts[1].x() - 50) < 3 and abs(sa._pts[1].y()) < 3   # 세그먼트 중앙에 삽입

    # 정점 위(끝점) hover는 세그먼트 추가가 아니라 이동 우선 → None
    vtx = view.mapFromScene(QPointF(0, 0))
    assert view._segment_add_at(vtx) is None


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"ALL {len(tests)} TESTS PASSED")


if __name__ == "__main__":
    _run_all()
