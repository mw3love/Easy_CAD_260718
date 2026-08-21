"""단축키 설정(§, 실사용 요청 2026-08-21) — 레지스트리(`shortcuts.py`) + 뷰 단축키
재바인딩(`core_view.py._shortcut_hit`) + 메뉴/툴바 QAction 라이브 갱신 + 설정 다이얼로그.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part12_shortcuts.py. `_isolated_shortcuts()`로 QSettings가 실사용자 값을
안 건드리게 격리(테스트 간에도 서로 오염 안 되게 매번 리셋).
"""
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QKeySequence
from PyQt6.QtTest import QTest

from _shared import *  # noqa: F401,F403
from easycad.canvas import shortcuts
from easycad.canvas.host_dialogs import _ShortcutSettingsDialog


# ---- 레지스트리 기본 동작 --------------------------------------------------

def test_default_sequence_matches_registry():
    with _isolated_shortcuts():
        assert shortcuts.default_sequence("tool_select") == "1"
        assert shortcuts.default_sequence("save_doc") == "Ctrl+S"
        assert shortcuts.default_sequence("no-such-id") == ""


def test_current_sequence_falls_back_to_default_when_unset():
    with _isolated_shortcuts():
        assert shortcuts.current_sequence("tool_rect") == "2"


def test_set_and_reset_sequence_roundtrip():
    with _isolated_shortcuts():
        shortcuts.set_sequence("tool_rect", "R")
        assert shortcuts.current_sequence("tool_rect") == "R"
        shortcuts.reset_sequence("tool_rect")
        assert shortcuts.current_sequence("tool_rect") == "2"


def test_reset_all_clears_every_override():
    with _isolated_shortcuts():
        shortcuts.set_sequence("tool_rect", "R")
        shortcuts.set_sequence("save_doc", "Ctrl+Shift+K")
        shortcuts.reset_all()
        assert shortcuts.current_sequence("tool_rect") == "2"
        assert shortcuts.current_sequence("save_doc") == "Ctrl+S"


def test_no_duplicate_ids_and_every_default_parses():
    ids = [d[0] for d in shortcuts.SHORTCUT_DEFS]
    assert len(ids) == len(set(ids))
    for sid, _cat, _label, default in shortcuts.SHORTCUT_DEFS:
        seq = QKeySequence(default)
        assert not seq.isEmpty(), f"{sid} 기본 시퀀스가 비어있음: {default!r}"


# ---- 뷰 단축키 — 실제 QKeyEvent로 검증 -------------------------------------

def test_tool_switch_default_key_works():
    with _isolated_shortcuts():
        w = CanvasWindow()
        w.set_tool("select")
        QTest.keyClick(w._view, Qt.Key.Key_2)
        assert w.current_tool == "rect"


def test_tool_switch_reassigned_key_replaces_default():
    with _isolated_shortcuts():
        w = CanvasWindow()
        shortcuts.set_sequence("tool_rect", "R")
        w.set_tool("select")
        QTest.keyClick(w._view, Qt.Key.Key_2)
        assert w.current_tool == "select"   # 옛 키는 더 이상 안 먹음
        QTest.keyClick(w._view, Qt.Key.Key_R)
        assert w.current_tool == "rect"


def test_tool_switch_ignores_extra_modifiers():
    with _isolated_shortcuts():
        w = CanvasWindow()
        w.set_tool("select")
        QTest.keyClick(w._view, Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
        assert w.current_tool == "select"   # Ctrl+2는 "2"와 다른 시퀀스라 매칭 안 됨


def test_delete_key_and_backspace_alias_both_delete():
    with _isolated_shortcuts():
        w = CanvasWindow()
        r = _mk_pen_rect(w)
        r.setSelected(True)
        QTest.keyClick(w._view, Qt.Key.Key_Backspace)
        assert r.scene() is None   # Backspace는 "delete" 재할당과 무관한 고정 별칭

        r2 = _mk_pen_rect(w)
        r2.setSelected(True)
        QTest.keyClick(w._view, Qt.Key.Key_Delete)
        assert r2.scene() is None


def test_undo_redo_default_and_shift_z_legacy_alias():
    with _isolated_shortcuts():
        w = CanvasWindow()
        r = _mk_pen_rect(w)
        w.push_undo_add_many([r])
        assert r.scene() is not None
        QTest.keyClick(w._view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert r.scene() is None
        QTest.keyClick(w._view, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        assert r.scene() is not None
        QTest.keyClick(w._view, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        assert r.scene() is None
        QTest.keyClick(w._view, Qt.Key.Key_Z,
                       Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        assert r.scene() is not None   # Ctrl+Shift+Z = redo 고정 별칭


# ---- QAction 배선 — display_only(undo/redo)와 실 단축키(save 등) 구분 -----

def test_undo_redo_actions_stay_display_only():
    with _isolated_shortcuts():
        w = CanvasWindow()
        assert w._act_undo.shortcut().isEmpty()
        assert w._act_redo.shortcut().isEmpty()
        assert "Ctrl+Z" in w._act_undo.toolTip()


def test_registered_actions_get_real_shortcut_and_tooltip():
    with _isolated_shortcuts():
        w = CanvasWindow()
        assert w._act_save.shortcut() == QKeySequence("Ctrl+S")
        assert "Ctrl+S" in w._act_save.toolTip()


def test_refresh_shortcut_ui_propagates_reassignment_to_action():
    with _isolated_shortcuts():
        w = CanvasWindow()
        shortcuts.set_sequence("save_doc", "Ctrl+Shift+K")
        w.refresh_shortcut_ui()
        assert w._act_save.shortcut() == QKeySequence("Ctrl+Shift+K")
        assert "Ctrl+Shift+K" in w._act_save.toolTip()


def test_refresh_shortcut_ui_updates_tool_button_tooltip_and_menu_text():
    # 상단 툴바 버튼은 rect/ellipse/sarrow는 안 담는다(좌측 팔레트가 담당) — 실제로
    # 담기는 도구(trim)로 검증.
    with _isolated_shortcuts():
        w = CanvasWindow()
        shortcuts.set_sequence("tool_trim", "Y")
        w.refresh_shortcut_ui()
        assert "(Y)" in w._tool_buttons["trim"].toolTip()
        assert w._tool_menu_actions["trim"].text().endswith("\tY")


# ---- 설정 다이얼로그 --------------------------------------------------------

def test_dialog_prefills_current_values():
    with _isolated_shortcuts():
        shortcuts.set_sequence("tool_rect", "R")
        w = CanvasWindow()
        dlg = _ShortcutSettingsDialog(w)
        assert dlg._edits["tool_rect"].keySequence() == QKeySequence("R")
        assert dlg._edits["tool_select"].keySequence() == QKeySequence("1")


def test_dialog_conflict_blocks_ok_until_resolved():
    with _isolated_shortcuts():
        w = CanvasWindow()
        dlg = _ShortcutSettingsDialog(w)
        ok_btn = dlg._btns.button(dlg._btns.StandardButton.Ok)
        assert ok_btn.isEnabled()
        dlg._edits["tool_rect"].setKeySequence(QKeySequence("1"))   # tool_select과 충돌
        assert not ok_btn.isEnabled()
        assert "사각형" in dlg._conflict_label.text() or "선택" in dlg._conflict_label.text()
        dlg._edits["tool_rect"].setKeySequence(QKeySequence("2"))
        assert ok_btn.isEnabled()


def test_dialog_accept_persists_and_prunes_default_values():
    with _isolated_shortcuts():
        w = CanvasWindow()
        dlg = _ShortcutSettingsDialog(w)
        dlg._edits["save_doc"].setKeySequence(QKeySequence("Ctrl+Shift+K"))
        dlg._on_accept()
        assert shortcuts.current_sequence("save_doc") == "Ctrl+Shift+K"
        # 다시 열어 기본값으로 되돌리면 QSettings 키 자체가 지워져야(reset_sequence) 함.
        dlg2 = _ShortcutSettingsDialog(w)
        dlg2._edits["save_doc"].setKeySequence(QKeySequence("Ctrl+S"))
        dlg2._on_accept()
        settings = QSettings(shortcuts._SETTINGS_ORG, shortcuts._SETTINGS_APP)
        assert settings.value("shortcuts/save_doc") in (None, "")


def test_dialog_reset_all_button_restores_defaults():
    with _isolated_shortcuts():
        shortcuts.set_sequence("tool_rect", "R")
        w = CanvasWindow()
        dlg = _ShortcutSettingsDialog(w)
        assert dlg._edits["tool_rect"].keySequence() == QKeySequence("R")
        dlg._reset_all_fields()
        for sid, edit in dlg._edits.items():
            assert edit.keySequence() == QKeySequence(shortcuts.default_sequence(sid))


def test_dialog_cancel_discards_changes():
    with _isolated_shortcuts():
        w = CanvasWindow()
        dlg = _ShortcutSettingsDialog(w)
        dlg._edits["save_doc"].setKeySequence(QKeySequence("Ctrl+Shift+K"))
        dlg.reject()
        assert shortcuts.current_sequence("save_doc") == "Ctrl+S"


def test_shortcut_settings_menu_action_exists():
    with _isolated_shortcuts():
        w = CanvasWindow()
        assert w._act_shortcut_settings.text() == "단축키 설정…"
