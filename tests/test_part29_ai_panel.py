"""§8 항목36 1단계(2026-10-05) — 「AI로 만들기」 오른쪽 기둥 패널 뼈대.

켜기/끄기·다른 카드 비켜나기·종류 탭·입력 검사·기록·Enter·테마. 실제 생성은 3~5단계(지금은 "준비 중").
"""
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QKeyEvent

from _shared import *  # noqa: F401,F403

import pytest

from easycad.ai import gateway as gw
from easycad.canvas.ai_panel import PLACEHOLDER


@pytest.fixture(autouse=True)
def _no_real_gateway():
    """이 PC엔 실제 게이트웨이 키가 있다 — 흐름도·심볼 「만들기」가 진짜 호출을 하지 않게 기본은 키 없음.
    생성이 필요한 테스트는 `_fake_gateway`(가짜 키+가짜 생성 함수)로 덮는다."""
    from unittest.mock import patch
    with patch("easycad.ai.gateway.resolve_api_key", return_value=""):
        yield


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
    p.set_kind("symbol")   # 흐름도는 3단계부터 실제 생성을 부른다 — 아직 "준비 중"인 심볼로
    p._prompt_edit.setPlainText("송신기 → 결합기 → 안테나")
    req = p.request_make()
    assert req is not None and req.kind == "symbol" and req.text == "송신기 → 결합기 → 안테나"
    assert got == [req]
    assert p._prompt_edit.toPlainText() == ""          # 입력 칸은 비운다
    assert p._empty.isHidden() and not p._hist_scroll.isHidden()
    assert len(p.entries()) == 1
    from easycad.canvas.host_aimake import NO_KEY_TEXT
    assert req.entry.status_text() == NO_KEY_TEXT      # 호스트가 요청을 받아 상태를 단다(이 테스트는 키 없음)


def test_image_counts_as_input_and_is_cleared_after_make():
    from PIL import Image
    w = CanvasWindow()
    p = w._ai_panel
    p.set_kind("flow")
    p._set_attached_image(Image.new("RGB", (40, 30), "white"), "IMG_7074_매우_긴_파일_이름_입니다.jpg")
    assert p._image_name_label.text() != "IMG_7074_매우_긴_파일_이름_입니다.jpg"   # 좁은 칸에 맞춰 줄임
    req = p.request_make()
    assert req is not None and req.image is not None and req.image_name.startswith("IMG_7074")
    assert p._attached_image is None and p._image_chip.isHidden()
    # 베끼기는 사진이 캔버스에 깔린 채 만들므로 첨부를 남긴다(끝나면 호스트가 비움)
    p.set_kind("trace")
    p._set_attached_image(Image.new("RGB", (40, 30), "white"), "IMG_7074.jpg")
    assert p.request_make() is not None and p._attached_image is not None


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
    p.set_kind("symbol")   # 생성 없이 "준비 중"으로 끝나는 종류(4단계 전까지) — 여기선 도형을 직접 넣는다
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
    assert len(got) == 1 and got[0].text == "BNC 커넥터" and got[0].kind == "symbol"
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


# ── 3단계(2026-10-05): 흐름도 — 패널에서 생성 → 캔버스에 임시로, 방향·코드 칸 ─────────────────

from contextlib import contextmanager
from PyQt6.QtWidgets import QCheckBox, QComboBox
from unittest.mock import patch as _patch

_FLOW = "flowchart LR\n  A[송신기] --> B[결합기]\n  B --> C[안테나]\n  B --> D[감시장치]"


@contextmanager
def _fake_gateway(result=_FLOW, error=None, key="k"):
    """게이트웨이를 부르지 않게 — 키·생성 함수를 가짜로(워커는 진짜 QThread로 돈다)."""
    def gen(*_a, **_k):
        if error:
            raise RuntimeError(error)
        return result, "fake-model"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value=key), \
            _patch("easycad.ai.text_to_mermaid.generate_mermaid", side_effect=gen):
        yield


def _wait_until(cond, ms=5000):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        _app.processEvents()
        if cond():
            return True
    return False


def _make_flow(w, text="송신기 → 결합기 → 안테나, 감시장치 분기"):
    p = w._ai_panel
    p.set_kind("flow")
    p._prompt_edit.setPlainText(text)
    return p.request_make()


def test_flow_generates_and_stages_at_request_center():
    w = _shown_window()
    with _fake_gateway():
        req = _make_flow(w)
        assert _wait_until(lambda: w._ai_staged is not None)
    st = w._ai_staged
    assert st.request is req and req.entry.status_text() == STAGED_TEXT
    assert len(st.items) == 7   # 상자 4 + 화살표 3
    c = w._ai_staged_scene_rect().center()
    assert abs(c.x() - req.center.x()) < 2 and abs(c.y() - req.center.y()) < 60
    assert w._ai_panel.flow_code() == _FLOW
    _close_clean(w)


def test_flow_without_key_and_failure_show_in_entry():
    from easycad.canvas.host_aimake import NO_KEY_TEXT
    w = _shown_window()
    with _fake_gateway(key=""):
        req = _make_flow(w)
    assert req.entry.status_text() == NO_KEY_TEXT and not w._ai_jobs
    with _fake_gateway(error="503 busy"):
        req2 = _make_flow(w)
        assert _wait_until(lambda: not w._ai_jobs)
    assert "실패" in req2.entry.status_text() and "503" in req2.entry.status_text()
    assert w._ai_staged is None
    _close_clean(w)


def test_flow_direction_change_redraws_without_new_history():
    w = _shown_window()
    with _fake_gateway():
        _make_flow(w)
        assert _wait_until(lambda: w._ai_staged is not None)
    n_undo = len(w._undo)
    old_items = list(w._ai_staged.items)
    combo = [c for c in w._ai_staged.bar.findChildren(QComboBox)][0]
    combo.setCurrentIndex(combo.findData("TD"))
    st = w._ai_staged
    assert st is not None and st.items != old_items
    assert all(it.scene() is None for it in old_items)
    assert len(w._undo) == n_undo
    assert w._ai_panel.flow_code().startswith("flowchart TD")
    # 세로가 되면 결과가 가로보다 높다
    r = w._ai_staged_scene_rect()
    assert r.height() > r.width() * 0.6
    _close_clean(w)


def test_flow_code_edit_redraws_and_bad_code_keeps_result():
    w = _shown_window()
    with _fake_gateway():
        _make_flow(w)
        assert _wait_until(lambda: w._ai_staged is not None)
    w._on_ai_code_edited(_FLOW + "\n  D --> E[경보]")
    assert len(w._ai_staged.items) == 9
    before = list(w._ai_staged.items)
    w._on_ai_code_edited("이건 머메이드가 아님")
    assert w._ai_staged.items == before and "코드 오류" in w._ai_staged.request.entry.status_text()
    _close_clean(w)


def test_code_insert_without_ai():
    w = _shown_window()
    p = w._ai_panel
    p.set_kind("flow")
    p._adv_btn.click()
    assert not p._code_box.isHidden()
    p._code_edit.setPlainText(_FLOW)
    with _patch("easycad.ai.gateway.resolve_api_key", return_value=""):
        p._code_insert_btn.click()
    assert w._ai_staged is not None and len(w._ai_staged.items) == 7
    assert not w._ai_jobs
    _close_clean(w)


def test_flow_result_goes_back_to_request_tab():
    w = _shown_window()
    first = w._active_doc
    with _fake_gateway():
        _make_flow(w)
        w._new_doc()   # 생성 도중 새 탭으로 옮겨 감
        assert _wait_until(lambda: w._ai_staged is not None)
    assert w._ai_staged.doc is first and w._active_doc is first
    _close_clean(w)


def test_wide_result_zooms_out_to_fit_between_side_cards():
    # 2026-10-05 실제 창: 넓은 흐름도 왼쪽이 「도형」 카드 밑에 깔리고 막대 「채택」이 가려짐 → 카드 사이 띠에 맞춰 축소.
    w = _shown_window()
    p = w._ai_panel
    p.set_kind("flow")
    p._adv_btn.click()
    chain = " --> ".join(f"N{i}[단계 {i}]" for i in range(12))
    p._code_edit.setPlainText("flowchart LR\n  " + chain)
    s0 = w._view.transform().m11()
    p._code_insert_btn.click()
    _app.processEvents()
    st = w._ai_staged
    assert st is not None and w._view.transform().m11() < s0   # 줄였다(확대는 안 함)
    free = w._ai_free_viewport_rect(w._view)
    vp = w._view.mapFromScene(w._ai_staged_scene_rect()).boundingRect()
    assert free.left() <= vp.left() and vp.right() <= free.right()
    assert st.bar.x() >= free.left()    # 막대도 카드 밑에 안 깔림
    _close_clean(w)


# ── 4단계(2026-10-05): 심볼 — 후보 줄, 클릭으로 고르기, 안 고르면 버림, 우클릭 바꾸기 ─────────────

from PyQt6.QtCore import QRectF as _QRectF
from easycad.canvas.host_aimake import SYMBOL_COUNT, UNPICKED_TEXT

_SVG = '<svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="14" fill="none" stroke="black"/></svg>'


@contextmanager
def _fake_svg(fail=False):
    def gen(*_a, **_k):
        if fail:
            raise RuntimeError("429 quota")
        return _SVG, "fake-svg-model"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.canvas.host_dialogs.generate_svg", side_effect=gen):
        yield


def _make_symbol(w, text="BNC 커넥터 아이콘"):
    p = w._ai_panel
    p.set_kind("symbol")
    p._prompt_edit.setPlainText(text)
    req = p.request_make()
    assert _wait_until(lambda: not w._ai_jobs)
    return req


def test_symbol_candidates_arrive_in_a_row_without_history():
    w = _shown_window()
    n_undo = len(w._undo)
    with _fake_svg():
        req = _make_symbol(w)
    st = w._ai_staged
    assert st is not None and st.slots is not None and len(st.cands) == SYMBOL_COUNT
    assert len(w._undo) == n_undo                     # 고르기 전엔 기록에 없음
    xs = [s.center().x() for s in st.slots]
    assert xs == sorted(xs) and len({round(s.center().y()) for s in st.slots}) == 1   # 한 줄
    assert "6개" in req.entry.status_text()
    _close_clean(w)


def test_click_one_candidate_keeps_only_it_as_one_step():
    w = _shown_window()
    with _fake_svg():
        req = _make_symbol(w)
    st = w._ai_staged
    n_undo = len(w._undo)
    pick, others = st.cands[2], [c for i, c in enumerate(st.cands) if i != 2]
    pick.items[0].setSelected(True)
    _wait_until(lambda: w._ai_staged is None, 1000)
    assert w._ai_staged is None and all(it.scene() is w._scene for it in pick.items)
    assert all(it.scene() is None for c in others for it in c.items)
    assert len(w._undo) == n_undo + 1 and "1개 넣음" in req.entry.status_text()
    w.undo()
    assert all(it.scene() is None for it in pick.items)
    _close_clean(w)


def test_ctrl_click_several_then_accept():
    w = _shown_window()
    with _fake_svg():
        _make_symbol(w)
    st = w._ai_staged
    ctrl = Qt.KeyboardModifier.ControlModifier
    with _patch("easycad.canvas.host_aimake.QApplication.keyboardModifiers", return_value=ctrl):
        st.cands[0].items[0].setSelected(True)
        st.cands[4].items[0].setSelected(True)
    _app.processEvents()
    assert w._ai_staged is st and st.picked == {0, 4}
    st.bar.accept_btn.click()
    assert w._ai_staged is None
    kept = [i for i, c in enumerate(st.cands) if c.items[0].scene() is w._scene]
    assert kept == [0, 4]
    _close_clean(w)


def test_unpicked_candidates_vanish_on_other_edit_or_new_make():
    w = _shown_window()
    with _fake_svg():
        req = _make_symbol(w)
    st = w._ai_staged
    w.push_undo_add(_mk_pen_rect(w, x=900, y=900))
    assert w._ai_staged is None and req.entry.status_text() == UNPICKED_TEXT
    assert all(it.scene() is None for c in st.cands for it in c.items)
    with _fake_svg():
        req2 = _make_symbol(w)
        st2 = w._ai_staged
        w._ai_panel._prompt_edit.setPlainText("다른 것")
        w._ai_panel.request_make()   # 새 만들기 → 고르지 않은 후보 줄은 버림
    assert req2.entry.status_text() == UNPICKED_TEXT
    assert all(it.scene() is None for c in st2.cands for it in c.items)
    _close_clean(w)


def test_all_candidates_fail_reports_in_entry():
    w = _shown_window()
    with _fake_svg(fail=True):
        req = _make_symbol(w)
    assert w._ai_staged is None and "실패" in req.entry.status_text() and "429" in req.entry.status_text()
    _close_clean(w)


def test_right_click_replace_swaps_shape_in_place():
    w = _shown_window()
    rect = _mk_pen_rect(w, x=0, y=0, ww=120, hh=80)
    w.push_undo_add(rect)
    rect.setSelected(True)
    texts = [a.text() for a in w._build_context_menu().actions()]
    assert any("AI로 바꾸기" in t for t in texts)
    w._ai_open_for_replace(rect)
    assert not w._ai_panel.isHidden() and w._ai_panel.kind() == "symbol"
    with _fake_svg():
        req = _make_symbol(w, "안테나")
    st = w._ai_staged
    assert req.replace_target is rect
    # sceneBoundingRect는 선택 손잡이 여백까지 커져 실제 도형 크기가 아니다(pitfalls "좌표계·변환") — rect() 기준
    assert min(s.top() for s in st.slots) > rect.mapToScene(rect.rect()).boundingRect().bottom()   # 도형 아래 줄
    n_undo = len(w._undo)
    st.cands[0].items[0].setSelected(True)
    _wait_until(lambda: w._ai_staged is None, 1000)
    assert rect.scene() is None and len(w._undo) == n_undo + 1
    new = w._scene.selectedItems()
    box = _QRectF()
    for it in new:
        box = box.united(it.sceneBoundingRect())
    assert abs(box.center().x() - 60) < 6 and abs(box.center().y() - 40) < 6   # 같은 가운데
    w.undo()
    assert rect.scene() is w._scene and all(it.scene() is None for it in new)
    _close_clean(w)


def test_save_candidates_to_my_symbols():
    w = _shown_window()
    with _fake_svg():
        _make_symbol(w)
    got = {}

    def fake_save(entries, subject, folder):
        got.update(n=len(entries), subject=subject, folder=folder)
        return len(entries)
    from PyQt6.QtWidgets import QDialog
    with _patch("easycad.canvas.host_aimake._SaveToSymbolsFolderDialog.exec",
                return_value=QDialog.DialogCode.Accepted), \
            _patch("easycad.canvas.host_aimake._SaveToSymbolsFolderDialog.chosen_folder", return_value=None), \
            _patch.object(w, "_save_svg_candidates_to_symbols", side_effect=fake_save):
        assert w._ai_save_candidates_to_symbols() == SYMBOL_COUNT
    assert got == {"n": SYMBOL_COUNT, "subject": "BNC 커넥터 아이콘", "folder": None}
    assert w._ai_staged is not None   # 저장해도 후보 줄은 그대로(고르기는 따로)
    _close_clean(w)


# ── 5단계(2026-10-05): 그대로 베끼기 — 캔버스 바닥 사진·모서리 4점·생성 중 편집·취소·사진 남기기 ─────

from PyQt6.QtCore import QPointF as _QPointF
from PyQt6.QtGui import QMouseEvent as _QMouseEvent
from easycad.canvas.host_aimake import CANCELLED_TEXT, TRACE_HINT

_SPEC = {"ops": [{"op": "box", "id": "a", "x1": 100, "y1": 80, "x2": 300, "y2": 200},
                 {"op": "text", "x": 120, "y": 140, "text": "TX"}]}


def _photo(w=800, h=600):
    from PIL import Image
    return Image.new("RGB", (w, h), "white")


def _attach_trace(w, img=None):
    p = w._ai_panel
    p.set_kind("trace")
    p._set_attached_image(img or _photo(), "IMG_7074.jpg")
    _app.processEvents()
    return w._ai_trace


@contextmanager
def _fake_trace(spec=_SPEC, wait_cancel=False):
    """구역 생성(generate_ops_tiled)을 가짜로 — wait_cancel이면 취소될 때까지 진행 신호만 보내며 버틴다."""
    import time as _t
    from easycad.ai.photo_to_ops import Cancelled

    def gen(_client, _photo_, *, model, progress=None, cancelled=None, **_k):
        if wait_cancel:
            for i in range(200):
                if progress:
                    progress(min(i, 5), 6, "구역")
                if cancelled and cancelled():
                    raise Cancelled()
                _t.sleep(0.02)
        if progress:
            progress(6, 6, "끝")
        return spec, [{"tile": i} for i in range(6)]
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.photo_to_ops.generate_ops_tiled", side_effect=gen):
        yield


def _mouse(w, etype, vp_pos, button=Qt.MouseButton.LeftButton):
    vp = w._view.viewport()
    buttons = button if etype != _QMouseEvent.Type.MouseButtonRelease else Qt.MouseButton.NoButton
    ev = _QMouseEvent(etype, _QPointF(vp_pos), _QPointF(vp.mapToGlobal(vp_pos)), button, buttons,
                      Qt.KeyboardModifier.NoModifier)
    return w.eventFilter(vp, ev)


def test_trace_photo_lays_on_canvas_background_not_as_item():
    w = _shown_window()
    n_items = len(w._scene.items())
    tr = _attach_trace(w)
    assert tr is not None and tr.bar.isVisible() and tr.hint.text() == TRACE_HINT
    assert len(w._scene.items()) == n_items and not w._undo   # 도형도 기록도 아님(저장에 안 섞임)
    c = w._view.mapToScene(w._view.viewport().rect().center())
    assert abs(tr.rect.center().x() - c.x()) < 40
    w._ai_panel.set_kind("flow")            # 다른 종류로 가면 걷힘
    assert w._ai_trace is None
    w._ai_panel.set_kind("trace")           # 돌아오면 붙인 사진으로 다시
    assert w._ai_trace is not None
    w._ai_trace.bar.findChildren(QToolButton)[1].click()   # 「사진 빼기」
    assert w._ai_trace is None and w._ai_panel._attached_image is None
    _close_clean(w)


def test_trace_corner_drag_moves_quad_and_other_clicks_pass_through():
    w = _shown_window()
    tr = _attach_trace(w)
    corner = w._view.mapFromScene(w._ai_trace_corner_scene(tr, 0))
    assert _mouse(w, _QMouseEvent.Type.MouseButtonPress, corner) is True
    assert _mouse(w, _QMouseEvent.Type.MouseMove, corner + QPoint(40, 30)) is True
    assert _mouse(w, _QMouseEvent.Type.MouseButtonRelease, corner + QPoint(40, 30)) is True
    assert tr.quad[0][0] > 10 and tr.quad[0][1] > 5
    far = w._view.viewport().rect().center()
    assert _mouse(w, _QMouseEvent.Type.MouseButtonPress, far) is False   # 점에서 먼 누름은 캔버스로
    tr_w = tr.fitted.size[0]
    w._ai_trace_reset_corners()
    assert tr.quad[1] == (float(tr_w), 0.0)
    _close_clean(w)


def test_trace_make_places_result_on_photo_with_underlay_toggle():
    w = _shown_window()
    tr = _attach_trace(w)
    center = tr.rect.center()
    with _fake_trace():
        req = w._ai_panel.request_make()
        assert w._ai_trace.running
        assert _wait_until(lambda: w._ai_staged is not None)
    st = w._ai_staged
    assert w._ai_trace is None and w._ai_panel._attached_image is None
    assert req.entry.status_text() == STAGED_TEXT
    img = st.items[0]
    assert type(img).__name__ == "_ImageItem" and img.scene() is w._scene
    r = img.sceneBoundingRect()
    assert abs(r.center().x() - center.x()) < 3 and abs(r.center().y() - center.y()) < 3
    keep = st.bar.findChildren(QCheckBox)[0]
    keep.setChecked(False)
    assert img.scene() is None and all(op[1] is not img for op in st.undo_entry.ops)
    keep.setChecked(True)
    assert img.scene() is w._scene and st.undo_entry.ops[0][1] is img
    keep.setChecked(False)
    st.bar.accept_btn.click()
    w.undo()   # 한 번에 결과 전부(사진 빼고 넣은 것) 사라짐
    assert all(it.scene() is None for it in st.items) and img.scene() is None
    _close_clean(w)


def test_trace_cancel_returns_to_setup():
    w = _shown_window()
    _attach_trace(w)
    with _fake_trace(wait_cancel=True):
        req = w._ai_panel.request_make()
        assert _wait_until(lambda: w._ai_jobs and next(iter(w._ai_jobs.values())).progress is not None, 3000)
        w._ai_trace.cancel_btn.click()
        assert _wait_until(lambda: not w._ai_jobs, 5000)
    assert req.entry.status_text() == CANCELLED_TEXT
    assert w._ai_trace is not None and not w._ai_trace.running and w._ai_staged is None
    _close_clean(w)


def test_editing_elsewhere_while_trace_runs():
    w = _shown_window()
    _attach_trace(w)
    with _fake_trace(wait_cancel=False):
        w._ai_panel.request_make()
        other = _mk_pen_rect(w, x=-900, y=-900)
        w.push_undo_add(other)   # 만드는 동안 다른 편집
        assert _wait_until(lambda: w._ai_staged is not None)
    assert other.scene() is w._scene and w._ai_staged is not None
    _close_clean(w)


def test_trace_retry_restores_photo_and_corners_and_regenerates():
    w = _shown_window()
    tr = _attach_trace(w)
    tr.quad[0] = (30.0, 20.0)
    with _fake_trace():
        w._ai_panel.request_make()
        assert _wait_until(lambda: w._ai_staged is not None)
        first = w._ai_staged
        first.bar.retry_btn.click()
        assert w._ai_trace is not None and w._ai_trace.quad[0] == (30.0, 20.0)   # 같은 모서리로 되살림
        assert _wait_until(lambda: w._ai_staged is not None and w._ai_staged is not first)
    assert all(it.scene() is None for it in first.items)
    assert len(w._ai_panel.entries()) == 2
    _close_clean(w)
