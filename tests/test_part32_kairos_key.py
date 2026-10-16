"""§8 항목40·41(2026-10-16) — 「KAIROS로 만들기」 이름 + 처음 실행 때 키 넣기 + 남은 크레딧.

키 없이 만들기 → 「KAIROS 연결」 창(모달 아님) → 키를 넣고 확인하면 같은 요청을 이어서. 가운데 칸 아래 남은 크레딧 줄
(§8 항목51 — 옛 오른쪽 패널 자리).
"""
from contextlib import contextmanager
from unittest.mock import patch as _patch

from _shared import *  # noqa: F401,F403

from easycad.canvas.host_dialogs import _AIGatewaySettingsDialog

_FLOW = "flowchart LR\n    A[휴가 신청] --> B[팀장 결재]"


def _shown_window():
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    _app.processEvents()
    return w


def _wait_until(cond, ms=5000):
    import time
    end = time.time() + ms / 1000
    while time.time() < end:
        _app.processEvents()
        if cond():
            return True
    return False


@contextmanager
def _key(value):
    with _patch("easycad.ai.gateway.resolve_api_key", return_value=value), \
            _patch("easycad.ai.text_to_mermaid.generate_mermaid", return_value=(_FLOW, "fake-model")):
        yield


def test_names_say_kairos_and_toolbar_stays_short():
    w = _shown_window()
    assert w._act_ai_make.text() == "KAIROS로 만들기"
    assert w._toolbar.widgetForAction(w._act_ai_make).text() == "AI"   # 10-11 결정(혼자 너무 큼) 유지
    assert w._act_ai_settings.text() == "KAIROS 연결 설정…"
    assert "KAIROS" in w._start_prompt._sub.text()


def test_credit_line_without_and_with_key():
    w = _shown_window()
    lbl = w._start_prompt._credit_lbl
    with _key(""):
        w._open_ai_prompt()
        assert "키 넣기" in lbl.text()
        w._close_ai_prompt()
    with _key("k"):   # conftest가 get_credit_balance를 (1234, 40000)으로 고정
        w._open_ai_prompt()
        assert _wait_until(lambda: "1,234 / 40,000" in lbl.text())


def test_credit_failure_shows_short_line():
    w = _shown_window()

    def boom(*_a, **_k):
        raise RuntimeError("401")
    with _key("k"), _patch("easycad.ai.gateway.get_credit_balance", side_effect=boom):
        w._open_ai_prompt()
        assert _wait_until(lambda: "못 읽었어요" in w._start_prompt._credit_lbl.text())


def test_make_without_key_opens_dialog_and_continues_after_key():
    from easycad.canvas.host_aimake import NO_KEY_TEXT
    w = _shown_window()
    p = w._ai_ctrl
    with _key(""):
        req = p.request_make("휴가 신청부터 팀장 결재까지", kind="flow")
    assert req.entry.status_text() == NO_KEY_TEXT and not w._ai_jobs
    dlg = w._ai_key_dialog
    assert dlg is not None and dlg.isVisible() and not dlg.isModal()
    assert dlg.windowTitle() == "KAIROS 연결"
    with _key("k"):
        dlg._key_edit.setText("k")
        dlg._on_accept()   # 확인 — 키 저장 + accept
        assert _wait_until(lambda: w._ai_staged is not None), "같은 요청이 이어서 만들어짐"
    assert len(p.entries()) == 1, "기록 칸이 새로 생기지 않음(같은 요청)"


def test_second_make_without_key_reuses_open_dialog():
    w = _shown_window()
    p = w._ai_ctrl
    with _key(""):
        p.request_make("하나", kind="flow")
        first = w._ai_key_dialog
        p.request_make("둘", kind="flow")
    assert w._ai_key_dialog is first


def test_dialog_folds_address_and_speaks_plainly():
    dlg = _AIGatewaySettingsDialog(reason="만들려면 KAIROS 키가 필요해요.")
    assert not dlg._url_box.isVisibleTo(dlg), "주소는 접어 둠(바꿀 일이 거의 없음)"
    dlg._url_toggle.setChecked(True)
    assert dlg._url_box.isVisibleTo(dlg)
    assert dlg._test_btn.text() == "연결 확인"
