"""점검 2단계(2026-10-03) — 되돌리기 왕복 퍼즈·실제 창 재현에서 찾은 문제들의 회귀 테스트.

- 지웠다/바꿨다 되돌리면 겹침 순서가 맨 위로 올라가던 것(`document._DocScene`·`_apply_entry`)
- 미완성 화살표(점 1개)를 씬에서 뺄 때 앱이 죽지 않을 것(위 기록이 boundingRect를 안 부름)
- 화살표만 붙여넣기/복제하면 원본 도형에 연결된 채 떠 있던 것(`drop_outside_bindings`)
- 연결된 화살표를 통째로 옮기면 연결이 풀리고, 되돌리면 다시 붙을 것(`push_undo_move`)
- 방향키 이동 뒤 되돌리기→다시실행이 한 칸 덜 가던 것(core_view 방향키 기록 순서)
- 클립보드가 None을 줄 때 Ctrl+V 오류(`_clipboard_pixmap`), 옛 파일 변환 뒤 선택 잔존"""
import os
from unittest.mock import patch

from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QPen
from PyQt6.QtWidgets import QApplication

from _shared import *  # noqa: F401,F403

from easycad.canvas import host_widgets


def _tops(w):
    return [it for it in w._scene.items() if it.parentItem() is None]   # 위→아래


def _filled_rect(w, x, y, ww, hh):
    it = _mk_pen_rect(w, x=x, y=y, ww=ww, hh=hh)
    it.setBrush(QBrush(QColor("#3366cc")))
    return it


def _bound_arrow(w, a, b):
    ar = _ArrowItem(QColor("#111111"), 2, True)
    pa = QPointF(a.rect().right(), a.rect().center().y())
    pb = QPointF(b.rect().left(), b.rect().center().y())
    ar.set_points(a.mapToScene(pa), b.mapToScene(pb))
    ar.set_bound(0, a, pa); ar.set_bound(1, b, pb)
    ar.setFlags(ar.GraphicsItemFlag.ItemIsSelectable | ar.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(ar)
    return ar


# ---- 겹침 순서 ---------------------------------------------------------------
def test_delete_undo_keeps_filled_shape_below():
    w = CanvasWindow()
    big = _filled_rect(w, 0, 0, 200, 200)
    small = _mk_pen_rect(w, x=50, y=50, ww=40, hh=40)   # 나중에 추가 = 위
    assert _tops(w) == [small, big]
    w._scene.clearSelection(); big.setSelected(True); w.delete_selection()
    w.undo()
    assert _tops(w) == [small, big]   # 예전: [big, small] — 채운 큰 상자가 작은 상자를 가림
    w.redo(); w.undo()
    assert _tops(w) == [small, big]


def test_swap_undo_keeps_stacking():
    w = CanvasWindow()
    big = _filled_rect(w, 0, 0, 200, 200)
    small = _mk_pen_rect(w, x=50, y=50, ww=40, hh=40)
    w._scene.clearSelection(); big.setSelected(True); w._swap_selected("ellipse")
    w.undo()
    assert _tops(w) == [small, big]


def test_batch_delete_undo_restores_three_level_stack():
    """함께 지운 아이템들은 되살리는 순서와 무관하게 원래 위아래로 — 위쪽 것부터 자리를 잡는다."""
    w = CanvasWindow()
    a = _filled_rect(w, 0, 0, 100, 100)
    b = _filled_rect(w, 20, 20, 100, 100)
    c = _filled_rect(w, 40, 40, 100, 100)
    assert _tops(w) == [c, b, a]
    w._scene.clearSelection()
    for it in (a, b, c):
        it.setSelected(True)
    w.delete_selection(); w.undo()
    assert _tops(w) == [c, b, a]


def test_removing_one_point_arrow_does_not_crash():
    """화살표 그리기를 Esc로 끝내는 순간처럼 점이 1개뿐인 아이템을 빼도 앱이 죽지 않아야 한다
    (회귀하면 이 테스트에서 프로세스가 exit 127로 죽는다)."""
    w = CanvasWindow()
    pa = _PolyArrowItem(QColor("#111111"), 2, True)
    pa._pts = [QPointF(0, 0)]
    w._scene.addItem(pa)
    w._scene.removeItem(pa)
    assert pa.scene() is None


# ---- 붙여넣기·복제 사본의 연결 ------------------------------------------------
def test_paste_lone_bound_arrow_becomes_free():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=300, y=0)
    ar = _bound_arrow(w, a, b)
    w._scene.clearSelection(); ar.setSelected(True)
    w.copy_selection(); w.paste_selection()
    new = [it for it in w._scene.selectedItems()][0]
    assert new is not ar
    assert new._bind1 is None and new._bind2 is None
    assert ar._bind1 is a and ar._bind2 is b


def test_duplicate_keeps_inside_binding_drops_outside():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=300, y=0)
    ar = _bound_arrow(w, a, b)
    w._scene.clearSelection(); b.setSelected(True); ar.setSelected(True)   # a는 같이 안 복제
    w.duplicate_selection()
    new_ar = [it for it in w._scene.selectedItems() if isinstance(it, _ArrowItem)][0]
    new_b = [it for it in w._scene.selectedItems() if isinstance(it, _RectItem)][0]
    assert new_ar._bind1 is None          # 같이 복제 안 된 a와의 연결은 풂
    assert new_ar._bind2 is new_b         # 같이 복제된 b의 사본에는 다시 연결


# ---- 연결된 화살표 통째 이동 ---------------------------------------------------
def test_moving_bound_arrow_alone_detaches_and_undo_reattaches():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=300, y=0)
    ar = _bound_arrow(w, a, b)
    old = QPointF(ar.pos())
    ar.moveBy(40, 0)
    w.push_undo_move([(ar, old)])
    assert ar._bind1 is None and ar._bind2 is None
    w.undo()
    assert ar.pos() == old and ar._bind1 is a and ar._bind2 is b
    w.redo()
    assert ar.pos() == old + QPointF(40, 0) and ar._bind1 is None


def test_moving_arrow_with_its_shapes_keeps_binding():
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=300, y=0)
    ar = _bound_arrow(w, a, b)
    pairs = [(it, QPointF(it.pos())) for it in (a, b, ar)]
    for it in (a, b, ar):
        it.moveBy(40, 0)
    w.push_undo_move(pairs)
    assert ar._bind1 is a and ar._bind2 is b
    pairs = [(it, QPointF(it.pos())) for it in (a, ar)]   # 한쪽 도형만 같이 이동
    for it in (a, ar):
        it.moveBy(0, 30)
    w.push_undo_move(pairs)
    assert ar._bind1 is a and ar._bind2 is None


def _press(view, key):
    from PyQt6.QtTest import QTest
    view.setFocus()
    QTest.keyClick(view.viewport(), key)


def test_arrow_key_nudge_redo_goes_full_distance():
    w = CanvasWindow(); w.show()
    r = _mk_pen_rect(w, x=0, y=0)
    w._scene.clearSelection(); r.setSelected(True)
    x0 = r.pos().x()
    _press(w._view, Qt.Key.Key_Right)
    w.undo(); assert r.pos().x() == x0
    w.redo(); assert r.pos().x() == x0 + 10    # 예전: 제자리(기록이 이동 전에 실렸음)
    r2 = _mk_pen_rect(w, x=0, y=200)           # 연속 3번 = 되돌리기 1번, 다시실행은 3칸 다
    w._scene.clearSelection(); r2.setSelected(True)
    y0 = r2.pos().x()
    for _ in range(3):
        _press(w._view, Qt.Key.Key_Right)
    w.undo(); assert r2.pos().x() == y0
    w.redo(); assert r2.pos().x() == y0 + 30   # 예전: 20(한 칸 덜 감)


def test_arrow_key_nudge_of_bound_arrow_coalesces_with_detach():
    w = CanvasWindow(); w.show()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=300, y=0)
    ar = _bound_arrow(w, a, b)
    old = QPointF(ar.pos())
    w._scene.clearSelection(); ar.setSelected(True)
    for _ in range(3):
        _press(w._view, Qt.Key.Key_Right)
    assert ar._bind1 is None and ar.pos() == old + QPointF(30, 0)
    w.undo()   # 연속 방향키 = 되돌리기 1번
    assert ar.pos() == old and ar._bind1 is a and ar._bind2 is b
    w.redo()
    assert ar.pos() == old + QPointF(30, 0) and ar._bind1 is None


# ---- 클립보드·옛 파일 -----------------------------------------------------------
def test_clipboard_pixmap_handles_none_mimedata():
    class _CB:
        def pixmap(self): return QPixmap()
        def image(self): return QPixmap().toImage()
        def mimeData(self): return None
    with patch.object(QApplication, "clipboard", staticmethod(lambda: _CB())):
        assert host_widgets._clipboard_pixmap() is None


def test_legacy_cut_migration_leaves_nothing_selected():
    w = CanvasWindow(); w.grid_enabled = False
    legacy = _mk_pen_rect(w, x=0, y=0, ww=600, hh=400)
    legacy._cuts = [(0, 0.2, 0.5)]
    w._migrate_legacy_closed_cuts()
    assert w._scene.selectedItems() == []


# ---- 대량 삭제·되돌리기 성능(점검 2단계 후속) ---------------------------------------
def _grid_doc(n=60):
    w = CanvasWindow()
    items = []
    for i in range(n):
        it = _filled_rect(w, (i % 10) * 30, (i // 10) * 30, 50, 50)   # 이웃끼리 겹침
        items.append(it)
    return w, items


def test_mass_delete_and_undo_refresh_properties_once():
    """선택된 아이템을 하나씩 빼고 넣을 때마다 속성 패널을 다시 계산하던 O(n²) — 1000개 전체
    삭제 8.4초·되돌리기 8.7초였다. 이제 일괄 편집 동안 신호를 끊고 끝에 한 번만 갱신."""
    w, items = _grid_doc()
    w.select_all()
    calls = []
    orig = w._refresh_properties
    with patch.object(w, "_refresh_properties", side_effect=lambda: (calls.append(1), orig())):
        # selectionChanged에 이미 연결된 건 원래 바운드 메서드라, 일시정지 해제 시 재연결되는
        # 쪽을 세려면 시그널을 패치된 것으로 다시 잇는다.
        sig = w._scene.selectionChanged
        sig.disconnect(orig); sig.connect(w._refresh_properties)
        w.delete_selection()
        n_del = len(calls); calls.clear()
        w.undo()
        n_undo = len(calls)
        sig.disconnect(w._refresh_properties); sig.connect(orig)
    assert n_del <= 2 and n_undo <= 2, (n_del, n_undo)
    assert len(w._scene.selectedItems()) == len(items)   # 되돌리면 선택도 그대로


def test_mass_delete_undo_restores_exact_full_stacking():
    w, items = _grid_doc()
    before = _tops(w)
    w.select_all(); w.delete_selection(); w.undo()
    assert _tops(w) == before
    w.redo(); w.undo()
    assert _tops(w) == before


def test_partial_delete_undo_keeps_full_stacking():
    w, items = _grid_doc()
    before = _tops(w)
    w._scene.clearSelection()
    for it in items[::3]:
        it.setSelected(True)
    w.delete_selection(); w.undo()
    assert _tops(w) == before


def _pump():
    for _ in range(3):
        QApplication.processEvents()


def test_undo_of_full_delete_skips_reroute_of_revived_arrows():
    """되돌리기로 함께 되살아난 화살표는 지워질 때 경로 그대로 — 다시 A*를 돌리지 않는다
    (1000개 전체삭제 되돌리기에서 A* 500회·실화면 2.6초 → 0.6초)."""
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=300, y=100)
    ar = _bound_arrow(w, a, b)
    _pump()
    before = (QPointF(ar._p1), QPointF(ar._p2))
    w.select_all(); w.delete_selection(); _pump()
    calls = []
    orig = type(ar).reroute
    with patch.object(type(ar), "reroute", lambda self, *x, **k: (calls.append(self), orig(self, *x, **k))[1]):
        w.undo(); _pump()
    assert ar not in calls
    assert (ar._p1, ar._p2) == before and ar._bind1 is a and ar._bind2 is b
    assert w._active_doc.skip_reroute_once == set()   # 한 번 쓰고 비움


def test_undo_of_shape_only_delete_still_reroutes_remaining_arrow():
    """도형만 지웠다 되돌리면(화살표는 안 지움) 그 화살표는 되살아난 게 아니므로 평소처럼 다시
    계산돼 도형에 붙는다 — 건너뛰기는 '함께 되살아난 화살표'에만."""
    w = CanvasWindow()
    a = _mk_pen_rect(w, x=0, y=0); b = _mk_pen_rect(w, x=300, y=100)
    ar = _bound_arrow(w, a, b)
    _pump()
    w._scene.clearSelection(); b.setSelected(True); w.delete_selection(); _pump()
    b_old = QPointF(b.pos())
    calls = []
    orig = type(ar).reroute
    with patch.object(type(ar), "reroute", lambda self, *x, **k: (calls.append(self), orig(self, *x, **k))[1]):
        w.undo(); _pump()
    assert ar in calls
    assert b.pos() == b_old and ar._bind2 is b
