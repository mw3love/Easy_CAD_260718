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
