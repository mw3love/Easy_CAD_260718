"""§8 항목36(2026-10-05) → §8 항목51(2026-10-16 Magic Board 개편) — AI 만들기.

옛 오른쪽 패널은 없앴다: 입구는 가운데 칸 하나(`start_prompt.py`), 요청·기록·모델은 `ai_control._AIController`,
이어 고치기는 결과 막대의 입력 한 줄, 진행·실패는 상태 알약. 임시 결과·흐름도·심볼·베끼기·부분 다시는 그대로.
"""
from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QKeyEvent

from _shared import *  # noqa: F401,F403

import pytest

from easycad.ai import gateway as gw
from easycad.app_settings import app_settings
from easycad.canvas.ai_control import PLACEHOLDER


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


def _say(w, text, alt=False):
    """결과 막대(또는 비교 중 원본 막대) 한 줄에 쓰고 Enter."""
    st = w._ai_staged
    line = st.alt_line if alt else st.bar.line
    line.setText(text)
    line.returnPressed.emit()
    _app.processEvents()


def test_ai_button_opens_center_card_over_drawing_no_side_panel():
    w = _shown_window()
    assert not hasattr(w, "_ai_panel")
    w.push_undo_add(_mk_pen_rect(w, x=0, y=0))   # 빈 도면이 아니면 저절로는 안 뜬다
    _app.processEvents()
    sp = w._start_prompt
    assert sp.isHidden()
    view_w = w._view.width()
    w._act_ai_make.trigger()   # 상단바 「AI」·메뉴와 같은 경로
    _app.processEvents()
    assert sp.isVisible() and not w._act_ai_make.isCheckable()
    assert w._view.width() == view_w                 # 오른쪽 기둥이 없어 도면이 좁아지지 않는다
    vg = w._view.geometry()
    assert abs(sp.geometry().center().x() - vg.center().x()) < 30   # 뷰 가운데
    sp._close_btn.click()
    _app.processEvents()
    assert sp.isHidden()
    w._open_ai_prompt()
    esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    assert sp.eventFilter(sp._edit, esc) is True and sp.isHidden()   # Esc로도 닫힘
    _close_clean(w)


def test_kind_actions_open_card_with_kind_hint_only():
    """[§8 항목36 6단계 → 51] 삽입 메뉴 세 항목·단축키(Ctrl+Shift+F/A/P, id 그대로)는 가운데 칸을 그 종류 안내글로 연다
    (종류 칩·버튼은 없다)."""
    import easycad.canvas.host_dialogs as hd
    import easycad.canvas.photo_dialog as pd
    for gone in ("_MermaidDialog", "_SvgAssetDialog"):
        assert not hasattr(hd, gone)
    assert not hasattr(pd, "_PhotoToDrawingDialog")
    w = _shown_window()
    sp = w._start_prompt
    assert not hasattr(sp, "_kind_btn")
    for act, kind, key in ((w._act_mmd, "flow", "Ctrl+Shift+F"), (w._act_ai_svg, "symbol", "Ctrl+Shift+A"),
                           (w._act_photo, "trace", "Ctrl+Shift+P")):
        assert act.shortcut().toString() == key
        act.trigger()
        _app.processEvents()
        assert sp.isVisible() and sp.kind_hint() == kind and sp.kind() == kind
        assert sp._edit.placeholderText() == PLACEHOLDER[kind]
    for gone in ("_insert_mermaid", "_insert_ai_svg_asset", "_insert_photo_drawing", "_generate_svg_replace"):
        assert not hasattr(w, gone)
    _close_clean(w)


def test_toolbar_has_one_ai_icon_instead_of_three():
    w = CanvasWindow()
    acts = w._toolbar.actions()
    assert w._act_ai_make in acts
    for old in (w._act_mmd, w._act_ai_svg, w._act_photo):
        assert old not in acts
    menu_acts = [a for m in w.menuBar().actions() if m.menu() for a in m.menu().actions()]
    for a in (w._act_ai_make, w._act_mmd, w._act_ai_svg, w._act_photo):
        assert a in menu_acts


def test_model_auto_by_kind_and_chosen_model():
    w = CanvasWindow()
    c = w._ai_ctrl
    c.set_model_choice("auto")
    assert c.model_for("symbol") == gw.TEXT_RECOMMEND_1 and c.model_for("flow") == gw.TEXT_RECOMMEND_MERMAID
    assert c.model_for("trace") == "gpt-6.1-sol" and c.model_for("explain") == gw.TEXT_RECOMMEND_EXPLAIN
    c.set_model_choice("gpt-6-sol")
    assert c.model_for("flow") == "gpt-6-sol" and c.model_for("symbol") == "gpt-6-sol"
    assert c.model_for("trace") == "gpt-6.1-sol"      # 사진→도면은 검증한 사진 모델만
    assert CanvasWindow()._ai_ctrl.model_choice() == "gpt-6-sol"   # 기억
    c.set_model_choice("auto")


def test_model_menu_shows_prices_and_picks():
    w = CanvasWindow()
    c, sp = w._ai_ctrl, w._start_prompt
    c.set_model_choice("auto")
    c._model_info = [{"id": "gemini-3.5-flash-lite", "input": 0.3, "output": 2.5},
                     {"id": "gpt-5.5", "input": 5.0, "output": 30.0}]
    assert sp._model_btn.text() == "모델 자동 ▾"
    sp._fill_model_menu()
    texts = [a.text() for a in sp._model_menu.actions()]
    assert texts[0].startswith("자동 (추천)")
    assert any("gemini-3.5-flash-lite" in t and "저렴" in t and "$0.3 / 2.5" in t for t in texts)
    assert any("gpt-5.5" in t and "아주 비쌈" in t for t in texts)
    pick = next(a for a in sp._model_menu.actions() if a.data() == "gpt-5.5")
    pick.trigger()
    assert c.model_choice() == "gpt-5.5" and sp._model_btn.text() == "모델 gpt-5.5 ▾"
    c.set_model_choice("auto")


def test_price_tier_and_model_info_filter():
    assert gw.price_tier(0.5) == "아주 저렴" and gw.price_tier(2.5) == "저렴" and gw.price_tier(3.75) == "보통"
    assert gw.price_tier(10) == "비쌈" and gw.price_tier(30) == "아주 비쌈" and gw.price_tier(None) == ""

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [
                {"id": "gpt-6-sol", "type": "llm", "lifecycle": "current", "pricing": {"input": 2.0, "output": 10.0}},
                {"id": "gpt-5.4-mini", "type": "llm", "lifecycle": "legacy", "pricing": {"input": 0.75, "output": 4.5}},
                {"id": "gemini-3.1-flash-lite-image", "type": "image", "pricing": {}},
                {"id": "gemini-3.5-flash-lite", "type": "llm", "lifecycle": "current",
                 "pricing": {"input": 0.3, "output": 2.5}}]}
    from unittest.mock import patch
    with patch("httpx.get", return_value=_Resp()):
        got = gw.list_text_models_info("k")
    assert [m["id"] for m in got] == ["gemini-3.5-flash-lite", "gpt-6-sol"]   # 은퇴·그림 모델 빼고 싼 것부터


def test_make_validates_input_and_records_history():
    w = CanvasWindow()
    c = w._ai_ctrl
    got, notes = [], []
    c.make_requested.connect(got.append)
    c.notice.connect(notes.append)
    assert c.request_make("") is None and notes                      # 빈 입력
    assert c.request_make("설명만", kind="trace") is None and "사진" in notes[-1]   # 베끼기는 사진 필수
    req = c.request_make("송신기 → 결합기 → 안테나", kind="symbol")
    assert req is not None and req.kind == "symbol" and req.text == "송신기 → 결합기 → 안테나"
    assert got == [req] and len(c.entries()) == 1
    from easycad.canvas.host_aimake import NO_KEY_TEXT
    assert req.entry.status_text() == NO_KEY_TEXT      # 호스트가 요청을 받아 상태를 단다(이 테스트는 키 없음)
    assert c.request_make("방송용 카메라 아이콘").kind == "symbol"   # 종류를 안 주면 짐작


def test_center_card_submit_guesses_kind_and_clears():
    from PIL import Image
    w = _shown_window()
    sp = w._start_prompt
    got = []
    w._ai_ctrl.make_requested.connect(got.append)
    sp._edit.setPlainText("휴가 신청 결재 흐름도")
    assert sp.kind() == "flow" and sp.submit() == "flow"
    assert got[-1].kind == "flow" and sp._edit.toPlainText() == "" and sp.isHidden()
    w._open_ai_prompt()
    sp._set_attached_image(Image.new("RGB", (40, 30), "white"), "IMG_7074.jpg")
    sp._edit.setPlainText("이 사진의 관계만 흐름도로")
    assert sp.submit() == "flow" and got[-1].image is not None and got[-1].image_name == "IMG_7074.jpg"
    assert sp._attached_image is None and sp._image_chip.isHidden()
    _close_clean(w)


def test_enter_makes_and_shift_enter_does_not():
    w = _shown_window()
    sp = w._start_prompt
    sp._edit.setPlainText("BNC 커넥터 아이콘")
    shift = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert sp.eventFilter(sp._edit, shift) is False
    assert w._ai_ctrl.entries() == []
    enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    assert sp.eventFilter(sp._edit, enter) is True
    assert len(w._ai_ctrl.entries()) == 1
    _close_clean(w)


def test_plus_and_drop_accept_any_file_and_explain_unsupported():
    w = _shown_window()
    sp = w._start_prompt
    assert sp._attach_btn.text() == "+"
    assert sp.attach_path(os.path.join(_TMP, "현장영상.mp4")) is False
    assert "아직 못 읽어요" in sp._notice.text() and "현장영상.mp4" in sp._notice.text() and "PDF" in sp._notice.text()
    from PIL import Image
    path = os.path.join(_TMP, "plus_ok.png")
    Image.new("RGB", (20, 10), "white").save(path)
    assert sp.attach_path(path) is True and sp._attached_image is not None and sp._notice.isHidden()
    _close_clean(w)


def test_pill_shows_running_and_failure_until_closed():
    w = _shown_window()
    pill = w._ai_pill
    assert pill.isHidden()
    w._ai_ctrl.request_make("송신기", kind="symbol")   # 키 없음 → 남겨 두는 안내
    _app.processEvents()
    assert pill.isVisible() and "KAIROS 키" in pill.text()
    pill.close_btn.click()
    assert pill.isHidden()
    w._ai_fill_history_menu()
    assert any("심볼" in a.text() for a in w._ai_history_menu.actions())
    _close_clean(w)


def test_theme_toggle_keeps_card_pill_and_history():
    w = _shown_window()
    w._ai_ctrl.request_make("BNC 커넥터 아이콘", kind="symbol")
    w._apply_theme(not w._dark)
    w._apply_theme(not w._dark)
    assert w._start_prompt is not None and w._ai_pill is not None and len(w._ai_ctrl.entries()) == 1
    _close_clean(w)


# ── 2단계(2026-10-05): 임시 결과 — 캔버스에 실제로 넣고 점선·결과 막대만 덧씌움 ───────────────

from easycad.canvas.host_aimake import ACCEPTED_TEXT, DISCARDED_TEXT, STAGED_TEXT, UNDONE_TEXT


def _close_clean(w):
    """편집한 창을 닫으면 「저장할까요?」 창이 떠 테스트가 멈춘다 — 저장할 것 없음으로 만든 뒤 닫는다."""
    for d in w._docs:
        d.dirty = False
    w.close()


def _staged(w, n=3, text="송신기 → 결합기"):
    """요청 하나 + 결과 도형 n개를 넣고(되돌리기 한 칸) 임시 결과로 띄운다(키 없음 — 생성 없이 도형을 직접 넣는다)."""
    req = w._ai_ctrl.request_make(text, kind="symbol")
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
    assert st.bar.line is not None and st.bar.line.placeholderText().startswith("예:")   # §8 항목51 입력 한 줄
    assert st.bar.history_btn is not None and st.bar.history_btn.text() == "기록"
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
    w._ai_ctrl.request_make("다음 요청", kind="symbol")
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
    w._ai_ctrl.make_requested.connect(got.append)
    st.bar.retry_btn.click()
    assert w._ai_staged is None and all(it.scene() is None for it in items)
    assert len(got) == 1 and got[0].text == "BNC 커넥터" and got[0].kind == "symbol"
    assert got[0].entry is not req.entry and len(w._ai_ctrl.entries()) == 2
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
            _patch("easycad.ai.text_to_flow.generate_flow", side_effect=gen):
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
    return w._ai_ctrl.request_make(text, kind="flow")


def test_flow_generates_and_stages_at_request_center():
    w = _shown_window()
    with _fake_gateway():
        req = _make_flow(w)
        assert _wait_until(lambda: w._ai_staged is not None)
    st = w._ai_staged
    assert st.request is req and req.entry.status_text() == STAGED_TEXT
    assert len(st.items) == 7   # 상자 4 + 화살표 3
    assert st.bar.retry_btn is None   # 피드백 5차: 흐름도 막대엔 「다시」 없음(기록 칸으로 다시 채움)
    c = w._ai_staged_scene_rect().center()
    assert abs(c.x() - req.center.x()) < 2 and abs(c.y() - req.center.y()) < 60
    assert w._ai_ctrl.flow_code() == _FLOW
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
    assert not any(b.property("dir") for b in w._ai_staged.bar.findChildren(QToolButton))   # §8 항목51: 버튼 대신 한 줄
    n_entries = len(w._ai_ctrl.entries())
    _say(w, "세로로")                                  # 짧은 방향 말은 AI 없이 그 자리에서
    st = w._ai_staged
    assert len(w._ai_ctrl.entries()) == n_entries and not w._ai_jobs
    assert st is not None and st.items != old_items
    assert all(it.scene() is None for it in old_items)
    assert len(w._undo) == n_undo
    assert w._ai_ctrl.flow_code().startswith("flowchart TD")
    # 세로가 되면 결과가 가로보다 높다
    r = w._ai_staged_scene_rect()
    assert r.height() > r.width() * 0.6
    _close_clean(w)


def test_flow_code_edit_redraws_and_bad_code_keeps_result():
    w = _shown_window()
    with _fake_gateway():
        _make_flow(w)
        assert _wait_until(lambda: w._ai_staged is not None)
    w._ai_replace_flow(_FLOW + "\n  D --> E[경보]")
    assert len(w._ai_staged.items) == 9
    before = list(w._ai_staged.items)
    w._ai_replace_flow("이건 머메이드가 아님")
    assert w._ai_staged.items == before and "코드 오류" in w._ai_staged.request.entry.status_text()
    _close_clean(w)


def test_code_insert_without_ai():
    w = _shown_window()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value=""):
        w._insert_mermaid_code(_FLOW)
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
    chain = " --> ".join(f"N{i}[단계 {i}]" for i in range(12))
    s0 = w._view.transform().m11()
    w._insert_mermaid_code("flowchart LR\n  " + chain)
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
    req = w._ai_ctrl.request_make(text, kind="symbol")
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


def test_click_toggles_pick_and_accept_inserts_as_one_step():
    # 피드백 3차: 클릭 하나로 나머지가 사라지는 건 가혹 → 클릭은 고름/풀기(실선+☑), 넣기는 「채택」.
    w = _shown_window()
    with _fake_svg():
        req = _make_symbol(w)
    st = w._ai_staged
    assert st.picked == set() and st.bar.retry_btn is None            # 기본은 아무것도 안 고름, 「다시」 없음
    n_undo = len(w._undo)
    st.cands[2].items[0].setSelected(True)
    _app.processEvents()
    assert w._ai_staged is st and st.picked == {2} and st.bar.accept_btn.text() == "1개 채택"
    assert all(it.scene() is w._scene for c in st.cands for it in c.items)   # 아무것도 안 사라짐
    assert not any(it.isSelected() for c in st.cands for it in c.items)       # 캔버스 선택은 걷힘
    st.cands[2].items[0].setSelected(True)                                    # 다시 누르면 풀림
    _app.processEvents()
    assert st.picked == set()
    st.cands[2].items[0].setSelected(True)
    _app.processEvents()
    st.bar.accept_btn.click()
    assert w._ai_staged is None and all(it.scene() is w._scene for it in st.cands[2].items)
    assert all(it.scene() is None for i, c in enumerate(st.cands) if i != 2 for it in c.items)
    assert len(w._undo) == n_undo + 1 and "1개 넣음" in req.entry.status_text()
    w.undo()
    assert all(it.scene() is None for it in st.cands[2].items)
    _close_clean(w)


def test_select_all_toggle():
    w = _shown_window()
    with _fake_svg():
        _make_symbol(w)
    st = w._ai_staged
    st.all_btn.click()
    assert st.picked == set(range(SYMBOL_COUNT)) and st.all_btn.text() == "모두 풀기"
    st.all_btn.click()
    assert st.picked == set() and st.all_btn.text() == "모두 선택"
    _close_clean(w)


def test_check_boxes_pick_several_then_accept():
    # 2026-10-05 피드백: Ctrl+클릭은 이 캔버스에서 선택을 바꿔 버려(추가는 Shift) 마지막 하나만 골라졌다 → 칸마다 □.
    w = _shown_window()
    with _fake_svg():
        _make_symbol(w)
    st = w._ai_staged
    view = w._view
    s_ = view.transform().m11()

    def press_check(i):
        r = w._ai_check_scene_rect(st.slots[i], s_)
        return _mouse(w, _QMouseEvent.Type.MouseButtonPress, view.mapFromScene(r.center()))
    assert press_check(0) is True and press_check(4) is True
    assert st.picked == {0, 4} and st.bar.accept_btn.text() == "2개 채택"
    assert press_check(4) is True and st.picked == {0}          # 다시 누르면 빠짐
    assert press_check(3) is True
    st.bar.accept_btn.click()
    assert w._ai_staged is None
    kept = [i for i, c in enumerate(st.cands) if c.items[0].scene() is w._scene]
    assert kept == [0, 3]
    _close_clean(w)


def test_accept_without_checks_does_nothing():
    w = _shown_window()
    with _fake_svg():
        _make_symbol(w)
    st = w._ai_staged
    st.bar.accept_btn.click()
    assert w._ai_staged is st    # 고른 게 없으면 그대로(안내만)
    _close_clean(w)


def test_symbol_count_comes_from_saved_setting():
    # §8 항목51: 「고급 › 후보 수」 칸은 없앴다 — 옛 패널에서 저장한 값이 있으면 그대로 쓴다(기본 6).
    w = _shown_window()
    app_settings().setValue("ai_panel/symbol_count", 3)
    try:
        with _fake_svg():
            _make_symbol(w)
        assert len(w._ai_staged.slots) == 3
    finally:
        app_settings().setValue("ai_panel/symbol_count", 6)
    _close_clean(w)


def test_history_menu_refills_center_card():
    from PIL import Image
    w = _shown_window()
    req = w._ai_ctrl.request_make("송신기 → 안테나", kind="flow", image=Image.new("RGB", (40, 30), "white"),
                                  image_name="손그림.png")
    w._ai_fill_history_menu()
    act = next(a for a in w._ai_history_menu.actions() if a.data() is req.entry)
    assert "흐름도" in act.text()
    act.trigger()
    sp = w._start_prompt
    assert sp.isVisible() and sp._edit.toPlainText() == "송신기 → 안테나" and sp._attached_image is req.image
    _close_clean(w)


def test_candidates_survive_other_edits_and_new_make_keeps_picked():
    # 피드백 3차: 다른 편집을 해도 후보 줄은 남는다. 새 만들기는 고른 것은 넣고 안 고른 것은 버림.
    w = _shown_window()
    with _fake_svg():
        req = _make_symbol(w)
    st = w._ai_staged
    w.push_undo_add(_mk_pen_rect(w, x=900, y=900))
    w.undo()
    assert w._ai_staged is st and all(it.scene() is w._scene for c in st.cands for it in c.items)
    w._ai_toggle_check(1)
    with _fake_svg():
        w._ai_ctrl.request_make("다른 것", kind="symbol")
        assert _wait_until(lambda: not w._ai_jobs)
    assert "1개 넣음" in req.entry.status_text()
    assert st.cands[1].items[0].scene() is w._scene and st.cands[0].items[0].scene() is None
    _close_clean(w)


def _save_choosing(w, label_start, tmp):
    from PyQt6.QtWidgets import QMessageBox
    w._doc_path = str(tmp)

    def pick(box):
        return next(b for b in box.buttons() if b.text().startswith(label_start))
    with _patch.object(QMessageBox, "exec", return_value=0),             _patch.object(QMessageBox, "clickedButton", new=lambda self: pick(self)):
        w._save_doc()


def test_save_with_candidates_asks(tmp_path):
    w = _shown_window()
    with _fake_svg():
        _make_symbol(w)
    st = w._ai_staged
    _save_choosing(w, "취소", tmp_path / "a.ecad")
    assert w._ai_staged is st and not os.path.exists(tmp_path / "a.ecad")      # 취소면 저장 안 함
    w._ai_toggle_check(0)
    _save_choosing(w, "고른 1개", tmp_path / "b.ecad")
    assert w._ai_staged is None and st.cands[0].items[0].scene() is w._scene
    assert st.cands[1].items[0].scene() is None and os.path.exists(tmp_path / "b.ecad")
    with _fake_svg():
        _make_symbol(w)
    st2 = w._ai_staged
    _save_choosing(w, "후보 버리고", tmp_path / "c.ecad")
    assert w._ai_staged is None and all(it.scene() is None for c in st2.cands for it in c.items)
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
    assert w._start_prompt.isVisible() and w._start_prompt.kind_hint() == "symbol"
    with _fake_svg():
        req = _make_symbol(w, "안테나")
    st = w._ai_staged
    assert req.replace_target is rect
    # sceneBoundingRect는 선택 손잡이 여백까지 커져 실제 도형 크기가 아니다(pitfalls "좌표계·변환") — rect() 기준
    assert min(s.top() for s in st.slots) > rect.mapToScene(rect.rect()).boundingRect().bottom()   # 도형 아래 줄
    n_undo = len(w._undo)
    st.cands[0].items[0].setSelected(True)
    _app.processEvents()
    st.bar.accept_btn.click()
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
from easycad.canvas.host_aimake import CANCELLED_TEXT, TRACE_HINT, TRACE_PHOTO_OPACITY, _TRACE_HINT_QSS
from PyQt6.QtWidgets import QSlider

_SPEC = {"ops": [{"op": "box", "id": "a", "x1": 100, "y1": 80, "x2": 300, "y2": 200},
                 {"op": "text", "x": 120, "y": 140, "text": "TX"}]}


def _photo(w=800, h=600):
    from PIL import Image
    return Image.new("RGB", (w, h), "white")


def _attach_trace(w, img=None):
    """가운데 칸에 사진만 넣고 「만들기」 — 베끼기로 짐작해 사진이 캔버스 바닥에 깔린다."""
    w._open_ai_prompt()
    sp = w._start_prompt
    sp._set_attached_image(img or _photo(), "IMG_7074.jpg")
    assert sp.submit() == "trace"
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
    # 사진은 카드 사이 빈 띠 가운데(`_ai_ensure_visible`) — [2026-10-07] 왼쪽 카드가 넓어져(칸 48→56)
    # viewport 가운데와 띠 가운데가 더 벌어졌으므로 띠 가운데로 잰다.
    c = w._view.mapToScene(w._ai_free_viewport_rect(w._view).center())
    assert abs(tr.rect.center().x() - c.x()) < 40
    assert w._start_prompt.isHidden()        # 사진이 깔린 동안 빈 도면이어도 가운데 칸은 저절로 안 뜬다
    assert w._ai_trace.remove_btn.text() == "취소"
    w._ai_trace.remove_btn.click()                          # 「취소」(옛 「사진 빼기」)
    assert w._ai_trace is None
    _close_clean(w)


def test_trace_bar_make_button_and_rotate():
    # 피드백(2026-10-06): 사진 위 막대에도 「만들기」, 90° 돌리기는 붙인 사진 자체를 돌리고 모서리를 처음 자리로.
    w = _shown_window()
    tr = _attach_trace(w, _photo(800, 600))
    tr.quad[0] = (30.0, 20.0)
    tr.rotate_btn.click()
    tr2 = w._ai_trace
    assert tr2 is not tr and tr2.original.size == (600, 800) and tr2.name == "IMG_7074.jpg"
    assert tr2.fitted.size[0] < tr2.fitted.size[1] and tr2.quad[0] == (0.0, 0.0)
    assert _TRACE_HINT_QSS in tr2.hint.styleSheet()
    with _fake_trace(wait_cancel=True):
        tr2.make_btn.click()
        assert w._ai_trace.running and not tr2.make_btn.isVisibleTo(tr2.bar) and not tr2.rotate_btn.isVisibleTo(tr2.bar)
        assert "font-weight:700" in tr2.hint.styleSheet()
        tr2.cancel_btn.click()
        assert _wait_until(lambda: not w._ai_jobs, 5000)
    _close_clean(w)


def test_trace_reset_corners_button_shows_only_after_moving():
    w = _shown_window()
    tr = _attach_trace(w)
    assert not tr.reset_btn.isVisibleTo(tr.bar)
    corner = w._view.mapFromScene(w._ai_trace_corner_scene(tr, 0))
    _mouse(w, _QMouseEvent.Type.MouseButtonPress, corner)
    _mouse(w, _QMouseEvent.Type.MouseMove, corner + QPoint(40, 30))
    _mouse(w, _QMouseEvent.Type.MouseButtonRelease, corner + QPoint(40, 30))
    assert tr.reset_btn.isVisibleTo(tr.bar)
    tr.reset_btn.click()
    assert not tr.reset_btn.isVisibleTo(tr.bar)
    _close_clean(w)


def test_trace_mix_slider_full_shows_only_original():
    # 2026-10-06 2차: 원본을 도면 위에 덮어 그려 100%면 도면 선이 안 보이고 원본만(바닥에 깔면 선이 늘 위를 덮었음).
    from PIL import Image
    w = _shown_window()
    _attach_trace(w, Image.new("RGB", (800, 600), (255, 0, 0)))
    with _fake_trace():
        w._ai_trace_make()
        assert _wait_until(lambda: w._ai_staged is not None)
    st = w._ai_staged
    slider = st.bar.findChildren(QSlider)[0]
    on_line = w._view.mapFromScene(_QPointF(st.photo_rect.left() + 200 * 2.0, st.photo_rect.top() + 80 * 2.0))

    def px():
        return w._view.viewport().grab().toImage().pixelColor(on_line)
    slider.setValue(0)
    _app.processEvents()
    assert px().red() < 200 or px().green() > 100   # 도면 선(빨강 아님)
    slider.setValue(100)
    _app.processEvents()
    c = px()
    assert c.red() > 240 and c.green() < 20 and c.blue() < 20   # 원본만
    _close_clean(w)


def test_load_image_path_applies_exif_orientation():
    from PIL import Image
    path = os.path.join(_TMP, "exif_rot.jpg")
    im = Image.new("RGB", (80, 40), "white")
    exif = im.getexif()
    exif[0x0112] = 6   # 시계 방향 90° 돌려 보여라(폰 세로 사진)
    im.save(path, exif=exif)
    w = _shown_window()
    w._start_prompt._load_image_path(path)
    assert w._start_prompt._attached_image.size == (40, 80)
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


def test_trace_make_places_result_on_photo_with_photo_view_toggle():
    # 피드백(2026-10-06): 사진은 도면에 넣지 않고 고르는 동안만 바닥에 겹쳐 본다(켜고 끄기·진하기), 채택하면 사라짐.
    w = _shown_window()
    tr = _attach_trace(w)
    center = tr.rect.center()
    with _fake_trace():
        req = w._ai_trace_make()
        assert w._ai_trace.running
        assert _wait_until(lambda: w._ai_staged is not None)
    st = w._ai_staged
    assert w._ai_trace is None
    assert req.entry.status_text() == STAGED_TEXT
    assert not any(type(it).__name__ == "_ImageItem" for it in st.items)
    assert not any(type(it).__name__ == "_ImageItem" for it in w._scene.items())
    assert st.photo is not None and st.photo_shown
    assert abs(st.photo_rect.center().x() - center.x()) < 3 and abs(st.photo_rect.center().y() - center.y()) < 3
    show = st.bar.findChildren(QCheckBox)[0]
    slider = st.bar.findChildren(QSlider)[0]
    assert show.text() == "원본 보기" and slider.value() == TRACE_PHOTO_OPACITY
    slider.setValue(80)
    assert st.photo_opacity == 80
    show.setChecked(False)
    assert not st.photo_shown and not slider.isEnabled()
    w._view.grab()   # 그리기 경로가 터지지 않는지
    show.setChecked(True)
    w._view.grab()
    assert st.photo.width() == 800   # 비교용은 AI용(1600 이하로 줄인 것)이 아니라 편 원본 해상도
    st.bar.accept_btn.click()
    assert w._ai_staged is None
    w.undo()   # 한 번에 결과 전부 사라짐
    assert all(it.scene() is None for it in st.items)
    _close_clean(w)


def test_trace_cancel_returns_to_setup():
    w = _shown_window()
    _attach_trace(w)
    with _fake_trace(wait_cancel=True):
        req = w._ai_trace_make()
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
        w._ai_trace_make()
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
        w._ai_trace_make()
        assert _wait_until(lambda: w._ai_staged is not None)
        first = w._ai_staged
        first.bar.retry_btn.click()
        assert w._ai_trace is not None and w._ai_trace.quad[0] == (30.0, 20.0)   # 같은 모서리로 되살림
        assert _wait_until(lambda: w._ai_staged is not None and w._ai_staged is not first)
    assert all(it.scene() is None for it in first.items)
    assert len(w._ai_ctrl.entries()) == 2
    _close_clean(w)



# ── 피드백 2차(2026-10-05): 가운데 안내·종류별 기록·기록 지우기·빈 자리에 놓기 ───────────────────

def test_remove_entry_and_clear_history():
    w = _shown_window()
    c = w._ai_ctrl
    for t in ("a", "b", "c"):
        c.request_make(t, kind="symbol")
    ents = c.entries()
    c.remove_entry(ents[1])
    assert [e.request.text for e in c.entries()] == ["a", "c"]
    w._ai_clear_history()                              # 기록 메뉴 「기록 모두 지우기」
    assert c.entries() == []
    _close_clean(w)


def test_removing_running_entry_cancels_generation():
    import threading
    gate = threading.Event()

    def slow(*_a, **_k):
        gate.wait(5)
        return _FLOW, "m"
    w = _shown_window()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"),             _patch("easycad.ai.text_to_flow.generate_flow", side_effect=slow):
        req = _make_flow(w)
        assert w._ai_jobs
        w._ai_ctrl.remove_entry(req.entry)
        assert not w._ai_jobs                          # 떼어 냄
        gate.set()
        _wait_until(lambda: False, 400)
    assert w._ai_staged is None                        # 늦게 온 결과는 버림
    _close_clean(w)


def test_flow_result_avoids_existing_drawing():
    w = _shown_window()
    c = w._view.mapToScene(w._view.viewport().rect().center())
    block = _mk_pen_rect(w, x=c.x() - 150, y=c.y() - 100, ww=300, hh=200)
    w.push_undo_add(block)
    with _fake_gateway():
        _make_flow(w)
        assert _wait_until(lambda: w._ai_staged is not None)
    st = w._ai_staged
    r = w._ai_items_rect(st.items)
    assert not r.intersects(block.mapToScene(block.rect()).boundingRect())
    assert len(st.items) == 7 and all(it.scene() is w._scene for it in st.items)
    n = len(w._undo)
    st.bar.discard_btn.click()                         # 옮겨 다시 그린 것도 기록 한 칸
    assert len(w._undo) == n - 1 and block.scene() is w._scene
    _close_clean(w)


def test_symbol_row_and_trace_photo_avoid_existing_drawing():
    w = _shown_window()
    c = w._view.mapToScene(w._view.viewport().rect().center())
    block = _mk_pen_rect(w, x=c.x() - 200, y=c.y() - 60, ww=400, hh=120)
    w.push_undo_add(block)
    br = block.mapToScene(block.rect()).boundingRect()
    with _fake_svg():
        _make_symbol(w)
    row = w._ai_staged_scene_rect()
    assert not row.intersects(br)
    w._ai_discard_staged()
    tr = _attach_trace(w)
    assert not tr.rect.intersects(br)
    _close_clean(w)


def test_find_free_center_returns_near_when_empty():
    w = _shown_window()
    near = QPointF(1234.0, -567.0)
    assert w._ai_find_free_center(w._scene, 100, 80, near) == near
    _close_clean(w)


def test_theme_switch_repaints_floating_bars():
    # 2026-10-05 실제 창: 결과 막대가 떠 있는 채 라이트로 바꾸면 막대만 어둡게 남음(QSS 테마 박제 함정) → 다시 칠함.
    w = _shown_window()
    with _fake_svg():
        _make_symbol(w)
    _attach_trace(w)
    bars = [w._ai_staged.bar, w._ai_trace.bar]
    w._apply_theme(not w._dark)
    for bar in bars:
        assert "aiStagingBar" in bar.styleSheet()
        assert all(not b.property("aiIcon") or not b.icon().isNull() for b in bar.findChildren(QToolButton))
    w._apply_theme(not w._dark)
    _close_clean(w)



# ── 피드백 4차(2026-10-05): 칸 빈 곳 클릭·흐름 방향 화살표·이어 만들기 ─────────────────────

def test_click_empty_space_inside_slot_toggles_pick():
    w = _shown_window()
    with _fake_svg():
        _make_symbol(w)
    st = w._ai_staged
    view = w._view
    slot = st.slots[2]
    near_corner = view.mapFromScene(QPointF(slot.left() + 6, slot.bottom() - 6))   # 도형 선이 없는 칸 구석
    assert _mouse(w, _QMouseEvent.Type.MouseButtonPress, near_corner) is True
    assert st.picked == {2}
    assert _mouse(w, _QMouseEvent.Type.MouseButtonPress, near_corner) is True
    assert st.picked == set()
    _close_clean(w)


def test_flow_arrows_enter_along_flow_direction():
    # 피드백 4차 사용자 화면: 위아래로 멀리 떨어진 짝이 위·아래 변으로 들어가며 같은 열 좁은 틈(40)을 지나
    # 마지막 꺾임(12)이 화살촉+모서리보다 짧아 겹쳤다 → 앞으로 가는 화살표는 흐름 방향 변으로(가로면 오른쪽→왼쪽).
    import math
    code = ("flowchart LR\n A[내부 구조] --> B[기저대역부]\n A --> C[RF부]\n B --> D[데이터입력]\n"
            " B --> E[부호화기]\n B --> F[변조기]\n C --> G[상향변환기]\n C --> H[전력증폭기]\n C --> I[안테나]")
    w = CanvasWindow()
    _n, _a, _d, added = w._build_mermaid_items(code)
    arrows = [it for it in added if isinstance(it, _PolyArrowItem)]
    boxes = [it for it in added if not isinstance(it, _PolyArrowItem)]
    assert len(arrows) == 8
    for arr in arrows:
        pts = [arr.mapToScene(q) for q in arr._pts]
        last = math.hypot(pts[-1].x() - pts[-2].x(), pts[-1].y() - pts[-2].y())
        assert last >= 25, last                                     # 고치기 전 최솟값 12
        end = pts[-1]
        dst = next(b for b in boxes if b.mapRectToScene(b.rect()).adjusted(-1, -1, 1, 1).contains(end))
        assert abs(end.x() - dst.mapRectToScene(dst.rect()).left()) < 1.0   # 왼쪽 변으로 들어감


def _distinct_svg_gen(seen=None, tag="a"):
    """후보마다 다른 SVG(반지름이 다름) — 「바탕」 표시를 SVG 글로 맞추므로 같은 글이면 구분이 안 된다."""
    n = [0]

    def gen(*_a, refs=None, **_k):
        n[0] += 1
        if seen is not None:
            seen.append(refs)
        return (f'<svg viewBox="0 0 64 64"><circle cx="32" cy="32" r="{4 + n[0]}" fill="none" stroke="black"'
                f' id="{tag}{n[0]}"/></svg>'), "m"
    return gen


def _symbol_followup(w, text="두 개를 섞어서", seen=None, fail=False):
    inner = _distinct_svg_gen(seen, tag="b")

    def gen(*a, **k):
        if fail:
            raise RuntimeError("429 quota")
        return inner(*a, **k)
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.canvas.host_dialogs.generate_svg", side_effect=gen):
        n = len(w._ai_ctrl.entries())
        _say(w, text)
        assert len(w._ai_ctrl.entries()) == n + 1
        req = w._ai_ctrl.entries()[-1].request
        assert _wait_until(lambda: not w._ai_jobs)
    return req


def test_symbol_followup_keeps_row_and_adds_new_row_below():
    # 피드백 6차: 이어 만들기가 앞 후보를 걷어 버려 선택지가 줄었다 → 앞 줄은 그대로 두고 아래에 새 줄을 붙인다.
    w = _shown_window()
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.canvas.host_dialogs.generate_svg", side_effect=_distinct_svg_gen()):
        req0 = _make_symbol(w)
    st = w._ai_staged
    first_row = list(st.slots)
    w._ai_toggle_check(1)
    w._ai_toggle_check(4)
    seen = []
    req = _symbol_followup(w, seen=seen)
    assert req.refs == [st.cands[1].svg, st.cands[4].svg] and all(r == req.refs for r in seen)
    assert w._ai_staged is st and st.request is req                              # 같은 후보 줄에 이어 붙음
    assert req0.entry.status_text().startswith("이어 만들기")
    assert len(st.cands) == SYMBOL_COUNT * 2 and len(st.slots) == SYMBOL_COUNT * 2 and st.row_start == SYMBOL_COUNT
    assert all(it.scene() is w._scene for c in st.cands for it in c.items)   # 앞 후보도 그대로
    assert st.slots[:SYMBOL_COUNT] == first_row
    assert min(r.top() for r in st.slots[SYMBOL_COUNT:]) > max(r.bottom() for r in first_row)   # 새 줄은 아래
    assert st.base_marks == {1, 4} and st.picked == set()                       # 고름은 풀고 바탕 표시
    assert w._ai_ctrl.followup() is None
    assert "[이어서]" in req.entry.title()
    assert req.entry.status_text().startswith(f"후보 {SYMBOL_COUNT}개")
    # 앞 줄 하나 + 새 줄 하나를 골라 넣으면 둘 다 들어간다.
    w._ai_toggle_check(0)
    w._ai_toggle_check(SYMBOL_COUNT + 2)
    keep = st.cands[0].items + st.cands[SYMBOL_COUNT + 2].items
    w._ai_commit_picked()
    assert w._ai_staged is None and all(it.scene() is w._scene for it in keep)
    assert sum(1 for c in st.cands for it in c.items if it.scene() is not None) == len(keep)
    _close_clean(w)


def test_symbol_followup_failure_keeps_previous_rows():
    w = _shown_window()
    with _fake_svg():
        _make_symbol(w)
    st = w._ai_staged
    w._ai_toggle_check(0)
    req = _symbol_followup(w, fail=True)
    assert w._ai_staged is st and len(st.slots) == SYMBOL_COUNT and len(st.cands) == SYMBOL_COUNT
    assert "앞 후보는 그대로" in req.entry.status_text()
    _close_clean(w)


def test_symbol_followup_cuts_unfinished_jobs_of_previous_row():
    # 앞 줄이 다 오기 전에 이어 만들면 앞 줄의 남은 생성은 끊는다 — 늦게 온 앞 줄 후보가 새 줄 칸을 차지하지 않게.
    import time as _t
    from easycad.canvas.host_aimake import _AIJob
    w = _shown_window()
    with _fake_svg():
        _make_symbol(w)
    st = w._ai_staged
    st.slots.append(QRectF(st.slots[-1].translated(200, 0)))   # 아직 안 온 칸 하나
    fake = object()
    w._ai_jobs[fake] = _AIJob(st.request, fake, _t.monotonic())
    w._ai_toggle_check(0)
    with _patch("easycad.canvas.host_aimake._detach_worker") as det:
        _symbol_followup(w)
    det.assert_any_call(fake)
    assert fake not in w._ai_jobs and st.row_start == SYMBOL_COUNT and len(st.slots) == SYMBOL_COUNT * 2
    _close_clean(w)


def test_flow_followup_keeps_original_beside_new_result():
    # 피드백 6차: 끝에만 붙여 달라 해도 AI가 가운데를 고칠 수 있다 → 원본을 왼쪽에 남기고 새 결과를 오른쪽에, 다른 곳 표시.
    w, st, new, n_undo = _flow_compare()
    _close_clean(w)


def _flow_compare():
    w = _shown_window()
    with _fake_gateway():
        _make_flow(w)
        assert _wait_until(lambda: w._ai_staged is not None)
    st = w._ai_staged
    n_undo = len(w._undo)
    assert not [b for b in st.bar.findChildren(QToolButton) if b.text() == "이어 고치기"]   # 버튼 대신 막대 한 줄
    _say(w, "")
    assert "어떻게 고칠지" in w._ai_pill.text() and w._ai_staged is st   # 흐름도는 지시가 필요
    seen = []
    new_code = _FLOW + "\n  D --> E[경보]"

    def gen(*_a, base_code="", **_k):
        seen.append(base_code)
        return new_code, "m"
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.text_to_flow.generate_flow", side_effect=gen):
        _say(w, "감시장치 뒤에 경보 추가")
        req = w._ai_ctrl.entries()[-1].request
        assert _wait_until(lambda: w._ai_staged is not None and w._ai_staged is not st)
    assert seen == [_FLOW]
    new = w._ai_staged
    assert new.request is req and new.alt is st and len(new.items) == 9
    assert all(it.scene() is w._scene for it in st.items)                       # 원본은 그대로
    assert len(w._undo) == n_undo + 1
    assert w._ai_items_rect(new.items).left() > w._ai_items_rect(st.items).right()   # 새 결과는 오른쪽
    assert len(new.marks) == 2 and new.alt_marks == []                           # 경보 상자 + 화살표
    assert new.alt_bar is not None and not new.alt_bar.isHidden()
    assert new.bar.accept_btn.text() == "이걸로" and "2군데" in req.entry.status_text()
    assert "원본" in st.request.entry.status_text()
    return w, st, new, n_undo


def test_flow_compare_choose_new_removes_original_and_its_history():
    w, st, new, n_undo = _flow_compare()
    new.bar.accept_btn.click()
    assert w._ai_staged is None and new.alt_bar is None
    assert all(it.scene() is None for it in st.items) and all(it.scene() is w._scene for it in new.items)
    assert len(w._undo) == n_undo and st.undo_entry not in w._undo              # 원본 기록 칸째 빠짐
    assert new.request.entry.status_text() == ACCEPTED_TEXT
    _close_clean(w)


def test_flow_compare_choose_original_drops_new():
    w, st, new, n_undo = _flow_compare()
    pick = [b for b in new.alt_bar.findChildren(QToolButton) if b.text() == "이걸로"][0]
    pick.click()
    assert w._ai_staged is None
    assert all(it.scene() is w._scene for it in st.items) and all(it.scene() is None for it in new.items)
    assert len(w._undo) == n_undo and st.request.entry.status_text() == ACCEPTED_TEXT
    assert w._ai_ctrl.flow_code() == _FLOW
    _close_clean(w)


def test_flow_compare_discard_or_undo_restages_original():
    for how in ("discard", "undo"):
        w, st, new, n_undo = _flow_compare()
        if how == "discard":
            new.bar.discard_btn.click()
        else:
            w.undo()
        cur = w._ai_staged
        assert cur is not None and cur.items == st.items and cur.alt is None, how   # 원본이 다시 임시 결과
        assert all(it.scene() is None for it in new.items) and len(w._undo) == n_undo, how
        assert cur.request.entry.status_text() == STAGED_TEXT, how
        _close_clean(w)


def test_flow_compare_auto_accept_keeps_both():
    w, st, new, n_undo = _flow_compare()
    w._ai_accept_staged()                                                         # 새 만들기·저장의 자동 채택 길목
    assert w._ai_staged is None
    assert all(it.scene() is w._scene for it in st.items + new.items)
    assert new.request.entry.status_text() == "✓ 넣음(원본도 남김)"
    _close_clean(w)


def test_flow_compare_direction_change_keeps_original():
    w, st, new, n_undo = _flow_compare()
    _say(w, "세로로")
    cur = w._ai_staged
    assert cur is not new and cur.alt is st and cur.request.result_text.startswith("flowchart TD")
    assert all(it.scene() is w._scene for it in st.items) and len(w._undo) == n_undo + 1
    assert w._ai_items_rect(cur.items).left() > w._ai_items_rect(st.items).right()
    _close_clean(w)


def _followup_from(w, alt, third):
    before = w._ai_staged
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.text_to_flow.generate_flow", return_value=(third, "m")):
        _say(w, "기록 추가", alt=alt)
        assert _wait_until(lambda: w._ai_staged is not None and w._ai_staged is not before)
    return w._ai_staged


_THIRD = _FLOW + "\n  D --> E[경보]\n  E --> F[기록]"


def test_flow_followup_again_from_new_keeps_older_original_on_canvas():
    # 피드백 6차 2회(사용자 결정): 비교에 안 끼는 쪽은 지우지 않고 캔버스에 남긴다.
    w, st, new, n_undo = _flow_compare()
    cur = _followup_from(w, False, _THIRD)
    assert cur.alt is new and all(it.scene() is w._scene for it in st.items)   # 가장 앞 원본은 캔버스에 남음
    assert st.undo_entry in w._undo and len(w._undo) == n_undo + 2
    assert "남김" in st.request.entry.status_text()
    assert len(cur.marks) == 2
    _close_clean(w)


def test_flow_followup_from_original_side():
    w, st, new, n_undo = _flow_compare()
    cur = _followup_from(w, True, _THIRD)
    assert cur.alt is st and cur is not new                                       # 원본이 바탕
    assert all(it.scene() is w._scene for it in new.items) and "남김" in new.request.entry.status_text()
    assert len(cur.marks) == 4                                                    # 원본 대비 상자 2 + 화살표 2
    _close_clean(w)


def test_flow_compare_bars_have_same_controls():
    w, st, new, n_undo = _flow_compare()
    alt_texts = [b.text() for b in new.alt_bar.findChildren(QToolButton) if b.text()]
    new_texts = [b.text() for b in new.bar.findChildren(QToolButton) if b.text()]
    for t in ("이걸로", "버리기"):
        assert t in alt_texts and t in new_texts, t
    assert "둘 다 넣기" in new_texts
    assert new.alt_line is not None and new.bar.line is not None   # 양쪽 다 입력 한 줄(방향·이어 고치기)
    _close_clean(w)


def test_flow_compare_keep_both_button():
    w, st, new, n_undo = _flow_compare()
    [b for b in new.bar.findChildren(QToolButton) if b.text() == "둘 다 넣기"][0].click()
    assert w._ai_staged is None and len(w._undo) == n_undo + 1
    assert all(it.scene() is w._scene for it in st.items + new.items)
    assert st.request.entry.status_text() == ACCEPTED_TEXT
    _close_clean(w)


def test_flow_compare_discard_original_only():
    w, st, new, n_undo = _flow_compare()
    [b for b in new.alt_bar.findChildren(QToolButton) if b.text() == "버리기"][0].click()
    assert w._ai_staged is new and new.alt is None and new.alt_bar is None and new.both_btn is None
    assert all(it.scene() is None for it in st.items) and len(w._undo) == n_undo
    assert new.bar.accept_btn.text() == "채택" and new.request.entry.status_text() == STAGED_TEXT
    new.bar.accept_btn.click()                                                    # 보통 채택으로 돌아옴
    assert w._ai_staged is None and new.request.entry.status_text() == ACCEPTED_TEXT
    _close_clean(w)


def test_flow_compare_original_direction_change_redraws_in_place():
    w, st, new, n_undo = _flow_compare()
    _say(w, "세로로", alt=True)
    cur = w._ai_staged
    assert cur is new and cur.alt is st and st.request.result_text.startswith("flowchart TD")
    assert len(w._undo) == n_undo + 1 and w._undo[-1] is new.undo_entry and st.undo_entry in w._undo
    assert all(it.scene() is w._scene for it in st.items)
    assert w._ai_items_rect(st.items).right() < w._ai_items_rect(new.items).left()   # 새 결과와 안 겹침
    pick = [b for b in new.alt_bar.findChildren(QToolButton) if b.text() == "이걸로"][0]
    pick.click()                                                                  # 바꾼 원본을 고르면 그대로 남음
    assert all(it.scene() is w._scene for it in st.items) and all(it.scene() is None for it in new.items)
    _close_clean(w)


def test_mermaid_long_labels_wrap_and_fit_box():
    # 피드백 6차 2회: 상자 폭 120 고정이라 긴 글이 하한 5pt로 줄어도 넘쳤다 → 두 줄로 나누고 상자를 글에 맞춰 키움.
    w = CanvasWindow()
    code = ("flowchart LR\n A[고출력 증폭 모듈 1 HPA Module 1] --> B[LDMOS/GaN 트랜지스터 LDMOS/GaN Transistor]\n"
            " B --> C[출력 정합 회로 Output Matching]")
    _n, _a, _d, added = w._build_mermaid_items(code)
    for it in added[:3]:
        box = it.mapRectToScene(it.rect())
        lb = it._label.mapRectToScene(it._label.boundingRect())
        assert box.contains(lb), (box, lb)
        # 글자 크기 하한은 폭 상한(280)에 안 걸릴 때만 — 헤드리스는 한글 글꼴이 없어 글자 폭이 달라진다.
        assert it._label.font().pointSize() >= w._MMD_LABEL_PT or box.width() >= w._MMD_NODE_W_MAX - 0.5, box.width()
    assert added[1]._label.toPlainText() == "LDMOS/GaN 트랜지스터\nLDMOS/GaN Transistor"
    short = w._build_mermaid_items("flowchart LR\n A[송신기] --> B[안테나]")[3]
    assert short[0].rect().width() == 120 and short[0].rect().height() == 56   # 짧은 글은 예전 크기 그대로


def test_bar_line_examples_rotate_while_empty():
    from easycad.canvas.host_aimake import BAR_EXAMPLES, _BarLine
    line = _BarLine(BAR_EXAMPLES["flow"])
    first = line.placeholderText()
    line._next_example()
    assert line.placeholderText() != first and line.placeholderText() in BAR_EXAMPLES["flow"]
    line.setText("쓰는 중")
    shown = line.placeholderText()
    line._next_example()
    assert line.placeholderText() == shown        # 쓰는 동안엔 안 바뀜


def test_bar_line_switches_kind():
    w = _shown_window()
    with _fake_gateway():
        _make_flow(w, "방송용 카메라")
        assert _wait_until(lambda: w._ai_staged is not None)
    st = w._ai_staged
    got = []
    w._ai_ctrl.make_requested.connect(got.append)
    _say(w, "심볼로 바꿔 줘")
    assert all(it.scene() is None for it in st.items)          # 지금 결과는 버리고
    assert got and got[-1].kind == "symbol" and got[-1].text == "방송용 카메라"   # 처음 요청을 그 종류로
    _close_clean(w)


def test_flow_diff_matches_by_text_not_id():
    from easycad.canvas.host_aimake import _flow_diff_items
    old = "flowchart LR\n A[송신] --> B[수신]\n B --> C[끝]"
    new = "flowchart LR\n N1[송신] --> N2[수신]\n N2 --> N3[끝]\n N3 --> N4[경보]"
    items = list(range(4 + 3))       # 노드 4 → 화살표 3 순서
    assert _flow_diff_items(new, old, items) == [3, 6]
    assert _flow_diff_items(old, new, list(range(5))) == []
    assert _flow_diff_items(new, old, [1, 2]) == []   # 개수 안 맞으면 표시 안 함


# ── 부분 다시 베끼기(2026-10-06): 결과에서 상자로 고른 곳만 다시 그려 같은 결과에 바꿔 끼움 ─────────────

def test_ops_in_region_and_region_content():
    from easycad.ai.photo_to_ops import ops_in_region, region_content
    ops = [{"op": "box", "x1": 100, "y1": 80, "x2": 300, "y2": 200},
           {"op": "text", "x": 500, "y": 400, "text": "밖"},
           {"op": "line", "pts": [[110, 90], [150, 90]]}]
    assert ops_in_region(ops, (50, 50, 320, 220)) == [ops[0], ops[2]]
    content = region_content(_photo(), "TASK", (50, 50, 320, 220), prev_ops=ops[:1], note="표 칸이 빠짐")
    assert "x 50~320" in content[0]["text"] and "표 칸이 빠짐" in content[0]["text"] and '"x1": 100' in content[0]["text"]
    assert len(content) == 3


def _staged_trace(w):
    _attach_trace(w)
    with _fake_trace():
        w._ai_trace_make()
        assert _wait_until(lambda: w._ai_staged is not None)
    return w._ai_staged


def _drag_region(w, st, x1, y1, x2, y2):
    o = st.photo_rect.topLeft()
    a = w._view.mapFromScene(_QPointF(o.x() + x1 * 2.0, o.y() + y1 * 2.0))
    b = w._view.mapFromScene(_QPointF(o.x() + x2 * 2.0, o.y() + y2 * 2.0))
    _mouse(w, _QMouseEvent.Type.MouseButtonPress, a)
    _mouse(w, _QMouseEvent.Type.MouseMove, b)
    _mouse(w, _QMouseEvent.Type.MouseButtonRelease, b)


def test_trace_region_redraw_replaces_only_inside_and_stays_one_undo():
    w = _shown_window()
    st = _staged_trace(w)
    n_undo = len(w._undo)
    old_box, old_text = st.items[0], st.items[1]
    st.region_btn.click()
    assert st.region_picking and st.region_btn.isChecked()
    _drag_region(w, st, 80, 60, 320, 120)             # 상자 가운데(200,140)는 밖, 글자(120,140)도 밖 → 둘 다 남아야
    _drag_region(w, st, 50, 50, 350, 220)             # 다시 고르기 아님 — 고르기는 첫 상자로 끝남
    assert not st.region_picking and st.region is not None and st.region_bar.isVisible()
    fu = w._ai_ctrl.followup()
    assert fu is not None and fu["kind"] == "trace" and fu["base"] is st
    st.region_bar.findChildren(QToolButton)[-1].click()   # 상자 막대 「취소」
    assert st.region is None and w._ai_ctrl.followup() is None
    st.region_btn.click()
    _drag_region(w, st, 50, 50, 350, 220)             # 상자·글자 둘 다 안
    calls = []

    def region(_client, _photo_, reg, *, model, note="", prev_ops=(), **_k):
        calls.append((reg, note, list(prev_ops)))
        return {"ops": [{"op": "box", "id": "n", "x1": 60, "y1": 60, "x2": 200, "y2": 210}]}, {"tries": 1}
    st.bar.line.setText("표 칸이 빠짐")   # 막대 한 줄의 글이 틀린 점
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.photo_to_ops.generate_ops_region", side_effect=region):
        st.region_make_btn.click()
        assert st.region_worker is not None
        assert _wait_until(lambda: st.region_worker is None)
    assert calls and calls[0][1] == "표 칸이 빠짐" and len(calls[0][2]) == 2   # 이전 결과(상자·글자)도 같이 보냄
    assert old_box.scene() is None and old_text.scene() is None
    new = [it for it in st.items if it.scene() is w._scene]
    assert len(new) == 1 and w._ai_staged is st and len(w._undo) == n_undo   # 같은 결과·같은 되돌리기 칸
    assert st.region is None and st.region_bar is None and w._ai_ctrl.followup() is None
    st.bar.accept_btn.click()
    w.undo()
    assert new[0].scene() is None
    _close_clean(w)


def test_trace_region_discarded_result_is_dropped():
    import threading
    gate = threading.Event()

    def slow(*_a, **_k):
        gate.wait(5)
        return {"ops": [{"op": "box", "x1": 60, "y1": 60, "x2": 200, "y2": 210}]}, {}
    w = _shown_window()
    st = _staged_trace(w)
    st.region_btn.click()
    _drag_region(w, st, 50, 50, 350, 220)
    n_items = len(w._scene.items())
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.photo_to_ops.generate_ops_region", side_effect=slow):
        st.region_make_btn.click()
        st.bar.discard_btn.click()                       # 다시 그리는 중에 결과 버리기
        gate.set()
        _wait_until(lambda: False, 400)
    assert w._ai_staged is None and len(w._scene.items()) < n_items
    _close_clean(w)


def test_trace_region_cancel_while_running_keeps_old_result():
    import threading
    gate = threading.Event()

    def slow(*_a, **_k):
        gate.wait(5)
        return {"ops": [{"op": "box", "x1": 60, "y1": 60, "x2": 200, "y2": 210}]}, {}
    w = _shown_window()
    st = _staged_trace(w)
    old = list(st.items)
    st.region_btn.click()
    _drag_region(w, st, 50, 50, 350, 220)
    with _patch("easycad.ai.gateway.resolve_api_key", return_value="k"), \
            _patch("easycad.ai.photo_to_ops.generate_ops_region", side_effect=slow):
        req = w._ai_region_make()
        st.region_bar.findChildren(QToolButton)[-1].click()   # 다시 그리는 중 「취소」
        assert st.region is None and st.region_worker is None
        gate.set()
        _wait_until(lambda: False, 400)
    assert req.entry.status_text() == CANCELLED_TEXT
    assert st.items == old and all(it.scene() is w._scene for it in old)   # 늦게 온 결과는 버림
    _close_clean(w)


def test_trace_region_picking_lets_pan_buttons_through():
    # 2026-10-06 실사용: 「부분 다시」 고르는 중 휠·우클릭 끌기 이동이 막혀 있었음 — 왼쪽만 가로챈다.
    w = _shown_window()
    st = _staged_trace(w)
    st.region_btn.click()
    c = w._view.viewport().rect().center()
    assert _mouse(w, _QMouseEvent.Type.MouseButtonPress, c, Qt.MouseButton.RightButton) is False
    assert _mouse(w, _QMouseEvent.Type.MouseButtonPress, c, Qt.MouseButton.MiddleButton) is False
    assert _mouse(w, _QMouseEvent.Type.MouseButtonPress, c, Qt.MouseButton.LeftButton) is True
    assert st.region_picking
    _close_clean(w)


# ── §8 항목51(2026-10-16): Mermaid는 AI 화면에서 빼고 「삽입 › Mermaid 코드 가져오기…」에만 ──────────────────

def test_mermaid_code_import_menu_checks_code_and_stages():
    from PyQt6.QtWidgets import QDialog
    from easycad.canvas.host_dialogs import _MermaidCodeDialog
    w = _shown_window()
    menu_acts = [a for m in w.menuBar().actions() if m.menu() for a in m.menu().actions()]
    assert w._act_mmd_code in menu_acts and w._act_mmd_code not in w._toolbar.actions()
    dlg = _MermaidCodeDialog(w)
    dlg._edit.setPlainText("그냥 글")
    dlg._on_accept()
    assert dlg.result() != QDialog.DialogCode.Accepted and "flowchart" in dlg._error.text()   # 틀리면 닫지 않고 알림
    dlg._edit.setPlainText(_FLOW)
    dlg._on_accept()
    assert dlg.result() == QDialog.DialogCode.Accepted
    with _patch.object(_MermaidCodeDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
            _patch.object(_MermaidCodeDialog, "code", return_value=_FLOW):
        st = w._import_mermaid_code()
    assert st is not None and w._ai_staged is st and len(st.items) == 7 and not w._ai_jobs
    assert st.request.entry.title().startswith("흐름도")
    _close_clean(w)
