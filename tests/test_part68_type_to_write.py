"""데스크톱 손맛 = 웹 keys.js(2026-10-22) — 글이 들어가는 도형 하나를 고르고 바로 치면 그 도형의 글.

상자·원·심볼·닫힌 다각형·글은 있던 글을 새로 쓰고, 메모는 끝에 이어 씀. 숫자·Shift+H 같은 한 글자 단축키보다 먼저.
화살표·선이나 아무것도 안 골랐을 땐 지금처럼 단축키. 한글 입력기는 그런 도형을 골랐을 때만 칠판에 붙음(아니면 한글 모드에서도 Z·T가 먹음).
"""
import copy

from _shared import _app  # noqa: F401  (QApplication)
from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QInputMethodEvent, QKeyEvent

from test_part66_desktop_web_kinds import COMMON, DOCS, _win_with

NO, SHIFT = Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ShiftModifier
RECT = {**COMMON, "type": "rect", "pos": [0, 0], "rect": [0, 0, 160, 80], "pen": "#ff000000", "width": 1.0, "style": 1, "fill": None,
        "label": {"text": "옛 글", "color": "#ff000000", "font": 12, "bg": None}}
ARROW = {**COMMON, "type": "line", "pos": [300, 0], "line": [0, 0, 120, 0], "pen": "#ff000000", "width": 1.0, "style": 1}


def _key(v, key, text, mods=NO):
    v.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, mods, text))


def _label(it):
    return it._label.toPlainText() if it._label_alive() else ""


def test_typing_on_selected_shape_rewrites_its_text_even_digits_and_shift_h():
    w, (r,) = _win_with(RECT)
    v = w._view
    try:
        r.setSelected(True)
        _key(v, Qt.Key.Key_1, "1")                                                      # 도구 1(선택)이 아니라 글
        _key(v, Qt.Key.Key_unknown, "번")
        fi = w._scene.focusItem()
        assert fi is r._label and _label(r) == "1번" and w.current_tool == "select"
        fi.clearFocus()
        r.setSelected(True)
        ov = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_H, SHIFT, "H")
        ov.ignore()
        v.event(ov)
        assert ov.isAccepted()                                                          # Shift+H = 글(창의 좌우 반전보다 먼저)
    finally:
        w.close()


def test_typing_on_memo_appends_and_on_line_or_nothing_keeps_shortcuts():
    w, (memo, ln) = _win_with({**copy.deepcopy(DOCS["memo"]), "lines": [{"k": "p", "t": "있던 글"}]}, ARROW)
    v = w._view
    try:
        memo.setSelected(True)
        _key(v, Qt.Key.Key_A, "a")
        ed = v._memo_editor
        assert ed is not None and ed.toPlainText() == "있던 글a"                       # 메모 = 끝에 이어 씀
        ed.commit()
        w._scene.clearSelection()
        ln.setSelected(True)
        assert v._type_target() is None                                                  # 선 = 글 도형 아님 → 단축키 그대로
        w._scene.clearSelection()
        _key(v, Qt.Key.Key_2, "2")
        assert w.current_tool == "sarrow" and w._scene.focusItem() is None               # 아무것도 안 골랐을 때 2 = 화살표 도구
    finally:
        w.close()


def test_korean_ime_attaches_only_for_type_target_and_first_syllable_opens_edit():
    w, (r, ln) = _win_with(RECT, ARROW)
    v = w._view
    try:
        assert v.inputMethodQuery(Qt.InputMethodQuery.ImEnabled) is False               # 안 골랐을 땐 입력기 안 붙음(한글 모드에서도 Z·T)
        ln.setSelected(True)
        assert v.inputMethodQuery(Qt.InputMethodQuery.ImEnabled) is False
        w._scene.clearSelection()
        r.setSelected(True)
        assert v.inputMethodQuery(Qt.InputMethodQuery.ImEnabled) is True
        assert v.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled)
        v.inputMethodEvent(QInputMethodEvent("ㄱ", []))                                 # 조합 첫 글자 = 그 도형 글 고치기를 열고 넘김
        assert w._scene.focusItem() is r._label
        e = QInputMethodEvent()
        e.setCommitString("가")
        v.inputMethodEvent(e)
        assert _label(r) == "가"
    finally:
        w.close()


def test_ctrl_x_cuts_with_one_undo_and_paste_returns_to_same_place():
    w, (r,) = _win_with(RECT)
    v = w._view
    try:
        r.setSelected(True)
        pos0 = r.pos()
        v.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier, ""))
        assert r.scene() is None
        w.paste_selection()
        pasted = w._scene.selectedItems()
        assert len(pasted) == 1 and pasted[0].pos() == pos0                              # 잘라 붙이면 원래 자리
        w.undo()
        w.undo()
        assert r.scene() is w._scene                                                     # 잘라내기도 Ctrl+Z 한 칸
    finally:
        w.close()


def test_z_twice_returns_to_previous_view_and_alt_z_fits_selection():
    far = {**RECT, "pos": [3000, 2000]}
    w, (r, r2) = _win_with(RECT, far)
    try:
        v = w._view
        v.resetTransform()
        v.scale(2.0, 2.0)
        v.centerOn(r)
        before = (v.transform().m11(), v.mapToScene(v.viewport().rect().center()))
        w._zoom_fit()
        assert v.transform().m11() < 1.0                                                 # 다 보기 = 멀리 있는 것까지
        w._zoom_fit()                                                                    # 한 번 더 = 보던 자리로
        after = (v.transform().m11(), v.mapToScene(v.viewport().rect().center()))
        assert abs(after[0] - before[0]) < 1e-9 and (after[1] - before[1]).manhattanLength() < 2   # centerOn 반올림(화면 1px)
        w._zoom_fit()
        v.scale(1.1, 1.1)                                                                # 그 사이 화면을 움직이면
        w._zoom_fit()
        assert v.transform().m11() < 1.0                                                 # 다시 다 보기(돌아가지 않음)
        r2.setSelected(True)
        w._zoom_fit_selection()                                                          # Alt+Z = 고른 것만
        c = v.mapToScene(v.viewport().rect().center())
        assert (c - r2.sceneBoundingRect().center()).manhattanLength() < 2 and v.transform().m11() > 1.0
    finally:
        w.close()


def test_double_click_empty_area_places_text_there():
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QMouseEvent
    from easycad.canvas.core_shapes import _TextItem
    w, _ = _win_with()
    v = w._view
    try:
        vp = v.viewport().rect().center()
        v.mouseDoubleClickEvent(QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(vp), QPointF(v.viewport().mapToGlobal(vp)),
                                            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, NO))
        fi = w._scene.focusItem()
        assert isinstance(fi, _TextItem) and fi.sceneBoundingRect().contains(v.mapToScene(vp)) and w.current_tool == "select"
    finally:
        w.close()


# ---- 표 칸 고르기(웹 cellSel) ----
def _table_win():
    from PyQt6.QtCore import QRectF
    from easycad.canvas.core_shapes import _TableItem
    w, _ = _win_with()
    t = _TableItem(3, 3, QRectF(0, 0, 300, 90), [["가", "나", "다"], ["1", "2", "3"], ["", "", ""]])
    t.setFlags(t.GraphicsItemFlag.ItemIsMovable | t.GraphicsItemFlag.ItemIsSelectable)
    w._scene.addItem(t)
    w._view.centerOn(t)
    t.setSelected(True)
    return w, t


def _click(w, scene_pt, mods=NO):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QMouseEvent
    v = w._view
    vp = v.mapFromScene(scene_pt)
    g = v.viewport().mapToGlobal(vp)
    v.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(vp), QPointF(g), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, mods))
    v.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, QPointF(vp), QPointF(g), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, mods))


def _cell_pt(t, r, c):
    return t.mapToScene(t.cell_rect(r, c).center())


def test_click_selected_table_picks_cell_shift_extends_and_arrows_move():
    w, t = _table_win()
    v = w._view
    try:
        _click(w, _cell_pt(t, 1, 1))                                                     # 고른 표의 칸을 한 번 더 = 그 칸
        assert v._cell_sel and (v._cell_sel["r0"], v._cell_sel["c0"]) == (1, 1)
        _click(w, _cell_pt(t, 2, 2), SHIFT)                                              # Shift = 범위
        assert v._cell_range() == (1, 2, 1, 2)
        _key(v, Qt.Key.Key_Left, "")                                                     # 방향키 = 옆 칸(범위는 풀림)
        assert v._cell_range() == (1, 1, 0, 0)
        _key(v, Qt.Key.Key_Down, "", SHIFT)                                              # Shift+방향키 = 넓히기
        assert v._cell_range() == (1, 2, 0, 0)
        w._scene.clearSelection()                                                        # 표를 안 고르면 칸 고르기도 풂
        assert v._cell_sel is None
    finally:
        w.close()


def test_cell_keys_type_fresh_enter_continue_delete_with_undo():
    w, t = _table_win()
    v = w._view
    try:
        _click(w, _cell_pt(t, 0, 0))
        _key(v, Qt.Key.Key_X, "x")                                                       # 글자 = 그 칸에 새로 씀
        ed = v._cell_editor
        assert ed.text() == "x"
        ed._commit(); ed.close()
        assert t.cell_text(0, 0) == "x"
        w.undo()
        assert t.cell_text(0, 0) == "가"                                                 # 칸 고치기도 Ctrl+Z 한 칸(전엔 되돌리기 밖)
        t.setSelected(True)
        _click(w, _cell_pt(t, 0, 1))
        _key(v, Qt.Key.Key_F2, "")                                                       # F2 = 이어 고치기(커서 끝)
        ed = v._cell_editor
        assert ed.text() == "나" and not ed.hasSelectedText() and ed.cursorPosition() == 1
        ed._commit(); ed.close()
        t.setSelected(True)
        _click(w, _cell_pt(t, 1, 0))
        _click(w, _cell_pt(t, 1, 2), SHIFT)
        _key(v, Qt.Key.Key_Delete, "")                                                   # Del = 칸 글만(표는 그대로)
        assert [t.cell_text(1, c) for c in range(3)] == ["", "", ""] and t.scene() is w._scene
        w.undo()
        assert [t.cell_text(1, c) for c in range(3)] == ["1", "2", "3"]
    finally:
        w.close()


def test_cell_selected_attaches_ime_and_korean_opens_cell_editor():
    w, t = _table_win()
    v = w._view
    try:
        assert v.inputMethodQuery(Qt.InputMethodQuery.ImEnabled) is False               # 표만 고름 = 글 도형 아님
        _click(w, _cell_pt(t, 2, 0))
        assert v.inputMethodQuery(Qt.InputMethodQuery.ImEnabled) is True
        v.inputMethodEvent(QInputMethodEvent("ㄱ", []))
        assert v._cell_editor is not None and v._cell_editor.isVisible()
    finally:
        w.close()


# ---- 위 막대 버튼을 칠판으로 끌어 놓기(웹 startToolDrag) ----
def _tb_drag(w, btn, vp_pt, release=True):
    """버튼에 누르기 → (6px 넘게) 끌기 → 칠판 vp_pt에서 놓기 — 이벤트를 버튼에 직접(화면 커서 안 건드림)."""
    from PyQt6.QtCore import QPoint, QPointF
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication
    vp = w._view.viewport()
    start = btn.rect().center()
    g0, g1 = btn.mapToGlobal(start), vp.mapToGlobal(vp_pt)

    def ev(t, g, b, bs):
        return QMouseEvent(t, QPointF(btn.mapFromGlobal(g)), QPointF(g), b, bs, NO)
    L = Qt.MouseButton.LeftButton
    QApplication.sendEvent(btn, ev(QEvent.Type.MouseButtonPress, g0, L, L))
    for f in (0.02, 0.3, 0.7, 1.0):
        QApplication.sendEvent(btn, ev(QEvent.Type.MouseMove, g0 + (g1 - g0) * f, Qt.MouseButton.NoButton, L))
    if release:
        QApplication.sendEvent(btn, ev(QEvent.Type.MouseButtonRelease, g1, L, Qt.MouseButton.NoButton))
    QApplication.processEvents()


def _tb_win():
    w, _ = _win_with()
    sp = getattr(w, "_start_prompt", None)
    if sp is not None:
        sp.hide()                                                                        # 가운데 「무엇을 그릴까요?」 칸(패널 위는 놓기 취소)
    btns = {k: b for b, k in w._toolbar_drag._keys.items()}
    return w, btns


def test_toolbar_buttons_drag_to_board_place_default_item_at_drop():
    from PyQt6.QtCore import QPoint
    from easycad.canvas.core_shapes import _BadgeItem, _LineItem, _PolyArrowItem, _TableItem
    from easycad.canvas.core_web import _MemoItem
    w, btns = _tb_win()
    v = w._view
    try:
        assert set(btns) == {"arrow", "text", "line", "badge", "memo", "table", "polygon"}
        for i, (k, cls) in enumerate((("arrow", _PolyArrowItem), ("line", _LineItem), ("badge", _BadgeItem), ("memo", _MemoItem), ("table", _TableItem))):
            pt = QPoint(400 + (i % 3) * 300, 200 + (i // 3) * 300)
            _tb_drag(w, btns[k], pt)
            made = [it for it in w._scene.items() if type(it) is cls and it.parentItem() is None]
            assert len(made) == 1, k
            it = made[0]
            assert it.sceneBoundingRect().adjusted(-30, -30, 30, 30).contains(v.mapToScene(pt)), k   # 놓은 자리(가운데)에
            assert it.opacity() == 1.0 and it.isSelected(), k                                  # 확정 — 반투명 아님, 골라진 채
        assert w.current_tool == "select"                                                        # 도구는 안 바뀜(끌기 = 놓기만)
        w.undo()
        assert not [it for it in w._scene.items() if type(it) is _TableItem]                     # 하나씩 Ctrl+Z 한 칸
    finally:
        w.close()


def test_toolbar_text_drag_opens_empty_text_at_drop_and_click_still_works():
    from PyQt6.QtCore import QPoint
    from easycad.canvas.core_shapes import _TextItem
    w, btns = _tb_win()
    try:
        _tb_drag(w, btns["text"], QPoint(500, 300))
        fi = w._scene.focusItem()
        assert isinstance(fi, _TextItem) and fi.toPlainText() == ""                              # 「글」은 끄는 동안만 — 놓으면 빈 글 상자에 바로 쓰기
        fi.clearFocus()
        btns["line"].click()                                                                     # 그냥 누르기 = 지금처럼 도구 켜기
        assert w.current_tool == "line"
        _tb_drag(w, btns["memo"], QPoint(-50, -50))                                              # 칠판 밖에 놓으면 취소
        assert not [it for it in w._scene.items() if type(it).__name__ == "_MemoItem"]
    finally:
        w.close()


def test_toolbar_polygon_drag_places_first_segment_then_continues_clicking():
    from PyQt6.QtCore import QPoint
    from PyQt6.QtTest import QTest
    from easycad.canvas.core_shapes import _LineItem, _PolygonItem
    w, btns = _tb_win()
    v = w._view
    try:
        _tb_drag(w, btns["polygon"], QPoint(500, 300))
        assert w.current_tool == "polygon"                                                       # 웹처럼 다각형 도구로
        it = v._place
        assert isinstance(it, _PolygonItem) and len(it._draw_pts) == 3                           # 확정 2점 + 커서 추종
        a, b = it._draw_pts[0], it._draw_pts[1]
        c = v.mapToScene(QPoint(500, 300))
        assert abs((a.x() + b.x()) / 2 - c.x()) < 30 and abs(a.y() - b.y()) < 1e-6              # 놓은 자리 가운데, 가로 선분
        assert abs(v.mapFromScene(b).x() - v.mapFromScene(a).x() - 120) <= 2                     # 화면 120px
        assert not [x for x in w._scene.items() if type(x) is _LineItem]                         # 끄는 동안 미리보기는 지워짐
        _click(w, v.mapToScene(QPoint(560, 420)))                                                # 이어 찍기
        QTest.keyClick(v, Qt.Key.Key_Return)                                                     # Enter = 끝
        made = [x for x in w._scene.items() if type(x) is _PolygonItem]
        assert len(made) == 1 and v._place is None
        w.undo()
        assert not [x for x in w._scene.items() if type(x) is _PolygonItem]                      # Ctrl+Z 한 번
    finally:
        w.close()
