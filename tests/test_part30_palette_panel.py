"""[실사용 피드백 2026-10-11] 도형·심볼 카드 정리 — 스크롤 위치 유지 · 폴더마다 처음 보이는 개수(손잡이)·
「더 보기」·크게 보기 창 · 카드 높이(창 절반·손잡이·제목 더블클릭) · 레이어 카드 버튼 아이콘."""
from PyQt6.QtCore import QEvent, QPointF, QSize, Qt
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


def _drag_h(grip, dx):
    def ev(kind, x, button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton):
        p = QPointF(2, 20)
        g = QPointF(grip.mapToGlobal(p.toPoint())) + QPointF(x, 0)
        return QMouseEvent(kind, p, g, button, buttons, Qt.KeyboardModifier.NoModifier)
    grip.mousePressEvent(ev(QEvent.Type.MouseButtonPress, 0))
    grip.mouseMoveEvent(ev(QEvent.Type.MouseMove, dx, Qt.MouseButton.NoButton))
    grip.mouseReleaseEvent(ev(QEvent.Type.MouseButtonRelease, dx, buttons=Qt.MouseButton.NoButton))


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
            more = next(b for b in w._folder_more_btns if b.isVisibleTo(sec) and b.text().startswith("더 보기"))
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
        assert sec.findChild(_DragGrip) is None
        assert not [b for b in w._folder_more_btns if b.text().startswith("더 보기")]


def test_more_button_opens_big_browser_with_all_symbols():
    """[2026-10-11 후속] 크게 보기 = 도형·심볼 카드 오른쪽 패널(따로 뜨는 창 아님), 폴더 고르기 없음."""
    with _isolated_symbol_library():
        ents = _fill("장비", 10)
        _fill("전원", 2)
        w = CanvasWindow()
        w.show()
        sec = _folder_section(w, "장비")
        more = next(b for b in w._folder_more_btns if b.isVisibleTo(sec) and b.text().startswith("더 보기"))
        more.click()
        b = w._symbol_browser
        assert b.isVisible() and b.parent() is w and b.folder == "장비"
        assert b._title_lbl.text() == "장비" and not hasattr(b, "_combo")
        assert len(b._buttons) == 10 and b._count.text() == "10개"
        # 위치: 도형·심볼 카드 바로 오른쪽, 위는 같은 높이, 아래는 레이어 카드 아래까지
        assert b.x() > w._left_panel.geometry().right() and b.y() == w._left_panel.y()
        assert b.geometry().bottom() >= w._layers_panel.geometry().bottom() - 2
        # 칸 클릭 = 도구로 쥐기, 패널과 체크 상태 같이
        b._buttons[3].click()
        assert w.current_tool == f"customsym:{ents[3]['id']}" and b._buttons[3].isChecked()
        w.set_tool(None)
        assert not b._buttons[3].isChecked()
        # 라이브러리가 바뀌면 따라 다시 그림
        with patch.object(QInputDialog, "getText", return_value=("새이름", True)):
            w._rename_custom_symbol_prompt(ents[0]["id"])
        assert "새이름" in [x._full_name for x in b._buttons]
        # 다른 폴더의 ⤢ → 그 폴더로, 같은 ⤢ 다시 → 닫힘
        big = next(x for x in w._folder_more_btns if getattr(x, "_faint", False) and x.isVisibleTo(_folder_section(w, "전원")))
        big.click()
        assert b.isVisible() and b.folder == "전원" and len(b._buttons) == 2
        big.click()
        assert not b.isVisible()
        w._active_doc.dirty = False
        w.close()


def test_browser_is_one_column_list_of_big_icon_and_name():
    """[2026-10-11 후속] 크게 보기 = 폴더 목록을 확대한 표 — 번호 | 그림(64×48, 칸 모양대로 꽉) | 이름, 한 줄에 하나씩 아래로,
    맨 위 고정 제목 줄, 너비는 도형·심볼 카드와 같게. 긴 이름은 두 줄까지 접음, 오른쪽 끝 손잡이로 너비."""
    from PyQt6.QtWidgets import QLabel
    from easycad.canvas.host_widgets import _wrap_two_lines
    st = app_settings()
    st.remove("symbol_browser_width")
    try:
        with _isolated_symbol_library():
            rect = [{"type": "rect", "rect": [0, 0, 120, 30], "pen": "#ff000000", "width": 1.0, "fill": None,
                     "pos": [0, 0], "scale": 1.0, "rotation": 0.0, "z": 0, "origin": [0, 0]}]
            symbol_library.create_folder("긴것")
            symbol_library.add_symbol("가로로 긴 심볼", rect, "", folder="긴것")
            symbol_library.add_symbol("야옹이 — gemini-3.5-flash-lite 아주 긴 이름입니다", rect, "", folder="긴것")
            w = CanvasWindow()
            w.show()
            w._open_symbol_browser("긴것")
            b = w._symbol_browser
            assert not hasattr(b, "_view_btns") and b.width() == b.DEFAULT_W == w._left_panel.width()
            b0, b1 = b._buttons
            assert b1.y() > b0.y() and b1.x() == b0.x()                      # 한 줄에 하나, 아래로
            texts = [l.text() for l in b0.findChildren(QLabel)]
            assert texts[0] == "1" and [l.text() for l in b1.findChildren(QLabel)][0] == "2"   # 번호
            head = [l.text() for l in b.findChildren(QLabel)]
            assert "#" in head and "그림" in head and "이름" in head                # 제목 줄
            pm = b0._pixmap
            assert (pm.width(), pm.height()) == (b.ICON_W, b.ICON_H)         # 칸 모양 그대로(정사각 아님)
            img = pm.toImage()
            xs = [x for x in range(img.width()) if any(img.pixelColor(x, y).alpha() for y in range(img.height()))]
            assert xs[0] <= 4 and xs[-1] >= b.ICON_W - 5                      # 긴 심볼이 칸 가로를 끝까지 쓴다
            assert b1._name_lbl.text().count("\n") == 1                       # 긴 이름은 두 줄
            assert b0._name_lbl.text().replace("\n", " ").startswith("가로로")
            fm = b1._name_lbl.fontMetrics()
            assert all(fm.horizontalAdvance(line) <= b._name_width() for line in b1._name_lbl.text().split("\n"))
            assert _wrap_two_lines(fm, "짧음", 100) == "짧음"
            w0 = b.width()
            _drag_h(b._grip, 120)
            assert b.width() == w0 + 120 and st.value("symbol_browser_width", type=int) == w0 + 120
            b._grip.mouseDoubleClickEvent(QMouseEvent(QEvent.Type.MouseButtonDblClick, QPointF(2, 2), QPointF(2, 2),
                                                      Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                                      Qt.KeyboardModifier.NoModifier))
            assert b.width() == b.DEFAULT_W
            b._close_btn.click()
            assert not b.isVisible()
            w._active_doc.dirty = False
            w.close()
    finally:
        st.remove("symbol_browser_width")


def test_folder_title_has_always_visible_big_view_button_and_no_collapse_arrow():
    with _isolated_symbol_library():
        _fill("장비", 3)
        symbol_library.create_folder("빈폴더")
        w = CanvasWindow()
        w.show()
        sec = _folder_section(w, "장비")
        assert sec._tail_btn.isVisibleTo(sec) and sec._tail_btn._icon_name == "menu_expand"
        assert "▾" not in [b.text() for b in sec.findChildren(QToolButton)]
        assert getattr(_folder_section(w, "빈폴더"), "_tail_btn", None) is None   # 빈 폴더엔 없음
        QTest.mouseClick(sec._title_lbl, Qt.MouseButton.LeftButton)            # 제목 눌러 접기
        assert sec.body.isHidden()
        app_settings().remove("symfolder_collapsed_장비")
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


def _press_canvas(w):
    vp = w._view.viewport()
    p = QPointF(vp.width() / 2, vp.height() / 2)
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, p, QPointF(vp.mapToGlobal(p.toPoint())),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    w.eventFilter(vp, ev)


def test_feedback_followups_chip_folder_button_browser_close_layer_text():
    """[실사용 피드백 2026-10-11 후속] 개수 칩은 제목 바로 뒤 · 「새 폴더」는 테두리 버튼(레이어 버튼과 같게) ·
    크게 보기는 선택 도구로 도면을 누르면 닫히고, 심볼을 쥔 채 누르면(놓기) 안 닫힘 · 레이어 버튼 「Layer」."""
    with _isolated_symbol_library():
        ents = _fill("장비", 3)
        w = CanvasWindow()
        w.show()
        sec = _folder_section(w, "장비")
        hl = sec.header_layout
        assert hl.indexOf(sec.count_lbl) == hl.indexOf(sec._title_lbl) + 1
        assert sec.count_lbl.geometry().left() - sec._title_lbl.geometry().right() < 20
        assert not w._add_folder_btn.isFlat() and w._add_folder_btn.iconSize() == w._layer_add_btn.iconSize()
        assert w._layer_add_btn.text() == "Layer"
        w._open_symbol_browser("장비")
        b = w._symbol_browser
        w._custom_sym_buttons[ents[0]["id"]][0].click()   # 심볼을 쥠 = 놓기 대기
        _press_canvas(w)
        assert b.isVisible()
        w.set_tool(None)
        _press_canvas(w)
        assert not b.isVisible()
        w._active_doc.dirty = False
        w.close()


def test_type_button_icon_and_rotation_field_follows_handle_rotation():
    """[실사용 피드백 2026-10-11 후속] 속성 카드 「종류」 버튼에 지금 도형 그림 · 회전 손잡이로 돌리거나 되돌려도 회전 칸이 따라옴."""
    w = CanvasWindow()
    r = _RectItem(QRectF(0, 0, 100, 60))
    r.setFlags(r.GraphicsItemFlag.ItemIsSelectable | r.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(r); r.setSelected(True)
    assert not w._pf_swap_btn.icon().isNull()
    snaps = [(r, r.capture_geom())]
    r.setRotation(30)                 # 손잡이 끌기와 같은 기록 경로(core_shapes mouseReleaseEvent → push_undo_geom)
    w.push_undo_geom(snaps)
    _app.processEvents()
    assert w._pf_rotation.value() == 30.0
    w.undo(); _app.processEvents()
    assert r.rotation() == 0.0 and w._pf_rotation.value() == 0.0
    w._active_doc.dirty = False
    w.close()


def test_text_section_edits_shape_label_and_standalone_text():
    """[시안 T1 2026-10-11] 속성 카드 「글자」 구역 — 도형 안 글자(라벨)의 크기·색을 도형을 고른 채로 바꾼다(예전 「폰트」는
    도형 선택 때 늘 꺼짐). 글자 없는 도형은 구역 숨김, 독립 글자만 고르면 「선」 줄 숨김. 되돌리기 1번에 원래대로."""
    w = CanvasWindow(); w.show()
    form = w._props_form
    r = _RectItem(QRectF(0, 0, 200, 80))
    r.setFlags(r.GraphicsItemFlag.ItemIsSelectable | r.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(r); r.setSelected(True); _app.processEvents()
    assert not form.isRowVisible(w._pf_font) and not form.isRowVisible(w._pf_text_head)   # 글자 없음 → 숨김
    lbl = r.ensure_label(); lbl.setPlainText("처리 A")
    w._refresh_properties()
    assert form.isRowVisible(w._pf_font) and w._pf_font.isEnabled() and form.isRowVisible(w._pf_line_row)
    assert w._pf_font.value() == 16 and "처리 A" in w._pf_text_preview.text()
    pen_before = r.pen().color().name()
    w._pf_font.setValue(24)
    assert lbl._base_pt == 24 and r.isSelected()
    w._apply_text_color_preset(1)
    assert lbl.defaultTextColor().name() == w._line_presets()[1].name()
    assert r.pen().color().name() == pen_before   # 도형 선 색은 그대로
    w.undo(); w.undo()
    assert lbl._base_pt == 16
    w._scene.clearSelection()
    t = _TextItem(QColor("#000000")); t.setPlainText("메모")
    t.setFlags(t.GraphicsItemFlag.ItemIsSelectable | t.GraphicsItemFlag.ItemIsMovable)
    w._scene.addItem(t); t.setSelected(True); _app.processEvents()
    assert form.isRowVisible(w._pf_font) and not form.isRowVisible(w._pf_line_row)
    w._active_doc.dirty = False
    w.close()


def test_basic_section_title_has_shapes_mark():
    """[2026-10-12] 즐겨찾기 ★과 짝 — 「기본 도형」 제목 앞 □○△ 그림(폴더엔 없음), 테마를 바꿔도 남는다."""
    with _isolated_symbol_library():
        _fill("장비", 1)
        w = CanvasWindow(); w.show(); _app.processEvents()
        lead = w._basic_section._lead
        assert lead.isVisible() and not lead.pixmap().isNull()
        assert w._basic_section.header_layout.indexOf(lead) < w._basic_section.header_layout.indexOf(w._basic_section._title_lbl)
        assert not _folder_section(w, "장비")._lead.isVisible()
        w._apply_theme(False)
        assert lead.isVisible() and not lead.pixmap().isNull()
        w._active_doc.dirty = False
        w.close()
