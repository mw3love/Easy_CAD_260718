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
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPixmap

from easycad.canvas.host import CanvasWindow
from easycad.canvas.annotator_core import (
    _RectItem, _EllipseItem, _LineItem, _PathItem, _ArrowItem, _TextItem, _BadgeItem,
    _PolyArrowItem, _SymbolItem, _ImageItem, _TitleBlockItem, _TableItem, _SYMBOL_KINDS,
    _nearest_border, _shape_ports, _axis_scale_fn, _mirror_fn)
from easycad.fileio.pdf_export import export_pdf, _selection_rect
from easycad.fileio.document import save_document, load_document, item_to_dict
from easycad.fileio.dxf_export import export_dxf
from easycad.fileio.sketch_build import Sketch, _argb

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
    # 상단 툴바 = 그리기 도구 7종(네모·원은 왼쪽 「도형」 팔레트로 이관).
    assert len(w._tool_buttons) == 7
    assert "rect" not in w._tool_buttons and "ellipse" not in w._tool_buttons
    # 왼쪽 팔레트: 기본(네모·원) + 순서도 6종.
    assert set(w._shape_tool_buttons) == {"rect", "ellipse"}
    assert len(w._sym_buttons) == 6
    r = w._scene.sceneRect()
    assert r.width() > 90000 and r.height() > 90000
    m0 = w._view.transform().m11()
    w._on_wheel_zoom(120)
    assert w._view.transform().m11() > m0


def test_shape_palette_arms_tool():
    # 팔레트 네모 버튼 클릭 → rect 도구 무장 + 버튼 체크 동기화. 단축키 경로도 유지.
    w = CanvasWindow()
    w._shape_tool_buttons["rect"].click()
    assert w.current_tool == "rect" and w._shape_tool_buttons["rect"].isChecked()
    w.set_tool("select")
    assert not w._shape_tool_buttons["rect"].isChecked()
    # 심볼 무장 시 기본 버튼은 해제 유지
    w.set_tool("sym:decision")
    assert not w._shape_tool_buttons["rect"].isChecked()
    assert w._sym_buttons["decision"].isChecked()


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


def test_route_ortho_astar_dense():
    # [Stage2 승격] Hanan 그리드 A* — 엇갈린 장애물 벽(단순 후보로는 못 뚫는 밀집 배치)에서도
    #   관통 0 우회로 보장. 직교성·끝점 보존·실제 우회(Stage1 관통) 함께 검증.
    from easycad.canvas.annotator_core import _route_ortho, _ortho_elbow, _path_hits_rects
    P = QPointF
    c = 12.0
    s, e = P(0, 0), P(300, 0)
    ns, ne = P(1, 0), P(-1, 0)          # 양끝 수평 → Stage1은 y=0 직선(같은 y)
    # y=0 선을 엇갈려 막는 세 기둥 — 좁은 세로 틈으로만 통과 가능(밀집).
    obs = [QRectF(80, -50, 40, 60),     # x80..120,  y-50..10
           QRectF(160, -10, 40, 60),    # x160..200, y-10..50
           QRectF(240, -50, 40, 60)]    # x240..280, y-50..10
    infl = [r.adjusted(-c, -c, c, c) for r in obs]

    # 전제: Stage1 직선은 세 기둥을 관통한다(우회가 실제로 필요한 밀집 상황).
    pref = _ortho_elbow(s, e, ns, ne)
    assert _path_hits_rects([s] + pref + [e], infl), "테스트 전제: Stage1이 관통해야 함"

    mids = _route_ortho(s, e, ns, ne, obs, c)
    full = [s] + mids + [e]
    # (a) 관통 0 — 팽창 장애물에도 안 걸림(핵심 보장)
    assert not _path_hits_rects(full, infl), (mids, "관통 발생")
    # (b) 원본 장애물에도 당연히 관통 0
    assert not _path_hits_rects(full, obs), mids
    # (c) 전 구간 직교(수평 또는 수직)
    for a, b in zip(full, full[1:]):
        assert abs(a.x() - b.x()) < 1e-6 or abs(a.y() - b.y()) < 1e-6, (a, b)
    # (d) 끝점 보존
    assert _close(full[0], s) and _close(full[-1], e), full
    # (e) 실제로 우회했다(Stage1과 다름)
    assert mids != pref


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


def _box_drag(item, kind, key, lp, host):
    """[2c] 박스 리사이즈 한 번 시뮬레이트(press→move→release) + geom undo 커밋."""
    item._begin_box_geom()
    item._box_resize = (kind, key)
    item._apply_box_resize(lp)
    snap = item._box_snap
    item._box_resize = None
    item._box_snap = None
    item._box_bound = None
    item._box_orig_rect = None
    if snap:
        host.push_undo_geom(snap)


def test_box_handles_gate():
    # [2c] 네모·원만 박스 8핸들, 텍스트·번호는 기존 단일 핸들.
    w = CanvasWindow()
    assert _mk_rect(w._scene, w.make_pen(), 0, 0, 50, 50)._box_handles()
    el = _EllipseItem(QRectF(0, 0, 50, 50)); w._scene.addItem(el)
    assert el._box_handles()
    t = _TextItem(QColor("black")); w._scene.addItem(t)
    assert not t._box_handles()
    b = _BadgeItem(1, QColor("black")); w._scene.addItem(b)
    assert not b._box_handles()


def test_box_corner_resize():
    # [2c] 꼭짓점 = 2D 자유 리사이즈, 반대 꼭짓점 고정.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    _box_drag(a, "corner", 2, QPointF(150, 90), w)   # 우하단(BR) → (150,90), 좌상단 고정
    assert a.rect() == QRectF(0, 0, 150, 90)
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60)
    _box_drag(a, "corner", 0, QPointF(-20, -10), w)  # 좌상단(TL) → (-20,-10), 우하단(100,60) 고정
    assert a.rect() == QRectF(-20, -10, 120, 70)
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60)


def test_box_edge_resize():
    # [2c] 변 = 1축만. 우변=가로만(세로 불변), 상변=세로만(가로 불변).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    _box_drag(a, "edge", "r", QPointF(200, 999), w)  # y는 무시돼야 함
    assert a.rect() == QRectF(0, 0, 200, 60)
    w.undo()
    _box_drag(a, "edge", "t", QPointF(999, -40), w)  # x는 무시돼야 함
    assert a.rect() == QRectF(0, -40, 100, 100)
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60)


def test_box_resize_keeps_binding():
    # [2c] 네모에 붙은 화살표 — 리사이즈해도 상대 테두리 위치 유지(우변 중점→새 우변 중점).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); b.setPos(QPointF(400, 0))
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(100, 30), QPointF(400, 30))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(100, 30)))   # a 우변 중점
    ar.set_bound(1, b, b.mapFromScene(QPointF(400, 30)))
    _box_drag(a, "edge", "r", QPointF(200, 30), w)         # a 우변 100→200
    assert a.rect() == QRectF(0, 0, 200, 60)
    # 부착점이 새 우변 중점(200,30)으로 재매핑되고 끝점이 따라옴.
    assert _close(a.mapToScene(ar._bind1_pt), QPointF(200, 30))
    assert _close(ar.mapToScene(ar._endpoints()[0]), QPointF(200, 30))
    assert _close(ar.mapToScene(ar._endpoints()[1]), QPointF(400, 30))   # 반대끝 불변
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60) and ar.has_binding()


def test_box_handle_cursor():
    # [2c] 호버 커서 매핑 — 꼭짓점=대각, 변=가로/세로, 좌상단 회전.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    corners = dict((i, r.center()) for i, r in a._box_corner_rects())
    assert a._box_handle_cursor(corners[0]) == Qt.CursorShape.SizeFDiagCursor   # TL ↖↘
    assert a._box_handle_cursor(corners[1]) == Qt.CursorShape.SizeBDiagCursor   # TR ↗↙
    edges = dict((k, r.center()) for k, r in a._box_edge_rects())
    assert a._box_handle_cursor(edges["r"]) == Qt.CursorShape.SizeHorCursor
    assert a._box_handle_cursor(edges["t"]) == Qt.CursorShape.SizeVerCursor
    assert a._box_handle_cursor(a._box_rot_rect().center()) == "rotate"


def test_qc_dots_geometry():
    # [2d] 선택된 네모는 상하좌우 외부 도트 4개(테두리 바깥).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    dots = dict((k, r) for k, r in a._qc_dot_rects())
    assert set(dots) == {"t", "r", "b", "l"}
    assert dots["r"].center().x() > a.rect().right()      # 우측 도트는 우변 바깥
    assert dots["l"].center().x() < a.rect().left()
    assert dots["t"].center().y() < a.rect().top()
    assert dots["b"].center().y() > a.rect().bottom()


def test_qc_create_default():
    # [2d] 클릭(기본 배치) — 우측 도트 → 우측에 동일도형 복제 + 양끝 바인딩 연결 화살표.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    dup, arrow = w._view._qc_create(a, "r", None)
    sr = a.mapToScene(a.rect()).boundingRect()
    dsr = dup.mapToScene(dup.rect()).boundingRect()
    assert abs(dsr.left() - (sr.right() + 40)) < 1e-6     # 간격 40
    assert abs(dsr.center().y() - sr.center().y()) < 1e-6 # 같은 축 정렬
    assert isinstance(dup, _RectItem) and abs(dup.rect().width() - 100) < 1e-6
    assert arrow.has_binding() and arrow._bind_start is a and arrow._bind_end is dup
    assert _close(arrow.mapToScene(arrow._pts[0]), QPointF(100, 30))   # 원본 우변 중점
    assert _close(arrow.mapToScene(arrow._pts[-1]), QPointF(dsr.left(), 30))
    assert dup.isSelected() and not a.isSelected()        # 새 도형 선택
    w.undo()                                              # 한 번에 둘 다 제거
    assert dup.scene() is None and arrow.scene() is None


def test_qc_create_drag_position():
    # [2d] 드래그(커서 위치) — 복제 중심이 커서 씬좌표.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    dup, _arrow = w._view._qc_create(a, "b", QPointF(250, 400))
    dsr = dup.mapToScene(dup.rect()).boundingRect()
    assert _close(dsr.center(), QPointF(250, 400))


def test_qc_dot_at_roundtrip():
    # [2d] 도트 씬좌표 → 뷰좌표 → _qc_dot_at. 핸들과 동일하게 '어느 도구에서든' 잡혀야 한다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    v = w._view
    rd_local = dict(a._qc_dot_rects())["r"].center()
    view_pos = v.mapFromScene(a.mapToScene(rd_local))
    for tool in ("select", "rect", "ellipse"):
        w.set_tool(tool); a.setSelected(True)
        hit = v._qc_dot_at(view_pos)
        assert hit is not None and hit[0] is a and hit[1] == "r", tool


def _cleft(o):
    return o.mapToScene(o._content_rect()).boundingRect().left()


def test_smart_align_snaps_within_threshold():
    # [2e] 임계 내로 어긋난 좌변 → 정렬 스냅 + 세로 가이드 기록.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    thr = 6.0 / v._view_scale()
    b.setPos(QPointF(thr * 0.5, 300)); b.setSelected(True)   # 좌변 임계 내 어긋남
    assert abs(_cleft(a) - _cleft(b)) > 1e-6
    v._apply_smart_snap()
    assert abs(_cleft(a) - _cleft(b)) < 1e-6                 # 정렬됨
    assert any(g[0] == "v" for g in v._align_guides)


def test_smart_align_no_snap_beyond_threshold():
    # [2e] 임계 밖이면 스냅·가이드 없음(자유 이동).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    thr = 6.0 / v._view_scale()
    b.setPos(QPointF(thr * 4, 300)); b.setSelected(True)
    before = _cleft(b)
    v._apply_smart_snap()
    assert abs(_cleft(b) - before) < 1e-6 and v._align_guides == []


def test_smart_align_skips_multiselect():
    # [2e] 2개 이상 선택 시엔 스마트 정렬 스냅을 적용하지 않는다(그룹 변형 영역).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    b = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    v = w._view
    thr = 6.0 / v._view_scale()
    b.setPos(QPointF(thr * 0.5, 300))
    a.setSelected(True); b.setSelected(True)
    before = _cleft(b)
    v._apply_smart_snap()
    assert abs(_cleft(b) - before) < 1e-6 and v._align_guides == []


def test_stretch_grips_pure():
    # [2b] grip 수집 — 네모=4모서리, 선/화살표/폴리=끝점들.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 10, 20, 100, 60)
    gs = a._stretch_grips()
    assert len(gs) == 4
    assert any(_close(g, QPointF(10, 20)) for g in gs)
    assert any(_close(g, QPointF(110, 80)) for g in gs)
    ln = _LineItem(QLineF(0, 0, 200, 40)); w._scene.addItem(ln)
    gl = ln._stretch_grips()
    assert len(gl) == 2 and _close(gl[0], QPointF(0, 0)) and _close(gl[1], QPointF(200, 40))
    pa = _PolyArrowItem(QColor("black"), 4, True)
    pa.set_points(QPointF(0, 0), QPointF(50, 0)); pa.insert_vertex(0, QPointF(25, 30))
    w._scene.addItem(pa)
    assert len(pa._stretch_grips()) == 3   # 3정점(waypoint 포함)


def test_stretch_arm_requires_box():
    # [2b] 명시적 모드 — 러버밴드 박스가 '기억'돼 있고 선택이 있을 때만 S 무장.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    v = w._view
    v._last_sel_rect = None
    v._stretch_arm_now()
    assert not v._stretch_arm            # 박스 기억 없으면 무장 안 됨(암묵 트리거 방지)
    v._last_sel_rect = QRectF(-10, -10, 200, 200)
    v._stretch_arm_now()
    assert v._stretch_arm and len(v._stretch_grip_pts) == 4   # 전 모서리 박스 안
    v._stretch_cancel()
    assert not v._stretch_arm and v._stretch_grip_pts == []


def test_stretch_straddle_line():
    # [2b] crossing 박스가 오른 끝만 걸침 → 그 끝만 이동, 왼 끝은 고정(AutoCAD stretch 핵심).
    w = CanvasWindow()
    ln = _LineItem(QLineF(0, 0, 200, 0)); ln.setPen(w.make_pen())
    ln.setFlags(ln.GraphicsItemFlag.ItemIsSelectable | ln.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ln); ln.setSelected(True)
    v = w._view
    v._last_sel_rect = QRectF(150, -50, 100, 100)   # 오른 끝(200,0)만 포함
    v._stretch_arm_now()
    assert v._stretch_arm and len(v._stretch_grip_pts) == 1
    assert _close(v._stretch_grip_pts[0], QPointF(200, 0))
    v._stretch_begin(QPointF(200, 0))               # 기준점
    v._stretch_apply(QPointF(300, 0))               # 도착 → delta (100,0)
    v._stretch_commit()
    eps = ln._endpoints()
    assert _close(ln.mapToScene(eps[0]), QPointF(0, 0))      # 왼 끝 고정
    assert _close(ln.mapToScene(eps[1]), QPointF(300, 0))    # 오른 끝만 이동
    w.undo()
    assert _close(ln._endpoints()[1], QPointF(200, 0))


def test_stretch_contained_translates():
    # [2b] 완전포함 도형 = 모든 grip이 박스 안 → 전부 +delta = 강체 이동(왜곡 없음).
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    v = w._view
    v._last_sel_rect = QRectF(-20, -20, 200, 200)
    v._stretch_arm_now()
    v._stretch_begin(QPointF(0, 0))
    v._stretch_apply(QPointF(50, 30))               # delta (50,30)
    v._stretch_commit()
    assert a.rect() == QRectF(50, 30, 100, 60)       # 크기 불변, 위치만 +delta
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60)


def test_stretch_binding_follows_crossed_side():
    # [2b] 도형의 걸친 변만 stretch → 그 변에 붙은 (미선택) 화살표 부착점이 따라온다.
    w = CanvasWindow()
    a = _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60); a.setSelected(True)
    ar = _ArrowItem(QColor("#ffff9500"), 6, True)
    ar.set_points(QPointF(100, 30), QPointF(250, 30))
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    ar.set_bound(0, a, a.mapFromScene(QPointF(100, 30)))   # 시작 = 네모 오른 변
    v = w._view
    v._last_sel_rect = QRectF(80, -20, 60, 100)     # 오른 두 모서리+부착점만(왼 변·화살표 끝 제외)
    v._stretch_arm_now()
    v._stretch_begin(QPointF(100, 30))
    v._stretch_apply(QPointF(150, 30))              # delta (50,0) → 오른 변 150으로
    v._stretch_commit()
    assert a.rect() == QRectF(0, 0, 150, 60)         # 오른 변만 +50
    assert ar.has_binding()
    assert _close(ar.mapToScene(ar._endpoints()[0]), QPointF(150, 30))   # 시작이 새 변 추종
    assert _close(ar.mapToScene(ar._endpoints()[1]), QPointF(250, 30))   # 끝은 고정
    w.undo()
    assert a.rect() == QRectF(0, 0, 100, 60)
    assert _close(ar.mapToScene(ar._endpoints()[0]), QPointF(100, 30))


def test_symbol_kinds_render_and_geom():
    # M1: 6종 심볼이 모두 경로를 만들고, rect 기반 기계(박스핸들·geom undo·clone)를 물려받는다.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    assert set(_SYMBOL_KINDS) == {"decision", "terminal", "data", "prep", "document", "database"}
    for kind in _SYMBOL_KINDS:
        it = _SymbolItem(kind, QRectF(0, 0, 120, 80))
        it.setPen(QPen(QColor("#ff000000"))); it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
        sc.addItem(it)
        # 경로·경계·shape 모두 실체가 있어야(빈 도형이면 클릭/렌더 불가)
        assert it._sym_path().elementCount() > 0, kind
        assert not it.boundingRect().isEmpty(), kind
        assert not it.shape().isEmpty(), kind
        # rect 기반이라 Lucid 박스 핸들이 자동 활성(리사이즈 공짜)
        assert it._box_handles() is True, kind
        # geom 스냅샷 → 리사이즈 → 복원이 정확히 되돌아온다
        tok = it.capture_geom()
        it.setRect(QRectF(5, 5, 200, 140))
        it.apply_geom(tok)
        assert _close(it.rect().topLeft(), QPointF(0, 0)) and abs(it.rect().width() - 120) < 0.5, kind
        # clone은 kind·기하·스타일 보존
        c = it.clone()
        assert isinstance(c, _SymbolItem) and c._kind == kind
        assert _close(c.rect().topLeft(), it.rect().topLeft())


def test_symbol_draw_via_tool():
    # M2: 심볼 도구 무장 → 캔버스 드래그 → 해당 kind의 _SymbolItem이 생성·선택된다.
    w = CanvasWindow(); w.show(); w.set_tool("sym:decision"); w._zoom_reset()
    view = w._view
    press, release, _click, _move, drag_move, _dbl = _draw_helpers(view)
    press(QPointF(0, 0)); drag_move(QPointF(140, 90)); release(QPointF(140, 90))
    syms = [it for it in w._scene.items() if isinstance(it, _SymbolItem)]
    assert len(syms) == 1
    s = syms[0]
    assert s._kind == "decision"
    r = s.mapRectToScene(s.rect())
    assert abs(r.width() - 140) < 2 and abs(r.height() - 90) < 2
    assert s.isSelected()
    # 팔레트 버튼 무장 상태가 set_tool과 동기화됐는지
    assert w._sym_buttons["decision"].isChecked()
    w.set_tool("select")
    assert not w._sym_buttons["decision"].isChecked()


def test_symbol_roundtrip():
    # M4: 심볼(kind 포함)이 .ecad 저장/열기로 무손실 왕복한다.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    for i, kind in enumerate(("data", "database")):
        it = _SymbolItem(kind, QRectF(0, 0, 100, 60))
        p = QPen(QColor("#ff112233")); p.setWidthF(3.0)
        it.setPen(p); it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        it.setPos(QPointF(50 * i, 20 * i)); it.setRotation(10 * i)
        sc.addItem(it)
    before = [item_to_dict(it) for it in reversed(sc.items())]
    assert all(d["type"] == "symbol" for d in before)
    path = os.path.join(_TMP, "symbols.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 2
    after = [item_to_dict(it) for it in reversed(sc2.items())]
    assert [d["kind"] for d in after] == ["data", "database"]
    for b, a in zip(before, after):
        assert b["kind"] == a["kind"] and b["type"] == a["type"]


def test_symbol_is_arrow_connectable():
    # self-review 갭: 순서도의 본질은 '심볼 잇는 화살표'. 심볼이 _conn_shapes/장애물에 포함돼
    # 화살표가 테두리 스냅+지속연결로 붙어야 한다(네모와 동일 동작).
    w = CanvasWindow(); w.show(); w.set_tool("sarrow"); w._zoom_reset()
    sym = _SymbolItem("decision", QRectF(200, 0, 100, 60))   # 우측 박스 테두리 x=300, 중앙 y=30
    sym.setPen(w.make_pen()); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sym.setFlags(sym.GraphicsItemFlag.ItemIsSelectable | sym.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sym)
    view = w._view
    assert sym in view._conn_shapes()                        # 연결 대상 목록에 포함
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)
    press(QPointF(0, 30)); drag_move(QPointF(305, 30)); release(QPointF(305, 30))
    sa = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)][0]
    assert sa.has_binding()                                  # 심볼 테두리에 부착됨
    assert _close(sa.mapToScene(sa._pts[-1]), QPointF(300, 30)), sa.mapToScene(sa._pts[-1])
    # 심볼을 옮기면 지속연결로 화살표 끝이 따라온다
    sym.moveBy(40, 0)
    w._on_scene_changed(None)
    assert _close(sa.mapToScene(sa._pts[-1]), QPointF(340, 30)), sa.mapToScene(sa._pts[-1])


def test_symbol_border_follows_outline():
    # GUI 리포트 수정: 화살표 스냅이 외접 '박스'가 아니라 심볼의 '실제 외곽선'에 닿아야 한다.
    # 마름모(판단)는 박스와 4점에서만 만나므로, 박스 기반이면 대부분 허공에 스냅돼 안 붙는다.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    import math as _m
    sc = QGraphicsScene()
    sym = _SymbolItem("decision", QRectF(200, 0, 100, 60))   # 중심(250,30), a=50 b=30
    sym.setPen(QPen(QColor("#ff000000"))); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sc.addItem(sym)

    def on_diamond(q):   # 마름모 경계식 |x-250|/50 + |y-30|/30 = 1
        return abs(q.x() - 250) / 50.0 + abs(q.y() - 30) / 30.0

    # 변(꼭짓점 아님) 근처의 여러 점 → 스냅점이 마름모 외곽선 위(경계식≈1)에 있어야
    for scene_pt in (QPointF(210, 8), QPointF(288, 12), QPointF(215, 52), QPointF(285, 50)):
        snap, n = _nearest_border(sym, scene_pt)
        assert abs(on_diamond(snap) - 1.0) < 0.02, (scene_pt, snap, on_diamond(snap))
        # 법선은 바깥(중심 반대)을 향한다
        assert (snap.x() - 250) * n.x() + (snap.y() - 30) * n.y() > 0, (snap, n)

    # 박스 위이되 마름모 '밖'인 점(좌상단 코너 근처)도 외곽선으로 당겨진다(박스 top y=0이 아님)
    snap, _n = _nearest_border(sym, QPointF(205, 3))
    assert snap.y() > 3.5, snap   # 박스 top(y=0)이 아니라 마름모 변 위로


def test_symbol_center_label():
    # 심볼 라벨은 선·화살표(중점 위쪽)와 달리 도형 '정중앙'에 놓이고, 리사이즈하면 따라온다.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    sym = _SymbolItem("decision", QRectF(0, 0, 120, 80))
    sym.setPen(QPen(QColor("#ff000000"))); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sc.addItem(sym)
    lbl = sym.ensure_label(); lbl.setPlainText("예"); sym._sync_label()
    assert sym.has_label()
    br = lbl._content_rect()
    # x는 문서박스 중심, y는 글리프 잉크 광학중심(작은 세로 보정 허용). 중앙(60,40) 근방.
    assert abs(lbl.pos().x() + br.width() / 2.0 - 60) < 1, lbl.pos()
    assert abs(lbl.pos().y() + br.height() / 2.0 - 40) < 4, lbl.pos()
    # 리사이즈 → 라벨이 새 중앙(100,50)으로 자동 이동(setRect override)
    sym.setRect(QRectF(0, 0, 200, 100))
    br = lbl._content_rect()
    assert abs(lbl.pos().x() + br.width() / 2.0 - 100) < 1, lbl.pos()
    assert abs(lbl.pos().y() + br.height() / 2.0 - 50) < 4, lbl.pos()


def test_symbol_label_roundtrip():
    # 심볼 중앙 라벨이 .ecad 저장/열기로 왕복한다.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    sym = _SymbolItem("terminal", QRectF(0, 0, 100, 60))
    sym.setPen(QPen(QColor("#ff112233"))); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sc.addItem(sym)
    sym.ensure_label().setPlainText("시작"); sym._sync_label()
    path = os.path.join(_TMP, "symlabel.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 1
    got = [it for it in sc2.items() if isinstance(it, _SymbolItem)][0]
    assert got.has_label() and got._label.toPlainText() == "시작"


def test_rect_ellipse_center_label():
    # A: 네모·원도 심볼과 같은 중앙 라벨을 공유(_CenterLabelMixin). 더블클릭 라벨 + 리사이즈 추종.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    for cls, make in ((_RectItem, lambda: _RectItem(QRectF(0, 0, 120, 80))),
                      (_EllipseItem, lambda: _EllipseItem(QRectF(0, 0, 120, 80)))):
        it = make()
        it.setPen(QPen(QColor("#ff0000ff"))); it.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        sc.addItem(it)
        lbl = it.ensure_label(); lbl.setPlainText("칸"); it._sync_label()
        assert it.has_label(), cls.__name__
        br = lbl._content_rect()
        # x=문서박스 중심, y=글리프 잉크 광학중심(작은 세로 보정 허용)
        assert abs(lbl.pos().x() + br.width() / 2.0 - 60) < 1, (cls.__name__, lbl.pos())
        assert abs(lbl.pos().y() + br.height() / 2.0 - 40) < 4, (cls.__name__, lbl.pos())
        it.setRect(QRectF(0, 0, 200, 100))         # 리사이즈 → 새 중앙(100,50) 추종
        br = lbl._content_rect()
        assert abs(lbl.pos().x() + br.width() / 2.0 - 100) < 1, (cls.__name__, lbl.pos())
        # 라벨 색 = 테두리색(파랑)
        assert lbl.defaultTextColor().name() == QColor("#0000ff").name(), cls.__name__


def test_rect_label_roundtrip():
    # 네모 중앙 라벨이 .ecad로 왕복한다(직렬화에 _RectItem 포함).
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    sc = QGraphicsScene()
    r = _RectItem(QRectF(0, 0, 100, 60)); r.setPen(QPen(QColor("#ff333333")))
    r.setBrush(QBrush(Qt.BrushStyle.NoBrush)); sc.addItem(r)
    r.ensure_label().setPlainText("상자"); r._sync_label()
    path = os.path.join(_TMP, "rectlabel.ecad")
    save_document(sc, path)
    sc2 = QGraphicsScene()
    load_document(sc2, path)
    got = [it for it in sc2.items() if isinstance(it, _RectItem)][0]
    assert got.has_label() and got._label.toPlainText() == "상자"


def test_shape_ports_pure():
    # M1: 포트 = 변 중점 4개(N/E/S/W)를 실제 외곽선에 투영. 네모=변 중점, 마름모=꼭짓점.
    r = _RectItem(QRectF(0, 0, 100, 60))
    got = sorted((round(p.x()), round(p.y())) for p, _n in _shape_ports(r))
    assert got == sorted([(50, 0), (100, 30), (50, 60), (0, 30)]), got
    # 법선은 바깥(중심 반대). 중심 (50,30).
    for p, n in _shape_ports(r):
        assert (p.x() - 50) * n.x() + (p.y() - 30) * n.y() >= -1e-6, (p, n)
    sym = _SymbolItem("decision", QRectF(200, 0, 100, 60))   # 마름모 꼭짓점 = N/E/S/W
    got2 = sorted((round(p.x()), round(p.y())) for p, _n in _shape_ports(sym))
    assert got2 == sorted([(250, 0), (300, 30), (250, 60), (200, 30)]), got2


def test_port_priority_then_continuous_fallback():
    # M2: 포트 근처 커서 → 포트에 딱. 포트에서 먼 변 중간 → 기존 연속 외곽선 폴백.
    w = CanvasWindow(); w.show(); w.set_tool("arrow"); w._zoom_reset()
    view = w._view
    sym = _SymbolItem("decision", QRectF(200, 0, 100, 60))
    sym.setPen(w.make_pen()); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sym.setFlags(sym.GraphicsItemFlag.ItemIsSelectable | sym.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sym)
    # N 포트(250,0) 근처(253,3) → 포트로 스냅
    snap = view._border_snap_at(view.mapFromScene(QPointF(253, 3)))
    assert snap is not None and _close(snap[0], QPointF(250, 0)), snap
    # 상-우 변 중점(275,15) — 꼭짓점서 ~29px라 포트 밖 → 연속 외곽선(그 점 그대로)
    snap2 = view._border_snap_at(view.mapFromScene(QPointF(275, 15)))
    assert snap2 is not None and _close(snap2[0], QPointF(275, 15), eps=2), snap2


def test_arrow_binds_to_port_and_follows():
    # M4: 화살표를 포트 근처로 그리면 포트에 부착, 도형을 옮기면 포트 따라 이동.
    w = CanvasWindow(); w.show(); w.set_tool("arrow"); w._zoom_reset()
    view = w._view
    sym = _SymbolItem("decision", QRectF(200, 0, 100, 60))
    sym.setPen(w.make_pen()); sym.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    sym.setFlags(sym.GraphicsItemFlag.ItemIsSelectable | sym.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(sym)
    press, release, _c, _m, drag_move, _d = _draw_helpers(view)
    press(QPointF(50, 200)); drag_move(QPointF(253, 3)); release(QPointF(253, 3))
    ar = [it for it in w._scene.items() if isinstance(it, _ArrowItem)][-1]
    assert ar.has_binding()
    assert _close(ar.mapToScene(ar._p2), QPointF(250, 0)), ar.mapToScene(ar._p2)
    sym.moveBy(40, 0); w._on_scene_changed(None)              # N 포트 (250,0)→(290,0)
    assert _close(ar.mapToScene(ar._p2), QPointF(290, 0)), ar.mapToScene(ar._p2)


def test_dxf_export():
    # Phase 3: 각 도형 타입이 개별 DXF 엔티티로 매핑되는지 + Y축 뒤집기 확인.
    import ezdxf
    from PyQt6.QtGui import QPen
    w = CanvasWindow(); w.show()
    sc = w._scene

    rect = _RectItem(QRectF(0, 0, 100, 60)); rect.setPen(QPen(QColor("red")))
    rect.setBrush(QBrush(Qt.BrushStyle.NoBrush)); rect.setPos(QPointF(10, 20)); sc.addItem(rect)
    circ = _EllipseItem(QRectF(0, 0, 80, 80)); circ.setPen(QPen(QColor("blue")))
    circ.setBrush(QBrush(Qt.BrushStyle.NoBrush)); circ.setPos(QPointF(200, 0)); sc.addItem(circ)
    ell = _EllipseItem(QRectF(0, 0, 120, 60)); ell.setPen(QPen(QColor("blue")))
    ell.setBrush(QBrush(Qt.BrushStyle.NoBrush)); ell.setPos(QPointF(400, 0)); sc.addItem(ell)
    line = _LineItem(QLineF(0, 0, 100, 50)); line.setPen(QPen(QColor("black"))); sc.addItem(line)
    ar = _ArrowItem(QColor("green"), 2.0, True)      # 베지어 화살 → SPLINE
    ar.set_points(QPointF(0, 0), QPointF(100, 40)); ar._ctrl1 = QPointF(30, -20)
    ar._ctrl2 = QPointF(70, 60); sc.addItem(ar)
    sar = _PolyArrowItem(QColor("purple"), 2.0, True)
    sar._pts = [QPointF(0, 0), QPointF(50, 0), QPointF(50, 40)]; sc.addItem(sar)
    txt = _TextItem(QColor("black")); txt.setPlainText("hello"); txt.setPos(QPointF(0, 300))
    sc.addItem(txt)
    badge = _BadgeItem(7, QColor("orange")); badge.setPos(QPointF(300, 300)); sc.addItem(badge)
    sym = _SymbolItem("decision", QRectF(0, 0, 100, 60)); sym.setPen(QPen(QColor("teal")))
    sym.setBrush(QBrush(Qt.BrushStyle.NoBrush)); sym.setPos(QPointF(0, 400)); sc.addItem(sym)

    path = os.path.join(_TMP, "export.dxf")
    assert export_dxf(sc, path)
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    kinds = {}
    for e in msp:
        kinds[e.dxftype()] = kinds.get(e.dxftype(), 0) + 1
    # 베지어 화살 = SPLINE, 정원 = CIRCLE, 타원 = ELLIPSE, 직교화살+심볼+네모 = LWPOLYLINE.
    assert kinds.get("SPLINE", 0) >= 1, kinds          # arrow 샤프트
    assert kinds.get("CIRCLE", 0) >= 2, kinds          # circ + badge
    assert kinds.get("ELLIPSE", 0) >= 1, kinds         # ell
    assert kinds.get("LINE", 0) >= 1, kinds            # line
    assert kinds.get("LWPOLYLINE", 0) >= 4, kinds      # rect + sarrow + symbol(1+) + 화살촉2
    assert kinds.get("MTEXT", 0) >= 2, kinds           # txt + badge 번호
    # Y축 뒤집기: rect 좌상단 로컬(0,0)+pos(10,20) → world(10,20) → DXF(10,-20).
    rects = [e for e in msp if e.dxftype() == "LWPOLYLINE"]
    corners = [tuple(p[:2]) for e in rects for p in e.get_points()]
    assert any(abs(x - 10) < 1e-6 and abs(y + 20) < 1e-6 for x, y in corners), corners
    # 타입별 레이어 분리 확인.
    layers = {e.dxf.layer for e in msp}
    assert {"EC_RECT", "EC_ARROW", "EC_SARROW", "EC_SYMBOL", "EC_TEXT"} <= layers, layers


def _rect_world_corners(it):
    r = it.rect()
    pts = [(r.left(), r.top()), (r.right(), r.top()), (r.right(), r.bottom()), (r.left(), r.bottom())]
    return sorted((round(it.mapToScene(QPointF(x, y)).x(), 1),
                   round(it.mapToScene(QPointF(x, y)).y(), 1)) for x, y in pts)


def test_dxf_import_roundtrip():
    # Phase 3 후반: export→import 왕복에서 핵심 기하(꼭짓점·끝점·중심·텍스트·번호)가 보존되는지.
    # 소실 허용(설계 결정): 심볼 kind(→외곽선 _PathItem), 지속연결 바인딩, 자식 라벨(→독립),
    # 폭, 변환 필드값(회전/스케일은 월드 기하로만 보존). 판정은 dict 일치가 아니라 월드 기하 일치.
    from PyQt6.QtWidgets import QGraphicsScene
    from PyQt6.QtGui import QPen
    from easycad.fileio.dxf_import import import_dxf

    def pen(c="#ffff0000", wd=3):
        p = QPen(QColor(c)); p.setWidthF(wd); return p

    sc = QGraphicsScene()
    # 네모(평행이동) + 회전 네모(회전 흡수 검증)
    rect = _RectItem(QRectF(0, 0, 100, 60)); rect.setPen(pen()); rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    rect.setPos(QPointF(10, 20)); sc.addItem(rect)
    rrot = _RectItem(QRectF(0, 0, 80, 40)); rrot.setPen(pen()); rrot.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    rrot.setPos(QPointF(600, 500)); rrot.setTransformOriginPoint(QPointF(40, 20)); rrot.setRotation(30); sc.addItem(rrot)
    # 정원 + 타원
    circ = _EllipseItem(QRectF(0, 0, 80, 80)); circ.setPen(pen("#ff0000ff")); circ.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    circ.setPos(QPointF(200, 0)); sc.addItem(circ)
    ell = _EllipseItem(QRectF(0, 0, 120, 60)); ell.setPen(pen("#ff0000ff")); ell.setBrush(QBrush(Qt.BrushStyle.NoBrush))
    ell.setPos(QPointF(400, 0)); sc.addItem(ell)
    # 선
    line = _LineItem(QLineF(0, 0, 100, 50)); line.setPen(pen("#ff333333")); sc.addItem(line)
    # 곡선 화살표(끝쪽 촉) + 직선 화살표(시작쪽 촉 — 방향 복원 검증)
    ar = _ArrowItem(QColor("#ff00ff00"), 6, True)
    ar.set_points(QPointF(0, 0), QPointF(100, 40)); ar._ctrl1 = QPointF(30, -20); ar._ctrl2 = QPointF(70, 60)
    sc.addItem(ar)
    ars = _ArrowItem(QColor("#ff00ff00"), 6, False)      # head_at_end=False
    ars.set_points(QPointF(0, 700), QPointF(150, 760)); sc.addItem(ars)
    # 직교 화살표
    sar = _PolyArrowItem(QColor("#ffff00ff"), 6, True)
    sar._pts = [QPointF(0, 0), QPointF(50, 0), QPointF(50, 40)]; sc.addItem(sar)
    # 텍스트
    txt = _TextItem(QColor("#ff000000")); txt.apply_font_size(20); txt.setPlainText("hello")
    txt.setPos(QPointF(0, 300)); sc.addItem(txt)
    # 번호 배지
    badge = _BadgeItem(7, QColor("#ffff9500")); badge.setPos(QPointF(300, 300)); badge.setScale(2.0); sc.addItem(badge)
    # 심볼(kind 소실 → 외곽선만)
    sym = _SymbolItem("decision", QRectF(0, 0, 100, 60)); sym.setPen(pen("#ff008080"))
    sym.setBrush(QBrush(Qt.BrushStyle.NoBrush)); sym.setPos(QPointF(0, 400)); sc.addItem(sym)

    path = os.path.join(_TMP, "roundtrip_dxf.dxf")
    assert export_dxf(sc, path)
    sc2 = QGraphicsScene()
    import_dxf(sc2, path)

    # 네모 2개(평행이동·회전) — 월드 꼭짓점 집합 일치.
    rects = [it for it in sc2.items() if isinstance(it, _RectItem)]
    assert len(rects) == 2, len(rects)
    want = {tuple(_rect_world_corners(rect)), tuple(_rect_world_corners(rrot))}
    got = {tuple(_rect_world_corners(r)) for r in rects}
    assert got == want, (got, want)

    # 원/타원 — 월드 경계 꼭짓점 집합 일치(_RectItem과 같은 방식).
    ells = [it for it in sc2.items() if isinstance(it, _EllipseItem)]
    assert len(ells) == 2, len(ells)
    ewant = {tuple(_rect_world_corners(circ)), tuple(_rect_world_corners(ell))}
    egot = {tuple(_rect_world_corners(e)) for e in ells}
    assert egot == ewant, (egot, ewant)

    # 선 — 끝점 집합 일치 + 펜 두께(XDATA) 보존.
    lines = [it for it in sc2.items() if isinstance(it, _LineItem)]
    assert len(lines) == 1
    ln = lines[0].line()
    ends = sorted([(round(ln.x1(), 1), round(ln.y1(), 1)), (round(ln.x2(), 1), round(ln.y2(), 1))])
    assert ends == sorted([(0.0, 0.0), (100.0, 50.0)]), ends
    assert abs(lines[0].pen().widthF() - 3.0) < 1e-6, lines[0].pen().widthF()

    # 펜 두께 왕복 — 네모(3)·화살표(6)·직교화살(6)이 XDATA로 보존(기본값 1로 얇아지지 않음).
    r_thick = [r for r in rects if abs(r.pen().widthF() - 3.0) < 1e-6]
    assert len(r_thick) == 2, [r.pen().widthF() for r in rects]

    # 곡선 화살표 — 끝점+제어점(월드) 보존, 방향 복원.
    arrows = [it for it in sc2.items() if isinstance(it, _ArrowItem)]
    assert len(arrows) == 2, len(arrows)
    curved = [a for a in arrows if a._ctrl1 is not None]
    assert len(curved) == 1
    c = curved[0]
    assert _close(c.mapToScene(c._p1), QPointF(0, 0)) and _close(c.mapToScene(c._p2), QPointF(100, 40))
    assert _close(c.mapToScene(c._ctrl1), QPointF(30, -20)) and _close(c.mapToScene(c._ctrl2), QPointF(70, 60))
    assert c._head_at_end is True
    assert abs(c._width - 6.0) < 1e-6, c._width          # 화살표 폭 XDATA 보존
    straight = [a for a in arrows if a._ctrl1 is None][0]
    assert straight._head_at_end is False, "시작쪽 촉 방향이 복원돼야(무시+방향복원)"

    # 직교 화살표 — 정점 보존.
    sas = [it for it in sc2.items() if isinstance(it, _PolyArrowItem)]
    assert len(sas) == 1
    spts = [(round(p.x(), 1), round(p.y(), 1)) for p in sas[0]._pts]
    assert spts == [(0.0, 0.0), (50.0, 0.0), (50.0, 40.0)], spts

    # 텍스트 — 문자열+위치.
    texts = [it for it in sc2.items() if isinstance(it, _TextItem)]
    assert len(texts) == 1 and texts[0].toPlainText() == "hello"
    assert _close(texts[0].pos(), QPointF(0, 300), eps=1.5)

    # 배지 — 번호+중심+스케일(반경).
    badges = [it for it in sc2.items() if isinstance(it, _BadgeItem)]
    assert len(badges) == 1 and badges[0]._number == 7
    assert _close(badges[0].pos(), QPointF(300, 300), eps=1.0)
    assert abs(badges[0].scale() - 2.0) < 0.05, badges[0].scale()

    # 심볼 — kind 소실, 외곽선 _PathItem으로 복원(마름모 4변 영역 안).
    paths = [it for it in sc2.items() if isinstance(it, _PathItem)]
    assert len(paths) >= 1, "심볼 외곽선이 path로 복원돼야"
    dia = [p for p in paths if p.mapToScene(p.boundingRect()).boundingRect().center().y() > 380]
    assert dia, "심볼(y≈400 부근) 외곽선 path 존재해야"


def test_dxf_import_external_fallback():
    # 임의 외부 DXF(우리 레이어 관례 없음) → dxftype 폴백으로 손실 매핑(LINE·CIRCLE·TEXT).
    from PyQt6.QtWidgets import QGraphicsScene
    import ezdxf
    from easycad.fileio.dxf_import import import_dxf

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_line((0, 0), (100, 0))                    # 레이어 "0"
    msp.add_circle((50, 50), 25)
    msp.add_text("EXT", dxfattribs={"insert": (10, 10)})
    path = os.path.join(_TMP, "external.dxf")
    doc.saveas(path)

    sc = QGraphicsScene()
    n = import_dxf(sc, path)
    assert n >= 3, n
    assert any(isinstance(it, _LineItem) for it in sc.items())
    assert any(isinstance(it, _EllipseItem) for it in sc.items())
    assert any(isinstance(it, _TextItem) for it in sc.items())


# ---- Phase 4: 이미지 삽입 ---------------------------------------------------
def _mk_pixmap(w=40, h=20, color="#3366cc"):
    pm = QPixmap(w, h)
    pm.fill(QColor(color))
    return pm


def test_image_item_basic():
    # rect 기반이라 박스 8핸들·리사이즈 기계를 물려받고, 픽스맵을 보관한다.
    it = _ImageItem(_mk_pixmap(), QRectF(0, 0, 40, 20))
    assert it._box_handles() is True          # setRect 보유 → 박스 핸들 경로
    assert it._pixmap.width() == 40 and it._pixmap.height() == 20
    c = it.clone()                            # 복제도 픽스맵·rect 보존
    assert isinstance(c, _ImageItem)
    assert c._pixmap.width() == 40 and c.rect() == QRectF(0, 0, 40, 20)


def test_image_aspect_lock_on_corner():
    # 꼭짓점 리사이즈는 원본 종횡비(2:1) 유지. 변 리사이즈는 자유(늘림 허용).
    it = _ImageItem(_mk_pixmap(40, 20), QRectF(0, 0, 40, 20))   # aspect 2.0
    it._box_orig_rect = QRectF(it.rect())
    it._box_bound = []
    it._box_snap = []
    it._box_resize = ("corner", 2)            # BR 꼭짓점(대각 고정 = TL)
    it._apply_box_resize(QPointF(100, 100))   # 자유라면 100×100(1:1)이 될 지점
    r = it.rect()
    assert abs(r.width() / r.height() - 2.0) < 1e-6   # 종횡비 고정됨
    # 변 드래그(오른쪽)는 종횡비 무시하고 자유.
    it2 = _ImageItem(_mk_pixmap(40, 20), QRectF(0, 0, 40, 20))
    it2._box_orig_rect = QRectF(it2.rect())
    it2._box_bound = []; it2._box_snap = []
    it2._box_resize = ("edge", "r")
    it2._apply_box_resize(QPointF(200, 0))
    r2 = it2.rect()
    assert r2.width() > 150 and abs(r2.height() - 20) < 1e-6   # 높이 불변, 폭만 늘어남


def test_image_roundtrip():
    # .ecad 저장/재열기에서 픽스맵 픽셀·크기·기하가 base64 embed로 보존되는지.
    w = CanvasWindow()
    it = _ImageItem(_mk_pixmap(40, 20, "#cc2233"), QRectF(0, 0, 40, 20))
    it.setPos(QPointF(120, 80))
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    path = os.path.join(_TMP, "img.ecad")
    save_document(w._scene, path)
    w2 = CanvasWindow()
    n = load_document(w2._scene, path)
    assert n == 1
    imgs = [x for x in w2._scene.items() if isinstance(x, _ImageItem)]
    assert len(imgs) == 1
    lo = imgs[0]
    assert lo._pixmap.width() == 40 and lo._pixmap.height() == 20
    assert _close(lo.pos(), QPointF(120, 80))
    assert lo.rect() == QRectF(0, 0, 40, 20)
    # 픽셀 색 보존(무손실 PNG embed) — 좌상단 픽셀이 원본 색.
    col = lo._pixmap.toImage().pixelColor(0, 0)
    assert (col.red(), col.green(), col.blue()) == (0xcc, 0x22, 0x33)


def test_image_insert_via_host():
    # host._insert_image_at: 파일 → 씬에 삽입(중심 배치·긴 변 축소·undo 등록).
    w = CanvasWindow()
    png = os.path.join(_TMP, "src.png")
    _mk_pixmap(800, 400, "#22aa55").save(png, "PNG")   # 대형 → 긴 변 400으로 축소돼야
    w._insert_image_at(png, QPointF(0, 0))
    imgs = [x for x in w._scene.items() if isinstance(x, _ImageItem)]
    assert len(imgs) == 1
    it = imgs[0]
    assert it._pixmap.width() == 800                    # 원본 해상도 보관(표시만 축소)
    assert abs(it.rect().width() - 400.0) < 1e-6        # 긴 변 = _IMG_LONG
    assert abs(it.rect().height() - 200.0) < 1e-6       # 종횡비 유지(2:1)
    assert _close(it.sceneBoundingRect().center(), QPointF(0, 0), eps=1.0)  # 중심 배치
    assert it.isSelected()
    w.undo()                                            # 삽입 undo로 제거
    assert not [x for x in w._scene.items() if isinstance(x, _ImageItem)]


def test_image_skipped_in_dxf():
    # 범위 결정: DXF 내보내기는 이미지 제외(외부참조 배제). 씬에 이미지가 있어도
    # 크래시 없이 건너뛰고, 다른 엔티티(네모)는 정상 export.
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    img = _ImageItem(_mk_pixmap(40, 20), QRectF(0, 0, 40, 20))
    img.setFlags(img.GraphicsItemFlag.ItemIsSelectable | img.GraphicsItemFlag.ItemIsMovable)
    img.setPos(QPointF(200, 200)); w._scene.addItem(img)
    out = os.path.join(_TMP, "img_skip.dxf")
    assert export_dxf(w._scene, out) is not False
    import ezdxf
    doc = ezdxf.readfile(out)
    types = [e.dxftype() for e in doc.modelspace()]
    assert "LWPOLYLINE" in types            # 네모는 export됨
    assert "IMAGE" not in types             # 이미지는 제외됨


def test_image_pdf_export():
    # 이미지가 포함된 씬도 PDF로 렌더된다(scene.render 경로).
    w = CanvasWindow()
    it = _ImageItem(_mk_pixmap(60, 40), QRectF(0, 0, 60, 40))
    it.setFlags(it.GraphicsItemFlag.ItemIsSelectable | it.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(it)
    out = os.path.join(_TMP, "img.pdf")
    assert export_pdf(w._scene, out, page="A4") is True
    assert os.path.getsize(out) > 0


def test_titleblock_roundtrip():
    # [Phase 4] 표제란/용지틀: 삽입 → 필드 설정 → .ecad 왕복에서 용지 크기·방향·필드값 보존.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    tb = _TitleBlockItem("A2", "landscape",
                         {"number": "E-001", "title": "결선도", "scale": "1:50",
                          "client": "KBS", "author": "김민무", "reviewer": "홍길동",
                          "date": "2026-07-20"})
    tb.setFlags(tb.GraphicsItemFlag.ItemIsSelectable | tb.GraphicsItemFlag.ItemIsMovable)
    tb.setPos(QPointF(300, 400)); tb.setZValue(-1000.0)
    w._scene.addItem(tb)
    # 용지 치수: A2 가로 = 594 × 420
    pw, ph = tb.paper_wh()
    assert abs(pw - 594.0) < 0.1 and abs(ph - 420.0) < 0.1
    path = os.path.join(_TMP, "tb.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 1
    got = [it for it in sc2.items() if isinstance(it, _TitleBlockItem)][0]
    assert got._size == "A2" and got._orient == "landscape"
    assert got._fields["number"] == "E-001"
    assert got._fields["scale"] == "1:50"
    assert got._fields["author"] == "김민무"
    assert _close(got.pos(), QPointF(300, 400))
    assert got.zValue() == -1000.0


def test_titleblock_drives_pdf_page():
    # 씬에 표제란이 있으면 PDF가 프레임 용지 경계를 기준으로 자동 전환(출력 성공).
    w = CanvasWindow()
    tb = _TitleBlockItem("A3", "portrait")
    tb.setFlags(tb.GraphicsItemFlag.ItemIsSelectable | tb.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tb)
    _mk_rect(w._scene, w.make_pen(), 40, 40, 120, 80)   # 용지 안 도형
    out = os.path.join(_TMP, "tb.pdf")
    # page 인자를 A4로 줘도 프레임(A3)이 우선함 — 성공 여부만 확인(실제 페이지는 실조건).
    assert export_pdf(w._scene, out, page="A4") is True
    assert os.path.getsize(out) > 0


def test_titleblock_shape_is_clickthrough():
    # 용지 내부는 히트영역에서 제외(shape 통과) → 그 위에 도형을 그리거나 잡을 수 있다.
    # 표제란 표 영역과 용지 테두리 밴드만 히트영역.
    tb = _TitleBlockItem("A2", "landscape")
    r = tb.rect()
    interior = QPointF(r.center().x(), r.top() + 60.0)   # 상단 여백 아래 내부
    assert not tb.shape().contains(interior)             # 내부는 통과(선택 안 됨)
    tbr = tb._tb_rect()
    assert tb.shape().contains(tbr.center())             # 표제란 표는 히트영역
    assert tb.shape().contains(QPointF(r.left() + 2.0, r.center().y()))  # 좌측 테두리 밴드


def test_titleblock_skipped_in_dxf():
    # 스코프: DXF 내보내기는 표제란 제외(조용히 skip), 다른 엔티티는 정상 export.
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    tb = _TitleBlockItem("A2", "landscape")
    tb.setFlags(tb.GraphicsItemFlag.ItemIsSelectable | tb.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(tb)
    out = os.path.join(_TMP, "tb_skip.dxf")
    assert export_dxf(w._scene, out) is not False
    import ezdxf
    doc = ezdxf.readfile(out)
    types = [e.dxftype() for e in doc.modelspace()]
    assert "LWPOLYLINE" in types            # 네모는 export됨


def test_table_cell_geometry():
    # [Phase 4] 표 격자 기하: 균등 분할 cell_rect·cell_at 왕복(로컬좌표).
    t = _TableItem(3, 4, QRectF(0, 0, 160, 60))   # 셀 40×20
    assert t.dims() == (3, 4)
    r00 = t.cell_rect(0, 0)
    assert r00 == QRectF(0, 0, 40, 20)
    r12 = t.cell_rect(1, 2)
    assert r12 == QRectF(80, 20, 40, 20)
    assert t.cell_at(QPointF(90, 25)) == (1, 2)     # (r=1, c=2)
    assert t.cell_at(QPointF(1, 1)) == (0, 0)
    assert t.cell_at(QPointF(159, 59)) == (2, 3)    # 우하단 셀
    assert t.cell_at(QPointF(-5, 5)) is None        # 격자 밖


def test_table_roundtrip():
    # 삽입 → 셀 텍스트 설정 → .ecad 왕복에서 rows·cols·header·rect·셀텍스트·기하 보존.
    from PyQt6.QtWidgets import QGraphicsScene
    w = CanvasWindow()
    t = _TableItem(2, 3, QRectF(0, 0, 120, 40),
                   cells=[["번호", "명칭", "규격"], ["1", "카메라", "4K"]], header=True)
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    t.setPos(QPointF(200, 150)); t.setRotation(10)
    w._scene.addItem(t)
    path = os.path.join(_TMP, "table.ecad")
    save_document(w._scene, path)
    sc2 = QGraphicsScene()
    assert load_document(sc2, path) == 1
    got = [it for it in sc2.items() if isinstance(it, _TableItem)][0]
    assert got.dims() == (2, 3)
    assert got._header is True
    assert got.rect() == QRectF(0, 0, 120, 40)
    assert got.cell_text(0, 1) == "명칭"
    assert got.cell_text(1, 2) == "4K"
    assert _close(got.pos(), QPointF(200, 150))
    assert abs(got.rotation() - 10.0) < 1e-6


def test_table_clone():
    # 복제(그룹변형·복붙 경로): 셀 텍스트·차원·헤더가 독립 복사되고 원본과 분리.
    t = _TableItem(2, 2, QRectF(0, 0, 80, 40), cells=[["a", "b"], ["c", "d"]], header=False)
    c = t.clone()
    assert isinstance(c, _TableItem)
    assert c.dims() == (2, 2) and c._header is False
    assert c.cell_text(1, 0) == "c"
    c.set_cell_text(1, 0, "X")                       # 복제본 변경이 원본에 안 샘
    assert t.cell_text(1, 0) == "c"


def test_table_insert_via_host():
    # host._insert_table 경로: 다이얼로그를 건너뛰고 삽입 로직을 직접 검증하기 어려우니
    # _TableItem을 직접 넣어 undo/선택/PDF까지 통하는지 확인.
    w = CanvasWindow()
    t = _TableItem(3, 3, QRectF(0, 0, 120, 42))
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(t)
    w.push_undo_add(t)
    assert [x for x in w._scene.items() if isinstance(x, _TableItem)]
    w.undo()
    assert not [x for x in w._scene.items() if isinstance(x, _TableItem)]


def test_table_skipped_in_dxf():
    # 스코프: DXF 내보내기는 표 제외(조용히 skip), 다른 엔티티는 정상 export.
    w = CanvasWindow()
    _mk_rect(w._scene, w.make_pen(), 0, 0, 100, 60)
    t = _TableItem(2, 2, QRectF(0, 0, 80, 40))
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    t.setPos(QPointF(200, 200)); w._scene.addItem(t)
    out = os.path.join(_TMP, "table_skip.dxf")
    assert export_dxf(w._scene, out) is not False
    import ezdxf
    doc = ezdxf.readfile(out)
    types = [e.dxftype() for e in doc.modelspace()]
    assert "LWPOLYLINE" in types            # 네모는 export됨


def test_table_inline_edit():
    # 인라인 편집 로직: 커밋·Tab 이동(줄넘김)·Esc 취소가 셀 텍스트에 정확히 반영되는지.
    w = CanvasWindow()
    t = _TableItem(2, 2, QRectF(0, 0, 80, 40))
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(t)
    v = w._view
    v._begin_cell_edit(t, 0, 0)
    ed = v._cell_editor
    ed.setText("A"); ed._move(0, 1)                 # Tab → (0,1)로 이동하며 (0,0) 커밋
    assert t.cell_text(0, 0) == "A"
    ed = v._cell_editor
    assert (ed._r, ed._c) == (0, 1)
    ed.setText("B"); ed._move(0, 1)                 # 줄 끝 Tab → 다음 줄 첫 칸 (1,0)
    assert t.cell_text(0, 1) == "B"
    ed = v._cell_editor
    assert (ed._r, ed._c) == (1, 0)
    ed.setText("Z"); ed._cancel(); ed.close()       # Esc 취소 → 커밋 안 됨
    assert t.cell_text(1, 0) == ""


def test_table_pdf_export():
    # 표가 포함된 씬도 PDF로 렌더된다(scene.render → paint 경로).
    w = CanvasWindow()
    t = _TableItem(2, 3, QRectF(0, 0, 120, 40), cells=[["A", "B", "C"], ["1", "2", "3"]])
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(t)
    out = os.path.join(_TMP, "table.pdf")
    assert export_pdf(w._scene, out, page="A4") is True
    assert os.path.getsize(out) > 0


def test_symbol_label_optical_center():
    # 원기둥은 윗 타원을 피해 라벨을 rect 중심보다 아래(광학중심)로, 문서는 아래 물결을 피해
    # 살짝 위로. 상하 대칭 kind(마름모·스타디움 등)는 rect 중심 그대로.
    cyl = _SymbolItem("database", QRectF(0, 0, 120, 56))
    dia = _SymbolItem("decision", QRectF(0, 0, 120, 56))
    doc = _SymbolItem("document", QRectF(0, 0, 120, 56))
    assert cyl._label_anchor().y() > cyl.rect().center().y()      # 아래로
    assert doc._label_anchor().y() < doc.rect().center().y()      # 위로
    assert abs(dia._label_anchor().y() - dia.rect().center().y()) < 1e-6  # 대칭=보정없음
    # 리사이즈 후에도 광학중심 오프셋이 rect에 비례해 유지된다.
    cyl.setRect(QRectF(0, 0, 240, 120))
    assert cyl._label_anchor().y() > cyl.rect().center().y()


def test_mermaid_parse_core():
    # 핵심 부분집합: 방향·노드 모양 8종 매핑·엣지 4종·파이프 라벨.
    from easycad.fileio.mermaid_import import parse_mermaid
    g = parse_mermaid(
        "flowchart TD\n"
        "  A[start] --> B{cond}\n"
        "  B -->|yes| C([end])\n"
        "  B -->|no| D[retry]\n"
        "  D --> B\n"
        "  E[(db)] --- C\n")
    assert g.direction == "TD"
    assert set(g.nodes) == {"A", "B", "C", "D", "E"}
    assert g.nodes["B"].shape == "rhombus"
    assert g.nodes["C"].shape == "stadium"
    assert g.nodes["E"].shape == "cylinder"
    assert g.nodes["A"].label == "start"
    assert len(g.edges) == 5
    # 파이프 라벨 흡수
    yes = [e for e in g.edges if e.src == "B" and e.dst == "C"][0]
    assert yes.label == "yes" and yes.arrow is True
    # --- 는 화살촉 없는 선
    line = [e for e in g.edges if e.src == "E"][0]
    assert line.arrow is False


def test_mermaid_parse_lr_inline_and_styles():
    # LR 방향 + 인라인 라벨(-- txt -->) + 점선/굵은선 스타일 분류.
    from easycad.fileio.mermaid_import import parse_mermaid
    g = parse_mermaid(
        "graph LR\n"
        "  S([start]) -- go --> T[work]\n"
        "  T -.-> U{ok?}\n"
        "  U ==> V\n")
    assert g.direction == "LR"
    e_go = [e for e in g.edges if e.src == "S"][0]
    assert e_go.label == "go"
    assert [e for e in g.edges if e.src == "T"][0].style == "dotted"
    assert [e for e in g.edges if e.src == "U"][0].style == "thick"
    assert g.nodes["V"].label == "V"   # bare 참조는 id를 라벨로


def test_mermaid_layout_levels_no_cycle_blowup():
    # 사이클(D-->B)이 있어도 레벨이 발산하지 않는다(BFS 거리).
    from easycad.fileio.mermaid_import import parse_mermaid, layout_positions
    g = parse_mermaid("flowchart TD\n A-->B\n B-->C\n C-->B\n A-->D\n")
    pos = layout_positions(g, node_w=120, node_h=56)
    ys = {k: pos[k][1] for k in pos}
    assert ys["A"] < ys["B"]          # 레벨 0 < 레벨 1
    assert ys["B"] == ys["D"]         # 같은 레벨(둘 다 A의 자식/형제)
    assert max(ys.values()) < 1000    # 발산 없음(예전 버그는 y가 수천까지 치솟았음)


def test_mermaid_layout_lr_axis_swap():
    # LR은 흐름이 x축, TD는 y축.
    from easycad.fileio.mermaid_import import parse_mermaid, layout_positions
    g = parse_mermaid("flowchart LR\n A-->B-->C\n")
    pos = layout_positions(g, node_w=120, node_h=56)
    assert pos["A"][0] < pos["B"][0] < pos["C"][0]   # x 증가
    assert pos["A"][1] == pos["B"][1] == pos["C"][1]  # y 동일


def test_mermaid_empty_raises():
    from easycad.fileio.mermaid_import import parse_mermaid, MermaidError
    for bad in ("", "   \n  ", "flowchart TD\n"):
        try:
            parse_mermaid(bad)
            assert False, "MermaidError 기대"
        except MermaidError:
            pass


def test_mermaid_import_via_host():
    # 전체 빌더: 도형+화살표 개수·라벨·지속연결 바인딩·자동라우팅·단일 undo.
    w = CanvasWindow()
    n_nodes, n_arrows, direction = w._build_mermaid(
        "flowchart TD\n"
        "  A[시작] --> B{조건?}\n"
        "  B -->|예| C[처리]\n"
        "  B -->|아니오| D([종료])\n"
        "  C --> D\n"
        "  E[(DB)] --- C\n")
    assert direction == "TD"
    assert n_nodes == 5 and n_arrows == 5
    nodes = [it for it in w._scene.items()
             if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))]
    arrows = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(nodes) == 5 and len(arrows) == 5
    assert all(it.has_label() for it in nodes)               # 노드 라벨 부착
    assert all(a.has_binding() and a._auto_route for a in arrows)  # 지속연결+직교라우팅
    # 심볼 kind 매핑(마름모=decision, 스타디움=terminal, 원기둥=database)
    kinds = {it._kind for it in nodes if isinstance(it, _SymbolItem)}
    assert {"decision", "terminal", "database"} <= kinds
    assert len(w._undo) == 1                                  # 배치 전체가 한 번의 undo


def test_mermaid_labels_centered_not_stuck_at_origin():
    # 회귀: 라벨을 씬에 넣기 '전'에 붙이면 _sync_label이 no-op해 라벨이 도형 좌상단(0,0)에
    # 박힌다(초기 버그). 빌드 후 각 노드 라벨의 중심이 도형 중심 근방(가로 정렬, 세로는 광학보정
    # 허용)인지 확인 — (0,0)에 박히면 가로 오프셋이 도형 반폭만큼 크게 벌어진다.
    w = CanvasWindow()
    w._build_mermaid(
        "flowchart TD\n A[처리] --> B{유효?}\n B -->|예| C([끝])\n B -->|아니오| D[(저장)]\n")
    nodes = [it for it in w._scene.items()
             if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem)) and it._label is not None]
    assert len(nodes) == 4
    for it in nodes:
        sc = it.sceneBoundingRect().center()
        lc = it._label.sceneBoundingRect().center()
        assert abs(lc.x() - sc.x()) < 4, (it, lc, sc)     # 가로 중앙(0,0 박힘이면 크게 벗어남)
        assert abs(lc.y() - sc.y()) < 12, (it, lc, sc)    # 세로 중앙 근방(원기둥 광학보정 여유)


def test_mermaid_roundtrip():
    # import한 도면을 .ecad로 저장→열기 하면 노드·화살표가 보존된다(기존 직렬화 재사용).
    w = CanvasWindow()
    w._build_mermaid("flowchart LR\n A[a] --> B{b}\n B -->|x| C([c])\n")
    n0 = len([it for it in w._scene.items()
              if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))])
    a0 = len([it for it in w._scene.items() if isinstance(it, _PolyArrowItem)])
    path = os.path.join(_TMP, "mermaid.ecad")
    save_document(w._scene, path)
    w2 = CanvasWindow()
    load_document(w2._scene, path)
    n1 = len([it for it in w2._scene.items()
              if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))])
    a1 = len([it for it in w2._scene.items() if isinstance(it, _PolyArrowItem)])
    assert n1 == n0 == 3 and a1 == a0 == 2


def test_mermaid_pdf_export():
    # import 결과가 PDF로 렌더된다(paint 경로 안전).
    w = CanvasWindow()
    w._build_mermaid("flowchart TD\n A[a]-->B{b}\n B-->C([c])\n")
    out = os.path.join(_TMP, "mermaid.pdf")
    assert export_pdf(w._scene, out, page="A4") is True
    assert os.path.getsize(out) > 0


def test_sketch_argb_normalizes_color():
    # 빌더 색 정규화 → .ecad HexArgb(#AARRGGBB, alpha 먼저). Qt 비의존 순수 파이썬.
    assert _argb("#000000") == "#ff000000"        # 6자리 → 불투명 부여
    assert _argb("#FF3B30") == "#ffff3b30"         # 대문자·불투명
    assert _argb("#ff112233") == "#ff112233"       # 8자리 그대로
    assert _argb("#0f0") == "#ff00ff00"            # 3자리 확장


def test_sketch_build_roundtrip():
    # Phase 5 핵심: Sketch 빌더 → .ecad → load_document 왕복. 노드·심볼 kind·화살표 지속연결·
    # 라벨이 모두 편집가능 아이템으로 복원되는지. 빌더가 Qt 없이 만든 JSON을 앱이 그대로 연다.
    s = Sketch()
    a = s.symbol("terminal", 60, 40, 160, 70, "시작")
    b = s.symbol("decision", 90, 170, 120, 100, "조건?")
    c = s.box(300, 185, 160, 70, "처리")
    d = s.ellipse(90, 340, 120, 70, "끝")
    s.arrow(a, b)
    s.arrow(b, c, label="예")
    s.arrow(b, d, label="아니오")
    path = os.path.join(_TMP, "sketch.ecad")
    n = s.save(path)
    assert n == 7                                            # 노드 4 + 화살표 3

    w = CanvasWindow()
    load_document(w._scene, path)
    nodes = [it for it in w._scene.items()
             if isinstance(it, (_RectItem, _EllipseItem, _SymbolItem))]
    arrows = [it for it in w._scene.items() if isinstance(it, _PolyArrowItem)]
    assert len(nodes) == 4 and len(arrows) == 3
    # 심볼 kind 복원(마름모=decision, 스타디움=terminal)
    kinds = {it._kind for it in nodes if isinstance(it, _SymbolItem)}
    assert kinds == {"terminal", "decision"}
    # 화살표: 양끝 지속연결 + 직교 자동라우팅
    assert all(ar.has_binding() and ar._auto_route for ar in arrows)
    # 라벨: 노드 4개 전부 중앙 라벨 복원(0,0 박힘 아님 — 가로 중앙 정렬)
    labeled = [it for it in nodes if it._label is not None]
    assert len(labeled) == 4
    for it in labeled:
        sc = it.sceneBoundingRect().center()
        lc = it._label.sceneBoundingRect().center()
        assert abs(lc.x() - sc.x()) < 4, (it, lc, sc)


def test_sketch_arrow_binding_follows_move():
    # 지속연결 검증: 로드 후 화살표가 도형에 붙어 reroute(재라우팅)가 동작한다.
    s = Sketch()
    a = s.box(0, 0, 100, 60, "A")
    b = s.box(300, 0, 100, 60, "B")
    s.arrow(a, b)
    path = os.path.join(_TMP, "sketch_bind.ecad")
    s.save(path)
    w = CanvasWindow()
    load_document(w._scene, path)
    ar = next(it for it in w._scene.items() if isinstance(it, _PolyArrowItem))
    assert ar.has_binding()
    ar.reroute()                                            # 부착점 추종 + 직교 엘보(예외 없이)
    assert len(ar._pts) >= 2                                # 유효한 폴리라인 유지


def test_sketch_arrow_port_side_hint():
    # 밀집 순서도용: from_side/to_side로 접속 변을 명시하면 그 변 중점 포트에 붙는다
    # (피드백 루프를 본선과 겹치지 않게 측면으로 빼는 용도). 생략 시 최근접(기존 동작).
    s = Sketch()
    a = s.box(0, 0, 100, 60, "A")          # cx=50, cy=30
    b = s.box(0, 200, 100, 60, "B")        # cx=50, cy=230
    s.arrow(a, b)                          # 자동: a S(50,60) → b N(50,200)
    s.arrow(b, a, from_side="E", to_side="E")   # 루프: 둘 다 오른쪽 변으로
    doc = s.to_dict()
    down, loop = doc["items"][2], doc["items"][3]
    assert down["bind1_pt"] == [50.0, 60.0] and down["bind2_pt"] == [50.0, 200.0]
    assert loop["bind1_pt"] == [100.0, 230.0]   # b E
    assert loop["bind2_pt"] == [100.0, 30.0]    # a E
    # 잘못된 방향은 즉시 실패
    try:
        s.arrow(a, b, from_side="X")
        assert False, "잘못된 포트 방향이 통과됨"
    except ValueError:
        pass


def test_sketch_arrow_outer_channel():
    # 긴 루프백을 외곽 채널로 우회: channel_x면 명시 4점 경로 + auto_route=False
    # (코어 라우터가 다른 화살표를 장애물로 안 봐 생기는 내부 교차를 손수 회피).
    s = Sketch()
    a = s.box(0, 0, 100, 60, "A")          # A E=(100,30)
    b = s.box(0, 400, 100, 60, "B")        # B E=(100,430)
    s.arrow(b, a, from_side="E", to_side="E", channel_x=300)
    ar = s.to_dict()["items"][2]
    assert ar["auto_route"] is False
    assert ar["pts"] == [[100.0, 430.0], [300.0, 430.0], [300.0, 30.0], [100.0, 30.0]]
    assert ar["bind1"] == 1 and ar["bind2"] == 0        # 바인딩은 유지(끝점 추종)
    # 채널 2개 동시 지정은 실패
    try:
        s.arrow(a, b, channel_x=1, channel_y=1)
        assert False, "channel_x/y 동시 지정이 통과됨"
    except ValueError:
        pass


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"ALL {len(tests)} TESTS PASSED")


if __name__ == "__main__":
    _run_all()
