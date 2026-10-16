"""§8 항목39(2026-10-16) — 빈 도면 가운데 입구 「무엇을 그릴까요?」.

짐작 규칙·보이는 조건(빈 도면·✕·AI 패널)·첫 획이면 사라짐·패널로 넘기기(흐름도는 바로 요청, 베끼기는 사진만).
"""
from _shared import *  # noqa: F401,F403

import pytest
from PIL import Image

from easycad.canvas.start_prompt import guess_kind


@pytest.fixture(autouse=True)
def _no_real_gateway():
    """이 PC엔 실제 게이트웨이 키가 있다 — 「만들기」가 진짜 호출을 하지 않게 키 없음으로."""
    from unittest.mock import patch
    with patch("easycad.ai.gateway.resolve_api_key", return_value=""):
        yield


def _shown_window():
    w = CanvasWindow()
    w.resize(1400, 900)
    w.show()
    _app.processEvents()
    return w


def test_guess_kind_rules():
    assert guess_kind("휴가 신청 결재 흐름도", False) == "flow"
    assert guess_kind("방송용 카메라 아이콘", False) == "symbol"
    assert guess_kind("파라볼라 안테나 부품", False) == "symbol"
    assert guess_kind("", False) == "flow"
    assert guess_kind("", True) == "trace"                        # 사진만 = 모양 그대로
    assert guess_kind("이 사진의 관계만 흐름도로", True) == "flow"   # 사진 + 흐름·관계 = 다시 배치
    assert guess_kind("흐름도 그대로 베껴줘", True) == "trace"       # 베끼기 말이 이김


def test_shown_centered_on_empty_doc_and_gone_after_first_item():
    w = _shown_window()
    sp = w._start_prompt
    assert sp.isVisible()
    view_c = w._view.mapTo(w, w._view.rect().center())
    assert abs(sp.geometry().center().x() - view_c.x()) <= 2
    w._scene.addItem(_RectItem(QRectF(0, 0, 50, 30)))
    _app.processEvents()   # scene.changed는 다음 이벤트 루프에서
    assert not sp.isVisible()
    for it in list(w._scene.items()):
        w._scene.removeItem(it)
    _app.processEvents()
    assert not sp.isVisible(), "다 지워도 다시 안 뜸(숙련자를 귀찮게 하지 않음)"


def test_dismiss_is_per_doc_and_new_tab_shows_again():
    w = _shown_window()
    sp = w._start_prompt
    sp.dismissed.emit()
    assert not sp.isVisible()
    w._open_new_tab()
    _app.processEvents()
    assert sp.isVisible()
    w._tabs.setCurrentIndex(0)
    _app.processEvents()
    assert not sp.isVisible()


def test_hidden_while_ai_panel_open():
    w = _shown_window()
    sp = w._start_prompt
    w._set_ai_panel_visible(True)
    assert not sp.isVisible()
    w._set_ai_panel_visible(False)
    assert sp.isVisible()


def test_typing_guesses_kind_until_user_picks():
    w = _shown_window()
    sp = w._start_prompt
    sp._edit.setPlainText("카메라 아이콘")
    assert sp.kind() == "symbol"
    sp._edit.setPlainText("결재 흐름도")
    assert sp.kind() == "flow"
    sp._kind_actions["symbol"].trigger()   # 사용자가 버튼으로 고름
    sp._edit.setPlainText("결재 흐름도 다시")
    assert sp.kind() == "symbol", "고른 뒤엔 짐작이 덮어쓰지 않음"


def test_submit_flow_goes_to_panel_as_request():
    w = _shown_window()
    sp = w._start_prompt
    assert sp.submit() is None and not sp._notice.isHidden()   # 빈 입력은 안내만
    sp._edit.setPlainText("휴가 신청부터 결재까지 흐름도")
    assert sp.submit() == "flow"
    p = w._ai_panel
    assert p.isVisible() and p.kind() == "flow"
    assert len(p.entries()) == 1, "패널 기록에 요청 한 칸(생성 경로가 패널과 같음)"
    assert not sp.isVisible()
    assert sp._edit.toPlainText() == ""


def test_submit_trace_needs_photo_and_only_attaches_it():
    w = _shown_window()
    sp = w._start_prompt
    sp.set_kind("trace", manual=True)
    assert sp.submit() is None and "사진" in sp._notice.text()
    img = Image.new("RGB", (64, 48), "white")
    sp._set_attached_image(img, "drawing.png")
    assert sp.kind() == "trace"
    assert sp.submit() == "trace"
    p = w._ai_panel
    assert p.kind() == "trace" and p._attached_image is img
    assert len(p.entries()) == 0, "베끼기는 사진 위 막대 「만들기」로 진행(모서리 맞추기)"
    assert w._ai_trace is not None, "사진이 도면에 깔림"


def test_theme_toggle_keeps_prompt():
    w = _shown_window()
    w._toggle_theme()
    w._toggle_theme()
    assert w._start_prompt.isVisible()
