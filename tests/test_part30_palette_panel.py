"""[실사용 피드백 2026-10-11] 도형·심볼 카드 정리 — 스크롤 위치 유지 · 폴더마다 처음 보이는 개수(손잡이)·
「더 보기」·크게 보기 창 · 카드 높이(창 절반·손잡이·제목 더블클릭) · 레이어 카드 버튼 아이콘."""
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QInputDialog, QToolButton
from unittest.mock import patch

from _shared import *  # noqa: F401,F403
from easycad.app_settings import app_settings
from easycad.canvas.host_ui import _FOLDER_ROWS_DEFAULT
from easycad.canvas.host_widgets import _DragGrip
from easycad.fileio import symbol_library


def _fill(folder, n):
    symbol_library.create_folder(folder)
    return [symbol_library.add_symbol(f"{folder}{i}", [], "", folder=folder) for i in range(n)]


def _folder_section(w, folder):
    lay = w._custom_sym_body.layout()
    zone = next(lay.itemAt(i).widget() for i in range(lay.count())
                if getattr(lay.itemAt(i).widget(), "_folder", None) == folder)
    return zone.layout().itemAt(0).widget()


def _drag(grip, dy):
    """손잡이를 dy px 끈다(누름 → 이동 → 놓음)."""
    def ev(kind, y, button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton):
        p = QPointF(5, 4)
        g = QPointF(grip.mapToGlobal(p.toPoint())) + QPointF(0, y)
        return QMouseEvent(kind, p, g, button, buttons, Qt.KeyboardModifier.NoModifier)
    grip.mousePressEvent(ev(QEvent.Type.MouseButtonPress, 0))
    grip.mouseMoveEvent(ev(QEvent.Type.MouseMove, dy, Qt.MouseButton.NoButton))
    grip.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, dy, buttons=Qt.MouseButton.NoButton))


def test_folder_shows_first_six_then_more_button_and_grip_changes_count():
    with _isolated_symbol_library():
        ents = _fill("장비", 10)
        st = app_settings()
        st.remove("symfolder_rows_장비")
        try:
            w = CanvasWindow()
            w.show()
            btns = [w._custom_sym_buttons[e["id"]][0] for e in ents]
            sec = _folder_section(w, "장비")
            assert [b.isVisibleTo(sec) for b in btns] == [True] * _FOLDER_ROWS_DEFAULT + [False] * 4
            more = next(b for b in w._folder_more_btns if b.isVisibleTo(sec))
            assert more.text() == "더 보기 (+4)" and not more.icon().isNull()
            grip = sec.findChild(_DragGrip)
            _drag(grip, 2 * btns[0].height())                      # 두 줄 아래로 → 8개
            assert sum(b.isVisibleTo(sec) for b in btns) == 8 and more.text() == "더 보기 (+2)"
            assert st.value("symfolder_rows_장비", type=int) == 8  # 폴더마다 기억
            _drag(grip, 10 * btns[0].height())                     # 끝까지 → 전부, 「더 보기」 사라짐
            assert all(b.isVisibleTo(sec) for b in btns) and not more.isVisibleTo(sec)
            w2 = CanvasWindow()                                     # 다음 창에도 그 개수
            sec2 = _folder_section(w2, "장비")
            assert all(w2._custom_sym_buttons[e["id"]][0].isVisibleTo(sec2) for e in ents)
            grip.mouseDoubleClickEvent(QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(5, 4), QPointF(5, 4),
                                                   Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                                   Qt.KeyboardModifier.NoModifier))
            assert sum(b.isVisibleTo(sec) for b in btns) == _FOLDER_ROWS_DEFAULT
            assert not st.contains("symfolder_rows_장비")
            w._active_doc.dirty = False
            w.close()
        finally:
            st.remove("symfolder_rows_장비")


def test_small_folder_has_no_grip_or_more_button():
    with _isolated_symbol_library():
        _fill("하나", 1)
        w = CanvasWindow()
        sec = _folder_section(w, "하나")
        assert sec.findChild(_DragGrip) is None and not w._folder_more_btns


def test_more_button_opens_big_browser_with_all_symbols():
    with _isolated_symbol_library():
        ents = _fill("장비", 10)
        _fill("전원", 2)
        w = CanvasWindow()
        w.show()
        sec = _folder_section(w, "장비")
        more = next(b for b in w._folder_more_btns if b.isVisibleTo(sec))
        more.click()
        b = w._symbol_browser
        assert b.isVisible() and not b.isModal() and b.folder == "장비"
        assert len(b._buttons) == 10 and b._count.text() == "10개"
        assert all(x.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonTextUnderIcon and x.text() for x in b._buttons)
        b.resize(700, 400); QApplication.instance().processEvents(); b._cols = 0; b._reflow()
        assert b._cols >= 5                                         # 넓히면 줄당 칸이 늘어난다
        # 칸 클릭 = 도구로 쥐기, 패널과 체크 상태 같이
        b._buttons[3].click()
        assert w.current_tool == f"customsym:{ents[3]['id']}" and b._buttons[3].isChecked()
        w.set_tool(None)
        assert not b._buttons[3].isChecked()
        # 폴더 바꾸기·라이브러리 바뀌면 따라 다시 그림
        b._combo.setCurrentText("전원")
        assert len(b._buttons) == 2
        with patch.object(QInputDialog, "getText", return_value=("새이름", True)):
            w._rename_custom_symbol_prompt(symbol_library.load_library()[-1]["id"])
        assert "새이름" in [x._full_name for x in b._buttons]
        # 폴더 ⋯ 메뉴의 「크게 보기」도 같은 창
        w._open_symbol_browser("장비")
        assert w._symbol_browser is b and b.folder == "장비"
        b.close()
        w._active_doc.dirty = False
        w.close()


def test_rename_keeps_scroll_position():
    """[실사용 버그 수정 2026-10-11] 개인 폴더 심볼 이름을 바꾸면 패널 스크롤이 늘 맨 위로 가던 것."""
    with _isolated_symbol_library():
        for f in range(6):
            _fill(f"폴더{f}", 4)
        w = CanvasWindow()
        w.show()
        QTest.qWait(30)
        sb = w._left_scroll.verticalScrollBar()
        assert sb.maximum() > 200
        sb.setValue(sb.maximum() - 20)
        before = sb.value()
        last = symbol_library.load_library()[-1]["id"]
        with patch.object(QInputDialog, "getText", return_value=("바뀐 이름", True)):
            w._rename_custom_symbol_prompt(last)
        QTest.qWait(30)
        assert sb.value() == before
        w._toggle_custom_symbol_favorite(last)                     # 즐겨찾기 넣기도(위 칸이 길어져도) 그대로
        QTest.qWait(30)
        assert sb.value() == before
        w._active_doc.dirty = False
        w.close()


def test_left_panel_height_is_half_view_and_grip_resizes_and_title_double_click_resets():
    with _isolated_symbol_library():
        for f in range(6):
            _fill(f"폴더{f}", 4)
        st = app_settings()
        st.remove("left_panel_height")
        try:
            w = CanvasWindow()
            w.show()
            QTest.qWait(30)
            half = w._view.height() // 2
            assert w._left_scroll.height() == max(w._LEFT_PANEL_MIN_H, half)   # 기본 = 도면 칸 절반
            grip = w._left_grip
            _drag(grip, 80)
            assert w._left_scroll.height() == half + 80
            assert st.value("left_panel_height", type=int) == half + 80
            _drag(grip, 5000)                                       # 레이어 카드와는 안 겹친다
            assert w._left_panel.geometry().bottom() < w._layers_panel.geometry().top()
            # 제목 줄 더블클릭 → 원래대로
            head = w._left_panel._title_lbl
            QApplication.sendEvent(head, QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(3, 3), QPointF(3, 3),
                                                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                                     Qt.KeyboardModifier.NoModifier))
            assert w._left_scroll.height() == max(w._LEFT_PANEL_MIN_H, half)
            assert not st.contains("left_panel_height")
            w._active_doc.dirty = False
            w.close()
        finally:
            st.remove("left_panel_height")


def test_layer_buttons_have_icons_and_header_close_menu_has_icon():
    from PyQt6.QtWidgets import QMenu
    w = CanvasWindow()
    for b in (w._layer_add_btn, w._layer_move_btn):
        assert not b.icon().isNull() and b.text()
        assert b.toolButtonStyle() in (Qt.ToolButtonStyle.ToolButtonTextBesideIcon,
                                       Qt.ToolButtonStyle.ToolButtonIconOnly)
    seen = []
    with patch.object(QMenu, "exec", lambda m, *_a: seen.extend(m.actions())):
        w._left_panel._show_header_menu_at(w.mapToGlobal(w.rect().center()))
    assert [a.text() for a in seen] == ["닫기"] and not seen[0].icon().isNull()
