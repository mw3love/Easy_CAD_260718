"""§8 항목36 1단계(2026-10-05) — 「AI로 만들기」 오른쪽 기둥 패널 뼈대.

켜기/끄기·다른 카드 비켜나기·종류 탭·입력 검사·기록·Enter·테마. 실제 생성은 3~5단계(지금은 "준비 중").
"""
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QKeyEvent

from _shared import *  # noqa: F401,F403

from easycad.ai import gateway as gw
from easycad.canvas.ai_panel import PENDING_TEXT, PLACEHOLDER


def _shown_window():
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    _app.processEvents()
    return w


def _view_right(w):
    return w._view.mapTo(w, QPoint(0, 0)).x() + w._view.width()


def test_panel_hidden_by_default_and_toggle_shrinks_view():
    w = _shown_window()
    p = w._ai_panel
    assert p.isHidden() and not w._act_ai_make.isChecked()
    view_w = w._view.width()
    w._act_ai_make.trigger()   # 메뉴·상단바와 같은 경로
    _app.processEvents()
    assert p.isVisible() and w._act_ai_make.isChecked()
    assert w._view.width() == view_w - p.WIDTH
    # 속성·미니맵 카드는 패널을 피해 뷰 안쪽에 있다
    for card in (w._props_panel, w._minimap_panel):
        assert card.x() + card.width() <= _view_right(w)
    assert p.x() >= _view_right(w)
    w._act_ai_make.trigger()
    _app.processEvents()
    assert p.isHidden() and w._view.width() == view_w
    w.close()


def test_close_button_hides_and_unchecks_action():
    w = _shown_window()
    w._set_ai_panel_visible(True)
    w._ai_panel._close_btn.click()
    _app.processEvents()
    assert w._ai_panel.isHidden() and not w._act_ai_make.isChecked()
    w.close()


def test_toolbar_has_one_ai_icon_instead_of_three():
    w = CanvasWindow()
    acts = w._toolbar.actions()
    assert w._act_ai_make in acts
    for old in (w._act_mmd, w._act_ai_svg, w._act_photo):
        assert old not in acts
    # 옛 창은 종류별 생성이 패널로 옮겨질 때까지 삽입 메뉴에 남는다
    menu_acts = [a for m in w.menuBar().actions() if m.menu() for a in m.menu().actions()]
    for a in (w._act_ai_make, w._act_mmd, w._act_ai_svg, w._act_photo):
        assert a in menu_acts


def test_kind_switch_updates_placeholder_hint_and_model():
    w = CanvasWindow()
    p = w._ai_panel
    assert p.kind() == "symbol" and p.model() == gw.TEXT_RECOMMEND_1
    for key in ("flow", "trace", "symbol"):
        p._kind_buttons[key].click()
        assert p.kind() == key
        assert p._prompt_edit.placeholderText() == PLACEHOLDER[key]
    p.set_kind("flow")
    assert p.model() == gw.TEXT_RECOMMEND_MERMAID
    p.set_kind("trace")
    assert p.model() == "gpt-6.1-sol"
    assert not p._hint_lbl.isHidden() and "분" in p._hint_lbl.text()
    # 빈 상태 카드를 눌러도 종류가 바뀐다
    p._kind_cards["flow"].clicked.emit("flow")
    assert p.kind() == "flow" and p._kind_buttons["flow"].isChecked()


def test_make_validates_input_and_records_history():
    w = CanvasWindow()
    p = w._ai_panel
    got = []
    p.make_requested.connect(got.append)
    assert p.request_make() is None and not p._notice.isHidden()   # 빈 입력
    p.set_kind("trace")
    p._prompt_edit.setPlainText("설명만")
    assert p.request_make() is None and "사진" in p._notice.text()   # 베끼기는 사진 필수
    p.set_kind("flow")
    p._prompt_edit.setPlainText("송신기 → 결합기 → 안테나")
    req = p.request_make()
    assert req is not None and req.kind == "flow" and req.text == "송신기 → 결합기 → 안테나"
    assert got == [req]
    assert p._prompt_edit.toPlainText() == ""          # 입력 칸은 비운다
    assert p._empty.isHidden() and not p._hist_scroll.isHidden()
    assert len(p.entries()) == 1
    assert req.entry.status_text() == PENDING_TEXT     # 1단계: 호스트가 "준비 중"을 단다


def test_image_counts_as_input_and_is_cleared_after_make():
    from PIL import Image
    w = CanvasWindow()
    p = w._ai_panel
    p.set_kind("trace")
    p._set_attached_image(Image.new("RGB", (40, 30), "white"), "IMG_7074_매우_긴_파일_이름_입니다.jpg")
    assert p._image_name_label.text() != "IMG_7074_매우_긴_파일_이름_입니다.jpg"   # 좁은 칸에 맞춰 줄임
    req = p.request_make()
    assert req is not None and req.image is not None and req.image_name.startswith("IMG_7074")
    assert p._attached_image is None and p._image_chip.isHidden()


def test_enter_makes_and_shift_enter_does_not():
    w = CanvasWindow()
    p = w._ai_panel
    p._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    shift = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert p.eventFilter(p._prompt_edit, shift) is False
    assert p.entries() == []
    enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    assert p.eventFilter(p._prompt_edit, enter) is True
    assert len(p.entries()) == 1


def test_advanced_section_folds_and_theme_toggle_keeps_panel_alive():
    w = CanvasWindow()
    p = w._ai_panel
    assert p._adv_box.isHidden() and p._adv_btn.text().startswith("▸")
    p._adv_btn.click()
    assert not p._adv_box.isHidden() and p._adv_btn.text().startswith("▾")
    p._prompt_edit.setPlainText("BNC 커넥터 아이콘")
    p.request_make()   # 기록 칸이 있는 채로 테마 전환(칸 QSS를 다시 거는 경로 — 라이트에서 흰 글자 남던 것)
    w._apply_theme(not w._dark)
    w._apply_theme(not w._dark)
    assert p._head.styleSheet() == w._props_panel._head.styleSheet()


# ── 2단계(2026-10-05): 임시 결과 — 캔버스에 실제로 넣고 점선·결과 막대만 덧씌움 ───────────────

from easycad.canvas.host_aimake import ACCEPTED_TEXT, DISCARDED_TEXT, STAGED_TEXT, UNDONE_TEXT


def _close_clean(w):
    """편집한 창을 닫으면 「저장할까요?」 창이 떠 테스트가 멈춘다 — 저장할 것 없음으로 만든 뒤 닫는다."""
    for d in w._docs:
        d.dirty = False
    w.close()


def _staged(w, n=3, text="송신기 → 결합기"):
    """패널 요청 하나 + 결과 도형 n개를 넣고(되돌리기 한 칸) 임시 결과로 띄운다."""
    p = w._ai_panel
    p.set_kind("flow")
    p._prompt_edit.setPlainText(text)
    req = p.request_make()
    items = [_mk_pen_rect(w, x=i * 80, y=0) for i in range(n)]
    w.push_undo_add_many(items)
    st = w._ai_stage(items, req)
    assert st is not None
    return req, items, st


def test_stage_shows_bar_and_status():
    w = _shown_window()
    req, items, st = _staged(w)
    assert w._ai_staged is st and st.bar.isVisible()
    assert req.entry.status_text() == STAGED_TEXT
    for b in ("채택", "다시", "버리기"):
        assert any(btn.text() == b for btn in (st.bar.accept_btn, st.bar.retry_btn, st.bar.discard_btn))
    _close_clean(w)


def test_accept_keeps_items_and_clears_marker():
    w = _shown_window()
    req, items, st = _staged(w)
    n_undo = len(w._undo)
    st.bar.accept_btn.click()
    assert w._ai_staged is None and all(it.scene() is w._scene for it in items)
    assert len(w._undo) == n_undo and req.entry.status_text() == ACCEPTED_TEXT
    _close_clean(w)


def test_discard_removes_items_and_cannot_be_redone():
    w = _shown_window()
    n_before = len(w._undo)
    req, items, st = _staged(w)
    st.bar.discard_btn.click()
    assert w._ai_staged is None and all(it.scene() is None for it in items)
    assert len(w._undo) == n_before and st.undo_entry not in w._redo
    assert req.entry.status_text() == DISCARDED_TEXT
    _close_clean(w)


def test_other_edit_auto_accepts():
    w = _shown_window()
    req, items, st = _staged(w)
    other = _mk_pen_rect(w, x=500, y=500)
    w.push_undo_add(other)
    assert w._ai_staged is None and req.entry.status_text() == ACCEPTED_TEXT
    assert all(it.scene() is w._scene for it in items)
    _close_clean(w)


def test_ctrl_z_removes_result_and_marker():
    w = _shown_window()
    req, items, st = _staged(w)
    w.undo()
    assert w._ai_staged is None and all(it.scene() is None for it in items)
    assert req.entry.status_text() == UNDONE_TEXT
    _close_clean(w)


def test_new_make_auto_accepts_previous():
    w = _shown_window()
    req, items, st = _staged(w)
    w._ai_panel._prompt_edit.setPlainText("다음 요청")
    w._ai_panel.request_make()
    assert w._ai_staged is None and req.entry.status_text() == ACCEPTED_TEXT
    _close_clean(w)


def test_save_auto_accepts(tmp_path):
    w = _shown_window()
    req, items, st = _staged(w)
    w._doc_path = str(tmp_path / "staged.ecad")
    w._save_doc()
    assert w._ai_staged is None and req.entry.status_text() == ACCEPTED_TEXT
    assert os.path.exists(w._doc_path)
    _close_clean(w)


def test_retry_discards_and_resubmits_same_request():
    w = _shown_window()
    req, items, st = _staged(w, text="BNC 커넥터")
    got = []
    w._ai_panel.make_requested.connect(got.append)
    st.bar.retry_btn.click()
    assert w._ai_staged is None and all(it.scene() is None for it in items)
    assert len(got) == 1 and got[0].text == "BNC 커넥터" and got[0].kind == "flow"
    assert got[0].entry is not req.entry and len(w._ai_panel.entries()) == 2
    _close_clean(w)


def test_closing_staged_tab_clears_marker():
    from unittest.mock import patch
    from PyQt6.QtWidgets import QMessageBox
    w = _shown_window()
    w._new_doc()
    _app.processEvents()
    req, items, st = _staged(w)
    with patch.object(QMessageBox, "warning", return_value=QMessageBox.StandardButton.Discard):
        w._close_tab_at(w._docs.index(st.doc))
    _app.processEvents()
    assert w._ai_staged is None
    _close_clean(w)


def test_bar_sits_above_dashed_rect_and_follows_zoom():
    w = _shown_window()
    req, items, st = _staged(w)
    w._view.centerOn(items[1])
    w._view.viewport().repaint()   # drawForeground → 막대 자리 예약(singleShot 0)
    _app.processEvents()
    rect = w._ai_staged_scene_rect()
    top_vp = w._view.mapFromScene(rect.topLeft()).y()
    assert st.bar.y() + st.bar.height() <= top_vp   # 점선 위
    y0 = st.bar.y()
    w._on_wheel_zoom(240)
    w._view.viewport().repaint()
    _app.processEvents()
    assert st.bar.y() != y0   # 확대하면 결과 위쪽 가장자리가 옮겨 가고 막대도 따라간다
    _close_clean(w)
