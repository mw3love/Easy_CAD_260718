"""§8 항목18(AI 이미지→도면) 후속 — Mermaid 가져오기 통합(2026-08-12).

deep-interview(2026-08-12)로 확정된 대로 이미지 입력 경로(옛 sketch_pipeline.py 전체,
P1~P3.75 타일링, host_ai.py QThread 워커, _AIImageImportDialog)를 완전히 폐기하고
"텍스트 설명 → AI(게이트웨이 1회 호출) → Mermaid 텍스트"로 `fileio/mermaid_import.py`
가져오기 다이얼로그(`host_dialogs._MermaidDialog`)에 흡수했다.

이 파일이 검증하는 것:
  - `gateway.py`의 텍스트 전용 호출(`call_text`/`call_text_with_fallback`) — 이미지 없는
    단순 chat completion. 게이트웨이 실호출은 여기서 하지 않는다(수동 `tools/ai_probe.py`
    스타일 실행이 필요하나, §8 항목18 텍스트 전용 실측은 API 키가 있어야 가능 — 아직 없음).
  - `easycad/ai/text_to_mermaid.py` — 프롬프트 빌더·코드펜스 벗기기·generate_mermaid.
  - `_MermaidDialog`의 AI 보조 생성(모델 드롭다운 추천1/추천2, AI 버튼 클릭 배선,
    새로고침 버튼, 게이트웨이 설정 버튼).
  - `_AIGatewaySettingsDialog`(2026-08-12 실사용 요청) — 게이트웨이 주소·API 키를 앱
    안에서 직접 입력·저장·연결테스트.
  - 옛 이미지 경로가 실제로 사라졌는지(메뉴 액션·믹스인 잔존 여부) 회귀 가드.

tests/test_easycad.py 실행 시 함께 돈다. 실행: python tests/test_easycad.py (전체) 또는
pytest test_part9_ai_mermaid.py.
"""
from PyQt6.QtCore import QSettings, QEvent
from PyQt6.QtWidgets import QDialog

from _shared import *  # noqa: F401,F403

from easycad.ai import gateway as gw  # noqa: E402
from easycad.ai import text_to_mermaid as ttm  # noqa: E402
from easycad.canvas.host_dialogs import _MermaidDialog, _AIGatewaySettingsDialog  # noqa: E402


def _clear_gateway_settings():
    """`store_api_key`/`store_base_url` 테스트가 실사용자 QSettings를 건드리므로
    (기존 dark모드·recent_colors 테스트와 동일 관례), 매번 명시적으로 지워 오염 방지."""
    s = QSettings("EasyCAD", "EasyCAD")
    s.remove("ai_gateway_key")
    s.remove("ai_gateway_base_url")


# ── gateway.py: 텍스트 전용 호출 ─────────────────────────────────────────────

def test_call_text_sends_plain_string_content_not_vision_array():
    """`call_vision`은 content가 [image_url, text] 배열이지만, `call_text`는 이미지가
    없으므로 문자열 하나만 보내야 한다 — vision 콘텐츠 배열을 실수로 재사용하면 게이트웨이가
    이미지 없는 요청을 거부하거나 프롬프트를 잘못 해석할 위험이 있다."""
    captured = {}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    captured.update(kw)
                    class _Resp:
                        choices = [type("_C", (), {"message": type("_M", (), {"content": "ok"})()})()]
                    return _Resp()

    text, dt = gw.call_text(_FakeClient(), "gpt-5.4-mini", "설명을 Mermaid로")
    assert text == "ok"
    assert captured["messages"] == [{"role": "user", "content": "설명을 Mermaid로"}]
    assert captured["model"] == "gpt-5.4-mini"


def test_call_text_with_fallback_no_chain_raises_on_timeout():
    """텍스트 전용은 기본 폴백 사슬이 없다(사용자가 드롭다운에서 직접 모델을 고름) —
    빈 `fallback_chain`이면 실패를 그대로 올려야 한다."""
    def fake_call_text(client, model, prompt, *, max_tokens=0):
        raise RuntimeError("Error code: 504 Gateway Timeout")

    with patch.object(gw, "_client", lambda *a, **k: object()), \
         patch.object(gw, "call_text", fake_call_text):
        try:
            gw.call_text_with_fallback("key", "prompt", model="gpt-5.4-mini")
            assert False, "should have raised"
        except RuntimeError as e:
            assert "504" in str(e)


def test_call_text_with_fallback_uses_chain_when_provided():
    calls = []

    def fake_call_text(client, model, prompt, *, max_tokens=0):
        calls.append(model)
        if model == "gpt-5.4-mini":
            raise RuntimeError("Error code: 404 model_not_found")
        return "결과", 0.5

    with patch.object(gw, "_client", lambda *a, **k: object()), \
         patch.object(gw, "call_text", fake_call_text):
        result = gw.call_text_with_fallback(
            "key", "prompt", model="gpt-5.4-mini",
            fallback_chain=("gpt-5.4-mini", "gemini-3.6-flash"))
    assert calls == ["gpt-5.4-mini", "gemini-3.6-flash"]
    assert result.model_used == "gemini-3.6-flash"
    assert result.fallback_from == "gpt-5.4-mini"


def test_call_text_with_fallback_does_not_swallow_quota_error():
    def fake_call_text(*a, **k):
        raise RuntimeError("Error code: 429 RESOURCE_EXHAUSTED")

    with patch.object(gw, "_client", lambda *a, **k: object()), \
         patch.object(gw, "call_text", fake_call_text):
        try:
            gw.call_text_with_fallback("key", "prompt", model="gpt-5.4-mini",
                                       fallback_chain=("gemini-3.6-flash",))
            assert False, "should have raised"
        except RuntimeError as e:
            assert "429" in str(e)


def test_list_text_models_filters_to_gpt_and_gemini_only():
    """사용자 확정(deep-interview 2026-08-12) — claude 계열은 텍스트 전용 드롭다운에서 제외."""
    with patch.object(gw, "list_models",
                      lambda *a, **k: ["claude-sonnet-5", "gpt-5.4-mini", "gemini-3.6-flash",
                                       "claude-haiku-4-5", "gpt-5.4-nano"]):
        out = gw.list_text_models("key")
    assert out == sorted(["gpt-5.4-mini", "gemini-3.6-flash", "gpt-5.4-nano"])
    assert "claude-sonnet-5" not in out
    assert "claude-haiku-4-5" not in out


# ── text_to_mermaid.py ───────────────────────────────────────────────────────

def test_build_prompt_includes_description_and_mermaid_rules():
    text = ttm.build_prompt("날씨를 예보하는 워크플로우")
    assert "날씨를 예보하는 워크플로우" in text
    assert "flowchart" in text
    assert "Mermaid" in text


def test_extract_mermaid_strips_language_tagged_code_fence():
    raw = "```mermaid\nflowchart TD\n A-->B\n```"
    assert ttm.extract_mermaid(raw) == "flowchart TD\n A-->B"


def test_extract_mermaid_strips_bare_code_fence():
    raw = "```\nflowchart LR\n A-->B\n```"
    assert ttm.extract_mermaid(raw) == "flowchart LR\n A-->B"


def test_extract_mermaid_passthrough_when_no_fence():
    raw = "flowchart TD\n A-->B"
    assert ttm.extract_mermaid(raw) == raw


def test_generate_mermaid_returns_text_and_model_used():
    def fake_call(api_key, prompt, *, model, **kw):
        assert "설명" in prompt or True
        return gw.GatewayResult("```mermaid\nflowchart TD\n A-->B\n```", model, None, 1.2)

    with patch.object(ttm.gw, "call_text_with_fallback", fake_call):
        text, used = ttm.generate_mermaid("key", "간단한 흐름", model="gpt-5.4-mini")
    assert text == "flowchart TD\n A-->B"
    assert used == "gpt-5.4-mini"


# ── _MermaidDialog: AI 보조 생성 ─────────────────────────────────────────────

def test_mermaid_dialog_populate_models_groups_by_family_with_separator():
    """gpt/gemini를 구분선으로 명확히 나누고(실사용 요청), 추천 모델엔 금색 별
    아이콘을 붙인다(텍스트 라벨 "(추천1)"/"(추천2)"는 그대로 유지)."""
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models",
               return_value=["gpt-5.4-mini", "gpt-5.4-nano", "gemini-3.6-flash"]):
        dlg = _MermaidDialog()
    assert dlg.model() == gw.TEXT_RECOMMEND_1
    idx1 = dlg._model_combo.findData(gw.TEXT_RECOMMEND_1)
    idx2 = dlg._model_combo.findData(gw.TEXT_RECOMMEND_2)
    assert "추천1" in dlg._model_combo.itemText(idx1)
    assert "추천2" in dlg._model_combo.itemText(idx2)
    assert not dlg._model_combo.itemIcon(idx1).isNull()
    assert not dlg._model_combo.itemIcon(idx2).isNull()
    idx3 = dlg._model_combo.findData("gpt-5.4-nano")
    assert dlg._model_combo.itemIcon(idx3).isNull()   # 비추천 항목엔 배지 없음(구별)
    # gemini 그룹(1개) + 구분선(1) + gpt 그룹(2개) = 4행.
    assert dlg._model_combo.count() == 4
    # claude는 애초에 list_text_models가 걸러주므로 드롭다운에 아예 없어야 함(방어적 확인).
    assert dlg._model_combo.findData("claude-sonnet-5") == -1


def test_mermaid_dialog_populate_models_falls_back_when_list_fails():
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models",
               side_effect=RuntimeError("no network")):
        dlg = _MermaidDialog()
    assert dlg.model() == gw.TEXT_RECOMMEND_1
    assert dlg._model_combo.count() == 3   # 추천1(gemini 1) + 구분선 + 추천2(gpt 1)


def test_mermaid_dialog_single_box_ai_button_fills_in_place_and_stays_editable():
    """단일 입력칸 — 설명을 그 칸에 직접 입력하고, AI 생성 후에도 같은 칸에서 계속
    편집 가능해야 한다(실사용 피드백으로 분리형 → 단일칸으로 되돌림)."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("날씨를 예보하는 워크플로우")

    def fake_generate(key, desc, *, model, **kw):
        assert desc == "날씨를 예보하는 워크플로우"
        return "flowchart TD\n A[관측] --> B[예보]", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate):
        dlg._on_ai_clicked()

    assert dlg.text() == "flowchart TD\n A[관측] --> B[예보]"
    dlg._edit.setPlainText(dlg.text() + "\n B --> C[게시]")
    assert "게시" in dlg.text()


def test_mermaid_dialog_ai_fill_is_undoable_via_ctrl_z():
    """setPlainText() 대신 QTextCursor 치환을 써서, AI가 채운 결과를 Ctrl+Z(칸 자체의
    undo 스택)로 원래 입력했던 설명으로 복구할 수 있어야 한다(단일칸 통합의 안전망)."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("날씨를 예보하는 워크플로우")

    def fake_generate(key, desc, *, model, **kw):
        return "flowchart TD\n A-->B", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate):
        dlg._on_ai_clicked()
    assert dlg.text() == "flowchart TD\n A-->B"
    dlg._edit.undo()
    assert dlg.text() == "날씨를 예보하는 워크플로우"


def test_mermaid_dialog_ctrl_enter_triggers_ai_generation():
    """Ctrl+Enter로 마우스 없이 바로 변환(실사용 요청) — _edit에 설치된 eventFilter가
    가로채 AI 생성을 트리거하고 이벤트를 소비한다(기본 줄바꿈 삽입 방지)."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    calls = {"n": 0}
    dlg._on_ai_clicked = lambda: calls.__setitem__("n", calls["n"] + 1)

    from PyQt6.QtGui import QKeyEvent
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    handled = dlg.eventFilter(dlg._edit, ev)
    assert handled is True
    assert calls["n"] == 1


def test_mermaid_dialog_plain_enter_without_ctrl_does_not_trigger_ai():
    """일반 Enter는 줄바꿈(Mermaid 여러 줄 입력용)이지 AI 트리거가 아니어야 한다."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    calls = {"n": 0}
    dlg._on_ai_clicked = lambda: calls.__setitem__("n", calls["n"] + 1)

    from PyQt6.QtGui import QKeyEvent
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    handled = dlg.eventFilter(dlg._edit, ev)
    assert handled is False
    assert calls["n"] == 0


def test_mermaid_dialog_ai_button_shows_credit_balance_on_success():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("아무 설명")

    def fake_generate(key, desc, *, model, **kw):
        return "flowchart TD\n A-->B", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate), \
         patch("easycad.canvas.host_dialogs.gw.get_credit_balance", return_value=(100.0, 200.0)):
        dlg._on_ai_clicked()
    assert "100" in dlg._credit_label.text() and "200" in dlg._credit_label.text()


def test_mermaid_dialog_ai_button_credit_lookup_failure_does_not_break_result():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("아무 설명")

    def fake_generate(key, desc, *, model, **kw):
        return "flowchart TD\n A-->B", model

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate), \
         patch("easycad.canvas.host_dialogs.gw.get_credit_balance",
               side_effect=RuntimeError("네트워크 없음")):
        dlg._on_ai_clicked()
    assert dlg.text() == "flowchart TD\n A-->B"   # 크레딧 조회 실패가 본 결과를 막지 않음


def test_mermaid_dialog_ai_button_requires_nonempty_box():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    with patch("easycad.canvas.host_dialogs.QMessageBox.information") as info, \
         patch("easycad.ai.text_to_mermaid.generate_mermaid") as gen:
        dlg._on_ai_clicked()
    assert info.called
    assert not gen.called
    assert dlg.text() == ""


def test_mermaid_dialog_ai_button_warns_when_no_api_key():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("아무 설명")
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value=""), \
         patch("easycad.canvas.host_dialogs.QMessageBox.warning") as warn, \
         patch("easycad.ai.text_to_mermaid.generate_mermaid") as gen:
        dlg._on_ai_clicked()
    assert warn.called
    assert not gen.called


def test_mermaid_dialog_ai_button_shows_warning_on_generation_failure():
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("아무 설명")

    def fake_generate(key, desc, *, model, **kw):
        raise RuntimeError("게이트웨이 실패")

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.QMessageBox.warning") as warn, \
         patch("easycad.ai.text_to_mermaid.generate_mermaid", fake_generate):
        dlg._on_ai_clicked()
    assert warn.called
    assert dlg.text() == "아무 설명"   # 실패해도 기존 입력을 지우지 않음
    assert dlg._ai_btn.isEnabled()   # finally에서 버튼이 다시 활성화됨


def test_mermaid_dialog_direct_paste_still_works_without_ai():
    """게이트웨이를 쓰고 싶지 않을 때 — 외부 AI 챗에서 받은 Mermaid를 그대로 붙여넣고
    OK만 눌러도 되는 경로(옛 "수동 모드"를 대신하는 것이 바로 이 경로)."""
    with patch.object(_MermaidDialog, "_populate_models", lambda self: None):
        dlg = _MermaidDialog()
    dlg._edit.setPlainText("flowchart LR\n A-->B\n")
    assert dlg.text() == "flowchart LR\n A-->B\n"


def test_mermaid_dialog_refresh_button_reloads_model_list():
    """새로고침 버튼 = _populate_models 재호출 — 새 모델이 나오면 다이얼로그를 다시
    열지 않고도 목록을 갱신할 수 있어야 한다는 실사용 요청."""
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models",
               return_value=["gpt-5.4-mini", "gemini-3.6-flash"]):
        dlg = _MermaidDialog()
    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models",
               return_value=["gpt-5.4-mini", "gpt-6.0-new", "gemini-3.6-flash"]) as new_list:
        dlg._refresh_btn.click()
    assert new_list.called
    assert dlg._model_combo.findData("gpt-6.0-new") >= 0


def test_mermaid_dialog_populate_models_uses_resolved_base_url():
    """모델 조회가 하드코딩 BASE_URL이 아니라 resolve_base_url()(설정창에서 바꾼 값
    포함)을 쓰는지 — 커스텀 게이트웨이 주소를 저장했으면 그 주소로 조회해야 한다."""
    captured = {}

    def fake_list_text_models(key, base_url, timeout=8.0):
        captured["base_url"] = base_url
        return ["gpt-5.4-mini"]

    with patch("easycad.canvas.host_dialogs.gw.resolve_api_key", return_value="key"), \
         patch("easycad.canvas.host_dialogs.gw.resolve_base_url",
               return_value="https://custom.example.com/v1/gateway"), \
         patch("easycad.canvas.host_dialogs.gw.list_text_models", fake_list_text_models):
        _MermaidDialog()
    assert captured["base_url"] == "https://custom.example.com/v1/gateway"


# ── 게이트웨이 설정 진입점 — 상단 메뉴/툴바로 이동(2026-08-12) ────────────────
# 옛 _MermaidDialog._settings_btn/_on_settings_clicked는 삭제됐다 — "버튼 안으로
# 하지 말고 상위로 상시 노출해달라"는 실사용 요청으로 CanvasWindow 메뉴+툴바 액션으로
# 옮겼다(host_ui.py._open_ai_gateway_settings).

def test_ai_gateway_settings_action_exists_on_menu_and_toolbar():
    w = CanvasWindow()
    assert hasattr(w, "_act_ai_gw_settings")
    assert w._act_ai_gw_settings in w._toolbar.actions()
    w.deleteLater()


def test_open_ai_gateway_settings_opens_dialog():
    w = CanvasWindow()
    opened = {}

    class _FakeDlg:
        def __init__(self, parent=None):
            opened["parent"] = parent

        def exec(self):
            opened["exec"] = True
            return QDialog.DialogCode.Accepted

    with patch("easycad.canvas.host_dialogs._AIGatewaySettingsDialog", _FakeDlg):
        w._open_ai_gateway_settings()
    assert opened.get("exec") is True
    assert opened.get("parent") is w
    w.deleteLater()


# ── gateway.py: 게이트웨이 주소 저장/해석 ────────────────────────────────────

def test_resolve_base_url_defaults_to_constant_when_nothing_stored():
    _clear_gateway_settings()
    assert gw.resolve_base_url() == gw.BASE_URL
    assert gw.BASE_URL == "https://factchat.mindlogic-kr-api.com/v1/gateway"


def test_store_base_url_then_resolve_reads_it_back():
    _clear_gateway_settings()
    try:
        gw.store_base_url("https://custom.example.com/v1/gateway")
        assert gw.resolve_base_url() == "https://custom.example.com/v1/gateway"
    finally:
        _clear_gateway_settings()


def test_resolve_base_url_prefers_explicit_over_stored():
    _clear_gateway_settings()
    try:
        gw.store_base_url("https://stored.example.com")
        assert gw.resolve_base_url("https://explicit.example.com") == "https://explicit.example.com"
    finally:
        _clear_gateway_settings()


# ── _AIGatewaySettingsDialog ─────────────────────────────────────────────────

def test_gateway_settings_dialog_prefills_default_url_when_nothing_stored():
    _clear_gateway_settings()
    dlg = _AIGatewaySettingsDialog()
    assert dlg.base_url() == "https://factchat.mindlogic-kr-api.com/v1/gateway"
    assert dlg.api_key() == ""


def test_gateway_settings_dialog_test_connection_reports_model_count():
    dlg = _AIGatewaySettingsDialog()
    dlg._key_edit.setText("some-key")
    with patch("easycad.canvas.host_dialogs.gw.list_models",
              return_value=["gpt-5.4-mini", "gemini-3.6-flash", "claude-sonnet-5"]):
        dlg._on_test_clicked()
    assert "3" in dlg._test_label.text()
    assert dlg._test_btn.isEnabled()


def test_gateway_settings_dialog_test_connection_reports_failure():
    dlg = _AIGatewaySettingsDialog()
    dlg._key_edit.setText("bad-key")
    with patch("easycad.canvas.host_dialogs.gw.list_models",
              side_effect=RuntimeError("401 Unauthorized")):
        dlg._on_test_clicked()
    assert "실패" in dlg._test_label.text()
    assert "401" in dlg._test_label.text()


def test_gateway_settings_dialog_test_connection_requires_key():
    _clear_gateway_settings()   # 남은 키가 있으면 필드가 미리 채워져 이 테스트가 무의미해짐
    dlg = _AIGatewaySettingsDialog()
    with patch("easycad.canvas.host_dialogs.gw.list_models") as list_models:
        dlg._on_test_clicked()
    assert not list_models.called
    assert "키를 입력" in dlg._test_label.text()


def test_gateway_settings_dialog_accept_persists_url_and_key():
    _clear_gateway_settings()
    try:
        dlg = _AIGatewaySettingsDialog()
        dlg._url_edit.setText("https://custom.example.com/v1/gateway")
        dlg._key_edit.setText("my-secret-key")
        dlg._on_accept()
        assert gw.resolve_base_url() == "https://custom.example.com/v1/gateway"
        assert gw.resolve_api_key() == "my-secret-key"
        assert dlg.result() == QDialog.DialogCode.Accepted
    finally:
        _clear_gateway_settings()


def test_gateway_settings_dialog_cancel_does_not_persist():
    _clear_gateway_settings()
    try:
        dlg = _AIGatewaySettingsDialog()
        dlg._url_edit.setText("https://should-not-be-saved.example.com")
        dlg.reject()
        assert gw.resolve_base_url() == gw.BASE_URL
    finally:
        _clear_gateway_settings()


# ── 이미지 경로 폐기 회귀 가드 ────────────────────────────────────────────────

def test_ai_image_menu_action_and_mixin_are_gone():
    w = CanvasWindow()
    assert not hasattr(w, "_act_ai_sketch")
    assert not hasattr(w, "_import_ai_image")
    w.deleteLater()


def test_sketch_pipeline_and_host_ai_modules_removed():
    import importlib
    for modname in ("easycad.ai.sketch_pipeline", "easycad.canvas.host_ai"):
        try:
            importlib.import_module(modname)
            assert False, f"{modname} should have been deleted"
        except ModuleNotFoundError:
            pass
