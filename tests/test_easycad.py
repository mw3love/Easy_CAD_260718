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
    _PolyArrowItem, _axis_scale_fn, _mirror_fn)
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


def test_ortho_constraint():
    # F8 Ortho 제약 계산: start 기준 0/90°. |dx|≥|dy|=수평(y 고정), 아니면 수직(x 고정).
    from easycad.canvas.annotator_core import _AnnotatorView
    c = _AnnotatorView._constrain
    assert c(QPointF(0, 0), QPointF(100, 20), "ortho") == QPointF(100, 0)   # 수평
    assert c(QPointF(0, 0), QPointF(20, 100), "ortho") == QPointF(0, 100)   # 수직
    assert c(QPointF(50, 50), QPointF(10, 55), "ortho") == QPointF(10, 50)  # 수평(음의 dx)

    # 정점 드래그 ortho: 인접 정점(이전 우선) 기준 0/90° 스냅.
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(0, 0), QPointF(100, 0))
    # 끝점 1 드래그(anchor=pts[0]=(0,0)). (90,30) → |dx|90≥|dy|30 → 수평 → (90,0)
    assert sa._ortho_endpoint(1, QPointF(90, 30)) == QPointF(90, 0)
    # (30,90) → 수직 → x=anchor.x=0 → (0,90)
    assert sa._ortho_endpoint(1, QPointF(30, 90)) == QPointF(0, 90)
    # 끝점 0 드래그(anchor=pts[1]=(100,0)). (70,90) → dx=-30,dy=90 → 수직 → x=100 → (100,90)
    assert sa._ortho_endpoint(0, QPointF(70, 90)) == QPointF(100, 90)


def _draw_helpers(view):
    """뷰 이벤트 시뮬 헬퍼(핸들러 직접 호출 — 클릭 배치·드래그 경로는 아이템 라우팅 불요)."""
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtCore import QEvent
    NO = Qt.KeyboardModifier.NoModifier
    L = Qt.MouseButton.LeftButton
    NB = Qt.MouseButton.NoButton

    def _ev(t, sp, btn, btns):
        vp = view.mapFromScene(sp)
        return QMouseEvent(t, QPointF(vp), QPointF(vp), btn, btns, NO)

    def press(sp):
        view.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, sp, L, L))

    def release(sp):
        view.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, sp, L, NB))

    def click(sp):
        press(sp); release(sp)

    def move(sp):
        view.mouseMoveEvent(_ev(QEvent.Type.MouseMove, sp, NB, NB))

    def drag_move(sp):
        view.mouseMoveEvent(_ev(QEvent.Type.MouseMove, sp, NB, L))

    def dbl(sp):
        press(sp)
        view.mouseDoubleClickEvent(_ev(QEvent.Type.MouseButtonDblClick, sp, L, L))
        release(sp)

    return press, release, click, move, drag_move, dbl


def test_straight_arrow_click_draw():
    # 하이브리드 클릭 배치(직선화살표): 클릭→이동→클릭으로 정점 누적, 더블클릭 마무리, Esc=마지막 점까지 확정.
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    NO = Qt.KeyboardModifier.NoModifier
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    view = w._view
    _p, _r, click, move, _dm, dbl = _draw_helpers(view)

    # 첫 클릭(드래그 없음) = 배치 시작(v0 + 미리보기 정점)
    click(QPointF(0, 0))
    assert view._place is not None and view._place_tool == "sarrow"
    assert len(view._place._pts) == 2

    move(QPointF(100, 0))
    assert _close(view._place._pts[-1], QPointF(100, 0))

    click(QPointF(100, 0))                 # 둘째 클릭 = 정점 확정
    assert len(view._place._pts) == 3

    move(QPointF(80, 100))
    dbl(QPointF(80, 100))                   # 더블클릭 = 마무리
    assert view._place is None
    sas = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    pts = [(round(p.x()), round(p.y())) for p in sas[0]._pts]
    assert pts == [(0, 0), (100, 0), (80, 100)], pts
    assert sas[0].isSelected()

    # [개정] Esc = 취소가 아니라 '지금까지 놓은 점으로 확정'(마지막 커서 추종 미리보기만 버림)
    before = len([it for it in w._scene.items() if isinstance(it, _PolyArrowItem)])
    click(QPointF(300, 300)); move(QPointF(400, 300)); click(QPointF(400, 300))
    move(QPointF(500, 300))                 # 미리보기만 이동(확정 안 함)
    assert view._place is not None
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, NO))
    assert view._place is None
    sas2 = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas2) == before + 1, "Esc는 놓은 점까지 확정해야 함(폐기 아님)"
    committed = [s for s in sas2 if s.isSelected()][0]
    pts = [(round(p.x()), round(p.y())) for p in committed._pts]
    assert pts == [(300, 300), (400, 300)], pts   # 미리보기(500,300)는 버려짐

    # 시작점만 놓고 Esc → 확정할 정점 부족(1개) → 폐기
    before2 = len([it for it in w._scene.items() if isinstance(it, _PolyArrowItem)])
    click(QPointF(700, 700))
    assert view._place is not None
    view.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, NO))
    assert view._place is None
    after2 = len([it for it in w._scene.items() if isinstance(it, _PolyArrowItem)])
    assert after2 == before2, "시작점만 있으면 Esc는 폐기(2정점 미만)"


def test_straight_arrow_click_draw_ortho():
    # F8 Ortho + 클릭 배치: 미리보기 정점이 직전 정점 기준 0/90°로 스냅.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    w.ortho_enabled = True
    view = w._view
    _p, _r, click, move, _dm, _d = _draw_helpers(view)

    click(QPointF(0, 0))
    move(QPointF(100, 20))                  # |dx|>|dy| → 수평 → y=0
    assert _close(view._place._pts[-1], QPointF(100, 0))
    move(QPointF(20, 100))                   # 수직 → x=0
    assert _close(view._place._pts[-1], QPointF(0, 100))
    view._cancel_place()
    assert view._place is None


def test_hybrid_two_click_shapes():
    # 2점 도구(선·네모)를 투클릭으로: 클릭→이동→클릭 = 확정(드래그 안 해도 그려짐).
    w = CanvasWindow(); w.show(); w._zoom_reset()
    view = w._view
    _p, _r, click, move, _dm, _d = _draw_helpers(view)

    # 선: 투클릭
    w.set_tool("line")
    click(QPointF(0, 0))
    assert view._place is not None and view._place_tool == "line"
    move(QPointF(100, 50))
    click(QPointF(100, 50))                  # 둘째 클릭 = 확정
    assert view._place is None
    lines = [it for it in w._scene.items() if isinstance(it, _LineItem)]
    assert len(lines) == 1
    ln = lines[0].line()
    assert _close(ln.p1(), QPointF(0, 0)) and _close(ln.p2(), QPointF(100, 50))
    assert lines[0].isSelected()

    # 네모: 투클릭
    w.set_tool("rect")
    click(QPointF(200, 0)); move(QPointF(320, 80)); click(QPointF(320, 80))
    assert view._place is None
    rects = [it for it in w._scene.items() if isinstance(it, _RectItem)]
    assert len(rects) == 1
    r = rects[0].rect()
    assert abs(r.width() - 120) < 2 and abs(r.height() - 80) < 2, (r.width(), r.height())


def test_hybrid_drag_still_works():
    # 드래그(press-move(버튼)-release, 이동>=임계) = 즉시 확정(기존 동작 보존).
    w = CanvasWindow(); w.show(); w._zoom_reset()
    view = w._view
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)

    # 네모 드래그
    w.set_tool("rect")
    press(QPointF(0, 0)); drag_move(QPointF(120, 80)); release(QPointF(120, 80))
    assert view._place is None and view._drawing is False
    rects = [it for it in w._scene.items() if isinstance(it, _RectItem)]
    assert len(rects) == 1 and rects[0].isSelected()

    # 직선화살 드래그 = 2점 직선(멀티정점 아님)
    w.set_tool("sarrow")
    press(QPointF(0, 200)); drag_move(QPointF(150, 200)); release(QPointF(150, 200))
    assert view._place is None
    sas = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1 and len(sas[0]._pts) == 2
    assert sas[0].isSelected()


def test_straight_arrow_binding():
    # [A3] 직선화살표 끝점을 도형 테두리에 지속 연결 → 도형 이동 시 추종, waypoint는 제외, .ecad 왕복.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    r = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(500, 30), QPointF(100, 30))     # 끝(idx1)을 우측 테두리(100,30)에
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)

    sa.set_bound(1, r, QPointF(100, 30))                  # 끝을 도형 로컬(100,30)에 고정
    assert sa.has_binding()
    sa.reroute(pin_pred=lambda i: True)
    assert _close(sa.mapToScene(sa._pts[1]), QPointF(100, 30))

    r.setPos(QPointF(200, 0)); w._on_scene_changed(None)   # 도형 이동 → 끝점 추종
    assert _close(sa.mapToScene(sa._pts[-1]), QPointF(300, 30))

    r.setSelected(True); sa.setSelected(True)              # 둘 다 선택 = 강체
    assert w._make_pin_pred(sa)(1) is False
    r.setSelected(False)                                   # 도형만 = 늘림
    assert w._make_pin_pred(sa)(1) is True

    # 중간 waypoint 삽입 → 끝 바인딩은 '역할'로 새 끝(idx2)에 유지, 중간(idx1)은 무바인딩
    r.setPos(QPointF(0, 0)); sa.set_bound(1, r, QPointF(100, 30)); sa.reroute(pin_pred=lambda i: True)
    sa.insert_vertex(0, QPointF(300, 100))                 # pts=[(500,30),(300,100),(100,30)]
    assert sa._bound(2) is r and sa._bound(1) is None

    # .ecad 왕복 — 바인딩 보존
    path = os.path.join(_TMP, "sabind.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    load_document(sc2, path)
    a2 = [it for it in sc2.items() if isinstance(it, _PolyArrowItem)][0]
    r2 = [it for it in sc2.items() if isinstance(it, _RectItem)][0]
    last = len(a2._pts) - 1
    assert a2._bound(last) is r2 and a2._bound(0) is None
    assert a2._bind_pt(last) == QPointF(100, 30)


def test_straight_arrow_draw_binds():
    # [A3] 드래그로 그린 직선화살표의 끝이 도형 테두리 근처면 확정 시 스냅+바인딩(그리기-시점 부착).
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    r = _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)   # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)

    press(QPointF(0, 30)); drag_move(QPointF(305, 30)); release(QPointF(305, 30))
    sas = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    sa = sas[0]
    assert sa.has_binding()
    assert _close(sa.mapToScene(sa._pts[-1]), QPointF(300, 30)), sa.mapToScene(sa._pts[-1])
    assert sa._bound(0) is None                             # 시작(0,30)은 테두리에서 멀어 무바인딩

    # o-snap(F3) 꺼짐이면 새로 그려도 바인딩 안 됨
    w.snap_enabled = False
    press(QPointF(0, 130)); drag_move(QPointF(305, 130)); release(QPointF(305, 130))
    sas2 = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    newest = [s for s in sas2 if s is not sa][0]
    assert not newest.has_binding()
    w.snap_enabled = True


def test_straight_arrow_live_snap():
    # [이슈] sarrow 그리는 중 끝점이 도형 테두리에 '라이브 스냅'(마커) + 직전 점 근처 스냅은 무시.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)

    # 시작(0,30) 멀리 → 끝을 테두리 근처(305,30)로 드래그 → 라이브 tip 마커 = 테두리점(300,30)
    press(QPointF(0, 30)); drag_move(QPointF(305, 30))
    assert view._arrow_tip_snap is not None and _close(view._arrow_tip_snap, QPointF(300, 30))
    release(QPointF(305, 30))

    # 직전 점 바로 근처(30px 이내)의 테두리 스냅은 무시 — 겹친 극소 화살표 방지
    press(QPointF(295, 30)); drag_move(QPointF(305, 30))   # 시작이 테두리에 스냅→끝이 그 30px내
    assert view._arrow_tip_snap is None, "직전 점 근처 스냅은 무시돼야(극소 화살표 방지)"
    view._cancel_place() if view._place is not None else release(QPointF(305, 30))


def test_arrow_border_start_gestures():
    # [이슈] sarrow·곡선화살 모두 테두리에서 시작 가능(하이브리드): 드래그도 클릭(투클릭)도.
    w = CanvasWindow(); w.show(); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    press, release, click, move, drag_move, _d = _draw_helpers(view)

    # sarrow: 테두리 근처(305,30)서 press → 드래그 → 시작이 테두리에 스냅·바인딩된 화살표
    w.set_tool("sarrow")
    press(QPointF(305, 30)); drag_move(QPointF(500, 30)); release(QPointF(500, 30))
    sas = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    assert _close(sas[0].mapToScene(sas[0]._pts[0]), QPointF(300, 30))   # 시작 테두리 스냅
    assert sas[0]._bound(0) is not None                                   # 시작 바인딩

    # 곡선화살: 테두리 근처 클릭 → 배치 모드(하이브리드 복원, sarrow와 동일) — 시작 바인딩.
    # 앞서 그린 sarrow 선택 해제 + 그 sarrow와 안 겹치는 상단 테두리(y=0)에서 시작.
    w.set_tool("arrow")
    w._scene.clearSelection()
    click(QPointF(250, 3))                                                # 네모 상단 테두리 근처
    assert view._place is not None and view._place_tool == "arrow"
    assert view._place._bound(0) is not None                             # 시작이 테두리에 바인딩
    view._cancel_place()

    # 곡선화살: 테두리서 드래그도 정상 생성
    n0 = len([it for it in w._scene.items() if isinstance(it, _ArrowItem)])
    press(QPointF(250, 3)); drag_move(QPointF(250, 300)); release(QPointF(250, 300))
    assert len([it for it in w._scene.items() if isinstance(it, _ArrowItem)]) == n0 + 1


def test_sarrow_click_near_border_no_tiny_arrow():
    # [버그] 테두리 근처 '가만히 클릭'은 시작 스냅 점프를 드래그로 오인해 극소 화살표를 만들면 안 됨.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    _p, _r, click, _m, _dm, _d = _draw_helpers(view)

    click(QPointF(308, 30))          # 테두리(300,30)서 8px 떨어진 곳을 가만히 클릭
    assert view._place is not None, "가만히 클릭은 배치 모드로 들어가야(드래그 오인 금지)"
    pts = [(round(p.x()), round(p.y())) for p in view._place._pts]
    assert pts == [(300, 30), (300, 30)], pts   # 시작이 테두리 스냅, 둘 다 같은 점(배치 대기)
    view._cancel_place()


def test_sarrow_ortho_preview_matches_click():
    # [버그] F8 Ortho에서 미리보기(move)와 클릭(_place_click)이 같은 좌표여야(전엔 더블클릭 때만 수평).
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    w.ortho_enabled = True
    view = w._view
    _p, _r, click, move, _dm, _d = _draw_helpers(view)

    click(QPointF(0, 30))            # 시작
    move(QPointF(200, 50))           # dx=200>dy=20 → 수평 → y=30
    assert _close(view._place._pts[-1], QPointF(200, 30)), "미리보기가 수평이어야"
    click(QPointF(200, 50))          # 클릭 배치 — 미리보기와 같은 (200,30)
    assert _close(view._place._pts[-2], QPointF(200, 30)), "클릭 배치가 미리보기와 일치해야"
    view._cancel_place()


def test_sarrow_ortho_snaps_to_border():
    # [버그] F8 Ortho에서도 끝이 도형 테두리 근처면 스냅+마커(수직 모서리면 수평 유지).
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    w.ortho_enabled = True
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)     # 우측 테두리 x=300, y[0..60]
    view = w._view
    _p, _r, click, move, _dm, _d = _draw_helpers(view)

    click(QPointF(0, 30))            # 시작(테두리와 같은 y=30)
    move(QPointF(305, 40))           # 우측 테두리 근처. ortho→y=30, 근처면 (300,30)로 스냅
    assert view._arrow_tip_snap is not None and _close(view._arrow_tip_snap, QPointF(300, 30))
    assert _close(view._place._pts[-1], QPointF(300, 30)), "수평(y=30) 유지 + 테두리 스냅"
    view._cancel_place()


def test_sarrow_snap_click_auto_finishes():
    # [개정] 클릭 배치 중 도형 테두리에 스냅된 클릭 = 종점 → 더블클릭 없이 자동 마무리.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 200, 0, 100, 60)      # 우측 테두리 x=300, 중앙 y=30
    view = w._view
    _p, _r, click, move, _dm, _d = _draw_helpers(view)

    click(QPointF(0, 30))                 # 시작(테두리에서 멂) → 배치 모드
    assert view._place is not None
    move(QPointF(305, 30)); click(QPointF(305, 30))   # 테두리 근처 클릭 = 스냅 → 자동 마무리
    assert view._place is None, "스냅점 클릭은 더블클릭 없이 마무리돼야"
    sas = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    sa = sas[0]
    assert _close(sa.mapToScene(sa._pts[-1]), QPointF(300, 30)), sa.mapToScene(sa._pts[-1])
    assert sa._bound(len(sa._pts) - 1) is not None   # 종점이 도형에 바인딩

    # 시작점이 테두리 근처여도(_enter_click_place 경로) 조기 종료되지 않는다.
    w2 = CanvasWindow(); w2.show(); w2.set_tool("sarrow"); w2._zoom_reset()
    _mk_rect(w2._scene, w2.make_pen(), 200, 0, 100, 60)
    v2 = w2._view
    _p2, _r2, click2, _m2, _dm2, _d2 = _draw_helpers(v2)
    click2(QPointF(305, 30))              # 시작이 테두리 스냅
    assert v2._place is not None, "시작 스냅은 마무리 트리거가 아님(배치 계속)"
    v2._cancel_place()


def test_ortho_elbow_pure():
    # [Stage1] _ortho_elbow / _dedup_pts 순수함수 — 법선 우세축으로 엘보 정점 생성 + 퇴화 접힘.
    from easycad.canvas.annotator_core import _ortho_elbow, _dedup_pts
    P = QPointF
    s, e = P(100, 30), P(300, 230)
    # 양끝 수평 법선 → H-V-H (중간 x=200)
    mids = _ortho_elbow(s, e, P(1, 0), P(-1, 0))
    assert [(round(m.x()), round(m.y())) for m in mids] == [(200, 30), (200, 230)]
    # 양끝 수직 법선 → V-H-V (중간 y=130)
    mids = _ortho_elbow(s, e, P(0, 1), P(0, -1))
    assert [(round(m.x()), round(m.y())) for m in mids] == [(100, 130), (300, 130)]
    # 혼합(시작 수평·끝 수직) → L자 모서리 하나 = (e.x, s.y)
    mids = _ortho_elbow(s, e, P(1, 0), P(0, -1))
    assert [(round(m.x()), round(m.y())) for m in mids] == [(300, 30)]
    # 수평 정렬(같은 y) + 양끝 수평 → 엘보가 직선으로 접힘(공선 제거)
    full = _dedup_pts([P(100, 30)] + _ortho_elbow(P(100, 30), P(300, 30), P(1, 0), P(-1, 0)) + [P(300, 30)])
    assert [(round(m.x()), round(m.y())) for m in full] == [(100, 30), (300, 30)]


def test_sarrow_auto_elbow_route():
    # [Stage1] 양끝 바인딩 직선화살 → 직교 엘보 자동 생성 / 도형 이동 시 엘보 재계산.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)       # 우측 테두리 (100,30), 법선 +x
    b = _mk_rect(w._scene, w.make_pen(), 300, 200, 100, 60)   # 좌측 테두리 (300,230), 법선 -x
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(100, 30), QPointF(300, 230))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(100, 30))
    sa.set_bound(1, b, QPointF(300, 230))
    sa._auto_route = True
    assert sa.build_elbow()
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert len(sp) == 4, sp
    assert _close(sp[0], QPointF(100, 30)) and _close(sp[-1], QPointF(300, 230))
    assert _close(sp[1], QPointF(200, 30)) and _close(sp[2], QPointF(200, 230))   # H-V-H, mx=200

    # 도형 이동 → reroute가 끝점 추종 + 엘보 재계산
    b.setPos(QPointF(0, 100))            # b 좌측 테두리 → 씬 (300,330)
    w._on_scene_changed(None)
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert _close(sp[-1], QPointF(300, 330)), sp[-1]
    assert _close(sp[1], QPointF(200, 30)) and _close(sp[2], QPointF(200, 330)), sp


def test_sarrow_manual_edit_disables_auto():
    # [Stage1] 수동 정점 조작(핸들 드래그 시작·waypoint 삽입·삭제) → 자동 라우팅 해제, 경로 동결.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 300, 200, 100, 60)
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(100, 30), QPointF(300, 230))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(100, 30)); sa.set_bound(1, b, QPointF(300, 230))
    sa._auto_route = True; sa.build_elbow()

    # (1) 정점 핸들 드래그 시작 훅 → 해제
    sa._on_endpoint_drag_start(1)
    assert sa._auto_route is False
    frozen = [(round(p.x()), round(p.y())) for p in sa._pts]
    b.setPos(QPointF(0, 100)); w._on_scene_changed(None)   # 도형 이동해도 엘보 재계산 안 함
    mids = [(round(sa._pts[i].x()), round(sa._pts[i].y())) for i in (1, 2)]
    assert mids == frozen[1:3], "해제 후 중간 정점은 동결(재계산 금지)"

    # (2) waypoint 삽입도 해제 트리거
    sa2 = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa2.set_points(QPointF(0, 0), QPointF(400, 400)); w._scene.addItem(sa2)
    sa2._auto_route = True
    sa2.insert_vertex(0, QPointF(200, 0))
    assert sa2._auto_route is False


def test_sarrow_draw_between_shapes_auto_routes():
    # [Stage1] 드래그로 양끝을 도형 테두리에 붙이면 확정 시 자동 직교 엘보로 전환.
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)          # 우측 (100,30)
    _mk_rect(w._scene, w.make_pen(), 300, 200, 100, 60)      # 좌측 (300,230)
    view = w._view
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)
    press(QPointF(100, 30)); drag_move(QPointF(300, 230)); release(QPointF(300, 230))
    sa = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)][0]
    last = len(sa._pts) - 1
    assert sa._bound(0) is not None and sa._bound(last) is not None
    assert sa._auto_route is True
    assert len(sa._pts) == 4, [(round(p.x()), round(p.y())) for p in sa._pts]

    # .ecad 왕복 — auto_route 상태 보존
    from PyQt6.QtWidgets import QGraphicsScene
    path = os.path.join(_TMP, "sa_autoroute.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene(); load_document(sc2, path)
    a2 = [it for it in sc2.items() if isinstance(it, _PolyArrowItem)][0]
    assert a2._auto_route is True


def test_route_ortho_pure():
    # [Stage2] _route_ortho 순수함수 — 장애물 없으면 Stage1 그대로, 있으면 관통 없는 경로 선택.
    from easycad.canvas.annotator_core import _route_ortho, _ortho_elbow, _path_hits_rects
    P = QPointF
    s, e = P(100, 30), P(300, 230)
    ns, ne = P(1, 0), P(-1, 0)   # 양끝 수평 → Stage1은 H-V-H(x=200)
    # (1) 장애물 없음 → Stage1과 동일
    assert _route_ortho(s, e, ns, ne, [], 12.0) == _ortho_elbow(s, e, ns, ne)
    # (2) 수직 채널(x=200) 위에 장애물 → 우회 경로가 그 사각형을 관통하지 않음
    obs = QRectF(180, 110, 40, 40)   # x180..220, y110..150 — 채널 x=200 가로막음
    mids = _route_ortho(s, e, ns, ne, [obs], 12.0)
    assert not _path_hits_rects([s] + mids + [e], [obs]), mids
    # 우회는 Stage1과 달라야 함(관통했으므로 대체됨)
    assert mids != _ortho_elbow(s, e, ns, ne)
    # (3) 장애물이 경로에서 비켜 있으면(멀리) Stage1 유지
    far = QRectF(1000, 1000, 40, 40)
    assert _route_ortho(s, e, ns, ne, [far], 12.0) == _ortho_elbow(s, e, ns, ne)


def test_sarrow_routes_around_obstacle():
    # [Stage2] 양끝 도형 사이 세 번째 도형이 경로를 가로막으면 우회 라우팅 / 장애물 이동 시 재라우팅 /
    #          양끝 바인딩 도형은 장애물에서 제외.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)       # 우측 (100,30), 법선 +x
    b = _mk_rect(w._scene, w.make_pen(), 300, 200, 100, 60)   # 좌측 (300,230), 법선 -x
    c = _mk_rect(w._scene, w.make_pen(), 700, 700, 60, 60)    # 처음엔 경로 밖(멀리)
    sa = _PolyArrowItem(QColor("#ff0000ff"), 6, True)
    sa.set_points(QPointF(100, 30), QPointF(300, 230))
    sa.setFlags(sa.GraphicsItemFlag.ItemIsSelectable | sa.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sa)
    sa.set_bound(0, a, QPointF(100, 30)); sa.set_bound(1, b, QPointF(300, 230))
    sa._auto_route = True

    # 바인딩 도형(a,b)은 장애물에서 제외 — c만 장애물
    obst = sa._obstacle_rects()
    assert len(obst) == 1, obst

    # (1) 장애물이 경로 밖 → Stage1 H-V-H(x=200) 그대로
    sa.build_elbow()
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert len(sp) == 4 and _close(sp[1], QPointF(200, 30)) and _close(sp[2], QPointF(200, 230)), sp

    # (2) 장애물을 수직 채널(x=200) 위로 이동 → reroute가 우회 경로로 재계산 → c 관통 안 함
    c.setPos(QPointF(-520, -580))    # 700-520=180 → x180..240, 700-580=120 → y120..180 (채널 가로막음)
    w._on_scene_changed(None)
    from easycad.canvas.annotator_core import _path_hits_rects
    c_rect = c.mapRectToScene(c.rect())
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert _close(sp[0], QPointF(100, 30)) and _close(sp[-1], QPointF(300, 230)), sp
    assert not _path_hits_rects(sp, [c_rect]), (sp, c_rect)
    assert len(sp) > 2   # 여전히 직교 엘보(≥1 모서리)

    # (3) 장애물을 다시 치우면 Stage1로 복귀(우회 해제) — 무변경 가드가 되먹임 없이 안정
    c.setPos(QPointF(0, 0))          # 다시 (700,700) 멀리
    w._on_scene_changed(None)
    sp = [sa.mapToScene(p) for p in sa._pts]
    assert len(sp) == 4 and _close(sp[1], QPointF(200, 30)) and _close(sp[2], QPointF(200, 230)), sp


def _rot(p, c, deg):
    import math
    r = math.radians(deg); cs, sn = math.cos(r), math.sin(r)
    dx, dy = p.x() - c.x(), p.y() - c.y()
    return QPointF(c.x() + dx * cs - dy * sn, c.y() + dx * sn + dy * cs)


def test_group_transform_availability():
    # [Stage1] 그룹 오버레이는 최상위 2개 이상 선택 & select/손 도구에서만 활성.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 300, 0, 100, 60)
    g = w._view._group
    assert g.bbox() is None and not g.available()      # 0개
    a.setSelected(True)
    assert g.bbox() is None and not g.available()      # 1개 — 그룹 아님(개별 핸들)
    b.setSelected(True)
    assert g.bbox() is not None and g.available()      # 2개 — 그룹 활성
    # 그리기 도구로 바꾸면 그룹 조작 비활성(오버레이 숨김)
    w.set_tool("rect")
    assert not g.available()
    w.set_tool("select")
    # 개별 핸들은 그룹 중엔 꺼진다(그룹 오버레이가 대신 변형)
    assert a._group_active() and not a._handle_active()
    # 회전 핸들 히트테스트가 상단 회전점을 잡는다
    bb = g.bbox()
    assert g.handle_at(g._rot_center(bb))[0] == "rotate"
    assert g.handle_at(bb.topLeft())[0] == "scale"


def test_group_rotate():
    # [Stage1] 그룹 중심 기준 90° 회전 — 각 아이템의 씬 중심이 그룹 중심 둘레로 회전.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)      # pos (0,0)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 0))
    a.setSelected(True); b.setSelected(True)
    g = w._view._group
    c = g.bbox().center()
    ca0 = a.mapToScene(a._content_rect().center())
    cb0 = b.mapToScene(b._content_rect().center())
    g.begin(("rotate", c), QPointF(c.x() + 50, c.y()))       # start_angle = 0°
    g.update_to(QPointF(c.x(), c.y() + 50))                  # → +90° (y-down)
    assert abs(a.rotation() - 90) < 1e-6 and abs(b.rotation() - 90) < 1e-6
    assert _close(a.mapToScene(a._content_rect().center()), _rot(ca0, c, 90))
    assert _close(b.mapToScene(b._content_rect().center()), _rot(cb0, c, 90))
    g.end()
    # undo → 원상복구(위치·회전 모두)
    w.undo()
    assert abs(a.rotation()) < 1e-6 and _close(a.mapToScene(a._content_rect().center()), ca0)
    assert _close(b.mapToScene(b._content_rect().center()), cb0)


def test_group_scale():
    # [Stage1] 대각 모서리(anchor) 기준 균일 ×2 — 씬 위치는 anchor 기준 2배, 아이템 scale도 2배.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 200))
    a.setSelected(True); b.setSelected(True)
    g = w._view._group
    bb = g.bbox()
    anchor, corner = bb.topLeft(), bb.bottomRight()
    pa0 = a.mapToScene(a._content_rect().center())
    pb0 = b.mapToScene(b._content_rect().center())
    g.begin(("scale", anchor, corner), corner)
    g.update_to(QPointF(2 * corner.x() - anchor.x(), 2 * corner.y() - anchor.y()))  # f=2
    assert abs(a.scale() - 2.0) < 1e-6 and abs(b.scale() - 2.0) < 1e-6
    exp_a = QPointF(anchor.x() + 2 * (pa0.x() - anchor.x()), anchor.y() + 2 * (pa0.y() - anchor.y()))
    exp_b = QPointF(anchor.x() + 2 * (pb0.x() - anchor.x()), anchor.y() + 2 * (pb0.y() - anchor.y()))
    assert _close(a.mapToScene(a._content_rect().center()), exp_a)
    assert _close(b.mapToScene(b._content_rect().center()), exp_b)
    g.end()
    w.undo()
    assert abs(a.scale() - 1.0) < 1e-6 and _close(a.mapToScene(a._content_rect().center()), pa0)


def test_group_rotate_keeps_binding():
    # [Stage1] 바인딩 화살표+양끝 도형을 함께 그룹 회전 → 화살표가 강체로 따라가 부착 유지.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)          # 우측 (100,30)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 200))  # 좌측 (300,230)
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(100, 30), QPointF(300, 230))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(100, 30)))
    ar.set_bound(1, b, b.mapFromScene(QPointF(300, 230)))
    assert ar.has_binding()
    ep0 = [ar.mapToScene(p) for p in ar._endpoints()]
    a.setSelected(True); b.setSelected(True); ar.setSelected(True)
    g = w._view._group
    c = g.bbox().center()
    g.begin(("rotate", c), QPointF(c.x() + 50, c.y()))
    g.update_to(QPointF(c.x(), c.y() + 50))                      # +90°
    g.end()
    w._on_scene_changed(None)   # 리라우트 — 전부 선택(rigid)이라 끝점 안 흔들림
    ep1 = [ar.mapToScene(p) for p in ar._endpoints()]
    # 끝점이 회전된 원위치에 그대로(강체) — 도형 테두리에 붙은 채 유지
    assert _close(ep1[0], _rot(ep0[0], c, 90)), (ep1[0], _rot(ep0[0], c, 90))
    assert _close(ep1[1], _rot(ep0[1], c, 90)), (ep1[1], _rot(ep0[1], c, 90))
    assert ar.has_binding()


def test_rebake_scene_pure():
    # [Stage2] 씬공간 함수로 기하를 다시 굽는 핵심 수학 — 회전=0·스케일=1이면 정확.
    w = CanvasWindow()
    sc, pen = w._scene, w.make_pen()
    # 네모: x축 ×2(anchor=0) → 폭 2배, 좌변 고정. 미러 x(anchor=0) → 좌우 반전.
    a = _mk_rect(sc, pen, 0, 0, 100, 60)
    a.rebake_scene(_axis_scale_fn("x", 0.0, 2.0))
    assert _close(a.rect().topLeft(), QPointF(0, 0)) and abs(a.rect().width() - 200) < 1e-6
    a2 = _mk_rect(sc, pen, 0, 0, 100, 60)
    a2.rebake_scene(_mirror_fn("x", 0.0))
    assert _close(a2.rect().topLeft(), QPointF(-100, 0)) and abs(a2.rect().width() - 100) < 1e-6
    # 타원(네모와 동일 경로)
    el = _EllipseItem(QRectF(0, 0, 100, 60)); sc.addItem(el)
    el.rebake_scene(_axis_scale_fn("y", 0.0, 3.0))
    assert abs(el.rect().height() - 180) < 1e-6
    # 선
    ln = _LineItem(QLineF(0, 0, 100, 0)); sc.addItem(ln)
    ln.rebake_scene(_axis_scale_fn("x", 0.0, 2.0))
    assert _close(ln.line().p2(), QPointF(200, 0))
    # 곡선 화살표(끝점+제어점 반전)
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 0)); sc.addItem(ar)
    ar.rebake_scene(_mirror_fn("x", 0.0))
    assert _close(ar._p1, QPointF(0, 0)) and _close(ar._p2, QPointF(-100, 0))
    # 직선 화살표(정점 스케일) — 미러/왜곡은 수동 폴리라인으로
    pa = _PolyArrowItem(QColor("#ffff9500"), 6, True)
    pa.set_points(QPointF(0, 0), QPointF(0, 100)); pa._auto_route = True; sc.addItem(pa)
    pa.rebake_scene(_axis_scale_fn("y", 0.0, 2.0))
    assert _close(pa._pts[1], QPointF(0, 200)) and pa._auto_route is False
    # 텍스트(스칼라 폴백 — 내용 중심만 반사, 글자 크기·방향 유지)
    t = _TextItem(QColor("black")); t.setPlainText("hi"); t.setPos(QPointF(10, 10)); sc.addItem(t)
    c0 = t.mapToScene(t._content_rect().center())
    t.rebake_scene(_mirror_fn("x", 0.0))
    c1 = t.mapToScene(t._content_rect().center())
    assert _close(c1, QPointF(-c0.x(), c0.y()))


def test_group_nonuniform_scale():
    # [Stage2] 변 중점 핸들 = 1축 비균일 스케일. 오른 변 핸들 잡아 x ×2 → 각 네모 폭 2배.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(200, 0))
    a.setSelected(True); b.setSelected(True)
    g = w._view._group
    bb = g.bbox()
    right_pt, axis, anchor_val = g._edges(bb)[1]   # 우측 변
    assert axis == "x"
    hit = g.handle_at(right_pt)
    assert hit[0] == "scale_axis" and hit[1] == "x"
    wa0, wb0 = a.rect().width(), b.rect().width()
    ha0 = a.rect().height()
    g.begin(hit, right_pt)
    g.update_to(QPointF(anchor_val + 2 * (right_pt.x() - anchor_val), right_pt.y()))  # f=2
    g.end()
    assert abs(a.rect().width() - 2 * wa0) < 1e-6 and abs(b.rect().width() - 2 * wb0) < 1e-6
    assert abs(a.rect().height() - ha0) < 1e-6   # y축은 불변(1축)
    w.undo()
    assert abs(a.rect().width() - wa0) < 1e-6 and abs(b.rect().width() - wb0) < 1e-6


def test_group_nonuniform_scale_keeps_binding():
    # [Stage2] 바인딩 화살표+양끝 도형을 함께 1축 스케일 → 부착점도 같이 스케일돼 연결 유지.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 0))
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(100, 30), QPointF(300, 30))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(100, 30)))
    ar.set_bound(1, b, b.mapFromScene(QPointF(300, 30)))
    a.setSelected(True); b.setSelected(True); ar.setSelected(True)
    g = w._view._group
    bb = g.bbox()
    right_pt, _axis, anchor_val = g._edges(bb)[1]
    g.begin(g.handle_at(right_pt), right_pt)
    g.update_to(QPointF(anchor_val + 2 * (right_pt.x() - anchor_val), right_pt.y()))
    g.end()
    assert ar.has_binding()
    # 끝점이 각 도형의 (스케일된) 부착점에 그대로 붙어 있다.
    assert _close(ar.mapToScene(ar._endpoints()[0]), a.mapToScene(ar._bind1_pt))
    assert _close(ar.mapToScene(ar._endpoints()[1]), b.mapToScene(ar._bind2_pt))
    w.undo()
    assert abs(a.rect().width() - 100) < 1e-6 and ar.has_binding()


def test_mirror_horizontal():
    # [Stage2] 좌우 미러 — 각 아이템 씬 중심이 그룹 bbox 중심 기준 x반사. undo로 원복.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 0))
    a.setSelected(True); b.setSelected(True)
    cx = w._view._group.bbox().center().x()
    ca0 = a.mapToScene(a._content_rect().center())
    cb0 = b.mapToScene(b._content_rect().center())
    w._view.mirror_selection("x")
    assert _close(a.mapToScene(a._content_rect().center()), QPointF(2 * cx - ca0.x(), ca0.y()))
    assert _close(b.mapToScene(b._content_rect().center()), QPointF(2 * cx - cb0.x(), cb0.y()))
    w.undo()
    assert _close(a.mapToScene(a._content_rect().center()), ca0)
    assert _close(b.mapToScene(b._content_rect().center()), cb0)


def test_mirror_keeps_binding():
    # [Stage2] 바인딩 화살표+양끝 도형을 함께 미러 → 부착점도 반사돼 연결·화살표 유지.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(300, 0))
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(100, 30), QPointF(300, 30))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(100, 30)))
    ar.set_bound(1, b, b.mapFromScene(QPointF(300, 30)))
    a.setSelected(True); b.setSelected(True); ar.setSelected(True)
    w._view.mirror_selection("x")
    assert ar.has_binding()
    assert _close(ar.mapToScene(ar._endpoints()[0]), a.mapToScene(ar._bind1_pt))
    assert _close(ar.mapToScene(ar._endpoints()[1]), b.mapToScene(ar._bind2_pt))
    w.undo()
    assert _close(ar.mapToScene(ar._endpoints()[0]), QPointF(100, 30))


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"ALL {len(tests)} TESTS PASSED")


if __name__ == "__main__":
    _run_all()
